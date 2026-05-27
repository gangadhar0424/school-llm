"""
Evaluation runner — scores real student traffic (Q&A, summaries, quizzes)
plus teacher-generated assignment questions. All evaluations are
reference-free: the judge looks at the AI's actual output and (when
available) the source PDF context, without a curated "expected answer".

Concurrency: items are graded sequentially (one at a time). The judge
model is cheap but Mongo round-trips and rate limits make parallel
grading less useful than it sounds. Sequential keeps logs readable.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from evaluation.judge import judge_summary, judge_quiz_question
from evaluation.storage import save_run

logger = logging.getLogger(__name__)


async def run_evaluation_on_recent_qa(
    triggered_by: str,
    label: Optional[str] = None,
    limit: int = 20,
    user_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluate REAL student Q&A traffic (no golden-set / no expected
    answer). Pulls the most recent (question, AI answer) turns from
    `chat_sessions` and scores each one on faithfulness + answer relevance.

    Args:
        triggered_by: admin email kicking off the run
        label: optional human label for the run
        limit: max number of Q&A pairs to score (across all sessions)
        user_email: optional filter — only evaluate this user's sessions
    """
    from database import mongodb
    from evaluation.judge import judge_qa_pair_reference_free

    # Pull recent sessions, newest first. We grab more sessions than `limit`
    # because each session can contain multiple Q&A pairs (one per turn),
    # but we'll stop once we've collected `limit` pairs.
    query: Dict[str, Any] = {}
    if user_email:
        query["user_email"] = user_email

    cursor = (
        mongodb.db.chat_sessions.find(query)
        .sort("updated_at", -1)
        .limit(max(20, int(limit)))
    )
    sessions: List[Dict[str, Any]] = await cursor.to_list(length=None)

    # Walk through each session's messages, extracting (user, assistant) pairs.
    pairs: List[Dict[str, Any]] = []
    for sess in sessions:
        messages = sess.get("messages") or []
        pdf_ids = sess.get("pdf_ids") or []
        pdf_ref = pdf_ids[0] if pdf_ids else None
        owner_email = sess.get("user_email")
        # Walk messages so each user turn is paired with the next assistant turn
        i = 0
        while i < len(messages) - 1:
            m_user = messages[i]
            m_ai = messages[i + 1]
            if (m_user.get("role") == "user"
                    and m_ai.get("role") == "assistant"
                    and (m_ai.get("content") or "").strip()):
                pairs.append({
                    "question": m_user.get("content", ""),
                    "ai_answer": m_ai.get("content", ""),
                    "sources": m_ai.get("sources") or [],
                    "pdf_ref": pdf_ref,
                    "session_id": str(sess.get("_id")),
                    "session_name": sess.get("name", ""),
                    "user_email": owner_email,
                })
                if len(pairs) >= int(limit):
                    break
                i += 2
            else:
                i += 1
        if len(pairs) >= int(limit):
            break

    if not pairs:
        return {
            "error": (
                "No student Q&A traffic found yet. Have students ask questions "
                "in the Workspace tab first — those conversations are what gets "
                "evaluated here."
            ),
            "run_id": None,
        }

    from ai.llm_client import get_llm_client
    llm = get_llm_client()
    gen_model = getattr(llm, "generation_model", None) or "unknown"
    eval_model = getattr(llm, "evaluation_model", None) or "unknown"

    def _source_text(src: Any) -> str:
        """Sources can be either plain strings OR dicts (the qa system
        stores chunk objects with keys like 'text', 'content', 'chunk').
        Coerce both shapes into a usable string for the judge."""
        if isinstance(src, str):
            return src.strip()
        if isinstance(src, dict):
            for key in ("text", "content", "chunk", "page_content", "snippet"):
                v = src.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return ""

    results: List[Dict[str, Any]] = []
    total = len(pairs)
    logger.info(f"[eval/qa] starting — {total} Q&A pair(s) to score "
                f"(judge_model={eval_model})")
    for idx, p in enumerate(pairs, start=1):
        ctx_parts = []
        for s in (p["sources"] or []):
            txt = _source_text(s)
            if txt:
                ctx_parts.append(txt)
        context = "\n\n---\n\n".join(ctx_parts)

        q_preview = (p["question"] or "")[:60].replace("\n", " ")
        logger.info(f"[eval/qa] {idx}/{total} judging: {q_preview}")
        scores = await judge_qa_pair_reference_free(
            question=p["question"],
            ai_answer=p["ai_answer"],
            context=context,
        )
        if scores.error:
            logger.warning(f"[eval/qa] {idx}/{total} judge error: {scores.error}")
        else:
            logger.info(
                f"[eval/qa] {idx}/{total} scored — overall={scores.overall:.2f} "
                f"faithfulness={scores.faithfulness:.2f} "
                f"answer_relevance={scores.answer_relevance:.2f}"
            )
        # Adapt the ReferenceFreeScores schema to the same dict shape that
        # the storage layer + Admin UI expect. Keeps the runs table uniform.
        scores_dict = {
            "faithfulness": scores.faithfulness,
            "answer_relevance": scores.answer_relevance,
            "semantic_match": 0.0,  # not applicable — kept for schema parity
            "completeness": 0.0,    # not applicable
            "overall": scores.overall,
            "rationale": scores.rationale,
            "judge_model": scores.judge_model,
            "error": scores.error,
        }
        results.append({
            "question_id": p["session_id"],
            "question": p["question"],
            "expected_answer": "",  # n/a for reference-free
            "ai_answer": p["ai_answer"],
            "scores": scores_dict,
            "pdf_ref": p["pdf_ref"],
            "class_level": None,
            "subject": None,
            "judged_at": datetime.utcnow(),
            "session_id": p["session_id"],
            "session_name": p["session_name"],
            "user_email": p["user_email"],
        })

    run_id = await save_run(
        judge_model=eval_model,
        generation_model=gen_model,
        items=results,
        triggered_by=triggered_by,
        label=label or "Real Q&A traffic",
        eval_type="reference_free",
    )

    n = len(results)
    avg_overall = round(sum(r["scores"]["overall"] for r in results) / n, 4) if n else 0.0
    return {
        "run_id": run_id,
        "n_items": n,
        "avg_overall": avg_overall,
        "judge_model": eval_model,
        "generation_model": gen_model,
        "label": label or "Real Q&A traffic",
        "eval_type": "reference_free",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Summaries — pulls from generated_summaries (populated by /api/summarize)
# ─────────────────────────────────────────────────────────────────────────────
async def run_evaluation_on_summaries(
    triggered_by: str,
    label: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Evaluate the most recent AI-generated summaries against their source
    PDF excerpt. Scores faithfulness, completeness, semantic match."""
    from database import mongodb

    cursor = (
        mongodb.db.generated_summaries.find({})
        .sort("created_at", -1)
        .limit(max(1, int(limit)))
    )
    docs = await cursor.to_list(length=None)
    if not docs:
        return {
            "error": (
                "No persisted summaries found yet. Have students generate "
                "summaries from the Workspace tab first — those will then be "
                "available here for evaluation."
            ),
            "run_id": None,
        }

    from ai.llm_client import get_llm_client
    llm = get_llm_client()
    gen_model = getattr(llm, "generation_model", None) or "unknown"
    eval_model = getattr(llm, "evaluation_model", None) or "unknown"

    results: List[Dict[str, Any]] = []
    total = len(docs)
    logger.info(f"[eval/summary] starting — {total} summary/summaries to score "
                f"(judge_model={eval_model})")
    for idx, d in enumerate(docs, start=1):
        summary_text = d.get("content") or ""
        source_excerpt = d.get("source_excerpt") or ""
        logger.info(f"[eval/summary] {idx}/{total} judging ({d.get('summary_type','short')}) "
                    f"pdf={d.get('pdf_ref','?')}")
        scores = await judge_summary(summary_text, source_excerpt)
        if scores.error:
            logger.warning(f"[eval/summary] {idx}/{total} judge error: {scores.error}")
        else:
            logger.info(
                f"[eval/summary] {idx}/{total} scored — overall={scores.overall:.2f} "
                f"faithfulness={scores.faithfulness:.2f} "
                f"completeness={scores.completeness:.2f}"
            )
        results.append({
            "question_id": str(d.get("_id")),
            "question": f"Summary ({d.get('summary_type','short')})",
            "expected_answer": (source_excerpt[:300] + "…") if source_excerpt else "",
            "ai_answer": summary_text,
            "scores": scores.to_dict(),
            "pdf_ref": d.get("pdf_ref"),
            "class_level": None,
            "subject": None,
            "judged_at": datetime.utcnow(),
            "user_email": d.get("user_email"),
        })

    run_id = await save_run(
        judge_model=eval_model,
        generation_model=gen_model,
        items=results,
        triggered_by=triggered_by,
        label=label or "Student summaries",
        eval_type="summary",
    )
    n = len(results)
    avg = round(sum(r["scores"]["overall"] for r in results) / n, 4) if n else 0.0
    return {"run_id": run_id, "n_items": n, "avg_overall": avg,
            "judge_model": eval_model, "generation_model": gen_model,
            "label": label or "Student summaries", "eval_type": "summary"}


# ─────────────────────────────────────────────────────────────────────────────
# Student quizzes — pulls from generated_quizzes (populated by /api/quiz)
# Each generated quiz batch can have N questions — we judge each one.
# ─────────────────────────────────────────────────────────────────────────────
async def run_evaluation_on_quizzes(
    triggered_by: str,
    label: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Evaluate the most recent AI-generated quizzes. Judges each question
    individually on validity + correctness + faithfulness vs source PDF."""
    from database import mongodb

    # Pull recent quiz documents. `limit` here = number of quiz BATCHES to
    # evaluate; each batch has multiple questions which all get judged.
    cursor = (
        mongodb.db.generated_quizzes.find({})
        .sort("created_at", -1)
        .limit(max(1, int(limit)))
    )
    docs = await cursor.to_list(length=None)
    if not docs:
        return {
            "error": (
                "No persisted quizzes found yet. Have students generate "
                "quizzes from the Workspace tab first — those will then be "
                "available here for evaluation."
            ),
            "run_id": None,
        }

    from ai.llm_client import get_llm_client
    llm = get_llm_client()
    gen_model = getattr(llm, "generation_model", None) or "unknown"
    eval_model = getattr(llm, "evaluation_model", None) or "unknown"

    results: List[Dict[str, Any]] = []
    # Flatten upfront so we know the total count for nice progress logs.
    flat = [
        (d, q)
        for d in docs
        for q in (d.get("questions") or [])
        if (q.get("question") or q.get("text"))
    ]
    total = len(flat)
    logger.info(f"[eval/quiz] starting — {total} question(s) across "
                f"{len(docs)} quiz batch(es) (judge_model={eval_model})")
    for idx, (d, q) in enumerate(flat, start=1):
        source_excerpt = d.get("source_excerpt") or ""
        q_text = q.get("question") or q.get("text") or ""
        q_type = q.get("type") or d.get("question_type") or "short-answer"
        correct = q.get("correct_answer") or q.get("expected_answer") or ""
        options = q.get("options") or []
        logger.info(f"[eval/quiz] {idx}/{total} judging [{q_type}]: "
                    f"{q_text[:60].replace(chr(10),' ')}")
        scores = await judge_quiz_question(
            question=q_text,
            correct_answer=correct,
            q_type=q_type,
            options=options,
            context=source_excerpt,
        )
        if scores.error:
            logger.warning(f"[eval/quiz] {idx}/{total} judge error: {scores.error}")
        else:
            logger.info(
                f"[eval/quiz] {idx}/{total} scored — overall={scores.overall:.2f} "
                f"validity={scores.validity:.2f} correctness={scores.correctness:.2f} "
                f"faithfulness={scores.faithfulness:.2f}"
            )
        results.append({
                "question_id": str(d.get("_id")),
                "question": q_text,
                "expected_answer": correct,
                "ai_answer": ", ".join(options) if options else correct,
                "scores": scores.to_dict(),
                "pdf_ref": d.get("pdf_ref"),
                "class_level": None,
                "subject": None,
                "judged_at": datetime.utcnow(),
                "user_email": d.get("user_email"),
            })

    if not results:
        return {"error": "Found quiz documents but no scorable questions.", "run_id": None}

    run_id = await save_run(
        judge_model=eval_model,
        generation_model=gen_model,
        items=results,
        triggered_by=triggered_by,
        label=label or "Student quizzes",
        eval_type="quiz",
    )
    n = len(results)
    avg = round(sum(r["scores"]["overall"] for r in results) / n, 4) if n else 0.0
    return {"run_id": run_id, "n_items": n, "avg_overall": avg,
            "judge_model": eval_model, "generation_model": gen_model,
            "label": label or "Student quizzes", "eval_type": "quiz"}


# ─────────────────────────────────────────────────────────────────────────────
# Teacher AI-generated assignment questions — pulls from `assignments`.
# Each assignment has its own questions[] array; we judge each question.
# ─────────────────────────────────────────────────────────────────────────────
async def run_evaluation_on_teacher_questions(
    triggered_by: str,
    label: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Evaluate the most-recently-created assignments' questions. Same
    metrics as student quizzes (validity / correctness / faithfulness)
    but with no source-PDF context — teachers may have written manually
    or generated from a PDF we don't have a handle on."""
    from database import mongodb

    cursor = (
        mongodb.db.assignments.find({})
        .sort("created_at", -1)
        .limit(max(1, int(limit)))
    )
    docs = await cursor.to_list(length=None)
    if not docs:
        return {
            "error": (
                "No teacher assignments found yet. Teachers need to create "
                "an assignment (draft or published) before its questions can "
                "be evaluated."
            ),
            "run_id": None,
        }

    from ai.llm_client import get_llm_client
    llm = get_llm_client()
    gen_model = getattr(llm, "generation_model", None) or "unknown"
    eval_model = getattr(llm, "evaluation_model", None) or "unknown"

    results: List[Dict[str, Any]] = []
    flat = [
        (a, q)
        for a in docs
        for q in (a.get("questions") or [])
        if (q.get("question") or q.get("text"))
    ]
    total = len(flat)
    logger.info(f"[eval/teacher_question] starting — {total} question(s) across "
                f"{len(docs)} assignment(s) (judge_model={eval_model})")
    for idx, (a, q) in enumerate(flat, start=1):
        a_title = a.get("title") or ""
        a_subject = a.get("subject")
        q_text = q.get("question") or q.get("text") or ""
        q_type = q.get("type") or "short-answer"
        correct = q.get("expected_answer") or ""
        options = q.get("options") or []
        logger.info(f"[eval/teacher_question] {idx}/{total} judging [{q_type}]: "
                    f"{q_text[:60].replace(chr(10),' ')}")
        scores = await judge_quiz_question(
            question=q_text,
            correct_answer=correct,
            q_type=q_type,
            options=options,
            context="",  # teacher questions have no stored source excerpt
        )
        if scores.error:
            logger.warning(f"[eval/teacher_question] {idx}/{total} judge error: {scores.error}")
        else:
            logger.info(
                f"[eval/teacher_question] {idx}/{total} scored — "
                f"overall={scores.overall:.2f} validity={scores.validity:.2f} "
                f"correctness={scores.correctness:.2f}"
            )
        results.append({
            "question_id": f"{a.get('_id')}::{a_title[:30]}",
            "question": q_text,
            "expected_answer": correct,
            "ai_answer": ", ".join(options) if options else correct,
            "scores": scores.to_dict(),
            "pdf_ref": None,
            "class_level": q.get("target_class"),
            "subject": q.get("subject") or a_subject,
            "judged_at": datetime.utcnow(),
            "user_email": a.get("teacher_email") or a.get("created_by"),
        })

    if not results:
        return {"error": "Found assignments but no scorable questions.", "run_id": None}

    run_id = await save_run(
        judge_model=eval_model,
        generation_model=gen_model,
        items=results,
        triggered_by=triggered_by,
        label=label or "Teacher assignment questions",
        eval_type="teacher_question",
    )
    n = len(results)
    avg = round(sum(r["scores"]["overall"] for r in results) / n, 4) if n else 0.0
    return {"run_id": run_id, "n_items": n, "avg_overall": avg,
            "judge_model": eval_model, "generation_model": gen_model,
            "label": label or "Teacher assignment questions",
            "eval_type": "teacher_question"}

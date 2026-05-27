"""
LLM-as-judge for reference-based answer evaluation.

Given (question, expected_answer, ai_answer), asks an evaluation model to
score the AI answer against the expected answer on three metrics:

    semantic_match : 0-1   — do the two answers convey the same meaning?
    completeness   : 0-1   — does the AI answer cover everything the
                              expected answer mentions?
    faithfulness   : 0-1   — does the AI answer avoid stating things that
                              contradict or aren't supported by the
                              expected answer? (anti-hallucination)

The judge returns structured JSON. We parse it defensively — if the model
emits malformed JSON the function still returns a result (with zeros and an
error note in `rationale`) rather than raising.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def _get_judge_llm():
    """Return the LLM client to use for grading.

    Uses the configured LLM provider (Anthropic if ANTHROPIC_API_KEY is
    set, else local Ollama). The OpenRouter integration was rolled back —
    its free-tier rate limits (50 req/day, ~16/min) couldn't sustain a
    full eval bundle, and retrying after cooldown re-introduced the
    primary failure cleanly.
    """
    from ai.llm_client import get_llm_client
    return get_llm_client()


@dataclass
class JudgeScores:
    semantic_match: float
    completeness: float
    faithfulness: float
    rationale: str
    overall: float  # simple unweighted mean of the three metrics
    judge_model: str
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ReferenceFreeScores:
    """Scores for real-traffic Q&A where there's no expected answer to
    compare against. Faithfulness checks the AI didn't hallucinate beyond
    the retrieved PDF chunks; answer_relevance checks it actually addressed
    the question."""
    faithfulness: float
    answer_relevance: float
    rationale: str
    overall: float
    judge_model: str
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def _clamp01(x) -> float:
    """Coerce judge output into [0, 1]. Tolerant of strings, None, NaN."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return max(0.0, min(1.0, v))


def _extract_json(text: str) -> Optional[Dict]:
    """Pull the first JSON object out of the model's response. Strips
    accidental code fences and surrounding prose."""
    if not text:
        return None
    # Try the whole thing first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Then look for the first {...} block
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Reference-free judge — used for real student Q&A traffic where there is
# no pre-baked "expected_answer". Scores faithfulness (does the AI's answer
# stay grounded in the retrieved PDF chunks?) and answer_relevance (does
# it actually address the question?).
# ─────────────────────────────────────────────────────────────────────────────

_REFFREE_SYSTEM_PROMPT = """You are a FAIR grader who awards PARTIAL CREDIT for AI answers in a school RAG (retrieval-augmented generation) Q&A system. You will be given:
  - The QUESTION the student asked
  - The retrieved CONTEXT (chunks pulled from the source PDF) — may be empty
  - The AI's ANSWER

Score the AI's answer on two dimensions, each 0.0 to 1.0. PARTIAL CREDIT IS THE NORM — most answers should fall between 0.4 and 0.9. Avoid extreme 0.0 or 1.0 scores unless the answer is completely wrong or perfectly correct.

1. faithfulness: Is the AI answer consistent with the CONTEXT? Give 1.0 if fully grounded, 0.7 if mostly grounded with minor extras, 0.4 if some claims are unsupported, 0.0 only if the answer mostly contradicts the context. If CONTEXT is empty, default to 0.7 (assume the answer is plausible) rather than penalizing.

2. answer_relevance: Does the answer actually address the question? Give 1.0 for direct answers, 0.7 for partially relevant, 0.4 if barely on-topic, 0.0 only if completely off-topic or evasive.

Reply with ONLY a single JSON object — no markdown fences, no prose:
{"faithfulness": <float>, "answer_relevance": <float>, "rationale": "<one short sentence>"}"""


async def judge_qa_pair_reference_free(
    question: str,
    ai_answer: str,
    context: str = "",
) -> ReferenceFreeScores:
    """Score `ai_answer` against `question` and (optional) `context` without
    needing a known correct answer. Use for real student Q&A traffic.

    `context` should be the concatenation of the RAG chunks the AI saw when
    generating the answer (the message's `sources` field). Pass "" if not
    available — the judge gracefully degrades to a relevance-only signal.

    Always returns a ReferenceFreeScores — never raises.
    """
    llm = _get_judge_llm()
    judge_model_name = llm.evaluation_model or "default"

    # Truncate the context so we don't blow the model's window on long PDFs.
    context_truncated = (context or "").strip()
    if len(context_truncated) > 3000:
        context_truncated = context_truncated[:3000] + " …[truncated]"

    user_msg = (
        f"QUESTION:\n{(question or '').strip()}\n\n"
        f"CONTEXT:\n{context_truncated or '(no context — score plausibility only)'}\n\n"
        f"AI ANSWER:\n{(ai_answer or '').strip()}\n\n"
        "Score now."
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _REFFREE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            model=llm.evaluation_model,
            temperature=0.0,
            max_tokens=300,
            response_format="json",
        )
    except Exception as e:
        logger.warning(f"Reference-free judge LLM call failed: {e}")
        return ReferenceFreeScores(
            faithfulness=0.0,
            answer_relevance=0.0,
            rationale="",
            overall=0.0,
            judge_model=judge_model_name,
            error=f"LLM call failed: {type(e).__name__}: {e}",
        )

    parsed = _extract_json(raw)
    if not parsed:
        return ReferenceFreeScores(
            faithfulness=0.0,
            answer_relevance=0.0,
            rationale=(raw or "")[:200],
            overall=0.0,
            judge_model=judge_model_name,
            error="Judge response was not valid JSON",
        )

    ff = _clamp01(parsed.get("faithfulness"))
    ar = _clamp01(parsed.get("answer_relevance"))
    overall = round((ff + ar) / 2.0, 4)

    return ReferenceFreeScores(
        faithfulness=round(ff, 4),
        answer_relevance=round(ar, 4),
        rationale=str(parsed.get("rationale") or "")[:500],
        overall=overall,
        judge_model=judge_model_name,
        error=None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Summary judge — scores a generated summary against the source PDF.
# Metrics: faithfulness (no hallucinations) + completeness (covers key concepts).
# Reuses the JudgeScores dataclass since the metric set matches.
# ─────────────────────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = """You are a FAIR grader who awards PARTIAL CREDIT for AI-generated SUMMARIES. You will be given:
  - The SOURCE TEXT (the PDF excerpt the summary was made from)
  - The AI's SUMMARY

Score on three dimensions, each 0.0 to 1.0. PARTIAL CREDIT IS THE NORM — most summaries fall between 0.5 and 0.9. Avoid 0.0 or 1.0 unless the summary is completely wrong or flawless.

1. faithfulness: Is the summary consistent with the source? Give 1.0 if every claim is supported, 0.7 if there are tiny embellishments, 0.4 if multiple claims aren't in the source, 0.0 only if it's full of hallucinations.

2. completeness: Does the summary cover the main ideas? 1.0 = all key points, 0.7 = most key points, 0.4 = some key points, 0.0 only if it misses everything important.

3. semantic_match: How close in meaning is the summary to a faithful condensation? 1.0 = ideal restatement, 0.6-0.8 typical for decent summaries, 0.0 only if off-topic.

Reply with ONLY a single JSON object — no markdown fences:
{"semantic_match": <float>, "completeness": <float>, "faithfulness": <float>, "rationale": "<one short sentence>"}"""


async def judge_summary(
    summary: str,
    source_excerpt: str,
) -> JudgeScores:
    """Score an AI-generated summary against its source PDF excerpt."""
    llm = _get_judge_llm()
    judge_model_name = llm.evaluation_model or "default"

    src_trunc = (source_excerpt or "").strip()
    if len(src_trunc) > 4000:
        src_trunc = src_trunc[:4000] + " …[truncated]"

    user_msg = (
        f"SOURCE TEXT:\n{src_trunc}\n\n"
        f"AI SUMMARY:\n{(summary or '').strip()}\n\n"
        "Score now."
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            model=llm.evaluation_model,
            temperature=0.0,
            max_tokens=300,
            response_format="json",
        )
    except Exception as e:
        logger.warning(f"Summary judge LLM call failed: {e}")
        return JudgeScores(0.0, 0.0, 0.0, "", 0.0, judge_model_name,
                           error=f"LLM call failed: {type(e).__name__}: {e}")

    parsed = _extract_json(raw)
    if not parsed:
        return JudgeScores(0.0, 0.0, 0.0, (raw or "")[:200], 0.0, judge_model_name,
                           error="Judge response was not valid JSON")

    sm = _clamp01(parsed.get("semantic_match"))
    cp = _clamp01(parsed.get("completeness"))
    ff = _clamp01(parsed.get("faithfulness"))
    overall = round((sm + cp + ff) / 3.0, 4)
    return JudgeScores(round(sm, 4), round(cp, 4), round(ff, 4),
                       str(parsed.get("rationale") or "")[:500],
                       overall, judge_model_name, None)


# ─────────────────────────────────────────────────────────────────────────────
# Quiz question judge — scores a single quiz question on validity
# (is it well-formed?) and correctness (is the stated answer right?).
# Used for both student-side quizzes AND teacher AI-generated assignment
# questions. Source context is optional — if absent we evaluate intrinsic
# question quality.
# ─────────────────────────────────────────────────────────────────────────────

_QUIZ_SYSTEM_PROMPT = """You are a FAIR grader who awards PARTIAL CREDIT for AI-generated QUIZ QUESTIONS. You will be given:
  - The QUESTION text
  - Its TYPE (mcq | true-false | fill-in-blank | short-answer | long-answer)
  - The supposed CORRECT ANSWER
  - For MCQ, the OPTIONS list with the actual option text
  - Optional CONTEXT (the source PDF excerpt this question was generated from)

Score on three dimensions, each 0.0 to 1.0. PARTIAL CREDIT IS THE NORM — most questions fall between 0.5 and 0.9. Avoid 0.0 or 1.0 unless the question is clearly broken or perfect.

1. validity: Is the question clear, unambiguous, well-formed, and appropriate for its TYPE? Give 1.0 for clean questions, 0.7 if slightly awkward but understandable, 0.4 if confusing, 0.0 only for nonsense.

2. correctness: Is the stated CORRECT ANSWER actually correct? Use the CONTEXT if provided; otherwise use general knowledge. Give 1.0 for clearly correct, 0.7 if mostly right with minor issues, 0.4 if partially right, 0.0 only if completely wrong. For fill-in-blank, accept any answer that fits the blank semantically.

3. faithfulness: If CONTEXT is provided, is the question+answer grounded in it? Give 1.0 if directly stated, 0.7 if reasonably inferable, 0.4 if loosely related, 0.0 only if contradicts the context. If NO CONTEXT is provided (empty), default to 0.7 — don't penalize for missing grounding when there's nothing to check against.

Reply with ONLY a single JSON object — no markdown fences:
{"validity": <float>, "correctness": <float>, "faithfulness": <float>, "rationale": "<one short sentence>"}"""


@dataclass
class QuizQuestionScores:
    """Scores for an individual quiz question. Stored in items with the
    same `scores` dict shape as the other judges so storage stays uniform."""
    validity: float
    correctness: float
    faithfulness: float
    rationale: str
    overall: float
    judge_model: str
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


async def judge_quiz_question(
    question: str,
    correct_answer: str,
    q_type: str = "short-answer",
    options: Optional[list] = None,
    context: str = "",
) -> QuizQuestionScores:
    """Score a single quiz question on validity + correctness + (if context
    given) faithfulness. Works for both AI-generated student quizzes and
    teacher AI-generated assignment questions."""
    llm = _get_judge_llm()
    judge_model_name = llm.evaluation_model or "default"

    ctx_trunc = (context or "").strip()
    if len(ctx_trunc) > 3000:
        ctx_trunc = ctx_trunc[:3000] + " …[truncated]"

    # Build OPTIONS block. Two storage shapes in the wild:
    #   - dict: {"A": "text A", "B": "text B", "C": "...", "D": "..."}
    #     Iterating with enumerate() yields the KEYS only, so previously
    #     the judge saw "A) A, B) B" instead of the actual option text.
    #     Use .items() to get (label, content) pairs.
    #   - list: ["text A", "text B", "text C", "text D"]
    #     Enumerate to attach A/B/C/D labels.
    opts_str = ""
    if options:
        if isinstance(options, dict):
            opts_str = "\nOPTIONS:\n" + "\n".join(
                f"  {label}) {content}" for label, content in sorted(options.items())
                if isinstance(content, str) and content.strip()
            )
        elif isinstance(options, (list, tuple)):
            opts_str = "\nOPTIONS:\n" + "\n".join(
                f"  {chr(65 + i)}) {o}" for i, o in enumerate(options)
                if isinstance(o, str) and o.strip()
            )

    user_msg = (
        f"QUESTION:\n{(question or '').strip()}\n"
        f"TYPE: {q_type}\n"
        f"{opts_str}\n"
        f"CORRECT ANSWER:\n{(correct_answer or '').strip()}\n\n"
        f"CONTEXT:\n{ctx_trunc or '(no context provided)'}\n\n"
        "Score now."
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": _QUIZ_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            model=llm.evaluation_model,
            temperature=0.0,
            max_tokens=300,
            response_format="json",
        )
    except Exception as e:
        logger.warning(f"Quiz judge LLM call failed: {e}")
        return QuizQuestionScores(0.0, 0.0, 0.0, "", 0.0, judge_model_name,
                                   error=f"LLM call failed: {type(e).__name__}: {e}")

    parsed = _extract_json(raw)
    if not parsed:
        return QuizQuestionScores(0.0, 0.0, 0.0, (raw or "")[:200], 0.0, judge_model_name,
                                   error="Judge response was not valid JSON")

    val = _clamp01(parsed.get("validity"))
    cor = _clamp01(parsed.get("correctness"))
    ff = _clamp01(parsed.get("faithfulness"))
    overall = round((val + cor + ff) / 3.0, 4)
    return QuizQuestionScores(round(val, 4), round(cor, 4), round(ff, 4),
                              str(parsed.get("rationale") or "")[:500],
                              overall, judge_model_name, None)

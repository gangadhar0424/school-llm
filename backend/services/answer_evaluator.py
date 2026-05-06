"""
Hybrid Answer Evaluation Service.

Combines:
  1. Keyword-based scoring  (rule-based, fast, deterministic)
  2. Semantic evaluation     (LLM, slower, handles paraphrasing)

The hybrid decision rule:
  - If keyword match ratio >= 0.70  -> use keyword score
  - Else                              -> use semantic score
The other score is always returned alongside for transparency.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from services.grading_standards import (
    build_rubric_block,
    keyword_pass_ratio,
    get_band_for_class,
)

logger = logging.getLogger(__name__)


# Common English stopwords — ignored when comparing keyword presence in answers
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "for", "of", "to", "in", "on",
    "at", "by", "with", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "may", "might", "this", "that", "these", "those", "it",
    "its", "as", "from", "into", "about", "than", "then", "so", "such",
}


def _normalize_word(w: str) -> str:
    """Lowercase, strip surrounding punctuation, and apply a tiny stem."""
    out = w.strip().lower().strip("'\".,;:!?()[]{}")
    if len(out) > 4 and out.endswith("ies"):
        out = out[:-3] + "y"
    elif len(out) > 4 and out.endswith("es"):
        out = out[:-2]
    elif len(out) > 4 and out.endswith("s"):
        out = out[:-1]
    elif len(out) > 5 and out.endswith("ed"):
        out = out[:-2]
    elif len(out) > 5 and out.endswith("ing"):
        out = out[:-3]
    return out


def _tokenize(text: str) -> List[str]:
    """Split text into normalized tokens, dropping stopwords and short noise."""
    raw = re.findall(r"[A-Za-z][A-Za-z\-']+", text or "")
    out: List[str] = []
    for w in raw:
        n = _normalize_word(w)
        if not n or len(n) < 2 or n in _STOPWORDS:
            continue
        out.append(n)
    return out


def _phrase_in_answer(phrase: str, student_tokens: List[str], student_text_lower: str) -> bool:
    """Check whether a keyword/phrase is present in the student's answer.

    For single words: token match against the normalized token list.
    For multi-word phrases: substring match against the lowercased text.
    """
    phrase = (phrase or "").strip().lower()
    if not phrase:
        return False

    if " " in phrase:
        # Multi-word phrase — substring match (allow extra whitespace)
        normalized_phrase = re.sub(r"\s+", " ", phrase).strip()
        return normalized_phrase in student_text_lower

    norm = _normalize_word(phrase)
    if not norm:
        return False
    if norm in student_tokens:
        return True
    # Final fallback: substring (handles e.g. "atmosphere" vs "atmospheric")
    return norm[:5] in student_text_lower if len(norm) >= 5 else False


def keyword_match_score(student_answer: str, keywords: List[str]) -> Dict:
    """Compute keyword match: how many of `keywords` appear in `student_answer`."""
    keywords = [k for k in (keywords or []) if str(k).strip()]
    if not keywords:
        return {
            "matched": [],
            "missed": [],
            "matched_count": 0,
            "total": 0,
            "ratio": 0.0,
            "score_out_of_10": 0.0,
        }

    student_text = (student_answer or "")
    student_text_lower = student_text.lower()
    student_tokens = _tokenize(student_text)

    matched: List[str] = []
    missed: List[str] = []
    for kw in keywords:
        if _phrase_in_answer(kw, student_tokens, student_text_lower):
            matched.append(kw)
        else:
            missed.append(kw)

    total = len(keywords)
    ratio = len(matched) / total if total else 0.0
    return {
        "matched": matched,
        "missed": missed,
        "matched_count": len(matched),
        "total": total,
        "ratio": round(ratio, 3),
        "score_out_of_10": round(ratio * 10, 1),
    }


def _parse_semantic_response(raw: str) -> Dict:
    """Parse the LLM's structured evaluation response. Falls back to regex."""
    if not raw:
        return {
            "semantic_score_out_of_10": 0.0,
            "correct_points": [],
            "mistakes": [],
            "improvements": [],
            "correct_answer": "",
        }

    # First try JSON parse (we ask the model for JSON)
    try:
        # Strip code fences if present
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            score = data.get("score") or data.get("semantic_score") or 0
            score_str = str(score).strip()
            num = re.search(r"(\d+(?:\.\d+)?)", score_str)
            score_val = float(num.group(1)) if num else 0.0
            score_val = max(0.0, min(10.0, score_val))
            return {
                "semantic_score_out_of_10": round(score_val, 1),
                "correct_points": data.get("correct_points") or [],
                "mistakes": data.get("mistakes") or [],
                "improvements": data.get("improvements") or [],
                "correct_answer": str(data.get("correct_answer") or "").strip(),
            }
    except Exception:
        pass

    # Regex fallback: parse "Score: X/10" + the four sections
    def _block(label: str) -> List[str]:
        m = re.search(
            rf"{label}\s*:\s*(.*?)(?=(?:Score|Correct\s+Points|Mistakes|Improvements|Correct\s+Answer)\s*:|\Z)",
            raw, flags=re.IGNORECASE | re.DOTALL,
        )
        if not m:
            return []
        body = m.group(1).strip()
        items = [
            re.sub(r"^[\-\*•]\s*", "", line).strip()
            for line in body.splitlines() if line.strip()
        ]
        return [i for i in items if i]

    score_match = re.search(r"Score\s*:\s*(\d+(?:\.\d+)?)\s*/\s*10", raw, re.IGNORECASE)
    score_val = float(score_match.group(1)) if score_match else 0.0
    score_val = max(0.0, min(10.0, score_val))

    ca_match = re.search(r"Correct\s+Answer\s*:\s*(.+?)(?:\Z)", raw, re.IGNORECASE | re.DOTALL)
    correct_answer = ca_match.group(1).strip() if ca_match else ""

    return {
        "semantic_score_out_of_10": round(score_val, 1),
        "correct_points": _block("Correct\\s+Points"),
        "mistakes": _block("Mistakes"),
        "improvements": _block("Improvements"),
        "correct_answer": correct_answer,
    }


async def semantic_evaluate(
    question: str,
    expected_answer: str,
    student_answer: str,
    ollama_client,
    model: str,
    class_level: Optional[int] = None,
    subject: Optional[str] = None,
) -> Dict:
    """Ask the LLM to evaluate the student's answer.

    The grading rubric is selected based on `class_level` (Phase 2) and
    optionally fine-tuned by `subject` (Phase 6). The model is instructed
    to return JSON; we fall back to regex parsing.
    """
    rubric_block = build_rubric_block(class_level, subject)

    system_prompt = (
        "You are an experienced teacher who evaluates student answers fairly and constructively. "
        "Apply the grading standard below — DIFFERENT class levels have DIFFERENT expectations:\n\n"
        f"{rubric_block}\n\n"
        "Return ONLY a valid JSON object with this exact schema and no extra text:\n"
        '{\n'
        '  "score": <integer 0-10>,\n'
        '  "correct_points": [<short bullet strings>],\n'
        '  "mistakes": [<short bullet strings>],\n'
        '  "improvements": [<short bullet strings>],\n'
        '  "correct_answer": "<concise model answer in 1-3 sentences>"\n'
        '}'
    )
    user_prompt = (
        f"Question:\n{question.strip()}\n\n"
        f"Expected Answer:\n{expected_answer.strip()}\n\n"
        f"Student Answer:\n{student_answer.strip()}\n\n"
        "Evaluate the student's answer using the grading standard above. Return JSON only."
    )

    try:
        raw = await ollama_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=model,
            temperature=0.2,
            max_tokens=600,
            response_format="json",
            extra_options={"num_ctx": 2048},
        )
    except Exception as e:
        logger.warning(f"Semantic evaluation LLM call failed: {e}")
        return _parse_semantic_response("")

    return _parse_semantic_response(raw)


async def hybrid_evaluate(
    question: str,
    expected_answer: str,
    keywords: List[str],
    student_answer: str,
    ollama_client,
    model: str,
    class_level: Optional[int] = None,
    subject: Optional[str] = None,
) -> Dict:
    """End-to-end hybrid evaluation. Returns the structured result.

    `class_level` (1-10) selects the grading band (Phase 2). `subject`
    layers on subject-specific instructions (Phase 6). Both are optional;
    omitting them falls back to a default band that keeps current behavior.
    """
    question = (question or "").strip()
    expected_answer = (expected_answer or "").strip()
    student_answer = (student_answer or "").strip()

    band = get_band_for_class(class_level)
    pass_ratio = keyword_pass_ratio(class_level)

    if not student_answer:
        return {
            "score_out_of_10": 0.0,
            "method": "none",
            "grading_band": band.get("id"),
            "grading_band_label": band.get("label"),
            "class_level": class_level,
            "subject": subject,
            "keyword_score": keyword_match_score("", keywords or []),
            "semantic_score": {
                "semantic_score_out_of_10": 0.0,
                "correct_points": [], "mistakes": [], "improvements": [],
                "correct_answer": expected_answer,
            },
            "correct_points": [],
            "mistakes": ["Student answer is empty."],
            "improvements": ["Provide an answer to the question."],
            "correct_answer": expected_answer,
        }

    # Always compute keyword score (cheap)
    kw = keyword_match_score(student_answer, keywords or [])

    # Run semantic evaluation if we have a question + expected answer
    if question and expected_answer:
        sem = await semantic_evaluate(
            question, expected_answer, student_answer,
            ollama_client, model,
            class_level=class_level, subject=subject,
        )
    else:
        sem = {
            "semantic_score_out_of_10": 0.0,
            "correct_points": [], "mistakes": [], "improvements": [],
            "correct_answer": expected_answer or "",
        }

    # Hybrid decision — keyword threshold is now per-band
    kw_ratio = kw["ratio"]
    if kw["total"] >= 1 and kw_ratio >= pass_ratio:
        final_score = kw["score_out_of_10"]
        method = "keyword"
    elif question and expected_answer:
        final_score = sem["semantic_score_out_of_10"]
        method = "semantic"
    elif kw["total"] >= 1:
        final_score = kw["score_out_of_10"]
        method = "keyword"
    else:
        final_score = 0.0
        method = "none"

    return {
        "score_out_of_10": round(final_score, 1),
        "method": method,
        "grading_band": band.get("id"),
        "grading_band_label": band.get("label"),
        "class_level": class_level,
        "subject": subject,
        "keyword_pass_ratio": pass_ratio,
        "keyword_score": kw,
        "semantic_score": sem,
        "correct_points": sem.get("correct_points", []),
        "mistakes": sem.get("mistakes", []),
        "improvements": sem.get("improvements", []),
        "correct_answer": sem.get("correct_answer") or expected_answer or "",
    }


# Helpers to parse the AI-Features-generated copyable text -------------------

_QUESTION_BLOCK_RE = re.compile(
    r"^\s*Q\s*\d+\.?\s*",  # leading Q1. / Q2.
    re.MULTILINE,
)


def parse_question_blocks(copyable_text: str) -> List[Dict]:
    """Parse the AI Features 'Copyable text' format into a list of dicts.

    Format expected (loosely):
        Q1. <question text>
            Answer: <text>
            Keywords: <comma-separated>
            Explanation: <text>
            Class: <1-10>           (optional, Phase 4)
            Subject: <subject>      (optional, Phase 6)
        Q2. ...
    """
    if not copyable_text:
        return []

    text = copyable_text.replace("\r\n", "\n")
    parts = re.split(r"\n(?=\s*Q\s*\d+[\.)]\s)", "\n" + text)
    blocks: List[Dict] = []
    LABELS = ("Answer", "Keywords", "Explanation", "Class", "Subject")
    label_alt = "|".join(LABELS)

    for raw in parts:
        raw = raw.strip()
        if not raw:
            continue
        m = re.match(r"\s*Q\s*\d+[\.)]\s*(.*)", raw, re.DOTALL)
        if not m:
            continue
        body = m.group(1)

        question = ""
        answer = ""
        keywords_line = ""
        explanation = ""
        target_class: Optional[int] = None
        subject: str = ""

        first_label_match = re.search(
            rf"^\s*(?:{label_alt})\s*:",
            body, re.IGNORECASE | re.MULTILINE,
        )
        if first_label_match:
            question = body[:first_label_match.start()].strip()
        else:
            question = body.strip()

        for label in LABELS:
            sec_re = re.search(
                rf"^\s*{label}\s*:\s*(.+?)(?=^\s*(?:{label_alt})\s*:|\Z)",
                body, re.IGNORECASE | re.MULTILINE | re.DOTALL,
            )
            if not sec_re:
                continue
            value = sec_re.group(1).strip()
            if label == "Answer":
                answer = value
            elif label == "Keywords":
                keywords_line = value
            elif label == "Explanation":
                explanation = value
            elif label == "Class":
                m_cls = re.search(r"\d+", value)
                if m_cls:
                    try:
                        target_class = max(1, min(10, int(m_cls.group(0))))
                    except ValueError:
                        target_class = None
            elif label == "Subject":
                # take first non-empty token (strip trailing punctuation)
                subject = value.split("\n", 1)[0].strip().strip(".")

        keywords = [
            k.strip() for k in re.split(r"[,;|]", keywords_line)
            if k.strip()
        ]

        if not question:
            continue
        block = {
            "question": question,
            "expected_answer": answer,
            "keywords": keywords,
            "explanation": explanation,
        }
        if target_class is not None:
            block["target_class"] = target_class
        if subject:
            block["subject"] = subject
        blocks.append(block)

    return blocks

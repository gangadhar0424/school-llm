"""
Grade-aware grading standards (Phase 2 + Phase 6).

Loads `grading_standards.json` once at import and exposes helpers that the
evaluator uses to:
  - Pick the right grading band for a class level (1-10)
  - Build the rubric block injected into the LLM prompt
  - Get the keyword-pass ratio threshold for a band
  - Layer on subject-specific instructions (Phase 6)

This keeps grading rules in CONFIG, not code — so adding a new band, a new
subject, or tweaking strictness is a JSON edit, not a redeploy.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_STANDARDS_PATH = Path(__file__).parent / "grading_standards.json"


def _load_standards() -> Dict:
    try:
        with open(_STANDARDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "bands" not in data:
            raise ValueError("grading_standards.json missing 'bands' key")
        return data
    except FileNotFoundError:
        logger.warning(f"grading_standards.json not found at {_STANDARDS_PATH}; using fallback")
        return _FALLBACK
    except Exception as e:
        logger.error(f"Failed to load grading_standards.json: {e}; using fallback")
        return _FALLBACK


# Minimal fallback so the system never crashes if the JSON is missing/corrupt
_FALLBACK: Dict = {
    "version": "fallback",
    "bands": [{
        "id": "default",
        "label": "Default (no class-aware tuning)",
        "class_min": 1, "class_max": 10,
        "keyword_pass_ratio": 0.7,
        "expected_min_chars": 30, "expected_max_chars": 600,
        "spelling_weight": 0.15,
        "vocab_tolerance": "medium",
        "partial_credit_generosity": "medium",
        "feedback_tone": "constructive",
        "rubric_instructions": [
            "Score the student answer 0-10 based on accuracy, completeness, and clarity.",
            "Be fair and provide actionable feedback.",
        ],
    }],
    "subjects": {},
}


_STANDARDS = _load_standards()


def reload_standards() -> Dict:
    """Re-read the JSON from disk. Useful for tuning without restarting the server."""
    global _STANDARDS
    _STANDARDS = _load_standards()
    return _STANDARDS


def get_all_bands() -> List[Dict]:
    return list(_STANDARDS.get("bands") or [])


def get_band_for_class(class_level: Optional[int]) -> Dict:
    """Return the grading band whose class_min..class_max contains class_level.
    Falls back to the first band (or the fallback default) if class_level is None
    or out of range."""
    if class_level is None:
        return _STANDARDS["bands"][0]
    try:
        cl = int(class_level)
    except (TypeError, ValueError):
        return _STANDARDS["bands"][0]
    for band in _STANDARDS.get("bands", []):
        if int(band.get("class_min", 1)) <= cl <= int(band.get("class_max", 10)):
            return band
    # Out of range — clamp to nearest band
    bands = _STANDARDS.get("bands", [])
    if not bands:
        return _FALLBACK["bands"][0]
    if cl < int(bands[0].get("class_min", 1)):
        return bands[0]
    return bands[-1]


def get_subject_instructions(subject: Optional[str]) -> List[str]:
    """Return extra instructions specific to a subject (Phase 6).
    Returns [] if subject is None or not configured."""
    if not subject:
        return []
    subj_cfg = (_STANDARDS.get("subjects") or {}).get(subject) or {}
    return list(subj_cfg.get("extra_instructions") or [])


def build_rubric_block(class_level: Optional[int], subject: Optional[str] = None) -> str:
    """Compose the rubric instructions text injected into the evaluator's
    system prompt. Returns a multi-line string.

    Format:
        GRADING STANDARD: <Band Label>
        - <instruction 1>
        - <instruction 2>
        ...
        SUBJECT FOCUS (<subject>):  ← only if subject given
        - <subject-specific instruction>
        FEEDBACK TONE: <tone>
    """
    band = get_band_for_class(class_level)
    lines: List[str] = []
    lines.append(f"GRADING STANDARD: {band.get('label', 'Default')}")
    lines.append(
        f"(Vocab tolerance: {band.get('vocab_tolerance', 'medium')}; "
        f"partial-credit generosity: {band.get('partial_credit_generosity', 'medium')})"
    )
    for instr in band.get("rubric_instructions", []):
        lines.append(f"- {instr}")

    subj_extra = get_subject_instructions(subject)
    if subj_extra:
        lines.append("")
        lines.append(f"SUBJECT FOCUS ({subject}):")
        for instr in subj_extra:
            lines.append(f"- {instr}")

    lines.append("")
    lines.append(f"FEEDBACK TONE: {band.get('feedback_tone', 'constructive')}")
    return "\n".join(lines)


def keyword_pass_ratio(class_level: Optional[int]) -> float:
    """Threshold above which the keyword score (rather than semantic) is
    used as the final score in hybrid mode."""
    band = get_band_for_class(class_level)
    try:
        return float(band.get("keyword_pass_ratio", 0.7))
    except (TypeError, ValueError):
        return 0.7

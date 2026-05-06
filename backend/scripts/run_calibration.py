"""
Calibration runner (Phase 5).

Compares the AI grader's scores against human-assigned scores on the
calibration set. Prints a per-sample diff table and overall summary stats.

Usage (from project root):
    python -m backend.scripts.run_calibration
    python -m backend.scripts.run_calibration --provider anthropic
    python -m backend.scripts.run_calibration --tolerance 1.5
    python -m backend.scripts.run_calibration --filter primary

Exit code is 0 if every sample is within `--tolerance` of the human score,
non-zero otherwise — so this script can be wired into CI.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Dict, List

# Make the `backend` package importable when run from the project root
HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parent
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

CALIBRATION_PATH = BACKEND_ROOT / "calibration_data" / "calibration_set.json"


def _load_samples() -> List[Dict]:
    with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    samples = data.get("samples", [])
    if not isinstance(samples, list):
        raise ValueError("calibration_set.json must contain a 'samples' list")
    return samples


def _band_id_for(class_level: int) -> str:
    if class_level <= 3:
        return "primary"
    if class_level <= 5:
        return "upper_primary"
    if class_level <= 8:
        return "middle"
    return "secondary"


async def _evaluate_sample(sample: Dict) -> Dict:
    """Run the evaluator on one sample and return {ai_score, method, band, ...}."""
    from services.answer_evaluator import hybrid_evaluate
    try:
        from ai.llm_client import get_llm_client
        llm = get_llm_client()
    except Exception:
        from ai.ollama_client import ollama_client as llm
    from config import settings

    result = await hybrid_evaluate(
        question=sample.get("question", ""),
        expected_answer=sample.get("expected_answer", ""),
        keywords=sample.get("keywords", []) or [],
        student_answer=sample.get("student_answer", ""),
        ollama_client=llm,
        model=settings.OLLAMA_CHAT_MODEL,
        class_level=sample.get("class_level"),
        subject=sample.get("subject"),
    )
    return {
        "id": sample.get("id"),
        "class_level": sample.get("class_level"),
        "subject": sample.get("subject"),
        "human_score": float(sample.get("human_score") or 0),
        "ai_score": float(result.get("score_out_of_10") or 0),
        "method": result.get("method"),
        "band": result.get("grading_band"),
        "diff": float(result.get("score_out_of_10") or 0) - float(sample.get("human_score") or 0),
    }


def _print_table(rows: List[Dict], tolerance: float) -> None:
    header = (
        f"{'ID':<22} {'Class':>5} {'Subject':<10} "
        f"{'Human':>6} {'AI':>6} {'Diff':>7} {'Method':<10} {'Band':<14} {'OK':>3}"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        ok = "✓" if abs(r["diff"]) <= tolerance else "✗"
        print(
            f"{str(r['id']):<22} {str(r['class_level']):>5} "
            f"{str(r['subject'] or '-'):<10} "
            f"{r['human_score']:>6.1f} {r['ai_score']:>6.1f} "
            f"{r['diff']:>+7.2f} {str(r['method'] or '-'):<10} "
            f"{str(r['band'] or '-'):<14} {ok:>3}"
        )


def _print_summary(rows: List[Dict], tolerance: float) -> None:
    print()
    print("=" * 60)
    diffs = [r["diff"] for r in rows]
    abs_diffs = [abs(d) for d in diffs]
    pass_count = sum(1 for d in abs_diffs if d <= tolerance)

    print(f"Samples evaluated      : {len(rows)}")
    print(f"Pass (|diff| <= {tolerance:>3}) : {pass_count} / {len(rows)}  ({100*pass_count/max(1,len(rows)):.0f}%)")
    print(f"Mean abs diff          : {statistics.mean(abs_diffs):.2f}")
    if len(abs_diffs) >= 2:
        print(f"Stdev abs diff         : {statistics.stdev(abs_diffs):.2f}")
    print(f"Max overshoot (AI>H)   : {max(diffs):+.2f}")
    print(f"Max undershoot (AI<H)  : {min(diffs):+.2f}")

    # Per-band breakdown
    print()
    print("Per-band breakdown:")
    bands: Dict[str, List[float]] = {}
    for r in rows:
        bands.setdefault(r["band"] or "—", []).append(r["diff"])
    for band, diffs_b in sorted(bands.items()):
        abs_b = [abs(d) for d in diffs_b]
        passes = sum(1 for d in abs_b if d <= tolerance)
        print(
            f"  {band:<14} n={len(diffs_b):>2}   "
            f"pass={passes}/{len(diffs_b)}  "
            f"mean|d|={statistics.mean(abs_b):.2f}  "
            f"bias={statistics.mean(diffs_b):+.2f}"
        )

    print("=" * 60)


async def _main_async(args: argparse.Namespace) -> int:
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider

    samples = _load_samples()
    if args.filter:
        # filter on band id keyword (e.g. "primary" matches "primary" and "upper_primary")
        f = args.filter.lower()
        samples = [
            s for s in samples
            if f in _band_id_for(int(s.get("class_level") or 1)).lower()
            or f in (s.get("id") or "").lower()
            or f == (s.get("subject") or "").lower()
        ]

    if not samples:
        print("No calibration samples to run after filtering.")
        return 1

    print(f"Running {len(samples)} sample(s) "
          f"with provider={os.environ.get('LLM_PROVIDER', 'ollama')} "
          f"tolerance=±{args.tolerance}")
    print()

    rows: List[Dict] = []
    for i, s in enumerate(samples, 1):
        try:
            row = await _evaluate_sample(s)
        except Exception as e:
            print(f"  [{i}/{len(samples)}] {s.get('id')}: FAILED — {e}")
            continue
        rows.append(row)
        ok = "✓" if abs(row["diff"]) <= args.tolerance else "✗"
        print(f"  [{i}/{len(samples)}] {row['id']}: AI={row['ai_score']:.1f} "
              f"H={row['human_score']:.1f} d={row['diff']:+.2f} {ok}")

    if not rows:
        print("All evaluations failed.")
        return 1

    print()
    _print_table(rows, args.tolerance)
    _print_summary(rows, args.tolerance)

    # Optionally write a JSON report
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"tolerance": args.tolerance, "rows": rows}, f, indent=2)
        print(f"\nReport written to: {out}")

    failed = sum(1 for r in rows if abs(r["diff"]) > args.tolerance)
    return 0 if failed == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Run grading calibration.")
    parser.add_argument(
        "--provider", choices=["ollama", "anthropic"],
        help="Override LLM_PROVIDER env var for this run.",
    )
    parser.add_argument(
        "--tolerance", type=float, default=1.0,
        help="A sample passes if |AI - human| <= tolerance (default: 1.0).",
    )
    parser.add_argument(
        "--filter", type=str, default="",
        help="Filter samples by band ('primary', 'middle' …), id substring, or subject.",
    )
    parser.add_argument(
        "--report", type=str, default="",
        help="Optional: write JSON report to this path.",
    )
    args = parser.parse_args()
    rc = asyncio.run(_main_async(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()

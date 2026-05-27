"""
MongoDB persistence for evaluation runs.

Two collections:

    evaluation_runs   — one document per evaluation batch (a "run").
                        Holds aggregate scores, judge model, item count,
                        and a creation timestamp.

    evaluation_items  — one document per (question, expected, ai_answer,
                        scores) tuple. Belongs to a run via `run_id`.

Why two collections? The run document is small and fast to list (for the
admin dashboard's overview). The items collection holds the heavy detail
and is fetched on demand when drilling into a single run.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from database import mongodb


async def save_run(
    judge_model: str,
    generation_model: Optional[str],
    items: List[Dict[str, Any]],
    triggered_by: str,
    label: Optional[str] = None,
    eval_type: str = "reference_free",
) -> str:
    """Persist a completed evaluation run and its items. Returns the run id.

    `items` is a list of dicts with keys:
        question, expected_answer, ai_answer, scores (dict), pdf_ref,
        class_level, subject, judged_at

    `eval_type` is either:
        "reference_free"  — real student Q&A; uses faithfulness + answer_relevance
        "reference"       — golden-set; uses semantic_match + completeness + faithfulness
    Stored at the run level so the dashboard can render appropriate columns.
    """
    now = datetime.utcnow()

    n = len(items)
    if n:
        def _avg(key: str) -> float:
            return sum(it.get("scores", {}).get(key, 0.0) for it in items) / n
        avg_overall = _avg("overall")
        avg_semantic = _avg("semantic_match")
        avg_completeness = _avg("completeness")
        avg_faithfulness = _avg("faithfulness")
        avg_answer_relevance = _avg("answer_relevance")
        # Quiz/teacher-question runs also surface these:
        avg_validity = _avg("validity")
        avg_correctness = _avg("correctness")
        n_errors = sum(1 for it in items if it.get("scores", {}).get("error"))
    else:
        avg_overall = avg_semantic = avg_completeness = avg_faithfulness = avg_answer_relevance = 0.0
        avg_validity = avg_correctness = 0.0
        n_errors = 0

    run_doc = {
        "label": label or now.strftime("Eval %Y-%m-%d %H:%M"),
        "eval_type": eval_type,
        "judge_model": judge_model,
        "generation_model": generation_model,
        "triggered_by": triggered_by,
        "created_at": now,
        "n_items": n,
        "n_errors": n_errors,
        "avg_overall": round(avg_overall, 4),
        "avg_semantic_match": round(avg_semantic, 4),
        "avg_completeness": round(avg_completeness, 4),
        "avg_faithfulness": round(avg_faithfulness, 4),
        "avg_answer_relevance": round(avg_answer_relevance, 4),
        "avg_validity": round(avg_validity, 4),
        "avg_correctness": round(avg_correctness, 4),
    }
    result = await mongodb.db.evaluation_runs.insert_one(run_doc)
    run_id = str(result.inserted_id)

    # Save items in one batch (a single bulk insert is much faster than
    # one insert per item on a remote Mongo).
    item_docs = []
    for it in items:
        item_docs.append({
            "run_id": run_id,
            "question_id": it.get("question_id"),
            "question": it.get("question"),
            "expected_answer": it.get("expected_answer"),
            "ai_answer": it.get("ai_answer"),
            "scores": it.get("scores", {}),
            "pdf_ref": it.get("pdf_ref"),
            "class_level": it.get("class_level"),
            "subject": it.get("subject"),
            "judged_at": it.get("judged_at") or now,
        })
    if item_docs:
        await mongodb.db.evaluation_items.insert_many(item_docs)

    return run_id


async def list_runs(limit: int = 30) -> List[Dict[str, Any]]:
    """Return the most recent runs (overview cards on the admin dashboard).
    Newest first. Excludes the items themselves for speed."""
    cursor = (
        mongodb.db.evaluation_runs.find({})
        .sort("created_at", -1)
        .limit(int(limit))
    )
    runs = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("created_at"), datetime):
            doc["created_at"] = doc["created_at"].isoformat()
        runs.append(doc)
    return runs


async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Single run by id. Doesn't include items — fetch those separately."""
    from bson import ObjectId
    try:
        oid = ObjectId(run_id)
    except Exception:
        return None
    doc = await mongodb.db.evaluation_runs.find_one({"_id": oid})
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    if isinstance(doc.get("created_at"), datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


async def list_run_items(run_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    """Per-question detail for a single run. Used to render the drill-down
    table in the admin dashboard."""
    cursor = (
        mongodb.db.evaluation_items.find({"run_id": run_id})
        .sort("judged_at", 1)
        .limit(int(limit))
    )
    items = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        if isinstance(doc.get("judged_at"), datetime):
            doc["judged_at"] = doc["judged_at"].isoformat()
        items.append(doc)
    return items

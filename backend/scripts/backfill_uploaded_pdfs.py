"""
One-shot migration for legacy ``uploaded_pdfs`` documents.

Older versions of ``log_upload`` persisted only a thin shape:
    filename - file_size - uploader_email - upload_date - pdf_identifier
    - stored_filename

Newer code expects additional derived fields:
    total_pages - total_chunks - total_chars

The frontend also reads ``uploaded_at`` even though the field on disk
is named ``upload_date`` -- most recently-introduced response models
canonicalize that name, but this script optionally copies the value
into a parallel ``uploaded_at`` field for direct Mongo consumers.

What this script does
---------------------
For every document in ``uploaded_pdfs``:
  * adds ``total_pages``, ``total_chunks``, ``total_chars`` with
    default ``0`` if missing
  * adds ``file_size: 0`` if missing
  * adds ``uploader_email: ""`` if missing
  * derives ``upload_date`` from the ObjectId timestamp when both
    ``upload_date`` and ``uploaded_at`` are missing
  * copies ``upload_date`` -> ``uploaded_at`` so direct Mongo queries
    can use either name

With ``--recover-from-disk`` it also:
  * re-opens the PDF (if ``stored_filename`` resolves under
    ``settings.UPLOAD_DIR``) to recover real ``file_size`` and
    ``total_pages``. Slow on large libraries; safe to skip.

Usage
-----
From the project root:

    python -m backend.scripts.backfill_uploaded_pdfs              # apply
    python -m backend.scripts.backfill_uploaded_pdfs --dry-run    # preview
    python -m backend.scripts.backfill_uploaded_pdfs --recover-from-disk

Idempotent -- running twice on the same database is a no-op on the
second pass because every conditional `$set` is keyed on missing
fields.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Make `backend/` importable when invoked as a module from the repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from config import settings  # noqa: E402
from database import mongodb  # noqa: E402

logger = logging.getLogger("backfill_uploaded_pdfs")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)


# Expected field defaults. Each entry: (field_name, default_value).
# Used to compute a single per-doc `$set` patch with only the fields
# that are actually missing -- keeps the update minimal and idempotent.
_FIELD_DEFAULTS: Dict[str, Any] = {
    "total_pages": 0,
    "total_chunks": 0,
    "total_chars": 0,
    "file_size": 0,
    "uploader_email": "",
}


async def _open_pdf_safely(
    stored_filename: Optional[str],
    fallback_filename: Optional[str] = None,
) -> Optional[Dict[str, int]]:
    """Open the PDF on disk and return real (file_size, total_pages).

    Tries `stored_filename` first (the canonical opaque name written by
    newer uploads), then falls back to `fallback_filename` (the
    user-visible name) since older uploads never recorded the
    `stored_filename` field.

    Returns ``None`` when the file isn't accessible -- caller falls back
    to defaults. Importing PyMuPDF lazily so the script still runs in
    --dry-run mode when fitz isn't installed for some reason.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    path: Optional[Path] = None
    for name in (stored_filename, fallback_filename):
        if not name:
            continue
        candidate = upload_dir / name
        if candidate.is_file():
            path = candidate
            break
    if path is None:
        return None
    try:
        size = path.stat().st_size
        try:
            import fitz  # type: ignore
        except ImportError:
            logger.warning("PyMuPDF not available; recovering size only.")
            return {"file_size": size}
        with fitz.open(str(path)) as doc:
            pages = doc.page_count
        return {"file_size": size, "total_pages": pages}
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read %s: %s", path, e)
        return None


def _build_patch(doc: Dict[str, Any], recovered: Optional[Dict[str, int]]) -> Dict[str, Any]:
    """Compute the minimal `$set` payload for one document.

    `recovered` (when present) supersedes the zero defaults for
    file_size and total_pages.
    """
    patch: Dict[str, Any] = {}

    for field, default in _FIELD_DEFAULTS.items():
        if field not in doc or doc.get(field) is None:
            # Prefer disk-recovered value when available
            if recovered and field in recovered:
                patch[field] = recovered[field]
            else:
                patch[field] = default

    # Even if `file_size` exists but is 0, overwrite with disk truth
    # so admins see meaningful sizes.
    if recovered and "file_size" in recovered and not doc.get("file_size"):
        patch["file_size"] = recovered["file_size"]
    if recovered and "total_pages" in recovered and not doc.get("total_pages"):
        patch["total_pages"] = recovered["total_pages"]

    # Derive a timestamp when neither field exists. ObjectId carries
    # the document's creation instant -- a reasonable best-effort proxy
    # for an upload that never recorded one.
    if "upload_date" not in doc and "uploaded_at" not in doc:
        try:
            patch["upload_date"] = doc["_id"].generation_time
        except Exception:
            pass

    # Mirror upload_date into uploaded_at so any direct Mongo consumer
    # gets the same field name as the response model.
    if "uploaded_at" not in doc:
        ts = doc.get("upload_date") or patch.get("upload_date")
        if ts is not None:
            patch["uploaded_at"] = ts

    return patch


async def run(dry_run: bool, recover_from_disk: bool) -> int:
    await mongodb.connect()
    coll = mongodb.db.uploaded_pdfs
    total = await coll.count_documents({})
    logger.info("Scanning %s uploaded_pdfs documents...", total)

    examined = 0
    patched = 0
    recovered_pages_count = 0
    recovered_size_count = 0

    cursor = coll.find({})
    async for doc in cursor:
        examined += 1
        recovered: Optional[Dict[str, int]] = None
        if recover_from_disk:
            recovered = await _open_pdf_safely(
                doc.get("stored_filename"),
                fallback_filename=doc.get("filename"),
            )

        patch = _build_patch(doc, recovered)
        if not patch:
            continue

        if recovered:
            if "total_pages" in recovered and "total_pages" in patch:
                recovered_pages_count += 1
            if "file_size" in recovered and "file_size" in patch:
                recovered_size_count += 1

        if dry_run:
            logger.info(
                "[dry-run] %s <- %s",
                doc.get("filename") or doc.get("_id"),
                {k: v for k, v in patch.items() if k != "uploaded_at"},
            )
        else:
            await coll.update_one({"_id": doc["_id"]}, {"$set": patch})
        patched += 1

    mode = "WOULD patch" if dry_run else "Patched"
    logger.info(
        "%s %s/%s documents. Recovered from disk: pages=%s size=%s.",
        mode, patched, examined, recovered_pages_count, recovered_size_count,
    )
    if dry_run:
        logger.info("Dry-run: nothing was written. Re-run without --dry-run to apply.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the patches without writing anything.",
    )
    parser.add_argument(
        "--recover-from-disk",
        action="store_true",
        help="When set, re-open each PDF (if its stored_filename still "
             "exists under UPLOAD_DIR) to recover the real file_size and "
             "total_pages. Otherwise missing fields get default 0.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args.dry_run, args.recover_from_disk))


if __name__ == "__main__":
    sys.exit(main())

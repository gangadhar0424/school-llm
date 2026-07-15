"""File storage abstraction: local disk (default) or S3-compatible object
storage.

Why: uploads, generated audio and generated video currently live on the local
filesystem (``RUNTIME_DATA_DIR``). That makes the single box a hard dependency
and blocks running more than one instance — a second worker can't serve a file
the first one wrote. This module lets those artifacts live in an S3-compatible
bucket instead, so any instance can serve any file.

Design goals:
  - **Zero behavior change by default.** ``STORAGE_BACKEND=local`` (the
    default) keeps the existing local-disk read/write/serve paths exactly as
    they were.
  - **Opt-in remote.** Set ``STORAGE_BACKEND=s3`` plus the S3_* settings and
    generated files are mirrored to the bucket and served via redirect.
  - **Never hard-fail.** boto3 is imported lazily; a remote hiccup logs and
    falls back to the local copy when one still exists.

Categories map to the existing per-type dirs so call sites only pass a logical
category ("audio" | "video" | "uploads") + filename.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi.responses import FileResponse, RedirectResponse
from starlette.responses import Response

from config import settings

logger = logging.getLogger(__name__)

# Logical category → local directory. Mirrors config.py.
_CATEGORY_DIRS = {
    "audio": settings.AUDIO_DIR,
    "video": settings.VIDEO_DIR,
    "uploads": settings.UPLOAD_DIR,
}


def is_remote() -> bool:
    return (getattr(settings, "STORAGE_BACKEND", "local") or "local").strip().lower() == "s3"


def local_path(category: str, filename: str) -> Path:
    base = _CATEGORY_DIRS.get(category, settings.RUNTIME_DATA_DIR)
    return Path(base) / filename


def _object_key(category: str, filename: str) -> str:
    return f"{category}/{filename}"


# ─────────────────────────────────────────────────────────────────────────────
# S3 client (lazy, optional)
# ─────────────────────────────────────────────────────────────────────────────
_s3_client = None
_s3_init_done = False


def _get_s3():
    """Return a boto3 S3 client if configured + installed, else None."""
    global _s3_client, _s3_init_done
    if _s3_init_done:
        return _s3_client
    _s3_init_done = True
    if not is_remote() or not getattr(settings, "S3_BUCKET", ""):
        _s3_client = None
        return None
    try:
        import boto3  # type: ignore
        kwargs = {}
        if settings.S3_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        if settings.S3_REGION:
            kwargs["region_name"] = settings.S3_REGION
        if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
            kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
            kwargs["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
        _s3_client = boto3.client("s3", **kwargs)
        logger.info("storage: using S3 backend (bucket=%s)", settings.S3_BUCKET)
    except Exception as e:  # noqa: BLE001
        logger.warning("storage: STORAGE_BACKEND=s3 but boto3/S3 unavailable (%s); using local disk", e)
        _s3_client = None
    return _s3_client


def public_url(category: str, filename: str) -> Optional[str]:
    """Public URL for a remote object, or None when serving locally."""
    if not is_remote():
        return None
    base = (getattr(settings, "S3_PUBLIC_BASE_URL", "") or "").rstrip("/")
    if base:
        return f"{base}/{_object_key(category, filename)}"
    return None


def mirror_to_remote(category: str, filename: str, content_type: Optional[str] = None) -> bool:
    """Upload a locally-written file to the object store. No-op (returns True)
    in local mode. Best-effort: logs and returns False on failure so the
    caller can still serve the local copy."""
    if not is_remote():
        return True
    s3 = _get_s3()
    if s3 is None:
        return False
    src = local_path(category, filename)
    if not src.exists():
        logger.warning("storage.mirror_to_remote: local file missing: %s", src)
        return False
    try:
        extra = {"ContentType": content_type} if content_type else {}
        s3.upload_file(str(src), settings.S3_BUCKET, _object_key(category, filename), ExtraArgs=extra or None)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("storage.mirror_to_remote failed for %s/%s: %s", category, filename, e)
        return False


def ensure_local(category: str, filename: str) -> Optional[Path]:
    """Return a local path for the file, fetching it from the object store
    first if this instance doesn't have it.

    - Local mode: returns the local path if it exists, else None.
    - Remote mode: if the local copy is missing, downloads the object to the
      local path so the (sync, disk-based) processing/vector pipeline can read
      it. Returns None if it exists in neither place. Best-effort: a remote
      error logs and returns the local path only if present.

    This is what lets a second instance re-process a PDF that a *different*
    instance originally received and uploaded to the bucket.
    """
    lp = local_path(category, filename)
    if lp.exists():
        return lp
    if not is_remote():
        return None
    s3 = _get_s3()
    if s3 is None:
        return None
    try:
        lp.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(settings.S3_BUCKET, _object_key(category, filename), str(lp))
        return lp if lp.exists() else None
    except Exception as e:  # noqa: BLE001
        logger.warning("storage.ensure_local failed for %s/%s: %s", category, filename, e)
        return lp if lp.exists() else None


def delete_remote(category: str, filename: str) -> None:
    """Best-effort delete of a remote object. No-op in local mode; never raises."""
    if not is_remote():
        return
    s3 = _get_s3()
    if s3 is None:
        return
    try:
        s3.delete_object(Bucket=settings.S3_BUCKET, Key=_object_key(category, filename))
    except Exception as e:  # noqa: BLE001
        logger.warning("storage.delete_remote failed for %s/%s: %s", category, filename, e)


def serve(
    category: str,
    filename: str,
    media_type: str,
    download_name: Optional[str] = None,
) -> Response:
    """Return a response that serves the file from the best available source.

    - Local mode: FileResponse from disk (raises FileNotFoundError if absent).
    - Remote mode: redirect to the public object URL when one is configured;
      otherwise generate a presigned URL; otherwise fall back to a local copy
      if this instance happens to still have it.
    """
    lp = local_path(category, filename)
    if not is_remote():
        if not lp.exists():
            raise FileNotFoundError(str(lp))
        return FileResponse(str(lp), media_type=media_type, filename=download_name or filename)

    # Remote: prefer a stable public URL (CDN / public bucket).
    url = public_url(category, filename)
    if not url:
        s3 = _get_s3()
        if s3 is not None:
            try:
                url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": settings.S3_BUCKET, "Key": _object_key(category, filename)},
                    ExpiresIn=3600,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("storage.serve presign failed for %s/%s: %s", category, filename, e)
    if url:
        return RedirectResponse(url, status_code=302)
    # Last resort: local copy on this instance.
    if lp.exists():
        return FileResponse(str(lp), media_type=media_type, filename=download_name or filename)
    raise FileNotFoundError(f"{category}/{filename} not found locally or remotely")

"""
School LLM - Main FastAPI Application
Complete backend API for AI-powered learning platform
"""
from fastapi import (
    FastAPI,
    File,
    UploadFile,
    HTTPException,
    Depends,
    status,
    Request,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4
import requests
from bs4 import BeautifulSoup
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# All modules under backend/ use bare relative imports (`from config import …`,
# `from ai.summary import …`). That works when uvicorn is run from inside
# backend/ (the README's canonical recipe) but breaks when run as
# `python -m uvicorn backend.main:app` from the repo root because then
# sys.path[0] is the repo root, not backend/. Inserting backend/ at the
# front of sys.path here makes both invocations work, without forcing every
# sub-module to switch to package-qualified imports.
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Import configuration and modules
from config import settings, validate_config
from concurrency import (
    AI_GATE,
    AV_GATE,
    AlreadyInFlightError,
    PDF_GATE,
    ServerBusyError,
    all_gate_stats,
)
import storage
from database import (
    mongodb, user_db, activity_db, pdf_upload_db, chat_history_db, school_admin_db,
    chat_session_db, analytics_db, assignment_db, submission_db,
    role_permissions_db, notifications_db, chat_messages_db, schools_db,
)
from pdf_handler import pdf_handler
from vector_db import vector_db
from ai.summary import summary_generator
from ai.quiz import quiz_generator
from ai.qa import qa_system
from ai.audio import audio_generator
from ai.video import video_generator
from timing_utils import log_phase
from middleware.rate_limiter import RateLimitMiddleware
from rate_limiting import (
    rate_limit, get_rate_limits, set_rate_limits, get_today_usage,
    get_today_usage_by_role,
    map_quiz_feature, features_for_role,
    _check_and_increment as _rate_check_and_increment,
    FEATURES as RATE_LIMIT_FEATURES,
    FEATURES_BY_ROLE as RATE_LIMIT_FEATURES_BY_ROLE,
    DEFAULT_LIMITS as RATE_LIMIT_DEFAULTS,
)
from auth import (
    UserCreate, UserLogin, Token, LoginResponse, UserResponse, ChangePasswordRequest,
    UpdateUserClassRequest, AssignTeacherRequest,
    AssignmentCreate, AssignmentUpdate, SubmissionCreate, GradeOverride,
    UploadedPdfResponse,
    hash_password, verify_password, create_access_token, verify_token,
)
from auth_context import UserCtx
from auth_backend import auth_backend, AuthError
from services.realtime import (
    hub as realtime_hub,
    emit_chat_message,
    emit_chat_read,
    emit_notification_created,
    emit_notification_read,
)

def _configure_console_streams() -> None:
    """Use UTF-8 for console logging on Windows terminals when possible."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

_configure_console_streams()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Keep recent PDF processing results in memory so AI features can reuse them.
_PDF_CACHE_TTL_SECONDS = 60 * 30
_AI_CACHE_SCHEMA_VERSION = "2026-04-13-quiz-parse-v1"
_pdf_content_cache: Dict[str, Dict[str, Any]] = {}
_pdf_processing_locks: Dict[str, asyncio.Lock] = {}
_resolved_pdf_url_cache: Dict[str, str] = {}
_ai_result_cache: Dict[str, Dict[str, Any]] = {}


def _cache_get(pdf_key: str) -> Optional[Dict[str, Any]]:
    cached = _pdf_content_cache.get(pdf_key)
    if not cached:
        return None
    if time.time() - cached["ts"] > _PDF_CACHE_TTL_SECONDS:
        _pdf_content_cache.pop(pdf_key, None)
        return None
    return cached["data"]


def _cache_set(pdf_key: str, data: Dict[str, Any]) -> None:
    _pdf_content_cache[pdf_key] = {"ts": time.time(), "data": data}


def _cache_invalidate(pdf_key: str) -> None:
    _pdf_content_cache.pop(pdf_key, None)


def _ai_cache_key(task: str, pdf_key: str, payload: Dict[str, Any]) -> str:
    raw = json.dumps(
        {"version": _AI_CACHE_SCHEMA_VERSION, "task": task, "pdf_key": pdf_key, "payload": payload},
        sort_keys=True,
        default=str
    )
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _ai_cache_get(cache_key: str) -> Optional[Any]:
    cached = _ai_result_cache.get(cache_key)
    if not cached:
        return None
    if time.time() - cached["ts"] > _PDF_CACHE_TTL_SECONDS:
        _ai_result_cache.pop(cache_key, None)
        return None
    return cached["data"]


def _ai_cache_set(cache_key: str, data: Any) -> None:
    _ai_result_cache[cache_key] = {"ts": time.time(), "data": data}


def _get_pdf_lock(pdf_key: str) -> asyncio.Lock:
    lock = _pdf_processing_locks.get(pdf_key)
    if lock is None:
        lock = asyncio.Lock()
        _pdf_processing_locks[pdf_key] = lock
    return lock


async def _warm_pdf_vectors(pdf_key: str) -> None:
    """Build vector index in the background so later AI requests respond faster."""
    try:
        await _ensure_pdf_ready(pdf_key, ensure_vector=True)
        logger.info("Background vector indexing complete for %s", pdf_key)
    except Exception as exc:
        logger.warning("Background vector indexing failed for %s: %s", pdf_key, exc)

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("🚀 Starting School LLM API...")
    logger.info(f"⚙️  Configuration:")
    logger.info(f"   - MongoDB URI: {settings.MONGODB_URI}")
    logger.info(f"   - Database: {settings.DATABASE_NAME}")
    logger.info(f"   - API Host: {settings.HOST}:{settings.PORT}")
    logger.info(f"   - Ollama URL: {settings.OLLAMA_BASE_URL}")
    logger.info(f"   - Embeddings Provider: {settings.EMBEDDINGS_PROVIDER}")
    
    # Validate configuration. In production (anything that's NOT pointing
    # MongoDB at localhost) we fail-fast so a misconfigured deployment
    # crashes immediately instead of silently issuing forgeable tokens
    # or running with localhost-only CORS.
    if not validate_config():
        is_dev = (
            "localhost" in (settings.MONGODB_URI or "")
            or "127.0.0.1" in (settings.MONGODB_URI or "")
        )
        if is_dev:
            logger.warning("⚠️  Configuration warnings — continuing because MongoDB looks like dev.")
        else:
            logger.error("❌ Configuration is missing production-required values. Refusing to start.")
            import sys as _sys
            _sys.exit(1)
    
    # Connect to MongoDB
    logger.info("🔌 Attempting to connect to MongoDB...")
    try:
        await mongodb.connect()
        logger.info("✅ MongoDB connected successfully!")
        # One-time migration: reset all users' theme to the new default (cobalt).
        # Tracked in _migrations collection so it runs exactly once.
        try:
            marker = await mongodb.db["_migrations"].find_one({"_id": "reset_theme_cobalt_v1"})
            if not marker:
                result = await mongodb.db.users.update_many({}, {"$set": {"theme": "cobalt"}})
                await mongodb.db["_migrations"].insert_one(
                    {"_id": "reset_theme_cobalt_v1", "applied_at": datetime.utcnow(),
                     "modified": result.modified_count}
                )
                logger.info(f"🎨 Theme migration: reset {result.modified_count} user(s) to 'cobalt'")
        except Exception as mig_err:
            logger.warning(f"⚠️  Theme migration skipped (non-blocking): {mig_err}")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {type(e).__name__}: {str(e)}")
        logger.error(f"📍 Tried to connect to: {settings.MONGODB_URI}")
        logger.warning("⚠️  API will continue but database features (auth, uploads) will NOT work")
        logger.warning("💡 Solutions:")
        logger.warning("   1. Start MongoDB: mongod")
        logger.warning("   2. Or use Docker: docker run -d -p 27017:27017 --name mongodb mongo")
        logger.warning("   3. Or set MONGODB_URI to MongoDB Atlas cloud instance")
    
    # Warm up Ollama model in background (don't block startup)
    logger.info("🔥 Warming up Ollama model in background...")
    import asyncio
    from ai.ollama_client import ollama_client
    
    async def safe_warmup():
        try:
            await ollama_client.warm_up()
        except Exception as e:
            logger.warning(f"⚠️  Ollama warmup failed (non-blocking): {type(e).__name__}: {str(e)}")
            logger.info("💡 Make sure Ollama is running: http://localhost:11434")
    
    asyncio.create_task(safe_warmup())
    
    logger.info("✅ School LLM API is ready!")
    logger.info("🌐 API running at: http://localhost:8000")
    logger.info("📚 API docs at: http://localhost:8000/docs")
    
    yield
    
    # Shutdown
    logger.info("Shutting down School LLM API...")
    await mongodb.disconnect()

# Initialize FastAPI app with lifespan
app = FastAPI(
    title="School LLM API",
    description="AI-powered educational platform for students",
    version="1.0.0",
    lifespan=lifespan
)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# CORS middleware — allowed origins are read from settings.CORS_ORIGINS
# so production deployments can list their real domain without touching
# code. The env var accepts a comma-separated list:
#   CORS_ORIGINS="https://llm.school.com,https://staging.llm.school.com"
# In local dev (no env set) we fall back to the common Next.js + FastAPI
# localhost combinations.
def _parse_cors_origins(raw: str) -> List[str]:
    if not raw or raw.strip() == "*":
        # Wildcard is incompatible with allow_credentials=True (the
        # browser will reject the response), so collapse "*" to the
        # local dev origins instead of silently breaking auth.
        return [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    return [o.strip() for o in raw.split(",") if o.strip()]


_cors_origins = _parse_cors_origins(getattr(settings, "CORS_ORIGINS", ""))
logger.info(f"🌐 CORS allowed origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Concurrency-gate exception handlers — translate the typed exceptions
# from backend/concurrency.py into JSON HTTP responses. Both messages
# are deliberately generic ("server busy", "already running") so users
# don't see internal queue-depth numbers or worker counts.
@app.exception_handler(ServerBusyError)
async def _busy_handler(request, exc):  # type: ignore[override]
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc) or "The server is processing many requests right now. Please try again in a moment."},
        headers={"Retry-After": "10"},
    )


@app.exception_handler(AlreadyInFlightError)
async def _double_click_handler(request, exc):  # type: ignore[override]
    return JSONResponse(
        status_code=429,
        content={"detail": str(exc) or "This action is already running. Please wait for it to finish."},
    )


@app.get("/api/health/gates")
async def health_gates():
    """Cheap snapshot of the request-gate state. Useful for tailing
    during incident response. Not authenticated because it leaks no
    user data — just counts."""
    return {"gates": all_gate_stats()}


@app.get("/api/health/ready")
async def health_ready():
    """Deep readiness probe for load balancers / uptime monitors.

    Unlike ``/`` (which always returns "online"), this actively checks the
    dependencies the app cannot serve traffic without and returns HTTP 503
    when any critical one is down, so an orchestrator can pull this instance
    out of rotation instead of routing users into a degraded backend.

    Checks:
      - mongodb  (critical)  — admin ping
      - llm      (degraded)  — at least one provider reachable

    A failing LLM is reported but does NOT flip the probe to 503 on its own,
    because the extractive fallback still lets the app answer; a failing
    MongoDB does, because auth/uploads/assignments cannot work without it.
    """
    from database import mongodb

    checks: Dict[str, Any] = {}
    overall_ok = True

    # MongoDB — critical. Bounded so a hung socket can't hang the probe.
    try:
        if mongodb.client is None:
            raise RuntimeError("MongoDB client not initialised")
        await asyncio.wait_for(
            mongodb.client.admin.command("ping"), timeout=3.0
        )
        checks["mongodb"] = {"ok": True}
    except Exception as e:  # noqa: BLE001
        checks["mongodb"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        overall_ok = False

    # LLM provider — degraded-only. Probe Ollama's lightweight reachability
    # check (blocking requests.get, so run it off the event loop); otherwise
    # report that a provider key is at least set.
    try:
        llm_ok = False
        detail = "no provider reachable"
        try:
            from ai.ollama_client import ollama_client
            llm_ok = await asyncio.wait_for(
                asyncio.to_thread(ollama_client.is_available), timeout=4.0
            )
            detail = "ollama reachable" if llm_ok else "ollama unreachable"
        except Exception:
            llm_ok = False
        if not llm_ok and getattr(settings, "ANTHROPIC_API_KEY", ""):
            # Can't cheaply ping Anthropic without spending tokens; treat a
            # configured key as a usable provider for readiness purposes.
            llm_ok = True
            detail = "anthropic configured"
        checks["llm"] = {"ok": llm_ok, "detail": detail}
    except Exception as e:  # noqa: BLE001
        checks["llm"] = {"ok": False, "error": f"{type(e).__name__}: {e}"}

    body = {"status": "ready" if overall_ok else "degraded", "checks": checks}
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)

# Pydantic models for request/response
class QuestionRequest(BaseModel):
    pdf_url: str
    question: str
    conversation_history: Optional[List[Dict]] = None
    session_id: Optional[str] = None

class QuizRequest(BaseModel):
    pdf_url: str
    num_questions: Optional[int] = None
    difficulty: Optional[str] = None  # basic, medium, hard
    search_query: Optional[str] = None  # optional topic filter
    question_types: Optional[List[str]] = None  # ["mcq", "fill-in-blank", "true-false", "short-answer"]
    target_class: Optional[int] = None  # Phase 4: tag questions with the class they're written for (1-10)
    subject: Optional[str] = None       # Phase 6: subject tag (Math/Science/English/Social/Computer)

class SummaryRequest(BaseModel):
    pdf_url: str
    summary_type: str = "both"  # short, detailed, or both
    topic: Optional[str] = None  # optional topic/instruction for focused summary


class MultiDocQuestionRequest(BaseModel):
    pdf_identifiers: List[str]
    question: str
    conversation_history: Optional[List[Dict]] = None
    session_id: Optional[str] = None


class ChatSessionCreateRequest(BaseModel):
    pdf_ids: Optional[List[str]] = None
    mode: str = "single"  # "single" | "multi"
    name: Optional[str] = "New chat"


class ChatSessionRenameRequest(BaseModel):
    name: str


class ChatHistorySaveRequest(BaseModel):
    document_ids: List[str]
    question: str
    answer: str
    sources: Optional[List[str]] = None
    confidence: Optional[str] = "medium"


class AudioRequest(BaseModel):
    text: str
    pdf_url: Optional[str] = None

class VideoRequest(BaseModel):
    summary: Optional[str] = None
    pdf_url: Optional[str] = None
    query: Optional[str] = None
    style: Optional[str] = "slides"  # "slides" or "manim"


class EvaluateAnswerRequest(BaseModel):
    question: Optional[str] = ""
    expected_answer: Optional[str] = ""
    keywords: Optional[List[str]] = None
    student_answer: str
    # Phase 2 + Phase 4 + Phase 6 — class-aware evaluation
    student_class: Optional[int] = None  # student's actual class (1-10)
    target_class: Optional[int] = None   # class the question was generated for
    subject: Optional[str] = None        # Math / Science / English / Social / Computer


class ParseQuestionsRequest(BaseModel):
    copyable_text: str

# Health check endpoint
@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "online",
        "message": "School LLM API is running",
        "version": "1.0.0"
    }

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

security = HTTPBearer()

async def get_current_user_ctx(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserCtx:
    """Verify the bearer token against the active auth backend (local or
    eskoolia) and return a typed UserCtx. Prefer this in new code."""
    token = credentials.credentials
    try:
        ctx = await auth_backend.verify_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not ctx.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return ctx


async def get_current_user(
    ctx: UserCtx = Depends(get_current_user_ctx),
) -> Dict:
    """Legacy dependency: returns the dict shape existing route handlers
    expect (``user["email"]``, ``user["role"]``, ``user["assigned_classes"]``,
    etc.). New endpoints should depend on ``get_current_user_ctx`` instead.

    Also enforces the per-school LLM feature gate. Platform super admins
    bypass. In local mode ``llm_enabled`` is always True, so this is a
    no-op for the standalone product. In eskoolia mode it returns 402 when
    the school's ``School.llm_enabled`` flag is False — only ``/api/auth/me``,
    ``/api/auth/login``, and the health check stay reachable.
    """
    if not ctx.is_superuser and not ctx.llm_enabled:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                "AI features are not enabled for your school. "
                "Please contact your administrator."
            ),
        )
    return ctx.to_legacy_dict()


def _block_if_eskoolia(current_user: Dict, what: str) -> None:
    """Reject Mongo-user-mutating actions when identity is owned by the ERP.

    In ``AUTH_PROVIDER=eskoolia``, the user record lives in the eSkoolia
    Postgres database. Anything that writes to the LLM-side Mongo ``users``
    collection (signup, password change, role/class re-assignment, theme
    persistence) makes no sense and would silently fail. Use this guard at
    the top of those handlers to return a clear 409 instead.
    """
    if (current_user or {}).get("auth_source") == "eskoolia":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{what} is managed by your school ERP (eSkoolia). "
                "Please use the eSkoolia portal."
            ),
        )

# ============================================================================
# AUTH DECORATORS/MIDDLEWARE
# ============================================================================

def _resolve_role(user: Dict) -> str:
    """Read the user's effective role: prefer the explicit `role` field
    (set since Phase 1) and fall back to is_admin for legacy accounts.
    Super admin is the top of the hierarchy and passes any admin gate."""
    role = (user.get("role") or "").strip().lower()
    if role in ("super_admin", "admin", "teacher", "student"):
        return role
    if user.get("is_superuser"):
        return "super_admin"
    return "admin" if user.get("is_admin") else "student"


async def get_admin_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is an admin (or super admin)."""
    role = _resolve_role(current_user)
    if role not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


async def get_admin_user_ctx(ctx: UserCtx = Depends(get_current_user_ctx)) -> UserCtx:
    """Admin dependency that returns the typed `UserCtx` (not the legacy
    dict). New school-shaped admin endpoints prefer this so they can read
    `school_id` directly for per-tenant scoping. Super admin is over admin
    and is allowed through."""
    if ctx.role not in ("admin", "super_admin") and not ctx.is_admin and not ctx.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return ctx


async def get_super_admin_user(
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Gate routes to the platform owner (super admin) only.

    Source of truth is `is_superuser` (from the ERP /me response or the
    LocalAuthBackend allowlist). The role string is checked as a
    redundancy in case future code paths set role without setting the flag."""
    if not (
        current_user.get("is_superuser")
        or _resolve_role(current_user) == "super_admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return current_user


async def get_super_admin_user_ctx(
    ctx: UserCtx = Depends(get_current_user_ctx),
) -> UserCtx:
    """Typed UserCtx variant of `get_super_admin_user`."""
    if not (ctx.is_superuser or ctx.role == "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin privileges required",
        )
    return ctx


# ─── Concurrency-gate dependencies ──────────────────────────────────────
#
# Acquire a gate slot at request entry, release on response exit. The
# yield-based dependency runs the request body inside the `async with`
# block, so the gate is held for the duration of the entire handler —
# including the FastAPI response serialization. ServerBusyError and
# AlreadyInFlightError propagate to the exception handlers registered
# at the top of this file (translated to 503 / 429).

def gate_ai(feature: str):
    """Factory: return a FastAPI dep that holds the AI gate for the
    request lifecycle, tagged with the feature name for per-user dedup."""
    async def _dep(current_user: Dict = Depends(get_current_user)):
        async with AI_GATE.acquire(
            user_email=current_user.get("email"), feature=feature,
        ):
            yield
    return _dep


def gate_pdf(feature: str = "pdf"):
    async def _dep(current_user: Dict = Depends(get_current_user)):
        async with PDF_GATE.acquire(
            user_email=current_user.get("email"), feature=feature,
        ):
            yield
    return _dep


def gate_av(feature: str):
    async def _dep(current_user: Dict = Depends(get_current_user)):
        async with AV_GATE.acquire(
            user_email=current_user.get("email"), feature=feature,
        ):
            yield
    return _dep


async def get_teacher_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is a teacher."""
    if _resolve_role(current_user) != "teacher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher access only",
        )
    return current_user


async def get_student_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is a student."""
    if _resolve_role(current_user) != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students only",
        )
    return current_user


def _norm_class_section(s: str) -> str:
    """Normalize '5a' / ' 10 a ' → '5A'."""
    return (s or "").strip().upper().replace(" ", "")


def _assert_teacher_owns_class(teacher: Dict, class_section: str) -> None:
    """Raise 403 if `class_section` is not in this teacher's assigned_classes."""
    assigned = [
        _norm_class_section(c) for c in (teacher.get("assigned_classes") or [])
    ]
    cs = _norm_class_section(class_section)
    if cs not in assigned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You are not assigned to class {cs}.",
        )


async def _require_permission(user: Dict, feature: str) -> None:
    """Raise 403 if the user's role is not allowed to use `feature` per the
    role-permissions matrix configured by the admin. Admins still pass through
    role checks but can have specific features disabled (e.g., export_data)."""
    role = _resolve_role(user)
    allowed = await role_permissions_db.is_allowed(role, feature)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature ('{feature}') is currently disabled for {role}s by the administrator.",
        )


@app.post("/api/auth/signup")
async def signup(user_data: UserCreate):
    """Register a new user.

    Role-specific required fields:
      - student: class_level + section
      - teacher: subjects_taught + assigned_classes
      - admin:   no extra fields

    Disabled when AUTH_PROVIDER=eskoolia — users are created in the ERP.
    """
    if (settings.AUTH_PROVIDER or "local").lower() == "eskoolia":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Signup is managed by your school ERP (eSkoolia). "
                "Please use the eSkoolia portal to create accounts."
            ),
        )
    try:
        logger.info(f"📝 SIGNUP attempt: email={user_data.email}, role={user_data.role}")

        # Treat legacy "user" as "student" for backward compat
        role = user_data.role
        if role == "user":
            role = "student"

        # Role-specific validation
        if role == "student":
            if user_data.class_level is None or not user_data.section:
                raise HTTPException(
                    status_code=400,
                    detail="Students must provide class_level (1-10) and section (A/B/C).",
                )
        elif role == "teacher":
            if not (user_data.subjects_taught and user_data.assigned_classes):
                raise HTTPException(
                    status_code=400,
                    detail="Teachers must provide subjects_taught and at least one assigned_class (e.g. '5A').",
                )

        existing_user = await user_db.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = hash_password(user_data.password)
        is_admin = (role == "admin")

        # Build role-specific user document
        user_doc = {
            'email': user_data.email,
            'username': user_data.username,
            'full_name': user_data.full_name,
            'hashed_password': hashed_password,
            'created_at': datetime.utcnow(),
            'is_active': True,
            'is_admin': is_admin,
            'role': role,
            'onboarding_completed': False,
            'theme': 'cobalt',  # default theme
        }
        if role == "student":
            cl = int(user_data.class_level)
            sec = str(user_data.section).upper()
            user_doc['class_level'] = cl
            user_doc['section'] = sec
            user_doc['class_section'] = f"{cl}{sec}"
        elif role == "teacher":
            user_doc['subjects_taught'] = list(user_data.subjects_taught or [])
            user_doc['assigned_classes'] = [
                str(c).strip().upper().replace(" ", "")
                for c in (user_data.assigned_classes or [])
            ]

        user_id = await user_db.create_user(user_doc)
        if not user_id:
            raise HTTPException(status_code=500, detail="Failed to create user in database")

        logger.info(f"✅ SIGNUP SUCCESSFUL: user_id={user_id}, email={user_data.email}, role={role}")

        return UserResponse(
            id=str(user_id),
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            created_at=user_doc['created_at'],
            is_active=True,
            is_admin=is_admin,
            role=role,
            class_level=user_doc.get('class_level'),
            section=user_doc.get('section'),
            subjects_taught=user_doc.get('subjects_taught'),
            assigned_classes=user_doc.get('assigned_classes'),
            theme=user_doc.get('theme', 'cobalt'),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CRITICAL SIGNUP ERROR: {type(e).__name__}: {str(e)}", exc_info=True)
        logger.error(f"💥 Check MongoDB connection at: {settings.MONGODB_URI}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {type(e).__name__}. Please ensure MongoDB is running and accessible.")

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    """Login and get an access token.

    Delegates to the active auth backend (``settings.AUTH_PROVIDER``):
      * ``local``    — Mongo + bcrypt, self-issued JWT (existing behavior).
      * ``eskoolia`` — Forwards credentials to the ERP's
                       ``/api/v1/auth/login/`` and returns the ERP-issued JWT.
    """
    logger.info(f"🔐 Login attempt for email: {credentials.email} via {auth_backend.name}")
    try:
        token, ctx = await auth_backend.login(
            email=credentials.email,
            password=credentials.password,
            requested_role=credentials.role,
        )
    except AuthError as e:
        logger.warning(f"❌ Login failed for {credentials.email}: {e}")
        raise HTTPException(
            status_code=e.status_code,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"} if e.status_code == 401 else None,
        )
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"💥 MongoDB connection error during login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Login failed: database unreachable. Check MongoDB at {settings.MONGODB_URI}."
            ),
        )
    except Exception as e:
        logger.error(
            f"❌ CRITICAL LOGIN ERROR for {credentials.email}: {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to an internal server error. Check backend logs.",
        )

    # Best-effort activity log (do not block the login response on logging errors).
    try:
        await activity_db.log_activity(
            user_email=ctx.email,
            activity_type="login",
            details={"username": ctx.username, "role": ctx.role, "source": auth_backend.name},
        )
    except Exception as e:
        logger.warning(f"⚠ Failed to log login activity for {ctx.email}: {e}")

    # Mirror the ERP user into the local `users` collection so school-admin
    # listing endpoints have something to query without re-hitting the ERP
    # per request. Skipped for local auth (the row is already there).
    if auth_backend.name == "eskoolia":
        try:
            await user_db.upsert_from_ctx(ctx)
        except Exception as e:
            logger.warning(f"⚠ Failed to mirror ERP user {ctx.email}: {e}")

    # Update the schools registry so the super-admin dashboard can list
    # "schools using the app" without aggregating users on every page load.
    # Super admins have no school_id; the call is a no-op for them.
    if ctx.school_id is not None:
        try:
            await schools_db.upsert_seen(ctx.school_id, ctx.school_name, ctx.school_plan)
        except Exception as e:
            logger.warning(f"⚠ Failed to record school sighting {ctx.school_id}: {e}")

    logger.info(f"✅ LOGIN SUCCESSFUL for {ctx.email} (role={ctx.role}, backend={auth_backend.name})")
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "is_admin": ctx.is_admin,
            "theme": ctx.theme or "cobalt",
        },
    }

@app.post("/api/auth/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Invalidate the caller's token server-side.

    For ``local`` auth this adds the token's id to a revocation denylist so
    it can't be reused even though the JWT is still well-formed. For
    ``eskoolia`` it drops the cached /me/ entry. Always returns 200 (logout
    is idempotent and should never fail the client's sign-out flow)."""
    token = credentials.credentials
    try:
        await auth_backend.logout(token)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"⚠ logout cleanup failed (non-fatal): {e}")
    return {"detail": "Logged out"}


@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(ctx: UserCtx = Depends(get_current_user_ctx)):
    """Get current user information including role + class fields.

    Works for both auth backends. For ``eskoolia``, ``school_id`` /
    ``school_name`` / ``llm_enabled`` are populated from the ERP.
    """
    return UserResponse(
        id=ctx.user_id,
        email=ctx.email,
        username=ctx.username,
        full_name=ctx.full_name,
        created_at=ctx.created_at,
        is_active=ctx.is_active,
        is_admin=ctx.is_admin,
        role=ctx.role,
        class_level=ctx.class_level,
        section=ctx.section,
        subjects_taught=list(ctx.subjects_taught),
        assigned_classes=list(ctx.assigned_classes),
        onboarding_completed=ctx.onboarding_completed,
        theme=ctx.theme or "cobalt",
        school_id=ctx.school_id,
        school_name=ctx.school_name,
        school_plan=ctx.school_plan,
        llm_enabled=ctx.llm_enabled,
        auth_source=ctx.auth_source,
        must_change_password=ctx.must_change_password,
    )


@app.put("/api/auth/complete-onboarding")
async def complete_onboarding(current_user: Dict = Depends(get_current_user)):
    """Mark the user's onboarding as completed (persists across logins)."""
    _block_if_eskoolia(current_user, "Onboarding state")
    try:
        from bson import ObjectId
        await mongodb.db.users.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": {"onboarding_completed": True}},
        )
        return {"message": "Onboarding completed", "onboarding_completed": True}
    except Exception as e:
        logger.error(f"Failed to mark onboarding complete: {e}")
        raise HTTPException(status_code=500, detail="Failed to update onboarding status")


# Valid theme names — kept in sync with frontend_next/src/lib/themes.ts
_VALID_THEMES = {"midnight", "cobalt", "onyx", "sand"}


@app.put("/api/auth/theme")
async def update_user_theme(
    body: Dict[str, Any],
    current_user: Dict = Depends(get_current_user),
):
    """Save the user's chosen color theme. Persists across logins + devices."""
    _block_if_eskoolia(current_user, "Theme persistence")
    theme = (body.get("theme") or "").strip().lower()
    if theme not in _VALID_THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid theme. Must be one of: {', '.join(sorted(_VALID_THEMES))}",
        )
    try:
        from bson import ObjectId
        await mongodb.db.users.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": {"theme": theme}},
        )
        return {"message": "Theme updated", "theme": theme}
    except Exception as e:
        logger.error(f"Failed to update theme: {e}")
        raise HTTPException(status_code=500, detail="Failed to update theme")

@app.post("/api/auth/change-password")
async def change_password(
    change_pwd_request: ChangePasswordRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Change user password"""
    _block_if_eskoolia(current_user, "Password change")
    await _require_permission(current_user, "change_password")
    try:
        # Verify old password
        if not verify_password(change_pwd_request.old_password, current_user['hashed_password']):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current password is incorrect"
            )
        
        # Validate new password strength (at least 8 characters)
        if len(change_pwd_request.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be at least 8 characters long"
            )
        
        # Hash new password
        new_hashed_password = hash_password(change_pwd_request.new_password)
        
        # Update password in database
        from bson import ObjectId
        result = await mongodb.db.users.update_one(
            {"_id": ObjectId(current_user['_id'])},
            {"$set": {"hashed_password": new_hashed_password}}
        )
        
        if result.modified_count > 0:
            logger.info(f"✓ Password changed for user: {current_user['email']}")
            await activity_db.log_activity(
                user_email=current_user['email'],
                activity_type='password_change',
                details={'username': current_user['username']}
            )
            return {"message": "Password changed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error changing password"
        )

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@app.get("/api/admin/assignments")
async def admin_list_assignments(admin: Dict = Depends(get_admin_user)):
    """Return all assignments created by teachers in the admin's school."""
    school_id = admin.get("school_id")
    base = {"school_id": school_id} if school_id is not None else {}
    
    # 1. Get all teachers in this school
    teacher_cursor = mongodb.db.users.find({"role": "teacher", **base})
    teacher_emails = []
    teacher_map = {}
    async for t in teacher_cursor:
        email = t.get("email")
        if email:
            teacher_emails.append(email)
            teacher_map[email] = t.get("full_name") or t.get("username")

    if not teacher_emails:
        return {"assignments": [], "count": 0}

    # 2. Get all assignments for these teachers
    cursor = mongodb.db.assignments.find({"teacher_email": {"$in": teacher_emails}}).sort("created_at", -1)
    assignments = await cursor.to_list(None)
    
    # 3. For each assignment, get submissions
    for a in assignments:
        a["id"] = str(a.pop("_id"))
        a["teacher_name"] = teacher_map.get(a.get("teacher_email"), "Unknown Teacher")
        subs = await submission_db.list_for_assignment(a["id"])
        a["submission_count"] = len(subs)

    return {"assignments": assignments, "count": len(assignments)}


@app.get("/api/admin/users")
async def get_all_users(admin_user: Dict = Depends(get_admin_user)):
    """Get all users with their activity (admin only)"""
    await _require_permission(admin_user, "manage_users")
    users = await activity_db.get_all_users_with_activity()
    return {"users": users, "total": len(users)}


# ============================================================================
# SCHOOL-SHAPED ADMIN VIEWS (Phase 1)
# ----------------------------------------------------------------------------
# Six read-only endpoints that turn the flat "Users" admin into a school-aware
# experience: an overview card, separate teacher/student lists with
# drilldowns, and an adjacency list for the "who teaches whom" view.
#
# Source of truth is the local `users` collection, populated for ERP users by
# `UserDB.upsert_from_ctx` on each login. Per-tenant scoping comes from
# `admin_ctx.school_id`; local-mode admins (school_id=None) see everything.
# ============================================================================

_school_admin_cache: Dict[Tuple[str, Optional[int]], Tuple[float, Any]] = {}
_SCHOOL_ADMIN_CACHE_TTL = 60  # seconds; matches ESKOOLIA_ME_CACHE_TTL default


def _cache_lookup(key: Tuple[str, Optional[int]]) -> Optional[Any]:
    entry = _school_admin_cache.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _cache_store(key: Tuple[str, Optional[int]], value: Any) -> Any:
    _school_admin_cache[key] = (time.time() + _SCHOOL_ADMIN_CACHE_TTL, value)
    return value


def _isoformat(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else None


@app.get("/api/admin/school/overview")
async def school_overview(admin_ctx: UserCtx = Depends(get_admin_user_ctx)):
    """High-level counts for the admin dashboard's school card."""
    cache_key = ("overview", admin_ctx.school_id)
    cached = _cache_lookup(cache_key)
    if cached is not None:
        return cached
    payload = await school_admin_db.school_overview(admin_ctx.school_id)
    # Header chip uses school_name; if the mirror didn't carry it yet,
    # fall back to whatever the admin's own UserCtx has.
    if not payload.get("school_name") and admin_ctx.school_name:
        payload["school_name"] = admin_ctx.school_name
    if not payload.get("school_plan") and admin_ctx.school_plan:
        payload["school_plan"] = admin_ctx.school_plan
    return _cache_store(cache_key, payload)


@app.get("/api/admin/teachers")
async def list_teachers(admin_ctx: UserCtx = Depends(get_admin_user_ctx)):
    """List of teachers in the admin's school with classes, subjects, and
    AI usage. Sorted by last-active descending."""
    cache_key = ("teachers", admin_ctx.school_id)
    cached = _cache_lookup(cache_key)
    if cached is not None:
        return cached
    rows = await school_admin_db.list_teachers(admin_ctx.school_id)
    payload = {
        "teachers": [
            {**r, "last_active": _isoformat(r.get("last_active"))} for r in rows
        ],
        "total": len(rows),
    }
    return _cache_store(cache_key, payload)


@app.get("/api/admin/teachers/{teacher_id}")
async def teacher_detail(
    teacher_id: str,
    admin_ctx: UserCtx = Depends(get_admin_user_ctx),
):
    """Profile + student roster + per-feature AI usage breakdown."""
    detail = await school_admin_db.teacher_detail(admin_ctx.school_id, teacher_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Teacher not found")
    t = detail["teacher"]
    t["last_login_at"] = _isoformat(t.get("last_login_at"))
    return detail


@app.get("/api/admin/students")
async def list_students(admin_ctx: UserCtx = Depends(get_admin_user_ctx)):
    """List of students in the admin's school with class section, class
    teacher (best-effort until ERP exposes the relation), and AI usage."""
    cache_key = ("students", admin_ctx.school_id)
    cached = _cache_lookup(cache_key)
    if cached is not None:
        return cached
    rows = await school_admin_db.list_students(admin_ctx.school_id)
    payload = {
        "students": [
            {**r, "last_active": _isoformat(r.get("last_active"))} for r in rows
        ],
        "total": len(rows),
    }
    return _cache_store(cache_key, payload)


@app.get("/api/admin/students/{student_id}")
async def student_detail(
    student_id: str,
    admin_ctx: UserCtx = Depends(get_admin_user_ctx),
):
    """Profile + class teacher + subject teachers + 14-day activity timeline."""
    detail = await school_admin_db.student_detail(admin_ctx.school_id, student_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Student not found")
    s = detail["student"]
    s["last_login_at"] = _isoformat(s.get("last_login_at"))
    return detail


@app.get("/api/admin/users/lookup")
async def admin_user_lookup(
    email: str,
    admin_ctx: UserCtx = Depends(get_admin_user_ctx),
):
    """Resolve an email to `{id, role, full_name}` within the admin's
    school. Used by the Activity feed to open the canonical "person
    sheet" without hard-coding the user's role on the client."""
    result = await school_admin_db.lookup_by_email(admin_ctx.school_id, email)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found in this school")
    return result


@app.get("/api/admin/relationships")
async def school_relationships(admin_ctx: UserCtx = Depends(get_admin_user_ctx)):
    """Adjacency list for the org-chart view: teachers, classes, and
    teacher↔class edges with subjects."""
    cache_key = ("relationships", admin_ctx.school_id)
    cached = _cache_lookup(cache_key)
    if cached is not None:
        return cached
    payload = await school_admin_db.relationships(admin_ctx.school_id)
    return _cache_store(cache_key, payload)

@app.get("/api/admin/activity")
async def get_user_activity_log(
    user_email: Optional[str] = None,
    limit: int = 100,
    admin_user: Dict = Depends(get_admin_user)
):
    """Get user activity logs (admin only)"""
    await _require_permission(admin_user, "view_audit_logs")
    activities = await activity_db.get_user_activity(user_email, limit)
    return {"activities": activities, "count": len(activities)}

@app.get("/api/admin/uploaded-pdfs")
async def get_uploaded_pdfs(
    limit: int = 100,
    admin_ctx: UserCtx = Depends(get_admin_user_ctx),
):
    """Get all uploaded PDFs (admin only).

    Each document is normalized through UploadedPdfResponse so legacy
    records (missing total_pages, file_size, etc.) come out with the
    same shape as fresh uploads. Each row also carries `uploader_role`
    and `uploader_school_id`, joined from the `users` mirror so the
    admin UI can filter by who uploaded it (Teachers / Students /
    Admins) and we can scope to the admin's school.
    """
    # Permission check kept for parity with the rest of the admin routes
    # (UserCtx → legacy dict only when needed).
    await _require_permission(admin_ctx.to_legacy_dict(), "manage_users")
    raw = await pdf_upload_db.get_all_uploads(limit)

    # Batch-join uploader emails against the users mirror in a single
    # round-trip so the response carries the role + school of whoever
    # uploaded each PDF.
    emails = list({d.get("uploader_email") for d in raw if d.get("uploader_email")})
    user_meta: Dict[str, Dict[str, Any]] = {}
    if emails:
        cursor = mongodb.db.users.find(
            {"email": {"$in": emails}},
            {"email": 1, "role": 1, "school_id": 1},
        )
        async for u in cursor:
            user_meta[u["email"]] = {
                "uploader_role": u.get("role"),
                "uploader_school_id": u.get("school_id"),
            }

    # School scoping: when the admin's UserCtx carries a school_id (ERP
    # mode), only return PDFs whose uploader belongs to the same school.
    # Local-mode admins (school_id=None) keep the unscoped view.
    scoped: list = []
    for d in raw:
        em = d.get("uploader_email") or ""
        meta = user_meta.get(em, {})
        if admin_ctx.school_id is not None:
            if meta.get("uploader_school_id") != admin_ctx.school_id:
                continue
        scoped.append({**d, **meta})

    pdfs = [
        UploadedPdfResponse.from_doc(d).model_dump(mode="json")
        for d in scoped
    ]
    return {"pdfs": pdfs, "total": len(pdfs)}

@app.get("/api/my-uploaded-pdfs")
async def get_my_uploaded_pdfs(
    limit: int = 100,
    current_user: Dict = Depends(get_current_user)
):
    """Get only the PDFs uploaded by the currently logged-in user.

    Same normalization as /api/admin/uploaded-pdfs so the student
    dashboard never has to defensively check for missing fields.
    """
    raw = await pdf_upload_db.get_user_uploads(current_user["email"], limit)
    pdfs = [
        UploadedPdfResponse.from_doc(d).model_dump(mode="json")
        for d in raw
    ]
    return {"pdfs": pdfs, "total": len(pdfs)}

@app.put("/api/admin/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: dict,
    admin_user: Dict = Depends(get_admin_user)
):
    """Activate or deactivate a user (admin only)"""
    _block_if_eskoolia(admin_user, "User activation toggle")
    await _require_permission(admin_user, "toggle_user_status")
    try:
        from bson import ObjectId
        is_active = request.get("is_active", True)

        result = await mongodb.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"is_active": is_active}}
        )

        if result.modified_count > 0:
            return {"message": f"User {'activated' if is_active else 'deactivated'} successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Class hierarchy + teacher assignment endpoints (admin only)
# ─────────────────────────────────────────────────────────────────────────────
@app.put("/api/admin/users/{user_id}/class")
async def admin_update_user_class(
    user_id: str,
    body: UpdateUserClassRequest,
    admin_user: Dict = Depends(get_admin_user),
):
    """Set a student's class_level (1-10) and section (A/B/C)."""
    _block_if_eskoolia(admin_user, "Class/section assignment")
    await _require_permission(admin_user, "assign_class_section")
    ok = await user_db.update_user_class(user_id, body.class_level, body.section)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found or no change applied")
    return {"message": "Class updated", "class_section": f"{body.class_level}{body.section}"}


@app.put("/api/admin/users/{user_id}/teacher-assignments")
async def admin_assign_teacher(
    user_id: str,
    body: AssignTeacherRequest,
    admin_user: Dict = Depends(get_admin_user),
):
    """Set a teacher's subjects_taught + assigned_classes (e.g. ['5A','6A'])."""
    _block_if_eskoolia(admin_user, "Teacher subject/class assignment")
    await _require_permission(admin_user, "assign_teacher_subjects")
    ok = await user_db.assign_teacher(user_id, body.subjects_taught, body.assigned_classes)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found or no change applied")
    return {
        "message": "Teacher assignments updated",
        "subjects_taught": body.subjects_taught,
        "assigned_classes": body.assigned_classes,
    }


@app.get("/api/admin/teachers-for-class")
async def admin_get_teachers_for_class(
    class_section: str,
    subject: Optional[str] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Find teachers assigned to a class+section like '5A', optionally filtered by subject."""
    teachers = await user_db.get_teachers_for_class(class_section, subject)
    for t in teachers:
        t.pop("_id", None)
    return {"teachers": teachers, "count": len(teachers)}


# =============================================================================
# ROLE PERMISSIONS — admin-toggleable RBAC matrix
# =============================================================================
@app.get("/api/admin/permissions")
async def get_role_permissions(admin_user: Dict = Depends(get_admin_user)):
    """Return the full role → feature → enabled matrix (defaults merged with overrides)."""
    perms = await role_permissions_db.get_all()
    return {"permissions": perms}


@app.put("/api/admin/permissions")
async def update_role_permission(
    body: Dict[str, Any],
    admin_user: Dict = Depends(get_admin_user),
):
    """Update a single permission. Body: { role: str, feature: str, enabled: bool }."""
    role = (body.get("role") or "").strip().lower()
    feature = (body.get("feature") or "").strip()
    enabled = bool(body.get("enabled"))

    if role not in ("admin", "teacher", "student"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if not feature:
        raise HTTPException(status_code=400, detail="Feature key required")

    # Prevent admin from locking themselves out of permission management
    if role == "admin" and feature == "manage_users" and not enabled:
        raise HTTPException(
            status_code=400,
            detail="Cannot disable 'manage_users' for admins (would lock you out).",
        )

    ok = await role_permissions_db.set_permission(role, feature, enabled)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update permission")

    # Audit log
    try:
        await activity_db.log_activity(
            user_email=admin_user["email"],
            activity_type="permission_change",
            details={"role": role, "feature": feature, "enabled": enabled},
        )
    except Exception:
        pass

    return {
        "message": f"Permission '{feature}' for {role}s set to {enabled}.",
        "role": role,
        "feature": feature,
        "enabled": enabled,
    }


@app.post("/api/admin/permissions/{role}/reset")
async def reset_role_permissions(
    role: str,
    admin_user: Dict = Depends(get_admin_user),
):
    """Restore a single role's permissions to the backend defaults.

    Implemented by deleting every per-feature override for that role,
    so the next `get_all` falls back through the merge to
    ``RolePermissionsDB.DEFAULT_PERMISSIONS``. Safe to call repeatedly
    (it's a no-op once the role has no overrides).

    Returns the post-reset merged map so the admin UI can update its
    React Query cache without a second round-trip.
    """
    role_norm = (role or "").strip().lower()
    if role_norm not in ("admin", "teacher", "student"):
        raise HTTPException(status_code=400, detail="Invalid role")

    ok = await role_permissions_db.reset_role(role_norm)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to reset permissions")

    try:
        await activity_db.log_activity(
            user_email=admin_user["email"],
            activity_type="permission_reset",
            details={"role": role_norm},
        )
    except Exception:
        pass

    # Hand back the full merged map so the client can swap its cache
    # without an extra GET.
    perms = await role_permissions_db.get_all()
    return {
        "message": f"Permissions for {role_norm}s reset to defaults.",
        "role": role_norm,
        "permissions": perms,
    }


# =============================================================================
# RATE LIMITS — managed by the SUPER ADMIN (see routes/super_admin.py).
# The /api/my/rate-limits endpoint below remains for every authenticated user
# so they can see their own daily quota and remaining-today count.
# =============================================================================
@app.get("/api/my/rate-limits")
async def get_my_rate_limits(current_user: Dict = Depends(get_current_user)):
    """Today's input + output token budgets + spend for the calling user.

    Budget model: per-role daily pools, split input / output (mirrors how
    Claude and ChatGPT bill — input tokens are cheaper, output tokens are
    pricier). Students and teachers are metered; admins and super admins
    return ``limit = -1`` (unlimited) on both pools.

    Response shape::

        {
          "role": "student",
          "input":  {"limit": 200000, "used": 1234, "remaining": 198766},
          "output": {"limit":  50000, "used":  456, "remaining":  49544},
          "by_feature": {"qa": 800, "summary": 434, ...},
          "resets_in_seconds": 12345
        }

    On either pool, ``limit = -1`` = unlimited (``remaining`` null);
    ``limit = 0`` = role disabled.
    """
    from rate_limiting import (
        DEFAULT_LIMITS as _DEFAULTS,
        _resolve_role,
        _seconds_until_midnight,
        get_today_tokens,
        get_today_usage as _get_today_usage,
    )

    role = _resolve_role(current_user)
    school_id_val = current_user.get("school_id")
    try:
        school_id_int: Optional[int] = int(school_id_val) if school_id_val is not None else None
    except (TypeError, ValueError):
        school_id_int = None

    user_id_str = str(current_user.get("id") or current_user.get("_id") or "")
    by_feature = await _get_today_usage(user_id_str) if user_id_str else {}

    # Admins / super admins are unmetered; both pools report -1.
    if role in ("admin", "super_admin"):
        return {
            "role": role,
            "input": {"limit": -1, "used": 0, "remaining": None},
            "output": {"limit": -1, "used": 0, "remaining": None},
            "by_feature": by_feature,
            "resets_in_seconds": _seconds_until_midnight(),
        }

    all_limits = await get_rate_limits(school_id=school_id_int)
    pool = all_limits.get(role) or _DEFAULTS.get(role) or {}
    used = await get_today_tokens(user_id_str) if user_id_str else {"input": 0, "output": 0}

    def _slice(kind: str) -> Dict[str, Any]:
        limit = int(pool.get(kind, 0))
        used_k = int(used.get(kind, 0))
        remaining: Optional[int] = None if limit < 0 else max(0, limit - used_k)
        return {"limit": limit, "used": used_k, "remaining": remaining}

    return {
        "role": role,
        "input": _slice("input"),
        "output": _slice("output"),
        "by_feature": by_feature,
        "resets_in_seconds": _seconds_until_midnight(),
    }


# =============================================================================
# TEACHER ENDPOINTS — assignments + per-class students
# =============================================================================
async def _grade_submission_answers(
    questions: list, answers: list, student_class: Optional[int]
) -> list:
    """Auto-grade each submitted answer using the Phase 2-6 hybrid evaluator.
    Returns the list of graded answer dicts (with ai_score, scaled_score, etc.)."""
    from services.answer_evaluator import hybrid_evaluate
    try:
        from ai.llm_client import get_llm_client
        llm = get_llm_client()
    except ImportError:
        from ai.ollama_client import ollama_client as llm

    # Index answers by question_index for quick lookup
    by_idx = {int(a.get("question_index", -1)): a for a in answers}
    graded: list = []
    for qi, q in enumerate(questions):
        student_answer = (by_idx.get(qi) or {}).get("student_answer", "") or ""
        marks = float(q.get("marks") or 10)
        target_class = q.get("target_class") or student_class
        subject = q.get("subject")

        if not student_answer.strip():
            graded.append({
                "question_index": qi,
                "student_answer": "",
                "ai_score": 0.0,
                "ai_method": "none",
                "ai_band": None,
                "marks": marks,
                "scaled_score": 0.0,
                "feedback": {
                    "correct_points": [],
                    "mistakes": ["No answer provided."],
                    "improvements": ["Attempt the question."],
                    "correct_answer": q.get("expected_answer", ""),
                },
                "kw_summary": None,
                "teacher_override": None,
            })
            continue

        try:
            result = await hybrid_evaluate(
                question=q.get("question", "") or "",
                expected_answer=q.get("expected_answer", "") or "",
                keywords=q.get("keywords") or [],
                student_answer=student_answer,
                ollama_client=llm,
                model=settings.OLLAMA_CHAT_MODEL,
                class_level=target_class,
                subject=subject,
            )
        except Exception as e:
            logger.error(f"Grading Q{qi} failed: {e}")
            result = {
                "score_out_of_10": 0.0,
                "method": "error",
                "grading_band": None,
                "keyword_score": {},
                "correct_points": [],
                "mistakes": [f"Grading error: {e}"],
                "improvements": [],
                "correct_answer": q.get("expected_answer", ""),
            }

        ai_score = float(result.get("score_out_of_10") or 0.0)
        scaled = round(ai_score * marks / 10.0, 2)
        kw = result.get("keyword_score") or {}

        graded.append({
            "question_index": qi,
            "student_answer": student_answer,
            "ai_score": ai_score,
            "ai_method": result.get("method"),
            "ai_band": result.get("grading_band"),
            "marks": marks,
            "scaled_score": scaled,
            "kw_summary": {
                "matched": kw.get("matched") or [],
                "missed": kw.get("missed") or [],
                "ratio": kw.get("ratio", 0.0),
            },
            "feedback": {
                "correct_points": result.get("correct_points") or [],
                "mistakes": result.get("mistakes") or [],
                "improvements": result.get("improvements") or [],
                "correct_answer": result.get("correct_answer") or q.get("expected_answer", ""),
            },
            "teacher_override": None,
        })
    return graded


@app.get("/api/teacher/analytics")
async def teacher_analytics(
    period: str = "30d",
    teacher: Dict = Depends(get_teacher_user),
):
    """Per-teacher usage analytics for the teacher home dashboard.

    Returns four headline counts (PDFs uploaded, Assignments created,
    Submissions graded, AI sessions in the selected period), a feature
    usage breakdown for the period, a daily activity series for the
    sparkline, and a per-class breakdown of assignments + submissions.

    `period` accepts ``1d`` / ``7d`` / ``30d`` / ``90d`` — anything else
    falls back to 30d. The window starts today minus N days so the
    rightmost bar in the sparkline is "today".
    """
    period_days = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}.get(period, 30)
    now = datetime.utcnow()
    window_start = now - timedelta(days=period_days - 1)

    email = teacher.get("email", "")
    assigned_classes = [
        _norm_class_section(c) for c in (teacher.get("assigned_classes") or [])
    ]

    # ── Headline counts ──────────────────────────────────────────────
    # 1. PDFs uploaded (all-time — teachers care about their library
    # size, not the period).
    pdfs_uploaded = await mongodb.db.uploaded_pdfs.count_documents(
        {"uploader_email": email}
    )

    # 2. Assignments created (all-time).
    assignments_created = await mongodb.db.assignments.count_documents(
        {"teacher_email": email}
    )

    # 3. Submissions graded — count submissions whose assignment belongs
    # to this teacher AND that have a non-null grade/score.
    assignment_ids: List[str] = []
    async for a in mongodb.db.assignments.find(
        {"teacher_email": email}, {"_id": 1}
    ):
        assignment_ids.append(str(a["_id"]))
    submissions_graded = 0
    if assignment_ids:
        submissions_graded = await mongodb.db.submissions.count_documents({
            "assignment_id": {"$in": assignment_ids},
            "graded_at": {"$ne": None},
        })

    # 4. AI sessions in the selected period.
    # Teacher-side generation features only — Q&A / Summary / Quiz /
    # Audio / Video are student-side flows and would always sit at 0
    # for a teacher account.
    AI_TYPES = [
        "short_answer", "long_answer", "mcq",
        "fill_in_blank", "true_false", "question_paper",
    ]
    ai_sessions_period = await mongodb.db.user_activity.count_documents({
        "user_email": email,
        "activity_type": {"$in": AI_TYPES},
        "timestamp": {"$gte": window_start},
    })

    # ── Feature usage breakdown for the period ───────────────────────
    feature_cursor = mongodb.db.user_activity.aggregate([
        {"$match": {
            "user_email": email,
            "activity_type": {"$in": AI_TYPES},
            "timestamp": {"$gte": window_start},
        }},
        {"$group": {"_id": "$activity_type", "count": {"$sum": 1}}},
    ])
    feature_usage = {row["_id"]: int(row["count"]) for row in await feature_cursor.to_list(length=None)}
    for t in AI_TYPES:
        feature_usage.setdefault(t, 0)

    # ── Daily activity series for the sparkline ──────────────────────
    daily_cursor = mongodb.db.user_activity.aggregate([
        {"$match": {
            "user_email": email,
            "timestamp": {"$gte": window_start},
        }},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ])
    by_day = {r["_id"]: int(r["count"]) for r in await daily_cursor.to_list(length=None)}
    daily_activity: List[Dict[str, Any]] = []
    for i in range(period_days):
        day = (window_start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_activity.append({"date": day, "count": by_day.get(day, 0)})

    # ── Per-class breakdown ──────────────────────────────────────────
    # For each class this teacher is assigned to, count: students in
    # roster, assignments published to that class, submissions graded
    # from that class.
    per_class: List[Dict[str, Any]] = []
    if assigned_classes:
        for cs in assigned_classes:
            student_count = await mongodb.db.users.count_documents({
                "role": "student",
                "class_section": cs,
            })
            class_assignments = []
            async for a in mongodb.db.assignments.find(
                {"teacher_email": email, "class_section": cs},
                {"_id": 1},
            ):
                class_assignments.append(str(a["_id"]))
            class_submissions = 0
            if class_assignments:
                class_submissions = await mongodb.db.submissions.count_documents({
                    "assignment_id": {"$in": class_assignments},
                })
            per_class.append({
                "class_section": cs,
                "students": student_count,
                "assignments": len(class_assignments),
                "submissions": class_submissions,
            })
        per_class.sort(key=lambda x: x["class_section"])

    return {
        "period": period,
        "period_days": period_days,
        "counts": {
            "pdfs_uploaded": pdfs_uploaded,
            "assignments_created": assignments_created,
            "submissions_graded": submissions_graded,
            "ai_sessions_period": ai_sessions_period,
        },
        "feature_usage": feature_usage,
        "daily_activity": daily_activity,
        "per_class": per_class,
    }


@app.get("/api/teacher/students")
async def teacher_list_students(teacher: Dict = Depends(get_teacher_user)):
    """List students in classes this teacher is assigned to."""
    assigned = [_norm_class_section(c) for c in (teacher.get("assigned_classes") or [])]
    if not assigned:
        return {"students": [], "by_class": {}}

    students = await user_db.list_users(role="student")
    in_scope = [
        s for s in students
        if (s.get("class_section") or
            (f"{s.get('class_level')}{s.get('section')}" if s.get('class_level') and s.get('section') else "")) in assigned
    ]
    for s in in_scope:
        s.pop("_id", None)

    by_class: Dict[str, list] = {}
    for s in in_scope:
        cs = s.get("class_section") or f"{s.get('class_level')}{s.get('section')}"
        by_class.setdefault(cs, []).append(s)

    return {"students": in_scope, "by_class": by_class}


@app.get("/api/teacher/students/{student_id}/submissions")
async def teacher_student_submissions(
    student_id: str,
    teacher: Dict = Depends(get_teacher_user),
):
    """Submission history for a student, restricted to assignments the
    requesting teacher created."""
    await _require_permission(teacher, "view_submissions")
    student = await user_db.get_user_by_id(student_id)
    if not student or _resolve_role(student) != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    cs = student.get("class_section") or (
        f"{student.get('class_level')}{student.get('section')}"
        if student.get('class_level') and student.get('section') else ""
    )
    _assert_teacher_owns_class(teacher, cs)

    subs = await submission_db.list_for_student_and_teacher(
        student_email=student["email"],
        teacher_email=teacher["email"],
    )
    for s in subs:
        s.pop("_id", None)
    return {
        "student": {
            "id": student["id"],
            "email": student["email"],
            "username": student.get("username"),
            "full_name": student.get("full_name"),
            "class_section": cs,
        },
        "submissions": subs,
        "count": len(subs),
    }


class QuestionPaperRequest(BaseModel):
    """Teacher-only: generate a mixed-type question paper.

    Counted as ONE ``question_paper`` quota unit regardless of how many
    sub-types are requested. This is the atomic "exam paper" generation
    operation, not a series of individual quiz calls.
    """
    pdf_url: str
    topic: str
    difficulty: str = "medium"
    # Section counts (any combination; zeros are skipped)
    mcq: int = 0
    short_answer: int = 0
    long_answer: int = 0
    fill_in_blank: int = 0
    true_false: int = 0
    # Optional metadata
    target_class: Optional[int] = None
    subject: Optional[str] = None


@app.post("/api/teacher/question-paper")
async def teacher_generate_question_paper(
    body: QuestionPaperRequest,
    teacher: Dict = Depends(get_teacher_user),
    _gate=Depends(gate_ai("question_paper")),
):
    """Generate a multi-section question paper as a single rate-limited
    operation. Charges 1 ``question_paper`` quota unit per call, then
    internally generates each section by calling the quiz generator. The
    returned ``questions`` list mirrors the shape that the existing teacher
    AI tabs already consume."""
    await _rate_check_and_increment(teacher, "question_paper")

    if not body.topic.strip():
        raise HTTPException(status_code=400, detail="A topic/chapter is required for question paper generation.")

    sections = [
        ("mcq",            int(body.mcq)),
        ("fill-in-blank",  int(body.fill_in_blank)),
        ("true-false",     int(body.true_false)),
        ("short-answer",   int(body.short_answer)),
        ("long-answer",    int(body.long_answer)),
    ]
    total_requested = sum(c for _, c in sections if c > 0)
    if total_requested == 0:
        raise HTTPException(status_code=400, detail="Set at least one section count > 0.")

    await _assert_upload_access(body.pdf_url, teacher)
    ready = await _ensure_pdf_ready(body.pdf_url, ensure_vector=False)
    pdf_key = ready["pdf_key"]
    pdf_data = ready["pdf_data"]
    full_text = pdf_data["full_text"]
    study_context = pdf_data.get("study_context", "")

    # Sequential generation. Tried parallel (asyncio.gather) first, but local
    # Ollama instances serialize at the model level — 5 concurrent quiz
    # generations either time out or silently return empties for most of
    # them, leaving only 1-2 successful sections. Sequential is slower
    # wall-clock but reliable: every section either succeeds completely
    # or surfaces a clear failure message to the teacher.
    active_sections = [(qt, c) for qt, c in sections if c > 0]

    combined: List[Dict[str, Any]] = []
    failures: List[str] = []
    for qtype, count in active_sections:
        try:
            section_result = await quiz_generator.generate_quiz(
                text=full_text,
                num_questions=count,
                difficulty=body.difficulty,
                study_context=study_context,
                search_query=body.topic.strip(),
                pdf_identifier=pdf_key,
                question_types=[qtype],
                target_class=body.target_class,
                subject=body.subject,
            )
        except Exception as e:
            logger.error(f"Question paper {qtype} section raised: {e}", exc_info=True)
            failures.append(f"{qtype}: {e}")
            continue

        qlist = section_result.get("questions") or []
        if not qlist:
            # Generation succeeded but produced nothing usable — usually
            # means the type-strict validator dropped every question. Tell
            # the teacher rather than silently dropping the section.
            failures.append(
                f"{qtype}: AI returned no usable questions for this section "
                f"(requested {count}). Try rephrasing the topic or lowering difficulty."
            )
            continue

        for q in qlist:
            q.setdefault("question_type", qtype)
        combined.extend(qlist)

    return _expose_expected_answer({
        "questions": combined,
        "total_questions": len(combined),
        "requested": total_requested,
        "sections_failed": failures,
    })


@app.post("/api/teacher/assignments")
async def _notify_students_of_published_assignment(
    *, teacher: Dict, assignment_id: str, class_section: str,
    title: str, due_date: Optional[datetime],
) -> int:
    """Bulk-insert one notification per student in this class+section.

    Quietly skips when no students match — useful so a teacher can publish
    in a class that hasn't been populated yet without erroring out.
    """
    try:
        cursor = mongodb.db.users.find({
            "role": "student",
            "class_section": class_section,
        })
        teacher_name = (
            teacher.get("full_name") or teacher.get("username")
            or teacher.get("email") or "Your teacher"
        )
        due_str = (
            f" Due {due_date.strftime('%d %b %I:%M %p')}." if due_date else ""
        )
        body_text = (
            f"{teacher_name} published a new assignment in {class_section}: "
            f"\"{title}\".{due_str}"
        )
        notifications: List[Dict[str, Any]] = []
        recipient_ids: List[str] = []
        async for stu in cursor:
            sid = str(stu.get("_id"))
            recipient_ids.append(sid)
            notifications.append({
                "user_id": sid,
                "type": "assignment_published",
                "title": "New assignment",
                "body": body_text,
                "link": f"assignment:{assignment_id}",
            })
        n = await notifications_db.create_many(notifications)
        return n
    except Exception as e:
        logger.error(f"publish-assignment notification fan-out failed: {e}")
        return 0


async def teacher_create_assignment(
    body: AssignmentCreate,
    teacher: Dict = Depends(get_teacher_user),
):
    """Create a new assignment (draft or published)."""
    await _require_permission(teacher, "create_assignments")
    _assert_teacher_owns_class(teacher, body.class_section)
    if not body.questions:
        raise HTTPException(status_code=400, detail="At least one question is required.")

    doc = {
        "teacher_email": teacher["email"],
        "teacher_id": teacher["id"],
        "title": body.title,
        "description": body.description or "",
        "class_section": _norm_class_section(body.class_section),
        "subject": body.subject,
        "questions": [q.dict() for q in body.questions],
        "due_date": body.due_date,
        "status": body.status,
    }
    if body.status == "published":
        doc["published_at"] = datetime.utcnow()
    aid = await assignment_db.create(doc)
    if not aid:
        raise HTTPException(status_code=500, detail="Failed to create assignment.")

    # Fire notifications for every student in the class+section as soon
    # as the assignment is published. Drafts are silent.
    if body.status == "published":
        await _notify_students_of_published_assignment(
            teacher=teacher,
            assignment_id=aid,
            class_section=_norm_class_section(body.class_section),
            title=body.title,
            due_date=body.due_date,
        )
    return {"id": aid, "message": f"Assignment {body.status}"}


@app.get("/api/teacher/assignments")
async def teacher_list_assignments(teacher: Dict = Depends(get_teacher_user)):
    items = await assignment_db.list_by_teacher(teacher["email"])
    # Attach a quick submission count per assignment
    for a in items:
        a.pop("_id", None)
        subs = await submission_db.list_for_assignment(a["id"])
        a["submission_count"] = len(subs)
    return {"assignments": items, "count": len(items)}


@app.get("/api/teacher/assignments/{assignment_id}")
async def teacher_get_assignment(
    assignment_id: str,
    teacher: Dict = Depends(get_teacher_user),
):
    a = await assignment_db.get(assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if a.get("teacher_email") != teacher["email"]:
        raise HTTPException(status_code=403, detail="Not your assignment")
    a.pop("_id", None)
    _expose_expected_answer(a)
    subs = await submission_db.list_for_assignment(assignment_id)
    for s in subs:
        s.pop("_id", None)
    return {"assignment": a, "submissions": subs, "submission_count": len(subs)}


@app.put("/api/teacher/assignments/{assignment_id}")
async def teacher_update_assignment(
    assignment_id: str,
    body: AssignmentUpdate,
    teacher: Dict = Depends(get_teacher_user),
):
    await _require_permission(teacher, "edit_assignments")
    a = await assignment_db.get(assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if a.get("teacher_email") != teacher["email"]:
        raise HTTPException(status_code=403, detail="Not your assignment")

    update_doc: Dict = {}
    if body.title is not None:
        update_doc["title"] = body.title
    if body.description is not None:
        update_doc["description"] = body.description
    if body.subject is not None:
        update_doc["subject"] = body.subject
    if body.questions is not None:
        update_doc["questions"] = [q.dict() for q in body.questions]
    if body.due_date is not None:
        update_doc["due_date"] = body.due_date
    if body.status is not None:
        update_doc["status"] = body.status

    if not update_doc:
        return {"message": "No changes"}

    # Detect a draft→published transition BEFORE saving so we know whether
    # to fan out notifications afterwards.
    was_published = (a.get("status") == "published")
    will_be_published = (update_doc.get("status") == "published")
    becoming_published = (not was_published) and will_be_published

    ok = await assignment_db.update(assignment_id, update_doc)

    if ok and becoming_published:
        await _notify_students_of_published_assignment(
            teacher=teacher,
            assignment_id=assignment_id,
            class_section=a.get("class_section") or "",
            title=update_doc.get("title") or a.get("title") or "Untitled",
            due_date=update_doc.get("due_date") or a.get("due_date"),
        )

    return {"message": "Updated" if ok else "No changes applied"}


@app.delete("/api/teacher/assignments/{assignment_id}")
async def teacher_delete_assignment(
    assignment_id: str,
    teacher: Dict = Depends(get_teacher_user),
):
    await _require_permission(teacher, "edit_assignments")
    a = await assignment_db.get(assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if a.get("teacher_email") != teacher["email"]:
        raise HTTPException(status_code=403, detail="Not your assignment")
    ok = await assignment_db.delete(assignment_id)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete")
    return {"message": "Deleted"}


@app.put("/api/teacher/submissions/{submission_id}/override")
async def teacher_override_submission(
    submission_id: str,
    body: GradeOverride,
    teacher: Dict = Depends(get_teacher_user),
):
    """Override an auto-graded answer's score (0-10 scale, will be rescaled
    against the question's marks)."""
    await _require_permission(teacher, "override_grading")
    sub = await submission_db.get(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    a = await assignment_db.get(sub.get("assignment_id"))
    if not a or a.get("teacher_email") != teacher["email"]:
        raise HTTPException(status_code=403, detail="Not your submission")

    updated = await submission_db.override_grade(
        submission_id=submission_id,
        question_index=body.question_index,
        score=body.score,
        comment=body.comment or "",
        by=teacher["email"],
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Override failed (bad index?)")
    updated.pop("_id", None)
    return {"submission": updated}


@app.get("/api/teacher/submissions/{submission_id}")
async def teacher_get_submission(
    submission_id: str,
    teacher: Dict = Depends(get_teacher_user),
):
    """Get detailed submission info for a teacher (includes grading breakdown)."""
    await _require_permission(teacher, "view_submissions")
    sub = await submission_db.get(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    a = await assignment_db.get(sub.get("assignment_id"))
    if not a or a.get("teacher_email") != teacher["email"]:
        raise HTTPException(status_code=403, detail="Not your assignment")
    sub.pop("_id", None)
    if a:
        a.pop("_id", None)
    return {"submission": sub, "assignment": a}


# =============================================================================
# STUDENT ASSIGNMENT ENDPOINTS — list, take, submit, view past submissions
# =============================================================================
@app.get("/api/student/assignments")
async def student_list_assignments(student: Dict = Depends(get_student_user)):
    """List published assignments for this student's class."""
    cs = student.get("class_section") or (
        f"{student.get('class_level')}{student.get('section')}"
        if student.get('class_level') and student.get('section') else ""
    )
    if not cs:
        return {"assignments": [], "count": 0,
                "warning": "Your class is not set; ask the admin to assign one."}
    items = await assignment_db.list_for_class(cs, only_published=True)
    # Attach the student's own submission for each (if any)
    for a in items:
        a.pop("_id", None)
        sub = await submission_db.get_by_student_and_assignment(student["email"], a["id"])
        if sub:
            a["my_submission"] = {
                "id": sub.get("id") or str(sub.get("_id")),
                "submitted_at": sub.get("submitted_at"),
                "total_score": sub.get("total_score"),
                "total_max": sub.get("total_max"),
                "percent": sub.get("percent"),
            }
        else:
            a["my_submission"] = None
    return {"assignments": items, "count": len(items)}


@app.get("/api/student/assignments/{assignment_id}")
async def student_get_assignment(
    assignment_id: str,
    student: Dict = Depends(get_student_user),
):
    a = await assignment_db.get(assignment_id)
    if not a or a.get("status") != "published":
        raise HTTPException(status_code=404, detail="Assignment not available")
    cs = student.get("class_section") or (
        f"{student.get('class_level')}{student.get('section')}"
        if student.get('class_level') and student.get('section') else ""
    )
    if a.get("class_section") != cs:
        raise HTTPException(status_code=403, detail="Not for your class")
    a.pop("_id", None)
    # Strip expected_answer/keywords so a student inspecting the network call
    # doesn't see the answer key
    safe_questions = []
    for q in a.get("questions") or []:
        safe_questions.append({
            "question": q.get("question"),
            "marks": q.get("marks"),
            "target_class": q.get("target_class"),
            "subject": q.get("subject"),
        })
    a["questions"] = safe_questions

    existing = await submission_db.get_by_student_and_assignment(student["email"], assignment_id)
    if existing:
        existing.pop("_id", None)
    return {"assignment": a, "my_submission": existing}


@app.post("/api/student/assignments/{assignment_id}/submit")
async def student_submit_assignment(
    assignment_id: str,
    body: SubmissionCreate,
    student: Dict = Depends(get_student_user),
):
    """Submit answers — auto-grades immediately and stores the result."""
    await _require_permission(student, "submit_assignments")
    a = await assignment_db.get(assignment_id)
    if not a or a.get("status") != "published":
        raise HTTPException(status_code=404, detail="Assignment not available")
    cs = student.get("class_section") or (
        f"{student.get('class_level')}{student.get('section')}"
        if student.get('class_level') and student.get('section') else ""
    )
    if a.get("class_section") != cs:
        raise HTTPException(status_code=403, detail="Not for your class")

    existing = await submission_db.get_by_student_and_assignment(student["email"], assignment_id)
    if existing:
        raise HTTPException(status_code=400, detail="You have already submitted this assignment.")

    questions = a.get("questions") or []
    answers_in = [a.dict() for a in body.answers]
    graded = await _grade_submission_answers(
        questions, answers_in, student.get("class_level"),
    )
    total = sum(float(g.get("scaled_score") or 0) for g in graded)
    total_max = sum(float(g.get("marks") or 0) for g in graded)
    percent = round((total / total_max * 100), 1) if total_max else 0.0

    sub_doc = {
        "assignment_id": assignment_id,
        "student_email": student["email"],
        "student_id": student["id"],
        "class_section": cs,
        "answers": graded,
        "total_score": round(total, 2),
        "total_max": round(total_max, 2),
        "percent": percent,
    }
    sid = await submission_db.create(sub_doc)
    if not sid:
        raise HTTPException(status_code=500, detail="Failed to save submission.")

    asyncio.create_task(activity_db.log_activity(
        student["email"], "assignment_submitted",
        {
            "assignment_id": assignment_id,
            "percent": percent,
            "total_score": round(total, 2),
            "total_max": round(total_max, 2),
        },
    ))

    # Notify the teacher who owns the assignment. We look up by email
    # because that's what's stored on the assignment document.
    try:
        teacher_email = a.get("teacher_email")
        if teacher_email:
            teacher_doc = await user_db.get_user_by_email(teacher_email)
            if teacher_doc:
                student_name = (
                    student.get("full_name") or student.get("username")
                    or student.get("email") or "A student"
                )
                teacher_id = str(teacher_doc.get("id") or teacher_doc.get("_id"))
                await notifications_db.create(
                    user_id=teacher_id,
                    type_="submission_received",
                    title="New submission",
                    body=(
                        f"{student_name} ({cs}) submitted "
                        f"\"{a.get('title', 'an assignment')}\" — "
                        f"auto-graded {percent}%."
                    ),
                    link=f"submission:{sid}",
                )
                await emit_notification_created(teacher_id)
    except Exception as e:
        logger.error(f"submission-received notification failed: {e}")

    sub_doc["id"] = sid
    return {
        "submission": sub_doc,
        "message": f"Submitted! Auto-graded: {percent}% ({total:.1f} / {total_max:.0f}).",
    }


@app.get("/api/student/submissions")
async def student_list_submissions(student: Dict = Depends(get_student_user)):
    await _require_permission(student, "view_own_grades")
    items = await submission_db.list_for_student(student["email"])
    for s in items:
        s.pop("_id", None)
        # Also attach the assignment title for display
        if s.get("assignment_id"):
            a = await assignment_db.get(s["assignment_id"])
            if a:
                s["assignment_title"] = a.get("title")
    return {"submissions": items, "count": len(items)}


@app.get("/api/student/submissions/{submission_id}")
async def student_get_submission(
    submission_id: str,
    student: Dict = Depends(get_student_user),
):
    await _require_permission(student, "view_own_grades")
    s = await submission_db.get(submission_id)
    if not s or s.get("student_email") != student["email"]:
        raise HTTPException(status_code=404, detail="Submission not found")
    s.pop("_id", None)
    a = await assignment_db.get(s.get("assignment_id"))
    if a:
        a.pop("_id", None)
        # Hide answer keys until after submission? Already submitted, so OK to return.
    return {"submission": s, "assignment": a}


@app.get("/api/student/progress")
async def student_progress(student: Dict = Depends(get_student_user)):
    """Aggregate dashboard data for the student Home page:
      - features_used: list of feature keys the student has used at least once
      - total_features: total trackable features
      - streak_days: consecutive-day login/activity streak (calculated from user_activity)
      - recent_pdfs: up to 6 most recent uploads with last-action info
      - last_used_pdf: the single most recently used PDF
      - pending_assignments: count of published assignments not yet submitted
      - onboarding_completed: bool
    """
    from datetime import timedelta

    email = student["email"]

    # ── 1. Features used (distinct activity_type values)
    feature_map = {
        "pdf_upload": "upload",
        "qa": "qa",
        "quiz": "quiz",
        "summary": "summary",
        "audio": "audio",
        "video": "video",
        "qa_multi": "multi_doc",
        "assignment_submitted": "submit",
    }
    activity_types = await mongodb.db.user_activity.distinct(
        "activity_type", {"user_email": email}
    )
    features_used = sorted({
        feature_map[t] for t in activity_types if t in feature_map
    })
    total_features = len(set(feature_map.values()))

    # ── 2. Streak (count consecutive days back from today with at least 1 activity)
    streak_days = 0
    try:
        now = datetime.utcnow()
        # Pull last 30 days of activity timestamps. Cap result count to 500
        # so an unusually active student doesn't make this query slow.
        cursor = mongodb.db.user_activity.find(
            {
                "user_email": email,
                "timestamp": {"$gte": now - timedelta(days=30)},
            },
            {"timestamp": 1, "_id": 0},
        ).sort("timestamp", -1).limit(500)
        timestamps = [d["timestamp"] async for d in cursor]
        active_days = {ts.date() for ts in timestamps if ts}
        today = now.date()
        check_day = today
        # Allow today to be inactive (still counts streak from yesterday)
        if check_day not in active_days:
            check_day -= timedelta(days=1)
        while check_day in active_days:
            streak_days += 1
            check_day -= timedelta(days=1)
    except Exception as e:
        logger.warning(f"Streak calc failed for {email}: {e}")

    # ── 3. Recent PDFs (most recent 6)
    recent_pdfs = await pdf_upload_db.get_user_uploads(email, limit=6)
    # Attach a "last_action" derived from user_activity per PDF (best effort).
    # Cap to most recent 50 activity events — enough to find the latest action
    # for each of the 6 recent PDFs without scanning the whole activity log.
    last_action_per_pdf: Dict[str, Dict[str, Any]] = {}
    try:
        cursor = mongodb.db.user_activity.find(
            {
                "user_email": email,
                "activity_type": {"$in": list(feature_map.keys())},
            },
            {"activity_type": 1, "details": 1, "timestamp": 1, "_id": 0},
        ).sort("timestamp", -1).limit(50)
        async for entry in cursor:
            details = entry.get("details") or {}
            pdf_key = details.get("pdf") or details.get("pdf_id") or details.get("filename")
            if not pdf_key:
                continue
            if pdf_key not in last_action_per_pdf:
                last_action_per_pdf[pdf_key] = {
                    "action": feature_map.get(entry.get("activity_type"), entry.get("activity_type")),
                    "at": entry.get("timestamp").isoformat() if entry.get("timestamp") else None,
                }
    except Exception as e:
        logger.warning(f"Last-action lookup failed: {e}")

    for p in recent_pdfs:
        key = p.get("pdf_identifier") or p.get("filename")
        info = last_action_per_pdf.get(key) or {}
        p["last_action"] = info.get("action")
        p["last_action_at"] = info.get("at")

    last_used_pdf = recent_pdfs[0] if recent_pdfs else None

    # ── 4. Pending assignments (published assignments for this class with no submission)
    cs = student.get("class_section") or (
        f"{student.get('class_level')}{student.get('section')}"
        if student.get("class_level") and student.get("section") else ""
    )
    pending_assignments = 0
    if cs:
        try:
            assignments = await assignment_db.list_for_class(cs, only_published=True)
            # Batched query — fetch ALL of this student's submission assignment IDs
            # in a SINGLE round-trip instead of one query per assignment (N+1 → 1).
            submitted_ids: set = set()
            if assignments:
                cursor = mongodb.db.submissions.find(
                    {"student_email": email},
                    {"assignment_id": 1, "_id": 0},
                )
                async for s in cursor:
                    aid = s.get("assignment_id")
                    if aid:
                        submitted_ids.add(str(aid))

            for a in assignments:
                aid = str(a.get("_id") or a.get("id"))
                if aid not in submitted_ids:
                    pending_assignments += 1
        except Exception as e:
            logger.warning(f"Pending assignments calc failed: {e}")

    return {
        "features_used": features_used,
        "total_features": total_features,
        "streak_days": streak_days,
        "recent_pdfs": recent_pdfs,
        "last_used_pdf": last_used_pdf,
        "pending_assignments": pending_assignments,
        "onboarding_completed": bool(student.get("onboarding_completed", False)),
    }


# ==================== PDF PROCESSING ENDPOINTS ====================

@app.post("/api/debug/upload-test")
async def debug_upload_test(request: Request):
    """Debug endpoint to check if Authorization header is received"""
    logger.info(f"📋 Debug upload test called")
    auth_header = request.headers.get('Authorization', 'NO HEADER FOUND')
    logger.info(f"Authorization header value: {auth_header}")
    logger.info(f"All headers: {list(request.headers.keys())}")
    
    if auth_header and auth_header != 'NO HEADER FOUND':
        logger.info(f"Header preview: {auth_header[:50]}...")
    
    return {
        "auth_header_present": auth_header != 'NO HEADER FOUND',
        "auth_header": auth_header[:50] if auth_header != 'NO HEADER FOUND' else auth_header,
        "all_header_keys": list(request.headers.keys())
    }

@app.post("/api/upload_pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
    _gate=Depends(gate_pdf("upload")),
):
    """Upload and process local PDF file.

    Auth is delegated to `get_current_user`, the same dependency every
    other endpoint uses. That dependency routes through `auth_backend`,
    which knows how to validate both local JWTs (signed by our
    JWT_SECRET_KEY) and eskoolia JWTs (validated by calling the ERP's
    /api/v1/auth/me/). Hand-rolling the verification here previously
    broke uploads whenever `AUTH_PROVIDER=eskoolia` was active, because
    the token in the bearer header was ERP-signed and our local
    verify_token() couldn't validate it.
    """
    try:
        logger.info(f"Starting PDF upload: {file.filename}")

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        upload_id = uuid4().hex
        stored_filename = f"{upload_id}.pdf"
        pdf_identifier = f"upload_{upload_id}"

        # Save uploaded file using a unique server-side name so different users do not collide.
        file_path = Path(settings.UPLOAD_DIR) / stored_filename

        # Hard size limit — protects the box's RAM and disk from a
        # malicious / runaway upload. Configurable via MAX_PDF_UPLOAD_MB
        # in .env (default 50 MB matches what a typical NCERT textbook
        # PDF chapter looks like). Streaming read keeps memory flat
        # regardless of file size.
        max_bytes = int(getattr(settings, "MAX_PDF_UPLOAD_MB", 50)) * 1024 * 1024
        bytes_written = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    f.close()
                    try:
                        file_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"PDF too large. Max allowed is {max_bytes // (1024 * 1024)} MB.",
                    )
                f.write(chunk)
            if bytes_written == 0:
                f.close()
                try:
                    file_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        # Get file size
        file_size = file_path.stat().st_size

        # Mirror the upload to shared object storage (no-op in local mode) so a
        # different instance can re-process / re-index this PDF later. Runs off
        # the event loop — the upload is blocking I/O.
        asyncio.create_task(
            asyncio.to_thread(storage.mirror_to_remote, "uploads", stored_filename, "application/pdf")
        )

        logger.info(f"Processing uploaded PDF: {file.filename}")

        # Fast path: process and chunk now; warm vectors in the background for later AI calls.
        ready = await _ensure_pdf_ready(pdf_identifier, ensure_vector=False)
        pdf_data = ready["pdf_data"]
        asyncio.create_task(_warm_pdf_vectors(pdf_identifier))
        
        # Log the PDF upload with the real derived counts so the admin
        # table shows meaningful Pages/Chunks immediately.
        await pdf_upload_db.log_upload(
            filename=file.filename,
            file_size=file_size,
            uploader_email=current_user['email'],
            pdf_identifier=pdf_identifier,
            stored_filename=stored_filename,
            total_pages=int(pdf_data.get("total_pages") or 0),
            total_chunks=int(pdf_data.get("total_chunks") or 0),
            total_chars=int(pdf_data.get("total_chars") or 0),
        )
        
        return {
            "status": "success",
            "message": "PDF uploaded and processed successfully",
            "pdf_identifier": pdf_identifier,
            "vector_indexed": False,
            "filename": file.filename,
            "total_pages": pdf_data.get("total_pages", 0),
            "total_chunks": pdf_data["total_chunks"],
            "total_chars": pdf_data["total_chars"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def _is_upload_identifier(pdf_ref: str) -> bool:
    return pdf_ref.startswith("upload_")

def _resolve_upload_path(pdf_identifier: str) -> Path:
    raw_identifier = pdf_identifier.replace("upload_", "", 1)
    candidates: List[Path] = []

    if raw_identifier.lower().endswith(".pdf"):
        candidates.append(Path(settings.UPLOAD_DIR) / raw_identifier)
    else:
        candidates.append(Path(settings.UPLOAD_DIR) / f"{raw_identifier}.pdf")
        candidates.append(Path(settings.UPLOAD_DIR) / raw_identifier)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Not on this instance's disk — in remote-storage mode, try to pull the
    # canonical object down so processing can proceed. No-op in local mode.
    canonical = raw_identifier if raw_identifier.lower().endswith(".pdf") else f"{raw_identifier}.pdf"
    fetched = storage.ensure_local("uploads", canonical)
    if fetched is not None:
        return fetched

    return candidates[0]

async def _assert_upload_access(pdf_ref: str, current_user: Dict) -> None:
    """Ensure a user can access only their own uploaded PDFs."""
    if not pdf_ref or not _is_upload_identifier(pdf_ref):
        return

    upload = await pdf_upload_db.get_upload_by_identifier(pdf_ref)
    if not upload:
        raise HTTPException(status_code=404, detail="Uploaded PDF not found")

    if upload.get("uploader_email") != current_user.get("email"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can access only the PDFs uploaded by your own account"
        )

def _looks_like_pdf(url: str) -> bool:
    lower = url.lower()
    parsed = urlparse(lower)
    return parsed.path.endswith(".pdf") or ".pdf" in parsed.path or ".pdf" in lower

def _extract_pdf_links(html: str, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: List[str] = []

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href")
        full = urljoin(base_url, href)
        if _looks_like_pdf(full):
            candidates.append(full)

    for tag_name, attr in [("iframe", "src"), ("embed", "src"), ("object", "data")]:
        for tag in soup.find_all(tag_name):
            src = tag.get(attr)
            if not src:
                continue
            full = urljoin(base_url, src)
            if _looks_like_pdf(full):
                candidates.append(full)

    seen = set()
    unique = []
    for link in candidates:
        if link not in seen:
            unique.append(link)
            seen.add(link)

    return unique

def _resolve_pdf_url(input_url: str) -> str:
    if _looks_like_pdf(input_url):
        return input_url

    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(input_url, headers=headers, timeout=20)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "application/pdf" in content_type:
        return input_url

    links = _extract_pdf_links(response.text, input_url)
    if not links:
        raise HTTPException(status_code=400, detail="No PDF links found on the page")

    return links[0]


def _resolve_pdf_url_cached(input_url: str) -> str:
    cached = _resolved_pdf_url_cache.get(input_url)
    if cached:
        return cached
    resolved = _resolve_pdf_url(input_url)
    _resolved_pdf_url_cache[input_url] = resolved
    return resolved


async def _ensure_pdf_ready(pdf_ref: str, ensure_vector: bool = True) -> Dict[str, Any]:
    """Return normalized pdf_key and processed PDF data, reusing cache/index when possible."""
    if _is_upload_identifier(pdf_ref):
        pdf_key = pdf_ref
    else:
        pdf_key = _resolve_pdf_url_cached(pdf_ref)

    cached_data = _cache_get(pdf_key)
    has_vectors = vector_db.collection_has_documents(pdf_key) if ensure_vector else True
    if cached_data is not None and has_vectors:
        return {"pdf_key": pdf_key, "pdf_data": cached_data}

    lock = _get_pdf_lock(pdf_key)
    async with lock:
        cached_data = _cache_get(pdf_key)
        has_vectors = vector_db.collection_has_documents(pdf_key) if ensure_vector else True

        if cached_data is None:
            if _is_upload_identifier(pdf_key):
                file_path = _resolve_upload_path(pdf_key)
                if not file_path.exists():
                    raise HTTPException(status_code=404, detail="Uploaded PDF not found")
                cached_data = await pdf_handler.process_pdf(str(file_path), is_url=False)
            else:
                cached_data = await pdf_handler.process_pdf(pdf_key, is_url=True)
            _cache_set(pdf_key, cached_data)

        if "study_context" not in cached_data:
            cached_data["study_context"] = pdf_handler.build_study_context(
                cached_data.get("chunks", []),
                cached_data.get("pages_text", []),
                sections=cached_data.get("sections", []),
            )

        if ensure_vector and not has_vectors:
            chunk_texts = [chunk["text"] for chunk in cached_data["chunks"]]
            metadatas = [
                {
                    "chunk_index": i,
                    "page_number": int(chunk.get("metadata", {}).get("page_number", 0) or 0),
                    "chapter": str(chunk.get("metadata", {}).get("chapter", "") or ""),
                    "topic": str(chunk.get("metadata", {}).get("topic", "") or ""),
                    "section_code": str(chunk.get("metadata", {}).get("section_code", "") or ""),
                    "section_title": str(chunk.get("metadata", {}).get("section_title", "") or ""),
                    "start_pos": int(chunk.get("start_pos", 0) or 0),
                    "end_pos": int(chunk.get("end_pos", 0) or 0)
                }
                for i, chunk in enumerate(cached_data["chunks"])
            ]
            await vector_db.add_documents(pdf_url=pdf_key, chunks=chunk_texts, metadata=metadatas)

    return {"pdf_key": pdf_key, "pdf_data": cached_data}

async def _process_pdf_source(pdf_ref: str) -> Dict:
    if _is_upload_identifier(pdf_ref):
        file_path = _resolve_upload_path(pdf_ref)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Uploaded PDF not found")
        return await pdf_handler.process_pdf(str(file_path), is_url=False)

    resolved_url = _resolve_pdf_url(pdf_ref)
    return await pdf_handler.process_pdf(resolved_url, is_url=True)

# ==================== AI FEATURE ENDPOINTS ====================

def _friendly_error(e: Exception) -> str:
    """Convert raw exceptions to user-friendly messages."""
    msg = str(e).lower()
    if "connect" in msg or "connection" in msg:
        return "Cannot reach the AI model. Please make sure Ollama is running."
    if "timed out" in msg or "timeout" in msg:
        return "The AI model took too long to respond. Please try again — shorter questions work faster."
    if "parse" in msg or "json" in msg:
        return "The AI returned an unexpected format. Please try again."
    return str(e)

@app.post("/api/summarize")
async def generate_summary(request: SummaryRequest, current_user: Dict = Depends(rate_limit("summary")), _gate=Depends(gate_ai("summary"))):
    """Generate summary from PDF"""
    try:
        started = time.perf_counter()
        phase_started = time.perf_counter()
        await _assert_upload_access(request.pdf_url, current_user)
        log_phase(logger, "api.summary", "access_check", phase_started)
        phase_started = time.perf_counter()
        ready = await _ensure_pdf_ready(request.pdf_url, ensure_vector=False)
        log_phase(logger, "api.summary", "ensure_pdf_ready", phase_started)
        pdf_key = ready["pdf_key"]
        pdf_data = ready["pdf_data"]
        full_text = pdf_data["full_text"]
        study_context = pdf_data.get("study_context", "")
        cache_key = _ai_cache_key(
            "summary",
            pdf_key,
            {"summary_type": request.summary_type}
        )
        phase_started = time.perf_counter()
        cached = _ai_cache_get(cache_key)
        if cached is not None:
            logger.info(f"Summary cache hit for {pdf_key} ({request.summary_type})")
            log_phase(logger, "api.summary", "cache_lookup", phase_started, cache_hit=True)
            log_phase(logger, "api.summary", "total", started, cache_hit=True)
            return cached
        log_phase(logger, "api.summary", "cache_lookup", phase_started, cache_hit=False)
        
        phase_started = time.perf_counter()
        topic = (request.topic or "").strip() or None
        if request.summary_type == "short":
            summary = await summary_generator.generate_short_summary(full_text, study_context=study_context, topic=topic)
            result = {"summary": summary, "type": "short"}
        elif request.summary_type == "detailed":
            summary = await summary_generator.generate_detailed_summary(full_text, study_context=study_context, topic=topic)
            result = {"summary": summary, "type": "detailed"}
        else:  # both
            result = await summary_generator.generate_both_summaries(full_text, study_context=study_context, topic=topic)
        log_phase(logger, "api.summary", "generate_summary", phase_started, summary_type=request.summary_type)
        asyncio.create_task(activity_db.log_activity(current_user["email"], "summary", {"pdf": pdf_key, "type": request.summary_type}))
        # Persist the actual summary content so the AI Evaluation tab can
        # score it later. We store a sample of the source text alongside so
        # the judge has grounding for faithfulness scoring.
        try:
            _summary_text = ""
            if isinstance(result, dict):
                _summary_text = (
                    result.get("summary")
                    or result.get("short")
                    or result.get("detailed")
                    or ""
                )
            if _summary_text:
                asyncio.create_task(mongodb.db.generated_summaries.insert_one({
                    "user_email": current_user["email"],
                    "pdf_ref": pdf_key,
                    "summary_type": request.summary_type,
                    "content": str(_summary_text)[:8000],
                    "source_excerpt": (full_text or "")[:15000],
                    "created_at": datetime.utcnow(),
                }))
        except Exception as _persist_err:
            logger.debug(f"Summary persist (non-blocking) failed: {_persist_err}")

        _ai_cache_set(cache_key, result)
        log_phase(logger, "api.summary", "total", started, cache_hit=False, summary_type=request.summary_type)
        logger.info(f"Summary generated in {time.perf_counter() - started:.2f}s for {pdf_key} ({request.summary_type})")
        return result
            
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/quiz")
async def generate_quiz(request: QuizRequest, current_user: Dict = Depends(get_current_user), _gate=Depends(gate_ai("quiz"))):
    """Generate quiz from PDF.

    Rate-limit bucket is resolved at runtime from the user's role and the
    requested question_type. Students consume a single ``quiz`` counter;
    teachers consume one of ``short_answer`` / ``long_answer`` / ``mcq`` /
    ``fill_in_blank`` based on which AI tab they used in New Assignment.
    """
    from rate_limiting import _resolve_role
    role = _resolve_role(current_user)
    requested_types = request.question_types or ["mcq"]
    quiz_feature = map_quiz_feature(role, requested_types[0] if requested_types else "mcq")
    await _rate_check_and_increment(current_user, quiz_feature)

    try:
        started = time.perf_counter()
        phase_started = time.perf_counter()
        await _assert_upload_access(request.pdf_url, current_user)
        log_phase(logger, "api.quiz", "access_check", phase_started)
        logger.info(
            f"Quiz request received: pdf_url={request.pdf_url}, num_questions={request.num_questions}, difficulty={request.difficulty}, search={request.search_query}"
        )
        phase_started = time.perf_counter()
        ready = await _ensure_pdf_ready(request.pdf_url, ensure_vector=False)
        log_phase(logger, "api.quiz", "ensure_pdf_ready", phase_started)
        pdf_key = ready["pdf_key"]
        pdf_data = ready["pdf_data"]
        full_text = pdf_data["full_text"]
        study_context = pdf_data.get("study_context", "")
        cache_key = _ai_cache_key(
            "quiz",
            pdf_key,
            {
                "num_questions": request.num_questions,
                "difficulty": request.difficulty or "",
                "search_query": request.search_query or "",
                "question_types": ",".join(request.question_types or ["mcq"])
            }
        )
        phase_started = time.perf_counter()
        cached = _ai_cache_get(cache_key)
        if cached is not None:
            logger.info(f"Quiz cache hit for {pdf_key} ({request.num_questions} questions, {request.difficulty}, search={request.search_query})")
            log_phase(logger, "api.quiz", "cache_lookup", phase_started, cache_hit=True)
            log_phase(logger, "api.quiz", "total", started, cache_hit=True)
            return cached
        log_phase(logger, "api.quiz", "cache_lookup", phase_started, cache_hit=False)

        phase_started = time.perf_counter()
        quiz_data = await quiz_generator.generate_quiz(
            full_text,
            request.num_questions,
            request.difficulty,
            study_context=study_context,
            search_query=request.search_query,
            pdf_identifier=pdf_key,
            question_types=request.question_types or ["mcq"],
            target_class=request.target_class,
            subject=request.subject,
        )
        # Phase 4: tag every generated question with target_class + subject
        # so the evaluator can later check student/question class alignment
        if request.target_class is not None or request.subject:
            for q in (quiz_data.get("questions") or []):
                if request.target_class is not None:
                    q["target_class"] = int(request.target_class)
                if request.subject:
                    q["subject"] = request.subject
        log_phase(logger, "api.quiz", "generate_quiz", phase_started, requested_questions=request.num_questions or 3)
        _ai_cache_set(cache_key, quiz_data)
        log_phase(logger, "api.quiz", "total", started, cache_hit=False, questions=quiz_data.get("total_questions", 0))
        logger.info(
            f"Quiz generated successfully with {quiz_data.get('total_questions', 0)} questions "
            f"in {time.perf_counter() - started:.2f}s"
        )
        asyncio.create_task(activity_db.log_activity(current_user["email"], "quiz", {"pdf": pdf_key, "questions": quiz_data.get("total_questions", 0)}))
        # Persist the actual quiz questions so the AI Evaluation tab can
        # later judge their validity + correctness against the source PDF.
        try:
            # Store a larger excerpt (15k chars) so the judge has enough of
            # the source PDF to actually verify whether the question/answer
            # is faithful to it. 6k was missing relevant chapters.
            asyncio.create_task(mongodb.db.generated_quizzes.insert_one({
                "user_email": current_user["email"],
                "pdf_ref": pdf_key,
                "question_type": getattr(request, "question_type", None),
                "difficulty": getattr(request, "difficulty", None),
                "questions": list(quiz_data.get("questions") or []),
                "source_excerpt": (full_text or "")[:15000],
                "created_at": datetime.utcnow(),
            }))
        except Exception as _persist_err:
            logger.debug(f"Quiz persist (non-blocking) failed: {_persist_err}")
        return _expose_expected_answer(quiz_data)

    except Exception as e:
        # Tier 3 fallback case: both LLM providers are down. Quiz has no
        # acceptable extractive fallback so we return 503 with a clear,
        # user-friendly message that the frontend can detect and display.
        from ai.fallback_helpers import AIServiceUnavailable
        if isinstance(e, AIServiceUnavailable):
            logger.warning("Quiz unavailable (both LLMs down): %s", e)
            raise HTTPException(
                status_code=503,
                detail="Quiz temporarily unavailable, try Summary or Q&A instead.",
            )

        error_msg = str(e).lower()
        # Check if this is a validation error (expected user input issue) vs system error
        if "not found in the pdf" in error_msg or "topic" in error_msg:
            # Log validation errors as INFO (expected behavior, not a bug)
            logger.info(f"Quiz validation error: {e}")
        else:
            # Log real system errors as ERROR
            logger.error(f"Error generating quiz: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=400 if "not found in the pdf" in error_msg else 500, detail=msg)

# ──────────────────────────────────────────────────────────────────────────
# Active quiz persistence — survives browser reload so students don't lose
# a generated quiz when they hit Ctrl+R mid-attempt. One active quiz per
# (user, pdf). On submit the student deletes it; on regenerate it's
# overwritten via upsert.
# ──────────────────────────────────────────────────────────────────────────

@app.post("/api/quiz/active")
async def save_active_quiz(
    body: Dict[str, Any],
    current_user: Dict = Depends(get_current_user),
):
    """Save (or overwrite) the student's currently-in-progress quiz for a
    given PDF. Body: {pdf_id, questions, question_type, difficulty, answers?}.
    """
    pdf_id = (body.get("pdf_id") or "").strip()
    if not pdf_id:
        raise HTTPException(status_code=400, detail="pdf_id is required")
    questions = body.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="questions list is required")

    doc = {
        "user_email": current_user["email"],
        "pdf_ref": pdf_id,
        "question_type": body.get("question_type") or "mcq",
        "difficulty": body.get("difficulty") or "basic",
        "questions": questions,
        "answers": body.get("answers") or {},
        "updated_at": datetime.utcnow(),
    }
    # Upsert so a fresh generate overwrites any previous active quiz for the
    # same student + PDF. created_at is only set on first insert.
    await mongodb.db.active_quizzes.update_one(
        {"user_email": current_user["email"], "pdf_ref": pdf_id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
        upsert=True,
    )
    return {"message": "Active quiz saved"}


@app.get("/api/quiz/active/{pdf_id}")
async def get_active_quiz(
    pdf_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Return the saved active quiz for this (user, pdf), or 404 if none."""
    doc = await mongodb.db.active_quizzes.find_one({
        "user_email": current_user["email"],
        "pdf_ref": pdf_id,
    })
    if not doc:
        raise HTTPException(status_code=404, detail="No active quiz for this PDF")
    doc["id"] = str(doc.pop("_id"))
    for k in ("created_at", "updated_at"):
        if isinstance(doc.get(k), datetime):
            doc[k] = doc[k].isoformat()
    # Legacy active quizzes were persisted with the old `correct_answer`
    # field name — rename in flight so the editor sees `expected_answer`.
    _expose_expected_answer(doc)
    return doc


@app.delete("/api/quiz/active/{pdf_id}")
async def discard_active_quiz(
    pdf_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Discard the saved active quiz (called on submit or 'Restart')."""
    result = await mongodb.db.active_quizzes.delete_one({
        "user_email": current_user["email"],
        "pdf_ref": pdf_id,
    })
    return {"deleted": result.deleted_count}


# ──────────────────────────────────────────────────────────────────────────
# Quiz attempts — saved on submission so the student's History tab can
# show past scores and let them re-view questions/answers later.
# ──────────────────────────────────────────────────────────────────────────

@app.post("/api/student/quiz-attempt")
async def save_quiz_attempt(
    body: Dict[str, Any],
    current_user: Dict = Depends(get_current_user),
):
    """Persist a completed quiz attempt. Frontend calls this on Submit."""
    pdf_id = (body.get("pdf_id") or "").strip()
    questions = body.get("questions") or []
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=400, detail="questions list required")
    score = int(body.get("score") or 0)
    total = int(body.get("total") or len(questions))
    percent = int((score / total) * 100) if total else 0
    doc = {
        "user_email": current_user["email"],
        "pdf_ref": pdf_id,
        "question_type": body.get("question_type") or "mcq",
        "difficulty": body.get("difficulty") or "basic",
        "questions": questions,
        "answers": body.get("answers") or {},
        "score": score,
        "total": total,
        "percent": percent,
        "submitted_at": datetime.utcnow(),
    }
    result = await mongodb.db.quiz_attempts.insert_one(doc)
    return {"id": str(result.inserted_id), "score": score, "percent": percent}


# ──────────────────────────────────────────────────────────────────────────
# Student history endpoints — read-only views over each generation type,
# scoped to the calling student. Used by the History tab in the Student
# Dashboard.
# ──────────────────────────────────────────────────────────────────────────

def _stringify_id_and_dates(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Mongo's _id + datetime fields to JSON-safe strings in place."""
    if not doc:
        return doc
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    for k, v in list(doc.items()):
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


def _expose_expected_answer(payload: Any) -> Any:
    """Rename the internal ``correct_answer`` field to ``expected_answer``
    on every question in a quiz-shaped payload before it ships to the
    frontend.

    The AI pipeline + grading code call the model answer ``correct_answer``
    (matches the LLM JSON schema, MCQ option letter math, etc.); the
    frontend, including the student quiz scorer and the teacher
    new-assignment editor, has always read ``expected_answer``. This
    helper bridges the two without touching the parser, validator, or
    grading paths.

    Accepts:
        - a dict shaped like ``{"questions": [...]}`` (the quiz and
          question-paper response shape) — renames in-place on each item
        - a single question dict
        - a list of question dicts
        - any other shape (returned unchanged)

    Idempotent: if a question already has ``expected_answer`` set, the
    rename is a no-op for that item.
    """
    if payload is None:
        return payload

    def _patch(q: Dict[str, Any]) -> None:
        if not isinstance(q, dict):
            return
        if "expected_answer" not in q and "correct_answer" in q:
            q["expected_answer"] = q.get("correct_answer")

    if isinstance(payload, list):
        for q in payload:
            _patch(q)
        return payload

    if isinstance(payload, dict):
        qs = payload.get("questions")
        if isinstance(qs, list):
            for q in qs:
                _patch(q)
        else:
            # Bare single-question dict.
            _patch(payload)
    return payload


@app.get("/api/student/history/qa")
async def history_qa(
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Past Q&A chat sessions for the current student (newest first)."""
    cursor = (
        mongodb.db.chat_sessions.find({"user_email": current_user["email"]})
        .sort("updated_at", -1)
        .limit(int(limit))
    )
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        d["message_count"] = len(d.get("messages") or [])
        # Drop the full messages array — keeps the list payload small.
        d.pop("messages", None)
        items.append(_stringify_id_and_dates(d))
    return {"items": items, "count": len(items)}


@app.get("/api/student/history/quizzes")
async def history_quizzes(
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Past quiz attempts (newest first), including the score."""
    cursor = (
        mongodb.db.quiz_attempts.find({"user_email": current_user["email"]})
        .sort("submitted_at", -1)
        .limit(int(limit))
    )
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        _expose_expected_answer(d)
        items.append(_stringify_id_and_dates(d))
    return {"items": items, "count": len(items)}


@app.get("/api/student/history/summaries")
async def history_summaries(
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Past generated summaries (newest first)."""
    cursor = (
        mongodb.db.generated_summaries.find({"user_email": current_user["email"]})
        .sort("created_at", -1)
        .limit(int(limit))
    )
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        # Drop source_excerpt from list payload — it can be large. Frontend
        # can fetch full doc by id if it needs it later.
        d.pop("source_excerpt", None)
        items.append(_stringify_id_and_dates(d))
    return {"items": items, "count": len(items)}


@app.get("/api/student/history/audio")
async def history_audio(
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Past audio generations (newest first)."""
    cursor = (
        mongodb.db.generated_audio.find({"user_email": current_user["email"]})
        .sort("created_at", -1)
        .limit(int(limit))
    )
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        items.append(_stringify_id_and_dates(d))
    return {"items": items, "count": len(items)}


@app.get("/api/student/history/video")
async def history_video(
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Past video generations (newest first)."""
    cursor = (
        mongodb.db.generated_video.find({"user_email": current_user["email"]})
        .sort("created_at", -1)
        .limit(int(limit))
    )
    items: List[Dict[str, Any]] = []
    async for d in cursor:
        items.append(_stringify_id_and_dates(d))
    return {"items": items, "count": len(items)}


async def _auto_name_session(session_id: str, user_email: str, question: str, answer: str) -> None:
    """Use a quick LLM call to generate a short conversation title after the first exchange."""
    import re as _re
    def _fallback_title(q: str) -> str:
        """Pull a 3-5 word topic from the question by stripping Q-words,
        leading articles, and trailing punctuation. Used when the LLM
        title is unusable."""
        cleaned = _re.sub(
            r'^\s*(what|how|why|when|where|who|which|whose|whom|is|are|was|were|am|be|been|being|can|could|do|does|did|will|would|should|shall|may|might|must|have|has|had|please|explain|tell me|describe|define|list|give me|summarize|compare|differentiate)\s+',
            '', (q or "").strip(), flags=_re.I,
        )
        cleaned = _re.sub(r'[?.!,;:]+$', '', cleaned).strip()
        # Strip common leading filler words after Q-word removal
        cleaned = _re.sub(r'^\s*(the|a|an|to|of|about|on|in|for|with|from)\s+', '', cleaned, flags=_re.I)
        if not cleaned:
            return "New chat"
        words = cleaned.split()[:5]
        title = " ".join(words).strip().title()
        return title[:50] if title else "New chat"

    try:
        # Routed through the abstracted LLM client so it uses Haiku (the
        # naming model) on Anthropic — a small, cheap, fast model is perfect
        # for short title generation. On Ollama it falls back to the
        # configured chat model.
        from ai.llm_client import get_llm_client
        _llm = get_llm_client()
        prompt_answer = (answer or "")[:400]
        title_raw = await _llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a chat title generator. Given a question and its answer, output ONLY a concise 3-5 word title in Title Case that names the TOPIC.\n\n"
                        "Rules:\n"
                        "- 3 to 5 words, Title Case\n"
                        "- Name the subject, not the question form (so 'Photosynthesis Process' not 'What Is Photosynthesis')\n"
                        "- No quotes, colons, brackets, markdown, hashtags, or trailing punctuation\n"
                        "- No prefixes like 'Title:', 'Topic:', 'INTENT:', 'Subject:'\n"
                        "- Output the title only, nothing else\n\n"
                        "Examples:\n"
                        "Q: What is photosynthesis? → Photosynthesis Process\n"
                        "Q: How do I solve quadratic equations? → Solving Quadratic Equations\n"
                        "Q: Explain the French Revolution. → French Revolution Causes\n"
                        "Q: Why does ice float on water? → Ice Density And Water\n"
                        "Q: List the parts of a cell. → Parts Of A Cell"
                    ),
                },
                {"role": "user", "content": f"Question: {question}\nAnswer: {prompt_answer}\nTitle:"},
            ],
            model=_llm.naming_model or settings.OLLAMA_CHAT_MODEL,
            temperature=0.0,
            max_tokens=20,
        )

        # Sanitize the raw output
        title = (title_raw or "").strip()
        # Strip code fences / markdown / leading headers
        title = _re.sub(r'^```.*?```', '', title, flags=_re.DOTALL).strip()
        title = title.split("\n")[0].strip()          # first line only
        title = _re.sub(r'^[#*\-\s>]+', '', title)    # strip leading markdown
        title = _re.sub(r'[#*`_~]', '', title)        # strip remaining md chars
        # Strip prefixes like "Title:", "INTENT:", "Subject:"
        title = _re.sub(r'^[A-Z]{3,}\s*:\s*', '', title)
        title = _re.sub(r'^(title|topic|subject|intent)\s*:\s*', '', title, flags=_re.I)
        title = title.strip(' "\'\t.:-')
        if len(title) > 55:
            title = title[:55].rstrip() + "..."

        # If still garbled (starts with punctuation / too short / looks like system phrase), fallback
        bad_patterns = [r'^$', r'intent', r'^concept explanation', r'^audience', r'^[<\[\(]']
        is_bad = any(_re.search(p, title, flags=_re.I) for p in bad_patterns) or len(title) < 3
        if is_bad:
            title = _fallback_title(question)

        await chat_session_db.rename_session(session_id, user_email, title, auto=True)
    except Exception as e:
        logger.warning(f"Auto-name failed for session {session_id}: {e}")
        await chat_session_db.rename_session(session_id, user_email, _fallback_title(question), auto=True)


async def _load_session_history(
    session_id: Optional[str],
    user_email: str,
    max_turns: int = 6,
) -> tuple[List[Dict], Optional[Dict]]:
    """Return (history_for_llm, session_doc) or ([], None) if no session."""
    if not session_id:
        return [], None
    session = await chat_session_db.get_session(session_id, user_email)
    if not session:
        return [], None
    msgs = session.get("messages", [])[-max_turns * 2:]
    history = [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in msgs
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return history, session


@app.post("/api/ask")
async def ask_question(request: QuestionRequest, current_user: Dict = Depends(rate_limit("qa")), _gate=Depends(gate_ai("qa"))):
    """Answer question using RAG"""
    try:
        started = time.perf_counter()
        phase_started = time.perf_counter()
        await _assert_upload_access(request.pdf_url, current_user)
        log_phase(logger, "api.qa", "access_check", phase_started)
        phase_started = time.perf_counter()
        ready = await _ensure_pdf_ready(request.pdf_url, ensure_vector=True)
        log_phase(logger, "api.qa", "ensure_pdf_ready", phase_started)
        pdf_key = ready["pdf_key"]
        pdf_data = ready["pdf_data"]

        session_history, session_doc = await _load_session_history(
            request.session_id, current_user["email"]
        )
        effective_history = session_history or (request.conversation_history or [])
        is_first_exchange = bool(request.session_id) and not session_history

        cache_key = None
        if not effective_history:
            cache_key = _ai_cache_key(
                "qa",
                pdf_key,
                {
                    "question": request.question.strip(),
                    "role": "admin" if current_user.get("is_admin", False) else "user"
                }
            )
            phase_started = time.perf_counter()
            cached = _ai_cache_get(cache_key)
            if cached is not None:
                logger.info(f"Q&A cache hit for {pdf_key}: {request.question[:80]}")
                log_phase(logger, "api.qa", "cache_lookup", phase_started, cache_hit=True)
                log_phase(logger, "api.qa", "total", started, cache_hit=True)
                if request.session_id:
                    await chat_session_db.append_message(request.session_id, current_user["email"], "user", request.question)
                    await chat_session_db.append_message(
                        request.session_id, current_user["email"], "assistant",
                        cached.get("answer", ""), cached.get("sources", []),
                    )
                    if is_first_exchange:
                        asyncio.create_task(_auto_name_session(
                            request.session_id, current_user["email"], request.question, cached.get("answer", "")
                        ))
                return cached
            log_phase(logger, "api.qa", "cache_lookup", phase_started, cache_hit=False)

        phase_started = time.perf_counter()
        answer_data = await qa_system.answer_question(
            pdf_url=pdf_key,
            question=request.question,
            conversation_history=effective_history,
            full_text=pdf_data.get("full_text", ""),
            user_role="admin" if current_user.get("is_admin", False) else "user",
            sections=pdf_data.get("sections", []),
            chunks=pdf_data.get("chunks", []),
        )
        log_phase(logger, "api.qa", "generate_answer", phase_started, question_chars=len(request.question or ""))
        if cache_key:
            _ai_cache_set(cache_key, answer_data)
        log_phase(logger, "api.qa", "total", started, cache_hit=False, confidence=answer_data.get("confidence", "unknown"))
        logger.info(f"Q&A answered in {time.perf_counter() - started:.2f}s for {pdf_key}")

        if request.session_id:
            await chat_session_db.append_message(request.session_id, current_user["email"], "user", request.question)
            await chat_session_db.append_message(
                request.session_id, current_user["email"], "assistant",
                answer_data.get("answer", ""), answer_data.get("sources", []),
            )
            if is_first_exchange:
                asyncio.create_task(_auto_name_session(
                    request.session_id, current_user["email"], request.question, answer_data.get("answer", "")
                ))

        asyncio.create_task(activity_db.log_activity(current_user["email"], "qa", {"pdf": pdf_key, "question": request.question[:100]}))
        return answer_data

    except Exception as e:
        logger.error(f"Error answering question: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/ask/stream")
async def ask_question_stream(request: QuestionRequest, current_user: Dict = Depends(rate_limit("qa")), _gate=Depends(gate_ai("qa"))):
    """Streaming variant of /api/ask using Server-Sent Events.

    Emits the answer token-by-token (on the Anthropic provider) so the user
    sees words appear instead of waiting for the whole response. Event shapes:
        data: {"type": "token", "text": "..."}      # 0..N of these
        data: {"type": "done", "answer": "...", "sources": [...], ...}
        data: {"type": "error", "detail": "..."}
    On the Ollama dev provider the answer arrives as a single token event;
    the contract is identical so the frontend needs only one code path."""
    await _assert_upload_access(request.pdf_url, current_user)
    ready = await _ensure_pdf_ready(request.pdf_url, ensure_vector=True)
    pdf_key = ready["pdf_key"]
    pdf_data = ready["pdf_data"]

    session_history, _session_doc = await _load_session_history(
        request.session_id, current_user["email"]
    )
    effective_history = session_history or (request.conversation_history or [])
    is_first_exchange = bool(request.session_id) and not session_history

    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    async def _on_token(chunk: str) -> None:
        await queue.put(("token", chunk))

    async def _run() -> None:
        try:
            answer_data = await qa_system.answer_question(
                pdf_url=pdf_key,
                question=request.question,
                conversation_history=effective_history,
                full_text=pdf_data.get("full_text", ""),
                user_role="admin" if current_user.get("is_admin", False) else "user",
                sections=pdf_data.get("sections", []),
                chunks=pdf_data.get("chunks", []),
                stream_handler=_on_token,
            )
            await queue.put(("result", answer_data))
            # Persist to the chat session + history, same as the non-stream path.
            if request.session_id:
                await chat_session_db.append_message(request.session_id, current_user["email"], "user", request.question)
                await chat_session_db.append_message(
                    request.session_id, current_user["email"], "assistant",
                    answer_data.get("answer", ""), answer_data.get("sources", []),
                )
                if is_first_exchange:
                    asyncio.create_task(_auto_name_session(
                        request.session_id, current_user["email"], request.question, answer_data.get("answer", "")
                    ))
            asyncio.create_task(activity_db.log_activity(current_user["email"], "qa", {"pdf": pdf_key, "question": request.question[:100], "stream": True}))
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error in streaming Q&A: {e}")
            await queue.put(("error", _friendly_error(e)))
        finally:
            await queue.put((_DONE, None))

    async def _event_source():
        worker = asyncio.create_task(_run())
        streamed_any = False
        try:
            while True:
                kind, payload = await queue.get()
                if kind is _DONE:
                    break
                if kind == "token":
                    streamed_any = True
                    yield f"data: {json.dumps({'type': 'token', 'text': payload})}\n\n"
                elif kind == "result":
                    # If nothing streamed (e.g. cache hit / extractive fallback),
                    # emit the full answer as one token so the client still renders it.
                    if not streamed_any and payload.get("answer"):
                        yield f"data: {json.dumps({'type': 'token', 'text': payload['answer']})}\n\n"
                    done_evt = {"type": "done", **payload}
                    yield f"data: {json.dumps(done_evt)}\n\n"
                elif kind == "error":
                    yield f"data: {json.dumps({'type': 'error', 'detail': payload})}\n\n"
        finally:
            await worker

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/audio")
async def generate_audio(request: AudioRequest, current_user: Dict = Depends(rate_limit("audio")), _gate=Depends(gate_av("audio"))):
    """Generate audio overview"""
    try:
        if request.pdf_url:
            await _assert_upload_access(request.pdf_url, current_user)
        audio_data = await audio_generator.generate_audio(
            text=request.text,
            pdf_identifier=request.pdf_url
        )
        # Mirror to object storage (no-op in local mode) so any instance can
        # serve it. Runs off the event loop — uploads are blocking I/O.
        _afname = audio_data.get("filename") if isinstance(audio_data, dict) else None
        if _afname and storage.is_remote():
            _mt = "audio/wav" if str(_afname).lower().endswith(".wav") else "audio/mpeg"
            asyncio.create_task(asyncio.to_thread(storage.mirror_to_remote, "audio", _afname, _mt))
        # Persist a history record so the student can find this audio later
        # in their History tab.
        try:
            fname = audio_data.get("filename") if isinstance(audio_data, dict) else None
            asyncio.create_task(mongodb.db.generated_audio.insert_one({
                "user_email": current_user["email"],
                "pdf_ref": request.pdf_url,
                "text_excerpt": (request.text or "")[:2000],
                "filename": fname,
                "file_url": f"/api/audio/{fname}" if fname else None,
                "duration_estimate": audio_data.get("duration_estimate") if isinstance(audio_data, dict) else None,
                "voice": audio_data.get("voice") if isinstance(audio_data, dict) else None,
                "created_at": datetime.utcnow(),
            }))
        except Exception as _persist_err:
            logger.debug(f"Audio history persist failed: {_persist_err}")
        return audio_data

    except Exception as e:
        logger.error(f"Error generating audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio/{filename}")
async def get_audio_file(filename: str):
    """Serve audio file (local disk, or redirect to object storage)."""
    try:
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        suffix = Path(filename).suffix.lower()
        media_type = "audio/wav" if suffix == ".wav" else "audio/mpeg"
        try:
            return storage.serve("audio", filename, media_type, download_name=filename)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Audio file not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video")
async def generate_video(request: VideoRequest, current_user: Dict = Depends(rate_limit("video")), _gate=Depends(gate_av("video"))):
    """Generate a slideshow-style animated MP4 video from either:
       - a supplied `summary`, or
       - a `pdf_url` + optional `query` (RAG retrieves relevant chunks)."""
    try:
        source_text = (request.summary or "").strip()
        pdf_identifier = request.pdf_url
        query = (request.query or "").strip() or None

        if not source_text and pdf_identifier:
            await _assert_upload_access(pdf_identifier, current_user)
            ready = await _ensure_pdf_ready(pdf_identifier, ensure_vector=True)
            pdf_key = ready["pdf_key"]
            pdf_data = ready["pdf_data"]

            if query:
                results = await vector_db.query_documents(pdf_url=pdf_key, query=query, n_results=8)
                docs = results.get("documents", []) or []
                source_text = "\n\n".join(docs[:8])[:5000]
            if not source_text:
                full_text = pdf_data.get("full_text", "") or ""
                source_text = full_text[:5000]

        if not source_text:
            raise HTTPException(status_code=400, detail="Provide `summary`, or `pdf_url` with optional `query`.")

        video_data = await video_generator.generate_video(
            source_text=source_text,
            pdf_identifier=pdf_identifier,
            query=query,
            style=request.style or "slides",
        )
        # Mirror to object storage (no-op in local mode) off the event loop.
        _vfname0 = video_data.get("filename") if isinstance(video_data, dict) else None
        if _vfname0 and storage.is_remote():
            asyncio.create_task(asyncio.to_thread(storage.mirror_to_remote, "video", _vfname0, "video/mp4"))
        asyncio.create_task(activity_db.log_activity(
            current_user["email"], "video",
            {"pdf": pdf_identifier, "query": (query or "")[:80], "style": request.style or "slides"}
        ))
        # Persist a history record for the History tab.
        try:
            vfname = video_data.get("filename") if isinstance(video_data, dict) else None
            asyncio.create_task(mongodb.db.generated_video.insert_one({
                "user_email": current_user["email"],
                "pdf_ref": pdf_identifier,
                "query": query,
                "style": request.style or "slides",
                "script_excerpt": (source_text or "")[:2000],
                "filename": vfname,
                "file_url": f"/api/video/{vfname}" if vfname else None,
                "duration": video_data.get("duration") if isinstance(video_data, dict) else None,
                "created_at": datetime.utcnow(),
            }))
        except Exception as _persist_err:
            logger.debug(f"Video history persist failed: {_persist_err}")
        return video_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/video/{filename}")
async def get_video_file(filename: str):
    """Serve generated MP4 files (local disk, or redirect to object storage)."""
    try:
        # Basic path-traversal guard
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        try:
            return storage.serve("video", filename, "video/mp4", download_name=filename)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Video file not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving video file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== PDF MANAGEMENT (DELETE) ====================

@app.delete("/api/my-uploaded-pdfs/{pdf_id}")
async def delete_my_pdf(
    pdf_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Delete an uploaded PDF (student can only delete their own)."""
    try:
        from bson import ObjectId
        upload = await mongodb.db.uploaded_pdfs.find_one({"_id": ObjectId(pdf_id)})
        if not upload:
            raise HTTPException(status_code=404, detail="PDF not found")
        if upload.get("uploader_email") != current_user.get("email"):
            if not current_user.get("is_admin", False):
                raise HTTPException(status_code=403, detail="Access denied")

        pdf_identifier = upload.get("pdf_identifier", "")
        stored_filename = upload.get("stored_filename", "")

        # Remove physical file (local copy + shared object-store copy)
        if stored_filename:
            file_path = Path(settings.UPLOAD_DIR) / stored_filename
            if file_path.exists():
                file_path.unlink()
            try:
                storage.delete_remote("uploads", stored_filename)
            except Exception:
                pass

        # Remove vector collection
        if pdf_identifier:
            try:
                vector_db.delete_collection(pdf_identifier)
            except Exception:
                pass
            _cache_invalidate(pdf_identifier)

        await mongodb.db.uploaded_pdfs.delete_one({"_id": ObjectId(pdf_id)})
        return {"message": "PDF deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== MULTI-DOCUMENT Q&A ====================

@app.post("/api/ask-multi")
async def ask_question_multi(
    request: MultiDocQuestionRequest,
    current_user: Dict = Depends(rate_limit("qa")),
    _gate=Depends(gate_ai("qa")),
):
    """Answer a question using RAG across multiple PDFs."""
    try:
        if not request.pdf_identifiers:
            raise HTTPException(status_code=400, detail="No PDF identifiers provided")
        if len(request.pdf_identifiers) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 PDFs allowed per query")

        all_contexts = []
        all_metadatas = []
        doc_name_map = {}

        async def _fetch_pdf_context(pdf_id: str):
            await _assert_upload_access(pdf_id, current_user)
            ready = await _ensure_pdf_ready(pdf_id, ensure_vector=True)
            pdf_key = ready["pdf_key"]
            upload = await pdf_upload_db.get_upload_by_identifier(pdf_id)
            filename = upload.get("filename", pdf_id) if upload else pdf_id
            results = await vector_db.query_documents(
                pdf_url=pdf_key,
                query=request.question,
                n_results=6,
            )
            return pdf_key, filename, results

        fetch_results = await asyncio.gather(
            *[_fetch_pdf_context(pdf_id) for pdf_id in request.pdf_identifiers],
            return_exceptions=True,
        )

        for item in fetch_results:
            if isinstance(item, Exception):
                logger.warning("Multi-doc fetch failed for one PDF: %s", item)
                continue
            pdf_key, filename, results = item
            doc_name_map[pdf_key] = filename
            for doc, meta in zip(results.get("documents", []), results.get("metadatas", [])):
                if isinstance(meta, dict):
                    meta["source_doc"] = filename
                all_contexts.append(doc)
                all_metadatas.append(meta if isinstance(meta, dict) else {})

        if not all_contexts:
            return {
                "answer": "No relevant context found in the selected documents.",
                "sources": [],
                "confidence": "low",
            }

        # Build combined context — limit to top 5 chunks and trim each to 600 chars
        # to keep the prompt small enough for fast CPU inference.
        context_parts = []
        for i, (ctx, meta) in enumerate(zip(all_contexts[:5], all_metadatas[:5]), 1):
            src = meta.get("source_doc", "Unknown")
            page = meta.get("page_number", "?")
            trimmed_ctx = (ctx or "")[:600]
            context_parts.append(f"[S{i}|{src}|p{page}] {trimmed_ctx}")
        context_text = "\n\n".join(context_parts)

        is_admin_user = current_user.get("is_admin", False)
        if is_admin_user:
            audience_sys = (
                "AUDIENCE: Administrator. Be concise — 3-5 short bullets maximum. "
                "No introductions, no analogies. Bold key terms only. End with a complete sentence."
            )
            multi_max_tokens = 380
        else:
            audience_sys = (
                "AUDIENCE: College student. Aim for 5-9 sentences total — concise but informative.\n"
                "Open with a one-sentence direct answer, then explain the key idea synthesizing across the documents, "
                "then add a brief example or detail if the evidence supports it.\n"
                "Use **bold** for key terms. End with a complete sentence — never trail off mid-thought."
            )
            multi_max_tokens = 600

        session_history, session_doc = await _load_session_history(
            request.session_id, current_user["email"]
        )
        effective_history = session_history or (request.conversation_history or [])
        is_first_exchange = bool(request.session_id) and not session_history

        from ai.ollama_client import ollama_client
        llm_messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an AI tutor. You read source passages from multiple PDFs and "
                    "write a synthesized answer in your own words.\n\n"
                    "CRITICAL OUTPUT RULES:\n"
                    "1. NEVER repeat the source passages verbatim — paraphrase and synthesize.\n"
                    "2. NEVER include the words 'Question', 'Evidence', 'Source', 'Task', 'PDF' as headings or labels.\n"
                    "3. NEVER copy the structure of the user's prompt.\n"
                    "4. Use only facts that appear in the provided passages.\n"
                    "5. Cite source tags inline like [S1], [S2] after the supported claim.\n"
                    "6. Start with the substance — no 'Certainly', 'Sure', or filler.\n"
                    "7. If passages are insufficient, reply: "
                    "'This question is outside the provided documents, so I can only answer from the document content.'\n\n"
                    f"{audience_sys}"
                ),
            },
        ]
        if effective_history:
            llm_messages.extend(effective_history[-4:])
        llm_messages.append({
            "role": "user",
            "content": (
                "Below are source passages from multiple PDFs. Read them, then answer the question that follows.\n\n"
                "----- SOURCE PASSAGES BEGIN -----\n"
                f"{context_text}\n"
                "----- SOURCE PASSAGES END -----\n\n"
                f"Question: {request.question}\n\n"
                "Now write a complete answer to that question, using only what the source passages say. "
                "Paraphrase — do not copy sentences verbatim. Cite [S1], [S2] etc. after each supported claim. "
                "Do not include any heading or label; just write the answer directly."
            ),
        })

        answer = await ollama_client.chat(
            messages=llm_messages,
            model=settings.OLLAMA_CHAT_MODEL,
            temperature=0.15,
            max_tokens=multi_max_tokens,
            # num_ctx caps the model's context — smaller = faster CPU inference
            extra_options={"repeat_penalty": 1.1, "num_ctx": 2048},
        )

        # Safety: trim mid-sentence cutoffs from the model output
        if answer:
            from ai.qa import qa_system as _qa
            answer = _qa._strip_echoed_structure(answer)
            answer = _qa._trim_to_complete_sentence(answer)

        sources = []
        for i, (ctx, meta) in enumerate(zip(all_contexts[:8], all_metadatas[:8]), 1):
            src = meta.get("source_doc", "Unknown")
            page = meta.get("page_number", "?")
            sources.append(f"[S{i}] {src} (page {page}): {ctx[:120]}...")

        if request.session_id:
            await chat_session_db.append_message(request.session_id, current_user["email"], "user", request.question)
            await chat_session_db.append_message(
                request.session_id, current_user["email"], "assistant", answer, sources
            )
            if is_first_exchange:
                asyncio.create_task(_auto_name_session(
                    request.session_id, current_user["email"], request.question, answer
                ))

        asyncio.create_task(activity_db.log_activity(
            current_user["email"], "qa",
            {"multi_doc": True, "docs": request.pdf_identifiers, "question": request.question[:100]}
        ))

        return {
            "answer": answer,
            "sources": sources,
            "confidence": "medium",
            "num_sources": len(all_contexts),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-doc Q&A: {e}")
        raise HTTPException(status_code=500, detail=_friendly_error(e))


# ==================== CHAT SESSIONS ====================

@app.post("/api/chat-sessions")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Create a new chat session for the current user."""
    session_id = await chat_session_db.create_session(
        user_email=current_user["email"],
        pdf_ids=request.pdf_ids or [],
        mode=request.mode or "single",
        name=request.name or "New chat",
    )
    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return {"id": session_id, "name": request.name or "New chat"}


@app.get("/api/chat-sessions")
async def list_chat_sessions(
    mode: Optional[str] = None,
    current_user: Dict = Depends(get_current_user),
):
    """List all chat sessions owned by the current user."""
    sessions = await chat_session_db.list_sessions(current_user["email"])
    if mode:
        sessions = [s for s in sessions if s.get("mode") == mode]
    for s in sessions:
        if isinstance(s.get("created_at"), datetime):
            s["created_at"] = s["created_at"].isoformat()
        if isinstance(s.get("updated_at"), datetime):
            s["updated_at"] = s["updated_at"].isoformat()
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/chat-sessions/{session_id}")
async def get_chat_session(
    session_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Get full conversation for a session."""
    session = await chat_session_db.get_session(session_id, current_user["email"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if isinstance(session.get("created_at"), datetime):
        session["created_at"] = session["created_at"].isoformat()
    if isinstance(session.get("updated_at"), datetime):
        session["updated_at"] = session["updated_at"].isoformat()
    for m in session.get("messages", []):
        if isinstance(m.get("timestamp"), datetime):
            m["timestamp"] = m["timestamp"].isoformat()
    return session


@app.patch("/api/chat-sessions/{session_id}")
async def rename_chat_session(
    session_id: str,
    request: ChatSessionRenameRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Rename a session manually."""
    ok = await chat_session_db.rename_session(
        session_id, current_user["email"], request.name.strip() or "New chat"
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Renamed"}


@app.delete("/api/chat-sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Delete a chat session."""
    ok = await chat_session_db.delete_session(session_id, current_user["email"])
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Deleted"}


# ==================== CHAT HISTORY ====================

@app.post("/api/chat-history")
async def save_chat_message(
    request: ChatHistorySaveRequest,
    current_user: Dict = Depends(get_current_user),
):
    """Persist a Q&A exchange to chat history."""
    msg_id = await chat_history_db.save_message(
        user_email=current_user["email"],
        document_ids=request.document_ids,
        question=request.question,
        answer=request.answer,
        sources=request.sources or [],
        confidence=request.confidence or "medium",
    )
    return {"id": msg_id, "message": "Saved"}


@app.get("/api/chat-history")
async def get_chat_history(
    document_id: Optional[str] = None,
    limit: int = 50,
    current_user: Dict = Depends(get_current_user),
):
    """Retrieve chat history for the current user."""
    history = await chat_history_db.get_history(
        user_email=current_user["email"],
        document_id=document_id,
        limit=limit,
    )
    return {"history": history, "count": len(history)}


@app.delete("/api/chat-history")
async def clear_chat_history(
    document_id: Optional[str] = None,
    current_user: Dict = Depends(get_current_user),
):
    """Clear chat history for the current user (optionally for one document)."""
    deleted = await chat_history_db.clear_history(
        user_email=current_user["email"],
        document_id=document_id,
    )
    return {"message": f"Cleared {deleted} messages"}


# ==================== ANSWER EVALUATION (admin) ====================

@app.post("/api/evaluate-answer")
async def evaluate_answer(
    request: EvaluateAnswerRequest,
    admin_user: Dict = Depends(get_admin_user),
    _gate=Depends(gate_ai("evaluate")),
):
    """Hybrid, class-aware evaluation of a student's answer (admin only).

    - Keyword score (rule-based)
    - Semantic score (LLM, with rubric tuned to `student_class`)
    - Hybrid decision: keyword score wins above the per-band threshold
      (lower for primary classes, higher for secondary).
    - If `target_class` differs from `student_class`, a class-mismatch
      warning is included in the response so the admin sees it.
    """
    try:
        from services.answer_evaluator import hybrid_evaluate
        # Phase 3: route through the LLM provider abstraction (Ollama / Claude).
        # Falls back to OllamaClient if the new module isn't loaded yet.
        try:
            from ai.llm_client import get_llm_client
            llm = get_llm_client()
        except ImportError:
            from ai.ollama_client import ollama_client as llm

        if not (request.student_answer or "").strip():
            raise HTTPException(status_code=400, detail="student_answer is required")

        # Effective class: prefer explicit student_class, else target_class
        effective_class = request.student_class or request.target_class

        result = await hybrid_evaluate(
            question=request.question or "",
            expected_answer=request.expected_answer or "",
            keywords=request.keywords or [],
            student_answer=request.student_answer,
            ollama_client=llm,
            model=settings.OLLAMA_CHAT_MODEL,
            class_level=effective_class,
            subject=request.subject,
        )

        # Class-mismatch warning (Phase 4): admin gets a heads-up if the
        # question targets a different class than the student.
        if (request.student_class is not None
                and request.target_class is not None
                and request.student_class != request.target_class):
            result["class_mismatch_warning"] = (
                f"Question was generated for class {request.target_class}, "
                f"but the student is in class {request.student_class}. "
                f"Grading was applied for class {effective_class}."
            )

        asyncio.create_task(activity_db.log_activity(
            admin_user["email"], "evaluate_answer",
            {
                "method": result.get("method"),
                "score": result.get("score_out_of_10"),
                "class_level": effective_class,
                "subject": request.subject,
                "band": result.get("grading_band"),
            },
        ))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error evaluating answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/grading-standards")
async def list_grading_standards(admin_user: Dict = Depends(get_admin_user)):
    """Return the configured grading bands + subject overlays (Phase 2 + 6)."""
    from services.grading_standards import get_all_bands, _STANDARDS  # type: ignore
    return {
        "bands": get_all_bands(),
        "subjects": _STANDARDS.get("subjects") or {},
        "version": _STANDARDS.get("version"),
    }


@app.post("/api/admin/grading-standards/reload")
async def reload_grading_standards(admin_user: Dict = Depends(get_admin_user)):
    """Re-read grading_standards.json from disk so tuning doesn't need a restart.
    Useful during the calibration loop (Phase 5)."""
    from services.grading_standards import reload_standards
    data = reload_standards()
    return {
        "message": "Grading standards reloaded",
        "version": data.get("version"),
        "band_count": len(data.get("bands") or []),
    }


# ──────────────────────────────────────────────────────────────────────────
# AI evaluation (admin-only) — reference-free scoring of real student
# traffic (Q&A, summaries, quizzes) plus teacher-generated questions.
# Uses Claude Haiku as the judge model on Anthropic; whichever model the
# llm_client exposes via `.evaluation_model` on Ollama.
# ──────────────────────────────────────────────────────────────────────────

@app.get("/api/admin/eval/runs")
async def list_eval_runs(
    limit: int = 30,
    admin_user: Dict = Depends(get_admin_user),
):
    """List recent evaluation runs (most recent first)."""
    from evaluation.storage import list_runs
    runs = await list_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@app.get("/api/admin/eval/runs/{run_id}")
async def get_eval_run(
    run_id: str,
    admin_user: Dict = Depends(get_admin_user),
):
    """Get a single run + all of its scored items (drill-down view)."""
    from evaluation.storage import get_run, list_run_items
    run = await get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    items = await list_run_items(run_id)
    return {"run": run, "items": items, "count": len(items)}


@app.post("/api/admin/eval/run-student-bundle")
async def trigger_eval_student_bundle(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """One-shot evaluation across all STUDENT-side generation features —
    Q&A traffic, summaries, and quizzes. Runs each sub-evaluation
    sequentially, creating three separate run rows in `evaluation_runs`
    so they're independently inspectable, and returns a combined summary.

    Sub-evals that have no data yet (e.g. no summaries persisted) are
    skipped with a note rather than aborting the whole bundle.
    """
    from evaluation.runner import (
        run_evaluation_on_recent_qa,
        run_evaluation_on_summaries,
        run_evaluation_on_quizzes,
    )
    body = body or {}
    label_prefix = (body.get("label") or "").strip() or "Student bundle"
    try:
        limit_int = int(body.get("limit") or 20)
    except (TypeError, ValueError):
        limit_int = 20
    triggered_by = admin_user.get("email", "unknown")

    bundle: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    async def _run_one(label_suffix: str, runner_coro):
        try:
            result = await runner_coro
            if result.get("error"):
                skipped.append({"part": label_suffix, "reason": result["error"]})
            else:
                bundle.append({"part": label_suffix, **result})
        except Exception as exc:
            skipped.append({"part": label_suffix, "reason": f"{type(exc).__name__}: {exc}"})

    await _run_one("Q&A", run_evaluation_on_recent_qa(
        triggered_by=triggered_by,
        label=f"{label_prefix} — Q&A",
        limit=limit_int,
    ))
    await _run_one("Summaries", run_evaluation_on_summaries(
        triggered_by=triggered_by,
        label=f"{label_prefix} — Summaries",
        limit=limit_int,
    ))
    await _run_one("Quizzes", run_evaluation_on_quizzes(
        triggered_by=triggered_by,
        label=f"{label_prefix} — Quizzes",
        limit=limit_int,
    ))

    if not bundle:
        # All three sub-runs failed or had no data — surface the most
        # informative reason from the first skipped entry.
        first_reason = skipped[0]["reason"] if skipped else "Unknown"
        raise HTTPException(
            status_code=400,
            detail=(
                f"No student-side content available to evaluate yet. "
                f"First reason: {first_reason}"
            ),
        )

    avg_of_avgs = round(
        sum(b.get("avg_overall", 0.0) for b in bundle) / len(bundle), 4
    )
    return {
        "bundle": bundle,
        "skipped": skipped,
        "n_sub_runs": len(bundle),
        "avg_overall": avg_of_avgs,
    }


@app.post("/api/admin/eval/run-teacher-bundle")
async def trigger_eval_teacher_bundle(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """One-shot evaluation across every TEACHER-side AI-generated content
    type — short answer, long answer, MCQ, fill-in-blank, true/false.

    Mirrors the student bundle pattern: each question type produces its
    own evaluation_runs row so admins can see per-type quality scores
    ('MCQs at 85%, short answers at 60%') instead of one merged number.

    Sub-types with no matching teacher questions yet are reported in
    ``skipped`` rather than aborting the whole bundle. Returns 400 only
    if every sub-type had nothing to evaluate.
    """
    from evaluation.runner import run_evaluation_on_teacher_questions
    body = body or {}
    label_prefix = (body.get("label") or "").strip() or "Teacher bundle"
    try:
        limit_int = int(body.get("limit") or 20)
    except (TypeError, ValueError):
        limit_int = 20
    triggered_by = admin_user.get("email", "unknown")

    # The five question types the assignment builder generates. We use
    # the hyphen form since that's how the question paper builder and
    # the quiz generator store them.
    sub_types = [
        ("Short answer", "short-answer"),
        ("Long answer", "long-answer"),
        ("MCQ", "mcq"),
        ("Fill-in-blank", "fill-in-blank"),
        ("True / False", "true-false"),
    ]

    bundle: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for label_suffix, qt in sub_types:
        try:
            result = await run_evaluation_on_teacher_questions(
                triggered_by=triggered_by,
                label=f"{label_prefix} — {label_suffix}",
                limit=limit_int,
                question_type=qt,
            )
            if result.get("error"):
                skipped.append({"part": label_suffix, "reason": result["error"]})
            else:
                bundle.append({"part": label_suffix, **result})
        except Exception as exc:  # noqa: BLE001
            skipped.append({
                "part": label_suffix,
                "reason": f"{type(exc).__name__}: {exc}",
            })

    if not bundle:
        first_reason = skipped[0]["reason"] if skipped else "Unknown"
        raise HTTPException(
            status_code=400,
            detail=(
                f"No teacher-generated questions found to evaluate yet. "
                f"First reason: {first_reason}"
            ),
        )

    avg_of_avgs = round(
        sum(b.get("avg_overall", 0.0) for b in bundle) / len(bundle), 4
    )
    return {
        "bundle": bundle,
        "skipped": skipped,
        "n_sub_runs": len(bundle),
        "avg_overall": avg_of_avgs,
    }


@app.post("/api/admin/eval/run-on-summaries")
async def trigger_eval_run_on_summaries(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Evaluate recently-generated summaries against their source PDFs."""
    from evaluation.runner import run_evaluation_on_summaries
    body = body or {}
    summary = await run_evaluation_on_summaries(
        triggered_by=admin_user.get("email", "unknown"),
        label=(body.get("label") or "").strip() or None,
        limit=int(body.get("limit") or 10),
    )
    if summary.get("error"):
        raise HTTPException(status_code=400, detail=summary["error"])
    return summary


@app.post("/api/admin/eval/run-on-quizzes")
async def trigger_eval_run_on_quizzes(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Evaluate recently-generated student quizzes — judges each question
    in each quiz on validity, correctness, and faithfulness."""
    from evaluation.runner import run_evaluation_on_quizzes
    body = body or {}
    summary = await run_evaluation_on_quizzes(
        triggered_by=admin_user.get("email", "unknown"),
        label=(body.get("label") or "").strip() or None,
        limit=int(body.get("limit") or 10),
    )
    if summary.get("error"):
        raise HTTPException(status_code=400, detail=summary["error"])
    return summary


@app.post("/api/admin/eval/run-on-teacher-questions")
async def trigger_eval_run_on_teacher_questions(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Evaluate the questions in recently-created teacher assignments —
    same scoring as student quizzes but without a source PDF context."""
    from evaluation.runner import run_evaluation_on_teacher_questions
    body = body or {}
    summary = await run_evaluation_on_teacher_questions(
        triggered_by=admin_user.get("email", "unknown"),
        label=(body.get("label") or "").strip() or None,
        limit=int(body.get("limit") or 10),
    )
    if summary.get("error"):
        raise HTTPException(status_code=400, detail=summary["error"])
    return summary


@app.post("/api/admin/eval/run-on-qa")
async def trigger_eval_run_on_qa(
    body: Optional[Dict[str, Any]] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Reference-free evaluation on REAL student Q&A traffic.

    Pulls the most recent (question, AI answer) turns from `chat_sessions`
    and scores each one on faithfulness (against the retrieved PDF context)
    and answer relevance (against the question itself).

    Body (all optional):
      label: human label for this run
      limit: max number of Q&A pairs to score (default 20)
      user_email: only evaluate this user's sessions
    """
    from evaluation.runner import run_evaluation_on_recent_qa
    body = body or {}
    label = (body.get("label") or "").strip() or None
    try:
        limit_int = int(body.get("limit") or 20)
    except (TypeError, ValueError):
        limit_int = 20
    user_filter = (body.get("user_email") or "").strip() or None
    summary = await run_evaluation_on_recent_qa(
        triggered_by=admin_user.get("email", "unknown"),
        label=label,
        limit=limit_int,
        user_email=user_filter,
    )
    if summary.get("error"):
        raise HTTPException(status_code=400, detail=summary["error"])
    return summary


@app.post("/api/extract-text")
async def extract_text_from_upload(
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user),
):
    """Extract text from an uploaded PDF or image (any authenticated user).

    Supports PDF (text-layer extraction with OCR fallback) and JPG/PNG images.
    Used by:
      - Admin Answer Evaluation dialog (scanned student scripts)
      - Student assignment-taking flow (upload a photo / PDF of handwritten answer
        and let OCR convert it to text the auto-grader can score).
    """
    try:
        from services.text_extractor import extract_text, SUPPORTED_EXTS

        filename = file.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Supported: PDF, JPG, PNG, WEBP, BMP.",
            )

        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file")
        if len(contents) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large (max 25 MB)")

        result = extract_text(contents, filename)
        if not result["text"]:
            return {
                "text": "",
                "char_count": 0,
                "method": result.get("method", ""),
                "warning": (
                    "No text could be extracted. If this is a handwritten scan, "
                    "OCR accuracy on handwriting is limited — please type the answer manually."
                ),
            }
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Text extraction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/parse-questions")
async def parse_questions(
    request: ParseQuestionsRequest,
    admin_user: Dict = Depends(get_admin_user),
):
    """Parse the AI Features 'Copyable text' format into question blocks (admin only).

    Returns a list of {question, expected_answer, keywords, explanation}.
    """
    try:
        from services.answer_evaluator import parse_question_blocks
        blocks = parse_question_blocks(request.copyable_text or "")
        return {"blocks": blocks, "count": len(blocks)}
    except Exception as e:
        logger.error(f"Error parsing questions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== NOTIFICATIONS ====================
# Persisted notifications cover the "teacher published" and "student submitted"
# events. The "assignment due today, not submitted" case is synthesized live
# inside the list endpoint so it auto-disappears when the day rolls over and
# never gets duplicated.

def _resolve_user_id_str(user: Dict) -> str:
    return str(user.get("id") or user.get("_id") or user.get("email") or "")


async def _synthesize_deadline_notifications(student: Dict) -> List[Dict[str, Any]]:
    """Compute on-the-fly deadline-today notifications for a student.

    Returns synthetic notification dicts (not persisted). Skips assignments the
    student has already submitted.
    """
    role = (student.get("role") or "").strip().lower()
    if role != "student":
        return []
    cs = student.get("class_section") or ""
    if not cs:
        cl = student.get("class_level")
        sec = student.get("section")
        if cl and sec:
            cs = f"{cl}{str(sec).upper()}"
    if not cs:
        return []

    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    try:
        cursor = mongodb.db.assignments.find({
            "status": "published",
            "class_section": cs,
            "due_date": {"$gte": day_start, "$lt": day_end},
        })
        student_email = student.get("email", "")
        student_user_id = _resolve_user_id_str(student)
        synthesized: List[Dict[str, Any]] = []
        async for assignment in cursor:
            assignment_id = str(assignment.get("_id"))
            # Has the student already submitted?
            existing = await mongodb.db.submissions.find_one({
                "assignment_id": assignment_id,
                "$or": [
                    {"student_email": student_email},
                    {"student_user_id": student_user_id},
                ],
            })
            if existing:
                continue
            due_human = assignment.get("due_date").strftime("%I:%M %p")
            synthesized.append({
                "_id": f"deadline:{assignment_id}",
                "user_id": student_user_id,
                "type": "deadline_today",
                "title": "Assignment due today",
                "body": (
                    f"\"{assignment.get('title', 'Untitled')}\" is due by "
                    f"{due_human} and you haven't submitted yet."
                ),
                "link": f"assignment:{assignment_id}",
                "is_read": False,
                "created_at": now,
                "_synthetic": True,
            })
        return synthesized
    except Exception as e:
        logger.error(f"deadline synthesis failed: {e}")
        return []


@app.get("/api/notifications")
async def list_notifications(current_user: Dict = Depends(get_current_user)):
    """Return the caller's recent notifications (most-recent-first), with
    live-computed deadline-today notifications merged in."""
    user_id = _resolve_user_id_str(current_user)
    persisted = await notifications_db.list_for_user(user_id, limit=30)
    synthetic = await _synthesize_deadline_notifications(current_user)
    # Synthetic first so deadlines surface above stale read ones.
    return {"notifications": synthetic + persisted}


@app.get("/api/notifications/unread-count")
async def notifications_unread_count(current_user: Dict = Depends(get_current_user)):
    """Cheap endpoint used by the bell-icon badge. Counts persisted unread
    plus live-synthesized deadline notifications."""
    user_id = _resolve_user_id_str(current_user)
    persisted = await notifications_db.unread_count(user_id)
    synthetic = await _synthesize_deadline_notifications(current_user)
    return {"unread_count": persisted + len(synthetic)}


@app.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str, current_user: Dict = Depends(get_current_user)
):
    """Mark a single notification as read. Synthetic deadline ids (prefix
    ``deadline:``) are silently accepted — they aren't persisted, so they
    re-appear on the next fetch as long as the deadline is still today and
    the assignment is still unsubmitted."""
    if notification_id.startswith("deadline:"):
        return {"ok": True, "synthetic": True}
    user_id = _resolve_user_id_str(current_user)
    ok = await notifications_db.mark_read(notification_id, user_id)
    if ok:
        await emit_notification_read(user_id, notification_id)
    return {"ok": ok}


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read(current_user: Dict = Depends(get_current_user)):
    """Mark every persisted notification for the caller as read."""
    user_id = _resolve_user_id_str(current_user)
    n = await notifications_db.mark_all_read(user_id)
    # Tell every open tab to drop its unread badge to zero.
    await emit_notification_read(user_id)
    return {"marked": n}


# ==================== REALTIME (WebSocket fan-out) ====================


@app.websocket("/ws")
async def realtime_websocket(ws: WebSocket, token: str = Query(default="")):
    """Persistent connection used by the bell icons in the dashboard header.

    Auth: the client passes ?token=<jwt> in the URL. We validate via the
    same auth_backend used everywhere else so revocation propagates. On
    success we register the socket against the user_id and stream events;
    on auth failure we close with 1008 (policy violation).

    Per-tab: one socket per browser tab. A user with 3 tabs gets 3 sockets
    and broadcasts go to all 3.

    Heartbeat: clients may send ``{"type":"ping"}`` periodically; we reply
    ``{"type":"pong"}`` so reverse proxies don't reap idle sockets.
    """
    await ws.accept()

    if not token:
        await ws.send_json({"type": "error", "code": "no_token"})
        await ws.close(code=1008)
        return

    try:
        ctx = await auth_backend.verify_token(token)
    except Exception:  # noqa: BLE001
        logger.exception("WS auth raised unexpectedly")
        ctx = None

    if ctx is None:
        await ws.send_json({"type": "error", "code": "invalid_token"})
        await ws.close(code=1008)
        return

    user_id = str(ctx.user_id or "")
    if not user_id:
        await ws.send_json({"type": "error", "code": "no_user_id"})
        await ws.close(code=1008)
        return

    await realtime_hub.register(user_id, ws)
    await ws.send_json({"type": "ready", "user_id": user_id})

    try:
        while True:
            data = await ws.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            # Other messages are ignored on purpose. The browser is a
            # passive recipient — every state change comes through HTTP.
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("WS receive loop failed for user %s", user_id)
    finally:
        await realtime_hub.unregister(user_id, ws)


# ==================== CHAT (teacher ↔ student, admin ↔ everyone) ====================

async def _resolve_chat_user(user_id: str) -> Optional[Dict]:
    if user_id == "broadcast_teachers":
        return {"_id": "broadcast_teachers", "role": "group", "username": "All Teachers (Broadcast)"}
    if user_id == "broadcast_students":
        return {"_id": "broadcast_students", "role": "group", "username": "All Students (Broadcast)"}
    if user_id.startswith("broadcast_school_all_"):
        return {"_id": user_id, "role": "group", "username": "School Everyone (Broadcast)"}
    if user_id.startswith("broadcast_school_admin_"):
        return {"_id": user_id, "role": "group", "username": "School Admins (Broadcast)"}
    from bson import ObjectId
    try:
        return await mongodb.db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


async def _can_chat(initiator: Dict, other: Dict) -> bool:
    """Authorize a chat pair. A teacher can talk to any student in one of
    their assigned class+section combos; a student can talk to any teacher
    assigned to their class+section. Admins can talk to anyone."""
    role_a = (initiator.get("role") or "").strip().lower()
    role_b = (other.get("role") or "").strip().lower()

    if role_b == "group":
        return role_a in ("admin", "super_admin")

    if role_a in ("admin", "super_admin") or role_b in ("admin", "super_admin"):
        school_a = initiator.get("school_id")
        school_b = other.get("school_id")
        if role_a == "super_admin" or role_b == "super_admin":
            return True
        if school_a is not None and school_b is not None and school_a != school_b:
            return False
        return True

    def cs_of(u: Dict) -> str:
        s = u.get("class_section") or ""
        if not s:
            cl = u.get("class_level"); sec = u.get("section")
            if cl and sec:
                s = f"{cl}{str(sec).upper()}"
        return s

    def classes_of_teacher(t: Dict) -> List[str]:
        return [str(c).strip().upper().replace(" ", "")
                for c in (t.get("assigned_classes") or [])]

    if role_a == "teacher" and role_b == "student":
        return cs_of(other) in classes_of_teacher(initiator)
    if role_a == "student" and role_b == "teacher":
        return cs_of(initiator) in classes_of_teacher(other)
    return False


@app.get("/api/chat/contacts")
async def chat_contacts(current_user: Dict = Depends(get_current_user)):
    """Return the list of users the caller is allowed to chat with."""
    role = (current_user.get("role") or "").strip().lower()
    me_id = _resolve_user_id_str(current_user)
    school_id = current_user.get("school_id")

    query_or = []

    # Helper to add admins into the contact list
    def add_admins():
        query_or.append({"role": "super_admin"})
        if school_id is not None:
            # in local mode where everyone has None, we won't strictly enforce,
            # but if school_id is set, we strictly enforce it for admins.
            # However, to be safe against mixed local data, let's allow school_id=None admins too.
            query_or.append({"role": "admin", "school_id": {"$in": [school_id, None]}})
        else:
            query_or.append({"role": "admin"})

    if role == "teacher":
        assigned = [
            str(c).strip().upper().replace(" ", "")
            for c in (current_user.get("assigned_classes") or [])
        ]
        if assigned:
            query_or.append({"role": "student", "class_section": {"$in": assigned}})
        add_admins()

    elif role == "student":
        cs = current_user.get("class_section") or ""
        if not cs:
            cl = current_user.get("class_level"); sec = current_user.get("section")
            if cl and sec:
                cs = f"{cl}{str(sec).upper()}"
        if cs:
            query_or.append({"role": "teacher", "assigned_classes": cs})
        add_admins()

    elif role in ("admin", "super_admin"):
        # Admin sees all teachers, students, and other admins in their school.
        # Super admin sees everyone.
        if role == "super_admin":
            query_or.append({"role": {"$in": ["teacher", "student", "admin", "super_admin"]}})
        else:
            query_or.append({"role": "super_admin"})
            query_or.append({
                "role": {"$in": ["teacher", "student", "admin"]},
                "school_id": {"$in": [school_id, None]} # Fallback for local testing data
            })
    else:
        return {"contacts": []}

    cursor = mongodb.db.users.find({"$or": query_or}) if query_or else []
    
    contacts: List[Dict[str, Any]] = []
    
    if role == "admin":
        virtual_contacts = [
            {
                "user_id": "broadcast_teachers",
                "name": "All Teachers (Broadcast)",
                "role": "group",
                "email": "",
                "class_section": None,
                "subjects_taught": [],
                "unread": 0,
            },
            {
                "user_id": "broadcast_students",
                "name": "All Students (Broadcast)",
                "role": "group",
                "email": "",
                "class_section": None,
                "subjects_taught": [],
                "unread": 0,
            }
        ]
        for vc in virtual_contacts:
            last = await chat_messages_db.last_message_with(me_id, vc["user_id"])
            vc["last_message"] = last.get("message") if last else None
            vc["last_message_at"] = last.get("created_at") if last else None
            contacts.append(vc)

    if query_or:
        async for u in cursor:
            other_id = str(u.get("_id"))
            if other_id == me_id:
                continue # don't add yourself to contacts
            last = await chat_messages_db.last_message_with(me_id, other_id)
            unread = await chat_messages_db.unread_count_from(me_id, other_id)
            contacts.append({
                "user_id": other_id,
                "name": u.get("full_name") or u.get("username") or "User",
                "role": u.get("role"),
                "email": u.get("email"),
                "class_section": u.get("class_section"),
                "subjects_taught": u.get("subjects_taught") or [],
                "last_message": (last.get("message") if last else None),
                "last_message_at": (last.get("created_at") if last else None),
                "unread": unread,
            })

    contacts.sort(
        key=lambda c: (c["last_message_at"] or datetime.min, c["name"]),
        reverse=True,
    )
    return {"contacts": contacts}




class ChatSendRequest(BaseModel):
    to_user_id: str
    message: str


@app.post("/api/chat/messages")
async def send_chat_message(
    body: ChatSendRequest, current_user: Dict = Depends(get_current_user)
):
    """Send a message. Authorizes the pair, then writes the message and
    creates a notification for the recipient so they get a bell badge even
    if their Messages dialog isn't open."""
    if not body.message or not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(body.message) > 2000:
        raise HTTPException(status_code=400, detail="Message is too long (max 2000 chars).")

    other = await _resolve_chat_user(body.to_user_id)
    if not other:
        raise HTTPException(status_code=404, detail="Recipient not found.")

    if not await _can_chat(current_user, other):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to chat with this user.",
        )

    me_id = _resolve_user_id_str(current_user)
    my_name = (
        current_user.get("full_name") or current_user.get("username")
        or current_user.get("email") or "User"
    )
    other_id = str(other.get("_id"))
    other_name = other.get("full_name") or other.get("username") or "User"

    msg = await chat_messages_db.send(
        from_user_id=me_id,
        from_role=(current_user.get("role") or "").lower(),
        from_name=my_name,
        to_user_id=other_id,
        to_role=(other.get("role") or "").lower(),
        to_name=other_name,
        message=body.message,
    )
    if not msg:
        raise HTTPException(status_code=500, detail="Could not deliver message.")

    preview = body.message.strip()
    if len(preview) > 80:
        preview = preview[:77] + "…"

    if other.get("role") == "group":
        # Broadcast fan-out
        if body.to_user_id == "broadcast_teachers":
            target_roles = ["teacher"]
            school_id = current_user.get("school_id")
        elif body.to_user_id == "broadcast_students":
            target_roles = ["student"]
            school_id = current_user.get("school_id")
        elif body.to_user_id.startswith("broadcast_school_all_"):
            target_roles = ["teacher", "student", "admin"]
            school_id_str = body.to_user_id.split("_")[-1]
            school_id = int(school_id_str) if school_id_str != "None" else None
        elif body.to_user_id.startswith("broadcast_school_admin_"):
            target_roles = ["admin"]
            school_id_str = body.to_user_id.split("_")[-1]
            school_id = int(school_id_str) if school_id_str != "None" else None
        else:
            raise HTTPException(status_code=400, detail="Invalid broadcast group.")

        base = {"school_id": school_id} if school_id is not None else {}
        
        cursor = mongodb.db.users.find({"role": {"$in": target_roles}, **base})
        async for u in cursor:
            u_id = str(u.get("_id"))
            await chat_messages_db.send(
                from_user_id=me_id,
                from_role=(current_user.get("role") or "").lower(),
                from_name=my_name,
                to_user_id=u_id,
                to_role=(u.get("role") or "").lower(),
                to_name=u.get("full_name") or u.get("username"),
                message=body.message
            )
            await notifications_db.create(
                user_id=u_id,
                type_="new_message",
                title=f"New broadcast from {my_name}",
                body=preview,
                link=f"chat:{me_id}",
            )
            await emit_chat_message(u_id, me_id)
            await emit_notification_created(u_id)
    else:
        # 1-on-1 direct message
        await notifications_db.create(
            user_id=other_id,
            type_="new_message",
            title=f"New message from {my_name}",
            body=preview,
            link=f"chat:{me_id}",
        )
        await emit_chat_message(other_id, me_id)
        await emit_notification_created(other_id)

    msg["created_at"] = msg["created_at"].isoformat()
    return msg


@app.get("/api/chat/messages/{other_user_id}")
async def get_chat_thread(
    other_user_id: str, current_user: Dict = Depends(get_current_user)
):
    """Return the message thread with one other user."""
    other = await _resolve_chat_user(other_user_id)
    if not other or not await _can_chat(current_user, other):
        raise HTTPException(status_code=403, detail="Not allowed.")
    me_id = _resolve_user_id_str(current_user)
    messages = await chat_messages_db.list_thread(me_id, other_user_id)
    for m in messages:
        if isinstance(m.get("created_at"), datetime):
            m["created_at"] = m["created_at"].isoformat()
    return {"messages": messages, "me_id": me_id}


@app.post("/api/chat/read/{other_user_id}")
async def mark_chat_thread_read(
    other_user_id: str, current_user: Dict = Depends(get_current_user)
):
    """Mark every message the caller has received from `other_user_id` as read."""
    me_id = _resolve_user_id_str(current_user)
    n = await chat_messages_db.mark_thread_read(me_id, other_user_id)
    if n:
        # Tell my OWN other tabs that the unread badge dropped, and tell
        # the sender's tab that I read their messages.
        await emit_chat_read(me_id, other_user_id)
        await emit_chat_read(other_user_id, me_id)
    return {"marked": n}


# ==================== ANALYTICS ====================

_PERIOD_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}


@app.get("/api/admin/analytics")
async def get_analytics(
    period: str = "7d",
    admin_user: Dict = Depends(get_admin_user),
):
    """Analytics dashboard data for the school admin — scoped to the
    admin's own school. Super admins also pass this gate (they're above
    admin), but they should use `/api/super-admin/analytics` to get a
    platform-wide view; calling this one returns Default School's slice
    since the super admin sits in school_id=1 from the ERP.

    `period` controls the window for the time-series chart. The KPI
    metrics + feature_usage rollup stay as all-time totals — they're
    cheap counts and the dashboard treats them as headline numbers,
    not deltas.
    """
    await _require_permission(admin_user, "view_analytics")
    days = _PERIOD_DAYS.get(period, 7)
    school_id = admin_user.get("school_id")
    metrics = await analytics_db.get_metrics(school_id=school_id)
    usage_over_time = await analytics_db.get_usage_over_time(
        days=days, school_id=school_id
    )
    feature_usage = await analytics_db.get_feature_usage(school_id=school_id)
    return {
        "metrics": metrics,
        "usage_over_time": usage_over_time,
        "feature_usage": feature_usage,
        "period": period,
        "days": days,
    }


# Audit-log CSV export used to live here as `/api/admin/export-logs`.
# It was deleted when we moved CSV export entirely to the frontend — each
# admin page now exports its own currently-filtered view via the shared
# `csv-export.ts` utility. Removed: 2026-06-09.


# Mount the super-admin router AFTER all dependencies in this module are
# defined. The router lazily imports `get_super_admin_user_ctx` from here,
# so the order matters — placing the include at the bottom guarantees the
# symbol is bound by the time the route is registered.
from routes.super_admin import router as super_admin_router  # noqa: E402
app.include_router(super_admin_router)


# Run the application
if __name__ == "__main__":
    import uvicorn
    import sys
    import socket
    
    def _check_port_available(host: str, port: int) -> bool:
        """Check if a port is available before attempting to bind."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            sock.close()
            return True
        except OSError:
            return False
    
    # Determine if reload should be enabled
    enable_reload = "--reload" in sys.argv or os.getenv("RELOAD", "").lower() == "true"
    
    # Windows fix: Use 127.0.0.1 instead of 0.0.0.0 to avoid DNS resolution issues
    host = settings.HOST
    if host == "0.0.0.0":
        # For Windows development, use localhost
        if sys.platform == "win32":
            host = "127.0.0.1"
            logger.info("🖥️  Windows detected - using 127.0.0.1 instead of 0.0.0.0")
    
    logger.info(f"🚀 Starting backend server on {host}:{settings.PORT}")
    logger.info(f"🔄 Auto-reload: {'Enabled' if enable_reload else 'Disabled (use --reload flag or RELOAD=true env var)'}")
    
    # Pre-flight check: Ensure port is available
    if not _check_port_available(host, settings.PORT):
        logger.error(f"❌ Port {settings.PORT} is already in use!")
        logger.error(f"💡 To find and kill the process:")
        logger.error(f"   netstat -ano | findstr :{settings.PORT}")
        logger.error(f"   taskkill /PID <PID> /F")
        sys.exit(1)
    
    # Worker count: read from UVICORN_WORKERS env var. On a 2-vCPU box
    # (Hostinger KVM 2) the right value is 2 — matches the cores and
    # gives the second worker something to do while the first one is
    # parsing a PDF synchronously. Reload mode forces single-worker
    # because uvicorn's reloader can't supervise multiple worker
    # processes. Set UVICORN_WORKERS=1 if you genuinely want single
    # worker (e.g. while debugging shared state).
    _workers_env = os.getenv("UVICORN_WORKERS")
    try:
        _workers = max(1, int(_workers_env)) if _workers_env else 1
    except ValueError:
        _workers = 1
    if enable_reload:
        _workers = 1  # reloader requires single worker
    logger.info(f"⚙️  Uvicorn workers: {_workers}")

    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=settings.PORT,
            reload=enable_reload,
            workers=_workers if not enable_reload else None,
            log_level="info",
        )
    except OSError as e:
        error_str = str(e)
        # Handle DNS/network errors
        if "getaddrinfo failed" in error_str or "Errno 11001" in error_str:
            logger.error(f"❌ Network/DNS error: {e}")
            logger.error("🔧 Attempting fallback configuration...")
            logger.info(f"🚀 Retrying with localhost (127.0.0.1) and reload disabled...")
            uvicorn.run(
                "main:app",
                host="127.0.0.1",
                port=settings.PORT,
                reload=False,
                log_level="info"
            )
        # Handle port already in use errors
        elif "10048" in error_str or "Address already in use" in error_str or "only one usage of each socket address" in error_str:
            logger.error(f"❌ Port {settings.PORT} is already in use!")
            logger.error("🔧 Port conflict detected. Please ensure no other instances are running.")
            logger.error(f"💡 To free the port, run: netstat -ano | findstr :{settings.PORT}")
            logger.error(f"   Then: taskkill /PID <PID> /F")
            raise
        else:
            logger.error(f"❌ Failed to start server: {e}")
            raise

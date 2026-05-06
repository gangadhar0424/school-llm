"""
School LLM - Main FastAPI Application
Complete backend API for AI-powered learning platform
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
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

# Import configuration and modules
from config import settings, validate_config
from database import (
    mongodb, user_db, activity_db, pdf_upload_db, chat_history_db,
    chat_session_db, analytics_db, assignment_db, submission_db,
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
from auth import (
    UserCreate, UserLogin, Token, LoginResponse, UserResponse, ChangePasswordRequest,
    UpdateUserClassRequest, AssignTeacherRequest,
    AssignmentCreate, AssignmentUpdate, SubmissionCreate, GradeOverride,
    hash_password, verify_password, create_access_token, verify_token,
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
    
    # Validate configuration
    if not validate_config():
        logger.error("⚠️  Configuration validation failed. Please check your .env file.")
        # Continue anyway for development
    
    # Connect to MongoDB
    logger.info("🔌 Attempting to connect to MongoDB...")
    try:
        await mongodb.connect()
        logger.info("✅ MongoDB connected successfully!")
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

# CORS middleware - Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:8502",
        "http://127.0.0.1:8502",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    """Verify JWT token and get current user"""
    token = credentials.credentials
    logger.info(f"🔐 Verifying token: {token[:20]}...")
    token_data = verify_token(token)
    
    if token_data is None or token_data.email is None:
        logger.error(f"❌ Token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"✓ Token verified for email: {token_data.email}")
    user = await user_db.get_user_by_email(token_data.email)
    if user is None:
        logger.error(f"❌ User not found in database for email: {token_data.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"✓ User found: {user['email']}")
    return user

# ============================================================================
# AUTH DECORATORS/MIDDLEWARE
# ============================================================================

def _resolve_role(user: Dict) -> str:
    """Read the user's effective role: prefer the explicit `role` field
    (set since Phase 1) and fall back to is_admin for legacy accounts."""
    role = (user.get("role") or "").strip().lower()
    if role in ("admin", "teacher", "student"):
        return role
    return "admin" if user.get("is_admin") else "student"


async def get_admin_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is an admin"""
    if _resolve_role(current_user) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


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

@app.post("/api/auth/signup")
async def signup(user_data: UserCreate):
    """Register a new user.

    Role-specific required fields:
      - student: class_level + section
      - teacher: subjects_taught + assigned_classes
      - admin:   no extra fields
    """
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
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CRITICAL SIGNUP ERROR: {type(e).__name__}: {str(e)}", exc_info=True)
        logger.error(f"💥 Check MongoDB connection at: {settings.MONGODB_URI}")
        raise HTTPException(status_code=500, detail=f"Signup failed: {type(e).__name__}. Please ensure MongoDB is running and accessible.")

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    """Login and get JWT token"""
    try:
        logger.info(f"🔐 Login attempt for email: {credentials.email}")
        
        # Get user by email
        logger.info(f"📡 Querying database for user: {credentials.email}")
        user = await user_db.get_user_by_email(credentials.email)
        
        if not user:
            logger.warning(f"❌ User not found: {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✓ User found: {credentials.email}")
        
        # Verify password
        logger.info(f"🔑 Verifying password for: {credentials.email}")
        if not verify_password(credentials.password, user['hashed_password']):
            logger.warning(f"❌ Invalid password for: {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"✓ Password verified for: {credentials.email}")
        
        # Check if user is active
        if not user.get('is_active', True):
            logger.warning(f"❌ Account inactive: {credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive"
            )
        
        is_admin = user.get('is_admin', False)
        # Resolve actual_role: prefer the explicit `role` field (set since
        # Phase 1) and fall back to is_admin for legacy accounts created
        # before the three-tier hierarchy existed.
        stored_role = (user.get('role') or "").strip().lower()
        if stored_role in ("admin", "teacher", "student"):
            actual_role = stored_role
        else:
            actual_role = "admin" if is_admin else "student"

        # Accept legacy "user" as an alias for "student" so older clients
        # don't break after the Phase 1 schema change.
        requested_role = (credentials.role or "").strip().lower()
        if requested_role == "user":
            requested_role = "student"

        logger.info(
            f"✓ User role determined: actual={actual_role}, "
            f"requested={requested_role} for {credentials.email}"
        )

        if requested_role != actual_role:
            pretty = {
                "admin": "Admin", "teacher": "Teacher", "student": "Student",
            }.get(actual_role, actual_role.title())
            detail = (
                f"This account is a {pretty} account. "
                f"Please select the {pretty} role."
            )
            logger.warning(
                f"❌ Role mismatch for {credentials.email}: "
                f"requested={requested_role}, actual={actual_role}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail,
            )
        
        # Log login activity
        try:
            await activity_db.log_activity(
                user_email=user['email'],
                activity_type='login',
                details={'username': user['username'], 'role': actual_role}
            )
            logger.info(f"✓ Login activity logged for: {credentials.email}")
        except Exception as e:
            logger.warning(f"⚠ Failed to log activity for {credentials.email}: {e}")
        
        # Create access token with role information
        logger.info(f"🎫 Generating JWT token for: {credentials.email}")
        access_token = create_access_token(data={"sub": user['email'], "role": actual_role})
        
        logger.info(f"✅ LOGIN SUCCESSFUL for: {credentials.email} (role: {actual_role})")
        
        # Return token with user info and actual admin status from database
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "is_admin": is_admin
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ CRITICAL LOGIN ERROR for {credentials.email}: {type(e).__name__}: {str(e)}", exc_info=True)
        if isinstance(e, (ConnectionFailure, ServerSelectionTimeoutError)):
            logger.error(f"💥 MongoDB Connection Status: Checking {settings.MONGODB_URI}")
            detail = (
                f"Login failed: {type(e).__name__}. Database connection error. Ensure:\n"
                f"1. MongoDB is running on {settings.MONGODB_URI}\n"
                "2. Network connection is available\n"
                "3. Database credentials are correct"
            )
        else:
            detail = "Login failed due to an internal server error. Check backend logs for details."

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: Dict = Depends(get_current_user)):
    """Get current user information including role + class fields."""
    return UserResponse(
        id=current_user['id'],
        email=current_user['email'],
        username=current_user['username'],
        full_name=current_user.get('full_name'),
        created_at=current_user['created_at'],
        is_active=current_user.get('is_active', True),
        is_admin=current_user.get('is_admin', False),
        role=_resolve_role(current_user),
        class_level=current_user.get('class_level'),
        section=current_user.get('section'),
        subjects_taught=current_user.get('subjects_taught'),
        assigned_classes=current_user.get('assigned_classes'),
    )

@app.post("/api/auth/change-password")
async def change_password(
    change_pwd_request: ChangePasswordRequest,
    current_user: Dict = Depends(get_current_user)
):
    """Change user password"""
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

@app.get("/api/admin/users")
async def get_all_users(admin_user: Dict = Depends(get_admin_user)):
    """Get all users with their activity (admin only)"""
    users = await activity_db.get_all_users_with_activity()
    return {"users": users, "total": len(users)}

@app.get("/api/admin/activity")
async def get_user_activity_log(
    user_email: Optional[str] = None,
    limit: int = 100,
    admin_user: Dict = Depends(get_admin_user)
):
    """Get user activity logs (admin only)"""
    activities = await activity_db.get_user_activity(user_email, limit)
    return {"activities": activities, "count": len(activities)}

@app.get("/api/admin/uploaded-pdfs")
async def get_uploaded_pdfs(
    limit: int = 100,
    admin_user: Dict = Depends(get_admin_user)
):
    """Get all uploaded PDFs (admin only)"""
    pdfs = await pdf_upload_db.get_all_uploads(limit)
    return {"pdfs": pdfs, "total": len(pdfs)}

@app.get("/api/my-uploaded-pdfs")
async def get_my_uploaded_pdfs(
    limit: int = 100,
    current_user: Dict = Depends(get_current_user)
):
    """Get only the PDFs uploaded by the currently logged-in user."""
    pdfs = await pdf_upload_db.get_user_uploads(current_user["email"], limit)
    return {"pdfs": pdfs, "total": len(pdfs)}

@app.put("/api/admin/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    request: dict,
    admin_user: Dict = Depends(get_admin_user)
):
    """Activate or deactivate a user (admin only)"""
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


@app.post("/api/teacher/assignments")
async def teacher_create_assignment(
    body: AssignmentCreate,
    teacher: Dict = Depends(get_teacher_user),
):
    """Create a new assignment (draft or published)."""
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

    ok = await assignment_db.update(assignment_id, update_doc)
    return {"message": "Updated" if ok else "No changes applied"}


@app.delete("/api/teacher/assignments/{assignment_id}")
async def teacher_delete_assignment(
    assignment_id: str,
    teacher: Dict = Depends(get_teacher_user),
):
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

    sub_doc["id"] = sid
    return {
        "submission": sub_doc,
        "message": f"Submitted! Auto-graded: {percent}% ({total:.1f} / {total_max:.0f}).",
    }


@app.get("/api/student/submissions")
async def student_list_submissions(student: Dict = Depends(get_student_user)):
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
    s = await submission_db.get(submission_id)
    if not s or s.get("student_email") != student["email"]:
        raise HTTPException(status_code=404, detail="Submission not found")
    s.pop("_id", None)
    a = await assignment_db.get(s.get("assignment_id"))
    if a:
        a.pop("_id", None)
        # Hide answer keys until after submission? Already submitted, so OK to return.
    return {"submission": s, "assignment": a}


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
    request: Request,
    file: UploadFile = File(...)
):
    """Upload and process local PDF file"""
    try:
        logger.info(f"📄 Starting PDF upload: {file.filename}")
        
        # Manually extract and verify token
        auth_header = request.headers.get('Authorization')
        logger.info(f"📋 Authorization header present: {bool(auth_header)}")
        
        current_user = None
        if auth_header:
            logger.info(f"📋 Auth header value: {auth_header[:30]}...")
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
                logger.info(f"🔐 Verifying token...")
                token_data = verify_token(token)
                
                if token_data and token_data.email:
                    logger.info(f"✓ Token verified for email: {token_data.email}")
                    current_user = await user_db.get_user_by_email(token_data.email)
                    if current_user:
                        logger.info(f"✓ User found: {current_user['email']}")
                    else:
                        logger.error(f"❌ User not found in database for email: {token_data.email}")
                else:
                    logger.error(f"❌ Token verification failed")
            else:
                logger.error(f"❌ Invalid Authorization header format")
        else:
            logger.warning(f"⚠️ No Authorization header provided")
        
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        upload_id = uuid4().hex
        stored_filename = f"{upload_id}.pdf"
        pdf_identifier = f"upload_{upload_id}"

        # Save uploaded file using a unique server-side name so different users do not collide.
        file_path = Path(settings.UPLOAD_DIR) / stored_filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            f.write(content)
        
        # Get file size
        file_size = file_path.stat().st_size
        
        logger.info(f"Processing uploaded PDF: {file.filename}")

        # Fast path: process and chunk now; warm vectors in the background for later AI calls.
        ready = await _ensure_pdf_ready(pdf_identifier, ensure_vector=False)
        pdf_data = ready["pdf_data"]
        asyncio.create_task(_warm_pdf_vectors(pdf_identifier))
        
        # Log the PDF upload
        await pdf_upload_db.log_upload(
            filename=file.filename,
            file_size=file_size,
            uploader_email=current_user['email'],
            pdf_identifier=pdf_identifier,
            stored_filename=stored_filename
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
async def generate_summary(request: SummaryRequest, current_user: Dict = Depends(get_current_user)):
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

        _ai_cache_set(cache_key, result)
        log_phase(logger, "api.summary", "total", started, cache_hit=False, summary_type=request.summary_type)
        logger.info(f"Summary generated in {time.perf_counter() - started:.2f}s for {pdf_key} ({request.summary_type})")
        return result
            
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/quiz")
async def generate_quiz(request: QuizRequest, current_user: Dict = Depends(get_current_user)):
    """Generate quiz from PDF"""
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
        return quiz_data
        
    except Exception as e:
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

async def _auto_name_session(session_id: str, user_email: str, question: str, answer: str) -> None:
    """Use a quick LLM call to generate a short conversation title after the first exchange."""
    import re as _re
    def _fallback_title(q: str) -> str:
        cleaned = _re.sub(r'^\s*(what|how|why|when|where|who|is|are|can|could|do|does|did|explain|tell me|describe)\s+', '', (q or "").strip(), flags=_re.I)
        cleaned = _re.sub(r'[?.!]+$', '', cleaned).strip()
        if not cleaned:
            return "New chat"
        words = cleaned.split()[:6]
        title = " ".join(words).strip().title()
        return title[:50] if title else "New chat"

    try:
        from ai.ollama_client import ollama_client
        prompt_answer = (answer or "")[:400]
        title_raw = await ollama_client.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a title generator. Output ONLY a plain 3-6 word title for this Q&A. "
                        "Rules: no markdown, no '#' or '*' characters, no quotes, no colons, no prefixes like 'Title:' or 'INTENT:', "
                        "no trailing punctuation. Just the title words themselves."
                    ),
                },
                {"role": "user", "content": f"Question: {question}\nAnswer: {prompt_answer}"},
            ],
            model=settings.OLLAMA_CHAT_MODEL,
            temperature=0.1,
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
async def ask_question(request: QuestionRequest, current_user: Dict = Depends(get_current_user)):
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

@app.post("/api/audio")
async def generate_audio(request: AudioRequest, current_user: Dict = Depends(get_current_user)):
    """Generate audio overview"""
    try:
        if request.pdf_url:
            await _assert_upload_access(request.pdf_url, current_user)
        audio_data = await audio_generator.generate_audio(
            text=request.text,
            pdf_identifier=request.pdf_url
        )
        
        return audio_data
        
    except Exception as e:
        logger.error(f"Error generating audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio/{filename}")
async def get_audio_file(filename: str):
    """Serve audio file"""
    try:
        file_path = Path(settings.AUDIO_DIR) / filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        suffix = file_path.suffix.lower()
        media_type = "audio/wav" if suffix == ".wav" else "audio/mpeg"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving audio file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video")
async def generate_video(request: VideoRequest, current_user: Dict = Depends(get_current_user)):
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
        asyncio.create_task(activity_db.log_activity(
            current_user["email"], "video",
            {"pdf": pdf_identifier, "query": (query or "")[:80], "style": request.style or "slides"}
        ))
        return video_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/video/{filename}")
async def get_video_file(filename: str):
    """Serve generated MP4 files."""
    try:
        # Basic path-traversal guard
        if "/" in filename or "\\" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        file_path = Path(settings.VIDEO_DIR) / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        return FileResponse(str(file_path), media_type="video/mp4", filename=filename)
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

        # Remove physical file
        if stored_filename:
            file_path = Path(settings.UPLOAD_DIR) / stored_filename
            if file_path.exists():
                file_path.unlink()

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
    current_user: Dict = Depends(get_current_user),
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


# ==================== ANALYTICS ====================

@app.get("/api/admin/analytics")
async def get_analytics(admin_user: Dict = Depends(get_admin_user)):
    """Analytics dashboard data (admin only)."""
    metrics = await analytics_db.get_metrics()
    usage_over_time = await analytics_db.get_usage_over_time(days=7)
    feature_usage = await analytics_db.get_feature_usage()
    return {
        "metrics": metrics,
        "usage_over_time": usage_over_time,
        "feature_usage": feature_usage,
    }


# ==================== AUDIT LOG EXPORT ====================

@app.get("/api/admin/export-logs")
async def export_audit_logs(
    user_email: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin_user: Dict = Depends(get_admin_user),
):
    """Export audit logs as CSV (admin only)."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    start_dt = None
    end_dt = None
    if start_date:
        try:
            from datetime import datetime as dt
            start_dt = dt.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format. Use YYYY-MM-DD")
    if end_date:
        try:
            from datetime import datetime as dt
            end_dt = dt.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format. Use YYYY-MM-DD")

    logs = await analytics_db.get_audit_logs(
        user_email=user_email,
        start_date=start_dt,
        end_date=end_dt,
        limit=5000,
    )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["id", "user_email", "activity_type", "details", "timestamp"],
        extrasaction="ignore",
    )
    writer.writeheader()
    for log in logs:
        log["details"] = json.dumps(log.get("details", {}))
        log["timestamp"] = str(log.get("timestamp", ""))
        writer.writerow(log)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


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
    
    try:
        uvicorn.run(
            "main:app",
            host=host,
            port=settings.PORT,
            reload=enable_reload,
            log_level="info"
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

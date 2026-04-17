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
from database import mongodb, user_db, activity_db, pdf_upload_db
from pdf_handler import pdf_handler
from vector_db import vector_db
from ai.summary import summary_generator
from ai.quiz import quiz_generator
from ai.qa import qa_system
from ai.audio import audio_generator
from ai.video import video_generator
from timing_utils import log_phase
from auth import (
    UserCreate, UserLogin, Token, LoginResponse, UserResponse, ChangePasswordRequest,
    hash_password, verify_password, create_access_token, verify_token
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

# CORS middleware - Allow frontend to access backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
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

class QuizRequest(BaseModel):
    pdf_url: str
    num_questions: Optional[int] = None
    difficulty: Optional[str] = None  # basic, medium, hard
    search_query: Optional[str] = None  # optional topic filter
    question_types: Optional[List[str]] = None  # ["mcq", "fill-in-blank", "true-false", "short-answer"]

class SummaryRequest(BaseModel):
    pdf_url: str
    summary_type: str = "both"  # short, detailed, or both

class AudioRequest(BaseModel):
    text: str
    pdf_url: Optional[str] = None

class VideoRequest(BaseModel):
    summary: str

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

async def get_admin_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is an admin"""
    if not current_user.get('is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user

async def get_student_user(current_user: Dict = Depends(get_current_user)) -> Dict:
    """Verify that current user is a student (non-admin)"""
    if current_user.get('is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students only"
        )
    return current_user

@app.post("/api/auth/signup")
async def signup(user_data: UserCreate):
    """Register a new user"""
    try:
        logger.info(f"📝 SIGNUP attempt: email={user_data.email}, username={user_data.username}")
        
        # Check if user already exists
        logger.info(f"🔍 Checking if email already registered: {user_data.email}")
        existing_user = await user_db.get_user_by_email(user_data.email)
        if existing_user:
            logger.warning(f"❌ Email already registered: {user_data.email}")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        logger.info(f"✓ Email available, proceeding with signup...")
        
        # Hash password
        logger.info(f"🔑 Hashing password...")
        hashed_password = hash_password(user_data.password)
        logger.info(f"✓ Password hashed successfully")
        
        is_admin = (user_data.role == "admin")
        logger.info(f"✓ Role selected={user_data.role} → stored_is_admin={is_admin}")
        
        # Create user document
        user_doc = {
            'email': user_data.email,
            'username': user_data.username,
            'full_name': user_data.full_name,
            'hashed_password': hashed_password,
            'created_at': datetime.utcnow(),
            'is_active': True,
            'is_admin': is_admin
        }
        
        logger.info(f"💾 Saving user to MongoDB database...")
        
        # Save to database
        user_id = await user_db.create_user(user_doc)
        
        if not user_id:
            logger.error(f"❌ Failed to create user in database for: {user_data.email}")
            raise HTTPException(status_code=500, detail="Failed to create user in database")
        
        logger.info(f"✅ SIGNUP SUCCESSFUL: user_id={user_id}, email={user_data.email}, role={'admin' if is_admin else 'user'}")
        
        return UserResponse(
            id=str(user_id),
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            created_at=user_doc['created_at'],
            is_active=True,
            is_admin=is_admin
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
        actual_role = "admin" if is_admin else "user"
        requested_role = credentials.role.strip().lower()
        logger.info(f"✓ User role determined: actual={actual_role}, requested={requested_role} for {credentials.email}")

        if requested_role != actual_role:
            detail = (
                "This account is an Admin account. Please select the Admin role."
                if is_admin else
                "This account is a Student account. Please select the Student role."
            )
            logger.warning(f"❌ Role mismatch for {credentials.email}: requested={requested_role}, actual={actual_role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=detail
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
    """Get current user information"""
    return UserResponse(
        id=current_user['id'],
        email=current_user['email'],
        username=current_user['username'],
        full_name=current_user.get('full_name'),
        created_at=current_user['created_at'],
        is_active=current_user.get('is_active', True),
        is_admin=current_user.get('is_admin', False)
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
        if request.summary_type == "short":
            summary = await summary_generator.generate_short_summary(full_text, study_context=study_context)
            result = {"summary": summary, "type": "short"}
        elif request.summary_type == "detailed":
            summary = await summary_generator.generate_detailed_summary(full_text, study_context=study_context)
            result = {"summary": summary, "type": "detailed"}
        else:  # both
            result = await summary_generator.generate_both_summaries(full_text, study_context=study_context)
        log_phase(logger, "api.summary", "generate_summary", phase_started, summary_type=request.summary_type)

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
            question_types=request.question_types or ["mcq"]
        )
        log_phase(logger, "api.quiz", "generate_quiz", phase_started, requested_questions=request.num_questions or 3)
        _ai_cache_set(cache_key, quiz_data)
        log_phase(logger, "api.quiz", "total", started, cache_hit=False, questions=quiz_data.get("total_questions", 0))
        logger.info(
            f"Quiz generated successfully with {quiz_data.get('total_questions', 0)} questions "
            f"in {time.perf_counter() - started:.2f}s"
        )
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
        cache_key = None
        if not request.conversation_history:
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
                return cached
            log_phase(logger, "api.qa", "cache_lookup", phase_started, cache_hit=False)
        
        phase_started = time.perf_counter()
        answer_data = await qa_system.answer_question(
            pdf_url=pdf_key,
            question=request.question,
            conversation_history=request.conversation_history,
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
    """Generate video overview"""
    try:
        video_data = await video_generator.generate_video(request.summary)
        return video_data
        
    except Exception as e:
        logger.error(f"Error generating video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

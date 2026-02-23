"""
School LLM - Main FastAPI Application
Complete backend API for AI-powered learning platform
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List, Dict
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

# Import configuration and modules
from config import settings, validate_config
from database import mongodb, TextbookDB, SessionDB, user_db, scraper_db, activity_db
from pdf_handler import pdf_handler
from vector_db import vector_db
from ai.summary import summary_generator
from ai.quiz import quiz_generator
from ai.qa import qa_system
from ai.audio import audio_generator
from ai.video import video_generator
from scraper import NCERTScraper, APScraper, TelanganaScraper, karnataka_scraper, tamil_nadu_scraper
from auth import (
    UserCreate, UserLogin, Token, LoginResponse, UserResponse,
    hash_password, verify_password, create_access_token, verify_token
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("🚀 Starting School LLM API...")
    
    # Validate configuration
    if not validate_config():
        logger.error("Configuration validation failed. Please check your .env file.")
        # Continue anyway for development
    
    # Connect to MongoDB
    try:
        await mongodb.connect()
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        logger.warning("API will continue but database features may not work")
    
    # Warm up Ollama model in background (don't block startup)
    import asyncio
    from ai.ollama_client import ollama_client
    asyncio.create_task(ollama_client.warm_up())
    
    logger.info("✅ School LLM API is ready!")
    
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for request/response
class PDFUrlRequest(BaseModel):
    pdf_url: str

class QuestionRequest(BaseModel):
    pdf_url: str
    question: str
    conversation_history: Optional[List[Dict]] = None

class QuizRequest(BaseModel):
    pdf_url: str
    num_questions: Optional[int] = None
    difficulty: Optional[str] = None  # basic, medium, hard

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
    token_data = verify_token(token)
    
    if token_data is None or token_data.email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await user_db.get_user_by_email(token_data.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

@app.post("/api/auth/signup")
async def signup(user_data: UserCreate):
    """Register a new user"""
    try:
        logger.info(f"✓ Signup endpoint called with email: {user_data.email}")
        
        # Check if user already exists
        existing_user = await user_db.get_user_by_email(user_data.email)
        if existing_user:
            logger.warning(f"Email already registered: {user_data.email}")
            raise HTTPException(status_code=400, detail="Email already registered")
        
        logger.info(f"✓ Email not found, proceeding with signup...")
        
        # Hash password
        hashed_password = hash_password(user_data.password)
        logger.info(f"✓ Password hashed")
        
        # Use role from user input
        is_admin = (user_data.role == "admin")
        logger.info(f"✓ Role set to: {user_data.role} (is_admin={is_admin})")
        
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
        
        logger.info(f"✓ User document created, saving to database...")
        
        # Save to database
        user_id = await user_db.create_user(user_doc)
        
        logger.info(f"✓ User saved with ID: {user_id}")
        
        if not user_id:
            raise HTTPException(status_code=500, detail="Failed to create user")
        
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
        logger.error(f"❌ Signup error: {str(e)}", exc_info=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    """Login and get JWT token"""
    # Get user by email
    user = await user_db.get_user_by_email(credentials.email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(credentials.password, user['hashed_password']):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.get('is_active', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Log login activity
    await activity_db.log_activity(
        user_email=user['email'],
        activity_type='login',
        details={'username': user['username']}
    )
    
    # Create access token
    access_token = create_access_token(data={"sub": user['email']})
    
    # Return token with user info (for immediate redirect decision)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "is_admin": user.get('is_admin', False)
        }
    }

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

# ============================================================================
# SCRAPER ENDPOINTS
# ============================================================================

@app.get("/api/scraper/data")
async def get_scraped_data():
    """Get all scraped website data (public endpoint)"""
    data = await scraper_db.get_all_scraped_data()
    return data

@app.get("/api/scraper/pdfs")
async def get_scraped_pdfs(current_user: Dict = Depends(get_current_user)):
    """Get all scraped PDF links"""
    pdfs = await scraper_db.get_scraped_pdfs()
    return {"count": len(pdfs), "pdfs": pdfs}

@app.post("/api/scraper/scrape-url")
async def scrape_single_url(
    request: dict,
    current_user: Dict = Depends(get_current_user)
):
    """Scrape a single URL provided by the user"""
    try:
        url = request.get("url")
        if not url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URL is required"
            )
        
        from scraper import WebScraper
        
        async with WebScraper() as scraper:
            result = await scraper.scrape_url(url)
            
            if result:
                # Save to database
                await scraper.save_to_database(result)
                return {
                    "message": "URL scraped successfully",
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "links_found": len(result.get("links", [])),
                    "pdfs_found": len(result.get("pdf_links", []))
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to scrape URL"
                )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scraping failed: {str(e)}"
        )

# ==================== NCERT Books Routes ====================

# Cache for NCERT books data
_ncert_books_cache: Dict[str, any] = None

# Cache for AP board books data
_ap_books_cache: Dict[str, any] = None

# Cache for Telangana board books data
_ts_books_cache: Dict[str, any] = None

# Cache for Tamil Nadu board books data
_tn_books_cache: Dict[str, any] = None

@app.get("/api/ncert/books")
async def get_ncert_books(refresh: bool = False):
    """
    Get all NCERT books for all classes (1-12)
    Returns: Dictionary with class-wise, subject-wise book data
    """
    global _ncert_books_cache
    
    # Return cached data if available and not forcing refresh
    if _ncert_books_cache and not refresh:
        return _ncert_books_cache
    
    # Scrape fresh data
    try:
        scraper = NCERTScraper()
        books_data = scraper.scrape_books()
        _ncert_books_cache = books_data
        return books_data
    except Exception as e:
        logger.error(f"Failed to fetch NCERT books: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch NCERT books: {str(e)}")


@app.get("/api/ap/books")
async def get_ap_books(refresh: bool = False):
    """Get AP state board book links grouped by class and subject."""
    global _ap_books_cache

    if _ap_books_cache and not refresh:
        return _ap_books_cache

    try:
        scraper = APScraper()
        books_data = scraper.scrape_books()
        _ap_books_cache = books_data
        return books_data
    except Exception as e:
        logger.error(f"Failed to fetch AP books: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch AP books: {str(e)}")


@app.get("/api/telangana/books")
async def get_telangana_books(refresh: bool = False):
    """Get Telangana Open School book links grouped by level and subject."""
    global _ts_books_cache

    if _ts_books_cache and not refresh:
        return _ts_books_cache

    try:
        scraper = TelanganaScraper()
        books_data = scraper.scrape_books()
        _ts_books_cache = books_data
        return books_data
    except Exception as e:
        logger.error(f"Failed to fetch Telangana books: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch Telangana books: {str(e)}")


@app.get("/api/tamilnadu/books")
async def get_tamilnadu_books(refresh: bool = False):
    """Get Tamil Nadu textbook links grouped by class and subject."""
    global _tn_books_cache
    
    cache_size = len(_tn_books_cache) if _tn_books_cache else 0
    logger.info(f"Tamil Nadu API called with refresh={refresh}, cache has {cache_size} items")

    if _tn_books_cache and not refresh:
        logger.info("Returning cached Tamil Nadu books")
        return _tn_books_cache

    try:
        logger.info("Calling tamil_nadu_scraper.scrape_books()...")
        books_data = tamil_nadu_scraper.scrape_books()
        logger.info(f"Scraper returned {len(books_data)} classes")
        _tn_books_cache = books_data
        return books_data
    except Exception as e:
        logger.error(f"Failed to fetch Tamil Nadu books: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Tamil Nadu books: {str(e)}")


@app.get("/api/karnataka/classes")
async def get_karnataka_classes(refresh: bool = False):
    """Get Karnataka State Textbook classes."""
    try:
        classes = await karnataka_scraper.fetch_classes()
        return classes
    except Exception as e:
        logger.error(f"Failed to fetch Karnataka classes: {e}")
        return _friendly_error("Failed to fetch Karnataka classes. Please try again later.")


@app.post("/api/karnataka/subjects")
async def get_karnataka_subjects(request: dict):
    """Get Karnataka State Textbook textbooks for a class.
    
    Expected POST body:
    {
        "class_number": "1"
    }
    """
    try:
        class_number = request.get("class_number")
        if not class_number:
            raise HTTPException(status_code=400, detail="class_number is required")
        
        subjects = await karnataka_scraper.fetch_subjects(str(class_number))
        return subjects
    except Exception as e:
        logger.error(f"Failed to fetch Karnataka subjects: {e}")
        return _friendly_error("Failed to fetch Karnataka subjects. Please try again later.")


@app.get("/api/ncert/books/class/{class_number}")
async def get_ncert_books_by_class(class_number: int):
    """
    Get books for a specific class (1-12)
    Args:
        class_number: Class number (1-12)
    Returns: Dictionary with subject-wise book data
    """
    if class_number < 1 or class_number > 12:
        raise HTTPException(status_code=400, detail="Class number must be between 1 and 12")
    
    books_data = await get_ncert_books()
    class_key = f"class_{class_number}"
    
    if class_key not in books_data:
        raise HTTPException(status_code=404, detail=f"No books found for class {class_number}")
    
    return books_data[class_key]


@app.get("/api/ncert/books/class/{class_number}/subject/{subject}")
async def get_ncert_books_by_subject(class_number: int, subject: str):
    """
    Get books for a specific class and subject
    Args:
        class_number: Class number (1-12)
        subject: Subject name (e.g., mathematics, science, english)
    Returns: List of books for the subject
    """
    class_books = await get_ncert_books_by_class(class_number)
    
    if subject not in class_books:
        raise HTTPException(
            status_code=404, 
            detail=f"No books found for subject '{subject}' in class {class_number}"
        )
    
    return class_books[subject]

# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

async def get_admin_user(current_user: Dict = Depends(get_current_user)):
    """Verify user is an admin"""
    if not current_user.get('is_admin', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

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

@app.put("/api/admin/scraped-data/{data_id}")
async def update_scraped_url(
    data_id: str,
    request: dict,
    admin_user: Dict = Depends(get_admin_user)
):
    """Update scraped URL data (admin only)"""
    try:
        update_data = {k: v for k, v in request.items() if k in ['url', 'title', 'description']}
        if update_data:
            success = await scraper_db.update_scraped_data(data_id, update_data)
            if success:
                return {"message": "URL updated successfully"}
            else:
                raise HTTPException(status_code=404, detail="Data not found")
        else:
            raise HTTPException(status_code=400, detail="No valid fields to update")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/admin/scraped-data/{data_id}")
async def delete_scraped_url(
    data_id: str,
    admin_user: Dict = Depends(get_admin_user)
):
    """Delete scraped URL data (admin only)"""
    try:
        success = await scraper_db.delete_scraped_data(data_id)
        if success:
            return {"message": "URL deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Data not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DASHBOARD ENDPOINTS ====================

@app.get("/api/boards")
async def get_boards():
    """Get all available boards"""
    try:
        boards = await TextbookDB.get_all_boards()
        return {"boards": boards}
    except Exception as e:
        logger.error(f"Error fetching boards: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/classes/{board}")
async def get_classes(board: str):
    """Get classes for a specific board"""
    try:
        classes = await TextbookDB.get_classes_by_board(board)
        return {"board": board, "classes": classes}
    except Exception as e:
        logger.error(f"Error fetching classes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/subjects/{board}/{class_name}")
async def get_subjects(board: str, class_name: str):
    """Get subjects for a specific board and class"""
    try:
        subjects = await TextbookDB.get_subjects_by_board_and_class(board, class_name)
        return {"board": board, "class": class_name, "subjects": subjects}
    except Exception as e:
        logger.error(f"Error fetching subjects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/textbooks")
async def get_textbooks(board: Optional[str] = None, class_name: Optional[str] = None, subject: Optional[str] = None):
    """Get textbooks with optional filters"""
    try:
        textbooks = await TextbookDB.get_textbooks(board, class_name, subject)
        return {"textbooks": textbooks, "count": len(textbooks)}
    except Exception as e:
        logger.error(f"Error fetching textbooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/textbooks/{textbook_id}")
async def get_textbook(textbook_id: str):
    """Get a specific textbook by ID"""
    try:
        textbook = await TextbookDB.get_textbook_by_id(textbook_id)
        if not textbook:
            raise HTTPException(status_code=404, detail="Textbook not found")
        return textbook
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching textbook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
async def search_textbooks(q: str):
    """Search textbooks"""
    try:
        results = await TextbookDB.search_textbooks(q)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"Error searching textbooks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PDF PROCESSING ENDPOINTS ====================

@app.post("/api/process_pdf_url")
async def process_pdf_url(request: PDFUrlRequest):
    """Process PDF from URL and prepare for AI features"""
    try:
        logger.info(f"Processing PDF from URL: {request.pdf_url}")

        resolved_url = _resolve_pdf_url(request.pdf_url)
        
        # Extract and chunk PDF
        pdf_data = await pdf_handler.process_pdf(resolved_url, is_url=True)
        
        # Store in vector database for Q&A
        chunk_texts = [chunk["text"] for chunk in pdf_data["chunks"]]
        await vector_db.add_documents(
            pdf_url=resolved_url,
            chunks=chunk_texts
        )
        
        return {
            "status": "success",
            "message": "PDF processed successfully",
            "pdf_url": resolved_url,
            "total_chunks": pdf_data["total_chunks"],
            "total_chars": pdf_data["total_chars"]
        }
        
    except Exception as e:
        logger.error(f"Error processing PDF URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload and process local PDF file"""
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Save uploaded file
        file_path = Path(settings.UPLOAD_DIR) / file.filename
        
        with open(file_path, "wb") as f:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            f.write(content)
        
        logger.info(f"Processing uploaded PDF: {file.filename}")
        
        # Process PDF
        pdf_data = await pdf_handler.process_pdf(str(file_path), is_url=False)
        
        # Store in vector database
        chunk_texts = [chunk["text"] for chunk in pdf_data["chunks"]]
        pdf_identifier = f"upload_{file.filename}"
        
        await vector_db.add_documents(
            pdf_url=pdf_identifier,
            chunks=chunk_texts
        )
        
        return {
            "status": "success",
            "message": "PDF uploaded and processed successfully",
            "pdf_identifier": pdf_identifier,
            "filename": file.filename,
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
    filename = pdf_identifier.replace("upload_", "", 1)
    return Path(settings.UPLOAD_DIR) / filename

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
async def generate_summary(request: SummaryRequest):
    """Generate summary from PDF"""
    try:
        pdf_data = await _process_pdf_source(request.pdf_url)
        full_text = pdf_data["full_text"]
        
        if request.summary_type == "short":
            summary = await summary_generator.generate_short_summary(full_text)
            return {"summary": summary, "type": "short"}
        elif request.summary_type == "detailed":
            summary = await summary_generator.generate_detailed_summary(full_text)
            return {"summary": summary, "type": "detailed"}
        else:  # both
            summaries = await summary_generator.generate_both_summaries(full_text)
            return summaries
            
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/quiz")
async def generate_quiz(request: QuizRequest):
    """Generate quiz from PDF"""
    try:
        pdf_data = await _process_pdf_source(request.pdf_url)
        full_text = pdf_data["full_text"]
        quiz_data = await quiz_generator.generate_quiz(full_text, request.num_questions, request.difficulty)
        return quiz_data
        
    except Exception as e:
        logger.error(f"Error generating quiz: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/ask")
async def ask_question(request: QuestionRequest):
    """Answer question using RAG"""
    try:
        # Ensure PDF is processed in vector DB
        if not vector_db.collection_exists(request.pdf_url):
            pdf_data = await _process_pdf_source(request.pdf_url)
            chunk_texts = [chunk["text"] for chunk in pdf_data["chunks"]]
            await vector_db.add_documents(request.pdf_url, chunk_texts)
        
        answer_data = await qa_system.answer_question(
            pdf_url=request.pdf_url,
            question=request.question,
            conversation_history=request.conversation_history
        )
        return answer_data
        
    except Exception as e:
        logger.error(f"Error answering question: {e}")
        msg = _friendly_error(e)
        raise HTTPException(status_code=500, detail=msg)

@app.post("/api/audio")
async def generate_audio(request: AudioRequest):
    """Generate audio overview"""
    try:
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
async def generate_video(request: VideoRequest):
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
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )

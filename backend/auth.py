"""
Authentication module for School LLM
Handles JWT token generation, validation, and password hashing
"""
from datetime import datetime, timedelta
from typing import Literal, Optional
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
import logging
from config import settings

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pydantic models
class UserCreate(BaseModel):
    """User registration model"""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: Literal["admin", "user"] = "user"

class UserLogin(BaseModel):
    """User login model"""
    email: EmailStr
    password: str
    role: Literal["admin", "user"] = "user"

class Token(BaseModel):
    """JWT token response"""
    access_token: str
    token_type: str

class LoginResponse(BaseModel):
    """Login response with token and user info"""
    access_token: str
    token_type: str
    user: dict

class TokenData(BaseModel):
    """Token payload data"""
    email: Optional[str] = None
    role: Optional[str] = None  # "admin" or "user"

class UserResponse(BaseModel):
    """User response (no password)"""
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    created_at: datetime
    is_active: bool
    is_admin: bool = False

class ChangePasswordRequest(BaseModel):
    """Change password request model"""
    old_password: str
    new_password: str

# Password utilities
def _normalize_password_bytes(password: str) -> bytes:
    """Normalize password to bcrypt's 72-byte limit."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password_bytes
    return password_bytes[:72]

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    password_bytes = _normalize_password_bytes(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        if not hashed_password or not isinstance(hashed_password, str):
            logger.warning("Invalid password hash format encountered during verification")
            return False

        return bcrypt.checkpw(
            _normalize_password_bytes(plain_password),
            hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        logger.warning("Invalid password hash format encountered during verification")
        return False

# JWT utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with role information"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode a JWT token, extracting email and role"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role", "user")  # Default to "user" if not specified
        if email is None:
            return None
        return TokenData(email=email, role=role)
    except JWTError:
        return None

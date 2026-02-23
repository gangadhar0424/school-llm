"""
Authentication module for School LLM
Handles JWT token generation, validation, and password hashing
"""
from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
import os

# JWT Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pydantic models
class UserCreate(BaseModel):
    """User registration model"""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "user"  # "admin" or "user"

class UserLogin(BaseModel):
    """User login model"""
    email: EmailStr
    password: str

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

class UserResponse(BaseModel):
    """User response (no password)"""
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    created_at: datetime
    is_active: bool
    is_admin: bool = False

# Password utilities
def _normalize_password(password: str) -> str:
    """Normalize password to bcrypt's 72-byte limit."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) <= 72:
        return password
    return password_bytes[:72].decode("utf-8", errors="ignore")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(_normalize_password(password))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(_normalize_password(plain_password), hashed_password)

# JWT utilities
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode a JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            return None
        return TokenData(email=email)
    except JWTError:
        return None

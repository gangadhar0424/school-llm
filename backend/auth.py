"""
Authentication module for School LLM
Handles JWT token generation, validation, and password hashing
"""
from datetime import datetime, timedelta
from typing import List, Literal, Optional
import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field, validator
import logging
from config import settings

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = "HS256"
# JWT lifetime — set to None so tokens NEVER expire. Product decision:
# users stay logged in as long as they keep the cookie/URL. To re-enable
# expiry, set this to a positive number of minutes (e.g. 60*24*7 for 7 days).
#
# Security tradeoff: a leaked token is valid forever until the user logs
# out. Acceptable for a self-hosted school app; revisit if this ever ships
# to multi-tenant production.
ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = None

# Pydantic models
# ---------------------------------------------------------------------------
# Role hierarchy (added for grade-aware evaluation):
#   admin    — full system access (legacy "admin" role; is_admin=True)
#   teacher  — assigned to specific class+section combos and subjects;
#              can evaluate answers for those students
#   student  — has a class_level (1-10) + section (A/B/C); answers are
#              graded by class-specific standards
# ---------------------------------------------------------------------------
RoleType = Literal["admin", "teacher", "student"]
SectionType = Literal["A", "B", "C"]
SubjectType = Literal["Math", "Science", "English", "Social", "Computer"]


def _normalize_class_section(cls: str) -> str:
    """Normalize a class+section combo like '5a' or ' 10 a ' to '5A' / '10A'."""
    s = (cls or "").strip().upper().replace(" ", "")
    return s


class UserCreate(BaseModel):
    """User registration model.

    Required fields depend on role:
      - student: class_level (1-10) + section (A/B/C)
      - teacher: subjects_taught + assigned_classes (e.g. ['5A','6A'])
      - admin:   no extra fields
    """
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: RoleType = "student"
    # Student fields
    class_level: Optional[int] = Field(default=None, ge=1, le=10)
    section: Optional[SectionType] = None
    # Teacher fields
    subjects_taught: Optional[List[SubjectType]] = None
    assigned_classes: Optional[List[str]] = None  # e.g. ["5A","6A"]

    @validator("assigned_classes", each_item=True)
    def _norm_class(cls, v: str) -> str:
        return _normalize_class_section(v)


class UserLogin(BaseModel):
    """User login model.

    Accepts the legacy value "user" as an alias for "student" so that
    older cached frontend builds don't fail Pydantic validation after the
    Phase 1 hierarchy change. The endpoint normalizes it before lookup.
    """
    email: EmailStr
    password: str
    role: Literal["admin", "teacher", "student", "user"] = "student"

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
    role: Optional[str] = None  # admin / teacher / student (or legacy "user")


class UserResponse(BaseModel):
    """User response (no password)"""
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    created_at: datetime
    is_active: bool
    is_admin: bool = False
    role: Optional[str] = None
    class_level: Optional[int] = None
    section: Optional[str] = None
    subjects_taught: Optional[List[str]] = None
    assigned_classes: Optional[List[str]] = None
    onboarding_completed: bool = False
    theme: str = "cobalt"  # user's chosen color theme


class UpdateUserClassRequest(BaseModel):
    """Admin-only: update a student's class/section."""
    class_level: int = Field(..., ge=1, le=10)
    section: SectionType


class AssignTeacherRequest(BaseModel):
    """Admin-only: set a teacher's subjects + assigned class+section combos."""
    subjects_taught: List[SubjectType]
    assigned_classes: List[str]

    @validator("assigned_classes", each_item=True)
    def _norm_class(cls, v: str) -> str:
        return _normalize_class_section(v)


# ───────────────────────────────────────────────────────────────────────────
# Assignment + Submission models (teacher → students workflow)
# ───────────────────────────────────────────────────────────────────────────
AssignmentStatus = Literal["draft", "published", "closed"]


class AssignmentQuestion(BaseModel):
    """A single question inside an assignment.

    `marks` controls the per-question weight when computing the final
    assignment grade (default 10). The hybrid evaluator returns a 0-10
    score, which is rescaled to `marks` for the per-question result.
    """
    question: str
    expected_answer: str = ""
    keywords: Optional[List[str]] = None
    target_class: Optional[int] = Field(default=None, ge=1, le=10)
    subject: Optional[SubjectType] = None
    marks: int = Field(default=10, ge=1, le=100)


class AssignmentCreate(BaseModel):
    """Teacher-only: create or save-as-draft an assignment."""
    title: str
    description: Optional[str] = ""
    class_section: str  # e.g. "5A" — must be in teacher's assigned_classes
    subject: Optional[SubjectType] = None
    questions: List[AssignmentQuestion]
    due_date: Optional[datetime] = None
    status: AssignmentStatus = "draft"

    @validator("class_section")
    def _norm_cs(cls, v: str) -> str:
        return _normalize_class_section(v)


class AssignmentUpdate(BaseModel):
    """Teacher-only: partial update to an assignment they own."""
    title: Optional[str] = None
    description: Optional[str] = None
    subject: Optional[SubjectType] = None
    questions: Optional[List[AssignmentQuestion]] = None
    due_date: Optional[datetime] = None
    status: Optional[AssignmentStatus] = None


class SubmissionAnswer(BaseModel):
    """One answer in a student's assignment submission."""
    question_index: int = Field(..., ge=0)
    student_answer: str


class SubmissionCreate(BaseModel):
    """Student-only: submit answers to a published assignment."""
    answers: List[SubmissionAnswer]


class GradeOverride(BaseModel):
    """Teacher-only: override an auto-graded answer."""
    question_index: int = Field(..., ge=0)
    score: float = Field(..., ge=0.0, le=10.0)
    comment: Optional[str] = ""

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
    """Create a JWT access token with role information.

    If `expires_delta` is not provided AND `ACCESS_TOKEN_EXPIRE_MINUTES` is
    None, the token is issued WITHOUT an `exp` claim — it will never
    expire on its own. The verify_token call does no expiry check beyond
    what the JWT library does, so a token without `exp` is permanently valid
    until the user explicitly logs out (which clears the cookie/URL token)."""
    to_encode = data.copy()

    expire: Optional[datetime] = None
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif ACCESS_TOKEN_EXPIRE_MINUTES is not None:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    if expire is not None:
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

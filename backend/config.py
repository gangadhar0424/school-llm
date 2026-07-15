"""
Configuration management for School LLM
Loads environment variables and provides app settings
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load environment variables from .env file (in project root)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore"
    )

    # Local LLM (Ollama)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "800"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "60"))
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # ── Phase 3: LLM provider abstraction ────────────────────────────────
    # LLM_PROVIDER selects which backend the evaluator (and any other
    # LLM call routed through ai.llm_client) talks to.
    #   - "ollama"     → local Ollama (development default)
    #   - "anthropic"  → Claude API (production; needs ANTHROPIC_API_KEY)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    ANTHROPIC_MAX_TOKENS: int = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))
    # ── Multi-model config: different Claude tiers for different purposes.
    #    Each purpose has its own independent default so the legacy
    #    ANTHROPIC_MODEL setting doesn't accidentally pull generation down
    #    to a smaller model.
    #    Override individually via env vars to change a single tier.
    ANTHROPIC_GENERATION_MODEL: str = os.getenv(
        "ANTHROPIC_GENERATION_MODEL", "claude-sonnet-4-6"
    )
    ANTHROPIC_EVALUATION_MODEL: str = os.getenv(
        "ANTHROPIC_EVALUATION_MODEL", "claude-haiku-4-5-20251001"
    )
    ANTHROPIC_NAMING_MODEL: str = os.getenv(
        "ANTHROPIC_NAMING_MODEL", "claude-haiku-4-5-20251001"
    )

    # ── OpenRouter (3rd-party LLM gateway) — used optionally as an
    #    INDEPENDENT JUDGE model so the evaluator can be a bigger / different
    #    model from the one used for generation. Currently routes only the
    #    eval path (judge.py) — generation continues to follow LLM_PROVIDER.
    #    Free Nemotron 30B reasoning model is the default eval target.
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    OPENROUTER_EVAL_MODEL: str = os.getenv(
        "OPENROUTER_EVAL_MODEL",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    )
    # Enable Anthropic prompt caching on the static system prompt
    ANTHROPIC_PROMPT_CACHING: bool = os.getenv("ANTHROPIC_PROMPT_CACHING", "true").lower() == "true"

    # ── LLM provider fallback (graceful degradation) ──────────────────────
    # If the primary provider fails (timeout / network / API error), retry
    # the request on the other provider. Set to "false" to disable.
    LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "true").lower() == "true"
    # Seconds to skip a failed provider before retrying it again. Prevents
    # hammering a known-dead provider on every request.
    LLM_FALLBACK_COOLDOWN: int = int(os.getenv("LLM_FALLBACK_COOLDOWN", "60"))

    # ── Shared cache / coordination store ────────────────────────────────
    # When REDIS_URL is set (e.g. redis://localhost:6379/0) the cache and
    # rate-limit gate state can be shared across multiple worker processes /
    # instances. When empty, an in-process fallback is used (correct for a
    # single worker; gate/cache state is simply not shared across workers).
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    # AI answer/summary cache. Caches deterministic (no conversation history)
    # answers keyed by pdf + question so repeats are instant and free.
    AI_CACHE_ENABLED: bool = os.getenv("AI_CACHE_ENABLED", "true").lower() == "true"
    AI_CACHE_TTL: int = int(os.getenv("AI_CACHE_TTL", str(60 * 60 * 24)))  # 24h

    # ── Object storage (S3-compatible) for uploads / audio / video ───────
    # When STORAGE_BACKEND=s3, generated files and uploads are stored in an
    # S3-compatible bucket instead of local disk, so the app can run on more
    # than one machine. Defaults to local-disk (current behavior).
    STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local")  # local | s3
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")  # blank = AWS default
    S3_REGION: str = os.getenv("S3_REGION", "")
    S3_ACCESS_KEY_ID: str = os.getenv("S3_ACCESS_KEY_ID", "")
    S3_SECRET_ACCESS_KEY: str = os.getenv("S3_SECRET_ACCESS_KEY", "")
    S3_PUBLIC_BASE_URL: str = os.getenv("S3_PUBLIC_BASE_URL", "")  # CDN / public prefix

    # Embeddings Provider (sentence_transformers | ollama)
    EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "sentence_transformers")

    # Local Embeddings
    LOCAL_EMBEDDING_MODEL: str = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    # Database
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/school_llm")
    DATABASE_NAME: str = "school_llm"
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")
    # Local-JWT lifetime in minutes. Default 7 days. Set to 0 (or negative)
    # to issue non-expiring tokens (the old behavior). Only affects the
    # AUTH_PROVIDER=local path — eskoolia tokens are owned by the ERP.
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

    # ── Auth provider selection ──────────────────────────────────────────
    # This branch (eskoolia-LLM) is ERP-only. Default is "eskoolia" — the
    # eSkoolia ERP is the sole identity provider. Login forwards credentials
    # to the ERP, tokens are validated by calling GET /api/v1/auth/me/.
    # No signing secret is shared.
    # The "local" code path (Mongo + bcrypt) is retained for development
    # and test only; set AUTH_PROVIDER=local explicitly to use it. Never
    # use local in production on this branch.
    AUTH_PROVIDER: str = os.getenv("AUTH_PROVIDER", "eskoolia")
    ESKOOLIA_BASE_URL: str = os.getenv("ESKOOLIA_BASE_URL", "")
    # Cache the /me/ response per token for this many seconds so we don't
    # hit the ERP on every single request. Short enough that disabling a
    # school's LLM access propagates within ~1 minute.
    ESKOOLIA_ME_CACHE_TTL: int = int(os.getenv("ESKOOLIA_ME_CACHE_TTL", "60"))
    ESKOOLIA_HTTP_TIMEOUT: float = float(os.getenv("ESKOOLIA_HTTP_TIMEOUT", "10"))

    # ── Super admin (local-mode dev override) ────────────────────────────
    # Comma-separated emails. When AUTH_PROVIDER=local, any user whose
    # email matches one in this list is treated as a super admin
    # (role="super_admin", is_superuser=True) after authenticating against
    # the local users collection. In ERP mode this list is ignored — the
    # ERP's is_superuser flag is the source of truth.
    LOCAL_SUPER_ADMIN_EMAILS: str = os.getenv("LOCAL_SUPER_ADMIN_EMAILS", "")
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    
    # Audio (local TTS)
    AUDIO_VOICE: str = os.getenv("AUDIO_VOICE", "")
    AUDIO_RATE: int = int(os.getenv("AUDIO_RATE", "175"))

    # Upload guards — set MAX_PDF_UPLOAD_MB in .env to override the default
    # 50 MB cap. A 50 MB PDF is already a 200-page textbook chapter, so
    # this is generous for typical school content.
    MAX_PDF_UPLOAD_MB: int = int(os.getenv("MAX_PDF_UPLOAD_MB", "50"))
    
    # Runtime data root
    RUNTIME_DATA_DIR: str = str(Path(__file__).parent.parent / "runtime_data")

    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(Path(RUNTIME_DATA_DIR) / "chroma_db")
    # Optional shared Chroma server for multi-instance deploys. When
    # CHROMA_SERVER_HOST is set, the app connects to a standalone Chroma server
    # (HttpClient) so every instance shares one vector index instead of each
    # keeping its own local copy. Blank (default) = local PersistentClient.
    CHROMA_SERVER_HOST: str = os.getenv("CHROMA_SERVER_HOST", "")
    CHROMA_SERVER_PORT: int = int(os.getenv("CHROMA_SERVER_PORT", "8000"))

    # File Storage
    UPLOAD_DIR: str = str(Path(RUNTIME_DATA_DIR) / "uploads")
    AUDIO_DIR: str = str(Path(RUNTIME_DATA_DIR) / "generated_audio")
    VIDEO_DIR: str = str(Path(RUNTIME_DATA_DIR) / "generated_videos")
    
    # PDF Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Quiz Settings
    DEFAULT_QUIZ_QUESTIONS: int = 3
    
# Initialize settings
settings = Settings()

# Create necessary directories
for directory in [settings.RUNTIME_DATA_DIR, settings.UPLOAD_DIR, settings.AUDIO_DIR, settings.VIDEO_DIR, settings.CHROMA_PERSIST_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)

# Production-blocker sentinel: the literal default that ships in the
# repo. Tokens signed with this value are forgeable by anyone reading
# this file on GitHub, so a deployment that leaves it as the default is
# functionally unauthenticated.
_JWT_PLACEHOLDER = "your-secret-key-change-this-in-production"


# Validate required API keys
def validate_config():
    """Validate that required configuration is present.

    Returns ``False`` (caller decides whether to exit) when any blocker
    is present. Soft warnings (e.g. missing CORS_ORIGINS for production)
    are logged but don't fail validation — production should never run
    with the placeholder JWT or a localhost Mongo URI."""
    errors: list[str] = []
    warnings: list[str] = []

    if not settings.MONGODB_URI:
        errors.append("MONGODB_URI is not set")

    # JWT secret: if running production, the placeholder is a fatal
    # security issue. We treat any deployment outside obvious dev
    # (localhost MongoDB) as production.
    is_dev_mongo = "localhost" in (settings.MONGODB_URI or "") or "127.0.0.1" in (settings.MONGODB_URI or "")
    if settings.JWT_SECRET_KEY == _JWT_PLACEHOLDER:
        msg = (
            "JWT_SECRET_KEY is the public placeholder value. "
            "Set JWT_SECRET_KEY in .env to a 32+ char random string. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
        if is_dev_mongo:
            warnings.append(msg + "  [dev MongoDB detected — allowed for now]")
        else:
            errors.append(msg)
    elif len(settings.JWT_SECRET_KEY) < 16:
        warnings.append(
            f"JWT_SECRET_KEY is short ({len(settings.JWT_SECRET_KEY)} chars). "
            "Use 32+ characters of randomness for production."
        )

    # Ollama URL: warn if pointing at localhost in what looks like prod.
    if "localhost" in (settings.OLLAMA_BASE_URL or "") or "127.0.0.1" in (settings.OLLAMA_BASE_URL or ""):
        if not is_dev_mongo:
            warnings.append(
                f"OLLAMA_BASE_URL points at {settings.OLLAMA_BASE_URL} — "
                "production should point at the Ollama VPS, not localhost."
            )

    # CORS origins on a production-shaped deploy must be explicit.
    if not is_dev_mongo and (settings.CORS_ORIGINS or "*") == "*":
        warnings.append(
            "CORS_ORIGINS is '*' — set it to your real frontend domain(s) "
            "(comma-separated) in .env. Wildcard breaks cookie-based auth."
        )

    if warnings:
        print("\n  Configuration warnings:")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        print("\n  Configuration errors (deployment will NOT start):")
        for error in errors:
            print(f"  - {error}")
        print()
        return False
    return True

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

    # Embeddings Provider (sentence_transformers | ollama)
    EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "sentence_transformers")

    # Local Embeddings
    LOCAL_EMBEDDING_MODEL: str = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    # Database
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/school_llm")
    DATABASE_NAME: str = "school_llm"
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-this-in-production")

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
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    
    # Audio (local TTS)
    AUDIO_VOICE: str = os.getenv("AUDIO_VOICE", "")
    AUDIO_RATE: int = int(os.getenv("AUDIO_RATE", "175"))
    
    # Runtime data root
    RUNTIME_DATA_DIR: str = str(Path(__file__).parent.parent / "runtime_data")

    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(Path(RUNTIME_DATA_DIR) / "chroma_db")

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

# Validate required API keys
def validate_config():
    """Validate that required configuration is present"""
    errors = []

    if not settings.MONGODB_URI:
        errors.append("MONGODB_URI is not set in .env file")
    
    if errors:
        print("\n  Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        print("\n Please update your .env file with the required API keys.\n")
        return False
    
    return True

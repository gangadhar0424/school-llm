"""
Configuration management for School LLM
Loads environment variables and provides app settings
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env file (in project root)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Local LLM (Ollama)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b")
    OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.3"))
    OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "800"))
    OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "60"))
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    # Embeddings Provider (sentence_transformers | ollama)
    EMBEDDINGS_PROVIDER: str = os.getenv("EMBEDDINGS_PROVIDER", "sentence_transformers")

    # Local Embeddings
    LOCAL_EMBEDDING_MODEL: str = os.getenv("LOCAL_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    
    # Database
    MONGODB_URI: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017/school_llm")
    DATABASE_NAME: str = "school_llm"
    
    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # CORS
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "*")
    
    # Audio (local TTS)
    AUDIO_VOICE: str = os.getenv("AUDIO_VOICE", "")
    AUDIO_RATE: int = int(os.getenv("AUDIO_RATE", "175"))
    
    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(Path(__file__).parent.parent / "chroma_db")
    
    # File Storage
    UPLOAD_DIR: str = str(Path(__file__).parent.parent / "uploads")
    AUDIO_DIR: str = str(Path(__file__).parent.parent / "generated_audio")
    VIDEO_DIR: str = str(Path(__file__).parent.parent / "generated_videos")
    
    # PDF Processing
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    
    # Quiz Settings
    DEFAULT_QUIZ_QUESTIONS: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Initialize settings
settings = Settings()

# Create necessary directories
for directory in [settings.UPLOAD_DIR, settings.AUDIO_DIR, settings.VIDEO_DIR, settings.CHROMA_PERSIST_DIR]:
    Path(directory).mkdir(parents=True, exist_ok=True)

# Validate required API keys
def validate_config():
    """Validate that required configuration is present"""
    errors = []

    if not settings.MONGODB_URI:
        errors.append("MONGODB_URI is not set in .env file")
    
    if errors:
        print("\n⚠️  Configuration Errors:")
        for error in errors:
            print(f"  - {error}")
        print("\n📝 Please update your .env file with the required API keys.\n")
        return False
    
    return True

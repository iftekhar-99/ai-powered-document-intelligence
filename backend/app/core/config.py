from pathlib import Path
from typing import List, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ROOT_ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    # Application Info
    APP_ENV: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "Financial Document Intelligence System"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "development-secret-key-change-in-production"

    # Server & Networking
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    ALLOWED_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "doc_intel"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/doc_intel"
    DATABASE_URL_SYNC: str = "postgresql://postgres:postgres@localhost:5432/doc_intel"
    USE_SQLITE_FALLBACK: bool = True
    SQLITE_DB_PATH: str = "./doc_intel.db"

    # Redis & Background Tasks
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Background Processing Mode (inline for local dev, celery for distributed queue)
    PROCESSING_MODE: str = "inline"

    # Storage & Document Processing
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    TESSERACT_CMD: str = "tesseract"
    OCR_LANGUAGE: str = "eng"
    OCR_TIMEOUT_SECONDS: int = 30
    PDF_OCR_DPI: int = 300
    PDF_MIN_TEXT_CHARS_PER_PAGE: int = 50
    SPREADSHEET_CHUNK_ROW_SIZE: int = 50
    INCLUDE_HIDDEN_SHEETS: bool = True
    MAX_IMAGE_PIXELS: int = 100_000_000

    # AI & LLM Configuration
    LLM_ENABLED: bool = True
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # Validation Engine Configuration
    VALIDATION_ENABLED: bool = True
    VALIDATION_ROUNDING_TOLERANCE: float = 0.01

    # Gemini Configuration
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-lite-latest"
    GOOGLE_GENAI_API_VERSION: str = "v1beta"
    GEMINI_EMBEDDING_MODEL: str = "gemini-embedding-2"

    # LLM Operational Parameters
    LLM_TIMEOUT_SECONDS: Union[int, float] = 120.0
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_INPUT_CHARS: int = 30000
    LLM_MAX_OUTPUT_TOKENS: int = 8000
    EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.75

    # Embeddings (Configurable)
    EMBEDDING_PROVIDER: str = "gemini"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EMBEDDING_DIMENSION: int = 768

    model_config = SettingsConfigDict(
        env_file=(str(ROOT_ENV_FILE), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()

"""应用配置管理"""
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = f"sqlite:///{(BACKEND_DIR / 'tutor.db').as_posix()}"


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    
    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 2000
    DEFAULT_LLM_PROVIDER: str = "auto"

    # OpenAI-compatible chat providers
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    QWEN_API_KEY: Optional[str] = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    LINKAPI_API_KEY: Optional[str] = None
    LINKAPI_BASE_URL: str = "https://api.linkapi.ai/v1"
    LINKAPI_MODEL: str = "claude-sonnet-4-20250514"

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.1"

    # Per-user LLM credentials
    LLM_CREDENTIAL_ENCRYPTION_KEY: Optional[str] = None
    LLM_CREDENTIAL_PREVIOUS_KEYS: str = ""
    LLM_FINGERPRINT_HMAC_KEY: Optional[str] = None
    ALLOW_GLOBAL_LLM_FALLBACK: bool = True

    # Native provider placeholders for the next adapter iteration
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-1.5-pro"
    
    # 应用
    DEBUG: bool = True
    DB_AUTO_CREATE: Optional[bool] = None
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = [
        "http://localhost:4173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:5173",
    ]
    MAX_UPLOAD_SIZE_MB: int = 25

    # Auth
    JWT_SECRET: str = "dev-only-change-me-dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 900
    REFRESH_TOKEN_TTL_SECONDS: int = 60 * 60 * 24 * 30
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 128
    COOKIE_REFRESH_NAME: str = "refresh_token"
    COOKIE_REFRESH_PATH: str = "/api/auth"
    COOKIE_SAMESITE: str = "lax"
    COOKIE_SECURE: bool = False
    
    # 番茄钟
    DEFAULT_POMODORO_DURATION: int = 25  # 分钟
    DEFAULT_BREAK_DURATION: int = 5      # 分钟
    
    # 训练引擎
    MAX_CONSECUTIVE_ERRORS: int = 3       # 连续错几题降难度
    MAX_CONSECUTIVE_CORRECT: int = 3      # 连续对几题升难度

    # RAG / 学习资料
    RAG_UPLOAD_DIR: str = "storage/materials"
    RAG_CHUNK_SIZE: int = 1200
    RAG_CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_SEARCH_CANDIDATE_LIMIT: int = 500
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_HASH_EMBEDDING_DIMENSIONS: int = 128
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


"""应用配置管理"""

import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = "postgresql+psycopg://tutor:tutor@localhost:55432/tutor"
logger = logging.getLogger(__name__)
_warned_ephemeral_jwt_secret = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")
    """应用配置"""

    # 数据库
    DATABASE_URL: str = DEFAULT_DATABASE_URL

    # OpenAI
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_TEMPERATURE: float = 0.7
    OPENAI_MAX_TOKENS: int = 2000
    LLM_UNSUPPORTED_CHAT_PARAMS_BY_MODEL: str = "gpt-5*:temperature"
    DEFAULT_LLM_PROVIDER: str = "auto"
    BKT_INITIAL_KNOWLEDGE: float = 0.25
    BKT_LEARN_RATE: float = 0.12
    BKT_SLIP_RATE: float = 0.1
    BKT_GUESS_RATE: float = 0.2
    BKT_MIN_HALF_LIFE_DAYS: float = 3.0
    BKT_MAX_HALF_LIFE_DAYS: float = 45.0
    REVIEW_MASTERY_THRESHOLD: float = 0.55
    WEB_SEARCH_PROVIDER: str = "tavily"
    WEB_SEARCH_API_KEY: str | None = None
    WEB_SEARCH_PROXY: str | None = None
    WEB_SEARCH_MAX_RESULTS: int = 3
    WEB_SEARCH_TIMEOUT: float = 8.0
    RAG_MIN_SCORE: float = 0.35
    RAG_MATERIAL_MIN_SCORE: float = 0.35
    AGENT_TOOL_CALLING_ENABLED: bool = True
    MAX_TOOL_ITERATIONS: int = 4

    # OpenAI-compatible chat providers
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    LINKAPI_API_KEY: str | None = None
    LINKAPI_BASE_URL: str = "https://api.linkapi.ai/v1"
    LINKAPI_MODEL: str = "claude-sonnet-4-20250514"

    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "llama3.1"

    # Per-user LLM credentials
    LLM_CREDENTIAL_ENCRYPTION_KEY: str | None = None
    LLM_CREDENTIAL_PREVIOUS_KEYS: str = ""
    LLM_FINGERPRINT_HMAC_KEY: str | None = None
    ALLOW_GLOBAL_LLM_FALLBACK: bool = False

    # Native provider placeholders for the next adapter iteration
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    GEMINI_API_KEY: str | None = None
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # 应用
    DEBUG: bool = True
    DB_AUTO_CREATE: bool | None = None
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = [
        "http://localhost:4173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://127.0.0.1:5173",
    ]
    MAX_UPLOAD_SIZE_MB: int = 25

    # Auth
    JWT_SECRET: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_TTL_SECONDS: int = 900
    REFRESH_TOKEN_TTL_SECONDS: int = 60 * 60 * 24 * 30
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 128
    COOKIE_REFRESH_NAME: str = "refresh_token"
    COOKIE_REFRESH_PATH: str = "/api/auth"
    COOKIE_SAMESITE: str = "strict"
    COOKIE_SECURE: bool | None = None
    E2E_MOCK_LLM: bool = False

    # 番茄钟
    DEFAULT_POMODORO_DURATION: int = 25  # 分钟
    DEFAULT_BREAK_DURATION: int = 5  # 分钟

    # 训练引擎
    MAX_CONSECUTIVE_ERRORS: int = 3  # 连续错几题降难度
    MAX_CONSECUTIVE_CORRECT: int = 3  # 连续对几题升难度

    # RAG / 学习资料
    RAG_UPLOAD_DIR: str = "storage/materials"
    RAG_CHUNK_SIZE: int = 1200
    RAG_CHUNK_OVERLAP: int = 150
    RAG_TOP_K: int = 5
    RAG_SEARCH_CANDIDATE_LIMIT: int = 500
    RAG_VECTOR_DIM: int = 1536
    RAG_HNSW_EF_SEARCH: int = 40
    # Embedding provider: "openai" (production, requires RAG_EMBEDDING_API_KEY)
    # or "hash" (deterministic local vectors for tests/CI, no API calls).
    RAG_EMBEDDING_MODE: str = "openai"
    RAG_EMBEDDING_API_KEY: str | None = None
    RAG_EMBEDDING_BASE_URL: str = "https://api.openai.com/v1"
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_HASH_EMBEDDING_DIMENSIONS: int | None = None

    def model_post_init(self, __context: object) -> None:
        global _warned_ephemeral_jwt_secret
        if self.JWT_SECRET:
            return
        if not self.DEBUG:
            raise RuntimeError("JWT_SECRET must be set in production")
        self.JWT_SECRET = secrets.token_urlsafe(48)
        if not _warned_ephemeral_jwt_secret:
            logger.warning("JWT_SECRET is unset in DEBUG mode; generated an ephemeral in-memory secret")
            _warned_ephemeral_jwt_secret = True


settings = Settings()

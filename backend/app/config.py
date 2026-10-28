"""All settings come from environment variables. Nothing secret lives in code."""

import os
from dataclasses import dataclass, field

# Base URL and default model for each LLM provider.
# groq, gemini and openai all speak the OpenAI chat format, so they share one code path.
PROVIDERS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.8-flash"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-sonnet-5-5"),
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int
    llm_provider: str
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    openai_api_key: str  # only needed when EMBEDDING_PROVIDER=openai
    embedding_provider: str  # "hash" (offline, free) or "openai"
    min_similarity: float  # below this score we refuse to answer
    llm_timeout_seconds: float  # read timeout for one LLM call
    demo_mode: bool  # allows POST /auth/demo, which creates a sandbox workspace
    cors_origins: list[str] = field(default_factory=list)
    cors_origin_regex: str | None = None

    @property
    def embedding_dim(self) -> int:
        # The vector column size must match the embedding model.
        return 1536 if self.embedding_provider == "openai" else 384

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key)


def _api_key(provider: str) -> str:
    # LLM_API_KEY works for every provider. The provider-specific names still work too.
    fallback = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
                "groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}.get(provider, "")
    return os.getenv("LLM_API_KEY") or os.getenv(fallback, "")


def load_settings() -> Settings:
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    default_url, default_model = PROVIDERS.get(provider, ("", ""))
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./workos.db"),
        jwt_secret=os.getenv("JWT_SECRET", "change-me-in-production"),
        jwt_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "720")),
        llm_provider=provider,
        llm_model=os.getenv("LLM_MODEL") or default_model,
        llm_base_url=(os.getenv("LLM_BASE_URL") or default_url).rstrip("/"),
        llm_api_key=_api_key(provider),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "hash"),
        min_similarity=float(os.getenv("MIN_SIMILARITY", "0.15")),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "90")),
        demo_mode=os.getenv("DEMO_MODE", "true").lower() in ("1", "true", "yes"),
        cors_origins=[o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
        cors_origin_regex=os.getenv("CORS_ORIGIN_REGEX") or None,
    )


settings = load_settings()

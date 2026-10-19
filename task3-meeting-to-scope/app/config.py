import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    knowledge_url: str = field(default_factory=lambda: os.getenv("KNOWLEDGE_URL", "http://localhost:8001"))
    knowledge_key: str | None = field(default_factory=lambda: os.getenv("KB_API_KEY"))
    fast_model: str = field(default_factory=lambda: os.getenv("FAST_MODEL", "claude-haiku-5-5"))
    main_model: str = field(default_factory=lambda: os.getenv("MAIN_MODEL", "claude-sonnet-5-5"))
    prompt_version: str = field(default_factory=lambda: os.getenv("PROMPT_VERSION", "v1"))
    db_path: str = field(default_factory=lambda: os.getenv("SCOPE_DB", "data/projects.json"))
    hourly_rate: float = field(default_factory=lambda: float(os.getenv("HOURLY_RATE", "0")))   # 0 = no price shown
    currency: str = field(default_factory=lambda: os.getenv("CURRENCY", "USD"))
    chunk_chars: int = 6000

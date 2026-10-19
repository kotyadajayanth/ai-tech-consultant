"""All settings come from environment variables (see ../.env.example)."""
import os
from dataclasses import dataclass, field


def _f(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    sitemap_url: str = field(default_factory=lambda: _f("SITEMAP_URL", "https://support.brilliantdirectories.com/support/sitemap.xml"))
    db_path: str = field(default_factory=lambda: _f("KB_DB_PATH", "data/kb.sqlite3"))
    user_agent: str = field(default_factory=lambda: _f("CRAWLER_UA", "ai-tech-consultant-bot/0.1 (student capstone)"))
    max_concurrency: int = field(default_factory=lambda: int(_f("CRAWL_CONCURRENCY", "2")))
    delay_s: float = field(default_factory=lambda: float(_f("CRAWL_DELAY_S", "1.0")))
    max_retries: int = field(default_factory=lambda: int(_f("CRAWL_MAX_RETRIES", "3")))
    max_total_attempts: int = 5  # a page that keeps failing across runs is parked, not retried forever
    answer_model: str = field(default_factory=lambda: _f("ANSWER_MODEL", "claude-sonnet-5-5"))
    vision_model: str = field(default_factory=lambda: _f("VISION_MODEL", "claude-haiku-5-5"))
    embedder: str = field(default_factory=lambda: _f("EMBEDDER", "hash"))
    min_score: float = field(default_factory=lambda: float(_f("MIN_RETRIEVAL_SCORE", "0.12")))
    api_key: str | None = field(default_factory=lambda: os.getenv("KB_API_KEY"))
    ingest_interval_hours: float = field(default_factory=lambda: float(_f("INGEST_INTERVAL_HOURS", "24")))
    enable_scheduler: bool = field(default_factory=lambda: _f("ENABLE_SCHEDULER", "0") == "1")
    enable_vision: bool = field(default_factory=lambda: _f("ENABLE_VISION", "1") == "1")

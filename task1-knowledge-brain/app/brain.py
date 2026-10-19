"""Holds settings + embedder + LLM so everything else can be tested with fakes."""
from dataclasses import dataclass, field

from .config import Settings
from .db import connect
from .embeddings import get_embedder


@dataclass
class Brain:
    settings: Settings
    llm: object | None = None
    embedder: object = field(default=None)
    last_report: dict | None = None

    def __post_init__(self) -> None:
        if self.embedder is None:
            self.embedder = get_embedder(self.settings.embedder)

    def conn(self):
        return connect(self.settings.db_path)

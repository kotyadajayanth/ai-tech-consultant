import pytest

from app.config import Settings
from app.kb_client import KnowledgeUnavailable
from app.llm import JsonResult
from app.projects import ProjectStore


class FakeLLM:
    """Routes by agent role. replies[role] is a queue (or a single dict used every time)."""
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    async def complete_json(self, *, role, system, user, model, max_tokens=3000):
        self.calls.append(role)
        r = self.replies[role]
        data = r.pop(0) if isinstance(r, list) else r
        return JsonResult(data, 10, 5, 0.01)


class FakeKB:
    def __init__(self, by_keyword, down=False):
        self.by_keyword, self.down = by_keyword, down

    async def query(self, question, context=""):
        if self.down:
            raise KnowledgeUnavailable("down")
        for k, v in self.by_keyword.items():
            if k in question.lower():
                return v
        return {"status": "insufficient_evidence", "answer": "", "sources": [], "needs_human": True}


ANSWERED = {"status": "answered", "answer": "Search filters are available in Settings > Search.", "sources": [{"url": "https://kb/filters", "title": "Filters"}]}

MEETING_A = """Client: Our search is not great. We want customers to find products faster, with filters.
Consultant: Which filters?
Client: Price and category. And the site must work better on mobile.
Client: We need it by 30 November."""

MEETING_C = """Client: Update on last time: forget the mobile work, we are redoing the app next year.
Client: But please add a wishlist feature. And now we need it by 15 December."""


@pytest.fixture
def settings():
    return Settings(hourly_rate=50.0, db_path="")


@pytest.fixture
def store():
    return ProjectStore(None)

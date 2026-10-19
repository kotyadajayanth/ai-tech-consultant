import httpx


class KnowledgeUnavailable(Exception):
    pass


class KnowledgeClient:
    """Calls Task 1 over HTTP only. No imports from Task 1."""
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 30.0):
        self.base, self.key, self.timeout = base_url.rstrip("/"), api_key, timeout

    async def query(self, question: str, context: str = "") -> dict:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(f"{self.base}/query", json={"question": question, "context": context, "escalate": True},
                                 headers={"x-api-key": self.key} if self.key else {})
        except httpx.HTTPError as e:
            raise KnowledgeUnavailable(f"knowledge service unreachable: {type(e).__name__}")
        if r.status_code != 200:
            raise KnowledgeUnavailable(f"knowledge service returned HTTP {r.status_code}")
        return r.json()

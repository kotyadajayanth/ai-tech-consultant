import pytest

from app.brain import Brain
from app.config import Settings
from app.llm import JsonResult


class FakeLLM:
    """Scripted model: returns what the test queues. No network."""
    def __init__(self):
        self.replies, self.calls = [], 0

    async def complete_json(self, *, system, user, model, max_tokens=1000):
        self.calls += 1
        return JsonResult(self.replies.pop(0), 10, 5, 0.01, model)

    async def describe_image(self, **kw):
        return "Screenshot shows a Save Logo button."


@pytest.fixture
def brain(tmp_path):
    return Brain(Settings(db_path=str(tmp_path / "kb.sqlite3"), delay_s=0, max_retries=1), llm=FakeLLM())


SITEMAP = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://h.test/a1</loc><lastmod>2026-01-01</lastmod></url>
<url><loc>https://h.test/a2</loc><lastmod>2026-01-01</lastmod></url>
<url><loc>https://h.test/a2</loc><lastmod>2026-01-01</lastmod></url>
<url><loc>not-a-url</loc></url></urlset>"""

ART = """<html><body><nav>MENU</nav><article><h1>Change your logo</h1>
<p>Open Design Settings.</p><h2>Upload steps</h2><ol><li>Click Logo.</li><li>Choose a file and press Save Logo.</li></ol>
<img src="/img/logo.png" alt="logo screen"><table><tr><th>Format</th><th>Max size</th></tr><tr><td>PNG</td><td>2MB</td></tr></table>
</article><footer>FOOTER</footer></body></html>"""

REFUND = "<html><body><article><h1>Refund policy</h1><p>Refunds are processed within 5 business days.</p></article></body></html>"


class FakeFetcher:
    def __init__(self, pages: dict[str, tuple[int, bytes]], sitemap: str):
        self.pages, self.sitemap, self.hits = pages, sitemap, {}

    async def get(self, url):
        self.hits[url] = self.hits.get(url, 0) + 1
        if url.endswith("sitemap.xml"):
            return 200, self.sitemap.encode(), "application/xml"
        if url.endswith(".png"):
            return 200, b"\x89PNG", "image/png"
        code, body = self.pages.get(url, (404, b""))
        if isinstance(body, Exception):
            raise body
        return code, body, "text/html"

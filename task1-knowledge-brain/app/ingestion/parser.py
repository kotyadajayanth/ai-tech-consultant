"""HTML -> clean Article. Selectors are generic on purpose: TUNE THEM against the real help-center
HTML (open one article, inspect the main container) and note the change in AI_LOG/DESIGN."""
import hashlib
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

NOISE = ["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe"]


@dataclass
class ImageRef:
    url: str
    alt: str = ""
    context: str = ""  # text just before the image


@dataclass
class Section:
    heading: str
    blocks: list[str] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)


@dataclass
class Article:
    url: str
    title: str
    sections: list[Section]
    content_hash: str


def _clean(s: str) -> str:
    return " ".join(s.split())


def parse_article(url: str, html: str) -> Article:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(NOISE):
        t.decompose()
    h1 = soup.find("h1")
    title = _clean(h1.get_text()) if h1 else _clean(soup.title.get_text()) if soup.title else url
    main = soup.select_one("article") or soup.select_one("main") or soup.select_one("#content") or soup.body or soup
    sections = [Section(heading=title)]
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "table", "img"]):
        if el.name == "img":
            src = el.get("data-src") or el.get("src") or ""
            if not src or src.startswith("data:"):
                continue
            w = el.get("width", "")
            if w.isdigit() and int(w) < 50:
                continue  # icon, not a screenshot
            prev = sections[-1].blocks[-1] if sections[-1].blocks else ""
            sections[-1].images.append(ImageRef(urljoin(url, src), _clean(el.get("alt", "")), prev[-200:]))
        elif el.name in ("h1", "h2", "h3", "h4"):
            text = _clean(el.get_text())
            if text and not (el.name == "h1" and text == title):
                sections.append(Section(heading=text))
        elif el.name in ("p", "li", "pre") and not el.find_parent(["table"]):
            if el.name != "li" and el.find_parent(["li"]):
                continue  # already inside a list item
            text = _clean(el.get_text(" "))
            if text:
                sections[-1].blocks.append(("- " if el.name == "li" else "") + text)
        elif el.name == "table":
            rows = [" | ".join(_clean(c.get_text()) for c in tr.find_all(["th", "td"])) for tr in el.find_all("tr")]
            if rows:
                sections[-1].blocks.append("\n".join(rows))  # one block: header stays with its rows
    sections = [s for s in sections if s.blocks or s.images]
    sig = title + "\n".join(b for s in sections for b in s.blocks) + "".join(i.url for s in sections for i in s.images)
    return Article(url, title, sections, hashlib.sha256(sig.encode()).hexdigest())

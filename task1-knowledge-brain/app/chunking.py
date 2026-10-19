"""Split an Article at headings first, then pack paragraphs up to max_chars."""
from dataclasses import dataclass, field

from .ingestion.parser import Article


@dataclass
class Chunk:
    heading: str
    text: str
    image_urls: list[str] = field(default_factory=list)


def chunk_article(a: Article, max_chars: int = 1200) -> list[Chunk]:
    out: list[Chunk] = []
    for s in a.sections:
        head = f"{a.title} > {s.heading}\n"
        cur: list[str] = []
        size = 0
        for block in s.blocks:
            pieces = [block[i:i + max_chars] for i in range(0, len(block), max_chars)] or [block]
            for p in pieces:
                if cur and size + len(p) > max_chars:
                    out.append(Chunk(s.heading, head + "\n".join(cur)))
                    last = cur[-1]
                    cur = [last] if len(last) < 300 else []  # small overlap: keep the lead-in line
                    size = sum(len(x) for x in cur)
                cur.append(p)
                size += len(p)
        if cur:
            out.append(Chunk(s.heading, head + "\n".join(cur)))
    return out

"""Parse sitemap XML and compare it with what we already stored."""
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: str | None = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(xml_text: str) -> tuple[list[SitemapEntry], list[str]]:
    """Returns (page entries, child sitemap urls). Handles <urlset> and <sitemapindex>."""
    root = ET.fromstring(xml_text)
    pages: dict[str, SitemapEntry] = {}
    children: list[str] = []
    for node in root:
        loc = lastmod = None
        for f in node:
            if _local(f.tag) == "loc" and f.text:
                loc = f.text.strip()
            elif _local(f.tag) == "lastmod" and f.text:
                lastmod = f.text.strip()
        if not loc or not re.match(r"^https?://", loc):
            continue  # validate: skip junk
        if _local(root.tag) == "sitemapindex":
            children.append(loc)
        else:
            pages[loc] = SitemapEntry(loc, lastmod)  # dict => duplicates removed
    return list(pages.values()), children


@dataclass
class Diff:
    new: list[SitemapEntry]
    changed: list[SitemapEntry]
    unchanged: list[SitemapEntry]
    removed: list[str]


def diff_manifest(current: list[SitemapEntry], stored: dict[str, dict]) -> Diff:
    """stored: url -> {lastmod, status}. A page is 'changed' if its lastmod moved."""
    d = Diff([], [], [], [])
    seen = set()
    for e in current:
        seen.add(e.url)
        row = stored.get(e.url)
        if row is None or row["status"] == "removed":
            d.new.append(e)
        elif row["lastmod"] != e.lastmod:
            d.changed.append(e)
        else:
            d.unchanged.append(e)
    d.removed = [u for u, r in stored.items() if u not in seen and r["status"] != "removed"]
    return d

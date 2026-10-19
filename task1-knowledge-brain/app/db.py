"""SQLite storage. One small file, no server to run. See DESIGN.md for why not pgvector."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages(
  url TEXT PRIMARY KEY, lastmod TEXT, content_hash TEXT,
  status TEXT NOT NULL DEFAULT 'pending',      -- pending | ok | failed | removed
  attempts INTEGER NOT NULL DEFAULT 0, error TEXT, title TEXT, ingested_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, idx INTEGER NOT NULL,
  kind TEXT NOT NULL,                           -- text | image | expert
  title TEXT, heading TEXT, text TEXT NOT NULL, image_url TEXT,
  embedding BLOB, active INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS chunks_url ON chunks(url);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, chunk_id UNINDEXED);
CREATE TABLE IF NOT EXISTS image_cache(
  image_url TEXT PRIMARY KEY, description TEXT NOT NULL, model TEXT);
CREATE TABLE IF NOT EXISTS escalations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT NOT NULL, evidence TEXT, reason TEXT,
  status TEXT NOT NULL DEFAULT 'open',          -- open | resolved
  answer TEXT, approved INTEGER, expert TEXT, version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT);
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn

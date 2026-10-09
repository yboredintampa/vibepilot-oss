# dedupe_store.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Tuple, Optional, List
import time
import difflib

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
DB_PATH = POSTS / "dedupe.sqlite"
POSTS.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS captions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS prompts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL UNIQUE,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE TABLE IF NOT EXISTS posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  caption_id INTEGER,
  prompt_id INTEGER,
  image_path TEXT,
  fb_post_id TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def _ensure_schema() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)

_ensure_schema()

def _recent_texts(table: str, limit: int = 300) -> List[str]:
    with _conn() as c:
        cur = c.execute(f"SELECT text FROM {table} ORDER BY id DESC LIMIT ?", (limit,))
        return [r[0] for r in cur.fetchall()]

def _is_duplicate_text(text: str, table: str, sim_threshold: float = 0.92) -> Tuple[bool, Optional[str]]:
    """True if text exactly matches or is very similar to recent entries."""
    txt = (text or "").strip()
    if not txt:
        return False, None
    # Exact
    with _conn() as c:
        cur = c.execute(f"SELECT text FROM {table} WHERE text = ?", (txt,))
        row = cur.fetchone()
        if row:
            return True, row[0]
    # Fuzzy (against recent)
    for prev in _recent_texts(table, limit=400):
        if prev == txt:
            return True, prev
        r = difflib.SequenceMatcher(None, prev.lower(), txt.lower()).ratio()
        if r >= sim_threshold:
            return True, prev
    return False, None

def is_duplicate_caption(text: str, sim_threshold: float = 0.92) -> Tuple[bool, Optional[str]]:
    return _is_duplicate_text(text, "captions", sim_threshold)

def is_duplicate_prompt(text: str, sim_threshold: float = 0.92) -> Tuple[bool, Optional[str]]:
    return _is_duplicate_text(text, "prompts", sim_threshold)

def save_caption(text: str) -> int:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO captions(text, created_at) VALUES(?,?)", (text.strip(), int(time.time())))
        c.commit()
        cur = c.execute("SELECT id FROM captions WHERE text = ?", (text.strip(),))
        return int(cur.fetchone()[0])

def save_prompt(text: str) -> int:
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO prompts(text, created_at) VALUES(?,?)", (text.strip(), int(time.time())))
        c.commit()
        cur = c.execute("SELECT id FROM prompts WHERE text = ?", (text.strip(),))
        return int(cur.fetchone()[0])

def save_post(caption_text: str, prompt_text: str, image_path: str, fb_post_id: Optional[str]) -> int:
    cap_id = save_caption(caption_text)
    prm_id = save_prompt(prompt_text)
    with _conn() as c:
        c.execute(
            "INSERT INTO posts(caption_id, prompt_id, image_path, fb_post_id, created_at) VALUES(?,?,?,?,?)",
            (cap_id, prm_id, image_path, fb_post_id or "", int(time.time())),
        )
        c.commit()
        return int(c.execute("SELECT last_insert_rowid()").fetchone()[0])

def is_duplicate_opening(text: str, word_count: int = 8) -> Tuple[bool, Optional[str]]:
    """Check if opening phrase (first N words) is too similar to recent captions."""
    txt = (text or "").strip()
    if not txt:
        return False, None
    
    # Get first N words
    words = txt.split()[:word_count]
    opening = " ".join(words).lower()
    
    # Check against recent captions
    for prev in _recent_texts("captions", limit=100):
        prev_opening = " ".join(prev.split()[:word_count]).lower()
        if opening == prev_opening:
            return True, prev
        # Check similarity
        r = difflib.SequenceMatcher(None, prev_opening, opening).ratio()
        if r >= 0.90:  # Stricter for openings
            return True, prev
    
    return False, None

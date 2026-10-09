# dedupe.py
import sqlite3, hashlib, pathlib, time
DB = pathlib.Path("posts/dedupe.sqlite")
DB.parent.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  kind TEXT NOT NULL,          -- 'caption' | 'prompt'
  hash TEXT NOT NULL PRIMARY KEY,
  first_ts INTEGER NOT NULL,
  last_ts  INTEGER NOT NULL,
  samples  INTEGER NOT NULL
);
"""

def _h(txt: str) -> str:
    norm = " ".join(txt.lower().split())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()

def _conn():
    DB.touch(exist_ok=True)
    con = sqlite3.connect(DB)
    con.execute(_SCHEMA)
    return con

def seen(kind: str, text: str) -> bool:
    with _conn() as con:
        cur = con.execute("SELECT 1 FROM items WHERE kind=? AND hash=?", (kind, _h(text)))
        return cur.fetchone() is not None

def mark(kind: str, text: str) -> None:
    now = int(time.time())
    with _conn() as con:
        h = _h(text)
        cur = con.execute("SELECT samples FROM items WHERE kind=? AND hash=?", (kind, h)).fetchone()
        if cur:
            con.execute("UPDATE items SET last_ts=?, samples=samples+1 WHERE kind=? AND hash=?", (now, kind, h))
        else:
            con.execute("INSERT INTO items(kind,hash,first_ts,last_ts,samples) VALUES(?,?,?,?,1)", (kind, h, now, now))

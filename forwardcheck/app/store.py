"""SQLite: claim-result cache, per-user language preference and usage stats."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

from .config import settings

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(settings.db_path, check_same_thread=False)
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, payload TEXT, created_at REAL);
            CREATE TABLE IF NOT EXISTS prefs(user TEXT PRIMARY KEY, lang TEXT);
            CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY AUTOINCREMENT, created_at REAL,
                input_type TEXT, language TEXT, claims INTEGER, labels TEXT, elapsed_ms INTEGER);
        """)
    return _conn


def reset_for_tests(path: str) -> None:
    global _conn
    if _conn:
        _conn.close()
    _conn = None
    settings.db_path = path


def cache_key(text_en: str, lang: str) -> str:
    norm = re.sub(r"\W+", " ", text_en.lower()).strip()
    return hashlib.sha256(f"{lang}|{norm}".encode()).hexdigest()


def cache_get(key: str, time_sensitive: bool) -> dict | None:
    ttl = settings.cache_ttl_time_sensitive_seconds if time_sensitive else settings.cache_ttl_seconds
    with _lock:
        row = _db().execute("SELECT payload, created_at FROM cache WHERE key=?", (key,)).fetchone()
    if row and time.time() - row[1] < ttl:
        return json.loads(row[0])
    return None


def cache_put(key: str, payload: dict) -> None:
    with _lock:
        c = _db()
        c.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, json.dumps(payload, ensure_ascii=False), time.time()))
        c.commit()


def get_lang(user: str) -> str | None:
    with _lock:
        row = _db().execute("SELECT lang FROM prefs WHERE user=?", (user,)).fetchone()
    return row[0] if row else None


def set_lang(user: str, lang: str) -> None:
    with _lock:
        c = _db()
        c.execute("INSERT OR REPLACE INTO prefs VALUES(?,?)", (user, lang))
        c.commit()


def log_check(input_type: str, language: str, labels: list[str], elapsed_ms: int) -> None:
    with _lock:
        c = _db()
        c.execute("INSERT INTO checks(created_at,input_type,language,claims,labels,elapsed_ms) VALUES(?,?,?,?,?,?)",
                  (time.time(), input_type, language, len(labels), ",".join(labels), elapsed_ms))
        c.commit()


def stats() -> dict:
    with _lock:
        c = _db()
        n, avg = c.execute("SELECT COUNT(*), AVG(elapsed_ms) FROM checks").fetchone()
        by_type = dict(c.execute("SELECT input_type, COUNT(*) FROM checks GROUP BY input_type").fetchall())
        labels: dict[str, int] = {}
        for (lab,) in c.execute("SELECT labels FROM checks").fetchall():
            for x in filter(None, (lab or "").split(",")):
                labels[x] = labels.get(x, 0) + 1
    return {"checks": n, "avg_ms": int(avg or 0), "by_input_type": by_type, "by_label": labels}

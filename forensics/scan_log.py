"""Scan log — every scan the detector serves, in SQLite (stdlib only).

The cache in ``forensics/scan_cache.py`` answers "have I seen this before?".
This log answers the opposite question: "what has the detector actually been
asked to judge, and what did it say?" That is the raw material for calibration,
for a human/authentic whitelist corpus, and for answering "why did this get
flagged?" weeks later.

What is stored, per scan:

  * the normalized verdict (kind, score, tier, label, confidence) + the
    compact verdict JSON — never the payload bytes, never image/video data,
    never a heatmap overlay;
  * for text scans, a bounded excerpt of the text (default 4,000 chars) and
    the sha256 of the whole text, so a sample can be found again without the
    log becoming a copy of everything users ever pasted;
  * provenance: endpoint, HTTP status, cache hit/miss, latency, the source
    host (not the full URL — a hash is kept instead), a salted hash of the
    client IP (abuse clustering without storing addresses), and the
    user-agent;
  * `human_likely` — 1 when the verdict says AUTHENTIC_HUMAN / "Human-written".
    Human-looking scans are the ones worth keeping longest: they are the
    false-positive evidence.

Environment (all optional):

  SCAN_LOG=0                  turn logging off entirely
  SCAN_LOG_DIR                directory for scan_log.db (default <repo>/cache)
  SCAN_LOG_EXCERPT_CHARS      max chars of text stored per scan (default 4000)
  SCAN_LOG_RETENTION_DAYS     retention for non-human scans (default 90)
  SCAN_LOG_HUMAN_RETENTION_DAYS
                              retention for human-likely scans (default 365)
  SCAN_LOG_MAX_ROWS           soft row cap (default 200000)
  SCAN_LOG_SALT               salt for IP hashing (set it in production)

Design notes:

  * Same shape as the cache: WAL, one short-lived connection per operation,
    timeout=5, lazy maintenance after every N inserts (never on a timer).
  * Writing a log row must never break a scan. ``log_scan`` swallows and
    reports every error; the caller gets a bool.
  * Eviction is biased: non-human rows are trimmed first, so a burst of AI
    scans can never push the human corpus out.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.environ.get("SCAN_LOG_DIR") or os.path.join(REPO, "cache")
DB_PATH = os.path.join(LOG_DIR, "scan_log.db")

ENABLED = os.environ.get("SCAN_LOG", "1") not in ("0", "false", "no", "off")
EXCERPT_CHARS = int(os.environ.get("SCAN_LOG_EXCERPT_CHARS", "4000"))
RETENTION_DAYS = int(os.environ.get("SCAN_LOG_RETENTION_DAYS", "90"))
HUMAN_RETENTION_DAYS = int(os.environ.get("SCAN_LOG_HUMAN_RETENTION_DAYS", "365"))
MAX_ROWS = int(os.environ.get("SCAN_LOG_MAX_ROWS", "200000"))
SALT = os.environ.get("SCAN_LOG_SALT", "rinse-scan-log")

MAINTAIN_EVERY = 500  # inserts between lazy retention passes
MAX_VERDICT_JSON = 200_000  # chars; anything larger collapses to the summary

# Keys whose value is a blob we never want in a log row: heatmap overlays,
# frame dumps, inline media. Matched case-insensitively as a substring, so
# "heatmap_overlay_base64" and "frame_base64" both fall under it.
_HEAVY_KEY_FRAGMENTS = (
    "base64",
    "overlay",
    "heatmap_grid_image",
    "thumbnail",
    "frames",
)
_MAX_STRING_CHARS = 500
_MAX_LIST_ITEMS = 50

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at     REAL NOT NULL,
  kind           TEXT NOT NULL,               -- text | image | video
  source         TEXT NOT NULL,               -- endpoint, e.g. image/deep
  status         INTEGER NOT NULL,            -- HTTP status of the response
  cached         TEXT,                        -- NULL (fresh) | 'exact' | 'near'
  score          REAL,
  tier           TEXT,
  label          TEXT,
  confidence     TEXT,
  human_likely   INTEGER NOT NULL DEFAULT 0,
  content_sha256 TEXT,
  content_chars  INTEGER,
  excerpt        TEXT,                        -- text scans only, bounded
  source_host    TEXT,
  source_sha256  TEXT,
  ip_hash        TEXT,
  user_agent     TEXT,
  latency_ms     INTEGER,
  verdict        TEXT                         -- compact JSON
);
CREATE INDEX IF NOT EXISTS idx_scans_created ON scans(created_at);
CREATE INDEX IF NOT EXISTS idx_scans_kind ON scans(kind, created_at);
CREATE INDEX IF NOT EXISTS idx_scans_human ON scans(human_likely, created_at);
"""

_lock = threading.Lock()
_inserts_since_maintain = 0


# ---------------------------------------------------------------------------
# Connection / schema
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    os.makedirs(LOG_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes | str | None) -> str | None:
    if data is None:
        return None
    if isinstance(data, str):
        data = data.encode("utf-8", "ignore")
    return hashlib.sha256(data).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """Salted, truncated hash — clusters repeat callers without storing IPs."""
    if not ip:
        return None
    first = ip.split(",")[0].strip()
    if not first:
        return None
    return _sha256(f"{SALT}|{first}")[:16]


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).hostname
    except Exception:  # noqa: BLE001
        return None
    return host.lower() if host else None


def is_human_likely(verdict: dict[str, Any]) -> bool:
    """Does this verdict clear the content?

    Media verdicts carry a `tier` (AUTHENTIC_HUMAN is the cleared band); text
    detectors only carry a label ("Human-written") and a score. All three
    paths land on the same boolean so one log column can answer "show me the
    content we called human" across every mode.
    """
    tier = verdict.get("tier")
    if isinstance(tier, str) and tier:
        return tier.upper() == "AUTHENTIC_HUMAN"
    label = verdict.get("label")
    if isinstance(label, str) and label:
        low = label.lower()
        if "human" in low:
            return True
        if "ai" in low or "synthetic" in low:
            return False
    score = verdict.get("score")
    if isinstance(score, (int, float)):
        return score < 35
    return False


def _compact_verdict(verdict: dict[str, Any]) -> str:
    """Serialize the verdict without the heavy payloads (overlays, media)."""
    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, item in value.items():
                key_s = str(key)
                if any(frag in key_s.lower() for frag in _HEAVY_KEY_FRAGMENTS):
                    out[key_s] = "<omitted>"
                else:
                    out[key_s] = walk(item)
            return out
        if isinstance(value, (list, tuple)):
            return [walk(item) for item in list(value)[:_MAX_LIST_ITEMS]]
        if isinstance(value, (bytes, bytearray)):
            return f"<{len(value)} bytes>"
        if isinstance(value, str) and len(value) > _MAX_STRING_CHARS:
            return f"{value[:_MAX_STRING_CHARS]}… <{len(value)} chars>"
        return value

    try:
        text = json.dumps(walk(verdict), default=str)
    except Exception:  # noqa: BLE001
        text = json.dumps({"score": verdict.get("score"), "label": verdict.get("label")})
    if len(text) <= MAX_VERDICT_JSON:
        return text
    summary = {
        "score": verdict.get("score"),
        "tier": verdict.get("tier"),
        "label": verdict.get("label"),
        "confidence": verdict.get("confidence"),
        "truncated": True,
    }
    return json.dumps(summary)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def log_scan(
    kind: str,
    verdict: dict[str, Any] | None,
    *,
    source: str,
    status: int = 200,
    cached: Any = None,
    excerpt: str | None = None,
    content: bytes | str | None = None,
    content_sha256: str | None = None,
    content_chars: int | None = None,
    source_url: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    latency_ms: float | None = None,
) -> bool:
    """Record one scan. Returns True when the row was written.

    Never raises: logging is best-effort and must never turn a good scan into
    a 500. `content` is hashed, not stored; `excerpt` is truncated here so the
    caller can pass whatever it already has in memory.
    """
    if not ENABLED:
        return False
    verdict = verdict if isinstance(verdict, dict) else {}
    try:
        text = excerpt or ""
        if len(text) > EXCERPT_CHARS:
            text = text[:EXCERPT_CHARS]

        digest = content_sha256 or _sha256(content)
        if digest is None and text:
            digest = _sha256(text)

        cached_flag = None
        if cached:
            cached_flag = cached if isinstance(cached, str) else str(cached)
            if cached_flag in ("False", "0", "false", "none", "None"):
                cached_flag = None

        score = verdict.get("score")
        row = (
            time.time(),
            str(kind),
            str(source),
            int(status),
            cached_flag,
            float(score) if isinstance(score, (int, float)) else None,
            verdict.get("tier"),
            verdict.get("label") or verdict.get("short_label"),
            verdict.get("confidence"),
            1 if is_human_likely(verdict) else 0,
            digest,
            content_chars
            if content_chars is not None
            else (len(content) if isinstance(content, (bytes, str)) else (len(text) or None)),
            text or None,
            _host_of(source_url),
            _sha256(source_url) if source_url else None,
            hash_ip(ip),
            (user_agent or "")[:300] or None,
            int(latency_ms) if isinstance(latency_ms, (int, float)) else None,
            _compact_verdict(verdict),
        )

        _init()
        with _connect() as conn:
            conn.execute(
                "INSERT INTO scans (created_at, kind, source, status, cached, score,"
                " tier, label, confidence, human_likely, content_sha256, content_chars,"
                " excerpt, source_host, source_sha256, ip_hash, user_agent, latency_ms,"
                " verdict) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )
        _maybe_maintain()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"Scan log write failed (scan unaffected): {e}")
        return False


# ---------------------------------------------------------------------------
# Retention — human rows are kept longest, and trimmed last
# ---------------------------------------------------------------------------

def _maybe_maintain() -> None:
    """Run retention every MAINTAIN_EVERY inserts (plus a little jitter)."""
    global _inserts_since_maintain
    with _lock:
        _inserts_since_maintain += 1
        due = _inserts_since_maintain >= MAINTAIN_EVERY
        if due:
            _inserts_since_maintain = 0
    if due or random.random() < 0.001:
        try:
            maintain()
        except Exception as e:  # noqa: BLE001
            print(f"Scan log maintenance failed: {e}")


def maintain(now: float | None = None) -> dict[str, int]:
    """Apply retention + the row cap. Returns how many rows each step removed."""
    now = time.time() if now is None else now
    removed: dict[str, int] = {"expired_human": 0, "expired_other": 0, "trimmed": 0}
    _init()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM scans WHERE human_likely = 0 AND created_at < ?",
            (now - RETENTION_DAYS * 86400,),
        )
        removed["expired_other"] = cur.rowcount or 0

        cur = conn.execute(
            "DELETE FROM scans WHERE human_likely = 1 AND created_at < ?",
            (now - HUMAN_RETENTION_DAYS * 86400,),
        )
        removed["expired_human"] = cur.rowcount or 0

        over = (conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]) - MAX_ROWS
        if over > 0:
            # Non-human rows go first: the human corpus is the point of the log.
            cur = conn.execute(
                "DELETE FROM scans WHERE id IN ("
                "  SELECT id FROM scans ORDER BY human_likely ASC, created_at ASC LIMIT ?)",
                (over,),
            )
            removed["trimmed"] = cur.rowcount or 0
    return removed


# ---------------------------------------------------------------------------
# Reading — stats, recent rows, export
# ---------------------------------------------------------------------------

def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def stats(now: float | None = None) -> dict[str, Any]:
    """Aggregate counts for /scans/stats and the operator's sanity checks."""
    now = time.time() if now is None else now
    _init()
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        human = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE human_likely = 1"
        ).fetchone()[0]
        human_7d = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE human_likely = 1 AND created_at >= ?",
            (now - 7 * 86400,),
        ).fetchone()[0]
        by_kind = dict(
            conn.execute(
                "SELECT kind, COUNT(*) FROM scans GROUP BY kind"
            ).fetchall()
        )
        by_kind_human = dict(
            conn.execute(
                "SELECT kind, COUNT(*) FROM scans WHERE human_likely = 1"
                " GROUP BY kind"
            ).fetchall()
        )
        by_tier = dict(
            conn.execute(
                "SELECT COALESCE(tier, label, 'unknown'), COUNT(*) FROM scans"
                " GROUP BY COALESCE(tier, label, 'unknown')"
            ).fetchall()
        )
        cached = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE cached IS NOT NULL"
        ).fetchone()[0]
        last = conn.execute("SELECT MAX(created_at) FROM scans").fetchone()[0]

    db_bytes = 0
    for suffix in ("", "-wal", "-shm"):
        path = DB_PATH + suffix
        if os.path.exists(path):
            db_bytes += os.path.getsize(path)

    return {
        "enabled": ENABLED,
        "total": total,
        "human_likely": human,
        "human_likely_7d": human_7d,
        "by_kind": by_kind,
        "by_kind_human_likely": by_kind_human,
        "by_tier": by_tier,
        "cached_hits": cached,
        "last_scan_at": _iso(last),
        "db_bytes": db_bytes,
        "db_path": DB_PATH,
        "retention_days": RETENTION_DAYS,
        "human_retention_days": HUMAN_RETENTION_DAYS,
        "max_rows": MAX_ROWS,
    }


_RECENT_COLUMNS = (
    "id, created_at, kind, source, status, cached, score, tier, label, confidence,"
    " human_likely, content_sha256, content_chars, source_host, source_sha256,"
    " ip_hash, user_agent, latency_ms"
)


def recent(
    limit: int = 50,
    *,
    kind: str | None = None,
    human_only: bool = False,
    include_text: bool = False,
    since: float | None = None,
) -> list[dict[str, Any]]:
    """Newest scans first. Text is withheld unless `include_text` is set."""
    limit = max(1, min(int(limit), 500))
    where: list[str] = []
    params: list[Any] = []
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if human_only:
        where.append("human_likely = 1")
    if since:
        where.append("created_at >= ?")
        params.append(float(since))
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    columns = _RECENT_COLUMNS + (", excerpt" if include_text else "")

    _init()
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT {columns} FROM scans{clause} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        names = [d[0] for d in conn.execute(
            f"SELECT {columns} FROM scans{clause} LIMIT 0", params
        ).description]

    out = []
    for row in rows:
        item = dict(zip(names, row))
        item["created_at"] = _iso(item.get("created_at"))
        item["human_likely"] = bool(item.get("human_likely"))
        if include_text:
            item["excerpt"] = item.get("excerpt")
        out.append(item)
    return out


def iter_rows(
    *,
    kind: str | None = None,
    human_only: bool = False,
    since: float | None = None,
    include_verdict: bool = False,
) -> Iterator[dict[str, Any]]:
    """Stream rows for export. Yields dicts; the connection is closed at end."""
    where: list[str] = []
    params: list[Any] = []
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if human_only:
        where.append("human_likely = 1")
    if since:
        where.append("created_at >= ?")
        params.append(float(since))
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    columns = _RECENT_COLUMNS + ", excerpt" + (", verdict" if include_verdict else "")

    _init()
    conn = _connect()
    try:
        cur = conn.execute(f"SELECT {columns} FROM scans{clause} ORDER BY id ASC", params)
        names = [d[0] for d in cur.description]
        for row in cur:
            item = dict(zip(names, row))
            item["created_at"] = _iso(item.get("created_at"))
            item["human_likely"] = bool(item.get("human_likely"))
            yield item
    finally:
        conn.close()


def export_jsonl(
    out_path: str,
    *,
    kind: str | None = None,
    human_only: bool = False,
    since: float | None = None,
    include_verdict: bool = False,
) -> int:
    """Write matching rows as JSON Lines. Returns the row count."""
    written = 0
    with open(out_path, "w", encoding="utf-8") as handle:
        for item in iter_rows(
            kind=kind,
            human_only=human_only,
            since=since,
            include_verdict=include_verdict,
        ):
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            written += 1
    return written


def clear(kinds: Iterable[str] | None = None) -> int:
    """Delete rows (all, or the given kinds). Returns rows removed."""
    _init()
    with _connect() as conn:
        if kinds:
            kinds = list(kinds)
            marks = ",".join("?" for _ in kinds)
            cur = conn.execute(f"DELETE FROM scans WHERE kind IN ({marks})", kinds)
        else:
            cur = conn.execute("DELETE FROM scans")
        return cur.rowcount or 0

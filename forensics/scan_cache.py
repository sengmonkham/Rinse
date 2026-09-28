"""Scan result cache — SQLite (stdlib only), two lookup layers.

Implements the caching half of docs/brainrot-characters-and-scan-cache-plan.md:

  Layer 1 (exact):    sha256(raw bytes)  -> stored full verdict JSON
  Layer 2 (near-dup): dHash bridge table -> sha256 of a perceptually-similar
                      stored image; only DECISIVE verdicts are reusable
                      (tier SYNTHETIC_AI / AUTHENTIC_HUMAN with HIGH
                      confidence) so an uncertain result never spreads.

Also caches source fetches by URL (TTL 24h) so the same meme URL isn't
re-downloaded on every scan.

Design notes (from the plan):
  - WAL journal mode; one short-lived connection per operation with
    timeout=5 (Flask threads never block long).
  - TTLs enforced lazily on read; lazy LRU eviction after insert.
  - `pipeline_version` busts the whole cache whenever the detector stack
    changes (weights, fingerprint DB build id, model name).
  - `no_cache: true` in a request body skips reads (writes still happen).
  - Near-dup hits only reuse decisive verdicts and only at Hamming <= 6.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from typing import Any

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("SCAN_CACHE_DIR") or os.path.join(REPO, "cache")
DB_PATH = os.path.join(CACHE_DIR, "scan_cache.db")

VERDICT_TTL_S = 30 * 24 * 3600          # 30 days
FETCH_TTL_S = 24 * 3600                 # 24 hours
MAX_ROWS = 50_000                       # lazy LRU cap for verdicts
MAX_FETCH_BYTES = 150 * 1024 * 1024     # per-row cap for cached fetches
NEAR_DUP_MAX_DIST = 6                   # of 64 bits

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
  sha256           TEXT PRIMARY KEY,
  kind             TEXT NOT NULL,
  pipeline_version TEXT NOT NULL,
  verdict          TEXT NOT NULL,
  dhash            TEXT,                 -- 16-char hex (SQLite int64 overflow safety)
  created_at       REAL NOT NULL,
  last_hit_at      REAL,
  hits             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_verdicts_last_hit ON verdicts(last_hit_at);

CREATE TABLE IF NOT EXISTS dhash_pieces (
  piece_index INTEGER NOT NULL,
  piece_value INTEGER NOT NULL,
  sha256      TEXT NOT NULL REFERENCES verdicts(sha256) ON DELETE CASCADE,
  PRIMARY KEY (piece_index, piece_value, sha256)
);

CREATE TABLE IF NOT EXISTS fetches (
  url_key    TEXT PRIMARY KEY,
  content    BLOB NOT NULL,
  n_bytes    INTEGER NOT NULL,
  fetched_at REAL NOT NULL
);
"""


def pipeline_version() -> str:
    """Hash of everything that changes detector behavior.

    Bumping = weight changes in voter.py, fingerprint DB rebuilds, or neural
    model swaps. When this value moves, all cached verdicts become invisible
    (stale rows age out via eviction).
    """
    parts = []
    try:
        from forensics import voter

        parts.append(voter.__file__ or "")
    except Exception:  # noqa: BLE001
        parts.append("voter?")
    try:
        from fingerprints import db as fpdb

        parts.append(str(getattr(fpdb, "FINGERPRINT_DB_BUILD", "")))
        parts.append(str(getattr(fpdb, "FINGERPRINTS", []) and len(fpdb.FINGERPRINTS)))
    except Exception:  # noqa: BLE001
        parts.append("fpdb?")
    parts.append(os.environ.get("MODEL_NAME", "cnnspot"))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _connect() -> sqlite3.Connection:
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Decisive verdicts (near-dup reuse policy)
# ---------------------------------------------------------------------------


def is_decisive(verdict: dict[str, Any]) -> bool:
    """A verdict a near-duplicate may inherit: clear tier + HIGH confidence."""
    tier = verdict.get("tier")
    conf = verdict.get("confidence")
    return (
        tier in ("SYNTHETIC_AI", "AUTHENTIC_HUMAN")
        and conf == "HIGH"
    )


# ---------------------------------------------------------------------------
# Layer 1 — exact content lookups
# ---------------------------------------------------------------------------


def get_verdict_exact(sha256_hex: str) -> dict[str, Any] | None:
    """Return the stored verdict payload for exact content, if fresh."""
    _init()
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT verdict, created_at, pipeline_version FROM verdicts "
            "WHERE sha256 = ? AND kind IN ('image', 'video')",
            (sha256_hex,),
        ).fetchone()
    if not row:
        return None
    verdict_json, created_at, row_version = row
    if row_version != pipeline_version() or now - created_at > VERDICT_TTL_S:
        return None
    try:
        payload = json.loads(verdict_json)
    except Exception:  # noqa: BLE001
        return None
    with _connect() as conn:
        conn.execute(
            "UPDATE verdicts SET last_hit_at = ?, hits = hits + 1 WHERE sha256 = ?",
            (now, sha256_hex),
        )
    return payload


def store_verdict(
    sha256_hex: str,
    kind: str,
    verdict: dict[str, Any],
    dhash_value: int | None,
) -> None:
    """Store a full verdict (idempotent upsert) + its dHash near-key."""
    _init()
    now = time.time()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO verdicts (sha256, kind, pipeline_version, verdict, dhash, created_at, last_hit_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(sha256) DO UPDATE SET"
            " verdict=excluded.verdict, pipeline_version=excluded.pipeline_version,"
            " dhash=excluded.dhash, last_hit_at=excluded.last_hit_at",
            (
                sha256_hex,
                kind,
                pipeline_version(),
                json.dumps(verdict),
                dhash_value if dhash_value is None else format(int(dhash_value), "016x"),
                now,
                now,
            ),
        )
        if dhash_value is not None:
            dh_hex = format(int(dhash_value), "016x")
            for i in range(8):
                piece = (int(dhash_value) >> (8 * i)) & 0xFF
                conn.execute(
                    "INSERT OR IGNORE INTO dhash_pieces (piece_index, piece_value, sha256)"
                    " VALUES (?, ?, ?)",
                    (i, piece, sha256_hex),
                )
        _evict_if_needed(conn)


def get_verdict_near(
    dhash_value: int,
) -> tuple[dict[str, Any], str] | None:
    """Near-duplicate lookup: decisive cached verdict within Hamming <= 6.

    Returns (payload, similar_sha256) or None.

    Candidate generation uses a piecewise index: the 64-bit dHash is split
    into 8 bytes, each indexed separately. By pigeonhole, any hash within
    Hamming distance <= 7 of the query must match the query on at least one
    byte exactly — so 8 indexed lookups generate a small candidate set, which
    is then Hamming-verified in full (the index has no false negatives; the
    verification has no false positives).
    """
    _init()
    now = time.time()
    candidates: set[str] = set()
    with _connect() as conn:
        for i in range(8):
            piece = (dhash_value >> (8 * i)) & 0xFF
            rows = conn.execute(
                "SELECT sha256 FROM dhash_pieces WHERE piece_index = ? AND piece_value = ?",
                (i, piece),
            ).fetchall()
            candidates.update(r[0] for r in rows)
    if not candidates:
        return None

    current_version = pipeline_version()
    with _connect() as conn:
        for sha256_hex in candidates:
            row = conn.execute(
                "SELECT verdict, created_at, pipeline_version, dhash FROM verdicts"
                " WHERE sha256 = ? AND kind IN ('image', 'video')",
                (sha256_hex,),
            ).fetchone()
            if not row:
                continue
            verdict_json, created_at, row_version, stored_dhash = row
            if row_version != current_version or now - created_at > VERDICT_TTL_S:
                continue
            if stored_dhash is None:
                continue
            if bin(int(str(stored_dhash), 16) ^ dhash_value).count("1") > NEAR_DUP_MAX_DIST:
                continue
            try:
                payload = json.loads(verdict_json)
            except Exception:  # noqa: BLE001
                continue
            if not is_decisive(payload):
                continue
            with _connect() as conn:
                conn.execute(
                    "UPDATE verdicts SET last_hit_at = ?, hits = hits + 1 WHERE sha256 = ?",
                    (now, sha256_hex),
                )
            return payload, sha256_hex
    return None


# ---------------------------------------------------------------------------
# Source fetch cache (URL inputs)
# ---------------------------------------------------------------------------


def get_fetch(url: str) -> bytes | None:
    """Cached bytes for a URL, if fetched within TTL."""
    _init()
    key = hashlib.sha256(url.encode()).hexdigest()
    now = time.time()
    with _connect() as conn:
        row = conn.execute(
            "SELECT content, fetched_at FROM fetches WHERE url_key = ?",
            (key,),
        ).fetchone()
    if not row:
        return None
    content, fetched_at = row
    if now - fetched_at > FETCH_TTL_S:
        return None
    return content


def store_fetch(url: str, content: bytes) -> None:
    """Cache fetched URL bytes (capped at MAX_FETCH_BYTES)."""
    if len(content) > MAX_FETCH_BYTES:
        return
    _init()
    key = hashlib.sha256(url.encode()).hexdigest()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO fetches (url_key, content, n_bytes, fetched_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(url_key) DO UPDATE SET content=excluded.content,"
            " n_bytes=excluded.n_bytes, fetched_at=excluded.fetched_at",
            (key, content, len(content), time.time()),
        )


# ---------------------------------------------------------------------------
# Eviction + stats + admin
# ---------------------------------------------------------------------------


def _evict_if_needed(conn: sqlite3.Connection) -> None:
    """Lazy LRU: trim verdicts beyond MAX_ROWS (oldest last_hit first)."""
    n = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    if n <= MAX_ROWS:
        return
    conn.execute(
        "DELETE FROM verdicts WHERE sha256 IN ("
        "  SELECT sha256 FROM verdicts ORDER BY COALESCE(last_hit_at, created_at) ASC"
        "  LIMIT ?)",
        (n - MAX_ROWS,),
    )


def cache_stats() -> dict[str, Any]:
    """Aggregate stats for the /cache/stats admin endpoint."""
    _init()
    with _connect() as conn:
        (n_verdicts,) = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()
        (n_hits,) = conn.execute(
            "SELECT COALESCE(SUM(hits), 0) FROM verdicts"
        ).fetchone()
        (n_pieces,) = conn.execute("SELECT COUNT(*) FROM dhash_pieces").fetchone()
        (n_fetches, fetch_bytes) = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(n_bytes), 0) FROM fetches"
        ).fetchone()
    db_bytes = 0
    for suffix in ("", "-wal", "-shm"):
        p = DB_PATH + suffix
        if os.path.exists(p):
            db_bytes += os.path.getsize(p)
    return {
        "verdicts": n_verdicts,
        "total_hits": n_hits,
        "dhash_pieces": n_pieces,
        "cached_fetches": n_fetches,
        "cached_fetch_bytes": fetch_bytes,
        "db_bytes": db_bytes,
        "pipeline_version": pipeline_version(),
        "verdict_ttl_days": VERDICT_TTL_S // 86400,
    }


def cache_clear() -> dict[str, Any]:
    """Wipe all cached verdicts and fetches."""
    _init()
    with _connect() as conn:
        conn.execute("DELETE FROM verdicts")
        conn.execute("DELETE FROM fetches")
    return {"cleared": True}

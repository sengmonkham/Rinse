#!/usr/bin/env python3
"""Tests for the scan log (forensics/scan_log.py).

Runs offline against a throwaway SQLite file — no server, no network, no
detector models:

    .venv/bin/python tests/test_scan_log.py

Covers the things that would quietly rot: the fields a row must carry, the
human-likely flag across all three verdict shapes, verdict compaction (no
base64 blobs in the log), text excerpt bounds, IP hashing, cache flags,
retention that protects the human corpus, the row cap, filters, JSONL export,
and the promise that a logging failure can never raise into a scan.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# The DB path is resolved at import time, so point it at a temp dir first.
_TMP = tempfile.mkdtemp(prefix="rinse-scan-log-")
os.environ["SCAN_LOG_DIR"] = _TMP
os.environ["SCAN_LOG"] = "1"
os.environ["SCAN_LOG_SALT"] = "test-salt"

from forensics import scan_log  # noqa: E402

FAILED: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
    except Exception as e:  # noqa: BLE001
        FAILED.append(name)
        print(f"FAIL {name}: {type(e).__name__}: {e}")
    else:
        print(f"PASS {name}")


def _reset() -> None:
    scan_log.clear()
    scan_log.EXCERPT_CHARS = 4000
    scan_log.RETENTION_DAYS = 90
    scan_log.HUMAN_RETENTION_DAYS = 365
    scan_log.MAX_ROWS = 200_000
    scan_log.ENABLED = True


TEXT_HUMAN = {
    "score": 21,
    "label": "Human-written",
    "probability": 0.21,
    "reasons": ["Variable sentence lengths"],
}

TEXT_AI = {
    "score": 84,
    "label": "AI-generated",
    "probability": 0.84,
    "reasons": ["'Use of irony and humor' = 1 - entirely_straightfaced_no_discernible_humor"],
}

IMAGE_HUMAN = {
    "score": 12,
    "tier": "AUTHENTIC_HUMAN",
    "confidence": "HIGH",
    "label": "Camera capture",
    "alteration": {"label": "unlikely", "score": 8},
}

VIDEO_SUSPICIOUS = {
    "score": 74,
    "tier": "SUSPICIOUS",
    "confidence": "MEDIUM",
    "label": "Likely AI",
    "heatmap_overlay_base64": "AAAABBBBCCCC" * 500,
    "neural_submodels": {"a": 0.4, "b": 0.7},
}


# ---------------------------------------------------------------------------
# Human-likely normalization
# ---------------------------------------------------------------------------

def test_human_flag_covers_all_three_shapes():
    assert scan_log.is_human_likely(TEXT_HUMAN) is True
    assert scan_log.is_human_likely(TEXT_AI) is False
    assert scan_log.is_human_likely(IMAGE_HUMAN) is True
    assert scan_log.is_human_likely(VIDEO_SUSPICIOUS) is False
    # No tier and no label: fall back to the score band.
    assert scan_log.is_human_likely({"score": 12}) is True
    assert scan_log.is_human_likely({"score": 88}) is False
    assert scan_log.is_human_likely({}) is False


# ---------------------------------------------------------------------------
# Writing rows
# ---------------------------------------------------------------------------

def test_text_scan_row_has_provenance_and_excerpt():
    _reset()
    text = "I walked to the shop. It was closed, so I went home. " * 20
    ok = scan_log.log_scan(
        "text", TEXT_HUMAN,
        source="text/storyscope", excerpt=text, content=text,
        ip="203.0.113.9, 10.0.0.1", user_agent="Mozilla/5.0 Test",
        latency_ms=42.7,
    )
    assert ok is True
    row = scan_log.recent(1, include_text=True)[0]
    assert row["kind"] == "text"
    assert row["source"] == "text/storyscope"
    assert row["status"] == 200
    assert row["score"] == 21
    assert row["label"] == "Human-written"
    assert row["human_likely"] is True
    assert row["content_chars"] == len(text)
    assert row["content_sha256"] == scan_log._sha256(text)
    assert row["ip_hash"] and row["ip_hash"] != "203.0.113.9"
    assert len(row["ip_hash"]) == 16
    assert "203.0.113" not in str(row)  # the address itself is never stored
    assert row["user_agent"] == "Mozilla/5.0 Test"
    assert row["latency_ms"] == 42
    assert row["excerpt"].startswith("I walked to the shop")


def test_excerpt_is_bounded():
    _reset()
    scan_log.EXCERPT_CHARS = 120
    text = "word " * 1000
    scan_log.log_scan("text", TEXT_HUMAN, source="text/dna", excerpt=text, content=text)
    row = scan_log.recent(1, include_text=True)[0]
    assert len(row["excerpt"]) == 120
    assert row["content_chars"] == len(text)  # the hash covers the whole text
    assert row["content_sha256"] == scan_log._sha256(text)


def test_verdict_is_compacted_without_payloads():
    _reset()
    scan_log.log_scan("video", VIDEO_SUSPICIOUS, source="video/deep")
    with scan_log._connect() as conn:
        stored = conn.execute("SELECT verdict FROM scans ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert "AAAABBBB" not in stored
    assert "heatmap_overlay_base64" in stored  # key kept, value replaced
    assert len(stored) < 20_000
    assert '"tier": "SUSPICIOUS"' in stored


def test_failed_scan_is_logged_with_its_status():
    _reset()
    failure = {"score": 50, "label": "Inconclusive", "reasons": ["boom"]}
    scan_log.log_scan("text", failure, source="text/dna", status=500)
    row = scan_log.recent(1)[0]
    assert row["status"] == 500
    assert row["human_likely"] is False


def test_cache_flags_are_recorded_and_normalized():
    _reset()
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep", cached="near")
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep", cached=False)
    rows = scan_log.recent(2)
    assert rows[0]["cached"] is None  # False -> fresh scan, not "False"
    assert rows[1]["cached"] == "near"


def test_source_url_is_stored_as_host_and_hash_only():
    _reset()
    scan_log.log_scan(
        "video", VIDEO_SUSPICIOUS, source="video/deep",
        source_url="https://cdn.example.com/private/clip-42.mp4?sig=secret",
    )
    with scan_log._connect() as conn:
        host, url_hash = conn.execute(
            "SELECT source_host, source_sha256 FROM scans ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert host == "cdn.example.com"
    assert url_hash == scan_log._sha256(
        "https://cdn.example.com/private/clip-42.mp4?sig=secret"
    )
    assert "sig=secret" not in scan_log.recent(1).__str__()


def test_logging_errors_never_raise():
    _reset()
    original = scan_log._connect

    def boom():
        raise RuntimeError("disk full")

    scan_log._connect = boom
    try:
        assert scan_log.log_scan("text", TEXT_AI, source="text/dna") is False
    finally:
        scan_log._connect = original


def test_disabled_log_writes_nothing():
    _reset()
    scan_log.ENABLED = False
    try:
        assert scan_log.log_scan("text", TEXT_AI, source="text/dna") is False
        assert scan_log.recent(10) == []
    finally:
        scan_log.ENABLED = True


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def test_stats_count_humans_by_kind_and_tier():
    _reset()
    scan_log.log_scan("text", TEXT_HUMAN, source="text/storyscope", excerpt="hi there")
    scan_log.log_scan("text", TEXT_AI, source="text/dna", excerpt="as an AI language model")
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep")
    scan_log.log_scan("video", VIDEO_SUSPICIOUS, source="video/deep", cached="exact")

    s = scan_log.stats()
    assert s["total"] == 4
    assert s["human_likely"] == 2
    assert s["human_likely_7d"] == 2
    assert s["by_kind"] == {"text": 2, "image": 1, "video": 1}
    assert s["by_kind_human_likely"] == {"text": 1, "image": 1}
    assert s["by_tier"]["AUTHENTIC_HUMAN"] == 1
    assert s["by_tier"]["Human-written"] == 1
    assert s["cached_hits"] == 1
    assert s["db_bytes"] > 0


def test_recent_filters_by_kind_and_human():
    _reset()
    scan_log.log_scan("text", TEXT_HUMAN, source="text/storyscope", excerpt="human words")
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep")
    scan_log.log_scan("video", VIDEO_SUSPICIOUS, source="video/deep")

    assert len(scan_log.recent(10)) == 3
    assert [r["kind"] for r in scan_log.recent(10, kind="image")] == ["image"]
    humans = scan_log.recent(10, human_only=True)
    assert {r["kind"] for r in humans} == {"text", "image"}
    # Newest first.
    assert scan_log.recent(1)[0]["kind"] == "video"
    # Text stays out of responses unless asked for.
    assert "excerpt" not in scan_log.recent(10, kind="text")[0]
    assert scan_log.recent(10, kind="text", include_text=True)[0]["excerpt"]


def test_export_jsonl_writes_matching_rows():
    _reset()
    scan_log.log_scan("text", TEXT_HUMAN, source="text/storyscope", excerpt="one")
    scan_log.log_scan("text", TEXT_AI, source="text/dna", excerpt="two")
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep")

    out = os.path.join(_TMP, "export.jsonl")
    assert scan_log.export_jsonl(out, human_only=True) == 2
    with open(out, encoding="utf-8") as handle:
        lines = [line for line in handle if line.strip()]
    assert len(lines) == 2
    assert all('"human_likely": true' in line for line in lines)
    assert scan_log.export_jsonl(out, kind="image") == 1


# ---------------------------------------------------------------------------
# Retention — the human corpus survives
# ---------------------------------------------------------------------------

def test_retention_keeps_human_rows_longer():
    _reset()
    now = time.time()
    old_human = dict(IMAGE_HUMAN)
    scan_log.log_scan("image", old_human, source="image/deep")
    scan_log.log_scan("image", VIDEO_SUSPICIOUS, source="image/deep")
    # Age both rows by 200 days.
    with scan_log._connect() as conn:
        conn.execute("UPDATE scans SET created_at = ?", (now - 200 * 86400,))

    scan_log.RETENTION_DAYS = 90
    scan_log.HUMAN_RETENTION_DAYS = 365
    removed = scan_log.maintain(now=now)
    assert removed["expired_other"] == 1
    assert removed["expired_human"] == 0
    remaining = scan_log.recent(10)
    assert len(remaining) == 1 and remaining[0]["human_likely"] is True

    # Past the human window too, it finally goes.
    scan_log.HUMAN_RETENTION_DAYS = 30
    removed = scan_log.maintain(now=now)
    assert removed["expired_human"] == 1
    assert scan_log.recent(10) == []


def test_row_cap_trims_non_human_first():
    _reset()
    scan_log.MAX_ROWS = 3
    for i in range(5):
        scan_log.log_scan("text", TEXT_AI, source="text/dna", excerpt=f"ai {i}")
    scan_log.log_scan("image", IMAGE_HUMAN, source="image/deep")

    scan_log.maintain()
    rows = scan_log.recent(10)
    assert len(rows) == 3
    humans = [r for r in rows if r["human_likely"]]
    assert len(humans) == 1, "the human scan must survive the trim"


check("human flag covers all three verdict shapes", test_human_flag_covers_all_three_shapes)
check(
    "text scan row carries provenance + excerpt",
    test_text_scan_row_has_provenance_and_excerpt,
)
check("text excerpt is bounded, hash is not", test_excerpt_is_bounded)
check("verdict is compacted (no base64 blobs)", test_verdict_is_compacted_without_payloads)
check(
    "failed detector response is logged with status",
    test_failed_scan_is_logged_with_its_status,
)
check("cache flags are recorded and normalized", test_cache_flags_are_recorded_and_normalized)
check(
    "source URL stored as host + hash only",
    test_source_url_is_stored_as_host_and_hash_only,
)
check("logging errors never raise into a scan", test_logging_errors_never_raise)
check("SCAN_LOG=0 writes nothing", test_disabled_log_writes_nothing)
check("stats count humans by kind and tier", test_stats_count_humans_by_kind_and_tier)
check("recent filters by kind / human / text", test_recent_filters_by_kind_and_human)
check("JSONL export writes matching rows", test_export_jsonl_writes_matching_rows)
check("retention keeps human rows longer", test_retention_keeps_human_rows_longer)
check("row cap trims non-human rows first", test_row_cap_trims_non_human_first)

print()
if FAILED:
    print(f"{len(FAILED)} failing: {', '.join(FAILED)}")
    sys.exit(1)
print("All scan-log tests passed.")

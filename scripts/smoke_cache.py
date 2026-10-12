"""Smoke test for the scan cache wiring in server.py (run with the venv python).

Covers: exact-hit reuse, no_cache bypass, fast/deep key separation, and the
/cache/stats + /cache/clear endpoints. Uses Flask's test client, so no port
is opened. DetectZoo absent -> fallback simulation mode, which is fine: we
only assert cache behavior, not verdict quality.
"""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, ".")

# Run against an ISOLATED cache DB. This smoke test calls cache_clear() by
# design ("fresh cache for deterministic counts"), which would otherwise WIPE
# the real cache/scan_cache.db - including any deliberately forced verdicts.
# forensics.scan_cache reads SCAN_CACHE_DIR at import time, so it must be set
# before importing server.
_ISOLATED_CACHE_DIR = tempfile.mkdtemp(prefix="rinse_smoke_cache_")
os.environ["SCAN_CACHE_DIR"] = _ISOLATED_CACHE_DIR

import server  # noqa: E402


def make_jpeg(color, size=64):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (size, size), color).save(buf, format="JPEG")
    return buf.getvalue()


def post_image(client, path, raw, **extra):
    import base64
    payload = {"image_base64": base64.b64encode(raw).decode(), **extra}
    r = client.post(path, data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 200, (path, r.status_code, r.get_data(as_text=True)[:300])
    return r.get_json()


def main():
    # Fresh ISOLATED cache for deterministic counts (see SCAN_CACHE_DIR above).
    assert server.scan_cache.CACHE_DIR == _ISOLATED_CACHE_DIR, (
        "smoke test is not isolated; refusing to touch the real cache"
    )
    server.scan_cache.cache_clear()

    c = server.app.test_client()
    red = make_jpeg((220, 30, 30))

    # 1. Fast path: miss then exact hit.
    v1 = post_image(c, "/predict/image/fast", red)
    assert v1.get("cached") is False, v1.get("cached")
    v2 = post_image(c, "/predict/image/fast", red)
    assert v2.get("cached") == "exact", f"expected exact hit, got {v2.get('cached')}"
    assert v2["score"] == v1["score"], "cached verdict differs from stored one"
    print("PASS fast exact hit (cached=exact, score preserved)")

    # 2. no_cache bypasses reads (but still writes -> clear first).
    server.scan_cache.cache_clear()
    v3 = post_image(c, "/predict/image/fast", red)
    assert v3.get("cached") is False
    v4 = post_image(c, "/predict/image/fast", red, no_cache=True)
    assert v4.get("cached") is False, f"no_cache read the cache: {v4.get('cached')}"
    print("PASS no_cache bypass")

    # 3. fast/deep key separation: a deep scan must not be served the fast scan.
    server.scan_cache.cache_clear()
    post_image(c, "/predict/image/fast", red)
    v5 = post_image(c, "/predict/image/deep", red)
    assert v5.get("cached") is False, f"deep got served fast's entry: {v5.get('cached')}"
    v6 = post_image(c, "/predict/image/deep", red)
    assert v6.get("cached") == "exact", f"deep exact hit failed: {v6.get('cached')}"
    print("PASS fast/deep key separation")

    # 4. Standard /predict alias shares the deep entry (same kind + key).
    v7 = post_image(c, "/predict", red)
    assert v7.get("cached") == "exact", f"/predict alias miss: {v7.get('cached')}"
    print("PASS /predict alias shares deep cache")

    # 5. Stats reflect activity; clear wipes.
    stats = server.scan_cache.cache_stats()
    assert stats["verdicts"] == 2, stats
    assert stats["total_hits"] >= 2, stats
    r = c.get("/cache/stats")
    assert r.status_code == 200 and r.get_json()["verdicts"] == 2, r.get_json()
    c.post("/cache/clear")
    assert server.scan_cache.cache_stats()["verdicts"] == 0
    print("PASS stats + clear")

    print("ALL CACHE SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()

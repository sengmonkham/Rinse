"""Shared plumbing for the dedicated RINSE modality tests.

`tests/test_text.py`, `tests/test_images.py` and `tests/test_videos.py` each run
a corpus through the real detector code and print every score. They share this
module for three things:

* a request client that works two ways - **in-process** (Flask's test client, so
  no server process is needed; the default) or against a **running server**
  (`--live http://localhost:5001`), the same two modes
  `scripts/regression_check.py` and `scripts/eval_local.py` use;
* a uniform result record plus a printer that always prints the scores, so a run
  is readable without opening the JSON;
* JSON persistence of every run (default `tests/media_test_results.json`).

Every scan is sent with `no_cache=true` unless `--use-cache` is passed, so a
reported score reflects the current code rather than a stored verdict.

Assets come from three places:

* the repo corpus that already exists - `tests/calibration_corpus/{ai,real}`
  (images), `test videos/*.mp4` (videos), `demo-samples/texts/*.txt` and the
  StoryScope evasion samples (text);
* the Instagram links already registered in `tests/detector_assets.json`;
* the links registered in `tests/media_test_assets.json`.

Usage (any of the three test files):

    .venv/bin/python tests/test_videos.py
    .venv/bin/python tests/test_videos.py --live http://localhost:5001
    .venv/bin/python tests/test_videos.py --ids ig-DegUdkFAiJd
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_BASE_URL = os.environ.get("RINSE_BASE_URL", "http://localhost:5001")
MEDIA_ASSETS_PATH = os.path.join(ROOT, "tests", "media_test_assets.json")
DETECTOR_ASSETS_PATH = os.path.join(ROOT, "tests", "detector_assets.json")
DEFAULT_RESULTS_PATH = os.path.join(ROOT, "tests", "media_test_results.json")

# Verdict tiers the server can return, split by what the label expects.
AI_TIERS = {"SYNTHETIC_AI", "SUSPICIOUS"}
HUMAN_TIERS = {"AUTHENTIC_HUMAN", "INCONCLUSIVE"}

# Text detectors return a 0-100 AI probability (higher = more AI-like).
TEXT_AI_THRESHOLD = 50

MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif",
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".m4v": "video/mp4", ".mkv": "video/x-matroska",
}


# ---------------------------------------------------------------------------
# HTTP / client
# ---------------------------------------------------------------------------

def http_json(url, payload=None, timeout=900, token=""):
    """POST (or GET) JSON and return (status, body). Errors are returned as
    (0, {"error": ...}) rather than raised, so a bad asset never aborts a run.

    `token` adds ``Authorization: Bearer`` for servers started with API_KEY set
    (the deployed HF Space rejects unauthenticated /predict calls with 401)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if payload is None:
        req = urllib.request.Request(url, headers=headers)
    else:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:  # noqa: BLE001
            return e.code, {"error": body[:400]}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": f"request failed: {e}"}


class Detector:
    """Thin client over the detector endpoints.

    With no base URL the Flask app is imported and driven through its test
    client (no server process, no port). With a base URL every request is a
    real HTTP POST to a running server.
    """

    def __init__(self, base_url: str = "", token: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.token = (token or "").strip()
        self.client = None
        if not self.base_url:
            import server  # noqa: PLC0415  (imports the Flask app + forensics stack)

            self.client = server.app.test_client()

    @property
    def mode(self) -> str:
        return f"live {self.base_url}" if self.base_url else "in-process"

    def post(self, path: str, payload: dict, timeout: int = 900):
        if self.client is not None:
            r = self.client.post(path, json=payload)
            body = r.get_json(silent=True)
            if body is None:
                body = {"error": r.get_data(as_text=True)[:400]}
            return r.status_code, body
        return http_json(self.base_url + path, payload, timeout=timeout,
                         token=self.token)

    def health(self):
        if self.client is not None:
            return self.client.get("/health").get_json(silent=True) or {}
        status, body = http_json(self.base_url + "/health", None, timeout=10,
                                 token=self.token)
        return body if status == 200 else {}


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--live", nargs="?", const=DEFAULT_BASE_URL, default="", metavar="URL",
        help=f"POST to a running server instead of importing the app in-process "
             f"(default when omitted: in-process; bare --live uses {DEFAULT_BASE_URL})")
    parser.add_argument("--key", default=os.environ.get("RINSE_API_KEY", ""),
                        help="Bearer API key for a protected server "
                             "(default: $RINSE_API_KEY; unneeded in-process)")
    parser.add_argument("--ids", default="",
                        help="comma-separated asset ids to run (default: every asset)")
    parser.add_argument("--use-cache", action="store_true",
                        help="allow the server's scan cache (default: no_cache=true, "
                             "so every score is freshly computed)")
    parser.add_argument("--out", default=DEFAULT_RESULTS_PATH,
                        help=f"JSON results file (default: {os.path.relpath(DEFAULT_RESULTS_PATH, ROOT)})")
    parser.add_argument("--timeout", type=int, default=900,
                        help="per-request timeout in seconds for --live runs (default: 900)")


def payload_flags(args) -> dict:
    """Common payload fields for every scan request."""
    return {"no_cache": True} if not args.use_cache else {}


def filter_by_ids(assets: list, ids: str) -> list:
    if not ids:
        return assets
    wanted = {s.strip() for s in ids.split(",") if s.strip()}
    kept = [a for a in assets if a["id"] in wanted]
    missing = wanted - {a["id"] for a in kept}
    if missing:
        print(f"WARNING: unknown asset ids ignored: {sorted(missing)}")
    return kept


# ---------------------------------------------------------------------------
# Corpora
# ---------------------------------------------------------------------------

def load_media_assets(section: str) -> list:
    """Entries from tests/media_test_assets.json for a section (videos/texts)."""
    if not os.path.exists(MEDIA_ASSETS_PATH):
        return []
    with open(MEDIA_ASSETS_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get(section, [])


def load_detector_assets(kind: str) -> list:
    """Entries from tests/detector_assets.json with a given 'kind'."""
    if not os.path.exists(DETECTOR_ASSETS_PATH):
        return []
    with open(DETECTOR_ASSETS_PATH, "r", encoding="utf-8") as f:
        assets = json.load(f).get("assets", [])
    return [a for a in assets if a.get("kind") == kind]


def b64_data_uri(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = MIME_BY_EXT.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


# ---------------------------------------------------------------------------
# Verdict → pass/fail
# ---------------------------------------------------------------------------

def tier_verdict(expected_label: str, tier, tier_expect=None):
    """True/False/None for an image/video verdict against its expected label.

    `tier_expect` (from tests/detector_assets.json) wins when present; otherwise
    'ai' expects a flagged tier and 'human' expects a clean/inconclusive one.
    None means "no expectation" - the score is reported without a pass/fail.
    """
    if tier_expect:
        return tier in set(tier_expect)
    if expected_label == "ai":
        return tier in AI_TIERS
    if expected_label == "human":
        return tier in HUMAN_TIERS
    return None


def text_verdict(expected_label: str, score):
    """True/False/None for a 0-100 text AI-probability against its label."""
    if score is None:
        return None
    if expected_label == "ai":
        return score >= TEXT_AI_THRESHOLD
    if expected_label == "human":
        return score < TEXT_AI_THRESHOLD
    return None


# ---------------------------------------------------------------------------
# Records, printing, persistence
# ---------------------------------------------------------------------------

def make_record(asset_id: str, *, expected: str = "unknown", source: str = "",
                scores: dict | None = None, verdict=None, error: str = "",
                note: str = "", elapsed_s: float = 0.0, extra: dict | None = None) -> dict:
    """One asset's result. `scores` is an ordered name->value map that the
    printer renders verbatim, so every detector's numbers show up in the log."""
    rec = {
        "id": asset_id,
        "expected": expected,
        "source": source,
        "scores": scores or {},
        "verdict": verdict,
        "error": error,
        "note": note,
        "elapsed_s": round(elapsed_s, 1),
    }
    if extra:
        rec["extra"] = extra
    return rec


def _mark(rec: dict) -> str:
    if rec.get("error"):
        return "ERROR"
    if rec.get("verdict") is None:
        return "SCORE"
    return "PASS" if rec["verdict"] else "FAIL"


def _scores_str(rec: dict) -> str:
    parts = []
    for key, value in (rec.get("scores") or {}).items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return "  ".join(parts)


def log_record(rec: dict, reasons: int = 1) -> None:
    """Print one asset's score line as soon as it lands (long video runs
    download and analyze serially, so progress must not be buffered to the end)."""
    mark = _mark(rec)
    line = (f"[{mark:<5}] {rec['id']:<32} expected={rec['expected']:<12} "
            f"{_scores_str(rec)}")
    if rec.get("note"):
        line += f"   # {rec['note']}"
    print(line, flush=True)
    if rec.get("error"):
        print(f"          error: {rec['error'][:400]}", flush=True)
    for reason in (rec.get("extra") or {}).get("top_reasons", [])[:reasons]:
        print(f"          - {str(reason)[:200]}", flush=True)


def print_header(modality: str, n_assets: int, detector: Detector) -> None:
    health = detector.health() or {}
    print(f"\n{'=' * 100}", flush=True)
    print(f"RINSE {modality.upper()} DETECTOR TESTS  ({n_assets} asset(s), client: {detector.mode})",
          flush=True)
    if health:
        print(f"  health: detectzoo_loaded={health.get('detectzoo_loaded')} "
              f"characters_loaded={health.get('characters_loaded')} "
              f"storyscope={health.get('storyscope_available', health.get('mode'))} "
              f"cache={health.get('cache_enabled')}", flush=True)
    print(f"{'=' * 100}", flush=True)


def print_summary(modality: str, records: list, detector: Detector, out_path: str = "") -> int:
    """Print the SCORES recap plus a summary; return a shell exit code."""
    passed = sum(1 for r in records if _mark(r) == "PASS")
    failed = sum(1 for r in records if _mark(r) == "FAIL")
    errored = sum(1 for r in records if _mark(r) == "ERROR")
    scored = sum(1 for r in records if _mark(r) == "SCORE")

    print(f"{'-' * 100}", flush=True)
    print("SCORES")
    for rec in records:
        print(f"  {rec['id']:<32} {_scores_str(rec) or 'no score'}   [{_mark(rec)}]")
    print(f"{'-' * 100}")
    print(f"{modality.upper()}: {passed} passed, {failed} failed, {errored} error(s), "
          f"{scored} score-only  ({len(records)} assets, client: {detector.mode})")

    if out_path:
        saved = save_results(out_path, modality, records, detector.mode)
        print(f"Results written to {os.path.relpath(saved, ROOT)}")
    print(f"{'=' * 100}\n")
    return 1 if (failed or errored) else 0


def save_results(path: str, modality: str, records: list, mode: str) -> str:
    """Merge this run into the results file, keyed by (modality, asset id)."""
    data = {"last_run_at": "", "runs": [], "text": [], "image": [], "video": []}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                data.update(stored)
        except Exception:  # noqa: BLE001
            pass

    by_id = {r["id"]: r for r in data.get(modality, []) if isinstance(r, dict) and "id" in r}
    for rec in records:
        by_id[rec["id"]] = {**rec, "mark": _mark(rec)}
    data[modality] = [by_id[k] for k in sorted(by_id)]

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    data["last_run_at"] = now
    data["runs"] = (data.get("runs") or [])[-19:] + [{
        "at": now, "modality": modality, "client": mode,
        "ids": [r["id"] for r in records],
        "passed": sum(1 for r in records if _mark(r) == "PASS"),
        "failed": sum(1 for r in records if _mark(r) == "FAIL"),
        "errored": sum(1 for r in records if _mark(r) == "ERROR"),
    }]

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return os.path.abspath(path)


def run_main(fn) -> int:
    """Entrypoint wrapper so a failed run reports rather than tracebacking."""
    try:
        return fn()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130

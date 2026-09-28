# Plan: Brainrot Character Recognition + Scan Cache

Status: **PARTIALLY IMPLEMENTED** (2026-09-26) — see “Implementation status” at the bottom. What's live: fingerprints infra + two-of-three matcher + full scan cache (exact + near-dup + admin endpoints), all smoke-tested. What's outstanding: canonical image seeding (§2.2), eval script (§5), rinse-web banner (§4).
Target repo: RINSE (this repo, `server.py` + new support files).
Downstream consumers: `rinse-web` `/scan` page + `/api/scan` proxy (additive response fields only).

---

## 0. Goals

1. **Brainrot character recognition** — when someone scans an image of Tung Tung Tung Sahur, Ballerina Cappuccina, Tralalero Tralala, Bombardiro Crocodilo, Brr Brr Patapim, etc., the detector should say *which* character it is and that it is AI-generated — not just a generic score.
2. **Scan cache** — remember images already scanned (exact files AND near-duplicates) and return the stored verdict instantly, marked as cached.

---

## 1. Where we are today (audited)

### 1.1 Fingerprint matching — `KNOWN_AI_ARTWORK_FINGERPRINTS` (server.py:495)

- **3 entries total**: 2× Tung Tung Tung Sahur stills, 1× AI receipt. No Ballerina Cappuccina or any other brainrot character.
- Each entry: a single 64-bit **dHash**, matched at Hamming distance ≤ 10 of 64 bits.
- On match (`_pixel_forensics_img`, server.py:662): `match_label` is set → the deep path forces `s1["score"] = 99` (server.py:1464) → `fuse_ensemble_verdict` hard-override raises the fused score to ≥ 92 → tier `SYNTHETIC_AI`. **The "tell the user it's AI" escalation already works; what's missing is coverage + identification quality.**
- Video path has a frame-level fingerprint check too (server.py:1070).

### 1.2 No cache anywhere

- No memoization, no dedup: every request re-decodes the image, re-fetches URLs, and re-runs the neural layer (the slow one).
- Helpers that the plan reuses: `_dhash(img)` (server.py:476), `_hamming`, and `raw_bytes` is already loaded in both image paths (server.py:1244 `_load_image_from_payload`), so an exact-content hash is nearly free.

---

## 2. Brainrot character recognition

### 2.1 New fingerprints directory + manifest

```
RINSE/
├─ fingerprints/
│  ├─ manifest.json              # character metadata (name, label, source URLs, notes)
│  └─ canon/                     # canonical reference images, one file per hash entry
│     ├─ ballerina-cappuccina/
│     │  ├─ cover.jpg
│     │  ├─ still-01.png … still-05.png
│     └─ tung-tung-sahur/ …
└─ scripts/
   ├─ build_fingerprints.py      # hashes everything in canon/ → regenerates fingerprints/db.py
   └─ eval_fingerprints.py       # measures false-positive rate on real photos + detection rate on variants
```

- `manifest.json` per character: `{ id, label, source: "italian-brainrot", ai_generated: true, refs: [filenames], added_at }`.
- `scripts/build_fingerprints.py` computes, per reference image: **dHash + pHash + aHash** (64-bit each) and emits `fingerprints/db.py` (a generated dict, same shape as today's, plus per-entry hash triplets). Generated file → committed, so the server never needs to hash at boot.

### 2.2 Character set to seed (initial ~12)

Tung Tung Tung Sahur (multiple stills — highest priority, already partial), Ballerina Cappuccina, Tralalero Tralala, Bombardiro Crocodilo, Brr Brr Patapim, Lirili Larila, Chimpanzini Bananini, Cappuccino Assassino, Girafa Celestre, Bombombini Gusini, Frigo Camelo, Trippi Troppi. 4–8 canonical views each (cover art, common meme stills, TikTok frames) — brainrot images circulate as recompressed screenshots, so **multiple views per character matters more than hash sophistication**.

### 2.3 Matching upgrade (server.py changes)

Replace the single-dHash ≤ 10 loop with a small matcher module (new `forensics/characters.py`):

1. Compute the query's dHash/pHash/aHash once.
2. Linear scan over the generated DB (hundreds of entries — linear is fine, <1 ms; no BK-tree needed yet).
3. **Two-of-three hash agreement**: dHash ≤ 10 AND (pHash ≤ 12 OR aHash ≤ 10) → confirmed match. This kills the main failure mode of dHash-only matching on flat/white images (dHash of any near-blank region collides easily), which matters because the match hard-forces a 99.
4. **Center-crop fallback** for fan edits/memes where the character sits on a busy background: also hash the central 60% crop at two scales, match those too. (Brainrot memes are usually full-frame character art, so this is a fallback, not the default.)
5. Return structured data instead of a bare label:

```python
{
  "match": "ballerina-cappuccina",
  "label": "Ballerina Cappuccina (viral AI-generated brainrot character)",
  "distance": {"dhash": 4, "phash": 7},
  "match_strength": "exact"   # exact: dHash ≤ 6 · likely: ≤ 10 + agreement · weak: > 10
}
```

### 2.4 Response contract (additive, non-breaking)

- `verdict.character_match` = the object above (or absent). `match_label` string stays for backward compatibility (extension + web).
- Reasons line becomes: `"Known AI-generated character: Ballerina Cappuccina (perceptual fingerprint match, d=4)."`

### 2.5 UX copy downstream (rinse-web, tiny change)

`/scan` result card: when `character_match` is present, show a distinct banner —
**"Known AI-generated character: Ballerina Cappuccina"** — above the normal score dial, instead of relying on the generic SYNTHETIC_AI tier text.

---

## 3. Scan cache

### 3.1 Design: SQLite (stdlib) — two lookup layers

No new dependencies (`sqlite3` is stdlib). One DB file, `cache/scan_cache.db` (gitignored), WAL mode.

```sql
-- Layer 1: exact-content verdicts
CREATE TABLE verdicts (
  sha256            TEXT PRIMARY KEY,     -- of raw image/video bytes
  kind              TEXT NOT NULL,        -- 'image' | 'video'
  pipeline_version  TEXT NOT NULL,        -- cache busts when the pipeline changes
  verdict           TEXT NOT NULL,        -- full JSON response
  created_at        REAL NOT NULL,
  last_hit_at       REAL,
  hits              INTEGER DEFAULT 0
);
CREATE INDEX idx_verdicts_last_hit ON verdicts(last_hit_at);

-- Layer 2: near-duplicate bridge (dHash → exact hash of the stored original)
CREATE TABLE near_keys (
  dhash       INTEGER NOT NULL,           -- 64-bit dHash as int
  sha256      TEXT NOT NULL REFERENCES verdicts(sha256) ON DELETE CASCADE,
  PRIMARY KEY (dhash, sha256)
);
```

- **Pipeline version string**: hash of the fused-weight constants + fingerprint DB build id + neural model name — bumped automatically when any of those change, so stale verdicts never resurface after detector upgrades.

### 3.2 Lookup flow (image deep path)

1. Compute `sha256(raw_bytes)` → **exact hit?** return stored verdict + `"cached": "exact"`.
2. Compute dHash (already computed for fingerprints — zero extra cost) → `near_keys` lookup, verify Hamming ≤ 6 against candidates → **near hit?** only reuse if the cached verdict was *decisive* (`tier` SYNTHETIC_AI / AUTHENTIC_HUMAN with HIGH confidence — conservative on purpose) → return + `"cached": "near"`.
3. Miss → run pipeline → store verdict + dHash → return + `"cached": false`.

Same flow for `image/fast`. Video: exact-hash only (near-dup on video is out of scope — temporal hashes are window-dependent).

### 3.3 Source-fetch cache (URL inputs)

`fetches` table: `sha256(url-canonical) → raw bytes, fetched_at`, TTL 24 h. Avoids re-downloading the same meme 50×/day and makes repeat scans of a URL hit layer 1. Size-capped per row (20 MB image / 150 MB video as today).

### 3.4 Policies

- **TTL**: 30 days for verdicts, 24 h for fetched bytes. Enforced lazily on read (no cron).
- **Decisive-only reuse**: near-dup hits only return cached *decisive* verdicts; anything UNCERTAIN/INCONCLUSIVE re-runs. Exact hits always return cached (same bytes, same pipeline version → same result, no reason to recompute).
- **Concurrency**: Flask threaded + SQLite WAL → one connection per request with `timeout=5`, no global lock needed at our scale.
- **Eviction**: lazy LRU — after insert, if row count > 50k, delete oldest `last_hit_at` beyond cap. Cached bytes dir capped at ~1 GB with the same policy.
- **Bypass**: `{"no_cache": true}` in the request body skips reads (still writes) — for evals and A/B of the pipeline.
- **Admin**: `GET /cache/stats` (hits/misses/rows/bytes, auth'd like the rest) and `POST /cache/clear`.

### 3.5 Response contract (additive)

Top-level on image/video verdicts: `"cached": false | "exact" | "near"`, plus `"cache_age_s"` and, for near hits, `"similar_to": "<sha256>"`. Downstream can ignore all of it.

---

## 4. rinse-web side (small, additive)

- `/api/scan` proxy: no logic changes — JSON passes through; both new fields ride along.
- `/scan` UI: (a) character-match banner (§2.5), (b) subtle "served from cache" note when `cached` is truthy.

---

## 5. Evaluation & safety

- `scripts/eval_fingerprints.py`:
  - **Detection set**: the 12 characters × recompression variants (JPEG q60/q85, 320px/720px resizes, screenshot-with-UI-overlay) → target ≥ 95% identified at `match_strength` ≥ likely.
  - **False-positive set**: ≥ 500 real camera photos (any public set) + `demo-samples/images` → target **zero** false matches (a match forces a 99, so FPs are expensive). The two-of-three agreement rule + decisive-only cache reuse are the guards.
  - Tune thresholds here once; do not tune by vibes.
- Cache integration test (Flask test client): same bytes twice → 2nd response `cached: "exact"`; recompressed variant → `cached: "near"` when decisive; pipeline-version bump → miss.

---

## 6. Rollout order (steps 1, 3, 5, 6 done — see §8)

1. `fingerprints/` infra + `build_fingerprints.py` + manifest (mechanical, no behavior change).
2. Seed the 12 characters' canonical views.
3. `forensics/characters.py` matcher (two-of-three + structured match) wired into `_pixel_forensics_img` and the video frame path; keep `match_label` for compat.
4. Eval + threshold tuning (§5) — gate for everything else.
5. Cache: exact-hash layer + stats endpoints.
6. Near-dup layer + fetch cache.
7. rinse-web: banner + cache note.

Steps 1–3 alone deliver the user-visible brainrot behavior; 5–6 deliver the speedup. Nothing in this plan changes the fused-score math except through the already-existing fingerprint-override path.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| dHash FP on flat images forces a false 99 | Two-of-three hash agreement; `match_strength` reported; eval gate before rollout |
| Meme variants drift from canonical art | 4–8 views/character incl. TikTok-frame stills; center-crop fallback; weak matches reported but never silently escalate |
| Cache returns stale verdicts after detector upgrades | `pipeline_version` column busts automatically; TTL 30 d; `no_cache` escape hatch |
| Near-dup reuse amplifies a wrong verdict | Decisive-only reuse policy |
| Character names/copyright | Labels are descriptive ("viral AI-generated meme character"); manifest keeps source attribution |

---

## 8. Implementation status (2026-09-26)

### Done and verified

| Plan item | Where | Notes |
|---|---|---|
| §2.1 fingerprints infra | `fingerprints/manifest.json` (12 characters), `fingerprints/legacy_seeds.json`, `scripts/build_fingerprints.py` → `fingerprints/db.py` | dHash byte-identical to legacy `_dhash` (verified on 20 synthetic images); canon/ dirs not yet seeded → db currently holds the 3 legacy entries only |
| §2.3 matcher | `forensics/characters.py` `match_character()` | two-of-three rule (dHash ≤ 6 + pHash ≤ 12 / aHash ≤ 10 → exact; dHash 7–10 + both → likely; legacy seeds keep historical ≤ 10), center-crop fallback (60 % / 36 % area, capped at "likely"), structured `{match, label, ref, distance, match_strength}`; no FPs on flat/white test images |
| §2.4 wiring | `server.py` `_pixel_forensics_img` returns `character_match`; fast + deep paths thread it into `extra_data`; fast path escalates on exact/likely | legacy `match_label` compat kept; falls back to legacy loop when DB unavailable |
| §3.1 cache core | `forensics/scan_cache.py` | SQLite stdlib, WAL, piecewise dHash index (8×byte pigeonhole) instead of the plan's single near_keys table (scales to 50 k rows), `pipeline_version()` = hash of voter.py + fingerprint build + MODEL_NAME |
| §3.2 lookup flow | `server.py` `_cache_lookup_or_run()` wrapped around **fast**, **deep** (`/predict` aliases included) and **video deep** | exact always; near-dup ≤ 6 decisive-only; fresh runs tagged `"cached": false`; cache key = sha256(namespace‖bytes) with namespaces `image:fast` / `image:deep` / `video:deep` so scan depths never cross-contaminate (found + fixed during smoke tests) |
| §3.2 video | `_cached_video_deep` / `_video_cache_bytes` | exact-key only, key derived from payload (video_base64 / video_url / frames) so an exact hit skips the download+decode entirely; no near-dup layer |
| §3.4 admin | `GET /cache/stats`, `POST /cache/clear`, `/health` now reports `characters_loaded` + `cache_enabled` | auth-gated like other endpoints |
| §3.4 policies | TTL 30 d verdicts / 24 h fetches, lazy LRU 50 k, `no_cache: true` bypass, decisive-only reuse | all in scan_cache.py + helper |
| §5 cache integration test | `scripts/smoke_cache.py` | exact hit, no_cache bypass, fast/deep key separation, /predict alias sharing, stats + clear — **all passing**; video error paths return clean JSON (`cached: false` on errors) |

### Implementation notes / deviations from plan

- Cache key namespaces (`image:fast` vs `image:deep`): the plan didn't specify, but the first smoke run showed a deep request being served a stored fast verdict. `kind` stays `image`/`video` for the SQL near-dup layer, which deliberately still matches across depths (decisive-only makes that safe).
- Temp-file cleanup had to move to the endpoint level (fast + deep): on a cache hit the closure never runs, so a cleanup `finally` inside the closure would leak the temp file.
- `no_cache` responses (and cache-disabled fallback) always carry `"cached": false` rather than omitting the field, so downstream can rely on the key's presence.

### Still open

1. **§2.2 canonical image seeding** — `fingerprints/canon/<character>/` for the 11 non-tung characters (needs source images; time-boxed in plan). Only legacy seeds live today.
2. **§5 `scripts/eval_fingerprints.py`** — FP gate before trusting "exact" escalation on the new matcher.
3. **§4 rinse-web** — `/scan` character banner + "served from cache" note (types need `character_match` + `cached` fields).
4. §3.5 `cache_age_s` field (minor, not yet exposed).

# Rewriting the RINSE detector server in Rust

**Status:** plan only — nothing in this document is built yet. It is written to
be copied as the seed README of the new `rinse-detector-rs` repo.

**Reference:** [`arjaythedev/twelve-dollar-server-challenge` →
`submissions/rust-iouring-kensac`](https://github.com/arjaythedev/twelve-dollar-server-challenge/tree/main/submissions/rust-iouring-kensac)
— **310,000 users / 29,284 req/s** on 1 vCPU / 2 GB, p95 62 ms, p99 190 ms,
82% CPU, 25 µs/req, 1,114 MB RSS (leaderboard row 1, 2026-11-02).

---

## 1. Executive summary

The reference is a **CRUD** server: every request is a JWT check, one SQLite
lookup and a hand-written JSON response. Ours is a **compute** server: the same
edges (auth, quota, cache, log, JSON) wrapped around a detector that costs
0.5 ms to 3.5 s of CPU per request, depending on mode.

So the rewrite splits cleanly:

1. **The edge moves to Rust and copies the reference's playbook** — one
   io_uring event loop (with an epoll/tokio fallback), hand-rolled HTTP/1.1,
   hand-rolled JSON, fixed buffers, multishot receive, provided buffers, WAL +
   group commit, checkpoints on a nice-19 thread. This is where 29k rps lives.
2. **Compute does not become 29k rps, and no rewrite can make it so.** At a
   measured 3.1 s per cold image scan, one core serves ~0.3 image scans/s.
   The rewrite's compute goal is *scheduling and fairness*: keep the edge
   responsive (p99 on cached/text/health traffic) while a bounded worker pool
   grinds through inference, with admission control and honest 503s instead of
   a GIL-shaped pile-up.
3. **State moves into the Rust process**: the scan cache, the scan log and
   admission counters, in the same SQLite file family, written in batches per
   event-loop tick, exactly like the reference's group commit.

Target after all phases, on the $12 box:

| path | today (measured, dev Mac ratios) | after |
|---|---|---|
| `/health`, auth, 404s, quota refusals | ~0.1 ms but thread-locked | 20–40 µs, non-blocking |
| cached image/video verdict | 1.2–1.5 ms (Python) | 30–60 µs, ~20k rps |
| text DNA scan | 0.5 ms | 25–60 µs if ported, ~15–30k rps |
| StoryScope (heuristic) | 4.2 ms | 0.5–1.5 ms if ported |
| cold image scan | 3.1–3.5 s | ~1.5–3 s (ONNX), 0.3–0.6/s per core |
| idle keep-alive connections | Werkzeug thread each | ~150–250k in ~40 MB |

---

## 2. What the reference actually does

| | |
|---|---|
| Language / runtime | Rust 1.94, **no framework** |
| I/O | `io_uring` (Linux 6.1+), `DEFER_TASKRUN`, `SINGLE_ISSUER`, multishot receive, provided-buffer rings, direct (ring) descriptors |
| DB | SQLite 3.54.1 amalgamation, linked in statically, `-O3 -march=native` |
| Networking | Serves `0.0.0.0:80` directly (no Nginx); 8 × `SO_REUSEPORT` listeners |
| Code | `main.rs` 741, `db.rs` 485, `json.rs` 558, `app.rs` 263, `jwt.rs` 191, `http.rs` 89, `shim.c` 487 |
| Score | 310,000 users held 5 min, 29,284 req/s, p95 62 ms, p99 190 ms, 0 errors |

The techniques, and whether they transfer to us:

| # | Technique | Transfers? | Our version |
|---|---|---|---|
| 1 | One thread owns the event loop; everything is non-blocking | **Yes, for the edge** | Edge loop in Rust; compute is a separate bounded worker pool |
| 2 | Multishot receive into a provided-buffer ring (idle connection holds no buffer) | **Yes** | Same; we have more idle sockets than the challenge (extension beacons, plus web) |
| 3 | Direct descriptors + sharded rings + 8 reuseport listeners | **Yes** | Same, with a per-ring fd budget; `LimitNOFILE=65535` and graceful ring growth |
| 4 | Hand-written HTTP/1.1 + JSON, no framework, back-filled `Content-Length`, no chunked | **Yes** | Same. Our bodies are small (verdict JSON < 8 KB) except image/video uploads |
| 5 | Every event-loop pass = one SQLite transaction; responses held until COMMIT | **Yes** | Cache writes + log rows + admission counters commit per tick; a 200 never claims an uncommitted log row |
| 6 | Checkpoints off-loop on a nice-19 thread; writes paused during catch-up | **Yes** | Same; the log DB grows continuously, so this matters more for us |
| 7 | Read SQLite B-tree records directly, skipping the SQL VM | **No (adapted)** | Our hot lookups are one primary-key hit (`cache`) and one insert (`log`). Measure first: prepared statements may already be within 5–10 µs; don't write 500 lines of record decoding without a profile |
| 8 | JWT verified with prehashed HMAC blocks, constant time | **Yes (adapted)** | We use a shared Bearer `API_KEY`: `hmac::verify_slice` constant-time compare, no parsing |
| 9 | `unix-excl` VFS, one connection for the loop + one for checkpoints, `THREADSAFE=2` | **Yes** | Same two-connection split; worker processes never touch the DB |
| 10 | No caching of request data (challenge rule) | **No** | Verdict caching is a product feature; we keep it and make it faster |
| 11 | No epoll fallback (refuses to start on Docker default seccomp) | **No** | We need a fallback: Render/HF containers may block `io_uring`. Ship `tokio`/`epoll` runtime behind the same interfaces and pick at boot |

---

## 3. Our baseline, measured

Measured in-process on the dev machine (M-series Mac), so treat these as
**ratios**, not droplet numbers. The point is the shape of the distribution.

| Endpoint | Mode | p50 | Notes |
|---|---|---|---|
| `GET /health` | — | 0.1 ms | pure CPU/JSON |
| `POST /predict/text/dna` | text | **0.5 ms** | 168-char sample, pure Python |
| `POST /predict/storyscope` | text | **4.2 ms** | 360 chars, 204/304 features, heuristic engine |
| `POST /predict/image/fast` | image | **3,098 ms** | 512×512 JPEG, warm model, cache off |
| `POST /predict/image/deep` | image | **3,455 ms** | all 6 image layers |
| `POST /predict/video/deep` | video | **2,007 ms** | 8 frames @ 320×180 |
| cached image (exact or near-dup) | image | **1.2 ms** | the cache is doing the real work |

Other facts that shape the plan:

- **Production runs `python server.py` → `werkzeug.serving.run_simple(threaded=True)`** — the development server, one process, one GIL, a thread per connection. Every image scan blocks a thread for seconds.
- RSS after loading `cnnspot` (282 MB weights) + torch: **~1.05 GB**. On a 2 GB box that is one worker, not four.
- Code: `server.py` 2,906 lines; detectors `forensics/*.py` ~2,970 lines (voter 1,065, neural 280, spai 456, frequency 200, ai_metadata 599, c2pa 159, synthid 106), `storyscope/heuristic.py` 2,659 lines, `storyscope/dna_detect.py` 350 lines, XGBoost reader `storyscope/scorer.py` 124 lines.
- State today: two SQLite files (`cache/scan_cache.db` via a 347-line module, `cache/scan_log.db` via a 545-line one), and per-user quota lives in the **web** repo's Postgres — the detector only sees a shared API key.

### The ceiling math (why 29k rps is the wrong target for scans)

```
cold image scan     3.1 s/req   →  0.32 scans/s per core   (1 core = ~19/min)
cold video scan     2.0 s/req   →  0.50 scans/s per core
text DNA            0.5 ms/req  →  2,000 req/s per core (Python), ~30k ported
cached verdict      1.2 ms/req  →    830 req/s per core (Python), ~20k in Rust
health/refusals    0.1 ms/req   → 10,000 req/s per core (Python), ~40k in Rust
```

A 1 vCPU box therefore holds ~**300k idle connections** (the reference's result
is mostly a socket-memory result) and a few **cold scans per second**. The
rewrite's real wins are: (a) connections and tiny requests stop paying Python
thread+GIL costs, (b) cached and text traffic gets 20–50× cheaper, (c) cold
inference gets a fair, bounded queue instead of starving the process, and (d)
memory drops enough to fit a second worker or a bigger model.

---

## 4. Goals and non-goals

**Goals**

1. `p99 < 50 ms` for `/health`, auth failures, quota refusals and cache hits at 5,000 rps on 1 vCPU.
2. `p99 < 400 ms` end-to-end for uncached **text** scans at 1,000 rps (after the Rust text port).
3. Cold image/video scans: no p99 regression vs today, plus honest backpressure (`503` + `Retry-After`) instead of unbounded queueing.
4. Support ≥ 100k idle keep-alive connections in < 100 MB RSS for the edge process.
5. Total host memory fit: edge (≤ 100 MB) + one Python/ONNX worker (≤ 1.2 GB) inside 2 GB with headroom.
6. Byte-identical responses vs today for every documented case (verdict JSON, error bodies, status codes) — enforced by a golden-fixture suite.

**Non-goals**

- Reaching 29k rps on cold scans. Physically impossible at these model costs; anyone claiming otherwise is measuring cache hits.
- Rewriting the web app's quota/Postgres logic. The detector keeps its own admission counters; per-user quotas stay where the users are.
- Replacing torch/SQLite/ffmpeg with something "faster" before profiling says they matter.
- Micro-optimising the HTTP parser before the compute path stops dominating (Phase 1 measures; Phase 5 optimises).

---

## 5. Target architecture

```
                    ┌──────────────────────────── rinse-rs (one process) ───────────────────────────┐
  15k–300k          │  io_uring loop (or epoll fallback)                                           │
  keep-alive ──────▶│    accept → multishot recv → parse head/body → route                        │
  connections       │      ├─ /health, 404, 401, 429        → respond from static buffer          │
                    │      ├─ cache hit (image/video/text)  → SQLite read → respond                  │
                    │      ├─ admit/reject (API key, per-IP, queue depth) → 429/503                  │
                    │      ├─ text scan                     → in-process text engine (Phase 3)       │
                    │      └─ image/video scan              → submit frame to worker ring            │
                    │    per-tick: COMMIT (log rows + cache writes + counters) → then flush sends     │
                    │  second thread: PASSIVE checkpoint (nice 19)                                    │
                    └───────────────┬───────────────────────────────┬──────────────────────────────┘
                                    │ length-prefixed frames        │ mmap'd scratch arena
                                    ▼                               ▼
                    ┌───────────────────────────────┐   ┌──────────────────────────────────┐
                    │ worker-0 … worker-N           │   │ state (SQLite)                    │
                    │ Rust+ORT (Phase 4) or Python   │   │  cache/scan_cache.db  (WAL)       │
                    │ torch (Phase 1–3 fallback)     │   │  cache/scan_log.db    (WAL)       │
                    │ ffmpeg for video               │   │  cache/admission.db   (WAL)       │
                    └───────────────────────────────┘   └──────────────────────────────────┘
```

**Runtime choice.** Build on `tokio` (mio/epoll) for the first two phases —
Render and Hugging Face containers can block `io_uring` via seccomp, and the
edge must boot everywhere. Put the io_uring backend behind a compile-time
feature (`--features uring`) and select at boot: `uring` if
`io_uring_setup` succeeds, otherwise `epoll`. Same trait, same buffers. Copy the
reference's ring design (sharded rings, direct descriptors, multishot,
provided buffers) only in the `uring` backend, and the connection-budget logic
(1/8 margin before switching rings) verbatim — it is the part that makes 300k
connections work.

**Why a worker process instead of in-process threads for torch.** torch's
GIL-bound Python layers and 1 GB RSS do not belong in the edge's address
space. One UDS socket pair, length-prefixed framing: a 24-byte header
(`mode:u8`, `flags:u8`, `len:u32`, `id:u64`, `deadline_ms:u32`, pad) then the
payload. Images go through a preallocated `mmap` arena so a 20 MB upload is
copied once, not three times.

**Backpressure.** A semaphore of `workers × 2` in-flight compute jobs.
Beyond it: `429` with `Retry-After: 1` for scans (not 503 — the caller is a
user action, not a probe). Per-IP token bucket at the edge (the reference has
no equivalent; ours is needed because every scan costs real CPU).

---

## 6. State: what SQLite does in the new server

Keep the schema. It is two small tables plus the existing verdict cache; the
rewrite changes *how* they are written, not what they contain.

- **One connection for the loop, one for checkpoints** (`THREADSAFE=2`,
  `unix-excl` VFS, WAL, `synchronous=NORMAL`, `wal_autocheckpoint=0`).
- **One transaction per event-loop tick.** Cache inserts + scan-log rows +
  admission counters commit together; responses that depend on a commit
  (a `201`-style "scan recorded" contract, quota spend) are held until COMMIT
  returns, and become `500` + connection close if it fails. This is rule 6 of
  the challenge applied to our semantics: never report a scan that was not
  logged and charged.
- **Checkpoint thread.** Wake at ≥ 4,096 WAL frames (~16 MB), PASSIVE
  checkpoint, nice 19. Log retention (`maintain()`) runs on the same thread so
  it never blocks the loop.
- **Prepared statements** reused per connection; no SQL string building.
- **B-tree fast path only if profiling justifies it.** Start with prepared
  statements (likely 5–15 µs for our 3–4 statements/request); revisit the
  reference's record-decoding trick (`csrc/shim.c`) only for the cache-hit read
  if it shows up in the profile.
- **Failure semantics we keep from today:** quota is spent only after the
  detector answers; a detector failure refunds; the log row records the status
  (including 5xx) and is written in the same commit as the refund.

---

## 7. Work plan

Each phase is shippable on its own (strangler pattern: the Rust edge proxies
anything it does not own yet to today's Flask app). Every phase has an exit
gate; do not start the next one until the gate is measured.

### Phase 0 — Freeze the contract and build the harness (2–3 days)

- Export a golden-fixture suite from today's server: every endpoint ×
  (success, every documented error), with exact bytes. ~120 cases. Includes
  the text verdicts for 12 corpus samples, 8 images, 4 videos (verdicts compared
  with tolerance on scores, exact on status/labels/keys).
- Stand up the $12-equivalent box (DigitalOcean 1 vCPU / 2 GB, Ubuntu 24.04)
  and a k6 (or `wrk2`) workload that reflects *our* traffic, not the challenge's:
  70% text scans, 20% cached media hits, 8% cold image, 2% cold video, plus a
  keep-alive ramp to 100k idle connections.
- Record baseline: p50/p95/p99, rps per mode, CPU, RSS, cache hit rate.

**Gate:** fixtures green on the current server; baseline numbers committed to
`benches/results/baseline.json`.

### Phase 1 — Rust edge, Python compute (1–1.5 weeks)

- `crates/edge`: accept loop, HTTP/1.1 parser (headers capped at 16 KB, bodies
  at 25 MB for images, no chunked), JSON writer with back-filled
  `Content-Length`, constant-time Bearer check, routing, static `/health`.
- Proxy for `/predict/*` to a Python worker over UDS; strip Flask from the
  worker (keep the detector functions untouched), add a warmup probe and a
  fixed worker pool.
- Connection budget: fd limit raise, per-connection state ≤ 64 bytes, idle
  timeout 75 s (longer than any LB's), no per-connection allocation when idle.

**Gate:** 100k idle connections in < 120 MB RSS; `/health` p99 < 5 ms at 10k
rps; cold-scan p99 within 5% of baseline through the proxy.

### Phase 2 — State moves into Rust (1 week)

- Cache read/write and scan log in `crates/state` (WAL, group commit,
  checkpoint thread, retention). Port `scan_cache.py` and `scan_log.py`
  semantics 1:1 — same tables, same TTLs, same near-dup policy (decisive
  verdicts only, Hamming ≤ 6), same log columns.
- Job protocol + admission control (semaphore, per-IP token bucket, queue
  deadline). Refusal bodies byte-identical to today.
- Delete the SQLite code from the Python worker; it may only compute.

**Gate:** cache-hit p99 < 2 ms at 5k rps; log rows and quota spend match the
old server for a replayed fixture run; `kill -9` during a write loses no
acknowledged row (`integrity_check` ok) — same test the reference reports.

### Phase 3 — Text detectors in Rust (2–3 weeks)

Port, in this order, each gated by fixture parity:

1. **DNA-DetectLLM** (350 lines, pure statistics) — expected 25–60 µs/scan.
2. **StoryScope heuristic** (2,659 lines; 304-feature taxonomy, 204 extracted
   in heuristic mode) — port `heuristic.py` + `taxonomy.py`, and read the same
   XGBoost model (`scorer.py` 124 lines) with a native tree walker.
3. Keep the LLM StoryScope mode as-is (async HTTP to the provider), proxied.

Parity rule: same label/tier for every corpus sample, score within ±1 point
(floating-point summation order differs). If parity fails, ship the Python
implementation behind the same Rust trait and move on — no accuracy trade for
speed.

**Gate:** 1,000 rps text mix at p99 < 50 ms on 1 vCPU; fixtures green.

### Phase 4 — Media compute (2–4 weeks, largest risk)

- Export `cnnspot` (282 MB `.pth`) to ONNX, run through `ort` (CPU, 1 intra-op
  thread on the $12 box, AVX-512 on the reference hardware). Validate score
  parity on the image corpus (±2 points) before switching.
- Port the cheap layers (C2PA/metadata, frequency, SPAI, character
  fingerprints) to Rust with `image`/`ndarray` — these are the parts that run
  in single-digit ms; keep them off the worker queue and answer inline.
- Video: keep ffmpeg as a subprocess, port the temporal/PwTF math last, behind
  the same fixture gate. Video stays the slowest path; that is acceptable.
- Memory gate: worker RSS ≤ 1.2 GB with ORT, ≤ 1.4 GB with torch fallback.

**Gate:** image fast-path p50 ≤ 40% of baseline on the same box; deep path
within 10%; memory inside budget.

### Phase 5 — Scale and tune (1 week)

- io_uring backend (multishot, provided buffers, sharded rings, 8 reuseport
  listeners), A/B against epoll on the same box.
- Allocator (`mimalloc`), buffer pools, zero-copy sends, `TCP_NODELAY` policy,
  `SO_REUSEPORT` hashing, per-ring accept margins.
- Profile-guided pass: attack whatever the flame graph says, not what the
  reference's README brags about.

**Gate:** ≥ 2× the Phase-1 connection count at the same RSS; no regression on
any earlier gate.

### Phase 6 — Cutover (2–3 days)

- Deploy side-by-side on Render (edge) + worker container; 10% traffic → 50%
  → 100% with the golden fixtures replayed against both.
- Keep the Flask image runnable for one release as a rollback target.
- Dashboards: per-mode p50/p95/p99, queue depth, admission refusals, cache hit
  rate, WAL size, checkpoint duration, worker RSS.

**Gate:** one week at 100% with no fixture drift, no p99 regression, and fewer
than 0.1% 5xx.

---

## 8. New repo layout

```
rinse-detector-rs/
├── Cargo.toml                     # workspace, pinned versions
├── crates/
│   ├── edge/                      # accept, rings, http.rs, json.rs, auth.rs, router.rs
│   ├── state/                     # sqlite: cache, scan_log, admission, group commit, checkpoint
│   ├── text/                      # dna, storyscope (features + xgboost reader)
│   ├── media/                     # image decode, c2pa, frequency, spai, ort, ffmpeg
│   ├── verdict/                   # voter / tier bands / confidence (port of forensics/voter.py)
│   └── proto/                     # worker framing, deadlines, error codes
├── pyworker/                      # torch fallback worker (detectors unchanged, Flask removed)
├── tests/golden/                  # fixtures exported from the current server
├── benches/                       # k6 scripts, corpus, runner, results/
├── deploy/                        # Dockerfile, systemd unit, nginx.conf (optional), .env.example
└── README.md                      # this document, updated with real numbers
```

Rules carried over from the challenge that are worth keeping as house rules:

- Pin every dependency; build from source; no prebuilt binaries.
- One README table of measured results per phase, on the same box, reproducible
  with `benches/run.sh`.
- No "optimisation" without a profile line and a fixture run.

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| ONNX/torch numeric drift changes tiers near band edges | Verdicts shift; product trust | Fixture corpus with tolerance (±2 score) + per-tier boundary cases; ship Python fallback behind the same trait |
| `io_uring` blocked in Render/HF containers | Won't boot | epoll/tokio backend is the default; uring is a feature flag chosen at boot |
| 2 GB box cannot hold edge + ORT + torch during migration | OOM kills | Run one compute runtime at a time; memory gate in CI; canary with RSS alarm |
| Porting 2.6k lines of StoryScope introduces silent feature bugs | Wrong verdicts | Port feature-by-feature with a diff harness (`features_extracted` and per-dimension values compared to Python) |
| Queueing makes cold scans slower in exchange for fast cache hits | User-visible p99 | Deadline per job, `429` + `Retry-After` past the queue limit, and a measured admission policy, not a guess |
| Scan log DB grows faster than retention keeps up | Disk/WAL pressure | Retention on the checkpoint thread (already implemented); WAL frame threshold alarms |
| Reference's no-fallback, no-framework choices copied blindly | Maintenance cost | Only copy techniques that survive our own profile; document each one with the measurement that justified it |

---

## 10. Open questions for the owner

1. **What is the real traffic mix?** Cache hit rate and the cold-scan share decide whether the edge rewrite is worth 1 week or 5. Phase 0 answers this from the new scan log (`human_likely`, `cached`, `kind`, `latency_ms` are recorded).
2. **Must the detector stay single-tenant behind one `API_KEY`?** Per-user keys would let the edge enforce quotas the way the web app does, and remove a Postgres round trip from the scan path.
3. **Is torch required, or will ONNX be the single runtime?** One runtime halves memory and simplifies the worker.
4. **Does the LLM StoryScope mode need to survive the rewrite?** It is an HTTP call, so it can stay Python and async — but it changes the worker's shape.
5. **Where does this run long term — the $12 VPS or Render?** io_uring, disk persistence and the memory budget all differ.

---

## Appendix A — Reference numbers used above

From `LEADERBOARD.md` (2026-11-02), submission scored at PR #264 `4298101`:

| metric | value |
|---|---|
| users held (5 min) | 310,000 |
| throughput | 29,284 req/s |
| p95 | 62 ms |
| p99 | 190 ms |
| errors | 0.00% |
| CPU | 82% |
| per request | 25 µs |
| RSS | 1,114 MB |

## Appendix B — How to reproduce our baseline

```bash
cd /path/to/RINSE
.venv/bin/python - <<'PY'   # in-process timings, cache off
import base64, io, time, statistics
import server
from PIL import Image
c = server.app.test_client()
# …build a 512×512 JPEG + 8 frames, then time each endpoint, see §3.
PY
```

For the droplet number, run the same against `python server.py` with
`SCAN_CACHE=0` and `bench/`'s k6 mix (Phase 0 builds it).

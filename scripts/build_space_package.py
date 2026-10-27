"""Stage the RINSE Hugging Face Space package into deploy/space_stage/.

Copies the real backend sources into the Space staging directory alongside
the deployment template files (app.py / README.md / requirements.txt /
packages.txt), bakes the DetectZoo weights into the package, then
byte-compiles every staged .py file so a syntax error never reaches the
Space build.

Usage:  .venv/bin/python scripts/build_space_package.py
"""

from __future__ import annotations

import py_compile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "deploy" / "space_stage"

# The real backend: single-file Flask server + the forensic layers + the
# character-fingerprint DB + the local StoryScope package. The Space template
# files (app.py, README.md, requirements.txt, packages.txt) live directly in
# deploy/space_stage/ and are git-tracked there - this script refreshes the
# backend sources and bakes the model weights.
COPY_ITEMS = [
    ("server.py", "server.py"),
    ("forensics", "forensics"),
    ("fingerprints", "fingerprints"),
    ("storyscope", "storyscope"),
]

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", "cache"}

# Model weights DetectZoo would otherwise download on the first boot of every
# Space restart. Baking them into the package removes that dependency on the
# weights CDN (Dropbox rate-limits boot IPs, and a failed download makes
# detectzoo silently fall back to "simulation mode" - /health then reports
# detectzoo_loaded: false while every endpoint still answers 200). detectzoo
# reads weights from CWD/.detectzoo_data and skips files that already exist.
WEIGHT_FILES = [
    Path(".detectzoo_data/cnnspot/blur_jpg_prob0.5.pth"),
]


def _copytree_clean(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(*(f"{d}*" for d in EXCLUDE_DIRS)),
        dirs_exist_ok=True,
    )


def main() -> int:
    STAGE.mkdir(parents=True, exist_ok=True)

    # Local-test leftovers that must never ship: a model-cache symlink from a
    # local boot, runtime caches, and bytecode. Real weight files are re-baked
    # from the repo's .detectzoo_data below.
    for junk in (".detectzoo_data", "cache", "__pycache__"):
        p = STAGE / junk
        if p.is_symlink() or p.is_dir():
            shutil.rmtree(p, ignore_errors=False) if p.is_dir() and not p.is_symlink() else p.unlink()
            print(f"cleared staged {junk}")
    for src_name, dst_name in COPY_ITEMS:
        src = ROOT / src_name
        if not src.exists():
            print(f"MISSING required source: {src_name}")
            return 1
        dst = STAGE / dst_name
        if dst.exists() and dst.is_dir():
            shutil.rmtree(dst)
        if src.is_dir():
            _copytree_clean(src, dst)
            print(f"copied dir  {src_name}/ -> {dst_name}/")
        else:
            shutil.copy2(src, dst)
            print(f"copied file {src_name} -> {dst_name}")

    # Bake the weights detectzoo would download at boot. A missing local copy
    # is a warning, not a failure: the Space then downloads them at startup
    # exactly as before (and the DEPLOY.md verification step catches it when
    # detectzoo_loaded reads false).
    baked = 0
    for rel in WEIGHT_FILES:
        src = ROOT / rel
        if not src.exists():
            print(f"WARNING: weight not found locally, not baked: {rel}")
            print("         (the Space will download it on first boot)")
            continue
        dst = STAGE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        baked += 1
        print(f"baked weight {rel} ({src.stat().st_size / 1e6:.0f} MB)")

    # Byte-compile every staged .py file (into a throwaway cache dir, so no
    # __pycache__ litter ships to the Space) and fail on any syntax error.
    cache_dir = STAGE / ".compile_cache"
    py_staged = sorted(STAGE.rglob("*.py"))
    try:
        for py in py_staged:
            cfile = cache_dir / (str(py.relative_to(STAGE)) + ".pyc")
            cfile.parent.mkdir(parents=True, exist_ok=True)
            try:
                py_compile.compile(str(py), cfile=str(cfile), doraise=True)
            except py_compile.PyCompileError as e:
                print(f"SYNTAX ERROR in staged file {py.relative_to(STAGE)}:\n{e}")
                return 1
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)
    print(f"py_compile OK ({len(py_staged)} files)")

    total = sum(1 for _ in STAGE.rglob("*") if _.is_file())
    size_mb = sum(_.stat().st_size for _ in STAGE.rglob("*") if _.is_file()) / 1e6
    print(f"staged {total} files ({size_mb:.0f} MB, {baked} baked weight(s)) "
          f"in {STAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

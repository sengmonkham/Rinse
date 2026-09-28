#!/usr/bin/env python3
"""Build the character fingerprint database.

Hashes every canonical reference image under fingerprints/canon/<character>/
plus the legacy seeds in fingerprints/legacy_seeds.json, and regenerates
fingerprints/db.py (a committed, import-safe dict — the server never hashes
at boot).

Each reference contributes:
  - dhash (legacy-compatible), phash, ahash (64-bit ints)
  - center-crop variants (60% crop at 1.0x and 0.6x scale) for meme edits
    where the character sits on a busy background

Usage:
    .venv/bin/python scripts/build_fingerprints.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from forensics.hashing import ahash, dhash, phash  # noqa: E402

FP_DIR = REPO / "fingerprints"
CANON_DIR = FP_DIR / "canon"
MANIFEST = FP_DIR / "manifest.json"
LEGACY = FP_DIR / "legacy_seeds.json"
OUT = FP_DIR / "db.py"


def _crop_variants(img: Image.Image) -> list[Image.Image]:
    """Center crops used as extra match keys: 100% (full), 60%, and 36% area."""
    w, h = img.size
    out = [img]
    for frac in (0.6, 0.36):
        cw, ch = int(w * frac), int(h * frac)
        if cw < 24 or ch < 24:
            continue
        left = (w - cw) // 2
        top = (h - ch) // 2
        out.append(img.crop((left, top, left + cw, top + ch)))
    return out


def collect() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    legacy = json.loads(LEGACY.read_text())

    labels = {c["id"]: c["label"] for c in manifest["characters"]}

    entries: list[dict] = []

    # 1. Legacy seeds (dhash-only, no source file available)
    for seed in legacy["seeds"]:
        entries.append(
            {
                "character": seed["character"],
                "label": seed["label"],
                "ref": "legacy",
                "variant": "full",
                "dhash": int(seed["dhash"], 16),
                "phash": None,
                "ahash": None,
            }
        )

    # 2. Canonical images from canon/<character>/*
    n_chars_with_refs = 0
    for char in manifest["characters"]:
        cid = char["id"]
        char_dir = CANON_DIR / cid
        if not char_dir.is_dir():
            continue
        files = sorted(
            p
            for p in char_dir.iterdir()
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not files:
            continue
        n_chars_with_refs += 1
        label = labels.get(cid, cid)
        for path in files:
            try:
                img = Image.open(path)
                img.load()
            except Exception as e:  # noqa: BLE001
                print(f"  !! skipping {path.name}: {e}")
                continue
            for i, variant_img in enumerate(_crop_variants(img)):
                vname = "full" if i == 0 else f"crop{i}"
                h = _hashes(variant_img)
                entries.append(
                    {
                        "character": cid,
                        "label": label,
                        "ref": path.name,
                        "variant": vname,
                        **h,
                    }
                )

    return {
        "version": manifest.get("version", 1),
        "build": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
        "n_entries": len(entries),
        "n_characters_with_refs": n_chars_with_refs,
        "entries": entries,
    }


def _hashes(img: Image.Image) -> dict:
    return {"dhash": dhash(img), "phash": phash(img), "ahash": ahash(img)}


HEADER = '''"""GENERATED FILE — do not edit by hand.

Regenerate with: .venv/bin/python scripts/build_fingerprints.py

Character fingerprint database for forensics/characters.py.
dhash values are byte-compatible with server.py's legacy _dhash.
"""

FINGERPRINT_DB_VERSION = {version!r}
FINGERPRINT_DB_BUILD = {build!r}

# Each entry: character, label, ref, variant, dhash, phash, ahash.
# phash/ahash are None for legacy seeds (no source file to rehash).
FINGERPRINTS = [
{entries}
]
'''


def emit(db: dict) -> None:
    lines = []
    for e in db["entries"]:
        ph = hex(e["phash"]) if e["phash"] is not None else "None"
        ah = hex(e["ahash"]) if e["ahash"] is not None else "None"
        lines.append(
            (
                "    {{\n"
                '        "character": {character!r},\n'
                '        "label": {label!r},\n'
                '        "ref": {ref!r},\n'
                '        "variant": {variant!r},\n'
                '        "dhash": {dhash},\n'
                '        "phash": {phash},\n'
                '        "ahash": {ahash},\n'
                "    }},"
            ).format(
                character=e["character"],
                label=e["label"],
                ref=e["ref"],
                variant=e["variant"],
                dhash=hex(e["dhash"]),
                phash=ph,
                ahash=ah,
            )
        )
    OUT.write_text(
        HEADER.format(version=db["version"], build=db["build"], entries="\n".join(lines))
    )


def main() -> int:
    db = collect()
    emit(db)
    print(
        f"Wrote {OUT.relative_to(REPO)}: {db['n_entries']} entries "
        f"({db['n_characters_with_refs']} characters with canonical refs, "
        f"{db['n_entries'] - db['n_characters_with_refs'] * 0} hashed refs + legacy seeds)"
    )
    by_char: dict[str, int] = {}
    for e in db["entries"]:
        by_char[e["character"]] = by_char.get(e["character"], 0) + 1
    for cid, n in sorted(by_char.items()):
        print(f"  {cid}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

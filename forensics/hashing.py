"""Perceptual image hashing — dHash / pHash / aHash (64-bit each).

Compatibility contract: `dhash()` byte-matches server.py's legacy `_dhash`
(same 8x9 LANCZOS grayscale, same row-major horizontal-diff bit order,
MSB-first packing). The three original KNOWN_AI_ARTWORK_FINGERPRINTS
hashes were produced by that function and MUST keep matching.

pHash: 32x32 grayscale DCT-II (scipy-free, via numpy), top-left 8x8
(excluding [0,0] DC), median-threshold bit packing, row-major MSB-first.
aHash: 8x8 grayscale mean-threshold, row-major MSB-first.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------
# dHash — must stay byte-identical to server.py's _dhash
# --------------------------------------------------------------------------


def dhash(img: Image.Image, hash_size: int = 8) -> int:
    """64-bit difference hash. Byte-compatible with the legacy server _dhash."""
    gray = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = gray.tobytes()  # mode "L": one byte per pixel
    bits: list[int] = []
    for row in range(hash_size):
        base = row * (hash_size + 1)
        for col in range(hash_size):
            bits.append(1 if px[base + col] > px[base + col + 1] else 0)
    return int("".join(str(b) for b in bits), 2)


def hamming(a: int, b: int) -> int:
    """Hamming distance between two 64-bit hashes."""
    return bin(a ^ b).count("1")


# --------------------------------------------------------------------------
# DCT-II (unnormalized orthonormal variant) via numpy matrix multiply
# --------------------------------------------------------------------------

_DCT_MATRIX: np.ndarray | None = None


def _dct_matrix(n: int) -> np.ndarray:
    """n x n orthonormal DCT-II matrix (rows are frequencies)."""
    global _DCT_MATRIX
    if _DCT_MATRIX is None or _DCT_MATRIX.shape[0] != n:
        k = np.arange(n).reshape(-1, 1)
        i = np.arange(n).reshape(1, -1)
        _DCT_MATRIX = np.cos((2 * i + 1) * k * np.pi / (2 * n)) * np.sqrt(
            2.0 / n
        )
        _DCT_MATRIX[0, :] *= np.sqrt(0.5)
    return _DCT_MATRIX


def _dct2(a: np.ndarray) -> np.ndarray:
    """2-D DCT-II via row/column matrix multiplies."""
    m = _dct_matrix(a.shape[0])
    return m @ a @ m.T


# --------------------------------------------------------------------------
# pHash / aHash
# --------------------------------------------------------------------------


def phash(img: Image.Image, hash_size: int = 8, highfreq_factor: int = 4) -> int:
    """64-bit perceptual hash: DCT low-frequency sign pattern.

    32x32 grayscale -> DCT-II -> top-left 8x8 block, DC term dropped,
    median-thresholded, row-major MSB-first packing.
    """
    img_size = hash_size * highfreq_factor  # 32 for the defaults
    gray = img.convert("L").resize((img_size, img_size), Image.LANCZOS)
    arr = np.asarray(gray, dtype=np.float64)
    dct = _dct2(arr)
    block = dct[:hash_size, :hash_size].flatten()
    block = block[1:]  # drop DC
    med = np.median(block)
    bits = (block > med).astype(int)
    return int("".join(str(b) for b in bits), 2)


def ahash(img: Image.Image, hash_size: int = 8) -> int:
    """64-bit average hash: 8x8 grayscale mean-threshold, row-major MSB-first."""
    gray = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    px = np.asarray(gray, dtype=np.float64)
    bits = (px > px.mean()).astype(int).flatten()
    return int("".join(str(b) for b in bits), 2)


def hashes_all(img: Image.Image) -> dict[str, int]:
    """All three 64-bit hashes in one pass."""
    return {
        "dhash": dhash(img),
        "phash": phash(img),
        "ahash": ahash(img),
    }

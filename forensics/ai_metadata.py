"""
Layer 7: AI-provenance metadata probe (file/container/source-label scanning).

Complements the C2PA layer (forensics/c2pa.py) with a broader scan for
AI-generation markers:

  - C2PA / XMP / JUMBF markers in the raw file bytes (images AND video
    containers: Sora, Veo, Runway, ... embed Content Credentials or generator
    handler metadata in the file; social platforms strip it, direct-from-
    generator files carry it).
  - PIL image info / PNG tEXt chunks (Stable Diffusion 'parameters' chunk,
    NovelAI / ComfyUI / Fooocus comment chunks, ...).
  - MP4/MOV container metadata: handler/udta strings mentioning a generator.
  - Filename / URL hints (sora_clip.mp4, stable-diffusion-0001.png, ...).
  - OPTIONAL source label (post caption / page title supplied by the client):
    a creator declaring the generator tool ("made with Sora", "Higgsfield
    Genjutsu test") is strong provenance evidence about the content's origin.

Score contract (fed to the voter as the 'metadata' layer):
  95  explicit in-file AI assertion (trainedAlgorithmicMedia, generator
      software tag embedded in the FILE itself)
  75  strong provenance claim without in-file confirmation (caption/source
      names a specific generator tool, or in-file weak marker + label hint)
  65  multiple weak markers only (>= 3)
  35  full camera EXIF set (Make+Model+DateTime) and no AI marker:
      provenance suggests authentic capture (soft anti-AI evidence)
  None  nothing found (layer inactive)

Surrounding-text inputs (image path; the video path keeps using the
resolver's source caption):
  alt_text      the <img> alt/title/figcaption text — the page's own label
                for THIS asset; strong tools score like a caption (75), weak
                patterns count toward the >= 3 weak-marker rule.
  page_context  the surrounding post/article text. Context ONLY: a strong
                tool name there counts as one weak vote and weak patterns
                count toward the >= 3 weak-marker rule, and only while the
                file itself carries no AI metadata. A post discussing AI
                tools is not a claim about the image, so page text can never
                produce a synthetic-band verdict on its own.

False-positive guards:
  - Short/tool names are matched with word boundaries so 'veo' does not fire
    inside 'video' and 'ai' is never a keyword by itself.
  - A single weak marker never raises the score.
  - Caption evidence is REPORTED distinctly (source_label marker) so the
    verdict reason is transparent that it is a provenance claim, not pixel
    evidence.
  - alt_text/page_context markers are REPORTED distinctly ('alt_text ' /
    'page_context ' prefixes) so a page label can never be confused with
    in-file evidence in the reasons shown to users.
  - When the FILE carries any AI metadata itself, alt/caption/page labels no
    longer influence the score (no double counting; the file evidence is the
    stronger, harder-to-spoof signal) — they are still reported as markers.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

# Specific generator tools -> strong markers. Long unique names may match as
# plain substrings; short/ambiguous names are matched with word boundaries.
# Each entry: key = canonical name, value = regex pattern (case-insensitive).
# Generators are grouped by family for reporting clarity.
_STRONG_TOOLS = {
    # Video generators
    "sora": r"\bsora(?:\b|_)|sora\s+by\s+openai|openai\s+sora|sora[-_]?(?:clip|video|gen|generation)",
    "openai sora": r"openai\s+sora|sora\s+by\s+openai",
    "veo": r"\bveo\d?\b|google\s+veo",
    "runway": r"\brunway(ml)?\b|runway\s+gen|gen[-:]2",
    "higgsfield": r"higgsfield|genjutsu",
    "kling": r"\bkling\b|kling\s+ai|kling\s+video",
    "hailuo": r"\bhailuo\b|hai\s?luo|minimax\s+video",
    "minimax": r"\bminimax\b|minimax\s+video",
    "pika labs": r"\bpika\b|pika\s+labs|pika\s+video|pikart",
    "luma dream machine": r"luma\s+dream\s+machine|\bluma\s+ai\b|dream\s?machine|luma\s+video",
    # Image generators - major
    "midjourney": r"midjourney|midjourney\s+v[3-7]|mj\s*(?:v\d)?|mj\.?run",
    "stable diffusion": r"stable\s?-?diffusion|\bsdturbo\b|\bsdxl\b|stable\s+video\s+diffusion|svd\b",
    "dall-e": r"dall[·.\- ]?e\b|dalle|openai\s+\*?dall|openai\s+dall|dall\s*[-:]?e(?:\s*3)?",
    "comfyui": r"comfy\s?ui|comfyworkflows",
    "automatic1111": r"automatic1111|a1111|stable\s+diffusion\s+webui",
    "invokeai": r"invoke\s?ai|invoke\s+ai",
    "fooocus": r"fooocus",
    "novelai": r"novel\s?ai\b|novelai\s+(?:image|diffusion)",
    "adobe firefly": r"firefly|adobe\s+firefly|generative\s+fill",
    "grok imagine": r"grok\s+imagine|grok\s*(?:2|3)?\s*(?:imagine|ai)",
    "flux.1": r"\bflux[.\-_ ]?[012]\b|black\s*[-]?\s*forest\s+\*?labs",
    "leonardo.ai": r"leonardo\.(ai|dio)|leonardo\s+ai",
    "ideogram": r"\bideogram\b|ideogram\s+(?:2|3)?",
    "recraft": r"\brecraft\b|recraft\s+v[12]",
    "elevenlabs": r"eleven\s?labs|elevenlabs\s+(?:video|speech)",
    "imagen": r"\bimagen\b|google\s+imagen|imagen\s+[23]",
    "copilot creative": r"copilot\s+(creative|image|designer)",
    # Additional generators
    "bing image creator": r"bing\s+(?:image|creator)|microsoft\s+designer",
    "craiyon": r"craiyon|hot[.]?\s*dall",
    "playgroundai": r"playground\s*(?:ai)?|playground\s+ai",
    "starryai": r"starry\s*(?:ai)?|starryai",
    "nightcafe": r"night\s*cafe|nightcafe",
    "dreamstudio": r"dream\s*studio|stability\s+ai",
}

# Weak/ambiguous markers: generic AI-language without a specific tool name.
_WEAK_PATTERNS = {
    "ai_generated_claim": r"\bai[\s\-_]?(generated|generated\s+content|gen)\b|\ba\.i\.\s+(generated|video|art|image)",
    "made_with_ai": r"made\s+(with|using|by)\s+(open\s?)?ai\b",
    "created_with_ai": r"created\s+(with|using|by)\s+(open\s?)?ai\b",
    "ai_hashtag": r"#aigc|#aiart|#aiartcommunity|#aivideo|#aiimage",
    "text_to_image": r"text[\s\-]?to[\s\-]?(image|video)",
    "prompt_field": r"\bprompt\s*[:=]|negative[_\s]?prompt\b",
    "seed_field": r"\bseed\s*[:=]\s*\d",
    "sampler_field": r"\bsampler\s*[:=]|\beuler[_\s]a?\b|\bdpm\+\+|\buni[_\s]?pc\b",
    "checkpoint_field": r"\bcheckpoint\s*[:=]|\.safetensors\b|\.ckpt\b",
    "cfg_field": r"\bcfg(\s*scale)?\s*[:=]\s*\d",
    "ai_suffix": r"[\-_]ai[\-_\.](mp4|mp3|png|jpg|jpeg|webp|mov)\b|\bai[\-_](video|image|art|clip|render)\b",
}

# In-file assertion markers (binary scan) -> strong.
_FILE_STRONG_REGEX_LIST = [
    re.compile(r"action[\"'\s:]{0,6}(ai_)?generated", re.IGNORECASE),
    re.compile(r"digitalsourcetype", re.IGNORECASE),
    re.compile(r"trainedalgorithmicmedia|compositesynthetic", re.IGNORECASE),
    re.compile(r"c2pa[\"'\s:]{0,6}claim[\"'\s:]{0,6}generator", re.IGNORECASE),
    re.compile(r"xmp\:[\"'\s:]{0,6}iptc\:digitalsourcetype", re.IGNORECASE),
    re.compile(r"photoshop\:[\"'\s:]{0,6}credit\b|photoshop\:[\"'\s:]{0,6}creator\s*tool", re.IGNORECASE),
    re.compile(r"software\s*[:=]\s*[\"']?(?:midjourney|dalle|stable\s*diffusion|comfy|invoke|automatic1111)", re.IGNORECASE),
]

# Camera provenance: a FULL EXIF set (Make+Model+DateTime) suggests a real
# camera capture. Single fields (e.g. software-only tags) are ignored.
_CAMERA_EXIF_FIELDS = ("Make", "Model", "DateTime")

# Search-engine image proxies embed the ORIGINAL source URL in the path
# (base64url in the last segments for Brave: /i/<sig>/rs:.../<b64url>). The
# proxy URL's own basename is an opaque signature blob, so filename hints are
# useless until decoded. Best-effort, only when the payload round-trips to a
# plausible http(s) URL.
_URL_B64_RE = re.compile(r"[A-Za-z0-9_\\-]{24,}")


def _decode_url_payloads(text: str) -> str:
    """Decode base64url URL payloads embedded in proxy image URLs (best effort).

    'aHR0cHM6...' is 'https://...' base64url-encoded. Decoded candidates are
    APPENDED to the scanned text (the original text stays in it), so a decode
    failure never loses the raw text either.
    """
    out = [text]
    from urllib.parse import unquote
    import base64 as _b64
    for token in _URL_B64_RE.findall(text):
        if len(token) % 4:
            token_p = token + "=" * (4 - len(token) % 4)
        else:
            token_p = token
        try:
            decoded = _b64.urlsafe_b64decode(token_p.encode("ascii")).decode(
                "utf-8", errors="strict"
            )
        except Exception:
            continue
        if decoded.startswith(("http://", "https://")):
            out.append(unquote(decoded).lower())
    return " ".join(out)

# How much of a binary payload to scan (containers put metadata at the head;
# MP4 'moov' can be at the tail for non-faststart files).
_HEAD_SCAN = 2 * 1024 * 1024
_TAIL_SCAN = 1024 * 1024

_VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".m4v")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".heic")


def _compile(patterns: Dict[str, str]) -> List[tuple]:
    out = []
    for name, pat in patterns.items():
        try:
            out.append((name, re.compile(pat, re.IGNORECASE)))
        except re.error:
            continue
    return out


_STRONG_RES = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in _STRONG_TOOLS.items()]
_WEAK_RES = _compile(_WEAK_PATTERNS)

# Metadata-neighborhood keywords that legitimize a short-token tool-string hit
# inside binary data (PNG tEXt chunks, EXIF software tags, MP4 udta atoms).
_META_CONTEXT_RX = re.compile(
    r"(udta|meta|ilst|handler|hdlr|software|encoder|comment|desc|params|prompt|"
    r"xmp|exif|c2pa|jumbf|credits|generator|producer|title|json)",
    re.IGNORECASE,
)


def _scan_text_for_markers(text: str) -> tuple:
    """Scan one text corpus for strong/weak markers. Returns (strong, weak) lists."""
    strong: List[str] = []
    weak: List[str] = []
    for name, rx in _STRONG_RES:
        m = rx.search(text)
        if m:
            strong.append(f"{name}:'{m.group(0)[:40]}'")
    for name, rx in _WEAK_RES:
        m = rx.search(text)
        if m:
            weak.append(f"{name}:'{m.group(0)[:40]}'")
    return strong, weak


def _parse_mp4_atoms(raw: bytes) -> List[str]:
    """Parse MP4/MOV container atoms for generator-related metadata.

    MP4 containers store metadata in atoms (boxes). Key atoms for AI detection:
    - udta (user data) contains handler/generator info
    - free/void atoms sometimes contain leftover generator strings
    - Metadata atoms (mdhd, hdlr) can carry generator names
    - co64/compact atoms may contain generator tool references

    Scans both head and tail since moov can be at either end.
    """
    if not raw or len(raw) < 8:
        return []
    
    found = []
    # Scan both head and tail of file
    scan_regions = [raw[:_HEAD_SCAN]]
    if len(raw) > _HEAD_SCAN:
        scan_regions.append(raw[-_TAIL_SCAN:])
    
    for region in scan_regions:
        try:
            text = region.decode("latin-1", errors="ignore").lower()
        except Exception:
            continue
        
        # Look for common MP4 metadata atom patterns containing generator info
        # udta (user data) atoms often contain generator tool names
        udta_patterns = [
            r"udta[\x00]*[^\x00]{8,200}(?:midjourney|dalle|stable.?diffusion|runway|pika|luma|kling|higgsfield|veo|sora|comfy|invoke|firefly|flux|leondardo|ideogram)",
            r"free[\x00]*[^\x00]{8,100}(?:midjourney|dalle|stable.?diffusion|runway|pika|luma|kling|higgsfield|veo|sora|comfy|invoke|firefly|flux)",
            r"moov[\x00]{0,20}.*?(?:midjourney|dalle|stable.?diffusion|runway|pika|luma|kling|higgsfield|veo|sora|comfy|invoke|firefly|flux)",
        ]
        for pat in udta_patterns:
            try:
                for m in re.finditer(pat, text):
                    hit = m.group(0).strip()
                    # Extract just the generator mention
                    for gen_name, gen_rx in _STRONG_RES:
                        gm = gen_rx.search(hit)
                        if gm and len(gm.group(0)) > 2:
                            found.append(f"MP4 container atom: generator '{gm.group(0)[:40]}' in metadata")
                            break
            except re.error:
                continue
    
    return found


def _binary_ai_markers(raw: bytes) -> List[str]:
    """Scan raw file bytes (head+tail) for in-file AI assertions."""
    if not raw:
        return []
    found = []
    
    # For video files, parse MP4/MOV container atoms first
    chunk = raw[:_HEAD_SCAN] + (raw[-_TAIL_SCAN:] if len(raw) > _HEAD_SCAN else b"")
    try:
        text = chunk.decode("latin-1", errors="ignore")
    except Exception:
        return found
    lowered = text.lower()
    
    # MP4 container metadata parsing
    mp4_markers = _parse_mp4_atoms(raw)
    found.extend(mp4_markers)
    
    if "trainedalgorithmicmedia" in lowered:
        found.append("C2PA digitalSourceType 'trainedAlgorithmicMedia' (declared AI generation)")
    if "compositesynthetic" in lowered:
        found.append("C2PA assertion 'compositeSynthetic' (declared synthetic content)")
    if "c2pa" in lowered or "jumbf" in lowered or "contentcredentials" in lowered:
        for rx in _FILE_STRONG_REGEX_LIST:
            m = rx.search(lowered)
            if m:
                found.append(f"C2PA/Content Credentials AI action assertion ('{m.group(0)[:40]}')")
    
    # Check for explicit generator claims in XMP/IPTC metadata
    xmp_patterns = [
        (r"xmp:_creator_tool[\"'\s:]{0,6}[\"']?(midjourney|dalle|stable.?diffusion|runway|pika|luma|kling|higgsfield|veo|sora|comfy|invoke|firefly|flux)", "XMP creator tool"),
        (r"iptc\:digitalsourcetype[\"'\s:]{0,6}[\"']?(trainedAlgorithmicMedia|compositeSynthetic)", "IPTC digitalSourceType"),
        (r"photoshop\:credit[\"'\s:]{0,6}[\"']?(midjourney|dalle|stable.?diffusion|runway|pika|luma|kling|higgsfield|veo|sora)", "Photoshop credit"),
    ]
    for pat, label in xmp_patterns:
        m = re.search(pat, lowered)
        if m:
            found.append(f"{label} assertion in file metadata: '{m.group(0)[:60]}'")
    
    # Generator software strings inside the file (metadata atoms, PNG chunks):
    for name, rx in _STRONG_RES:
        m = rx.search(lowered)
        if not m:
            continue
        hit = m.group(0).lower()
        # Short-token guard: video/media streams are high-entropy binary, so
        # short tool names occur by chance inside compressed data. Only count
        # the hit when it appears in a plausible metadata neighborhood (utf-8
        # style text with a metadata keyword nearby).
        if len(hit) <= 5:
            window = lowered[max(0, m.start() - 200):m.end() + 200]
            if not _META_CONTEXT_RX.search(window):
                continue
        # Avoid double-counting if already found via XMP/IPTC parsing
        if not any(name.lower() in f.lower() for f in found):
            found.append(f"generator tool string '{m.group(0)[:40]}' embedded in file metadata")
    return found


def _pil_info_markers(img) -> tuple:
    """Scan PIL image info (PNG tEXt / JPEG comment / EXIF) for markers.

    Returns (strong_reasons, weak_names, camera_fields_present).
    """
    strong: List[str] = []
    weak: List[str] = []
    try:
        parts = []
        info = getattr(img, "info", {}) or {}
        for k, v in info.items():
            parts.append(f"{k}={str(v)[:2000]}")
        text = " ".join(parts).lower()
        s, w = _scan_text_for_markers(text)
        strong.extend(s)
        weak.extend(w)
    except Exception:
        pass

    camera_fields = []
    try:
        exif = img.getexif()
        # _CAMERA_EXIF_FIELDS holds tag NAMES; Exif tags are numeric - resolve
        # via PIL's reverse map (TAGS) with a name lookup fallback.
        try:
            from PIL.ExifTags import TAGS
            tag_ids = {name: tid for tid, name in TAGS.items()}
        except Exception:  # noqa: BLE001
            tag_ids = {"Make": 271, "Model": 272, "DateTime": 306}
        for field in _CAMERA_EXIF_FIELDS:
            tid = tag_ids.get(field)
            val = exif.get(tid) if (tid is not None and hasattr(exif, "get")) else None
            if val not in (None, ""):
                camera_fields.append(field)
    except Exception:
        pass
    return strong, weak, camera_fields


def _container_markers(raw: bytes, kind: str) -> List[str]:
    """Scan video container metadata atoms (moov/udta/hdlr strings)."""
    if kind not in ("video",) or not raw:
        return []
    return _binary_ai_markers(raw)


def probe_ai_metadata(
    img=None,
    raw_bytes: bytes = b"",
    kind: str = "image",
    source_url: str = "",
    source_caption: str = "",
    alt_text: str = "",
    page_context: str = "",
) -> Dict[str, Any]:
    """Run the AI-provenance metadata probe.

    Args:
        img: PIL Image (optional; enables PNG tEXt / EXIF scanning).
        raw_bytes: raw file bytes (enables binary C2PA/container scanning).
        kind: 'image' or 'video'.
        source_url: the URL the media was fetched from (filename hints;
            base64url URL payloads from search-engine proxies are decoded).
        source_caption: optional post caption / page title supplied by the
            caller (strong provenance evidence when it names a generator).
        alt_text: the image's own page label (alt/title/figcaption) - strong
            tools match like a caption, weak patterns count toward the
            weak-marker rule. Image path only.
        page_context: surrounding post/article text - never produces a
            synthetic-band verdict on its own; a strong tool name there
            counts as one weak vote and weak patterns count toward the
            >= 3 weak-marker rule, and ONLY while the file itself is silent.

    Returns:
        {"score": int|None, "source": str, "reason": str, "markers": [...]}
    """
    markers: List[str] = []
    strong_file = 0    # in-file binary / PIL-info AI markers
    weak_file = 0
    strong_label = 0   # caption / alt-text / filename tool claims
    weak_label = 0
    weak_page = 0      # surrounding-text context (never a strong vote)
    camera_fields: List[str] = []

    # 1. In-file binary assertions (both kinds).
    file_markers = _binary_ai_markers(raw_bytes)
    # The binary text also carries weak parameter-style markers (generation
    # parameters embedded in PNG tEXt chunks, container atoms, JPEG comments).
    _, weak_from_file = _scan_text_for_markers(
        (raw_bytes[:_HEAD_SCAN] + (raw_bytes[-_TAIL_SCAN:] if len(raw_bytes) > _HEAD_SCAN else b""))
        .decode("latin-1", errors="ignore")
    ) if raw_bytes else ([], [])
    for m in file_markers:
        if m not in markers:
            markers.append(m)
    markers.extend(f"file weak {m}" for m in weak_from_file)
    # Explicit trainedAlgorithmicMedia / compositeSynthetic -> decisive 95.
    if any("trainedAlgorithmicMedia" in m or "compositeSynthetic" in m for m in file_markers):
        return {
            "score": 95,
            "source": "file_manifest",
            "reason": "AI metadata confirmed: " + "; ".join(file_markers[:2]) + ".",
            "markers": markers,
        }
    strong_file += len(file_markers)
    weak_file += len(weak_from_file)

    # 2. PIL info / EXIF / PNG text chunks. The camera-EXIF anti-AI vote is
    #    decided AFTER the label scans below: a page-declared AI label must
    #    not be silently masked by an early return.
    if img is not None:
        s, w, camera_fields = _pil_info_markers(img)
        strong_file += len(s)
        weak_file += len(w)
        for m in s:
            if m not in markers:
                markers.append(f"file-info {m}")
        markers.extend(f"file-info weak {m}" for m in w)

    # 3. Filename / URL hints. Search-engine proxy URLs carry the original
    #    source URL base64url-encoded in the path; decode those payloads first
    #    so the filename hint is readable (the raw proxy path alone is an
    #    opaque signature blob).
    if source_url:
        try:
            from urllib.parse import unquote, urlparse

            path = unquote(urlparse(source_url).path or "")
            fname = os.path.basename(path)
            # Also scan the full URL path for generator hints (not just basename)
            # e.g. /uploads/sora-generations/clip-001.mp4
            full_path = unquote(urlparse(source_url).path or "")
        except Exception:
            fname = source_url[-80:]
            full_path = source_url[-200:]
        # NOTE: no .lower() here - base64url payloads in proxy URLs are
        # case-sensitive and lowercasing breaks their decode; the marker
        # regexes are compiled with re.IGNORECASE anyway.
        # Scan both the filename AND the full path for generator hints
        combined_path_text = _decode_url_payloads(f"{fname} {full_path}")
        s, w = _scan_text_for_markers(combined_path_text)
        strong_label += len(s)
        weak_label += len(w)
        if s:
            markers.extend(f"url_path {m}" for m in s)
        if w:
            markers.extend(f"url_path weak {m}" for m in w)

    # 4. Source caption / page title (caller-supplied provenance label).
    if source_caption:
        s, w = _scan_text_for_markers(source_caption.lower())
        strong_label += len(s)
        weak_label += len(w)
        markers.extend(f"source_caption {m}" for m in s + w)

    # 5. The image's own page label (alt/title/figcaption). Treated like a
    #    caption: the page asserts this label for THIS asset specifically.
    if alt_text:
        s, w = _scan_text_for_markers(alt_text.lower())
        strong_label += len(s)
        weak_label += len(w)
        markers.extend(f"alt_text {m}" for m in s + w)

    # 6. Surrounding post/article text: CONTEXT ONLY. A post that discusses AI
    #    tools is not a claim about the image, so a strong tool name there
    #    counts as one weak vote (never a synthetic-band escalation from
    #    prose) and weak patterns count toward the >= 3 weak-marker rule.
    if page_context:
        s, w = _scan_text_for_markers(page_context.lower())
        for m in s:
            weak_page += 1
            markers.append(f"page_context {m} (surrounding-text context, not an asset claim)")
        weak_page += len(w)
        markers.extend(f"page_context weak {m}" for m in w)

    strong = strong_file + strong_label
    weak = weak_file + weak_label + weak_page

    # Full camera EXIF provenance and zero AI markers anywhere (file, labels,
    # context) is soft evidence FOR authentic capture.
    if (
        len(camera_fields) >= len(_CAMERA_EXIF_FIELDS)
        and strong == 0 and weak == 0
    ):
        return {
            "score": 35,
            "source": "camera_exif",
            "reason": (
                "Full camera EXIF provenance present ("
                + ", ".join(camera_fields)
                + ") and no AI-generation metadata found - consistent with authentic camera capture."
            ),
            "markers": markers,
        }

    # Alt/caption/URL/page labels only influence the score when the file
    # itself carries no AI metadata - in-file markers are the harder-to-spoof
    # signal and must not be double-counted with page-declared labels.
    if strong_file or weak_file:
        strong_label = 0
        weak_label = 0
        weak_page = 0
        strong = strong_file
        weak = weak_file

    if strong >= 2 or (strong >= 1 and weak >= 2):
        # Two IN-FILE strong markers are decisive (95); one in-file marker
        # corroborated by anything else stays at 75 - the file evidence alone
        # is what makes a hard provenance assertion.
        score = 95 if strong >= 2 and strong_file >= 2 else 75
        # Boost score for specific, well-known generator detections (higher
        # confidence, less likely to be a false positive)
        if strong_file >= 1:
            for marker in markers:
                # Known high-confidence video generators
                if any(g in marker.lower() for g in ("sora", "veo", "runway", "kling", "pika", "luma", "higgsfield")):
                    if score < 85:
                        score = 85  # Video generator detected in-file
                    break
                # Known high-confidence image generators  
                if any(g in marker.lower() for g in ("midjourney", "dall-e", "dall\u2022e", "flux")):
                    if score < 80:
                        score = 80  # Major image generator detected
                    break
        return {
            "score": score,
            "source": "file+label" if strong_file else "source_label",
            "reason": (
                f"AI provenance markers found ({strong} strong, {weak} weak): "
                + "; ".join(markers[:3])
                + "."
            ),
            "markers": markers,
        }
    if strong == 1:
        origin = next(
            (m for m in markers if m.startswith(("source_caption", "alt_text"))),
            markers[0],
        )
        if origin.startswith(("source_caption", "alt_text", "filename")):
            # A single source-label claim: strong provenance evidence about
            # the content's origin, but not in-file confirmation -> 75.
            return {
                "score": 75,
                "source": "source_label",
                "reason": (
                    f"Source label declares an AI generator ({origin.split(':', 1)[-1].strip(chr(39)) or origin}). "
                    "Provenance claim - the file itself carries no AI metadata (social platforms strip it)."
                ),
                "markers": markers,
            }
        # A single in-file marker without corroboration: modest evidence.
        return {
            "score": 65,
            "source": "file_metadata",
            "reason": f"Single AI metadata marker found in the file: {markers[0]}.",
            "markers": markers,
        }
    if weak >= 3:
        return {
            "score": 65,
            "source": "weak_markers",
            "reason": f"Multiple weak AI-generation markers ({weak}): " + "; ".join(markers[:3]) + ".",
            "markers": markers,
        }
    if markers:
        return {
            "score": None,
            "source": "hint_only",
            "reason": f"Inconclusive AI metadata hint (too weak to vote): {markers[0]}.",
            "markers": markers,
        }
    return {
        "score": None,
        "source": "none",
        "reason": "No AI-generation metadata markers in file, container, source URL, caption or page context.",
        "markers": [],
    }

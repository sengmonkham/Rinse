#!/usr/bin/env python3
"""Inspect and export the scan log (forensics/scan_log.py).

    .venv/bin/python scripts/scan_log_cli.py stats
    .venv/bin/python scripts/scan_log_cli.py recent --limit 20 --kind text --human --text
    .venv/bin/python scripts/scan_log_cli.py export --out human-corpus.jsonl --human-only
    .venv/bin/python scripts/scan_log_cli.py export --out all.jsonl --include-verdict
    .venv/bin/python scripts/scan_log_cli.py maintain

Everything reads the same SQLite file the server writes
(cache/scan_log.db, or SCAN_LOG_DIR when set). Nothing here touches the
detector — it is a read-only view unless you run `maintain`.

The export is JSON Lines, one scan per line: the normalized verdict, content
hash, excerpt (text scans), and provenance. Filter to `--human-only` to build
a human/authentic corpus.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forensics import scan_log  # noqa: E402


def _since(value: str | None) -> float | None:
    """Accept a Unix timestamp or an ISO date (2026-10-01, 2026-10-01T12:00Z)."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"--since must be a Unix timestamp or ISO date: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def cmd_stats(_args) -> int:
    stats = scan_log.stats()
    print(f"log:            {stats['db_path']} ({stats['db_bytes'] / 1024:.0f} KB)")
    print(f"enabled:        {stats['enabled']}")
    print(f"total scans:    {stats['total']}")
    print(f"human-likely:   {stats['human_likely']} ({stats['human_likely_7d']} in last 7d)")
    print(f"by kind:        {stats['by_kind']}")
    print(f"human by kind:  {stats['by_kind_human_likely']}")
    print(f"cache hits:     {stats['cached_hits']}")
    print(f"last scan:      {stats['last_scan_at']}")
    print(
        f"retention:      {stats['retention_days']}d "
        f"(human {stats['human_retention_days']}d), max {stats['max_rows']} rows"
    )
    print("by verdict:")
    for label, count in sorted(stats["by_tier"].items(), key=lambda kv: -kv[1]):
        print(f"  {str(label):<28} {count}")
    return 0


def cmd_recent(args) -> int:
    rows = scan_log.recent(
        args.limit,
        kind=args.kind,
        human_only=args.human,
        include_text=args.text,
        since=_since(args.since),
    )
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    if not rows:
        print("no scans matched.")
        return 0
    for row in rows:
        print(
            f"{row['created_at']}  {row['kind']:<5} {row['source']:<16} "
            f"score={row['score']}  {row['tier'] or row['label'] or '-':<16} "
            f"human={str(row['human_likely']):<5} cached={row['cached'] or '-'}"
        )
        if row.get("excerpt"):
            print(f"    {row['excerpt'][:160]!r}")
    print(f"\n{len(rows)} row(s).")
    return 0


def cmd_export(args) -> int:
    count = scan_log.export_jsonl(
        args.out,
        kind=args.kind,
        human_only=args.human_only,
        since=_since(args.since),
        include_verdict=args.include_verdict,
    )
    print(f"wrote {count} row(s) to {args.out}")
    return 0 if count else 1


def cmd_maintain(_args) -> int:
    removed = scan_log.maintain()
    print(
        f"expired non-human: {removed['expired_other']}, "
        f"expired human: {removed['expired_human']}, "
        f"trimmed over cap: {removed['trimmed']}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect and export the RINSE scan log.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_stats = sub.add_parser("stats", help="counts by kind, verdict and human flag")
    p_stats.set_defaults(func=cmd_stats)

    p_recent = sub.add_parser("recent", help="newest scans first")
    p_recent.add_argument("--limit", type=int, default=20)
    p_recent.add_argument("--kind", choices=["text", "image", "video"])
    p_recent.add_argument("--human", action="store_true", help="only human-likely")
    p_recent.add_argument("--text", action="store_true", help="include text excerpts")
    p_recent.add_argument("--since", help="Unix timestamp or ISO date")
    p_recent.add_argument("--json", action="store_true", help="raw JSON output")
    p_recent.set_defaults(func=cmd_recent)

    p_export = sub.add_parser("export", help="write matching rows as JSON Lines")
    p_export.add_argument("--out", required=True, help="output .jsonl path")
    p_export.add_argument("--kind", choices=["text", "image", "video"])
    p_export.add_argument(
        "--human-only", action="store_true", help="only human-likely scans"
    )
    p_export.add_argument("--since", help="Unix timestamp or ISO date")
    p_export.add_argument(
        "--include-verdict", action="store_true", help="include compact verdict JSON"
    )
    p_export.set_defaults(func=cmd_export)

    p_maintain = sub.add_parser("maintain", help="apply retention + the row cap now")
    p_maintain.set_defaults(func=cmd_maintain)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

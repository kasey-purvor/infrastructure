#!/usr/bin/env python3
"""claude-sessions — map every Claude Code conversation on this machine.

Claude Code stores each conversation as a JSONL transcript under
``<config-dir>/projects/<path-encoded-cwd>/<session-id>.jsonl``. The folder name
is derived from the directory ``claude`` was launched in, but the encoding is
lossy and has drifted across versions (``/`` and ``.`` become ``-``; underscores
are sometimes preserved, sometimes not). That makes the folder names an
unreliable index, and it scatters one logical project across several buckets
(plus a separate bucket per git worktree).

This tool sidesteps all of that by reading the *real* ``cwd`` stored inside each
transcript and grouping by that. Conversations that the folder names had split
apart are reunited under their true working directory.

Usage:
    claude-sessions                 Overview: projects grouped by real cwd.
    claude-sessions <filter>        Drill into projects whose path matches
                                    <filter> and list their conversations.
    claude-sessions --orphans       Only projects whose cwd no longer exists
                                    (unreachable via `claude --continue/--resume`).
    claude-sessions --by-path       Sort the overview by path (worktrees cluster
                                    under their parent repo) instead of recency.

Stdlib only; no third-party dependencies.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

# How far into a transcript we are willing to read when hunting for metadata or
# the first human message. Transcripts can be megabytes of tool output, so we cap
# the scan rather than slurping whole files.
_HEAD_LINES = 60          # cwd / gitBranch / version appear in the first few lines
_MSG_SCAN_LINES = 400     # first real user message is almost always near the top


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_config_dirs() -> list[str]:
    """Return every Claude config dir that has a projects/ folder.

    Covers ~/.claude (default/personal) and any sibling like ~/.claude-work,
    so conversations from all account profiles show up in one map.
    """
    home = os.path.expanduser("~")
    dirs = []
    for path in sorted(glob.glob(os.path.join(home, ".claude*"))):
        if os.path.isdir(os.path.join(path, "projects")):
            dirs.append(path)
    return dirs


def profile_label(config_dir: str) -> str:
    """Human-friendly tag for a config dir: ~/.claude -> 'default', ~/.claude-work -> 'work'."""
    name = os.path.basename(config_dir)
    if name == ".claude":
        return "default"
    return name.removeprefix(".claude-") or name.lstrip(".")


# --------------------------------------------------------------------------- #
# Transcript reading (deliberately partial — we never read whole files)
# --------------------------------------------------------------------------- #
def read_head_meta(path: str) -> dict:
    """Pull cwd / gitBranch / version from the first lines of a transcript."""
    meta: dict = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(_HEAD_LINES), fh):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for key in ("cwd", "gitBranch", "version"):
                    if key not in meta and obj.get(key):
                        meta[key] = obj[key]
                if "cwd" in meta and "gitBranch" in meta and "version" in meta:
                    break
    except OSError:
        pass
    return meta


def first_user_message(path: str) -> str:
    """Best-effort: the first real human message, to identify a conversation.

    Skips system/tool noise (lines whose content starts with '<', and tool
    results that arrive wrapped as user-role messages).
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(_MSG_SCAN_LINES), fh):
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "user":
                    continue
                content = obj.get("message", {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    # A list of content blocks; keep only text blocks, drop
                    # tool_result blocks (those aren't something the user typed).
                    if any(isinstance(p, dict) and p.get("type") == "tool_result" for p in content):
                        continue
                    text = " ".join(
                        p.get("text", "") for p in content if isinstance(p, dict)
                    )
                else:
                    text = ""
                text = " ".join(text.split())  # collapse whitespace/newlines
                if text and not text.startswith("<"):
                    return text
    except OSError:
        pass
    return ""


def approx_path_from_bucket(bucket: str) -> str:
    """Lossy fallback when a bucket has no readable cwd: '-a-b-c' -> '/a/b/c'."""
    return "/" + bucket.lstrip("-").replace("-", "/")


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #
def scan_transcripts(config_dirs: list[str]) -> list[dict]:
    """One record per transcript: profile, bucket, path, mtime (cheap — stat only)."""
    records = []
    for config_dir in config_dirs:
        projects = os.path.join(config_dir, "projects")
        for bucket in os.listdir(projects):
            bucket_dir = os.path.join(projects, bucket)
            if not os.path.isdir(bucket_dir):
                continue
            for path in glob.glob(os.path.join(bucket_dir, "*.jsonl")):
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                records.append(
                    {
                        "profile": profile_label(config_dir),
                        "bucket": bucket,
                        "path": path,
                        "mtime": mtime,
                    }
                )
    return records


def resolve_cwd(records: list[dict]) -> None:
    """Annotate each record with the real cwd, reading one transcript per bucket.

    All transcripts in a bucket share a launch cwd, so we only read the newest
    one per bucket and reuse the answer — keeps the overview fast.
    """
    by_bucket: dict[tuple, list[dict]] = defaultdict(list)
    for rec in records:
        by_bucket[(rec["profile"], rec["bucket"])].append(rec)

    for (_, bucket), recs in by_bucket.items():
        # Newest first: the latest transcript usually has the cwd in its head,
        # but short/aborted or sidechain transcripts may not — so fall through
        # to older ones before resorting to the lossy folder-name decode.
        cwd = None
        for rec in sorted(recs, key=lambda r: -r["mtime"]):
            cwd = read_head_meta(rec["path"]).get("cwd")
            if cwd:
                break
        approx = cwd is None
        if cwd is None:
            cwd = approx_path_from_bucket(bucket)
        for rec in recs:
            rec["cwd"] = cwd
            rec["cwd_approx"] = approx


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def rel_time(mtime: float) -> str:
    delta = datetime.now(timezone.utc) - datetime.fromtimestamp(mtime, timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit} ago"
    return f"{secs}s ago"


def full_id(path: str) -> str:
    """The session UUID — what `claude --resume` actually needs."""
    return os.path.basename(path).removesuffix(".jsonl")


def short_id(path: str) -> str:
    return full_id(path)[:8]


def line_count(path: str) -> int:
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def print_overview(records: list[dict], by_path: bool, orphans_only: bool) -> None:
    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        groups[rec["cwd"]].append(rec)

    rows = []
    for cwd, recs in groups.items():
        latest = max(r["mtime"] for r in recs)
        buckets = {r["bucket"] for r in recs}
        profiles = sorted({r["profile"] for r in recs})
        missing = not os.path.isdir(cwd) and not recs[0].get("cwd_approx")
        if orphans_only and not missing:
            continue
        rows.append(
            {
                "cwd": cwd,
                "count": len(recs),
                "latest": latest,
                "buckets": len(buckets),
                "profiles": profiles,
                "missing": missing,
                "approx": recs[0].get("cwd_approx", False),
            }
        )

    rows.sort(key=lambda r: (r["cwd"] if by_path else -r["latest"]))

    total_convs = sum(r["count"] for r in rows)
    total_missing = sum(1 for r in rows if r["missing"])
    print(
        f"\n{len(rows)} projects · {total_convs} conversations · "
        f"{total_missing} with a missing path\n"
    )
    print("  last active   convs  project (real cwd)")
    print("  " + "-" * 70)
    for r in rows:
        flags = []
        if r["buckets"] > 1:
            flags.append(f"{r['buckets']} buckets")
        if r["profiles"] != ["default"]:
            flags.append("+".join(r["profiles"]))
        if r["missing"]:
            flags.append("MISSING")
        if r["approx"]:
            flags.append("path≈")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {rel_time(r['latest']):>11}  {r['count']:>5}  {r['cwd']}{flag_str}")
    print(
        "\nTip: `claude-sessions <text>` to list conversations in matching "
        "projects.\n     MISSING = path is gone; reach those via the picker "
        "(`claude --resume`, then Ctrl+A).\n"
    )


def print_drilldown(records: list[dict], needle: str, limit: int) -> None:
    needle_low = needle.lower()
    matched = [r for r in records if needle_low in r["cwd"].lower()]
    if not matched:
        print(f"\nNo projects matching {needle!r}.\n")
        return

    groups: dict[str, list[dict]] = defaultdict(list)
    for rec in matched:
        groups[rec["cwd"]].append(rec)

    for cwd in sorted(groups, key=lambda c: -max(r["mtime"] for r in groups[c])):
        recs = sorted(groups[cwd], key=lambda r: -r["mtime"])[:limit]
        exists = os.path.isdir(cwd)
        marker = "" if exists else "  [MISSING — path no longer exists]"
        print(f"\n\033[1m{cwd}\033[0m{marker}   ({len(groups[cwd])} conversations)")
        print("  " + "-" * 70)
        for rec in recs:
            meta = read_head_meta(rec["path"])
            branch = meta.get("gitBranch") or "—"
            version = meta.get("version") or "?"
            msg = first_user_message(rec["path"]) or "(no user message found)"
            if len(msg) > 88:
                msg = msg[:87] + "…"
            print(
                f"  {short_id(rec['path'])}  {rel_time(rec['mtime']):>9}  "
                f"{line_count(rec['path']):>4} lines  "
                f"[{rec['profile']}]  branch: {branch}  v{version}"
            )
            print(f"      “{msg}”")
            if exists:
                print(f"      resume: (cd {cwd!r} && claude --resume {full_id(rec['path'])})")
            print(f"      file:   {rec['path']}")
        if len(groups[cwd]) > limit:
            print(f"  … {len(groups[cwd]) - limit} older (raise --limit to see them)")
    print()


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="claude-sessions",
        description="Map Claude Code conversations by their real working directory.",
    )
    parser.add_argument(
        "filter",
        nargs="?",
        help="substring of a project path; drill into matching projects",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="overview, but only projects whose cwd no longer exists",
    )
    parser.add_argument(
        "--by-path",
        action="store_true",
        help="sort overview by path (worktrees cluster) instead of recency",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=12,
        help="max conversations to list per project in drill-down (default 12)",
    )
    args = parser.parse_args()

    config_dirs = discover_config_dirs()
    if not config_dirs:
        print("No Claude config dirs with a projects/ folder found.", file=sys.stderr)
        return 1

    records = scan_transcripts(config_dirs)
    if not records:
        print("No transcripts found.", file=sys.stderr)
        return 1
    resolve_cwd(records)

    if args.filter:
        print_drilldown(records, args.filter, args.limit)
    else:
        print_overview(records, by_path=args.by_path, orphans_only=args.orphans)
    return 0


if __name__ == "__main__":
    sys.exit(main())

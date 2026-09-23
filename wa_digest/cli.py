"""Command line: wa-digest EXPORT.zip -> out/<chat>_<date>.mp3"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from .cleaner import build_script
from .parser import LRM, Message, parse_export
from .state import Bookmark, parse_since
from .tts import DEFAULT_VOICE, ENGINES, synthesize


def chat_name(messages: list[Message], path: Path) -> str:
    """Group name from the iOS encryption notice, else from the file name."""
    for msg in messages[:3]:
        if msg.sender and "end-to-end encrypted" in msg.text and msg.text.startswith(LRM):
            return msg.sender.rstrip(":").strip()
    stem = re.sub(r"^[0-9a-f]{8}-", "", path.stem)  # upload prefixes like 'a29e7f06-'
    stem = re.sub(r"^WhatsApp[ _]Chat[ _-]*(with[ _]|-[ _])?", "", stem, flags=re.IGNORECASE)
    return stem.replace("_", " ").strip(" -") or "chat"


def slug(name: str) -> str:
    return re.sub(r"[^\w]+", "-", name).strip("-").lower() or "chat"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="wa-digest", description="Read new WhatsApp group messages aloud.")
    p.add_argument("export", type=Path, help="WhatsApp export (.zip or .txt)")
    p.add_argument("--since", help="start point, e.g. 2d, 12h or 2026-09-20 (overrides the bookmark)")
    p.add_argument("--all", action="store_true", help="read the whole export, ignore the bookmark")
    p.add_argument("--first-run", default="1d", help="window used when there is no bookmark yet (default 1d)")
    p.add_argument("--out", type=Path, default=Path("out"), help="output folder (default ./out)")
    p.add_argument("--state", type=Path, default=Path("state.json"), help="bookmark file (default ./state.json)")
    p.add_argument("--engine", choices=sorted(ENGINES), default="edge")
    p.add_argument("--voice", default=DEFAULT_VOICE)
    p.add_argument("--rate", default="+0%", help="speaking speed, e.g. +25%%")
    p.add_argument("--no-dates", action="store_true", help="don't announce the day between messages")
    p.add_argument("--text-only", action="store_true", help="write the script as .txt, no audio")
    p.add_argument("--no-bookmark", action="store_true", help="don't move the bookmark forward")
    args = p.parse_args(argv)

    messages = parse_export(args.export)
    if not messages:
        print("No messages found - is this a WhatsApp export?", file=sys.stderr)
        return 1
    chat = chat_name(messages, args.export)
    bookmark = Bookmark(args.state)

    if args.all:
        start = None
    elif args.since:
        start = parse_since(args.since)
    else:
        start = bookmark.get(chat) or parse_since(args.first_run, now=messages[-1].ts)

    new = [m for m in messages if start is None or m.ts > start]
    script = build_script(new, day_headings=not args.no_dates)
    if not script:
        print(f"{chat}: nothing new since {start:%d.%m.%Y %H:%M}." if start else f"{chat}: nothing to read.")
        return 0

    stamp = new[-1].ts.strftime("%Y-%m-%d_%H%M")
    base = args.out / f"{slug(chat)}_{stamp}"
    args.out.mkdir(parents=True, exist_ok=True)
    base.with_suffix(".txt").write_text(script, encoding="utf-8")
    print(f"{chat}: {len(new)} new messages, {len(script)} characters -> {base.with_suffix('.txt')}")

    if not args.text_only:
        mp3 = synthesize(script, base.with_suffix(".mp3"), engine=args.engine, voice=args.voice, rate=args.rate)
        print(f"Audio: {mp3}")

    if not args.no_bookmark:
        bookmark.set(chat, new[-1].ts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line: wa-digest EXPORT.zip -> out/<chat>_<date>.mp3"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import NothingNew, make_episode
from .state import Bookmark
from .tts import DEFAULT_VOICE, ENGINES


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
    p.add_argument("--dates", action="store_true", help="announce the day when it changes")
    p.add_argument("--no-names", action="store_true", help="don't say the sender's first name")
    p.add_argument("--text-only", action="store_true", help="write the script as .txt, no audio")
    p.add_argument("--no-bookmark", action="store_true", help="don't move the bookmark forward")
    args = p.parse_args(argv)

    try:
        ep = make_episode(
            args.export, args.out, Bookmark(args.state),
            since=args.since, read_all=args.all, first_run=args.first_run,
            engine=args.engine, voice=args.voice, rate=args.rate,
            names=not args.no_names, dates=args.dates,
            audio=not args.text_only, move_bookmark=not args.no_bookmark,
        )
    except NothingNew as e:
        print(e)
        return 0
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"{ep.chat}: {ep.message_count} new messages, {ep.chars} characters -> {ep.text_path}")
    if ep.audio_path:
        print(f"Audio: {ep.audio_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

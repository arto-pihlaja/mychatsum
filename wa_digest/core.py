"""Shared pipeline: export file -> new messages -> script -> MP3 episode.

Used by both the command line (cli.py) and the web app (web.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .cleaner import build_script
from .parser import LRM, Message, parse_export
from .state import Bookmark, parse_since
from .tts import DEFAULT_VOICE, synthesize


@dataclass
class Episode:
    chat: str
    message_count: int
    chars: int
    text_path: Path
    audio_path: Path | None
    last_ts: datetime


class NothingNew(Exception):
    """No new speakable messages since the start point."""


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


def make_episode(
    export: Path,
    out_dir: Path,
    bookmark: Bookmark,
    *,
    since: str | None = None,
    read_all: bool = False,
    first_run: str = "1d",
    engine: str = "edge",
    voice: str = DEFAULT_VOICE,
    rate: str = "+0%",
    names: bool = True,
    dates: bool = False,
    audio: bool = True,
    move_bookmark: bool = True,
) -> Episode:
    """Create <out_dir>/<chat>_<timestamp>.txt (+ .mp3). Raises NothingNew or ValueError."""
    messages = parse_export(export)
    if not messages:
        raise ValueError("No messages found - is this a WhatsApp export?")
    chat = chat_name(messages, export)

    if read_all:
        start = None
    elif since:
        start = parse_since(since, now=messages[-1].ts)
    else:
        start = bookmark.get(chat) or parse_since(first_run, now=messages[-1].ts)

    new = [m for m in messages if start is None or m.ts > start]
    script = build_script(new, day_headings=dates, names=names)
    if not script:
        when = f" since {start:%d.%m.%Y %H:%M}" if start else ""
        raise NothingNew(f"{chat}: nothing new{when}.")

    last_ts = new[-1].ts
    base = out_dir / f"{slug(chat)}_{last_ts:%Y-%m-%d_%H%M}"
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = base.with_suffix(".txt")
    text_path.write_text(script, encoding="utf-8")

    audio_path = None
    if audio:
        audio_path = synthesize(script, base.with_suffix(".mp3"), engine=engine, voice=voice, rate=rate)

    if move_bookmark:
        bookmark.set(chat, last_ts)
    return Episode(chat, len(new), len(script), text_path, audio_path, last_ts)

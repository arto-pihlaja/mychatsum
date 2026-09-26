"""Parse WhatsApp "Export chat" text files into Message objects.

Supports the iOS format:
    [22.4.2026, 20.06.05] ~ Name: text
    [4/22/26, 8:06:06 PM] Name: text
and the common Android format:
    22.4.2026 klo 20.06 - Name: text
    22/04/2026, 20:06 - Name: text

Day/month order is detected per file: 22.4.2026 (day first, European) or
4/22/26 (month first, US - e.g. WhatsApp desktop in English).
Lines that don't start with a header belong to the previous message.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAX_TEXT_BYTES = 200 * 1024 * 1024  # guard against zip bombs
LRM = "‎"  # invisible marker WhatsApp puts before system/attachment text

# a/b are day and month in either order; resolved by _day_first()
_DATE = r"(?P<a>\d{1,2})(?P<sep>[./-])(?P<b>\d{1,2})[./-](?P<y>\d{2,4})"
_TIME = r"(?P<H>\d{1,2})[.:](?P<M>\d{2})(?:[.:](?P<S>\d{2}))?(?:\s?(?P<ampm>[AaPp]\.?[Mm]\.?))?"

IOS_HEADER = re.compile(rf"^{LRM}?\[{_DATE},?\s{_TIME}\]\s(?:-\s)?(?P<rest>.*)$")
ANDROID_HEADER = re.compile(rf"^{LRM}?{_DATE},?(?:\sklo)?\s{_TIME}\s-\s(?P<rest>.*)$")


@dataclass
class Message:
    ts: datetime
    sender: str | None  # None for group-level system lines (no "Name:" part)
    text: str


def _day_first(matches: list[re.Match]) -> bool:
    """Decide the date order for a whole export."""
    if any(int(m["a"]) > 12 for m in matches):
        return True
    if any(int(m["b"]) > 12 for m in matches):
        return False
    # Ambiguous (all days <= 12): slashes with AM/PM are the US style
    us_style = any(m["sep"] == "/" and m["ampm"] for m in matches)
    return not us_style


def _to_datetime(m: re.Match, day_first: bool = True) -> datetime:
    day, month = (int(m["a"]), int(m["b"])) if day_first else (int(m["b"]), int(m["a"]))
    y = int(m["y"])
    if y < 100:
        y += 2000
    hour = int(m["H"])
    ampm = (m["ampm"] or "").lower().replace(".", "")
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return datetime(y, month, day, hour, int(m["M"]), int(m["S"] or 0))


def _split_sender(rest: str) -> tuple[str | None, str]:
    # "Name: text" -> ("Name", "text"). Group-name system lines also look like
    # this, which is fine: their text starts with LRM and gets filtered later.
    if ": " in rest:
        sender, text = rest.split(": ", 1)
        return sender.strip(), text
    return None, rest


def parse_text(raw: str) -> list[Message]:
    raw = raw.lstrip("﻿")
    # pass 1: split into (header match, text) blocks
    blocks: list[list] = []
    for line in re.split(r"\r?\n", raw):
        match = IOS_HEADER.match(line) or ANDROID_HEADER.match(line)
        if match:
            blocks.append([match, match["rest"]])
        elif blocks:
            blocks[-1][1] += "\n" + line
        # text before the first header is ignored
    # pass 2: dates, now that the day/month order is known
    day_first = _day_first([b[0] for b in blocks])
    messages = []
    for match, rest in blocks:
        sender, text = _split_sender(rest)
        messages.append(Message(_to_datetime(match, day_first), sender, text.rstrip()))
    return messages


def read_export(path: str | Path) -> str:
    """Return chat text from a .zip export or a plain .txt file."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            txt_names = [n for n in zf.namelist() if n.lower().endswith(".txt")]
            if not txt_names:
                raise ValueError(f"No .txt file inside {path.name}")
            # iOS uses _chat.txt; Android "WhatsApp Chat with X.txt"
            name = "_chat.txt" if "_chat.txt" in txt_names else txt_names[0]
            if zf.getinfo(name).file_size > MAX_TEXT_BYTES:
                raise ValueError(f"{name} is too large")
            return io.TextIOWrapper(zf.open(name), encoding="utf-8").read()
    return path.read_text(encoding="utf-8")


def parse_export(path: str | Path) -> list[Message]:
    return parse_text(read_export(path))

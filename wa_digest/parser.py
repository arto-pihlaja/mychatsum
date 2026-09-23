"""Parse WhatsApp "Export chat" text files into Message objects.

Supports the iOS format:
    [22.4.2026, 20.06.05] ~ Name: text
and the common Android format:
    22.4.2026 klo 20.06 - Name: text
    22/04/2026, 20:06 - Name: text

Dates are assumed to be day-month-year (European locales).
Lines that don't start with a header belong to the previous message.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LRM = "‎"  # invisible marker WhatsApp puts before system/attachment text

_DATE = r"(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>\d{2,4})"
_TIME = r"(?P<H>\d{1,2})[.:](?P<M>\d{2})(?:[.:](?P<S>\d{2}))?(?:\s?(?P<ampm>[AaPp]\.?[Mm]\.?))?"

IOS_HEADER = re.compile(rf"^{LRM}?\[{_DATE},? {_TIME}\] (?P<rest>.*)$")
ANDROID_HEADER = re.compile(rf"^{LRM}?{_DATE},?(?: klo)? {_TIME} - (?P<rest>.*)$")


@dataclass
class Message:
    ts: datetime
    sender: str | None  # None for group-level system lines (no "Name:" part)
    text: str


def _to_datetime(m: re.Match) -> datetime:
    y = int(m["y"])
    if y < 100:
        y += 2000
    hour = int(m["H"])
    ampm = (m["ampm"] or "").lower().replace(".", "")
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return datetime(y, int(m["m"]), int(m["d"]), hour, int(m["M"]), int(m["S"] or 0))


def _split_sender(rest: str) -> tuple[str | None, str]:
    # "Name: text" -> ("Name", "text"). Group-name system lines also look like
    # this, which is fine: their text starts with LRM and gets filtered later.
    if ": " in rest:
        sender, text = rest.split(": ", 1)
        return sender.strip(), text
    return None, rest


def parse_text(raw: str) -> list[Message]:
    raw = raw.lstrip("﻿")
    messages: list[Message] = []
    for line in re.split(r"\r?\n", raw):
        match = IOS_HEADER.match(line) or ANDROID_HEADER.match(line)
        if match:
            sender, text = _split_sender(match["rest"])
            messages.append(Message(_to_datetime(match), sender, text))
        elif messages:
            messages[-1].text += "\n" + line
        # text before the first header is ignored
    for msg in messages:
        msg.text = msg.text.rstrip()
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
            return io.TextIOWrapper(zf.open(name), encoding="utf-8").read()
    return path.read_text(encoding="utf-8")


def parse_export(path: str | Path) -> list[Message]:
    return parse_text(read_export(path))

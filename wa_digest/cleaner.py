"""Turn parsed messages into plain text suitable for reading aloud.

Removes: names, timestamps, system notices, attachments, polls, @-mentions,
URLs, emojis and edit/deleted markers.
"""

from __future__ import annotations

import re
from datetime import date

import emoji

from .parser import LRM, Message

_URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+(\.[\w-]+)*\.[a-z]{2,}/\S*", re.IGNORECASE)
_FORMATTING = re.compile(r"[*~]")  # WhatsApp *bold* and ~strike~
_MENTION = re.compile(r"@⁨[^⁩]*⁩|@\+?\d{6,}")
_EDITED = re.compile(r"<(This message was edited|Tätä viestiä on muokattu|Muokattu)>", re.IGNORECASE)
# "Caption ‎image omitted" -> keep caption. Covers iOS and Android wording.
_MEDIA = re.compile(
    rf"{LRM}?\b(image|video|audio|sticker|GIF|Contact card) omitted"
    r"|<(Media omitted|Mediaa ei sisällytetty|attached: [^>]*)>",
    re.IGNORECASE,
)
# Messages to drop entirely (matched against cleaned-but-unstripped text).
_DROP = re.compile(
    rf"(document omitted|{LRM}?POLL:"
    r"|^(This message was deleted|You deleted this message|Tämä viesti poistettiin|Poistit tämän viestin)\.?$"
    r"|^null$)",
    re.IGNORECASE | re.MULTILINE,
)
_INVISIBLE = re.compile("[​-‏⁠-⁯﻿]")
_HAS_WORD = re.compile(r"\w")
_END_PUNCT = ".!?…:;"

FI_WEEKDAYS = ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"]
FI_MONTHS = [
    "tammikuuta", "helmikuuta", "maaliskuuta", "huhtikuuta", "toukokuuta", "kesäkuuta",
    "heinäkuuta", "elokuuta", "syyskuuta", "lokakuuta", "marraskuuta", "joulukuuta",
]


def is_system(msg: Message) -> bool:
    """Group notices: no sender (Android) or text starting with LRM (iOS)."""
    return msg.sender is None or msg.text.startswith(LRM) and not _MEDIA.match(msg.text)


def clean_text(text: str) -> str | None:
    """Return speakable text, or None if nothing worth reading remains."""
    if _DROP.search(text):
        return None
    text = _EDITED.sub("", text)
    text = _MEDIA.sub("", text)
    text = _MENTION.sub("", text)
    text = _URL.sub("", text)
    text = emoji.replace_emoji(text, replace="")
    text = _INVISIBLE.sub("", text)
    text = _FORMATTING.sub("", text)
    # tidy up commas/spaces left behind by removed mentions and emojis
    text = re.sub(r"(?:[ \t]*,)+", ",", text)
    text = re.sub(r"[ \t]+([,.!?])", r"\1", text)
    text = re.sub(r",([.!?])", r"\1", text)

    sentences = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", line).strip(" ,")
        if not _HAS_WORD.search(line):
            continue
        if line[-1] not in _END_PUNCT:
            line += "."  # makes the voice pause between lines
        sentences.append(line)
    return " ".join(sentences) or None


def day_heading(d: date) -> str:
    return f"{FI_WEEKDAYS[d.weekday()].capitalize()} {d.day}. {FI_MONTHS[d.month - 1]}."


def build_script(messages: list[Message], day_headings: bool = True) -> str:
    """Join cleaned messages into one script, one paragraph per message."""
    parts: list[str] = []
    current_day = None
    for msg in messages:
        if is_system(msg):
            continue
        text = clean_text(msg.text)
        if not text:
            continue
        if day_headings and msg.ts.date() != current_day:
            current_day = msg.ts.date()
            parts.append(day_heading(current_day))
        parts.append(text)
    return "\n\n".join(parts)

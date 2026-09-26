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
    rf"({LRM}?POLL:"
    r"|^(This message was deleted|You deleted this message|Tämä viesti poistettiin|Poistit tämän viestin)\.?$"
    r"|^null$)",
    re.IGNORECASE | re.MULTILINE,
)
# "file.pdf • ‎1 page ‎document omitted" -> keep just the file name
_DOCUMENT = re.compile(rf"\s*(•[^\n]*?)?{LRM}?document omitted", re.IGNORECASE)
# System notices, dropped wherever they appear (belt and braces on top of is_system)
SYSTEM_PATTERNS = [
    "changed this group's icon", "changed the group icon", "deleted this group's icon",
    "changed the group description", "changed the subject", "changed the group name",
    "created group", "joined using this group's invite link", "joined using a group link",
    "security code changed", "security code with", "pinned a message",
    "messages and calls are end-to-end encrypted", "is now an admin", "no longer an admin",
    "turned on disappearing messages", "turned off disappearing messages",
    "changed their phone number", "changed the settings",
]
_SYSTEM = re.compile("|".join(re.escape(p) for p in SYSTEM_PATTERNS), re.IGNORECASE)
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
    if msg.sender is None or _SYSTEM.search(msg.text):
        return True
    return msg.text.startswith(LRM) and not _MEDIA.match(msg.text)


def first_name(sender: str | None) -> str | None:
    """'~ Sari Ylikantola' -> 'Sari', '~ E e v a K' -> 'Eeva'. None for phone numbers."""
    if not sender:
        return None
    name = _INVISIBLE.sub("", sender).replace("\u202f", " ").replace("\xa0", " ")
    name = name.lstrip("~ ").strip()
    if not name or name[0] in "+0123456789":
        return None
    tokens = name.split()
    if len(tokens[0]) == 1 and len(tokens) > 1:
        # letter-spaced name: join single letters until the next capital
        letters = [tokens[0]]
        for tok in tokens[1:]:
            if len(tok) != 1 or tok.isupper():
                break
            letters.append(tok)
        return "".join(letters)
    return tokens[0]


def clean_text(text: str) -> str | None:
    """Return speakable text, or None if nothing worth reading remains."""
    if _DROP.search(text):
        return None
    text = _EDITED.sub("", text)
    text = _DOCUMENT.sub("", text)
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


def build_script(messages: list[Message], day_headings: bool = False, names: bool = True) -> str:
    """Join cleaned messages into one script, one paragraph per message.

    names: start each message with the sender's first name ("Sari. ...").
    day_headings: announce the date when the day changes.
    """
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
        name = first_name(msg.sender) if names else None
        parts.append(f"{name}. {text}" if name else text)
    return "\n\n".join(parts)

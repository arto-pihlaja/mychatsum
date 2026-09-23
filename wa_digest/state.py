"""Remembers the timestamp of the last message already read (the "bookmark")."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path


class Bookmark:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def get(self, chat: str) -> datetime | None:
        value = self._load().get(chat)
        return datetime.fromisoformat(value) if value else None

    def set(self, chat: str, ts: datetime) -> None:
        data = self._load()
        data[chat] = ts.isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


def parse_since(value: str, now: datetime | None = None) -> datetime:
    """'2d', '12h', '30m' relative to now, or an ISO date/datetime like 2026-09-20."""
    now = now or datetime.now()
    m = re.fullmatch(r"(\d+)\s*([dhm])", value.strip().lower())
    if m:
        amount, unit = int(m[1]), m[2]
        delta = {"d": timedelta(days=amount), "h": timedelta(hours=amount), "m": timedelta(minutes=amount)}[unit]
        return now - delta
    return datetime.fromisoformat(value)

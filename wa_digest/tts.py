"""Text-to-speech engines. Each engine turns a script into an MP3 file.

To add an engine (OpenAI, Azure...), write a function with the same signature
and register it in ENGINES.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

DEFAULT_VOICE = "fi-FI-NooraNeural"  # alternatives: fi-FI-HarriNeural, fi-FI-SelmaNeural


def edge(text: str, out: Path, voice: str = DEFAULT_VOICE, rate: str = "+0%") -> None:
    """Microsoft Edge online voices via the unofficial edge-tts package (free)."""
    import edge_tts

    proxy = os.environ.get("EDGE_TTS_PROXY")  # only needed behind an HTTP proxy
    communicate = edge_tts.Communicate(text, voice, rate=rate, proxy=proxy)
    asyncio.run(communicate.save(str(out)))


def espeak(text: str, out: Path, voice: str = "fi", rate: str = "+0%") -> None:
    """Offline, robotic fallback for testing. Needs espeak-ng and ffmpeg."""
    if not (shutil.which("espeak-ng") and shutil.which("ffmpeg")):
        raise RuntimeError("espeak engine needs espeak-ng and ffmpeg installed")
    words_per_min = int(175 * (1 + int(rate.strip("%")) / 100))
    if voice.startswith("fi-FI"):
        voice = "fi"
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "out.wav"
        txt = Path(tmp) / "in.txt"
        txt.write_text(text, encoding="utf-8")
        subprocess.run(["espeak-ng", "-v", voice, "-s", str(words_per_min), "-f", str(txt), "-w", str(wav)], check=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav), "-b:a", "64k", str(out)], check=True)


ENGINES: dict[str, Callable[..., None]] = {"edge": edge, "espeak": espeak}


def synthesize(text: str, out: str | Path, engine: str = "edge", voice: str = DEFAULT_VOICE, rate: str = "+0%") -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        fn = ENGINES[engine]
    except KeyError:
        raise ValueError(f"Unknown engine {engine!r}; choose from {', '.join(ENGINES)}") from None
    fn(text, out, voice=voice, rate=rate)
    return out

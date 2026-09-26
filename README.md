# wa-digest

Turns a WhatsApp group export into an MP3 you can listen to. Only the message
text is read aloud, prefixed with the sender's first name ("Sari. ..."). Timestamps, system notices, attachments, polls,
@-mentions, URLs and emojis are left out. A bookmark remembers where you
stopped, so each run reads only messages that are new since the last run.

## Setup

Linux/macOS:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m wa_digest "WhatsApp Chat - My Group.zip"
```

## Use

1. On the phone: open the group → ⋮ / group info → **Export chat → Without media**.
   Save the zip somewhere your computer can see (iCloud Drive, OneDrive, AirDrop).
2. Run:

```bash
.venv/bin/python -m wa_digest "WhatsApp Chat - My Group.zip"
# -> out/my-group_2026-09-23_2018.txt and .mp3
```

Useful options:

| Option | Meaning |
|---|---|
| `--since 2d` / `--since 2026-09-20` | start point, overrides the bookmark |
| `--all` | read the whole export |
| `--first-run 1d` | window used when there's no bookmark yet (default 1 day) |
| `--rate +25%` | speak faster |
| `--voice fi-FI-HarriNeural` | other voices: `fi-FI-NooraNeural` (default), `fi-FI-SelmaNeural` |
| `--dates` | announce the day when it changes (off by default) |
| `--no-names` | don't start messages with the sender's first name |
| `--text-only` | only write the cleaned script, no audio |
| `--no-bookmark` | don't move the bookmark (good for trying things out) |
| `--engine espeak` | offline robot voice for testing (needs `espeak-ng` + `ffmpeg`) |

Supports iOS (`[22.4.2026, 20.06.05] Name: text`) and Android
(`22.4.2026 klo 20.06 - Name: text`) exports. Dates are read as day.month.year.

WhatsApp exports at most the latest ~40 000 messages without media, so exports
stay small; the bookmark makes sure only new messages are read.

## Layout

```
wa_digest/parser.py   export (.zip/.txt) -> messages
wa_digest/cleaner.py  messages -> speakable script
wa_digest/state.py    bookmark (last read timestamp per chat)
wa_digest/tts.py      speech engines (edge, espeak) - add more here
wa_digest/cli.py      command line
```

Tests use synthetic fixtures only (`tests/fixtures`). Don't commit real exports.

```bash
.venv/bin/python -m pytest
```

## Notes

- `edge-tts` is an unofficial client for Microsoft's Edge voices. If it gets
  blocked or throttled, add an Azure TTS engine in `tts.py` (same voices, official).
- Behind an HTTP proxy, set `EDGE_TTS_PROXY`.

## Roadmap

- [ ] FastAPI service: `POST /upload` (zip from an iOS Shortcut), `GET /feed.xml` private podcast feed
- [ ] Deploy on Railway with a volume for `state.json` and MP3s, token auth
- [ ] Optional LLM summary mode

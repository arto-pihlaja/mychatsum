# mychatsum

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

## Web app (for the phone)

`wa_digest/web.py` is a small FastAPI app: upload the export zip, get a list
of episodes with an audio player (plays directly in Safari), text and download
links, and a delete button. Protected with HTTP Basic auth (any user name,
password from `APP_PASSWORD`).

Run locally:

```powershell
$env:APP_PASSWORD="choose-one"; .venv\Scripts\uvicorn wa_digest.web:app --reload
# open http://127.0.0.1:8000
```

| Env var | Default | Meaning |
|---|---|---|
| `APP_PASSWORD` | (required) | login password; the app refuses requests without it |
| `DATA_DIR` | `data` (`/data` in Docker) | episodes + bookmark |
| `TTS_ENGINE` / `TTS_VOICE` | `edge` / `fi-FI-NooraNeural` | speech settings |
| `KEEP_EPISODES` | `30` | older episodes are deleted |
| `MAX_UPLOAD_MB` | `50` | upload limit |

API for scripts/Shortcuts: `POST /upload` (multipart: `file`, optional
`since` = `new`/`1d`/`3d`/`7d`/`all`, `rate` = `normal`/`faster`/`fastest`)
returns JSON with `audio_url` and `page_url`.

## Deploy on Railway

1. Push this repo to GitHub.
2. Railway → New Project → Deploy from GitHub repo. It builds the `Dockerfile`.
3. Service → Variables: add `APP_PASSWORD`.
4. Service → right-click → Attach Volume, mount path `/data`
   (otherwise episodes and the bookmark vanish on every deploy).
5. Service → Settings → Networking → Generate Domain.
6. Optional, to save credit: Settings → enable Serverless (sleeps when idle;
   the first request after a pause is slow).

## On the iPhone

Simple way:

1. WhatsApp → group → name → Export Chat → Without Media → **Save to Files**.
2. Open the app URL in Safari (add it to the Home Screen), choose the zip, tap
   *Tee äänitiedosto*, and play.

One-tap way (Shortcuts app), once:

1. New shortcut → turn on **Show in Share Sheet**, accepting Files.
2. Action **Get Contents of URL**: `https://<your-app>/upload`, Method POST,
   Request Body *Form*, field `file` (type File) = *Shortcut Input*;
   Header `Authorization` = `Basic <base64 of user:password>`.
3. Action **Get Dictionary Value** `page_url` → **Open URLs**.

Then WhatsApp → Export Chat → Without Media → pick the shortcut; Safari opens
the list with the new episode on top.

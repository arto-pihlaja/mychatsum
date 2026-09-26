"""Web app: upload a WhatsApp export from the phone, listen to the result.

Run locally:  uvicorn wa_digest.web:app --reload
Environment:
  APP_PASSWORD   required; HTTP Basic auth password (any user name)
  DATA_DIR       where episodes and the bookmark live (default ./data; a volume on Railway)
  TTS_ENGINE     edge (default) | espeak
  TTS_VOICE      default fi-FI-NooraNeural
  KEEP_EPISODES  how many episodes to keep (default 30)
  MAX_UPLOAD_MB  upload size limit (default 50)
"""

from __future__ import annotations

import html
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.concurrency import run_in_threadpool

from .core import NothingNew, make_episode
from .state import Bookmark
from .tts import DEFAULT_VOICE

SINCE_CHOICES = {"new": None, "1d": "1d", "3d": "3d", "7d": "7d", "all": "all"}
RATE_CHOICES = {"normal": "+0%", "faster": "+25%", "fastest": "+50%"}
_NAME_OK = re.compile(r"^[\w.-]+$")


def _settings() -> dict:
    data = Path(os.environ.get("DATA_DIR", "data"))
    return {
        "password": os.environ.get("APP_PASSWORD", ""),
        "data": data,
        "episodes": data / "episodes",
        "state": data / "state.json",
        "engine": os.environ.get("TTS_ENGINE", "edge"),
        "voice": os.environ.get("TTS_VOICE", DEFAULT_VOICE),
        "keep": int(os.environ.get("KEEP_EPISODES", "30")),
        "max_bytes": int(float(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024),
    }


app = FastAPI(title="wa-digest", docs_url=None, redoc_url=None)
_security = HTTPBasic(realm="wa-digest")
_lock = threading.Lock()  # one conversion at a time; also protects the bookmark


def require_auth(creds: HTTPBasicCredentials = Depends(_security)) -> None:
    password = _settings()["password"]
    if not password:
        raise HTTPException(503, "Set the APP_PASSWORD environment variable first.")
    if not secrets.compare_digest(creds.password.encode(), password.encode()):
        raise HTTPException(401, "Wrong password", headers={"WWW-Authenticate": 'Basic realm="wa-digest"'})


# ---------- episodes on disk ----------

def _list_episodes() -> list[dict]:
    folder = _settings()["episodes"]
    items = []
    for meta_path in folder.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta["name"] = meta_path.stem
        items.append(meta)
    return sorted(items, key=lambda m: m.get("created", ""), reverse=True)


def _delete_episode(name: str) -> None:
    folder = _settings()["episodes"]
    for ext in (".mp3", ".txt", ".json"):
        (folder / f"{name}{ext}").unlink(missing_ok=True)


def _prune(keep: int) -> None:
    for meta in _list_episodes()[keep:]:
        _delete_episode(meta["name"])


def _convert(upload_path: Path, since: str | None, rate: str) -> dict:
    s = _settings()
    with _lock:
        ep = make_episode(
            upload_path, s["episodes"], Bookmark(s["state"]),
            since=None if since in (None, "all") else since,
            read_all=since == "all",
            engine=s["engine"], voice=s["voice"], rate=rate,
        )
        name = ep.text_path.stem
        meta = {
            "chat": ep.chat,
            "messages": ep.message_count,
            "chars": ep.chars,
            "last_message": ep.last_ts.isoformat(),
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        (s["episodes"] / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        _prune(s["keep"])
    return {"name": name, **meta}


# ---------- routes ----------

@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/upload", dependencies=[Depends(require_auth)])
async def upload(
    request: Request,
    file: UploadFile = File(...),
    since: str = Form("new"),
    rate: str = Form("normal"),
):
    """Accepts the export zip. Browsers get redirected back to the list; other clients get JSON."""
    s = _settings()
    if since not in SINCE_CHOICES:
        raise HTTPException(422, f"since must be one of {', '.join(SINCE_CHOICES)}")
    wants_html = "text/html" in request.headers.get("accept", "")

    filename = Path(file.filename or "export.zip").name
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        size = 0
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > s["max_bytes"]:
                    raise HTTPException(413, "File too large")
                out.write(chunk)
        try:
            result = await run_in_threadpool(
                _convert, path, SINCE_CHOICES[since], RATE_CHOICES.get(rate, "+0%")
            )
        except NothingNew as e:
            if wants_html:
                return RedirectResponse(f"/?msg={_q(str(e))}", status_code=303)
            return JSONResponse({"status": "nothing_new", "detail": str(e)})
        except ValueError as e:
            if wants_html:
                return RedirectResponse(f"/?msg={_q(str(e))}", status_code=303)
            raise HTTPException(422, str(e))

    audio_url = str(request.url_for("episode_file", name=result["name"], ext="mp3"))
    if wants_html:
        return RedirectResponse("/?msg=" + _q(f"Valmis: {result['messages']} viestiä"), status_code=303)
    return {"status": "ok", "audio_url": audio_url, "page_url": str(request.url_for("index")), **result}


@app.get("/episodes/{name}.{ext}", name="episode_file", dependencies=[Depends(require_auth)])
def episode_file(name: str, ext: str):
    if ext not in ("mp3", "txt") or not _NAME_OK.match(name):
        raise HTTPException(404)
    path = _settings()["episodes"] / f"{name}.{ext}"
    if not path.exists():
        raise HTTPException(404)
    media = "audio/mpeg" if ext == "mp3" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media)


@app.post("/episodes/{name}/delete", dependencies=[Depends(require_auth)])
def delete_episode(name: str):
    if not _NAME_OK.match(name):
        raise HTTPException(404)
    _delete_episode(name)
    return RedirectResponse("/", status_code=303)


@app.get("/", response_class=HTMLResponse, name="index", dependencies=[Depends(require_auth)])
def index(msg: str = ""):
    return HTMLResponse(_page(_list_episodes(), msg))


# ---------- HTML ----------

def _q(text: str) -> str:
    from urllib.parse import quote
    return quote(text)


def _fmt_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m. klo %H.%M")
    except ValueError:
        return iso


def _page(episodes: list[dict], msg: str) -> str:
    e = html.escape
    rows = []
    for ep in episodes:
        name = e(ep["name"])
        mp3 = f"/episodes/{name}.mp3"
        rows.append(f"""
      <li class="ep">
        <div class="title">{e(ep.get('chat', ''))}</div>
        <div class="meta">{ep.get('messages', '?')} viestiä · viimeisin {e(_fmt_time(ep.get('last_message', '')))}</div>
        <audio controls preload="none" src="{mp3}"></audio>
        <div class="actions">
          <a href="/episodes/{name}.txt">Teksti</a>
          <a href="{mp3}" download>Lataa</a>
          <form method="post" action="/episodes/{name}/delete" onsubmit="return confirm('Poistetaanko?')">
            <button type="submit" class="link">Poista</button>
          </form>
        </div>
      </li>""")
    body = "".join(rows) or '<li class="empty">Ei vielä jaksoja.</li>'
    notice = f'<p class="notice">{e(msg)}</p>' if msg else ""
    since_opts = "".join(
        f'<option value="{k}">{label}</option>'
        for k, label in [("new", "Uudet (kirjanmerkistä)"), ("1d", "1 päivä"), ("3d", "3 päivää"),
                         ("7d", "7 päivää"), ("all", "Kaikki")]
    )
    rate_opts = "".join(
        f'<option value="{k}">{label}</option>'
        for k, label in [("normal", "Normaali"), ("faster", "Nopeampi"), ("fastest", "Nopein")]
    )
    return f"""<!doctype html>
<html lang="fi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>WA-kuuntelu</title>
<style>
  :root {{ --bg:#f6f7f5; --card:#fff; --text:#1c1f1d; --muted:#667068; --accent:#1f7a54; --on-accent:#fff; --line:#e2e5e1; color-scheme:light dark; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#121412; --card:#1c1f1d; --text:#e8ebe8; --muted:#9aa39c; --accent:#4fbf8b; --on-accent:#0d1f16; --line:#2c302d; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:16px; font:16px/1.4 -apple-system, system-ui, sans-serif; background:var(--bg); color:var(--text); }}
  main {{ max-width:640px; margin:0 auto; }}
  h1 {{ font-size:1.3rem; margin:4px 0 16px; }}
  form.upload, li.ep {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }}
  form.upload {{ display:grid; gap:10px; margin-bottom:20px; }}
  label {{ font-size:.85rem; color:var(--muted); display:grid; gap:4px; }}
  select, input[type=file] {{ font:inherit; color:inherit; }}
  select {{ padding:8px; border-radius:8px; border:1px solid var(--line); background:var(--bg); }}
  button.primary {{ font:inherit; font-weight:600; padding:12px; border:0; border-radius:10px; background:var(--accent); color:var(--on-accent); }}
  ul {{ list-style:none; padding:0; margin:0; display:grid; gap:12px; }}
  .title {{ font-weight:600; }}
  .meta, .empty {{ color:var(--muted); font-size:.85rem; margin-bottom:8px; }}
  audio {{ width:100%; }}
  .actions {{ display:flex; gap:16px; margin-top:8px; font-size:.9rem; align-items:center; }}
  .actions a, button.link {{ color:var(--accent); background:none; border:0; padding:0; font:inherit; text-decoration:none; }}
  .actions form {{ margin:0; }}
  .notice {{ background:var(--card); border-left:4px solid var(--accent); padding:10px 12px; border-radius:6px; }}
  .busy button.primary {{ opacity:.6; }}
</style></head>
<body><main>
  <h1>WhatsApp-kuuntelu</h1>
  {notice}
  <form class="upload" method="post" action="/upload" enctype="multipart/form-data"
        onsubmit="this.classList.add('busy'); this.querySelector('button').textContent='Muunnetaan…';">
    <label>Chat-vienti (.zip)
      <input type="file" name="file" accept=".zip,.txt,application/zip" required>
    </label>
    <label>Mitkä viestit <select name="since">{since_opts}</select></label>
    <label>Puhenopeus <select name="rate">{rate_opts}</select></label>
    <button class="primary" type="submit">Tee äänitiedosto</button>
  </form>
  <ul>{body}</ul>
</main></body></html>"""

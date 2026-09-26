import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wa_digest import tts

FIX = Path(__file__).parent / "fixtures"
AUTH = ("me", "secret")


def fake_engine(text, out, voice, rate):
    Path(out).write_bytes(b"ID3fake-mp3:" + text.encode())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setitem(tts.ENGINES, "fake", fake_engine)
    monkeypatch.setenv("TTS_ENGINE", "fake")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("KEEP_EPISODES", "2")
    from wa_digest.web import app
    return TestClient(app)


def export_zip(name="WhatsApp Chat - Testiryhmä.zip", fixture="ios_chat.txt"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.write(FIX / fixture, "_chat.txt")
    return {"file": (name, buf.getvalue(), "application/zip")}


def test_health_is_public(client):
    assert client.get("/health").json() == {"ok": True}


def test_auth_required(client):
    assert client.get("/").status_code == 401
    assert client.get("/", auth=("me", "wrong")).status_code == 401
    assert client.get("/", auth=AUTH).status_code == 200


def test_no_password_configured_fails_closed(client, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD")
    assert client.get("/", auth=AUTH).status_code == 503


def test_upload_json_flow_and_bookmark(client):
    r = client.post("/upload", files=export_zip(), data={"since": "all"}, auth=AUTH)
    body = r.json()
    assert body["status"] == "ok" and body["chat"] == "Testiryhmä"
    mp3 = client.get(f"/episodes/{body['name']}.mp3", auth=AUTH)
    assert mp3.status_code == 200 and mp3.headers["content-type"] == "audio/mpeg"
    assert b"Anna. Hei kaikki" in mp3.content
    txt = client.get(f"/episodes/{body['name']}.txt", auth=AUTH)
    assert txt.text.startswith("Anna. Hei kaikki")
    # same export again: bookmark says nothing new
    again = client.post("/upload", files=export_zip(), auth=AUTH).json()
    assert again["status"] == "nothing_new"
    # listed on the page
    assert "Testiryhmä" in client.get("/", auth=AUTH).text


def test_browser_upload_redirects(client):
    r = client.post("/upload", files=export_zip(), data={"since": "all", "rate": "faster"},
                    auth=AUTH, headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/?msg=")


def test_delete_and_prune(client):
    names = []
    for i in range(3):
        r = client.post("/upload", files=export_zip(f"WhatsApp Chat - Ryhmä {i}.zip", "android_chat.txt"), data={"since": "all"}, auth=AUTH)
        names.append(r.json()["name"])
    page = client.get("/", auth=AUTH).text
    # Android exports are named after the file -> 3 different chats, KEEP_EPISODES=2 keeps 2
    assert page.count('class="ep"') == 2
    client.post(f"/episodes/{names[-1]}/delete", auth=AUTH)
    assert client.get(f"/episodes/{names[-1]}.mp3", auth=AUTH).status_code == 404


def test_bad_input(client):
    r = client.post("/upload", files={"file": ("x.txt", b"not a chat", "text/plain")}, auth=AUTH)
    assert r.status_code == 422
    assert client.get("/episodes/..%2Fstate.mp3", auth=AUTH).status_code == 404

import zipfile
from datetime import datetime
from pathlib import Path

from wa_digest.cleaner import build_script, clean_text
from wa_digest.cli import chat_name, main
from wa_digest.parser import parse_export, parse_text
from wa_digest.state import Bookmark, parse_since

FIX = Path(__file__).parent / "fixtures"


def ios():
    return parse_export(FIX / "ios_chat.txt")


def test_ios_parsing_joins_multiline_messages():
    msgs = ios()
    assert len(msgs) == 12
    assert msgs[2].ts == datetime(2026, 9, 1, 10, 5)
    assert "Tervetuloa ryhmään" in msgs[2].text
    assert msgs[7].text.count("OPTION") == 2  # poll lines stay in their message


def test_android_parsing():
    msgs = parse_export(FIX / "android_chat.txt")
    assert [m.sender for m in msgs] == [None, "Anna", "Bertta", "Bertta"]
    assert msgs[1].text == "Hei kaikki\ntoinen rivi"
    assert msgs[3].ts == datetime(2026, 9, 2, 21, 15)


def test_script_contains_only_speakable_text():
    script = build_script(ios())
    for banned in ["Anna", "http", "kuksaan", "omitted", "POLL", "Kyllä", "edited", "pdf",
                   "Bertta", "Cecilia", "encrypted", "added", "*", "🎉", "10.05", "⁨"]:
        assert banned not in script, banned
    assert "Hei kaikki. Tervetuloa ryhmään! Kokous on ke klo 18.30." in script
    assert "Aikataulu tässä." in script  # image caption kept
    assert "Mitä mieltä, ja muut?" in script
    assert "Tärkeää: muistakaa ilmoittautua." in script
    assert script.startswith("Tiistai 1. syyskuuta.")
    assert "Keskiviikko 2. syyskuuta." in script


def test_emoji_only_message_is_dropped():
    assert clean_text("👍🏼") is None


def test_android_script():
    script = build_script(parse_export(FIX / "android_chat.txt"), day_headings=False)
    assert script == "Hei kaikki. toinen rivi.\n\nMoi taas."


def test_zip_input_and_chat_name(tmp_path):
    z = tmp_path / "WhatsApp Chat - Testiryhmä.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(FIX / "android_chat.txt", "_chat.txt")
    msgs = parse_export(z)
    assert len(msgs) == 4
    assert chat_name(msgs, z) == "Testiryhmä"  # from file name (Android has no notice)
    assert chat_name(ios(), FIX / "x.txt") == "Testiryhmä"  # from iOS notice


def test_bookmark_roundtrip(tmp_path):
    b = Bookmark(tmp_path / "s.json")
    assert b.get("x") is None
    b.set("x", datetime(2026, 9, 1, 10, 0))
    assert b.get("x") == datetime(2026, 9, 1, 10, 0)


def test_parse_since():
    now = datetime(2026, 9, 23, 12, 0)
    assert parse_since("2d", now) == datetime(2026, 9, 21, 12, 0)
    assert parse_since("2026-09-20") == datetime(2026, 9, 20)


def test_cli_only_reads_new_messages(tmp_path):
    args = [str(FIX / "ios_chat.txt"), "--text-only", "--out", str(tmp_path), "--state", str(tmp_path / "s.json")]
    assert main(args + ["--all"]) == 0
    first = sorted(tmp_path.glob("*.txt"))
    assert len(first) == 1
    # Second run: bookmark is at the last message, so nothing new
    assert main(args) == 0
    assert sorted(tmp_path.glob("*.txt")) == first

import zipfile
from datetime import datetime
from pathlib import Path

from wa_digest.cleaner import build_script, clean_text, first_name
from wa_digest.cli import main
from wa_digest.core import chat_name
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
    for banned in ["Ylikantola", "http", "kuksaan", "omitted", "page", "POLL", "Kyllä", "edited",
                   "encrypted", "added", "created", "*", "~", "🎉", "10.05", "syyskuuta", "\u2068"]:
        assert banned not in script, banned
    assert script.split("\n\n") == [
        "Anna. Hei kaikki. Tervetuloa ryhmään! Kokous on ke klo 18.30.",
        "Bertta. Katso ja.",
        "Anna. ohje.pdf.",
        "Anna. Aikataulu tässä.",
        "Anna. Mitä mieltä, ja muut?",
        "Bertta. Tärkeää: muistakaa ilmoittautua.",
    ]


def test_user_example():
    raw = (
        "[22.4.2026, 20.20.13] ~\u202fMaija Meikäläinen: Koekisa toteutetaan kalojen kuvilla.\r\n"
        "[22.4.2026, 20.33.24] ~\u202fMaija Meikäläinen: \u200e~\u202fMaija Meikäläinen changed this group's icon\r\n"
        "\u200e[22.4.2026, 20.54.33] ~\u202fMaija Meikäläinen: ohjeet-kaikille.pdf • \u200e1 page \u200edocument omitted\r\n"
        "[22.4.2026, 21.04.30] ~\u202fMaija Meikäläinen: Tästä tuli tällanen infotulva.\nSorry 😬\r\n"
    )
    assert build_script(parse_text(raw)) == (
        "Maija. Koekisa toteutetaan kalojen kuvilla.\n\n"
        "Maija. ohjeet-kaikille.pdf.\n\n"
        "Maija. Tästä tuli tällanen infotulva. Sorry."
    )


def test_day_headings_optional():
    script = build_script(ios(), day_headings=True, names=False)
    assert script.startswith("Tiistai 1. syyskuuta.\n\nHei kaikki.")
    assert "Keskiviikko 2. syyskuuta." in script


def test_first_name():
    assert first_name("~\u202fSari Ylikantola") == "Sari"
    assert first_name("~ E e v a K") == "Eeva"
    assert first_name("Mare") == "Mare"
    assert first_name("+358 44 1234567") is None
    assert first_name(None) is None


def test_emoji_only_message_is_dropped():
    assert clean_text("👍🏼") is None


def test_android_script():
    script = build_script(parse_export(FIX / "android_chat.txt"))
    assert script == "Anna. Hei kaikki. toinen rivi.\n\nBertta. Moi taas."


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


def test_us_date_format_desktop_export():
    raw = (
        "[4/22/26, 8:06:06\u202fPM] - +358 40 1234567 added You\r\n"
        "[4/22/26, 8:11:17 PM] Maija Meikäläinen: Hei kaikki\nToinen rivi\r\n"
        "[5/1/26, 9:05:00 AM] Bertta: Katso https://example.com/a?b=1 ja http://x.fi/y tästä\r\n"
    )
    msgs = parse_text(raw)
    assert [m.ts for m in msgs] == [
        datetime(2026, 4, 22, 20, 6, 6), datetime(2026, 4, 22, 20, 11, 17), datetime(2026, 5, 1, 9, 5)]
    assert msgs[0].sender is None  # "added You" is a system line
    assert build_script(msgs) == "Maija. Hei kaikki. Toinen rivi.\n\nBertta. Katso ja tästä."


def test_ambiguous_dates_default_to_day_first():
    msgs = parse_text("[3.4.2026, 10.00.00] A: moi\r\n")
    assert msgs[0].ts == datetime(2026, 4, 3, 10, 0)


def test_urls_never_read():
    for text in ["https://a.b/c", "Linkki: https://teams.microsoft.com/meet/1?p=x", "(http://x.fi)", "www.x.fi/y"]:
        assert "http" not in (clean_text(text) or "") and "www" not in (clean_text(text) or "")

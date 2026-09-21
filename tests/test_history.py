import json
from pathlib import Path

import pytest

from yue_studio.history import (
    EMPTY_NOTE,
    KIND_LABELS,
    TABLE_HEADERS,
    delete_entry,
    format_duration,
    format_stamp,
    history_table,
    load_entry,
    list_history,
    style_snippet,
)


def _write_json(path: Path, value: dict):
    path.write_text(json.dumps(value), encoding="utf-8")


def _song_dir(root: Path, stamp: str, identifier="city_lights", *, audio=True, style="warm piano pop"):
    directory = root / f"song-{stamp}-{identifier}"
    directory.mkdir()
    if audio:
        (directory / "audio.flac").write_bytes(b"fLaC")
    _write_json(directory / "request.json", {
        "style": style,
        "lyrics": "[Verse]\nhello",
        "cot": "full",
        "seed": 831001,
        "id": identifier,
    })
    _write_json(directory / "result.json", {"status": "complete", "audio_seconds": 64.6})
    (directory / "score.abc").write_text("X:1\nT:t\nK:C\nC", encoding="utf-8")
    (directory / "plan_manifest.json").write_text("{}", encoding="utf-8")
    return directory


def _plan_dir(root: Path, stamp: str, identifier="city_lights"):
    directory = root / f"plan-{stamp}-{identifier}"
    directory.mkdir()
    (directory / "score.abc").write_text("X:1\nT:plan\nK:C\nG", encoding="utf-8")
    (directory / "plan_manifest.json").write_text("{}", encoding="utf-8")
    _write_json(directory / "plan.json", {
        "request": {
            "style": "jazz trio",
            "lyrics": "[Chorus]\nnight",
            "cot": "full",
            "seed": 7,
            "id": identifier,
        },
    })
    return directory


def _transcribe_dir(root: Path, stamp: str, identifier="cover"):
    directory = root / f"transcribe-{stamp}-{identifier}"
    directory.mkdir()
    (directory / "score.abc").write_text("X:1\nT:cover\nK:C\nC", encoding="utf-8")
    return directory


def test_list_history_keeps_songs_and_plans(tmp_path: Path):
    older = _song_dir(tmp_path, "20260920-210000")
    newer = _song_dir(tmp_path, "20260920-233150", style="English, warm piano")
    plan = _plan_dir(tmp_path, "20260920-220000")
    transcribe = _transcribe_dir(tmp_path, "20260920-215000")
    _song_dir(tmp_path, "20260920-200000", identifier="broken", audio=False)
    (tmp_path / "not-a-job").mkdir()
    (tmp_path / "scratch.txt").write_text("x", encoding="utf-8")

    entries = list_history(tmp_path)
    assert [item.directory.name for item in entries] == [
        newer.name, plan.name, transcribe.name, older.name,
    ]
    assert entries[0].kind == "song" and entries[0].audio is not None
    assert entries[1].kind == "plan" and entries[1].audio is None
    assert entries[2].kind == "transcribe" and entries[2].audio is None
    assert entries[0].audio_seconds == pytest.approx(64.6)
    assert entries[1].request == {}


def test_history_table_rows_and_empty_note(tmp_path: Path):
    style = "English, warm piano pop, expressive female voice"
    _song_dir(tmp_path, "20260920-233150", style=style)
    rows, paths, note = history_table(tmp_path)
    assert TABLE_HEADERS[0] == "时间"
    assert rows == [[
        "2026-09-20 23:31:50",
        KIND_LABELS["song"],
        "city_lights",
        "1:05",
        style_snippet(style),
    ]]
    assert Path(paths[0]).name == "song-20260920-233150-city_lights"
    assert note == ""
    empty_rows, empty_paths, empty_note = history_table(tmp_path / "missing")
    assert empty_rows == [] and empty_paths == []
    assert empty_note == EMPTY_NOTE


def test_load_entry_reads_request_and_plan_fallback(tmp_path: Path):
    song = _song_dir(tmp_path, "20260920-233150")
    loaded = load_entry(song, root=tmp_path)
    assert loaded.request["style"].startswith("warm")
    assert loaded.request["lyrics"].startswith("[Verse]")
    assert loaded.audio == (song / "audio.flac").resolve()
    assert "T:t" in loaded.abc
    assert loaded.has_plan

    plan = _plan_dir(tmp_path, "20260920-220000")
    from_plan = load_entry(plan, root=tmp_path)
    assert from_plan.request["style"] == "jazz trio"
    assert from_plan.request["lyrics"] == "[Chorus]\nnight"
    assert from_plan.audio is None
    assert "T:plan" in from_plan.abc

    transcribe = _transcribe_dir(tmp_path, "20260920-215000")
    from_tr = load_entry(transcribe, root=tmp_path)
    assert from_tr.request == {}
    assert "T:cover" in from_tr.abc


def test_delete_entry_only_under_root(tmp_path: Path):
    song = _song_dir(tmp_path, "20260920-233150")
    deleted = delete_entry(song, root=tmp_path)
    assert deleted == song.resolve()
    assert not song.exists()

    outside = tmp_path.parent / "song-20260920-233150-escape"
    outside.mkdir()
    (outside / "audio.flac").write_bytes(b"fLaC")
    with pytest.raises(ValueError, match="不在输出根目录下"):
        delete_entry(outside, root=tmp_path)

    stray = tmp_path / "other-dir"
    stray.mkdir()
    with pytest.raises(ValueError, match="不是工作室任务目录"):
        delete_entry(stray, root=tmp_path)


def test_format_helpers():
    assert format_stamp("20260920-233150") == "2026-09-20 23:31:50"
    assert format_duration(64.6) == "1:05"
    assert format_duration(None) == "—"
    assert style_snippet("") == "—"
    assert style_snippet("short") == "short"
    assert style_snippet("x" * 41).endswith("…")
    assert len(style_snippet("x" * 41)) == 40

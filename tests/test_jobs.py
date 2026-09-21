from pathlib import Path

import pytest

from yue_studio.jobs import new_job_dir, song_id


def test_song_id_accepts_native_ids():
    assert song_id("city_lights") == "city_lights"
    assert song_id("cover-1") == "cover-1"


def test_new_job_dir_is_fresh(tmp_path: Path):
    first = new_job_dir(tmp_path, "plan", "city_lights")
    assert first.is_dir()
    assert first.parent == tmp_path
    assert "plan-" in first.name
    assert first.name.endswith("city_lights")


def test_new_job_dir_reuses_empty_leftover(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.jobs.time.strftime", lambda _: "20260921-002129")
    leftover = tmp_path / "transcribe-20260921-002129-cover"
    leftover.mkdir()
    reused = new_job_dir(tmp_path, "transcribe", "cover")
    assert reused == leftover
    assert leftover.is_dir()
    (leftover / "score.abc").write_text("X:1\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Nonempty output"):
        new_job_dir(tmp_path, "transcribe", "cover")

from pathlib import Path

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

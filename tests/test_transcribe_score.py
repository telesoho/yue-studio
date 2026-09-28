from pathlib import Path
from types import SimpleNamespace

import pytest

from yue_studio.paths import abc_tools_path
from yue_studio.runner import StudioRunner

ABC = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
"C"C4D4E4F4|G4A4B4c4|
V: Ins
Z2|
"""


def _need_tools():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")


def _patch(monkeypatch, tmp_path: Path, separate, recognize):
    monkeypatch.setattr("yue_studio.runner.outputs_dir", lambda: tmp_path)
    monkeypatch.setattr("yue_studio.runner.models_dir", lambda: tmp_path)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF")
    model = tmp_path / "SheetSage2"
    model.mkdir()
    mert = tmp_path / "MERT-v2-FullSong"
    mert.mkdir()
    captured = {}

    def fake_run_transcribe(path, directory, **kwargs):
        from yue_studio.sheetsage import _clear_empty_output

        captured.update(kwargs)
        captured["audio"] = Path(path)
        directory = _clear_empty_output(Path(directory))
        directory.mkdir()
        score = directory / "score.abc"
        score.write_text(ABC, encoding="utf-8")
        return score

    monkeypatch.setattr("yue_studio.runner.run_transcribe", fake_run_transcribe)
    monkeypatch.setattr(
        "yue_studio.runner.scan_catalog",
        lambda: [
            SimpleNamespace(spec=SimpleNamespace(name="SheetSage2"), present=True, path=model),
            SimpleNamespace(spec=SimpleNamespace(name="MERT-v2-FullSong"), present=True, path=mert),
        ],
    )
    monkeypatch.setattr("yue_studio.runner.separate_vocals", separate)
    monkeypatch.setattr("yue_studio.runner.recognize_lyrics", recognize)
    return audio, captured


def test_save_source_audio_keeps_original_bytes(tmp_path: Path):
    from yue_studio.runner import save_source_audio

    src = tmp_path / "mix.MP3"
    src.write_bytes(b"ID3" + b"\x00" * 20)
    job = tmp_path / "job"
    job.mkdir()
    saved = save_source_audio(src, job)
    assert saved.name == "source.mp3"
    assert saved.read_bytes() == src.read_bytes()

    bare = tmp_path / "upload"
    bare.write_bytes(b"fLaC" + b"\x00" * 8)
    sniffed = save_source_audio(bare, job)
    assert sniffed.name == "source.flac"
    assert sniffed.read_bytes() == bare.read_bytes()


def test_transcribe_score_writes_aligned_lyrics(tmp_path: Path, monkeypatch):
    _need_tools()
    vocals = tmp_path / "vocals.wav"
    vocals.write_bytes(b"v")
    seen = {}

    def separate(audio, output, **kwargs):
        seen["separate_audio"] = Path(audio)
        return vocals

    def recognize(audio, output, **kwargs):
        seen["recognize_audio"] = Path(audio)
        seen["language"] = kwargs.get("language")
        return [{"text": "春眠不觉晓处处闻", "start": 0.0, "end": 4.0}]

    audio, captured = _patch(monkeypatch, tmp_path, separate, recognize)
    runner = StudioRunner()
    runner.set_use_gpu(False)
    result = runner.transcribe_score(audio, language="zh")
    score = Path(result["score"])
    assert captured["task"] == "full"
    assert captured["device"] == "cpu"
    assert captured["audio"].name == "source.wav"
    assert Path(result["directory"]) not in captured["audio"].parents
    assert seen["recognize_audio"] == vocals
    assert seen["language"] == "zh"
    saved = Path(result["source"])
    assert saved.name == "source.wav"
    assert saved.read_bytes() == audio.read_bytes()
    assert seen["separate_audio"] == saved
    assert "w:" not in score.read_text(encoding="utf-8")
    assert "w:" not in result["abc"]
    assert "w: 春 眠 不 觉 晓 处 处 闻" in result["display_abc"]
    assert result["lyrics"] == "[Verse]\n春眠不觉晓处处闻"
    assert (score.parent / "lyrics.txt").read_text(encoding="utf-8") == result["lyrics"]
    assert Path(result["directory"]).name.endswith("-score")
    assert result["lyric_error"] is None


def test_transcribe_score_uses_mix_when_separation_fails(tmp_path: Path, monkeypatch):
    _need_tools()
    seen = {}

    def separate(audio, output, **kwargs):
        raise RuntimeError("demucs exploded")

    def recognize(audio, output, **kwargs):
        seen["audio"] = Path(audio)
        return [{"text": "春", "start": 0.0, "end": 0.5}]

    audio, _captured = _patch(monkeypatch, tmp_path, separate, recognize)
    result = StudioRunner().transcribe_score(audio)
    assert seen["audio"] == Path(result["source"])
    assert Path(result["source"]).read_bytes() == audio.read_bytes()
    assert any("原混音" in str(item) for item in result["warnings"])
    assert result["lyric_error"] is None
    assert "春" in result["lyrics"]
    assert "w:" not in Path(result["score"]).read_text(encoding="utf-8")


def test_transcribe_score_keeps_score_when_recognition_fails(tmp_path: Path, monkeypatch):
    vocals = tmp_path / "vocals.wav"
    vocals.write_bytes(b"v")

    def separate(audio, output, **kwargs):
        return vocals

    def recognize(audio, output, **kwargs):
        raise RuntimeError("whisper missing")

    audio, captured = _patch(monkeypatch, tmp_path, separate, recognize)
    result = StudioRunner().transcribe_score(audio)
    text = Path(result["score"]).read_text(encoding="utf-8")
    assert captured["task"] == "full"
    assert "w:" not in text
    assert result["abc"] == text
    assert result["lyrics"] == ""
    assert "whisper missing" in result["lyric_error"]
    assert any("歌词识别失败" in str(item) for item in result["warnings"])
    assert (Path(result["directory"]) / "score.abc").is_file()

from pathlib import Path
from types import SimpleNamespace

import pytest

from yue_studio.jobs import new_job_dir, song_id
from yue_studio.sheetsage import (
    TORCH_CPU_INDEX,
    TORCH_CUDA_INDEX,
    create_venv_command,
    ensure_sheetsage_env,
    ensure_transcribe_ready,
    install_hub_command,
    install_requirements_command,
    install_torch_command,
    run_transcribe,
    transcribe_command,
)


def test_transcribe_command_offline_for_local_model(tmp_path: Path):
    python = tmp_path / "python.exe"
    script = tmp_path / "transcribe.py"
    audio = tmp_path / "song.wav"
    output = tmp_path / "out"
    model = tmp_path / "SheetSage2"
    base = tmp_path / "MERT-v2-FullSong"
    command = transcribe_command(python, script, audio, output, task="melody-full",
                                 model=model, device="cuda", dtype="bf16", offline=True,
                                 base_model=base)
    assert command[:5] == [str(python), str(script), str(audio), "--output", str(output)]
    assert "--task" in command and "melody-full" in command
    assert "--offline" in command
    assert str(model) in command
    assert command[command.index("--base-model") + 1] == str(base)


def test_missing_sheetsage_python(tmp_path: Path):
    script = tmp_path / "transcribe.py"
    script.write_text("", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="SheetSage2"):
        ensure_transcribe_ready(python=tmp_path / "python.exe", script=script)


def test_install_torch_uses_cuda_or_cpu_index(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.sheetsage.uv_bin", lambda: "uv")
    python = tmp_path / "python.exe"
    cuda = install_torch_command(python, cuda=True)
    cpu = install_torch_command(python, cuda=False)
    assert TORCH_CUDA_INDEX in cuda
    assert TORCH_CPU_INDEX in cpu
    assert "torch==2.8.0" in cuda and "torchaudio==2.8.0" in cuda


def test_ensure_env_creates_venv_and_installs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.sheetsage.uv_bin", lambda: "uv")
    monkeypatch.setattr("yue_studio.sheetsage.sheetsage_python", lambda: None)
    monkeypatch.delenv("YUE_STUDIO_SHEETSAGE_PYTHON", raising=False)
    from yue_studio.paths import venv_python
    venv = tmp_path / ".venv-sheetsage2"
    python = venv_python(venv)
    model = tmp_path / "SheetSage2"
    model.mkdir()
    requirements = model / "requirements.txt"
    requirements.write_text("transformers\n", encoding="utf-8")
    commands: list[list[str]] = []
    installed = {"hub": False, "torch": False, "req": False}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, *, cwd=None):
        commands.append(list(command))
        joined = " ".join(command)
        if command[:2] == ["uv", "venv"]:
            python.parent.mkdir(parents=True)
            python.write_bytes(b"")
            return Result()
        if len(command) >= 3 and command[1] == "-c":
            if installed["hub"] and installed["torch"] and installed["req"]:
                return Result()
            raise RuntimeError("not ready")
        if "huggingface-hub==" in joined:
            installed["hub"] = True
            return Result()
        if "torch==" in joined:
            installed["torch"] = True
            return Result()
        if "-r" in command:
            installed["req"] = True
            return Result()
        raise AssertionError(command)

    result = ensure_sheetsage_env(
        venv_dir=venv, model_dir=model, cuda=True, run=fake_run,
    )
    assert result == python
    assert create_venv_command(venv) in commands
    assert install_hub_command(python) in commands
    assert install_torch_command(python, cuda=True) in commands
    assert install_requirements_command(python, requirements) in commands


def test_ensure_env_skips_install_when_ready(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.sheetsage.uv_bin", lambda: "uv")
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    commands: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, *, cwd=None):
        commands.append(list(command))
        if len(command) >= 3 and command[1] == "-c":
            return Result()
        raise AssertionError("should not install")

    assert ensure_sheetsage_env(python=python, run=fake_run) == python
    assert commands == [[str(python), "-c", "import torch, transformers, huggingface_hub"]]


def test_song_id_sanitizes():
    assert song_id("city_lights") == "city_lights"
    assert song_id("你好!") == "song" or song_id("cover-1") == "cover-1"
    assert song_id("cover-1") == "cover-1"


def test_run_transcribe_requires_ffmpeg(tmp_path: Path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    script = tmp_path / "transcribe.py"
    script.write_text("", encoding="utf-8")
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    output = tmp_path / "out"
    monkeypatch.setattr(
        "yue_studio.sheetsage.ensure_transcribe_ready", lambda **kwargs: (python, script),
    )
    monkeypatch.setattr("yue_studio.sheetsage.ffmpeg_bin", lambda: None)

    def fail_run(*args, **kwargs):
        raise AssertionError("should not invoke SheetSage2 without ffmpeg")

    monkeypatch.setattr("subprocess.run", fail_run)
    with pytest.raises(RuntimeError, match="FFmpeg"):
        run_transcribe(audio, output, python=python, script=script, model=tmp_path / "SheetSage2")


def test_run_transcribe_clears_studio_job_dir(tmp_path: Path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    script = tmp_path / "transcribe.py"
    script.write_text("", encoding="utf-8")
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    output = new_job_dir(tmp_path, "transcribe", "cover")
    assert output.is_dir()
    seen = {}

    def fake_ready(**kwargs):
        return python, script

    def fake_run(command, **kwargs):
        seen["command"] = list(command)
        dest = Path(command[command.index("--output") + 1])
        assert not dest.exists()
        dest.mkdir()
        (dest / "score.abc").write_text("X:1\nK:C\nC\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("yue_studio.sheetsage.ensure_transcribe_ready", fake_ready)
    monkeypatch.setattr("yue_studio.sheetsage.ffmpeg_bin", lambda: r"C:\bin\ffmpeg.exe")
    monkeypatch.setattr("subprocess.run", fake_run)
    mert = tmp_path / "MERT-v2-FullSong"
    score = run_transcribe(
        audio, output, python=python, script=script,
        model=tmp_path / "SheetSage2", base_model=mert,
    )
    assert score.is_file()
    assert str(output) in seen["command"]
    assert seen["command"][seen["command"].index("--base-model") + 1] == str(mert)


def test_run_transcribe_rejects_nonempty_output(tmp_path: Path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    script = tmp_path / "transcribe.py"
    script.write_text("", encoding="utf-8")
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    output = tmp_path / "occupied"
    output.mkdir()
    (output / "keep.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "yue_studio.sheetsage.ensure_transcribe_ready", lambda **kwargs: (python, script),
    )

    def fail_run(*args, **kwargs):
        raise AssertionError("should not invoke SheetSage2")

    monkeypatch.setattr("subprocess.run", fail_run)
    with pytest.raises(FileExistsError, match="Nonempty output"):
        run_transcribe(audio, output, python=python, script=script, model=tmp_path / "SheetSage2")
    assert (output / "keep.txt").is_file()

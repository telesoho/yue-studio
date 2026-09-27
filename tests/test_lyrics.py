import os
import sys
from pathlib import Path

import pytest

from yue_studio.lyrics import (
    TORCH_CPU_INDEX,
    TORCH_CUDA_INDEX,
    create_venv_command,
    ensure_lyrics_env,
    install_lyrics_packages_command,
    install_torch_command,
    recognize_command,
    separate_command,
)
from yue_studio.paths import venv_python


def test_register_cuda_dlls_prepends_torch_lib_on_windows(tmp_path: Path, monkeypatch):
    from yue_studio import lyrics_worker

    lib = tmp_path / "Lib" / "site-packages" / "torch" / "lib"
    lib.mkdir(parents=True)
    monkeypatch.setattr(lyrics_worker.sys, "prefix", str(tmp_path))
    monkeypatch.setenv("PATH", r"C:\Windows")
    added = lyrics_worker.register_cuda_dlls()
    if sys.platform != "win32":
        assert added == []
        assert os.environ["PATH"] == r"C:\Windows"
        return
    assert added == [str(lib)]
    assert os.environ["PATH"].startswith(str(lib) + os.pathsep)


def test_separate_and_recognize_commands(tmp_path: Path):
    python = tmp_path / "python.exe"
    script = tmp_path / "lyrics_worker.py"
    audio = tmp_path / "song.wav"
    output = tmp_path / "out"
    separate = separate_command(python, audio, output, device="cpu")
    assert separate[:3] == [str(python), "-m", "demucs"]
    assert "--two-stems" in separate and "vocals" in separate
    assert separate[separate.index("-d") + 1] == "cpu"
    recognize = recognize_command(
        python, script, audio, output / "words.json", model="large-v3",
        download_root=tmp_path / "faster-whisper", language="zh", device="cuda",
    )
    assert recognize[:2] == [str(python), str(script)]
    assert recognize[recognize.index("--language") + 1] == "zh"
    assert "--compute-type" in recognize and "int8" in recognize
    assert recognize[recognize.index("--model") + 1] == "large-v3"


def test_install_torch_uses_cuda_or_cpu_index(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.lyrics.uv_bin", lambda: "uv")
    python = tmp_path / "python.exe"
    cuda = install_torch_command(python, cuda=True)
    cpu = install_torch_command(python, cuda=False)
    assert TORCH_CUDA_INDEX in cuda
    assert TORCH_CPU_INDEX in cpu
    assert "torch==2.8.0" in cuda and "torchaudio==2.8.0" in cuda
    assert "demucs" in install_lyrics_packages_command(python)
    assert "faster-whisper" in install_lyrics_packages_command(python)


def test_ensure_lyrics_env_creates_venv_and_installs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.lyrics.uv_bin", lambda: "uv")
    monkeypatch.setattr("yue_studio.lyrics.lyrics_python", lambda: None)
    monkeypatch.delenv("YUE_STUDIO_LYRICS_PYTHON", raising=False)
    venv = tmp_path / ".venv-lyrics"
    python = venv_python(venv)
    commands: list[list[str]] = []
    installed = {"torch": False, "packages": False}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, *, cwd=None, env=None):
        commands.append(list(command))
        joined = " ".join(command)
        if command[:2] == ["uv", "venv"]:
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_bytes(b"")
            return Result()
        if len(command) >= 3 and command[1] == "-c":
            if installed["torch"] and installed["packages"]:
                return Result()
            raise RuntimeError("not ready")
        if "torch==" in joined:
            installed["torch"] = True
            return Result()
        if "demucs" in joined and "faster-whisper" in joined:
            installed["packages"] = True
            return Result()
        raise AssertionError(command)

    result = ensure_lyrics_env(venv_dir=venv, cuda=False, run=fake_run)
    assert result == python
    assert create_venv_command(venv) in commands
    assert "3.12" in create_venv_command(venv)
    assert install_torch_command(python, cuda=False) in commands
    assert install_lyrics_packages_command(python) in commands


def test_ensure_lyrics_env_skips_install_when_ready(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("yue_studio.lyrics.uv_bin", lambda: "uv")
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    commands: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, *, cwd=None, env=None):
        commands.append(list(command))
        if len(command) >= 3 and command[1] == "-c":
            return Result()
        raise AssertionError("should not install")

    assert ensure_lyrics_env(python=python, run=fake_run) == python
    assert commands == [[str(python), "-c", "import demucs, faster_whisper"]]


def test_separate_vocals_reports_missing_stem(tmp_path: Path, monkeypatch):
    python = tmp_path / "python.exe"
    python.write_bytes(b"")
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"x")
    output = tmp_path / "separated"

    class Result:
        returncode = 1
        stdout = ""
        stderr = "demucs exploded"

    monkeypatch.setattr("yue_studio.lyrics.ensure_lyrics_env", lambda **kwargs: python)
    monkeypatch.setattr("yue_studio.lyrics._invoke", lambda command, **kwargs: Result())
    from yue_studio.lyrics import separate_vocals
    with pytest.raises(RuntimeError, match="人声分离失败"):
        separate_vocals(audio, output, python=python, device="cpu")
    assert not any(output.rglob("vocals.wav"))

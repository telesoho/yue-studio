"""Vocal separation and lyric recognition via a separate Python 3.12 environment."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from pathlib import Path

from .paths import (
    lyrics_python,
    lyrics_venv_dir,
    lyrics_worker_script,
    models_dir,
    studio_root,
    venv_python,
)

TORCH_PACKAGES = ("torch==2.8.0", "torchaudio==2.8.0")
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
LYRICS_PACKAGES = ("demucs", "faster-whisper")
WHISPER_MODEL = "large-v3"
READY_IMPORT = "import demucs, faster_whisper"

_PROVISION_LOCK = threading.Lock()


def uv_bin() -> str:
    path = shutil.which("uv")
    if not path:
        raise RuntimeError("未找到 uv，无法自动配置歌词识别环境。")
    return path


def create_venv_command(venv: Path) -> list[str]:
    return [uv_bin(), "venv", str(venv), "--python", "3.12"]


def install_torch_command(python: Path, *, cuda: bool) -> list[str]:
    index = TORCH_CUDA_INDEX if cuda else TORCH_CPU_INDEX
    return [uv_bin(), "pip", "install", "--python", str(python),
            *TORCH_PACKAGES, "--index-url", index]


def install_lyrics_packages_command(python: Path) -> list[str]:
    return [uv_bin(), "pip", "install", "--python", str(python), *LYRICS_PACKAGES]


def packages_ready(python: Path, *, run=None) -> bool:
    if python is None or not Path(python).is_file():
        return False
    command = [str(python), "-c", READY_IMPORT]
    if run is not None:
        try:
            run(command)
        except RuntimeError:
            return False
        return True
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return completed.returncode == 0


def ensure_lyrics_env(*, python: Path | None = None, venv_dir: Path | None = None,
                      cuda: bool | None = None, on_status=None, run=None) -> Path:
    """Create the isolated 3.12 env and install Demucs / faster-whisper if needed."""
    with _PROVISION_LOCK:
        return _ensure_lyrics_env(
            python=python, venv_dir=venv_dir, cuda=cuda, on_status=on_status, run=run,
        )


def _ensure_lyrics_env(*, python, venv_dir, cuda, on_status, run) -> Path:
    runner = run or _run
    python = Path(python) if python is not None else lyrics_python()
    if python is not None and packages_ready(python, run=runner):
        return python

    if python is None:
        env_python = os.environ.get("YUE_STUDIO_LYRICS_PYTHON")
        if env_python:
            raise FileNotFoundError(
                "YUE_STUDIO_LYRICS_PYTHON 指向的解释器不存在: " + env_python
            )
        venv_dir = Path(venv_dir) if venv_dir is not None else lyrics_venv_dir()
        python = venv_python(venv_dir)
        if not python.is_file():
            if on_status:
                on_status("正在创建歌词识别 Python 3.12 环境…")
            runner(create_venv_command(venv_dir), cwd=str(studio_root()))
        if not python.is_file():
            raise RuntimeError(f"已创建虚拟环境但未找到解释器: {python}")

    if packages_ready(python, run=runner):
        return python

    if cuda is None:
        cuda = True
    if on_status:
        on_status("正在安装歌词识别所用 PyTorch…")
    runner(install_torch_command(python, cuda=cuda), cwd=str(studio_root()))
    if on_status:
        on_status("正在安装 Demucs 与 faster-whisper…")
    runner(install_lyrics_packages_command(python), cwd=str(studio_root()))
    if not packages_ready(python, run=runner):
        raise RuntimeError("歌词识别环境已安装依赖，但无法 import demucs / faster_whisper。")
    return python


def separate_command(python: Path, audio: Path, output: Path, *, device: str) -> list[str]:
    return [
        str(python), "-m", "demucs", "-n", "htdemucs", "--two-stems", "vocals",
        "-d", device, "-o", str(output), str(audio),
    ]


def recognize_command(python: Path, script: Path, audio: Path, output: Path, *,
                      model: str, download_root: Path, language: str,
                      device: str) -> list[str]:
    return [
        str(python), str(script),
        "--audio", str(audio),
        "--output", str(output),
        "--model", model,
        "--download-root", str(download_root),
        "--language", language,
        "--device", device,
        "--compute-type", "int8",
    ]


def whisper_download_root() -> Path:
    return models_dir() / "faster-whisper"


def demucs_home() -> Path:
    return models_dir() / "demucs"


def separate_vocals(audio: Path, output: Path, *, device="cuda",
                    python: Path | None = None, on_status=None, run=None) -> Path:
    """Return the separated vocals wav. Raises when Demucs does not produce one."""
    audio = Path(audio)
    output = Path(output)
    if not audio.is_file():
        raise FileNotFoundError(audio)
    output.mkdir(parents=True, exist_ok=True)
    python = ensure_lyrics_env(python=python, cuda=(device == "cuda"), on_status=on_status, run=run)
    command = separate_command(python, audio, output, device=device)
    if on_status:
        on_status("正在分离人声（首次会下载 Demucs）…")
    env = _lyrics_env()
    completed = _invoke(command, env=env, run=run)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"人声分离失败：{detail}")
    vocals = _find_vocals(output)
    if vocals is None:
        raise RuntimeError("人声分离完成但没有 vocals.wav")
    return vocals


def recognize_lyrics(audio: Path, output: Path, *, language="zh", device="cuda",
                     python: Path | None = None, script: Path | None = None,
                     on_status=None, run=None) -> list[dict]:
    """Write word timestamps and return ``[{text, start, end}, ...]``."""
    audio = Path(audio)
    output = Path(output)
    if not audio.is_file():
        raise FileNotFoundError(audio)
    script = Path(script or lyrics_worker_script())
    if not script.is_file():
        raise FileNotFoundError(f"未找到歌词识别脚本: {script}")
    python = ensure_lyrics_env(python=python, cuda=(device == "cuda"), on_status=on_status, run=run)
    lang = "" if language in (None, "", "auto") else str(language)
    command = recognize_command(
        python, script, audio, output, model=WHISPER_MODEL,
        download_root=whisper_download_root(), language=lang, device=device,
    )
    if on_status:
        on_status("正在识别歌词（首次会下载 Whisper large-v3）…")
    completed = _invoke(command, env=_lyrics_env(), run=run)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        raise RuntimeError(detail)
    if not output.is_file():
        raise FileNotFoundError("歌词识别完成但没有词时间戳")
    data = json.loads(output.read_text(encoding="utf-8"))
    words = data.get("words") if isinstance(data, dict) else None
    if not isinstance(words, list):
        raise ValueError("歌词识别结果缺少 words")
    cleaned = []
    for word in words:
        if not isinstance(word, dict):
            continue
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        cleaned.append({
            "text": text,
            "start": float(word["start"]),
            "end": float(word["end"]),
        })
    return cleaned


def _lyrics_env() -> dict:
    env = os.environ.copy()
    env["TORCH_HOME"] = str(demucs_home())
    env["HF_HOME"] = str(models_dir() / "hf-lyrics")
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    return env


def _find_vocals(output: Path) -> Path | None:
    matches = sorted(path for path in output.rglob("vocals.wav") if path.is_file())
    if len(matches) == 1:
        return matches[0]
    if not matches:
        return None
    preferred = [path for path in matches if path.parent.name != "no_vocals"]
    return preferred[-1] if preferred else matches[-1]


def _invoke(command, *, env, run=None):
    if run is not None:
        return run(command, env=env)
    return subprocess.run(
        command, env=env, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def _run(command: list[str], *, cwd: str | None = None, env=None) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command, cwd=cwd, env=env, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0 and len(command) >= 3 and command[1] == "-c":
        raise RuntimeError(completed.stderr or completed.stdout or "import failed")
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        label = " ".join(command[:3])
        raise RuntimeError(f"歌词识别环境配置失败（{label}）：{detail}")
    return completed

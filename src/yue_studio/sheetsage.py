"""SheetSage2 transcription via a separate Python 3.11 environment."""
from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

from .paths import (
    sheetsage_python,
    sheetsage_venv_dir,
    studio_root,
    transcribe_script,
    venv_python,
    yue_root,
)

HUB_PIN = "huggingface-hub==0.36.0"
TORCH_PACKAGES = ("torch==2.8.0", "torchaudio==2.8.0")
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
READY_IMPORT = "import torch, transformers, huggingface_hub"

_PROVISION_LOCK = threading.Lock()


def ffmpeg_bin() -> str | None:
    return shutil.which("ffmpeg")


def require_ffmpeg() -> str:
    path = ffmpeg_bin()
    if not path:
        raise RuntimeError("转谱需要本机 FFmpeg。请安装 FFmpeg 并把它加入 PATH 后重试。")
    return path


def transcribe_command(python: Path, script: Path, audio: Path, output: Path, *,
                       task="melody-full", model="m-a-p/SheetSage2",
                       device="cuda", dtype="bf16", offline=False,
                       base_model: str | Path | None = None) -> list[str]:
    command = [str(python), str(script), str(audio), "--output", str(output),
               "--task", task, "--model", str(model), "--device", device, "--dtype", dtype]
    if base_model:
        command.extend(["--base-model", str(base_model)])
    if offline:
        command.append("--offline")
    return command


def uv_bin() -> str:
    path = shutil.which("uv")
    if not path:
        raise RuntimeError("未找到 uv，无法自动配置 SheetSage2 环境。")
    return path


def create_venv_command(venv: Path) -> list[str]:
    return [uv_bin(), "venv", str(venv), "--python", "3.11"]


def install_hub_command(python: Path) -> list[str]:
    return [uv_bin(), "pip", "install", "--python", str(python), HUB_PIN]


def install_torch_command(python: Path, *, cuda: bool) -> list[str]:
    index = TORCH_CUDA_INDEX if cuda else TORCH_CPU_INDEX
    return [uv_bin(), "pip", "install", "--python", str(python),
            *TORCH_PACKAGES, "--index-url", index]


def install_requirements_command(python: Path, requirements: Path) -> list[str]:
    return [uv_bin(), "pip", "install", "--python", str(python), "-r", str(requirements)]


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


def ensure_sheetsage_env(*, python: Path | None = None, venv_dir: Path | None = None,
                         model_dir: Path | None = None, cuda: bool | None = None,
                         on_status=None, run=None) -> Path:
    """Create the isolated 3.11 env and install SheetSage2 deps if needed."""
    with _PROVISION_LOCK:
        return _ensure_sheetsage_env(
            python=python, venv_dir=venv_dir, model_dir=model_dir,
            cuda=cuda, on_status=on_status, run=run,
        )


def _ensure_sheetsage_env(*, python, venv_dir, model_dir, cuda, on_status, run) -> Path:
    runner = run or _run
    python = Path(python) if python is not None else sheetsage_python()
    if python is not None and packages_ready(python, run=runner):
        return python

    if python is None:
        env_python = os.environ.get("YUE_STUDIO_SHEETSAGE_PYTHON")
        if env_python:
            raise FileNotFoundError(
                "YUE_STUDIO_SHEETSAGE_PYTHON 指向的解释器不存在: " + env_python
            )
        venv_dir = Path(venv_dir) if venv_dir is not None else sheetsage_venv_dir()
        python = venv_python(venv_dir)
        if not python.is_file():
            if on_status:
                on_status("正在创建 SheetSage2 Python 3.11 环境…")
            runner(create_venv_command(venv_dir), cwd=str(studio_root()))
        if not python.is_file():
            raise RuntimeError(f"已创建虚拟环境但未找到解释器: {python}")

    if packages_ready(python, run=runner):
        return python

    requirements = _requirements_path(model_dir)
    if cuda is None:
        cuda = True
    if on_status:
        on_status("正在安装 SheetSage2 依赖（huggingface-hub / PyTorch / requirements）…")
    runner(install_hub_command(python), cwd=str(studio_root()))
    if on_status:
        on_status("正在安装 SheetSage2 所用 PyTorch…")
    runner(install_torch_command(python, cuda=cuda), cwd=str(studio_root()))
    if on_status:
        on_status("正在安装 SheetSage2 requirements.txt…")
    runner(install_requirements_command(python, requirements), cwd=str(studio_root()))
    if not packages_ready(python, run=runner):
        raise RuntimeError("SheetSage2 环境已安装依赖，但无法 import torch / transformers。")
    return python


def ensure_transcribe_ready(*, python: Path | None = None, script: Path | None = None,
                            model_dir: Path | None = None, cuda: bool | None = None,
                            on_status=None, run=None) -> tuple[Path, Path]:
    script = script or transcribe_script()
    if not Path(script).is_file():
        raise FileNotFoundError(f"未找到转谱脚本: {script}。请设置 YUE2_ROOT 指向 YuE 仓库。")
    if python is not None:
        python = Path(python)
        if not python.is_file():
            raise FileNotFoundError(f"未找到 SheetSage2 解释器: {python}")
        if not packages_ready(python, run=run):
            python = ensure_sheetsage_env(
                python=python, model_dir=model_dir, cuda=cuda,
                on_status=on_status, run=run,
            )
        return python, Path(script)
    python = ensure_sheetsage_env(
        model_dir=model_dir, cuda=cuda, on_status=on_status, run=run,
    )
    return python, Path(script)


def run_transcribe(audio: Path, output: Path, *, task="melody-full",
                   model: str | Path = "m-a-p/SheetSage2", device="cuda",
                   dtype="bf16", python: Path | None = None, script: Path | None = None,
                   base_model: str | Path | None = None,
                   timeout: int | None = None, on_status=None, run=None) -> Path:
    audio, output = Path(audio), _clear_empty_output(output)
    if not audio.is_file():
        raise FileNotFoundError(audio)
    ffmpeg = require_ffmpeg()
    python, script = ensure_transcribe_ready(
        python=python, script=script, model_dir=Path(model) if Path(model).is_dir() else None,
        cuda=(device == "cuda"), on_status=on_status, run=run,
    )
    command = transcribe_command(
        python, script, audio, output, task=task, model=model,
        device=device, dtype=dtype, offline=Path(model).is_dir(),
        base_model=base_model,
    )
    from .invoke import format_command
    if on_status:
        on_status("命令: " + format_command(command))
        on_status("SheetSage2 转谱中…")
    env = os.environ.copy()
    env["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = str(script.parent) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(command, cwd=str(yue_root()), env=env, check=False,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
    if on_status:
        for stream in (completed.stdout, completed.stderr):
            for line in (stream or "").splitlines():
                if line.strip():
                    on_status(line)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"SheetSage2 转谱失败：{detail}")
    score = output / "score.abc"
    if not score.is_file():
        raise FileNotFoundError("转谱完成但没有 score.abc")
    return score


def _clear_empty_output(output: Path) -> Path:
    """Leave a non-existent path for transcribe.py's exclusive mkdir."""
    output = Path(output)
    if not output.exists():
        return output
    if not output.is_dir() or any(output.iterdir()):
        raise FileExistsError(f"Nonempty output {output}")
    output.rmdir()
    return output


def _requirements_path(model_dir: Path | None) -> Path:
    if model_dir is not None:
        path = Path(model_dir) / "requirements.txt"
        if path.is_file():
            return path
    from .models import locate, RESOURCES
    spec = next(item for item in RESOURCES if item.name == "SheetSage2")
    status = locate(spec)
    if status.present and status.path is not None:
        path = status.path / "requirements.txt"
        if path.is_file():
            return path
    raise FileNotFoundError("未找到 SheetSage2 的 requirements.txt，请先下载 SheetSage2。")


def _run(command: list[str], *, cwd: str | None = None) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        command, cwd=cwd, check=False, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip() or f"exit {completed.returncode}"
        label = " ".join(command[:3])
        raise RuntimeError(f"SheetSage2 环境配置失败（{label}）：{detail}")
    return completed

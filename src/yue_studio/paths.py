"""Studio and sibling YuE2 locations."""
from __future__ import annotations

import os
from pathlib import Path


def studio_root() -> Path:
    return Path(__file__).resolve().parents[2]


def yue_root() -> Path:
    env = os.environ.get("YUE2_ROOT") or os.environ.get("YUE2_KIT")
    if env:
        return Path(env).expanduser().resolve()
    return (studio_root().parent / "YuE").resolve()


def models_dir() -> Path:
    env = os.environ.get("YUE_STUDIO_MODELS")
    if env:
        return Path(env).expanduser().resolve()
    return studio_root() / "models"


def outputs_dir() -> Path:
    env = os.environ.get("YUE_STUDIO_OUTPUTS")
    if env:
        return Path(env).expanduser().resolve()
    return studio_root() / "outputs"


def static_dir() -> Path:
    return studio_root() / "static"


def abcjs_path() -> Path:
    return static_dir() / "abcjs" / "abcjs-basic-min.js"


def transcribe_script() -> Path:
    return yue_root() / "skills" / "yue2-music" / "scripts" / "transcribe.py"


def abc_tools_path() -> Path:
    return yue_root() / "skills" / "yue2-music" / "scripts" / "abc_tools.py"


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return Path(venv) / "Scripts" / "python.exe"
    return Path(venv) / "bin" / "python"


def sheetsage_venv_dir() -> Path:
    for root in (studio_root(), yue_root()):
        candidate = root / ".venv-sheetsage2"
        if venv_python(candidate).is_file():
            return candidate
    return studio_root() / ".venv-sheetsage2"


def sheetsage_python() -> Path | None:
    env = os.environ.get("YUE_STUDIO_SHEETSAGE_PYTHON")
    if env:
        path = Path(env).expanduser()
        return path if path.is_file() else None
    candidate = venv_python(sheetsage_venv_dir())
    return candidate if candidate.is_file() else None

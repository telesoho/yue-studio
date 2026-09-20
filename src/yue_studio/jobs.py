"""Fresh output directories for each plan or render."""
from __future__ import annotations

import re
import time
from pathlib import Path

SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,179}")


def song_id(value: str | None, fallback="song") -> str:
    text = (value or fallback).strip() or fallback
    if SAFE_ID.fullmatch(text) and text not in {".", ".."}:
        return text
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("._-") or fallback
    if not SAFE_ID.fullmatch(cleaned):
        cleaned = fallback
    return cleaned[:180]


def new_job_dir(root: Path, kind: str, identifier: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    directory = Path(root) / f"{kind}-{stamp}-{song_id(identifier)}"
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Nonempty output {directory}")
    directory.mkdir(parents=True, exist_ok=False)
    return directory

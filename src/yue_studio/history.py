"""Scan studio outputs for previous plans, songs, and transcriptions."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .paths import outputs_dir

JOB_DIR = re.compile(r"^(song|plan|transcribe)-(\d{8}-\d{6})-(.+)$")
KIND_LABELS = {"song": "生成", "plan": "规划", "transcribe": "转谱"}
TABLE_HEADERS = ["时间", "类型", "id", "时长", "风格"]
EMPTY_NOTE = "还没有可播放或可查看的记录。在「生成」或「翻唱」页完成后会出现在这里。"
STYLE_LIMIT = 40


@dataclass(frozen=True)
class HistoryEntry:
    directory: Path
    kind: str
    stamp: str
    identifier: str
    audio: Path | None = None
    abc: str = ""
    request: dict = field(default_factory=dict)
    audio_seconds: float | None = None
    has_plan: bool = False

    def row(self) -> list[str]:
        return [
            format_stamp(self.stamp),
            KIND_LABELS.get(self.kind, self.kind),
            self.identifier,
            format_duration(self.audio_seconds),
            style_snippet(self.request.get("style") or ""),
        ]


def format_stamp(stamp: str) -> str:
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def style_snippet(style: str, limit: int = STYLE_LIMIT) -> str:
    text = " ".join((style or "").split())
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def parse_job_name(name: str) -> tuple[str, str, str] | None:
    match = JOB_DIR.fullmatch(name)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def job_dir_under(root: Path, directory: Path) -> Path:
    root = Path(root).resolve()
    path = Path(directory).resolve()
    if not path.is_dir():
        raise ValueError(f"不是输出目录: {directory}")
    if not path.is_relative_to(root) or path.parent != root:
        raise ValueError(f"不在输出根目录下: {directory}")
    if parse_job_name(path.name) is None:
        raise ValueError(f"不是工作室任务目录: {directory}")
    return path


def _list_entry(directory: Path) -> HistoryEntry | None:
    parsed = parse_job_name(directory.name)
    if parsed is None or not directory.is_dir():
        return None
    kind, stamp, identifier = parsed
    audio = directory / "audio.flac"
    score = directory / "score.abc"
    manifest = directory / "plan_manifest.json"
    if kind == "song":
        if not audio.is_file():
            return None
    elif not score.is_file() and not manifest.is_file():
        return None
    request = _read_json(directory / "request.json") or {}
    result = _read_json(directory / "result.json") or {}
    seconds = result.get("audio_seconds")
    try:
        audio_seconds = float(seconds) if seconds is not None else None
    except (TypeError, ValueError):
        audio_seconds = None
    return HistoryEntry(
        directory=directory.resolve(),
        kind=kind,
        stamp=stamp,
        identifier=identifier,
        audio=audio.resolve() if audio.is_file() else None,
        request=request,
        audio_seconds=audio_seconds,
        has_plan=manifest.is_file(),
    )


def list_history(root: Path | None = None) -> list[HistoryEntry]:
    root = Path(root) if root is not None else outputs_dir()
    if not root.is_dir():
        return []
    entries = []
    for child in root.iterdir():
        entry = _list_entry(child)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda item: item.stamp, reverse=True)
    return entries


def load_entry(directory: Path, *, root: Path | None = None) -> HistoryEntry:
    root = Path(root) if root is not None else outputs_dir()
    path = job_dir_under(root, directory)
    entry = _list_entry(path)
    if entry is None:
        raise ValueError(f"无法载入记录: {directory}")
    request = dict(entry.request)
    if not request:
        plan = _read_json(path / "plan.json") or {}
        nested = plan.get("request")
        if isinstance(nested, dict):
            request = nested
    abc = _read_text(path / "score.abc")
    return HistoryEntry(
        directory=entry.directory,
        kind=entry.kind,
        stamp=entry.stamp,
        identifier=entry.identifier,
        audio=entry.audio,
        abc=abc,
        request=request,
        audio_seconds=entry.audio_seconds,
        has_plan=entry.has_plan,
    )


def delete_entry(directory: Path, *, root: Path | None = None) -> Path:
    root = Path(root) if root is not None else outputs_dir()
    path = job_dir_under(root, directory)
    shutil.rmtree(path)
    return path


def history_table(root: Path | None = None) -> tuple[list[list[str]], list[str], str]:
    entries = list_history(root)
    rows = [item.row() for item in entries]
    paths = [str(item.directory) for item in entries]
    note = "" if entries else EMPTY_NOTE
    return rows, paths, note

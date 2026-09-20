"""Show the YuE2 command, parameters, and captured stderr for a studio job."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .runner import PipelineSettings
from .paths import outputs_dir


def format_command(argv: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(argv))
    import shlex
    return shlex.join(argv)


def yue2_generate_argv(*, model, vae, preset: PipelineSettings, request: dict,
                       stage="audio") -> list[str]:
    argv = [
        "yue2", "generate",
        "--model", str(model),
        "--vae", str(vae),
        "--device", str(preset.device),
        "--budget", f"{preset.memory_budget_gib:g}",
        "--quantization", str(preset.quantization),
    ]
    if preset.offload_ar:
        argv.append("--offload-ar")
    argv.extend([
        "--offline",
        "--stage", stage,
        "--id", str(request.get("id", "song")),
        "--cot", str(request.get("cot", "full")),
        "--seed", str(int(request.get("seed", 0))),
        "--output", str(outputs_dir()),
    ])
    if request.get("cfg_scale") is not None:
        argv.extend(["--cfg-scale", str(request["cfg_scale"])])
    if request.get("abc"):
        argv.extend(["--abc-file", "<request.abc>"])
    return argv


def format_python_call(stage: str, model, vae, preset: PipelineSettings) -> str:
    lines = [
        "YuE2Pipeline.from_pretrained(",
        f"  {str(model)!r},",
        f"  vae={str(vae)!r},",
        "  local_files_only=True,",
        "  progress=True,",
    ]
    for key, value in preset.pipeline_kwargs().items():
        lines.append(f"  {key}={value!r},")
    lines.append(")")
    if stage == "plan":
        lines.append("pipe.plan(**request)")
    else:
        lines.extend([
            "pipe.plan(**request)",
            "pipe.generate_semantic(plan)",
            "pipe.synthesize(semantic)",
            "pipe.decode(latents)",
        ])
    return "\n".join(lines)


def format_params(request: dict, preset: PipelineSettings, *, model, vae) -> str:
    payload = {
        "pipeline": {
            "model": str(model),
            "vae": str(vae),
            "local_files_only": True,
            "progress": True,
            **preset.pipeline_kwargs(),
        },
        "request": _jsonable(request),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def format_invocation(*, stage: str, request: dict, preset: PipelineSettings,
                      model, vae) -> str:
    argv = yue2_generate_argv(model=model, vae=vae, preset=preset, request=request,
                              stage=stage)
    return "\n".join((
        "=== 命令 ===",
        format_command(argv),
        "",
        format_python_call(stage, model, vae, preset),
        "",
        "=== 参数 ===",
        format_params(request, preset, model=model, vae=vae),
    ))


def status_line(message, completed=None, total=None) -> str:
    if completed is None or not total:
        return str(message)
    return f"{message} {int(completed)}/{int(total)}"


class InvocationLog:
    def __init__(self, header: str):
        self.header = header.rstrip()
        self.lines: list[str] = []
        self.live = ""

    def add(self, line: str, *, live=False):
        text = str(line).rstrip()
        if not text:
            return
        stamped = f"{_stamp()}  {text}"
        if live:
            self.live = stamped
            return
        self.live = ""
        self.lines.append(stamped)

    def text(self) -> str:
        parts = [self.header, "", "=== 日志 ==="]
        parts.extend(self.lines)
        if self.live:
            parts.append(self.live)
        return "\n".join(parts)


class StreamTee:
    """Copy writes to the original stream and emit complete/live lines."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, original, on_line):
        self._original = original
        self._on_line = on_line
        self._buf = ""
        self._lock = threading.Lock()

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("not a real file")

    def write(self, data):
        if not data:
            return 0
        if not isinstance(data, str):
            data = data.decode(self.encoding, self.errors)
        try:
            self._original.write(data)
        except Exception:
            pass
        with self._lock:
            self._buf += data.replace("\r\n", "\n")
            self._drain(commit_partial=False)
        return len(data)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass

    def close(self):
        with self._lock:
            self._drain(commit_partial=True)

    def _drain(self, commit_partial):
        while True:
            newline = self._buf.find("\n")
            ret = self._buf.find("\r")
            if ret != -1 and (newline == -1 or ret < newline):
                live, self._buf = self._buf[:ret], self._buf[ret + 1:]
                live = live.strip()
                if live:
                    self._on_line(live, True)
                continue
            if newline != -1:
                line, self._buf = self._buf[:newline], self._buf[newline + 1:]
                line = line.strip()
                if line:
                    self._on_line(line, False)
                continue
            break
        if commit_partial:
            leftover = self._buf.strip()
            self._buf = ""
            if leftover:
                self._on_line(leftover, False)


@contextmanager
def capture_stderr(on_line):
    original = sys.stderr
    tee = StreamTee(original, on_line)
    sys.stderr = tee
    try:
        yield tee
    finally:
        sys.stderr = original
        tee.close()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _stamp() -> str:
    return time.strftime("%H:%M:%S")

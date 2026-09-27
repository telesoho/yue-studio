#!/usr/bin/env python3
"""Recognize lyric words in the isolated lyrics environment.

This file is executed by ``.venv-lyrics`` and must not import ``yue_studio``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_DLL_HANDLES = []


def register_cuda_dlls() -> list[str]:
    """Put PyTorch's CUDA DLLs on PATH so CTranslate2's LoadLibrary can find them.

    ``os.add_dll_directory`` alone does not affect that ``LoadLibraryA`` call.
    """
    if sys.platform != "win32":
        return []
    site = Path(sys.prefix) / "Lib" / "site-packages"
    candidates = [site / "torch" / "lib"]
    nvidia = site / "nvidia"
    if nvidia.is_dir():
        candidates.extend(path / "bin" for path in nvidia.iterdir() if path.is_dir())
    added = []
    for path in candidates:
        if not path.is_dir():
            continue
        added.append(str(path))
        if hasattr(os, "add_dll_directory"):
            try:
                _DLL_HANDLES.append(os.add_dll_directory(str(path)))
            except OSError:
                pass
    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + os.environ.get("PATH", "")
    return added


def recognize(args) -> int:
    register_cuda_dlls()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from faster_whisper import WhisperModel

    language = args.language or None
    if language == "auto":
        language = None
    model_name = args.model

    def load(device: str):
        kwargs = dict(
            device=device,
            compute_type="int8" if device == "cpu" else args.compute_type,
            download_root=str(args.download_root),
        )
        if Path(model_name).is_dir():
            kwargs["local_files_only"] = True
        return WhisperModel(model_name, **kwargs)

    devices = [args.device] if args.device == "cpu" else [args.device, "cpu"]
    words = []
    info = None
    for device in devices:
        try:
            model = load(device)
            segments, info = model.transcribe(
                str(args.audio),
                language=language,
                word_timestamps=True,
                vad_filter=True,
            )
            words = []
            for segment in segments:
                for word in segment.words or []:
                    text = (word.word or "").strip()
                    if not text:
                        continue
                    words.append({
                        "text": text,
                        "start": float(word.start),
                        "end": float(word.end),
                    })
            break
        except Exception as exc:
            if device == "cpu":
                raise
            print(f"CUDA 歌词识别失败，改用 CPU：{exc}", file=sys.stderr)
    payload = {
        "language": getattr(info, "language", None) or language,
        "words": words,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"words={len(words)}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--download-root", type=Path, required=True)
    parser.add_argument("--language", default="")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args(argv)
    try:
        return recognize(args)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

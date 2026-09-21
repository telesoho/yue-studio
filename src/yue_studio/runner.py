"""One GPU job at a time. YuE2 pipeline is not shared across threads."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .jobs import new_job_dir, song_id
from .models import download_by_name, required_ready, scan_catalog
from .paths import models_dir, outputs_dir, yue_root
from .sheetsage import run_transcribe


@dataclass(frozen=True)
class PipelineSettings:
    device: str
    memory_budget_gib: float
    quantization: str
    offload_ar: bool
    vae_core_frames: int

    def pipeline_kwargs(self) -> dict:
        return {
            "device": self.device,
            "memory_budget_gib": self.memory_budget_gib,
            "quantization": self.quantization,
            "offload_ar": self.offload_ar,
            "vae_core_frames": self.vae_core_frames,
        }

    def summary(self) -> str:
        return "\n".join((
            f"device={self.device}",
            f"memory_budget_gib={self.memory_budget_gib:g}",
            f"quantization={self.quantization}",
            f"offload_ar={self.offload_ar}",
            f"vae_core_frames={self.vae_core_frames}",
        ))


def settings_from_pipe(pipe) -> PipelineSettings:
    return PipelineSettings(
        device=str(pipe.device),
        memory_budget_gib=float(pipe.memory_budget_gib),
        quantization=str(pipe.quantization),
        offload_ar=bool(pipe.offload_ar),
        vae_core_frames=int(pipe.vae_core_frames),
    )


DEFAULT_SETTINGS = PipelineSettings(
    device="cuda",
    memory_budget_gib=24,
    quantization="none",
    offload_ar=False,
    vae_core_frames=1024,
)


class _StageProgress:
    """Throttle token/step callbacks into ``on_status(label, completed, total)``."""

    def __init__(self, on_status, label, total=None, interval=0.25):
        self.on_status = on_status
        self.label = label
        self.total = total
        self.interval = interval
        self.completed = 0
        self._last = 0.0
        self._emit(force=True)

    def on_token(self, phase, token):
        self._set(self.completed + 1)

    def on_progress(self, completed, total):
        self.total = total
        self._set(completed, force=total is not None and completed >= total)

    def finish(self):
        self._emit(force=True)

    def _set(self, completed, force=False):
        self.completed = completed
        self._emit(force=force)

    def _emit(self, force=False):
        if self.on_status is None:
            return
        now = time.monotonic()
        done = self.total is not None and self.completed >= self.total
        if not force and self.completed != 1 and not done and now - self._last < self.interval:
            return
        self._last = now
        self.on_status(self.label, self.completed, self.total)


def _token_callbacks(on_status, label, total):
    if on_status is None:
        return None, lambda: None
    tracker = _StageProgress(on_status, label, total)
    return tracker.on_token, tracker.finish


def _step_callbacks(on_status, label, total=None):
    if on_status is None:
        return None, lambda: None
    tracker = _StageProgress(on_status, label, total)
    return tracker.on_progress, tracker.finish


class StudioRunner:
    def __init__(self, pipeline_kwargs: dict | None = None):
        self._pipeline_kwargs = dict(pipeline_kwargs or {})
        self._pipeline_kwargs.setdefault("device", DEFAULT_SETTINGS.device)
        self.settings: PipelineSettings | None = None
        self.lock = threading.Lock()
        self._pipe = None
        self._key = None

    def set_use_gpu(self, use_gpu: bool):
        device = "cuda" if use_gpu else "cpu"
        if self._pipeline_kwargs.get("device") == device:
            return
        self._pipeline_kwargs["device"] = device
        self.unload()

    def apply_settings(self, settings: PipelineSettings):
        kwargs = settings.pipeline_kwargs()
        if all(key in self._pipeline_kwargs and self._pipeline_kwargs[key] == value
               for key, value in kwargs.items()):
            return
        self._pipeline_kwargs.update(kwargs)
        self.unload()

    @property
    def display_settings(self) -> PipelineSettings:
        if self.settings is not None:
            return self.settings
        return PipelineSettings(
            device=str(self._pipeline_kwargs.get("device", DEFAULT_SETTINGS.device)),
            memory_budget_gib=float(self._pipeline_kwargs.get(
                "memory_budget_gib", DEFAULT_SETTINGS.memory_budget_gib)),
            quantization=str(self._pipeline_kwargs.get(
                "quantization", DEFAULT_SETTINGS.quantization)),
            offload_ar=bool(self._pipeline_kwargs.get("offload_ar", DEFAULT_SETTINGS.offload_ar)),
            vae_core_frames=int(self._pipeline_kwargs.get(
                "vae_core_frames", DEFAULT_SETTINGS.vae_core_frames)),
        )

    def unload(self):
        pipe = self._pipe
        self._pipe = None
        self._key = None
        self.settings = None
        if pipe is not None:
            pipe.close()

    def _ensure_pipe(self, *, on_status=None):
        mot, vae = required_ready()
        key = (str(mot.path), str(vae.path), tuple(sorted(self._pipeline_kwargs.items())))
        if self._pipe is not None and self._key == key:
            return self._pipe
        self.unload()
        if on_status:
            on_status("正在加载 YuE2…")
        from yue2 import YuE2Pipeline
        self._pipe = YuE2Pipeline.from_pretrained(
            str(mot.path), vae=str(vae.path), local_files_only=True,
            progress=True, **self._pipeline_kwargs,
        )
        self.settings = settings_from_pipe(self._pipe)
        self._key = key
        return self._pipe

    def plan(self, request: dict, *, on_status=None) -> dict:
        with self.lock:
            pipe = self._ensure_pipe(on_status=on_status)
            kwargs = _request_kwargs(request)
            generating = kwargs.get("cot") != "off" and not kwargs.get("abc")
            on_token, done = (None, lambda: None)
            if generating:
                on_token, done = _token_callbacks(
                    on_status, "正在规划曲谱…", pipe.generation_config.abc.max_tokens)
            elif on_status:
                on_status("正在载入曲谱…")
            try:
                plan = pipe.plan(**kwargs, on_token=on_token)
            finally:
                done()
            directory = new_job_dir(outputs_dir(), "plan", kwargs.get("id", "song"))
            plan.save(directory)
            abc = plan.abc or ""
            return {
                "directory": str(directory),
                "abc": abc,
                "truncated": plan.truncated,
                "request": plan.request.to_dict(),
                "cot": plan.request.cot,
            }

    def render(self, request: dict, *, abc_text: str | None = None,
               plan_dir: str | Path | None = None, on_status=None) -> dict:
        from yue2.pipeline import SongResult
        from yue2.storage import identity

        with self.lock:
            pipe = self._ensure_pipe(on_status=on_status)
            kwargs = _request_kwargs(request)
            if abc_text is not None and abc_text.strip() and kwargs.get("cot") != "off":
                kwargs["abc"] = abc_text
            directory = new_job_dir(outputs_dir(), "song", kwargs.get("id", "song"))
            plan_path = Path(plan_dir) if plan_dir else None
            saved_abc = None
            if plan_path and (plan_path / "score.abc").is_file():
                saved_abc = (plan_path / "score.abc").read_text(encoding="utf-8")
            reuse_plan = False
            plan = None
            if (plan_path is not None and (plan_path / "plan_manifest.json").is_file()
                    and kwargs.get("cot") != "off" and abc_text is not None
                    and saved_abc is not None and abc_text == saved_abc):
                from yue2 import SymbolicPlan
                plan = SymbolicPlan.load(plan_path)
                reuse_plan = all(
                    kwargs.get(key, getattr(plan.request, key)) == getattr(plan.request, key)
                    for key in ("style", "lyrics", "cot", "seed", "id")
                )
            start = time.perf_counter()
            if reuse_plan:
                if plan is None:
                    raise RuntimeError("Saved plan was not loaded")
                if on_status:
                    on_status("沿用已保存的曲谱规划…")
            else:
                generating = kwargs.get("cot") != "off" and not kwargs.get("abc")
                on_token, done = (None, lambda: None)
                if generating:
                    on_token, done = _token_callbacks(
                        on_status, "正在规划曲谱…", pipe.generation_config.abc.max_tokens)
                elif on_status:
                    on_status("正在载入曲谱…")
                try:
                    plan = pipe.plan(**kwargs, on_token=on_token)
                finally:
                    done()
            on_token, done = _token_callbacks(
                on_status, "正在生成语义 token…", pipe.generation_config.semantic.max_tokens)
            try:
                semantic = pipe.generate_semantic(plan, on_token=on_token)
            finally:
                done()
            on_progress, done = _step_callbacks(on_status, "正在合成声学 latent…")
            try:
                nar_start = time.perf_counter()
                latents = pipe.synthesize(semantic, on_progress=on_progress)
                nar_seconds = time.perf_counter() - nar_start
            finally:
                done()
            frames = latents.shape[0]
            tiles = max(1, (frames + pipe.vae_core_frames - 1) // pipe.vae_core_frames)
            on_progress, done = _step_callbacks(on_status, "正在解码音频…", tiles)
            try:
                vae_start = time.perf_counter()
                audio = pipe.decode(latents, on_progress=on_progress)
                vae_seconds = time.perf_counter() - vae_start
            finally:
                done()
            config = pipe.effective_config(plan.request)
            timing = {"abc": plan.timing, "semantic": semantic.timing,
                      "nar_seconds": nar_seconds, "vae_seconds": vae_seconds}
            if not reuse_plan:
                timing["load"] = dict(getattr(pipe, "load_timing", {}) or {})
                timing["e2e_seconds"] = time.perf_counter() - start
            request_id = identity({"request": plan.request.to_dict(),
                                   "config": config, "weights": pipe.weights})
            song = SongResult(audio, 48000, semantic, latents, config,
                              pipe.weights, timing, request_id)
            result = song.save_artifacts(directory)
            audio_path = directory / "audio.flac"
            abc = song.abc or ""
            if abc:
                score_path = directory / "score.abc"
                if not score_path.is_file():
                    score_path.write_text(abc, encoding="utf-8")
            return {
                "directory": str(directory),
                "audio": str(audio_path) if audio_path.is_file() else None,
                "abc": abc,
                "truncated": song.truncated,
                "audio_seconds": result.get("audio_seconds"),
                "request": song.semantic.plan.request.to_dict(),
            }

    def transcribe(self, audio: str | Path, *, task="melody-full",
                   identifier="cover", on_status=None) -> dict:
        with self.lock:
            if on_status:
                on_status("卸载 YuE2 以便转谱占用 GPU…")
            self.unload()
            sheetsage = _ensure_resource("SheetSage2", on_status=on_status)
            mert = _ensure_resource("MERT-v2-FullSong", on_status=on_status)
            directory = new_job_dir(outputs_dir(), "transcribe", identifier)
            device = "cpu" if self._pipeline_kwargs.get("device") == "cpu" else "cuda"
            dtype = "bf16" if device == "cuda" else "fp32"
            score = run_transcribe(
                Path(audio), directory, task=task, model=sheetsage.path,
                base_model=mert.path, device=device, dtype=dtype, on_status=on_status,
            )
            abc = score.read_text(encoding="utf-8")
            warnings_path = directory / "transcription_manifest.json"
            warnings = []
            if warnings_path.is_file():
                import json
                data = json.loads(warnings_path.read_text(encoding="utf-8"))
                warnings = data.get("warnings") or []
            return {
                "directory": str(directory),
                "abc": abc,
                "warnings": warnings,
                "score": str(score),
            }


def _ensure_resource(name: str, *, on_status=None):
    statuses = {item.spec.name: item for item in scan_catalog()}
    item = statuses.get(name)
    if item is None or not item.present:
        if on_status:
            on_status(f"正在下载 {name}…")
        download_by_name(name, dest_root=models_dir())
        statuses = {item.spec.name: item for item in scan_catalog()}
        item = statuses.get(name)
    if item is None or not item.present or item.path is None:
        raise FileNotFoundError(f"{name} 下载后仍不可用")
    return item


def _request_kwargs(request: dict) -> dict:
    allowed = {"style", "lyrics", "cot", "seed", "abc", "cfg_scale", "id"}
    data = {key: request[key] for key in allowed if key in request and request[key] is not None}
    if "id" in data:
        data["id"] = song_id(str(data["id"]))
    if "seed" in data:
        data["seed"] = int(data["seed"])
    return data


def default_request() -> dict:
    path = yue_root() / "examples" / "song.json"
    if path.is_file():
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "id": "city_lights",
        "style": "English, warm piano pop, expressive female voice, acoustic piano, rounded bass and light drums, lyrical memorable melody, unhurried phrasing, 88 BPM",
        "lyrics": "[Verse]\nNeon fades along the lane\nFootsteps keep the time of rain\nFold the night and leave it here\nMorning has a sky to clear\n\n[Chorus]\nLet the day come into view\nEvery road begins with you\nHold a little room for light\nWe will sing beyond the night",
        "cot": "full",
        "seed": 831001,
    }

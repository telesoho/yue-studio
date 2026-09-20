"""Official YuE2 / SheetSage2 resources: locate locally or download from the Hub."""
from __future__ import annotations

import importlib.metadata
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .paths import models_dir, studio_root, yue_root


@dataclass(frozen=True)
class ResourceSpec:
    name: str
    repo_id: str
    role: str
    required: bool
    kind: str  # yue2 | vae | sheetsage | mert
    local_name: str


RESOURCES = (
    ResourceSpec("YuE2-3B", "m-a-p/YuE2-3B", "歌词+风格 → 曲谱规划 → 语义 token → 声学 latent", True, "yue2", "YuE2-3B"),
    ResourceSpec("YuE2-Vae", "m-a-p/YuE2-Vae", "聆听解码：latent → 48 kHz 立体声", True, "vae", "YuE2-Vae"),
    ResourceSpec("YuE2-Vae-legacy", "m-a-p/YuE2-Vae-legacy", "评测协议解码器，不要与聆听输出混放", False, "vae", "YuE2-Vae-legacy"),
    ResourceSpec("SheetSage2", "m-a-p/SheetSage2", "音频 → ABC 曲谱/和弦（翻唱转谱）", False, "sheetsage", "SheetSage2"),
    ResourceSpec("MERT-v2-FullSong", "m-a-p/MERT-v2-FullSong", "SheetSage2 自动加载的父编码器", False, "mert", "MERT-v2-FullSong"),
)

LICENSE_NOTE = "模型权重为 CC BY-NC 4.0（另有创作者许可条款）。代码 Apache 2.0 不改变权重许可。"


@dataclass(frozen=True)
class ResourceStatus:
    spec: ResourceSpec
    present: bool
    path: Path | None
    source: str | None
    size_bytes: int | None
    revision: str | None
    note: str

    def row(self) -> list[str]:
        need = "必需" if self.spec.required else "可选"
        state = "已就绪" if self.present else "缺失"
        loc = str(self.path) if self.path else "—"
        size = _format_size(self.size_bytes) if self.size_bytes else "—"
        rev = (self.revision or "—")[:12]
        return [self.spec.name, need, state, self.spec.role, loc, size, rev, self.source or "—"]


def _format_size(nbytes: int) -> str:
    value = float(nbytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{nbytes} B"


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


def _looks_complete(path: Path, kind: str) -> bool:
    if not path.is_dir() or not (path / "config.json").is_file():
        return False
    if kind in {"yue2", "vae"}:
        return ((path / "model.safetensors").is_file()
                or (path / "model.safetensors.index.json").is_file()
                or any(path.glob("model-*.safetensors")))
    return any(path.glob("*.safetensors")) or any(path.glob("*.bin")) or any(path.glob("*.py"))


def hub_cache_root() -> Path:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        return Path(HF_HUB_CACHE)
    except Exception:
        home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
        return Path(os.environ.get("HF_HUB_CACHE", home / "hub"))


def hub_snapshot(repo_id: str, cache: Path | None = None) -> tuple[Path | None, str | None]:
    folder = (cache or hub_cache_root()) / f"models--{repo_id.replace('/', '--')}"
    refs_main = folder / "refs" / "main"
    revision = refs_main.read_text(encoding="utf-8").strip() if refs_main.is_file() else None
    snapshots = folder / "snapshots"
    if revision and (snapshots / revision).is_dir():
        return snapshots / revision, revision
    if snapshots.is_dir():
        candidates = [p for p in snapshots.iterdir() if p.is_dir()]
        if candidates:
            latest = max(candidates, key=lambda p: p.stat().st_mtime)
            return latest, latest.name
    return None, None


def _candidate_dirs(spec: ResourceSpec, studio: Path, yue: Path) -> list[tuple[str, Path]]:
    return [
        ("studio", studio / spec.local_name),
        ("yue", yue / "models" / spec.local_name),
    ]


def locate(spec: ResourceSpec, *, studio: Path | None = None, yue: Path | None = None,
           include_hub: bool = True, hub_cache: Path | None = None) -> ResourceStatus:
    studio = studio or models_dir()
    yue = yue or yue_root()
    for source, path in _candidate_dirs(spec, studio, yue):
        if _looks_complete(path, spec.kind):
            revision = None
            if (path / "revision.txt").is_file():
                revision = (path / "revision.txt").read_text(encoding="utf-8").strip()
            return ResourceStatus(spec, True, path.resolve(), source, _dir_size(path), revision, "")
    if include_hub:
        snap, revision = hub_snapshot(spec.repo_id, hub_cache)
        if snap is not None and _looks_complete(snap, spec.kind):
            return ResourceStatus(spec, True, snap.resolve(), "hf-cache", _dir_size(snap),
                                  revision, "位于 Hugging Face 缓存")
    hint = "可在本页下载到 studio/models/"
    if spec.kind == "sheetsage":
        hint += "。翻唱转谱时会自动配置独立 Python 3.11 环境。"
    return ResourceStatus(spec, False, None, None, None, None, hint)


def scan_catalog(*, studio: Path | None = None, yue: Path | None = None,
                 include_hub: bool = True, hub_cache: Path | None = None) -> list[ResourceStatus]:
    return [locate(spec, studio=studio, yue=yue, include_hub=include_hub, hub_cache=hub_cache)
            for spec in RESOURCES]


def required_ready(statuses: list[ResourceStatus] | None = None) -> tuple[ResourceStatus, ResourceStatus]:
    statuses = statuses or scan_catalog()
    by_name = {item.spec.name: item for item in statuses}
    mot, vae = by_name["YuE2-3B"], by_name["YuE2-Vae"]
    missing = [item.spec.name for item in (mot, vae) if not item.present]
    if missing:
        raise FileNotFoundError("请先下载：" + "、".join(missing))
    return mot, vae


def _yue_allow_patterns() -> list[str]:
    from yue2.storage import MODEL_FILES, MODEL_LICENSES
    return sorted(MODEL_FILES) + ["model-?????-of-?????.safetensors"] + [
        "licenses/" + name for name in sorted(MODEL_LICENSES)
    ]


def download(spec: ResourceSpec, dest: Path, *, on_progress=None) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    import importlib

    from huggingface_hub import snapshot_download

    kwargs = {"repo_id": spec.repo_id, "local_dir": str(dest)}
    if spec.kind in {"yue2", "vae"}:
        kwargs["allow_patterns"] = _yue_allow_patterns()
    tqdm_class = _progress_tqdm(on_progress) if on_progress is not None else None
    if tqdm_class is not None:
        kwargs["tqdm_class"] = tqdm_class
    hf_tqdm_mod = importlib.import_module("huggingface_hub.utils.tqdm")
    previous = hf_tqdm_mod.tqdm
    if tqdm_class is not None:
        hf_tqdm_mod.tqdm = tqdm_class
    try:
        snapshot_download(**kwargs)
    finally:
        hf_tqdm_mod.tqdm = previous
    if not _looks_complete(dest, spec.kind):
        raise FileNotFoundError(f"Download of {spec.repo_id} did not produce a usable snapshot")
    return dest.resolve()


def download_by_name(name: str, *, dest_root: Path | None = None, on_progress=None) -> Path:
    spec = next((item for item in RESOURCES if item.name == name), None)
    if spec is None:
        raise KeyError(name)
    dest = (dest_root or models_dir()) / spec.local_name
    return download(spec, dest, on_progress=on_progress)


def _progress_tqdm(on_progress, *, min_interval=0.2):
    sink = _ProgressSink(on_progress, min_interval=min_interval)

    class _Tqdm:
        def __init__(self, iterable=None, desc="", total=None, **kwargs):
            kwargs.pop("name", None)
            self.iterable = iterable
            self.desc = desc or kwargs.get("desc") or ""
            self.total = total if total is not None else kwargs.get("total")
            self.n = kwargs.get("initial") or 0
            self.disable = kwargs.get("disable", False)
            self.unit = kwargs.get("unit", "it")
            if iterable is not None and self.total is None:
                try:
                    self.total = len(iterable)
                except TypeError:
                    self.total = None
            sink.touch(self)

        @classmethod
        def get_lock(cls):
            if not hasattr(cls, "_lock"):
                cls._lock = Lock()
            return cls._lock

        @classmethod
        def set_lock(cls, lock):
            cls._lock = lock

        def update(self, n=1):
            self.n += n
            sink.touch(self)

        def close(self):
            sink.touch(self, force=True)

        def __iter__(self):
            if self.iterable is None:
                return iter(())
            for item in self.iterable:
                self.update(1)
                yield item

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

        def set_description(self, desc=None, **kwargs):
            if desc:
                self.desc = desc
            sink.touch(self)

        def set_postfix(self, *args, **kwargs):
            return None

        def refresh(self):
            return None

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    return _Tqdm


class _ProgressSink:
    def __init__(self, on_progress, min_interval=0.2):
        self._on_progress = on_progress
        self._min_interval = min_interval
        self._lock = Lock()
        self._bars: dict[int, tuple] = {}
        self._last = 0.0
        self._desc = ""

    def touch(self, bar, *, force=False):
        with self._lock:
            self._desc = getattr(bar, "desc", "") or self._desc
            self._bars[id(bar)] = (
                float(getattr(bar, "n", 0) or 0),
                getattr(bar, "total", None),
                getattr(bar, "desc", "") or "",
                getattr(bar, "unit", "it") or "it",
            )
            now = time.monotonic()
            if not force and now - self._last < self._min_interval:
                return
            self._last = now
            bars = list(self._bars.values())
            byte_bars = [item for item in bars if item[3] == "B"]
            chosen = byte_bars or bars
            n = sum(item[0] for item in chosen)
            sized = [item[1] for item in chosen if item[1]]
            total = sum(sized) if sized else None
            desc = self._desc
            self._on_progress(n, total, desc)


def environment_report(settings) -> dict:
    versions = {}
    for package in ("transformers", "huggingface-hub", "safetensors", "gradio", "yue2-infer"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "studio_root": str(studio_root()),
        "yue_root": str(yue_root()),
        "models_dir": str(models_dir()),
        "hf_endpoint": os.environ.get("HF_ENDPOINT") or os.environ.get("HUGGINGFACE_HUB_ENDPOINT"),
        "versions": versions,
        "settings": {
            "device": settings.device,
            "memory_budget_gib": settings.memory_budget_gib,
            "quantization": settings.quantization,
            "offload_ar": settings.offload_ar,
            "vae_core_frames": settings.vae_core_frames,
        },
        "license": LICENSE_NOTE,
    }


CATALOG_HEADERS = ["名称", "级别", "状态", "用途", "路径", "体积", "revision", "来源"]

"""Studio-facing GPU probe and named YuE2 invocation presets.

Detection lives in ``yue2.hardware``. This module only labels devices,
picks a preset from VRAM, and explains the resulting pipeline kwargs.
"""
from __future__ import annotations

import html
from dataclasses import dataclass, field, replace

from yue2.hardware import DeviceInfo, HardwarePreset, cuda_devices, detect_preset, torch_runtime

PROFILE_AUTO = "auto"
PROFILE_8GB = "8gb"
PROFILE_24GB = "24gb"
PROFILE_CPU = "cpu"

PROFILE_CHOICES = (
    ("自动（按显存）", PROFILE_AUTO),
    ("8 GB FP8", PROFILE_8GB),
    ("24 GB BF16", PROFILE_24GB),
    ("CPU", PROFILE_CPU),
)


@dataclass(frozen=True)
class HardwareSnapshot:
    devices: tuple[DeviceInfo, ...]
    cuda_available: bool
    recommended: HardwarePreset
    runtime: dict = field(default_factory=dict)
    error: str | None = None


def fp8_supported(gpu: DeviceInfo | None) -> bool:
    if gpu is None:
        return False
    return gpu.major > 8 or (gpu.major == 8 and gpu.minor >= 9)


def probe(*, cuda_available: bool | None = None,
          devices: tuple[DeviceInfo, ...] | list[DeviceInfo] | None = None,
          runtime: dict | None = None) -> HardwareSnapshot:
    error = None
    live = cuda_available is None and devices is None
    if live:
        try:
            found = cuda_devices()
            cuda_available = bool(found)
            devices = found
            runtime = runtime if runtime is not None else torch_runtime()
        except Exception as exc:
            cuda_available = False
            devices = ()
            runtime = runtime or {}
            error = str(exc)
    info = tuple(devices or ())
    available = bool(cuda_available)
    recommended = detect_preset(device="auto", cuda_available=available, devices=info)
    return HardwareSnapshot(
        devices=info, cuda_available=available, recommended=recommended,
        runtime=runtime or {}, error=error,
    )


def device_choices(snapshot: HardwareSnapshot) -> list[tuple[str, str]]:
    items = []
    for gpu in snapshot.devices:
        torch_id = "cuda" if len(snapshot.devices) == 1 else gpu.torch_id
        items.append((_gpu_label(gpu), torch_id))
    items.append(("CPU", "cpu"))
    return items


def resolve_profile(profile: str, snapshot: HardwareSnapshot, *,
                    device: str | None = None) -> HardwarePreset:
    name = profile or PROFILE_AUTO
    requested = None if device in {None, "", "auto"} else str(device)
    if name == PROFILE_CPU or requested == "cpu":
        return _pretty_preset(replace(
            detect_preset(device="cpu", cuda_available=snapshot.cuda_available,
                          devices=snapshot.devices),
            notes=_cpu_notes(snapshot),
        ))
    if not snapshot.cuda_available or not snapshot.devices:
        return _pretty_preset(replace(
            detect_preset(device="cpu", cuda_available=False, devices=()),
            notes=("没有可用的 CUDA GPU，已改用 CPU。CPU 推理远慢于 GPU 预设。",),
        ))
    gpu_device = requested if requested and requested.startswith("cuda") else "cuda"
    if name == PROFILE_AUTO:
        preset = detect_preset(device=gpu_device, cuda_available=True, devices=snapshot.devices)
        return _pretty_preset(replace(preset, notes=_auto_notes(preset)))
    base = detect_preset(device=gpu_device, cuda_available=True, devices=snapshot.devices)
    gpu = _pick_gpu(snapshot.devices, base.device)
    if name == PROFILE_8GB:
        return _pretty_preset(_eight_gb_preset(base, gpu))
    if name == PROFILE_24GB:
        return _pretty_preset(_twenty_four_gb_preset(base, gpu))
    raise ValueError(f"Unknown hardware profile {profile!r}")


def preset_from_controls(*, device: str, memory_budget_gib: float, quantization: str,
                         offload_ar: bool, vae_core_frames: int,
                         snapshot: HardwareSnapshot) -> HardwarePreset:
    gpu = None
    if device != "cpu" and snapshot.devices:
        gpu = _pick_gpu(snapshot.devices, device)
    notes = ["自定义 YuE2 调用参数。"]
    if device == "cpu":
        notes = list(_cpu_notes(snapshot))
        if quantization == "fp8":
            notes.append("CPU 不支持 FP8，请改用 none。")
    elif gpu is None:
        notes.append("没有可用的 CUDA GPU，生成时可能改走 CPU 或失败。")
    else:
        if quantization == "fp8" and not fp8_supported(gpu):
            notes.append("此 GPU 不支持 FP8（需要 compute ≥ 8.9），生成时可能失败。")
        if memory_budget_gib > gpu.vram_gib + 0.05:
            notes.append(
                f"预算 {memory_budget_gib:g} GiB 大于本机显存 {gpu.vram_gib:.1f} GiB，可能 OOM。"
            )
        tight = memory_budget_gib <= 12 or gpu.vram_gib <= 12
        if tight and not offload_ar:
            notes.append("≤12 GiB 上关闭 offload_ar 更容易显存不足。")
        if tight and quantization == "none":
            notes.append("≤12 GiB 建议 FP8（compute ≥ 8.9）；当前为全精度。")
    return HardwarePreset(
        device=device,
        memory_budget_gib=float(memory_budget_gib),
        quantization=str(quantization),
        offload_ar=bool(offload_ar),
        vae_core_frames=int(vae_core_frames),
        gpu_name=None if gpu is None else gpu.name,
        vram_gib=None if gpu is None else gpu.vram_gib,
        compute_capability=None if gpu is None else gpu.compute,
        notes=tuple(notes),
    )


def recommended_profile(snapshot: HardwareSnapshot) -> str:
    preset = snapshot.recommended
    if preset.device == "cpu":
        return PROFILE_CPU
    if preset.memory_budget_gib <= 12:
        return PROFILE_8GB
    return PROFILE_24GB


def torch_line(snapshot: HardwareSnapshot | None = None) -> str:
    info = (snapshot.runtime if snapshot is not None else None) or {}
    if not info:
        try:
            info = torch_runtime()
        except Exception as exc:
            return f"PyTorch: 不可用（{exc}）"
    version = info.get("version") or "unknown"
    cuda = info.get("cuda")
    if info.get("cuda_available"):
        return f"PyTorch: {version}（CUDA {cuda}）"
    if cuda:
        return f"PyTorch: {version}（含 CUDA {cuda}，运行时不可用）"
    if info.get("mps_available"):
        return f"PyTorch: {version}（MPS）"
    return f"PyTorch: {version}（CPU）"


def hardware_html(snapshot: HardwareSnapshot, preset: HardwarePreset) -> str:
    vram = "—"
    gpu_line = "未检测到 CUDA GPU"
    if snapshot.error:
        gpu_line = "GPU 探测失败：" + snapshot.error
    elif snapshot.devices:
        gpu = _pick_gpu(snapshot.devices, preset.device) or snapshot.devices[0]
        vram = f"{gpu.vram_gib:.1f} GiB"
        gpu_line = _gpu_label(gpu)
        if len(snapshot.devices) > 1:
            gpu_line += f"  （共 {len(snapshot.devices)} 张）"
    elif snapshot.recommended.device == "mps":
        vram = "共享"
        gpu_line = "Apple MPS"
    params = (
        f"{preset.device} · budget {preset.memory_budget_gib:g} GiB · "
        f"{preset.quantization} · "
        f"{'offload_ar' if preset.offload_ar else 'no offload'} · "
        f"vae {preset.vae_core_frames}"
    )
    warning = next((item for item in preset.notes
                    if any(token in item for token in ("OOM", "失败", "不足", "不支持"))), None)
    note = warning or (preset.notes[0] if preset.notes else "按显存选择 YuE2 调用参数。")
    note_class = "hw-note warn" if warning else "hw-note"
    return (
        '<div class="hw-bar">'
        '<div class="hw-vram">'
        '<span class="hw-k">显存</span>'
        f'<span class="hw-v">{html.escape(vram)}</span>'
        f'{_vram_leds(snapshot, preset)}'
        f'<span class="hw-gpu">{html.escape(gpu_line)}</span>'
        "</div>"
        f'<p class="hw-params">{html.escape(params)}</p>'
        f'<p class="{note_class}">{html.escape(note)}</p>'
        "</div>"
    )


def _vram_leds(snapshot: HardwareSnapshot, preset: HardwarePreset) -> str:
    gib = preset.vram_gib
    if gib is None and snapshot.devices:
        gpu = _pick_gpu(snapshot.devices, preset.device) or snapshot.devices[0]
        gib = gpu.vram_gib
    if not gib:
        return ""
    filled = min(6, max(1, int(round(float(gib) / 4.0))))
    cells = "".join(
        f'<i class="{"on" if index < filled else "off"}"></i>' for index in range(6)
    )
    return f'<span class="hw-leds" aria-hidden="true">{cells}</span>'


def _pretty_preset(preset: HardwarePreset) -> HardwarePreset:
    return replace(preset, memory_budget_gib=round(float(preset.memory_budget_gib), 1))


def _gpu_label(gpu: DeviceInfo) -> str:
    return f"{gpu.name} · {gpu.vram_gib:.1f} GiB · CC {gpu.major}.{gpu.minor}"


def _pick_gpu(devices: tuple[DeviceInfo, ...], device: str) -> DeviceInfo | None:
    if not devices or not device or device in {"cpu", "mps"}:
        return None
    if device in {"cuda", "auto"}:
        return devices[0]
    if device.startswith("cuda:"):
        index = int(device.split(":", 1)[1])
        for gpu in devices:
            if gpu.index == index:
                return gpu
    return devices[0]


def _eight_gb_preset(base: HardwarePreset, gpu: DeviceInfo | None) -> HardwarePreset:
    vram = gpu.vram_gib if gpu is not None else 8.0
    fp8 = fp8_supported(gpu)
    notes = ["8 GB FP8 路径：AR 量化，NAR 仍为 BF16。不是官方 24 GB 音质基线。"]
    if not fp8:
        notes.append("此 GPU 不支持 FP8（需要 compute ≥ 8.9），量化已关闭。")
    if vram > 12:
        notes.append(f"本机显存约 {vram:.1f} GiB，也可改用 24 GB BF16。")
    return HardwarePreset(
        device=base.device, memory_budget_gib=min(8.0, vram),
        quantization="fp8" if fp8 else "none",
        offload_ar=True, vae_core_frames=512,
        gpu_name=base.gpu_name, vram_gib=base.vram_gib,
        compute_capability=base.compute_capability, notes=tuple(notes),
    )


def _twenty_four_gb_preset(base: HardwarePreset, gpu: DeviceInfo | None) -> HardwarePreset:
    notes = []
    if gpu is not None and gpu.vram_gib < 24:
        notes.append(f"本机显存约 {gpu.vram_gib:.1f} GiB，使用 24 GB 预设可能 OOM。")
    notes.append("官方 24 GB BF16 预设。")
    return HardwarePreset(
        device=base.device, memory_budget_gib=24, quantization="none",
        offload_ar=False, vae_core_frames=1024,
        gpu_name=base.gpu_name, vram_gib=base.vram_gib,
        compute_capability=base.compute_capability, notes=tuple(notes),
    )


def _auto_notes(preset: HardwarePreset) -> tuple[str, ...]:
    if preset.device == "cpu":
        return _cpu_notes_from_preset(preset)
    if preset.device == "mps":
        return ("Apple MPS。",)
    if (preset.vram_gib or 99) <= 12:
        notes = ["自动：≤12 GiB 走 8 GB FP8 路径，不是官方 24 GB BF16 音质基线。"]
        if preset.quantization != "fp8":
            notes.append("此 GPU 不支持 FP8（需要 compute ≥ 8.9），量化已关闭。")
        return tuple(notes)
    return ("自动：官方 24 GB BF16 预设。",)


def _cpu_notes(snapshot: HardwareSnapshot) -> tuple[str, ...]:
    if snapshot.devices:
        return (f"已选择 CPU。{snapshot.devices[0].name} 仍可用。",)
    return ("已选择 CPU。未检测到 CUDA，推理远慢于 GPU 预设。",)


def _cpu_notes_from_preset(preset: HardwarePreset) -> tuple[str, ...]:
    if preset.gpu_name:
        return (f"已选择 CPU。{preset.gpu_name} 仍可用。",)
    return ("未检测到 CUDA：CPU 推理远慢于 GPU 预设。",)

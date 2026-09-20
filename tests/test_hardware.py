from yue2.hardware import DeviceInfo

from yue_studio.hardware import (
    PROFILE_8GB,
    PROFILE_24GB,
    PROFILE_AUTO,
    PROFILE_CPU,
    HardwareSnapshot,
    device_choices,
    hardware_html,
    preset_from_controls,
    probe,
    recommended_profile,
    resolve_profile,
)


def _gpu(name="NVIDIA GeForce RTX 4060 Laptop GPU", gib=8, major=8, minor=9, index=0):
    return DeviceInfo(name, int(gib * 2**30), major, minor, index)


def _snapshot(devices):
    info = tuple(devices)
    return probe(cuda_available=bool(info), devices=info, runtime={"version": "test", "cuda": None})


def test_probe_without_cuda():
    snapshot = probe(cuda_available=False, devices=(), runtime={"version": "x", "cuda": None})
    assert snapshot.cuda_available is False
    assert snapshot.recommended.device == "cpu"
    assert recommended_profile(snapshot) == PROFILE_CPU
    assert device_choices(snapshot) == [("CPU", "cpu")]


def test_auto_8gb_fp8():
    snapshot = _snapshot((_gpu(),))
    preset = resolve_profile(PROFILE_AUTO, snapshot)
    assert preset.device == "cuda"
    assert preset.quantization == "fp8"
    assert preset.memory_budget_gib == 8
    assert preset.offload_ar is True
    assert preset.vae_core_frames == 512
    assert recommended_profile(snapshot) == PROFILE_8GB
    assert "8 GB FP8" in preset.notes[0]


def test_auto_24gb_bf16():
    snapshot = _snapshot((_gpu("RTX 4090", 24),))
    preset = resolve_profile(PROFILE_AUTO, snapshot)
    assert preset.quantization == "none"
    assert preset.memory_budget_gib == 24
    assert preset.offload_ar is False
    assert recommended_profile(snapshot) == PROFILE_24GB


def test_force_8gb_on_24gb_card():
    snapshot = _snapshot((_gpu("RTX 4090", 24),))
    preset = resolve_profile(PROFILE_8GB, snapshot)
    assert preset.memory_budget_gib == 8
    assert preset.quantization == "fp8"
    assert preset.offload_ar is True
    assert any("24 GB" in note for note in preset.notes)


def test_force_24gb_on_8gb_card_warns():
    snapshot = _snapshot((_gpu(),))
    preset = resolve_profile(PROFILE_24GB, snapshot)
    assert preset.memory_budget_gib == 24
    assert preset.quantization == "none"
    assert preset.offload_ar is False
    assert any("OOM" in note for note in preset.notes)


def test_8gb_without_fp8():
    snapshot = _snapshot((_gpu("Old GPU", 8, 7, 5),))
    preset = resolve_profile(PROFILE_8GB, snapshot)
    assert preset.quantization == "none"
    assert preset.offload_ar is True
    assert any("FP8" in note for note in preset.notes)


def test_gpu_profile_without_cuda_falls_back_to_cpu():
    snapshot = probe(cuda_available=False, devices=())
    preset = resolve_profile(PROFILE_8GB, snapshot)
    assert preset.device == "cpu"
    assert any("CPU" in note for note in preset.notes)


def test_device_choices_include_vram():
    gpus = (_gpu("GPU0", 24, index=0), _gpu("GPU1", 8, index=1))
    snapshot = _snapshot(gpus)
    choices = device_choices(snapshot)
    assert choices[0][0].startswith("GPU0")
    assert "24.0 GiB" in choices[0][0]
    assert choices[0][1] == "cuda:0"
    assert choices[1][1] == "cuda:1"
    assert choices[-1] == ("CPU", "cpu")
    preset = resolve_profile(PROFILE_AUTO, snapshot, device="cuda:1")
    assert preset.device == "cuda:1"
    assert preset.memory_budget_gib == 8


def test_custom_params_warn_when_budget_exceeds_vram():
    snapshot = _snapshot((_gpu(),))
    preset = preset_from_controls(
        device="cuda", memory_budget_gib=24, quantization="none",
        offload_ar=False, vae_core_frames=1024, snapshot=snapshot,
    )
    assert any("大于本机显存" in note for note in preset.notes)
    assert any("offload_ar" in note for note in preset.notes)


def test_auto_rounds_uneven_vram_budget():
    gpu = DeviceInfo("NVIDIA GeForce RTX 4060 Laptop GPU", 8585224192, 8, 9)
    snapshot = _snapshot((gpu,))
    preset = resolve_profile(PROFILE_AUTO, snapshot)
    assert preset.memory_budget_gib == 8.0
    assert "budget 8 GiB" in hardware_html(snapshot, preset)


def test_hardware_html_shows_vram_and_params():
    snapshot = _snapshot((_gpu(),))
    preset = resolve_profile(PROFILE_AUTO, snapshot)
    markup = hardware_html(snapshot, preset)
    assert "8.0 GiB" in markup
    assert "RTX 4060" in markup
    assert "budget 8 GiB" in markup
    assert "fp8" in markup
    assert "&lt;" in hardware_html(
        HardwareSnapshot((), False, snapshot.recommended, error="<boom>"),
        preset,
    )


def test_on_profile_applies_detected_vram(monkeypatch):
    from yue_studio import app

    monkeypatch.setattr(app, "SNAPSHOT", _snapshot((_gpu(),)))
    monkeypatch.setattr(app, "RUNNER", None)
    html, budget, quant, offload, vae, notes, env = app.on_profile(PROFILE_AUTO, "cuda")
    assert budget == 8
    assert quant == "fp8"
    assert offload is True
    assert vae == 512
    assert "8.0 GiB" in html
    assert "fp8" in env
    assert app.RUNNER.display_settings.memory_budget_gib == 8
    html, budget, quant, offload, vae, notes, env = app.on_profile(PROFILE_24GB, "cuda")
    assert budget == 24
    assert quant == "none"
    assert "OOM" in notes
    _, custom = app.sync_hardware(PROFILE_24GB, "cuda", 24, "none", False, 1024)
    assert any("OOM" in note for note in custom.notes)
    assert not any("自定义" in note for note in custom.notes)

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from yue2.protocol import GenerationConfig, SongRequest
from yue_studio.app import _progress_markup
from yue_studio.runner import StudioRunner, _StageProgress


def _events(on_status_calls=None):
    calls = [] if on_status_calls is None else on_status_calls

    def on_status(*args):
        calls.append(args)

    return calls, on_status


def test_stage_progress_moves_off_zero_then_throttles():
    events, on_status = _events()
    tracker = _StageProgress(on_status, "规划", 10, interval=60)
    assert events == [("规划", 0, 10)]
    tracker.on_token("abc", 65)
    assert events[-1] == ("规划", 1, 10)
    tracker.on_token("abc", 66)
    assert events[-1] == ("规划", 1, 10)
    tracker.finish()
    assert events[-1] == ("规划", 2, 10)


def test_stage_progress_updates_total_from_step_callback():
    events, on_status = _events()
    tracker = _StageProgress(on_status, "NAR", None, interval=0)
    tracker.on_progress(1, 8)
    tracker.on_progress(8, 8)
    assert events == [("NAR", 0, None), ("NAR", 1, 8), ("NAR", 8, 8)]


def test_progress_markup_shows_fraction_and_counts():
    idle = _progress_markup("正在加载 YuE2…", state="running")
    running = _progress_markup("正在规划曲谱…", 3, 4096, state="running")
    assert "正在加载 YuE2…" in idle
    assert "indeterminate" in idle
    assert "正在规划曲谱…" in running
    assert "3/4096" in running
    assert "0.1%" in running
    assert "indeterminate" not in running


class FakePlan:
    def __init__(self, abc="X:1\nK:C\nC"):
        self.abc = abc
        self.truncated = False
        self.timing = {"output_tokens": 3}
        self.request = SongRequest(style="piano", lyrics="lyric", cot="full", seed=1, id="song")

    def save(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / "score.abc").write_text(self.abc, encoding="utf-8")


def _runner(tmp_path, monkeypatch, pipe):
    monkeypatch.setattr("yue_studio.runner.outputs_dir", lambda: tmp_path)
    runner = StudioRunner(pipeline_kwargs={"device": "cpu"})
    runner._ensure_pipe = lambda **kwargs: pipe
    return runner


def test_set_use_gpu_sets_device_without_probing():
    runner = StudioRunner()
    assert runner.display_settings.device == "cuda"
    runner.set_use_gpu(False)
    assert runner.display_settings.device == "cpu"
    runner.set_use_gpu(True)
    assert runner.display_settings.device == "cuda"


def test_apply_settings_updates_budget_and_unloads():
    from yue_studio.runner import PipelineSettings

    runner = StudioRunner()
    runner._pipe = SimpleNamespace(close=lambda: None)
    runner._key = ("x",)
    runner.settings = runner.display_settings
    next_settings = PipelineSettings(
        device="cuda", memory_budget_gib=8, quantization="fp8",
        offload_ar=True, vae_core_frames=512,
    )
    runner.apply_settings(next_settings)
    assert runner.display_settings == next_settings
    assert runner._pipe is None
    runner.apply_settings(next_settings)
    assert runner.display_settings.memory_budget_gib == 8


def test_apply_settings_writes_explicit_24gb_when_only_device_set():
    from yue_studio.runner import PipelineSettings

    runner = StudioRunner()
    assert "memory_budget_gib" not in runner._pipeline_kwargs
    settings = PipelineSettings(
        device="cuda", memory_budget_gib=24, quantization="none",
        offload_ar=False, vae_core_frames=1024,
    )
    runner.apply_settings(settings)
    assert runner._pipeline_kwargs["memory_budget_gib"] == 24
    assert runner._pipeline_kwargs["quantization"] == "none"
    assert runner._pipeline_kwargs["offload_ar"] is False


def test_transcribe_uses_runner_device(tmp_path, monkeypatch):
    monkeypatch.setattr("yue_studio.runner.outputs_dir", lambda: tmp_path)
    monkeypatch.setattr("yue_studio.runner.models_dir", lambda: tmp_path)
    audio = tmp_path / "song.wav"
    audio.write_bytes(b"RIFF")
    model = tmp_path / "SheetSage2"
    model.mkdir()
    captured = {}

    def fake_run_transcribe(path, directory, **kwargs):
        captured.update(kwargs)
        score = directory / "score.abc"
        score.write_text("X:1\nK:C\nC", encoding="utf-8")
        return score

    monkeypatch.setattr("yue_studio.runner.run_transcribe", fake_run_transcribe)
    monkeypatch.setattr(
        "yue_studio.runner.scan_catalog",
        lambda: [SimpleNamespace(
            spec=SimpleNamespace(name="SheetSage2"),
            present=True, path=model,
        )],
    )
    runner = StudioRunner()
    runner.set_use_gpu(False)
    result = runner.transcribe(audio)
    assert captured["device"] == "cpu"
    assert captured["dtype"] == "fp32"
    assert "score.abc" in result["score"]


def test_plan_reports_token_counts(tmp_path, monkeypatch):
    events, on_status = _events()
    tokens = []

    class FakePipe:
        generation_config = GenerationConfig()

        def plan(self, **kwargs):
            on_token = kwargs.get("on_token")
            assert on_token is not None
            for token in (10, 11, 12):
                tokens.append(token)
                on_token("abc", token)
            return FakePlan()

    result = _runner(tmp_path, monkeypatch, FakePipe()).plan(
        {"style": "piano", "lyrics": "lyric", "cot": "full", "seed": 1, "id": "song"},
        on_status=on_status,
    )
    assert tokens == [10, 11, 12]
    assert events[0] == ("正在规划曲谱…", 0, GenerationConfig().abc.max_tokens)
    assert events[-1] == ("正在规划曲谱…", 3, GenerationConfig().abc.max_tokens)
    assert "X:1" in result["abc"]


def test_render_reports_semantic_nar_and_vae(tmp_path, monkeypatch):
    class DummySong:
        def __init__(self, audio, sr, semantic, latents, config, weights, timing, request_id):
            self.abc = semantic.plan.abc
            self.truncated = {"abc": False, "semantic": False}
            self.semantic = semantic

        def save_artifacts(self, directory):
            Path(directory).mkdir(parents=True, exist_ok=True)
            (Path(directory) / "audio.flac").write_bytes(b"fLaC")
            return {"audio_seconds": 1.5}

    monkeypatch.setattr("yue2.pipeline.SongResult", DummySong)
    monkeypatch.setattr("yue2.storage.identity", lambda value: "id")

    events, on_status = _events()
    plan = FakePlan()
    semantic = SimpleNamespace(plan=plan, tokens=[1, 2], timing={}, truncated=False)
    latents = np.zeros((64, 64), dtype=np.float32)

    class FakePipe:
        generation_config = GenerationConfig()
        vae_core_frames = 32
        weights = {}
        load_timing = {}

        def plan(self, **kwargs):
            on_token = kwargs.get("on_token")
            if on_token:
                on_token("abc", 1)
            return plan

        def generate_semantic(self, saved, *, on_token=None, sampling=None, cancelled=None):
            assert saved is plan
            if on_token:
                on_token("semantic", 2)
                on_token("semantic", 3)
            return semantic

        def synthesize(self, result, *, on_progress=None, cancelled=None):
            assert result is semantic
            if on_progress:
                on_progress(1, 8)
                on_progress(8, 8)
            return latents

        def decode(self, z, *, on_progress=None, full=False, vae=None):
            assert z is latents
            if on_progress:
                on_progress(1, 2)
                on_progress(2, 2)
            return np.zeros((16, 2), dtype=np.float32)

        def effective_config(self, request):
            return {}

    result = _runner(tmp_path, monkeypatch, FakePipe()).render(
        {"style": "piano", "lyrics": "lyric", "cot": "full", "seed": 1, "id": "song"},
        on_status=on_status,
    )
    labels = [item[0] for item in events]
    assert "正在规划曲谱…" in labels
    assert "正在生成语义 token…" in labels
    assert "正在合成声学 latent…" in labels
    assert "正在解码音频…" in labels
    assert any(item == ("正在合成声学 latent…", 8, 8) for item in events)
    assert any(item[0] == "正在生成语义 token…" and item[1] >= 1 for item in events)
    assert result["audio_seconds"] == 1.5
    assert result["audio"] is not None

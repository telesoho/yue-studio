import io
import sys

from pathlib import Path
from types import SimpleNamespace

from yue_studio.app import (
    _download_log_line,
    _logged_work,
    _progress_markup,
    download_resource,
    transcribe_cover,
)
from yue_studio.runner import PipelineSettings
from yue_studio.invoke import (
    InvocationLog,
    StreamTee,
    format_invocation,
    status_line,
    yue2_generate_argv,
)


def _preset():
    return PipelineSettings(
        device="cuda", memory_budget_gib=8, quantization="fp8",
        offload_ar=True, vae_core_frames=512,
    )


def test_generate_argv_includes_hardware_and_stage():
    argv = yue2_generate_argv(
        model=r"C:\models\YuE2-3B", vae=r"C:\models\YuE2-Vae",
        preset=_preset(), request={"id": "city", "cot": "full", "seed": 831001},
        stage="plan",
    )
    assert argv[:2] == ["yue2", "generate"]
    assert argv[argv.index("--budget") + 1] == "8"
    assert argv[argv.index("--quantization") + 1] == "fp8"
    assert "--offload-ar" in argv
    assert "--offline" in argv
    assert argv[argv.index("--stage") + 1] == "plan"
    assert argv[argv.index("--seed") + 1] == "831001"
    assert "--abc-file" not in argv


def test_generate_argv_marks_external_abc():
    argv = yue2_generate_argv(
        model="m", vae="v", preset=_preset(),
        request={"id": "s", "cot": "melody", "seed": 1, "abc": "X:1\n"},
        stage="audio",
    )
    assert argv[argv.index("--abc-file") + 1] == "<request.abc>"
    assert argv[argv.index("--cot") + 1] == "melody"


def test_invocation_shows_command_and_request():
    text = format_invocation(
        stage="audio",
        request={"id": "song", "cot": "full", "seed": 2, "style": "piano",
                 "lyrics": "hello lyrics"},
        preset=_preset(), model=r"C:\m", vae=r"C:\v",
    )
    assert text.startswith("=== 命令 ===")
    assert "=== 参数 ===" in text
    assert "yue2" in text and "generate" in text
    assert "hello lyrics" in text
    assert "pipe.generate_semantic(plan)" in text
    assert '"quantization": "fp8"' in text


def test_status_line_includes_counts():
    assert status_line("规划") == "规划"
    assert status_line("规划", 3, 4096) == "规划 3/4096"


def test_invocation_log_live_line_replaced():
    log = InvocationLog("HEADER")
    log.add("start")
    log.add("progress 1", live=True)
    first = log.text()
    log.add("progress 2", live=True)
    second = log.text()
    log.add("done")
    assert "HEADER" in first and "=== 日志 ===" in first
    assert first.count("progress") == 1
    assert "progress 1" not in second
    assert "progress 2" in second
    assert "progress 2" not in log.text()
    assert "done" in log.text()


def test_stream_tee_splits_newlines_and_carriage_returns():
    lines = []
    tee = StreamTee(io.StringIO(), lambda line, live=False: lines.append((line, live)))
    tee.write("hello\n")
    tee.write("[YuE2] Running 1\r")
    tee.write("[YuE2] Running 2\r")
    tee.write("[YuE2] Completed\n")
    tee.write("leftover")
    tee.close()
    assert ("hello", False) in lines
    assert ("[YuE2] Running 1", True) in lines
    assert ("[YuE2] Running 2", True) in lines
    assert ("[YuE2] Completed", False) in lines
    assert ("leftover", False) in lines


def test_progress_markup_is_separate_from_log():
    idle = _progress_markup()
    running = _progress_markup("正在规划曲谱…", 306, 4896, state="running")
    assert "等待任务" in idle
    assert "正在规划曲谱…" in running
    assert "306/4896" in running
    assert "job-progress-bar" in running
    assert "&lt;" in _progress_markup("<script>", state="running")


def test_progress_markup_formats_byte_counts():
    markup = _progress_markup("model.safetensors", 40 * 1024, 100 * 1024, state="running", unit="bytes")
    assert "model.safetensors" in markup
    assert "40.0 KiB / 100.0 KiB" in markup
    assert "40.0%" in markup
    assert "40960/102400" not in markup


def test_download_log_line_keeps_size_on_one_line():
    line = _download_log_line("YuE2-3B", 40 * 1024, 100 * 1024, "model.safetensors")
    assert "model.safetensors" in line
    assert "40.0 KiB / 100.0 KiB" in line
    assert "40.0%" in line
    assert "\n" not in line


def test_download_resource_streams_only_download_panel(monkeypatch):
    import gradio as gr

    def fake_download(name, dest_root=None, on_progress=None):
        print("hub-fetch", file=sys.stderr)
        on_progress(32, 80, "model.safetensors")
        on_progress(80, 80, "model.safetensors")
        return Path("/tmp/YuE2-3B")

    monkeypatch.setattr("yue_studio.app.download_by_name", fake_download)
    monkeypatch.setattr("yue_studio.app._catalog_rows", lambda: [["YuE2-3B", "已就绪"]])
    monkeypatch.setattr("yue_studio.app._env_text", lambda: "env-ready")
    monkeypatch.setattr(
        "yue_studio.app.get_runner",
        lambda: SimpleNamespace(display_settings=SimpleNamespace(device="cpu")),
    )

    events = list(download_resource("YuE2-3B"))
    assert events[0][:2] == (gr.skip(), gr.skip())
    assert "开始下载 YuE2-3B" in events[0][3]
    assert "job-progress" in events[0][2]
    progress_logs = [event[3] for event in events]
    assert any("model.safetensors" in text for text in progress_logs)
    assert any("hub-fetch" in text for text in progress_logs)
    assert events[-1][0] == [["YuE2-3B", "已就绪"]]
    assert events[-1][1] == "env-ready"
    assert "完成" in events[-1][2]
    assert "已下载到" in events[-1][3]
    for catalog, env, *_ in events[:-1]:
        assert catalog == gr.skip()
        assert env == gr.skip()


def test_logged_work_records_failure_without_raising():
    def work(on_status):
        on_status("SheetSage2 转谱中…")
        raise RuntimeError("ffmpeg is required to read audio files")

    events = list(_logged_work("HEADER", work))
    assert events[-1][0] == "failed"
    assert "ffmpeg is required" in events[-1][1]
    assert "ffmpeg is required" in events[-1][2]
    assert "failed" in events[-1][3]


def test_transcribe_cover_failure_keeps_score_panels(monkeypatch):
    import gradio as gr

    class Boom:
        def transcribe(self, *args, **kwargs):
            raise RuntimeError("ffmpeg is required to read audio files")

    monkeypatch.setattr("yue_studio.app.sync_hardware", lambda *args, **kwargs: None)
    monkeypatch.setattr("yue_studio.app.get_runner", lambda *args, **kwargs: Boom())

    events = []
    for event in transcribe_cover(
        "song.wav", None, "", "旋律（推荐翻唱）",
        "auto", "cuda", 8, "fp8", True, 512,
    ):
        events.append(event)

    last = events[-1]
    assert last[:4] == (gr.skip(), gr.skip(), gr.skip(), gr.skip())
    assert "failed" in last[4]
    assert "ffmpeg is required" in last[5]


def test_download_resource_failure_keeps_catalog(monkeypatch):
    import gradio as gr

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("yue_studio.app.download_by_name", boom)
    monkeypatch.setattr(
        "yue_studio.app.get_runner",
        lambda: SimpleNamespace(display_settings=SimpleNamespace(device="cpu")),
    )

    events = list(download_resource("YuE2-3B"))
    assert events[-1][0] == gr.skip()
    assert events[-1][1] == gr.skip()
    assert "failed" in events[-1][2]
    assert "disk full" in events[-1][3]


def test_logged_work_streams_status_and_stderr():
    def work(on_status):
        print("native-log", file=sys.stderr)
        on_status("正在规划曲谱…", 3, 10)
        on_status("正在规划曲谱…", 4, 10)
        on_status("正在生成语义 token…", 1, 8)
        return {"ok": True}

    events = list(_logged_work("HEADER", work))
    assert events[0][0] == "running"
    assert events[-1][0] == "done"
    assert events[-1][2] == {"ok": True}
    text = events[-1][1]
    assert "HEADER" in text
    assert "=== 日志 ===" in text
    assert "native-log" in text
    assert "正在规划曲谱… 4/10" in text
    assert "正在规划曲谱… 3/10" not in text
    assert "正在生成语义 token… 1/8" in text
    assert "完成" in text
    progress_updates = [event[3] for event in events]
    assert any("3/10" in markup for markup in progress_updates)
    assert any("4/10" in markup for markup in progress_updates)
    assert "完成" in progress_updates[-1]
    assert progress_updates[-1] != text

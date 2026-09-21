"""Yue Studio Gradio app."""
from __future__ import annotations

import html
import queue
import threading
import traceback
from pathlib import Path

import gradio as gr

from .hardware import (
    PROFILE_AUTO,
    PROFILE_CHOICES,
    device_choices,
    hardware_html,
    preset_from_controls,
    probe,
    resolve_profile,
    torch_line,
)
from .invoke import (
    InvocationLog,
    capture_stderr,
    format_invocation,
    status_line,
)
from .history import (
    TABLE_HEADERS as HISTORY_HEADERS,
    delete_entry,
    history_table,
    load_entry,
)
from .history import TABLE_HEADERS, delete_entry, history_table, load_entry
from .jobs import song_id
from .models import (
    CATALOG_HEADERS,
    LICENSE_NOTE,
    RESOURCES,
    _format_size,
    download_by_name,
    environment_report,
    required_ready,
    scan_catalog,
)
from .paths import models_dir, outputs_dir, sheetsage_python, studio_root, yue_root
from .runner import PipelineSettings, StudioRunner, default_request
from .score import CHORD_HEADERS, inspect_abc
from .sheetsage import ensure_sheetsage_env
from .theme import CSS

RUNNER: StudioRunner | None = None
SNAPSHOT = None


def current_snapshot():
    global SNAPSHOT
    if SNAPSHOT is None:
        SNAPSHOT = probe()
    return SNAPSHOT


def refresh_snapshot():
    global SNAPSHOT
    SNAPSHOT = probe()
    return SNAPSHOT


def get_runner(settings: PipelineSettings | None = None) -> StudioRunner:
    global RUNNER
    if RUNNER is None:
        if settings is None:
            preset = resolve_profile(PROFILE_AUTO, current_snapshot())
            settings = PipelineSettings(**preset.pipeline_kwargs())
        RUNNER = StudioRunner(pipeline_kwargs=settings.pipeline_kwargs())
    elif settings is not None:
        RUNNER.apply_settings(settings)
    return RUNNER


def _catalog_rows():
    return [item.row() for item in scan_catalog()]


def _env_text() -> str:
    runner = get_runner()
    report = environment_report(runner.display_settings)
    python = sheetsage_python()
    snapshot = current_snapshot()
    gpu_lines = [
        f"GPU{gpu.index}: {gpu.name} · {gpu.vram_gib:.1f} GiB · CC {gpu.major}.{gpu.minor}"
        for gpu in snapshot.devices
    ] or ["GPU: 未检测到 CUDA"]
    if snapshot.error:
        gpu_lines.append("探测错误: " + snapshot.error)
    lines = [
        f"工作室: {report['studio_root']}",
        f"YuE2: {report['yue_root']}",
        f"模型目录: {report['models_dir']}",
        f"HF_ENDPOINT: {report['hf_endpoint'] or '（默认 huggingface.co）'}",
        "",
        *gpu_lines,
        torch_line(snapshot),
        runner.display_settings.summary(),
        "",
        "依赖: " + ", ".join(f"{k}={v}" for k, v in report["versions"].items()),
        f"SheetSage2 解释器: {python or '未配置（翻唱转谱时自动安装）'}",
        f"FFmpeg: {report.get('ffmpeg') or '未找到（翻唱转谱需要，请安装并加入 PATH）'}",
        "",
        LICENSE_NOTE,
    ]
    return "\n".join(lines)


def _active_device(profile, gpu_device, snapshot):
    if profile == "cpu" or gpu_device == "cpu":
        return "cpu"
    if gpu_device:
        return gpu_device
    return resolve_profile(profile, snapshot, device=gpu_device).device


def sync_hardware(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    snapshot = current_snapshot()
    named = resolve_profile(profile, snapshot, device=gpu_device)
    device = _active_device(profile, gpu_device, snapshot)
    budget_v = float(budget if budget is not None else named.memory_budget_gib)
    quant_v = str(quantization or named.quantization)
    offload_v = named.offload_ar if offload_ar is None else bool(offload_ar)
    vae_v = int(vae_core_frames or named.vae_core_frames)
    matches = (
        device == named.device
        and round(budget_v, 1) == round(named.memory_budget_gib, 1)
        and quant_v == named.quantization
        and offload_v == named.offload_ar
        and vae_v == named.vae_core_frames
    )
    if matches:
        preset = named
    else:
        preset = preset_from_controls(
            device=device, memory_budget_gib=budget_v, quantization=quant_v,
            offload_ar=offload_v, vae_core_frames=vae_v, snapshot=snapshot,
        )
    get_runner(PipelineSettings(**preset.pipeline_kwargs()))
    return snapshot, preset


def _hardware_outputs(snapshot, preset):
    return (
        hardware_html(snapshot, preset),
        preset.memory_budget_gib,
        preset.quantization,
        preset.offload_ar,
        preset.vae_core_frames,
        "\n".join(preset.notes),
        _env_text(),
    )


def on_profile(profile, gpu_device):
    snapshot = current_snapshot()
    preset = resolve_profile(profile, snapshot, device=gpu_device)
    get_runner(PipelineSettings(**preset.pipeline_kwargs()))
    return _hardware_outputs(snapshot, preset)


def on_params(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    snapshot, preset = sync_hardware(
        profile, gpu_device, budget, quantization, offload_ar, vae_core_frames)
    return hardware_html(snapshot, preset), "\n".join(preset.notes), _env_text()


def _score_outputs(abc: str):
    view = inspect_abc(abc or "")
    chords = view.chords or []
    status = "曲谱有效" if view.error is None else view.error
    if view.error is None and not chords:
        status = "曲谱有效（无和弦符号）"
    return view.html, abc or "", chords, status


def _file_path(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    name = getattr(value, "name", None)
    return str(name) if name else None


def _truncated_text(value) -> str:
    if not value:
        return "未截断"
    if isinstance(value, dict):
        flags = [key for key, flag in value.items() if flag]
        return "截断: " + ", ".join(flags) if flags else "未截断"
    return str(value)


def refresh_models(profile, gpu_device):
    refresh_snapshot()
    hw = on_profile(profile, gpu_device)
    return (_catalog_rows(),) + hw


def download_resource(name):
    if not name:
        raise gr.Error("请选择要下载的资源")

    updates: queue.Queue = queue.Queue()
    log = InvocationLog(f"=== 下载 ===\n{name}")
    cuda = get_runner().display_settings.device != "cpu"

    def on_progress(n, total, desc):
        updates.put(("p", n, total, desc))

    def on_line(line, live=False):
        updates.put(("line", line, live, None))

    def worker():
        try:
            with capture_stderr(on_line):
                path = download_by_name(name, dest_root=models_dir(), on_progress=on_progress)
                if name == "SheetSage2":
                    ensure_sheetsage_env(
                        model_dir=path,
                        cuda=cuda,
                        on_status=lambda message: updates.put(("msg", message, None, None)),
                    )
            updates.put(("ok", path, None, None))
        except Exception as exc:
            updates.put(("err", f"{type(exc).__name__}: {exc}", None, None))

    threading.Thread(target=worker, daemon=True).start()
    log.add(f"开始下载 {name}")
    progress_html = _progress_markup(f"开始下载 {name}", state="running")
    yield gr.skip(), gr.skip(), progress_html, log.text()
    while True:
        kind, payload, extra, desc = updates.get()
        if kind == "p":
            progress_html = _progress_markup(
                (desc or "").strip() or f"下载 {name}",
                payload, extra, state="running", unit="bytes",
            )
            log.add(_download_log_line(name, payload, extra, desc), live=True)
            yield gr.skip(), gr.skip(), progress_html, log.text()
        elif kind == "line":
            log.add(payload, live=bool(extra))
            yield gr.skip(), gr.skip(), progress_html, log.text()
        elif kind == "msg":
            log.add(payload)
            progress_html = _progress_markup(payload, state="running")
            yield gr.skip(), gr.skip(), progress_html, log.text()
        elif kind == "ok":
            log.add(f"已下载到 {payload}")
            progress_html = _progress_markup("完成", 1, 1, state="done")
            yield _catalog_rows(), _env_text(), progress_html, log.text()
            return
        else:
            log.add(payload)
            progress_html = _progress_markup(payload, state="failed")
            yield gr.skip(), gr.skip(), progress_html, log.text()
            return


def _download_log_line(name, n, total, desc) -> str:
    label = (desc or "").strip() or f"下载 {name}"
    if total:
        if total >= 1024:
            body = f"{_format_size(int(n))} / {_format_size(int(total))}"
        else:
            body = f"{int(n)} / {int(total)}"
        return f"{label}  {body}  ({100.0 * n / total:.1f}%)"
    return f"{label}  {_format_size(int(n)) if n >= 1024 else int(n)}"


def _progress_markup(message="", completed=None, total=None, *, state="idle", unit=None) -> str:
    label = html.escape(str(message)) if message else "等待任务"
    bar_class = "job-progress-bar"
    width = "0%"
    if state == "idle":
        cls = "job-progress idle"
    elif state == "failed":
        cls = "job-progress failed"
        bar_class += " indeterminate"
    elif completed is None or not total:
        cls = "job-progress"
        bar_class += " indeterminate"
    else:
        cls = "job-progress done" if state == "done" else "job-progress"
        pct = min(100.0, max(0.0, 100.0 * float(completed) / float(total)))
        width = f"{pct:.1f}%"
        if unit == "bytes":
            counts = f"{_format_size(int(completed))} / {_format_size(int(total))} — {pct:.1f}%"
        else:
            counts = f"{int(completed)}/{int(total)} — {pct:.1f}%"
        label = f"{label} {counts}"
    return (
        f'<div class="{cls}">'
        f'<div class="job-progress-label">{label}</div>'
        f'<div class="job-progress-track">'
        f'<div class="{bar_class}" style="width:{width}"></div>'
        f"</div></div>"
    )


def _model_paths():
    try:
        mot, vae = required_ready()
        return str(mot.path), str(vae.path)
    except FileNotFoundError as exc:
        return f"<{exc}>", f"<{exc}>"


def _logged_work(header, work):
    log = InvocationLog(header)
    updates = queue.Queue()
    last_stage = None
    last_status = None

    def on_line(line, live=False):
        updates.put(("line", line, live))

    def on_status(message, completed=None, total=None):
        updates.put(("status", message, completed, total))

    def worker():
        try:
            with capture_stderr(on_line):
                result = work(on_status)
            updates.put(("ok", result))
        except Exception as exc:
            updates.put(("err", f"{type(exc).__name__}: {exc}", traceback.format_exc()))

    threading.Thread(target=worker, daemon=True).start()
    progress_html = _progress_markup("正在运行…", state="running")
    yield "running", log.text(), None, progress_html
    while True:
        kind, *rest = updates.get()
        if kind == "line":
            log.add(rest[0], live=rest[1])
            yield "running", log.text(), None, progress_html
        elif kind == "status":
            message, completed, total = rest
            progress_html = _progress_markup(message, completed, total, state="running")
            label = status_line(message, completed, total)
            if last_stage is not None and message != last_stage and last_status:
                log.add(last_status)
            log.add(label, live=True)
            last_stage = message
            last_status = label
            yield "running", log.text(), None, progress_html
        elif kind == "ok":
            if last_status:
                log.add(last_status)
            log.add("完成")
            progress_html = _progress_markup("完成", 1, 1, state="done")
            yield "done", log.text(), rest[0], progress_html
            return
        else:
            if last_status:
                log.add(last_status)
            log.add(rest[0])
            for line in (rest[1] or "").splitlines():
                log.add(line)
            progress_html = _progress_markup(rest[0], state="failed")
            yield "failed", log.text(), rest[0], progress_html
            return


def _invocation_header(stage, request):
    model, vae = _model_paths()
    return format_invocation(
        stage=stage, request=request, preset=get_runner().display_settings,
        model=model, vae=vae,
    )


def plan_song(style, lyrics, cot, seed, identifier, extra_abc,
              profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    sync_hardware(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames)
    request = {
        "style": style, "lyrics": lyrics, "cot": cot,
        "seed": int(seed), "id": song_id(identifier or "song"),
    }
    if extra_abc and extra_abc.strip() and cot != "off":
        request["abc"] = extra_abc
    header = _invocation_header("plan", request)
    abc_in = extra_abc or ""
    score_html, _abc_show, chords, _score_status = _score_outputs(abc_in if cot != "off" else "")
    if cot == "off":
        log = InvocationLog(header)
        log.add("cot=off 不生成曲谱，可直接合成音频。")
        yield None, request, score_html, abc_in, chords, _progress_markup("cot=off", 1, 1, state="done"), log.text(), None
        return
    for phase, log_text, payload, progress_html in _logged_work(
            header, lambda on_status: get_runner().plan(request, on_status=on_status)):
        if phase == "running":
            yield gr.skip(), request, gr.skip(), gr.skip(), gr.skip(), progress_html, log_text, gr.skip()
            continue
        if phase == "failed":
            yield gr.skip(), request, gr.skip(), gr.skip(), gr.skip(), progress_html, log_text, gr.skip()
            return
        result = payload
        score_html, abc, chords, score_status = _score_outputs(result["abc"])
        note = score_status
        if result["truncated"]:
            note = "规划被截断。\n" + note
        yield (result["directory"], result["request"], score_html, abc, chords,
               progress_html, log_text + "\n" + note, None)


def render_song(style, lyrics, cot, seed, identifier, abc_text, plan_dir, request_state,
                profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    sync_hardware(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames)
    request = dict(request_state or {})
    request.update({
        "style": style, "lyrics": lyrics, "cot": cot,
        "seed": int(seed), "id": song_id(identifier or request.get("id") or "song"),
    })
    if cot != "off" and abc_text and abc_text.strip():
        view = inspect_abc(abc_text)
        if view.error:
            raise gr.Error("ABC 无法解析: " + view.error)
        request["abc"] = abc_text
    header = _invocation_header("audio", request)
    for phase, log_text, payload, progress_html in _logged_work(
            header,
            lambda on_status: get_runner().render(
                request, abc_text=abc_text if cot != "off" else None,
                plan_dir=plan_dir, on_status=on_status)):
        if phase == "running":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            continue
        if phase == "failed":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            return
        result = payload
        score_html, abc, chords, score_status = _score_outputs(result["abc"] or abc_text or "")
        info = (
            f"{log_text}\n"
            f"输出: {result['directory']}\n"
            f"{_truncated_text(result['truncated'])}\n"
            f"时长: {result.get('audio_seconds')}\n"
            f"{score_status}"
        )
        yield result["audio"], score_html, abc, chords, progress_html, info


def transcribe_cover(audio, abc_file, abc_text, task_label,
                     profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    sync_hardware(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames)
    file_abc = _file_path(abc_file)
    if file_abc:
        abc_text = Path(file_abc).read_text(encoding="utf-8")
    audio_path = _file_path(audio)
    score_html, abc, chords, score_status = _score_outputs(abc_text or "")
    if abc_text and abc_text.strip() and not audio_path:
        yield (None, score_html, abc, chords,
               _progress_markup("使用已有 ABC", 1, 1, state="done"),
               "使用上传/粘贴的 ABC。\n" + score_status)
        return
    if not audio_path:
        raise gr.Error("请上传音频，或提供 ABC")
    task = "full" if task_label.startswith("完整") else "melody-full"
    header = "=== 命令 ===\nSheetSage2 转谱（子进程；命令写入日志）\n\n=== 参数 ===\n" + (
        f"audio={audio_path}\ntask={task}"
    )
    for phase, log_text, payload, progress_html in _logged_work(
            header,
            lambda on_status: get_runner().transcribe(audio_path, task=task, on_status=on_status)):
        if phase == "running":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            continue
        if phase == "failed":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            return
        result = payload
        score_html, abc, chords, score_status = _score_outputs(result["abc"])
        warnings = result.get("warnings") or []
        note = score_status
        if warnings:
            note = "转谱警告:\n" + "\n".join(map(str, warnings)) + "\n" + note
        yield result["directory"], score_html, abc, chords, progress_html, log_text + "\n" + note


def render_cover(style, lyrics, seed, identifier, abc_text, keep_chords, _transcribe_dir,
                 profile, gpu_device, budget, quantization, offload_ar, vae_core_frames):
    sync_hardware(profile, gpu_device, budget, quantization, offload_ar, vae_core_frames)
    if not abc_text or not abc_text.strip():
        raise gr.Error("没有可用曲谱")
    from .score import inspect_abc as inspect, strip_chords
    view = inspect(abc_text)
    if view.error:
        raise gr.Error("ABC 无法解析: " + view.error)
    if keep_chords:
        abc, cot = abc_text, "full"
    else:
        abc, cot = strip_chords(abc_text), "melody"
        view = inspect(abc)
        if view.error:
            raise gr.Error("去掉和弦后 ABC 无效: " + view.error)
    request = {
        "style": style, "lyrics": lyrics, "cot": cot,
        "seed": int(seed), "id": song_id(identifier or "cover"),
        "abc": abc,
    }
    header = _invocation_header("audio", request)
    for phase, log_text, payload, progress_html in _logged_work(
            header,
            lambda on_status: get_runner().render(
                request, abc_text=abc, plan_dir=None, on_status=on_status)):
        if phase == "running":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            continue
        if phase == "failed":
            yield gr.skip(), gr.skip(), gr.skip(), gr.skip(), progress_html, log_text
            return
        result = payload
        score_html, shown, chords, score_status = _score_outputs(result["abc"] or abc)
        info = (
            f"{log_text}\n"
            f"cot={cot}\n输出: {result['directory']}\n"
            f"{_truncated_text(result['truncated'])}\n{score_status}"
        )
        yield result["audio"], score_html, shown, chords, progress_html, info


def on_abc_edit(abc):
    html, _text, chords, _status = _score_outputs(abc or "")
    return html, chords


def refresh_history():
    return history_table()


def on_history_tab(evt: gr.SelectData):
    if evt.value not in {"history", "历史"}:
        return gr.skip(), gr.skip(), gr.skip()
    return refresh_history()


def select_history(evt: gr.SelectData, paths):
    paths = list(paths or [])
    index = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
    if index is None or not paths or index < 0 or index >= len(paths):
        raise gr.Error("请选择一条记录")
    try:
        entry = load_entry(paths[index])
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc
    score_html, _abc, chords, status = _score_outputs(entry.abc)
    audio = str(entry.audio) if entry.audio else None
    info = f"{entry.directory}\n{status}"
    return (
        str(entry.directory),
        audio,
        score_html,
        chords,
        entry.request.get("style") or "",
        entry.request.get("lyrics") or "",
        info,
    )


def load_history_to_generate(selected, style, lyrics, cot, seed, identifier):
    if not selected:
        raise gr.Error("请先选择一条记录")
    try:
        entry = load_entry(selected)
    except ValueError as exc:
        raise gr.Error(str(exc)) from exc
    request = dict(entry.request)
    abc = entry.abc or ""
    score_html, _abc, chords, _status = _score_outputs(abc)
    plan_dir = str(entry.directory) if entry.has_plan else None
    if request:
        style = request.get("style") or style
        lyrics = request.get("lyrics") or lyrics
        cot = request.get("cot") or cot
        if request.get("seed") is not None:
            seed = int(request["seed"])
        identifier = request.get("id") or entry.identifier or identifier
        request_state = request
    else:
        style = gr.skip()
        lyrics = gr.skip()
        cot = gr.skip()
        seed = gr.skip()
        identifier = gr.skip()
        request_state = gr.skip()
    return (
        gr.update(selected="generate"),
        style, lyrics, cot, seed, identifier,
        abc, plan_dir, request_state, score_html, chords,
    )


def delete_history(selected, confirm):
    if not selected:
        raise gr.Error("请先选择一条记录")
    if not confirm:
        raise gr.Error("请勾选「确认删除本地目录」")
    score_html, _abc, chords, _status = _score_outputs("")
    yield (
        gr.skip(), gr.skip(), gr.skip(), selected, None,
        gr.skip(), gr.skip(), gr.skip(), gr.skip(), "正在删除…", False,
    )
    try:
        delete_entry(selected)
    except OSError as exc:
        yield (
            gr.skip(), gr.skip(), gr.skip(), selected, gr.skip(),
            gr.skip(), gr.skip(), gr.skip(), gr.skip(),
            f"无法删除（文件可能正在播放）: {exc}", False,
        )
        return
    except ValueError as exc:
        yield (
            gr.skip(), gr.skip(), gr.skip(), selected, gr.skip(),
            gr.skip(), gr.skip(), gr.skip(), gr.skip(),
            str(exc), False,
        )
        return
    rows, paths, note = history_table()
    yield (
        rows, paths, note, None, None, score_html, chords, "", "", "已删除。", False,
    )


def build_app():
    defaults = default_request()
    empty_chords = []
    snapshot = refresh_snapshot()
    initial = resolve_profile(PROFILE_AUTO, snapshot)
    get_runner(PipelineSettings(**initial.pipeline_kwargs()))
    gpu_items = device_choices(snapshot)
    default_device = gpu_items[0][1]
    hw_event_out = []

    with gr.Blocks(title="Yue Studio", css=CSS, theme=gr.themes.Base()) as demo:
        gr.HTML(
            '<div class="studio-head">'
            "<h1>Yue Studio</h1>"
            "<p>曲谱 · 和弦 · 翻唱 · 历史 · YuE2 模型与资源</p>"
            "</div>"
        )
        hw_html = gr.HTML(value=hardware_html(snapshot, initial), elem_classes=["hw-bar-wrap"])
        with gr.Row(elem_classes=["hw-controls"]):
            profile = gr.Radio(
                choices=list(PROFILE_CHOICES),
                value=PROFILE_AUTO,
                label="调用预设",
                info="按本机显存选择 YuE2 的 device / budget / quantization",
            )
            gpu_device = gr.Dropdown(
                choices=gpu_items,
                value=default_device,
                label="设备",
                visible=len(snapshot.devices) > 1,
            )
        with gr.Accordion("YuE2 参数", open=True, elem_classes=["hw-params-panel"]):
            with gr.Row():
                budget = gr.Number(
                    value=initial.memory_budget_gib, label="显存预算 GiB",
                    minimum=1, step=0.5, precision=1,
                )
                quantization = gr.Radio(
                    ["none", "fp8"], value=initial.quantization, label="quantization",
                )
                offload_ar = gr.Checkbox(value=initial.offload_ar, label="offload_ar")
                vae_core_frames = gr.Radio(
                    [512, 1024], value=initial.vae_core_frames, label="vae_core_frames",
                )
            hw_notes = gr.Textbox(
                value="\n".join(initial.notes), label="说明", lines=2, interactive=False,
            )
        hw_inputs = [profile, gpu_device, budget, quantization, offload_ar, vae_core_frames]
        init_hist_rows, init_hist_paths, init_hist_note = history_table()
        with gr.Tabs() as studio_tabs:
            with gr.Tab("模型与资源", id="models"):
                env_box = gr.Textbox(label="环境", value=_env_text(), lines=14, elem_id="env-box")
                catalog = gr.Dataframe(headers=CATALOG_HEADERS, value=_catalog_rows(),
                                       wrap=True, interactive=False, label="官方模型与资源")
                with gr.Row():
                    resource = gr.Dropdown([item.name for item in RESOURCES],
                                           value="YuE2-3B", label="下载")
                    download_btn = gr.Button("下载到 models/", variant="primary")
                    refresh_btn = gr.Button("刷新")
                download_progress = gr.HTML(value=_progress_markup(), label="进度",
                                           elem_classes=["job-progress-wrap"])
                download_log = gr.Textbox(label="下载记录", lines=8, elem_classes=["invoke-log"])
                download_btn.click(
                    download_resource, [resource],
                    [catalog, env_box, download_progress, download_log],
                    show_progress="hidden",
                )
                refresh_btn.click(
                    refresh_models, [profile, gpu_device],
                    [catalog, hw_html, budget, quantization, offload_ar, vae_core_frames,
                     hw_notes, env_box],
                )
                hw_event_out.extend(
                    [hw_html, budget, quantization, offload_ar, vae_core_frames, hw_notes, env_box]
                )

            with gr.Tab("生成", id="generate"):
                plan_dir = gr.State(None)
                request_state = gr.State({})
                with gr.Row():
                    style = gr.Textbox(label="style（风格/编制/人声/语种/速度）",
                                       value=defaults["style"], lines=4)
                    lyrics = gr.Textbox(label="lyrics（段落标签与歌词）",
                                        value=defaults["lyrics"], lines=8)
                with gr.Row():
                    cot = gr.Radio(["full", "melody", "off"], value=defaults.get("cot", "full"),
                                   label="cot")
                    seed = gr.Number(value=defaults.get("seed", 831001), precision=0, label="seed")
                    identifier = gr.Textbox(value=defaults.get("id", "song"), label="id")
                extra_abc = gr.Textbox(label="可选外部 ABC（full / melody）", lines=6)
                with gr.Row():
                    plan_btn = gr.Button("规划曲谱", variant="primary")
                    render_btn = gr.Button("合成音频")
                score_html = gr.HTML(value=_score_outputs("")[0], elem_classes=["staff-panel"])
                abc_editor = gr.Textbox(label="曲谱 ABC（可编辑；改谱后合成会作为新输入）",
                                        lines=12, max_lines=30)
                chords = gr.Dataframe(headers=CHORD_HEADERS, value=empty_chords,
                                      label="和弦", wrap=True, interactive=False)
                gen_progress = gr.HTML(value=_progress_markup(), label="进度",
                                       elem_classes=["job-progress-wrap"])
                gen_status = gr.Textbox(label="命令 / 参数 / 日志", lines=16, max_lines=40,
                                        elem_classes=["invoke-log"])
                gen_audio = gr.Audio(label="音频", type="filepath", interactive=False)
                plan_btn.click(
                    plan_song,
                    [style, lyrics, cot, seed, identifier, extra_abc, *hw_inputs],
                    [plan_dir, request_state, score_html, abc_editor, chords,
                     gen_progress, gen_status, gen_audio],
                    show_progress="minimal",
                )
                render_btn.click(
                    render_song,
                    [style, lyrics, cot, seed, identifier, abc_editor, plan_dir, request_state,
                     *hw_inputs],
                    [gen_audio, score_html, abc_editor, chords, gen_progress, gen_status],
                    show_progress="minimal",
                )
                abc_editor.blur(on_abc_edit, [abc_editor], [score_html, chords])

            with gr.Tab("翻唱", id="cover"):
                transcribe_dir = gr.State(None)
                audio_in = gr.Audio(label="源音频", type="filepath", sources=["upload"])
                with gr.Row():
                    abc_file = gr.File(label="或上传 ABC", file_types=[".abc", ".txt"])
                    cover_task = gr.Radio(
                        ["旋律（推荐翻唱）", "完整含和弦"],
                        value="旋律（推荐翻唱）",
                        label="转谱任务",
                    )
                    keep_chords = gr.Checkbox(False, label="保留原和弦（cot=full）")
                cover_abc = gr.Textbox(label="曲谱 ABC", lines=10)
                transcribe_btn = gr.Button("转谱 / 载入 ABC", variant="primary")
                cover_score = gr.HTML(value=_score_outputs("")[0], elem_classes=["staff-panel"])
                cover_chords = gr.Dataframe(headers=CHORD_HEADERS, value=empty_chords,
                                            label="和弦", wrap=True, interactive=False)
                cover_progress = gr.HTML(value=_progress_markup(), label="进度",
                                         elem_classes=["job-progress-wrap"])
                cover_status = gr.Textbox(label="命令 / 参数 / 日志", lines=16, max_lines=40,
                                          elem_classes=["invoke-log"])
                with gr.Row():
                    cover_style = gr.Textbox(label="目标 style", value=defaults["style"], lines=3)
                    cover_lyrics = gr.Textbox(label="目标 lyrics", value=defaults["lyrics"], lines=8)
                with gr.Row():
                    cover_seed = gr.Number(value=defaults.get("seed", 831001), precision=0, label="seed")
                    cover_id = gr.Textbox(value="cover", label="id")
                cover_btn = gr.Button("生成翻唱")
                cover_audio = gr.Audio(label="翻唱音频", type="filepath", interactive=False)
                transcribe_btn.click(
                    transcribe_cover,
                    [audio_in, abc_file, cover_abc, cover_task, *hw_inputs],
                    [transcribe_dir, cover_score, cover_abc, cover_chords, cover_progress, cover_status],
                    show_progress="minimal",
                )
                cover_btn.click(
                    render_cover,
                    [cover_style, cover_lyrics, cover_seed, cover_id, cover_abc, keep_chords,
                     transcribe_dir, *hw_inputs],
                    [cover_audio, cover_score, cover_abc, cover_chords, cover_progress, cover_status],
                    show_progress="minimal",
                )
                cover_abc.blur(on_abc_edit, [cover_abc], [cover_score, cover_chords])

            with gr.Tab("历史", id="history"):
                hist_paths = gr.State(init_hist_paths)
                hist_selected = gr.State(None)
                hist_table = gr.Dataframe(
                    headers=TABLE_HEADERS, value=init_hist_rows, wrap=True,
                    interactive=False, label="点选一行查看并播放",
                )
                hist_note = gr.Textbox(
                    value=init_hist_note, label="状态", lines=2, interactive=False,
                )
                with gr.Row():
                    hist_refresh = gr.Button("刷新")
                    hist_load = gr.Button("载入到生成页", variant="primary")
                    hist_delete = gr.Button("删除")
                    hist_confirm = gr.Checkbox(False, label="确认删除本地目录")
                hist_audio = gr.Audio(label="音频", type="filepath", interactive=False)
                hist_score = gr.HTML(value=_score_outputs("")[0], elem_classes=["staff-panel"])
                hist_chords = gr.Dataframe(
                    headers=CHORD_HEADERS, value=empty_chords,
                    label="和弦", wrap=True, interactive=False,
                )
                with gr.Row():
                    hist_style = gr.Textbox(label="style", lines=3, interactive=False)
                    hist_lyrics = gr.Textbox(label="lyrics", lines=8, interactive=False)
                hist_info = gr.Textbox(label="路径", lines=3, interactive=False)
                hist_refresh.click(
                    refresh_history, None, [hist_table, hist_paths, hist_note],
                )
                hist_table.select(
                    select_history, [hist_paths],
                    [hist_selected, hist_audio, hist_score, hist_chords,
                     hist_style, hist_lyrics, hist_info],
                )
                hist_load.click(
                    load_history_to_generate,
                    [hist_selected, style, lyrics, cot, seed, identifier],
                    [studio_tabs, style, lyrics, cot, seed, identifier,
                     abc_editor, plan_dir, request_state, score_html, chords],
                )
                hist_delete.click(
                    delete_history, [hist_selected, hist_confirm],
                    [hist_table, hist_paths, hist_note, hist_selected, hist_audio,
                     hist_score, hist_chords, hist_style, hist_lyrics, hist_info,
                     hist_confirm],
                    show_progress="minimal",
                )

        studio_tabs.select(
            on_history_tab, None, [hist_table, hist_paths, hist_note],
        )
        profile.change(on_profile, [profile, gpu_device], hw_event_out)
        gpu_device.change(on_profile, [profile, gpu_device], hw_event_out)
        for control in (budget, quantization, offload_ar, vae_core_frames):
            control.change(
                on_params, hw_inputs, [hw_html, hw_notes, env_box],
            )

    return demo


def main(argv=None):
    demo = build_app()
    demo.queue(default_concurrency_limit=1)
    demo.launch(
        server_name="127.0.0.1",
        allowed_paths=[str(studio_root()), str(yue_root()), str(models_dir()), str(outputs_dir())],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

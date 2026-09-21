from pathlib import Path

from yue_studio.models import RESOURCES, _progress_tqdm, environment_report, locate, scan_catalog


def _fake_model(root: Path, name: str, filename="model.safetensors"):
    path = root / name
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / filename).write_bytes(b"x")
    (path / "revision.txt").write_text("abc123", encoding="utf-8")
    return path


def test_catalog_names():
    assert [item.name for item in RESOURCES] == [
        "YuE2-3B", "YuE2-Vae", "YuE2-Vae-legacy", "SheetSage2", "MERT-v2-FullSong",
    ]


def test_locate_prefers_studio_then_yue(tmp_path: Path):
    studio = tmp_path / "studio"
    yue = tmp_path / "yue"
    spec = RESOURCES[0]
    yue_model = _fake_model(yue / "models", spec.local_name)
    from_yue = locate(spec, studio=studio, yue=yue, include_hub=False)
    assert from_yue.present and from_yue.source == "yue"
    assert from_yue.path == yue_model.resolve()
    studio_model = _fake_model(studio, spec.local_name)
    found = locate(spec, studio=studio, yue=yue, include_hub=False)
    assert found.present and found.source == "studio"
    assert found.path == studio_model.resolve()
    assert found.revision == "abc123"


def test_locate_yue_models(tmp_path: Path):
    studio = tmp_path / "studio"
    yue = tmp_path / "yue"
    spec = RESOURCES[1]
    path = _fake_model(yue / "models", spec.local_name)
    found = locate(spec, studio=studio, yue=yue, include_hub=False)
    assert found.present and found.source == "yue"
    assert found.path == path.resolve()


def test_scan_missing(tmp_path: Path):
    rows = scan_catalog(studio=tmp_path / "studio", yue=tmp_path / "yue", include_hub=False)
    assert len(rows) == 5
    assert all(not item.present for item in rows)
    assert rows[0].spec.required is True
    sheetsage = next(item for item in rows if item.spec.name == "SheetSage2")
    assert "自动配置" in sheetsage.note
    mert = next(item for item in rows if item.spec.name == "MERT-v2-FullSong")
    assert "父编码器" in mert.note


def test_locate_rejects_code_only_mert(tmp_path: Path):
    spec = next(item for item in RESOURCES if item.name == "MERT-v2-FullSong")
    studio = tmp_path / "studio"
    path = studio / spec.local_name
    path.mkdir(parents=True)
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / "configuration_mert2.py").write_text("x", encoding="utf-8")
    found = locate(spec, studio=studio, yue=tmp_path / "yue", include_hub=False)
    assert not found.present
    (path / "model.safetensors").write_bytes(b"x")
    found = locate(spec, studio=studio, yue=tmp_path / "yue", include_hub=False)
    assert found.present and found.path == path.resolve()


def test_progress_tqdm_supports_hub_thread_map():
    events = []
    tqdm_class = _progress_tqdm(
        lambda n, total, desc: events.append((n, total, desc)), min_interval=0,
    )
    lock = tqdm_class.get_lock()
    tqdm_class.set_lock(lock)
    from tqdm.contrib.concurrent import thread_map

    result = thread_map(lambda x: x + 1, [1, 2, 3], tqdm_class=tqdm_class, max_workers=2)
    assert result == [2, 3, 4]
    assert events
    assert events[-1][0] == 3


def test_progress_tqdm_aggregates_byte_bars():
    events = []
    cls = _progress_tqdm(lambda n, total, desc: events.append((n, total, desc)), min_interval=0)
    first = cls(total=100, unit="B", desc="a.bin")
    second = cls(total=400, unit="B", desc="b.bin")
    first.update(40)
    second.update(100)
    first.close()
    second.close()
    assert events[-1][0] == 140
    assert events[-1][1] == 500


def test_download_reports_hub_fallback_on_incomplete_snapshot(tmp_path: Path, monkeypatch):
    import logging

    from yue_studio.models import download

    spec = next(item for item in RESOURCES if item.name == "MERT-v2-FullSong")
    dest = tmp_path / spec.local_name
    dest.mkdir()
    (dest / "config.json").write_text("{}", encoding="utf-8")

    def fake_snapshot_download(**kwargs):
        logging.getLogger("huggingface_hub._snapshot_download").warning(
            f"Returning existing local_dir `{dest}` as remote repo cannot be accessed in "
            "`snapshot_download` (ConnectTimeoutError(Connection to hf-mirror.com timed out.))"
        )
        return str(dest)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)
    try:
        download(spec, dest)
    except FileNotFoundError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
    assert "model.safetensors" in message
    assert "cannot be accessed" in message
    assert "timed out" in message


def test_download_hooks_hub_byte_tqdm(tmp_path: Path, monkeypatch):
    from yue_studio.models import download

    spec = RESOURCES[0]
    dest = tmp_path / spec.local_name
    events = []

    def fake_snapshot_download(**kwargs):
        dest.mkdir()
        (dest / "config.json").write_text("{}", encoding="utf-8")
        (dest / "model.safetensors").write_bytes(b"x")
        import importlib
        hooked = importlib.import_module("huggingface_hub.utils.tqdm").tqdm
        assert kwargs["tqdm_class"] is hooked
        bar = hooked(total=80, unit="B", desc="model.safetensors", name="huggingface_hub.http_get")
        bar.update(32)
        bar.close()

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake_snapshot_download)
    download(spec, dest, on_progress=lambda n, total, desc: events.append((n, total, desc)))
    assert events
    assert events[-1][0] == 32
    assert events[-1][1] == 80


def test_environment_report_includes_ffmpeg(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("yue_studio.models.shutil.which", lambda name: r"C:\bin\ffmpeg.exe")
    report = environment_report(SimpleNamespace(
        device="cuda", memory_budget_gib=8, quantization="fp8",
        offload_ar=True, vae_core_frames=512,
    ))
    assert report["ffmpeg"] == r"C:\bin\ffmpeg.exe"

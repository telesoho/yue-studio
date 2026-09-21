import shutil
import subprocess
from pathlib import Path

import pytest

from yue_studio.paths import abc_tools_path, static_dir
from yue_studio.score import inspect_abc, load_abc_tools, score_html, strip_chords

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_score_chords_and_strip():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")
    tools = load_abc_tools()
    abc = (FIXTURES / "score.abc").read_text(encoding="utf-8")
    view = inspect_abc(abc, tools=tools)
    assert view.error is None
    symbols = [row[1] for row in view.chords]
    assert symbols == ["C", "G", "Am", "F", "C", "F", "G", "C"]
    stripped = strip_chords(abc, tools=tools)
    melody = inspect_abc(stripped, tools=tools)
    assert melody.error is None
    assert melody.chords == []


def test_melody_has_no_chords():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")
    abc = (FIXTURES / "melody.abc").read_text(encoding="utf-8")
    view = inspect_abc(abc)
    assert view.error is None
    assert view.chords == []


def test_invalid_abc():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")
    view = inspect_abc("not abc")
    assert view.error
    assert view.chords == []


def test_score_html_embeds_abc():
    html = score_html("X:1\nT:t\nK:C\nC")
    assert "score-frame" in html
    assert "X:1" in html


def test_score_html_embeds_playback():
    html = score_html("X:1\nT:t\nK:C\nC")
    assert 'allow="autoplay"' in html
    assert "播放" in html
    assert "试听曲谱" in html
    assert "setUpAudio" in html
    assert "AudioContext" in html
    assert "TimingCallbacks" in html


def test_score_html_embeds_jianpu_bridge():
    # The iframe must load abc2svg via the Gradio file API. The path must
    # be relative to CWD with the static/ prefix so it matches Gradio's
    # allowed_paths check — not absolute, and not bare "abc2svg/...".
    html = score_html("X:1\nT:t\nK:C\nCDEF")
    assert "abc2svg-1.js" in html
    assert "static/abc2svg/abc2svg-1.js" in html, (
        "abc2svg script src must include the static/ prefix; "
        "Gradio resolves /gradio_api/file=... relative to CWD"
    )
    assert "static/abc2svg/jianpu-1.js" in html, (
        "jianpu is a separate abc2svg module; the iframe must load jianpu-1.js"
    )
    assert "abc2svg.Abc" in html
    assert "%%jianpu true" in html
    assert "V:1\\n%%jianpu true" not in html, (
        "YuE voices are named Vocal/Ins; a dummy V:1 gets no notes and crashes jianpu"
    )
    assert r"replace(/^(V:.*)$/gm" in html, (
        "%%jianpu must be applied to every V: line, not a synthetic V:1"
    )
    assert "五线谱" in html and "简谱" in html


def test_jianpu_module_is_vendored():
    path = static_dir() / "abc2svg" / "jianpu-1.js"
    assert path.is_file(), f"missing {path}; abc2svg core does not include jianpu"
    text = path.read_text(encoding="utf-8")
    assert "abc2svg.jianpu" in text
    assert "modules.hooks.push" in text
    assert "mark_rest" in text, "Z/Z4 (MREST) must be numbered or the SVG prints undefined"
    assert "jp_hide_hl" in text, (
        "full-measure rests must skip the Western ledger that sits on 0"
    )
    assert "short_nm" in text and "唱" in text and "伴" in text, (
        "YuE Vocal/Ins labels should collapse to 唱/伴 on the jianpu staff"
    )


def test_jianpu_svg_is_numbered_notation():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to render abc2svg jianpu SVG")
    script = Path(__file__).resolve().parent / "jianpu_render.js"
    result = subprocess.run(
        [node, str(script)], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

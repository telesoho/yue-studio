from pathlib import Path

import pytest

from yue_studio.paths import abc_tools_path
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

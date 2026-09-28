import json
import shutil
import subprocess
from pathlib import Path

import pytest

from yue_studio.paths import abc_tools_path
from yue_studio.score_edit import commit_edited_abc, strip_w_lines, write_edited_score

DISPLAY = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
"C"C4D4E4F4|G4A4B4c4|
w: 春 眠 不 觉 晓 处 处 闻
V: Ins
Z2|
"""

SHORT = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
C4D4E4|
V: Ins
Z|
"""

TINY = """X:1
T:
M:4/4
L:1/4
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
CCCC|
V: Ins
Z|
"""

RESTING = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
C4z4D4E4|
V: Ins
Z|
"""


def _need_tools():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")


def _node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to edit jianpu")
    return node


def _edit(abc, **command):
    payload = dict(command)
    payload["abc"] = abc
    result = subprocess.run(
        [_node(), str(Path(__file__).resolve().parent / "score_edit_render.js"), "--edit"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_set_degree_octave_and_accidental():
    degree = _edit(DISPLAY, op="degree", index=0, degree=2)
    assert degree["error"] is None
    assert '"C"D4D4E4F4|' in degree["abc"]
    assert "Z2|" in degree["abc"]
    assert "w: 春 眠 不 觉 晓 处 处 闻" in degree["abc"]

    up = _edit(DISPLAY, op="octave", index=0, delta=1)
    assert up["error"] is None
    assert '"C"c4D4E4F4|' in up["abc"]
    down = _edit(DISPLAY, op="octave", index=0, delta=-1)
    assert down["error"] is None
    assert '"C"C,4D4E4F4|' in down["abc"]

    sharp = _edit(DISPLAY, op="accidental", index=0, kind="sharp")
    assert sharp["error"] is None
    assert '"C"^C4D4E4F4|' in sharp["abc"]
    again = _edit(sharp["abc"], op="accidental", index=0, kind="sharp")
    assert again["error"] is None
    assert '"C"C4D4E4F4|' in again["abc"]


def test_duration_insert_delete_and_lyric():
    halved = _edit(DISPLAY, op="duration", index=0, factor=0.5)
    assert halved["error"] is None
    assert '"C"C2z2D4E4F4|' in halved["abc"]
    assert "w: 春 眠 不 觉 晓 处 处 闻" in halved["abc"]

    blocked = _edit(DISPLAY, op="duration", index=0, factor=2)
    assert blocked["error"]
    assert blocked["abc"] == DISPLAY
    dotted = _edit(DISPLAY, op="duration", index=0, factor=1.5)
    assert dotted["error"]
    assert dotted["abc"] == DISPLAY

    doubled = _edit(RESTING, op="duration", index=0, factor=2)
    assert doubled["error"] is None
    assert "C8D4E4|" in doubled["abc"]
    dotted_rest = _edit(RESTING, op="duration", index=0, factor=1.5)
    assert dotted_rest["error"] is None
    assert "C6z2D4E4|" in dotted_rest["abc"]

    tiny = _edit(TINY, op="duration", index=0, factor=0.5)
    assert tiny["error"] == "这个时值写不进曲谱"
    assert tiny["abc"] == TINY

    inserted = _edit(DISPLAY, op="insert", index=0)
    assert inserted["error"] is None
    assert '"C"C2C2D4E4F4|' in inserted["abc"]
    assert "Z2|" in inserted["abc"]
    assert "w: 春 * 眠 不 觉 晓 处 处 闻" in inserted["abc"]

    filled = _edit(SHORT, op="insert", index=2)
    assert filled["error"] is None
    assert "C4D4E4C4|" in filled["abc"]

    deleted = _edit(DISPLAY, op="delete", index=1)
    assert deleted["error"] is None
    assert '"C"C4z4E4F4|' in deleted["abc"]
    assert "w: 春 不 觉 晓 处 处 闻" in deleted["abc"]
    assert "Z2|" in deleted["abc"]

    lyric = _edit(DISPLAY, op="lyric", index=0, text="山")
    assert lyric["error"] is None
    assert "w: 山 眠 不 觉 晓 处 处 闻" in lyric["abc"]
    assert '"C"C4D4E4F4|' in lyric["abc"]


def test_tie_same_pitch_and_extend_syllable():
    same = DISPLAY.replace('"C"C4D4E4F4|', '"C"C4C4E4F4|', 1)
    tied = _edit(same, op="tie", index=0)
    assert tied["error"] is None
    assert '"C"C4-C4E4F4|' in tied["abc"]
    assert "w: 春 眠 不 觉 晓 处 处 闻" in tied["abc"]
    assert "Z2|" in tied["abc"]
    off = _edit(tied["abc"], op="tie", index=0)
    assert off["error"] is None
    assert '"C"C4C4E4F4|' in off["abc"]
    assert "C4-C4" not in off["abc"]

    mismatch = _edit(DISPLAY, op="tie", index=0)
    assert mismatch["error"] == "连音要接在后面同样的音上"
    assert mismatch["abc"] == DISPLAY
    rest = _edit(RESTING, op="tie", index=1)
    assert rest["error"] == "休止不能连音"

    lyric_rest = RESTING.replace(
        "C4z4D4E4|\n",
        "C4z4D4E4|\nw: 春 * 眠 晓\n",
    )
    held = _edit(lyric_rest, op="sustain", index=0)
    assert held["error"] is None
    assert "C8D4E4|" in held["abc"]
    assert "w: 春 眠 晓" in held["abc"]
    assert "Z|" in held["abc"]

    blocked = _edit(DISPLAY, op="sustain", index=0)
    assert blocked["error"] == "后面没有可以让出来的休止"
    assert blocked["abc"] == DISPLAY


def test_commit_strips_w_lines_and_rebuilds_lyrics():
    _need_tools()
    edited = _edit(DISPLAY, op="lyric", index=0, text="山")
    committed = commit_edited_abc(edited["abc"])
    assert committed.error is None
    assert "w:" not in committed.clean
    assert '"C"C4D4E4F4|' in committed.clean
    assert "Z2|" in committed.clean
    assert committed.lyrics == "[Verse]\n山眠不觉晓处处闻"
    assert "w: 山 眠 不 觉 晓 处 处 闻" in committed.display


def test_commit_rejects_illegal_score_and_writes_job_files(tmp_path):
    _need_tools()
    rejected = commit_edited_abc("not abc")
    assert rejected.error
    assert "w:" not in strip_w_lines(DISPLAY)

    halved = _edit(DISPLAY, op="duration", index=0, factor=0.5)
    committed = commit_edited_abc(halved["abc"])
    assert committed.error is None
    assert "C2z2" in committed.clean

    (tmp_path / "alignment.json").write_text(
        json.dumps({"language": "zh", "lyrics": "old", "display_abc": "old"}, ensure_ascii=False),
        encoding="utf-8",
    )
    write_edited_score(tmp_path, committed)
    assert "w:" not in (tmp_path / "score.abc").read_text(encoding="utf-8")
    assert "C2z2" in (tmp_path / "score.abc").read_text(encoding="utf-8")
    saved = json.loads((tmp_path / "alignment.json").read_text(encoding="utf-8"))
    assert saved["language"] == "zh"
    assert saved["lyrics"] == committed.lyrics
    assert "w:" in saved["display_abc"]
    assert (tmp_path / "lyrics.txt").read_text(encoding="utf-8") == committed.lyrics


def test_jianpu_edit_script_renders_heads():
    result = subprocess.run(
        [_node(), str(Path(__file__).resolve().parent / "score_edit_render.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_editor_head_loads_score_script_only():
    from yue_studio.score_edit import EDITOR_HEAD

    assert "score_edit.js" in EDITOR_HEAD
    assert "abc2svg-1.js" not in EDITOR_HEAD
    assert "jianpu-1.js" not in EDITOR_HEAD


def test_editor_button_reads_abc_from_the_browser():
    import inspect

    from yue_studio.app import build_app

    demo = build_app()
    editor_fns = [
        fn for fn in demo.fns.values()
        if isinstance(getattr(fn, "js", None), str) and "yueScoreEditor" in fn.js
    ]
    assert len(editor_fns) == 2
    for fn in editor_fns:
        for block in fn.inputs[:3]:
            assert block.stateful is False
        assert len(fn.inputs) == 5
        assert type(fn.inputs[4]).__name__ == "Audio"
        params = list(inspect.signature(fn.fn).parameters)
        assert params[:4] == ["edited", "previous", "_clean", "job"]
        assert params[4] == "_audio"
        assert "open(source, audio)" in fn.js
        assert fn.js.count("job, audio]") == 4


def test_apply_score_edit_skips_when_unchanged_and_requires_a_score():
    from yue_studio.app import apply_score_edit

    import gradio as gr

    skipped = apply_score_edit(DISPLAY, DISPLAY, DISPLAY, None)
    assert skipped == (gr.skip(),) * 6
    with pytest.raises(gr.Error):
        apply_score_edit("", "", "", None)


def test_history_transcribe_can_edit_jianpu(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import gradio as gr

    from yue_studio.app import apply_history_edit, select_history

    monkeypatch.setattr("yue_studio.history.outputs_dir", lambda: tmp_path)
    clean = strip_w_lines(DISPLAY)
    transcribe = tmp_path / "transcribe-20260920-215000-cover"
    transcribe.mkdir()
    (transcribe / "score.abc").write_text(clean, encoding="utf-8")
    (transcribe / "alignment.json").write_text(
        json.dumps({"display_abc": DISPLAY, "language": "zh"}, ensure_ascii=False),
        encoding="utf-8",
    )
    song = tmp_path / "song-20260920-233150-city"
    song.mkdir()
    (song / "audio.flac").write_bytes(b"fLaC")
    (song / "score.abc").write_text(clean, encoding="utf-8")

    picked = select_history(SimpleNamespace(index=(0,)), [str(transcribe)])
    assert picked[7] == clean
    assert "w: 春" in picked[8]
    assert picked[9]["visible"] is True
    song_pick = select_history(SimpleNamespace(index=(0,)), [str(song)])
    assert song_pick[9]["visible"] is False

    edited = DISPLAY.replace("春", "山", 1)
    shown, _chords, lyrics, saved_clean, saved_display = apply_history_edit(
        edited, DISPLAY, clean, str(transcribe),
    )
    assert "山" in lyrics
    assert "w:" not in saved_clean
    assert "w: 山" in saved_display
    assert shown
    assert "w:" not in (transcribe / "score.abc").read_text(encoding="utf-8")
    assert "山" in (transcribe / "lyrics.txt").read_text(encoding="utf-8")
    payload = json.loads((transcribe / "alignment.json").read_text(encoding="utf-8"))
    assert payload["language"] == "zh"
    assert "w: 山" in payload["display_abc"]

    with pytest.raises(gr.Error, match="只有转谱"):
        apply_history_edit(edited, DISPLAY, clean, str(song))
    with pytest.raises(gr.Error, match="请先在历史里选择一条转谱"):
        apply_history_edit("", "", "", None)


LONG_REST = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
V: Vocal
z16C8|
V: Ins
C4D4E4F4|
"""

LYRIC_REST = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
V: Vocal
C4z16D4|
w: 春 * 晓
V: Ins
C4|
"""


def test_one_rest_glyph_and_accompaniment_note():
    third = _edit(LONG_REST, op="degree", index=0, slice=2, degree=5)
    assert third["error"] is None
    assert "z4z4G4z4C8|" in third["abc"]
    assert "C4D4E4F4|" in third["abc"]

    lyric = _edit(LYRIC_REST, op="degree", index=1, slice=1, degree=3)
    assert lyric["error"] is None
    assert "C4z4E4z4z4D4|" in lyric["abc"]
    assert "w: 春 * 晓" in lyric["abc"]

    ins = _edit(LONG_REST, op="degree", index=0, voice="Ins", slice=0, degree=2)
    assert ins["error"] is None
    assert "D4D4E4F4|" in ins["abc"]
    assert "z16C8|" in ins["abc"]
    assert "w:" not in ins["abc"]


def test_commit_keeps_an_accompaniment_edit():
    _need_tools()
    both = DISPLAY.replace("Z2|", "C4D4E4F4|G4A4B4c4|")
    ins = _edit(both, op="octave", index=0, voice="Ins", slice=0, delta=1)
    assert ins["error"] is None
    assert "c4D4E4F4|" in ins["abc"]
    assert '"C"C4D4E4F4|' in ins["abc"]
    committed = commit_edited_abc(ins["abc"])
    assert committed.error is None
    assert "c4D4E4F4|" in committed.clean
    assert "w:" not in committed.clean
    assert committed.lyrics == "[Verse]\n春眠不觉晓处处闻"


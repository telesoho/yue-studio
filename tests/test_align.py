import pytest

from yue_studio.align import align_lyrics
from yue_studio.paths import abc_tools_path

VERSE = """X:1
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
V: Ins
Z2|
"""

TIED = """X:1
T:
M:4/4
L:1/16
Q:1/4=120
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Vocal
C4-C4D4E4|
V: Ins
Z|
"""


def _need_tools():
    if not abc_tools_path().is_file():
        pytest.skip("YuE abc_tools.py is not available")


def test_chinese_syllables_align_without_writing_w_into_source():
    _need_tools()
    words = [{"text": "春眠不觉晓处处闻", "start": 0.0, "end": 4.0}]
    result = align_lyrics(VERSE, words)
    assert "w:" not in VERSE
    assert result.lyrics == "[Verse]\n春眠不觉晓处处闻"
    assert "w: 春 眠 不 觉 晓 处 处 闻" in result.display_abc
    assert "w:" not in result.lyrics
    assert result.notes[0]["syllable"] == "春"
    assert result.notes[0]["midi_pitch"] == 60
    assert result.notes[-1]["syllable"] == "闻"
    assert result.unassigned == []


def test_english_word_spans_later_notes_with_melisma():
    _need_tools()
    words = [{"text": "love", "start": 0.0, "end": 1.5}]
    result = align_lyrics(TIED, words)
    assert "w: love - - *" in result.display_abc
    assert result.lyrics == "[Verse]\nlove"
    assert "w:" not in TIED


def test_unparsed_abc_keeps_transcript_without_w_lines():
    result = align_lyrics("not abc", [{"text": "春", "start": 0.0, "end": 1.0}])
    assert result.lyrics == "春"
    assert result.display_abc == "not abc"
    assert result.warnings

import array
import struct
import wave
from pathlib import Path

import pytest

from yue_studio.capture import (
    MIN_SECONDS,
    CaptureError,
    SessionInfo,
    WindowInfo,
    assess_pcm16,
    capture_targets,
    floats_to_pcm16,
    pcm_from_mix,
    require_usable,
    target_pid,
    write_pcm16_wav,
)


def test_window_label_uses_the_session_process():
    targets = capture_targets(
        [SessionInfo(7, "cloudmusic.exe", "")],
        [WindowInfo(1, 7, "晴天")],
        {7: None},
    )
    assert len(targets) == 1
    assert targets[0].pid == 7
    assert targets[0].label == "晴天 — cloudmusic.exe"
    assert targets[0].value == "7"
    assert target_pid(targets[0].value) == 7


def test_parent_window_is_only_a_label():
    targets = capture_targets(
        [SessionInfo(10, "chrome.exe")],
        [WindowInfo(3, 4, "YouTube")],
        {10: 7, 7: 4, 4: 1},
    )
    assert len(targets) == 1
    assert targets[0].pid == 10
    assert targets[0].label == "YouTube — chrome.exe (10)"
    assert target_pid(targets[0].value) == 10


def test_session_window_wins_over_parent():
    targets = capture_targets(
        [SessionInfo(10, "app.exe")],
        [WindowInfo(1, 5, "Parent"), WindowInfo(2, 10, "Child")],
        {10: 5},
    )
    assert len(targets) == 1
    assert "Child" in targets[0].label
    assert "Parent" not in targets[0].label
    assert targets[0].pid == 10


def test_each_window_of_one_process_is_a_row():
    targets = capture_targets(
        [SessionInfo(7, "cloudmusic.exe"), SessionInfo(7, "cloudmusic.exe", "重复")],
        [WindowInfo(1, 7, "歌一"), WindowInfo(2, 7, "歌二"), WindowInfo(3, 7, "  ")],
        {7: None},
    )
    assert [item.label for item in targets] == [
        "歌一 — cloudmusic.exe",
        "歌二 — cloudmusic.exe",
    ]
    assert {target_pid(item.value) for item in targets} == {7}
    assert len({item.value for item in targets}) == 2


def test_session_without_a_window_is_still_listed():
    targets = capture_targets(
        [SessionInfo(4, "cloudmusic.exe")],
        [],
        {4: None},
    )
    assert targets[0].pid == 4
    assert targets[0].label == "cloudmusic.exe (4)"
    assert target_pid("4") == 4


def test_target_pid_rejects_a_blank_choice():
    with pytest.raises(CaptureError):
        target_pid("")
    with pytest.raises(CaptureError):
        target_pid("window")


def test_float_samples_become_a_pcm16_wav(tmp_path: Path):
    pcm = floats_to_pcm16([0.0, 1.0, -1.0, 0.5])
    samples = array.array("h")
    samples.frombytes(pcm)
    assert list(samples) == [0, 32767, -32767, 16384]
    path = tmp_path / "tone.wav"
    write_pcm16_wav(path, 48000, 1, pcm)
    with wave.open(str(path)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getframerate() == 48000
        assert handle.getsampwidth() == 2
        assert handle.readframes(4) == pcm


def test_mix_float_converts_and_silence_is_flagged():
    pcm = pcm_from_mix(struct.pack("<fff", 0.0, 1.0, -1.0), 3, 32, 1)
    assert pcm == floats_to_pcm16([0.0, 1.0, -1.0])
    duration, peak, silent = assess_pcm16(48000, 1, floats_to_pcm16([0.0] * 48000))
    assert duration == 1
    assert peak == 0
    assert silent
    require_usable(duration, 48000)
    _duration, _peak, loud = assess_pcm16(48000, 1, floats_to_pcm16([0.5]))
    assert not loud


def test_short_capture_is_refused():
    duration, _peak, _silent = assess_pcm16(48000, 1, floats_to_pcm16([0.2] * 100))
    assert duration < MIN_SECONDS
    with pytest.raises(CaptureError, match="录音太短"):
        require_usable(duration, 100)
    with pytest.raises(CaptureError, match="录音太短"):
        require_usable(0.0, 0)

"""Align timestamped lyric syllables to native Vocal notes.

The saved score stays free of ``w:`` lines. A display copy may add them for the
staff view only.
"""
from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

TOKEN = re.compile(
    r'"(?P<chord>[^"\n]*)"|\[K:(?P<key>[^\]\n]+)\]|'
    r"(?P<acc>\^\^|__|\^|_|=)?(?P<note>[A-Ga-gz])"
    r"(?P<oct>[,']*)(?P<duration>[0-9]*)(?P<tie>-?)"
)
_PUNCT = ".,!?;:，。！？；：、…—-\"'()[]"
SECTION_TAGS = {
    "verse": "Verse",
    "chorus": "Chorus",
    "bridge": "Bridge",
    "intro": "Intro",
    "outro": "Outro",
    "interlude": "Interlude",
    "pre-chorus": "Pre-Chorus",
    "prechorus": "Pre-Chorus",
}


@dataclass(frozen=True)
class LyricAlignment:
    lyrics: str
    display_abc: str
    notes: list
    unassigned: list
    warnings: list = field(default_factory=list)
    bpm: int | None = None


def align_lyrics(abc: str, words: list[dict], *, tools=None) -> LyricAlignment:
    parsed = _parse(abc, tools)
    if parsed is None:
        syllables = syllables_from_words(words or [])
        lyrics = join_syllables([item["text"] for item in syllables])
        return LyricAlignment(
            lyrics, abc or "", [], [{"text": item["text"], "start": item["start"], "end": item["end"]}
                                    for item in syllables],
            ["曲谱无法解析，歌词未对齐到音符"], None,
        )
    score, vocal = parsed
    bpm = int(score.bpm)
    notes = _sounding_notes(vocal, bpm)
    groups = vocal_groups(abc)
    spans = _section_spans(groups, vocal.bars, bpm)
    _tag_notes(notes, spans)
    timing = lyric_groups(words or [])
    scale, offset = fit_lyric_timing(notes, timing)
    slots, unassigned = place_lyric_groups(notes, timing, scale, offset)
    for note, slot in zip(notes, slots):
        note["syllable"] = slot
    warnings = []
    if scale != 1 or offset != 0:
        warnings.append(f"歌词时间已按倍率 {scale:.2f}、偏移 {offset:+.2f}s 对齐")
    if unassigned:
        warnings.append(f"有 {len(unassigned)} 个字未能对上旋律音符")
    positioned = _positions_for_groups(groups)
    display = abc
    line_slots = None
    if positioned is not None and sum(item[1] for item in positioned) == len(notes):
        display, line_slots = _display_abc(abc, groups, positioned, slots)
    elif groups and notes:
        warnings.append("旋律音符无法逐行切分，谱面不标注歌词")
    lyrics = _lyrics_text(groups, spans, slots, line_slots, unassigned, notes)
    return LyricAlignment(lyrics, display, notes, unassigned, warnings, bpm)


def write_lyric_files(directory: Path, alignment: LyricAlignment, *, language: str,
                      warnings: list | None = None) -> None:
    directory = Path(directory)
    payload = {
        "language": language,
        "bpm": alignment.bpm,
        "warnings": list(alignment.warnings if warnings is None else warnings),
        "lyrics": alignment.lyrics,
        "display_abc": alignment.display_abc,
        "notes": alignment.notes,
        "unassigned": alignment.unassigned,
    }
    (directory / "alignment.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n",
    )
    (directory / "lyrics.txt").write_text(alignment.lyrics, encoding="utf-8", newline="\n")


def syllables_from_words(words: list[dict]) -> list[dict]:
    syllables = []
    for word in words:
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        pieces = _split_word(text)
        if not pieces:
            continue
        span = (end - start) / len(pieces)
        for index, piece in enumerate(pieces):
            syllables.append({
                "text": piece,
                "start": start + index * span,
                "end": start + (index + 1) * span,
            })
    return syllables


def lyric_groups(words: list[dict]) -> list[dict]:
    """One Whisper token keeps a shared time span for every syllable it contains."""
    groups = []
    for order, word in enumerate(words or []):
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        try:
            start = float(word["start"])
            end = float(word["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        pieces = _split_word(text)
        if not pieces:
            continue
        groups.append({"start": start, "end": end, "texts": pieces, "order": order})
    groups.sort(key=lambda item: (item["start"], item["end"], item["order"]))
    return groups


_ONSET_WINDOW = 0.2
_MIN_OVERLAP = 0.35


def fit_lyric_timing(notes: list[dict], groups: list[dict]) -> tuple[float, float]:
    """Map audio time onto score time: ``score = scale * audio + offset``.

    Word onsets are matched to note onsets. Near-ties prefer the smaller
    offset, then the scale closer to 1, so a beat-grid shift does not win.
    """
    onsets = sorted(float(note["start"]) for note in notes)
    if not onsets or not groups:
        return 1.0, 0.0
    best_score = -1.0
    near: list[tuple[float, float, float, float]] = []
    for scale_i in range(90, 111):
        scale = scale_i / 100
        for offset_i in range(-20, 21):
            offset = offset_i / 20
            score = _onset_score(onsets, groups, scale, offset)
            if score > best_score + 1e-9:
                best_score = score
                near = [(abs(offset), abs(scale - 1), scale, offset)]
            elif score >= best_score - 1e-9:
                near.append((abs(offset), abs(scale - 1), scale, offset))
    _abs_offset, _abs_scale, scale, offset = min(near)
    return scale, offset


def place_lyric_groups(notes: list[dict], groups: list[dict], scale: float,
                       offset: float) -> tuple[list[str], list[dict]]:
    """Assign each group's syllables in order. The note cursor only moves forward."""
    slots = [""] * len(notes)
    unassigned = []
    cursor = 0
    ordered = sorted(groups, key=lambda item: (item["start"], item["end"], item.get("order", 0)))
    for group in ordered:
        start = scale * float(group["start"]) + offset
        end = scale * float(group["end"]) + offset
        texts = list(group["texts"])
        candidates = _overlap_candidates(notes, cursor, start, end)
        if not candidates or not texts:
            unassigned.extend(_unassigned_texts(group, texts))
            continue
        count = min(len(texts), len(candidates))
        ranked = sorted(candidates, key=lambda item: (-item[1], -item[2], item[0]))
        picked = [item[0] for item in sorted(ranked[:count], key=lambda item: item[0])]
        for text, index in zip(texts, picked):
            slots[index] = text
        if len(texts) > len(picked):
            last = picked[-1]
            slots[last] = join_syllables([slots[last], *texts[len(picked):]])
        chosen = set(picked)
        first, last = picked[0], picked[-1]
        consumed = last
        for index, _overlap, _duration in candidates:
            if index in chosen:
                continue
            if first < index < last or index > last:
                if slots[index] == "":
                    slots[index] = "-"
                if index > consumed:
                    consumed = index
        cursor = consumed + 1
    return slots, unassigned


def _onset_score(onsets: list[float], groups: list[dict], scale: float, offset: float) -> float:
    total = 0.0
    for group in groups:
        moment = scale * float(group["start"]) + offset
        index = bisect.bisect_left(onsets, moment)
        distance = _ONSET_WINDOW
        if index < len(onsets):
            distance = min(distance, onsets[index] - moment)
        if index > 0:
            distance = min(distance, moment - onsets[index - 1])
        if distance < _ONSET_WINDOW:
            total += 1.0 - distance / _ONSET_WINDOW
    return total


def _overlap_candidates(notes: list[dict], cursor: int, start: float, end: float) -> list[tuple[int, float, float]]:
    found = []
    for index in range(cursor, len(notes)):
        note = notes[index]
        duration = float(note["end"]) - float(note["start"])
        if duration <= 0:
            continue
        overlap = min(float(note["end"]), end) - max(float(note["start"]), start)
        if overlap < _MIN_OVERLAP * duration:
            continue
        found.append((index, overlap, duration))
    return found


def _unassigned_texts(group: dict, texts: list[str]) -> list[dict]:
    return [
        {"text": text, "start": group["start"], "end": group["end"]}
        for text in texts
    ]


def join_syllables(parts: list[str]) -> str:
    text = ""
    for part in parts:
        if not part or part == "-":
            continue
        if not text:
            text = part
            continue
        if _is_cjk(text[-1]) and _is_cjk(part[0]):
            text += part
        else:
            text += " " + part
    return text


def vocal_groups(abc: str) -> list[dict]:
    lines = (abc or "").splitlines()
    groups = []
    section = "section"
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("% "):
            section = line[2:].strip() or "section"
            index += 1
            continue
        if line == "V: Vocal":
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].startswith(("M:", "K:")):
                cursor += 1
            if cursor < len(lines):
                groups.append({
                    "section": section,
                    "tag": section_tag(section),
                    "index": cursor,
                    "music": lines[cursor],
                })
            index = cursor
        index += 1
    return groups


def section_tag(name: str) -> str:
    key = (name or "").strip().lower()
    if key in SECTION_TAGS:
        return SECTION_TAGS[key]
    if not key or key == "section":
        return "Section"
    return key[:1].upper() + key[1:]


def _parse(abc: str, tools):
    if not (abc or "").strip():
        return None
    try:
        if tools is None:
            from .score import load_abc_tools
            tools = load_abc_tools()
        score = tools.parse_abc(abc)
    except Exception:
        return None
    vocal = score.voices.get("Vocal") if getattr(score, "voices", None) else None
    if vocal is None or not getattr(score, "bpm", None):
        return None
    return score, vocal


def _sounding_notes(vocal, bpm: int) -> list[dict]:
    notes = []
    for onset, pitch, duration in vocal.notes:
        start = Fraction(onset)
        length = Fraction(duration)
        notes.append({
            "onset_quarters": str(start),
            "duration_quarters": str(length),
            "onset_seconds": float(start * 60 / bpm),
            "midi_pitch": int(pitch),
            "start": float(start * 60 / bpm),
            "end": float((start + length) * 60 / bpm),
            "syllable": "",
            "section": "Section",
        })
    return notes


def _section_spans(groups: list[dict], bars, bpm: int) -> list[dict]:
    spans = []
    cursor = 0
    for group in groups:
        count = _bar_count(group["music"])
        if count is None:
            return []
        chunk = list(bars)[cursor:cursor + count]
        cursor += count
        if not chunk:
            continue
        start = Fraction(chunk[0][0])
        end = Fraction(chunk[-1][0]) + Fraction(chunk[-1][1])
        spans.append({
            "tag": group["tag"],
            "index": group["index"],
            "start": float(start * 60 / bpm),
            "end": float(end * 60 / bpm),
        })
    if cursor != len(list(bars)):
        return []
    return spans


def _tag_notes(notes: list[dict], spans: list[dict]) -> None:
    if not spans:
        return
    for note in notes:
        chosen = spans[-1]["tag"]
        for span in spans:
            if span["start"] <= note["start"] < span["end"]:
                chosen = span["tag"]
                break
        note["section"] = chosen


def _bar_count(line: str) -> int | None:
    if not line.endswith("|"):
        return None
    count = 0
    for bar in line[:-1].split("|"):
        bar = bar.strip()
        if not bar:
            return None
        match = re.fullmatch(r"Z([2-4])?", bar)
        count += int(match.group(1) or "1") if match else 1
    return count


def _positions_for_groups(groups: list[dict]) -> list[tuple[int, int, list[str]]] | None:
    pending = False
    positioned = []
    for group in groups:
        positions, pending = _lyric_positions(group["music"], pending)
        if positions is None:
            return None
        note_count = sum(kind == "note" for kind in positions)
        positioned.append((group["index"], note_count, positions))
    if pending:
        return None
    return positioned


def _lyric_positions(line: str, pending_tie: bool) -> tuple[list[str] | None, bool]:
    if not line.endswith("|"):
        return None, pending_tie
    positions = []
    for bar in line[:-1].split("|"):
        bar = bar.strip()
        if not bar:
            return None, pending_tie
        if re.fullmatch(r"Z([2-4])?", bar):
            if pending_tie:
                return None, pending_tie
            continue
        cursor = 0
        while cursor < len(bar):
            if bar[cursor].isspace():
                cursor += 1
                continue
            match = TOKEN.match(bar, cursor)
            if match is None:
                return None, pending_tie
            cursor = match.end()
            if match.group("chord") is not None or match.group("key") is not None:
                continue
            if match.group("note") == "z":
                if pending_tie:
                    return None, pending_tie
                continue
            positions.append("tie" if pending_tie else "note")
            pending_tie = bool(match.group("tie"))
    return positions, pending_tie


def _display_abc(abc: str, groups, positioned, slots: list[str]) -> tuple[str, list[list[str]]]:
    by_index = {}
    line_slots = []
    cursor = 0
    for group, (index, count, positions) in zip(groups, positioned):
        chunk = slots[cursor:cursor + count]
        cursor += count
        line_slots.append(chunk)
        lyric = _render_w(positions, chunk)
        if lyric and index == group["index"]:
            by_index[index] = lyric
    lines = abc.splitlines()
    rendered = []
    for index, line in enumerate(lines):
        rendered.append(line)
        if index in by_index:
            rendered.append(by_index[index])
    text = "\n".join(rendered)
    if abc.endswith("\n"):
        text += "\n"
    return text, line_slots


def _render_w(positions: list[str], slots: list[str]) -> str | None:
    tokens = []
    index = 0
    for kind in positions:
        if kind == "note":
            tokens.append(_w_token(slots[index] if index < len(slots) else ""))
            index += 1
        else:
            previous = tokens[-1] if tokens else "*"
            tokens.append("-" if previous not in {"*", "-"} else "*")
    if not any(token not in {"*", "-"} for token in tokens):
        return None
    return "w: " + " ".join(tokens)


def _w_token(text: str) -> str:
    if not text or text == "*":
        return "*"
    if text == "-":
        return "-"
    cleaned = text.replace("|", "").replace(" ", "~").strip()
    return cleaned or "*"


def _lyrics_text(groups, spans, slots, line_slots, unassigned, notes) -> str:
    blocks: list[dict] = []

    def block_for(tag: str) -> dict:
        if blocks and blocks[-1]["tag"] == tag:
            return blocks[-1]
        item = {"tag": tag, "lines": []}
        blocks.append(item)
        return item

    if line_slots is not None:
        for group, chunk in zip(groups, line_slots):
            text = join_syllables(chunk)
            if text:
                block_for(group["tag"])["lines"].append(text)
    else:
        current_tag = None
        bucket: list[str] = []

        def flush():
            nonlocal bucket
            if bucket and current_tag:
                block_for(current_tag)["lines"].append(join_syllables(bucket))
            bucket = []

        for note in notes:
            tag = note.get("section") or "Section"
            if current_tag is None:
                current_tag = tag
            if tag != current_tag:
                flush()
                current_tag = tag
            if note.get("syllable") and note["syllable"] != "-":
                bucket.append(note["syllable"])
        flush()

    for item in unassigned:
        tag = _span_tag(spans, item["start"]) or (blocks[-1]["tag"] if blocks else "Section")
        block_for(tag)["lines"].append(item["text"])
    parts = []
    for block in blocks:
        body = "\n".join(line for line in block["lines"] if line)
        if body:
            parts.append(f"[{block['tag']}]\n{body}")
    return "\n\n".join(parts)


def _span_tag(spans, start: float) -> str | None:
    for span in spans:
        if span["start"] <= start < span["end"]:
            return span["tag"]
    if spans and start >= spans[-1]["end"]:
        return spans[-1]["tag"]
    return spans[0]["tag"] if spans else None


def _split_word(text: str) -> list[str]:
    pieces = []
    latin = ""
    for char in text:
        if char.isspace() or char in _PUNCT:
            if latin:
                pieces.append(latin)
                latin = ""
            continue
        if _is_cjk(char):
            if latin:
                pieces.append(latin)
                latin = ""
            pieces.append(char)
        else:
            latin += char
    if latin:
        pieces.append(latin)
    return pieces


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3400 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x3040 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )

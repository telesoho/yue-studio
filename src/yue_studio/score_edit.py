"""Commit a jianpu edit back onto the Vocal ABC and the lyric files.

The browser editor rewrites the display ABC (music plus ``w:`` lines). Saving
strips those lyric lines before ``abc_tools`` will accept the score.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .align import join_syllables, section_tag
from .score import load_abc_tools

_W_LINE = re.compile(r"^\s*w:", re.IGNORECASE)

# Gradio replaces the Python arguments with this function's return value, so the
# audio FileData is passed through and ignored by the edit handlers.
OPEN_EDITOR_JS = r"""
async (display, previous, clean, job, audio) => {
  const source = (display && String(display).trim()) ? String(display) : String(clean || "");
  if (!source.trim()) return ["", "", clean, job, audio];
  if (!window.yueScoreEditor || !window.yueScoreEditor.open) {
    return ["__YUE_EDITOR_MISSING__", display, clean, job, audio];
  }
  const edited = await window.yueScoreEditor.open(source, audio);
  if (edited == null || edited === source) return [source, source, clean, job, audio];
  return [edited, source, clean, job, audio];
}
"""

# Gradio copies `head` into the page by creating script elements and appending
# them. Those scripts run as they arrive, so the smaller jianpu module can
# execute before abc2svg exists and never register. score_edit.js loads the
# two files itself, abc2svg first.
EDITOR_HEAD = """
<script src="/gradio_api/file=static/score_edit.js"></script>
"""


@dataclass(frozen=True)
class EditedScore:
    clean: str
    display: str
    lyrics: str
    error: str | None


def strip_w_lines(abc: str) -> str:
    text = abc or ""
    kept = [line for line in text.splitlines() if not _W_LINE.match(line)]
    while kept and not kept[-1].strip():
        kept.pop()
    body = "\n".join(kept)
    if body and text.endswith("\n"):
        body += "\n"
    return body


def _syllables(w_line: str) -> list[str]:
    body = w_line.split(":", 1)[1] if ":" in w_line else ""
    syllables = []
    for token in body.split():
        if token in {"*", "-"}:
            continue
        syllables.append(token.replace("~", " "))
    return syllables


def lyrics_from_display(abc: str) -> str:
    lines = (abc or "").splitlines()
    blocks: list[dict] = []
    section = "section"

    def block_for(tag: str) -> dict:
        if blocks and blocks[-1]["tag"] == tag:
            return blocks[-1]
        item = {"tag": tag, "lines": []}
        blocks.append(item)
        return item

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("% "):
            section = line[2:].strip() or "section"
            index += 1
            continue
        if line != "V: Vocal":
            index += 1
            continue
        index += 1
        while index < len(lines) and lines[index].startswith(("M:", "K:")):
            index += 1
        if index < len(lines):
            index += 1
        syllables: list[str] = []
        if index < len(lines) and _W_LINE.match(lines[index]):
            syllables = _syllables(lines[index])
            index += 1
        text = join_syllables(syllables)
        if text:
            block_for(section_tag(section))["lines"].append(text)
    parts = []
    for block in blocks:
        body = "\n".join(block["lines"])
        if body:
            parts.append(f"[{block['tag']}]\n{body}")
    return "\n\n".join(parts)


def commit_edited_abc(text: str, *, tools=None) -> EditedScore:
    display = text or ""
    clean = strip_w_lines(display)
    if not clean.strip():
        return EditedScore("", display, "", "请先识谱")
    try:
        tools = tools or load_abc_tools()
        tools.parse_abc(clean)
    except Exception as exc:
        return EditedScore(clean, display, "", str(exc))
    return EditedScore(clean, display, lyrics_from_display(display), None)


def write_edited_score(directory, edited: EditedScore) -> None:
    directory = Path(directory)
    if not directory.is_dir() or edited.error:
        return
    clean = edited.clean if edited.clean.endswith("\n") else edited.clean + "\n"
    display = edited.display if edited.display.endswith("\n") else edited.display + "\n"
    (directory / "score.abc").write_text(clean, encoding="utf-8", newline="\n")
    (directory / "lyrics.txt").write_text(edited.lyrics, encoding="utf-8", newline="\n")
    path = directory / "alignment.json"
    payload = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded
    payload["lyrics"] = edited.lyrics
    payload["display_abc"] = display
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )

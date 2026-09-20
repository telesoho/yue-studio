"""Native YuE2 ABC inspect/render helpers. Loads abc_tools by path."""
from __future__ import annotations

import html
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from .paths import abc_tools_path, abcjs_path


def load_abc_tools(path: Path | None = None):
    location = Path(path or abc_tools_path())
    if not location.is_file():
        raise FileNotFoundError(f"abc_tools.py not found: {location}")
    spec = importlib.util.spec_from_file_location("yue_studio_abc_tools", location)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class ScoreView:
    abc: str
    html: str
    chords: list[list[str]]
    error: str | None
    report: dict | None
    bpm: int | None = None


def inspect_abc(text: str, *, tools=None, abcjs: Path | None = None) -> ScoreView:
    abc = text or ""
    if not abc.strip():
        return ScoreView("", _empty_score_html("没有曲谱"), [], "请提供 ABC 曲谱", None)
    try:
        tools = tools or load_abc_tools()
        parsed = tools.parse_abc(abc)
        data = tools.report(parsed)
    except Exception as exc:
        return ScoreView(abc, _plain_score_html(abc, str(exc)), [], str(exc), None)
    chords = []
    vocal = data.get("voices", {}).get("Vocal", {})
    for onset, symbol in vocal.get("chords") or []:
        chords.append([str(onset), str(symbol)])
    return ScoreView(abc, score_html(abc, abcjs=abcjs), chords, None, data, data.get("bpm"))


def strip_chords(text: str, *, tools=None) -> str:
    tools = tools or load_abc_tools()
    return tools.strip_chords(text)


def score_html(abc: str, *, abcjs: Path | None = None) -> str:
    script = ""
    location = abcjs or abcjs_path()
    if location.is_file():
        script = location.read_text(encoding="utf-8")
    payload = json.dumps(abc)
    inner = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
  html,body {{ margin:0; background:#efe6d4; color:#1c1610; }}
  #paper {{ padding:10px 14px 18px; min-height:120px; }}
  pre {{ white-space:pre-wrap; font:13px/1.45 "IBM Plex Mono", ui-monospace, monospace; padding:12px; }}
</style>
<script>{script}</script>
</head>
<body>
<div id="paper"></div>
<script>
const abc = {payload};
const paper = document.getElementById("paper");
try {{
  if (window.ABCJS) {{
    ABCJS.renderAbc("paper", abc, {{
      responsive: "resize",
      staffwidth: 720,
      wrap: {{ minSpacing: 1.35, maxSpacing: 2.4, preferredMeasuresPerLine: 4 }},
      add_classes: true,
      format: {{
        titlefont: "serif 15",
        gchordfont: "serif 13",
        voicefont: "serif 11",
        annotationfont: "serif 11"
      }}
    }});
  }} else {{
    paper.innerHTML = "<pre></pre>";
    paper.firstChild.textContent = abc;
  }}
}} catch (err) {{
  paper.innerHTML = "<pre></pre>";
  paper.firstChild.textContent = String(err) + "\\n\\n" + abc;
}}
</script>
</body></html>"""
    return (
        '<iframe class="score-frame" sandbox="allow-scripts" '
        f'srcdoc="{html.escape(inner, quote=True)}"></iframe>'
    )


def _empty_score_html(message: str) -> str:
    return (
        '<div class="score-empty">'
        f'<span>{html.escape(message)}</span></div>'
    )


def _plain_score_html(abc: str, error: str) -> str:
    return (
        '<div class="score-error">'
        f'<p>{html.escape(error)}</p>'
        f'<pre>{html.escape(abc)}</pre></div>'
    )


CHORD_HEADERS = ["拍点（四分音符）", "和弦"]

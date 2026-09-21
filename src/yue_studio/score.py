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


_SCORE_PLAYER_JS = r"""
const paper = document.getElementById("paper");
const transport = document.getElementById("transport");
const playBtn = document.getElementById("play");
const stopBtn = document.getElementById("stop");
const clock = document.getElementById("clock");
const seek = document.getElementById("seek");
const tempoEl = document.getElementById("tempo");
const hint = document.getElementById("hint");

const state = {
  visual: null,
  notes: [],
  total: 0,
  ctx: null,
  voices: [],
  timer: null,
  playing: false,
  offset: 0,
  startedAt: 0,
  raf: 0,
};

function midiToFreq(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

function formatTime(seconds) {
  const safe = Math.max(0, seconds || 0);
  const m = Math.floor(safe / 60);
  const s = Math.floor(safe % 60);
  return m + ":" + String(s).padStart(2, "0");
}

function setClock(position) {
  clock.textContent = formatTime(position) + " / " + formatTime(state.total);
  if (!seek.matches(":active")) {
    seek.value = state.total ? String(Math.round(1000 * position / state.total)) : "0";
  }
}

function collectNotes(visual) {
  const audio = visual.setUpAudio({});
  const bpm = visual.getBpm() || 120;
  const beat = visual.getBeatLength() || 0.25;
  const fromBeat = (60 / bpm) / beat;
  const totalTime = visual.getTotalTime && visual.getTotalTime();
  const scale = (totalTime && audio.totalDuration) ? totalTime / audio.totalDuration : fromBeat;
  const notes = [];
  for (const track of audio.tracks || []) {
    for (const ev of track) {
      if (ev.cmd !== "note" || ev.pitch == null) continue;
      notes.push({
        start: ev.start * scale,
        duration: Math.max(0.05, (ev.duration || 0) * scale),
        pitch: ev.pitch,
        volume: Math.max(0.04, Math.min(0.22, ((ev.volume || 64) / 127) * 0.2)),
      });
    }
  }
  return {
    notes,
    total: totalTime || notes.reduce((max, note) => Math.max(max, note.start + note.duration), 0),
    bpm,
  };
}

function ensureCtx() {
  const Ctor = window.AudioContext || window.webkitAudioContext;
  if (!Ctor) throw new Error("此浏览器不支持 AudioContext");
  if (!state.ctx) state.ctx = new Ctor();
  return state.ctx;
}

function silence() {
  for (const node of state.voices) {
    try { if (node.stop) node.stop(); } catch (err) {}
    try { node.disconnect(); } catch (err) {}
  }
  state.voices = [];
}

function scheduleNote(note, when, duration) {
  const ctx = state.ctx;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "triangle";
  osc.frequency.setValueAtTime(midiToFreq(note.pitch), when);
  gain.gain.setValueAtTime(0.0001, when);
  gain.gain.exponentialRampToValueAtTime(note.volume, when + 0.012);
  const releaseAt = when + Math.max(0.04, duration - 0.03);
  gain.gain.setValueAtTime(note.volume, releaseAt);
  gain.gain.exponentialRampToValueAtTime(0.0001, when + duration + 0.04);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(when);
  osc.stop(when + duration + 0.05);
  state.voices.push(osc, gain);
}

function nowPosition() {
  if (!state.playing || !state.ctx) return state.offset;
  return Math.min(state.total, state.offset + state.ctx.currentTime - state.startedAt);
}

function tick() {
  if (!state.playing) return;
  const position = nowPosition();
  setClock(position);
  if (position >= state.total - 0.02) {
    finish();
    return;
  }
  state.raf = requestAnimationFrame(tick);
}

function startTimer(position) {
  if (!state.timer) return;
  if (state.timer.stop) state.timer.stop();
  state.timer.start(position, "seconds");
}

function playFrom(position) {
  const ctx = ensureCtx();
  const resume = ctx.resume ? ctx.resume() : Promise.resolve();
  return Promise.resolve(resume).then(function () {
    silence();
    const offset = Math.max(0, Math.min(position, state.total));
    const when0 = ctx.currentTime;
    state.playing = true;
    state.offset = offset;
    state.startedAt = when0;
    for (const note of state.notes) {
      if (note.start + note.duration <= offset) continue;
      const when = when0 + Math.max(0, note.start - offset);
      const duration = note.duration - Math.max(0, offset - note.start);
      scheduleNote(note, when, duration);
    }
    startTimer(offset);
    playBtn.textContent = "暂停";
    playBtn.setAttribute("aria-pressed", "true");
    hint.textContent = "试听曲谱";
    cancelAnimationFrame(state.raf);
    tick();
  });
}

function pause() {
  if (!state.playing) return;
  state.offset = nowPosition();
  state.playing = false;
  silence();
  if (state.timer && state.timer.pause) state.timer.pause();
  cancelAnimationFrame(state.raf);
  playBtn.textContent = "播放";
  playBtn.setAttribute("aria-pressed", "false");
  setClock(state.offset);
}

function finish() {
  state.playing = false;
  state.offset = 0;
  silence();
  if (state.timer && state.timer.stop) state.timer.stop();
  cancelAnimationFrame(state.raf);
  playBtn.textContent = "播放";
  playBtn.setAttribute("aria-pressed", "false");
  setClock(0);
}

function stopPlayback() {
  finish();
}

function togglePlay() {
  if (!state.notes.length) return;
  if (state.playing) pause();
  else playFrom(state.offset >= state.total ? 0 : state.offset).catch(function (err) {
    hint.textContent = String(err.message || err);
  });
}

function pingPitches(pitches) {
  if (!pitches || !pitches.length) return;
  try {
    const ctx = ensureCtx();
    Promise.resolve(ctx.resume && ctx.resume()).then(function () {
      const when = ctx.currentTime;
      for (const item of pitches) {
        scheduleNote({
          pitch: item.pitch,
          volume: 0.16,
        }, when, Math.max(0.18, (item.durationInMeasures || 0.25) * 0.7));
      }
    });
  } catch (err) {}
}

try {
  if (!window.ABCJS) {
    transport.hidden = true;
    paper.innerHTML = "<pre></pre>";
    paper.firstChild.textContent = abc;
  } else {
    const tunes = ABCJS.renderAbc("paper", abc, {
      responsive: "resize",
      staffwidth: 720,
      wrap: { minSpacing: 1.35, maxSpacing: 2.4, preferredMeasuresPerLine: 4 },
      add_classes: true,
      clickListener: function (elem) {
        pingPitches(elem && elem.midiPitches);
      },
      format: {
        titlefont: "serif 15",
        gchordfont: "serif 13",
        voicefont: "serif 11",
        annotationfont: "serif 11"
      }
    });
    const visual = tunes && tunes[0];
    if (!visual || typeof visual.setUpAudio !== "function") {
      hint.textContent = "当前 abcjs 不支持试听";
      playBtn.disabled = true;
    } else {
      const prepared = collectNotes(visual);
      state.visual = visual;
      state.notes = prepared.notes;
      state.total = prepared.total;
      tempoEl.textContent = "♩=" + prepared.bpm;
      setClock(0);
      if (!prepared.notes.length) {
        playBtn.disabled = true;
        hint.textContent = "没有可播放的音符";
      } else if (ABCJS.TimingCallbacks) {
        state.timer = new ABCJS.TimingCallbacks(visual, {
          eventCallback: function (ev) {
            if (!ev) {
              if (state.playing) finish();
            }
          }
        });
      }
    }
    playBtn.addEventListener("click", togglePlay);
    stopBtn.addEventListener("click", stopPlayback);
    seek.addEventListener("input", function () {
      const position = state.total * (Number(seek.value) || 0) / 1000;
      setClock(position);
    });
    seek.addEventListener("change", function () {
      const position = state.total * (Number(seek.value) || 0) / 1000;
      if (state.playing) playFrom(position);
      else state.offset = position;
    });
  }
} catch (err) {
  transport.hidden = true;
  paper.innerHTML = "<pre></pre>";
  paper.firstChild.textContent = String(err) + "\n\n" + abc;
}
"""


_SCORE_DOCUMENT = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
  html,body { margin:0; background:transparent; color:#1b1712; }
  #transport {
    display:flex; align-items:center; gap:8px; flex-wrap:wrap;
    padding:10px 14px;
    background:
      radial-gradient(circle at 18% 50%, rgba(255, 122, 69, 0.55) 0%, transparent 22%),
      radial-gradient(circle at 82% 50%, rgba(192, 132, 252, 0.35) 0%, transparent 22%),
      linear-gradient(180deg, #2b3148 0%, #1a2030 100%);
    border:0;
    border-bottom:1px solid rgba(255, 184, 107, 0.28);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    font:12px/1.3 "IBM Plex Mono", ui-monospace, monospace;
    color:#e7eaf3;
  }
  #transport[hidden] { display:none; }
  #transport button {
    background:#ff7a45; color:#1a0e07; border:0; padding:5px 14px;
    font:600 12px/1.2 "IBM Plex Mono", ui-monospace, monospace; cursor:pointer;
    border-radius:6px; letter-spacing:0.04em;
    box-shadow: 0 2px 8px -2px rgba(255, 122, 69, 0.5);
  }
  #transport button[disabled] { opacity:0.45; cursor:default; }
  #transport button[aria-pressed="true"] { background:#e85a25; color:#fff; }
  #clock, #tempo { color:#c5cee0; min-width:5.5em; font-weight:500; }
  #hint { color:#8b94ad; }
  #seek { flex:1; min-width:120px; accent-color:#ff7a45; }
  #paper { padding:6px 14px 18px; min-height:120px; background:transparent; }
  pre { white-space:pre-wrap; font:13px/1.45 "IBM Plex Mono", ui-monospace, monospace; padding:12px; }
  svg .abcjs-highlight { fill:#c45c4a; stroke:#c45c4a; }
</style>
<script>__ABCJS__</script>
</head>
<body>
<div id="transport">
  <button id="play" type="button" aria-pressed="false">播放</button>
  <button id="stop" type="button">停止</button>
  <span id="tempo"></span>
  <input id="seek" type="range" min="0" max="1000" value="0" aria-label="进度"/>
  <span id="clock">0:00 / 0:00</span>
  <span id="hint">试听曲谱</span>
</div>
<div id="paper"></div>
<script>
const abc = __ABC__;
__PLAYER__
</script>
</body></html>"""


def score_html(abc: str, *, abcjs: Path | None = None) -> str:
    script = ""
    location = abcjs or abcjs_path()
    if location.is_file():
        script = location.read_text(encoding="utf-8")
    inner = (
        _SCORE_DOCUMENT
        .replace("__PLAYER__", _SCORE_PLAYER_JS)
        .replace("__ABCJS__", script)
        .replace("__ABC__", json.dumps(abc))
    )
    return (
        '<iframe class="score-frame" sandbox="allow-scripts" allow="autoplay" '
        f'srcdoc="{html.escape(inner, quote=True)}"></iframe>'
    )


def _empty_score_html(message: str) -> str:
    return (
        '<div class="score-empty">'
        f'<span>{html.escape(message)}</span>'
        "</div>"
    )


def _plain_score_html(abc: str, error: str) -> str:
    return (
        '<div class="score-error">'
        f'<p>{html.escape(error)}</p>'
        f'<pre>{html.escape(abc)}</pre></div>'
    )


CHORD_HEADERS = ["拍点（四分音符）", "和弦"]

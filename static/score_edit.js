/**
 * Jianpu editor for Yue Studio.
 * The page shows the vocal staff (唱) and the accompaniment staff (伴).
 * Both staves edit in the browser. w: lyrics stay on the vocal staff.
 * Click a lyric syllable, empty slot, or use 词 / Enter to edit that line.
 * A rest of a half note or longer is drawn as several 0s; the clicked 0 is one edit.
 * Durations are integer L: counts in the YuE set (1 2 3 4 6 8 12 16 24 32 48).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.yueScoreEditor = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DURATIONS = new Set([1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48]);
  const PLAY_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.2v9.6l8.2-4.8z"/></svg>';
  const PAUSE_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 3h2.6v10H4zm5.4 0H12v10H9.4z"/></svg>';
  const STOP_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4h8v8H4z"/></svg>';
  const STEPS = "CDEFGAB";
  const NATURAL = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  const ACC = { "^^": 2, "^": 1, "=": 0, _: -1, __: -2 };
  const ABS_TEXT = { 2: "^^", 1: "^", 0: "=", "-1": "_", "-2": "__" };
  const FIFTHS = {
    Cb: -7, Gb: -6, Db: -5, Ab: -4, Eb: -3, Bb: -2, F: -1, C: 0,
    G: 1, D: 2, A: 3, E: 4, B: 5, "F#": 6, "C#": 7,
    Abm: -7, Ebm: -6, Bbm: -5, Fm: -4, Cm: -3, Gm: -2, Dm: -1, Am: 0,
    Em: 1, Bm: 2, "F#m": 3, "C#m": 4, "G#m": 5, "D#m": 6, "A#m": 7,
  };
  const SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6];
  const FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3];
  const TOKEN = /^(?:"([^"\n]*)"|\[K:([^\]\n]+)\]|(\^\^|__|\^|_|=)?([A-Ga-gz])([,']*)([0-9]*)(-?))/;

  function keyAlter(stepIdx, fifths) {
    if (fifths > 0) return SHARP_ORDER.slice(0, fifths).indexOf(stepIdx) >= 0 ? 1 : 0;
    if (fifths < 0) return FLAT_ORDER.slice(0, -fifths).indexOf(stepIdx) >= 0 ? -1 : 0;
    return 0;
  }

  function keyFromName(text) {
    const raw = String(text || "").trim().split(/\s+/)[0] || "C";
    const match = /^([A-G])([#b])?(m)?/.exec(raw);
    if (!match) return keyFromName("C");
    const name = match[1] + (match[2] || "") + (match[3] || "");
    return {
      step: match[1],
      acc: match[2] || "",
      fifths: Object.prototype.hasOwnProperty.call(FIFTHS, name) ? FIFTHS[name] : 0,
      name: name,
    };
  }

  function cloneKey(key) {
    return { step: key.step, acc: key.acc, fifths: key.fifths, name: key.name };
  }

  function parseHeader(lines) {
    let meter = [4, 4];
    let lDen = 8;
    let bpm = 120;
    let key = keyFromName("C");
    for (let i = 0; i < lines.length && i < 12; i++) {
      const line = lines[i];
      const meterMatch = /^M:\s*(\d+)\s*\/\s*(\d+)/.exec(line);
      if (meterMatch) meter = [Number(meterMatch[1]), Number(meterMatch[2])];
      const unit = /^L:1\/(\d+)/.exec(line);
      if (unit) lDen = Number(unit[1]);
      const tempo = /^Q:1\/4=(\d+)/.exec(line);
      if (tempo) bpm = Number(tempo[1]);
      const keyLine = /^K:\s*(.*)$/.exec(line);
      if (keyLine) key = keyFromName(keyLine[1]);
    }
    return { meter: meter, lDen: lDen, bpm: bpm, key: key };
  }

  function perBarUnits(meter, lDen) {
    if (!meter[1]) return 0;
    return meter[0] * lDen / meter[1];
  }

  function jianpuAbcWithDirective(src) {
    const withVoices = String(src).replace(/^(V:.*)$/gm, "$1\n%%jianpu true");
    if (withVoices !== src) return withVoices;
    const lines = String(src).split(/\r?\n/);
    let kIdx = -1;
    for (let i = 0; i < lines.length; i++) {
      if (/^K:\s*/.test(lines[i])) {
        kIdx = i;
        break;
      }
    }
    const injection = "%%jianpu true\n";
    if (kIdx < 0) return injection + src;
    return lines.slice(0, kIdx + 1).join("\n") + "\n" + injection + lines.slice(kIdx + 1).join("\n");
  }

  function previewAbc(abc) {
    return jianpuAbcWithDirective(String(abc || ""));
  }

  function countHeads(svg) {
    const text = String(svg || "");
    const vocal = text.match(/<text class="fj v-Vocal"[^>]*>[0-7]<\/text>/g);
    if (vocal && vocal.length) return vocal.length;
    const matches = text.match(/<text class="fj(?: [^"]*)?"[^>]*>[0-7]<\/text>/g);
    return matches ? matches.length : 0;
  }

  function noteMidi(abc, index, voice) {
    const score = timeline(abc);
    if (!score.notes) return null;
    const want = voice || "Vocal";
    for (const note of score.notes) {
      if ((note.voice || "Vocal") !== want) continue;
      if (note.indexes.indexOf(index) >= 0) return note.midi;
    }
    return null;
  }

  function scientific(letter, marks) {
    let octave = /[a-g]/.test(letter) ? 5 : 4;
    for (const mark of marks || "") octave += mark === "'" ? 1 : -1;
    return octave;
  }

  function spellLetter(step, sci) {
    if (sci >= 5 && sci <= 8) {
      return { letter: step.toLowerCase(), marks: "'".repeat(sci - 5) };
    }
    if (sci >= 1 && sci <= 4) {
      return { letter: step, marks: ",".repeat(4 - sci) };
    }
    return null;
  }

  function spell(degree, jpOctave, key, relative) {
    const tonic = STEPS.indexOf(key.step);
    const degree0 = degree - 1;
    const stepIdx = (tonic + degree0) % 7;
    const wrap = Math.floor((tonic + degree0) / 7);
    const shift = tonic === 6 ? 1 : 0;
    const sci = 4 + jpOctave + wrap - shift;
    const abs = keyAlter(stepIdx, key.fifths) + relative;
    if (abs < -2 || abs > 2) return null;
    const written = spellLetter(STEPS[stepIdx], sci);
    if (!written) return null;
    const acc = relative === 0 ? "" : ABS_TEXT[String(abs)];
    if (acc == null) return null;
    return { acc: acc, letter: written.letter, marks: written.marks, stepIdx: stepIdx };
  }

  function midiNumber(letter, marks, acc, key, local) {
    const step = letter.toUpperCase();
    let written = 60 + NATURAL[step] + (/[a-g]/.test(letter) ? 12 : 0);
    for (const mark of marks || "") written += mark === "'" ? 12 : -12;
    let alter = keyAlter(STEPS.indexOf(step), key.fifths);
    if (acc) alter = ACC[acc];
    else if (local && local[step] != null) alter = local[step];
    return written + alter;
  }

  function readJp(ev) {
    if (ev.kind !== "note") return null;
    const stepIdx = STEPS.indexOf(ev.letter.toUpperCase());
    const tonic = STEPS.indexOf(ev.key.step);
    const sci = scientific(ev.letter, ev.marks);
    const degree0 = (stepIdx - tonic + 7) % 7;
    const wrap = Math.floor((tonic + degree0) / 7);
    const shift = tonic === 6 ? 1 : 0;
    const keyAlt = keyAlter(stepIdx, ev.key.fifths);
    const relative = ev.acc ? ACC[ev.acc] - keyAlt : 0;
    return { degree: degree0 + 1, octave: sci - 4 - wrap + shift, relative: relative, stepIdx: stepIdx };
  }

  function printToken(ev) {
    if (ev.kind === "zrest") return ev.bars > 1 ? "Z" + ev.bars : "Z";
    const dur = ev.units === 1 ? "" : String(ev.units);
    if (ev.kind === "rest") return "z" + dur;
    return (ev.acc || "") + ev.letter + (ev.marks || "") + dur + (ev.tie ? "-" : "");
  }

  function lyricToken(ev) {
    if (ev.kind !== "note") return "*";
    const text = String(ev.lyric == null ? "*" : ev.lyric).replace(/[|\s]/g, "");
    if (!text || text === "*") return "*";
    if (text === "-") return "-";
    return text;
  }

  // abc2svg draws a syllable as text. "*" is empty, and "-" / "_" are extender lines.
  function lyricIsDrawn(text) {
    const token = String(text == null ? "" : text).trim();
    return token !== "" && token !== "*" && token !== "-" && token !== "_";
  }

  function isCjkChar(ch) {
    const code = ch.codePointAt(0);
    return (code >= 0x3400 && code <= 0x9fff)
      || (code >= 0xf900 && code <= 0xfaff)
      || (code >= 0x3040 && code <= 0x30ff)
      || (code >= 0xac00 && code <= 0xd7af);
  }

  // Split a pasted lyric line into one token per vocal note.
  // Spaced text keeps spaces; unspaced CJK is one character per token.
  function splitLyricLine(text) {
    const raw = String(text == null ? "" : text).trim();
    if (!raw) return [];
    if (/\s/.test(raw)) {
      return raw.split(/\s+/).filter(Boolean).map((token) => {
        if (token === "·" || token === "*") return "*";
        if (token === "-") return "-";
        return token.replace(/[|\s]/g, "") || "*";
      });
    }
    const tokens = [];
    let i = 0;
    while (i < raw.length) {
      const ch = raw[i];
      if (ch === "·" || ch === "*") {
        tokens.push("*");
        i += 1;
        continue;
      }
      if (ch === "-") {
        tokens.push("-");
        i += 1;
        continue;
      }
      if (isCjkChar(ch)) {
        tokens.push(ch);
        i += 1;
        continue;
      }
      let j = i + 1;
      while (
        j < raw.length
        && !isCjkChar(raw[j])
        && raw[j] !== "·"
        && raw[j] !== "*"
        && raw[j] !== "-"
      ) {
        j += 1;
      }
      const word = raw.slice(i, j).replace(/[|\s]/g, "");
      if (word) tokens.push(word);
      i = j;
    }
    return tokens;
  }

  function displayLyricToken(lyric) {
    const text = String(lyric == null ? "*" : lyric).trim();
    if (!text || text === "*") return "·";
    if (text === "-") return "-";
    return text;
  }

  function lineLyricText(events, lineNo) {
    return events
      .filter((ev) => !ev.removed && ev.line === lineNo && ev.kind === "note")
      .map((ev) => displayLyricToken(ev.lyric))
      .join(" ");
  }

  function clusterRows(items, slack) {
    const sorted = items.slice().sort((a, b) => a.y - b.y || a.x - b.x);
    const rows = [];
    for (const item of sorted) {
      const row = rows[rows.length - 1];
      if (!row || Math.abs(item.y - row.y) > slack) rows.push({ y: item.y, items: [item] });
      else row.items.push(item);
    }
    for (const row of rows) row.items.sort((a, b) => a.x - b.x);
    return rows;
  }

  // Pair lyric glyphs with the vocal notes above them. Rests and melismas draw no syllable.
  // When counts disagree, bind the shorter side left-to-right.
  function assignLyricHits(heads, glyphs, drawn, limits) {
    const slack = limits && limits.rowSlack != null ? limits.rowSlack : 8;
    const maxGap = limits && limits.maxGap != null ? limits.maxGap : 80;
    const vocalRows = clusterRows((heads || []).filter((head) => (head.voice || "Vocal") === "Vocal"), slack);
    const glyphRows = clusterRows(glyphs || [], slack);
    const hits = [];
    for (const row of glyphRows) {
      let staff = null;
      for (const candidate of vocalRows) {
        if (candidate.y >= row.y - 2) continue;
        if (!staff || candidate.y > staff.y) staff = candidate;
      }
      if (!staff || row.y - staff.y > maxGap) continue;
      let below = null;
      for (const candidate of vocalRows) {
        if (candidate.y <= row.y + 2) continue;
        if (!below || candidate.y < below.y) below = candidate;
      }
      if (below && below.y - row.y < row.y - staff.y) continue;
      const seen = new Set();
      const indexes = [];
      for (const head of staff.items) {
        if (seen.has(head.index)) continue;
        seen.add(head.index);
        indexes.push(head.index);
      }
      const slots = indexes.filter((index) => drawn && drawn[index]);
      const count = Math.min(slots.length, row.items.length);
      if (!count) continue;
      for (let i = 0; i < count; i++) hits.push({ glyph: row.items[i], index: slots[i] });
    }
    return hits;
  }

  function assignLyrics(events, wLine) {
    const tokens = wLine
      ? wLine.replace(/^w:\s*/, "").trim().split(/\s+/).filter(Boolean)
      : [];
    const noteCount = events.filter((ev) => ev.kind === "note").length;
    if (tokens.length === events.length) {
      events.forEach((ev, index) => {
        ev.lyric = tokens[index];
      });
      return;
    }
    let cursor = 0;
    for (const ev of events) {
      if (ev.kind === "note" && tokens.length === noteCount) ev.lyric = tokens[cursor++] || "*";
      else if (ev.kind === "note") ev.lyric = cursor < tokens.length ? tokens[cursor++] : "*";
      else ev.lyric = "*";
    }
  }

  function scanMusic(line, key, perBar) {
    const events = [];
    let barIndex = 0;
    let barUnits = 0;
    let pendingTie = false;
    let pendingChord = "";
    let i = 0;
    while (i < line.length) {
      const ch = line[i];
      if (ch === "|") {
        barIndex += 1;
        barUnits = 0;
        i += 1;
        continue;
      }
      if (/\s/.test(ch)) {
        i += 1;
        continue;
      }
      const zrest = /^Z([2-4])?/.exec(line.slice(i));
      if (zrest) {
        const bars = zrest[1] ? Number(zrest[1]) : 1;
        const units = bars * perBar;
        events.push({
          kind: "zrest",
          units: units,
          bars: bars,
          start: i,
          end: i + zrest[0].length,
          raw: zrest[0],
          barIndex: barIndex,
          perBar: perBar,
          key: cloneKey(key),
          lyric: "*",
          tie: false,
          continuesTie: false,
          acc: "",
          letter: "z",
          marks: "",
          chord: pendingChord,
        });
        pendingChord = "";
        barUnits += units;
        pendingTie = false;
        i += zrest[0].length;
        continue;
      }
      const match = TOKEN.exec(line.slice(i));
      if (!match) return { error: "读不懂这里的记号" };
      const raw = match[0];
      if (match[1] != null) {
        pendingChord = match[1];
        i += raw.length;
        continue;
      }
      if (match[2] != null) {
        key = keyFromName(match[2]);
        i += raw.length;
        continue;
      }
      const units = match[6] ? Number(match[6]) : 1;
      const tie = match[7] === "-";
      const rest = match[4] === "z";
      events.push({
        kind: rest ? "rest" : "note",
        units: units,
        bars: 1,
        start: i,
        end: i + raw.length,
        raw: raw,
        barIndex: barIndex,
        perBar: perBar,
        key: cloneKey(key),
        lyric: "*",
        tie: tie,
        continuesTie: pendingTie && !rest,
        acc: match[3] || "",
        letter: match[4],
        marks: match[5] || "",
        chord: pendingChord,
      });
      pendingChord = "";
      barUnits += units;
      pendingTie = tie;
      i += raw.length;
    }
    return { events: events, key: key };
  }

  function collect(abc) {
    const lines = String(abc || "").split(/\r?\n/);
    const header = parseHeader(lines);
    let key = header.key;
    let perBar = perBarUnits(header.meter, header.lDen);
    const buckets = { Vocal: [], Ins: [] };
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^M:\s*\d/.test(line)) {
        const meterMatch = /^M:\s*(\d+)\s*\/\s*(\d+)/.exec(line);
        if (meterMatch) perBar = perBarUnits([Number(meterMatch[1]), Number(meterMatch[2])], header.lDen);
        i += 1;
        continue;
      }
      if (/^K:\s*/.test(line)) {
        key = keyFromName(line.slice(2));
        i += 1;
        continue;
      }
      const voice = line === "V: Vocal" ? "Vocal" : line === "V: Ins" ? "Ins" : "";
      if (!voice) {
        i += 1;
        continue;
      }
      i += 1;
      while (i < lines.length && /^(M:|K:)/.test(lines[i])) {
        if (lines[i].startsWith("M:")) {
          const meterMatch = /^M:\s*(\d+)\s*\/\s*(\d+)/.exec(lines[i]);
          if (meterMatch) perBar = perBarUnits([Number(meterMatch[1]), Number(meterMatch[2])], header.lDen);
        } else {
          key = keyFromName(lines[i].slice(2));
        }
        i += 1;
      }
      if (i >= lines.length) break;
      const scanned = scanMusic(lines[i], key, perBar);
      if (scanned.error) {
        return { error: scanned.error, lines: lines, events: [], ins: [], header: header };
      }
      key = scanned.key;
      const musicLine = i;
      i += 1;
      let lyricLine = -1;
      let wLine = null;
      if (voice === "Vocal" && i < lines.length && /^w:/.test(lines[i])) {
        lyricLine = i;
        wLine = lines[i];
        i += 1;
      }
      if (voice === "Vocal") assignLyrics(scanned.events, wLine);
      const bucket = buckets[voice];
      for (const ev of scanned.events) {
        ev.line = musicLine;
        ev.lyricLine = lyricLine;
        ev.voice = voice;
        ev.index = bucket.length;
        bucket.push(ev);
      }
    }
    return { lines: lines, events: buckets.Vocal, ins: buckets.Ins, header: header, error: null };
  }

  function barSum(events, ev) {
    return events
      .filter((item) => !item.removed && item.line === ev.line && item.barIndex === ev.barIndex)
      .reduce((sum, item) => sum + item.units + (item.spawn ? item.spawn.units : 0), 0);
  }

  function acceptBar(oldSum, newSum, perBar) {
    if (newSum > perBar) return "这一小节会超过拍号";
    if (oldSum === perBar && newSum !== perBar) return "这一小节的拍数对不上";
    return null;
  }

  function applySpans(line, reps) {
    const ordered = reps.slice().sort((a, b) => b.start - a.start);
    let out = line;
    for (const rep of ordered) out = out.slice(0, rep.start) + rep.text + out.slice(rep.end);
    return out;
  }

  function rewriteMusic(lines, events) {
    const byLine = new Map();
    for (const ev of events) {
      if (ev.inserted) continue;
      if (!byLine.has(ev.line)) byLine.set(ev.line, []);
      byLine.get(ev.line).push(ev);
    }
    for (const [lineNo, group] of byLine) {
      const reps = [];
      for (const ev of group) {
        if (ev.removed) {
          reps.push({ start: ev.start, end: ev.end, text: "" });
          continue;
        }
        let text = printToken(ev);
        if (ev.insertAfter) text += ev.insertAfter;
        if (text !== ev.raw) reps.push({ start: ev.start, end: ev.end, text: text });
      }
      if (reps.length) lines[lineNo] = applySpans(lines[lineNo], reps);
    }
  }

  function visibleEvents(events) {
    const out = [];
    for (const ev of events) {
      if (ev.removed) continue;
      out.push(ev);
      if (ev.spawn) out.push(ev.spawn);
    }
    return out;
  }

  function rewriteLyrics(lines, events) {
    const groups = new Map();
    for (const ev of visibleEvents(events)) {
      if (!groups.has(ev.line)) groups.set(ev.line, []);
      groups.get(ev.line).push(ev);
    }
    const musicLines = [...groups.keys()].sort((a, b) => b - a);
    for (const musicLine of musicLines) {
      const group = groups.get(musicLine);
      // abc2svg skips rests, so a "*" written for a rest would land on the next note.
      const tokens = group.filter((ev) => ev.kind === "note").map(lyricToken);
      const meaningful = tokens.some((token) => token !== "*" && token !== "-");
      const has = lines[musicLine + 1] && /^w:/.test(lines[musicLine + 1]);
      if (!meaningful) {
        if (has) lines.splice(musicLine + 1, 1);
        continue;
      }
      const text = "w: " + tokens.join(" ");
      if (has) lines[musicLine + 1] = text;
      else lines.splice(musicLine + 1, 0, text);
    }
  }

  function joinAbc(lines, abc) {
    let text = lines.join("\n");
    if (String(abc || "").endsWith("\n") && !text.endsWith("\n")) text += "\n";
    return text;
  }

  function breakTies(events, index) {
    const ev = events[index];
    if (ev.tie) ev.tie = false;
    const prev = events[index - 1];
    if (prev && prev.tie && ev.continuesTie && prev.line === ev.line) {
      prev.tie = false;
      ev.continuesTie = false;
    }
    const next = events[index + 1];
    if (ev.tie && next && next.continuesTie) {
      ev.tie = false;
      next.continuesTie = false;
    }
  }

  function applySpelling(ev, spelled) {
    ev.kind = "note";
    ev.acc = spelled.acc;
    ev.letter = spelled.letter;
    ev.marks = spelled.marks;
    const midi = midiNumber(spelled.letter, spelled.marks, spelled.acc, ev.key, null);
    if (midi < 0 || midi > 127) return "这个音超出音域";
    return null;
  }

  function makeRest(ev) {
    ev.kind = "rest";
    ev.acc = "";
    ev.letter = "z";
    ev.marks = "";
    ev.tie = false;
    ev.continuesTie = false;
    ev.lyric = "*";
    ev.bars = 1;
  }

  function tonicNote(ev, units) {
    const spelled = spell(1, 0, ev.key, 0);
    return {
      kind: "note",
      units: units,
      bars: 1,
      line: ev.line,
      barIndex: ev.barIndex,
      perBar: ev.perBar,
      key: cloneKey(ev.key),
      lyric: "*",
      tie: false,
      continuesTie: false,
      acc: spelled.acc,
      letter: spelled.letter,
      marks: spelled.marks,
      inserted: true,
    };
  }

  function checkUnits(units) {
    return Number.isInteger(units) && DURATIONS.has(units);
  }

  function quarterUnits(lDen) {
    const units = lDen / 4;
    return Number.isInteger(units) && units >= 1 ? units : 0;
  }

  function samePitch(a, b) {
    if (!a || !b || a.kind !== "note" || b.kind !== "note") return false;
    const left = readJp(a);
    const right = readJp(b);
    return left.degree === right.degree && left.octave === right.octave && left.relative === right.relative;
  }

  function sliceUnits(ev, lDen) {
    const count = digitGlyphs(ev, lDen);
    if (count <= 1 || ev.kind === "note") return null;
    if (ev.kind === "zrest") {
      const bar = ev.perBar;
      if (ev.bars !== count || !checkUnits(bar) || ev.units !== count * bar) return null;
      return Array(count).fill(bar);
    }
    const quarter = quarterUnits(lDen);
    if (!quarter || ev.units !== count * quarter) return null;
    return Array(count).fill(quarter);
  }

  function padLyricStars(lines, events, ev, count) {
    if (ev.lyricLine < 0) return;
    const lyricAt = ev.lyricLine;
    if (!lines[lyricAt] || !/^w:/.test(lines[lyricAt])) return;
    const tokens = lines[lyricAt].replace(/^w:\s*/, "").trim().split(/\s+/).filter(Boolean);
    const onLine = events.filter((item) => item.line === ev.line);
    if (tokens.length !== onLine.length) return;
    const pos = onLine.findIndex((item) => item === ev);
    if (pos < 0) return;
    const extra = [];
    for (let n = 1; n < count; n++) extra.push("*");
    tokens.splice(pos + 1, 0, ...extra);
    lines[lyricAt] = "w: " + tokens.join(" ");
  }

  // One ABC rest is drawn as several 0s. Split it so the clicked 0 can change alone.
  function expandSlicedRest(abc, voice, index, slice) {
    const parsed = collect(abc);
    if (parsed.error) return { abc: abc, index: index, error: parsed.error };
    const events = voice === "Ins" ? parsed.ins : parsed.events;
    if (index < 0 || index >= events.length) return { abc: abc, index: index };
    const ev = events[index];
    const count = digitGlyphs(ev, parsed.header.lDen);
    if (count <= 1 || ev.kind === "note") return { abc: abc, index: index };
    const sizes = sliceUnits(ev, parsed.header.lDen);
    if (!sizes) return { abc: abc, index: index, error: "这个休止拆不开" };
    if (slice < 0 || slice >= sizes.length) return { abc: abc, index: index };
    const tokens = sizes.map((units) => "z" + (units === 1 ? "" : String(units))).join("");
    const lines = parsed.lines.slice();
    lines[ev.line] = lines[ev.line].slice(0, ev.start) + tokens + lines[ev.line].slice(ev.end);
    if (voice !== "Ins") padLyricStars(lines, events, ev, sizes.length);
    return { abc: joinAbc(lines, abc), index: index + slice };
  }

  function editScore(abc, command) {
    const voice = command.voice === "Ins" ? "Ins" : "Vocal";
    if (command.slice != null) {
      const expanded = expandSlicedRest(abc, voice, command.index | 0, command.slice | 0);
      if (expanded.error) return { abc: abc, error: expanded.error };
      const result = editScore(expanded.abc, Object.assign({}, command, {
        index: expanded.index,
        voice: voice,
        slice: null,
      }));
      if (result.error) return { abc: abc, error: result.error };
      return result;
    }
    const parsed = collect(abc);
    if (parsed.error) return { abc: abc, error: parsed.error };
    const events = voice === "Ins" ? parsed.ins : parsed.events;
    const index = command.index | 0;
    if (!events.length) {
      return { abc: abc, error: voice === "Ins" ? "没有可编辑的伴奏音符" : "没有可编辑的人声音符" };
    }
    if (index < 0 || index >= events.length) return { abc: abc, error: "没有这个音" };
    const ev = events[index];
    const op = command.op;
    let lyricsDirty = false;
    let leftover = 0;
    let select = index;
    const oldSum = barSum(events, ev);

    if (op === "degree") {
      const degree = command.degree | 0;
      if (ev.kind === "zrest" && (ev.bars !== 1 || !checkUnits(ev.units))) {
        return { abc: abc, error: "整段休止不能改成一个音" };
      }
      const wasRest = ev.kind !== "note";
      breakTies(events, index);
      if (degree === 0) {
        makeRest(ev);
        lyricsDirty = true;
      } else if (degree >= 1 && degree <= 7) {
        const jp = ev.kind === "note" ? readJp(ev) : { octave: 0 };
        const spelled = spell(degree, jp.octave || 0, ev.key, 0);
        if (!spelled) return { abc: abc, error: "这个音超出音域" };
        const range = applySpelling(ev, spelled);
        if (range) return { abc: abc, error: range };
        if (wasRest) {
          ev.lyric = "*";
          lyricsDirty = true;
        }
      } else {
        return { abc: abc, error: "唱名要用 1 到 7，休止是 0" };
      }
    } else if (op === "octave") {
      if (ev.kind !== "note") return { abc: abc, error: "休止没有八度" };
      const jp = readJp(ev);
      const spelled = spell(jp.degree, jp.octave + (command.delta | 0), ev.key, jp.relative);
      if (!spelled) return { abc: abc, error: "这个音超出音域" };
      breakTies(events, index);
      const range = applySpelling(ev, spelled);
      if (range) return { abc: abc, error: range };
    } else if (op === "accidental") {
      if (ev.kind !== "note") return { abc: abc, error: "休止没有升降号" };
      const jp = readJp(ev);
      let relative = jp.relative;
      if (command.kind === "sharp") relative = relative === 1 ? 0 : 1;
      else if (command.kind === "flat") relative = relative === -1 ? 0 : -1;
      else {
        const abs = ev.acc ? ACC[ev.acc] : keyAlter(jp.stepIdx, ev.key.fifths);
        relative = abs === 0 ? 0 : -keyAlter(jp.stepIdx, ev.key.fifths);
        if (abs === 0 && ev.acc) relative = 0;
      }
      const spelled = spell(jp.degree, jp.octave, ev.key, relative);
      if (!spelled) return { abc: abc, error: "这个音超出音域" };
      breakTies(events, index);
      const range = applySpelling(ev, spelled);
      if (range) return { abc: abc, error: range };
    } else if (op === "duration") {
      if (ev.kind === "zrest") return { abc: abc, error: "整段休止先改成音符再改时值" };
      const factor = command.factor;
      breakTies(events, index);
      if (factor === 0.5) {
        const half = ev.units / 2;
        if (!checkUnits(half) || !checkUnits(ev.units - half)) {
          return { abc: abc, error: "这个时值写不进曲谱" };
        }
        const rest = tonicNote(ev, ev.units - half);
        rest.kind = "rest";
        rest.letter = "z";
        rest.acc = "";
        rest.marks = "";
        ev.units = half;
        ev.spawn = rest;
        ev.insertAfter = printToken(rest);
        lyricsDirty = true;
      } else if (factor === 2 || factor === 1.5) {
        const added = factor === 2 ? ev.units : ev.units / 2;
        const nextUnits = factor === 2 ? ev.units * 2 : ev.units + added;
        if (!checkUnits(nextUnits) || !Number.isInteger(added)) {
          return { abc: abc, error: "这个时值写不进曲谱" };
        }
        const next = events[index + 1];
        if (!next || next.removed || next.line !== ev.line || next.barIndex !== ev.barIndex ||
            (next.kind !== "rest" && next.kind !== "zrest") || next.units < added) {
          return { abc: abc, error: "这一小节会超过拍号" };
        }
        if (next.kind === "zrest") return { abc: abc, error: "这一小节会超过拍号" };
        const left = next.units - added;
        if (left !== 0 && !checkUnits(left)) return { abc: abc, error: "这个时值写不进曲谱" };
        ev.units = nextUnits;
        if (left === 0) next.removed = true;
        else next.units = left;
        lyricsDirty = true;
      } else {
        return { abc: abc, error: "这个时值写不进曲谱" };
      }
      const problem = acceptBar(oldSum, barSum(events, ev), ev.perBar);
      if (problem) return { abc: abc, error: problem };
    } else if (op === "insert") {
      if (ev.kind === "zrest" && ev.bars !== 1) return { abc: abc, error: "这里插不进同长度的音" };
      breakTies(events, index);
      if (oldSum + ev.units <= ev.perBar) {
        const problem = acceptBar(oldSum, oldSum + ev.units, ev.perBar);
        if (!problem) {
          const spawned = tonicNote(ev, ev.units);
          ev.spawn = spawned;
          ev.insertAfter = printToken(spawned);
          lyricsDirty = true;
        }
      }
      if (!ev.spawn) {
        const half = ev.units / 2;
        if (!checkUnits(half)) return { abc: abc, error: "这里插不进同长度的音" };
        const spawned = tonicNote(ev, half);
        ev.units = half;
        if (ev.kind === "zrest") makeRest(ev);
        ev.spawn = spawned;
        ev.insertAfter = printToken(spawned);
        lyricsDirty = true;
      }
    } else if (op === "delete") {
      if (ev.kind === "rest" || ev.kind === "zrest") {
        const prev = events[index - 1];
        if (ev.kind === "zrest" || !prev || prev.line !== ev.line || prev.barIndex !== ev.barIndex || prev.kind === "zrest") {
          return { abc: abc, error: "删掉后这一小节不够拍" };
        }
        const merged = prev.units + ev.units;
        if (!checkUnits(merged)) return { abc: abc, error: "删掉后这一小节不够拍" };
        breakTies(events, index);
        prev.units = merged;
        ev.removed = true;
        lyricsDirty = true;
      } else {
        breakTies(events, index);
        makeRest(ev);
        lyricsDirty = true;
      }
      const problem = acceptBar(oldSum, barSum(events, ev.removed ? events[index - 1] || ev : ev), ev.perBar);
      if (problem) return { abc: abc, error: problem };
    } else if (op === "tie") {
      if (ev.kind !== "note") return { abc: abc, error: "休止不能连音" };
      const next = events[index + 1];
      if (!samePitch(ev, next)) return { abc: abc, error: "连音要接在后面同样的音上" };
      ev.tie = !ev.tie;
      next.continuesTie = ev.tie;
    } else if (op === "sustain") {
      if (ev.kind !== "note") return { abc: abc, error: "休止不能延长" };
      const added = quarterUnits(parsed.header.lDen);
      const nextUnits = ev.units + added;
      if (!added || !checkUnits(nextUnits)) return { abc: abc, error: "这个时值写不进曲谱" };
      const next = events[index + 1];
      if (!next || next.removed || next.line !== ev.line || next.barIndex !== ev.barIndex || next.kind !== "rest") {
        return { abc: abc, error: "后面没有可以让出来的休止" };
      }
      if (next.units < added) return { abc: abc, error: "后面的休止不够一拍" };
      const left = next.units - added;
      if (left !== 0 && !checkUnits(left)) return { abc: abc, error: "这个时值写不进曲谱" };
      breakTies(events, index);
      ev.units = nextUnits;
      if (left === 0) next.removed = true;
      else next.units = left;
      lyricsDirty = true;
      const problem = acceptBar(oldSum, barSum(events, ev), ev.perBar);
      if (problem) return { abc: abc, error: problem };
    } else if (op === "lyric") {
      if (voice === "Ins") return { abc: abc, error: "伴奏没有歌词" };
      if (ev.kind !== "note") return { abc: abc, error: "休止的歌词是 *" };
      const text = String(command.text == null ? "" : command.text).trim();
      ev.lyric = text && text !== "*" ? text : "*";
      lyricsDirty = true;
    } else if (op === "lyric-line") {
      if (voice === "Ins") return { abc: abc, error: "伴奏没有歌词" };
      const lineNo = ev.line;
      const notes = events.filter((item) => !item.removed && item.line === lineNo && item.kind === "note");
      if (!notes.length) return { abc: abc, error: "这一行没有可填词的音" };
      const tokens = splitLyricLine(command.text);
      notes.forEach((note, i) => {
        if (i < tokens.length) {
          const token = tokens[i];
          note.lyric = token && token !== "*" ? token : "*";
        } else {
          note.lyric = "*";
        }
      });
      leftover = Math.max(0, tokens.length - notes.length);
      lyricsDirty = true;
    } else {
      return { abc: abc, error: "不支持这个修改" };
    }

    if (op === "insert") select = index + 1;
    if (op === "delete" && ev.removed) select = Math.max(0, index - 1);
    const lines = parsed.lines.slice();
    rewriteMusic(lines, events);
    if (lyricsDirty && voice !== "Ins") rewriteLyrics(lines, events);
    const result = { abc: joinAbc(lines, abc), error: null, index: select };
    if (leftover) result.leftover = leftover;
    return result;
  }

  function accidentalName(acc) {
    if (acc === "^" || acc === "^^") return "sharp";
    if (acc === "_" || acc === "__") return "flat";
    if (acc === "=") return "natural";
    return "";
  }

  function eventsFor(abc, voice) {
    const parsed = collect(abc);
    if (parsed.error) return [];
    const events = voice === "Ins" ? parsed.ins : parsed.events;
    return events.map((ev) => {
      const jp = ev.kind === "note" ? readJp(ev) : null;
      return {
        index: ev.index,
        kind: ev.kind,
        lyric: ev.lyric,
        units: ev.units,
        digit: jp ? String(jp.degree) : "0",
        accidental: ev.kind === "note" ? accidentalName(ev.acc) : "",
        tie: !!ev.tie,
      };
    });
  }

  function listEvents(abc) {
    return eventsFor(abc, "Vocal");
  }

  // abc2svg jianpu draws one digit per note. A rest at least a half note is
  // sliced into quarter-length 0s (1, 2, or 3 extras). A multi-bar Z is one 0 per bar.
  function digitGlyphs(ev, lDen) {
    if (ev.kind === "note") return 1;
    if (ev.kind === "zrest" && ev.bars > 1) return ev.bars;
    const half = lDen / 2;
    if (ev.units < half) return 1;
    if (ev.units >= lDen) return 4;
    if (ev.units === half) return 2;
    return 3;
  }

  function headIndexes(abc, voice) {
    const parsed = collect(abc);
    if (parsed.error) return [];
    const events = voice === "Ins" ? parsed.ins : parsed.events;
    const indexes = [];
    for (const ev of events) {
      const count = digitGlyphs(ev, parsed.header.lDen);
      for (let n = 0; n < count; n++) indexes.push(ev.index);
    }
    return indexes;
  }

  const CHORD_INTERVALS = {
    "": [0, 4, 7],
    m: [0, 3, 7],
    dim: [0, 3, 6],
    aug: [0, 4, 8],
    "7": [0, 4, 7, 10],
    maj7: [0, 4, 7, 11],
    m7: [0, 3, 7, 10],
    dim7: [0, 3, 6, 9],
    m7b5: [0, 3, 6, 10],
    sus4: [0, 5, 7],
    sus2: [0, 2, 7],
    "6": [0, 4, 7, 9],
    m6: [0, 3, 7, 9],
    "7sus4": [0, 5, 7, 10],
    "m(maj7)": [0, 3, 7, 11],
  };
  const CHORD_RE = /^([A-G](?:bb|##|b|#)?)(m\(maj7\)|maj7|dim7|m7b5|7sus4|sus4|sus2|m7|m6|dim|aug|7|6|m)?(?:\/([A-G](?:bb|##|b|#)?))?$/;
  const CHORD_ACC = { bb: -2, "##": 2, b: -1, "#": 1 };

  function pitchClass(name) {
    const match = /^([A-G])(bb|##|b|#)?$/.exec(name || "");
    if (!match) return null;
    return (NATURAL[match[1]] + (CHORD_ACC[match[2]] || 0) + 12) % 12;
  }

  // Chord tones sit in the C4 octave so they stay audible on small speakers.
  // A slash bass, or the root, is added an octave below.
  function spellChord(symbol) {
    const match = CHORD_RE.exec(String(symbol || "").trim());
    if (!match) return null;
    const root = pitchClass(match[1]);
    const quality = match[2] || "";
    const bass = match[3] ? pitchClass(match[3]) : root;
    const intervals = CHORD_INTERVALS[quality];
    if (root == null || bass == null || !intervals) return null;
    const tones = [];
    for (const interval of intervals) tones.push(60 + ((root + interval) % 12));
    let low = 48 + bass;
    if (low >= 60) low -= 12;
    if (tones.indexOf(low) < 0) tones.unshift(low);
    tones.sort((a, b) => a - b);
    return tones.filter((midi, index) => tones.indexOf(midi) === index);
  }

  function scheduleVoice(events, quarter, voice) {
    let units = 0;
    let barKey = null;
    let local = {};
    const notes = [];
    const chords = [];
    for (const ev of events) {
      const key = ev.line + ":" + ev.barIndex;
      if (key !== barKey) {
        barKey = key;
        local = {};
      }
      const startQ = units * quarter;
      units += ev.units;
      if (ev.chord && spellChord(ev.chord)) chords.push({ symbol: ev.chord, startQ: startQ });
      if (ev.kind !== "note") continue;
      const midi = midiNumber(ev.letter, ev.marks, ev.acc, ev.key, local);
      if (ev.acc) local[ev.letter.toUpperCase()] = ACC[ev.acc];
      const endQ = startQ + ev.units * quarter;
      const prev = notes[notes.length - 1];
      if (ev.continuesTie && prev && prev.midi === midi && Math.abs(prev.endQ - startQ) < 1e-6) {
        prev.endQ = endQ;
        prev.indexes.push(ev.index);
        continue;
      }
      notes.push({ midi: midi, startQ: startQ, endQ: endQ, voice: voice, indexes: [ev.index] });
    }
    return { notes: notes, chords: chords, endQ: units * quarter };
  }

  function chordNotes(changes, endQ, bpm) {
    const notes = [];
    for (let i = 0; i < changes.length; i++) {
      const change = changes[i];
      const until = i + 1 < changes.length ? changes[i + 1].startQ : endQ;
      if (until - change.startQ <= 1e-6) continue;
      const tones = spellChord(change.symbol);
      if (!tones) continue;
      const start = change.startQ * 60 / bpm;
      const duration = (until - change.startQ) * 60 / bpm;
      for (const midi of tones) {
        notes.push({
          midi: midi,
          voice: "Chord",
          start: start,
          duration: duration,
          indexes: [],
          volume: 0.16,
          velocity: 86,
        });
      }
    }
    return notes;
  }

  function timeline(abc) {
    const parsed = collect(abc);
    if (parsed.error) return { bpm: 120, notes: [], error: parsed.error };
    const quarter = 4 / parsed.header.lDen;
    const vocal = scheduleVoice(parsed.events, quarter, "Vocal");
    const ins = scheduleVoice(parsed.ins || [], quarter, "Ins");
    const bpm = parsed.header.bpm || 120;
    const notes = vocal.notes.concat(ins.notes).map((note) => ({
      midi: note.midi,
      voice: note.voice,
      start: note.startQ * 60 / bpm,
      duration: (note.endQ - note.startQ) * 60 / bpm,
      indexes: note.indexes,
    }));
    const endQ = Math.max(vocal.endQ, ins.endQ);
    return {
      bpm: bpm,
      error: null,
      notes: notes.concat(chordNotes(vocal.chords, endQ, bpm)),
    };
  }

  // One mark per drawn digit, including rest slices, so the playhead walks
  // through 0s as well as sounding notes. Vocal is listed first.
  function playMarks(abc) {
    const parsed = collect(abc);
    if (parsed.error) return [];
    const quarter = 4 / parsed.header.lDen;
    const bpm = parsed.header.bpm || 120;
    const secPerUnit = quarter * 60 / bpm;
    const marks = [];
    function walk(events, voice) {
      let units = 0;
      for (const ev of events) {
        const count = digitGlyphs(ev, parsed.header.lDen);
        const sliceUnits = count ? ev.units / count : ev.units;
        for (let slice = 0; slice < count; slice++) {
          marks.push({
            voice: voice,
            index: ev.index,
            slice: slice,
            start: (units + slice * sliceUnits) * secPerUnit,
          });
        }
        units += ev.units;
      }
    }
    walk(parsed.events, "Vocal");
    walk(parsed.ins || [], "Ins");
    return marks;
  }

  // The glyph that playback has reached: latest start at or before now.
  // A tie stays on the vocal digit.
  function cursorAt(marks, now) {
    if (!marks || !marks.length) return null;
    let best = null;
    for (const mark of marks) {
      if (mark.start > now + 1e-3) continue;
      const later = !best || mark.start > best.start + 1e-3;
      const vocalTie = best && Math.abs(mark.start - best.start) <= 1e-3
        && mark.voice === "Vocal" && best.voice !== "Vocal";
      if (later || vocalTie) best = mark;
    }
    return best || marks[0];
  }

  function markTime(marks, voice, index, slice) {
    if (!marks || !marks.length || index == null) return null;
    const wantVoice = voice || "Vocal";
    const wantSlice = slice || 0;
    for (const mark of marks) {
      if (mark.voice === wantVoice && mark.index === index && mark.slice === wantSlice) {
        return mark.start;
      }
    }
    return null;
  }

  // Gradio 5 hands the browser a FileData object. A raw filesystem path cannot
  // be played, so only an http(s), blob, or app-relative URL is accepted.
  function fileUrl(file) {
    if (!file) return "";
    if (typeof file === "string") {
      return /^(https?:|blob:|\/)/.test(file) ? file : "";
    }
    if (typeof file.url === "string" && file.url) return file.url;
    if (typeof file.path === "string" && file.path) {
      return "/gradio_api/file=" + encodeURI(file.path.replace(/\\/g, "/"));
    }
    return "";
  }

  function inspectScore(abc) {
    const parsed = collect(abc);
    if (parsed.error) return { error: parsed.error, events: [], bpm: 120, keyName: "C" };
    return {
      error: null,
      bpm: parsed.header.bpm,
      keyName: parsed.header.key.name,
      events: listEvents(abc),
    };
  }

  const ui = {
    abc: "",
    index: -1,
    voice: "Vocal",
    slice: 0,
    resolve: null,
    nodes: [],
    generation: 0,
    arming: false,
    ctx: null,
    osc: [],
    raf: 0,
    lyricInput: null,
    playhead: null,
    playKey: "",
    audioUrl: "",
    audio: null,
    transport: "midi",
    marks: [],
    sourceTouched: false,
    midiPlaying: false,
    midiOffset: 0,
    midiStartedAt: 0,
    midiTotal: 0,
  };

  function ensureDom() {
    if (ui.root || typeof document === "undefined") return;
    const style = document.createElement("style");
    style.textContent = [
      ".yue-jp-editor{position:fixed;inset:0;z-index:80;background:rgba(11,13,20,.72);",
      "display:flex;align-items:stretch;justify-content:center;padding:28px 18px;}",
      ".yue-jp-editor[hidden]{display:none;}",
      ".yue-jp-card{width:min(1100px,100%);background:#f6e9c8;color:#2a1f12;border-radius:16px;",
      "box-shadow:0 24px 60px rgba(0,0,0,.45);display:flex;flex-direction:column;overflow:hidden;}",
      ".yue-jp-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:12px 14px;",
      "background:#1a140e;color:#f6e9c8;}",
      ".yue-jp-bar h2{margin:0 8px 0 0;font-size:16px;font-weight:650;}",
      ".yue-jp-bar button{font:inherit;cursor:pointer;border:0;border-radius:8px;}",
      ".yue-jp-bar button{background:#3a2e22;color:#f6e9c8;padding:6px 10px;}",
      ".yue-jp-bar button.icon{display:inline-flex;align-items:center;justify-content:center;",
      "width:32px;height:32px;padding:0;}",
      ".yue-jp-bar button.icon svg{width:15px;height:15px;display:block;fill:currentColor;}",
      ".yue-jp-bar button.on{box-shadow:inset 0 0 0 2px #e85a25;}",
      ".yue-jp-bar button[hidden]{display:none;}",
      ".yue-jp-bar button.primary{background:#e85a25;color:#fff;}",
      ".yue-jp-meta{opacity:.8;font-size:13px;margin-right:auto;}",
      ".yue-jp-tools{display:flex;flex-wrap:wrap;gap:8px 0;align-items:center;",
      "padding:8px 6px 10px;background:#241910;color:#f6e9c8;border-top:1px solid rgba(246,233,200,.14);}",
      ".yue-jp-tools[hidden]{display:none;}",
      ".yue-jp-group{display:flex;flex-wrap:wrap;gap:4px;align-items:center;padding:0 8px;}",
      ".yue-jp-group + .yue-jp-group{border-left:1px solid rgba(246,233,200,.22);}",
      ".yue-jp-tools button{font:inherit;cursor:pointer;border:0;border-radius:8px;",
      "background:#3a2e22;color:#f6e9c8;padding:4px 8px;min-width:28px;}",
      ".yue-jp-tools button.digit{font-weight:700;min-width:32px;}",
      ".yue-jp-tools button.on{box-shadow:inset 0 0 0 2px #e03131;color:#fff;}",
      ".yue-jp-status{min-height:1.4em;padding:8px 14px;color:#8a5a20;font-size:13px;}",
      ".yue-jp-paper{position:relative;overflow:auto;padding:8px 16px 16px;flex:1;}",
      ".yue-jp-paper svg{max-width:100%;height:auto;}",
      ".yue-sel-box{fill:rgba(224,49,49,.16);stroke:#e03131;pointer-events:none;}",
      ".yue-jp-lyric{position:absolute;z-index:3;box-sizing:border-box;font:inherit;",
      "font-weight:700;font-size:15px;padding:4px 8px;",
      "border-radius:8px;border:2px solid #e03131;background:#fffaf0;color:#2a1f12;}",
      ".yue-jp-lyric-line{min-width:220px;width:auto;}",
      ".yue-jp-empty-lyric{position:absolute;z-index:2;cursor:text;color:#a89880;",
      "font-weight:700;font-size:15px;line-height:1;user-select:none;padding:0 2px;}",
      ".yue-jp-empty-lyric.yue-sel{color:#c22525;}",
      "text[data-lyric]{cursor:text;}",
      "text[data-lyric].yue-sel{fill:#c22525;}",
      "text.fj.yue-sel{fill:#c22525;}",
      "text.fj.yue-play{fill:#0b7285;}",
      "line.yue-playhead{stroke:#e03131;stroke-width:2;pointer-events:none;}",
    ].join("");
    document.head.appendChild(style);
    const root = document.createElement("div");
    root.className = "yue-jp-editor";
    root.hidden = true;
    root.innerHTML = [
      '<div class="yue-jp-card" tabindex="-1">',
      '<div class="yue-jp-bar">',
      "<h2>编辑简谱</h2>",
      '<span class="yue-jp-meta"></span>',
      '<button type="button" data-act="mode" data-mode="midi" hidden>MIDI</button>',
      '<button type="button" data-act="mode" data-mode="source" hidden>原声</button>',
      '<button type="button" class="icon" data-act="play" aria-label="播放" title="播放">' + PLAY_ICON + "</button>",
      '<button type="button" class="icon" data-act="stop" aria-label="停止" title="停止">' + STOP_ICON + "</button>",
      '<span class="yue-jp-clock">0:00</span>',
      '<button type="button" data-act="ok" class="primary">完成</button>',
      '<button type="button" data-act="cancel">取消</button>',
      "</div>",
      '<div class="yue-jp-tools" hidden></div>',
      '<div class="yue-jp-status"></div>',
      '<div class="yue-jp-paper"></div>',
      "</div>",
    ].join("");
    document.body.appendChild(root);
    ui.root = root;
    ui.card = root.querySelector(".yue-jp-card");
    ui.meta = root.querySelector(".yue-jp-meta");
    ui.status = root.querySelector(".yue-jp-status");
    ui.paper = root.querySelector(".yue-jp-paper");
    ui.clock = root.querySelector(".yue-jp-clock");
    ui.tools = root.querySelector(".yue-jp-tools");
    fillTools(ui.tools);
    root.addEventListener("click", (ev) => {
      if (ev.target === root) finish(null);
    });
    ui.card.addEventListener("mousedown", (ev) => {
      const button = ev.target.closest && ev.target.closest("button");
      if (!button) return;
      if (button.closest(".yue-jp-tools") || button.getAttribute("data-act") === "ok") {
        ev.preventDefault();
      }
    });
    ui.card.addEventListener("click", (ev) => {
      const button = ev.target.closest && ev.target.closest("button");
      const act = button && button.getAttribute("data-act");
      if (act === "mode") setTransport(button.getAttribute("data-mode"));
      else if (act === "play") togglePlay();
      else if (act === "stop") stopPlayback();
      else if (act === "ok") {
        commitOpenLyric();
        finish(ui.abc);
      }
      else if (act === "cancel") finish(null);
      else if (act === "lyric") beginLyricLine(ui.index);
      else if (button && ui.tools.contains(button)) {
        const command = commandFrom(button);
        if (!command) return;
        commitOpenLyric();
        run(command);
      }
    });
    ui.paper.addEventListener("click", (ev) => {
      const picked = pickedHead(ev.target);
      if (!picked) return;
      selectNote(picked.voice, picked.index, picked.slice);
      if (ui.transport === "source") seekSource(picked);
      if (picked.lyric) {
        if (picked.voice !== "Vocal") {
          setStatus("伴奏没有歌词");
          return;
        }
        beginLyricLine(picked.index);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (!ui.root || ui.root.hidden) return;
      if (ui.lyricInput && event.target === ui.lyricInput) return;
      onKey(event);
    });
  }

  function formatClock(seconds) {
    const safe = Math.max(0, seconds || 0);
    const m = Math.floor(safe / 60);
    const s = Math.floor(safe % 60);
    return m + ":" + String(s).padStart(2, "0");
  }

  function setStatus(text) {
    if (ui.status) ui.status.textContent = text || "";
  }

  function fillTools(root) {
    const groups = [
      ["1", "2", "3", "4", "5", "6", "7", "0"].map((digit) => ({
        label: digit,
        title: digit === "0" ? "休止（0）" : "唱名 " + digit,
        className: "digit",
        attrs: { act: "degree", degree: digit },
      })),
      [
        { label: "↑", title: "升高八度", attrs: { act: "octave", delta: "1" } },
        { label: "↓", title: "降低八度", attrs: { act: "octave", delta: "-1" } },
        { label: "♯", title: "升号（#）", attrs: { act: "accidental", kind: "sharp" } },
        { label: "♭", title: "降号（b）", attrs: { act: "accidental", kind: "flat" } },
        { label: "♮", title: "还原号（n）", attrs: { act: "accidental", kind: "natural" } },
      ],
      [
        { label: "½", title: "时值减半", attrs: { act: "duration", factor: "0.5" } },
        { label: "×2", title: "时值加倍", attrs: { act: "duration", factor: "2" } },
        { label: "附点", title: "附点", attrs: { act: "duration", factor: "1.5" } },
        { label: "延长", title: "延长音节：从后面的休止让出一拍", attrs: { act: "sustain" } },
      ],
      [
        { label: "连音", title: "连音符：接到后面同样的音，再按一次取消", attrs: { act: "tie" } },
        { label: "插入", title: "在这个音后面插入", attrs: { act: "insert" } },
        { label: "删除", title: "删除这个音", attrs: { act: "delete" } },
        { label: "词", title: "改这一行的歌词", attrs: { act: "lyric" } },
      ],
    ];
    groups.forEach((specs) => {
      const group = document.createElement("div");
      group.className = "yue-jp-group";
      specs.forEach((spec) => {
        const button = document.createElement("button");
        button.type = "button";
        if (spec.className) button.className = spec.className;
        button.textContent = spec.label;
        button.title = spec.title;
        Object.keys(spec.attrs).forEach((key) => button.setAttribute("data-" + key, spec.attrs[key]));
        group.appendChild(button);
      });
      root.appendChild(group);
    });
  }

  function commandFrom(button) {
    const act = button.getAttribute("data-act");
    if (act === "degree") return { op: "degree", degree: Number(button.getAttribute("data-degree")) };
    if (act === "octave") return { op: "octave", delta: Number(button.getAttribute("data-delta")) };
    if (act === "accidental") return { op: "accidental", kind: button.getAttribute("data-kind") };
    if (act === "duration") return { op: "duration", factor: Number(button.getAttribute("data-factor")) };
    if (act === "tie" || act === "sustain" || act === "insert" || act === "delete") return { op: act };
    return null;
  }

  function digitNodes(list) {
    return [...list].filter((el) => /^[0-7]$/.test((el.textContent || "").trim()));
  }

  function heads() {
    if (!ui.paper) return [];
    const voiced = digitNodes(ui.paper.querySelectorAll("text.fj.v-Vocal, text.fj.v-Ins"));
    if (voiced.length) return voiced;
    return digitNodes(ui.paper.querySelectorAll("text.fj"));
  }

  function pickedHead(target) {
    const lyric = target && target.closest && (
      target.closest("text[data-lyric]") || target.closest(".yue-jp-empty-lyric")
    );
    if (lyric && lyric.dataset.idx != null && lyric.dataset.idx !== "") {
      const lyricIndex = Number(lyric.dataset.idx);
      if (Number.isInteger(lyricIndex)) {
        return { voice: "Vocal", index: lyricIndex, slice: 0, lyric: true };
      }
    }
    const node = target && target.closest && target.closest("text.fj");
    if (!node || node.dataset.idx == null || node.dataset.idx === "") return null;
    const index = Number(node.dataset.idx);
    if (!Number.isInteger(index)) return null;
    return {
      voice: node.dataset.voice || "Vocal",
      index: index,
      slice: Number(node.dataset.slice || 0),
    };
  }

  function sameHead(el) {
    if (ui.index < 0) return false;
    return (el.dataset.voice || "Vocal") === (ui.voice || "Vocal")
      && Number(el.dataset.idx) === ui.index
      && Number(el.dataset.slice || 0) === (ui.slice || 0);
  }

  function boxInSvg(el) {
    const svg = el.ownerSVGElement;
    if (!svg || !el.getBBox) return null;
    let bb;
    try { bb = el.getBBox(); } catch (err) { return null; }
    if (!(bb.width || bb.height)) return null;
    const screen = el.getScreenCTM && el.getScreenCTM();
    const root = svg.getScreenCTM && svg.getScreenCTM();
    if (!screen || !root || !root.inverse) {
      return { svg: svg, x: bb.x, y: bb.y, w: bb.width, h: bb.height };
    }
    const m = root.inverse().multiply(screen);
    const pts = [
      new DOMPoint(bb.x, bb.y),
      new DOMPoint(bb.x + bb.width, bb.y),
      new DOMPoint(bb.x, bb.y + bb.height),
      new DOMPoint(bb.x + bb.width, bb.y + bb.height),
    ].map((p) => p.matrixTransform(m));
    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);
    const x = Math.min.apply(null, xs);
    const y = Math.min.apply(null, ys);
    return {
      svg: svg,
      x: x,
      y: y,
      w: Math.max.apply(null, xs) - x,
      h: Math.max.apply(null, ys) - y,
    };
  }

  function drawSelectionBox(node) {
    if (!node) return;
    const box = boxInSvg(node);
    if (!box) return;
    const pad = Math.max(3, box.h * 0.22);
    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("class", "yue-sel-box");
    rect.setAttribute("x", String(box.x - pad));
    rect.setAttribute("y", String(box.y - pad));
    rect.setAttribute("width", String(Math.max(1, box.w + pad * 2)));
    rect.setAttribute("height", String(Math.max(1, box.h + pad * 2)));
    rect.setAttribute("rx", String(Math.max(2, pad * 0.45)));
    rect.setAttribute("fill", "rgba(224,49,49,0.16)");
    rect.setAttribute("stroke", "#e03131");
    rect.setAttribute("stroke-width", String(Math.max(1.6, box.h * 0.08)));
    rect.setAttribute("pointer-events", "none");
    box.svg.appendChild(rect);
  }

  function syncTools() {
    if (!ui.tools) return;
    const ev = ui.index >= 0 ? eventsFor(ui.abc, ui.voice)[ui.index] : null;
    ui.tools.hidden = !ev;
    if (!ev) return;
    ui.tools.querySelectorAll("[data-degree]").forEach((btn) => {
      const on = ev.digit === btn.getAttribute("data-degree");
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    ui.tools.querySelectorAll("[data-kind]").forEach((btn) => {
      const on = ev.accidental === btn.getAttribute("data-kind");
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    const tie = ui.tools.querySelector("[data-act='tie']");
    if (tie) {
      tie.classList.toggle("on", !!ev.tie);
      tie.setAttribute("aria-pressed", ev.tie ? "true" : "false");
    }
  }

  function selectNote(voice, index, slice) {
    ui.voice = voice || "Vocal";
    ui.index = index;
    ui.slice = slice || 0;
    if (ui.lyricInput) ui.lyricInput.dispatchEvent(new FocusEvent("blur"));
    else {
      setStatus("");
      markSelection();
    }
  }

  function markSelection() {
    const nodes = heads();
    if (ui.paper) ui.paper.querySelectorAll(".yue-sel-box").forEach((el) => el.remove());
    nodes.forEach((el) => {
      const on = sameHead(el);
      el.classList.toggle("yue-sel", on);
      if (on) drawSelectionBox(el);
    });
    if (ui.paper) {
      ui.paper.querySelectorAll("text[data-lyric], .yue-jp-empty-lyric").forEach((el) => {
        const on = (ui.voice || "Vocal") !== "Ins" && Number(el.dataset.idx) === ui.index;
        el.classList.toggle("yue-sel", on);
      });
    }
    reveal(nodes.find(sameHead));
    syncTools();
  }

  function reveal(node) {
    const host = ui.paper;
    if (!host || !node || !node.getBoundingClientRect) return;
    const box = node.getBoundingClientRect();
    const frame = host.getBoundingClientRect();
    if (box.top < frame.top + 4) host.scrollTop -= frame.top + 4 - box.top;
    else if (box.bottom > frame.bottom - 4) host.scrollTop += box.bottom - (frame.bottom - 4);
  }

  function headFor(mark) {
    if (!mark) return null;
    return heads().find((el) =>
      (el.dataset.voice || "Vocal") === mark.voice
      && Number(el.dataset.idx) === mark.index
      && Number(el.dataset.slice || 0) === mark.slice
    ) || null;
  }

  function systemSpan(svg) {
    const parts = String(svg.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
    if (parts.length === 4 && parts.every((n) => Number.isFinite(n)) && parts[3] > 0) {
      return { y: parts[1], h: parts[3] };
    }
    try {
      const bb = svg.getBBox();
      return { y: bb.y, h: bb.height || 40 };
    } catch (err) {
      return { y: 0, h: 40 };
    }
  }

  function clearPlayhead() {
    if (ui.playhead) ui.playhead.remove();
    ui.playhead = null;
    ui.playKey = "";
  }

  function drawPlayhead(node) {
    const box = boxInSvg(node);
    if (!box) return;
    const span = systemSpan(box.svg);
    const x = Math.max(0.8, box.x - Math.max(1.5, box.w * 0.2));
    let line = ui.playhead;
    if (!line || line.ownerSVGElement !== box.svg) {
      if (line) line.remove();
      line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("class", "yue-playhead");
      line.setAttribute("stroke", "#e03131");
      line.setAttribute("stroke-width", "2");
      line.setAttribute("stroke-linecap", "round");
      line.setAttribute("pointer-events", "none");
      box.svg.appendChild(line);
      ui.playhead = line;
    }
    line.setAttribute("x1", String(x));
    line.setAttribute("x2", String(x));
    line.setAttribute("y1", String(span.y + 2));
    line.setAttribute("y2", String(span.y + Math.max(8, span.h - 2)));
  }

  function followPlayhead(node) {
    const host = ui.paper;
    if (!host || !node || !node.getBoundingClientRect) return;
    const box = node.getBoundingClientRect();
    const frame = host.getBoundingClientRect();
    const margin = 48;
    if (box.bottom > frame.bottom - margin) {
      host.scrollTop += box.top - (frame.top + margin);
    } else if (box.top < frame.top + 8) {
      host.scrollTop -= frame.top + 8 - box.top;
    }
    if (box.right > frame.right - 16) {
      host.scrollLeft += box.right - (frame.right - 16);
    } else if (box.left < frame.left + 8) {
      host.scrollLeft -= frame.left + 8 - box.left;
    }
  }

  const ABC2SVG_SRC = "/gradio_api/file=static/abc2svg/abc2svg-1.js";
  const JIANPU_SRC = "/gradio_api/file=static/abc2svg/jianpu-1.js";

  function jianpuReady() {
    return typeof abc2svg !== "undefined" && !!abc2svg.Abc && !!abc2svg.jianpu;
  }

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.onload = () => resolve();
      el.onerror = () => reject(new Error(src));
      document.head.appendChild(el);
    });
  }

  let jianpuLoading = null;
  function ensureJianpu() {
    if (jianpuReady()) return Promise.resolve(true);
    if (jianpuLoading) return jianpuLoading;
    jianpuLoading = (async () => {
      if (typeof abc2svg === "undefined" || !abc2svg.Abc) {
        await loadScript(ABC2SVG_SRC);
      }
      if (typeof abc2svg === "undefined" || !abc2svg.jianpu) {
        await loadScript(JIANPU_SRC);
      }
      return jianpuReady();
    })().catch((err) => {
      jianpuLoading = null;
      throw err;
    });
    return jianpuLoading;
  }

  function renderScore() {
    if (ui.lyricInput) ui.lyricInput = null;
    ui.marks = playMarks(ui.abc);
    ui.playhead = null;
    ui.playKey = "";
    const info = inspectScore(ui.abc);
    ui.meta.textContent = info.error ? "" : "1=" + info.keyName + "  ·  ♩=" + info.bpm;
    if (typeof abc2svg === "undefined" || !abc2svg.Abc || !abc2svg.jianpu) {
      ui.paper.innerHTML = "<p>简谱模块没有载入。</p>";
      return;
    }
    const buf = [];
    try {
      const renderer = new abc2svg.Abc({
        img_out: (svg) => buf.push(svg),
        errbld: () => {},
        errmsg: () => {},
        read_file: () => "",
      });
      renderer.tosvg("jianpu", previewAbc(ui.abc));
    } catch (err) {
      ui.paper.textContent = "简谱渲染失败";
      return;
    }
    ui.paper.innerHTML = buf.join("") || "<p>简谱是空的。</p>";
    const vocalOk = stampVoice("Vocal");
    const insOk = stampVoice("Ins");
    stampLyrics();
    if (!vocalOk) setStatus("简谱上的音和人声对不上。");
    else if (!insOk) setStatus("伴奏谱上的音对不上。");
    if (ui.index >= 0) {
      const pool = eventsFor(ui.abc, ui.voice);
      if (ui.index >= pool.length) {
        ui.index = pool.length ? pool.length - 1 : -1;
        ui.slice = 0;
      }
    }
    markSelection();
    if (ui.transport === "source" && ui.audio && ui.audioUrl && (ui.sourceTouched || !ui.audio.paused)) {
      paintPlayhead(ui.audio.currentTime || 0);
    }
  }

  function stampVoice(voice) {
    const nodes = digitNodes(ui.paper.querySelectorAll("text.fj.v-" + voice));
    if (!nodes.length) return true;
    const indexes = headIndexes(ui.abc, voice);
    if (indexes.length !== nodes.length) return false;
    const seen = new Map();
    nodes.forEach((el, i) => {
      const index = indexes[i];
      const slice = seen.has(index) ? seen.get(index) : 0;
      seen.set(index, slice + 1);
      el.dataset.voice = voice;
      el.dataset.idx = String(index);
      el.dataset.slice = String(slice);
    });
    return true;
  }

  function stampLyrics() {
    if (!ui.paper || !ui.paper.querySelectorAll) return;
    ui.paper.querySelectorAll(".yue-jp-empty-lyric").forEach((el) => el.remove());
    const vocal = heads().filter((el) => el.dataset.voice === "Vocal");
    const events = eventsFor(ui.abc, "Vocal");
    const drawn = {};
    events.forEach((ev) => {
      if (lyricIsDrawn(ev.lyric)) drawn[ev.index] = true;
    });
    const headBoxes = [];
    vocal.forEach((el) => {
      if (!el.getBoundingClientRect) return;
      const box = el.getBoundingClientRect();
      if (!(box.width || box.height)) return;
      headBoxes.push({
        x: (box.left + box.right) / 2,
        y: (box.top + box.bottom) / 2,
        h: box.height,
        index: Number(el.dataset.idx),
        voice: "Vocal",
      });
    });
    const glyphs = [];
    ui.paper.querySelectorAll("text").forEach((el) => {
      if (el.classList.contains("fj") || el.classList.contains("jacc")) return;
      const cls = el.getAttribute("class") || "";
      if (!/(?:^|\s)f\d+/.test(cls)) return;
      const text = (el.textContent || "").replace(/\s+/g, "");
      if (!text || text === "唱" || text === "伴" || text.indexOf("=") >= 0) return;
      if (!el.getBoundingClientRect) return;
      const box = el.getBoundingClientRect();
      if (!(box.width || box.height)) return;
      glyphs.push({
        el: el,
        x: (box.left + box.right) / 2,
        y: (box.top + box.bottom) / 2,
      });
    });
    const heights = headBoxes.map((head) => head.h).filter((h) => h > 0).sort((a, b) => a - b);
    const noteH = heights.length ? heights[(heights.length / 2) | 0] : 16;
    const hits = assignLyricHits(headBoxes, glyphs, drawn, {
      rowSlack: Math.max(4, noteH * 0.6),
      maxGap: Math.max(48, noteH * 4),
    });
    const hitIndexes = new Set();
    hits.forEach((hit) => {
      hitIndexes.add(hit.index);
      const el = hit.glyph.el;
      el.dataset.lyric = "1";
      el.dataset.voice = "Vocal";
      el.dataset.idx = String(hit.index);
      el.setAttribute("role", "button");
      el.setAttribute("aria-label", "歌词 " + (el.textContent || "").replace(/\s+/g, ""));
    });
    const host = ui.paper.getBoundingClientRect();
    events.forEach((ev) => {
      if (ev.kind !== "note") return;
      if (hitIndexes.has(ev.index)) return;
      const head = vocal.find((el) => Number(el.dataset.idx) === ev.index);
      if (!head || !head.getBoundingClientRect) return;
      const box = head.getBoundingClientRect();
      if (!(box.width || box.height)) return;
      const span = document.createElement("span");
      span.className = "yue-jp-empty-lyric";
      span.dataset.lyric = "1";
      span.dataset.voice = "Vocal";
      span.dataset.idx = String(ev.index);
      span.setAttribute("role", "button");
      span.setAttribute("aria-label", "空歌词");
      span.textContent = "·";
      const left = box.left - host.left + ui.paper.scrollLeft + box.width / 2 - 5;
      const top = box.bottom - host.top + ui.paper.scrollTop + Math.max(2, noteH * 0.15);
      span.style.left = left + "px";
      span.style.top = top + "px";
      ui.paper.appendChild(span);
    });
  }

  function beginLyricLine(index) {
    if (ui.lyricInput) ui.lyricInput.blur();
    const parsed = collect(ui.abc);
    if (parsed.error) {
      setStatus(parsed.error);
      return;
    }
    const ev = parsed.events[index];
    if (!ev || ev.kind !== "note") {
      setStatus(index < 0 ? "先点一个音符" : "休止的歌词是 *");
      return;
    }
    ui.voice = "Vocal";
    ui.index = index;
    ui.slice = 0;
    ui.lyricIndex = index;
    markSelection();
    const lineNotes = parsed.events.filter((item) => item.line === ev.line && item.kind === "note");
    const value = lineLyricText(parsed.events, ev.line);
    const input = document.createElement("input");
    input.className = "yue-jp-lyric yue-jp-lyric-line";
    input.setAttribute("aria-label", "这一行的歌词");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("spellcheck", "false");
    input.value = value;
    placeLyricLineInput(input, lineNotes);
    ui.paper.appendChild(input);
    ui.lyricInput = input;
    let composing = false;
    let commitAfterCompose = false;
    const commit = () => {
      if (ui.lyricInput !== input) return;
      ui.lyricInput = null;
      try {
        run({ op: "lyric-line", index: index, voice: "Vocal", slice: null, text: input.value });
      } catch (err) {
        setStatus(String(err && err.message || err));
      }
    };
    input.addEventListener("compositionstart", () => { composing = true; });
    input.addEventListener("compositionend", () => {
      composing = false;
      if (commitAfterCompose) commit();
    });
    input.addEventListener("keydown", (event) => {
      event.stopPropagation();
      if (event.isComposing || event.keyCode === 229) return;
      if (event.key === "Enter") {
        event.preventDefault();
        commit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        ui.lyricInput = null;
        renderScore();
        setStatus(playHint());
      }
    });
    input.addEventListener("blur", () => {
      if (composing) {
        commitAfterCompose = true;
        return;
      }
      commit();
    });
    const tokenAt = lineNotes.findIndex((item) => item.index === index);
    input.focus({ preventScroll: true });
    if (tokenAt >= 0) {
      const parts = value.split(/\s+/);
      let start = 0;
      for (let i = 0; i < tokenAt; i++) start += (parts[i] || "").length + 1;
      const end = start + (parts[tokenAt] || "").length;
      try {
        input.setSelectionRange(start, end);
      } catch (_err) {
        input.select();
      }
    } else {
      input.select();
    }
    setStatus("回车确认这一行。Esc 取消。");
    playMidi(noteMidi(ui.abc, index, "Vocal"));
  }

  function placeLyricLineInput(input, lineNotes) {
    if (!ui.paper || !lineNotes || !lineNotes.length) return;
    const host = ui.paper.getBoundingClientRect();
    const indexes = new Set(lineNotes.map((ev) => ev.index));
    const lyricEls = [];
    ui.paper.querySelectorAll("text[data-lyric], .yue-jp-empty-lyric").forEach((el) => {
      if (indexes.has(Number(el.dataset.idx))) lyricEls.push(el);
    });
    const headEls = heads().filter((el) =>
      (el.dataset.voice || "Vocal") === "Vocal" && indexes.has(Number(el.dataset.idx))
    );
    const boxes = (lyricEls.length ? lyricEls : headEls)
      .map((el) => el.getBoundingClientRect && el.getBoundingClientRect())
      .filter((box) => box && (box.width || box.height));
    if (!boxes.length) return;
    const left = Math.min.apply(null, boxes.map((box) => box.left));
    const right = Math.max.apply(null, boxes.map((box) => box.right));
    const bottom = Math.max.apply(null, boxes.map((box) => box.bottom));
    const topBase = lyricEls.length
      ? Math.max.apply(null, boxes.map((box) => box.bottom))
      : bottom;
    input.style.left = (left - host.left + ui.paper.scrollLeft) + "px";
    input.style.top = (topBase - host.top + ui.paper.scrollTop + 4) + "px";
    const width = Math.max(220, Math.round(right - left + 24));
    input.style.width = width + "px";
    input.style.minWidth = width + "px";
  }

  function run(command) {
    stopPlayback();
    if (ui.index < 0) {
      setStatus("先点一个音符");
      return false;
    }
    const next = editScore(ui.abc, Object.assign({
      index: ui.index,
      voice: ui.voice || "Vocal",
      slice: ui.slice || 0,
    }, command));
    if (next.error) {
      setStatus(next.error);
      return false;
    }
    ui.abc = next.abc;
    if (command.index == null) {
      if (next.index != null) ui.index = next.index;
      ui.slice = 0;
    }
    if (next.leftover) setStatus("还有 " + next.leftover + " 个字没有音符");
    else setStatus("");
    renderScore();
    if (next.leftover && ui.status && !ui.status.textContent) {
      setStatus("还有 " + next.leftover + " 个字没有音符");
    }
    if (command.op === "degree" || command.op === "octave" || command.op === "accidental") {
      playMidi(noteMidi(ui.abc, ui.index, ui.voice));
    }
    return true;
  }

  function onKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (ui.lyricInput) return;
    const key = event.key;
    if (key === "Enter") {
      if ((ui.voice || "Vocal") === "Ins") return;
      event.preventDefault();
      beginLyricLine(ui.index);
      return;
    }
    if (key === "ArrowLeft" || key === "ArrowRight") {
      event.preventDefault();
      const nodes = heads();
      if (!nodes.length) return;
      const step = key === "ArrowLeft" ? -1 : 1;
      let pos = nodes.findIndex(sameHead);
      if (pos < 0) pos = step < 0 ? nodes.length - 1 : 0;
      else pos = Math.max(0, Math.min(nodes.length - 1, pos + step));
      const node = nodes[pos];
      selectNote(node.dataset.voice || "Vocal", Number(node.dataset.idx), Number(node.dataset.slice || 0));
      return;
    }
    const command = commandOfKey(key);
    if (!command) return;
    event.preventDefault();
    run(command);
  }

  function commandOfKey(key) {
    if (/^[0-7]$/.test(key)) return { op: "degree", degree: Number(key) };
    if (key === "ArrowUp") return { op: "octave", delta: 1 };
    if (key === "ArrowDown") return { op: "octave", delta: -1 };
    if (key === "#") return { op: "accidental", kind: "sharp" };
    if (key === "b") return { op: "accidental", kind: "flat" };
    if (key === "n") return { op: "accidental", kind: "natural" };
    if (key === "_") return { op: "duration", factor: 0.5 };
    if (key === "=") return { op: "duration", factor: 2 };
    if (key === ".") return { op: "duration", factor: 1.5 };
    if (key === "-") return { op: "sustain" };
    if (key === "t") return { op: "tie" };
    if (key === "Delete" || key === "Backspace") return { op: "delete" };
    if (key === "+") return { op: "insert" };
    return null;
  }

  function playMidi(midi) {
    if (typeof window === "undefined" || midi == null) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx || !window.yuePiano) return;
    ui.ctx = ui.ctx || new AudioCtx();
    const ctx = ui.ctx;
    if (ctx.state === "suspended" && ctx.resume) ctx.resume();
    const known = window.yuePiano.voice && window.yuePiano.voice(ctx);
    const previous = ui.status ? ui.status.textContent : "";
    if (!known) setStatus("正在加载钢琴音色");
    const loading = window.yuePiano.prepare ? window.yuePiano.prepare(ctx) : Promise.resolve(null);
    Promise.resolve(loading).then(function (voice) {
      if (!known && ui.status && ui.status.textContent === "正在加载钢琴音色") {
        setStatus(voice && voice.kind === "synthetic" ? "采样钢琴加载失败，改用合成音色" : previous);
      }
      window.yuePiano.schedule(ctx, { midi: midi, volume: 0.18 }, ctx.currentTime + 0.02, 0.42, ui.osc);
    });
  }

  function playbackTransport(hasSource, mode) {
    return hasSource && mode === "source" ? "source" : "midi";
  }

  // The red cursor tracks the score clock. Source audio is the original
  // recording, so that line stays off while it plays.
  function showsPlayhead(transport) {
    return transport !== "source";
  }

  function playHint() {
    if (ui.audioUrl) {
      return "点唱谱或伴奏上的一个音来改，会响起这个音。可播放 MIDI 或源音频；听源音频时点简谱可跳转。单击歌词改这一行。";
    }
    return "点唱谱或伴奏上的一个音来改，会响起这个音。单击歌词改这一行。";
  }

  function syncTransport() {
    if (!ui.audioUrl) ui.transport = "midi";
    if (!ui.root) return;
    const show = !!ui.audioUrl;
    ui.root.querySelectorAll("[data-act='mode']").forEach((button) => {
      const mode = button.getAttribute("data-mode");
      const on = show && mode === ui.transport;
      button.hidden = !show;
      button.classList.toggle("on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function setTransport(mode) {
    const next = playbackTransport(!!ui.audioUrl, mode);
    if (next === ui.transport) return;
    stopPlayback();
    ui.transport = next;
    syncTransport();
    setStatus(playHint());
  }

  function setPlayLabel(text) {
    if (!ui.root) return;
    const button = ui.root.querySelector("[data-act='play']");
    if (!button) return;
    const playing = text === "暂停";
    button.innerHTML = playing ? PAUSE_ICON : PLAY_ICON;
    button.setAttribute("aria-label", playing ? "暂停" : "播放");
    button.setAttribute("aria-pressed", playing ? "true" : "false");
    button.title = playing ? "暂停" : "播放";
  }

  function setPlayClock(now, total) {
    if (!ui.clock) return;
    const shown = Math.max(0, now || 0);
    if (total > 0) ui.clock.textContent = formatClock(shown) + " / " + formatClock(total);
    else ui.clock.textContent = formatClock(shown);
  }

  function paintPlayhead(now) {
    if (!showsPlayhead(ui.transport)) {
      clearPlayhead();
      return;
    }
    const marks = ui.marks && ui.marks.length ? ui.marks : playMarks(ui.abc);
    ui.marks = marks;
    const mark = cursorAt(marks, Math.max(0, now || 0));
    if (!mark) {
      clearPlayhead();
      return;
    }
    const playKey = mark.voice + ":" + mark.index + ":" + mark.slice;
    const node = headFor(mark);
    if (!node) return;
    if (playKey !== ui.playKey || !ui.playhead) {
      ui.playKey = playKey;
      drawPlayhead(node);
      followPlayhead(node);
    }
  }

  function abandonSource(message) {
    ui.generation += 1;
    if (ui.raf) cancelAnimationFrame(ui.raf);
    ui.raf = 0;
    if (ui.audio) ui.audio.pause();
    ui.audio = null;
    ui.audioUrl = "";
    ui.sourceTouched = false;
    ui.transport = "midi";
    syncTransport();
    setPlayLabel("播放");
    setStatus(message);
  }

  function ensureAudio() {
    if (!ui.audioUrl || typeof Audio === "undefined") return null;
    if (ui.audio) return ui.audio;
    let audio;
    try {
      audio = new Audio(ui.audioUrl);
    } catch (err) {
      abandonSource("源音频打不开，改为试听简谱。");
      return null;
    }
    audio.preload = "auto";
    audio.addEventListener("error", () => {
      if (ui.audio !== audio || !ui.audioUrl) return;
      abandonSource("源音频打不开，改为试听简谱。");
    });
    audio.addEventListener("ended", () => {
      if (ui.audio !== audio) return;
      ui.generation += 1;
      if (ui.raf) cancelAnimationFrame(ui.raf);
      ui.raf = 0;
      setPlayLabel("播放");
      paintPlayhead(audio.currentTime || 0);
    });
    ui.audio = audio;
    return audio;
  }

  function attachSource(audioFile) {
    const next = fileUrl(audioFile);
    if (next !== ui.audioUrl) {
      if (ui.audio) ui.audio.pause();
      ui.audio = null;
      ui.audioUrl = next;
    }
    if (ui.audioUrl) ensureAudio();
  }

  function seekSource(picked) {
    if (!ui.audioUrl) return;
    const audio = ui.audio || ensureAudio();
    if (!audio || !picked) return;
    const marks = ui.marks && ui.marks.length ? ui.marks : playMarks(ui.abc);
    ui.marks = marks;
    const time = markTime(marks, picked.voice, picked.index, picked.slice);
    if (time == null) return;
    const apply = () => {
      if (ui.audio !== audio) return;
      try { audio.currentTime = time; } catch (err) { return; }
      ui.sourceTouched = true;
      paintPlayhead(time);
      const total = Number.isFinite(audio.duration) ? audio.duration : 0;
      setPlayClock(time, total);
    };
    if (audio.readyState >= 1) apply();
    else audio.addEventListener("loadedmetadata", apply, { once: true });
  }

  function tickSource(audio, generation) {
    if (ui.generation !== generation || ui.audio !== audio) return;
    const now = audio.currentTime || 0;
    const total = Number.isFinite(audio.duration) ? audio.duration : 0;
    setPlayClock(now, total);
    paintPlayhead(now);
    if (!audio.paused && !audio.ended) ui.raf = requestAnimationFrame(() => tickSource(audio, generation));
  }

  function toggleSource() {
    const audio = ensureAudio();
    if (!audio) return;
    if (!audio.paused && !audio.ended) {
      audio.pause();
      ui.generation += 1;
      if (ui.raf) cancelAnimationFrame(ui.raf);
      ui.raf = 0;
      ui.sourceTouched = true;
      setPlayLabel("播放");
      paintPlayhead(audio.currentTime || 0);
      return;
    }
    if (audio.ended || (Number.isFinite(audio.duration) && audio.currentTime >= audio.duration - 0.02)) {
      try { audio.currentTime = 0; } catch (err) { /* metadata not ready yet */ }
    }
    const generation = ++ui.generation;
    ui.sourceTouched = true;
    const started = audio.play();
    if (started && typeof started.catch === "function") {
      started.catch(() => {
        if (ui.generation !== generation) return;
        abandonSource("源音频打不开，改为试听简谱。");
      });
    }
    setPlayLabel("暂停");
    tickSource(audio, generation);
  }

  function soundingNotes(notes, offset) {
    const at = Math.max(0, offset || 0);
    const queued = [];
    for (const note of notes || []) {
      const end = note.start + note.duration;
      if (end <= at + 1e-4) continue;
      queued.push({
        note: note,
        delay: Math.max(0, note.start - at),
        duration: end - Math.max(at, note.start),
      });
    }
    return queued;
  }

  // A five-minute score is more than a thousand notes. Scheduling every one
  // at play time stalls the audio thread: the clock still advances, but the
  // speakers stay silent. Arm only the notes that start inside the lookahead.
  function pumpMidi(queue, now, ahead) {
    const horizon = now + (ahead == null ? 1.5 : ahead);
    const due = [];
    for (const item of queue || []) {
      if (!item || item.armed) continue;
      const note = item.note;
      if (!note || note.start > horizon) continue;
      item.armed = true;
      if (note.start + note.duration > now + 0.02) due.push(item);
    }
    return due;
  }

  function silenceMidi() {
    for (const node of ui.osc) {
      try { if (node.stop) node.stop(); } catch (err) { /* already stopped */ }
      try { if (node.disconnect) node.disconnect(); } catch (err) {}
    }
    ui.osc = [];
  }

  function midiNow() {
    if (!ui.midiPlaying || !ui.ctx) return ui.midiOffset || 0;
    const elapsed = ui.ctx.currentTime - ui.midiStartedAt;
    return Math.min(ui.midiTotal || 0, Math.max(0, (ui.midiOffset || 0) + elapsed));
  }

  function stopPlayback() {
    ui.generation += 1;
    ui.arming = false;
    ui.midiPlaying = false;
    ui.midiOffset = 0;
    ui.midiStartedAt = 0;
    ui.midiTotal = 0;
    if (ui.raf) cancelAnimationFrame(ui.raf);
    ui.raf = 0;
    silenceMidi();
    if (ui.audio) {
      ui.audio.pause();
      try { ui.audio.currentTime = 0; } catch (err) { /* not seekable yet */ }
    }
    ui.sourceTouched = false;
    heads().forEach((el) => el.classList.remove("yue-play"));
    clearPlayhead();
    setPlayLabel("播放");
    if (ui.clock) ui.clock.textContent = "0:00";
  }

  function pauseMidi() {
    const position = midiNow();
    ui.generation += 1;
    ui.arming = false;
    ui.midiPlaying = false;
    if (ui.raf) cancelAnimationFrame(ui.raf);
    ui.raf = 0;
    silenceMidi();
    ui.midiOffset = Math.max(0, position);
    setPlayLabel("播放");
    if (ui.midiTotal > 0) {
      setPlayClock(ui.midiOffset, ui.midiTotal);
      paintPlayhead(ui.midiOffset);
    }
  }

  function playMidiFrom(position) {
    const score = timeline(ui.abc);
    if (score.error || !score.notes.length) {
      setStatus(score.error || "没有可播放的音符");
      return;
    }
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
      setStatus("这个浏览器不能播放 MIDI");
      return;
    }
    if (!window.yuePiano) {
      setStatus("钢琴音色未加载");
      return;
    }
    const total = score.notes.reduce((max, note) => Math.max(max, note.start + note.duration), 0);
    let offset = Math.max(0, position || 0);
    if (offset >= Math.max(0.02, total - 0.02)) offset = 0;
    ui.ctx = ui.ctx || new AudioCtx();
    if (ui.ctx.state === "suspended" && ui.ctx.resume) ui.ctx.resume();
    ui.arming = true;
    ui.midiTotal = total;
    setPlayLabel("暂停");
    const known = window.yuePiano.voice && window.yuePiano.voice(ui.ctx);
    if (!known) setStatus("正在加载钢琴音色");
    const generation = ++ui.generation;
    const loading = window.yuePiano.prepare ? window.yuePiano.prepare(ui.ctx) : Promise.resolve(null);
    Promise.resolve(loading).then(function (voice) {
      if (ui.generation !== generation) return;
      ui.arming = false;
      silenceMidi();
      const t0 = ui.ctx.currentTime + 0.05;
      ui.midiPlaying = true;
      ui.midiOffset = offset;
      ui.midiStartedAt = t0;
      ui.midiTotal = total;
      const queue = soundingNotes(score.notes, offset);
      const pump = () => {
        const elapsed = ui.ctx.currentTime - ui.midiStartedAt;
        const now = Math.min(total, ui.midiOffset + Math.max(0, elapsed));
        for (const item of pumpMidi(queue, now)) {
          window.yuePiano.schedule(
            ui.ctx,
            {
              midi: item.note.midi,
              volume: item.note.volume || 0.16,
              velocity: item.note.velocity,
            },
            ui.midiStartedAt + item.delay,
            Math.max(0.06, item.duration),
            ui.osc,
          );
        }
        return now;
      };
      setStatus(voice && voice.kind === "synthetic" ? "采样钢琴加载失败，改用合成音色" : playHint());
      const marks = playMarks(ui.abc);
      ui.marks = marks;
      const tick = () => {
        if (ui.generation !== generation || !ui.midiPlaying) return;
        const now = pump();
        setPlayClock(now, total);
        const active = new Set();
        for (const note of score.notes) {
          if (now >= note.start && now < note.start + note.duration) {
            note.indexes.forEach((index) => active.add((note.voice || "Vocal") + ":" + index));
          }
        }
        heads().forEach((el) => {
          const key = (el.dataset.voice || "Vocal") + ":" + el.dataset.idx;
          el.classList.toggle("yue-play", active.has(key));
        });
        const mark = cursorAt(marks, Math.max(0, now));
        const playKey = mark ? mark.voice + ":" + mark.index + ":" + mark.slice : "";
        if (playKey !== ui.playKey) {
          const node = headFor(mark);
          if (node) {
            ui.playKey = playKey;
            drawPlayhead(node);
            followPlayhead(node);
          }
        }
        if (now < total - 0.02) ui.raf = requestAnimationFrame(tick);
        else stopPlayback();
      };
      setPlayLabel("暂停");
      tick();
    }).catch(function (err) {
      if (ui.generation !== generation) return;
      ui.arming = false;
      ui.midiPlaying = false;
      setPlayLabel("播放");
      setStatus(String((err && err.message) || err));
    });
  }

  function togglePlay() {
    if (ui.transport === "source" && ui.audioUrl) {
      toggleSource();
      return;
    }
    if (ui.midiPlaying || ui.arming) {
      pauseMidi();
      return;
    }
    playMidiFrom(ui.midiOffset);
  }

  function commitOpenLyric() {
    const input = ui.lyricInput;
    if (!input) return;
    const lyricIndex = ui.lyricIndex;
    const text = input.value;
    ui.lyricInput = null;
    run({ op: "lyric-line", index: lyricIndex, voice: "Vocal", slice: null, text: text });
  }

  function finish(value) {
    stopPlayback();
    if (ui.lyricInput) {
      ui.lyricInput = null;
    }
    if (ui.root) ui.root.hidden = true;
    const resolve = ui.resolve;
    ui.resolve = null;
    if (resolve) resolve(value);
  }

  function open(abc, audioFile) {
    ensureDom();
    stopPlayback();
    attachSource(audioFile);
    ui.transport = playbackTransport(!!ui.audioUrl, "source");
    syncTransport();
    if (ui.resolve) ui.resolve(null);
    return new Promise((resolve) => {
      ui.abc = String(abc || "");
      ui.index = -1;
      ui.voice = "Vocal";
      ui.slice = 0;
      ui.resolve = resolve;
      setStatus(playHint());
      if (ui.clock) ui.clock.textContent = "0:00";
      ui.root.hidden = false;
      ensureJianpu().then((ok) => {
        if (ui.resolve !== resolve) return;
        if (!ok) {
          ui.paper.innerHTML = "<p>简谱模块没有载入。</p>";
          return;
        }
        renderScore();
      }).catch(() => {
        if (ui.resolve !== resolve) return;
        ui.paper.innerHTML = "<p>简谱模块没有载入。</p>";
      });
      ui.card.focus();
    });
  }

  return {
    DURATIONS: DURATIONS,
    editScore: editScore,
    listEvents: listEvents,
    timeline: timeline,
    spellChord: spellChord,
    soundingNotes: soundingNotes,
    pumpMidi: pumpMidi,
    playMarks: playMarks,
    cursorAt: cursorAt,
    markTime: markTime,
    fileUrl: fileUrl,
    playbackTransport: playbackTransport,
    showsPlayhead: showsPlayhead,
    inspectScore: inspectScore,
    previewAbc: previewAbc,
    noteMidi: noteMidi,
    jianpuAbcWithDirective: jianpuAbcWithDirective,
    ensureJianpu: ensureJianpu,
    countHeads: countHeads,
    headIndexes: headIndexes,
    lyricIsDrawn: lyricIsDrawn,
    assignLyricHits: assignLyricHits,
    splitLyricLine: splitLyricLine,
    commandOfKey: commandOfKey,
    open: open,
  };
});

/**
 * Jianpu editor for Yue Studio.
 * The page shows the vocal staff (唱) and the accompaniment staff (伴).
 * Both staves edit in the browser. w: lyrics stay on the vocal staff.
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
        });
        barUnits += units;
        pendingTie = false;
        i += zrest[0].length;
        continue;
      }
      const match = TOKEN.exec(line.slice(i));
      if (!match) return { error: "读不懂这里的记号" };
      const raw = match[0];
      if (match[1] != null) {
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
      });
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
      const tokens = group.map(lyricToken);
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
    } else {
      return { abc: abc, error: "不支持这个修改" };
    }

    if (op === "insert") select = index + 1;
    if (op === "delete" && ev.removed) select = Math.max(0, index - 1);
    const lines = parsed.lines.slice();
    rewriteMusic(lines, events);
    if (lyricsDirty && voice !== "Ins") rewriteLyrics(lines, events);
    return { abc: joinAbc(lines, abc), error: null, index: select };
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

  function scheduleVoice(events, quarter, voice) {
    let units = 0;
    let barKey = null;
    let local = {};
    const notes = [];
    for (const ev of events) {
      const key = ev.line + ":" + ev.barIndex;
      if (key !== barKey) {
        barKey = key;
        local = {};
      }
      const startQ = units * quarter;
      units += ev.units;
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
    return notes;
  }

  function timeline(abc) {
    const parsed = collect(abc);
    if (parsed.error) return { bpm: 120, notes: [], error: parsed.error };
    const quarter = 4 / parsed.header.lDen;
    const notes = scheduleVoice(parsed.events, quarter, "Vocal")
      .concat(scheduleVoice(parsed.ins || [], quarter, "Ins"));
    const bpm = parsed.header.bpm || 120;
    return {
      bpm: bpm,
      error: null,
      notes: notes.map((note) => ({
        midi: note.midi,
        voice: note.voice,
        start: note.startQ * 60 / bpm,
        duration: (note.endQ - note.startQ) * 60 / bpm,
        indexes: note.indexes,
      })),
    };
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
    ctx: null,
    osc: [],
    raf: 0,
    lyricInput: null,
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
      ".yue-jp-lyric{position:absolute;z-index:2;width:4.5em;font:inherit;padding:2px 6px;",
      "border-radius:8px;border:2px solid #e03131;background:#fffaf0;color:#2a1f12;}",
      "text.fj.yue-sel{fill:#c22525;}",
      "text.fj.yue-play{fill:#0b7285;}",
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
      '<button type="button" data-act="play">播放</button>',
      '<button type="button" data-act="stop">停止</button>',
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
      const button = ev.target.closest && ev.target.closest(".yue-jp-tools button");
      if (button) ev.preventDefault();
    });
    ui.card.addEventListener("click", (ev) => {
      const button = ev.target.closest && ev.target.closest("button");
      const act = button && button.getAttribute("data-act");
      if (act === "play") togglePlay();
      else if (act === "stop") stopPlayback();
      else if (act === "ok") finish(ui.abc);
      else if (act === "cancel") finish(null);
      else if (button && ui.tools.contains(button)) {
        const command = commandFrom(button);
        if (!command) return;
        if (ui.lyricInput) {
          const input = ui.lyricInput;
          const lyricIndex = ui.lyricIndex;
          ui.lyricInput = null;
          run({ op: "lyric", index: lyricIndex, voice: "Vocal", slice: null, text: input.value });
        }
        run(command);
      }
    });
    ui.paper.addEventListener("click", (ev) => {
      const picked = pickedHead(ev.target);
      if (!picked) return;
      selectNote(picked.voice, picked.index, picked.slice);
    });
    ui.paper.addEventListener("dblclick", (ev) => {
      const picked = pickedHead(ev.target);
      if (!picked) return;
      if (picked.voice !== "Vocal") {
        setStatus("伴奏没有歌词");
        return;
      }
      ev.preventDefault();
      beginLyric(picked.index);
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

  function renderScore() {
    if (ui.lyricInput) ui.lyricInput = null;
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

  function beginLyric(index) {
    if (ui.lyricInput) ui.lyricInput.blur();
    const info = inspectScore(ui.abc);
    const ev = info.events[index];
    if (!ev || ev.kind !== "note") {
      setStatus("休止的歌词是 *");
      return;
    }
    ui.voice = "Vocal";
    ui.index = index;
    ui.slice = 0;
    ui.lyricIndex = index;
    markSelection();
    const node = heads().find(sameHead);
    const input = document.createElement("input");
    input.className = "yue-jp-lyric";
    input.setAttribute("aria-label", "歌词");
    input.value = ev.lyric && ev.lyric !== "*" ? ev.lyric : "";
    if (node) {
      const box = node.getBoundingClientRect();
      const host = ui.paper.getBoundingClientRect();
      input.style.left = (box.left - host.left + ui.paper.scrollLeft) + "px";
      input.style.top = (box.bottom - host.top + ui.paper.scrollTop + 2) + "px";
    }
    ui.paper.appendChild(input);
    ui.lyricInput = input;
    const commit = () => {
      if (ui.lyricInput !== input) return;
      ui.lyricInput = null;
      try {
        run({ op: "lyric", index: index, voice: "Vocal", slice: null, text: input.value });
      } catch (err) {
        setStatus(String(err && err.message || err));
      }
    };
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
      }
    });
    input.addEventListener("blur", commit);
    input.focus();
    input.select();
  }

  function run(command) {
    stopPlayback();
    if (ui.index < 0) {
      setStatus("先点一个音符");
      return;
    }
    const next = editScore(ui.abc, Object.assign({
      index: ui.index,
      voice: ui.voice || "Vocal",
      slice: ui.slice || 0,
    }, command));
    if (next.error) {
      setStatus(next.error);
      return;
    }
    ui.abc = next.abc;
    if (command.index == null) {
      if (next.index != null) ui.index = next.index;
      ui.slice = 0;
    }
    setStatus("");
    renderScore();
    if (command.op === "degree" || command.op === "octave" || command.op === "accidental") {
      playMidi(noteMidi(ui.abc, ui.index, ui.voice));
    }
  }

  function onKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (ui.lyricInput) return;
    const key = event.key;
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
    if (!AudioCtx) return;
    ui.ctx = ui.ctx || new AudioCtx();
    if (ui.ctx.state === "suspended") ui.ctx.resume();
    const osc = ui.ctx.createOscillator();
    const gain = ui.ctx.createGain();
    osc.type = "triangle";
    osc.frequency.value = 440 * Math.pow(2, (midi - 69) / 12);
    const when = ui.ctx.currentTime + 0.02;
    const dur = 0.42;
    gain.gain.setValueAtTime(0.0001, when);
    gain.gain.exponentialRampToValueAtTime(0.2, when + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, when + dur);
    osc.connect(gain).connect(ui.ctx.destination);
    osc.start(when);
    osc.stop(when + dur + 0.03);
    ui.osc.push(osc);
  }

  function stopPlayback() {
    ui.generation += 1;
    if (ui.raf) cancelAnimationFrame(ui.raf);
    ui.raf = 0;
    for (const osc of ui.osc) {
      try { osc.stop(); } catch (err) { /* already stopped */ }
    }
    ui.osc = [];
    heads().forEach((el) => el.classList.remove("yue-play"));
  }

  function togglePlay() {
    if (ui.raf) {
      stopPlayback();
      return;
    }
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
    ui.ctx = ui.ctx || new AudioCtx();
    if (ui.ctx.state === "suspended") ui.ctx.resume();
    const generation = ++ui.generation;
    const t0 = ui.ctx.currentTime + 0.05;
    for (const note of score.notes) {
      const osc = ui.ctx.createOscillator();
      const gain = ui.ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = 440 * Math.pow(2, (note.midi - 69) / 12);
      const when = t0 + note.start;
      const dur = Math.max(0.06, note.duration);
      gain.gain.setValueAtTime(0.0001, when);
      gain.gain.exponentialRampToValueAtTime(0.18, when + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, when + dur);
      osc.connect(gain).connect(ui.ctx.destination);
      osc.start(when);
      osc.stop(when + dur + 0.03);
      ui.osc.push(osc);
    }
    const total = score.notes.reduce((max, note) => Math.max(max, note.start + note.duration), 0);
    const tick = () => {
      if (ui.generation !== generation) return;
      const now = ui.ctx.currentTime - t0;
      ui.clock.textContent = formatClock(Math.min(now, total)) + " / " + formatClock(total);
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
      if (now < total) ui.raf = requestAnimationFrame(tick);
      else stopPlayback();
    };
    tick();
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

  function open(abc) {
    ensureDom();
    stopPlayback();
    if (ui.resolve) ui.resolve(null);
    return new Promise((resolve) => {
      ui.abc = String(abc || "");
      ui.index = -1;
      ui.voice = "Vocal";
      ui.slice = 0;
      ui.resolve = resolve;
      setStatus("点唱谱或伴奏上的一个音来改，会响起这个音。双击唱谱改歌词。");
      if (ui.clock) ui.clock.textContent = "0:00";
      ui.root.hidden = false;
      renderScore();
      ui.card.focus();
    });
  }

  return {
    DURATIONS: DURATIONS,
    editScore: editScore,
    listEvents: listEvents,
    timeline: timeline,
    inspectScore: inspectScore,
    previewAbc: previewAbc,
    noteMidi: noteMidi,
    jianpuAbcWithDirective: jianpuAbcWithDirective,
    countHeads: countHeads,
    headIndexes: headIndexes,
    commandOfKey: commandOfKey,
    open: open,
  };
});

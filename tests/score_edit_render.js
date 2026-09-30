/**
 * Exercise score_edit.js and, unless --edit, render vocal and accompaniment jianpu heads.
 * Exit 0 = GREEN, 1 = RED. --edit reads a JSON command on stdin and writes the result.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const editor = require("../static/score_edit.js");

if (process.argv[2] === "--edit") {
  const command = JSON.parse(fs.readFileSync(0, "utf8"));
  process.stdout.write(JSON.stringify(editor.editScore(command.abc, command)));
  process.exit(0);
}

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "static", "abc2svg", "abc2svg-1.js");
const MODULE = path.join(ROOT, "static", "abc2svg", "jianpu-1.js");

const DISPLAY = [
  "X:1",
  "T:",
  "M:4/4",
  "L:1/16",
  "Q:1/4=120",
  "V: Vocal clef=treble name=\"Vocal Melody\" snm=\"Vocal\"",
  "V: Ins clef=treble name=\"Ins Melody\" snm=\"Inst.\"",
  "K:C",
  "% verse",
  "V: Vocal",
  "\"C\"C4D4E4F4|G4A4B4c4|",
  "w: 春 眠 不 觉 晓 处 处 闻",
  "V: Ins",
  "Z2|",
  "",
].join("\n");

function render(src) {
  const ctx = { console, abc2svg: undefined };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(CORE, "utf8"), ctx, { filename: "abc2svg-1.js" });
  vm.runInContext(fs.readFileSync(MODULE, "utf8"), ctx, { filename: "jianpu-1.js" });
  const buf = [];
  const abc = new ctx.abc2svg.Abc({
    img_out: (svg) => buf.push(svg),
    errbld: () => {},
    errmsg: () => {},
    read_file: () => "",
  });
  abc.tosvg("jianpu", editor.previewAbc(src));
  return buf.join("");
}

function digitHeads(svg) {
  const matches = String(svg).match(/<text class="fj(?: [^"]*)?"[^>]*>([0-7])<\/text>/g) || [];
  return matches.map((tag) => tag.replace(/.*>([0-7])<.*/, "$1"));
}

function check(label, ok, detail) {
  console.log((ok ? "GREEN" : "RED  ") + "  " + label + (detail ? "  " + detail : ""));
  return ok ? 0 : 1;
}

let red = 0;
const svg = render(DISPLAY);
const heads = editor.countHeads(svg);
const events = editor.listEvents(DISPLAY);
const insHeads = (svg.match(/<text class="fj v-Ins"[^>]*>[0-7]<\/text>/g) || []).length;
red += check(
  "vocal jianpu heads match notes",
  heads === events.length && heads === 8,
  "heads=" + heads + " events=" + events.length
);
red += check(
  "editor shows vocal and accompaniment",
  /唱/.test(svg) && /伴/.test(svg) && insHeads > 0,
  "insHeads=" + insHeads
);
const insMap = editor.headIndexes(DISPLAY, "Ins");
red += check(
  "accompaniment heads match the score",
  insMap.join(",") === "0,0" && insMap.length === insHeads,
  "map=" + insMap.join(",") + " heads=" + insHeads
);
red += check(
  "current note midi",
  editor.noteMidi(DISPLAY, 0) === 60,
  String(editor.noteMidi(DISPLAY, 0))
);

const degree = editor.editScore(DISPLAY, { op: "degree", index: 0, degree: 2 });
red += check("degree", !degree.error && degree.abc.includes('"C"D4D4E4F4|'), degree.error || "");
red += check(
  "changed note sounds as D4",
  editor.noteMidi(degree.abc, 0) === 62,
  String(editor.noteMidi(degree.abc, 0))
);

const play = editor.timeline(DISPLAY);
const melody = play.notes.filter((note) => note.voice !== "Chord");
const chord = play.notes.filter((note) => note.voice === "Chord");
red += check(
  "midi timeline",
  melody.length === 8 && melody[0].midi === 60 && Math.abs(melody[0].duration - 0.5) < 1e-6,
  play.error || ""
);
red += check(
  "midi timeline plays the chord with the melody",
  chord.length === 4 &&
    chord.map((note) => note.midi).join(",") === "48,60,64,67" &&
    chord.every((note) => note.start === 0 && Math.abs(note.duration - 4) < 1e-6),
  chord.map((note) => note.midi + "@" + note.start + "+" + note.duration).join(" ")
);
const chordChange = [
  "X:1", "T:", "M:4/4", "L:1/4", "Q:1/4=60", "K:C", "V: Vocal",
  '"C"C2 "G7"E2|', "V: Ins", "Z|", "",
].join("\n");
const changedPlay = editor.timeline(chordChange);
const changedChords = changedPlay.notes.filter((note) => note.voice === "Chord");
red += check(
  "a later chord replaces the one before it",
    changedChords.filter((note) => note.start === 0).map((note) => note.midi).join(",") === "48,60,64,67" &&
    changedChords.filter((note) => note.start === 0).every((note) => note.duration === 2) &&
    changedChords.filter((note) => note.start === 2).map((note) => note.midi).join(",") === "55,62,65,67,71",
  changedChords.map((note) => note.midi + "@" + note.start).join(" ")
);
red += check(
  "chord spelling",
  (editor.spellChord("Am") || []).join(",") === "57,60,64,69" &&
    (editor.spellChord("C/E") || []).join(",") === "52,60,64,67" &&
    editor.spellChord("nope") == null,
  String(editor.spellChord("C/E"))
);
const marks = editor.playMarks(DISPLAY);
const atBeat = editor.cursorAt(marks, 0.75);
const atBar = editor.cursorAt(marks, 2.1);
red += check(
  "playhead walks the vocal digits and rests",
  marks.filter((mark) => mark.voice === "Vocal").length === 8 &&
    marks.some((mark) => mark.voice === "Ins" && mark.slice === 1 && Math.abs(mark.start - 2) < 1e-6) &&
    atBeat && atBeat.voice === "Vocal" && atBeat.index === 1 &&
    atBar && atBar.voice === "Vocal" && atBar.index === 4,
  atBeat ? atBeat.voice + ":" + atBeat.index : "missing"
);
const vocalBeat = marks.find((mark) => mark.voice === "Vocal" && mark.index === 1 && mark.slice === 0);
red += check(
  "markTime is the clicked glyph's start",
  vocalBeat && editor.markTime(marks, "Vocal", 1, 0) === vocalBeat.start &&
    editor.markTime(marks, "Ins", 1, 0) !== vocalBeat.start &&
    editor.markTime(marks, "Vocal", 99, 0) == null,
  vocalBeat ? String(vocalBeat.start) : "missing"
);
red += check(
  "playback uses source audio only when it is available",
  editor.playbackTransport(true, "source") === "source" &&
    editor.playbackTransport(true, "midi") === "midi" &&
    editor.playbackTransport(false, "source") === "midi",
  ""
);
red += check(
  "source playback hides the red playhead",
  editor.showsPlayhead("source") === false && editor.showsPlayhead("midi") === true,
  ""
);
red += check(
  "fileUrl keeps a playable address",
  editor.fileUrl({ url: "/gradio_api/file=song.wav", path: "C:/other.wav" }) === "/gradio_api/file=song.wav" &&
    editor.fileUrl({ path: "C:\\song.wav" }) === "/gradio_api/file=C:/song.wav" &&
    editor.fileUrl("/gradio_api/file=song.wav") === "/gradio_api/file=song.wav" &&
    editor.fileUrl(null) === "" &&
    editor.fileUrl("C:\\song.wav") === "",
  editor.fileUrl({ path: "C:\\song.wav" })
);

const keys = editor.commandOfKey("5");
red += check("key 5", keys && keys.op === "degree" && keys.degree === 5, "");
const tieKey = editor.commandOfKey("t");
red += check("key t", tieKey && tieKey.op === "tie", "");
const holdKey = editor.commandOfKey("-");
red += check("key -", holdKey && holdKey.op === "sustain", "");

const LONG = [
  "X:1",
  "T:",
  "M:4/4",
  "L:1/16",
  "Q:1/4=120",
  "V: Vocal clef=treble name=\"Vocal Melody\" snm=\"Vocal\"",
  "K:C",
  "V: Vocal",
  "z16C8|",
  "",
].join("\n");
const restMarks = editor.playMarks(LONG);
const restAt = editor.cursorAt(restMarks, 1.2);
red += check(
  "playhead steps across a split rest",
  restMarks.filter((mark) => mark.index === 0).length === 4 &&
    restAt && restAt.index === 0 && restAt.slice === 2 &&
    editor.cursorAt(restMarks, 2.1).index === 1,
  restAt ? "slice=" + restAt.slice : "missing"
);
const longSvg = render(LONG);
const longHeads = digitHeads(longSvg);
const longMap = editor.headIndexes(LONG);
red += check(
  "whole rest splits into four zeros, one event",
  longHeads.join("") === "00001" && longMap.join(",") === "0,0,0,0,1",
  longHeads.join("") + " map=" + longMap.join(",")
);

const marked = [
  "X:1",
  "T:",
  "M:4/4",
  "L:1/4",
  "Q:1/4=120",
  "K:C",
  "V: Vocal",
  "^C _E =F G|",
  "",
].join("\n");
const markedEvents = editor.listEvents(marked);
red += check(
  "listed accidental follows the printed sign",
  JSON.stringify(markedEvents.map((ev) => ev.accidental)) ===
    JSON.stringify(["sharp", "flat", "natural", ""]),
  markedEvents.map((ev) => ev.accidental || "-").join(" ")
);
const markedSvg = render(marked);
const markedTexts = [...markedSvg.matchAll(/<text([^>]*)>([^<]*)<\/text>/g)].map((m) => ({
  attrs: m[1],
  t: m[2],
}));
function numAttr(attrs, name) {
  const hit = new RegExp(name + '="([0-9.]+)"').exec(attrs);
  return hit ? Number(hit[1]) : NaN;
}
const digit = markedTexts.find((node) => /class="fj[\s"]/.test(node.attrs) && node.t === "1");
const sharp = markedTexts.find((node) => /class="jacc"/.test(node.attrs));
red += check(
  "sharp sits above the left of the digit",
  !!digit && !!sharp &&
    numAttr(sharp.attrs, "y") < numAttr(digit.attrs, "y") - 8 &&
    numAttr(sharp.attrs, "x") < numAttr(digit.attrs, "x") &&
    numAttr(digit.attrs, "x") - numAttr(sharp.attrs, "x") < 6,
  sharp ? "dx=" + (numAttr(digit.attrs, "x") - numAttr(sharp.attrs, "x")).toFixed(1) +
    " dy=" + (numAttr(digit.attrs, "y") - numAttr(sharp.attrs, "y")).toFixed(1) : "missing"
);

const changed = editor.editScore(LONG, { op: "degree", index: 0, degree: 3 });
const changedHeads = digitHeads(render(changed.abc));
const changedMap = editor.headIndexes(changed.abc);
red += check(
  "degree rewrite shows on the next jianpu",
  !changed.error && changedHeads.join("") === "31" && changedMap.join(",") === "0,1",
  changed.error || changedHeads.join("")
);

const oneGlyph = editor.editScore(LONG, { op: "degree", index: 0, slice: 2, degree: 5 });
red += check(
  "clicked rest glyph changes alone",
  !oneGlyph.error && oneGlyph.abc.includes("z4z4G4z4C8|"),
  oneGlyph.error || oneGlyph.abc
);

const secondBar = editor.editScore(DISPLAY, {
  op: "degree", index: 0, voice: "Ins", slice: 1, degree: 5,
});
red += check(
  "one bar of a multi-bar rest",
  !secondBar.error && secondBar.abc.includes("z16G16|") && secondBar.abc.includes('"C"C4D4E4F4|'),
  secondBar.error || ""
);
const withIns = DISPLAY.replace("Z2|", "C4D4E4F4|");
const insEdit = editor.editScore(withIns, { op: "degree", index: 0, voice: "Ins", slice: 0, degree: 2 });
red += check(
  "accompaniment degree leaves the vocal line",
  !insEdit.error && insEdit.abc.includes("D4D4E4F4|") && insEdit.abc.includes('"C"C4D4E4F4|'),
  insEdit.error || ""
);

const lyricHits = editor.assignLyricHits(
  [
    { x: 90, y: 52, index: 0, voice: "Vocal" },
    { x: 110, y: 52, index: 1, voice: "Vocal" },
    { x: 130, y: 52, index: 2, voice: "Vocal" },
    { x: 90, y: 110, index: 0, voice: "Ins" },
    { x: 90, y: 200, index: 3, voice: "Vocal" },
  ],
  [
    { x: 90, y: 20, name: "chord" },
    { x: 89, y: 82, name: "春" },
    { x: 131, y: 82, name: "眠" },
    { x: 90, y: 150, name: "next-chord" },
    { x: 90, y: 230, name: "晓" },
  ],
  { 0: true, 2: true, 3: true }
);
red += check(
  "lyric glyphs bind to the notes above, skipping rests, melisma, and chords",
  lyricHits.map((hit) => hit.glyph.name + ":" + hit.index).join(",") === "春:0,眠:2,晓:3",
  lyricHits.map((hit) => hit.glyph.name + ":" + hit.index).join(",")
);

const partialHits = editor.assignLyricHits(
  [
    { x: 90, y: 52, index: 0, voice: "Vocal" },
    { x: 110, y: 52, index: 1, voice: "Vocal" },
    { x: 130, y: 52, index: 2, voice: "Vocal" },
  ],
  [
    { x: 89, y: 82, name: "春" },
    { x: 110, y: 82, name: "眠" },
  ],
  { 0: true, 1: true, 2: true }
);
red += check(
  "mismatched lyric counts still bind left to right",
  partialHits.map((hit) => hit.glyph.name + ":" + hit.index).join(",") === "春:0,眠:1",
  partialHits.map((hit) => hit.glyph.name + ":" + hit.index).join(",")
);

red += check(
  "splitLyricLine cuts CJK and keeps spaced English",
  editor.splitLyricLine("春眠").join(",") === "春,眠"
    && editor.splitLyricLine("let the day").join(",") === "let,the,day"
    && editor.splitLyricLine("love-day").join(",") === "love,-,day"
    && editor.splitLyricLine("春 · 晓").join(",") === "春,*,晓",
  editor.splitLyricLine("春眠").join(",")
);

const sung = editor.editScore(DISPLAY, { op: "lyric", index: 0, text: "山" });
const sungSvg = render(sung.abc);
red += check(
  "edited lyric is drawn under the vocal note",
  !sung.error && sungSvg.includes(">山<") && !sungSvg.includes(">春<"),
  sung.error || ""
);
const held = [
  "X:1", "T:", "M:4/4", "L:1/16", "Q:1/4=120", "K:C", "V: Vocal",
  "C4D4E4|", "w: 春 - 晓", "",
].join("\n");
const kept = editor.editScore([
  "X:1", "T:", "M:4/4", "L:1/16", "Q:1/4=120", "K:C", "V: Vocal",
  "C4D4z4E4|", "w: 春 - 晓", "",
].join("\n"), { op: "lyric", index: 0, text: "山" });
const keptSvg = render(kept.abc);
red += check(
  "a rest does not swallow the next lyric",
  !kept.error && kept.abc.includes("w: 山 - 晓") && keptSvg.includes(">山<") && keptSvg.includes(">晓<"),
  kept.error || kept.abc
);
const heldEvents = editor.listEvents(held);
red += check(
  "melisma is kept and not drawn as a syllable",
  heldEvents.map((ev) => ev.lyric).join(" ") === "春 - 晓" &&
    heldEvents.map((ev) => editor.lyricIsDrawn(ev.lyric)).join(",") === "true,false,true",
  heldEvents.map((ev) => ev.lyric).join(" ")
);

const queued = editor.soundingNotes([
  { start: 0, duration: 1, midi: 60 },
  { start: 1, duration: 1, midi: 62 },
  { start: 2, duration: 0.5, midi: 64 },
], 1.25);
red += check(
  "midi resume keeps the remainder and later notes",
  queued.length === 2 &&
    queued[0].delay === 0 && Math.abs(queued[0].duration - 0.75) < 1e-9 && queued[0].note.midi === 62 &&
    Math.abs(queued[1].delay - 0.75) < 1e-9 && queued[1].duration === 0.5 && queued[1].note.midi === 64,
  JSON.stringify(queued)
);
const finished = editor.soundingNotes([{ start: 0, duration: 1, midi: 60 }], 1);
red += check(
  "midi resume skips notes that already ended",
  finished.length === 0,
  JSON.stringify(finished)
);

const windowQueue = editor.soundingNotes([
  { start: 0, duration: 1, midi: 60 },
  { start: 1.2, duration: 0.4, midi: 62 },
  { start: 10, duration: 1, midi: 64 },
], 0);
const opened = editor.pumpMidi(windowQueue, 0);
const stillLater = editor.pumpMidi(windowQueue, 0);
const caughtUp = editor.pumpMidi(windowQueue, 9);
red += check(
  "midi playback arms only the lookahead, then the rest as the clock advances",
  opened.length === 2 && opened[0].note.midi === 60 && opened[1].note.midi === 62 &&
    stillLater.length === 0 &&
    caughtUp.length === 1 && caughtUp[0].note.midi === 64 &&
    editor.pumpMidi(windowQueue, 12).length === 0,
  JSON.stringify({ opened: opened.map((item) => item.note.midi), stillLater: stillLater.length, caughtUp: caughtUp.map((item) => item.note.midi) })
);

function checkLoadOrder() {
  const pending = [];
  global.document = {
    createElement() {
      return { onload: null, onerror: null, src: "" };
    },
    head: {
      appendChild(el) { pending.push(el); },
    },
  };
  const done = editor.ensureJianpu();
  return new Promise((resolve) => setImmediate(resolve)).then(() => {
    const firstOnly = pending.length === 1 && pending[0].src.endsWith("abc2svg-1.js");
    global.abc2svg = { Abc: function Abc() {} };
    pending[0].onload();
    return new Promise((resolve) => setImmediate(resolve)).then(() => {
      const secondAfter = pending.length === 2 && pending[1].src.endsWith("jianpu-1.js");
      global.abc2svg.jianpu = {};
      pending[1].onload();
      return done.then((ok) => check(
        "jianpu module loads after abc2svg",
        firstOnly && secondAfter && ok === true,
        pending.map((el) => el.src).join(" | ")
      ));
    });
  });
}

checkLoadOrder().then((failed) => {
  process.exit(red + failed ? 1 : 0);
}).catch((err) => {
  console.error(err);
  process.exit(1);
});

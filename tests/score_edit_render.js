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
red += check(
  "midi timeline",
  play.notes.length === 8 && play.notes[0].midi === 60 && Math.abs(play.notes[0].duration - 0.5) < 1e-6,
  play.error || ""
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

process.exit(red ? 1 : 0);

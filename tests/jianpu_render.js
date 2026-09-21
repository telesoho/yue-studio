/**
 * Render YuE ABC through abc2svg + jianpu-1.js and require numbered-notation SVG.
 * Invoked by tests/test_score.py. Exit 0 = GREEN, 1 = RED.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const CORE = path.join(ROOT, "static", "abc2svg", "abc2svg-1.js");
const MODULE = path.join(ROOT, "static", "abc2svg", "jianpu-1.js");
const FIXTURE = path.join(__dirname, "fixtures", "score.abc");

function jianpuAbcWithDirective(src) {
  // Keep in sync with _SCORE_PLAYER_JS in src/yue_studio/score.py.
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
  return (
    lines.slice(0, kIdx + 1).join("\n") +
    "\n" +
    injection +
    lines.slice(kIdx + 1).join("\n")
  );
}

function loadAbc2svg() {
  if (!fs.existsSync(CORE)) throw new Error("missing " + CORE);
  if (!fs.existsSync(MODULE)) throw new Error("missing " + MODULE);
  const ctx = { console, abc2svg: undefined };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(CORE, "utf8"), ctx, { filename: "abc2svg-1.js" });
  vm.runInContext(fs.readFileSync(MODULE, "utf8"), ctx, { filename: "jianpu-1.js" });
  if (!ctx.abc2svg || !ctx.abc2svg.jianpu) {
    throw new Error("jianpu module did not register abc2svg.jianpu");
  }
  return ctx.abc2svg;
}

function render(abc2svg, src) {
  const buf = [];
  const errors = [];
  const abc = new abc2svg.Abc({
    img_out: (svg) => buf.push(svg),
    errbld: (sev, msg) => errors.push(String(msg)),
    errmsg: (msg) => errors.push(String(msg)),
    read_file: () => "",
  });
  abc.tosvg("jianpu", jianpuAbcWithDirective(src));
  const svg = buf.join("");
  return {
    svg,
    errors,
    hasDigits: /class="fj"[^>]*>[1-7]/.test(svg),
    hasUndefined: /undefined/i.test(svg),
    hasLongVoice: /Vocal Melody|Ins Melody/.test(svg),
    hasShortVoice: /唱/.test(svg) && /伴/.test(svg),
    hasRestZero: /class="fj"[^>]*>0/.test(svg),
    // Whole-rest ledger from hl_rest(set_hl(..., -7, 7)) → m-7.00 0h14.00
    hasRestLedger: /m-7\.00 0h14\.00/.test(svg),
  };
}

const abc2svg = loadAbc2svg();
const fixture = fs.readFileSync(FIXTURE, "utf8");
const userAbc = fs.readFileSync(path.join(__dirname, "fixtures", "jianpu_user.abc"), "utf8");
const simple = "X:1\nT:t\nM:4/4\nL:1/4\nK:C\nCDEF|GABc|\n";

const cases = [
  { label: "YuE Vocal/Ins fixture", src: fixture, need: ["hasDigits", "hasShortVoice"] },
  { label: "default voice, no V:", src: simple, need: ["hasDigits"] },
  {
    label: "user ABC with Z/Z4 rests",
    src: userAbc,
    need: ["hasDigits", "hasRestZero", "hasShortVoice"],
    forbid: ["hasRestLedger"],
  },
];

let red = 0;
for (const spec of cases) {
  const result = render(abc2svg, spec.src);
  const missing = spec.need.filter((key) => !result[key]);
  const extra = (spec.forbid || []).filter((key) => result[key]);
  const bad = result.hasUndefined || result.hasLongVoice || missing.length || extra.length;
  console.log(
    (bad ? "RED  " : "GREEN") +
      "  " +
      spec.label +
      "  bytes=" +
      result.svg.length +
      (result.hasUndefined ? "  undefined" : "") +
      (result.hasLongVoice ? "  long-name" : "") +
      (missing.length ? "  missing=" + missing.join(",") : "") +
      (extra.length ? "  extra=" + extra.join(",") : "")
  );
  if (bad) red++;
}
process.exit(red ? 1 : 0);

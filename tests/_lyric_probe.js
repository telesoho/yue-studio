"use strict";
const fs = require("fs");
const vm = require("vm");
const editor = require("../static/score_edit.js");
const ctx = { console, abc2svg: undefined };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync("static/abc2svg/abc2svg-1.js", "utf8"), ctx, { filename: "abc2svg-1.js" });
vm.runInContext(fs.readFileSync("static/abc2svg/jianpu-1.js", "utf8"), ctx, { filename: "jianpu-1.js" });
const DISPLAY = [
  "X:1", "T:", "M:4/4", "L:1/16", "Q:1/4=120", "K:C",
  "V: Vocal",
  '"C"C4D4z4E4|',
  "w: 春 - 眠",
  "V: Ins",
  "z16|",
  "",
].join("\n");
const buf = [];
const abc = new ctx.abc2svg.Abc({
  img_out: (svg) => buf.push(svg),
  errbld: () => {},
  errmsg: (...a) => console.error("ERR", a),
  read_file: () => "",
});
abc.tosvg("jianpu", editor.previewAbc(DISPLAY));
const svg = buf.join("");
const i = svg.indexOf(">春<");
console.log(svg.slice(Math.max(0, i - 800), i + 500));
console.log("\n==== PATHS near lyrics ====");
const paths = [...svg.matchAll(/<path[^>]*>/g)].map((m) => m[0]);
for (const p of paths) {
  if (/h[0-9]/.test(p) && p.length < 200) console.log(p);
}

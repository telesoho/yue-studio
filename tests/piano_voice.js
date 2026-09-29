/**
 * Schedule one piano note through a fake AudioContext.
 * Exit 0 = GREEN, 1 = RED.
 */
"use strict";

const piano = require("../static/piano.js");

function check(name, ok, detail) {
  if (ok) return 0;
  console.error("RED " + name + (detail ? " — " + detail : ""));
  return 1;
}

function AudioParam(value) {
  this.value = value;
  this.events = [{ method: "set", value: value, time: 0 }];
}

AudioParam.prototype.setValueAtTime = function (value, time) {
  this.events.push({ method: "set", value: value, time: time });
  this.value = value;
};

AudioParam.prototype.exponentialRampToValueAtTime = function (value, time) {
  const prev = this.events[this.events.length - 1];
  if (!(value > 0) || !(time > prev.time)) {
    throw new Error("bad ramp " + value + " at " + time + " after " + prev.time);
  }
  this.events.push({ method: "ramp", value: value, time: time });
  this.value = value;
};

AudioParam.prototype.linearRampToValueAtTime = function (value, time) {
  const prev = this.events[this.events.length - 1];
  if (!(time > prev.time)) throw new Error("bad linear ramp at " + time);
  this.events.push({ method: "linear", value: value, time: time });
  this.value = value;
};

function node(kind) {
  return {
    kind: kind,
    connect: function (target) { this.target = target; return target; },
    start: function (when) { this.started = when; },
    stop: function (when) { this.stopped = when; },
    disconnect: function () { this.gone = true; },
  };
}

function Context() {
  this.sampleRate = 48000;
  this.destination = node("destination");
  this.oscs = [];
  this.sources = [];
  this.filters = [];
}

Context.prototype.createGain = function () {
  const gain = node("gain");
  gain.gain = new AudioParam(1);
  return gain;
};

Context.prototype.createOscillator = function () {
  const osc = node("osc");
  osc.frequency = new AudioParam(440);
  this.oscs.push(osc);
  return osc;
};

Context.prototype.createBiquadFilter = function () {
  const filter = node("filter");
  filter.frequency = new AudioParam(350);
  filter.Q = new AudioParam(1);
  this.filters.push(filter);
  return filter;
};

Context.prototype.createDynamicsCompressor = function () {
  const comp = node("compressor");
  comp.threshold = new AudioParam(-24);
  comp.knee = new AudioParam(30);
  comp.ratio = new AudioParam(12);
  comp.attack = new AudioParam(0.003);
  comp.release = new AudioParam(0.25);
  return comp;
};

Context.prototype.createBufferSource = function () {
  const source = node("buffer");
  this.sources.push(source);
  return source;
};

Context.prototype.createBuffer = function (channels, length, rate) {
  const data = new Float32Array(length);
  return {
    numberOfChannels: channels,
    length: length,
    sampleRate: rate,
    getChannelData: function () { return data; },
    data: data,
  };
};

let red = 0;
const ctx = new Context();
const voices = [];
piano.schedule(ctx, { pitch: 69, volume: 0.16 }, 1, 0.5, voices);

const fundamentals = ctx.oscs.filter((osc) => {
  const settled = osc.frequency.events[osc.frequency.events.length - 1].value;
  return Math.abs(settled - 440) < 8;
});
red += check(
  "A4 is a piano partial stack, not one triangle wave",
  ctx.oscs.length >= 5 &&
    ctx.oscs.every((osc) => osc.type === "sine") &&
    fundamentals.length >= 2,
  "oscs=" + ctx.oscs.length + " fundamentals=" + fundamentals.length
);
function meanAbs(data, from, to) {
  let sum = 0;
  for (let i = from; i < to; i++) sum += Math.abs(data[i]);
  return sum / Math.max(1, to - from);
}

const hammer = ctx.sources[0] && ctx.sources[0].buffer && ctx.sources[0].buffer.data;
const hammerHead = hammer ? meanAbs(hammer, 0, Math.floor(hammer.length * 0.1)) : 0;
const hammerTail = hammer ? meanAbs(hammer, Math.floor(hammer.length * 0.8), hammer.length) : 1;
red += check(
  "hammer click is a short noise burst",
  ctx.sources.length === 1 && hammerHead > hammerTail * 4,
  ""
);
red += check(
  "partials go straight to the speakers",
  ctx.oscs.every((osc) => osc.target && osc.target.target === ctx.destination) &&
    ctx.oscs.some((osc) => osc.target.gain.events.some((event) => event.value >= 0.1)),
  ""
);
const sources = voices.filter((item) => item.kind === "osc" || item.kind === "buffer");
red += check(
  "every source is started and stopped",
  sources.length > 0 && sources.every((item) => item.started != null && item.stopped > item.started),
  ""
);

const bass = new Context();
const high = new Context();
piano.schedule(bass, { midi: 36, volume: 0.16 }, 0, 0.4, []);
piano.schedule(high, { midi: 84, volume: 0.16 }, 0, 0.4, []);
const bassStop = Math.max(...bass.oscs.map((osc) => osc.stopped));
const highStop = Math.max(...high.oscs.map((osc) => osc.stopped));
red += check(
  "low notes ring longer than high notes",
  bassStop > highStop,
  bassStop + " vs " + highStop
);

piano.schedule(ctx, { midi: null }, 0, 0.2, []);
red += check("missing pitch is ignored", ctx.oscs.length === voices.filter((node) => node.kind === "osc").length, "");

const sampled = new Context();
sampled.currentTime = 0.2;
const fake = {
  started: [],
  stopTimes: [],
  start: function (sample) {
    this.started.push(sample);
    const self = this;
    let used = false;
    function stop(time) {
      if (used) throw new Error("already stopped");
      used = true;
      self.stopTimes.push(time == null ? sampled.currentTime : time);
    }
    if (typeof sample.duration === "number") stop(sample.time + sample.duration);
    return stop;
  },
};
piano.attach(sampled, fake);
const sampledVoices = [];
piano.schedule(sampled, { midi: 60, volume: 0.16 }, 1.5, 0.4, sampledVoices);
const started = fake.started[0] || {};
const gate = sampled.oscs[sampled.oscs.length - 1];
red += check(
  "a ready sampler is scheduled without a precommitted end",
  fake.started.length === 1 &&
    started.note === 60 &&
    started.time === 1.5 &&
    started.duration == null &&
    started.velocity === 90 &&
    fake.stopTimes.length === 0 &&
    gate && gate.stopped === 1.9,
  JSON.stringify(started) + " stops=" + JSON.stringify(fake.stopTimes)
);
let stopThrew = false;
try { sampledVoices[0].stop(); } catch (err) { stopThrew = true; }
red += check(
  "pause stops the sounding note now",
  !stopThrew && fake.stopTimes.length === 1 && fake.stopTimes[0] <= sampled.currentTime,
  JSON.stringify(fake.stopTimes)
);
piano.schedule(sampled, { midi: null }, 2, 0.2, sampledVoices);
red += check("sampler ignores a missing pitch", fake.started.length === 1, "");

const gradio = "http://127.0.0.1:7860/gradio_api/file=static/piano.js";
red += check(
  "sampler sits beside piano.js on the gradio file route",
  piano.libraryUrl(gradio) === "http://127.0.0.1:7860/gradio_api/file=static/smplr.mjs",
  piano.libraryUrl(gradio)
);
const plain = "http://127.0.0.1:8765/static/piano.js";
red += check(
  "sampler sits beside a normal script url",
  piano.libraryUrl(plain) === "http://127.0.0.1:8765/static/smplr.mjs",
  piano.libraryUrl(plain)
);

piano.prepare(new Context()).then(function (voice) {
  red += check(
    "prepare without samples uses the synthetic voice",
    voice && voice.kind === "synthetic",
    voice && voice.kind
  );
  if (red) process.exit(1);
  console.log("GREEN piano voice");
}).catch(function (err) {
  console.error(err);
  process.exit(1);
});

/**
 * Browser piano voice for MIDI preview.
 * Prefers a sampled Splendid Grand Piano (smplr, same instrument as eargym).
 * If those samples cannot be loaded, a few stretched partials and a hammer
 * click still play straight to the audio destination.
 */
(function (root, factory) {
  const script = typeof document !== "undefined" ? document.currentScript : null;
  const api = factory(root, script && script.src || "");
  if (typeof module === "object" && module.exports) module.exports = api;
  root.yuePiano = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root, scriptSrc) {
  "use strict";

  const VELOCITY = 90;
  const PARTIALS = [
    { n: 1, amp: 1, decay: 1 },
    { n: 2, amp: 0.42, decay: 0.62 },
    { n: 3, amp: 0.18, decay: 0.4 },
    { n: 4, amp: 0.08, decay: 0.24 },
  ];
  const ready = new WeakMap();
  const pending = new WeakMap();
  let libraryPromise = null;

  function notesToLoad() {
    const notes = [];
    for (let midi = 21; midi <= 108; midi++) notes.push(midi);
    return notes;
  }

  function libraryUrl(src) {
    const from = src == null ? scriptSrc : src;
    // Gradio serves the file as /gradio_api/file=static/piano.js, so the
    // script name is not its own path segment. Swap that token in place.
    if (from && from.indexOf("file=static/piano.js") >= 0) {
      return from.replace("file=static/piano.js", "file=static/smplr.mjs");
    }
    if (from) {
      try { return new URL("smplr.mjs", from).href; } catch (err) { /* fall through */ }
    }
    return "/gradio_api/file=static/smplr.mjs";
  }

  function importSource(text) {
    const blob = new Blob([text], { type: "text/javascript" });
    const url = URL.createObjectURL(blob);
    return import(url).finally(function () { URL.revokeObjectURL(url); });
  }

  function loadLibrary() {
    if (libraryPromise) return libraryPromise;
    const inline = root.__YUE_SMPLR_SOURCE__;
    libraryPromise = (async function () {
      if (typeof inline === "string" && inline) return importSource(inline);
      if (typeof fetch !== "function") throw new Error("smplr missing");
      const res = await fetch(libraryUrl());
      if (!res.ok) throw new Error("smplr " + res.status);
      return importSource(await res.text());
    })().catch(function (err) {
      libraryPromise = null;
      throw err;
    });
    return libraryPromise;
  }

  function storageFor(mod) {
    try {
      if (typeof caches !== "undefined" && mod.CacheStorage) {
        return new mod.CacheStorage("yue-studio-piano");
      }
    } catch (err) { /* HttpStorage still fetches the samples */ }
    return mod.HttpStorage;
  }

  function prepare(ctx) {
    if (!ctx) return Promise.resolve({ kind: "synthetic" });
    const have = ready.get(ctx);
    if (have) return Promise.resolve(have);
    const job = pending.get(ctx);
    if (job) return job;
    const next = loadLibrary().then(function (mod) {
      const piano = new mod.SplendidGrandPiano(ctx, {
        storage: storageFor(mod),
        velocity: VELOCITY,
        decayTime: 0.03,
        disableScheduler: true,
        notesToLoad: {
          notes: notesToLoad(),
          velocityRange: [85, 100],
        },
      });
      return piano.load.then(function () {
        const buffers = piano.buffers || {};
        if (!Object.keys(buffers).length) throw new Error("no piano samples");
        const voice = { kind: "sampled", piano: piano };
        ready.set(ctx, voice);
        return voice;
      });
    }).catch(function () {
      return { kind: "synthetic" };
    }).finally(function () {
      pending.delete(ctx);
    });
    pending.set(ctx, next);
    return next;
  }

  function voice(ctx) {
    return ready.get(ctx) || null;
  }

  function attach(ctx, instrument) {
    const sampled = { kind: "sampled", piano: instrument };
    ready.set(ctx, sampled);
    return sampled;
  }

  function hammerBuffer(ctx) {
    if (ctx.__yueHammer) return ctx.__yueHammer;
    const rate = ctx.sampleRate || 44100;
    const length = Math.max(1, Math.floor(rate * 0.03));
    const buffer = ctx.createBuffer(1, length, rate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i++) {
      const t = i / rate;
      data[i] = (Math.random() * 2 - 1) * Math.exp(-t / 0.004);
    }
    ctx.__yueHammer = buffer;
    return buffer;
  }

  function addPartial(ctx, voices, freq, pitch, level, t0, hold, n, amp, decay, cents) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const stiffness = 0.0002 * Math.pow(2, (40 - pitch) / 24);
    const ratio = n * Math.sqrt(1 + stiffness * n * n) * Math.pow(2, cents / 1200);
    const peak = Math.max(0.05, level * amp);
    const ring = Math.max(0.85, Math.min(1.7, Math.pow(2, (60 - pitch) / 36)));
    const doneAt = t0 + Math.max(0.18, hold * decay * ring);
    osc.type = "sine";
    osc.frequency.setValueAtTime(freq * ratio, t0);
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, doneAt);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(t0);
    osc.stop(doneAt + 0.03);
    if (voices) voices.push(osc);
  }

  function placed(ctx, note, when, duration) {
    const raw = note && (note.pitch != null ? note.pitch : note.midi);
    if (raw == null || raw === "") return null;
    const pitch = Number(raw);
    if (!Number.isFinite(pitch)) return null;
    const hold = Math.max(0.12, Number(duration) || 0.35);
    const requested = Number(when);
    const now = ctx.currentTime || 0;
    const t0 = Math.max(now, Number.isFinite(requested) ? requested : now);
    const velocity = Number(note.velocity);
    return {
      pitch: pitch,
      hold: hold,
      t0: t0,
      velocity: Number.isFinite(velocity) ? velocity : null,
    };
  }

  function scheduleSynthetic(ctx, note, slot, voices) {
    const freq = 440 * Math.pow(2, (slot.pitch - 69) / 12);
    const level = Math.max(0.24, Math.min(0.36, (Number(note.volume) || 0.2) * 2));
    for (let i = 0; i < PARTIALS.length; i++) {
      const partial = PARTIALS[i];
      if (partial.n === 1) {
        addPartial(ctx, voices, freq, slot.pitch, level, slot.t0, slot.hold, partial.n, partial.amp * 0.5, partial.decay, -3);
        addPartial(ctx, voices, freq, slot.pitch, level, slot.t0, slot.hold, partial.n, partial.amp * 0.5, partial.decay, 3);
      } else {
        addPartial(ctx, voices, freq, slot.pitch, level, slot.t0, slot.hold, partial.n, partial.amp, partial.decay, 0);
      }
    }
    try {
      const noise = ctx.createBufferSource();
      const noiseGain = ctx.createGain();
      noise.buffer = hammerBuffer(ctx);
      noiseGain.gain.setValueAtTime(Math.max(0.08, level * 0.35), slot.t0);
      noiseGain.gain.exponentialRampToValueAtTime(0.0001, slot.t0 + 0.03);
      noise.connect(noiseGain);
      noiseGain.connect(ctx.destination);
      noise.start(slot.t0);
      noise.stop(slot.t0 + 0.04);
      if (voices) voices.push(noise);
    } catch (err) {
      /* the partials already sound if the click buffer cannot be built */
    }
  }

  function scheduleSampled(ctx, piano, slot, voices) {
    // Duration must not be passed to the sampler. It stops the buffer
    // immediately at the written end, and a buffer source can only be
    // stopped once, so pause cannot cut the note short.
    const release = piano.start({
      note: slot.pitch,
      time: slot.t0,
      velocity: slot.velocity == null ? VELOCITY : slot.velocity,
    });
    let closed = false;
    function finish(time) {
      if (closed) return;
      closed = true;
      try {
        if (typeof release === "function") release(time);
      } catch (err) { /* already stopped */ }
    }
    try {
      const gate = ctx.createOscillator();
      const mute = ctx.createGain();
      mute.gain.setValueAtTime(0, slot.t0);
      gate.connect(mute);
      mute.connect(ctx.destination);
      gate.start(slot.t0);
      gate.stop(slot.t0 + slot.hold);
      gate.onended = function () { finish(slot.t0 + slot.hold); };
    } catch (err) {
      finish(slot.t0 + slot.hold);
    }
    if (voices) voices.push({ stop: function () { finish(); } });
  }

  function schedule(ctx, note, when, duration, voices) {
    const slot = placed(ctx, note, when, duration);
    if (!slot) return;
    const sampled = ready.get(ctx);
    if (sampled && sampled.kind === "sampled" && sampled.piano && sampled.piano.start) {
      scheduleSampled(ctx, sampled.piano, slot, voices);
      return;
    }
    scheduleSynthetic(ctx, note, slot, voices);
  }

  return {
    schedule: schedule,
    prepare: prepare,
    attach: attach,
    voice: voice,
    libraryUrl: libraryUrl,
  };
});

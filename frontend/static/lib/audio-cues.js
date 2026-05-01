// Web Audio cues — generated tones, no audio files.
//
// Implements ADR 0016: every meaningful event (snapshot saved, tracking start /
// stop, cluster forms, question advance, drift warning, control-marker
// recognised) gets a short, low-contrast acoustic confirmation. Cues are
// short (<2s), generated via OscillatorNode + GainNode, routed through a
// master gain so the operator can mute them in one place.
//
// Usage:
//   import { audioCues } from "/static/lib/audio-cues.js";
//   await audioCues.unlock();          // call once on a user gesture
//   audioCues.play("snapshot");
//
// Cues respect a per-question silent_mode flag — when active question's
// formation is privilege_walk, all room-facing cues are suppressed. The
// caller can also force silence via audioCues.silentMode(true).

const CUES = {
  // (name) → array of {freq, type, dur, gain, when_offset, sweep_to?}
  snapshot: [
    { freq: 880, type: "sine", dur: 0.18, gain: 0.18, when: 0 },
    { freq: 1320, type: "sine", dur: 0.30, gain: 0.12, when: 0.05 },
  ],
  tracking_start: [
    { freq: 110, type: "sine", dur: 1.6, gain: 0.18, when: 0, sweep_to: 165 },
  ],
  tracking_stop: [
    { freq: 165, type: "sine", dur: 1.6, gain: 0.18, when: 0, sweep_to: 110 },
  ],
  question_advance: [
    { freq: 600, type: "sine", dur: 0.20, gain: 0.10, when: 0, sweep_to: 900 },
    { freq: 900, type: "sine", dur: 0.10, gain: 0.05, when: 0.18 },
  ],
  drift_warning: [
    { freq: 380, type: "triangle", dur: 0.40, gain: 0.15, when: 0 },
    { freq: 380, type: "triangle", dur: 0.40, gain: 0.15, when: 0.50 },
  ],
  control_card: [
    { freq: 1200, type: "sine", dur: 0.07, gain: 0.10, when: 0 },
  ],
  cluster_chord: [
    { freq: 440, type: "sine", dur: 0.6, gain: 0.10, when: 0 },
    { freq: 554, type: "sine", dur: 0.6, gain: 0.10, when: 0 },  // E (third)
    { freq: 659, type: "sine", dur: 0.6, gain: 0.10, when: 0 },  // G
  ],
};

// Cues that are intended to be heard by *the room* (not just the operator).
// During privilege_walk formation these are suppressed.
const ROOM_FACING = new Set(["snapshot", "question_advance", "cluster_chord"]);

class AudioCues {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.muted = false;
    this.silent = false;
    this.volume = 0.7;
  }

  /** Must be called inside a user gesture (click, keypress) before any sound. */
  async unlock() {
    if (this.ctx) {
      if (this.ctx.state === "suspended") await this.ctx.resume();
      return;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    this.ctx = new Ctx();
    this.master = this.ctx.createGain();
    this.master.gain.value = this.volume;
    this.master.connect(this.ctx.destination);
    if (this.ctx.state === "suspended") await this.ctx.resume();
  }

  setVolume(v) {
    this.volume = Math.max(0, Math.min(1, v));
    if (this.master) this.master.gain.setTargetAtTime(this.volume, this.ctx.currentTime, 0.05);
  }

  setMuted(m) { this.muted = !!m; }
  silentMode(on) { this.silent = !!on; }

  play(name) {
    if (!this.ctx || this.muted) return;
    if (this.silent && ROOM_FACING.has(name)) return;
    const tones = CUES[name];
    if (!tones) return;
    const now = this.ctx.currentTime;
    for (const t of tones) {
      const osc = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      osc.type = t.type || "sine";
      osc.frequency.setValueAtTime(t.freq, now + (t.when || 0));
      if (t.sweep_to != null) {
        osc.frequency.exponentialRampToValueAtTime(t.sweep_to, now + (t.when || 0) + t.dur);
      }
      // Soft ASR envelope so each tone fades in + out instead of clicking.
      g.gain.setValueAtTime(0, now + (t.when || 0));
      g.gain.linearRampToValueAtTime(t.gain, now + (t.when || 0) + 0.02);
      g.gain.linearRampToValueAtTime(0, now + (t.when || 0) + t.dur);
      osc.connect(g);
      g.connect(this.master);
      osc.start(now + (t.when || 0));
      osc.stop(now + (t.when || 0) + t.dur + 0.05);
    }
  }
}

export const audioCues = new AudioCues();

// Auto-unlock on the first user gesture — covers /admin, /, /track, /present
// without each page having to wire its own listener.
let unlocked = false;
const unlockOnce = async () => {
  if (unlocked) return;
  unlocked = true;
  await audioCues.unlock();
  window.removeEventListener("pointerdown", unlockOnce);
  window.removeEventListener("keydown", unlockOnce);
};
window.addEventListener("pointerdown", unlockOnce, { once: false });
window.addEventListener("keydown", unlockOnce, { once: false });

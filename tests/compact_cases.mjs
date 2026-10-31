import { readFileSync } from "node:fs";

globalThis.location = { protocol: "http:", host: "127.0.0.1:9" };
globalThis.WebSocket = class { close() {} send() {} };
const presets = JSON.parse(readFileSync(new URL("../element_forge/app/app_presets.json", import.meta.url), "utf-8"));
globalThis.fetch = async () => ({ ok: true, json: async () => ({ ...presets, missing: {} }) });

const P = await import("../web/efa/ui/presets.js");
const S = await import("../web/efa/ui/state.js");
const R = await import("../web/efa/ui/run.js");
await P.loadPresets();

const clips = [
  { name: "tall.mp4", width: 1080, height: 1920, fps: 30, frames: 90, seconds: 3 },
  { name: "wide.mp4", width: 1920, height: 1080, fps: 25, frames: 250, seconds: 10 },
  { name: "odd.mp4", width: 853, height: 480, fps: 24, frames: 33, seconds: 1.375 },
  { name: "still.png", width: 1600, height: 1200, fps: 24, frames: 72, seconds: 3, still: true },
];
const variants = [
  {},
  { a: [300, 400], word: "hand" },
  { a: [500, 200], b: [700, 900], dir: 135, depth: 0.2, start: 0.5, strength: "strong" },
  { a: [200, 300], ground: "light", inpaint: true, scene: "A man on a skateboard in a park.", night: true },
  { a: [640, 360], look: "pale blue gas flame", motion: "sways gently", strength: "subtle" },
  { a: [100, 100], prompt: "My own words", inpaint: false, adv: { "Particle amount": 1.5 } },
  { a: [300, 400], box: [50, 600, 260, 380] },
  { a: [500, 500], b: [900, 700], box: [420, 120, 333, 301.5] },
];
const out = [];
for (const e of presets.effects) for (const s of e.styles) for (const clip of clips) for (const [vi, v] of variants.entries()) {
  const fx = S.blankEffect(e.id, s.id);
  if (v.a) fx.where.a = { x: v.a[0], y: v.a[1], ...(v.ground ? { ground: v.ground } : {}) };
  if (v.b) fx.where.b = { x: v.b[0], y: v.b[1] };
  if (v.word) fx.where.word = v.word;
  if (v.dir != null) fx.dir = v.dir;
  if (v.depth) fx.depth = v.depth;
  if (v.start) fx.timing.start = v.start;
  if (v.strength) fx.strength = v.strength;
  if (v.look) fx.text.look = v.look;
  if (v.motion) fx.text.motion = v.motion;
  if (v.prompt) fx.prompt = v.prompt;
  if (v.inpaint != null) fx.adv[P.INPAINT] = v.inpaint;
  if (v.adv) Object.assign(fx.adv, v.adv);
  if (v.box) fx.box = { x: v.box[0], y: v.box[1], w: v.box[2], h: v.box[3] };
  fx.seed = { mode: "keep", value: 1234 };
  const shot = { clip, night: !!v.night, scene: v.scene || "" };
  for (const scale of [1, 0.5]) {
    out.push({ effect: { ...fx, seed: 1234 }, shot, scale, values: R.valuesFor(fx, shot, scale), name: `${e.id}/${s.id} ${clip.name} v${vi} x${scale}` });
  }
}
process.stdout.write(JSON.stringify(out), () => process.exit(0));

import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { efaValues } from "./ui/run.js";
import { playhead } from "./ui/stage.js";
import { decodeLive } from "./ui/livesim.js";
import { effStyle, guideStyle, guideNow, emitterKind } from "./emitter.js";

export const PARTICLE_SEED = "Particle seed";
export const PREROLL = "Particle pre-roll (s, -2 = as in the preset, -1 = auto)";
export const PARTICLE_EMITTER = "Particle emitter (app, JSON)";
export const DISSOLVE_EXTRA = "Dissolve extra (JSON)";
const DEBOUNCE = 100;
const KEEP = 8;
const LOOK_ONLY = new Set(["colors", "color_var", "glow", "trail", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "plate_color",
  "dof", "focus", "bloom", "halo", "ambient", "relief", "shell", "look", "blend", "guide_style", "sprite", "sprite_gain", "sprite_aspect",
  "sprite_occlude", "sprite_play", "shutter", "depth_guide", "depth_edge"]);
function simSig(body) {
  const v = { ...body.values };
  for (const k of [PARTICLE_EMITTER, DISSOLVE_EXTRA]) {
    if (!v[k]) continue;
    try { v[k] = JSON.stringify(Object.fromEntries(Object.entries(JSON.parse(v[k])).filter(([x]) => !LOOK_ONLY.has(x)))); } catch {  }
  }
  return JSON.stringify({ ...body, values: v });
}
let lastSimSig = null;

export const livePreviews = (st) => (!!st?.settings?.Particles && (st.variant || "app") === "app") || st?.variant === "dissolve"
  || st?.variant === "climb";
export const motionPreview = (st, f) => !!st && !livePreviews(st) && st.cost === "gen" && f?.mode === "advanced" && !!f?.follows_motion
  && (st.placement === "point" || st.placement === "window");

export const shapePreview = (st, e) => !!st && guideStyle(st) && guideNow(st, e) === "object shape";

let fxOf = () => ({});
let timer = 0, lastSig = null, busy = null, queued = false, holdPoll = 0;
const kept = new Map();
const shapeKept = new Map();

export function initLive({ fx }) {
  fxOf = fx;
  S.subscribe(() => poke());
  holdPoll = setInterval(() => { if ((S.ui.liveMode || "play") === "hold") poke(); }, 400);
}
export const liveMode = () => S.ui.liveMode || "play";
export function setLiveMode(m) { S.setUI({ liveMode: m }); poke(true); }
export function refresh() { lastSig = null; lastSimSig = null; poke(true); }
export function poke(now = false) {
  clearTimeout(timer);
  timer = setTimeout(request, now ? 0 : DEBOUNCE);
}

function target() {
  const shot = S.getShot(), e = S.activeEffect(), c = shot.clip;
  if (!e || !c) return null;
  const st = effStyle(P.styleDef(e.kind, e.style), e);
  if (livePreviews(st)) return { shot, e, c, st, kind: "particles" };
  const parts = [motionPreview(st, fxOf() || {}) && "motion", shapePreview(st, e) && "shape"].filter(Boolean);
  return parts.length ? { shot, e, c, st, kind: "motion", parts } : null;
}

async function request() {
  const t = target();
  if (!t || t.kind === "motion") requestValues();
  if (!t) {
    if (S.ui.liveSim || S.ui.liveMotion) S.setUI({ liveSim: null, liveMotion: null });
    lastSig = null;
    return;
  }
  if (t.kind === "motion") return requestMotion(t);
  if (S.ui.liveMotion) S.setUI({ liveMotion: null });
  const { shot, e, c, st } = t;
  const { values, pending } = efaValues(shot);
  if (pending) Object.assign(values, await pending);
  const f = fxOf() || {};
  values[PARTICLE_SEED] = Number.isFinite(+f.particle_seed) ? +f.particle_seed : 42;
  values[PREROLL] = Number.isFinite(+f.preroll) ? +f.preroll : -2;
  if (f.mode === "advanced" && f.emitter_values) values[st.variant === "dissolve" ? DISSOLVE_EXTRA : PARTICLE_EMITTER] = f.emitter_values;
  const mode = st.variant === "dissolve" ? "play" : liveMode();
  const frame = mode === "hold" ? Math.round(playhead() * (c.fps || 25)) : 0;
  const body = { values, variant: st.variant || "app", mode, frame };
  const sig = JSON.stringify(body);
  if (sig === lastSig) return;
  if (busy) { queued = true; return; }
  lastSig = sig;
  const prev = S.ui.liveSim;
  const same = prev && prev.clip === c.name && prev.effect === e.id;
  const ss = simSig(body), lookOnly = same && !!prev.data && ss === lastSimSig;
  lastSimSig = ss;
  S.setUI({ liveSim: { ...(same ? prev : {}), clip: c.name, effect: e.id, status: "running", lookOnly, error: null } });
  const have = same ? prev.data?.header.key : null;
  const t0 = performance.now();
  busy = fetch("/element-forge/api/live", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, have }) });
  try {
    const r = await busy;
    if (r.status === 409) return;
    if (!r.ok) {
      let msg = `${r.status}`;
      try { msg = (await r.json()).error || msg; } catch {  }
      throw new Error(msg);
    }
    const d = decodeLive(await r.arrayBuffer());
    const only = !d.header.arrays?.length;
    if (only && !kept.has(d.header.key)) { lastSig = null; return poke(true); }
    const data = only ? kept.get(d.header.key) : d;
    if (only) for (const k of ["params", "base", "amount", "emitter", "look"]) if (k in d.header) data.header[k] = d.header[k];
    kept.delete(d.header.key);
    kept.set(d.header.key, data);
    while (kept.size > KEEP) kept.delete(kept.keys().next().value);
    const cur = target();
    if (!cur || cur.c.name !== c.name || cur.e.id !== e.id) return;
    S.setUI({ liveSim: { clip: c.name, effect: e.id, data, look: { ...d.header.look, kind: d.header.kind || "particles" }, status: "ready", lookOnly: false, error: null,
      ms: Math.round(performance.now() - t0), server: d.header.ms, leftOut: d.header.left_out || [], fallbacks: d.header.fallbacks || [] } });
  } catch (err) {
    S.setUI({ liveSim: { ...(S.ui.liveSim || {}), clip: c.name, effect: e.id, status: "failed", error: err.message } });
  } finally {
    busy = null;
    if (queued) { queued = false; poke(true); }
  }
}

let lastValSig = null, valBusy = false, valQueued = false;
async function requestValues() {
  const shot = S.getShot(), e = S.activeEffect(), c = shot.clip;
  const st0 = e ? P.styleDef(e.kind, e.style) : null;
  if (!e || !c || !st0 || emitterKind(st0) === "dissolve") return;
  const { values, pending } = efaValues(shot);
  if (pending) Object.assign(values, await pending);
  const f = fxOf() || {};
  values.Particles = true;
  values["Particle preset"] = f.guide_particles && f.guide_particles !== "style default" ? f.guide_particles : P.startPreset(st0);
  values[PARTICLE_SEED] = Number.isFinite(+f.particle_seed) ? +f.particle_seed : 42;
  values[PREROLL] = Number.isFinite(+f.preroll) ? +f.preroll : -2;
  if (f.mode === "advanced" && f.emitter_values) values[PARTICLE_EMITTER] = f.emitter_values;
  const body = { values, variant: st0.variant || "app", mode: "play", frame: 0 };
  const sig = JSON.stringify(body);
  const lv = S.ui.liveValues;
  if (sig === lastValSig && lv?.effect === e.id && lv?.clip === c.name) return;
  if (valBusy) { valQueued = true; return; }
  lastValSig = sig;
  valBusy = true;
  if (lv?.effect === e.id && lv?.clip === c.name) S.setUI({ liveValues: { ...lv, status: "running" } });
  try {
    const r = await fetch("/element-forge/api/live-values", { method: "POST", headers: { "Content-Type": "application/json" }, body: sig });
    if (!r.ok) {
      let msg = `${r.status}`;
      try { msg = (await r.json()).error || msg; } catch {  }
      throw new Error(msg);
    }
    const d = decodeLive(await r.arrayBuffer());
    const cur = S.activeEffect();
    if (!cur || cur.id !== e.id || S.getShot().clip?.name !== c.name) return;
    S.setUI({ liveValues: { clip: c.name, effect: e.id, header: d.header, status: "ready", error: null } });
  } catch (err) {
    lastValSig = null;
    S.setUI({ liveValues: { clip: c.name, effect: e.id, header: S.ui.liveValues?.header || null, status: "failed", error: err.message } });
  } finally {
    valBusy = false;
    if (valQueued) { valQueued = false; poke(true); }
  }
}

async function requestMotion({ shot, e, c, parts }) {
  const { values, pending } = efaValues(shot);
  if (pending) Object.assign(values, await pending);
  const body = { values, variant: "app", kind: "motion", parts };
  const sig = JSON.stringify(body);
  if (sig === lastSig) return;
  if (busy) { queued = true; return; }
  lastSig = sig;
  if (S.ui.liveSim) S.setUI({ liveSim: null });
  const prev = S.ui.liveMotion;
  S.setUI({ liveMotion: { ...(prev && prev.effect === e.id && prev.clip === c.name ? prev : {}), clip: c.name, effect: e.id, status: "running", error: null } });
  const still = () => { const cur = target(); return cur && cur.kind === "motion" && cur.c.name === c.name && cur.e.id === e.id; };
  const shapeSig = JSON.stringify(Object.fromEntries(Object.entries(values).filter(([k]) => !k.startsWith("Follows motion"))));
  let data = { parts: [] }, arrays = {};
  try {
    for (const [i, p] of parts.entries()) {
      let d = p === "shape" ? shapeKept.get(shapeSig) : null;
      if (!d) {
        busy = fetch("/element-forge/api/live", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, parts: [p] }) });
        const r = await busy;
        if (r.status === 409) return;
        if (!r.ok) {
          let msg = `${r.status}`;
          try { msg = (await r.json()).error || msg; } catch {  }
          throw new Error(msg);
        }
        d = decodeLive(await r.arrayBuffer());
        if (p === "shape") {
          shapeKept.set(shapeSig, d);
          while (shapeKept.size > 4) shapeKept.delete(shapeKept.keys().next().value);
        }
      }
      if (!still()) return;
      data = { ...data, ...d.header, parts: [...data.parts, p] };
      arrays = { ...arrays, ...(d.arrays || {}) };
      S.setUI({ liveMotion: { clip: c.name, effect: e.id, data, arrays, status: "ready", waiting: parts.slice(i + 1), error: null } });
    }
  } catch (err) {
    S.setUI({ liveMotion: { ...(S.ui.liveMotion || {}), clip: c.name, effect: e.id, status: "failed", error: err.message } });
  } finally {
    busy = null;
    if (queued) { queued = false; poke(true); }
  }
}

import { getJSON } from "./lib.js";

let data = null;
export async function loadPresets() {
  data = await getJSON("/element-forge/api/presets");
  return data;
}
export const presets = () => data;
export const effectDef = (kind) => data?.effects.find((e) => e.id === kind) || null;
export const styleDef = (kind, style) => effectDef(kind)?.styles.find((s) => s.id === style) || null;
export const DIRECT_LOOK = "Particles: direct look (no LTX, pro)";
export const PLACEMENT = "Placement (auto / point / area / object / frame / between)";
export const PLACES = [["point", "Point", "At point A: the element stands on it"], ["area", "Area", "In a frame around point A that you size"],
  ["object", "Object", "On the whole clicked object"], ["frame", "Frame", "Over the whole picture"],
  ["between", "A–B", "From point A to point B (Shift-click B)"]];
const PL_OF = { point: "point", window: "area", object: "object", frame: "frame", ab: "between" };
const PL_TO = { point: "point", area: "window", object: "object", frame: "frame", between: "ab" };
const PL_SHAPE = { frame: "whole frame", object: "object mask", between: "line A-B" };
export const placeFixed = (st) => !st || (st.variant || "app") !== "app";
export const placeOwn = (st) => PL_OF[st?.placement] || "point";
export const placeOf = (e, st) => (placeFixed(st) ? placeOwn(st) : e?.adv?.[PLACEMENT] || placeOwn(st));
export const SIDE = "Emitter side";
export const sideOf = (e, st) => e?.adv?.[SIDE] || st?.settings?.[SIDE] || "bottom";
function withPlace(st, e) {
  const side = e?.adv?.[SIDE];
  if (side && !placeFixed(st) && side !== (st.settings?.[SIDE] || "bottom")) st = { ...st, settings: { ...st.settings, [SIDE]: side } };
  const want = e?.adv?.[PLACEMENT];
  if (!want || placeFixed(st) || want === placeOwn(st) || !PL_TO[want]) return st;
  const s0 = st.settings || {}, sets = { ...s0 };
  if (!e.adv?.["Particle emitter"]) {
    if (PL_SHAPE[want]) sets["Particle emitter"] = PL_SHAPE[want];
    else if (["whole frame", "line A-B", "object mask", "object contour", "object bottom edge"].includes(s0["Particle emitter"])) delete sets["Particle emitter"];
  }
  if (want === "frame") sets["Sticks to scene (off = object)"] = s0["Sticks to scene (off = object)"] ?? true;
  if (want === "between") sets["Window A-B automatic"] = true;
  return { ...st, placement: PL_TO[want], settings: sets };
}
export function styleOf(e) {
  const st0 = e ? styleDef(e.kind, e.style) : null;
  if (!st0) return st0;
  const st = withPlace(st0, e);
  const a = e.adv || {}, s0 = st.settings || {};
  const parts = !!(a.Particles ?? s0.Particles), direct = !!(a[DIRECT_LOOK] ?? s0[DIRECT_LOOK]);
  const preset = a["Particle preset"] || s0["Particle preset"];
  if (parts === !!s0.Particles && direct === !!s0[DIRECT_LOOK] && preset === s0["Particle preset"]) return st;
  return { ...st, cost: direct && (parts || st.variant === "climb") ? "calc" : "gen",
    settings: { ...s0, Particles: parts, [DIRECT_LOOK]: direct, ...(preset ? { "Particle preset": preset } : {}) } };
}
export const startPreset = (st) => st?.settings?.["Particle preset"] || st?.guide_particles || "magic dust";
export const missingFor = (variant) => data?.missing?.[variant] || { nodes: [], models: [] };

const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const strip = (s) => (s || "").trim().replace(/[.\s]+$/, "");
const STRENGTH = { subtle: "subtle, small and delicate", strong: "large, intense and dramatic" };

export function directionWords(deg) {
  if (deg == null) return "";
  const names = ["upward", "up and to the right", "to the right", "down and to the right", "downward", "down and to the left", "to the left", "up and to the left"];
  return names[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}
const FALLS = { rain: 172, snow: 180, liquid: 180 };
export const naturalDir = (st) => FALLS[st?.settings?.["Particle preset"]] ?? 0;

export function promptOf(effect) {
  const p = styleDef(effect?.kind, effect?.style)?.prompt;
  return p?.light_ground && effect?.where?.a?.ground === "light" ? { ...p, ...p.light_ground } : p;
}

export function changedBlocks(effect) {
  const p = promptOf(effect);
  if (!p) return [];
  return ["look", "motion", "contact"].filter((k) => (effect.text[k] ?? "") !== "" && strip(effect.text[k]) !== strip(p[k]));
}

export const INPAINT = "Inpaint (off = on black)";
export const inScene = (effect) => {
  const st = styleDef(effect?.kind, effect?.style);
  return st?.placement !== "frame" && !!(effect?.adv?.[INPAINT] ?? st?.settings?.[INPAINT]);
};
export const LIBRARY = "Element from library", LIBRARY_ELEMENT = "Library element";
export const fromLibrary = (effect) => !!(effect?.adv?.[LIBRARY] && effect?.adv?.[LIBRARY_ELEMENT]) && !inScene(effect);
export const canPaintIn = (st) => !!st && st.cost === "gen" && st.variant === "app" && st.placement !== "frame";
export const objectWord = (effect) => (effect?.where?.word || "").trim();
export const fillWord = (s, word) => (s == null ? s : String(s).replace(/\{([^{}|]*)\|([^{}]*)\}/g, (m, a, b) => (word ? a.replace("%", word) : b)));
export const inpaintSettings = (kind) => ({ ...(data?.inpaint?.default || {}), ...(data?.inpaint?.[kind] || {}) });
export const withoutBlack = (s) => (s || "")
  .replace(/,?\s*(?:filmed |shot )?(?:on|against|over) (?:a )?(?:pure |plain )?black (?:background|backdrop)/gi, "")
  .replace(/,?\s*surrounded by black space/gi, "")
  .replace(/([.!?])\s*,\s*/g, "$1 ")
  .replace(/([.!?]\s+)([a-z])/g, (m, a, b) => a + b.toUpperCase())
  .trim();

export const QUICK_COLOURS = [["orange", "#ff7a1a"], ["red", "#e8202a"], ["gold", "#ffc23a"], ["green", "#38d26a"],
  ["blue", "#2f7bff"], ["violet", "#9b5cff"], ["white", "#f2f4ff"]];
export const QUICK = {
  amount: { less: [0.5, "sparse"], more: [2, "dense and abundant"] },
  speed: { slower: [0.5, "slow and gentle"], faster: [1.8, "fast and energetic"] },
  size: { smaller: [0.6, "small"], bigger: [1.6, "big"] },
};
const rgbOf = (hex) => [1, 3, 5].map((i) => parseInt(String(hex).slice(i, i + 2), 16) || 0);
export function colourName(hex) {
  const [r, g, b] = rgbOf(hex);
  let best = QUICK_COLOURS[0][0], bd = Infinity;
  for (const [n, h] of QUICK_COLOURS) {
    const [r2, g2, b2] = rgbOf(h), d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2;
    if (d < bd) { bd = d; best = n; }
  }
  return best;
}
export function quickWords(effect) {
  const q = effect?.quick || {};
  const w = q.colour ? [`mainly ${colourName(q.colour)}`] : [];
  for (const k of ["amount", "speed", "size"]) if (QUICK[k][q[k]]) w.push(QUICK[k][q[k]][1]);
  return w.join(", ");
}

export function composePrompt(effect) {
  return fillWord(composeRaw(effect), objectWord(effect));
}
function composeRaw(effect) {
  const st = styleDef(effect.kind, effect.style);
  const p = promptOf(effect);
  if (!p) return null;
  const paint = inScene(effect);
  const tail = paint ? "" : data?.tail_on_black || "";
  if (effect.prompt != null) return paint ? effect.prompt : withTail(effect.prompt, tail);
  const qw = quickWords(effect);
  const untouched = !changedBlocks(effect).length && effect.strength === "normal" && effect.dir == null && !qw;
  if (untouched && p.preset) return paint ? withoutBlack(p.preset) : p.preset;
  const block = (k) => strip(effect.text[k] !== undefined && effect.text[k] !== "" ? effect.text[k] : p[k]);
  const lookChanged = changedBlocks(effect).includes("look");
  let what = strip((lookChanged && p.what_plain) || p.what || effect.text.what || "");
  if (!what) what = strip(effect.text.look) || "A glowing element";
  if (effect.strength !== "normal") what = `${what}, ${STRENGTH[effect.strength]}`;
  if (qw) what = `${what}, ${qw}`;
  let action = block("motion");
  const dw = directionWords(effect.dir);
  if (dw && st.dir !== "dissolve") action = action ? `${action}, moving ${dw}` : `moves ${dw}`;
  const contact = block("contact");
  const first = cap([what, action].filter(Boolean).join(" ") + (contact ? `, and ${contact}` : "")) + ".";
  const look = block("look");
  return [first, look ? cap(look) + "." : ""].filter(Boolean).join(" ") + tail;
}

export const withTail = (s, tail = data?.tail_on_black || "") => (!tail || /black background/i.test(s || "") ? s : `${(s || "").trimEnd()}${tail}`);
export const wordCount = (s) => (s || "").trim().split(/\s+/).filter(Boolean).length;

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
export function styleOf(e) {
  const st = e ? styleDef(e.kind, e.style) : null;
  if (!st) return st;
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
  const untouched = !changedBlocks(effect).length && effect.strength === "normal" && effect.dir == null;
  if (untouched && p.preset) return paint ? withoutBlack(p.preset) : p.preset;
  const block = (k) => strip(effect.text[k] !== undefined && effect.text[k] !== "" ? effect.text[k] : p[k]);
  const lookChanged = changedBlocks(effect).includes("look");
  let what = strip((lookChanged && p.what_plain) || p.what || effect.text.what || "");
  if (!what) what = strip(effect.text.look) || "A glowing element";
  if (effect.strength !== "normal") what = `${what}, ${STRENGTH[effect.strength]}`;
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

import { postJSON } from "./lib.js";
import * as P from "./presets.js";
import { TINTS, LEVELS } from "./look.js";

const DIRS = { preset: null, up: 0, "up-right": 45, right: 90, "down-right": 135, down: 180, "down-left": 225, left: 270, "up-left": 315 };
const DEPTHS = { "far back": -0.3, back: -0.15, "as placed": 0, front: 0.15, "far front": 0.3 };
const COLOURS = { original: null, orange: TINTS[0], red: TINTS[1], "warm white": TINTS[2], blue: TINTS[3], purple: TINTS[4], green: TINTS[5] };
const LEVEL_NAMES = LEVELS.map((t) => t.toLowerCase());
const nameOf = (table, v) => Object.keys(table).find((k) => table[k] === v) ?? "custom";

const SYSTEM = `You set up Element Forge, an app that adds one visual effect (fire, sparks, lightning, smoke, snow, magic, dissolve ...) into the user's own video clip. You see the frame of the clip where the effect starts and read the user's wish. Choose the app settings that fulfil the wish and answer only with the JSON object of the schema.
Rules:
- "style" must be one of the listed style ids. Pick the one that fits the wish best.
- Keep every current value the wish does not ask to change.
- look, motion and contact are short English phrases (at most 15 words each) that go into the prompt of the video model: look = colour, size, texture; motion = how it moves; contact = what happens where it meets something. Use "" to keep the style's own wording.
- start and end are seconds in the clip; end = -1 means until the clip ends.
- object is the English word for the thing in the frame the effect belongs to (for example "hand", "skateboard", "car"), or "" if none.
- note is one short sentence to the user, for example what they still have to click.`;

export function schema(styleIds) {
  const str = { type: "string" };
  return {
    type: "object", additionalProperties: false,
    properties: {
      style: { type: "string", enum: styleIds }, strength: { type: "string", enum: ["subtle", "normal", "strong"] },
      look: str, motion: str, contact: str,
      direction: { type: "string", enum: Object.keys(DIRS) }, depth: { type: "string", enum: Object.keys(DEPTHS) },
      start: { type: "number" }, end: { type: "number" },
      light: { type: "string", enum: LEVEL_NAMES }, glow: { type: "string", enum: LEVEL_NAMES },
      colour: { type: "string", enum: Object.keys(COLOURS) }, object: str, note: str,
    },
    required: ["style", "strength", "look", "motion", "contact", "direction", "depth", "start", "end", "light", "glow", "colour", "object", "note"],
  };
}

function current(e, clip) {
  return {
    style: e.kind ? `${e.kind}/${e.style}` : "none", strength: e.strength,
    look: e.text.look, motion: e.text.motion, contact: e.text.contact,
    direction: nameOf(DIRS, e.dir), depth: nameOf(DEPTHS, e.depth || 0),
    start: e.timing.start, end: e.timing.end ?? -1, light: LEVEL_NAMES[e.look.light], glow: LEVEL_NAMES[e.look.glow],
    colour: nameOf(COLOURS, e.look.tint), object: e.where.word, clip_seconds: clip?.seconds ?? null,
  };
}

export async function suggest(e, clip, wish, allowed) {
  const styles = P.presets().effects.flatMap((f) => f.styles.filter(allowed).map((s) => ({ id: `${f.id}/${s.id}`, effect: f.name, style: s.name, text: s.text })));
  const list = styles.map((s) => `${s.id}: ${s.effect} – ${s.style}. ${s.text || ""}`).join("\n");
  const text = `Styles:\n${list}\n\nCurrent settings: ${JSON.stringify(current(e, clip))}\n\nWish: ${wish}`;
  const r = await postJSON("/element-forge/api/bonsai", { system: SYSTEM, text, clip: clip?.name || null, time: e.timing.start || 0, schema: schema(styles.map((s) => s.id)),
    max_tokens: 500, temperature: 0.2, keep: true });
  let proposal;
  try { proposal = JSON.parse(r.text); } catch { throw new Error("Bonsai did not answer in the expected form. Try again or say it differently."); }
  return { proposal, seconds: r.seconds };
}

const PICTURE = `${SYSTEM}
- The picture is a collage. Left: reference pictures of the effect the user wants. Right: the frame of the user's clip; the effect goes at the yellow ring, inside the yellow frame.
- Make the reference's effect at that place: pick the style that comes closest to it, and write look, motion and contact so they describe the reference's effect (colour, shape, size, texture, how it moves), fitted to what is at the yellow mark. Leave out the reference's background, people and objects.
- The yellow marks are only in this collage, the user does not see them: never mention them or the collage in note. A yellow ring means the place is set already: then note does not ask to click it.`;

export async function fromPictures(e, clip, images, words, allowed) {
  const styles = P.presets().effects.flatMap((f) => f.styles.filter(allowed).map((s) => ({ id: `${f.id}/${s.id}`, effect: f.name, style: s.name, text: s.text })));
  const list = styles.map((s) => `${s.id}: ${s.effect} – ${s.style}. ${s.text || ""}`).join("\n");
  const wish = String(words || "").trim() || "Make the effect of the reference pictures at the yellow mark.";
  const text = `Styles:\n${list}\n\nCurrent settings: ${JSON.stringify(current(e, clip))}\n\nWish: ${wish}`;
  const a = e.where?.a ? [e.where.a.x, e.where.a.y] : null;
  const box = e.box ? [e.box.x, e.box.y, e.box.w, e.box.h] : null;
  const r = await postJSON("/element-forge/api/bonsai/reference", { system: PICTURE, text, images, clip: clip?.name || null, time: e.timing.start || 0,
    a, box, schema: schema(styles.map((s) => s.id)), max_tokens: 600 });
  let proposal;
  try { proposal = JSON.parse(r.text); } catch { throw new Error("Bonsai did not answer in the expected form. Try again."); }
  return { proposal, seconds: r.seconds, ref: r.ref };
}

export async function smallPicture(file, side = 1024) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, side / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(bmp.width * k)); c.height = Math.max(1, Math.round(bmp.height * k));
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close?.();
  return c.toDataURL("image/jpeg", 0.9);
}

export function changes(e, p, clip) {
  const out = [];
  const add = (key, label, from, to) => { if (JSON.stringify(from) !== JSON.stringify(to)) out.push({ key, label, from, to }); };
  const [kind, style] = String(p.style || "").split("/");
  const st = P.styleDef(kind, style);
  if (st) add("style", "Effect", e.kind ? `${P.effectDef(e.kind)?.name} – ${P.styleDef(e.kind, e.style)?.name}` : "none", `${P.effectDef(kind).name} – ${st.name}`);
  if (["subtle", "normal", "strong"].includes(p.strength)) add("strength", "Strength", e.strength, p.strength);
  const def = st?.prompt || P.styleDef(e.kind, e.style)?.prompt;
  for (const k of ["look", "motion", "contact"]) {
    const t = String(p[k] || "").trim().slice(0, 160);
    if (t && def && t !== (e.text[k] || def[k] || "")) add(k, { look: "Look", motion: "Motion", contact: "Where it touches" }[k], e.text[k] || def[k] || "", t);
  }
  if (p.direction in DIRS) add("direction", "Direction", nameOf(DIRS, e.dir), p.direction);
  if (p.depth in DEPTHS) add("depth", "Depth", nameOf(DEPTHS, e.depth || 0), p.depth);
  const len = clip?.seconds || null;
  if (Number.isFinite(p.start) && len) add("start", "Starts at", e.timing.start, Math.round(Math.min(Math.max(p.start, 0), len - 0.1) * 10) / 10);
  if (Number.isFinite(p.end) && len) add("end", "Ends at", e.timing.end, p.end < 0 || p.end >= len ? null : Math.round(Math.max(p.end, 0.1) * 10) / 10);
  if (LEVEL_NAMES.includes(p.light)) add("light", "Light on the scene", LEVEL_NAMES[e.look.light], p.light);
  if (LEVEL_NAMES.includes(p.glow)) add("glow", "Glow", LEVEL_NAMES[e.look.glow], p.glow);
  if (p.colour in COLOURS) add("colour", "Colour", nameOf(COLOURS, e.look.tint), p.colour);
  const word = String(p.object || "").trim().replace(/[^A-Za-z -]/g, "").slice(0, 40);
  if (word) add("object", "Object", e.where.word || "", word);
  return out;
}

export function apply(e, p, list) {
  const keys = new Set(list.map((c) => c.key));
  const v = Object.fromEntries(list.map((c) => [c.key, c.to]));
  if (keys.has("style")) {
    const [kind, style] = p.style.split("/");
    if (e.kind !== kind) { e.text = { what: "", look: "", motion: "", contact: "" }; e.dir = null; }
    e.kind = kind; e.style = style; e.box = null; e.prompt = null;
    if (P.styleDef(kind, style).dir === "dissolve" && e.dir == null) e.dir = 90;
  }
  if (keys.has("strength")) e.strength = v.strength;
  for (const k of ["look", "motion", "contact"]) if (keys.has(k)) { e.text[k] = v[k]; e.prompt = null; }
  if (keys.has("direction")) e.dir = DIRS[v.direction];
  if (keys.has("depth")) e.depth = DEPTHS[v.depth];
  if (keys.has("start")) e.timing.start = v.start;
  if (keys.has("end")) e.timing.end = v.end;
  if (keys.has("light")) e.look.light = LEVEL_NAMES.indexOf(v.light);
  if (keys.has("glow")) e.look.glow = LEVEL_NAMES.indexOf(v.glow);
  if (keys.has("colour")) e.look.tint = COLOURS[v.colour];
  if (keys.has("object")) e.where.word = v.object;
}

export function stillToDo(e) {
  const st = P.styleDef(e.kind, e.style);
  if (!st) return "";
  if (st.placement === "object" && !e.where.a && e.where.word) return "";
  if (["point", "window", "object"].includes(st.placement) && !e.where.a) return "Now click the place or the object in the preview.";
  if (st.placement === "ab" && (!e.where.a || !e.where.b)) return "Now click point A and point B in the preview.";
  return "";
}

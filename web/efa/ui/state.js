import { clone, store, uid } from "./lib.js";

const MAX_UNDO = 200;
const listeners = new Set();
const undoStack = [];
const redoStack = [];
let gesture = null;
let saveTimer = 0;

export function blankShot() {
  return { v: 1, clip: null, effects: [], active: null, output: { name: "", exr: false }, grade: { exposure: 0, temperature: 0, saturation: 1, blur: 0, blurRange: 0.15 } };
}

export function blankEffect(kind, style) {
  return {
    id: uid(), kind, style,
    where: { a: null, b: null, word: "" },
    box: null,
    dir: null,
    depth: 0,
    strength: "normal",
    text: { what: "", look: "", motion: "", contact: "" },
    prompt: null,
    enhance: "off",
    timing: { start: 0, end: null, fadeIn: 0, fadeOut: 0 },
    look: { light: 2, glow: 2, tint: null, size: 1, bright: 1, mute: {} },
    place: { dx: 0, dy: 0, scale: 1, stretch: 1, rot: 0 },
    keys: { place: [], bright: [] },
    seed: { mode: "new", value: null },
    adv: {},
    quick: {},
    paint: { mask: [], guide: [] },
  };
}

const versions = store.get("versions", {});
const shownVersion = store.get("shown", {});
const onClip = (v) => !v.clip || !shot?.clip || v.clip === shot.clip.name;
export const allVersionsOf = (effectId) => versions[effectId] || [];
export const versionsOf = (effectId) => allVersionsOf(effectId).filter(onClip);
export const shownOf = (effectId) => versionsOf(effectId).find((v) => v.id === shownVersion[effectId]) || null;
export function addVersion(effectId, v) {
  (versions[effectId] ||= []).push(v);
  store.set("versions", versions);
  emit("version");
  persist();
}
const SESSION_ONLY = new Set(["preview", "previewError"]);
export const savedVersions = (vs) => Object.fromEntries(Object.entries(vs || {}).map(([e, list]) =>
  [e, (list || []).map((v) => Object.fromEntries(Object.entries(v).filter(([k]) => !SESSION_ONLY.has(k))))]));
export function updateVersion(effectId, id, patch) {
  const v = allVersionsOf(effectId).find((x) => x.id === id);
  if (!v) return;
  Object.assign(v, patch);
  store.set("versions", versions);
  emit("version");
  if (Object.keys(patch).some((k) => !SESSION_ONLY.has(k))) persist();
}
export function showVersion(effectId, id) {
  shownVersion[effectId] = id;
  store.set("shown", shownVersion);
  emit("version");
  persist();
}

function upgrade(s) {
  if (!s) return blankShot();
  const out = { ...blankShot(), ...s };
  out.effects = (s.effects || []).map((e) => {
    const d = blankEffect(e.kind, e.style);
    const m = { ...d, ...e, id: e.id };
    for (const k of ["where", "timing", "look", "place", "keys", "seed", "paint", "text", "quick"]) m[k] = { ...d[k], ...(e[k] || {}) };
    return m;
  });
  return out;
}
let shot = upgrade(store.get("shot", null));
export const ui = { mode: store.get("mode", "basic"), step: null, tool: "point", selected: null };

export const getShot = () => shot;
export const activeEffect = () => shot.effects.find((e) => e.id === shot.active) || null;
export const canUndo = () => undoStack.length > 0;
export const canRedo = () => redoStack.length > 0;

function emit(reason) {
  for (const fn of listeners) fn(reason);
}
let saveHook = null;
export const setSaveHook = (fn) => (saveHook = fn);
function persist() {
  clearTimeout(saveTimer);
  saveHook?.();
}
function pushUndo(snapshot) {
  undoStack.push(snapshot);
  if (undoStack.length > MAX_UNDO) undoStack.shift();
  redoStack.length = 0;
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const TYPING = new Set(["text", "prompt", "word"]);
let lastTyping = { reason: null, at: 0 };
export function change(fn, reason = "change") {
  const before = JSON.stringify(shot);
  fn(shot);
  if (JSON.stringify(shot) === before) return false;
  const now = Date.now();
  const joins = TYPING.has(reason) && lastTyping.reason === reason && now - lastTyping.at < 1500;
  lastTyping = TYPING.has(reason) ? { reason, at: now } : { reason: null, at: 0 };
  if (!gesture && !joins) pushUndo(before);
  persist();
  emit(reason);
  return true;
}
export function amend(fn) {
  fn(shot);
  persist();
  emit("amend");
}
export function begin() {
  if (!gesture) gesture = JSON.stringify(shot);
}
export function end() {
  if (gesture && gesture !== JSON.stringify(shot)) pushUndo(gesture);
  gesture = null;
  persist();
  emit("gesture-end");
}
export function cancelGesture() {
  if (!gesture) return;
  shot = JSON.parse(gesture);
  gesture = null;
  persist();
  emit("gesture-cancel");
}
export function undo() {
  if (!undoStack.length || gesture) return;
  redoStack.push(JSON.stringify(shot));
  shot = JSON.parse(undoStack.pop());
  persist();
  emit("undo");
}
export function redo() {
  if (!redoStack.length || gesture) return;
  undoStack.push(JSON.stringify(shot));
  shot = JSON.parse(redoStack.pop());
  persist();
  emit("redo");
}

export function setUI(patch) {
  Object.assign(ui, patch);
  if ("mode" in patch) store.set("mode", ui.mode);
  emit("ui");
  if ("step" in patch || "mode" in patch || "tool" in patch) saveHook?.();
}

export const exportState = () => ({ shot, versions, shown: shownVersion });
export function importState({ shot: s = null, versions: vs = {}, shown = {}, ui: u = {} } = {}, { resetUndo = true } = {}) {
  shot = upgrade(s);
  for (const k of Object.keys(versions)) delete versions[k];
  Object.assign(versions, vs || {});
  for (const k of Object.keys(shownVersion)) delete shownVersion[k];
  Object.assign(shownVersion, shown || {});
  if (u.mode) ui.mode = u.mode;
  if ("step" in u) ui.step = u.step;
  if (u.tool) ui.tool = u.tool;
  ui.selected = null;
  gesture = null;
  if (resetUndo) { undoStack.length = 0; redoStack.length = 0; }
  emit("replace");
}
export function applyContext(fn) {
  const before = JSON.stringify(shot);
  fn(shot);
  if (JSON.stringify(shot) === before) return false;
  persist();
  emit("context");
  return true;
}

export function replaceShot(next) {
  pushUndo(JSON.stringify(shot));
  shot = clone(next);
  persist();
  emit("replace");
}

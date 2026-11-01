import { h, getJSON } from "./ui/lib.js";
import { icon } from "./ui/icons.js";
import * as S from "./ui/state.js";
import { loadPresets, styleDef, startPreset, DIRECT_LOOK } from "./ui/presets.js";
import { efaValues, estimate, ltxFrames, RUN_STEPS, runStepOf } from "./ui/run.js";
import { mountStage, render as renderCanvas, releaseMedia, restoreMedia, togglePlay, loadNav, wheelZooms, dragPans, presentResult } from "./ui/stage.js";
import { mountTimeline } from "./ui/timeline.js";
import { mountPanel } from "./panel.js";
import { PANEL_ADV, AI_GUIDE, ALSO_DRAW } from "./emitter.js";
import { beforeRun as shotLineBeforeRun } from "./shotline.js";
import { addRun } from "./finish.js";
import { noteQueued, takeRecipe } from "./versions.js";
import { ltxForBuild, useModelsNode } from "./ui/machine.js";

const CSS_URL = new URL("./efa.css", import.meta.url).href;
const CARDS_CSS_URL = new URL("./cards.css", import.meta.url).href;
const STEPS = [["where", "Where"], ["effect", "Effect"], ["look", "Look"]];
const VIDEO_RE = /\.(mp4|mov|webm|mkv|m4v|avi)$/i;
const IMAGE_RE = /\.(png|jpe?g|webp)$/i;
const STILL_FPS = 24, STILL_SECONDS = 3;
const NOT_MEDIA = "That is neither a video nor a picture. Element Forge takes mp4, mov, webm, mkv, png, jpg or webp.";

let ws = null;
let current = null;
let presetsReady = null;
let panel = null;

function ensureCss() {
  if (document.querySelector(`link[data-efa-css]`)) return;
  document.head.append(h("link", { rel: "stylesheet", href: CSS_URL, "data-efa-css": "1" }), h("link", { rel: "stylesheet", href: CARDS_CSS_URL, "data-efa-cards-css": "1" }));
}

function themeOf() {
  try {
    const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g);
    const light = document.documentElement.classList.contains("light-theme") || (bg ? (+bg[0] + +bg[1] + +bg[2]) / 3 > 140 : false);
    return light ? "light" : "dark";
  } catch { return "dark"; }
}

function build() {
  const el = h("div", { class: "efa-root efa-ws", tabindex: "0", "aria-label": "Element Forge canvas and timeline" });
  const stage = h("div", { class: "efa-stage", "aria-label": "Canvas" });
  const resize = h("div", { class: "efa-tl-resize", title: "Drag to resize the timeline" });
  const timeline = h("section", { class: "efa-timeline", "aria-label": "Timeline" }, resize);
  const banner = h("div", { class: "efa-banner", role: "status", "aria-live": "polite" });
  const picker = h("input", { type: "file", accept: "video/*,image/png,image/jpeg,image/webp", class: "sr-only", tabindex: "-1",
    onchange: () => picker.files[0] && takeVideo(picker.files[0]) });
  const empty = h("div", { class: "empty" }, h("div", { class: "box" },
    h("h2", {}, "Put real VFX into your own video"),
    h("p", {}, "Choose a clip in the Clip step, or drop a video or a picture onto this canvas. Then click where the effect goes."),
    h("button", { class: "btn primary", onclick: () => { picker.value = ""; picker.click(); } }, icon("upload"), "Choose a video or picture")));
  const steps = h("div", { class: "seg efa-steps", role: "group", "aria-label": "Step" },
    ...STEPS.map(([id, t]) => h("button", { "data-step": id, title: `${t} step: its tools in the canvas`, onclick: () => S.setUI({ step: id }) }, t)));
  const drop = h("div", { class: "efa-drop", "aria-hidden": "true" }, h("div", { class: "frame" }, "Drop the video to use it"));
  const helpList = h("dl", {});
  const help = h("div", { class: "help", role: "dialog", "aria-label": "Shortcuts", hidden: true },
    h("div", { class: "help-box" },
      h("div", { class: "row between" }, h("h3", {}, "Shortcuts"), h("button", { class: "icon-btn", "aria-label": "Close", onclick: () => (help.hidden = true) }, icon("close"))),
      helpList));
  stage.append(empty, h("div", { class: "efa-corner" }, steps));
  const cards = h("div", { class: "efa-cards", "aria-label": "Steps" });
  el.append(cards, stage, timeline, banner, drop, help, picker);
  return { el, cards, stage, timeline, resize, banner, steps, help, helpList, empty, picker };
}

let dock = null;
let stepsHost = null;
function setRoot(...nodes) {
  const root = current?.root;
  if (!root) return;
  for (const c of [...root.children]) if (!c.classList.contains("efa-height-grip")) c.remove();
  root.prepend(...nodes);
}
function place() {
  if (!current) return;
  if (dock) {
    dock.box.querySelector(".efa-dock-body").append(ws.el);
    setRoot(ws.cards);
  } else if (stepsHost?.isConnected) {
    stepsHost.classList.add("efa-root", "efa-host");
    stepsHost.dataset.theme = ws.el.dataset.theme;
    if (ws.cards.parentElement !== stepsHost) stepsHost.replaceChildren(ws.cards);
    setRoot(ws.el);
  } else {
    ws.el.prepend(ws.cards);
    setRoot(ws.el);
  }
  if (dock) dock.box.hidden = dock.showing !== "canvas";
  placeProgress();
  renderChrome();
  panel?.render();
  renderCanvas();
  current.host.relayout?.();
}
function setDock(host) {
  if ((dock?.host || null) === (host || null) && (!dock || dock.box.isConnected)) return;
  if (dock) dock.box.remove();
  dock = null;
  if (host) {
    const seg = h("div", { class: "seg efa-dock-seg", role: "group", "aria-label": "Show" },
      h("button", { "data-show": "canvas", onclick: () => showInDock("canvas") }, "Canvas"),
      h("button", { "data-show": "result", onclick: () => showInDock("result"), title: "ComfyUI's results of this workflow" }, "Result"));
    const box = h("div", { class: "efa-root efa-host efa-dock" }, h("div", { class: "efa-dock-body" }));
    box.dataset.theme = ws.el.dataset.theme;
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    host.append(box);
    const sw = h("div", { class: "efa-root efa-dock-switch" }, seg);
    sw.dataset.theme = box.dataset.theme;
    host.append(sw);
    dock = { host, box, sw, seg, showing: "canvas" };
  }
  document.querySelectorAll(".efa-dock-switch").forEach((x) => { if (x !== dock?.sw) x.remove(); });
  syncDockSeg();
  place();
}
let prog = null;
function placeProgress() {
  if (!prog) return;
  const host = dock?.host || ws?.stage;
  if (host && prog.el.parentElement !== host) host.append(prog.el);
  prog.el.classList.toggle("in-dock", !!dock);
}
function progText() {
  if (prog.label) return prog.label;
  const name = prog.step >= 0 ? `${prog.step + 1}/${RUN_STEPS.length} · ${RUN_STEPS[prog.step][0]}` : "Starting…";
  if (!prog.est || !prog.t0) return name;
  const left = Math.round(prog.est - (Date.now() - prog.t0) / 60000);
  return `${name} · ${left >= 1 ? `about ${left} min left` : "almost done"}`;
}
function setProgress(info) {
  if (!info) { if (prog) { clearInterval(prog.tick); prog.el.remove(); } prog = null; return; }
  if (!prog) {
    const text = h("span", { class: "efa-progress-text" }), bar = h("span", { class: "efa-progress-bar" }, h("span", {}));
    prog = { el: h("div", { class: "efa-root efa-progress", role: "status", "aria-live": "polite" }, h("span", { class: "efa-progress-spin", "aria-hidden": "true" }), text, bar), text, bar, step: -1, label: null, est: 0, t0: 0 };
    prog.el.dataset.theme = ws?.el.dataset.theme || "";
    prog.tick = setInterval(() => { if (prog) prog.text.textContent = progText(); }, 15000);
  }
  if (info.label) {
    prog.label = info.label;
    if (info.est) prog.est = info.est;
    prog.bar.hidden = true;
  } else {
    prog.label = null;
    prog.t0 ||= Date.now();
    const i = runStepOf(info.classType);
    if (i >= 0) prog.step = i;
    const share = info.max ? Math.max(0, Math.min(1, info.value / info.max)) : null;
    prog.bar.hidden = share == null;
    if (share != null) prog.bar.firstChild.style.width = `${Math.round(share * 100)}%`;
  }
  prog.text.textContent = progText();
  placeProgress();
}
const runEstimate = () => {
  const sh = S.getShot(), e = S.activeEffect(), est = e ? estimate(e, sh) : null;
  if (!est) return 0;
  const c = sh.clip, ana = c && !c.still && clipInfo.has(c.name) && !clipInfo.get(c.name).analysis ? 3.5 * ltxFrames(c.frames) / 81 : 0;
  return (est.lo + est.hi) / 2 + ana;
};

function showInDock(what) {
  if (!dock) return;
  dock.showing = what;
  syncDockSeg();
  place();
}
function syncDockSeg() {
  if (!dock) return;
  for (const b of dock.seg.children) b.setAttribute("aria-pressed", String(b.dataset.show === dock.showing));
}

let bannerTimer = 0;
function say(text, { error = false, ms = 0 } = {}) {
  if (!ws) return;
  clearTimeout(bannerTimer);
  ws.banner.textContent = text;
  ws.banner.className = "efa-banner show" + (error ? " err" : "");
  if (ms) bannerTimer = setTimeout(() => (ws.banner.className = "efa-banner"), ms);
}

function showHelp() {
  ws.helpList.replaceChildren(...[
    ["Click", "set the point (Shift+click: second point) · select an area"],
    ["Drag inside an area", "move it (Shift: one direction, Ctrl: no snapping)"],
    ["Drag a corner or an edge", "size it freely (Shift: keep its shape, Alt: from the centre)"],
    ["Drag the arrow", "direction (Shift: 15° steps)"],
    ["Mouse wheel", wheelZooms() ? "zoom at the cursor, as in ComfyUI" : "move the view, Ctrl+wheel zooms, as in ComfyUI"],
    dragPans() ? ["Drag on empty space", "move the view, as in ComfyUI"] : null,
    ["Space (hold) + drag, middle button", "move the view"],
    [". · double-click", "fit the clip"], ["Alt+= · Alt+−", "zoom in · out"],
    ["H · P · F · D", "hand · point · area · direction"], ["B · M · E", "brush (Advanced) · move the result · take a colour"], ["[ ]", "brush size"],
    ["Arrow keys", "move the selected (Shift: 10×)"], ["+ −", "the selected larger · smaller"],
    ["Delete", "reset what you clicked"], ["Esc", "cancel a drag"], ["Space (tap)", "play / pause"], ["J · K · L", "back · pause · play (L again: faster)"],
    ["Page Up · Page Down", "one frame back · forward (Shift: 10)"], ["Ctrl+← · Ctrl+→", "previous · next key or edge"],
    ["I · O", "selected effect starts · ends at the playhead"], ["Ctrl+Z · Ctrl+Shift+Z", "undo · redo in the canvas"], ["Ctrl+Enter", "Run (ComfyUI)"],
    ["", "Keys work while the canvas has focus (click into it)."],
  ].filter(Boolean).flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)]));
  ws.help.hidden = !ws.help.hidden;
}

let stills = [];
let clipInfo = new Map();
async function loadStills() {
  try {
    const r = await fetch("/element-forge/api/clips");
    const j = await r.json();
    stills = (j.clips || []).filter((c) => c.still).map((c) => c.name);
    clipInfo = new Map((j.clips || []).map((c) => [c.name, c]));
    panel?.render();
  } catch {  }
}
async function useClip(name) {
  if (!name || S.getShot().clip?.name === name) return;
  try {
    const r = await fetch(`/element-forge/api/clip-meta?name=${encodeURIComponent(name)}${IMAGE_RE.test(name) ? `&seconds=${STILL_SECONDS}` : ""}`);
    const txt = await r.text();
    let m = null;
    try { m = JSON.parse(txt); } catch { m = null; }
    if (!r.ok || !m) throw new Error((m && m.error) || txt.trim().slice(0, 120) || `HTTP ${r.status}`);
    if (S.getShot().clip?.name === name) return;
    const clip = { name, fps: m.fps, frames: m.frames, width: m.width, height: m.height, seconds: m.seconds, codec: m.codec || null, ...(m.still ? { still: true } : {}) };
    const old = S.getShot();
    if (!old.clip) {
      const next = S.blankShot();
      const e = S.blankEffect(null, null);
      next.clip = clip; next.effects = [e]; next.active = e.id;
      S.replaceShot(next);
    } else {
      S.change((sh) => {
        const sx = clip.width / sh.clip.width, sy = clip.height / sh.clip.height;
        for (const e of sh.effects) {
          for (const k of ["a", "b"]) if (e.where[k]) e.where[k] = { x: Math.round(e.where[k].x * sx), y: Math.round(e.where[k].y * sy) };
          e.box = null;
          if (e.timing.end != null) e.timing.end = Math.min(e.timing.end, clip.seconds);
          e.timing.start = Math.min(e.timing.start, Math.max(0, clip.seconds - 0.5));
        }
        sh.clip = clip;
      }, "clip");
    }
    if (!S.ui.step) S.setUI({ step: "where" });
    if (current?.ctx) applyCtx(current.ctx);
  } catch (err) {
    say(`This video cannot be used: ${err.message}`, { error: true, ms: 7000 });
  }
}

const isMedia = (f) => f.type.startsWith("video/") || VIDEO_RE.test(f.name) || /^image\/(png|jpeg|webp)$/.test(f.type) || IMAGE_RE.test(f.name);
async function takeVideo(file) {
  if (!current) return;
  if (!isMedia(file)) { say(NOT_MEDIA, { error: true, ms: 5000 }); return; }
  try {
    say(`Uploading ${file.name}…`);
    const name = await current.host.uploadFile(file);
    say("", { ms: 1 });
    await chooseClip(name);
    if (IMAGE_RE.test(name)) loadStills();
  } catch (err) { say(`Upload failed: ${err.message}`, { error: true, ms: 7000 }); }
}
async function chooseClip(name) {
  if (!IMAGE_RE.test(name) && current?.host.setClip(name) === false) return;
  await useClip(name);
}
function setStillSeconds(sec) {
  const c = S.getShot().clip;
  if (!c?.still) return;
  const frames = Math.max(1, Math.round(Math.min(60, Math.max(0.5, +sec || STILL_SECONDS)) * STILL_FPS));
  if (frames === c.frames) return;
  S.change((sh) => {
    sh.clip = { ...sh.clip, frames, seconds: +(frames / STILL_FPS).toFixed(3) };
    for (const e of sh.effects) {
      if (e.timing.end != null) e.timing.end = Math.min(e.timing.end, sh.clip.seconds);
      e.timing.start = Math.min(e.timing.start, Math.max(0, sh.clip.seconds - 0.5));
    }
  }, "clip");
}

let ctxClip = null;
function applyCtx(ctx) {
  if (!ctx) return;
  if (ctx.mode && ctx.mode !== S.ui.mode) S.setUI({ mode: ctx.mode });
  const seen = ctxClip;
  ctxClip = ctx.clip?.name || null;
  if (ctx.clip?.name && ctx.clip.name !== S.getShot().clip?.name && (!S.getShot().clip?.still || (seen !== null && seen !== ctx.clip.name))) useClip(ctx.clip.name);
  S.applyContext((sh) => {
    sh.night = !!ctx.night;
    sh.scene = ctx.scene || "";
    if (!sh.clip) return;
    let e = sh.effects.find((x) => x.id === sh.active);
    if (!e) { e = S.blankEffect(null, null); sh.effects.push(e); sh.active = e.id; }
    if (ctx.kind && ctx.style && !e.fresh && (e.kind !== ctx.kind || e.style !== ctx.style)) {
      const st = styleDef(ctx.kind, ctx.style);
      if (e.kind !== ctx.kind) e.dir = st?.dir === "dissolve" ? 90 : null;
      else if (st?.dir === "dissolve" && e.dir == null) e.dir = 90;
      e.kind = ctx.kind; e.style = ctx.style; e.box = null;
      e.depth = 0; delete e.groups;
      if (e.adv) { e.adv = { ...e.adv }; for (const k of PANEL_ADV) delete e.adv[k]; }
    }
    if (ctx.strength) e.strength = ctx.strength;
    if (ctx.text) e.text = { what: ctx.text.what || "", look: ctx.text.look || "", motion: ctx.text.motion || "", contact: ctx.text.contact || "" };
    e.prompt = ctx.prompt || null;
    if (ctx.seed) e.seed = { mode: ctx.seed.mode || "keep", value: ctx.seed.value ?? null };
    e.where.word = ctx.word || "";
    const frame = styleDef(e.kind, e.style)?.placement === "frame";
    const adv = { ...e.adv };
    for (const k of [...ALWAYS, ...ADV_ONLY, ...GUIDE_PARTS]) delete adv[k];
    for (const [k, v] of Object.entries(ctx.adv || {})) {
      if ((ADV_ONLY.includes(k) && ctx.mode !== "advanced") || (frame && FOLLOWS_KEYS.includes(k))) continue;
      adv[k] = v;
    }
    const st0 = styleDef(e.kind, e.style);
    if (adv[AI_GUIDE] === "particles" && st0 && !st0.settings?.Particles) {
      adv.Particles = true;
      adv["Particle preset"] = ctx.guideParticles || startPreset(st0);
    }
    if (st0 && ctx.madeBy === "particles") {
      adv.Particles = true;
      adv[DIRECT_LOOK] = true;
      adv["Particle preset"] = ctx.guideParticles || startPreset(st0);
    } else if (st0 && ctx.madeBy === "ai" && st0.settings?.[DIRECT_LOOK]) adv[DIRECT_LOOK] = false;
    if (st0 && adv[ALSO_DRAW] && !adv.Particles && !st0.settings?.Particles) {
      adv.Particles = true;
      adv["Particle preset"] = ctx.guideParticles || startPreset(st0);
    }
    if (st0 && ctx.guideParticles && (adv.Particles || st0.settings?.Particles)) adv["Particle preset"] = ctx.guideParticles;
    e.adv = adv;
  });
}

const FOLLOWS_KEYS = ["Sticks to scene (off = object)", "Track follows the object mask (hands, bodies)", "Fixed on screen (Follows: Screen)"];
const ALWAYS = [...FOLLOWS_KEYS, "Own object mask (off = click)", "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)",
  "LTX upscale x2 (latent upscaler + second pass, test)", "Inpaint (off = on black)"];
const ADV_ONLY = ["Follows motion", "Guide source", AI_GUIDE, "Inpaint sigmas (start 0.909 = tested default)"];
const GUIDE_PARTS = ["Particles", "Particle preset", DIRECT_LOOK];

let saveTimer = 0;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 200);
}
function flushSave() {
  panel?.flush();
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = 0; save(); return; }
  if (presetsReady === true && current && JSON.stringify(ltxForBuild()) !== savedLtx) save();
}
let savedLtx;
let lastValues = { sig: null, at: 0 };
function stableAt(values, vf) {
  if (!vf) return vf;
  const sig = JSON.stringify([values, vf.effect, vf.kind, vf.style]);
  if (sig !== lastValues.sig) lastValues = { sig, at: vf.at };
  return { ...vf, at: lastValues.at };
}
function save() {
  saveTimer = 0;
  if (!current) return;
  const st = S.exportState();
  const { values, values_for, pending, app } = presetsReady === true ? efaValues(st.shot) : { values: {}, values_for: null, pending: null, app: null };
  const json = JSON.stringify({ efa: 1, follows: 2, shot: st.shot, ui: { step: S.ui.step, tool: S.ui.tool, mode: S.ui.mode },
    versions: S.savedVersions(st.versions), shown: st.shown, values, values_for: stableAt(values, values_for) || {}, ...(app ? { app } : {}) });
  current.lastWritten = json;
  savedLtx = JSON.stringify(ltxForBuild());
  current.host.setShot(json);
  if (pending) pending.then(scheduleSave, (err) => say(`The brush strokes could not be uploaded: ${err.message}`, { error: true, ms: 7000 }));
}

function readShot() {
  let obj = null;
  try { obj = JSON.parse(current.host.getShot() || "{}"); } catch { obj = null; }
  if (!obj || obj.efa !== 1) { lastValues = { sig: null, at: 0 }; S.importState({ ui: { step: null } }); return; }
  const vf = obj.values_for;
  lastValues = vf && vf.at ? { sig: JSON.stringify([obj.values || {}, vf.effect, vf.kind, vf.style]), at: vf.at } : { sig: null, at: 0 };
  S.importState({ shot: obj.shot, versions: obj.versions, shown: obj.shown, ui: obj.ui || {} });
}

const typing = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
function onKeyDown(e) {
  const mod = e.ctrlKey || e.metaKey;
  if (!typing(e.target)) {
    if (e.key === "Escape" && !ws.help.hidden) { ws.help.hidden = true; e.preventDefault(); }
    else if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? S.redo() : S.undo(); }
    else if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); S.redo(); }
    else if (mod && e.key === "Enter") { e.preventDefault(); if (!e.repeat) { flushSave(); current?.host.run(); } }
    else if (mod && (e.key === "+" || e.key === "-" || e.key === "=" || e.key === "0")) e.preventDefault();
    else if (e.key === "?") { e.preventDefault(); showHelp(); }
    else if (e.key === " " && !e.target.closest?.(".efa-stage") && !/^(BUTTON|A)$/.test(e.target.tagName)) { e.preventDefault(); togglePlay(); }
  }
  if (e.defaultPrevented || e.key === "Escape" || (!mod && !typing(e.target))) e.stopPropagation();
}
function onWheel(e) {
  if (e.ctrlKey) e.preventDefault();
  if (e.target.closest?.(".efa-stage")) e.stopPropagation();
}
function onMouseDown(e) { if (e.button === 1) e.preventDefault(); }
function onPointerDown(e) {
  if (!typing(e.target)) ws.stage.focus({ preventScroll: true });
  e.stopPropagation();
}
const ASSET = "application/x-comfy-asset-info";
const depth = new Map();
const canTake = (e) => { const t = [...(e.dataTransfer?.types || [])]; return t.includes("Files") || t.includes(ASSET); };
function onDragEnter(e) { if (!canTake(e)) return; e.preventDefault(); e.stopPropagation(); depth.set(e.currentTarget, (depth.get(e.currentTarget) || 0) + 1); e.currentTarget.classList.add("dragging"); }
function onDragLeave(e) {
  if (!canTake(e)) return;
  const n = (depth.get(e.currentTarget) || 0) - 1;
  depth.set(e.currentTarget, Math.max(0, n));
  if (n <= 0) e.currentTarget.classList.remove("dragging");
}
function onDragOver(e) { if (!canTake(e)) return; e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = "copy"; }
function onDrop(e) {
  if (!canTake(e)) return;
  e.preventDefault(); e.stopPropagation();
  depth.set(e.currentTarget, 0); e.currentTarget.classList.remove("dragging");
  const files = [...(e.dataTransfer.files || [])];
  if (!files.length && e.dataTransfer.types.includes(ASSET)) { takeAsset(e.dataTransfer); return; }
  const f = files.find(isMedia);
  if (f) takeVideo(f); else say(NOT_MEDIA, { error: true, ms: 5000 });
}
async function takeAsset(dt) {
  if (!current) return;
  let info = null;
  try { info = JSON.parse(dt.getData(ASSET) || "null"); } catch { info = null; }
  const uri = (dt.getData("text/uri-list") || "").split("\n").map((s) => s.trim()).find((s) => s && !s.startsWith("#")) || "";
  const name = String(info?.filename || "").split(/[\\/]/).pop();
  const pic = IMAGE_RE.test(name) || info?.media_kind === "image";
  if (!(VIDEO_RE.test(name) || info?.media_kind === "video" || pic)) { say(NOT_MEDIA, { error: true, ms: 5000 }); return; }
  try {
    if (info?.type === "input" && name && !info.subfolder) {
      await chooseClip(name);
      return;
    }
    if (!uri) throw new Error("the library gave no address for the file");
    say(`Taking ${info?.display_name || name}…`);
    const r = await fetch(uri);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    await takeVideo(new File([blob], name || (pic ? "picture.png" : "clip.mp4"), { type: blob.type || (pic ? "image/png" : "video/mp4") }));
  } catch (err) { say(`This ${pic ? "picture" : "video"} cannot be taken: ${err.message}`, { error: true, ms: 7000 }); }
}
function onResizeDown(e) {
  e.preventDefault(); e.stopPropagation();
  const handle = ws.resize;
  handle.setPointerCapture(e.pointerId);
  ws.el.dataset.tlSized = "1";
  const h0 = ws.timeline.offsetHeight, k = h0 ? ws.timeline.getBoundingClientRect().height / h0 || 1 : 1;
  const y0 = e.clientY, max = ws.el.clientHeight * 0.6;
  handle.onpointermove = (ev) => ws.el.style.setProperty("--tl-h", `${Math.min(Math.max(h0 + (y0 - ev.clientY) / k, 96), max)}px`);
  handle.onpointerup = handle.onpointercancel = () => { handle.onpointermove = null; handle.onpointerup = handle.onpointercancel = null; };
}

function onLiveError(e) { say(`The live preview could not be shown (${e.detail?.message || "unknown error"}).`, { error: true, ms: 9000 }); }
function onMediaError(e) {
  const clipPlate = String(e.detail?.url || "").includes("/media/input/");
  say(clipPlate ? "Your browser cannot show this video format. ComfyUI can still use it; convert it to H.264 MP4 to see it here."
    : "This result cannot be shown in the browser.", { error: true, ms: 9000 });
}

function renderChrome() {
  if (!ws) return;
  for (const b of ws.steps.children) b.setAttribute("aria-pressed", String(b.dataset.step === S.ui.step));
  ws.steps.hidden = !S.getShot().clip || !!panel;
  ws.cards.hidden = !panel;
  ws.el.classList.toggle("mode-adv", S.ui.mode === "advanced");
}

function teardown() {
  if (!current) return;
  if (saveTimer) { clearTimeout(saveTimer); save(); }
  if (dock) { dock.box.remove(); dock.sw.remove(); dock = null; }
  setProgress(null);
  stepsHost = null;
  ws.el.prepend(ws.cards);
  document.removeEventListener("ef:live-error", onLiveError);
  document.removeEventListener("ef:media-error", onMediaError);
  S.setSaveHook(null);
  releaseMedia();
  if (current.ownFocus) current.root.focus = current.ownFocus; else delete current.root.focus;
  ws.el.remove();
  current = null;
}

export function mountWorkspace(root, host) {
  ensureCss();
  if (current && current.root !== root) teardown();
  const first = !ws;
  if (first) ws = build();
  root.classList.add("efa-root", "efa-host");
  root.dataset.theme = ws.el.dataset.theme = themeOf();
  root.replaceChildren(ws.el);
  const ownFocus = Object.prototype.hasOwnProperty.call(root, "focus") ? root.focus : null;
  root.focus = (opt) => ws.stage.focus(opt);
  current = { root, host, ctx: null, lastWritten: null, ownFocus };

  if (first) {
    mountStage(ws.stage);
    mountTimeline(ws.timeline);
    const el = ws.el;
    el.addEventListener("keydown", onKeyDown);
    el.addEventListener("efa-help", showHelp);
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("mousedown", onMouseDown);
    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("dragenter", onDragEnter);
    el.addEventListener("dragleave", onDragLeave);
    el.addEventListener("dragover", onDragOver);
    el.addEventListener("drop", onDrop);
    for (const [ev, fn] of [["dragenter", onDragEnter], ["dragleave", onDragLeave], ["dragover", onDragOver], ["drop", onDrop]]) ws.cards.addEventListener(ev, fn);
    ws.resize.addEventListener("pointerdown", onResizeDown);
    el.addEventListener("focus", () => ws.stage.focus({ preventScroll: true }));
    S.subscribe((reason) => {
      renderChrome();
      panel?.render();
      if (reason === "undo" || reason === "redo") applyCtx(current?.ctx);
    });
  }
  document.addEventListener("ef:live-error", onLiveError);
  document.addEventListener("ef:media-error", onMediaError);
  S.setSaveHook(scheduleSave);

  readShot();
  current.ctx = host.context?.() || null;
  panel = typeof host.setEffect === "function" ? mountPanel(ws.cards, {
    fx: () => current?.host.effectValues?.() || {},
    setFx: (name, value) => current?.host.setEffect(name, value),
    setFxAll: (values) => current?.host.setEffects?.(values),
    clips: () => [...new Set([...(current?.host.clipChoices?.() || []), ...stills])],
    setClip: (name) => chooseClip(name),
    stillSeconds: (sec) => setStillSeconds(sec),
    clipInfo: (name) => clipInfo.get(name) || null,
    refreshClips: () => loadStills(),
    say: (text) => say(text, { error: true, ms: 6000 }),
    info: (text) => say(text, { ms: 5000 }),
    chooseFile: () => { ws.picker.value = ""; ws.picker.click(); },
    docked: () => (dock ? dock.showing : null),
    show: (what) => showInDock(what),
    relayout: () => current?.host.relayout?.(),
    userData: () => current?.host.userData || null,
    inApp: () => (current?.host.inApp ? !!current.host.inApp() : !!dock),
  }) : null;
  useModelsNode(typeof host.modelValues === "function"
    ? { get: () => current?.host.modelValues?.() || null, set: (v) => current?.host.setModels?.(v) } : null);
  presetsReady ||= loadPresets().then(() => (presetsReady = true), (err) => { presetsReady = null; say(`Presets could not be loaded: ${err.message}`, { error: true }); });
  Promise.resolve(presetsReady).then(() => { if (current?.root === root) { applyCtx(current.ctx); renderCanvas(); if (S.getShot().clip) scheduleSave(); } });
  loadNav();
  loadStills();
  renderChrome();
  renderCanvas();

  const controller = {
    setContext(ctx) { if (current?.root !== root) return; current.ctx = ctx; applyCtx(ctx); panel?.render(); },
    result(info) {
      if (current?.root !== root) return;
      const m = /^element-forge\/([^/]+)$/.exec(info?.run || "");
      const rec = m ? getJSON(`/element-forge/media/output/element-forge/${encodeURIComponent(m[1])}/app_recipe.json`).catch(() => null) : Promise.resolve(null);
      rec.then((r) => {
        if (current?.root !== root) return;
        const e = S.getShot().effects.find((x) => x.id === r?.effect) || S.activeEffect();
        const light = e ? (e.adv?.Light ?? styleDef(e.kind, e.style)?.settings?.Light ?? true) !== false : true;
        let v = null;
        try { v = addRun(info, light, e ? takeRecipe(e.id) : null, e, r); } catch (err) { console.warn("[Element Forge] version of the run:", err); }
        panel?.result(info);
        if (dock) showInDock(v ? "canvas" : "result");
        if (v && e && e.id === S.getShot().active && S.versionsOf(e.id).length === 1) setTimeout(presentResult, 300);
      });
    },
    dock(host) { if (current?.root !== root) return; setDock(host || null); },
    steps(el) {
      if (current?.root !== root) return;
      const next = el || null;
      if (next === stepsHost && (!next || ws.cards.parentElement === next || dock)) return;
      stepsHost = next;
      place();
    },
    show(what) { if (current?.root !== root) return; showInDock(what); },
    progress(info) { if (current?.root !== root) return; setProgress(info); },
    runError(msg) { if (current?.root !== root) return; say(String(msg || "").replace(/^\w*Error: /, "").trim(), { error: true, ms: 60000 }); },
    docked: () => !!dock,
    reloadShot() {
      if (current?.root !== root) return;
      if (host.getShot() === current.lastWritten) return;
      readShot();
      applyCtx(current.ctx);
      renderCanvas();
    },
    shown() {
      if (current?.root !== root) return;
      root.dataset.theme = ws.el.dataset.theme = themeOf();
      if (stepsHost) stepsHost.dataset.theme = ws.el.dataset.theme;
      loadNav(); restoreMedia(); renderCanvas();
    },
    theme() {
      if (current?.root !== root) return;
      const t = themeOf();
      if (ws.el.dataset.theme === t) return;
      for (const el of [root, ws.el, stepsHost, dock?.box, dock?.sw, prog?.el]) if (el) el.dataset.theme = t;
      renderCanvas();
    },
    hidden() { if (current?.root !== root) return; releaseMedia(); renderCanvas(); },
    flush() { if (current?.root !== root) return; flushSave(); },
    queued() { if (current?.root !== root) return; noteQueued(current.host.effectValues?.() || {}, S.activeEffect(), S.getShot()); },
    async beforeRun() {
      if (current?.root !== root) return;
      setProgress({ label: "Queued…", est: runEstimate() });
      if (await shotLineBeforeRun(() => setProgress({ label: "Writing the scene sentence…" }))) { current.ctx = host.context?.() || current.ctx; applyCtx(current.ctx); }
      if (prog?.label) setProgress({ label: "Queued…" });
      flushSave();
    },
    settle() {
      if (current?.root !== root) return;
      setTimeout(() => {
        if (!prog?.label) return;
        fetch("/queue").then((r) => r.json()).then((q) => {
          if (prog?.label && !(q.queue_running || []).length && !(q.queue_pending || []).length) setProgress(null);
        }).catch(() => {});
      }, 2000);
    },
    destroy() {
      if (current?.root !== root) return;
      teardown();
    },
  };
  return controller;
}

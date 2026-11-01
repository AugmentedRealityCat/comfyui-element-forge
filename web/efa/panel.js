import { h, fmtSec, getJSON, postJSON } from "./ui/lib.js";
import { icon } from "./ui/icons.js";
import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { estimate, efaValues, frameBox, ltxFrames, valuesFor, canPreview, outputOf } from "./ui/run.js";
import { loadRtx, hasRtx, ltxForBuild, loadSystem, systemNotes } from "./ui/machine.js";
import * as C from "./ui/comfy.js";
import { editBrush, seekTo, frameHere } from "./ui/stage.js";
import { initLive, poke as pokeLive, refresh as refreshLive, liveMode, setLiveMode, livePreviews } from "./live.js";
import { emitterPanel, basicFill, emitterKind, ownValues, SHAPES, SHAPE, shapeOf, shapeFixed, setAdv, effStyle, guideNow } from "./emitter.js";
import { initShotLine, lineState, describe as describeLine, typedByHand } from "./shotline.js";
import { enhance, enhancer, bonsaiStatus, wordDiff, hasBonsai, bonsaiSetup, startBonsaiSetup, resetBonsai } from "./ui/enhance.js";
import { initWish, suggestButton, wishResults } from "./wish.js";
import { initMyEffects, myTiles, saveRows } from "./myeffects.js";
import { finishRows } from "./finish.js";
import { versionRows } from "./versions.js";
import { exportRows } from "./export.js";
import { initEffects, effectStrip } from "./effects.js";
import { gearRows, loadGear } from "./gear.js";
import * as R from "./ui/run.js";
import * as L from "./ui/look.js";

const VIDEO_RE = /\.(mp4|mov|webm|mkv|m4v|avi)$/i;
const IMAGE_RE = /\.(png|jpe?g|webp)$/i;
const GLYPH = { fire: "🔥", lightning: "⚡", sparks: "✨", smoke: "☁", magic: "✦", weather: "❄", debris: "◆", liquid: "💧", dissolve: "░", own: "✎" };
const PLACE_HINT = {
  point: "Click the clip where it should sit; it hangs on your point. Drag the area in the canvas to size it.",
  window: "Click where it starts. The area in the canvas is where the AI works: drag it to move or size it.",
  ab: "Click point A, Shift-click point B. It runs from A to B.",
  object: "Click the object; it follows it through the clip.",
  frame: "It fills the whole picture: nothing to click.",
  none: "Click the object. Drag the arrow in the canvas to set the direction it crumbles in.",
};
const BLOCKS = [["look", "look_words", "Look", "Colour, size, texture"], ["motion", "motion_words", "Motion", "How it moves"],
  ["contact", "contact_words", "Where it touches", "What happens where it meets something"]];
const EXPERIMENTAL = "This style is experimental: results may vary.";
const STEPS = [["clip", "Clip"], ["position", "Position & Track"], ["effect", "Effect"], ["finish", "Scene & finish"], ["output", "Output"]];
const CANVAS_STEP = { position: "where", effect: "effect", finish: "look" };
const FOLLOWS = [
  ["point", "Point", "Follows the exact spot you clicked, e.g. the tip of a sword. Can slip on fast, blurry motion."],
  ["object", "Object", "Follows the whole object. Steady on fast hands and bodies; sits on the object, not on one spot."],
  ["scene", "Scene", "Stays in place in the world while the camera moves, e.g. fire on the ground."],
  ["screen", "Screen", "Stays at the same place in the picture. Nothing is tracked."],
];
const HOW = {
  overlay: "Made alone on black and laid over the clip: light, glow and place stay adjustable.",
  inpaint: "The AI repaints the area around the effect in every frame. A sentence about what is there keeps it the same scene.",
};

let el = null, api = null, open = null, frame = 0, lastResult = null, showTiles = false, clipView = "list", withScene = false;
let gearOpen = false;
let advance = null;
const typed = new Map();
const checks = new Map();
const groups = new Map();

const COST_WORD = { gen: "AI", calc: "no AI" };
function timeTag(e, kind, s) {
  const est = e && S.getShot().clip ? estimate({ ...e, kind, style: s.id, box: null }, S.getShot()) : null;
  const gen = (e ? P.styleOf({ ...e, kind, style: s.id }) || s : s).cost === "gen";
  const tip = gen ? "Made by the AI on the GPU" : "Made by the particles alone, without an LTX run";
  const k = gen ? "gen" : "calc";
  return h("span", { class: "cost " + k, title: tip },
    `${COST_WORD[k]} · ` + (est ? `${est.lo}–${est.hi} min` : gen ? "minutes" : "about a minute"));
}
const note = (kind, text, ...more) => h("p", { class: "note " + kind }, icon(kind === "err" ? "alert" : kind === "hint" ? "chevron" : "check"), h("span", {}, text, ...more));

function seg(label, options, value, onpick) {
  return h("div", { class: "seg wide", role: "radiogroup", "aria-label": label },
    ...options.map(([v, t, tip]) => h("button", { role: "radio", "aria-checked": String(value === v), "aria-pressed": String(value === v),
      title: tip || null, onclick: () => onpick(v) }, t)));
}
function toggle(label, value, onchange, tip) {
  return h("label", { class: "toggle", title: tip || null }, h("input", { type: "checkbox", checked: !!value, onchange: (ev) => onchange(ev.target.checked) }),
    h("span", { class: "track", "aria-hidden": "true" }), h("span", {}, label));
}
const link = (text, onclick) => h("button", { class: "link", onclick }, text);
function group(key, title, body, { open: dflt = false, hint = "", preview = "", badge = "", cls = "" } = {}) {
  const isOpen = groups.has(key) ? groups.get(key) : dflt;
  const flip = () => { groups.set(key, !isOpen); render(); };
  return h("div", { class: "group" + (isOpen ? " open" : "") + (cls ? ` ${cls}` : ""), "data-group": key },
    h("button", { class: "group-head", "aria-expanded": String(isOpen), onclick: flip }, icon("chevron", "chev"), h("span", {}, title),
      badge ? h("span", { class: "group-badge" }, badge) : null,
      hint ? h("span", { class: "group-hint", title: hint }, hint) : null),
    !isOpen && preview ? h("p", { class: "group-preview", onclick: flip }, preview) : null,
    isOpen ? h("div", { class: "group-body" }, ...[].concat(body()).filter(Boolean)) : null);
}
function fxText(name, placeholder, { area = false, label = "", num = false } = {}) {
  const t = typed.get(name);
  const el = h(area ? "textarea" : "input", { "data-key": name, class: area ? "text area" : "text", placeholder, "aria-label": label || placeholder,
    spellcheck: area ? "true" : "false", oninput: (ev) => {
      const v = ev.target.value, cur = typed.get(name);
      if (cur) clearTimeout(cur.timer);
      typed.set(name, { value: v, timer: setTimeout(() => { typed.delete(name); api.setFx(name, num ? Math.max(0, Math.trunc(+v) || 0) : v); }, 300) });
    } });
  el.value = t ? t.value : String(fx()[name] ?? "");
  if (area) el.rows = 3;
  if (num) { el.inputMode = "numeric"; el.dataset.num = "1"; }
  return el;
}
export function flushTyped() {
  for (const [name, t] of typed) { clearTimeout(t.timer); api?.setFx(name, name === "seed" ? Math.max(0, Math.trunc(+t.value) || 0) : t.value); }
  typed.clear();
}

const fx = () => api?.fx?.() || {};
const effect = () => S.activeEffect();
const style = () => { const e = effect(); return e ? P.styleDef(e.kind, e.style) : null; };
const placed = () => { const e = effect(); return e ? P.styleOf(e) : null; };
const needsPoint = (st) => !!st && st.placement !== "frame";
const lightDefault = (st, key) => st?.settings?.[key] ?? true;
const wordOf = () => String(typed.get("object_word")?.value ?? fx().object_word ?? "").trim();
const styleFollows = (st) => (!st ? "object" : st.settings?.[MASK] ? "object" : st.settings?.[SCENE] ? "scene" : "point");
const ownFollows = () => { const v = fx().sticks_to; return v === "mask" ? "object" : FOLLOWS.some(([k]) => k === v) ? v : null; };
const followsName = (v) => FOLLOWS.find(([k]) => k === v)?.[1] || v;

function stepState(id) {
  const shot = S.getShot(), e = effect(), st = style();
  if (id === "clip") return shot.clip ? "done" : "todo";
  if (!shot.clip) return "locked";
  if (id === "position") return !needsPoint(placed()) || e?.where.a ? "done" : "todo";
  if (id === "effect") return st ? "done" : "todo";
  if (!st) return id === "output" ? "todo" : "locked";
  if (id === "finish") return "todo";
  if (id === "output") return lastResult ? "done" : "todo";
  return "todo";
}
function autoOpen() {
  const first = STEPS.find(([id]) => stepState(id) === "todo");
  return first ? first[0] : "finish";
}

function summary(id) {
  const shot = S.getShot(), e = effect(), st = style();
  if (id === "clip") return shot.clip ? `${shot.clip.name} · ${fmtSec(shot.clip.seconds)}` : "";
  if (!e || !st) return "";
  if (id === "position") {
    if (!needsPoint(placed())) return "Whole picture";
    if (!e.where.a) return "";
    return [(wordOf() ? `“${wordOf()}”` : "Point set") + (e.where.b ? " · A → B" : ""), followsName(ownFollows() || styleFollows(st))].join(" · ");
  }
  if (id === "effect") return `${P.effectDef(e.kind)?.name || e.kind} · ${st.name}`;
  if (id === "finish") return shot.night ? "night" : (S.shownOf(e.id)?.status === "done" ? "live" : "");
  if (id === "output") {
    const o = outputOf(shot);
    return [o.quality === "preview" && canPreview(st, e) ? "Preview" : "Full", fx().sharper_2x && st.cost === "gen" ? "LTX × 2"
      : o.upscale === "nvidia" && st.cost === "gen" && hasRtx() ? "NVIDIA × 2" : null].filter(Boolean).join(" · ");
  }
  return "";
}

function card(id, n, title, body) {
  const state = stepState(id);
  const isOpen = open === id && state !== "locked";
  const num = state === "done" && !isOpen ? icon("check") : String(n);
  return h("section", { class: "card" + (isOpen ? " open" : ""), "data-state": state, "data-step": id },
    h("button", { class: "card-head", "aria-expanded": String(isOpen), disabled: state === "locked",
      title: state === "locked" ? (S.getShot().clip ? "Pick an effect first" : "Choose a video first") : null,
      onclick: () => setOpen(isOpen ? null : id) },
    h("span", { class: "num", "aria-hidden": "true" }, num), h("span", { class: "title" }, title),
    h("span", { class: "sum" }, summary(id))),
    isOpen ? h("div", { class: "card-body" }, ...[].concat(body()).filter(Boolean)) : null);
}

function setOpen(id) {
  open = id;
  if (CANVAS_STEP[id] && S.ui.step !== CANVAS_STEP[id]) S.setUI({ step: CANVAS_STEP[id] });
  render();
}

const thumb = (n) => `/element-forge/api/filmstrip?name=${encodeURIComponent(n)}&count=1&height=72`;
const kept = new Map();
const keptKey = (c) => `${c.name}|${ltxFrames(c.frames)}`;
const keptOf = (c) => (c ? kept.get(keptKey(c)) : null);
async function loadKept(c) {
  const rec = kept.get(keptKey(c)) || {};
  kept.set(keptKey(c), rec);
  try {
    const j = await getJSON(`/element-forge/api/analysis?clip=${encodeURIComponent(c.name)}&frames=${ltxFrames(c.frames)}`);
    rec.analysis = j.analysis;
    rec.tracks = j.tracks || [];
    rec.error = null;
  } catch (err) { rec.error = err.message; }
  rec.loaded = true;
  publishKept(c);
  render();
}
function publishKept(c) {
  const a = keptOf(c)?.analysis;
  const want = a ? { clip: c.name, previews: a.previews } : null;
  if (JSON.stringify(want) !== JSON.stringify(S.ui.analysis || null)) S.setUI({ analysis: want });
}
const fromQueue = (r) => (r.status === "done" ? "done" : r.status === "stopped" ? "stopped" : "failed");
async function runAnalysis(c) {
  const rec = kept.get(keptKey(c)) || {};
  kept.set(keptKey(c), rec);
  rec.run = { status: "running", phase: "Waiting in the queue", error: null, promptId: null };
  render();
  try {
    C.connectSocket();
    const { values, pending } = efaValues(S.getShot());
    if (pending) Object.assign(values, await pending);
    const { prompt } = await postJSON("/element-forge/api/analysis/build", { values, ltx: ltxForBuild() });
    rec.run.promptId = await C.queue(prompt, {
      onStart: () => { rec.run.phase = "Depth, normals and camera"; render(); },
      onProgress: (v, m) => { rec.run.phase = `Depth, normals and camera · ${Math.round((v / m) * 100)} %`; render(); },
      onDone: async (r) => {
        rec.run.status = fromQueue(r);
        rec.run.error = r.error || null;
        await loadKept(c);
        api.refreshClips?.();
        refreshLive();
        const pre = keptOf(c)?.analysis?.previews;
        if (rec.run.status === "done" && pre?.depth && S.getShot().clip?.name === c.name) { S.setUI({ media: { url: pre.depth, label: "Depth", analysis: "depth" } }); api.show?.("canvas"); }
        render();
      },
    });
  } catch (err) {
    rec.run.status = "failed";
    rec.run.error = err.message + (err.detail ? ` (${err.detail})` : "");
    render();
  }
}
const anaMinutes = (c) => { const k = ltxFrames(c.frames) / 81; return `${Math.max(1, Math.round(2.5 * k))}–${Math.max(2, Math.round(4.5 * k))}`; };
function analysisBlock(c) {
  const rec = keptOf(c), a = rec?.analysis, run = rec?.run;
  const kids = [h("div", { class: "label", title: "Depth (Video Depth Anything), normals (MoGe) and the camera's motion of the clip, kept for this clip" }, "Analysis")];
  if (run?.status === "running") kids.push(note("ok", `Analysing the scene… ${run.phase}`));
  else if (a) {
    const show = (part, label) => a.previews?.[part] ? link(`Show ${label.toLowerCase()}`, () => { S.setUI({ media: { url: a.previews[part], label, analysis: part } }); api.show?.("canvas"); }) : null;
    kids.push(note("ok", `Depth, normals and camera are ready (${a.frames} frames). The run takes them from here. `, show("depth", "Depth"), " · ", show("normals", "Normals")));
  } else if (run && run.status !== "done") kids.push(note("err", run.error || "The analysis was stopped."));
  else kids.push(h("p", { class: "muted small" }, rec?.loaded ? "Not analysed yet. Without it the run works out depth and normals itself; analysed first, the canvas shows them and later runs of this clip take them."
    : "Looking for a kept analysis…"));
  if (run?.status !== "running") kids.push(h("button", { class: "btn small", onclick: () => runAnalysis(c), title: "Only the analysis of the clip, without the AI effect" },
    a ? "Analyse the scene again" : `Analyse the scene (depth, normals, camera) · about ${anaMinutes(c)} min`));
  return h("div", { class: "field analysis" }, ...kids);
}
const midTrim = (n, max = 24) => (n.length <= max ? n : `${n.slice(0, Math.ceil((max - 1) * 0.55))}…${n.slice(n.length - Math.floor((max - 1) * 0.45))}`);
function clipBadges(n) {
  const i = api.clipInfo?.(n);
  return [IMAGE_RE.test(n) ? h("span", { class: "badge still" }, "still") : null,
    i?.analysis ? h("span", { class: "badge scene", title: "Analysed: depth, normals, camera" }, "◆ analysed") : null,
    i?.tracks ? h("span", { class: "badge", title: "Kept tracks of this clip" }, `${i.tracks} track${i.tracks > 1 ? "s" : ""}`) : null];
}
function clipBody() {
  const shot = S.getShot();
  const kids = [];
  if (shot.clip) {
    const c = shot.clip;
    kids.push(h("div", { class: "clip-info" }, h("b", {}, c.name),
      h("span", { class: "muted" }, c.still ? `Still picture · ${c.width}×${c.height}` : `${fmtSec(c.seconds)} · ${c.fps} fps · ${c.width}×${c.height}`)));
    if (c.still) {
      const len = h("input", { class: "text", type: "number", min: "0.5", max: "60", step: "0.5", value: String(c.seconds), "aria-label": "Length in seconds",
        onchange: (ev) => api.stillSeconds?.(ev.target.value) });
      kids.push(h("div", { class: "field" }, h("div", { class: "label", title: "The picture is held this long; the effect moves over it" }, "Length (s)"),
        h("div", { class: "row gap" }, len, h("span", { class: "muted small" }, `${c.frames} frames at ${c.fps} fps`))));
    }
    if (Math.min(c.width || 0, c.height || 0) > 1080 && !c.fullSize) {
      const fit = async () => {
        api.say?.("Making a 1080p copy…");
        try {
          const r = await postJSON("/element-forge/api/clip/fit", { clip: c.name });
          if (r.error) throw new Error(r.error);
          await api.refreshClips?.();
          api.setClip(r.name);
        } catch (err) { api.say?.(`The copy could not be made: ${err.message || err}`); }
      };
      kids.push(note("hint", `This ${c.still ? "picture" : "clip"} is ${c.width}×${c.height}. Depth, light and normals are worked out at this size: ` +
        "about 28 GB of memory at 1080p, roughly four times that at 4K. ",
        link("Use a 1080p copy", fit), " · ", link("Keep the full size", () => S.change((sh) => { if (sh.clip) sh.clip.fullSize = true; }, "clip"))));
    }
    if (c.frames > 161) kids.push(note("hint", `Only the first ${fmtSec(161 / c.fps)} of the clip are used.`));
    if (c.seconds < 2) kids.push(note("hint", "The clip is shorter than our test clips (2 s and more): results may vary."));
  }
  kids.push(group("clips", "Videos and pictures", () => pickerBody(shot), { open: !shot.clip, preview: shot.clip ? `${shot.clip.name} · change` : "" }));
  if (shot.clip) kids.push(analysisBlock(shot.clip));
  return kids;
}
function pickerBody(shot) {
  const kids = [];
  const all = (api.clips() || []).filter((n) => VIDEO_RE.test(n) || IMAGE_RE.test(n));
  const anyScene = all.some((n) => api.clipInfo?.(n)?.analysis);
  const names = withScene && anyScene ? all.filter((n) => api.clipInfo?.(n)?.analysis) : all;
  if (all.length) {
    const pick = (n) => { if (shot.clip?.name !== n) { advance = "clip"; groups.delete("clips"); } api.setClip(n); };
    kids.push(h("div", { class: "row between" }, h("span", { class: "label" }, "In ComfyUI's input folder"),
      h("div", { class: "row gap" }, anyScene ? h("button", { class: "chip" + (withScene ? " on" : ""), "aria-pressed": String(withScene),
        title: "Only clips that are analysed (depth, normals, camera)", onclick: () => { withScene = !withScene; render(); } }, "analysed") : null,
      h("div", { class: "seg clip-view", role: "radiogroup", "aria-label": "Show the clips as" },
        ...[["list", "List"], ["tiles", "Tiles"]].map(([v, t]) => h("button", { role: "radio", "aria-checked": String(clipView === v),
          "aria-pressed": String(clipView === v), onclick: () => { clipView = v; render(); } }, t))))));
    kids.push(clipView === "tiles"
      ? h("div", { class: "clip-tiles", role: "listbox", "aria-label": "Videos and pictures in ComfyUI's input folder" }, ...names.map((n) =>
        h("button", { class: "clip-tile" + (shot.clip?.name === n ? " on" : ""), role: "option", "aria-selected": String(shot.clip?.name === n),
          title: n, onclick: () => pick(n) }, h("img", { src: thumb(n), alt: "", loading: "lazy", decoding: "async" }),
          h("span", { class: "clip-name" }, midTrim(n)),
          h("span", { class: "clip-meta" }, api.clipInfo?.(n)?.seconds ? h("span", { class: "muted" }, fmtSec(api.clipInfo(n).seconds)) : null, ...clipBadges(n)))))
      : h("div", { class: "clip-list", role: "listbox", "aria-label": "Videos and pictures in ComfyUI's input folder" }, ...names.map((n) =>
        h("button", { class: "clip-item" + (shot.clip?.name === n ? " on" : ""), role: "option", "aria-selected": String(shot.clip?.name === n),
          onclick: () => pick(n) }, h("span", {}, n), ...clipBadges(n)))));
  }
  kids.push(h("button", { class: "drop-zone", onclick: () => api.chooseFile() }, icon("upload"),
    h("span", {}, "Choose a video or a picture from your computer, or drop it here or onto the canvas")));
  return kids;
}

const MASK = "Track follows the object mask (hands, bodies)", SCENE = "Sticks to scene (off = object)", OWN = "Own object mask (off = click)",
  ALIKE = "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)", STILL = "Fixed on screen (Follows: Screen)";
const whereKey = (e) => JSON.stringify([S.getShot().clip?.name, e.where, e.adv?.[SCENE], e.adv?.[MASK], e.adv?.[STILL], e.adv?.[OWN] ? e.paint?.mask : null, P.objectWord(e),
  ...(R.maskSet(e) ? [e.adv?.[R.LEAVE_PTS] || "", e.adv?.[R.LEAVE_WORDS] || "", R.maskFrame(e), e.adv?.[R.ADD_PTS] || "", e.adv?.[R.ADD_WORDS] || ""] : [])]);
const TRACK_KEYS = ["Clip", "Still image (a picture in the input folder instead of the clip)", "Still image length (s)", "Frames", "Point A x", "Point A y", "Point B x", "Point B y", "Object word (optional, helps the click)", ALIKE, OWN,
  "Own object mask: first frame, paint the object (mask editor)", SCENE, MASK, STILL, "Follows motion", "Inpaint (off = on black)", "On black: more room",
  "Window A-B automatic", "Window width (plate px)", "Window height (plate px)", "Emitter x in window", "Emitter y in window", "Generate width", "Generate height",
  R.LEAVE_PTS, R.LEAVE_WORDS, R.MASK_FRAME, R.ADD_PTS, R.ADD_WORDS, R.MASK_STEADY];
const CHECK_PHASE = { SAM3_Detect: "Finding the object", EFSaveTrack: "Keeping the track", EFFollowCrop: "Drawing the mask",
  EFMaskTrack: "Drawing the mask", EFTrackPreview: "Drawing the mask", CreateVideo: "Saving the video", SaveVideo: "Saving the video" };
function checkPhase(e, ck, phase) {
  if (phase) ck.phase = phase;
  const busy = ck.status === "running" && !ck.shown;
  if (busy) S.setUI({ waitNote: { effect: e.id, text: `Track check · ${ck.phase}` } });
  else if (S.ui.waitNote?.effect === e.id) S.setUI({ waitNote: null });
  render();
}
function showCheck(e, ck) {
  if (ck.shown || !ck.url) return;
  ck.shown = true;
  if (S.activeEffect()?.id === e.id) { S.setUI({ media: { url: ck.url, label: "Track check", clip: S.getShot().clip?.name, check: true } }); api.show?.("canvas"); }
  checkPhase(e, ck);
}
async function runCheck(e) {
  if (e.adv?.[OWN] && !e.paint?.mask?.length) return;
  const st = P.styleDef(e.kind, e.style);
  const ck = { key: whereKey(e), status: "running", phase: "Waiting in the queue", url: null, error: null, shown: false };
  checks.set(e.id, ck);
  checkPhase(e, ck);
  try {
    C.connectSocket();
    const run = `app-check-${new Date().toISOString().replace(/[-:T]/g, "").slice(4, 12)}-${Math.random().toString(36).slice(2, 6)}`;
    const { values: all, pending } = efaValues(S.getShot());
    if (pending) Object.assign(all, await pending);
    const values = { "Check track only": true };
    for (const k of TRACK_KEYS) if (k in all) values[k] = all[k];
    const { prompt, show } = await C.build("check", values, run, null);
    await C.queue(prompt, {
      onStart: () => checkPhase(e, ck, "Following the object"),
      onNode: (node) => { const p = CHECK_PHASE[prompt[node]?.class_type]; if (p && p !== ck.phase) checkPhase(e, ck, p); },
      onProgress: (v, m, node) => { if (prompt[node]?.class_type !== "SAM3_Detect") checkPhase(e, ck, `Following the object · ${Math.round((v / m) * 100)} %`); },
      onOutput: (node, out) => {
        if (show && String(node) !== String(show)) return;
        const f = [...(out?.images || []), ...(out?.gifs || []), ...(out?.videos || [])][0];
        if (f && !ck.url) ck.url = `/view?filename=${encodeURIComponent(f.filename)}&subfolder=${encodeURIComponent(f.subfolder || "")}&type=${encodeURIComponent(f.type || "output")}`;
        showCheck(e, ck);
      },
      onDone: (r) => {
        ck.status = r.status === "done" && ck.url ? "done" : r.status === "stopped" ? "stopped" : "failed";
        ck.error = r.status === "done" && !ck.url ? "The check finished without a video." : r.error || null;
        if (ck.status === "done") {
          trackKeys.delete(whereKey(e));
          const c = S.getShot().clip;
          if (c) loadKept(c).then(() => api.refreshClips?.());
          if (e.adv?.[OWN] && e.paint?.mask?.length && !e.paint.maskHidden && S.activeEffect()?.id === e.id) editBrush(false);
        }
        if (ck.status === "done") showCheck(e, ck);
        if (ck.status === "done") refreshLive();
        checkPhase(e, ck);
      },
    });
  } catch (err) {
    ck.status = "failed";
    ck.error = err.message + (err.detail ? ` (${err.detail})` : "");
    checkPhase(e, ck);
  }
}
const trackKeys = new Map();
async function loadTrackKey(e) {
  const wk = whereKey(e);
  if (trackKeys.has(wk)) return;
  trackKeys.set(wk, "loading");
  try {
    const { values, pending } = efaValues(S.getShot());
    if (pending) Object.assign(values, await pending);
    const v = {};
    for (const k of TRACK_KEYS) if (k in values) v[k] = values[k];
    trackKeys.set(wk, await postJSON("/element-forge/api/tracks/key", { values: v }));
  } catch { trackKeys.delete(wk); }
  render();
}
async function clearTrack(c, key) {
  try {
    await postJSON("/element-forge/api/tracks/clear", { clip: c.name, key });
    for (const [wk, v] of trackKeys) if (v?.key === key) trackKeys.delete(wk);
    for (const [id, ck] of checks) if (ck.status === "done") checks.delete(id);
  } catch (err) { api.say?.(`The track could not be cleared: ${err.message}`); }
  await loadKept(c);
  api.refreshClips?.();
}
function checkBlock(e) {
  const ck = checks.get(e.id);
  const fresh = ck && ck.key === whereKey(e);
  const c = S.getShot().clip;
  const tk = trackKeys.get(whereKey(e));
  if (!tk) loadTrackKey(e);
  const keptHere = tk && tk !== "loading" && tk.kept;
  const kids = [];
  if (fresh && ck.status === "running") kids.push(note("ok", `Tracking… ${ck.phase}`));
  else if (fresh && ck.status === "done") kids.push(note("ok", "Tracked: the canvas shows the mask and the points through the clip. The track is kept, the run takes it."),
    h("button", { class: "btn ghost small", onclick: () => S.setUI({ media: { url: ck.url, label: "Track check", clip: c?.name, check: true } }) }, "Show the track again"));
  else if (fresh && ck.status !== "done") kids.push(note("err", ck.error || "The track was stopped."));
  else if (keptHere) kids.push(note("ok", "This place has a kept track: the run takes it and does not track again."));
  if (!fresh || ck.status !== "running") {
    const ownMissing = e.adv?.[OWN] && !e.paint?.mask?.length;
    kids.push(h("div", { class: "row gap" }, h("button", { class: "btn small", disabled: !e.where.a || ownMissing ? "" : null,
      title: ownMissing ? "Paint over the object first" : "Only the track and the mask, without the AI: about a minute",
      onclick: () => runCheck(e) }, (fresh && ck.status === "done") || keptHere ? "Track it again" : "Track it"),
    keptHere ? h("button", { class: "btn ghost small", title: "The kept track of this place goes; the run tracks again",
      onclick: () => clearTrack(c, tk.key) }, "Clear track") : null));
  }
  return kids;
}
function savedTracks(e) {
  const c = S.getShot().clip, list = keptOf(c)?.tracks || [];
  if (!list.length) return null;
  const cur = trackKeys.get(whereKey(e));
  return group("tracks", `Saved tracks (${list.length})`, () => list.map((tr) => {
    const w = tr.where || {};
    const label = [`A ${w.a?.join(", ")}`, w.b?.length ? `B ${w.b.join(", ")}` : null, w.word ? `“${w.word}”` : null,
      w.alike ? "all alike" : null, w.own ? "painted" : null, w.frame ? `mask on frame ${w.frame}` : null,
      w.add || w.add_words ? `adding ${[w.add ? `${w.add.split(";").length} ${w.add.includes(";") ? "parts" : "part"}` : null,
        w.add_words ? `“${w.add_words}”` : null].filter(Boolean).join(", ")}` : null, w.leave || w.leave_words ? `leaving out ${[w.leave ? `${w.leave.split(";").length} ${w.leave.includes(";") ? "parts" : "part"}` : null,
        w.leave_words ? `“${w.leave_words}”` : null].filter(Boolean).join(", ")}` : null].filter(Boolean).join(" · ");
    const here = cur && cur !== "loading" && cur.key === tr.key;
    return h("div", { class: "row between saved-track" + (here ? " on" : "") }, h("span", { class: "small" }, label, here ? h("span", { class: "badge" }, "this place") : null),
      h("div", { class: "row gap" }, here ? null : h("button", { class: "btn ghost small", title: w.own ? "Puts back the points and the word; the painted mask stays as you have it now" : "Puts back the points and the word",
        onclick: () => useTrack(w) }, "Use"),
      h("button", { class: "icon-btn", title: "Clear this kept track", "aria-label": "Clear this kept track", onclick: () => clearTrack(c, tr.key) }, icon("close"))));
  }), { hint: cur && cur !== "loading" && cur.kept ? "this place is kept" : "" });
}
function useTrack(w) {
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (!x) return;
    x.where = { ...x.where, a: w.a?.length ? { x: w.a[0], y: w.a[1] } : x.where.a, b: w.b?.length ? { x: w.b[0], y: w.b[1] } : null };
  }, "point");
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (!x) return;
    x.adv = { ...x.adv };
    for (const [k, v] of [[R.LEAVE_PTS, w.leave], [R.LEAVE_WORDS, w.leave_words], [R.MASK_FRAME, w.frame], [R.ADD_PTS, w.add],
      [R.ADD_WORDS, w.add_words]]) if (v) x.adv[k] = v; else delete x.adv[k];
  }, "leave");
  typed.delete("object_word");
  api.setFx("object_word", w.word || "");
  api.setFx("all_alike", !!w.alike);
  if (!w.own) api.setFx("own_mask", false);
}
let firstMask = { key: null, status: null, promptId: null, ms: null, error: null };
let firstTimer = 0;
function scheduleFirstMask(e) {
  const c = S.getShot().clip, key = whereKey(e);
  if (e.adv?.[OWN] && (S.ui.firstMask || firstMask.key)) { firstMask = { ...firstMask, key: null }; if (S.ui.firstMask) S.setUI({ firstMask: null }); }
  if (!c || !e.where.a || e.adv?.[OWN] || key === firstMask.key) return;
  firstMask = { key, status: "waiting", promptId: firstMask.status === "running" ? firstMask.promptId : null, ms: null, error: null };
  clearTimeout(firstTimer);
  firstTimer = setTimeout(() => runFirstMask(key), 500);
}
async function runFirstMask(key) {
  const e = S.activeEffect(), c = S.getShot().clip;
  if (!e || !c || whereKey(e) !== key) return;
  if (firstMask.promptId) C.cancel(firstMask.promptId).catch(() => {});
  const fm = firstMask = { key, status: "running", promptId: null, ms: null, error: null, t0: performance.now(), urls: {}, frame: R.maskFrame(e) };
  render();
  try {
    C.connectSocket();
    const { values, pending } = efaValues(S.getShot());
    if (pending) Object.assign(values, await pending);
    const v = {};
    for (const k of TRACK_KEYS) if (k in values) v[k] = values[k];
    const { prompt } = await postJSON("/element-forge/api/first-mask/build", { values: v });
    fm.promptId = await C.queue(prompt, {
      onOutput: (node, out) => {
        const f = out?.images?.find((x) => x.type === "temp");
        const tag = { first_a: "a", first_b: "b", first_left: "left" }[String(node)];
        if (f && tag) fm.urls[tag] = `/view?filename=${encodeURIComponent(f.filename)}&subfolder=${encodeURIComponent(f.subfolder || "")}&type=${encodeURIComponent(f.type || "temp")}`;
      },
      onDone: (r) => {
        if (firstMask !== fm) return;
        fm.status = r.status === "done" && fm.urls.a ? "done" : fromQueue(r);
        fm.error = r.error || (r.status === "done" && !fm.urls.a ? "No mask came back." : null);
        fm.ms = Math.round(performance.now() - fm.t0);
        if (fm.status === "done") S.setUI({ firstMask: { clip: c.name, key, a: fm.urls.a, b: fm.urls.b || null, left: fm.urls.left || null, frame: fm.frame } });
        render();
      },
    });
  } catch (err) {
    fm.status = "failed";
    fm.error = err.message + (err.detail ? ` (${err.detail})` : "");
    render();
  }
}
function firstMaskNote(e) {
  if (!e.where.a || e.adv?.[OWN] || firstMask.key !== whereKey(e)) return null;
  const on = firstMask.frame ? `the mask frame (${firstMask.frame})` : "the first frame";
  if (firstMask.status === "waiting" || firstMask.status === "running") return h("p", { class: "muted small" }, `Finding the object on ${on}…`);
  if (firstMask.status === "done") return h("p", { class: "muted small" }, `Blue on ${on}: what will be tracked (${(firstMask.ms / 1000).toFixed(1)} s)${
    firstMask.urls?.left ? ", red: the parts left out" : ""}. Not right? Add or leave out parts under Object.`);
  if (firstMask.status === "failed") return note("err", `The first frame's mask failed: ${firstMask.error || "unknown error"}`);
  return null;
}
function boxWarnings(e, st, shot) {
  const out = [];
  if (!(st.placement === "window" || st.placement === "point" || (st.placement === "ab" && e.box))) return out;
  const c = shot.clip, adv = fx().mode === "advanced", area = "area";
  const b = frameBox(e, c);
  const v = valuesFor(e, shot);
  const gw = v["Generate width"], gh = v["Generate height"];
  if (!b || !gw || !gh) return out;
  const k = Math.max(b.w / gw, b.h / gh);
  if (k > 2.2) out.push(`The ${area} is much bigger than what the AI makes${adv ? ` (${gw} × ${gh})` : ""}: the effect will look soft. Make it smaller${st.cost === "gen" ? " or set Upscale to LTX × 2 in Output" : ""}.`);
  if (k < 0.15) out.push(`The ${area} is very small: fine detail will be lost.`);
  const outX = Math.max(0, -b.x) + Math.max(0, b.x + b.w - c.width), outY = Math.max(0, -b.y) + Math.max(0, b.y + b.h - c.height);
  if (outX > b.w * 0.25 || outY > b.h * 0.25) out.push(`A good part of the ${area} lies outside the picture: that part will not be seen.`);
  return out;
}
function followsBlock(st) {
  const own = ownFollows(), cur = own || styleFollows(st);
  const expl = FOLLOWS.find(([k]) => k === cur)?.[2] || "";
  return h("div", { class: "field" }, h("div", { class: "label" }, "Follows"),
    seg("Follows", FOLLOWS.map(([v, t, tip]) => [v, t, tip]), cur, (v) => api.setFx("sticks_to", v)),
    h("p", { class: "muted small follows-expl" }, expl, own ? null : h("span", { class: "muted" }, " · as tested for this style")),
    own && own !== styleFollows(st) ? h("p", { class: "muted small" }, link(`Back to the style default (${followsName(styleFollows(st))})`, () => api.setFx("sticks_to", "style default"))) : null);
}
function lockBaseRow(st) {
  if (fx().mode !== "advanced" || st.cost !== "gen" || st.placement !== "point") return null;
  return h("div", { class: "field" },
    toggle("Base stays on the point", fx().lock_base, (v) => api.setFx("lock_base", v),
      "The AI draws the effect a little differently in every frame, so its base can jitter. On: the base stays fixed on the tracked point, the effect still moves above it"),
    h("p", { class: "muted small" }, "For a flame or ball that jitters at its base. Off: only slow drift is smoothed."));
}
const STEADY = [[0, "Off", "The mask as the track made it"], [2, "Light", "Two frames on each side; keeps fast, small parts"],
  [4, "Strong", "Four frames on each side; smoothest on large, soft objects"]];
const STEADY_DEFAULT = 2;
function maskFields(e) {
  const c = S.getShot().clip, fps = c?.fps || 25, mf = R.maskFrame(e), tool = S.ui.maskTool || null;
  const edit = (fn) => S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (x) { x.adv = { ...x.adv }; fn(x.adv); }
  }, "mask");
  const useHere = () => {
    const f = frameHere();
    edit((a) => {
      if (f !== R.maskFrame(e)) { delete a[R.ADD_PTS]; delete a[R.LEAVE_PTS]; }
      if (f) a[R.MASK_FRAME] = f; else delete a[R.MASK_FRAME];
    });
  };
  const words = (k, ph, label) => {
    const el = h("input", { class: "text", type: "text", placeholder: ph, "aria-label": label, spellcheck: "false",
      onchange: (ev) => { const v = ev.target.value.trim(); edit((a) => { if (v) a[k] = v; else delete a[k]; }); } });
    el.value = e.adv?.[k] || "";
    return el;
  };
  const clicks = (kind, k, label, key) => {
    const on = tool === kind, n = R.ptsOf(e, k).length;
    return h("div", { class: "row gap" },
      h("button", { class: "btn small" + (on ? " on" : ""), "aria-pressed": String(on), disabled: e.where.a ? null : "",
        title: e.where.a ? `Then click each part in the canvas (${key}-click works at any time)` : "Click the object first",
        onclick: () => S.setUI({ maskTool: on ? null : kind, tool: "point" }) }, on ? "Done" : label),
      n ? link(n === 1 ? "Clear the part" : `Clear all ${n} parts`, () => edit((a) => { delete a[k]; })) : null);
  };
  return [
    h("div", { class: "field mask" },
      h("div", { class: "label", title: "The frame the mask is set on; the track runs from it to the start and to the end of the clip" }, "Mask frame"),
      h("p", { class: "small" }, mf ? `${fmtSec(mf / fps)} · frame ${mf}` : "The first frame"),
      h("div", { class: "row gap" },
        h("button", { class: "btn small", title: "The frame at the playhead becomes the mask frame (points set on another frame are cleared)",
          onclick: useHere }, "Use this frame"),
        mf ? h("button", { class: "btn ghost small", title: "The playhead goes to the mask frame", onclick: () => seekTo(mf / fps) }, "Go there") : null),
      h("p", { class: "muted small" }, "Where all of the object is in view (a drawn blade): move the playhead there and press Use this frame. Parts below are clicked on this frame.")),
    h("div", { class: "field mask" },
      h("div", { class: "label", title: "More of the object: tracked with it" }, "Add (optional)"),
      words(R.ADD_WORDS, "e.g. blade; tip", "Add: words"),
      clicks("add", R.ADD_PTS, "Click to add", "Ctrl"),
      h("p", { class: "muted small" }, "Words, or a click on each part (green ring).")),
    h("div", { class: "field mask" },
      h("div", { class: "label", title: "These parts are tracked and taken out of the object's mask: they give off nothing. The depth and the rest of the clip stay as they are" }, "Leave out (optional)"),
      words(R.LEAVE_WORDS, "e.g. hand; handle", "Leave out: words"),
      clicks("leave", R.LEAVE_PTS, "Click to leave out", "Alt"),
      h("p", { class: "muted small" }, "Words, or a click on each part (red ring). The mask frame shows them in red.")),
    fixesField(e, fps),
    h("div", { class: "field mask" },
      h("div", { class: "label", title: "Averages each frame's mask with its neighbours, aligned to the motion" }, "Steady mask"),
      seg("Steady mask", STEADY, +(e.adv?.[R.MASK_STEADY] ?? STEADY_DEFAULT), (v) => edit((a) => { if (v === STEADY_DEFAULT) delete a[R.MASK_STEADY]; else a[R.MASK_STEADY] = v; })),
      h("p", { class: "muted small" }, "Less flicker where the object blurs or the light is poor. Strong can round off fast, thin parts.")),
  ];
}
function fixesField(e, fps) {
  const list = R.fixesOf(e);
  const drop = (frame) => S.change((s) => {
    const x = s.effects.find((y) => y.id === e.id);
    if (!x) return;
    x.adv = { ...x.adv };
    const t = R.fixesText(R.fixesOf(x).filter((f) => f.frame !== frame));
    if (t) x.adv[R.MASK_FIXES] = t; else delete x.adv[R.MASK_FIXES];
  }, "mask-fix");
  return h("div", { class: "field mask" },
    h("div", { class: "label", title: "Where the track goes wrong: the mask is mended on that frame and tracked from it up to the fixes next to it" }, "Fixes on other frames"),
    ...list.map((f) => h("div", { class: "row gap fix-row" },
      h("span", { class: "small" }, `${fmtSec(f.frame / fps)} · frame ${f.frame}`),
      h("span", { class: "muted small" }, [f.add.length ? `+${f.add.length}` : null, f.leave.length ? `−${f.leave.length}` : null].filter(Boolean).join(" ")),
      h("span", { class: "spacer" }),
      h("button", { class: "btn ghost small", title: "The playhead goes to this frame", onclick: () => seekTo(f.frame / fps) }, "Go there"),
      h("button", { class: "btn ghost small", title: "Remove this fix", "aria-label": `Remove the fix on frame ${f.frame}`, onclick: () => drop(f.frame) }, "×"))),
    h("p", { class: "muted small" }, list.length ? "Each fix is tracked from its frame up to the fixes next to it. Track again to see them."
      : "Where the track loses a part or takes too much: move the playhead there, Ctrl-click what is missing, Alt-click what is too much."));
}
function objectGroup() {
  const f = fx(), word = wordOf(), e = effect(), left = e && R.leaveSet(e), masked = e && R.maskSet(e);
  const set = word || f.own_mask || f.all_alike || masked;
  return group("object", "Object", () => [
    h("p", { class: "muted small" }, "What is tracked: the mask the AI builds from your click. Only needed when it does not fit."),
    h("div", { class: "field" }, h("div", { class: "label", title: "A word for the click. Clicking a crown, the AI often takes the whole head without it" }, "What is it? (optional)"),
      fxText("object_word", "e.g. crown"),
      h("p", { class: "muted small" }, "The effect description uses the word too.")),
    toggle("All alike (e.g. all candles, all points of a crown)", f.all_alike, (v) => api.setFx("all_alike", v), "With the word: every object of this kind instead of the clicked one"),
    f.all_alike && !word ? note("hint", "All alike needs the word above.") : null,
    toggle("Paint it yourself (brush in the canvas)", f.own_mask, (v) => api.setFx("own_mask", v), "When the click misses parts (a raised arm, a crown): paint the object in the first frame, the track follows your mask"),
    f.own_mask ? h("p", { class: "muted small" }, effect()?.paint?.maskHidden
      ? ["Your mask is put away after the track; it still counts. ", link("Edit brush", () => editBrush(true))]
      : "Paint over the object in the first frame of the canvas; the track follows your mask.") : null,
    ...(e ? maskFields(e) : []),
    toggle("In front of the effect (its mask hides it)", f.object_in_front, (v) => api.setFx("object_in_front", v), "The object's mask cuts the effect out wherever the object is, whatever the depth says: a person in front of a portal"),
    f.object_in_front && left ? toggle("The parts left out are in front too", e.adv?.[R.FRONT_ALL] ?? true, (v) => setAdv(R.FRONT_ALL, v ? undefined : false),
      "On: the whole object hides the effect (the hand on the handle too). Off: only what is left") : null,
  ], { open: !!(set || f.object_in_front), hint: word ? `“${word}”` : f.own_mask ? "painted" : masked ? "mask set" : f.object_in_front ? "in front" : "optional" });
}
function positionBody() {
  const e = effect(), st = placed(), shot = S.getShot();
  if (!e || !st) return [h("p", { class: "muted" }, "Loading the effects…")];
  const kids = [h("p", { class: "muted small" }, PLACE_HINT[st.placement] || PLACE_HINT.point)];
  if (!needsPoint(st)) return kids;
  kids.push(e.where.a ? note("ok", `Your point is set${e.where.b ? " (A and B)" : ""}. Click again to move it.`) : note("hint", "No point yet: click the clip in the canvas."));
  if (shot.clip) for (const w of boxWarnings(e, st, shot)) kids.push(note("hint", w));
  if (shot.clip && open === "position") scheduleFirstMask(e);
  kids.push(firstMaskNote(e));
  kids.push(shapeBlock(e, st));
  kids.push(followsBlock(st));
  kids.push(lockBaseRow(st));
  kids.push(objectGroup());
  if (e.where.a && shot.clip) kids.push(...checkBlock(e));
  if (shot.clip) kids.push(savedTracks(e));
  return kids.filter(Boolean);
}

function hasMask(e) {
  const tk = trackKeys.get(whereKey(e)), ck = checks.get(e.id);
  return !!((tk && tk !== "loading" && tk.kept) || (ck && ck.key === whereKey(e) && ck.status === "done"));
}
function shapeNeeds(e, v) {
  const go = (id, tool) => () => { setOpen(id); if (tool) S.setUI({ tool }); };
  if (v === "point A") return e.where.a ? null : ["Click the clip in the canvas."];
  if (v === "line A-B") return e.where.b ? null : ["Shift-click point B in the canvas."];
  if (v === "drawing") return e.paint?.guide?.length ? null : ["Paint the path on the first frame: ", link("Brush", () => S.setUI({ tool: "brush" }))];
  if (v === "area") return e.box ? null : ["Drag the area in the canvas: ", link("Area", go("effect", "frame"))];
  if (v === "groups") return e.groups?.length ? null : ["List the places below."];
  if (v.startsWith("object")) return hasMask(e) ? null : ["Needs the object's mask: Track it (below)."];
  return null;
}
function shapeBlock(e, st) {
  if (emitterKind(st) !== "particles" || shapeFixed(st)) return null;
  const cur = shapeOf(e, st), dflt = st.settings?.[SHAPE] || "point A";
  const pick = (v) => setAdv(SHAPE, v === dflt ? undefined : v);
  const needs = shapeNeeds(e, cur);
  return h("div", { class: "field shape" }, h("div", { class: "label" }, "Shape", h("span", { class: "muted small" }, " · where the particles come from")),
    h("select", { class: "text", "aria-label": "Shape", onchange: (ev) => pick(ev.target.value) },
      ...SHAPES.map(([v, t, need]) => h("option", { value: v, selected: v === cur }, `${t}${v === dflt ? " (style default)" : ""} · needs ${need}`))),
    needs ? note("hint", ...needs) : null,
    cur === "groups" ? groupsField(e) : null,
    cur !== dflt ? h("p", { class: "muted small" }, link(`Back to the style default (${SHAPES.find(([k]) => k === dflt)?.[1] || dflt})`, () => pick(dflt))) : null);
}
function groupsField(e) {
  const ta = h("textarea", { class: "text area", rows: 3, placeholder: "0.3, 0.6, 0.2\n0.7, 0.5, 0.8", "aria-label": "Groups in depth",
    onchange: (ev) => {
      const rows = ev.target.value.split("\n").map((l) => l.split(/[,;\s]+/).filter(Boolean).map(Number)).filter((r) => r.length >= 3 && r.every(Number.isFinite));
      S.change((sh) => { const x = sh.effects.find((y) => y.id === sh.active); if (x) x.groups = rows.map((r) => r.slice(0, 4)); }, "emitter");
    } });
  ta.value = (e.groups || []).map((g) => g.join(", ")).join("\n");
  return h("div", {}, ta, h("p", { class: "muted small" }, "One place per line: x, y (share of the picture), depth (0 far, 1 near), size."));
}

function chooseStyle(kind, sid) {
  S.change((sh) => {
    const e = sh.effects.find((x) => x.id === sh.active);
    if (e?.adv && ("Light" in e.adv || "Glow" in e.adv)) { e.adv = { ...e.adv }; delete e.adv.Light; delete e.adv.Glow; }
    if (e?.fresh) { delete e.fresh; e.kind = kind; e.style = sid; e.dir = P.styleDef(kind, sid)?.dir === "dissolve" ? 90 : null; }
  }, "style");
  showTiles = false;
  if (fx().emitter_values) api.setFx("emitter_values", "");
  for (const k of ["guide", "guide_particles", "made_by"]) if (fx()[k] && fx()[k] !== "style default") api.setFx(k, "style default");
  if (fx().draw_path) api.setFx("draw_path", false);
  api.setFx("effect_style", `${kind}/${sid}`);
}
function positionHints(e, st) {
  if (!needsPoint(st)) return [];
  const go = () => setOpen("position");
  const out = [];
  if (!e.where.a) out.push(note("hint", "No position yet: the preview starts at the centre. ", link("Set the position", go)));
  else if (st.placement === "ab" && !e.where.b) out.push(note("hint", "Next: Shift-click point B in the picture. ", link("Go to Position", go)));
  const own = ownFollows();
  if (own && own !== styleFollows(st)) out.push(note("ok", `This style usually follows: ${followsName(styleFollows(st))}. You chose ${followsName(own)}. `,
    link(`Use ${followsName(styleFollows(st))}`, () => api.setFx("sticks_to", "style default"))));
  return out;
}
function promptGroup(e, st, p, adv) {
  const final = P.composePrompt(e) || "";
  const words = P.wordCount(final);
  const long = words > 200;
  return group("prompt", "Description", () => {
    const kids = [];
    for (const [k, w, label, tip] of BLOCKS) {
      const chips = p.chips?.[k] || [];
      if (!chips.length && !p[k] && p.what) continue;
      const cur = typed.get(w)?.value ?? String(fx()[w] ?? "");
      const word = P.objectWord(e);
      kids.push(h("div", { class: "field" }, h("div", { class: "label", title: tip }, label),
        chips.length ? h("div", { class: "chips" }, ...chips.map((c) => {
          const on = cur === c || (!cur && p[k] === c);
          return h("button", { class: "chip" + (on ? " on" : ""), "aria-pressed": String(on), onclick: () => { typed.delete(w); api.setFx(w, cur === c ? "" : c); } }, P.fillWord(c, word));
        })) : null,
        fxText(w, p[k] ? `or in your words (now: ${P.fillWord(p[k], word)})` : "in your words")));
    }
    if (adv) kids.push(h("div", { class: "field" }, h("div", { class: "label", title: "Empty = the description from the fields above" }, "Description by hand"),
      fxText("prompt_override", final, { area: true, label: "Description by hand" })));
    kids.push(h("p", { class: "small " + (long ? "warn" : "muted"), title: "The AI follows best below 200 words" },
      long ? `${words} words: the AI follows best below 200.` : `${words} words`));
    kids.push(...enhanceRows(e, final));
    return kids;
  }, { open: adv, hint: long ? `${words} words` : "", preview: final });
}
let enh = null;
let usedText = null;
function enhanceRows(e, final) {
  const f = fx(), mine = enh && enh.effect === e.id ? enh : null;
  const used = !!String(f.prompt_override || "").trim() && f.prompt_override === usedText;
  const start = () => {
    const before = final;
    enh = { effect: e.id, status: "busy", before, phase: "Starting" };
    render();
    enhance(e, before, { phase: (t) => { if (enh?.effect === e.id && enh.status === "busy") { enh.phase = t; render(); } } })
      .then((after) => { if (enh?.effect === e.id) enh = { effect: e.id, status: "ready", before, after }; render(); },
        (err) => { if (enh?.effect === e.id) enh = { effect: e.id, status: "failed", before, error: err.message }; render(); });
  };
  const rows = [h("div", { class: "row gap" },
    h("button", { class: "chip", disabled: mine?.status === "busy" || !final, title: `Rewrites the description with ${enhancer().label}; you see before and after`,
      onclick: start }, mine?.status === "busy" ? `Enhancing… ${mine.phase || ""}` : "✦ Enhance"),
    used ? h("span", { class: "muted small" }, "Enhanced · ", link("back to your words", () => { enh = null; api.setFx("prompt_override", ""); })) : null)];
  rows.push(...bonsaiRows());
  if (mine?.status === "failed") rows.push(note("err", `Enhance did not work: ${mine.error}`));
  if (mine?.status === "ready") {
    rows.push(h("p", { class: "diff" }, ...wordDiff(mine.before, mine.after).map((d) => h("span", { class: d.kind }, d.t))),
      h("div", { class: "row gap" },
        h("button", { class: "btn small", onclick: () => { const t = mine.after; enh = null; usedText = t; api.setFx("prompt_override", t); } }, "Use it"),
        h("button", { class: "btn ghost small", onclick: () => { enh = null; render(); } }, "Discard")));
  }
  return rows;
}
let setup = null;
let setupAsk = false;
let setupPoll = 0;
function pollSetup() {
  clearTimeout(setupPoll);
  bonsaiSetup().then((s) => {
    const was = setup?.state;
    setup = s;
    if (s.state === "running") setupPoll = setTimeout(pollSetup, 1500);
    if (s.state === "done" && was !== "done") { resetBonsai(); bonsaiStatus().then(() => render()).catch(() => {}); }
    render();
  }).catch(() => {});
}
function bonsaiRows() {
  const done = setup?.state === "done";
  if (hasBonsai() && !done) return [];
  if (!setup) { pollSetup(); return []; }
  const gb = (b) => `${(b / 1e9).toFixed(b < 1e9 ? 2 : 1)} GB`;
  if (setup.state === "running") {
    const of = setup.total ? ` · ${gb(setup.done)} of ${gb(setup.total)}` : "";
    return [note("hint", `Installing Bonsai 2… ${setup.phase}${of}`)];
  }
  if (done) return [hasBonsai() ? note("ok", "Bonsai 2 is installed: Enhance, the scene sentence for Inpaint and “Describe what you want” can use it now.")
    : note("err", "Bonsai 2 is downloaded but does not start here; restart ComfyUI and look at its console for “[Bonsai]”.")];
  const plan = setup.plan || [];
  if (!plan.length) return [];
  const size = plan.reduce((a, x) => a + x.bytes, 0);
  const rows = setup.state === "failed" ? [note("err", `The install stopped: ${setup.error}`)] : [];
  if (!setupAsk) rows.push(h("p", { class: "muted small" }, "Bonsai 2 writes better descriptions and can look at your clip. ",
    link(`Install Bonsai 2 (${gb(size)})`, () => { setupAsk = true; render(); })));
  else rows.push(h("div", { class: "field" }, h("p", { class: "muted small" },
    `Downloads ${plan.map((x) => `${x.name} (${gb(x.bytes)})`).join(", ")} from GitHub (PrismML's llama.cpp, MIT) and Hugging Face `
    + "(prism-ml, Apache 2.0), checks each file against its published sha256 and puts the model into ComfyUI's models/LLM."),
  h("div", { class: "row gap" }, h("button", { class: "btn small", onclick: () => {
    setupAsk = false;
    startBonsaiSetup().then((s) => { setup = s; pollSetup(); }).catch((err) => { setup = { ...setup, state: "failed", error: err.message }; render(); });
  } }, "Install"), link("Cancel", () => { setupAsk = false; render(); }))));
  return rows;
}
let library = null, libraryErr = "";
async function loadLibrary() {
  try {
    const opts = (await getJSON("/object_info/EFLoadElement"))?.EFLoadElement?.input?.required?.element?.[0];
    library = (Array.isArray(opts) ? opts : []).filter((n) => typeof n === "string" && !n.startsWith("("));
    libraryErr = "";
  } catch (err) { library = []; libraryErr = err.message; }
  render();
}
const canUseLibrary = (e, st) => !!st && (st.variant || "app") === "app" && !P.inScene(e);
const MADE_BY = [["ai", "AI", "The AI makes a new element at Run (particles, if set, guide it)"],
  ["particles", "Particles only", "The particles alone, drawn without an AI run (about a minute)"],
  ["library", "Library", "An element you kept with Save the element: placed again, no new AI run"]];
function libraryBlock(e, st) {
  const on = !!e.adv?.[P.LIBRARY] && canUseLibrary(e, st), name = e.adv?.[P.LIBRARY_ELEMENT] || "";
  const own = st.cost === "gen" ? "ai" : "particles";
  const now = on ? "library" : P.styleOf(e)?.cost === "gen" ? "ai" : "particles";
  const set = (use, n) => S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    x.adv = { ...x.adv };
    if (use) { x.adv[P.LIBRARY] = true; if (n) x.adv[P.LIBRARY_ELEMENT] = n; else delete x.adv[P.LIBRARY_ELEMENT]; }
    else { delete x.adv[P.LIBRARY]; delete x.adv[P.LIBRARY_ELEMENT]; }
  }, "library");
  const pick = (v) => {
    if (v === now) return;
    if (v === "library") {
      library = null; loadLibrary(); set(true, name);
      api.setFx("made_by", own === "ai" ? "style default" : "ai");
      return;
    }
    if (on) set(false, "");
    api.setFx("made_by", v === own ? "style default" : v);
  };
  const kids = [h("div", { class: "field" }, h("div", { class: "label" }, "Made by"),
    seg("Made by", MADE_BY.map(([k, t, tip]) => [k, t, k === own ? `${tip} · as the style has it` : tip]), now, pick))];
  if (e.adv?.[P.LIBRARY] && !on) kids.push(note("hint", "The library keeps AI elements made on black: this effect cannot place one."));
  if (!on) return kids;
  if (library === null) { loadLibrary(); kids.push(h("p", { class: "muted small" }, "Reading the library…")); return kids; }
  if (libraryErr) kids.push(note("err", `The library could not be read: ${libraryErr}`));
  if (!library.length) {
    kids.push(note("hint", "No saved elements yet. Turn on Save the element (Output, Passes) for an Overlay run; its element lands here."));
    return kids;
  }
  kids.push(h("select", { class: "text", "aria-label": "Library element", onchange: (ev) => set(true, ev.target.value) },
    h("option", { value: "", selected: !name, disabled: true }, "Pick a saved element"),
    ...library.map((n) => h("option", { value: n, selected: n === name }, n))),
    name && !library.includes(name) ? note("err", `"${name}" is not in the library on this computer.`) : null,
    h("p", { class: "muted small" }, "Placed like this style's element: position, size, light and glow as set here. The words are not used. ",
      link("Look again", () => { library = null; loadLibrary(); })));
  return kids.filter(Boolean);
}
const PLACE_LINE = {
  point: "Stands on point A and follows it. Size it with its frame in the canvas.",
  area: "Made in the frame around point A: drag its corners in the canvas.",
  object: "Covers the clicked object and moves with it: track the object in Position.",
  frame: "Over the whole picture, no point needed.",
  between: "Stretches from point A to point B: Shift-click B in the canvas.",
};
function placeBlock(e, st) {
  if (P.placeFixed(st)) return [];
  const own = P.placeOwn(st), cur = P.placeOf(e, st);
  const out = [h("div", { class: "field" }, h("div", { class: "label" }, "Placement"),
    seg("Placement", P.PLACES.map(([k, t, tip]) => [k, t, k === own ? `${tip} · as the style has it` : tip]), cur,
      (v) => setAdv(P.PLACEMENT, v === own ? undefined : v)),
    h("p", { class: "muted small" }, PLACE_LINE[cur]))];
  if (cur === "point") {
    const side0 = st.settings?.[P.SIDE] || "bottom", side = P.sideOf(e, st);
    out.push(h("div", { class: "field" }, h("div", { class: "label" }, "Sits on A by"),
      seg("Sits on A by", [["bottom", "Bottom", "Its bottom edge stands on A (a flame, a plant)"], ["centre", "Centre", "Its middle is on A (a glow, a swirl)"]]
        .map(([k, t, tip]) => [k, t, k === side0 ? `${tip} · as the style has it` : tip]), side === "centre" ? "centre" : "bottom",
      (v) => setAdv(P.SIDE, v === side0 ? undefined : v))));
  }
  return out;
}
const QUICK_ROWS = [["amount", "Amount", [["less", "Less"], ["", "As is"], ["more", "More"]]],
  ["speed", "Speed", [["slower", "Slower"], ["", "As is"], ["faster", "Faster"]]],
  ["size", "Size", [["smaller", "Smaller"], ["", "As is"], ["bigger", "Bigger"]]]];
function quickBlock(e, run) {
  const q = e.quick || {};
  const set = (k, v) => S.change((sh) => {
    const x = sh.effects.find((y) => y.id === e.id);
    if (!x) return;
    x.quick = { ...(x.quick || {}) };
    if (v) x.quick[k] = v; else delete x.quick[k];
  }, "quick");
  const parts = !!run?.settings?.Particles || !!e.adv?.Particles;
  const ai = !P.fromLibrary(e) && run?.cost === "gen" && !(e.adv?.[P.DIRECT_LOOK] ?? run?.settings?.[P.DIRECT_LOOK]);
  const words = P.quickWords(e);
  const own = q.colour && !P.QUICK_COLOURS.some(([, c]) => c === q.colour);
  const out = [h("div", { class: "field" }, h("div", { class: "label", title: "The colour it is made in. Scene & finish tints it after the run." }, "Colour"),
    h("div", { class: "swatches compact", role: "radiogroup", "aria-label": "Colour" },
      h("button", { class: "swatch none" + (!q.colour ? " on" : ""), role: "radio", "aria-checked": String(!q.colour), title: "The style's own colours",
        onclick: () => set("colour", null) }, "As is"),
      ...P.QUICK_COLOURS.map(([n, c]) => h("button", { class: "swatch" + (q.colour === c ? " on" : ""), role: "radio", "aria-checked": String(q.colour === c),
        title: n, "aria-label": `Colour ${n}`, style: { background: c }, onclick: () => set("colour", c) })),
      own ? h("button", { class: "swatch on", role: "radio", "aria-checked": "true", title: `Your colour (${P.colourName(q.colour)} for the AI)`,
        "aria-label": "Your colour", style: { background: q.colour } }) : null,
      h("label", { class: "swatch pick", title: "Any colour" }, icon("plus"), h("input", { type: "color", value: q.colour || "#ff7a1a", "aria-label": "Any colour",
        onchange: (ev) => set("colour", ev.target.value) }))))];
  for (const [k, label, opts] of QUICK_ROWS) {
    out.push(h("div", { class: "field" }, h("div", { class: "label" }, label), seg(label, opts, q[k] || "", (v) => set(k, v))));
  }
  const how = [ai && words ? `For the AI: “${words}”.` : ai ? "For the AI they are words in its description." : null,
    parts ? "They set the particles too." : null].filter(Boolean).join(" ");
  if (how) out.push(h("p", { class: "muted small" }, how));
  return out;
}
function howBlock(e, st) {
  const f = fx();
  const how = f.how_it_goes_in && f.how_it_goes_in !== "style default" ? f.how_it_goes_in : (st.settings?.[P.INPAINT] ? "inpaint" : "overlay");
  const kids = [h("div", { class: "field" }, h("div", { class: "label" }, "How it goes in"),
    seg("How it goes in", [["overlay", "Overlay", HOW.overlay], ["inpaint", "Inpaint", HOW.inpaint]], how, (v) => api.setFx("how_it_goes_in", v)),
    h("p", { class: "muted small" }, P.styleOf(e)?.cost === "gen" ? HOW[how] : "Counts when the AI makes the element; particles alone are drawn over the clip."))];
  if (how === "inpaint") {
    kids.push(sentenceField());
    if (fx().mode === "advanced") kids.push(keepRow());
    if (P.styleOf(e)?.placement === "ab" && !wordOf()) kids.push(note("hint", "Painted in between two points, the track holds better with a word for the objects. ",
      link("Name them in Position", () => { groups.set("object", true); setOpen("position"); })));
  }
  return kids;
}
const LINE_NOTE = {
  busy: "Bonsai is describing the area around the effect…",
  auto: "Written by Bonsai from the area around the effect. Type to change it; yours stays.",
  stale: "The effect moved: Bonsai describes the new area when you run.",
  own: "Your own sentence: it stays until Describe again.",
  none: "Bonsai writes it when you run, from the area around the effect.",
};
function sentenceField() {
  const s = lineState();
  const area = fxText("shot_sentence", "e.g. a man on a dark street at night, lit by a shop window", { area: true, label: "The shot in one sentence" });
  area.addEventListener("input", () => typedByHand());
  const text = s.status === "failed" ? s.error : !s.bonsai && s.status !== "own" ? `Write it yourself: ${s.why}.` : LINE_NOTE[s.status];
  return h("div", { class: "field" }, h("div", { class: "label" }, "The shot in one sentence"), area,
    h("div", { class: "row gap" }, h("span", { class: "small " + (s.status === "failed" ? "warn" : "muted") }, text),
      s.bonsai && s.status !== "busy" ? link("Describe again", () => { describeLine().catch(() => {}); }) : null));
}
function keepRow() {
  const k = Math.min(1, Math.max(0, +fx().keep_original || 0));
  const set = (v) => api.setFx("keep_original", Math.round(Math.min(1, Math.max(0, +v || 0)) * 20) / 20);
  return h("div", { class: "field" }, h("div", { class: "label" }, "Keep the original",
    h("span", { class: "muted small" }, k ? ` · ${Math.round(k * 100)} %` : " · off")),
  h("div", { class: "row gap" },
    h("input", { type: "range", min: "0", max: "1", step: "0.05", value: String(k), "aria-label": "Keep the original", onchange: (ev) => set(ev.target.value) }),
    k ? link("Off", () => set(0)) : null),
  h("p", { class: "muted small" }, "Repaints less of the area, so it stays closer to the clip. The effect gets less room; a thin one like lightning can vanish."));
}
function effectBody() {
  const data = P.presets();
  if (!data) return [h("p", { class: "muted" }, "Loading the effects…")];
  const e = effect(), st = style(), def = e && P.effectDef(e.kind);
  const adv = fx().mode === "advanced";
  const wx = { h, link, note, fx, setFx: (k, v) => api.setFx(k, v), chooseStyle, render };
  const mx = { h, link, note, fx, setFx: (k, v) => api.setFx(k, v), chooseStyle };
  const strip = effectStrip({ h, flush: flushTyped, say: (t) => api.say?.(t) });
  if (!def || showTiles || e.fresh) {
    return [...strip, h("div", { class: "tiles" }, ...data.effects.map((f) => h("button", {
      class: "tile" + (e?.kind === f.id ? " on" : ""), "aria-pressed": String(e?.kind === f.id),
      onclick: () => {
        if (e?.kind === f.id && def && !e.fresh) { showTiles = false; render(); return; }
        const first = f.styles.find((s) => s.prompt_tested !== false) || f.styles[0];
        chooseStyle(f.id, first.id);
      } },
    h("span", { class: "tile-art", "data-kind": f.id, "aria-hidden": "true" }, GLYPH[f.id] || "•"),
    h("span", { class: "tile-name" }, f.name), h("span", { class: "tile-text" }, f.text)))), ...myTiles(mx)];
  }
  const kids = [...strip, h("div", { class: "picked" }, h("span", { class: "tile-art small", "data-kind": def.id, "aria-hidden": "true" }, GLYPH[def.id] || "•"),
    h("span", { class: "strong" }, def.name), h("span", { class: "spacer" }),
    h("button", { class: "btn ghost small", onclick: () => { showTiles = true; render(); } }, "Change"))];
  const tested = (s) => (s.prompt_tested === false ? 1 : 0);
  kids.push(...myTiles(mx, def.id));
  const styleButton = (s) => h("button", { class: "style" + (s.id === e.style ? " on" : ""), role: "radio", "aria-checked": String(s.id === e.style), onclick: () => chooseStyle(def.id, s.id) },
    h("span", { class: "style-top" }, h("span", { class: "style-name" }, s.name), timeTag(e, def.id, s)),
    s.id === e.style ? h("span", { class: "style-text" }, s.text) : null);
  const exp = def.styles.filter((s) => tested(s));
  kids.push(h("div", { class: "styles", role: "radiogroup", "aria-label": "Style" }, ...def.styles.filter((s) => !tested(s)).map(styleButton),
    ...(exp.length ? [h("p", { class: "muted small styles-sub", title: "Not tested by us yet" }, "Experimental · results may vary"), ...exp.map(styleButton)] : [])));
  if (!st) return kids;
  if (st.prompt_tested === false) kids.push(note("hint", EXPERIMENTAL));
  kids.push(...positionHints(e, placed()));
  kids.push(...libraryBlock(e, st));
  kids.push(...placeBlock(e, st));
  const lib = P.fromLibrary(e) || (!!e.adv?.[P.LIBRARY] && canUseLibrary(e, st));
  if (!lib) {
    const p = P.promptOf(e);
    if (p) kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Strength"),
      seg("Strength", [["subtle", "Subtle"], ["normal", "Normal"], ["strong", "Strong"]], fx().strength || "normal", (v) => api.setFx("strength", v))));
    kids.push(...quickBlock(e, effStyle(st, e)));
    if (p && !p.what) kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Your effect in words"),
      h("div", { class: "row gap" }, fxText("describe", "e.g. a glowing blue crystal"), suggestButton(wx, typed.get("describe")?.value ?? fx().describe)),
      ...wishResults(wx)));
    if (p && (adv || !p.what)) kids.push(promptGroup(e, st, p, adv));
  }
  if (P.canPaintIn(st) && !lib) kids.push(...howBlock(e, st));
  if (adv && !lib) {
    const f = fx(), keep = f.control_after_generate === "fixed";
    kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "AI seed"),
      h("div", { class: "row gap" }, fxText("seed", "0", { label: "AI seed", num: true }),
        toggle("Keep it", keep, (v) => api.setFx("control_after_generate", v ? "fixed" : "randomize"), "Off: a new seed for every run"))));
    const sw = (k, label, tip) => {
      const own = st.settings?.[k] === true, cur = e.adv?.[k] ?? own;
      return toggle(label, cur, (v) => setAdv(k, v === own ? undefined : v), `${tip}${own ? " · on in this style" : ""}`);
    };
    kids.push(h("div", { class: "field stack" }, h("div", { class: "label" }, "AI element"),
      sw(SOLID, "Solid element", "Cut out with its own matte instead of its brightness: liquid, dust, stones (Alpha Gen)"),
      sw(START_VIDEO, "Particles start the AI's video", "The AI starts from the particles' picture as well as being guided by it")));
  }
  const run = effStyle(st, e);
  if (livePreviews(run) && S.getShot().clip) kids.push(...liveBlock(e, adv, run));
  if (!adv && livePreviews(run) && S.getShot().clip) kids.push(...basicFill(emitterCtx(e, run)));
  if (adv) kids.push(h("div", { class: "field emitter" }, ...emitterPanel({ ...emitterCtx(e, run), st0: st })));
  kids.push(...saveRows(mx));
  return kids;
}

function finishBody() {
  const e = effect(), f = fx();
  const made = e && S.shownOf(e.id)?.status === "done";
  return [
    ...finishRows({ h, seg, toggle, note, link, group, fx }),
    group("in-run", "In the run", () => [
      toggle("Night or dark clip", f.night, (v) => api.setFx("night", v), "Darkens the clip for night and lets the effect light it"),
      h("p", { class: "muted small" }, "The AI and the light pass are made on the darkened clip: run again to see a change."),
    ], { open: !made }),
  ];
}

const LEFT_OUT = [["VideoDepthAnything", "No depth yet, so nothing in the clip hides the particles: Analysis in Clip gives the depth."],
  ["SAM3", "No kept track of the object yet: the particles hang on your point. Track it (Position) for the object's motion."]];
function liveBlock(e, adv, st) {
  const ls = S.ui.liveSim, c = S.getShot().clip, f = fx();
  const mine = ls && ls.effect === e.id && ls.clip === c?.name;
  const hd = mine ? ls.data?.header : null;
  const kids = [h("div", { class: "label" }, "Live preview")];
  if (!mine || ls.status === "running") kids.push(note("ok", `Simulating the particles${e.where.a ? "" : " at the centre"}…`));
  else if (ls.status === "failed") kids.push(note("err", `The live preview failed: ${ls.error || "unknown error"}`));
  else if (hd) kids.push(note("ok", `The particles as the run makes them (same engine, particle seed ${hd.seed}), `
    + `${hd.mode === "hold" ? `${fmtSec(hd.n / hd.fps)} on frame ${hd.frame + 1}` : `${hd.n} frames`} · ${((ls.server?.total ?? ls.ms) / 1000).toFixed(1)} s.`));
  if (mine && ls.status === "ready") {
    for (const [cls, text] of LEFT_OUT) if ((ls.leftOut || []).some((x) => x.startsWith(cls))) kids.push(h("p", { class: "muted small" }, text));
    const guided = guideNow(P.styleDef(e.kind, e.style), e) === "particles";
    kids.push(h("p", { class: "muted small" }, st.cost !== "gen" ? "Made by the particles alone: the run draws them as they show here."
      : guided ? "How the AI turns them into sparks, smoke or flames shows only in the run."
        : "Drawn over the AI's element as they show here; the element itself shows only in the run."));
  }
  if (st.variant === "dissolve") {
    if (mine && ls.status === "ready") kids.push(h("p", { class: "muted small" }, "Dark where the object is gone: the run fills it with the scene."));
    return [h("div", { class: "field live" }, ...kids.filter(Boolean))];
  }
  kids.push(seg("Live preview", [["play", "Play with clip", "The clip plays, the particles with it (as in the run)"],
    ["hold", "Hold frame", "The clip stands on the frame at the playhead, the emitter keeps running on it"]], liveMode(), setLiveMode));
  if (!adv) kids.push(...prerollRows(hd));
  return [h("div", { class: "field live" }, ...kids.filter(Boolean))];
}
function prerollRows(hd) {
  const f = fx(), pre = Number.isFinite(+f.preroll) ? +f.preroll : -2;
  const own = pre >= 0;
  return [h("div", { class: "label" }, "Pre-roll", h("span", { class: "muted small" }, hd?.preroll_s ? ` · ${(+hd.preroll_s).toFixed(1)} s now` : "")),
    seg("Pre-roll", [["preset", "Preset", "As the style has it"], ["auto", "Auto", "Long enough for the particles to cross the frame"],
      ["own", "Seconds", "Your own length"]], pre === -2 ? "preset" : pre === -1 ? "auto" : "own",
    (v) => api.setFx("preroll", v === "preset" ? -2 : v === "auto" ? -1 : own ? pre : 2)),
    own ? h("input", { class: "text", type: "number", min: "0", max: "60", step: "0.5", value: String(pre), "aria-label": "Pre-roll in seconds",
      onchange: (ev) => api.setFx("preroll", Math.min(60, Math.max(0, +ev.target.value || 0))) }) : null,
    h("p", { class: "muted small" }, "The particles run this long before the clip starts, so the first frame is already full (snow, rain).")].filter(Boolean);
}
function emitterCtx(e, st) {
  const c = S.getShot().clip;
  const mine = (x) => x && x.effect === e.id && x.clip === c?.name;
  const sim = mine(S.ui.liveSim) && S.ui.liveSim.data?.header ? S.ui.liveSim : null;
  const ls = sim || (mine(S.ui.liveValues) && S.ui.liveValues.header ? { ...S.ui.liveValues, data: { header: S.ui.liveValues.header } } : null);
  const hd = ls ? ls.data.header : null;
  const kind = emitterKind(st);
  const own = ownValues(fx());
  const back = Object.fromEntries(Object.entries(hd?.base || {}).filter(([k]) => k !== "direction" && !(k in own)));
  return { e, st, kind, f: fx(), api, own, P: hd?.params ? { ...hd.params, ...back, ...own } : null, B: hd?.base || null, amount: hd?.amount ?? 1,
    fresh: !!hd && ls.status === "ready", busy: !!hd && ls.status === "running" && !ls.lookOnly,
    ui: { seg, toggle, group, note, link, open: setOpen },
    extras: { seed: () => particleSeed(e), preroll: () => (kind !== "dissolve" ? prerollRows(hd) : []) } };
}
const SOLID = "Solid element (Alpha Gen cut-out)", START_VIDEO = "Particles: start video (seed)";
function particleSeed(e) {
  const locked = !!e.seedLocked;
  const lock = (v) => S.change((sh) => { const x = sh.effects.find((y) => y.id === e.id); x.seedLocked = v; }, "seed-lock");
  const pseed = fxText("particle_seed", "42", { label: "Particle seed", num: true });
  pseed.disabled = locked;
  return [h("div", { class: "label" }, "Particle seed"),
    h("div", { class: "row gap" }, pseed,
      h("button", { class: "btn small", disabled: locked, title: "A new seed: other particles, the same settings",
        onclick: () => api.setFx("particle_seed", Math.floor(Math.random() * 2 ** 31)) }, "New seed"),
      toggle("Lock", locked, lock, "Keep this seed: the dice and the field are locked")),
    h("p", { class: "muted small" }, "The same seed gives the same particles in the preview and in the run. Apart from the AI seed.")];
}

const setOutput = (fn) => S.change((sh) => { sh.output = { ...outputOf(sh) }; sh.output.passes = { ...sh.output.passes }; fn(sh.output); }, "output");
function outputBody() {
  const e = effect(), st = style(), f = fx();
  const kids = [];
  if (!st) {
    kids.push(h("p", { class: "muted small" }, "Choose an effect in Effect for a run. Without one, Export gives the clip alone: its passes, NVIDIA × 2 or HDR."));
    kids.push(group("export", "Export", () => exportRows({ h, seg, toggle, note, link, render, say: (t) => api.say(t) }),
      { open: true, preview: "the clip alone, with its passes" }));
    return kids;
  }
  const o = outputOf(S.getShot());
  const gen = st?.cost === "gen";
  const preview = o.quality === "preview" && canPreview(st, e);
  if (gen) {
    for (const n of systemNotes()) kids.push(n.kind === "err" ? note("hint", n.text) : h("p", { class: "muted small" }, n.text));
    const can = canPreview(st, e);
    kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Quality"),
      seg("Quality", [["preview", "Preview (fast)", can ? "Half the size, without light, glow and normals: a quick look. Make it final afterwards from the same run."
        : "Preview works for AI elements in Overlay (not with Inpaint)"], ["full", "Full", "Full size with all passes"]], preview ? "preview" : "full",
      (v) => { if (v === "preview" && !can) return; setOutput((x) => { x.quality = v; }); })));
    if (!can && o.quality === "preview") kids.push(h("p", { class: "muted small" }, "Preview needs an AI element in Overlay: this one runs at full size."));
    const up = f.sharper_2x ? "ltx" : o.upscale === "nvidia" && hasRtx() ? "nvidia" : "off";
    const pick = (v) => {
      if (v === "nvidia" && !hasRtx()) return;
      if (!!f.sharper_2x !== (v === "ltx")) api.setFx("sharper_2x", v === "ltx");
      setOutput((x) => { x.upscale = v === "nvidia" ? "nvidia" : "off"; });
    };
    kids.push(h("div", { class: "field" }, h("div", { class: "label" }, "Upscale"),
      seg("Upscale", [["off", "Off"], ["ltx", "LTX × 2", "A second LTX pass at twice the size: more detail, takes longer"],
        ["nvidia", "NVIDIA × 2", hasRtx() ? "NVIDIA RTX Super Resolution: fast, draws nothing new (with the HDR core of TrueHDR)"
          : "Needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes"]], up, pick)));
    if (!hasRtx()) kids.push(h("p", { class: "muted small" }, "NVIDIA × 2 needs an NVIDIA RTX card and ComfyUI's NVIDIA nodes."));
  }
  const on = (k) => e?.adv?.[k] ?? lightDefault(st, k);
  const setAdv = (k, v) => S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    x.adv = { ...x.adv };
    if (v === lightDefault(st, k)) delete x.adv[k]; else x.adv[k] = v;
  }, "look");
  if (e && st) kids.push(group("passes", "Passes", () => [
    preview ? h("p", { class: "muted small" }, "A preview writes plate, element and depth only; Make final adds the rest.") : null,
    toggle("Light (on the scene)", on("Light"), (v) => setAdv("Light", v), "The light the effect throws on the clip (light pass); needed for Light on the scene"),
    toggle("Glow", on("Glow"), (v) => setAdv("Glow", v), "The glow as its own pass"),
    toggle("Depth", o.passes.depth, (v) => setOutput((x) => { x.passes.depth = v; }), "Depth of the clip: depth blur and haze in Scene & finish need it"),
    toggle("Normals", o.passes.normals, (v) => setOutput((x) => { x.passes.normals = v; }), "Surface normals of the clip, for relighting in compositing (made with the light pass)"),
    toggle("Mask", o.passes.mask, (v) => setOutput((x) => { x.passes.mask = v; }), "The mask of the object the effect sits on, per frame (from the track), for compositing"),
    h("p", { class: "muted small" }, "Plate and element (with its alpha) are always written, as EXR (half, linear) in ComfyUI's output folder, element-forge/<run>/."),
    R.canSaveElement(st, e) ? toggle("Save the element", !!o.saveElement, (v) => setOutput((x) => { x.saveElement = v; }),
      "Also keeps the AI element with its alpha in the element library (output/element-forge/elements/<run>/), to place it again without a new run") : null,
  ], { open: S.ui.mode === "advanced", preview: [on("Light") ? "light" : null, on("Glow") ? "glow" : null, o.passes.depth ? "depth" : null,
    o.passes.normals && on("Light") ? "normals" : null, o.passes.mask ? "mask" : null].filter(Boolean).join(" · ") }));
  const est = e && st ? estimate(e, S.getShot()) : null;
  const c = S.getShot().clip, anaRec = c ? keptOf(c) : null;
  if (est) kids.push(h("p", { class: "muted small" }, `Run makes it: about ${est.lo}–${est.hi} min` +
    (anaRec?.loaded && !anaRec.analysis && !c.still ? `, plus about ${anaMinutes(c)} min for depth and normals (the clip is not analysed yet).` : ".")))
  kids.push(...versionRows({ h, link, note, fx, setFx: (k, v) => api.setFx(k, v), chooseStyle, render,
    say: (t, err) => (err ? api.say(t) : (api.info || api.say)(t)) }));
  if (e && st) kids.push(group("export", "Export", () => exportRows({ h, seg, toggle, note, link, render, say: (t) => api.say(t) }),
    { open: S.getShot().effects.some((y) => S.shownOf(y.id)?.status === "done"),
      preview: S.getShot().effects.some((y) => S.shownOf(y.id)?.status === "done") ? "the comp as you see it, at full size" : "the clip alone, with its passes" }));
  if (lastResult) kids.push(note("ok", `Last run: ${lastResult.label}`));
  const d = api.docked?.(), made = S.getShot().effects.some((y) => S.shownOf(y.id)?.status === "done");
  if (d && (made || d !== "canvas")) kids.push(h("button", { class: "btn small", onclick: () => api.show(d === "canvas" ? "result" : "canvas") },
    d === "canvas" ? "Show the result in the middle" : "Show the canvas in the middle"));
  return kids;
}

function paint() {
  frame = 0;
  if (!el) return;
  if (advance && stepState(advance) === "done") { if (open === advance) open = null; advance = null; }
  pokeLive();
  const c = S.getShot().clip;
  if (c && !kept.has(keptKey(c))) loadKept(c);
  else if (c) publishKept(c);
  if (!open || stepState(open) === "locked") open = autoOpen();
  const ae = effect(), sv = ae && S.shownOf(ae.id);
  if (sv?.status === "done" && sv.comp && !sv.preview && !sv.previewError) L.ensurePreview(ae.id, sv);
  const act = document.activeElement;
  const key = el.contains(act) ? act?.dataset?.key : null;
  const sel = key && "selectionStart" in act ? [act.selectionStart, act.selectionEnd] : null;
  const mode = fx().mode === "advanced" ? "advanced" : "basic";
  const withGear = api.inApp ? !!api.inApp() : true;
  if (!withGear) gearOpen = false;
  el.replaceChildren(
    h("div", { class: "efa-cards-head" },
      seg("Mode", [["basic", "Basic"], ["advanced", "Advanced"]], mode, (v) => api.setFx("mode", v)),
      withGear ? h("button", { class: "btn ghost small icon gear" + (gearOpen ? " on" : ""), "aria-pressed": String(gearOpen), "aria-label": "This computer and the models",
        title: gearOpen ? "Back to the steps" : "This computer: LTX model, text encoder, text model, NVIDIA, and which models are installed",
        onclick: () => { gearOpen = !gearOpen; render(); } }, icon("gear")) : null),
    ...(gearOpen ? [h("section", { class: "card open gear-card", "data-step": "gear" },
      h("button", { class: "card-head", "aria-expanded": "true", onclick: () => { gearOpen = false; render(); } },
        h("span", { class: "num", "aria-hidden": "true" }, icon("gear")), h("span", { class: "title" }, "This computer and the models"),
        h("span", { class: "sum" }, "Back to the steps")),
      h("div", { class: "card-body" }, ...gearRows({ h, seg, toggle, note, link, render })))]
      : STEPS.map(([id, t], i) => card(id, i + 1, t, { clip: clipBody, position: positionBody, effect: effectBody, finish: finishBody, output: outputBody }[id]))));
  if (key) {
    const back = el.querySelector(`[data-key="${CSS.escape(key)}"]`);
    if (back) { back.focus({ preventScroll: true }); if (sel) try { back.setSelectionRange(sel[0], sel[1]); } catch {  } }
  }
  api.relayout?.();
}
export function render() {
  if (!frame) frame = requestAnimationFrame(paint);
}

export function mountPanel(target, a) {
  el = target;
  api = a;
  initLive({ fx });
  initEffects({ fx, setAll: (values) => api.setFxAll?.(values) });
  initShotLine({ fx, setFx: (k, v) => api.setFx(k, v) });
  bonsaiStatus().then(() => render()).catch(() => {});
  initWish(render);
  initMyEffects({ userData: api.userData?.(), render });
  loadRtx().then(render, () => {});
  loadSystem().then(render, () => {});
  loadGear(render);
  R.onRunChange(render);
  R.onVersionReady(() => render());
  render();
  return {
    render,
    result(info) { lastResult = info; render(); },
    flush: flushTyped,
  };
}

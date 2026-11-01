import * as S from "./state.js";
import * as C from "./comfy.js";
import { styleDef, styleOf, composePrompt, inScene, inpaintSettings, objectWord, INPAINT, fromLibrary } from "./presets.js";
import { clamp, store, uid } from "./lib.js";
import { ltxForBuild } from "./machine.js";

const MAX_FRAMES = 161;
export const ltxFrames = (n) => Math.max(9, Math.floor((Math.min(n, MAX_FRAMES) - 1) / 8) * 8 + 1);

export function genSize(style, aspect, guide, scale = 1) {
  const [gw, gh] = style.gen || [512, 768];
  const area = gw * gh * scale * scale, step = guide ? 64 : 32, lim = Math.max(1, area / (step * 4) ** 2);
  aspect = clamp(aspect, 1 / lim, lim);
  const w = Math.sqrt(area * aspect), h = w / aspect;
  const r = (v) => Math.max(step * 4, Math.round(v / step) * step);
  return [r(w), r(h)];
}

export function genWindow(style, b, guide, scale = 1) {
  const [gw, gh] = genSize(style, b.w / b.h, guide, scale);
  let w = b.w, h = b.h;
  if (w / h < gw / gh) w = h * gw / gh; else h = w * gh / gw;
  return { x: b.x + (b.w - w) / 2, y: b.y + (b.h - h) / 2, w, h, gw, gh };
}

export const GUIDE = "Guide for the AI (particles / drawn path / object shape / none)";
const withAdv = (st, effect) => ({ ...(st?.settings || {}), ...(effect?.adv || {}) });
export function guideOf(st, effect) {
  const s = withAdv(st, effect);
  if (s[GUIDE]) return s[GUIDE];
  if (s.Particles) return s["Particles: guide"] === false ? "none" : "particles";
  return s.Guide ? "drawn path" : "particles";
}
export const usesGuide = (st, effect) => {
  const g = guideOf(st, effect);
  return g === "drawn path" || g === "object shape" || (g === "particles" && !!withAdv(st, effect).Particles);
};
export const inWindow = (st, effect) => st?.placement === "point"
  && (usesGuide(st, effect) || !!withAdv(st, effect).Particles || !!withAdv(st, effect)["Follows motion"]);
export function basePoint(st, b) {
  const side = st?.settings?.["Emitter side"] || "bottom";
  return { x: side === "left" ? b.x : side === "right" ? b.x + b.w : b.x + b.w / 2,
    y: side === "top" ? b.y : side === "bottom" ? b.y + b.h : b.y + b.h / 2 };
}

export function defaultBox(effect, clip) {
  const st = styleOf(effect);
  const a = effect.where.a || { x: clip.width / 2, y: clip.height / 2 };
  if (!st) return null;
  if (st.placement === "window") {
    const s = Math.min(clip.width, clip.height);
    const [fw, fh] = st.win || [0.6, 0.6];
    const [ex, ey] = st.emitter || [0.5, 0.5];
    const w = fw * s, h = fh * s;
    return { x: a.x - ex * w, y: a.y - ey * h, w, h };
  }
  if (st.placement === "point") {
    const [gw, gh] = st.gen || [512, 768];
    const sc = st.settings?.["Size in plate"] ?? 0.3;
    const w = gw * sc, h = gh * sc;
    const side = st.settings?.["Emitter side"] || "bottom";
    const sh = guideOf(st, effect) === "object shape" ? 0.2 : 0;
    const ox = side === "left" ? 0 : side === "right" ? w : w / 2;
    const oy = side === "top" ? sh * h : side === "bottom" ? (1 - sh) * h : h / 2;
    return { x: a.x - ox, y: a.y - oy, w, h };
  }
  if (st.placement === "ab" && effect.where.a && effect.where.b) {
    const b = effect.where.b, w0 = Math.abs(a.x - b.x), h0 = Math.abs(a.y - b.y), extra = Math.max(w0, h0) + 96;
    const [gw, gh] = st.gen || [448, 640];
    const w = Math.max(w0 + extra, (h0 + extra) * gw / gh), h = w * gh / gw;
    return { x: (a.x + b.x) / 2 - w / 2, y: (a.y + b.y) / 2 - h / 2, w, h };
  }
  return null;
}
export function frameBox(effect, clip) {
  return effect.box || defaultBox(effect, clip);
}

export const quality = () => (S.getShot()?.output?.quality === "preview" ? "preview" : "full");
export const setQuality = (q) => store.set("quality", q === "preview" ? "preview" : "full");
export const canPreview = (st, effect) => !!st && st.cost === "gen" && st.variant === "app" && !inScene(effect) && !fromLibrary(effect);
const PREVIEW_PASSES = ["plate", "element", "depth", "mask"], ALL_PASSES = ["plate", "element", "light", "glow", "depth", "normals", "mask"];
export const ADDABLE = ["light", "glow", "normals"];
const VARIANT_PASSES = { dissolve: ["plate", "element", "depth", "light", "normals", "mask"] };
const OLD_VARIANT_PASSES = { dissolve: ["plate", "element", "depth"] };
export const missingPasses = (v) => (v?.status === "done" && v.passes && !v.paint && (v.variant || "app") === "app"
  ? ADDABLE.filter((p) => !v.passes.includes(p)) : []);
export const hasPass = (v, p) => !v?.passes || (v.passes.includes(p) && (v.exact || (OLD_VARIANT_PASSES[v.variant] || ALL_PASSES).includes(p)));
export const lightShown = (v) => !v || hasPass(v, "light") || missingPasses(v).includes("light");
const passesOf = (mode, effect, values, variant) => ((mode === "preview" && !VARIANT_PASSES[variant] ? PREVIEW_PASSES
  : VARIANT_PASSES[variant] || ALL_PASSES).filter((p) => values?.Light !== false || (p !== "light" && p !== "normals")));
const previewScale = (st, effect) => (canPreview(st, effect) && quality() === "preview" ? 0.5 : 1);

export function valuesFor(effect, shot, scale = 1) {
  const st = styleOf(effect);
  const clip = shot.clip;
  const v = { ...st.settings };
  if (clip.still) {
    v["Still image (a picture in the input folder instead of the clip)"] = clip.name;
    v["Still image length (s)"] = clip.seconds;
  } else v["Clip"] = clip.name;
  v["Frames"] = ltxFrames(clip.frames);
  const a = effect.where.a || { x: clip.width / 2, y: clip.height / 2 };
  v["Point A x"] = Math.round(a.x);
  v["Point A y"] = Math.round(a.y);
  if (effect.where.b) { v["Point B x"] = Math.round(effect.where.b.x); v["Point B y"] = Math.round(effect.where.b.y); }
  const word = objectWord(effect);
  if (word) v["Object word (optional, helps the click)"] = word;
  const guide = usesGuide(st, effect);
  if (st.placement === "window" || (st.placement === "ab" && effect.box) || inWindow(st, effect)) {
    const w = genWindow(st, frameBox(effect, clip), guide, scale);
    v["Window A-B automatic"] = false;
    v["Window width (plate px)"] = Math.round(w.w);
    v["Window height (plate px)"] = Math.round(w.h);
    v["Emitter x in window"] = +clamp((a.x - w.x) / w.w, -4, 5).toFixed(3);
    v["Emitter y in window"] = +clamp((a.y - w.y) / w.h, -4, 5).toFixed(3);
    [v["Generate width"], v["Generate height"]] = [w.gw, w.gh];
  } else if (st.placement === "ab") {
    v["Window A-B automatic"] = true;
    const g = st.gen || [448, 640];
    [v["Generate width"], v["Generate height"]] = scale === 1 ? g : genSize({ gen: g }, g[0] / g[1], guide, scale);
  } else if (st.placement === "frame" || (st.placement === "object" && st.variant === "app")) {
    v["Window width (plate px)"] = clip.width;
    v["Window height (plate px)"] = clip.height;
    v["Emitter x in window"] = 0.5;
    v["Emitter y in window"] = 0.5;
    [v["Generate width"], v["Generate height"]] = genSize(st, clip.width / clip.height, guide, scale);
  } else if (st.placement === "point") {
    const b = frameBox(effect, clip);
    const [gw, gh] = genSize(st, b.w / b.h, guide, scale);
    v["Generate width"] = gw;
    v["Generate height"] = gh;
    v["Size in plate"] = +Math.min(b.w / gw, b.h / gh).toFixed(3);
    const p = basePoint(st, b), dx = Math.round(p.x - a.x), dy = Math.round(p.y - a.y);
    if (dx) v["Base beside A x (plate px)"] = dx;
    if (dy) v["Base beside A y (plate px)"] = dy;
  }
  if (effect.timing.start) v["Starts at (s)"] = +effect.timing.start.toFixed(2);
  if (st.dir === "dissolve") {
    const end = effect.timing.end ?? Math.min(clip.seconds, 161 / clip.fps);
    v["Dissolve duration (s)"] = +Math.max(0.2, end - (effect.timing.start || 0)).toFixed(2);
    v["Dissolve direction (0 up, 90 right)"] = effect.dir ?? 90;
  }
  if (st.settings?.Particles && st.placement !== "ab" && st.dir !== "dissolve" && effect.dir != null) v["Particle direction (-1 = preset)"] = Math.round(effect.dir);
  if (effect.depth) {
    const key = st.settings?.Particles ? "Particle depth offset" : "Depth offset (+ = element nearer, less hidden)";
    v[key] = +((st.settings?.[key] ?? 0) + effect.depth).toFixed(3);
  }
  const prompt = composePrompt(effect);
  if (prompt) v["Effect prompt"] = prompt;
  if (shot.night) v["Night"] = true;
  if (inScene(effect)) {
    if (!st.settings?.[INPAINT]) Object.assign(v, inpaintSettings(effect.kind));
    if (shot.scene?.trim()) v["Shot description (Inpaint)"] = shot.scene.trim();
  }
  v["Seed"] = effect.seed.mode === "keep" && effect.seed.value != null ? effect.seed.value : Math.floor(Math.random() * 2 ** 31);
  Object.assign(v, effect.adv || {});
  if (st.settings?.Particles && v["Particle emitter"] === "area" && effect.box) {
    const b = effect.box;
    v["Particle area"] = [b.x / clip.width, b.y / clip.height, (b.x + b.w) / clip.width, (b.y + b.h) / clip.height]
      .map((x) => +clamp(x, 0, 1).toFixed(4)).join(", ");
  }
  if (st.settings?.Particles && v["Particle emitter"] === "groups" && effect.groups?.length) {
    let ex = {};
    try { ex = JSON.parse(v["Particle pro: extra (JSON)"] || "{}") || {}; } catch { ex = {}; }
    v["Particle pro: extra (JSON)"] = JSON.stringify({ ...ex, groups: effect.groups.map(([x, y, depth, scale = 1]) => ({ x, y, depth, scale })) });
  }
  return v;
}

export function estimate(effect, shot) {
  const st = styleOf(effect);
  if (!st || !shot.clip) return null;
  const frames = ltxFrames(shot.clip.frames);
  if (st.cost !== "gen" || fromLibrary(effect)) return { lo: 1, hi: 3 };
  const v = valuesFor(effect, shot, previewScale(st, effect));
  const [gw, gh] = v["Generate width"] ? [v["Generate width"], v["Generate height"]] : st.gen || [512, 768];
  const work = (gw * gh * frames) / (512 * 768 * 81);
  const base = 3 + 5 * work, mid = base * speed();
  const lo = Math.max(1, Math.round(mid * 0.75));
  return { lo, hi: Math.max(lo + 1, Math.round(mid * 1.35)), base };
}
const speed = () => {
  const r = store.get("speed", []).filter((x) => x > 0).sort((a, b) => a - b);
  return r.length ? clamp(r[(r.length - 1) >> 1], 0.15, 4) : 1;
};
export function learnSpeed(base, minutes) {
  if (!(base > 0) || !(minutes > 0)) return;
  store.set("speed", [...store.get("speed", []), +(minutes / base).toFixed(3)].slice(-5));
}

export const RUN_STEPS = [
  ["Reading the clip", /^(LoadVideo|GetVideoComponents|EFClipFrames|ResolutionSelector|ImageScale|ResizeImage|ImageResize|EFStartAt|EFFrameStep)/],
  ["Following the object", /^(SAM3|EFTrack|EFMaskTrack|EFCameraTrack|EFPointCameraTrack|EFAnchor|EFPoints|EFMotionTracks|EFFollowCrop)/],
  ["Measuring depth", /(DepthAnything|MoGe|Depth_?Anything)/i],
  ["AI is generating", /^(LTX|EmptyLTX|SamplerCustom|KSampler|CLIPTextEncode|CLIPLoader|DualCLIP|UNETLoader|UnetLoader|LoraLoader|VAELoader|VAEDecode|VAEEncode|CFGGuider|BasicScheduler|ManualSigmas|RandomNoise|KSamplerSelect|EFBonsai|RTXVideo|EFGuide|EFVideoLatentMask|EFClean)/],
  ["Building the effect", /^(EFParticles|EFDissolve|EFFireflies|EFLightning|EFSpark|EFPlace|EFUnmult|EFCompToLayer|EFContact|EFScatter|EFEffectLayer|EFCEffect|EFAlpha|EFElement|EFLoadElement|EFHDRMerge)/],
  ["Light and glow", /^(EFDepthLight|EFGlow|EFNightGrade|EFDeflicker|EFRelight|EFLightPass|EFCLightPass)/],
  ["Saving the result", /^(Save|EFSave|EFDither|CreateVideo|EFCompPreview|EFTrackPreview)/],
];
export const runStepOf = (cls) => (cls ? RUN_STEPS.findIndex(([, re]) => re.test(cls)) : -1);
const phaseOf = (cls) => RUN_STEPS[runStepOf(cls)]?.[0] || null;
const live = new Map();
export const running = (effectId) => live.get(effectId) || null;
let repaint = () => {};
export const onRunChange = (fn) => (repaint = fn);
let ready = () => {};
export const onVersionReady = (fn) => (ready = fn);
function finished(effectId, versionId) {
  const first = !S.shownOf(effectId);
  if (first) S.showVersion(effectId, versionId);
  else S.updateVersion(effectId, versionId, { unseen: true });
  ready(effectId, S.allVersionsOf(effectId).find((x) => x.id === versionId), first);
}

export async function uploadPaint(strokes, clip, tag) {
  const c = document.createElement("canvas");
  c.width = clip.width; c.height = clip.height;
  const g = c.getContext("2d");
  g.fillStyle = "#000"; g.fillRect(0, 0, c.width, c.height);
  g.lineCap = g.lineJoin = "round";
  for (const s of strokes) {
    g.globalCompositeOperation = s.erase ? "source-over" : "destination-out";
    g.strokeStyle = g.fillStyle = "#000";
    g.lineWidth = s.r * 2;
    g.beginPath();
    g.moveTo(s.pts[0][0], s.pts[0][1]);
    if (s.pts.length === 1) { g.arc(s.pts[0][0], s.pts[0][1], s.r, 0, Math.PI * 2); g.fill(); continue; }
    for (const [x, y] of s.pts.slice(1)) g.lineTo(x, y);
    g.stroke();
  }
  const blob = await new Promise((res) => c.toBlob(res, "image/png"));
  const fd = new FormData();
  fd.append("image", blob, `ef_paint_${tag}.png`);
  fd.append("type", "input");
  fd.append("overwrite", "true");
  const r = await fetch("/upload/image", { method: "POST", body: fd });
  if (!r.ok) throw new Error(`could not upload the painting (HTTP ${r.status})`);
  const j = await r.json();
  return j.subfolder ? `${j.subfolder}/${j.name}` : j.name;
}
export async function paintValues(effect, clip) {
  const v = {};
  const p = effect.paint || {};
  if (effect.adv?.["Own object mask (off = click)"] && p.mask?.length) {
    v["Own object mask: first frame, paint the object (mask editor)"] = await uploadPaint(p.mask, clip, `${effect.id}_mask_${uid().slice(0, 4)}`);
  }
  if (effect.adv?.["Guide source"] === "draw" && p.guide?.length) {
    v["Guide drawing (paint in the mask editor)"] = await uploadPaint(p.guide, clip, `${effect.id}_guide_${uid().slice(0, 4)}`);
    v[GUIDE] = "drawn path";
  } else if (effect.adv?.["Particle emitter"] === "drawing" && p.guide?.length) {
    v["Guide drawing (paint in the mask editor)"] = await uploadPaint(p.guide, clip, `${effect.id}_guide_${uid().slice(0, 4)}`);
  }
  return v;
}

export async function generate(effect, opts = {}) {
  C.connectSocket();
  if (live.has(effect.id)) return null;
  const state = { promptId: null, started: Date.now(), phase: "Preparing the job", value: 0, max: 0, est: estimate(effect, S.getShot()), ran: null };
  live.set(effect.id, state);
  repaint();
  let version = null;
  const setVersion = (patch) => {
    S.updateVersion(effect.id, version.id, patch);
    if (patch.status === "done") finished(effect.id, version.id);
  };
  try {
    const shot = S.getShot();
    const st = styleOf(effect);
    const from = opts.from || null;
    const mode = from ? "final" : previewScale(st, effect) < 1 ? "preview" : "full";
    state.learn = mode !== "final";
    const values = from ? {} : { ...valuesFor(effect, shot, mode === "preview" ? 0.5 : 1), ...(await paintValues(effect, shot.clip)) };
    const run = `app-${effect.kind}-${new Date().toISOString().replace(/[-:T]/g, "").slice(4, 12)}-${uid().slice(0, 4)}`;
    const recipe = from ? from.recipe : { ...JSON.parse(JSON.stringify(effect)), night: !!shot.night };
    const ltx = st.cost === "gen" ? ltxForBuild() : ltxForBuild()?.depth ? { depth: ltxForBuild().depth } : null;
    const extra = mode === "full" ? {} : { mode, ...(from ? { from_run: from.run } : {}) };
    const { prompt } = await C.build(st.variant, values, run, { effect: recipe, clip: from ? null : shot.clip, ...(ltx ? { ltx } : {}), mode }, ltx, extra);
    version = { id: uid(), run, variant: st.variant, seed: from ? from.seed : values.Seed, prompt: from ? from.prompt : values["Effect prompt"] || null,
      clip: from ? from.clip : shot.clip.name, started: Date.now(), status: "queued", recipe, files: [], comp: null,
      quality: mode, exact: true, ...(from ? { from: from.id } : {}), passes: from ? ALL_PASSES : passesOf(mode, effect, values, st.variant),...(!from && inScene(effect) ? { paint: true } : {}) };
    S.addVersion(effect.id, version);
    state.phase = "Waiting in the queue";
    state.promptId = await C.queue(prompt, handlers(effect.id, version, state, setVersion, prompt));
    setVersion({ status: "running", promptId: state.promptId });
    waitInQueue(effect.id, state);
  } catch (e) {
    live.delete(effect.id);
    if (version) setVersion({ status: "failed", error: e.message + (e.detail ? ` (${e.detail})` : "") });
    repaint();
    throw e;
  }
  repaint();
  return version;
}

export async function addPasses(effect, version, passes) {
  C.connectSocket();
  if (live.has(effect.id)) return null;
  const state = { promptId: null, started: Date.now(), phase: "Preparing the job", value: 0, max: 0, est: { lo: 1, hi: 3 }, ran: null };
  live.set(effect.id, state);
  repaint();
  const setVersion = (patch) => {
    const { status, error, oom, finished: _end, comp: _comp, ...rest } = patch;
    if (status && status !== "running" && status !== "queued") Object.assign(rest, status === "done"
      ? { adding: null, addError: null, preview: null, previewError: null, passes: [...new Set([...(version.passes || []), ...passes])] }
      : { adding: null, addError: error || status });
    S.updateVersion(effect.id, version.id, rest);
  };
  try {
    const { prompt } = await C.build(version.variant, {}, version.run, null, null, { mode: "add", from_run: version.run, passes });
    S.updateVersion(effect.id, version.id, { adding: passes, addError: null });
    state.phase = "Waiting in the queue";
    state.promptId = await C.queue(prompt, handlers(effect.id, version, state, setVersion, prompt));
    waitInQueue(effect.id, state);
  } catch (e) {
    live.delete(effect.id);
    S.updateVersion(effect.id, version.id, { adding: null, addError: e.message + (e.detail ? ` (${e.detail})` : "") });
    repaint();
    throw e;
  }
  repaint();
  return version;
}

const fileUrl = (f) => `/element-forge/media/${f.type || "output"}/${f.subfolder ? f.subfolder.replaceAll("\\", "/").split("/").map(encodeURIComponent).join("/") + "/" : ""}${encodeURIComponent(f.filename)}`;
export function filesOf(out) {
  return Object.values(out || {}).flat().filter((f) => f && typeof f === "object" && f.filename && f.type !== "input").map((f) => ({ name: f.filename, url: fileUrl(f) }));
}
const edgeOf = (outs) => outs.map((o) => o?.edge?.[0]).filter((x) => x?.sides).pop() || null;
export function edgeCut(edge, st) {
  if (!edge?.sides || !edge.frames || !st || st.placement === "frame" || st.placement === "none") return [];
  return Object.entries(edge.sides).filter(([s, v]) => !(st.placement === "ab" && (s === "left" || s === "right"))
    && v.frames >= Math.max(2, 0.1 * edge.frames) && v.max >= 0.08).map(([s]) => s);
}
function waitInQueue(effectId, state) {
  const look = async () => {
    if (live.get(effectId) !== state || state.ran) return;
    const n = await C.position(state.promptId).catch(() => -1);
    if (live.get(effectId) !== state || state.ran) return;
    if (n >= 1) { state.phase = n > 1 ? `Waiting behind ${n - 1} other job${n > 2 ? "s" : ""}` : "Waiting to start"; repaint(); }
    if (n !== 0) setTimeout(look, 3000);
  };
  look();
}
function handlers(effectId, version, state, setVersion, graph = null) {
  const files = [...(version.files || [])];
  return {
    onStart: () => { state.ran = Date.now(); state.phase = "Starting"; repaint(); },
    onNode: (node) => {
      state.ran ||= Date.now();
      const ph = phaseOf(graph?.[node]?.class_type);
      if (ph && ph !== state.phase) { state.phase = ph; state.value = 0; state.max = 0; }
      else if (!graph && !state.max) state.phase = "Working";
      repaint();
    },
    onCached: () => {},
    onProgress: (val, max) => {
      state.value = val; state.max = max;
      if (max > 1) state.step = `${state.phase.replace(/ · .*$/, "")} · step ${val} of ${max}`;
      repaint();
    },
    onOutput: (node, out) => {
      files.push(...filesOf(out));
      const comp = files.find((f) => /^comp_.*\.(mp4|webm|mov)$/i.test(f.name));
      setVersion({ files: [...files], comp: comp?.url || null, ...(edgeOf([out]) ? { edge: edgeOf([out]) } : {}) });
    },
    onDone: (r) => {
      live.delete(effectId);
      if (r.status === "done" && state.learn && state.ran) learnSpeed(state.est?.base, (Date.now() - state.ran) / 60000);
      for (const out of Object.values(r.outputs || {})) files.push(...filesOf(out).filter((f) => !files.some((x) => x.url === f.url)));
      const comp = files.find((f) => /^comp_.*\.(mp4|webm|mov)$/i.test(f.name));
      const edge = edgeOf(Object.values(r.outputs || {}));
      setVersion({ status: r.status, error: r.error || null, oom: !!r.oom, finished: Date.now(), files: [...files], comp: comp?.url || null, ...(edge ? { edge } : {}) });
      repaint();
    },
  };
}

export async function reattach() {
  for (const e of S.getShot().effects) {
    for (const v of S.allVersionsOf(e.id)) {
      if ((v.status !== "queued" && v.status !== "running") || !v.promptId) continue;
      const state = { promptId: v.promptId, started: v.started, phase: "Working", value: 0, max: 0 };
      const setVersion = (patch) => { S.updateVersion(e.id, v.id, patch); if (patch.status === "done") finished(e.id, v.id); };
      live.set(e.id, state);
      try {
        await C.follow(v.promptId, handlers(e.id, v, state, setVersion));
      } catch {
        live.delete(e.id);
      }
    }
  }
  repaint();
}

export async function stop(effectId) {
  const st = live.get(effectId);
  if (st?.promptId) return C.cancel(st.promptId);
  return "nothing";
}

const efaPaint = new Map();
export const OUTPUT = { quality: "full", upscale: "off", passes: { depth: true, normals: true, mask: true }, saveElement: false };
export const canSaveElement = (st, effect) => !!st && st.cost === "gen" && (st.variant || "app") === "app" && !inScene(effect) && !fromLibrary(effect);
export const outputOf = (shot) => ({ ...OUTPUT, ...shot?.output, passes: { ...OUTPUT.passes, ...shot?.output?.passes } });
export function efaApp(shot, e, st = styleOf(e)) {
  const o = outputOf(shot);
  return { mode: o.quality === "preview" && canPreview(st, e) ? "preview" : "full",
    skip: Object.entries(o.passes).filter(([, on]) => !on).map(([p]) => p), effect: e.id,
    ...(o.saveElement && canSaveElement(st, e) ? { save_element: true } : {}),
    ...(st?.cost === "gen" && ltxForBuild() ? { ltx: ltxForBuild() }
      : ltxForBuild()?.depth ? { ltx: { depth: ltxForBuild().depth } } : {}) };
}
export function efaValues(shot) {
  const e = shot.effects.find((x) => x.id === shot.active);
  if (!e || !shot.clip || !e.kind || !e.style || !styleDef(e.kind, e.style)) return { values: {}, values_for: null, pending: null, app: null };
  const st = styleOf(e), app = efaApp(shot, e, st);
  const v = valuesFor({ ...e, seed: { mode: "keep", value: e.seed?.value ?? 0 } }, shot, app.mode === "preview" ? 0.5 : 1);
  if (outputOf(shot).upscale === "nvidia" && st.cost === "gen") v["NVIDIA SR + HDR"] = true;
  const key = JSON.stringify([e.id, shot.clip.name, e.adv?.["Own object mask (off = click)"], e.adv?.["Guide source"], e.adv?.["Particle emitter"], e.paint]);
  let pending = null;
  if (efaPaint.has(key)) Object.assign(v, efaPaint.get(key));
  else pending = paintValues(e, shot.clip).then((pv) => { efaPaint.set(key, pv); return pv; });
  return { values: v, values_for: { effect: e.id, kind: e.kind, style: e.style, at: Date.now() }, pending, app };
}

import { h, clamp } from "./lib.js";
import { icon } from "./icons.js";
import * as S from "./state.js";
import { styleDef, directionWords, naturalDir } from "./presets.js";
import { frameBox, genSize, genWindow, usesGuide, inWindow } from "./run.js";
import { PostRenderer } from "./post.js";
import { LiveSim, blendCss } from "./livesim.js";
import { postSettings, commonSettings, weightAt, placeAt, brightAt, pivotOf, resultBox, setPlace, animated, keyHere, ensurePreview } from "./look.js";

let root, viewport, video, overlay, ctx, toolbar, zoomLabel, hint;
const paintLayer = document.createElement("canvas");
const view = { s: 1, x: 0, y: 0, fitted: true };
let spaceDown = false;
let brushR = { mask: 28, guide: 6 };
let brushAt = null;
let drag = null;
let hover = null;
let live = null;
const mediaListeners = new Set();
export const onMediaChange = (fn) => mediaListeners.add(fn);
const mediaChanged = () => { for (const fn of mediaListeners) fn(media()); };
export const media = () => (live?.ready ? live.renderer.video : video);
export const liveLayers = () => (live?.ready ? [...live.renderer.under.map((L) => ({ key: L.key, below: true, ready: L.ready })),
  ...live.renderer.over.map((L) => ({ key: L.key, below: false, ready: L.ready }))] : null);
export const playhead = () => (frozen ? resumeAt ?? 0 : media()?.currentTime || 0);
export function seekTo(t) {
  if (frozen) { resumeAt = t; return; }
  const v = media();
  if (v && v.getAttribute("src")) v.currentTime = t;
}
export const isLive = () => !!live?.ready;
export function togglePlay() {
  const v = media();
  if (!v.getAttribute("src")) return;
  if (v.paused) v.play().catch(() => {}); else v.pause();
}

const DPR = () => window.devicePixelRatio || 1;
const now = () => playhead();
const fpsOf = () => clip()?.fps || 25;
const clip = () => S.getShot().clip;
const eff = () => S.activeEffect();
const st = () => { const e = eff(); return e && styleDef(e.kind, e.style); };

const toScreen = (p) => ({ x: view.x + p.x * view.s, y: view.y + p.y * view.s });
const toClip = (sx, sy) => ({ x: (sx - view.x) / view.s, y: (sy - view.y) / view.s });
function box() {
  const r = root.getBoundingClientRect();
  const w = root.clientWidth || r.width, h = root.clientHeight || r.height;
  return { left: r.left, top: r.top, width: w, height: h, k: root.offsetWidth ? r.width / root.offsetWidth || 1 : 1 };
}
function local(e) { const r = box(); return { x: (e.clientX - r.left) / r.k, y: (e.clientY - r.top) / r.k }; }

export function fit() {
  const c = clip();
  if (!c) return;
  const r = box();
  const pad = 32;
  view.fitted = true;
  if (r.width <= pad * 2 || r.height <= pad * 2) return;
  view.s = Math.max(0.01, Math.min((r.width - pad * 2) / c.width, (r.height - pad * 2) / c.height));
  view.x = (r.width - c.width * view.s) / 2;
  view.y = (r.height - c.height * view.s) / 2;
  apply();
}
function zoomAt(sx, sy, factor) {
  const c = toClip(sx, sy);
  view.s = clamp(view.s * factor, 0.05, 16);
  view.x = sx - c.x * view.s;
  view.y = sy - c.y * view.s;
  view.fitted = false;
  apply();
}
export function presentResult() {
  fit();
  const go = () => {
    const v = media();
    if (!v?.getAttribute("src")) return false;
    try { v.currentTime = 0; } catch {  }
    v.play().catch(() => {});
    return true;
  };
  if (!go()) setTimeout(go, 800);
}
export const zoomBy = (f) => { const r = box(); zoomAt(r.width / 2, r.height / 2, f); };
export function zoom100() { const r = box(); zoomAt(r.width / 2, r.height / 2, 1 / view.s); }

function apply() {
  const c = clip();
  if (c) {
    video.style.width = `${c.width}px`;
    video.style.height = `${c.height}px`;
    video.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.s})`;
    if (live) Object.assign(live.canvas.style, { width: video.style.width, height: video.style.height, transform: video.style.transform });
    if (sim) Object.assign(sim.canvas.style, { width: video.style.width, height: video.style.height, transform: video.style.transform, filter: video.style.filter });
    if (wipeEl) Object.assign(wipeEl.style, { left: `${view.x + c.width * view.s * (live?.renderer.wipe ?? 0.5)}px`, top: `${view.y}px`, height: `${c.height * view.s}px`, bottom: "auto" });
  }
  zoomLabel.textContent = `${Math.round(view.s * 100)} %`;
  draw();
}

function tools() {
  const s = st(), step = S.ui.step;
  const list = ["hand"];
  if (step === "where" || step === "effect") list.push("point");
  const w = eff()?.where;
  if (step === "effect" && s && (s.placement === "window" || (s.placement === "point" && w?.a) || (s.placement === "ab" && w?.a && w?.b))) list.push("frame");
  if (step === "effect" && s && (s.dir === "dissolve" || (s.placement !== "ab" && (s.settings?.Particles || (s.cost === "gen" && (s.placement === "point" || s.placement === "window")))))) list.push("direction");
  if (isLive() && s?.dir !== "dissolve") list.push("move");
  if (step === "look" && isLive()) list.push("pick");
  if (paintTarget()) list.push("brush");
  return list;
}
const TOOLS = { hand: ["hand", "Hand", "H", "Move the view"], point: ["point", "Point", "P", "Click the object (Shift+click: second point)"],
  frame: ["frame", "Area", "F", "Size and place the area the effect is made in: corners and edges size it, inside moves it (drag point A inside it: origin)"], direction: ["arrow", "Direction", "D", "Drag the arrow: which way it moves (particles and the description follow it)"],
  move: ["hand", "Move effect", "M", "Move, size and turn the finished effect: inside moves, corners and edges size, just outside a corner turns (instant, no new run)"],
  pick: ["pick", "Colour", "E", "Click into the picture: the effect, its light and glow take on that colour"],
  brush: ["brush", "Brush", "B", "Paint on the first frame (Alt: erase, [ ]: size)"] };
const drawnShape = (e) => e?.adv?.["Particle emitter"] === "drawing";
export function paintTarget() {
  const e = eff(), s = st();
  if (!e) return null;
  if (S.ui.step === "where" && e.adv?.["Own object mask (off = click)"] && !e.paint?.maskHidden) return "mask";
  if (S.ui.step === "where" && drawnShape(e)) return "guide";
  if (S.ui.mode === "advanced" && S.ui.step === "effect" && s && e.adv?.["Guide source"] === "draw") return "guide";
  return null;
}
export function editBrush(show) {
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (!x?.paint) return;
    x.paint = { ...x.paint };
    if (show) delete x.paint.maskHidden; else x.paint.maskHidden = true;
  }, "paint");
  if (show) S.setUI({ tool: "brush" });
}
export function clearBrush() {
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (x?.paint) x.paint = { ...x.paint, mask: [], maskHidden: undefined };
  }, "paint");
}

let lastStep = null;
let lastTool = null;
let lastActive = null;
let dropped = null;
function renderToolbar() {
  if (S.ui.tool !== lastTool) {
    lastTool = S.ui.tool;
    if (S.ui.tool === "brush") { const v = media(); v.pause(); v.currentTime = 0; }
  }
  const list = tools();
  if (S.ui.step !== lastStep || S.getShot().active !== lastActive) S.ui.selected = null;
  lastActive = S.getShot().active;
  if (S.ui.step !== lastStep) {
    lastStep = S.ui.step;
    if (list.includes("point") && ["hand", "move", "pick"].includes(S.ui.tool)) S.ui.tool = "point";
    if (S.ui.step === "look" && st()?.dir !== "dissolve" && S.ui.tool !== "pick") S.ui.tool = "move";
  }
  if (dropped && S.ui.tool !== dropped.fallback) dropped = null;
  if (dropped && list.includes(dropped.tool)) { S.ui.tool = dropped.tool; dropped = null; }
  if (!list.includes(S.ui.tool)) {
    const fallback = list.includes("point") ? "point" : "hand";
    if (S.ui.tool === "move" || S.ui.tool === "pick") dropped = { tool: S.ui.tool, fallback };
    S.ui.tool = fallback;
  }
  toolbar.replaceChildren(...list.map((t) => {
    const [ic, name, key, tip] = TOOLS[t];
    return h("button", { class: "tool" + (S.ui.tool === t ? " on" : ""), title: `${tip} (${key})`, "aria-pressed": String(S.ui.tool === t),
      onclick: () => { S.setUI({ tool: t }); } }, icon(ic), h("span", {}, name));
  }), ...brushButtons());
  root.dataset.tool = S.ui.tool;
}

function brushButtons() {
  const e = eff();
  if (S.ui.step !== "where" || !e?.adv?.["Own object mask (off = click)"] || !e.paint?.mask?.length) return [];
  return [e.paint.maskHidden
    ? h("button", { class: "tool", title: "Show the strokes of your mask again to touch them up; track again afterwards", onclick: () => editBrush(true) }, icon("brush"), h("span", {}, "Edit brush"))
    : null,
  h("button", { class: "tool", title: "Clear the strokes of your mask", onclick: clearBrush }, icon("close"), h("span", {}, "Clear brush"))].filter(Boolean);
}

function boxOf(e) {
  const c = clip();
  if (!e || !c) return null;
  return frameBox(e, c);
}
const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const UNIT = { nw: [-1, -1], n: [0, -1], ne: [1, -1], e: [1, 0], se: [1, 1], s: [0, 1], sw: [-1, 1], w: [-1, 0] };
const HIT = 10;
const TURN_ZONE = 28;
const DRAG_MIN = 4;
const SMALL = 36;
function handlePos(b, k) { const [ux, uy] = UNIT[k]; return { x: b.x + (ux + 1) / 2 * b.w, y: b.y + (uy + 1) / 2 * b.h }; }
function frameHandles(e, b) {
  const q = e.where.a && toScreen(e.where.a);
  return HANDLES.filter((k) => (k.length === 2 || (UNIT[k][0] ? b.h : b.w) * view.s >= SMALL)
    && !(q && Math.hypot(toScreen(handlePos(b, k)).x - q.x, toScreen(handlePos(b, k)).y - q.y) < HIT));
}
function arrowTip(e) {
  const a = e.where.a || { x: clip().width / 2, y: clip().height / 2 };
  const len = 90 / view.s;
  const deg = e.dir ?? naturalDir(styleDef(e.kind, e.style));
  const r = (deg - 90) * Math.PI / 180;
  return { a, tip: { x: a.x + Math.cos(r) * len, y: a.y + Math.sin(r) * len } };
}

function resultGeom(e) {
  const c = clip(), b = resultBox(e, c), q = pivotOf(e, c), p = placeAt(e, now());
  const r = p.rot * Math.PI / 180, cs = Math.cos(r), sn = Math.sin(r);
  const sx = p.scale, sy = p.scale * p.stretch, hw = b.w / 2, hh = b.h / 2;
  const centre = { x: q.x + p.dx, y: q.y + p.dy };
  const at = (u, v) => ({ x: centre.x + cs * u * sx * hw - sn * v * sy * hh, y: centre.y + sn * u * sx * hw + cs * v * sy * hh });
  const own = (x, y) => ({ x: cs * x + sn * y, y: -sn * x + cs * y });
  return { q, p, hw, hh, sx, sy, cs, sn, centre, at, own, corners: [at(-1, -1), at(1, -1), at(1, 1), at(-1, 1)] };
}
const resultHandles = (g) => HANDLES.filter((k) => k.length === 2 || (UNIT[k][0] ? g.hh * g.sy : g.hw * g.sx) * 2 * view.s >= SMALL);
function insideQuad(q, p) {
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const a = q[i], b = q[(i + 1) % 4];
    const cr = Math.sign((b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x));
    if (cr && sign && cr !== sign) return false;
    sign ||= cr;
  }
  return true;
}
const resultActive = () => isLive() && st()?.dir !== "dissolve" && (S.ui.tool === "move" || (S.ui.step === "look" && S.ui.tool === "pick"));
const ROTATE_CURSOR = `url("data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path d="M19 12a7 7 0 1 1-2.05-4.95" fill="none" stroke="#000" stroke-width="4"/><path d="M19 12a7 7 0 1 1-2.05-4.95" fill="none" stroke="#fff" stroke-width="2"/><path d="M18 3v5h-5" fill="none" stroke="#000" stroke-width="4"/><path d="M18 3v5h-5" fill="none" stroke="#fff" stroke-width="2"/></svg>')}") 12 12, alias`;
const RESIZE = ["ew-resize", "nwse-resize", "ns-resize", "nesw-resize"];
function resizeCursor(k, deg = 0) {
  const [ux, uy] = UNIT[k], a = Math.atan2(uy, ux) * 180 / Math.PI + deg;
  return RESIZE[Math.round((((a % 180) + 180) % 180) / 45) % 4];
}

function hitTest(sx, sy) {
  const e = eff();
  if (!e || !clip()) return null;
  const near = (p, r = HIT) => { const q = toScreen(p); return Math.hypot(q.x - sx, q.y - sy) <= r; };
  const cp = toClip(sx, sy);
  if (resultActive()) {
    const g = resultGeom(e);
    for (const k of resultHandles(g)) if (near(g.at(...UNIT[k]))) return { kind: "rsize", k };
    if (insideQuad(g.corners, cp)) return { kind: "rmove" };
    for (const [i, k] of g.corners.entries()) if (near(k, TURN_ZONE)) return { kind: "turn", i };
    return null;
  }
  const s = st();
  if (S.ui.step === "effect" && tools().includes("direction") && (e.dir != null || S.ui.tool === "direction") && near(arrowTip(e).tip, 14)) return { kind: "dir" };
  for (const k of ["b", "a"]) if (e.where[k] && near(e.where[k], 13)) return { kind: "point", which: k };
  if (tools().includes("frame") && s && s.placement !== "frame") {
    const b = boxOf(e);
    if (b) {
      for (const k of frameHandles(e, b)) if (near(handlePos(b, k))) return { kind: "size", k };
      if ((S.ui.tool === "frame" || S.ui.tool === "point") && cp.x > b.x && cp.x < b.x + b.w && cp.y > b.y && cp.y < b.y + b.h) return { kind: "box" };
    }
  }
  return null;
}

function hitFor(x, y) {
  const hit = hitTest(x, y);
  if (S.ui.tool === "brush" && paintTarget()) return null;
  if (S.ui.tool === "direction" && hit?.kind !== "dir") return null;
  return hit;
}

function onDown(ev) {
  if (!clip() || drag) return;
  if (ev.target.closest?.(".toolbar, .zoombar, .view-switch, .wipe, button, input, a")) return;
  root.focus({ preventScroll: true });
  const p = local(ev);
  if (ev.button === 1 || spaceDown || (ev.button === 0 && S.ui.tool === "hand")) {
    startPan(p, ev.button === 0 && !spaceDown);
    root.setPointerCapture(ev.pointerId);
    return;
  }
  if (ev.button !== 0) return;
  const e = eff();
  const hit = hitFor(p.x, p.y);
  const cp = toClip(p.x, p.y);
  root.setPointerCapture(ev.pointerId);
  if (hit && hit.kind !== "box" && hit.kind !== "rmove") { startDrag(hit, cp); return; }
  if (S.ui.tool === "brush" && e && paintTarget()) {
    const target = paintTarget();
    S.begin();
    drag = { kind: "paint", target };
    S.change((sh) => {
      const fx = sh.effects.find((x) => x.id === sh.active);
      fx.paint ||= { mask: [], guide: [] };
      fx.paint[target].push({ pts: [[Math.round(cp.x), Math.round(cp.y)]], r: brushR[target], erase: ev.altKey });
    }, "paint");
    return;
  }
  if (S.ui.tool === "direction" && e && !hit) {
    S.begin();
    drag = { kind: "dir", start: cp };
    onMove(ev);
    return;
  }
  drag = { kind: "press", hit, x0: p.x, y0: p.y, start: cp, shift: ev.shiftKey };
}
function startPan(p, click) {
  drag = { kind: "pan", x0: p.x, y0: p.y, vx: view.x, vy: view.y, click };
  root.classList.add("panning");
}
function startDrag(hit, cp) {
  const e = eff();
  S.begin();
  if (hit.kind === "rsize" || hit.kind === "rmove" || hit.kind === "turn") {
    const g = resultGeom(e);
    drag = { ...hit, start: cp, g0: g, ang: Math.atan2(cp.y - g.centre.y, cp.x - g.centre.x), turned: 0 };
    S.setUI({ selected: "place" });
  } else {
    drag = { ...hit, start: cp, box0: boxOf(e) };
    S.setUI({ selected: hit.kind === "point" ? hit.which : hit.kind === "dir" ? "dir" : "box" });
  }
}
function clickAt(pr) {
  const e = eff(), cp = pr.start;
  if (S.ui.tool === "point" && inClip(cp)) { setPoint(cp, pr.shift || needsB() ? "b" : "a"); return; }
  if (S.ui.tool === "pick" && e && isLive() && inClip(cp)) {
    const col = pickColour(cp);
    if (col) S.change((sh) => { sh.effects.find((x) => x.id === sh.active).look.tint = col; }, "tint");
    return;
  }
  if (S.ui.compare && live?.ready) { live.renderer.setWipe(clamp((pr.x0 - view.x) / (clip().width * view.s), 0, 1)); apply(); return; }
  S.setUI({ selected: pr.hit ? (pr.hit.kind === "rmove" ? "place" : "box") : null });
}
function setPoint(cp, which) {
  const pt = { x: Math.round(cp.x), y: Math.round(cp.y) };
  if (which === "a") withGround(pt);
  S.change((s) => {
    const fx = s.effects.find((x) => x.id === s.active);
    if (!fx) { s.pendingWhere = { ...(s.pendingWhere || { a: null, b: null, word: "" }), [which]: pt }; return; }
    if (which === "a" && !fx.where.a) fx.box = null;
    fx.where[which] = pt;
  }, "point");
  S.setUI({ selected: which });
}
function withGround(pt) {
  let hex = null;
  try {
    if (isLive()) hex = pickColour(pt);
    else if (video?.videoWidth) {
      const c = clip();
      hex = meanColour(video, Math.round(pt.x * video.videoWidth / c.width), Math.round(pt.y * video.videoHeight / c.height));
    }
  } catch { return pt; }
  if (!hex) return pt;
  const n = parseInt(hex.slice(1), 16);
  pt.ground = (0.2126 * (n >> 16) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255 > 0.45 ? "light" : "dark";
  return pt;
}
function groundAfterLoad() {
  const g = S.getShot().effects.map((e) => (e.where.a && !e.where.a.ground ? withGround({ ...e.where.a }).ground : null));
  if (g.some(Boolean)) S.amend((sh) => sh.effects.forEach((e, i) => { if (g[i] && e.where.a) e.where.a.ground = g[i]; }));
}
function pickColour(cp) {
  const r = live.renderer, cv = live.canvas, c = clip();
  const prev = r.view;
  r.view = "plate";
  r.render();
  const hex = meanColour(cv, Math.round(cp.x * cv.width / c.width), Math.round(cp.y * cv.height / c.height));
  r.view = prev;
  r.render();
  return hex;
}
function meanColour(src, x, y) {
  const t = document.createElement("canvas");
  t.width = t.height = 5;
  const g = t.getContext("2d", { willReadFrequently: true });
  g.drawImage(src, x - 2, y - 2, 5, 5, 0, 0, 5, 5);
  const d = g.getImageData(0, 0, 5, 5).data;
  const sum = [0, 0, 0];
  for (let i = 0; i < d.length; i += 4) { sum[0] += d[i]; sum[1] += d[i + 1]; sum[2] += d[i + 2]; }
  return "#" + sum.map((v) => Math.round(v / 25).toString(16).padStart(2, "0")).join("");
}
function snapGuides(cx, cy, ev, extraX = [], extraY = [], edges = null, lock = null) {
  if (ev.altKey || ev.ctrlKey || ev.metaKey) return { dx: 0, dy: 0, lines: [] };
  const c = clip(), tol = 8 / view.s;
  const pick = (v, targets) => { let best = null; for (const t of targets) if (Math.abs(t - v) < tol && (best == null || Math.abs(t - v) < Math.abs(best - v))) best = t; return best; };
  let dx = 0, dy = 0;
  const lines = [];
  const sx = lock === "x" ? null : pick(cx, [c.width / 2, ...extraX]), sy = lock === "y" ? null : pick(cy, [c.height / 2, ...extraY]);
  if (sx != null) { dx = sx - cx; lines.push({ x: sx }); }
  if (sy != null) { dy = sy - cy; lines.push({ y: sy }); }
  if (edges && sx == null && lock !== "x") {
    for (const [v, t] of [[edges.x0, 0], [edges.x1, c.width]]) if (Math.abs(v - t) < tol) { dx = t - v; lines.push({ x: t }); break; }
  }
  if (edges && sy == null && lock !== "y") {
    for (const [v, t] of [[edges.y0, 0], [edges.y1, c.height]]) if (Math.abs(v - t) < tol) { dy = t - v; lines.push({ y: t }); break; }
  }
  return { dx, dy, lines };
}
const along = (ev, mx, my) => (!ev.shiftKey ? [mx, my, null] : Math.abs(mx) >= Math.abs(my) ? [mx, 0, "y"] : [0, my, "x"]);
const needsB = () => { const e = eff(), s = st(); return !!(e && s && S.ui.step === "effect" && s.placement === "ab" && e.where.a && !e.where.b); };
const inClip = (p) => p.x >= 0 && p.y >= 0 && p.x <= clip().width && p.y <= clip().height;

function onMove(ev) {
  const p = local(ev);
  if (S.ui.tool === "brush") { brushAt = toClip(p.x, p.y); if (!drag) draw(); }
  if (drag && ev.buttons === 0 && ev.pointerType === "mouse") { onCancel(ev); return; }
  if (!drag) {
    hover = clip() ? hitFor(p.x, p.y) : null;
    const ht = hoverHint(hover);
    if (ht !== hoverText) { hoverText = ht; autoHint(); }
    root.style.cursor = cursorFor(hover);
    return;
  }
  if (drag.kind === "press") {
    if (Math.hypot(p.x - drag.x0, p.y - drag.y0) < DRAG_MIN) return;
    const pr = drag;
    if (pr.hit) startDrag(pr.hit, pr.start);
    else if (nav.left === "panning") { startPan({ x: pr.x0, y: pr.y0 }, false); root.style.cursor = "grabbing"; }
    else drag = { kind: "none" };
  }
  if (drag.kind === "none") return;
  if (drag.kind === "pan") {
    if (spaceDown) pannedWithSpace = true;
    view.x = drag.vx + p.x - drag.x0;
    view.y = drag.vy + p.y - drag.y0;
    view.fitted = false;
    apply();
    return;
  }
  let cp = toClip(p.x, p.y);
  const c = clip();
  S.change((s) => {
    const e = s.effects.find((x) => x.id === s.active);
    if (!e) return;
    if (drag.kind === "point") {
      const pt = { x: Math.round(clamp(cp.x, 0, c.width)), y: Math.round(clamp(cp.y, 0, c.height)) };
      e.where[drag.which] = pt;
    } else if (drag.kind === "box") {
      const b = drag.box0;
      const [mx0, my0, lock] = along(ev, cp.x - drag.start.x, cp.y - drag.start.y);
      const sn = snapGuides(b.x + mx0 + b.w / 2, b.y + my0 + b.h / 2, ev, [], [], { x0: b.x + mx0, x1: b.x + mx0 + b.w, y0: b.y + my0, y1: b.y + my0 + b.h }, lock);
      const mx = mx0 + sn.dx, my = my0 + sn.dy;
      drag.guides = sn.lines;
      e.box = { x: b.x + mx, y: b.y + my, w: b.w, h: b.h };
    } else if (drag.kind === "size") {
      e.box = resizeBox(drag.box0, drag.k, cp, ev.altKey, ev.shiftKey);
    } else if (drag.kind === "paint") {
      const st0 = e.paint[drag.target].at(-1);
      const last = st0.pts.at(-1);
      if (Math.hypot(cp.x - last[0], cp.y - last[1]) >= Math.max(1.5, st0.r * 0.25)) st0.pts.push([Math.round(cp.x), Math.round(cp.y)]);
    } else if (drag.kind === "rmove") {
      const g = drag.g0;
      const [mx, my, lock] = along(ev, cp.x - drag.start.x, cp.y - drag.start.y);
      const sn = snapGuides(g.centre.x + mx, g.centre.y + my, ev, [g.q.x], [g.q.y], null, lock);
      drag.guides = sn.lines;
      setPlace(e, { dx: Math.round(g.p.dx + mx + sn.dx), dy: Math.round(g.p.dy + my + sn.dy) }, now(), fpsOf());
    } else if (drag.kind === "rsize") {
      setPlace(e, resizeResult(drag.g0, drag.k, cp, ev.altKey, ev.shiftKey), now(), fpsOf());
    } else if (drag.kind === "turn") {
      const c0 = drag.g0.centre, ang = Math.atan2(cp.y - c0.y, cp.x - c0.x);
      let d = ang - drag.ang;
      if (d > Math.PI) d -= 2 * Math.PI;
      if (d < -Math.PI) d += 2 * Math.PI;
      drag.turned += d;
      drag.ang = ang;
      let deg = drag.g0.p.rot + drag.turned * 180 / Math.PI;
      if (ev.shiftKey) deg = Math.round(deg / 15) * 15;
      setPlace(e, { rot: +deg.toFixed(1) }, now(), fpsOf());
    } else if (drag.kind === "dir") {
      const a = e.where.a || { x: c.width / 2, y: c.height / 2 };
      let deg = Math.atan2(cp.y - a.y, cp.x - a.x) * 180 / Math.PI + 90;
      if (ev.shiftKey) deg = Math.round(deg / 15) * 15;
      e.dir = Math.round(((deg % 360) + 360) % 360);
    }
  }, "drag");
}
function cursorFor(hv) {
  if (hv) {
    if (hv.kind === "size") return resizeCursor(hv.k);
    if (hv.kind === "rsize") return resizeCursor(hv.k, placeAt(eff(), now()).rot);
    if (hv.kind === "box" || hv.kind === "rmove") return "move";
    if (hv.kind === "turn") return ROTATE_CURSOR;
    return "grab";
  }
  if (spaceDown || S.ui.tool === "hand") return "grab";
  return S.ui.tool === "point" || S.ui.tool === "pick" ? "crosshair" : S.ui.tool === "brush" ? "none" : "default";
}

let hoverText = "";
function hoverHint(hv) {
  if (!hv) return "";
  if (hv.kind === "size") return "Drag: size · Shift: keep its shape · Alt: from the centre";
  if (hv.kind === "box") return S.ui.tool === "point" ? "Drag: move the area · Click: set the point here" : "Drag: move · Shift: one direction · Ctrl: no snapping";
  if (hv.kind === "point") return hv.which === "b" ? "Drag: move point B · Delete removes it" : "Drag: move the point";
  if (hv.kind === "dir") return "Drag: direction · Shift: 15° steps";
  if (hv.kind === "rsize") return "Drag: size · Shift: keep its shape · Alt: from the centre";
  if (hv.kind === "rmove") return S.ui.tool === "pick" ? "Drag: move the effect · Click: take the colour" : "Drag: move · Shift: one direction · Ctrl: no snapping";
  if (hv.kind === "turn") return "Drag: turn · Shift: 15° steps";
  return "";
}
function resizeBox(b, k, cp, centre, keep) {
  const min = 16;
  const [hx, hy] = UNIT[k];
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  const fx = hx < 0 ? b.x + b.w : b.x, fy = hy < 0 ? b.y + b.h : b.y;
  let w = !hx ? b.w : centre ? 2 * Math.abs(cp.x - cx) : Math.abs(cp.x - fx);
  let hh = !hy ? b.h : centre ? 2 * Math.abs(cp.y - cy) : Math.abs(cp.y - fy);
  if (keep) {
    const r = b.w / b.h;
    if (hx && hy) { if (w / r > hh) hh = w / r; else w = hh * r; }
    else if (hx) hh = w / r;
    else w = hh * r;
  }
  w = Math.max(min, w); hh = Math.max(min, hh);
  const side = (moved, c0, f, p, lo, n) => {
    if (centre || (!moved && keep)) return c0 - n / 2;
    if (!moved) return lo;
    return p >= f ? f : f - n;
  };
  return { x: side(!!hx, cx, fx, cp.x, b.x, w), y: side(!!hy, cy, fy, cp.y, b.y, hh), w, h: hh };
}
function resizeResult(g, k, cp, centre, keep) {
  const [ux, uy] = UNIT[k];
  const fu = centre ? 0 : -ux, fv = centre ? 0 : -uy;
  const F = g.at(fu, fv);
  const d = g.own(cp.x - F.x, cp.y - F.y);
  const spanX = (ux - fu) * g.hw, spanY = (uy - fv) * g.hh;
  let sx = ux ? d.x / spanX : g.sx, sy = uy ? d.y / spanY : g.sy;
  if (keep) {
    const vx = g.sx * spanX, vy = g.sy * spanY;
    const f = ux && uy ? (d.x * vx + d.y * vy) / (vx * vx + vy * vy) : ux ? sx / g.sx : sy / g.sy;
    sx = g.sx * f; sy = g.sy * f;
  }
  sx = clamp(sx, 0.05, 10); sy = clamp(sy, 0.05, 10);
  const ox = fu * sx * g.hw, oy = fv * sy * g.hh;
  const cx = F.x - (g.cs * ox - g.sn * oy), cy = F.y - (g.sn * ox + g.cs * oy);
  return { scale: +sx.toFixed(3), stretch: +(sy / sx).toFixed(3), dx: Math.round(cx - g.q.x), dy: Math.round(cy - g.q.y) };
}

function onCancel(ev) {
  if (drag?.kind === "press") { drag = null; return; }
  if (drag) onUp(ev);
}
function onUp(ev) {
  if (!drag) return;
  const was = drag;
  drag = null;
  root.classList.remove("panning");
  try { root.releasePointerCapture(ev.pointerId); } catch {  }
  if (was.kind === "press") { clickAt(was); return; }
  const e = eff();
  if (was.kind === "point" && was.which === "a" && e?.where.a) {
    const pt = withGround({ ...e.where.a });
    S.change((s) => { s.effects.find((x) => x.id === s.active).where.a = pt; }, "point");
  }
  if (was.kind !== "pan" && was.kind !== "none") S.end();
  if (was.click && S.ui.compare && live?.ready && ev.clientX != null) {
    const p = local(ev);
    if (Math.hypot(p.x - was.x0, p.y - was.y0) < DRAG_MIN) { live.renderer.setWipe(clamp((p.x - view.x) / (clip().width * view.s), 0, 1)); apply(); }
  }
  autoHint();
  draw();
}

const nav = { wheel: "zoom", left: "panning", speed: 1.1 };
export async function loadNav() {
  try {
    const s = await (await fetch("/settings")).json();
    nav.wheel = s["Comfy.Canvas.MouseWheelScroll"] === "panning" ? "panning" : "zoom";
    nav.left = s["Comfy.Canvas.LeftMouseClickBehavior"] === "select" ? "select" : "panning";
    nav.speed = clamp(+s["Comfy.Graph.ZoomSpeed"] || 1.1, 1.01, 2.5);
  } catch {  }
}
export const wheelZooms = () => nav.wheel === "zoom";
export const dragPans = () => nav.left === "panning";

function onWheel(ev) {
  if (!clip()) return;
  ev.preventDefault();
  const p = local(ev);
  const unit = ev.deltaMode === 1 ? 33 : ev.deltaMode === 2 ? 800 : 1;
  const dx = ev.deltaX * unit, dy = ev.deltaY * unit;
  if (((ev.ctrlKey || ev.metaKey) && !ev.altKey && !ev.shiftKey) || nav.wheel === "zoom") zoomAt(p.x, p.y, Math.pow(nav.speed, -clamp(dy, -300, 300) / 100));
  else { if (ev.shiftKey && !dx) view.x -= dy; else { view.x -= dx; view.y -= dy; } view.fitted = false; apply(); }
}

function onKey(ev) {
  if (ev.key === " ") { ev.preventDefault(); if (!ev.repeat) { spaceDown = true; spaceAt = performance.now(); root.style.cursor = "grab"; } }
  if (ev.key === "Escape" && drag) { const was = drag; drag = null; root.classList.remove("panning"); if (was.kind !== "pan" && was.kind !== "press" && was.kind !== "none") S.cancelGesture(); ev.preventDefault(); return; }
  if (ev.key === "Enter" && drag) { if (drag.kind !== "press") onUp(ev); return; }
  const k = ev.key.toLowerCase();
  if (!ev.ctrlKey && !ev.metaKey && !ev.altKey) {
    const map = { h: "hand", p: "point", f: "frame", d: "direction", m: "move", b: "brush", e: "pick" };
    if ((ev.key === "[" || ev.key === "]") && paintTarget()) {
      const t = paintTarget();
      brushR[t] = Math.max(2, Math.min(300, Math.round(brushR[t] * (ev.key === "]" ? 1.25 : 0.8))));
      draw(); ev.preventDefault(); return;
    }
    if (map[k] && tools().includes(map[k])) { S.setUI({ tool: map[k] }); ev.preventDefault(); return; }
    if (ev.key === "." || ev.key === "!" || (ev.shiftKey && ev.code === "Digit1")) { fit(); ev.preventDefault(); return; }
    if ((ev.key === "+" || ev.key === "=" || ev.key === "-") && selection()) { sizeSelected(ev.key === "-" ? 1 / 1.1 : 1.1); ev.preventDefault(); return; }
  }
  if (ev.altKey && !ev.ctrlKey && !ev.metaKey && (ev.key === "=" || ev.key === "+" || ev.key === "-")) {
    zoomBy(ev.key === "-" ? 1 / nav.speed : nav.speed); ev.preventDefault(); return;
  }
  if (ev.ctrlKey || ev.metaKey) return;
  if (ev.key.startsWith("Arrow") && selection()) { nudge(ev); ev.preventDefault(); }
  const sel = selection();
  if ((ev.key === "Delete" || ev.key === "Backspace") && sel && (sel !== "place" || S.ui.selected === "place")) { resetSelected(sel); ev.preventDefault(); }
}
let spaceAt = 0;
export const spaceWasTap = () => performance.now() - spaceAt < 220;
let pannedWithSpace = false;
function onKeyUp(ev) {
  if (ev.key !== " ") return;
  spaceDown = false;
  root.style.cursor = "";
  if (spaceWasTap() && !pannedWithSpace) togglePlay();
  pannedWithSpace = false;
}

function selection() {
  if (resultActive()) return "place";
  const sel = S.ui.selected, e = eff(), t = tools();
  if (sel === "box") return t.includes("frame") && e && boxOf(e) ? sel : null;
  if (sel === "dir") return t.includes("direction") ? sel : null;
  if (sel === "a" || sel === "b") return t.includes("point") && e?.where[sel] ? sel : null;
  return null;
}
function nudge(ev) {
  const step = (ev.shiftKey ? 10 : 1) / Math.max(view.s, 0.0001);
  const dx = ev.key === "ArrowLeft" ? -step : ev.key === "ArrowRight" ? step : 0;
  const dy = ev.key === "ArrowUp" ? -step : ev.key === "ArrowDown" ? step : 0;
  const sel = selection();
  S.change((s) => {
    const e = s.effects.find((x) => x.id === s.active);
    if (!e) return;
    if (sel === "a" || sel === "b") {
      const p = e.where[sel];
      if (!p) return;
      e.where[sel] = { x: Math.round(p.x + dx), y: Math.round(p.y + dy) };
    }
    if (sel === "box" && styleDef(e.kind, e.style)?.placement !== "ab") {
      const b = boxOf(e);
      if (b) e.box = { ...b, x: b.x + dx, y: b.y + dy };
    }
    if (sel === "place") { const p = placeAt(e, now()); setPlace(e, { dx: Math.round(p.dx + dx), dy: Math.round(p.dy + dy) }, now(), fpsOf()); }
    if (sel === "dir") e.dir = Math.round((((e.dir ?? naturalDir(styleDef(e.kind, e.style))) + (dx || dy) * view.s * (ev.shiftKey ? 1.5 : 1)) % 360 + 360) % 360);
  }, "nudge");
}
function sizeSelected(f) {
  const sel = selection();
  S.change((s) => {
    const e = s.effects.find((x) => x.id === s.active);
    if (!e) return;
    if (sel === "box") {
      const b = boxOf(e);
      if (!b) return;
      const a = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
      f = Math.max(f, 16 / Math.min(b.w, b.h));
      e.box = { x: a.x - (a.x - b.x) * f, y: a.y - (a.y - b.y) * f, w: b.w * f, h: b.h * f };
    }
    if (sel === "place") { const p = placeAt(e, now()); setPlace(e, { scale: +clamp(p.scale * f, 0.05, 10).toFixed(3) }, now(), fpsOf()); }
  }, "size");
}
export function resetSelected(which = selection()) {
  S.change((s) => {
    const e = s.effects.find((x) => x.id === s.active);
    if (!e) return;
    if (which === "b") e.where.b = null;
    if (which === "box") e.box = null;
    if (which === "dir" && styleDef(e.kind, e.style)?.dir !== "dissolve") e.dir = null;
    if (which === "place") { e.place = { dx: 0, dy: 0, scale: 1, stretch: 1, rot: 0 }; if (e.keys) e.keys.place = []; }
  }, `reset-${which}`);
  if (which === "b" || which === "box" || which === "dir") S.setUI({ selected: null });
}

const tintCache = new Map();
function tinted(url) {
  const have = tintCache.get(url);
  if (have) return have.ready ? have.canvas : null;
  const rec = { ready: false, canvas: document.createElement("canvas") };
  tintCache.set(url, rec);
  const img = new Image();
  img.onload = () => {
    const cv = rec.canvas;
    cv.width = img.naturalWidth; cv.height = img.naturalHeight;
    const g = cv.getContext("2d");
    g.drawImage(img, 0, 0);
    const px = g.getImageData(0, 0, cv.width, cv.height);
    for (let i = 0; i < px.data.length; i += 4) {
      const a = px.data[i];
      px.data[i] = 106; px.data[i + 1] = 168; px.data[i + 2] = 255; px.data[i + 3] = a;
    }
    g.putImageData(px, 0, 0);
    rec.ready = true;
    draw();
  };
  img.src = url;
  return null;
}

function draw() {
  const r = box();
  const d = DPR() * r.k;
  if (overlay.width !== Math.round(r.width * d) || overlay.height !== Math.round(r.height * d)) {
    overlay.width = Math.round(r.width * d);
    overlay.height = Math.round(r.height * d);
  }
  ctx.setTransform(d, 0, 0, d, 0, 0);
  ctx.clearRect(0, 0, r.width, r.height);
  const c = clip();
  if (!c) return;
  const e = eff();
  const shot = S.getShot();
  const where = e ? e.where : shot.pendingWhere || { a: null, b: null };
  const s = st();
  const sel = S.ui.selected;
  const line = (w, col) => { ctx.lineWidth = w; ctx.strokeStyle = col; };
  if (e && s && S.ui.step === "effect" && (s.placement === "window" || s.placement === "point" || (s.placement === "ab" && e.where.b))) {
    const b = boxOf(e);
    if (b) {
      const p0 = toScreen(b), p1 = toScreen({ x: b.x + b.w, y: b.y + b.h });
      ctx.save();
      ctx.setLineDash(e.box ? [] : [6, 5]);
      line(3, "rgba(0,0,0,.55)"); ctx.strokeRect(p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
      line(1.5, sel === "box" ? "#6aa8ff" : "#f5c84b"); ctx.strokeRect(p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
      ctx.restore();
      const adv = S.ui.mode === "advanced";
      let gw, gh;
      if (s.placement === "point" && !inWindow(s, e)) [gw, gh] = genSize(s, b.w / b.h, usesGuide(s, e));
      else {
        const w = genWindow(s, b, usesGuide(s, e));
        [gw, gh] = [w.gw, w.gh];
        if (adv && (Math.abs(w.w - b.w) > 2 || Math.abs(w.h - b.h) > 2)) {
          const q0 = toScreen(w), q1 = toScreen({ x: w.x + w.w, y: w.y + w.h });
          ctx.save(); ctx.setLineDash([2, 4]); line(1, "rgba(245,200,75,.6)"); ctx.strokeRect(q0.x, q0.y, q1.x - q0.x, q1.y - q0.y); ctx.restore();
        }
      }
      if (tools().includes("frame") && !resultActive()) {
        for (const k of frameHandles(e, b)) handle(toScreen(handlePos(b, k)), (hover?.kind === "size" && hover.k === k) || (drag?.kind === "size" && drag.k === k));
      }
      const sizing = drag?.kind === "size" || drag?.kind === "box";
      label(p0.x + 4, p0.y - 8, `Area${sizing && adv ? ` · ${Math.round(b.w)} × ${Math.round(b.h)} px` : e.box ? "" : " · automatic"}${adv ? ` · ${gw} × ${gh} generated` : ""}`);
    }
  }
  const fm = S.ui.firstMask;
  if (e && fm && fm.clip === c.name && S.ui.step === "where" && !S.ui.media && media().currentTime * (c.fps || 25) < 0.5) {
    const p0 = toScreen({ x: 0, y: 0 }), p1 = toScreen({ x: c.width, y: c.height });
    for (const url of [fm.a, fm.b]) {
      const m = url && tinted(url);
      if (m) { ctx.save(); ctx.globalAlpha = 0.5; ctx.drawImage(m, p0.x, p0.y, p1.x - p0.x, p1.y - p0.y); ctx.restore(); }
    }
  }
  if (e?.paint && (S.ui.step === "where" || S.ui.step === "effect")) {
    for (const target of ["mask", "guide"]) {
      const strokes = e.paint[target] || [];
      if (!strokes.length || (target === "mask" && (S.ui.step !== "where" || e.paint.maskHidden))
        || (target === "guide" && !(S.ui.step === "effect" && S.ui.mode === "advanced") && !(S.ui.step === "where" && drawnShape(e)))) continue;
      paintLayer.width = overlay.width; paintLayer.height = overlay.height;
      const pc = paintLayer.getContext("2d");
      pc.setTransform(d, 0, 0, d, 0, 0);
      pc.lineCap = pc.lineJoin = "round";
      for (const s0 of strokes) {
        pc.globalCompositeOperation = s0.erase ? "destination-out" : "source-over";
        pc.strokeStyle = pc.fillStyle = target === "mask" ? "#6aa8ff" : "#f5c84b";
        pc.lineWidth = s0.r * 2 * view.s;
        pc.beginPath();
        const q0 = toScreen({ x: s0.pts[0][0], y: s0.pts[0][1] });
        pc.moveTo(q0.x, q0.y);
        if (s0.pts.length === 1) { pc.arc(q0.x, q0.y, s0.r * view.s, 0, Math.PI * 2); pc.fill(); continue; }
        for (const [x, y] of s0.pts.slice(1)) { const q = toScreen({ x, y }); pc.lineTo(q.x, q.y); }
        pc.stroke();
      }
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = target === "mask" ? 0.45 : 0.9; ctx.drawImage(paintLayer, 0, 0); ctx.restore();
    }
  }
  if (S.ui.tool === "brush" && brushAt && paintTarget()) {
    const q = toScreen(brushAt);
    ctx.beginPath(); ctx.arc(q.x, q.y, brushR[paintTarget()] * view.s, 0, Math.PI * 2);
    line(3, "rgba(0,0,0,.5)"); ctx.stroke(); line(1.5, "#fff"); ctx.stroke();
  }
  if (e && s && S.ui.step === "effect" && tools().includes("direction") && (e.dir != null || S.ui.tool === "direction")) {
    const { a, tip } = arrowTip(e);
    const pa = toScreen(a), pt = toScreen(tip);
    line(4, "rgba(0,0,0,.5)"); arrow(pa, pt);
    line(2, sel === "dir" ? "#6aa8ff" : "#f5c84b"); arrow(pa, pt);
    handle(pt, hover?.kind === "dir" || drag?.kind === "dir", true);
    if (e.dir != null) label(pt.x + 10, pt.y - 10, s.dir === "dissolve" ? `crumbles ${directionWords(e.dir)}` : `moves ${directionWords(e.dir)}`);
  }
  if (e && shapeOn(e)) {
    const m = S.ui.liveMotion, sh = m.data.shape;
    const i = clamp(Math.round(playhead() * sh.fps), 0, sh.n - 1), r = sh.rects[i];
    if (r) {
      const q0 = toScreen({ x: r[0], y: r[1] }), q1 = toScreen({ x: r[0] + r[2], y: r[1] + r[3] });
      ctx.save();
      ctx.globalAlpha = 0.85;
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(shapeFrame(m, i), q0.x, q0.y, q1.x - q0.x, q1.y - q0.y);
      ctx.restore();
      ctx.save(); ctx.setLineDash([3, 4]); line(1, "rgba(190,140,255,.7)"); ctx.strokeRect(q0.x, q0.y, q1.x - q0.x, q1.y - q0.y); ctx.restore();
    }
  }
  if (drag?.guides?.length) {
    const c0 = toScreen({ x: 0, y: 0 }), c1 = toScreen({ x: clip().width, y: clip().height });
    ctx.save();
    ctx.setLineDash([4, 4]);
    line(1, "#ff4fd8");
    for (const g of drag.guides) {
      ctx.beginPath();
      if (g.x != null) { const x = toScreen({ x: g.x, y: 0 }).x; ctx.moveTo(x, c0.y); ctx.lineTo(x, c1.y); }
      else { const y = toScreen({ x: 0, y: g.y }).y; ctx.moveTo(c0.x, y); ctx.lineTo(c1.x, y); }
      ctx.stroke();
    }
    ctx.restore();
  }
  if (e && resultActive()) {
    const q = resultGeom(e);
    const pts = q.corners.map(toScreen);
    ctx.save();
    ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.closePath();
    ctx.setLineDash([6, 5]);
    line(3, "rgba(0,0,0,.55)"); ctx.stroke();
    line(1.5, sel === "place" ? "#6aa8ff" : "#f5c84b"); ctx.stroke();
    ctx.restore();
    for (const k of resultHandles(q)) handle(toScreen(q.at(...UNIT[k])), (hover?.kind === "rsize" && hover.k === k) || (drag?.kind === "rsize" && drag.k === k));
    const c0 = toScreen(q.centre);
    ctx.beginPath(); ctx.moveTo(c0.x - 6, c0.y); ctx.lineTo(c0.x + 6, c0.y); ctx.moveTo(c0.x, c0.y - 6); ctx.lineTo(c0.x, c0.y + 6);
    line(3, "rgba(0,0,0,.5)"); ctx.stroke(); line(1.5, "#fff"); ctx.stroke();
    const top = pts.reduce((a, b) => (b.y < a.y ? b : a));
    const keyed = animated(e, "place");
    label(top.x + 6, top.y - 10, keyed ? (keyHere(e, "place", now(), fpsOf()) ? "◆ key here" : "◇ a change adds a key here")
      : `${Math.abs(q.p.stretch - 1) < 0.005 ? `${Math.round(q.p.scale * 100)} %` : `${Math.round(q.sx * 100)} × ${Math.round(q.sy * 100)} %`}${q.p.rot ? ` · ${Math.round(q.p.rot)}°` : ""}`);
  }
  if (S.ui.step !== "look" && S.ui.step !== "export") for (const k of ["a", "b"]) {
    const p = where[k];
    if (!p) continue;
    const q = toScreen(p);
    ctx.beginPath(); ctx.arc(q.x, q.y, 9, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(0,0,0,.45)"; ctx.fill();
    line(2.5, sel === k ? "#6aa8ff" : "#f5c84b"); ctx.stroke();
    ctx.beginPath(); ctx.arc(q.x, q.y, 2.5, 0, Math.PI * 2); ctx.fillStyle = "#fff"; ctx.fill();
    label(q.x + 12, q.y - 10, k.toUpperCase());
  }
  if (e && motionOn(e)) {
    const { emit, tip, fps } = S.ui.liveMotion.data;
    const i = clamp(Math.round(playhead() * fps), 0, emit.length - 1);
    const path = (pts) => { ctx.beginPath(); pts.forEach(([x, y], j) => { const q = toScreen({ x, y }); if (j) ctx.lineTo(q.x, q.y); else ctx.moveTo(q.x, q.y); }); };
    ctx.save();
    path(emit); line(1.5, "rgba(245,200,75,.5)"); ctx.stroke();
    path(tip.slice(Math.max(0, i - 15), i + 1)); line(2, "rgba(106,168,255,.75)"); ctx.stroke();
    const pe = toScreen({ x: emit[i][0], y: emit[i][1] }), pq = toScreen({ x: tip[i][0], y: tip[i][1] });
    ctx.beginPath(); ctx.moveTo(pe.x, pe.y); ctx.lineTo(pq.x, pq.y);
    line(5, "rgba(0,0,0,.5)"); ctx.stroke(); line(2.5, "#6aa8ff"); ctx.stroke();
    ctx.beginPath(); ctx.arc(pq.x, pq.y, 4, 0, Math.PI * 2); ctx.fillStyle = "#6aa8ff"; ctx.fill();
    ctx.restore();
  }
}
function handle(p, active, round = false) {
  ctx.beginPath();
  if (round) ctx.arc(p.x, p.y, 6, 0, Math.PI * 2); else ctx.rect(p.x - 5, p.y - 5, 10, 10);
  ctx.fillStyle = active ? "#6aa8ff" : "#fff"; ctx.fill();
  ctx.lineWidth = 1.5; ctx.strokeStyle = "rgba(0,0,0,.7)"; ctx.stroke();
}
function arrow(a, b) {
  const ang = Math.atan2(b.y - a.y, b.x - a.x);
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
  ctx.moveTo(b.x, b.y); ctx.lineTo(b.x - 12 * Math.cos(ang - 0.45), b.y - 12 * Math.sin(ang - 0.45));
  ctx.moveTo(b.x, b.y); ctx.lineTo(b.x - 12 * Math.cos(ang + 0.45), b.y - 12 * Math.sin(ang + 0.45));
  ctx.stroke();
}
function label(x, y, t) {
  ctx.font = "600 11px Inter, Segoe UI, sans-serif";
  const w = ctx.measureText(t).width + 10;
  ctx.fillStyle = "rgba(0,0,0,.65)"; ctx.beginPath(); ctx.roundRect(x - 2, y - 11, w, 17, 4); ctx.fill();
  ctx.fillStyle = "#fff"; ctx.fillText(t, x + 3, y + 1);
}

let currentClip = null;
const plateUrl = (c) => (c.still ? `/element-forge/api/still-video?name=${encodeURIComponent(c.name)}&seconds=${c.seconds}`
  : `/element-forge/media/input/${encodeURIComponent(c.name)}`);
const isPlate = (u) => !!u && (u.startsWith("/element-forge/media/input/") || u.startsWith("/element-forge/api/still-video"));
function dropLive() {
  if (!live) return;
  live.renderer.destroy();
  live.canvas.remove();
  live = null;
  video.hidden = false;
  if (wipeEl) wipeEl.hidden = true;
  mediaChanged();
}
function ensureLive(url) {
  if (live?.url === url) return;
  dropLive();
  const canvas = h("canvas", { class: "plate live", "aria-label": "Result, live" });
  let renderer;
  try { renderer = new PostRenderer(canvas); } catch (err) {
    document.dispatchEvent(new CustomEvent("ef:live-error", { detail: { message: err.message } }));
    S.ui.media = { ...S.ui.media, live: null };
    loadClip();
    return;
  }
  live = { renderer, canvas, url, ready: false };
  const t = pendingResume ?? video.currentTime;
  pendingResume = null;
  renderer.load(url).then(() => {
    if (live?.renderer !== renderer) return;
    live.ready = true;
    viewport.append(canvas);
    video.pause();
    video.hidden = true;
    renderer.video.loop = video.loop;
    renderer.video.currentTime = Math.min(t, renderer.video.duration || t);
    followPlayback(renderer.video);
    applyLook();
    apply();
    mediaChanged();
    render();
  }).catch((err) => {
    if (live?.renderer !== renderer) return;
    liveFailed.add(url);
    dropLive();
    S.ui.media = S.ui.media ? { ...S.ui.media, live: null } : null;
    loadClip();
    document.dispatchEvent(new CustomEvent("ef:live-error", { detail: { message: err.message } }));
  });
}
const liveFailed = new Set();
function applyLook() {
  if (!live?.ready) return;
  const e = eff();
  if (!e) return;
  const r = live.renderer;
  const fps = r.man?.fps || clip()?.fps || 25;
  r.adjust = adjustOf(e, fps);
  const vs = S.versionsOf(e.id);
  const other = typeof S.ui.compare === "string" ? vs.find((x) => x.id === S.ui.compare && x.status === "done") : null;
  if (other && !other.preview && !other.previewError) ensurePreview(e.id, other);
  r.setCompare(other?.preview || null);
  r.view = other ? "versions" : S.ui.compare === true ? "before" : S.ui.pass || "comp";
  if (wipeTags) {
    const shown = S.shownOf(e.id);
    wipeTags[0].textContent = other ? (other.preview ? `Version ${vs.indexOf(other) + 1}` : `Version ${vs.indexOf(other) + 1} · preparing…`) : "Before";
    wipeTags[1].textContent = other ? `Version ${vs.indexOf(shown) + 1} · shown` : "After";
  }
  const s = { ...postSettings(e), ...commonSettings() };
  if (S.ui.checkExposure) s.finish = { exposure: S.ui.checkExposure };
  r.set(s);
  const sh = S.getShot(), at = sh.effects.findIndex((x) => x.id === e.id), layers = [];
  sh.effects.forEach((x, i) => {
    const v = x.id === e.id ? null : S.shownOf(x.id);
    if (v?.status !== "done") return;
    if (!v.preview) { if (!v.previewError) ensurePreview(x.id, v); return; }
    layers.push({ key: x.id, url: v.preview, below: i < at, settings: postSettings(x), adjust: adjustOf(x, fps) });
  });
  r.setLayers(layers).catch(() => {});
  if (wipeEl) wipeEl.hidden = !(other || S.ui.compare === true);
}
const adjustOf = (e, fps) => (settings, frame) => {
  const t = frame / fps, p = placeAt(e, t);
  return { ...settings, element: { ...settings.element, offset_x: p.dx, offset_y: p.dy, scale: p.scale, stretch: p.stretch, rotation: p.rot },
    weight: weightAt(e, fps, frame) * brightAt(e, t) };
};
function loadClip() {
  const c = clip();
  if (!c) { dropLive(); video.removeAttribute("src"); video.load(); currentClip = null; return; }
  if (S.ui.media?.live && !frozen && !liveFailed.has(S.ui.media.live)) { ensureLive(S.ui.media.live); applyLook(); return; }
  dropLive();
  const url = S.ui.media?.url || plateUrl(c);
  if (currentClip === url || frozen) return;
  const t = currentClip ? video.currentTime : 0;
  const wasClip = isPlate(currentClip) && isPlate(url) && currentClip !== url;
  currentClip = url;
  video.src = url;
  mediaLoading = S.ui.media ? url : null;
  if (mediaLoading) {
    const done = () => { if (mediaLoading !== url) return; mediaLoading = null; syncStatus(); };
    video.addEventListener("loadeddata", done, { once: true });
    video.addEventListener("error", done, { once: true });
  }
  video.addEventListener("loadedmetadata", () => { if (t && !wasClip) video.currentTime = Math.min(t, video.duration || t); }, { once: true });
  if (!S.ui.media) video.addEventListener("loadeddata", groundAfterLoad, { once: true });
  if (wasClip || !view.s) requestAnimationFrame(fit);
}
function followPlayback(v) {
  v.addEventListener("play", () => {
    const tick = () => { if (v.paused || v !== media()) return; if (resultActive() || motionOn(eff()) || shapeOn(eff())) draw(); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  });
  v.addEventListener("seeked", () => { if (v === media() && resultActive()) draw(); });
}
let frozen = false;
let resumeAt = null;
let pendingResume = null;
export function releaseMedia() {
  if (frozen || (!live && !video.getAttribute("src"))) return;
  const v = media();
  v.pause();
  try {
    const src = live?.ready ? live.canvas : video;
    const c = document.createElement("canvas");
    c.width = live?.ready ? live.canvas.width : video.videoWidth; c.height = live?.ready ? live.canvas.height : video.videoHeight;
    c.getContext("2d").drawImage(src, 0, 0);
    video.poster = c.toDataURL("image/jpeg", 0.85);
  } catch {  }
  resumeAt = v.currentTime;
  dropLive();
  video.removeAttribute("src");
  video.load();
  currentClip = null;
  frozen = true;
  root.classList.add("frozen");
}
export function restoreMedia() {
  if (!frozen) return;
  const t = resumeAt || 0;
  frozen = false;
  resumeAt = null;
  root.classList.remove("frozen");
  if (S.ui.media?.live && !liveFailed.has(S.ui.media.live)) pendingResume = t;
  loadClip();
  if (pendingResume != null) return;
  video.addEventListener("loadeddata", () => { video.removeAttribute("poster"); }, { once: true });
  if (t) video.addEventListener("loadedmetadata", () => { video.currentTime = t; }, { once: true });
}
export const isFrozen = () => frozen;

let sim = null;
let simRaf = 0;
let simBadge = null;
let simBadgeText = null;
let viewNote = null;
let mediaLoading = null;
export const simShown = () => !!sim && !sim.canvas.hidden;
export function previewSimLook(patch) {
  if (!sim?.look || sim.canvas.hidden) return;
  sim.r.setLook({ ...sim.look, ...patch });
  if (!simRaf) simRaf = requestAnimationFrame(simTick);
}
const shapeCache = new WeakMap();
function shapeFrame(m, i) {
  let per = shapeCache.get(m);
  if (!per) shapeCache.set(m, (per = []));
  if (per[i]) return per[i];
  const { w, h } = m.data.shape, g = m.arrays.shape, a = m.arrays.attention, o = i * w * h;
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  const c2 = cv.getContext("2d"), img = c2.createImageData(w, h), d = img.data;
  for (let p = 0; p < w * h; p++) {
    const v = g[o + p] / 255, at = a[o + p] / 255;
    const edge = at > 0.05 && at < 0.6 ? 0.25 : 0;
    d[4 * p] = 170 + 70 * v; d[4 * p + 1] = 110 + 90 * v; d[4 * p + 2] = 255;
    d[4 * p + 3] = Math.round(255 * Math.max(v > 0.02 ? 0.25 + 0.55 * v : 0, edge));
  }
  c2.putImageData(img, 0, 0);
  return (per[i] = cv);
}
function shapeOn(e) {
  const m = S.ui.liveMotion, c = clip();
  return !!(e && c && m?.data?.shape?.n && m.arrays?.shape && m.effect === e.id && m.clip === c.name
    && (S.ui.step === "effect" || S.ui.step === "where") && !S.ui.media);
}
function motionOn(e) {
  const m = S.ui.liveMotion, c = clip();
  return !!(e && c && m?.data?.emit?.length && m.effect === e.id && m.clip === c.name && (S.ui.step === "effect" || S.ui.step === "where") && !S.ui.media);
}
function syncStatus(simBusy = false) {
  if (!simBadge) return;
  const w = S.ui.waitNote, e = eff();
  const loading = mediaLoading || (live && !live.ready);
  const text = (w && w.effect === e?.id && w.text) || (loading && S.ui.media && `Loading the ${(S.ui.media.label || "result").toLowerCase()}…`)
    || (simBusy && "Updating the particles…") || "";
  simBadge.hidden = !text;
  if (text && simBadgeText.textContent !== text) simBadgeText.textContent = text;
}
function syncSim() {
  const L = S.ui.liveSim, c = clip();
  const mine = !!(L && c && L.clip === c.name && L.effect === eff()?.id && !S.ui.media && !frozen);
  const busy = mine && L.status === "running" && !L.lookOnly;
  syncStatus(busy);
  if (viewNote) viewNote.hidden = !(L?.data && c && L.clip === c.name && L.effect === eff()?.id && S.ui.media && S.ui.step === "effect" && !frozen);
  const show = mine && !!L.data;
  if (sim) sim.canvas.classList.toggle("stale", show && busy);
  if (!show) { if (sim) sim.canvas.hidden = true; return; }
  if (!sim) {
    const canvas = h("canvas", { class: "plate sim", "aria-label": "Particles, live" });
    let r;
    try { r = new LiveSim(canvas); } catch (err) {
      document.dispatchEvent(new CustomEvent("ef:live-error", { detail: { message: err.message } }));
      return;
    }
    sim = { r, canvas, data: null, look: null, t0: performance.now() };
  }
  if (sim.canvas.parentNode !== viewport || sim.canvas.previousElementSibling !== video) video.after(sim.canvas);
  sim.canvas.hidden = false;
  if (sim.data !== L.data) { sim.r.setData(L.data); sim.data = L.data; sim.t0 = performance.now(); }
  if (sim.look !== L.look) { sim.r.setLook(L.look); sim.look = L.look; sim.canvas.style.mixBlendMode = blendCss(L.look); }
  Object.assign(sim.canvas.style, { width: video.style.width, height: video.style.height, transform: video.style.transform, filter: video.style.filter });
  if (!simRaf) simRaf = requestAnimationFrame(simTick);
}
function simTick() {
  simRaf = 0;
  if (!sim || sim.canvas.hidden || !sim.data) return;
  const hd = sim.data.header;
  const i = hd.mode === "hold" ? Math.floor(((performance.now() - sim.t0) / 1000) * hd.fps) % hd.n : Math.round(playhead() * hd.fps);
  sim.r.draw(i);
  simRaf = requestAnimationFrame(simTick);
}

export function mountStage(el) {
  root = el;
  root.tabIndex = 0;
  root.classList.add("stage");
  video = h("video", { class: "plate", muted: true, playsInline: true, preload: "auto", "aria-label": "Your clip" });
  viewport = h("div", { class: "viewport" }, video);
  overlay = h("canvas", { class: "overlay", "aria-hidden": "true" });
  ctx = overlay.getContext("2d");
  toolbar = h("div", { class: "toolbar", role: "toolbar", "aria-label": "Canvas tools" });
  zoomLabel = h("span", { class: "zoom-label", "aria-live": "off" }, "100 %");
  const zoombar = h("div", { class: "zoombar" },
    h("button", { class: "zoom-btn keys-btn", title: "Keys and gestures (?)", onclick: () => root.dispatchEvent(new CustomEvent("efa-help", { bubbles: true })) }, "Keys ?"),
    h("button", { class: "icon-btn", title: "Zoom out (Alt+−, mouse wheel as in ComfyUI)", "aria-label": "Zoom out", onclick: () => zoomBy(1 / 1.25) }, icon("zoomOut")),
    h("button", { class: "zoom-btn", title: "100 %", onclick: zoom100 }, zoomLabel),
    h("button", { class: "icon-btn", title: "Zoom in (Alt+=, mouse wheel as in ComfyUI)", "aria-label": "Zoom in", onclick: () => zoomBy(1.25) }, icon("zoomIn")),
    h("button", { class: "icon-btn", title: "Fit (., double-click)", "aria-label": "Fit to the window", onclick: fit }, icon("fit")));
  hint = h("div", { class: "stage-hint", role: "status", hidden: true });
  simBadgeText = h("span", {}, "Updating the particles…");
  simBadge = h("div", { class: "sim-badge", role: "status", hidden: true }, h("span", { class: "spinner", "aria-hidden": "true" }), simBadgeText);
  viewNote = h("div", { class: "view-note", hidden: true }, h("span", {}, "This view hides the particles"),
    h("button", { class: "btn small", onclick: () => S.setUI({ media: null, compare: false, pass: null }) }, "Back to the clip"));
  viewSwitch = h("div", { class: "seg view-switch", role: "group", "aria-label": "Show", hidden: true });
  wipeTags = [h("span", { class: "wipe-tag l" }, "Before"), h("span", { class: "wipe-tag r" }, "After")];
  wipeEl = h("div", { class: "wipe", hidden: true, title: "Drag: before | after (a click into the picture puts the line there)", role: "slider", tabindex: "0",
    "aria-label": "Before and after line" }, h("span", { class: "wipe-grip" }), ...wipeTags);
  wipeEl.addEventListener("pointerdown", (ev) => {
    ev.stopPropagation(); ev.preventDefault();
    wipeEl.setPointerCapture(ev.pointerId);
    const move = (e2) => {
      if (!live?.ready) return;
      const c = clip(); const p = local(e2);
      live.renderer.setWipe(clamp((p.x - view.x) / (c.width * view.s), 0, 1));
      apply();
    };
    move(ev);
    wipeEl.onpointermove = move;
    wipeEl.onpointerup = () => { wipeEl.onpointermove = null; };
  });
  wipeEl.addEventListener("keydown", (ev) => {
    if (!live?.ready || (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight")) return;
    ev.preventDefault(); ev.stopPropagation();
    live.renderer.setWipe(clamp(live.renderer.wipe + (ev.key === "ArrowLeft" ? -0.02 : 0.02), 0, 1));
    apply();
  });
  root.append(viewport, overlay, wipeEl, toolbar, zoombar, hint, h("div", { class: "stage-notes" }, simBadge, viewNote), viewSwitch);
  root.addEventListener("pointerdown", onDown);
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerup", onUp);
  root.addEventListener("pointercancel", onCancel);
  root.addEventListener("lostpointercapture", onCancel);
  root.addEventListener("wheel", onWheel, { passive: false });
  root.addEventListener("dblclick", (ev) => { if (!ev.target.closest?.(".toolbar, .zoombar, .view-switch, .wipe") && !hitTest(local(ev).x, local(ev).y)) fit(); });
  root.addEventListener("keydown", onKey);
  root.addEventListener("keyup", onKeyUp);
  root.addEventListener("focusout", () => { spaceDown = false; });
  new ResizeObserver(() => (view.fitted ? fit() : draw())).observe(root);
  video.addEventListener("loadedmetadata", () => { if (view.fitted) fit(); });
  video.addEventListener("error", () => {
    if (video.getAttribute("src")) document.dispatchEvent(new CustomEvent("ef:media-error", { detail: { url: video.getAttribute("src") } }));
  });
  S.subscribe(render);
  render();
}

export function setHint(text, soft = false) { hint.textContent = text || ""; hint.hidden = !text; hint.classList.toggle("soft", soft); }
function autoHint() {
  const c = clip(), e = eff(), s = st();
  if (!c) return setHint("");
  if (drag) return setHint(hoverHint(drag), true);
  if (frozen) return setHint("Paused while ComfyUI works: the preview shows a still.");
  if (S.ui.tool === "brush" && paintTarget()) return setHint(paintTarget() === "mask" ? "Paint over the object on the first frame (Alt: erase, [ ]: brush size)"
    : "Draw the path the effect follows, on the first frame (Alt: erase)");
  if (S.ui.tool === "pick" && isLive()) return setHint("Click a colour in your clip: the effect, its light and glow take it on");
  if (S.ui.step === "where" && e && !e.where.a) return setHint("Click the object or the place for the effect");
  if (needsB()) return setHint("Now click where it should go (point B)");
  if (S.ui.step === "effect" && e && s && s.placement !== "frame" && !e.where.a) return setHint("Click the place for the effect first");
  setHint(hoverText, true);
}
let viewSwitch, wipeEl, wipeTags;
let lookFrom = null;
let shownResult = null;
const EXPOSURE = [0, 2, 4];
function renderViewSwitch() {
  const e = eff();
  const v = e && S.shownOf(e.id);
  const made = v?.comp ? { url: v.comp, live: v.preview && !liveFailed.has(v.preview) ? v.preview : null, label: "Result" } : null;
  if (made && S.ui.media?.url === made.url && !S.ui.media.live && made.live) S.ui.media = made;
  if (lookFrom && lookFrom !== S.ui.step && S.ui.media) Object.assign(S.ui, { media: null, compare: false, pass: null });
  if ((S.ui.step === "look" || S.ui.step === "export") && lookFrom !== S.ui.step && !S.ui.media && made) S.ui.media = made;
  lookFrom = S.ui.step;
  const ana = S.ui.media?.analysis;
  if (S.ui.media && !ana) shownResult = S.ui.media;
  if (shownResult && shownResult.clip && shownResult.clip !== clip()?.name) shownResult = null;
  const result = (!ana && S.ui.media) || shownResult || made;
  const pre = S.ui.analysis && S.ui.analysis.clip === clip()?.name ? S.ui.analysis.previews || {} : {};
  if (ana && !pre[ana]) { S.ui.media = null; return renderViewSwitch(); }
  if (!clip() || (!result && !pre.depth && !pre.normals)) { viewSwitch.hidden = true; video.style.filter = ""; return; }
  viewSwitch.hidden = false;
  const onResult = !!S.ui.media && !ana;
  const exp = S.ui.checkExposure || 0;
  const show = (part, label, tip) => pre[part] ? h("button", { "aria-pressed": String(ana === part), title: tip,
    onclick: () => S.setUI({ media: { url: pre[part], label, analysis: part }, compare: false }) }, label) : null;
  viewSwitch.replaceChildren(...[
    h("button", { "aria-pressed": String(!S.ui.media), title: "Your clip without the effect", onclick: () => S.setUI({ media: null, compare: false, pass: null }) }, "Clip"),
    show("depth", "Depth", "Depth of the scene (near = bright), from the analysis"),
    show("normals", "Normals", "Which way the surfaces face, from the analysis"),
    result?.live ? h("button", { "aria-pressed": String(onResult && !!S.ui.compare), title: "Before and after with a line to drag",
      onclick: () => S.setUI({ media: result, compare: true }) }, "Compare") : null,
    result ? h("button", { "aria-pressed": String(onResult && !S.ui.compare && !S.ui.pass), title: "What was made", onclick: () => S.setUI({ media: result, compare: false, pass: null }) }, result.label || "Result") : null,
    ...(result?.live ? [["element", "Element", "The element alone, with its alpha"], ["light", "Light", "The light it throws on the scene"], ["glow", "Glow", "The glow alone"]] : [])
      .map(([p, label, tip]) => h("button", { "aria-pressed": String(onResult && !S.ui.compare && S.ui.pass === p), title: tip,
        onclick: () => S.setUI({ media: result, compare: false, pass: p }) }, label)),
    h("button", { class: "exposure", "aria-pressed": String(!!exp), title: "Check exposure: brightens the view to show banding in dark gradients (view only)",
      onclick: () => S.setUI({ checkExposure: EXPOSURE[(EXPOSURE.indexOf(exp) + 1) % EXPOSURE.length] || null }) }, exp ? `+${exp} stops` : "Exposure"),
  ].filter(Boolean));
  video.style.filter = exp ? `brightness(${2 ** exp})` : "";
}

export function render() {
  if (!root) return;
  loadClip();
  root.classList.toggle("has-clip", !!clip());
  renderToolbar();
  renderViewSwitch();
  loadClip();
  applyLook();
  syncSim();
  autoHint();
  draw();
}

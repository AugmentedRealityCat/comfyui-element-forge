import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

export const EXT_NAME = "ElementForge.AppNodes";
export const STAGE_CLASS = "EFAppStage";
export const EFFECT_CLASS = "EFAppEffect";
export const MODELS_CLASS = "EFAppModels";
export const WIDGET_NAME = "ef_stage";
export const WIDGET_LABEL = "Canvas & timeline";
export const STEPS_WIDGET = "ef_steps";
export const STEPS_LABEL = "Steps";
export const TIMELINE_PX = 220;
export const STAGE_DEFAULT_PX = 420;
export const STAGE_MIN_PX = 160;
export const STAGE_MAX_PX = 1600;
export const GRIP_PX = 10;
export const WIDE_PX = 760;
export const SIDE_PX = 348;
export const SIDE_GAP_PX = 8;
export const COMP_NODE = "475";
export const CENTRE = '[data-testid="linear-center-panel"]';
export const DEBOUNCE_MS = 150;
export const POLL_MS = 500;
export const CLAIM_FRAMES = 30;
export const CLAIM_MAX_PER_S = 5;
const MOUNT_URL = new URL("./efa/mount.js", import.meta.url).href;

export const ADV = {
  own_mask: "Own object mask (off = click)",
  all_alike: "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)",
  follows_motion: "Follows motion",
  sharper_2x: "LTX upscale x2 (latent upscaler + second pass, test)",
};
export const ADV_SCENE = "Sticks to scene (off = object)";
export const ADV_MASK = "Track follows the object mask (hands, bodies)";
export const ADV_STILL = "Fixed on screen (Follows: Screen)";
export const FOLLOWS = { point: [false, false, false], object: [false, true, false], mask: [false, true, false], scene: [true, false, false],
  screen: [false, false, true] };
export const ADV_GUIDE = "Guide source";
export const ADV_AI_GUIDE = "Guide for the AI (particles / drawn path / object shape / none)";
export const ADV_INPAINT = "Inpaint (off = on black)";
export const ADV_INPAINT_SIGMAS = "Inpaint sigmas (start 0.909 = tested default)";
export function keepSigmas(k) {
  k = Math.min(1, Math.max(0, +k || 0));
  const start = +(0.909375 - k * (0.909375 - 0.725)).toFixed(6);
  return start <= 0.725 ? "0.725, 0.421875, 0.0" : `${start}, 0.725, 0.421875, 0.0`;
}


export function widgetValues(node) {
  const out = {};
  for (const w of node?.widgets || []) if (w?.name) out[w.name] = w.value;
  return out;
}

export function buildContext(fx, clipName) {
  fx = fx || {};
  const es = String(fx.effect_style || "");
  const cut = es.indexOf("/");
  const kind = cut >= 0 ? es.slice(0, cut) : es;
  const style = cut >= 0 ? es.slice(cut + 1) : "";
  const po = typeof fx.prompt_override === "string" ? fx.prompt_override.trim() : "";
  const seedVal = Number.isFinite(+fx.seed) ? Math.trunc(+fx.seed) : null;
  const adv = {};
  const fol = FOLLOWS[fx.sticks_to];
  if (fol) [adv[ADV_SCENE], adv[ADV_MASK], adv[ADV_STILL]] = fol;
  for (const [w, name] of Object.entries(ADV)) if (fx[w] !== undefined) adv[name] = !!fx[w];
  if (fx.guide && fx.guide !== "style default") adv[ADV_AI_GUIDE] = fx.guide;
  else if (fx.draw_path) adv[ADV_AI_GUIDE] = "drawn path";
  if (adv[ADV_AI_GUIDE] === "drawn path") adv[ADV_GUIDE] = "draw";
  const how = { overlay: false, inpaint: true, "layer on black": false, "painted into the clip": true }[fx.how_it_goes_in];
  if (how !== undefined) adv[ADV_INPAINT] = how;
  if (+fx.keep_original > 0) adv[ADV_INPAINT_SIGMAS] = keepSigmas(fx.keep_original);
  return {
    mode: fx.mode === "advanced" ? "advanced" : "basic",
    kind, style,
    strength: fx.strength || "normal",
    text: { what: fx.describe || "", look: fx.look_words || "", motion: fx.motion_words || "", contact: fx.contact_words || "" },
    prompt: po ? fx.prompt_override : null,
    seed: { mode: fx.control_after_generate === "fixed" ? "keep" : "new", value: seedVal },
    night: !!fx.night,
    scene: typeof fx.shot_sentence === "string" ? fx.shot_sentence.trim() : "",
    word: fx.object_word || "",
    adv,
    guideParticles: fx.guide_particles && fx.guide_particles !== "style default" ? String(fx.guide_particles) : null,
    madeBy: fx.made_by === "ai" || fx.made_by === "particles" ? fx.made_by : null,
    clip: clipName ? { name: String(clipName) } : null,
  };
}

export function migrateFollows(value, shotJson) {
  if (value === "mask") return "object";
  if (value !== "object") return null;
  try { const st = JSON.parse(shotJson || "{}"); return st && st.efa === 1 && !st.follows ? "point" : null; } catch { return null; }
}

export function aspectOf(shotJson) {
  try {
    const st = JSON.parse(shotJson || "{}");
    const c = st?.shot?.clip;
    const a = c && c.width > 0 && c.height > 0 ? c.height / c.width : 9 / 16;
    return Math.min(2.5, Math.max(0.25, a));
  } catch { return 9 / 16; }
}

export function stageHeight(width, aspect, cap = Infinity) {
  const w = Math.max(0, +width || 0);
  const top = Math.max(STAGE_MIN_PX, Math.min(STAGE_MAX_PX, +cap || Infinity));
  return Math.round(Math.min(Math.max(STAGE_MIN_PX, w * (aspect || 9 / 16)), top) + TIMELINE_PX);
}

function sortKeys(v) {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === "object") { const o = {}; for (const k of Object.keys(v).sort()) o[k] = sortKeys(v[k]); return o; }
  return v;
}
export function promptShot(json) {
  const raw = typeof json === "string" ? json : JSON.stringify(json ?? {});
  let st;
  try { st = JSON.parse(raw || "{}"); } catch { return raw; }
  if (!st || typeof st !== "object" || st.efa !== 1) return raw;
  const vf = st.values_for && typeof st.values_for === "object" ? { ...st.values_for } : {};
  delete vf.at;
  const values = st.values && typeof st.values === "object" ? st.values : {};
  return JSON.stringify({ efa: 1, values: sortKeys(values), values_for: sortKeys(vf) });
}

const TYPING = /^(INPUT|TEXTAREA|SELECT)$/;
const NAMED = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Delete", "Backspace", "Escape", "Enter",
  "Home", "End", "PageUp", "PageDown", " ", "Spacebar"]);
export function isWorkspaceKey(e) {
  const k = e.key || "";
  const mod = e.ctrlKey || e.metaKey;
  if (mod && !e.altKey) return /^(z|y|Z|Y|Enter|ArrowLeft|ArrowRight|\+|-|=|0)$/.test(k);
  if (e.altKey && !mod) return k === "=" || k === "+" || k === "-";
  if (mod || e.altKey) return false;
  return NAMED.has(k) || k.length === 1;
}

const APP_ITEM = '[data-testid="app-mode-widget-item"],[data-testid="builder-widget-item"]';
const shown = (el) => !!el && typeof el.getClientRects === "function" && el.getClientRects().length > 0;

export function appPanelOpen(doc = document) {
  const list = doc.querySelector?.('[data-testid="linear-widgets"]');
  if (list) return shown(list);
  return [...(doc.querySelectorAll?.(APP_ITEM) || [])].some(shown);
}

export function widgetKeyOf(node, widget) {
  if (widget?.widgetId) return widget.widgetId;
  const gid = node?.graph?.rootGraph?.id ?? node?.graph?.id;
  return gid ? [gid, encodeURIComponent(String(node.id)), encodeURIComponent(widget?.name ?? "")].join(":") : null;
}

export function panelSlotFor(node, widget, doc = document) {
  const items = [...(doc.querySelectorAll?.(APP_ITEM) || [])];
  if (!items.length) return null;
  const key = widgetKeyOf(node, widget);
  const tail = ":" + encodeURIComponent(String(node?.id)) + ":" + encodeURIComponent(widget?.name ?? "");
  const item = items.find((el) => el.dataset?.widgetKey === key) || items.find((el) => el.dataset?.widgetKey?.endsWith?.(tail));
  if (!item || !shown(item)) return null;
  const slots = item.querySelectorAll?.('div[class~="*:flex-1"]') || [];
  return slots.length ? slots[slots.length - 1] : null;
}

export function inLoadedGraph(A, n) {
  const g = n?.graph;
  if (!g) return false;
  const root = A?.graph;
  if (root && g !== root && g.rootGraph !== root) return false;
  const list = g._nodes || g.nodes;
  return Array.isArray(list) ? list.includes(n) : true;
}


function linkOf(graph, id) {
  if (id == null || !graph) return null;
  return graph.getLink?.(id) ?? graph.links?.get?.(id) ?? graph.links?.[id] ?? null;
}
export function linkedNode(node, inputName) {
  const idx = (node.inputs || []).findIndex((i) => i.name === inputName);
  if (idx < 0) return null;
  try { const n = node.getInputNode?.(idx); if (n) return n; } catch {  }
  const l = linkOf(node.graph, node.inputs[idx].link);
  return l ? node.graph?.getNodeById?.(l.origin_id) ?? null : null;
}

const bridges = new Set();
let active = null;

function linearKeys(A) {
  const inputs = A?.graph?.extra?.linearData?.inputs;
  return new Set(Array.isArray(inputs) ? inputs.filter((i) => Array.isArray(i) && i[1] === WIDGET_NAME).map((i) => String(i[0])) : []);
}
export function elect(A = app) {
  if (active && !(active.alive && inLoadedGraph(active.A, active.node))) { active.deactivate(); active = null; }
  if (!active) {
    const live = [...bridges].filter((x) => x.alive && inLoadedGraph(x.A, x.node));
    const lin = linearKeys(A);
    active = live.find((x) => lin.has(String(x.node.id))) || live[0] || null;
    active?.activate();
  }
  for (const x of bridges) if (x !== active && x.alive && inLoadedGraph(x.A, x.node)) x.showStandby();
  return active;
}
export function stageRegistry() {
  return { bridges: [...bridges], active, activeId: active?.node?.id ?? null, count: bridges.size };
}
export function resetRegistry() { for (const x of bridges) x.deactivate?.(); bridges.clear(); active = null; }


export function attachStage(node, deps = {}) {
  const A = deps.app || app;
  const API = deps.api || api;
  const doc = deps.document || document;
  const loadMount = deps.loadMount || (() => import(MOUNT_URL));
  const IO = deps.IntersectionObserver ?? globalThis.IntersectionObserver;
  const RO = deps.ResizeObserver ?? globalThis.ResizeObserver;
  const raf = deps.requestAnimationFrame ?? globalThis.requestAnimationFrame ?? ((f) => setTimeout(f, 16));
  const caf = deps.cancelAnimationFrame ?? globalThis.cancelAnimationFrame ?? clearTimeout;
  const now = () => (globalThis.performance?.now?.() ?? Date.now());

  const shotW = node.widgets?.find((w) => w.name === "shot");

  const root = doc.createElement("div");
  root.className = "efa-host";
  root.tabIndex = 0;
  root.dataset.efa = "stage";
  root.style.cssText = "position:relative;flex:none;width:100%;outline:none;overflow:hidden;box-sizing:border-box;padding-bottom:" + GRIP_PX +
    "px;min-height:" + (160 + TIMELINE_PX + GRIP_PX) + "px";
  const grip = doc.createElement("div");
  grip.className = "efa-height-grip";
  grip.title = "Drag to set the height of the picture";
  grip.style.cssText = "position:absolute;left:0;right:0;bottom:0;height:" + GRIP_PX + "px;cursor:ns-resize;z-index:5;" +
    "background:linear-gradient(transparent 4px, rgba(128,128,128,.45) 4px, rgba(128,128,128,.45) 6px, transparent 6px) center/40px 100% no-repeat";

  const b = { A, node, root, controller: null, pending: null, timer: null, alive: true, active: false, height: 0, lastCtx: "",
    poll: null, visible: false, claims: [], claimRaf: 0, claimCount: 0, claimStop: false, ready: Promise.resolve(false) };

  if (shotW) {
    shotW.hidden = true;
    shotW.options = shotW.options || {};
    shotW.options.hideInPanel = true;
    shotW.options.canvasOnly = true;
    shotW.computeSize = () => [0, -4];
    shotW.serializeValue = () => promptShot(b.pending != null ? b.pending : shotW.value);
    shotW.beforeQueued = () => { if (!b.active) return; try { b.controller?.flush?.(); b.controller?.queued?.(); } catch {  } flush(); };
  }

  const markChanged = () => {
    try { A.graph?.setDirtyCanvas?.(true, true); } catch {  }
    try {
      const ct = A.extensionManager?.workflow?.activeWorkflow?.changeTracker ?? A.workflowManager?.activeWorkflow?.changeTracker;
      if (ct?.captureCanvasState) ct.captureCanvasState(); else ct?.checkState?.();
    } catch {  }
  };
  const flush = (quiet = false) => {
    if (b.timer) { clearTimeout(b.timer); b.timer = null; }
    if (b.pending == null || !shotW) return;
    const v = b.pending; b.pending = null;
    if (shotW.value !== v) { shotW.value = v; if (!quiet) markChanged(); }
    if (quiet) return;
    syncPaintImages(v);
    resize();
  };
  const syncPaintImages = (json) => {
    let vals;
    try { vals = JSON.parse(json)?.values; } catch { return; }
    if (!vals || typeof vals !== "object") return;
    const nodes = A.graph?._nodes || A.graph?.nodes || [];
    for (const n of nodes) {
      if (n?.type !== "LoadImage" || typeof vals[n.title] !== "string" || !vals[n.title]) continue;
      const w = n.widgets?.find((x) => x.name === "image");
      if (!w || w.value === vals[n.title]) continue;
      const opts = w.options?.values;
      if (Array.isArray(opts) && !opts.includes(vals[n.title])) opts.push(vals[n.title]);
      w.value = vals[n.title];
      try { w.callback?.(w.value); } catch (e) { console.warn("[Element Forge] brush image:", e); }
    }
  };
  const fxNode = () => linkedNode(node, "effect");
  const stepsEl = () => { const f = fxNode(); const s = f?.__efaSteps; return s?.alive && inLoadedGraph(A, f) ? s.el : null; };
  b.syncSteps = () => { if (!b.active) return; try { b.controller?.steps?.(stepsEl()); } catch (e) { console.warn("[Element Forge] steps:", e); } };
  const clipNode = () => linkedNode(node, "video");
  const clipWidget = () => clipNode()?.widgets?.find((w) => w.name === "file") || null;
  const modelsNode = () => (A.graph?._nodes || A.graph?.nodes || []).find((n) => n?.type === MODELS_CLASS) || null;
  const context = () => buildContext(widgetValues(fxNode()), clipWidget()?.value || null);

  const host = {
    getShot: () => (b.pending != null ? b.pending : String(shotW?.value ?? "{}")),
    setShot(json) {
      b.pending = typeof json === "string" ? json : JSON.stringify(json);
      if (b.timer) clearTimeout(b.timer);
      b.timer = setTimeout(flush, DEBOUNCE_MS);
    },
    context,
    run() {
      try { b.controller?.flush?.(); } catch {  }
      flush();
      const cmd = A.extensionManager?.command;
      if (cmd?.execute) return cmd.execute("Comfy.QueuePrompt");
      return A.queuePrompt?.(0, 1);
    },
    async uploadFile(file) {
      const body = new FormData();
      body.append("image", file, file.name);
      body.append("type", "input");
      const r = await API.fetchApi("/upload/image", { method: "POST", body });
      if (!r.ok) throw new Error(r.status === 413
        ? "the file is too large for ComfyUI's upload. Put it into ComfyUI's input folder and pick it from the list instead."
        : `status ${r.status}. Try again, or put the file into ComfyUI's input folder and pick it from the list.`);
      const j = await r.json();
      return j.subfolder ? `${j.subfolder}/${j.name}` : j.name;
    },
    setClip(name) {
      const w = clipWidget();
      if (!w) return false;
      const vals = w.options?.values;
      if (Array.isArray(vals) && !vals.includes(name)) vals.push(name);
      const old = w.value;
      w.value = name;
      try { w.callback?.(name); } catch (e) { console.warn("[Element Forge] Clip-Callback:", e); }
      try { clipNode()?.onWidgetChanged?.(w.name, name, old, w); } catch (e) { console.warn("[Element Forge] clip change:", e); }
      markChanged();
      pushContext(true);
      return true;
    },
    effectValues: () => widgetValues(fxNode()),
    setEffect(name, value) {
      const n = fxNode();
      const w = n?.widgets?.find((x) => x.name === name);
      if (!w) return false;
      if (w.value === value) return true;
      const vals = w.options?.values;
      if (Array.isArray(vals) && !vals.includes(value)) return false;
      const old = w.value;
      w.value = value;
      try { w.callback?.(value); } catch (e) { console.warn("[Element Forge] widget callback:", e); }
      try { n.onWidgetChanged?.(name, value, old, w); } catch (e) { console.warn("[Element Forge] widget change:", e); }
      markChanged();
      pushContext(true);
      return true;
    },
    setEffects(values) {
      const n = fxNode();
      if (!n) return false;
      for (const [name, value] of Object.entries(values || {})) {
        const w = n.widgets?.find((x) => x.name === name);
        if (!w || w.value === value) continue;
        const vals = w.options?.values;
        if (Array.isArray(vals) && !vals.includes(value)) continue;
        const old = w.value;
        w.value = value;
        try { w.callback?.(value); } catch (e) { console.warn("[Element Forge] widget callback:", e); }
        try { n.onWidgetChanged?.(name, value, old, w); } catch (e) { console.warn("[Element Forge] widget change:", e); }
      }
      markChanged();
      pushContext(true);
      return true;
    },
    clipChoices: () => { const v = clipWidget()?.options?.values; return Array.isArray(v) ? [...v] : []; },
    modelValues: () => { const n = modelsNode(); return n ? widgetValues(n) : null; },
    setModels(values) {
      const n = modelsNode();
      if (!n) return false;
      for (const [name, value] of Object.entries(values || {})) {
        const w = n.widgets?.find((x) => x.name === name);
        if (!w || w.value === value) continue;
        const vals = w.options?.values;
        if (Array.isArray(vals) && !vals.includes(value)) continue;
        const old = w.value;
        w.value = value;
        try { w.callback?.(value); } catch (e) { console.warn("[Element Forge] models callback:", e); }
        try { n.onWidgetChanged?.(name, value, old, w); } catch (e) { console.warn("[Element Forge] models change:", e); }
      }
      markChanged();
      return true;
    },
    inApp: () => appPanelOpen(doc),
    relayout: () => resize(),
    userData: {
      async list(dir) {
        const r = await API.fetchApi(`/userdata?dir=${encodeURIComponent(dir)}&recurse=false&full_info=true`);
        if (r.status === 404) return [];
        if (!r.ok) throw new Error(`the user folder answered ${r.status}`);
        return r.json();
      },
      async get(path) {
        const r = await API.fetchApi(`/userdata/${encodeURIComponent(path)}`);
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      },
      async put(path, data, overwrite = true) {
        const r = await API.fetchApi(`/userdata/${encodeURIComponent(path)}?overwrite=${overwrite}`,
          { method: "POST", body: JSON.stringify(data, null, 1), headers: { "Content-Type": "application/json" } });
        if (!r.ok) throw new Error(r.status === 409 ? "a file of that name exists" : `the user folder answered ${r.status}`);
      },
      async remove(path) {
        const r = await API.fetchApi(`/userdata/${encodeURIComponent(path)}`, { method: "DELETE" });
        if (!r.ok && r.status !== 404) throw new Error(`the user folder answered ${r.status}`);
      },
    },
  };

  function pushContext(force = false) {
    if (!b.controller) return;
    const c = context();
    const sig = JSON.stringify(c);
    if (!force && sig === b.lastCtx) return;
    b.lastCtx = sig;
    try { b.controller.setContext(c); } catch (e) { console.warn("[Element Forge] setContext:", e); }
  }
  function hookSources() {
    for (const n of [fxNode(), clipNode()]) for (const w of n?.widgets || []) {
      if (w.__efaHooked) continue;
      w.__efaHooked = true;
      const cb = w.callback;
      w.callback = function () { const r = cb?.apply(this, arguments); queueMicrotask(() => { if (b.active) pushContext(); }); return r; };
    }
  }
  b.hookSources = hookSources;
  b.migrateFollows = () => {
    const n = fxNode();
    const w = n?.widgets?.find((x) => x.name === "sticks_to");
    const v = w ? migrateFollows(w.value, b.pending != null ? b.pending : shotW?.value) : null;
    if (!v) return false;
    const old = w.value;
    w.value = v;
    try { n.onWidgetChanged?.("sticks_to", v, old, w); } catch (e) { console.warn("[Element Forge] follows:", e); }
    return true;
  };

  const stageCap = () => { const v = +node.properties?.efa_stage_px; return v > 0 ? v : STAGE_DEFAULT_PX; };
  function resize() {
    const width = root.offsetWidth || root.getBoundingClientRect?.().width || root.clientWidth || 0;
    const cards = root.querySelector?.(".efa-cards:not([hidden])");
    const ws = root.querySelector?.(".efa-ws") || null;
    const withStage = !root.querySelector || !!ws;
    const wide = !!(ws && cards && cards.parentElement === ws && width >= WIDE_PX);
    ws?.classList?.toggle("efa-wide", wide);
    const aspect = aspectOf(host.getShot());
    const cardsH = Math.ceil(cards?.offsetHeight || 0);
    const natural = wide ? Math.max(stageHeight(width - SIDE_PX - SIDE_GAP_PX, aspect, stageCap()), cardsH) + GRIP_PX
      : (withStage ? stageHeight(width, aspect, stageCap()) + GRIP_PX : 0) + cardsH;
    const tlH = Math.ceil(root.querySelector?.(".efa-timeline")?.offsetHeight || 0) || TIMELINE_PX;
    const minH = withStage ? (wide ? Math.max(STAGE_MIN_PX + tlH, cardsH) : STAGE_MIN_PX + tlH + cardsH) + GRIP_PX : cardsH;
    const par = root.parentElement || null;
    if (b.ro && par && par !== b.par) { if (b.par) b.ro.unobserve?.(b.par); b.ro.observe(par); b.par = par; }
    const vue = withStage && !appPanelOpen(doc) && !!root.closest?.("[data-node-id]");
    const room = withStage && !vue && !appPanelOpen(doc) ? Math.floor(par?.clientHeight || 0) : 0;
    b.minH = minH;
    const h = vue ? 0 : room > 0 ? Math.max(minH, room) : natural;
    root.style.minHeight = withStage ? minH + "px" : "0px";
    root.style.flex = vue ? "1 1 auto" : "none";
    if (h !== b.height) { b.height = h; root.style.height = h ? h + "px" : ""; }
    if (room > 0 && minH > room + 1) try { node.setSize?.([node.size[0], node.computeSize?.()[1] || node.size[1]]); node.setDirtyCanvas?.(true, true); } catch {  }
  }
  grip.addEventListener("pointerdown", (e) => {
    e.preventDefault(); e.stopPropagation();
    const y0 = e.clientY;
    const stage0 = Math.max(STAGE_MIN_PX, (b.height || 0) - TIMELINE_PX - GRIP_PX);
    const node0 = node.size?.[1] || 0;
    const k = root.offsetHeight ? root.getBoundingClientRect().height / root.offsetHeight || 1 : 1;
    grip.setPointerCapture?.(e.pointerId);
    const move = (ev) => {
      if (b.par && !appPanelOpen(doc) && node.setSize) {
        node.setSize([node.size[0], Math.max(node.computeSize?.()[1] || 0, Math.round(node0 + (ev.clientY - y0) / k))]);
        node.setDirtyCanvas?.(true, true);
        return;
      }
      node.properties = node.properties || {};
      node.properties.efa_stage_px = Math.round(Math.max(STAGE_MIN_PX, Math.min(STAGE_MAX_PX, stage0 + (ev.clientY - y0) / k)));
      resize();
    };
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); markChanged(); };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  });

  root.addEventListener("pointerdown", (e) => {
    if (!TYPING.test(e.target?.tagName || "")) root.focus({ preventScroll: true });
  }, true);
  root.addEventListener("keydown", (e) => {
    if (TYPING.test(e.target?.tagName || "") && !(e.ctrlKey && e.key === "Enter")) { e.stopPropagation(); return; }
    if (isWorkspaceKey(e)) e.stopPropagation();
  });
  root.addEventListener("keyup", (e) => { if (isWorkspaceKey(e)) e.stopPropagation(); });
  root.addEventListener("focusout", () => { if (b.active) flush(); });
  const outsideDown = (e) => { if (!root.contains?.(e.target)) { try { b.controller?.flush?.(); } catch {  } flush(); } };

  const widget = node.addDOMWidget(WIDGET_NAME, "efa", root, {
    serialize: false,
    hideOnZoom: false,
    getValue: () => host.getShot(),
    setValue: (v) => { if (shotW && typeof v === "string") { shotW.value = v; b.controller?.reloadShot(); } },
    getMinHeight: () => b.minH || b.height || 160 + TIMELINE_PX,
  });
  widget.label = WIDGET_LABEL;
  widget.serialize = false;
  widget.computeLayoutSize = () => ({ minHeight: (b.minH || b.height || 160 + TIMELINE_PX) + 2 * (+widget.margin || 0), minWidth: 360 });
  Object.defineProperty(widget, "width", { configurable: true, get: () => undefined, set: () => {} });
  b.widget = widget;
  b.host = host;
  b.flush = flush;

  function claimNow() {
    if (!b.alive || !b.active || b.claimStop) return true;
    if (!appPanelOpen(doc)) return true;
    const slot = panelSlotFor(node, widget, doc);
    if (!slot) return false;
    if (slot.contains?.(root)) return true;
    const t = now();
    b.claims = b.claims.filter((x) => t - x < 1000);
    if (b.claims.length >= CLAIM_MAX_PER_S) {
      b.claimStop = true;
      console.warn("[Element Forge] the panel handover keeps switching between graph and panel - stopped.");
      return true;
    }
    b.claims.push(t);
    b.claimCount++;
    slot.replaceChildren(root);
    resize();
    return true;
  }
  function claimSoon(frames = CLAIM_FRAMES) {
    if (!b.active) return;
    caf(b.claimRaf);
    const step = (n) => { b.claimRaf = raf(() => { b.claimRaf = 0; if (!claimNow() && n > 0) step(n - 1); }); };
    step(frames);
  }
  b.claimSoon = claimSoon;
  b.claimNow = claimNow;

  const centre = () => (appPanelOpen(doc) ? doc.querySelector?.(CENTRE) || null : null);
  const syncDock = () => { try { b.controller?.dock?.(centre()); } catch (e) { console.warn("[Element Forge] dock:", e); } };
  b.syncDock = syncDock;
  const startPoll = () => { if (!b.poll) b.poll = setInterval(() => { if (b.alive && b.active) { hookSources(); pushContext(); syncDock(); b.syncSteps(); b.controller?.theme?.(); } }, POLL_MS); };
  const stopPoll = () => { if (b.poll) { clearInterval(b.poll); b.poll = null; } };
  const onIntersect = (entries) => {
    const vis = entries.some((x) => x.isIntersecting);
    if (!vis) claimSoon();
    if (vis === b.visible) return;
    b.visible = vis;
    if (vis) { resize(); startPoll(); try { b.controller?.shown(); } catch (e) { console.warn(e); } }
    else { stopPoll(); flush(); try { b.controller?.dock?.(null); b.controller?.hidden(); } catch (e) { console.warn(e); } }
  };

  function showStandby() {
    if (b.active) deactivate();
    if (b.standby) return;
    b.standby = true;
    const p = doc.createElement("p");
    p.className = "efa-standby";
    p.style.cssText = "margin:0;padding:12px;color:#d9a;font:13px sans-serif";
    p.textContent = "Element Forge: this workflow already has a workspace (Canvas & Timeline). Please use only one \"Canvas & Timeline\" node.";
    root.replaceChildren?.(p);
    if (!root.replaceChildren) root.textContent = p.textContent;
    b.ready = Promise.resolve(false);
  }
  b.showStandby = showStandby;

  const onExecuted = (ev) => {
    const d = ev?.detail;
    if (!b.active || String(d?.display_node ?? d?.node ?? "").split(":").pop() !== COMP_NODE) return;
    const file = Object.values(d.output || {}).flat().find((x) => x && typeof x === "object" && x.filename);
    const sub = String(file?.subfolder || "").replaceAll("\\", "/");
    if (file) try { b.controller?.result?.({ label: (sub ? sub + "/" : "") + file.filename, run: sub, filename: file.filename }); } catch (e) { console.warn(e); }
  };

  const run = { id: null, classes: null };
  const idOf = (d) => (d && typeof d === "object" ? d.display_node ?? d.node : d);
  const onRunStart = (ev) => {
    const pid = ev?.detail?.prompt_id;
    if (!b.active || !pid) return;
    run.id = pid; run.classes = null;
    fetch("/queue").then((r) => r.json()).then((q) => {
      if (run.id !== pid) return;
      const p = [...(q.queue_running || [])].find((x) => x[1] === pid)?.[2] || {};
      const classes = Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v?.class_type]));
      if (!Object.values(classes).some((c) => /^EF/.test(c || ""))) { run.id = null; return; }
      run.classes = classes;
      b.controller?.progress?.({ classType: null });
    }).catch(() => {});
  };
  const onRunNode = (ev) => {
    const id = idOf(ev?.detail);
    if (!b.active || !run.classes || id == null) return;
    const cls = run.classes[String(id)] ?? run.classes[String(id).split(".")[0]];
    b.controller?.progress?.({ classType: cls || null });
  };
  const onRunProgress = (ev) => {
    const d = ev?.detail;
    if (!b.active || !run.classes || !d?.max) return;
    const cls = run.classes[String(d.node ?? "")] ?? null;
    b.controller?.progress?.({ classType: cls, value: d.value, max: d.max });
  };
  const onRunError = (ev) => {
    const msg = ev?.detail?.exception_message || "";
    if (b.active && /Element Forge: /.test(msg)) b.controller?.runError?.(msg);
    onRunEnd(ev);
  };
  const onRunEnd = (ev) => {
    if (ev?.detail?.prompt_id && ev.detail.prompt_id !== run.id) return;
    run.id = null; run.classes = null;
    b.controller?.progress?.(null);
  };
  const RUN_EVENTS = [["execution_start", onRunStart], ["executing", onRunNode], ["progress", onRunProgress],
    ["execution_success", onRunEnd], ["execution_error", onRunError], ["execution_interrupted", onRunEnd]];

  function activate() {
    if (!b.alive) return Promise.resolve(false);
    if (b.active) return b.ready;
    b.active = true;
    b.standby = false;
    b.claimStop = false;
    b.claims = [];
    if (root.replaceChildren) root.replaceChildren(); else root.textContent = "";
    if (IO) { b.io = new IO(onIntersect); b.io.observe(root); } else startPoll();
    if (RO) { b.ro = new RO(() => resize()); b.ro.observe(root); }
    doc.addEventListener?.("pointerdown", outsideDown, true);
    API.addEventListener?.("executed", onExecuted);
    for (const [n, f] of RUN_EVENTS) API.addEventListener?.(n, f);
    b.ready = Promise.resolve()
      .then(loadMount)
      .then((mod) => {
        if (!b.alive || !b.active) return false;
        if (typeof mod?.mountWorkspace !== "function") throw new Error("mountWorkspace fehlt in efa/mount.js");
        b.controller = mod.mountWorkspace(root, host);
        root.appendChild(grip);
        hookSources();
        pushContext(true);
        b.syncSteps();
        resize();
        if (b.visible) b.controller?.shown?.();
        claimSoon();
        syncDock();
        return true;
      })
      .catch((e) => {
        console.warn("[Element Forge] the workspace does not load:", e);
        root.textContent = "Element Forge: the workspace does not load (" + String(e?.message || e).slice(0, 160) + ").";
        root.style.cssText += ";padding:12px;color:#d9a;font:13px sans-serif";
        return false;
      });
    return b.ready;
  }
  function deactivate() {
    if (!b.active) return;
    b.active = false;
    try { b.controller?.destroy(); } catch (e) { console.warn(e); }
    b.controller = null;
    b.lastCtx = "";
    flush(true);
    stopPoll();
    b.io?.disconnect?.(); b.ro?.disconnect?.(); b.io = b.ro = b.par = null;
    b.visible = false;
    caf(b.claimRaf); b.claimRaf = 0;
    doc.removeEventListener?.("pointerdown", outsideDown, true);
    API.removeEventListener?.("executed", onExecuted);
    for (const [n, f] of RUN_EVENTS) API.removeEventListener?.(n, f);
    run.id = null; run.classes = null;
  }
  b.activate = activate;
  b.deactivate = deactivate;

  const added = node.onAdded;
  node.onAdded = function () {
    const r = added?.apply(this, arguments);
    if (b.alive) { bridges.add(b); queueMicrotask(() => elect(A)); }
    return r;
  };
  const cfg = node.onConfigure;
  node.onConfigure = function () {
    const r = cfg?.apply(this, arguments);
    b.pending = null;
    queueMicrotask(() => { if (!b.active) return; hookSources(); try { b.controller?.reloadShot(); } catch (e) { console.warn(e); } resize(); pushContext(true); });
    return r;
  };
  const conn = node.onConnectionsChange;
  node.onConnectionsChange = function () { const r = conn?.apply(this, arguments); queueMicrotask(() => { if (b.active) { hookSources(); pushContext(); b.syncSteps(); } }); return r; };
  const rem = node.onRemoved;
  node.onRemoved = function () {
    const r = rem?.apply(this, arguments);
    destroy();
    return r;
  };
  function destroy() {
    if (!b.alive) return;
    const was = active === b;
    deactivate();
    b.alive = false;
    bridges.delete(b);
    if (was) { active = null; queueMicrotask(() => elect(A)); }
  }
  b.destroy = destroy;

  if (node.graph && inLoadedGraph(A, node)) { bridges.add(b); queueMicrotask(() => elect(A)); }
  return b;
}


export function hideOnNode(w) {
  const s = w?.visibility?.surfaces;
  if (!s || typeof s !== "object") return false;
  s.canvas = "never";
  s.vueNode = "never";
  return true;
}

export function attachSteps(node, deps = {}) {
  const doc = deps.document || document;
  const RO = deps.ResizeObserver ?? globalThis.ResizeObserver;
  const MO = deps.MutationObserver ?? globalThis.MutationObserver;
  const el = doc.createElement("div");
  el.className = "efa-steps-host";
  el.dataset.efa = "steps";
  el.style.cssText = "position:relative;width:100%;box-sizing:border-box;overflow:hidden;outline:none";
  const empty = doc.createElement("p");
  empty.className = "efa-steps-empty";
  empty.style.cssText = "margin:0;padding:10px 12px;color:#9a9aa3;font:12px/1.4 sans-serif";
  empty.textContent = "Connect \"effect\" to Element Forge · Canvas & Timeline: its steps 1–5 show here.";
  el.appendChild(empty);
  const s = { node, el, height: 0, alive: true, widget: null, ro: null, mo: null };
  const cards = () => el.querySelector?.(".efa-cards") || null;

  function size() {
    const c = cards();
    const h = Math.ceil((c ? c.offsetHeight : empty.offsetHeight) || 40) + 4;
    if (h === s.height) return;
    s.height = h;
    el.style.height = h + "px";
    try { const want = node.computeSize?.()[1]; if (want > 0) node.setSize?.([node.size[0], want]); } catch {  }
    try { node.setDirtyCanvas?.(true, true); } catch {  }
  }
  function children() {
    const c = cards();
    if (!c && !el.contains?.(empty)) { el.replaceChildren?.(empty); el.classList?.remove?.("efa-root", "efa-host"); }
    s.ro?.disconnect?.();
    if (RO) { s.ro = new RO(() => size()); s.ro.observe(c || empty); }
    size();
  }
  if (MO) { s.mo = new MO(() => children()); s.mo.observe(el, { childList: true }); }
  s.refresh = children;

  el.addEventListener("keydown", (e) => {
    if (TYPING.test(e.target?.tagName || "") && !(e.ctrlKey && e.key === "Enter")) e.stopPropagation();
  });
  const widget = node.addDOMWidget(STEPS_WIDGET, "efa-steps", el, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => (s.height || 40) + 2 * (+s.widget?.margin || 0),
  });
  widget.label = STEPS_LABEL;
  widget.serialize = false;
  const rowH = () => (s.height || 40) + 2 * (+s.widget?.margin || 0);
  widget.computeLayoutSize = () => ({ minHeight: rowH(), maxHeight: rowH(), minWidth: 320 });
  Object.defineProperty(widget, "width", { configurable: true, get: () => undefined, set: () => {} });
  s.widget = widget;
  s.hideFields = () => { for (const w of node.widgets || []) if (w !== widget) hideOnNode(w); };
  s.hideFields();

  const conn = node.onConnectionsChange;
  node.onConnectionsChange = function () { const r = conn?.apply(this, arguments); queueMicrotask(() => active?.syncSteps?.()); return r; };
  const rem = node.onRemoved;
  node.onRemoved = function () {
    const r = rem?.apply(this, arguments);
    s.alive = false;
    s.ro?.disconnect?.(); s.mo?.disconnect?.();
    queueMicrotask(() => active?.syncSteps?.());
    return r;
  };
  node.__efaSteps = s;
  children();
  queueMicrotask(() => active?.syncSteps?.());
  return s;
}

export function isFromWorkspace(e) {
  const t = e?.target;
  if (!t || typeof t.closest !== "function") return false;
  return !!(t.closest(".efa-ws") || (TYPING.test(t.tagName || "") && t.closest(".efa-steps-host")));
}
export function guardTrackerProto(proto) {
  if (!proto || typeof proto.undoRedo !== "function" || proto.undoRedo.__efaGuard) return false;
  const orig = proto.undoRedo;
  const wrapped = function (e, ...rest) {
    if (isFromWorkspace(e)) return Promise.resolve(true);
    return orig.call(this, e, ...rest);
  };
  wrapped.__efaGuard = true;
  proto.undoRedo = wrapped;
  return true;
}
function ensureUndoGuard() {
  try {
    const tr = app?.extensionManager?.workflow?.activeWorkflow?.changeTracker;
    if (tr) guardTrackerProto(Object.getPrototypeOf(tr));
  } catch {  }
}


const HIDE_PREVIEW_CSS = '[data-testid="linear-widgets"]:has(.efa-host) [data-testid="app-mode-widget-item"] '
  + '[data-testid="drop-zone-indicator"]:has(video[data-testid="drop-zone-media"]) { display: none; }'
  + ' [data-testid="linear-widgets"]:has(.efa-host) { scrollbar-gutter: stable; }';
function hideLoadVideoPreview() {
  if (document.querySelector("style[data-efa-hide-preview]")) return;
  const st = document.createElement("style");
  st.dataset.efaHidePreview = "1";
  st.textContent = HIDE_PREVIEW_CSS;
  document.head.append(st);
}

if (!globalThis.__EFA_NO_REGISTER__) {
  hideLoadVideoPreview();
  window.addEventListener("keydown", ensureUndoGuard, true);
  app.registerExtension({
    name: EXT_NAME,
    async setup() {
      const orig = app.queuePrompt;
      if (typeof orig !== "function" || orig.__efa) return;
      const wrapped = async function (...args) {
        try { await active?.controller?.beforeRun?.(); } catch (e) { console.warn("[Element Forge] before the run:", e); }
        try { return await orig.apply(this, args); } finally { try { active?.controller?.settle?.(); } catch {  } }
      };
      wrapped.__efa = true;
      app.queuePrompt = wrapped;
    },
    async nodeCreated(node) {
      if (node?.comfyClass === EFFECT_CLASS) {
        const s = attachSteps(node);
        requestAnimationFrame(() => { try { s.hideFields(); node.setSize([Math.max(node.size[0], 360), node.computeSize()[1]]); } catch {  } });
        return;
      }
      if (node?.comfyClass !== STAGE_CLASS) return;
      const b = attachStage(node);
      node.__efa = b;
      requestAnimationFrame(() => { try { node.setSize([Math.max(node.size[0], 480), Math.max(node.size[1], 520)]); } catch {  } });
    },
    async afterConfigureGraph() {
      for (const x of bridges) if (x.alive && inLoadedGraph(app, x.node)) x.migrateFollows?.();
      for (const n of app.graph?._nodes || []) n.__efaSteps?.hideFields?.();
      const b = elect(app);
      if (b?.alive) { b.hookSources?.(); b.syncSteps?.(); }
    },
    async afterLoadGraph() {
      const b = elect(app);
      b?.claimSoon?.();
    },
  });
}

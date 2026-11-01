import { h, fmtSec } from "./ui/lib.js";
import * as S from "./ui/state.js";
import { previewSimLook } from "./ui/stage.js";
import { fillRows } from "./fill.js";
import { styleDef, styleOf, startPreset, DIRECT_LOOK } from "./ui/presets.js";

export const FOLLOW_STRENGTH = "Follows motion: strength";
export const FOLLOW_LAG = "Follows motion: lag";
export const PREMASK = "Particle premask";
export const SHAPE = "Particle emitter";
export const AREA = "Particle area";
export const AI_GUIDE = "Guide for the AI (particles / drawn path / object shape / none)";
export const GUIDE_STRENGTH = "Guide strength (on black)";
export const ALSO_DRAW = "Particles: also draw (over the AI element)";
export const DISSOLVE_BG = "Dissolve: background behind the object (auto / smooth / structured)";
export const PANEL_ADV = [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, SHAPE, AREA, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG];

export function emitterKind(st) {
  if (!st) return null;
  if (st.variant === "dissolve") return "dissolve";
  if (st.settings?.Particles || st.variant === "climb") return "particles";
  return "ltx";
}
export const guideStyle = (st) => emitterKind(st) === "ltx" && st.variant !== "climb";
export const guideDefault = (st) => st?.settings?.[AI_GUIDE] || (emitterKind(st) === "particles" ? "particles" : "none");
export const guideNow = (st, e) => e?.adv?.[AI_GUIDE] || guideDefault(st);
export const effStyle = (st, e) => (e && st && st === styleDef(e.kind, e.style) ? styleOf(e) : st);
export function ownValues(f) {
  try {
    const o = JSON.parse(f?.emitter_values || "{}");
    return o && typeof o === "object" && !Array.isArray(o) ? o : {};
  } catch { return {}; }
}

export const SHAPES = [
  ["point A", "Point", "a click"],
  ["line A-B", "Between two points", "click A, Shift-click B"],
  ["drawing", "Drawn path", "the brush (Advanced)"],
  ["area", "Area", "the area dragged in the canvas"],
  ["whole frame", "Whole frame", "nothing"],
  ["object mask", "On the object", "the object's mask"],
  ["object contour", "Object outline", "the object's mask"],
  ["object bottom edge", "Object bottom edge", "the object's mask"],
  ["groups", "Groups in depth", "a list of places"],
];
export const shapeOf = (e, st) => e?.adv?.[SHAPE] || st?.settings?.[SHAPE] || "point A";
export const shapeName = (v) => SHAPES.find(([k]) => k === v)?.[1] || v;
export const shapeFixed = (st) => !!st && (st.placement === "ab" || st.variant === "climb");

const r = (v, d = 2) => (v == null || Number.isNaN(+v) ? "" : String(+(+v).toFixed(d)));
const hex = (c) => "#" + c.map((x) => Math.round(Math.min(1, Math.max(0, x)) * 255).toString(16).padStart(2, "0")).join("");
const rgb = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16) / 255);
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const DRAWN = new Set(["glow", "trail", "opacity", "shutter", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "color_var"]);

const key = (k, label, min, max, step, o = {}) => ({ k, label, min, max, step, ...o });
const PARTICLES = {
  source: { main: [key("radius", "Emitter size", 0, 300, 1, { unit: "px", tip: "How far around the point or the line they are born (At 1080 px)" })],
    more: [key("max_particles", "Max. alive at once", 100, 40000, 100, { tip: "More would be dropped (rain over a long clip)" })] },
  emission: {
    main: [key("rate", "Rate", 0, 2000, 1, { unit: "/s", tip: "Particles per second" }),
      key("burst", "Burst", 0, 2000, 1, { unit: "", tip: "Particles at once" })],
    more: [key("burst_at", "Burst at", 0, 10, 0.05, { unit: "s", tip: "When the burst comes, after the start" })],
  },
  motion: {
    main: [key("spread", "Spread", 0, 180, 1, { unit: "°", tip: "How far the particles fan out around the direction" }),
      key("speed", "Speed", 0, 3000, 5, { unit: "px/s", tip: "How fast they leave the emitter (At 1080 px)" }),
      key("speed_var", "± Variation", 0, 1, 0.05, { tip: "0: all equally fast, 0.5: between half and one and a half times" })],
    more: [key("lift", "Lift", -90, 90, 1, { unit: "°", tip: "Against motion: the spray tilted upwards" }),
      key("spread_falloff", "Bunch to the centre", 0, 1, 0.05, { tip: "0: evenly over the spread, 1: most of them near the direction" }),
      key("speed_end", "Speed at the end", 0, 2, 0.05, { tip: "Times the speed at birth: 0.2 = they come to rest, 1 = as they are" }),
      key("max_speed", "Speed limit", 0, 3000, 5, { unit: "px/s", tip: "No particle gets faster (wind, vortex, attract); 0 = off" })],
  },
  particle: {
    main: [key("life", "Life", 0.05, 60, 0.05, { unit: "s" }), key("life_var", "± Life", 0, 1, 0.05),
      key("size", "Size", 0.2, 60, 0.1, { unit: "px" }), key("size_var", "± Size", 0, 1, 0.05),
      key("size_start", "Size at birth", 0, 5, 0.05, { tip: "Times the size, over the life to the end value" }),
      key("size_end", "Size at the end", 0, 8, 0.05)],
    more: [key("trail", "Trail", 0, 60, 1, { unit: "frames", int: true }), key("glow", "Glow", 0, 5, 0.05),
      key("flicker", "Flicker", 0, 1, 0.05), key("flicker_hz", "Flicker speed", 0.1, 20, 0.1, { unit: "Hz" }),
      key("flicker_size", "Flicker by size", 0, 2, 0.05, { tip: "Small particles flicker faster, large ones slower (fire)" }),
      key("fine_share", "Small particles", 0, 1, 0.05, { tip: "Share of a second, smaller class: quick tongues beside the big body (fire)" }),
      key("fine_size", "Small: size", 0.05, 1, 0.05, { tip: "Times the size" }),
      key("fine_speed", "Small: speed", 0.2, 4, 0.05, { tip: "Times the speed" }),
      key("fine_life", "Small: life", 0.1, 2, 0.05, { tip: "Times the life" }),
      key("fade_in", "Fade in", 0, 1, 0.01, { tip: "Share of the life" }), key("fade_out", "Fade out", 0, 1, 0.01, { tip: "Share of the life" }),
      key("shutter", "Motion blur", 0, 5, 0.1, { tip: "The streak over this many frames of motion" }),
      key("opacity", "Opacity", 0, 1, 0.01), key("color_var", "Colour variation", 0, 1, 0.05, { tip: "Each particle a bit brighter or darker" }),
      key("spin", "Spin", 0, 720, 5, { unit: "°/s", tip: "How fast a particle turns at most; 0 = not at all (calm smoke, flakes)" })],
  },
  merge: {
    main: [key("blob", "Blur", 0, 60, 0.5, { unit: "px", tip: "The particles blurred together into one body (At 1080 px)" }),
      key("blob_choke", "Choke", 0, 1, 0.01, { tip: "Where the blurred body ends: higher = thinner, lone particles vanish sooner" }),
      key("blob_soft", "Edge", 0, 0.5, 0.01, { tip: "Width of the edge: small = hard liquid edge" })],
    more: [key("blob_fill", "Fill", 0, 1, 0.05, { tip: "1: evenly dense (liquid), 0: as dense as the blur (smoke)" }),
      key("blob_life", "Only while young", 0, 1, 0.05, { tip: "0: all merge. Above 0 a particle merges while young and is apart from this share of its life on: tongues tear off at the top (fire)" })],
  },
  forces: {
    main: [key("gravity", "Gravity", -3000, 3000, 10, { unit: "px/s²", tip: "Negative rises (smoke, fire)" }),
      key("wind", "Wind", -1500, 1500, 5, { unit: "px/s²", tip: "Sideways, + = to the right", get: (P) => P.wind?.[0] ?? 0,
        put: (P, v) => [v, P.wind?.[1] ?? 0] }),
      key("drag", "Drag", 0, 10, 0.05, { tip: "Air resistance per second" }),
      key("turbulence", "Turbulence", 0, 1500, 5, { unit: "px/s", tip: "Swirling (curl noise)" }),
      key("turb_scale", "Turbulence size", 10, 800, 5, { unit: "px" })],
    more: [key("windy", "Wind up/down", -1500, 1500, 5, { unit: "px/s²", tip: "+ = down", k2: "wind", get: (P) => P.wind?.[1] ?? 0,
        put: (P, v) => [P.wind?.[0] ?? 0, v] }),
      key("turb_speed", "Turbulence change", 0, 3, 0.05),
      key("vortex", "Vortex", -3000, 3000, 10, { tip: "Swirl around the emitter" }),
      key("attract", "Attract to B", 0, 6000, 20, { tip: "Pull towards point B" }),
      key("flock", "Flocking", 0, 1, 0.05, { tip: "Neighbours pull together: streams wander, clump and break into drops" }),
      key("flock_radius", "Flocking: reach", 5, 200, 1, { unit: "px" }),
      key("flock_cohesion", "Flocking: pull", 0, 20, 0.1),
      key("turb_fade", "Turbulence fades in", 0, 1, 0.05, { tip: "Share of the life: calm at birth, the swirl comes later" }),
      key("turb_drag", "Drag calms turbulence", 0, 1, 0.05, { tip: "1: the swirl slows down with the drag, as the speed does" })],
  },
  contact: {
    main: [key("restitution", "Bounce", 0, 1, 0.05)],
    more: [key("land_fade", "Lying time", 0, 20, 0.1, { unit: "s", tip: "How long a particle that sticks stays before it fades" }),
      key("depth_spread", "Depth spread", 0, 0.5, 0.01, { tip: "Random spread of the particles' depth around the emitter" }),
      key("friction", "Friction", 0, 1, 0.05)],
  },
};
const PATH = {
  particle: {
    main: [key("width", "Width", 0.3, 10, 0.1, { unit: "px" }), key("glow", "Glow", 0, 5, 0.05),
      key("roughness", "Jaggedness", 0, 1, 0.01), key("branches", "Branches", 0, 20, 1, { int: true })],
    more: [key("reroll_frames", "New shape every", 1, 12, 1, { unit: "frames", int: true })],
  },
};
const DISSOLVE = {
  emission: {
    main: [key("density", "Particles", 0, 1, 0.01, { tip: "Share of the crumbling pixels that fly off as particles" }),
      key("edge_noise", "Ragged edge", 0, 1, 0.05, { tip: "0: a straight front, 1: torn by noise" })],
    more: [key("noise_size", "Size of the tears", 0.02, 1, 0.01)],
  },
  motion: {
    main: [key("push", "Speed", 0, 1500, 5, { unit: "px/s", tip: "Along the direction" }), key("lift", "Lift", -500, 500, 5, { unit: "px/s" }),
      key("spread", "Spread", 0, 600, 5, { unit: "px/s", tip: "Random at birth" })],
    more: [],
  },
  particle: {
    main: [key("life", "Life", 0.1, 10, 0.05, { unit: "s" }), key("size", "Size", 0, 10, 0.1, { unit: "px" }),
      key("fade_out", "Fade out", 0, 1, 0.01), key("glow", "Glowing edge", 0, 5, 0.05)],
    more: [key("glow_width", "Width of the glow", 0, 0.5, 0.01), key("tint", "Glow colour over the life", 0, 1, 0.05)],
  },
  forces: {
    main: [key("gravity", "Gravity", -1500, 1500, 5, { unit: "px/s²", tip: "Negative rises (ash)" }), key("drag", "Drag", 0, 10, 0.05),
      key("turbulence", "Turbulence", 0, 1500, 5, { unit: "px/s" }), key("turb_scale", "Turbulence size", 10, 800, 5, { unit: "px" })],
    more: [],
  },
};

const MODES = [["angle", "Angle", "The direction of the arrow"], ["outward", "Outward", "Away from the object's outline"],
  ["against motion", "Against motion", "Sprayed backwards from the emitter's motion (grinding)"], ["random", "Random", "Every direction"]];
const COLLIDE = [["none", "None"], ["bounce", "Bounce"], ["stick", "Stick"], ["slide", "Slide"], ["die", "Die"]];
const SPRITES = ["soft", "dot", "flake", "puff", "wisp", "streak", "spark", "chunk"];
const EXPL = {
  inherit: "How much of the emitter's movement the particles take along. 0: they fly on their own. 1: they move with it.",
  carry: "Moving things in the clip push the particles along, e.g. a hand sweeping through smoke.",
  ltx: "The AI gets the path of the movement, so the effect leans and trails behind.",
  strength: "How strongly and how late the effect trails behind fast movement.",
};

const GUIDES = [["none", "Free"], ["object shape", "Object shape"], ["drawn path", "Drawn path"], ["particles", "Particles"]];
const GUIDE_PRESETS = ["fire", "embers", "sparks", "grinding sparks", "smoke", "dust burst", "magic dust", "aura", "liquid", "debris",
  "snow", "rain", "fireflies", "lightning", "cracks", "frost", "lightning climb", "energy A-B"];
const GUIDE_EXPL = {
  none: "The AI paints the element freely from the prompt.",
  "object shape": "The AI shapes the element to the object it sits on (a flame wraps round the fist): the object's depth guides it, only near the object. Needs the object: click it in Position.",
  "drawn path": "The AI follows the strokes you paint on the canvas while this step is open.",
  particles: "The particles guide the AI: the emitter below shapes where and how it moves, the AI paints the look.",
};

function write(ctx, own) {
  const keys = Object.keys(own);
  ctx.api.setFx("emitter_values", keys.length ? JSON.stringify(own) : "");
}
const setOwn = (ctx, k, v) => { const o = { ...ctx.own }; if (v === undefined) delete o[k]; else o[k] = v; write(ctx, o); };
function setEffect(fn, reason) {
  S.change((sh) => { const x = sh.effects.find((y) => y.id === sh.active); if (x) fn(x); }, reason);
}
export function setAdv(name, v) {
  setEffect((x) => { x.adv = { ...x.adv }; if (v === undefined) delete x.adv[name]; else x.adv[name] = v; }, "emitter");
}

function numRow(ctx, c) {
  const P = ctx.P, B = ctx.B;
  const get = c.get || ((p) => p[c.k]);
  let cur = get(P), base = get(B);
  let changed = (c.k2 || c.k) in ctx.own && !same(get(P), get(B));
  let set = (v) => setOwn(ctx, c.k2 || c.k, c.put ? c.put(P, v) : v);
  let reset = () => {
    if (!c.put) return setOwn(ctx, c.k, undefined);
    const back = c.put(P, get(B));
    setOwn(ctx, c.k2 || c.k, same(back, B[c.k2 || c.k]) ? undefined : back);
  };
  if (c.k === "rate" || c.k === "burst") {
    const a = ctx.amount || 1;
    cur = P[c.k] * a; base = B[c.k] * a;
    changed = c.k in ctx.own;
    set = (v) => setOwn(ctx, c.k, v / a);
  }
  const lo = Math.min(c.min, cur, base), hi = Math.max(c.max, cur, base);
  const num = h("input", { class: "text em-num", type: "number", step: String(c.step), value: r(cur, 3), "aria-label": c.label,
    onchange: (ev) => { const v = +ev.target.value; if (Number.isFinite(v)) set(c.int ? Math.round(v) : v); } });
  const at = hi > lo ? Math.min(1, Math.max(0, (base - lo) / (hi - lo))) : 0;
  const tick = h("span", { class: "em-tick", title: `The style's value: ${r(base, 3)}`, style: { left: `calc(${at.toFixed(4)} * (100% - 14px) + 6px)` } });
  const drawn = DRAWN.has(c.k2 || c.k) && !c.put;
  const range = h("input", { type: "range", min: String(lo), max: String(hi), step: String(c.step), value: String(cur), "aria-label": c.label,
    oninput: (ev) => { num.value = r(+ev.target.value, 3); if (drawn) previewSimLook({ [c.k]: +ev.target.value }); },
    onchange: (ev) => set(c.int ? Math.round(+ev.target.value) : +ev.target.value) });
  return h("div", { class: "em-row" + (changed ? " changed" : ""), "data-key": c.k },
    h("span", { class: "em-label", title: c.tip || null }, c.label, c.unit ? h("span", { class: "muted" }, ` ${c.unit}`) : null),
    h("span", { class: "em-slider" }, range, tick), num,
    changed ? h("button", { class: "em-reset", title: `Back to the style's value (${r(base, 3)})`, "aria-label": `Reset ${c.label}`, onclick: reset }, "×")
      : h("span", { class: "em-base", title: "The style's value" }, ""));
}
function choiceRow(ctx, k, label, options, tip) {
  const cur = ctx.P[k], changed = k in ctx.own && ctx.P[k] !== ctx.B[k];
  return h("div", { class: "em-row choice wide" + (changed ? " changed" : ""), "data-key": k },
    h("span", { class: "em-label", title: tip || null }, label),
    ctx.ui.seg(label, options, cur, (v) => setOwn(ctx, k, v === ctx.B[k] ? undefined : v)),
    changed ? h("button", { class: "em-reset", title: `Back to the style's value (${ctx.B[k]})`, onclick: () => setOwn(ctx, k, undefined) }, "×") : h("span", {}));
}
function spriteRow(ctx) {
  const cur = ctx.P.sprite, changed = "sprite" in ctx.own && cur !== ctx.B.sprite;
  const sel = h("select", { class: "text", "aria-label": "Sprite", onchange: (ev) => setOwn(ctx, "sprite", ev.target.value === ctx.B.sprite ? undefined : ev.target.value) },
    ...[...new Set([...SPRITES, cur])].map((s) => h("option", { value: s, selected: s === cur }, s)));
  return h("div", { class: "em-row choice" + (changed ? " changed" : ""), "data-key": "sprite" }, h("span", { class: "em-label" }, "Sprite"), sel,
    changed ? h("button", { class: "em-reset", onclick: () => setOwn(ctx, "sprite", undefined) }, "×") : h("span", {}));
}
function colorsRow(ctx) {
  const stops = ctx.P.colors || [], changed = "colors" in ctx.own && !same(ctx.P.colors, ctx.B.colors);
  const put = (i, v) => setOwn(ctx, "colors", stops.map(([t, c], j) => [t, j === i ? rgb(v) : c]));
  return h("div", { class: "em-row choice" + (changed ? " changed" : ""), "data-key": "colors" },
    h("span", { class: "em-label", title: "From birth (left) to the end of the life (right)" }, "Colour over life"),
    h("div", { class: "em-stops" }, ...stops.map(([t, c], i) => h("input", { type: "color", value: hex(c), title: `at ${Math.round(t * 100)} % of the life`,
      "aria-label": `Colour at ${Math.round(t * 100)} % of the life`, onchange: (ev) => put(i, ev.target.value) }))),
    changed ? h("button", { class: "em-reset", onclick: () => setOwn(ctx, "colors", undefined) }, "×") : h("span", {}));
}
function hexRow(ctx, k, label) {
  const cur = ctx.P[k], changed = k in ctx.own && cur !== ctx.B[k];
  return h("div", { class: "em-row choice" + (changed ? " changed" : ""), "data-key": k }, h("span", { class: "em-label" }, label),
    h("input", { type: "color", value: String(cur || "#ffffff"), "aria-label": label, onchange: (ev) => setOwn(ctx, k, ev.target.value) }),
    changed ? h("button", { class: "em-reset", onclick: () => setOwn(ctx, k, undefined) }, "×") : h("span", {}));
}
function dialRow(ctx, label, value, dflt, onset, tip) {
  const deg = value ?? dflt ?? 0;
  const needle = h("span", { class: "em-needle", style: { transform: `rotate(${deg}deg)` } });
  const num = h("input", { class: "text em-num", type: "number", min: "0", max: "359", step: "1", value: String(Math.round(deg)), "aria-label": label,
    onchange: (ev) => onset(((Math.round(+ev.target.value) % 360) + 360) % 360) });
  const angle = (ev, el) => {
    const b = el.getBoundingClientRect();
    return ((Math.round(Math.atan2(ev.clientX - (b.left + b.width / 2), -(ev.clientY - (b.top + b.height / 2))) * 180 / Math.PI) % 360) + 360) % 360;
  };
  const dial = h("span", { class: "em-dial", role: "slider", tabindex: "0", "aria-label": label, "aria-valuenow": String(Math.round(deg)), title: "Drag around: 0 up, 90 right",
    onpointerdown: (ev) => {
      const el = ev.currentTarget;
      el.setPointerCapture(ev.pointerId);
      let last = deg;
      const move = (m) => { last = angle(m, el); needle.style.transform = `rotate(${last}deg)`; num.value = String(last); };
      const up = () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); onset(last); };
      el.addEventListener("pointermove", move);
      el.addEventListener("pointerup", up);
      move(ev);
    },
    onkeydown: (ev) => { const d = { ArrowLeft: -5, ArrowDown: -5, ArrowRight: 5, ArrowUp: 5 }[ev.key]; if (d) { ev.preventDefault(); onset((deg + d + 360) % 360); } } }, needle);
  const changed = value != null && Math.round(value) !== Math.round(dflt ?? -1);
  return h("div", { class: "em-row dial" + (changed ? " changed" : ""), "data-key": "direction" },
    h("span", { class: "em-label", title: tip || null }, label, h("span", { class: "muted" }, " °")), dial, num,
    changed ? h("button", { class: "em-reset", title: `Back to the style's direction (${Math.round(dflt ?? 0)}°)`, onclick: () => onset(null) }, "×") : h("span", {}));
}
const setDir = (v) => setEffect((x) => { x.dir = v; }, "emitter");
function depthWrap(ctx, cur, base, mine, set) {
  const num = h("input", { class: "text em-num", type: "number", step: "0.01", value: r(cur, 3), "aria-label": "Depth offset", onchange: (ev) => set(+ev.target.value) });
  const range = h("input", { type: "range", min: String(Math.min(-1, cur)), max: String(Math.max(1, cur)), step: "0.01", value: String(cur), "aria-label": "Depth offset",
    oninput: (ev) => { num.value = r(+ev.target.value, 3); }, onchange: (ev) => set(+ev.target.value) });
  return h("div", { class: "em-row" + (mine ? " changed" : ""), "data-key": "depth_offset" },
    h("span", { class: "em-label", title: "+ = nearer, less hidden by the scene" }, "Depth offset"), range, num,
    mine ? h("button", { class: "em-reset", title: `Back to the style's value (${r(base, 3)})`, onclick: () => set(base) }, "×") : h("span", {}));
}
function advNum(ctx, name, label, min, max, step, dflt, tip) {
  const cur = ctx.e.adv?.[name] ?? dflt, changed = ctx.e.adv?.[name] != null && ctx.e.adv[name] !== dflt;
  const set = (v) => setAdv(name, v === dflt ? undefined : v);
  const num = h("input", { class: "text em-num", type: "number", step: String(step), value: r(cur, 3), "aria-label": label, onchange: (ev) => set(+ev.target.value) });
  const range = h("input", { type: "range", min: String(min), max: String(max), step: String(step), value: String(cur), "aria-label": label,
    oninput: (ev) => { num.value = r(+ev.target.value, 3); }, onchange: (ev) => set(+ev.target.value) });
  return h("div", { class: "em-row" + (changed ? " changed" : ""), "data-key": name }, h("span", { class: "em-label", title: tip || null }, label), range, num,
    changed ? h("button", { class: "em-reset", onclick: () => setAdv(name, undefined) }, "×") : h("span", {}));
}

const rows = (ctx, list) => list.map((c) => numRow(ctx, c));
const rowName = (x) => x?.querySelector?.(".em-label")?.firstChild?.textContent || x?.querySelector?.(".toggle span:last-child")?.textContent || "";
function box(ctx, key_, title, main, more, explain, summary = "") {
  const n = [...main, ...more].filter((x) => x?.classList?.contains("changed")).length;
  const names = more.map(rowName).filter(Boolean);
  return ctx.ui.group(`em-${key_}`, title, () => [
    explain ? h("p", { class: "muted small" }, explain) : null,
    ...main,
    more.length ? ctx.ui.group(`em-${key_}-more`, `More ${title.replace(/ \(.*\)$/, "").toLowerCase()} settings (${more.length})`, () => more,
      { preview: names.join(" · "), badge: more.filter((x) => x?.classList?.contains("changed")).length ? "changed" : "", cls: "em-more" }) : null,
  ], { hint: summary, badge: n ? `${n} changed` : "", cls: "em-group" });
}
const num_ = (v, d = 2) => (v == null || Number.isNaN(+v) ? "–" : String(+(+v).toFixed(d)).replace(/^-/, "−"));
const nonzero = (pairs) => pairs.filter(([, v]) => Math.abs(+v || 0) > 1e-9).map(([t, v, u = ""]) => `${t} ${num_(v)}${u}`);
function timeSpan(ctx) {
  const t = ctx.e.timing, c = S.getShot().clip, end = t.end ?? c?.seconds;
  return `${fmtSec(t.start || 0)}–${end != null ? fmtSec(end) : "end"}`;
}
function seedText(ctx) {
  const v = ctx.f?.particle_seed;
  return `seed ${Number.isFinite(+v) && v !== "" ? +v : 42}`;
}
const pname = (list, v) => list.find(([k]) => k === v)?.[1] || v;
function timing(ctx) {
  const t = ctx.e.timing, c = S.getShot().clip;
  const end = t.end ?? c?.seconds;
  return h("p", { class: "muted small" }, `From ${fmtSec(t.start || 0)} to ${end != null ? fmtSec(end) : "the end"}: drag the ends of its bar in the timeline.`);
}

function guideRows(ctx) {
  const { e, ui } = ctx, st = ctx.st0 || ctx.st;
  const cur = guideNow(st, e), dflt = guideDefault(st);
  const set = (v) => ctx.api.setFx("guide", v === dflt ? "style default" : v);
  const out = [h("div", { class: "em-row choice wide" + (cur !== dflt ? " changed" : ""), "data-key": "guide" },
    h("span", { class: "em-label", title: "What guides the AI where it paints the element" }, "Guide for the AI"),
    ui.seg("Guide for the AI", GUIDES, cur, set),
    cur !== dflt ? h("button", { class: "em-reset", title: `Back to the style's guide (${GUIDES.find(([k]) => k === dflt)?.[1] || dflt})`, onclick: () => set(dflt) }, "×")
      : h("span", {})),
  h("p", { class: "muted small" }, GUIDE_EXPL[cur] || "")];
  if (aiOff(ctx)) out.push(h("p", { class: "muted small" }, "Counts when the AI makes the element (Made by: AI)."));
  if (cur === "drawn path") out.push(h("p", { class: "muted small" }, `${e.paint?.guide?.length || 0} strokes painted.`));
  if (cur !== "none") out.push(advNum(ctx, GUIDE_STRENGTH, "Guide strength", 0, 1, 0.05, 1.0,
    "How strictly the AI keeps to the guide on black: 1 = fully, lower leaves it more of its own look"));
  return out;
}

function startRow(ctx) {
  const { f } = ctx, st = ctx.st0 || ctx.st, own = startPreset(st);
  const pick = f.guide_particles && f.guide_particles !== "style default" ? f.guide_particles : own;
  const sel = h("select", { class: "text", "aria-label": "Particles it starts from",
    onchange: (ev) => ctx.api.setFx("guide_particles", ev.target.value === own ? "style default" : ev.target.value) },
    ...[...new Set([...GUIDE_PRESETS, own])].map((p) => h("option", { value: p, selected: p === pick }, p === own ? `${p} (style default)` : p)));
  return h("div", { class: "em-row choice" + (pick !== own ? " changed" : ""), "data-key": "guide_particles" },
    h("span", { class: "em-label", title: "The particle preset this effect starts from: the values below are its own" }, "Particles"), sel,
    pick !== own ? h("button", { class: "em-reset", title: `Back to the style's particles (${own})`, onclick: () => ctx.api.setFx("guide_particles", "style default") }, "×")
      : h("span", {}));
}
const directLook = (ctx) => (ctx.e.adv?.[DIRECT_LOOK] ?? ctx.st.settings?.[DIRECT_LOOK]) === true;
const aiOff = (ctx) => directLook(ctx);
export const particlesUsed = (ctx) => directLook(ctx) || guideNow(ctx.st0 || ctx.st, ctx.e) === "particles" || ctx.e.adv?.[ALSO_DRAW] === true;
function alsoDrawRow(ctx) {
  const { e, ui } = ctx;
  if (directLook(ctx)) return null;
  return ui.toggle("Also draw the particles", e.adv?.[ALSO_DRAW] === true, (v) => setAlsoDraw(ctx, v),
    "The particles drawn over the AI's element as well, with their own pass \"particles\". Off: only the AI's element");
}
function setAlsoDraw(ctx, v) {
  const st = ctx.st0 || ctx.st;
  setEffect((x) => {
    x.adv = { ...x.adv };
    if (v) x.adv[ALSO_DRAW] = true; else delete x.adv[ALSO_DRAW];
    if (!st.settings?.Particles && guideNow(st, x) !== "particles" && !directLook({ ...ctx, e: x })) {
      if (v) { x.adv.Particles = true; x.adv["Particle preset"] = ctx.f.guide_particles && ctx.f.guide_particles !== "style default" ? ctx.f.guide_particles : startPreset(st); }
      else { delete x.adv.Particles; delete x.adv["Particle preset"]; }
    }
  }, "emitter");
}

const BG_CHOICES = [["auto", "Auto"], ["smooth", "Smooth"], ["structured", "Structured"]];
const BG_EXPL = {
  auto: "Measured around the object: a smooth background is filled from around it, a structured one gets the AI's clean plate.",
  smooth: "Sky, wall, studio: filled from around the object, no AI run (faster).",
  structured: "Leaves, crowd, pattern: the AI paints what was always behind the object.",
};
function backgroundRows(ctx) {
  const { e, ui } = ctx;
  const cur = e.adv?.[DISSOLVE_BG] || "auto";
  const set = (v) => setAdv(DISSOLVE_BG, v === "auto" ? undefined : v);
  return [h("div", { class: "em-row choice wide" + (cur !== "auto" ? " changed" : ""), "data-key": "background" },
    h("span", { class: "em-label", title: "What is behind the object where it never moves away" }, "Background"),
    ui.seg("Background", BG_CHOICES, cur, set),
    cur !== "auto" ? h("button", { class: "em-reset", title: "Back to auto", onclick: () => set("auto") }, "×") : h("span", {})),
  h("p", { class: "muted small" }, BG_EXPL[cur])];
}

function changedCount(ctx) {
  const e = ctx.e;
  let n = Object.keys(ctx.own).length;
  if (e.dir != null && !ctx.st.placement?.startsWith("ab")) n += Math.round(e.dir) !== Math.round(ctx.B?.direction ?? (ctx.kind === "dissolve" ? 90 : -1)) ? 1 : 0;
  if (e.depth) n += 1;
  for (const k of [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG]) if (e.adv?.[k] != null) n += 1;
  return n;
}
function resetAll(ctx) {
  ctx.api.setFx("emitter_values", "");
  setEffect((x) => {
    x.depth = 0;
    if (ctx.kind === "dissolve") x.dir = 90; else x.dir = null;
    x.adv = { ...x.adv };
    for (const k of [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH, ALSO_DRAW, DISSOLVE_BG]) delete x.adv[k];
  }, "emitter");
}

const ALL_PARTICLE_KEYS = [...Object.values(PARTICLES).flatMap((g) => [...g.main, ...g.more]),
  key("inherit", "Takes the emitter's motion", 0, 1, 0.05), key("motion_carry", "Carried by the clip", 0, 1, 0.05)];
function fillControls(ctx) {
  const a = ctx.amount || 1;
  const dirActs = ctx.P.direction_mode === "angle" || ctx.P.direction_mode === "against motion";
  const dir = dirActs && !ctx.st.placement?.startsWith("ab")
    ? [{ k: "direction", label: "Direction", min: 0, max: 359, step: 1, unit: "°", tip: "0 up, 90 right, 180 down, 270 left", int: true, angle: true,
      now: Math.round(ctx.e.dir ?? ctx.B.direction ?? 0) }] : [];
  return dir.concat(ALL_PARTICLE_KEYS.map((c) => {
    const get = c.get || ((p) => p[c.k]);
    const scale = c.k === "rate" || c.k === "burst" ? a : 1;
    const now = get(ctx.P);
    if (typeof now !== "number") return null;
    return { k: c.k, label: c.label, min: c.min, max: c.max, step: c.step, unit: c.unit || "", tip: c.tip || "", int: !!c.int, now: now * scale };
  }).filter(Boolean));
}
function applyFill(ctx, r) {
  const o = { ...ctx.own }, a = ctx.amount || 1;
  const before = { values: ctx.f?.emitter_values || "", dir: ctx.e.dir };
  const put = (k, v) => { if (same(v, ctx.B[k])) delete o[k]; else o[k] = v; };
  const wind = [...(ctx.P.wind || [0, 0])];
  for (const c of r.changes) {
    if (c.key === "direction") setDir(c.to);
    else if (c.key === "wind") wind[0] = c.to;
    else if (c.key === "windy") wind[1] = c.to;
    else put(c.key, c.key === "rate" || c.key === "burst" ? c.to / a : c.to);
  }
  if (r.changes.some((c) => c.key === "wind" || c.key === "windy")) put("wind", wind);
  if (r.mode) put("direction_mode", r.mode);
  if (r.collide) put("collide", r.collide);
  if (r.sprite) put("sprite", r.sprite);
  if (r.colors) put("colors", r.colors);
  write(ctx, o);
  return () => {
    ctx.api.setFx("emitter_values", before.values);
    if (r.changes.some((c) => c.key === "direction")) setDir(before.dir);
  };
}

export function basicFill(ctx) {
  if (ctx.kind !== "particles" || !ctx.P || !ctx.B || (ctx.P.path && ctx.P.path !== "particles")) return [];
  return [h("div", { class: "field fill-basic" }, ...fillRows(ctx, fillControls(ctx), (r) => applyFill(ctx, r), true))];
}

export function emitterPanel(ctx) {
  const { kind, st, e, P, B, ui } = ctx;
  const out = [];
  const n = P && B ? changedCount(ctx) : 0;
  out.push(h("div", { class: "em-head" }, h("span", { class: "label" }, "Emitter"),
    n ? h("span", { class: "muted small" }, `${n} changed · `, ui.link("Reset all", () => resetAll(ctx))) : h("span", { class: "muted small" }, "as the style has it")));
  if (!P || !B) {
    if (kind !== "dissolve") out.push(...guideRows(ctx), startRow(ctx));
    out.push(h("p", { class: "muted small" }, S.getShot().clip ? "The values show once the live preview has answered." : "Pick a clip: the values show with the live preview."));
    return out;
  }
  if (kind === "dissolve") return out.concat(dissolveGroups(ctx));
  if (!particlesUsed(ctx)) {
    out.push(h("p", { class: "muted small em-unused" }, "The AI paints this element freely: the particles below come in when they guide it, are drawn over it (Source) or make it (Made by: Particles only). ",
      ui.link("Let them guide the AI", () => ctx.api.setFx("guide", guideDefault(ctx.st0 || st) === "particles" ? "style default" : "particles"))));
  }
  return out.concat(fillRows(ctx, fillControls(ctx), (r) => applyFill(ctx, r)), particleGroups(ctx), P.path && P.path !== "particles" ? pathGroup(ctx) : []);
}

function particleGroups(ctx) {
  const { e, st, P, B, ui } = ctx;
  const G = PARTICLES;
  const dirActs = P.direction_mode === "angle" || P.direction_mode === "against motion";
  const amt = ctx.amount || 1;
  const sum = {
    source: [aiOff(ctx) ? "particles only" : `guide: ${pname(GUIDES, guideNow(ctx.st0 || st, e)).toLowerCase()}`,
      ctx.f.guide_particles && ctx.f.guide_particles !== "style default" ? ctx.f.guide_particles : startPreset(ctx.st0 || st),
      shapeName(shapeOf(e, st)), seedText(ctx)],
    emission: [P.rate > 0 ? `${num_(P.rate * amt, 0)} /s` : null, P.burst > 0 ? `${num_(P.burst * amt, 0)} at once` : null, timeSpan(ctx)],
    motion: [pname(MODES, P.direction_mode), `spread ${num_(P.spread, 0)}°`, `speed ${num_(P.speed, 0)} px/s`],
    particle: [`life ${num_(P.life)} s`, `size ${num_(P.size)} px`, P.trail > 0 ? `trail ${num_(P.trail, 0)}` : null],
    merge: [P.blob > 0 ? `blur ${num_(P.blob, 1)} px · choke ${num_(P.blob_choke)}` : "off"],
    forces: nonzero([["gravity", P.gravity], ["wind", P.wind?.[0]], ["turbulence", P.turbulence], ["drag", P.drag]]),
    contact: [P.collide === "none" ? "no collision" : pname(COLLIDE, P.collide), (e.adv?.[PREMASK] ?? true) ? null : "in front of all",
      Math.abs(P.depth_offset || 0) > 1e-6 ? `depth ${num_(P.depth_offset)}` : null],
  };
  const line = (k) => (sum[k].filter(Boolean).join(" · ") || "none");
  return [
    box(ctx, "source", "Source", [
      ...guideRows(ctx),
      startRow(ctx),
      alsoDrawRow(ctx),
      h("div", { class: "em-row choice" }, h("span", { class: "em-label" }, "Shape"),
        h("span", {}, shapeName(shapeOf(e, st)), " · ", ui.link("change in Position", () => ui.open("position")))),
      ...ctx.extras.seed(),
    ], rows(ctx, G.source.more), "", line("source")),
    box(ctx, "emission", "Emission", [...rows(ctx, G.emission.main), timing(ctx), ...ctx.extras.preroll()], rows(ctx, G.emission.more), "", line("emission")),
    box(ctx, "motion", "Motion", [
      choiceRow(ctx, "direction_mode", "Mode", MODES),
      dialRow(ctx, "Direction", e.dir, B.direction, setDir, dirActs ? "Which way they fly: the canvas arrow"
        : `Which way they fly: the canvas arrow (with the mode Angle or Against motion; ${pname(MODES, P.direction_mode)} sets its own)`),
      ...rows(ctx, G.motion.main),
      h("div", { class: "label sub" }, "Follows motion"),
      numRow(ctx, key("inherit", "Takes the emitter's motion", 0, 1, 0.05)), h("p", { class: "muted small" }, EXPL.inherit),
      numRow(ctx, key("motion_carry", "Carried by the clip", 0, 1, 0.05)), h("p", { class: "muted small" }, EXPL.carry),
      ...aiFollowRows(ctx),
    ].filter(Boolean), rows(ctx, G.motion.more), "", line("motion")),
    box(ctx, "particle", "Particle", [...rows(ctx, G.particle.main), colorsRow(ctx)], [spriteRow(ctx), ...rows(ctx, G.particle.more)], "", line("particle")),
    box(ctx, "merge", "Merge (liquid)", [
      ui.toggle("Merge into one body", P.blob > 0, (v) => setOwn(ctx, "blob", v ? (B.blob > 0 ? B.blob : 8) : 0),
        "The particles blurred together and choked: drops, thick smoke, flame tongues"),
      ...rows(ctx, G.merge.main),
    ], rows(ctx, G.merge.more), "", line("merge")),
    box(ctx, "forces", "Forces", rows(ctx, G.forces.main), rows(ctx, G.forces.more), "", line("forces")),
    box(ctx, "contact", "Contact & depth", [choiceRow(ctx, "collide", "Collision", COLLIDE, "What a particle does where it meets the scene (depth)"),
      ...rows(ctx, G.contact.main), depthWrapOf(ctx)],
    [...rows(ctx, G.contact.more), ui.toggle("Hidden by the scene", e.adv?.[PREMASK] ?? true, (v) => setAdv(PREMASK, v ? undefined : false),
      "Off: the particles stay in front of everything")], "", line("contact")),
  ];
}
const depthBase = new Map();
function depthWrapOf(ctx) {
  const mine = +(ctx.e.depth || 0);
  if (ctx.fresh || !depthBase.has(ctx.e.id)) depthBase.set(ctx.e.id, (ctx.P.depth_offset ?? 0) - mine);
  const base = depthBase.get(ctx.e.id), cur = base + mine;
  return depthWrap(ctx, cur, base, mine, (v) => setEffect((x) => { x.depth = +(v - base).toFixed(3); }, "emitter"));
}
function pathGroup(ctx) {
  return [box(ctx, "path", "Paths", [h("p", { class: "muted small" }, ctx.st.variant === "climb" ? "It climbs the thin parts of the object you clicked."
      : "From point A to point B."), ...rows(ctx, PATH.particle.main)], rows(ctx, PATH.particle.more), "",
    `${ctx.st.variant === "climb" ? "climbs the object" : "A to B"} · width ${num_(ctx.P.width)} px · ${num_(ctx.P.branches, 0)} branches`)];
}
function aiFollowRows(ctx) {
  const { e, f, ui } = ctx;
  const on = !!f.follows_motion, parts = guideNow(ctx.st0 || ctx.st, e) === "particles";
  return [h("div", { class: "label sub" }, "Follows motion (AI)"),
    ui.toggle("Follows motion", on, (v) => ctx.api.setFx("follows_motion", v), "The AI gets the path of the movement"),
    h("p", { class: "muted small" }, aiOff(ctx) ? "Counts when the AI makes the element (Made by: AI)."
      : parts ? "With the particle guide the particles carry the motion (above); this counts with another guide or none." : EXPL.ltx),
    on ? advNum(ctx, FOLLOW_STRENGTH, "Strength", 0, 3, 0.05, 1.0) : null,
    on ? advNum(ctx, FOLLOW_LAG, "Lag", 0, 1, 0.05, 0.6) : null,
    on ? h("p", { class: "muted small" }, EXPL.strength) : null];
}
function dissolveGroups(ctx) {
  const G = DISSOLVE;
  return [
    box(ctx, "source", "Source", [h("p", { class: "muted small" }, "The object you clicked: its mask crumbles."), ...backgroundRows(ctx),
      ...ctx.extras.seed()], [], "", [`background ${pname(BG_CHOICES, ctx.e.adv?.[DISSOLVE_BG] || "auto").toLowerCase()}`, seedText(ctx)].join(" · ")),
    box(ctx, "emission", "Emission", [...rows(ctx, G.emission.main), timing(ctx)], rows(ctx, G.emission.more), "",
      [`particles ${num_(ctx.P.density)}`, `ragged ${num_(ctx.P.edge_noise)}`, timeSpan(ctx)].join(" · ")),
    box(ctx, "motion", "Motion", [
      dialRow(ctx, "Direction", ctx.e.dir, 90, (v) => setDir(v ?? 90), "Which way it crumbles: the canvas arrow"),
      ...rows(ctx, G.motion.main),
      h("div", { class: "label sub" }, "Follows motion"),
      numRow(ctx, key("inherit", "Takes the object's motion", 0, 1, 0.05)), h("p", { class: "muted small" }, EXPL.inherit.replace("emitter's", "object's")),
      numRow(ctx, key("motion_carry", "Carried by the clip", 0, 1, 0.05)), h("p", { class: "muted small" }, EXPL.carry),
    ], [], "", [`${Math.round(ctx.e.dir ?? 90)}°`, `${num_(ctx.P.push, 0)} px/s`].join(" · ")),
    box(ctx, "particle", "Particle", [...rows(ctx, G.particle.main), hexRow(ctx, "glow_color", "Glow colour")], rows(ctx, G.particle.more), "",
      [`life ${num_(ctx.P.life)} s`, `size ${num_(ctx.P.size)} px`].join(" · ")),
    box(ctx, "forces", "Forces", rows(ctx, G.forces.main), [], "",
      nonzero([["gravity", ctx.P.gravity], ["turbulence", ctx.P.turbulence], ["drag", ctx.P.drag]]).join(" · ") || "none"),
  ];
}

import { h, postJSON } from "./ui/lib.js";
import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { hasBonsai } from "./ui/enhance.js";

const MODES = ["angle", "outward", "against motion", "random"];
const COLLIDE = ["none", "bounce", "stick", "slide", "die"];
const SPRITES = ["soft", "dot", "flake", "puff", "wisp", "streak", "spark", "chunk"];
const CHOICE_LABEL = { mode: "Mode", collide: "Collision", sprite: "Sprite" };
let state = null;
let words = "";
const pictures = new Map();
export function useReference(id, ref) { if (id && ref) pictures.set(id, { ref, auto: true }); }

const fmt = (v) => (typeof v === "number" ? String(+v.toFixed(3)) : String(v));
const tailOff = (t) => String(t || "").replace(/\s*Filmed on a pure black background[^.]*\.\s*$/i, "").trim();

function prompts(e, f) {
  const p = P.promptOf(e);
  if (!p) return null;
  const now = String(f.prompt_override || "").trim() || P.composePrompt(e) || "";
  const own = P.composePrompt({ ...e, text: { what: e.text?.what || "", look: "", motion: "", contact: "" }, strength: "normal", dir: null, prompt: null }) || p.preset || "";
  return { now: tailOff(now), own: tailOff(own) };
}

async function ask(ctx, controls, text, basic) {
  const { e, f, P: V } = ctx;
  const pr = prompts(e, f);
  const fromPics = pictures.has(e.id) && !text;
  const prompt = pr && (!basic || fromPics) ? { what: pr.now } : { what: text };
  const style = `${P.effectDef(e.kind)?.name || e.kind} – ${P.styleDef(e.kind, e.style)?.name || e.style}`;
  state = { effect: e.id, status: "busy" };
  S.setUI({});
  try {
    const r = await postJSON("/element-forge/api/bonsai/particles", {
      prompt, style_prompt: pr ? { what: pr.own } : { what: P.styleDef(e.kind, e.style)?.text || "" }, style, controls,
      now: { mode: V.direction_mode, collide: V.collide, sprite: V.sprite,
        colours: (V.colors || []).map(([t, c]) => `${Math.round(t * 100)}%: ${c.map((x) => x.toFixed(2)).join(" ")}`).join(" -> ") },
      modes: MODES, collides: COLLIDE, sprites: SPRITES, stops: V.colors, ref: pictures.get(e.id)?.ref,
    });
    if (state?.effect !== e.id) return;
    state = { effect: e.id, status: "ready", ...r, off: new Set() };
  } catch (err) {
    if (state?.effect === e.id) state = { effect: e.id, status: "failed", error: err.message };
  }
  S.setUI({});
}

function item(key, ...body) {
  const on = !state.off.has(key);
  return h("li", { class: on ? "" : "off" }, h("label", { class: "fill-item" },
    h("input", { type: "checkbox", checked: on, "aria-label": `Set ${key}`, onchange: (ev) => { if (ev.target.checked) state.off.delete(key); else state.off.add(key); S.setUI({}); } }),
    h("span", {}, ...body)));
}
function proposalList() {
  const items = state.changes.map((c) => item(c.key, h("span", { class: "strong" }, c.label), ": ", h("span", { class: "muted" }, fmt(c.from)), " → ", fmt(c.to),
    c.why ? h("span", { class: "muted" }, ` · ${c.why}`) : null));
  for (const k of ["mode", "collide", "sprite"]) if (state[k]) items.push(item(k, h("span", { class: "strong" }, CHOICE_LABEL[k]), ": ", state[k]));
  if (state.colors) items.push(item("colors", h("span", { class: "strong" }, "Colour over life"), ": ", state.colour_names.join(" → "),
    h("span", { class: "fill-swatches", "aria-hidden": "true" }, ...state.colors.map(([, c]) => h("span", { class: "fill-swatch",
      style: { background: `rgb(${c.map((x) => Math.round(x * 255)).join(",")})` } })))));
  return items;
}
const keys = () => [...state.changes.map((c) => c.key), ...["mode", "collide", "sprite"].filter((k) => state[k]), ...(state.colors ? ["colors"] : [])];
const count = () => keys().length;
const picked = () => keys().filter((k) => !state.off.has(k)).length;
const chosen = (r) => ({ ...r, changes: r.changes.filter((c) => !r.off.has(c.key)),
  ...Object.fromEntries(["mode", "collide", "sprite", "colors"].map((k) => [k, r.off.has(k) ? null : r[k]])) });

export function fillRows(ctx, controls, applyAll, basic = false) {
  if (!hasBonsai()) return [];
  const { e, f } = ctx;
  const mine = state?.effect === e.id ? state : null;
  const pr = basic ? null : prompts(e, f);
  const busy = mine?.status === "busy";
  const pic = pictures.get(e.id);
  const go = () => ask(ctx, controls, words.trim(), basic);
  if (pic?.auto && !mine) { pic.auto = false; queueMicrotask(go); }
  const pill = h("button", { class: "chip", disabled: busy || (!pr && !words.trim() && !pic),
    title: pic ? "Bonsai looks at your pictures again and sets the particles so they look and move like them"
      : pr ? `Bonsai reads the prompt and sets the values its words ask for: "${pr.now.slice(0, 160)}"` : "Bonsai sets the values your words ask for",
    onclick: go }, busy ? (pic ? "Looking at your pictures…" : pr ? "Reading the prompt…" : "Reading your words…")
    : pic ? "✦ Fill from the pictures" : pr ? "✦ Fill from the prompt" : "✦ Fill in");
  const rows = [];
  if (basic) rows.push(h("div", { class: "label" }, "Particles in your words"));
  if (pr) rows.push(h("div", { class: "row gap fill-row" }, pill, busy ? h("span", { class: "muted small" }, "about 20 s") : null));
  else {
    const input = h("input", { class: "text", placeholder: "e.g. slow green sparks that spiral up", "aria-label": "Describe the particles", value: words,
      oninput: (ev) => { words = ev.target.value; pill.disabled = busy || !words.trim(); },
      onkeydown: (ev) => { if (ev.key === "Enter" && words.trim() && !busy) { ev.preventDefault(); go(); } } });
    rows.push(h("div", { class: "row gap fill-row" }, input, pill));
    if (busy) rows.push(h("p", { class: "muted small" }, "Bonsai sets the particles, about 20 s."));
  }
  if (mine?.status === "failed") rows.push(ctx.ui.note("err", `Fill did not work: ${mine.error}`));
  if (mine?.status === "ready") {
    const n = count(), k = picked();
    rows.push(h("div", { class: "field fill-result" }, h("div", { class: "label" }, n ? "This is what I would set" : "Nothing to change"),
      n ? h("ul", { class: "small fill-list" }, ...proposalList()) : h("p", { class: "muted small" }, pic ? "The values already fit your pictures." : pr ? "The values already fit the prompt." : "The values already fit your words."),
      mine.note && n ? h("p", { class: "muted small" }, mine.note) : null,
      h("div", { class: "row gap" },
        n ? h("button", { class: "btn small", disabled: !k, onclick: () => { const undo = applyAll(chosen(mine)); state = { effect: e.id, status: "done", undo, n: k }; S.setUI({}); } },
          k === n ? `Apply all ${n}` : `Apply ${k} of ${n}`) : null,
        h("button", { class: "btn ghost small", onclick: () => { state = null; S.setUI({}); } }, n ? "Discard" : "OK"))));
  }
  if (mine?.status === "done") rows.push(h("p", { class: "muted small" }, basic ? `${mine.n} particle values set. In Advanced they show marked. ` : `${mine.n} values set, marked below. `,
    ctx.ui.link("Undo", () => { state = null; mine.undo(); S.setUI({}); }), " · ", ctx.ui.link("OK", () => { state = null; S.setUI({}); })));
  return rows;
}

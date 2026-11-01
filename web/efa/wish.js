import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { suggest, changes, stillToDo, fromPictures, smallPicture } from "./ui/assist.js";
import { bonsaiStatus, whyNotSeeing } from "./ui/enhance.js";
import { useReference } from "./fill.js";

const SUPPORTED = ["style", "strength", "look", "motion", "contact", "direction", "depth", "start", "end", "object", "light", "glow"];
const WORDS = { look: "look_words", motion: "motion_words", contact: "contact_words" };
const DIRS = { preset: null, up: 0, "up-right": 45, right: 90, "down-right": 135, down: 180, "down-left": 225, left: 270, "up-left": 315 };
const DEPTHS = { "far back": -0.3, back: -0.15, "as placed": 0, front: 0.15, "far front": 0.3 };
let state = null;
let wish = "";

export const canWish = () => !whyNotSeeing();
export function initWish(render) { bonsaiStatus().then(render).catch(() => {}); }

function effectNow() {
  const e = S.activeEffect();
  if (e) return e;
  return { kind: "", style: "", where: { a: null, b: null, word: "" }, dir: null, depth: 0, strength: "normal",
    text: { what: "", look: "", motion: "", contact: "" }, timing: { start: 0, end: null }, look: { light: 2, glow: 2, tint: null } };
}

async function ask(x) {
  const sh = S.getShot();
  state = { status: "busy", wish };
  x.render();
  try {
    const e = effectNow();
    const { proposal } = await suggest(e, sh.clip, wish, () => true);
    const list = changes(e, proposal, sh.clip).filter((c) => SUPPORTED.includes(c.key));
    state = { status: "ready", wish, proposal, list, note: String(proposal.note || "").slice(0, 200) };
  } catch (err) {
    state = { status: "failed", wish, error: err.message };
  }
  x.render();
}

function apply(x) {
  const e = applyProposal(x, state);
  state = { status: "done", todo: e ? stillToDo(e) : "" };
  x.render();
}
function applyProposal(x, { proposal: p, list }) {
  const keys = new Set(list.map((c) => c.key));
  const to = Object.fromEntries(list.map((c) => [c.key, c.to]));
  if (keys.has("style")) { const [kind, style] = p.style.split("/"); x.chooseStyle(kind, style); }
  if (keys.has("strength")) x.setFx("strength", to.strength);
  for (const k of ["look", "motion", "contact"]) if (keys.has(k)) x.setFx(WORDS[k], to[k]);
  if (keys.has("object")) x.setFx("object_word", to.object);
  S.change((sh) => {
    const e = sh.effects.find((y) => y.id === sh.active);
    if (!e) return;
    if (keys.has("direction")) e.dir = DIRS[to.direction];
    if (keys.has("depth")) e.depth = DEPTHS[to.depth];
    if (keys.has("start")) e.timing.start = to.start;
    if (keys.has("end")) e.timing.end = to.end;
    if (keys.has("light")) e.adv = { ...e.adv, Light: to.light !== "off" };
    if (keys.has("glow")) e.adv = { ...e.adv, Glow: to.glow !== "off" };
  }, "wish");
  return S.activeEffect();
}

const MAX_PICS = 3;
let pics = [];
let pic = null;

async function addPictures(x, files) {
  const imgs = [...(files || [])].filter((f) => /^image\//.test(f.type)).slice(0, MAX_PICS - pics.length);
  if (!imgs.length) return;
  try {
    for (const f of imgs) pics.push({ url: await smallPicture(f), name: f.name || "pasted picture" });
    pic = null;
  } catch {
    pic = { status: "failed", error: "This picture could not be read. PNG, JPEG or WebP work." };
  }
  x.render();
}

async function askPictures(x) {
  const sh = S.getShot();
  pic = { status: "busy" };
  x.render();
  try {
    const e = effectNow();
    const { proposal, ref } = await fromPictures(e, sh.clip, pics.map((p) => p.url), "", () => true);
    const list = changes(e, proposal, sh.clip).filter((c) => SUPPORTED.includes(c.key));
    pic = { status: "ready", proposal, list, ref, note: String(proposal.note || "").slice(0, 200) };
  } catch (err) {
    pic = { status: "failed", error: err.message };
  }
  x.render();
}

function applyPictures(x) {
  const e = pic.list.length ? applyProposal(x, pic) : S.activeEffect();
  useReference(S.getShot().active, pic.ref);
  pic = { status: "done", todo: e ? stillToDo(e) : "" };
  x.render();
}

export function pictureRows(x) {
  if (!canWish()) return [];
  const { h, link, note } = x;
  const busy = pic?.status === "busy";
  const e = S.activeEffect();
  const input = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", multiple: true, hidden: true,
    onchange: (ev) => { addPictures(x, ev.target.files); ev.target.value = ""; } });
  const thumbs = pics.map((p, i) => h("span", { class: "ref-thumb", title: p.name },
    h("img", { src: p.url, alt: p.name }),
    h("button", { class: "ref-x", "aria-label": `Remove ${p.name}`, title: "Remove", disabled: busy,
      onclick: () => { pics.splice(i, 1); pic = null; x.render(); } }, "×")));
  const rows = [h("div", { class: "label" }, "From a picture"),
    h("div", { class: "row gap ref-row" }, ...thumbs,
      pics.length < MAX_PICS ? h("button", { class: "btn ghost small", disabled: busy, title: "Add a picture of an effect you like (or drop or paste one here)",
        onclick: () => input.click() }, pics.length ? "+ Picture" : "Add picture") : null, input),
    pics.length ? h("div", { class: "row gap fill-row" },
      h("button", { class: "chip", disabled: busy, title: "Bonsai looks at your pictures beside the clip and proposes the style, its words and then the particles",
        onclick: () => askPictures(x) }, busy ? "Looking at your pictures…" : "✦ Make it like this"),
      busy ? h("span", { class: "muted small" }, "about 30 s") : null)
      : h("p", { class: "muted small" }, "A picture of an effect you like: Bonsai makes it at your place in the clip."),
    pics.length && !e?.where?.a ? h("p", { class: "muted small" }, "Click the place in the preview first, so Bonsai sees where it goes.") : null];
  if (pic?.status === "failed") rows.push(note("err", pic.error));
  if (pic?.status === "ready") {
    rows.push(h("div", { class: "field fill-result" }, h("div", { class: "label" }, pic.list.length ? "This is what I would set" : "The effect already fits"),
      pic.list.length ? h("ul", { class: "small" }, ...pic.list.map((c) => h("li", {}, h("span", { class: "strong" }, c.label), ": ",
        h("span", { class: "muted" }, String(c.from ?? "–")), " → ", String(c.to ?? "until the end")))) : null,
      pic.note ? h("p", { class: "muted small" }, pic.note) : null,
      pic.ref ? h("details", { class: "small" }, h("summary", { class: "muted" }, "What Bonsai saw"),
        h("img", { class: "ref-sheet", src: `/element-forge/api/bonsai/reference/${pic.ref}`, alt: "Your pictures beside the clip, the place marked" })) : null,
      h("div", { class: "row gap" },
        h("button", { class: "btn small", disabled: !pic.list.length && !e, title: "Then Bonsai sets the particles from the pictures too",
          onclick: () => applyPictures(x) }, pic.list.length ? "Apply" : "Set the particles"),
        h("button", { class: "btn ghost small", onclick: () => { pic = null; x.render(); } }, "Discard"))));
  }
  if (pic?.status === "done") rows.push(h("p", { class: "muted small" }, pic.todo || "Applied. Bonsai now sets the particles from the pictures too (below, at Particles).", " ",
    link("OK", () => { pic = null; x.render(); })));
  return [h("div", { class: "field ref-field", tabindex: "-1",
    ondragover: (ev) => { if (!busy) ev.preventDefault(); },
    ondrop: (ev) => { ev.preventDefault(); if (!busy) addPictures(x, ev.dataTransfer?.files); },
    onpaste: (ev) => { const fs = [...(ev.clipboardData?.files || [])]; if (fs.length && !busy) { ev.preventDefault(); addPictures(x, fs); } } }, ...rows)];
}

export function suggestButton(x, text) {
  if (!canWish()) return null;
  const t = String(text || "").trim();
  return x.h("button", { class: "btn small", disabled: state?.status === "busy" || !t, title: "Bonsai reads your words and the clip and proposes a style and its words",
    onclick: () => { wish = t; ask(x); } }, state?.status === "busy" ? "Thinking…" : "Suggest");
}
export function wishResults(x) {
  const { h, link, note } = x;
  const rows = [];
  if (state?.status === "failed") rows.push(note("err", state.error));
  if (state?.status === "ready") {
    rows.push(h("div", { class: "field" }, h("div", { class: "label" }, "This is what I would set"),
      state.list.length ? h("ul", { class: "small" }, ...state.list.map((c) => h("li", {}, h("span", { class: "strong" }, c.label), ": ",
        h("span", { class: "muted" }, String(c.from ?? "–")), " → ", String(c.to ?? "until the end")))) : h("p", { class: "muted small" }, "Nothing to change."),
      state.note ? h("p", { class: "muted small" }, state.note) : null,
      h("div", { class: "row gap" },
        state.list.length ? h("button", { class: "btn small", onclick: () => apply(x) }, "Apply") : null,
        h("button", { class: "btn ghost small", onclick: () => { state = null; x.render(); } }, "Discard"))));
  }
  if (state?.status === "done") rows.push(h("p", { class: "muted small" }, state.todo || "Applied.", " ", link("OK", () => { state = null; x.render(); })));
  return rows;
}
export function wishRows(x) {
  const { h, link, note } = x;
  const ok = canWish();
  const input = h("input", { class: "text", placeholder: "e.g. blue sparks flying off the skateboard", "aria-label": "Describe what you want",
    value: wish, disabled: !ok, oninput: (ev) => { wish = ev.target.value; },
    onkeydown: (ev) => { if (ev.key === "Enter" && wish.trim()) { ev.preventDefault(); ask(x); } } });
  const rows = [h("div", { class: "field" }, h("div", { class: "label" }, "Describe what you want"),
    h("div", { class: "row gap" }, input,
      h("button", { class: "btn small", disabled: !ok || state?.status === "busy" || !wish.trim(), onclick: () => ask(x) },
        state?.status === "busy" ? "Thinking…" : "Suggest")),
    !ok ? h("p", { class: "muted small" }, `Off: ${whyNotSeeing()}. Pick a tile instead.`) : null)];
  if (state?.status === "failed") rows.push(note("err", state.error));
  if (state?.status === "ready") {
    rows.push(h("div", { class: "field" }, h("div", { class: "label" }, "This is what I would set"),
      state.list.length ? h("ul", { class: "small" }, ...state.list.map((c) => h("li", {}, h("span", { class: "strong" }, c.label), ": ",
        h("span", { class: "muted" }, String(c.from ?? "–")), " → ", String(c.to ?? "until the end")))) : h("p", { class: "muted small" }, "Nothing to change."),
      state.note ? h("p", { class: "muted small" }, state.note) : null,
      h("div", { class: "row gap" },
        state.list.length ? h("button", { class: "btn small", onclick: () => apply(x) }, "Apply") : null,
        h("button", { class: "btn ghost small", onclick: () => { state = null; x.render(); } }, "Discard"))));
  }
  if (state?.status === "done") rows.push(h("p", { class: "muted small" }, state.todo || "Applied.", " ", link("OK", () => { state = null; x.render(); })));
  return rows;
}

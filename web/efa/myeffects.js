import * as S from "./ui/state.js";
import * as P from "./ui/presets.js";
import { FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH } from "./emitter.js";

export const DIR = "element-forge/my-effects";
export const WIDGETS = ["mode", "strength", "describe", "look_words", "motion_words", "contact_words", "prompt_override",
  "how_it_goes_in", "particle_seed", "preroll", "emitter_values", "guide", "guide_particles", "keep_original", "made_by"];
export const ADV = [FOLLOW_STRENGTH, FOLLOW_LAG, PREMASK, GUIDE_STRENGTH];

let store = null, render = () => {};
let list = null;
let failed = "";
let saving = null;
let editing = null;
let asking = null;

export function initMyEffects(a) {
  store = a.userData || null;
  render = a.render || render;
  refresh();
}
export async function refresh() {
  if (!store) { list = []; return; }
  try {
    const files = (await store.list(DIR)).map((f) => (typeof f === "string" ? f : f.path)).filter((f) => f.endsWith(".json"));
    const out = [];
    for (const f of files) {
      try { const r = await store.get(`${DIR}/${f}`); if (r?.ef_my_effect === 1) out.push({ file: f, ...summary(r) }); } catch {  }
    }
    list = out.sort((a, b) => a.name.localeCompare(b.name));
    failed = "";
  } catch (err) { list = []; failed = err.message; }
  render();
}
const summary = (r) => ({ name: String(r.name || "My effect"), style: String(r.effect_style || ""), kind: String(r.effect_style || "").split("/")[0], rec: r });

export function record(name, fx, e) {
  const widgets = {};
  for (const k of WIDGETS) if (fx[k] !== undefined) widgets[k] = fx[k];
  const adv = {};
  for (const k of ADV) if (e?.adv?.[k] != null) adv[k] = e.adv[k];
  return { ef_my_effect: 1, name: String(name).trim().slice(0, 60), effect_style: fx.effect_style, widgets, adv, saved: new Date().toISOString() };
}
export function fileName(name, now = Date.now()) {
  const slug = String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "effect";
  return `${slug}-${now.toString(36)}.json`;
}

export function apply(r, x) {
  const [kind, style] = String(r.effect_style || "").split("/");
  if (!P.styleDef(kind, style)) { failed = `"${r.name}" uses ${r.effect_style}, which this version does not have.`; render(); return false; }
  x.chooseStyle(kind, style);
  for (const [k, v] of Object.entries(r.widgets || {})) x.setFx(k, v);
  S.change((sh) => {
    const e = sh.effects.find((y) => y.id === sh.active);
    if (!e) return;
    e.adv = { ...e.adv };
    for (const k of ADV) { if (r.adv?.[k] != null) e.adv[k] = r.adv[k]; else delete e.adv[k]; }
  }, "my-effect");
  failed = "";
  render();
  return true;
}

async function save(x) {
  const name = String(saving || "").trim();
  if (!name || !store) return;
  const r = record(name, x.fx(), S.activeEffect());
  try {
    await store.put(`${DIR}/${fileName(name)}`, r, false);
    saving = null;
    await refresh();
  } catch (err) { failed = `Not saved: ${err.message}`; render(); }
}
async function rename(it, name) {
  name = String(name || "").trim();
  editing = null;
  if (!name || name === it.name) { render(); return; }
  try { await store.put(`${DIR}/${it.file}`, { ...it.rec, name: name.slice(0, 60) }, true); await refresh(); }
  catch (err) { failed = `Not renamed: ${err.message}`; render(); }
}
async function remove(it) {
  asking = null;
  try { await store.remove(`${DIR}/${it.file}`); await refresh(); }
  catch (err) { failed = `Not deleted: ${err.message}`; render(); }
}

export function myTiles(x, kind = null) {
  const { h, link, note } = x;
  const mine = (list || []).filter((it) => !kind || it.kind === kind);
  const out = [];
  if (failed) out.push(note("err", failed));
  if (!mine.length) return out;
  out.push(h("div", { class: "field my-effects" }, h("div", { class: "label" }, "My effects"),
    h("div", { class: "styles", role: "list", "aria-label": "My effects" }, ...mine.map((it) => {
      if (editing?.file === it.file) {
        const inp = h("input", { class: "text", value: editing.name, "aria-label": "New name",
          oninput: (ev) => { editing.name = ev.target.value; },
          onkeydown: (ev) => { if (ev.key === "Enter") { ev.preventDefault(); rename(it, editing.name); } if (ev.key === "Escape") { editing = null; render(); } } });
        setTimeout(() => inp.focus(), 0);
        return h("div", { class: "style", role: "listitem" }, inp,
          h("div", { class: "row gap" }, link("Save", () => rename(it, editing.name)), link("Cancel", () => { editing = null; render(); })));
      }
      const def = P.styleDef(it.kind, it.style.split("/")[1]);
      return h("div", { class: "style", role: "listitem" },
        h("button", { class: "style-pick", title: "Load this effect onto the active one", onclick: () => apply(it.rec, x) },
          h("span", { class: "style-name" }, it.name),
          h("span", { class: "style-text" }, def ? `${P.effectDef(it.kind)?.name || it.kind} · ${def.name}` : `${it.style} (not in this version)`)),
        asking === it.file
          ? h("div", { class: "row gap small" }, h("span", { class: "muted" }, "Delete it?"), link("Delete", () => remove(it)), link("Keep", () => { asking = null; render(); }))
          : h("div", { class: "row gap small" }, link("Rename", () => { editing = { file: it.file, name: it.name }; render(); }), link("Delete", () => { asking = it.file; render(); })));
    }))));
  return out;
}

export function saveRows(x) {
  const { h, link } = x;
  if (!store) return [];
  if (saving === null) return [h("div", { class: "row gap" }, h("button", { class: "btn small", title: "Keeps the style, its words, the emitter values and the switches, without clip and position",
    onclick: () => { const st = P.styleDef(...String(x.fx().effect_style || "").split("/")); saving = st ? st.name : "My effect"; render(); } }, "Save as my effect"))];
  const inp = h("input", { class: "text", value: saving, "aria-label": "Name of my effect",
    oninput: (ev) => { saving = ev.target.value; },
    onkeydown: (ev) => { if (ev.key === "Enter") { ev.preventDefault(); save(x); } if (ev.key === "Escape") { saving = null; render(); } } });
  setTimeout(() => { inp.focus(); inp.select(); }, 0);
  return [h("div", { class: "field" }, h("div", { class: "label" }, "Save as my effect"),
    h("div", { class: "row gap my-name" }, inp, h("button", { class: "btn small", onclick: () => save(x) }, "Save"), link("Cancel", () => { saving = null; render(); })),
    h("p", { class: "muted small" }, "Keeps the style, its words, the emitter values and the switches. Clip, position and track stay with the shot."))];
}

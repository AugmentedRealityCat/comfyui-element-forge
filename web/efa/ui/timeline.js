import { h, clamp, fmtSec, uid } from "./lib.js";
import { icon } from "./icons.js";
import * as S from "./state.js";
import * as P from "./presets.js";
import { media, togglePlay, onMediaChange, playhead, seekTo } from "./stage.js";
import * as L from "./look.js";
import { lightShown } from "./run.js";

let root, film, ruler, rows, head, timeLabel, playBtn, loopBtn, lane, tip, actions;
let drag = null;
let raf = 0;
const LIMIT_FRAMES = 161;

const clip = () => S.getShot().clip;
const used = () => { const c = clip(); return c ? Math.min(c.seconds, LIMIT_FRAMES / c.fps) : 0; };
const laneRect = () => lane.getBoundingClientRect();
const toX = (t) => (t / clip().seconds) * (lane.clientWidth || laneRect().width);
const toT = (clientX) => clamp(((clientX - laneRect().left) / laneRect().width) * clip().seconds, 0, clip().seconds);
const snapFrame = (t) => { const f = clip().fps; return Math.round(t * f) / f; };
function snap(t, ev) {
  if (ev?.altKey) return t;
  const ph = media() ? playhead() : -1;
  if (Math.abs(toX(t) - toX(ph)) < 7) return ph;
  return snapFrame(t);
}
const fxName = (e, i) => P.effectDef(e.kind)?.name || `Effect ${i + 1}`;
const endOf = (e) => e.timing.end ?? used();

function now() { return playhead(); }
function seek(t) { seekTo(clamp(t, 0, clip().seconds)); paintHead(); }
function paintHead() {
  const c = clip();
  if (!c || !lane) return;
  const t = now();
  head.style.transform = `translateX(${toX(t)}px)`;
  timeLabel.textContent = `${fmtSec(t)} / ${fmtSec(c.seconds)}`;
  const v = media();
  const playing = v && !v.paused;
  playBtn.replaceChildren(icon(playing ? "pause" : "play"));
  playBtn.title = playing ? "Pause (Space)" : "Play (Space)";
  playBtn.setAttribute("aria-label", playBtn.title);
  playBtn.setAttribute("aria-pressed", String(!!playing));
  loopBtn.setAttribute("aria-pressed", String(!!v?.loop));
}
function loop() { paintHead(); raf = media() && !media().paused ? requestAnimationFrame(loop) : 0; }

function startDrag(ev, kind, e, extra = {}) {
  ev.preventDefault();
  ev.stopPropagation();
  const t0 = toT(ev.clientX);
  drag = { kind, id: e?.id, t0, x0: ev.clientX, moved: false, timing: e ? { ...e.timing, end: endOf(e) } : null, open: e ? e.timing.end == null : false, pointer: ev.pointerId, ...extra };
  if (e) {
    S.begin();
    if (S.getShot().active !== e.id) S.change((sh) => { sh.active = e.id; }, "select");
  }
  root.setPointerCapture(ev.pointerId);
  if (kind === "head") onMove(ev);
}
function costOf(kind, e) {
  const st = P.styleOf(e);
  if (!st) return "";
  if (kind === "fin" || kind === "fout") return "instant";
  if (st.dir === "dissolve") return "needs a new run";
  if (kind === "start" || kind === "move") return st.cost === "gen" ? "needs a new AI run" : "needs a new run";
  return "instant";
}
function onMove(ev) {
  if (!drag) return;
  const c = clip();
  if (drag.kind === "head") { seek(snapFrame(toT(ev.clientX))); return; }
  if (!drag.moved) { if (Math.abs(ev.clientX - drag.x0) < 3) return; drag.moved = true; }
  const t = toT(ev.clientX);
  const d = t - drag.t0;
  const o = drag.timing;
  const min = 2 / c.fps;
  if (drag.kind === "key") {
    S.change((sh) => {
      const e = sh.effects.find((x) => x.id === drag.id);
      const k = e?.keys?.[drag.lane]?.find((x) => x.id === drag.kid);
      if (!k) return;
      const abs = clamp(snap(o.start + drag.k0 + d, ev), o.start, o.end);
      k.t = +(abs - o.start).toFixed(4);
      e.keys[drag.lane].sort((a, b) => a.t - b.t);
    }, "key-time");
    const e = S.getShot().effects.find((x) => x.id === drag.id);
    const k = e?.keys?.[drag.lane]?.find((x) => x.id === drag.kid);
    if (k) showTip(ev.clientX, `key at ${fmtSec(e.timing.start + k.t)} · instant`);
    return;
  }
  S.change((sh) => {
    const e = sh.effects.find((x) => x.id === drag.id);
    if (!e) return;
    const T = e.timing;
    if (drag.kind === "move") {
      const len = o.end - o.start;
      const s = clamp(snap(o.start + d, ev), 0, c.seconds - len);
      T.start = +s.toFixed(3);
      T.end = drag.open && Math.abs(s + len - used()) < 0.5 / c.fps ? null : +(s + len).toFixed(3);
    } else if (drag.kind === "start") {
      T.start = +clamp(snap(o.start + d, ev), 0, o.end - min).toFixed(3);
    } else if (drag.kind === "end") {
      const v = clamp(snap(o.end + d, ev), o.start + min, c.seconds);
      T.end = Math.abs(v - used()) < 0.5 / c.fps ? null : +v.toFixed(3);
    } else if (drag.kind === "fin") {
      T.fadeIn = +clamp((o.fadeIn || 0) + d, 0, (o.end - o.start) - (o.fadeOut || 0)).toFixed(3);
    } else if (drag.kind === "fout") {
      T.fadeOut = +clamp((o.fadeOut || 0) - d, 0, (o.end - o.start) - (o.fadeIn || 0)).toFixed(3);
    }
  }, "timing");
  const e = S.getShot().effects.find((x) => x.id === drag.id);
  if (e) showTip(ev.clientX, `${drag.kind === "fin" ? `fade in ${fmtSec(e.timing.fadeIn)}` : drag.kind === "fout" ? `fade out ${fmtSec(e.timing.fadeOut)}`
    : `${fmtSec(e.timing.start)} – ${fmtSec(endOf(e))}`} · ${costOf(drag.kind, e)}`);
}
function onUp(ev) {
  if (!drag) return;
  const was = drag;
  drag = null;
  try { root.releasePointerCapture(ev.pointerId); } catch {  }
  showTip();
  if (was.kind !== "head") S.end();
  if (was.kind === "key" && !was.moved) {
    const e = S.getShot().effects.find((x) => x.id === was.id);
    const k = e?.keys?.[was.lane]?.find((x) => x.id === was.kid);
    if (k) seek(e.timing.start + k.t);
  }
}
function cancelDrag() {
  if (!drag) return false;
  const was = drag;
  drag = null;
  try { root.releasePointerCapture(was.pointer); } catch {  }
  showTip();
  if (was.kind !== "head") S.cancelGesture();
  return true;
}
function showTip(x, text) {
  if (!text) { tip.hidden = true; return; }
  tip.hidden = false;
  tip.textContent = text;
  const r = root.getBoundingClientRect(), k = root.offsetWidth ? r.width / root.offsetWidth || 1 : 1;
  tip.style.left = `${clamp((x - r.left) / k, 80, root.offsetWidth - 80)}px`;
}

function handleKey(ev, kind, e) {
  if ((ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") || ev.ctrlKey || ev.metaKey) return;
  ev.preventDefault();
  ev.stopPropagation();
  const c = clip();
  const d = (ev.key === "ArrowLeft" ? -1 : 1) * (ev.shiftKey ? 10 : 1) / c.fps;
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === e.id);
    const T = x.timing, end = endOf(x);
    if (kind === "fin") T.fadeIn = +clamp((T.fadeIn || 0) + d, 0, (end - T.start) - (T.fadeOut || 0)).toFixed(3);
    if (kind === "fout") T.fadeOut = +clamp((T.fadeOut || 0) - d, 0, (end - T.start) - (T.fadeIn || 0)).toFixed(3);
    if (kind === "start") T.start = +clamp(T.start + d, 0, end - 2 / c.fps).toFixed(3);
    if (kind === "end") T.end = +clamp(end + d, T.start + 2 / c.fps, c.seconds).toFixed(3);
    if (kind === "move") { const len = end - T.start; T.start = +clamp(T.start + d, 0, c.seconds - len).toFixed(3); if (T.end != null) T.end = +(T.start + len).toFixed(3); }
  }, "nudge-time");
}

const LANES = [["place", "Position", "Animate place, size and turn: sets a key at the playhead"], ["bright", "Brightness", "Animate the brightness: sets a key at the playhead"]];
const selKey = (e) => {
  const s = S.ui.key;
  return s && e && s.effect === e.id ? e.keys?.[s.lane]?.find((k) => k.id === s.id) || null : null;
};
function toggleAnim(e, lane) {
  const t = now();
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === e.id);
    x.keys ||= { place: [], bright: [] };
    x.keys[lane] ||= [];
    if (x.keys[lane].length) {
      if (lane === "place") x.place = { ...x.place, ...L.placeAt(x, t) }; else x.look.bright = L.brightAt(x, t);
      x.keys[lane] = [];
    } else {
      const rel = clamp(Math.round((t - x.timing.start) * clip().fps) / clip().fps, 0, endOf(x) - x.timing.start);
      x.keys[lane] = [{ id: uid(), t: +rel.toFixed(4), ease: "even", ...(lane === "place" ? L.placeAt(x, t) : { v: L.brightAt(x, t) }) }];
    }
  }, "animate");
  S.setUI({ key: null });
}
function removeKey(e, lane, id) {
  S.change((sh) => { const x = sh.effects.find((y) => y.id === e.id); x.keys[lane] = x.keys[lane].filter((k) => k.id !== id); }, "key-delete");
  S.setUI({ key: null });
}
function keyKey(ev, e, lane, k) {
  if (ev.key === "Delete" || ev.key === "Backspace") { ev.preventDefault(); removeKey(e, lane, k.id); return; }
  if (ev.key === "Enter") { ev.preventDefault(); seek(e.timing.start + k.t); return; }
  if ((ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") || ev.ctrlKey || ev.metaKey) return;
  ev.stopPropagation();
  ev.preventDefault();
  const d = (ev.key === "ArrowLeft" ? -1 : 1) * (ev.shiftKey ? 10 : 1) / clip().fps;
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === e.id), y = x.keys[lane].find((q) => q.id === k.id);
    y.t = +clamp(y.t + d, 0, endOf(x) - x.timing.start).toFixed(4);
    x.keys[lane].sort((a, b) => a.t - b.t);
  }, "key-nudge");
}
function keyRows(e) {
  const c = clip();
  return LANES.map(([lane, name, tip]) => {
    const ks = e.keys?.[lane] || [];
    const on = ks.length > 0;
    const sk = selKey(e);
    return h("div", { class: "tl-row tl-keys" },
      h("button", { class: "tl-label tl-anim" + (on ? " on" : ""), "aria-pressed": String(on), onclick: () => toggleAnim(e, lane),
        title: on ? `${name} is animated. Click to stop (the value at the playhead stays)` : tip }, h("span", { class: "dia", "aria-hidden": "true" }, on ? "◆" : "◇"), name),
      h("div", { class: "tl-lane", onpointerdown: (ev) => startDrag(ev, "head") },
        ...ks.map((k) => h("span", { class: `tl-key ease-${k.ease || "even"}` + (sk?.id === k.id ? " on" : ""), style: { left: `${((e.timing.start + k.t) / c.seconds) * 100}%` },
          tabindex: "0", role: "slider", "aria-label": `${name} key`, "aria-valuetext": fmtSec(e.timing.start + k.t),
          title: `${name} key at ${fmtSec(e.timing.start + k.t)} · ${(L.EASE_NAMES.find((x) => x[0] === (k.ease || "even")) || [])[1]} · drag to move, click to jump there, Delete removes`,
          onpointerdown: (ev) => { S.setUI({ key: { effect: e.id, lane, id: k.id } }); startDrag(ev, "key", e, { lane, kid: k.id, k0: k.t, moved: false }); },
          onkeydown: (ev) => keyKey(ev, e, lane, k), onfocus: () => { if (S.ui.key?.id !== k.id) S.setUI({ key: { effect: e.id, lane, id: k.id } }); } }))));
  });
}

const PASSES = [["element", "Element"], ["light", "Light"], ["glow", "Glow"]];
function passRows(e) {
  const c = clip();
  const s = e.timing.start, en = endOf(e);
  return PASSES.filter(([p]) => p !== "light" || lightShown(S.shownOf(e.id))).map(([p, name]) => {
    const muted = !!e.look.mute?.[p];
    const solo = S.ui.pass === p;
    return h("div", { class: "tl-row tl-pass" + (muted ? " muted" : "") },
      h("div", { class: "tl-label tl-pass-label" },
        h("button", { class: "icon-btn tiny", "aria-pressed": String(!muted), title: muted ? `${name} is off (also in the export): click to show it` : `Hide the ${name.toLowerCase()} (also in the export)`,
          "aria-label": `${name} visible`, onclick: () => S.change((sh) => { const x = sh.effects.find((y) => y.id === e.id); x.look.mute = { ...(x.look.mute || {}), [p]: !muted }; }, "mute") },
          icon(muted ? "eyeOff" : "eye")),
        h("span", { class: "grow" }, name),
        h("button", { class: "solo" + (solo ? " on" : ""), "aria-pressed": String(solo), title: solo ? "Back to the whole comp" : `Show only the ${name.toLowerCase()} (view only)`,
          onclick: () => S.setUI({ pass: solo ? null : p, compare: false }) }, "S")),
      h("div", { class: "tl-lane", onpointerdown: (ev) => startDrag(ev, "head") },
        h("span", { class: "tl-passbar", style: { left: `${(s / c.seconds) * 100}%`, width: `${((en - s) / c.seconds) * 100}%` } })));
  });
}

function renderRows() {
  const shot = S.getShot();
  const c = clip();
  rows.replaceChildren(...shot.effects.map((e, i) => {
    const s = e.timing.start, en = endOf(e);
    const on = e.id === shot.active;
    if (!on) return [];
    const left = (s / c.seconds) * 100, width = ((en - s) / c.seconds) * 100;
    const fin = (e.timing.fadeIn / Math.max(en - s, 1e-6)) * 100, fout = (e.timing.fadeOut / Math.max(en - s, 1e-6)) * 100;
    const bar = h("div", { class: "tl-bar" + (on ? " on" : ""), style: { left: `${left}%`, width: `${width}%`, "--fin": `${fin}%`, "--fout": `${fout}%` },
      tabindex: "0", role: "slider", "aria-label": `${fxName(e, i)}: drag to move, arrow keys move by a frame`,
      "aria-valuetext": `${fmtSec(s)} to ${fmtSec(en)}`, onpointerdown: (ev) => startDrag(ev, "move", e), onkeydown: (ev) => handleKey(ev, "move", e) },
    h("span", { class: "tl-fade in", tabindex: "0", role: "slider", "aria-label": `${fxName(e, i)} fade in`, "aria-valuetext": fmtSec(e.timing.fadeIn || 0),
      title: "Fade in: drag to the right (arrow keys: a frame)", onpointerdown: (ev) => startDrag(ev, "fin", e), onkeydown: (ev) => handleKey(ev, "fin", e) }),
    h("span", { class: "tl-fade out", tabindex: "0", role: "slider", "aria-label": `${fxName(e, i)} fade out`, "aria-valuetext": fmtSec(e.timing.fadeOut || 0),
      title: "Fade out: drag to the left (arrow keys: a frame)", onpointerdown: (ev) => startDrag(ev, "fout", e), onkeydown: (ev) => handleKey(ev, "fout", e) }),
    h("span", { class: "tl-grip l", tabindex: "0", role: "slider", "aria-label": `${fxName(e, i)} start`, "aria-valuetext": fmtSec(s), title: "Start: drag",
      onpointerdown: (ev) => startDrag(ev, "start", e), onkeydown: (ev) => handleKey(ev, "start", e) }),
    h("span", { class: "tl-grip r", tabindex: "0", role: "slider", "aria-label": `${fxName(e, i)} end`, "aria-valuetext": fmtSec(en), title: "End: drag",
      onpointerdown: (ev) => startDrag(ev, "end", e), onkeydown: (ev) => handleKey(ev, "end", e) }),
    h("span", { class: "tl-bar-name" }, fxName(e, i), on && livePre(e, c) ? h("span", { class: "tl-pre-name" }, ` · ◂ ${+livePre(e, c).toFixed(1)} s pre-roll`) : null));
    const row = h("div", { class: "tl-row" + (on ? " on" : "") },
      h("button", { class: "tl-label", title: `Select ${fxName(e, i)}`, onclick: () => S.change((sh) => { sh.active = e.id; }, "select") },
        fxName(e, i), L.animated(e, "place") || L.animated(e, "bright") ? h("span", { class: "dia", title: "Animated with keys", "aria-label": "animated" }, " ◆") : null),
      h("div", { class: "tl-lane", onpointerdown: (ev) => startDrag(ev, "head") }, bar, ...(on ? liveMarks(e, c) : [])));
    return on && S.ui.mode === "advanced" && S.shownOf(e.id)?.status === "done" ? [row, ...keyRows(e), ...passRows(e)] : [row];
  }).flat());
}
function liveMarks(e, c) {
  const ls = S.ui.liveSim;
  if (!ls || ls.effect !== e.id || ls.clip !== c.name) return [];
  const hd = ls.data?.header;
  const out = [];
  const share = !hd ? 0 : hd.mode === "hold" ? 1 : Math.min(1, hd.n / hd.fps / c.seconds);
  const busy = ls.status === "running" && !ls.lookOnly;
  out.push(h("span", { class: "tl-cache" + (busy ? " busy" : "") + (ls.status === "failed" ? " failed" : ""),
    style: { width: `${(busy ? 100 : share * 100).toFixed(2)}%` },
    title: busy ? "Simulating the particles…" : ls.status === "failed" ? `Live preview failed: ${ls.error || ""}`
      : hd?.mode === "hold" ? `Live: ${fmtSec(hd.n / hd.fps)} on the held frame, ready` : "Live: simulated and ready" }));
  const pre = livePre(e, c);
  if (pre > 0) out.push(h("span", { class: "tl-preroll", style: { left: `${(e.timing.start / c.seconds) * 100}%` },
    title: `Pre-roll: the particles run ${fmtSec(pre)} before the clip begins, so the first frame is already full` }));
  return out;
}
function livePre(e, c) {
  const ls = S.ui.liveSim;
  return ls && ls.effect === e.id && ls.clip === c.name && ls.status !== "running" ? ls.data?.header.preroll_s || 0 : 0;
}
function renderActions() {
  const e = S.activeEffect();
  const sk = S.ui.mode === "advanced" ? selKey(e) : null;
  if (sk) {
    const lane = S.ui.key.lane;
    actions.replaceChildren(
      h("select", { class: "tl-ease", "aria-label": "How it moves to the next key", title: "How it moves to the next key",
        onchange: (ev) => S.change((sh) => { const x = sh.effects.find((y) => y.id === e.id); x.keys[lane].find((k) => k.id === sk.id).ease = ev.target.value; }, "key-ease") },
        ...L.EASE_NAMES.map(([v, n, t]) => h("option", { value: v, selected: (sk.ease || "even") === v, title: t }, n))),
      h("button", { class: "btn small ghost", title: "Delete this key (Delete)", onclick: () => removeKey(e, lane, sk.id) }, "Delete"));
    return;
  }
  actions.replaceChildren(...(e ? [
    h("button", { class: "btn small", title: "Let the selected effect start at the playhead (I)", onclick: () => setEdge("start") }, "Start here"),
    h("button", { class: "btn small", title: "Let the selected effect end at the playhead (O)", onclick: () => setEdge("end") }, "End here"),
  ] : []));
}
function renderRuler() {
  const c = clip();
  const step = c.seconds > 20 ? 5 : c.seconds > 8 ? 2 : c.seconds > 3 ? 1 : 0.5;
  const ticks = [];
  for (let t = 0; t <= c.seconds + 1e-6; t += step) ticks.push(h("span", { class: "tick", style: { left: `${(t / c.seconds) * 100}%` } }, `${+t.toFixed(1)} s`));
  const over = used() < c.seconds ? h("span", { class: "unused", style: { left: `${(used() / c.seconds) * 100}%` }, title: "Not used: Element Forge takes the first 161 frames" }) : null;
  ruler.replaceChildren(...ticks, ...(over ? [over] : []));
}
let filmFor = "";
export function render() {
  if (!root) return;
  const c = clip();
  root.classList.toggle("empty-tl", !c);
  if (!c) { rows.replaceChildren(); ruler.replaceChildren(); film.style.backgroundImage = ""; filmFor = ""; return; }
  if (filmFor !== c.name) {
    filmFor = c.name;
    film.style.backgroundImage = `url("/element-forge/api/filmstrip?name=${encodeURIComponent(c.name)}&count=24&height=56")`;
  }
  renderRuler();
  renderRows();
  renderActions();
  paintHead();
  fitHeight();
}
function fitHeight() {
  const box = root.closest(".efa-root") || document.documentElement;
  if (box.dataset.tlSized) return;
  const top = Math.max(lane.offsetHeight, root.querySelector(".tl-ctrl").offsetHeight);
  const want = Math.round(Math.min(Math.max(top + rows.offsetHeight + 8, 150), (box.clientHeight || innerHeight) * 0.45));
  box.style.setProperty("--tl-h", `${want}px`);
}

function setEdge(which) {
  const e = S.activeEffect();
  if (!e) return;
  const t = snapFrame(now()), f = 1 / clip().fps;
  S.change((sh) => {
    const x = sh.effects.find((y) => y.id === sh.active);
    if (which === "start") x.timing.start = +Math.min(t, endOf(x) - 2 * f).toFixed(3);
    else x.timing.end = +Math.max(t, x.timing.start + 2 * f).toFixed(3);
  }, which === "start" ? "start-here" : "end-here");
}
function jumpKey(dir) {
  const e = S.activeEffect();
  if (!e) return;
  const f = 1 / clip().fps, t = now();
  const marks = [e.timing.start, endOf(e), ...Object.values(e.keys || {}).flat().map((k) => e.timing.start + k.t)].sort((a, b) => a - b);
  const to = dir < 0 ? marks.filter((m) => m < t - f / 2).at(-1) : marks.find((m) => m > t + f / 2);
  if (to != null) { media()?.pause(); seek(to); }
}
function onKey(ev) {
  if (!clip()) return;
  const t = ev.target;
  if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
  if (ev.key === "Escape" && cancelDrag()) { ev.preventDefault(); ev.stopPropagation(); return; }
  if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && (ev.key === "ArrowLeft" || ev.key === "ArrowRight")) { ev.preventDefault(); ev.stopPropagation();  jumpKey(ev.key === "ArrowLeft" ? -1 : 1); return; }
  if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
  const v = media(), f = 1 / clip().fps;
  const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key;
  const act = {
    k: () => { v.pause(); v.playbackRate = 1; },
    l: () => { if (v.paused) { v.playbackRate = 1; v.play().catch(() => {}); } else v.playbackRate = Math.min(4, v.playbackRate * 2); },
    j: () => { v.pause(); seek(now() - (ev.shiftKey ? 10 : 3) * f); },
    PageUp: () => { v.pause(); seek(now() - (ev.shiftKey ? 10 : 1) * f); },
    PageDown: () => { v.pause(); seek(now() + (ev.shiftKey ? 10 : 1) * f); },
    Home: () => seek(0),
    End: () => seek(clip().seconds - f),
    i: () => setEdge("start"),
    o: () => setEdge("end"),
  }[k];
  if (!act) return;
  ev.preventDefault();
  ev.stopPropagation();
  act();
  paintHead();
}

export function mountTimeline(el) {
  (el.closest(".efa-root") || el).addEventListener("keydown", onKey, true);
  root = el;
  playBtn = h("button", { class: "icon-btn", onclick: () => togglePlay() }, icon("play"));
  loopBtn = h("button", { class: "icon-btn", title: "Repeat", "aria-label": "Repeat", onclick: () => { const v = media(); if (v) v.loop = !v.loop; paintHead(); } }, icon("loop"));
  timeLabel = h("span", { class: "tl-time" }, "0.0 s");
  actions = h("div", { class: "tl-actions" });
  ruler = h("div", { class: "tl-ruler", onpointerdown: (ev) => startDrag(ev, "head") });
  film = h("div", { class: "tl-film", title: "Click or drag to move the playhead", onpointerdown: (ev) => startDrag(ev, "head") });
  head = h("div", { class: "tl-head", "aria-hidden": "true" });
  rows = h("div", { class: "tl-rows" });
  tip = h("div", { class: "tl-tip", role: "status", hidden: true });
  lane = h("div", { class: "tl-lanes" }, ruler, film);
  const empty = h("div", { class: "tl-empty" }, "Your clip appears here as a filmstrip, with a bar for each effect.");
  root.append(
    h("div", { class: "tl-grid" },
      h("div", { class: "tl-ctrl" }, h("div", { class: "row" }, playBtn, loopBtn, timeLabel), actions),
      lane, rows, head),
    tip, empty);
  root.addEventListener("pointermove", onMove);
  root.addEventListener("pointerup", onUp);
  root.addEventListener("pointercancel", onUp);
  const bound = new WeakSet();
  const bind = (v) => {
    if (!v || bound.has(v)) return;
    bound.add(v);
    for (const t of ["play", "pause", "seeked", "timeupdate", "loadedmetadata"]) v.addEventListener(t, () => { if (v !== media()) return; paintHead(); if (t === "play" && !raf) raf = requestAnimationFrame(loop); });
  };
  bind(media());
  onMediaChange((v) => { bind(v); paintHead(); });
  new ResizeObserver(() => paintHead()).observe(lane);
  S.subscribe(render);
  render();
}

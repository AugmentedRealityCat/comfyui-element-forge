import asyncio
import collections
import concurrent.futures
import hashlib
import json
import os
import struct
import threading
import time
import types

import cv2
import numpy as np
from aiohttp import web

import folder_paths
import server

from . import app_routes as AR
from ..simulation import dissolve as DS
from ..simulation import particles as pt
from ..simulation import particles_node as PN

PARTICLES = "230"
MOTION = "252"
SHAPE = "810"
SHAPE_SIDE = 192
DISSOLVE = ("445", "446")
DISSOLVE_ARGS = ("amount", "speed", "size", "life", "edge_noise", "glow", "glow_color", "inherit_motion", "motion_carry", "style",
                 "extra", "background")
HEAVY = ("SAM3", "LTX", "VideoDepthAnything", "LoadVideoDepthAnything", "CheckpointLoader", "CLIPTextEncode", "CLIPLoader",
         "UNETLoader", "VAELoader", "VAEDecode", "VAEEncode", "EFMoGeNormals", "MoGe", "DownloadAndLoad", "KSampler",
         "SamplerCustom", "EFSave", "Save", "Preview")
PASS = {"EFFreeVRAM": "images"}
FALLBACK = {"track": ("198", 2), "window": ("198", 2), "track_b": ("199", 2)}
SETUP_ARGS = ("plate", "preset", "emitter", "amount", "speed", "size", "life", "direction", "spread", "follow", "start_seconds",
              "fps", "seed", "track", "track_b", "mask", "drawing", "depth", "settings", "area", "depth_offset", "premask",
              "edge_fade", "camera", "look_plate", "line_attach", "motion_carry", "screen_fixed", "window")
LOOK = {"colors", "color_var", "glow", "trail", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "plate_color", "dof", "focus",
        "bloom", "halo", "ambient", "relief", "shell", "look", "blend", "guide_style", "sprite", "sprite_gain", "sprite_aspect",
        "sprite_occlude", "sprite_play", "shutter", "depth_guide", "depth_edge"}
LOOK_SENT = ("colors", "color_var", "glow", "sprite", "trail", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "opacity",
             "plate_color", "shutter", "blend", "look")
PANEL = ("rate", "rate_curve", "burst", "burst_at", "burst_every", "max_particles", "life", "life_var", "size", "size_var", "size_start", "size_end", "speed",
         "speed_var", "spread", "direction", "direction_mode", "lift", "inherit", "motion_carry", "gravity", "wind", "drag",
         "turbulence", "turb_scale", "turb_speed", "vortex", "attract", "flock", "collide", "restitution", "friction",
         "depth_offset", "depth_spread", "fade_in", "fade_out", "opacity", "flicker", "flicker_hz", "flicker_size", "fine_share",
         "fine_size", "fine_speed", "fine_life", "sprite", "trail", "glow",
         "shutter", "colors", "blob", "blob_choke", "blob_soft", "blob_fill", "blob_life", "path", "roughness", "branches", "width",
         "reroll_frames", "preroll", "radius", "spread_falloff", "speed_end", "max_speed", "color_var", "spin", "flock_radius",
         "flock_cohesion", "turb_fade", "turb_drag", "land_fade",
         "grow_seconds", "fine_rough", "strike_leader", "strike_strokes", "strike_gap", "strike_decay", "strike_hold",
         "strike_hold_level", "strike_new_ground", "strike_streamer", "strike_lean", "strike_spread", "climb_seconds", "climb_pitch", "climb_rough", "climb_head", "climb_short", "fork_depth",
         "climb_zigzag", "crack_speed", "crack_length", "crack_branch", "crack_turn", "crack_step", "crack_seeds", "crack_taper",
         "crack_angle", "crack_angle_var", "crack_pairs", "relief",
         "scale", "scene_height", "gravity_end", "speed_by_size", "sway", "sway_hz", "flicker_duty", "roll",
         "blend", "plate_color", "ambient", "guide_style", "children",
         "depth_guide", "depth_edge")
DPANEL = ("density", "push", "lift", "spread", "inherit", "motion_carry", "gravity", "drag", "turbulence", "turb_scale", "life",
          "size", "fade_out", "edge_noise", "noise_size", "glow", "glow_width", "glow_color", "tint")
HOLD_SECONDS = 10.0
FILE_INPUTS = ("file", "image", "video")
MEMO_SIZE = 240
SIMS = 6


class Missing(Exception):
    pass


class Superseded(Exception):
    pass


def is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int)


def _stamp(name):
    try:
        p = folder_paths.get_annotated_filepath(name)
        st = os.stat(p)
        return [st.st_size, int(st.st_mtime)]
    except Exception:
        return None


def signatures(graph):
    sigs = {}

    def sig(nid):
        if nid in sigs:
            return sigs[nid]
        sigs[nid] = "loop"
        nd = graph[nid]
        parts = [nd["class_type"]]
        for k in sorted(nd["inputs"]):
            v = nd["inputs"][k]
            if is_link(v):
                parts.append([k, sig(v[0]) if v[0] in graph else "?", v[1]])
            else:
                parts.append([k, v, _stamp(v) if k in FILE_INPUTS and isinstance(v, str) else None])
        sigs[nid] = hashlib.sha1(json.dumps(parts, default=str).encode()).hexdigest()
        return sigs[nid]

    for k in graph:
        sig(k)
    return sigs


def heavy(class_type):
    return class_type.startswith(HEAVY)


def _input_kinds(cls):
    try:
        it = cls.INPUT_TYPES()
    except Exception:
        return set(), set()
    lazy = set()
    for cat in ("required", "optional"):
        for k, spec in (it.get(cat) or {}).items():
            if isinstance(spec, (list, tuple)) and len(spec) > 1 and isinstance(spec[1], dict) and spec[1].get("lazy"):
                lazy.add(k)
    return lazy, set(it.get("required") or {})


class Entry:
    __slots__ = ("outputs",)

    def __init__(self, outputs):
        self.outputs = outputs


class Runner:

    def __init__(self):
        self.memo = collections.OrderedDict()

    def trim(self):
        while len(self.memo) > MEMO_SIZE:
            self.memo.popitem(last=False)

    async def run(self, graph, nid, ctx):
        import execution
        import nodes
        sig = ctx["sigs"][nid]
        if sig in self.memo:
            self.memo.move_to_end(sig)
            return self.memo[sig]
        ctx["check"]()
        nd = graph[nid]
        ct = nd["class_type"]
        if heavy(ct):
            raise Missing(f"{ct} ({nid})")
        if ct in PASS:
            src = nd["inputs"][PASS[ct]]
            e = await self.run(graph, src[0], ctx)
            self.memo[sig] = Entry([e.outputs[src[1]]])
            return self.memo[sig]
        cls = nodes.NODE_CLASS_MAPPINGS.get(ct)
        if cls is None:
            raise Missing(f"{ct} ({nid}) is not installed")
        obj, data, v3 = await self.prepare(graph, nid, cls, ctx)
        t0 = time.time()
        try:
            res = await execution._async_map_node_over_list(None, nid, obj, data, cls.FUNCTION, allow_interrupt=False, v3_data=v3)
            res = await execution.resolve_map_node_over_list_results(res)
            out, _ui, sub = execution.get_output_from_returns(res, obj)
        except (Superseded, Missing):
            raise
        except Exception as e:
            raise Missing(f"{ct} ({nid}) failed: {e}") from e
        if sub:
            raise Missing(f"{ct} ({nid}) expands into a subgraph")
        ctx["times"][f"{ct} ({nid})"] = round(time.time() - t0, 3)
        self.memo[sig] = Entry(out)
        return self.memo[sig]

    async def prepare(self, graph, nid, cls, ctx):
        import execution
        inputs = graph[nid]["inputs"]
        lazy, required = _input_kinds(cls)

        async def need(k):
            try:
                await self.run(graph, inputs[k][0], ctx)
            except Missing as m:
                if k in required:
                    raise
                ctx["left_out"].append(str(m))

        for k, v in inputs.items():
            if is_link(v) and k not in lazy:
                await need(k)
        asked = set()
        lst = _Cache(self, ctx)
        while True:
            data, missing, v3 = execution.get_input_data(inputs, cls, nid, lst, None, {})
            obj = cls()
            if lazy and callable(getattr(obj, "check_lazy_status", None)):
                v3l = dict(v3)
                v3l["create_dynamic_tuple"] = True
                r = await execution._async_map_node_over_list(None, nid, obj, data, "check_lazy_status", allow_interrupt=False, v3_data=v3l)
                r = await execution.resolve_map_node_over_list_results(r)
                want = {x for x in sum([y for y in r if isinstance(y, list)], []) if isinstance(x, str) and is_link(inputs.get(x))
                        and x in missing and x not in asked}
                if want:
                    for k in sorted(want):
                        asked.add(k)
                        await need(k)
                    continue
            return obj, data, v3


class _Cache:

    def __init__(self, runner, ctx):
        self.runner, self.ctx = runner, ctx

    def get_cache(self, nid, _uid):
        return self.runner.memo.get(self.ctx["sigs"].get(nid))


def hold_track(tr, i, n):
    if not isinstance(tr, dict):
        return tr
    m = len(tr.get("point_track_px") or [])
    out = {}
    for k, v in tr.items():
        out[k] = [v[min(i, len(v) - 1)]] * n if isinstance(v, list) and m and len(v) == m else v
    return out


def held(arr, i, n):
    if arr is None:
        return None
    a = PN._np(arr)
    return np.broadcast_to(a[min(i, len(a) - 1)][None], (n,) + a.shape[1:])


def held_one(arr, i):
    if arr is None:
        return None
    a = PN._np(arr)
    return np.ascontiguousarray(a[min(i, len(a) - 1)][None])


def sim_key(inputs, sigs, settings, mode, frame, seconds):
    parts = []
    for k in SETUP_ARGS:
        if k == "settings":
            over, final = PN.split_final(settings)
            parts.append([k, {a: b for a, b in sorted(over.items()) if a not in LOOK},
                          {a: b for a, b in sorted(final.items()) if a not in LOOK}])
            continue
        v = inputs.get(k)
        parts.append([k, [sigs.get(v[0]), v[1]] if is_link(v) else v])
    parts.append([mode, frame if mode == "hold" else None, seconds if mode == "hold" else None])
    return hashlib.sha1(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()[:20]


IN_P = ("settings", "speed", "size", "life", "direction", "spread", "follow", "start_seconds", "depth_offset", "motion_carry")


def motion_key(inputs, sigs, P, mode, frame, seconds):
    parts = [[k, [sigs.get(v[0]), v[1]] if is_link(v) else v] for k in SETUP_ARGS if k not in IN_P for v in [inputs.get(k)]]
    parts.append({a: b for a, b in P.items() if a not in LOOK and a not in pt.LOOK_ONLY and not a.startswith("_")})
    parts.append([mode, frame if mode == "hold" else None, seconds if mode == "hold" else None])
    return "m" + hashlib.sha1(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()[:19]


def preroll_seconds(P, em):
    if P["start"] > 0:
        return 0.0
    pre = P["preroll"]
    if pre < 0:
        ps = min(em.W, em.H) / pt.REF
        v = max(P["speed"] * ps * (1 - P["speed_var"]) * pt.sfac0(em), 1.0)
        pre = min(60.0, P["life"], 1.1 * (em.H if em.kind == "whole frame" and P.get("band") == "top" else min(em.W, em.H)) / v)
    return float(max(pre, 0.0))


def look_of(P):
    return {k: P.get(k) for k in LOOK_SENT}


def encode(s, P, premask=True):
    rec, em, paths = s["rec"], s["em"], s["paths"]
    n, W, H = em.n, em.W, em.H
    dof = float(P.get("dof", 0) or 0)
    foc = P["focus"] if P.get("focus", -1) >= 0 else float(getattr(em, "zref", 0.5))
    fi, a = np.nonzero(np.isfinite(rec["x"])) if rec["x"].size else (np.zeros(0, np.int64), np.zeros(0, np.int64))
    x, y = rec["x"][fi, a].astype(np.float64), rec["y"][fi, a].astype(np.float64)
    r = rec["size"][fi, a].astype(np.float64)
    al = rec["alpha"][fi, a].astype(np.float64) * (rec["vis"][fi, a] if premask else 1.0)
    if dof > 0:
        coc = dof * min(W, H) / pt.REF * np.abs(rec["z"][fi, a] - foc)
        re_ = np.sqrt(r ** 2 + coc ** 2)
        al = al * (r / np.maximum(re_, 1e-6)) ** 2
        r = re_
    k = (al > 1e-3) & (np.abs(x) < 4000) & (np.abs(y) < 4000)
    fi, a, x, y, r, al = fi[k], a[k], x[k], y[k], r[k], al[k]
    offs = np.zeros(n + 1, np.int64)
    offs[1:] = np.cumsum(np.bincount(fi, minlength=n)[:n])
    cap = rec["x"].shape[1] if rec["x"].ndim == 2 else 0
    pcol = rec.get("pcol")
    arrays = {"offs": offs.astype(np.uint32), "id": a.astype(np.uint32), "x": np.round(x * 8).astype(np.int16),
              "y": np.round(y * 8).astype(np.int16), "r": np.clip(np.round(r * 16), 0, 65535).astype(np.uint16),
              "a": np.clip(np.round(al * 255), 0, 255).astype(np.uint8),
              "age": np.clip(np.round(rec["age"][fi, a] * 255), 0, 255).astype(np.uint8),
              "vx": np.clip(np.round(rec["vx"][fi, a]), -32767, 32767).astype(np.int16),
              "vy": np.clip(np.round(rec["vy"][fi, a]), -32767, 32767).astype(np.int16),
              "rot": np.round(np.mod(rec["rot"][fi, a], 2 * np.pi) / (2 * np.pi) * 255).astype(np.uint8),
              "rnd": np.clip(np.round(np.asarray(rec.get("rnd", np.zeros(cap)), np.float64) * 255), 0, 255).astype(np.uint8),
              "pcol": (np.clip(np.round(np.asarray(pcol) * 255), 0, 255).astype(np.uint8).reshape(-1)
                       if pcol is not None else np.zeros(0, np.uint8))}
    cracks = compact_cracks(paths, em, n)
    if cracks is not None:
        arrays["cracks"], arrays["cam"] = cracks
    pf = []
    for i in range(n if paths is not None else 0):
        for pts, w, a, _z in (paths[i] or []):
            pts = np.asarray(pts, np.float64)
            if pts.ndim == 3 and cracks is not None:
                continue
            if pts.ndim == 3:
                blk = np.empty((len(pts), 9))
                blk[:, 0], blk[:, 1], blk[:, 2] = i, 2, w
                blk[:, 3], blk[:, 4], blk[:, 6], blk[:, 7] = pts[:, 0, 0], pts[:, 0, 1], pts[:, 1, 0], pts[:, 1, 1]
                blk[:, 5] = blk[:, 8] = np.broadcast_to(np.asarray(a, np.float64), (len(pts),))
                pf.append(blk.reshape(-1))
                continue
            if len(pts) < 2:
                continue
            av = np.broadcast_to(np.asarray(a, np.float64), (len(pts),))
            pf.append(np.concatenate([[i, len(pts), w], np.stack([pts[:, 0], pts[:, 1], av], 1).reshape(-1)]))
    arrays["paths"] = np.concatenate(pf).astype(np.float32) if pf else np.zeros(0, np.float32)
    return arrays


STREAM = threading.local()
PART_FIRST, PART_EVERY, PART_GAP = 6, 12, 0.15
FRAME_KEYS = ("x", "y", "z", "vx", "vy", "size", "alpha", "vis", "age", "rot", "zd")


def _part_sender(header, P, premask, emit):
    state = {"sent": 0, "t": 0.0}
    STREAM.sent = 0

    def on_frame(i, rec, st, used):
        done, n = i + 1, rec["x"].shape[0]
        new, now = done - state["sent"], time.time()
        if done >= n or new < (PART_FIRST if not state["sent"] else PART_EVERY) or (state["sent"] and now - state["t"] < PART_GAP):
            return
        a = state["sent"]
        part = {k: rec[k][a:done, :used] for k in FRAME_KEYS if k in rec}
        part["rnd"] = st["rnd"][:used]
        em = types.SimpleNamespace(n=done - a, W=header["W"], H=header["H"], zref=0.5)
        arrays = encode({"rec": part, "em": em, "paths": None}, P, premask)
        STREAM.emit(pack({**header, "n": n, "stream": "part", "from": a, "to": done}, arrays))
        state["sent"], state["t"] = done, now
        STREAM.sent = done
    return on_frame


def frames_from(arrays, a):
    offs = arrays["offs"].astype(np.int64)
    k = int(offs[a])
    out = dict(arrays)
    out["offs"] = (offs[a:] - k).astype(np.uint32)
    for name in ("id", "x", "y", "r", "a", "age", "vx", "vy", "rot"):
        out[name] = arrays[name][k:]
    return out


def compact_cracks(paths, em, n):
    tab, cam = getattr(em, "crack_table", None), getattr(em, "cam", None)
    if paths is None or cam is None or tab is None or not len(tab):
        return None
    tab = tab[np.argsort(tab[:, 0], kind="stable")]
    mats = np.array([np.asarray(cam.m[i], np.float64)[:2].reshape(-1) for i in range(n)], np.float32).reshape(-1)
    return tab.astype(np.float32).reshape(-1), mats


def pack(header, arrays):
    blobs, at, table = [], 0, []
    for name, arr in (arrays or {}).items():
        b = np.ascontiguousarray(arr).tobytes()
        table.append({"name": name, "type": arr.dtype.name, "offset": at, "length": int(arr.size)})
        blobs.append(b + b"\0" * (-len(b) % 4))
        at += len(blobs[-1])
    head = json.dumps({**header, "arrays": table}).encode()
    head += b" " * (-len(head) % 4)
    return struct.pack("<I", len(head)) + head + b"".join(blobs)


RUNNER = Runner()
SIM_CACHE = collections.OrderedDict()
CAMERAS = collections.OrderedDict()
DEPTHS = collections.OrderedDict()
MEMOS = collections.OrderedDict()
MOTIONS = {}
WORKER = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix="ef-live")
LATEST = [0]


def mask_box(rec):
    any_ = np.zeros(rec["gone"][0].shape, bool)
    for g, b in zip(rec["gone"], rec["band"]):
        any_ |= (g > 0) | (b > 0)
    ys, xs = np.nonzero(any_.any(1))[0], np.nonzero(any_.any(0))[0]
    if not len(ys):
        return [0, 0, 0, 0]
    return [int(xs[0]), int(ys[0]), int(xs[-1] + 1 - xs[0]), int(ys[-1] + 1 - ys[0])]


def encode_dissolve(rec, box=None):
    x0, y0, bw, bh = box or mask_box(rec)
    offs, ids, xs, ys, cols, als = [0], [], [], [], [], []
    for pid, x, y, c, a in rec["frames"]:
        k = (a > 1e-3) & (np.abs(x) < 4000) & (np.abs(y) < 4000)
        ids.append(pid[k].astype(np.uint32))
        xs.append(np.round(x[k] * 8).astype(np.int16))
        ys.append(np.round(y[k] * 8).astype(np.int16))
        cols.append(np.clip(np.round(c[k] * 255), 0, 255).astype(np.uint8).reshape(-1))
        als.append(np.clip(np.round(a[k] * 255), 0, 255).astype(np.uint8))
        offs.append(offs[-1] + int(k.sum()))
    cat = lambda v, t: np.concatenate(v).astype(t) if v else np.zeros(0, t)
    return {"offs": np.asarray(offs, np.uint32), "id": cat(ids, np.uint32), "x": cat(xs, np.int16), "y": cat(ys, np.int16),
            "col": cat(cols, np.uint8), "a": cat(als, np.uint8),
            "gone": np.ascontiguousarray(np.stack(rec["gone"])[:, y0:y0 + bh, x0:x0 + bw]).reshape(-1),
            "band": np.ascontiguousarray(np.stack(rec["band"])[:, y0:y0 + bh, x0:x0 + bw]).reshape(-1)}


async def compute_dissolve(graph, body, ctx, t0, node):
    import nodes
    sigs = ctx["sigs"]
    try:
        _obj, data, _v3 = await RUNNER.prepare(graph, node, nodes.NODE_CLASS_MAPPINGS["EFDissolve"], ctx)
    except Missing as m:
        raise ValueError(f"the dissolve needs the object's mask: track it first (Position) ({m})") from m
    kw = {k: (v[0] if isinstance(v, list) and v else None) for k, v in data.items()}
    if kw.get("mask") is None:
        raise ValueError("the dissolve needs the object's mask: track it first (Position)")
    inputs = graph[node]["inputs"]
    parts = [[k, [sigs.get(v[0]), v[1]] if is_link(v) else v] for k, v in sorted(inputs.items()) if k != "clean_plate"]
    key = "d" + hashlib.sha1(json.dumps(parts, default=str).encode()).hexdigest()[:19]
    pl = PN._np(kw["plate"])[..., :3]
    fps = float(kw["fps"])
    header = {"key": key, "kind": "dissolve", "mode": "play", "fps": fps, "W": int(pl.shape[2]), "H": int(pl.shape[1]), "frame": 0,
              "start": float(kw["start_seconds"]), "preroll": 0.0, "preroll_s": 0.0, "seed": int(kw["seed"]),
              "left_out": sorted(set(ctx["left_out"])), "fallbacks": [], "cached": key in SIM_CACHE}
    dvals = [kw[k] if kw.get(k) is not None else d for k, d in zip(DISSOLVE_ARGS, (
        1.0, 1.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 1.0, 0.0, "plain", "", "auto"))]
    P, _style = DS.node_params(*dvals)
    Pb, _ = DS.node_params(*[("" if k == "extra" else v) for k, v in zip(DISSOLVE_ARGS, dvals)])
    full, fullb = dict(DS.DEFAULTS, **P), dict(DS.DEFAULTS, **Pb)
    header.update(params={k: full[k] for k in DPANEL if k in full}, base={k: fullb[k] for k in DPANEL if k in fullb})
    t1 = time.time()
    if key in SIM_CACHE:
        rec = SIM_CACHE[key]
        SIM_CACHE.move_to_end(key)
    else:
        mk = PN._np(kw["mask"])
        mk = mk.reshape(-1, *mk.shape[-2:])
        fit = DS.fit_duration(len(pl), fps, kw["start_seconds"], kw["duration_seconds"], dict(DS.DEFAULTS, **P))
        rec = {}
        dargs = (pl, mk, kw["direction"], kw["start_seconds"], fit["duration"], fps, int(kw["seed"]), P, None, DS.plate_flow(pl, P))
        if body.get("profile"):
            import cProfile
            import io
            import pstats
            prof = cProfile.Profile()
            r = prof.runcall(DS.dissolve, *dargs, record=rec)
            out = io.StringIO()
            pstats.Stats(prof, stream=out).sort_stats("tottime").print_stats(14)
            header["profile"] = out.getvalue()[-6000:]
        else:
            r = DS.dissolve(*dargs, record=rec)
        rec["stats"] = r["stats"]
        rec["n"] = len(pl)
        rec["box"] = mask_box(rec)
        SIM_CACHE[key] = rec
        while len(SIM_CACHE) > SIMS:
            SIM_CACHE.popitem(last=False)
    gh, gw = rec["gone"][0].shape
    header.update(n=rec["n"], look={"blur": rec["blur"], "glow": rec["glow"], "glow_color": rec["glow_color"], "tint": rec["tint"]},
                  small=[gw, gh], box=rec["box"], stats={k: int(v) for k, v in rec["stats"].items()},
                  ms={"sim": round((time.time() - t1) * 1000), "total": round((time.time() - t0) * 1000)}, node_seconds=ctx["times"])
    if body.get("have") == key:
        return header, None
    return header, encode_dissolve(rec, rec["box"])


def _plate_points(pts, cr, n):
    a = np.array([[p["x"], p["y"]] for p in pts], np.float64)
    if not cr or "crop_origin_plate_px" not in cr:
        return a
    m = int(cr["frames"])
    org = np.array(cr["crop_origin_plate_px"], np.float64)[:m]
    sc = np.array(cr.get("scale_per_frame", [cr["scale_roi_per_plate_px"]] * m), np.float64)[:m]
    if m < n:
        org, sc = np.pad(org, ((0, n - m), (0, 0)), mode="edge"), np.pad(sc, (0, n - m), mode="edge")
    return org[:n] + a / sc[:n, None]


async def compute_motion(graph, body, ctx, t0):
    import nodes
    from ..tracking import motion as MO
    if MOTION not in graph:
        raise ValueError("this workflow has no EF Motion Tracks")
    cls = nodes.NODE_CLASS_MAPPINGS["EFMotionTracks"]
    fallbacks = []
    try:
        _obj, data, _v3 = await RUNNER.prepare(graph, MOTION, cls, ctx)
    except Missing as m:
        ctx["left_out"].append(str(m))
        graph = json.loads(json.dumps(graph))
        for k in ("track", "crop"):
            if is_link(graph[MOTION]["inputs"].get(k)):
                graph[MOTION]["inputs"][k] = list(FALLBACK["track"])
                fallbacks.append(k)
        _obj, data, _v3 = await RUNNER.prepare(graph, MOTION, cls, ctx)
    kw = {k: (v[0] if isinstance(v, list) and v else None) for k, v in data.items()}
    kw = {k: v for k, v in kw.items() if v is not None}
    t1 = time.time()
    tracks, _cw, _ch, report, _below = MO.EFMotionTracks().tracks(**kw)
    out = json.loads(tracks)
    n = len(out[0])
    cr = kw.get("crop") or kw["track"]
    emit, tip = _plate_points(out[0], cr, n), _plate_points(out[1], cr, n)
    r1 = lambda a: np.round(a, 1).tolist()
    return {"kind": "motion", "key": "m" + hashlib.sha1(json.dumps([r1(emit), r1(tip)]).encode()).hexdigest()[:19], "n": n,
            "fps": float(kw.get("fps", 30.0)), "emit": r1(emit), "tip": r1(tip), "report": report,
            "strength": float(kw["amount"]), "lag": float(kw["inertia"]), "fallbacks": fallbacks,
            "left_out": sorted(set(ctx["left_out"])),
            "ms": {"motion": round((time.time() - t1) * 1000), "total": round((time.time() - t0) * 1000)}}, None


def _needs(m):
    s = str(m)
    if "SAM3" in s:
        return "the object's track (Position: click the object, then Track it)"
    if "DepthAnything" in s or "DA3" in s:
        return "the depth of the clip (Clip: Analysis)"
    return s


async def compute_shape(graph, ctx):
    import nodes
    from ..generation import guides as GD
    if SHAPE not in graph:
        raise ValueError("this workflow has no object shape guide")
    cls = nodes.NODE_CLASS_MAPPINGS["EFGuide"]
    try:
        _obj, data, _v3 = await RUNNER.prepare(graph, SHAPE, cls, ctx)
    except Missing as m:
        raise ValueError(f"The object shape needs {_needs(m)}.") from m
    kw = {k: (v[0] if isinstance(v, list) and v else None) for k, v in data.items()}
    kw = {k: v for k, v in kw.items() if v is not None}
    for k in ("object_mask", "depth"):
        if k not in kw:
            raise ValueError(f"The object shape needs {'the depth of the clip (Clip: Analysis)' if k == 'depth' else 'the object (click it)'}.")
    t1 = time.time()
    _full, roi, report, att = GD.EFGuide().make(**kw)
    g, a = PN._np(roi)[..., 0], PN._np(att)
    n, rh, rw = g.shape
    k = SHAPE_SIDE / max(rh, rw)
    w, h = max(1, round(rw * k)), max(1, round(rh * k))
    small = lambda x: np.stack([cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA) for f in x])
    cr = kw.get("crop")
    rects = []
    if cr:
        m = int(cr.get("frames", n))
        sc = cr.get("scale_per_frame") or [cr["scale_roi_per_plate_px"]] * m
        for i in range(n):
            s = float(sc[min(i, len(sc) - 1)])
            ox, oy = cr["crop_origin_plate_px"][min(i, len(cr["crop_origin_plate_px"]) - 1)]
            rects.append([round(float(ox), 1), round(float(oy), 1), round(rw / s, 1), round(rh / s, 1)])
    head = {"n": n, "w": w, "h": h, "rects": rects, "fps": float(kw.get("fps", 30.0)), "report": json.loads(report),
            "ms": round((time.time() - t1) * 1000)}
    q = lambda x: np.clip(np.round(small(x) * 255), 0, 255).astype(np.uint8).reshape(-1)
    return head, {"shape": q(g), "attention": q(a)}


async def compute_ai(graph, body, ctx, t0):
    parts = [p for p in (body.get("parts") or ["motion"]) if p in ("motion", "shape")]
    head, arrays = {"kind": "motion", "parts": parts}, None
    if "motion" in parts:
        h, _ = await compute_motion(graph, body, ctx, t0)
        head.update(h)
    if "shape" in parts:
        head["shape"], arrays = await compute_shape(graph, ctx)
        head["shape"]["sum"] = int(arrays["shape"].sum(dtype=np.int64))
    head["parts"] = parts
    head["key"] = "a" + hashlib.sha1(json.dumps([head.get("key"), head.get("shape")], default=str).encode()).hexdigest()[:19]
    head["left_out"] = sorted(set(ctx["left_out"]))
    head.setdefault("ms", {})["total"] = round((time.time() - t0) * 1000)
    return head, arrays


async def compute(body, check):
    t0 = time.time()
    mode = "hold" if body.get("mode") == "hold" else "play"
    variant = body.get("variant", "app")
    graph = AR.build_graph(variant, dict(body.get("values") or {}), "live")
    if body.get("kind") == "motion":
        return await compute_ai(graph, body, {"sigs": signatures(graph), "check": check, "left_out": [], "times": {}}, t0)
    node = next((k for k in DISSOLVE if k in graph), None) if variant == "dissolve" else None
    if node:
        return await compute_dissolve(graph, body, {"sigs": signatures(graph), "check": check, "left_out": [], "times": {}}, t0, node)
    if PARTICLES not in graph:
        raise ValueError("this workflow has no EF Particles to preview")
    sigs = signatures(graph)
    ctx = {"sigs": sigs, "check": check, "left_out": [], "times": {}}
    import nodes
    cls = nodes.NODE_CLASS_MAPPINGS["EFParticles"]
    _obj, data, _v3 = await RUNNER.prepare(graph, PARTICLES, cls, ctx)
    kw = {k: (v[0] if isinstance(v, list) and v else None) for k, v in data.items()}
    inputs = dict(graph[PARTICLES]["inputs"])
    fallbacks = []
    for k, (src, idx) in ({} if body.get("params_only") else FALLBACK).items():
        if kw.get(k) is None and is_link(inputs.get(k)) and src in graph:
            try:
                kw[k] = (await RUNNER.run(graph, src, ctx)).outputs[idx][0]
                inputs[k] = [src, idx]
                fallbacks.append(k)
            except Missing as m:
                ctx["left_out"].append(str(m))
    t_inputs = time.time() - t0
    plate = PN._np(kw["plate"])
    n0, fps = len(plate), float(kw["fps"])
    frame = int(np.clip(int(body.get("frame") or 0), 0, n0 - 1))
    seconds = float(np.clip(float(body.get("seconds") or HOLD_SECONDS), 1.0, 30.0))
    settings = kw.get("settings") or {}
    if mode == "hold" and "motion_carry" in (settings.get("final") or {}):
        settings = {**settings, "final": {a: b for a, b in settings["final"].items() if a != "motion_carry"}}
        kw["settings"] = settings
    key = sim_key(inputs, sigs, settings, mode, frame, seconds)
    args = {k: kw.get(k) for k in SETUP_ARGS}
    for k, d in (("area", "0.4, 0.4, 0.6, 0.6"), ("depth_offset", 0.0), ("premask", True), ("edge_fade", 0.08),
                 ("camera", "follow the plate"), ("line_attach", "track"), ("motion_carry", 0.0), ("screen_fixed", False)):
        if args[k] is None:
            args[k] = d
    pargs = (args["speed"], args["size"], args["life"], 0.0 if mode == "hold" else args["start_seconds"], args["depth_offset"],
             args["direction"], args["spread"], args["follow"], 0.0 if mode == "hold" else args["motion_carry"])
    P = PN.params_for(args["preset"], settings, *pargs)
    base = PN.params_for(args["preset"], PN.split_final(settings)[0], *pargs[:5], -1.0, *pargs[6:])
    header = {"key": key, "mode": mode, "fps": fps, "W": int(plate.shape[2]), "H": int(plate.shape[1]), "frame": frame,
              "seconds": seconds if mode == "hold" else None, "start": 0.0 if mode == "hold" else float(args["start_seconds"]),
              "preroll": float(P["preroll"]), "seed": int(args["seed"]), "preset": args["preset"], "look": look_of(P),
              "amount": float(args["amount"] if args["amount"] is not None else 1.0), "emitter": args["emitter"],
              "params": {k: P[k] for k in PANEL if k in P}, "base": {k: base[k] for k in PANEL if k in base},
              "fallbacks": fallbacks, "left_out": sorted(set(ctx["left_out"])), "cached": key in SIM_CACHE}
    if body.get("params_only"):
        return header, None
    if body.get("have") == key and key in SIM_CACHE:
        header.update(n=SIM_CACHE[key]["n"], preroll_s=round(preroll_seconds(SIM_CACHE[key]["P"], SIM_CACHE[key]["em"]), 3), ms={"inputs": round(t_inputs * 1000), "total": round((time.time() - t0) * 1000)})
        return header, None
    t1 = time.time()
    if args["depth"] is not None and is_link(inputs.get("depth")):
        dk = json.dumps([sigs.get(inputs["depth"][0]), inputs["depth"][1]])
        if dk not in DEPTHS:
            d = PN._np(args["depth"])
            DEPTHS[dk] = np.ascontiguousarray(d[..., 0] if d.ndim == 4 else d, np.float32)
            while len(DEPTHS) > 2:
                DEPTHS.popitem(last=False)
        args["depth"] = DEPTHS[dk]
    mot = motion_key(inputs, sigs, P, mode, frame, seconds)
    was = SIM_CACHE.get(MOTIONS.get(mot)) if key not in SIM_CACHE and P["path"] == "particles" else None
    again = pt.relook(was["rec"], P) if was is not None and was["P"]["path"] == "particles" else None
    if key in SIM_CACHE:
        s = SIM_CACHE[key]
        SIM_CACHE.move_to_end(key)
    elif again is not None:
        s = dict(was, rec=again, P=P)
        header["relook"] = True
        SIM_CACHE[key] = s
        while len(SIM_CACHE) > SIMS:
            SIM_CACHE.popitem(last=False)
        MOTIONS[mot] = key
    else:
        if mode == "hold":
            n = max(2, int(round(seconds * fps)))
            args.update(plate=held(plate, frame, n), track=hold_track(args["track"], frame, n),
                        track_b=hold_track(args["track_b"], frame, n), mask=held(args["mask"], frame, n),
                        depth=held_one(args["depth"], frame), start_seconds=0.0, motion_carry=0.0, look_plate=None)
            cam = pt.Camera(n)
        elif args["screen_fixed"] or args["camera"] == "fixed" or n0 < 2:
            cam = pt.Camera(n0)
        else:
            ck = json.dumps([[sigs.get(inputs["plate"][0]), inputs["plate"][1]] if is_link(inputs.get("plate")) else None,
                             [sigs.get(inputs["mask"][0]), inputs["mask"][1]] if is_link(inputs.get("mask")) and args["mask"] is not None else None])
            cam = CAMERAS.get(ck)
            if cam is None:
                cam = pt.Camera.from_plate(plate[..., :3], PN._mask3(args["mask"]) if args["mask"] is not None else None)
                CAMERAS[ck] = cam
                while len(CAMERAS) > 4:
                    CAMERAS.popitem(last=False)
        check()
        mk = json.dumps([[sigs.get(inputs[k][0]), inputs[k][1]] if is_link(inputs.get(k)) else None for k in ("plate", "mask", "drawing")]
                        + [mode, frame if mode == "hold" else None])
        memo = MEMOS.setdefault(mk, {})
        MEMOS.move_to_end(mk)
        while len(MEMOS) > 2:
            MEMOS.popitem(last=False)
        if body.get("profile"):
            import cProfile
            import io
            import pstats
            prof = cProfile.Profile()
            s = prof.runcall(PN.setup, **args, cam=cam, memo=memo)
            out = io.StringIO()
            pstats.Stats(prof, stream=out).sort_stats("cumtime").print_stats(18)
            header["profile"] = out.getvalue()[-6000:]
        else:
            on = STREAM.__dict__.get("emit")
            if on is not None:
                PN.LIVE.on_frame = _part_sender(header, P, bool(args["premask"]), on)
            try:
                s = PN.setup(**args, cam=cam, memo=memo)
            finally:
                PN.LIVE.on_frame = None
        s["plate"] = args["plate"]
        s.pop("pl", None)
        s["em"].memo = None
        SIM_CACHE[key] = s
        while len(SIM_CACHE) > SIMS:
            SIM_CACHE.popitem(last=False)
        MOTIONS[mot] = key
        for m_ in [m_ for m_, k_ in MOTIONS.items() if k_ not in SIM_CACHE]:
            del MOTIONS[m_]
    if float(P.get("plate_color", 0) or 0) > 0 and "pcol" not in s["rec"]:
        s["rec"]["pcol"] = pt.plate_colours(s["rec"], PN._np(s["plate"])[..., :3])
    t_sim = time.time() - t1
    arrays = encode(s, P, bool(args["premask"]))
    sent = STREAM.__dict__.get("sent", 0)
    if sent:
        arrays = frames_from(arrays, sent)
        header.update(stream="end", **{"from": sent, "to": int(s["n"])})
    st = s["rec"].get("stats", {})
    header.update(n=int(s["n"]), preroll_s=round(preroll_seconds(s["P"], s["em"]), 3), stats={k: int(v) for k, v in st.items() if isinstance(v, (int, np.integer))},
                  ms={"inputs": round(t_inputs * 1000), "sim": round(t_sim * 1000), "total": round((time.time() - t0) * 1000)},
                  node_seconds=ctx["times"])
    return header, arrays


def _job(seq, body, emit=None):
    def check():
        if LATEST[0] != seq:
            raise Superseded()
    PN.LIVE.check = check
    STREAM.emit, STREAM.sent = emit, 0
    try:
        return pack(*asyncio.run(compute(body, check)))
    finally:
        PN.LIVE.check = None
        STREAM.emit, STREAM.sent = None, 0
        RUNNER.trim()


def _values_job(body):
    return pack(*asyncio.run(compute({**body, "params_only": True}, lambda: None)))


LOOPBACK = ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost")


def _local(request):
    try:
        host = request.url.host or ""
    except Exception:
        host = ""
    return (request.remote or "") in LOOPBACK and host in LOOPBACK


routes = server.PromptServer.instance.routes


@routes.post("/element-forge/api/live")
async def ef_live(request):
    body = await request.json()
    LATEST[0] += 1
    seq = LATEST[0]
    if body.get("stream"):
        return await _live_stream(request, seq, body)
    try:
        data = await asyncio.get_running_loop().run_in_executor(WORKER, _job, seq, body)
    except Superseded:
        return web.json_response({"error": "superseded"}, status=409)
    except (ValueError, KeyError, Missing) as e:
        return web.json_response({"error": str(e)}, status=400)
    resp = web.Response(body=data, content_type="application/octet-stream")
    resp.headers["Cache-Control"] = "no-store"
    if not _local(request):
        resp.enable_compression()
    return resp


async def _live_stream(request, seq, body):
    loop = asyncio.get_running_loop()
    q = asyncio.Queue()
    put = lambda b: loop.call_soon_threadsafe(q.put_nowait, b)
    fut = loop.run_in_executor(WORKER, _job, seq, body, put)
    fut.add_done_callback(lambda f: loop.call_soon_threadsafe(q.put_nowait, None))
    resp = web.StreamResponse(headers={"Content-Type": "application/x-ef-live-stream", "Cache-Control": "no-store"})
    if not _local(request):
        resp.enable_compression()
    await resp.prepare(request)
    while True:
        b = await q.get()
        if b is None:
            break
        await resp.write(struct.pack("<I", len(b)) + b)
    try:
        last = fut.result()
    except Superseded:
        last = pack({"error": "superseded", "status": 409}, None)
    except (ValueError, KeyError, Missing) as e:
        last = pack({"error": str(e), "status": 400}, None)
    await resp.write(struct.pack("<I", len(last)) + last)
    await resp.write_eof()
    return resp


@routes.post("/element-forge/api/dissolve-values")
async def ef_dissolve_values(request):
    body = await request.json()
    try:
        style, extra = str(body.get("style") or "plain"), str(body.get("extra") or "")
        args = (1.0, 1.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 1.0, 0.0, style)
        base, _ = DS.node_params(*args, "", "auto")
        now, _ = DS.node_params(*args, extra, "auto")
    except (ValueError, KeyError, TypeError) as e:
        return web.json_response({"error": str(e)}, status=400)
    keep = lambda p: {k: v for k, v in {**DS.DEFAULTS, **p}.items() if isinstance(v, (int, float, str))}
    return web.json_response({"params": keep(now), "base": keep(base)})


@routes.post("/element-forge/api/live-values")
async def ef_live_values(request):
    body = await request.json()
    try:
        data = await asyncio.get_running_loop().run_in_executor(WORKER, _values_job, body)
    except (ValueError, KeyError, Missing) as e:
        return web.json_response({"error": str(e)}, status=400)
    resp = web.Response(body=data, content_type="application/octet-stream")
    resp.headers["Cache-Control"] = "no-store"
    return resp

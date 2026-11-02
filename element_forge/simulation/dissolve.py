import json
import math
import time

import cv2
import numpy as np
import torch

from .particles import CurlNoise, dither, hash_u, smoothstep


def fbm_texture(size=256, octaves=5, seed=0):
    out = np.zeros((size, size), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        g = 4 * 2 ** o
        yy, xx = np.mgrid[0:g, 0:g]
        grid = hash_u(xx, yy, np.full_like(xx, o), seed=seed)
        big = cv2.resize(np.tile(grid, (3, 3)), (3 * size, 3 * size), interpolation=cv2.INTER_CUBIC)[size:2 * size, size:2 * size]
        out += amp * big
        tot += amp
        amp *= 0.5
    out /= tot
    lo, hi = np.percentile(out, 1), np.percentile(out, 99)
    return np.clip((out - lo) / max(hi - lo, 1e-6), 0, 1)


def _hex(c, default=(1.0, 0.55, 0.15)):
    c = (c or "").strip().lstrip("#")
    if len(c) != 6:
        return np.array(default, np.float32)
    return np.array([int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], np.float32)


DEFAULTS = {
    "edge_noise": 0.5,
    "noise_size": 0.25,
    "grain": 0.04,
    "softness": 0.03,
    "density": 0.35,
    "radial": 0.0,
    "burst": 0.0,
    "push": 160.0,
    "lift": 70.0,
    "spread": 60.0,
    "inherit": 1.0,
    "motion_carry": 0.0,
    "gravity": -40.0,
    "drag": 0.4,
    "turbulence": 120.0,
    "turb_scale": 160.0,
    "life": 2.0,
    "size": 1.0,
    "fade_out": 0.5,
    "tint": 0.0,
    "glow": 0.0,
    "glow_width": 0.06,
    "glow_color": "#ff8c26",
    "grow": 0.006,
    "fill_grow": 0.02,
    "max_spawn": 40000,
    "fill_spread": 0.05,
    "cp_kept": 0.035,
    "cp_match": 0.03,
    "fill_match": 0.02,
    "guide_tail": 0.3,
    "fit_clip": 1.0,
    "fill_grain": 1.0,
    "fill_align": 0.0,
}

STYLES = {"plain": {}, "fire (LTX)": {"glow": 1.5, "tint": 0.7}, "gold dust": {"glow": 1.5, "tint": 0.7},
          "explodes": {"glow": 0.8, "tint": 0.3, "radial": 1.0, "burst": 0.12, "push": 900.0, "lift": 250.0, "spread": 450.0,
                       "gravity": 1400.0, "drag": 1.2, "turbulence": 40.0, "density": 0.3, "size": 3.0, "life": 1.6,
                       "edge_noise": 0.7, "glow_width": 0.25, "softness": 0.1}}
SPEED_KEYS = ("push", "lift", "spread", "turbulence", "gravity")


def style_name(style):
    k = (style or "plain").strip().lower()
    for name in STYLES:
        if k == name.lower() or (k and name.lower().startswith(k.split()[0])):
            return name
    raise ValueError(f"unknown dissolve style {style!r}; choose one of: {', '.join(STYLES)}")


def regrain(fill, plate, need, around, amount, rng):
    lum = lambda x: x @ np.float32([0.2126, 0.7152, 0.0722])
    hp = lambda y: y - cv2.GaussianBlur(y, (0, 0), 1.2)
    hp_p = hp(lum(plate))
    if around.sum() < 64 or not need.any():
        return fill
    target = 1.4826 * float(np.median(np.abs(hp_p[around])))
    hp_f = hp(lum(fill))
    local = np.sqrt(cv2.GaussianBlur(hp_f ** 2, (0, 0), 4.0))
    add = np.sqrt(np.maximum(target ** 2 - local ** 2, 0)) * amount * need
    nz = cv2.GaussianBlur(rng.standard_normal(need.shape).astype(np.float32), (0, 0), 0.6) * 1.6
    return fill + (nz * add)[..., None]


def lowfreq_offset(diff, w, sigma, eps=0.05):
    w = w.astype(np.float32)
    glob = (diff * w[..., None]).sum((0, 1)) / max(float(w.sum()), 1e-6)
    H, W = w.shape
    f = int(min(8, max(1, sigma // 4)))
    if f > 1:
        sw, sh = max(1, W // f), max(1, H // f)
        dw = cv2.resize(diff * w[..., None], (sw, sh), interpolation=cv2.INTER_AREA)
        ws = cv2.resize(w, (sw, sh), interpolation=cv2.INTER_AREA)
        num = cv2.GaussianBlur(dw.reshape(sh, sw, -1), (0, 0), sigma / f)
        den = cv2.GaussianBlur(ws, (0, 0), sigma / f)[..., None]
        off = (num + eps * glob) / (den + eps)
        return cv2.resize(off, (W, H), interpolation=cv2.INTER_LINEAR).reshape(H, W, -1)
    num = cv2.GaussianBlur(diff * w[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(w, (0, 0), sigma)[..., None]
    return (num + eps * glob) / (den + eps)


def pushpull_fill(img, hole):
    img = np.asarray(img, np.float32)
    known = (~np.asarray(hole, bool)).astype(np.float32)
    if known.sum() < 1:
        return img
    levels, I, Wt = [], img * known[..., None], known
    while min(Wt.shape) > 8:
        levels.append((I, Wt))
        I, Wt = cv2.pyrDown(I), cv2.pyrDown(Wt)
    cur = (I.reshape(-1, img.shape[-1]).sum(0) / max(float(Wt.sum()), 1e-6))[None, None] + 0 * I
    cur = np.where(Wt[..., None] > 1e-3, I / np.maximum(Wt, 1e-6)[..., None], cur)
    for I, Wt in reversed(levels):
        up = cv2.resize(cur, (Wt.shape[1], Wt.shape[0]), interpolation=cv2.INTER_LINEAR)
        a = np.clip(Wt, 0, 1)[..., None]
        cur = a * (I / np.maximum(Wt, 1e-6)[..., None]) + (1 - a) * up
    return np.where(known[..., None] > 0, img, cur).astype(np.float32)


def inpaint_f(img, hole, radius):
    m = hole.astype(np.uint8) * 255 if hole.dtype != np.uint8 else hole
    out = []
    for c in range(img.shape[-1]):
        ch = np.asarray(img[..., c], np.float32)
        lo, hi = float(ch.min()), float(ch.max())
        k = 65535.0 / max(hi - lo, 1e-6)
        q = cv2.inpaint(np.round((ch - lo) * k).astype(np.uint16), m, radius, cv2.INPAINT_TELEA)
        out.append(q.astype(np.float32) / k + lo)
    return np.stack(out, -1)


class Field:

    def __init__(self, masks, direction_deg, start, duration, P, seed, fps=None):
        n, H, W = masks.shape
        self.H, self.W, self.start, self.dur, self.P, self.seed = H, W, start, max(duration, 1e-3), P, seed
        if P.get("burst", 0) > 0:
            self.dur = max(min(float(P["burst"]), self.dur), 1e-3)
        a = math.radians(direction_deg)
        self.d = np.array([math.sin(a), -math.cos(a)], np.float32)
        self.e = np.array([-self.d[1], self.d[0]], np.float32)
        if fps:
            i0, i1 = int(math.floor((start - 0.25) * fps)), int(math.ceil((start + duration + 0.25) * fps))
        else:
            i0, i1 = 0, n
        cs, lo, hi, ext, win = [], [], [], [], []
        last = None
        for i, m in enumerate(masks):
            ys, xs = np.nonzero(m > 0.5)
            if len(xs) < 4:
                cs.append(last); continue
            c = np.array([xs.mean(), ys.mean()], np.float32)
            p = (xs - c[0]) * self.d[0] + (ys - c[1]) * self.d[1]
            q = (xs - c[0]) * self.e[0] + (ys - c[1]) * self.e[1]
            lo.append(np.percentile(p, 0.5)); hi.append(np.percentile(p, 99.5)); ext.append(np.ptp(q) + np.ptp(p))
            win.append(i0 <= i <= i1)
            cs.append(c); last = c
        first = next((c for c in cs if c is not None), np.array([W / 2, H / 2], np.float32))
        cs = np.array([first if c is None else c for c in cs], np.float32)
        if any(win):
            lo, hi, ext = [v for v, w in zip(lo, win) if w], [v for v, w in zip(hi, win) if w], [v for v, w in zip(ext, win) if w]
        k = max(1, int(round(len(cs) / 25)))
        if len(cs) > 2 * k:
            ker = np.ones(2 * k + 1, np.float32) / (2 * k + 1)
            cs = np.stack([np.convolve(np.pad(cs[:, j], k, mode="edge"), ker, "valid") for j in range(2)], 1)
        self.c = cs
        self.lo = float(np.median(lo)) if lo else -H / 4
        self.span = max(float(np.median(hi)) - self.lo, 4.0) if hi else H / 2
        self.ext = float(np.median(ext)) if ext else float(H)
        self.tex = fbm_texture(256, 5, seed)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy

    def times(self, i, box=None):
        P = self.P
        if box is not None:
            y0, y1, x0, x1 = box
            if not (y1 > y0 and x1 > x0):
                return np.full((self.H, self.W), 1e9, np.float32)
            v = self._times(self.xx[y0:y1, x0:x1] - self.c[i, 0], self.yy[y0:y1, x0:x1] - self.c[i, 1])
            out = np.full((self.H, self.W), 1e9, v.dtype)
            out[y0:y1, x0:x1] = v
            return out
        return self._times(self.xx - self.c[i, 0], self.yy - self.c[i, 1])

    def _times(self, rx, ry):
        P = self.P
        u = (rx * self.d[0] + ry * self.d[1] - self.lo) / self.span
        if P.get("radial", 0) > 0:
            k = min(float(P["radial"]), 1.0)
            u = (1 - k) * u + k * np.hypot(rx, ry) / max(0.5 * self.ext, 4.0)
        nz = P["edge_noise"]
        if nz > 0:
            f = 256.0 / max(P["noise_size"] * self.ext, 1.0)
            noise = cv2.remap(self.tex, (rx * f) % 256, (ry * f) % 256, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
            u = (u + nz * (noise - 0.5) + nz / 2) / (1 + nz)
        if P["grain"] > 0:
            g = hash_u(np.round(rx).astype(np.int64), np.round(ry).astype(np.int64), seed=self.seed + 11)
            u = u + P["grain"] * (g - 0.5)
        return self.start + self.dur * np.clip(u, 0.0, 1.0)


def first_k_median(smp, val, k):
    J, h, w = val.shape
    rank = np.cumsum(val, 0)
    sel = np.full((k, h, w, 3), np.nan, np.float32)
    for r in range(1, k + 1):
        hit = val & (rank == r)
        any_ = hit.any(0)
        idx = hit.argmax(0)
        v = np.take_along_axis(smp, idx[None, ..., None].repeat(3, -1), 0)[0]
        sel[r - 1][any_] = v[any_]
    cnt = np.minimum(rank[-1], k) if J else np.zeros((h, w), np.int64)
    srt = np.sort(sel, 0)
    lo = np.clip((cnt - 1) // 2, 0, k - 1)
    hi = np.clip(cnt // 2, 0, k - 1)
    g = lambda ix: np.take_along_axis(srt, ix[None, ..., None].repeat(3, -1), 0)[0]
    med = 0.5 * (g(lo) + g(hi))
    med[cnt == 0] = np.nan
    n_ = np.maximum(cnt, 1)[..., None].astype(np.float32)
    mean = np.where(np.isnan(sel), 0, sel).sum(0) / n_
    var = np.where(np.isnan(sel), 0, (sel - mean[None]) ** 2).sum(0) / n_
    return med, np.sqrt(var).mean(-1), cnt


class SceneFill:

    def __init__(self, plate, masks, grow_px, window=40, k=5, max_spread=0.05, match=0.0, align=0.0):
        from .particles import Camera
        self.plate, self.n, self.k, self.window, self.max_spread = plate, len(plate), k, window, max_spread
        self.match, self.align = match, align
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1))
        self.free = [(cv2.dilate((m > 0.5).astype(np.uint8), ker) == 0).astype(np.uint8) for m in masks]
        self.cam = Camera.from_plate(plate, masks) if self.n > 1 else Camera(1)
        self.holes = 0.0

    def frame(self, i, need, fallback=None):
        out = self.plate[i].astype(np.float32).copy()
        ys, xs = np.nonzero(need)
        if len(xs) == 0:
            return out
        H, W = need.shape
        sig = self.match * math.hypot(H, W)
        pad = int(round(1.5 * sig))
        if self.align > 0:
            pad = max(pad, int(round(0.05 * math.hypot(H, W))))
        x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
        x1, y1 = min(W, xs.max() + 1 + pad), min(H, ys.max() + 1 + pad)
        hw, hh = x1 - x0, y1 - y0
        order = sorted((j for j in range(self.n) if j != i), key=lambda j: abs(j - i))[: self.window]
        samples, valid = [], []
        for j in order:
            M = self.cam.m[i] @ np.linalg.inv(self.cam.m[j])
            T = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64) @ M
            samples.append(cv2.warpAffine(self.plate[j], T[:2], (hw, hh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE))
            valid.append(cv2.warpAffine(self.free[j], T[:2], (hw, hh), flags=cv2.INTER_NEAREST, borderValue=0) > 0)
        if samples:
            med, spread, cnt = first_k_median(np.stack(samples).astype(np.float32), np.stack(valid), self.k)
            if fallback is not None:
                med[(cnt < 2) | (spread > self.max_spread)] = np.nan
        else:
            med = np.full((hh, hw, 3), np.nan, np.float32)
        crop = out[y0:y1, x0:x1]
        nd = need[y0:y1, x0:x1]
        if self.align > 0:
            vis = ~nd & (self.free[i][y0:y1, x0:x1] > 0)
            med = seam_align(crop, med, vis, self.align, math.hypot(H, W))
        hole = nd & np.isnan(med[..., 0])
        fill = nd & ~hole
        if sig > 0 and fill.any():
            ring = (~nd & (self.free[i][y0:y1, x0:x1] > 0) & ~np.isnan(med[..., 0])).astype(np.float32)
            if ring.sum() > 16:
                dif = np.where(ring[..., None] > 0, crop - np.nan_to_num(med), 0).astype(np.float32)
                med = med + lowfreq_offset(dif, ring, sig)
        crop[fill] = med[fill]
        if hole.any():
            self.holes = max(self.holes, float(hole.sum()) / max(int(nd.sum()), 1))
        if hole.any() and fallback is not None:
            fb = fallback[y0:y1, x0:x1].astype(np.float32)
            if self.align > 0:
                fa = seam_align(crop, fb, ~nd & (self.free[i][y0:y1, x0:x1] > 0), self.align, math.hypot(H, W))
                fb = np.where(np.isnan(fa), fb, fa)
            wgt = np.maximum(cv2.GaussianBlur(hole.astype(np.float32), (0, 0), max(1.5, 0.004 * math.hypot(H, W))), hole)
            wgt = (wgt * nd)[..., None]
            crop[:] = crop * (1 - wgt) + fb * wgt
        elif hole.any():
            src_bad = hole | (self.free[i][y0:y1, x0:x1] == 0)
            if (~src_bad).sum() < 64:
                src_bad = hole
            big = hole.sum() > 0.002 * H * W
            crop[hole] = (pushpull_fill(crop, src_bad) if big else inpaint_f(crop, src_bad, 5))[hole]
        out[y0:y1, x0:x1] = crop
        return out


def seam_align(cur, src, vis, amount, diag):
    known = ~np.isnan(src[..., 0])
    sf = np.where(known[..., None], src, cur).astype(np.float32)
    est = vis & known
    if est.sum() < 64:
        return src
    f = flow_field(cur.astype(np.float32), sf, 1.0)
    g = cv2.cvtColor(np.clip(cur, 0, 1).astype(np.float32), cv2.COLOR_RGB2GRAY)
    gm = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    w = (est & (gm > np.percentile(gm[est], 70))).astype(np.float32)
    if w.sum() < 32:
        return src
    sig = max(2.0, 0.02 * diag)
    num = cv2.GaussianBlur(f * w[..., None], (0, 0), sig)
    den = cv2.GaussianBlur(w, (0, 0), sig)[..., None]
    fl = amount * num / np.maximum(den, 1e-6) * np.clip(den / max(float(den.max()) * 0.05, 1e-6), 0, 1)
    h, w_ = known.shape
    X, Y = np.meshgrid(np.arange(w_, dtype=np.float32), np.arange(h, dtype=np.float32))
    mx, my = X + fl[..., 0], Y + fl[..., 1]
    out = cv2.remap(sf, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    kn = cv2.remap(known.astype(np.uint8), mx, my, cv2.INTER_NEAREST, borderValue=0) > 0
    out[~kn] = np.nan
    return out


def match_colour(clean, plate, free, sigma):
    return clean + lowfreq_offset((plate - clean).astype(np.float32), free, sigma)


def refill_kept(b, clean, plate, need, thr, diag):
    sim = cv2.GaussianBlur(np.abs(clean - plate).max(-1), (0, 0), max(1.0, 0.006 * diag))
    used = np.abs(b - clean).max(-1) < 1e-3
    bad = need & used & (sim < thr)
    if bad.sum() < 16:
        return b
    bad8 = cv2.dilate(bad.astype(np.uint8), np.ones((5, 5), np.uint8))
    fill = inpaint_f(b.astype(np.float32), bad8, 7)
    w = cv2.GaussianBlur(bad8.astype(np.float32), (0, 0), 2.0)[..., None]
    return b * (1 - w) + fill * w


def flow_field(a, b, scale=0.5):
    g = lambda im: cv2.cvtColor(np.clip(cv2.resize(im, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    f = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(g(a), g(b), None)
    return cv2.resize(f, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_LINEAR) / scale


def splat(n_img, x, y, col, a, H, W):
    acc = np.zeros((H * W, 4), np.float32)
    ok = (x >= 0) & (x < W - 1) & (y >= 0) & (y < H - 1) & (a > 0)
    x, y, col, a = x[ok], y[ok], col[ok], a[ok]
    x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
    fx, fy = (x - x0).astype(np.float32), (y - y0).astype(np.float32)
    v = np.concatenate([col * a[:, None], a[:, None]], 1)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(acc, (y0 + dy) * W + x0 + dx, v * w[:, None])
    return acc.reshape(H, W, 4)


def dissolve(plate, masks, direction_deg, start, duration, fps, seed=1, P=None, background=None, flow=None, record=None):
    """Returns a dict of arrays: comp, particles (premultiplied RGB), particles_alpha, emission, person_matte,
    dissolve_mask, background, plus spawn statistics."""
    P = dict(DEFAULTS, **(P or {}))
    n, H, W = plate.shape[:3]
    if masks.shape[1:] != (H, W):
        masks = np.stack([cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) for m in masks])
    masks = np.stack([masks[min(i, len(masks) - 1)] for i in range(n)]).astype(np.float32)
    s = H / 1080.0
    grow_px = max(1, int(round(P["grow"] * math.hypot(H, W))))
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow_px + 1, 2 * grow_px + 1))
    field = Field(masks, direction_deg, start, duration, P, seed, fps)
    bg_info = "plate"
    mode = "none" if record is not None else P.get("background", "scene")
    clean = background.astype(np.float32) if background is not None else None
    if clean is not None and mode == "clean":
        bg = clean
        bg_info = "clean plate input"
    elif mode == "scene":
        bg = SceneFill(plate, masks, max(grow_px, int(round(P["fill_grow"] * math.hypot(H, W)))), max_spread=P["fill_spread"],
                       match=P["fill_match"], align=P["fill_align"])
        bg_info = "other frames, camera aligned" + (", clean plate where never free" if clean is not None else "")
    elif mode == "none":
        bg = None
        bg_info = "none (live preview)"
    else:
        bg = None
        bg_info = "inpaint per frame"
    glow_c = _hex(P["glow_color"])
    curl = CurlNoise(np.random.default_rng(seed + 3), P["turbulence"] * s, P["turb_scale"] * s, 0.3)
    grain_rng = np.random.default_rng(seed + 11)
    dt = 1.0 / fps
    if record is None:
        comp = np.empty_like(plate, dtype=np.float32)
        part = np.zeros((n, H, W, 3), np.float32)
        palpha = np.zeros((n, H, W), np.float32)
        emis = np.zeros((n, H, W, 3), np.float32)
        matte = np.zeros((n, H, W), np.float32)
        gone_m = np.zeros((n, H, W), np.float32)
        bg_out = np.zeros((n, H, W, 3), np.float32)
    else:
        record.update(frames=[], gone=[], band=[], glow_color=list(map(float, glow_c)), glow=float(P["glow"]), blur=float(P["size"] * s),
                      tint=float(P["tint"]))
        small = (max(1, W // 4), max(1, H // 4))
    px = np.zeros(0, np.float32); py = px.copy(); vx = px.copy(); vy = px.copy()
    age = px.copy(); life = px.copy(); col = np.zeros((0, 3), np.float32); pid = np.zeros(0, np.int64)
    stats = {"spawned": 0, "capped": 0, "outside": 0, "max_alive": 0}
    soft = max(P["softness"] * field.dur, 0.5 * dt)
    blur = P["size"] * s
    for i in range(n):
        t = i * dt
        m = masks[i]
        md = cv2.dilate((m > 0.5).astype(np.uint8), kern).astype(np.float32)
        md = np.maximum(md, m)
        ys_, xs_ = np.nonzero(md.max(1) > 0)[0], np.nonzero(md.max(0) > 0)[0]
        T = field.times(i, (ys_[0], ys_[-1] + 1, xs_[0], xs_[-1] + 1) if len(ys_) else (0, 0, 0, 0))
        alive = smoothstep((T - t) / soft + 0.5)
        keep = m * alive
        gone = md * (1 - alive)
        if record is not None:
            record["gone"].append(np.round(cv2.resize(gone, small, interpolation=cv2.INTER_AREA) * 255).astype(np.uint8))
            band = md * np.clip(1 - (T - t) / max(P["glow_width"] * field.dur, dt), 0, 1) * alive if P["glow"] > 0 else gone * 0
            record["band"].append(np.round(np.clip(cv2.resize(band, small, interpolation=cv2.INTER_AREA), 0, 1) * 255).astype(np.uint8))
            b_i = None
        elif bg is None:
            b_i = inpaint_f(plate[i].astype(np.float32), gone > 0.02, 5)
        else:
            cp_i = clean[min(i, len(clean) - 1)] if clean is not None else None
            if cp_i is not None and P["cp_match"] > 0 and gone.max() > 0.002:
                cp_i = match_colour(cp_i, plate[i], md < 0.5, P["cp_match"] * math.hypot(H, W))
            b_i = bg.frame(i, gone > 0.002, cp_i) if isinstance(bg, SceneFill) else cp_i
            if cp_i is not None and P["cp_kept"] > 0 and gone.max() > 0.002:
                b_i = refill_kept(b_i, cp_i, plate[i], gone > 0.002, P["cp_kept"], math.hypot(H, W))
        if record is None and P["fill_grain"] > 0 and gone.max() > 0.002:
            m8 = md.astype(np.uint8)
            around = (cv2.dilate(m8, kern, iterations=4) > 0) & ~(cv2.dilate(m8, kern, iterations=2) > 0)
            b_i = regrain(b_i, plate[i], (gone > 0.002).astype(np.float32), around, P["fill_grain"], grain_rng)
        base = plate[i] * (1 - gone[..., None]) + b_i * gone[..., None] if record is None else None
        if P["glow"] > 0 and record is None:
            band = md * np.clip(1 - (T - t) / max(P["glow_width"] * field.dur, dt), 0, 1) * alive
            emis[i] = band[..., None] * glow_c * P["glow"]
        born = (m > 0.5) & (T > t - dt) & (T <= t)
        ys, xs = np.nonzero(born)
        if len(xs):
            hu = hash_u(xs, ys, np.full_like(xs, i), seed=seed)
            sel = hu < P["density"]
            xs, ys = xs[sel], ys[sel]
            if len(xs) > P["max_spawn"]:
                stats["capped"] += len(xs) - P["max_spawn"]
                k = np.argsort(hash_u(xs, ys, seed=seed + 5))[: P["max_spawn"]]
                xs, ys = xs[k], ys[k]
        if len(xs):
            ids = (i * H + ys).astype(np.int64) * W + xs
            r1, r2, r3, r4 = (hash_u(ids, seed=seed + j) for j in (21, 22, 23, 24))
            dx, dy = np.full(len(xs), field.d[0], np.float32), np.full(len(xs), field.d[1], np.float32)
            if P.get("radial", 0) > 0:
                k = min(float(P["radial"]), 1.0)
                ox, oy = xs - field.c[i, 0], ys - field.c[i, 1]
                ol = np.maximum(np.hypot(ox, oy), 1.0)
                dx, dy = (1 - k) * dx + k * ox / ol, (1 - k) * dy + k * oy / ol
            nvx = (P["push"] * dx + P["spread"] * (2 * r1 - 1)) * s
            nvy = (P["push"] * dy - P["lift"] + P["spread"] * (2 * r2 - 1)) * s
            if flow is not None and P["inherit"] > 0 and n > 1:
                fl = flow(i) if callable(flow) else flow[i]
                nvx = nvx + P["inherit"] * fl[ys, xs, 0] * fps
                nvy = nvy + P["inherit"] * fl[ys, xs, 1] * fps
            px = np.concatenate([px, xs + r3 - 0.5]); py = np.concatenate([py, ys + r4 - 0.5])
            vx = np.concatenate([vx, nvx.astype(np.float32)]); vy = np.concatenate([vy, nvy.astype(np.float32)])
            age = np.concatenate([age, np.zeros(len(xs), np.float32)])
            life = np.concatenate([life, (P["life"] * (0.6 + 0.8 * hash_u(ids, seed=seed + 25))).astype(np.float32)])
            col = np.concatenate([col, plate[i][ys, xs, :3].astype(np.float32)])
            pid = np.concatenate([pid, ids])
            stats["spawned"] += len(xs)
        if len(px):
            new = age == 0
            cx, cy = curl(px, py, t)
            on = (~new).astype(np.float32)
            dr = math.exp(-P["drag"] * dt)
            vx = vx * (dr * on + (1 - on)) + 4.0 * cx * dt * on
            vy = vy * (dr * on + (1 - on)) + (4.0 * cy + P["gravity"] * s) * dt * on
            if flow is not None and P.get("motion_carry", 0) > 0 and n > 1:
                fl = flow(i) if callable(flow) else flow[i]
                xi = np.clip(px.astype(np.int64), 0, W - 1); yi = np.clip(py.astype(np.int64), 0, H - 1)
                ux, uy = fl[yi, xi, 0], fl[yi, xi, 1]
                inside = (px >= 0) & (px < W) & (py >= 0) & (py < H)
                w = smoothstep((np.hypot(ux, uy) / s - 0.3) / 1.2) * min(P["motion_carry"], 1.0) * on * inside
                vx = vx + w * (ux * fps - vx)
                vy = vy + w * (uy * fps - vy)
            px = px + vx * dt * on; py = py + vy * dt * on
            age = age + dt
            lf = np.clip(age / life, 0, 1)
            fo = P["fade_out"]
            a = np.ones_like(lf) if fo <= 0 else smoothstep((1 - lf) / fo)
            c = col * (1 - P["tint"] * lf[:, None]) + glow_c * (P["tint"] * lf[:, None])
            if record is not None:
                record["frames"].append((pid.copy(), px.copy(), py.copy(), c.astype(np.float32), a.astype(np.float32)))
                stats["max_alive"] = max(stats["max_alive"], len(px))
            else:
                acc = splat(n, px, py, c, a, H, W)
                if blur > 0.35:
                    acc = cv2.GaussianBlur(acc, (0, 0), blur)
                pa = np.clip(acc[..., 3], 0, 1)
                pc = acc[..., :3] / np.maximum(acc[..., 3:4], 1.0)
                part[i], palpha[i] = pc, pa
                if P["glow"] > 0 and P["tint"] > 0:
                    emis[i] += pc * P["glow"] * P["tint"]
                stats["max_alive"] = max(stats["max_alive"], len(px))
            dead = (age >= life) | (px < -50) | (px > W + 50) | (py < -50) | (py > H + 50)
            if dead.any():
                k = ~dead
                px, py, vx, vy, age, life, col, pid = px[k], py[k], vx[k], vy[k], age[k], life[k], col[k], pid[k]
        if record is not None:
            if len(record["frames"]) <= i:
                record["frames"].append((np.zeros(0, np.int64), np.zeros(0, np.float32), np.zeros(0, np.float32),
                                         np.zeros((0, 3), np.float32), np.zeros(0, np.float32)))
            continue
        comp[i] = base * (1 - palpha[i][..., None]) + part[i] + emis[i]
        matte[i], gone_m[i], bg_out[i] = keep, gone, b_i
    if record is not None:
        return {"stats": stats, "bg_info": bg_info, "field": field, "record": record}
    if isinstance(bg, SceneFill):
        bg_info += f" ({bg.holes:.1%} of a hole never free at most)"
    return {"comp": comp, "particles": part, "particles_alpha": palpha, "emission": emis, "person_matte": matte,
            "dissolve_mask": gone_m, "background": bg_out, "stats": stats, "bg_info": bg_info, "field": field}


def fit_duration(n, fps, start, duration, P):
    t_last = (n - 1) / fps
    tail = max(float(P.get("guide_tail", 0.0)), 0.0)
    soft = float(P.get("softness", 0.0)) / 2
    end = start + duration * (1 + soft)
    if start >= t_last:
        return {"duration": duration, "note": f"the dissolve starts at {start:.2f} s, after the clip's last frame "
                f"({t_last:.2f} s at {fps:g} fps) - nothing dissolves"}
    if end + tail <= t_last + 1e-6:
        return {"duration": duration, "note": ""}
    fitted = (t_last - tail - start) / (1 + soft)
    if P.get("fit_clip", 1.0) and fitted >= 0.25 * duration and fitted > 0.1:
        return {"duration": fitted, "note": f"duration shortened from {duration:.2f} s to {fitted:.2f} s so the dissolve "
                f"and the ember fade end inside the clip ({t_last:.2f} s at {fps:g} fps)"}
    return {"duration": duration, "note": f"the dissolve ends at {end:.2f} s (ember fade {end + tail:.2f} s), after the "
            f"clip's last frame ({t_last:.2f} s at {fps:g} fps) - the last part is still burning at the end"}


def node_params(amount, speed, size, life, edge_noise, glow, glow_color, inherit_motion, motion_carry, style, extra, background):
    P = {"density": DEFAULTS["density"] * amount, "edge_noise": edge_noise, "glow": glow, "glow_color": glow_color,
         "inherit": inherit_motion, "motion_carry": motion_carry, "size": DEFAULTS["size"] * size,
         "life": DEFAULTS["life"] * life}
    for k in ("push", "lift", "spread", "turbulence"):
        P[k] = DEFAULTS[k] * speed
    P["gravity"] = DEFAULTS["gravity"] * speed
    style = style_name(style)
    sty = STYLES[style]
    if sty:
        P["glow"] = glow if glow > 0 else sty["glow"]
        P["tint"] = sty["tint"]
        for k, v in sty.items():
            if k not in ("glow", "tint"):
                P[k] = v * speed if k in SPEED_KEYS else v * amount if k == "density" else v
    if extra.strip():
        P.update(json.loads(extra))
    P["density"] = min(1.0, P["density"])
    P["background"] = {"inpaint per frame": "inpaint", "clean plate": "clean"}.get(background, "scene")
    return P, style


def plate_flow(pl, P):
    if not ((P["inherit"] > 0 or P["motion_carry"] > 0) and len(pl) > 1):
        return None
    cache = {}

    def flow(i):
        if i not in cache:
            a, b = (i, i + 1) if i + 1 < len(pl) else (i - 1, i)
            cache.clear()
            cache[i] = flow_field(pl[a], pl[b])
        return cache[i]
    return flow


def _np(t):
    return t.detach().cpu().float().numpy() if torch.is_tensor(t) else np.asarray(t, np.float32)


class EFDissolve:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "The clip."}),
                "mask": ("MASK", {"tooltip": "Object mask per frame (e.g. SAM 3): what dissolves."}),
                "direction": ("FLOAT", {"default": 90.0, "min": 0.0, "max": 360.0, "step": 1.0, "tooltip": "Direction the front travels in degrees (0 up, 90 right, 180 down, 270 left), relative to the object, so it moves with a walking person."}),
                "start_seconds": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 600.0, "step": 0.05, "tooltip": "Second at which the front starts."}),
                "duration_seconds": ("FLOAT", {"default": 2.0, "min": 0.05, "max": 600.0, "step": 0.05, "tooltip": "Seconds until the whole object is gone. Shortened automatically if the dissolve (and the ember fade) would end after the clip (extra fit_clip 0 = keep; the report says so)."}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.85, "step": 0.05, "tooltip": "Times the particle density (1 = about every third dissolving pixel becomes a particle)."}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": "Times the push, lift and swirl of the particles."}),
                "size": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": "Times the particle size (softness)."}),
                "life": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 20.0, "step": 0.05, "tooltip": "Times the particle lifetime."}),
                "edge_noise": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 3.0, "step": 0.05, "tooltip": "How ragged the front is (0 a straight line)."}),
                "glow": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.05, "tooltip": "Glowing edge at the front (emission pass, also in the comp)."}),
                "fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "seed": ("INT", {"default": 1, "min": 0, "max": 2 ** 31 - 1}),
            },
            "optional": {
                "clean_plate": ("IMAGE", {"tooltip": "Background without the object (e.g. LTX Clean Plate). Without it: background from the other frames (camera aligned) or inpaint per frame. With it (auto): the other frames first, the clean plate only where the object never moves away."}),
                "background": (["auto", "clean plate", "other frames (camera aligned)", "inpaint per frame"], {"tooltip": "auto: the real background from the other frames (camera motion measured, nearest frames where the spot is free aligned, median); spots the object covers in every frame from the clean plate if connected (colour matched), else inpainted. clean plate: only the clean plate."}),
                "inherit_motion": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "Share of the object's motion (optical flow) the particles keep."}),
                "motion_carry": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How strongly moving things in the clip keep carrying the flying particles (optical flow of the plate): 0 off (only the motion at birth, inherit_motion), 1 they move with whatever moves under them. Still parts leave them to their physics."}),
                "glow_color": ("STRING", {"default": "#ff8c26", "tooltip": "Colour of the glowing edge (and of tinted particles)."}),
                "extra": ("STRING", {"default": "", "multiline": True, "tooltip": "Further settings as JSON, e.g. {\"tint\": 0.6, \"gravity\": -40, \"push\": 120}. The report lists all values."}),
                "style": ("STRING", {"default": "plain", "tooltip": "plain, fire (LTX), gold dust or explodes (short: fire, gold, expl). plain: the values as set. fire (LTX): glowing edge 1.5 and particles tinted towards the glow colour; output ltx_embers is true, so the workflow lets LTX turn them into real embers. gold dust: the same glowing particles without LTX. A glowing edge > 0 here and a tint in extra win over the style."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK", "IMAGE", "MASK", "MASK", "IMAGE", "STRING", "IMAGE", "IMAGE", "BOOLEAN")
    RETURN_NAMES = ("comp", "particles", "particles_alpha", "emission", "object_matte", "dissolve_mask", "background", "report",
                    "comp_no_glow", "glow_guide", "ltx_embers")
    FUNCTION = "run"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Particle dissolve: the masked object crumbles along a front into particles in its own colours and the "
                   "background appears. One dissolve-time field drives both the hole and the particles. Passes: particles "
                   "(premultiplied) + alpha, emission (glowing edge), object matte, dissolve mask, background.")

    def run(self, plate, mask, direction, start_seconds, duration_seconds, amount, speed, size, life, edge_noise, glow, fps,
            seed, clean_plate=None, background="auto", inherit_motion=1.0, glow_color="#ff8c26", extra="", style="plain",
            motion_carry=0.0):
        t0 = time.time()
        pl = _np(plate)[..., :3]
        mk = _np(mask)
        mk = mk.reshape(-1, *mk.shape[-2:])
        P, style = node_params(amount, speed, size, life, edge_noise, glow, glow_color, inherit_motion, motion_carry, style, extra, background)
        cp = _np(clean_plate)[..., :3] if clean_plate is not None and background in ("auto", "clean plate") else None
        if cp is not None and cp.shape[1:3] != pl.shape[1:3]:
            cp = np.stack([cv2.resize(f, (pl.shape[2], pl.shape[1]), interpolation=cv2.INTER_LINEAR) for f in cp])
        flow = plate_flow(pl, P)
        fit = fit_duration(len(pl), fps, start_seconds, duration_seconds, dict(DEFAULTS, **P))
        duration_seconds = fit["duration"]
        r = dissolve(pl, mk, direction, start_seconds, duration_seconds, fps, seed, P, cp, flow)
        rng = np.random.default_rng(seed + 9)
        st = r["stats"]
        rep = (f"style {style}; dissolve {direction:.0f} deg, {start_seconds:.2f} s + {duration_seconds:.2f} s: {st['spawned']} particles, "
               f"up to {st['max_alive']} at once; background: {r['bg_info']}; {time.time() - t0:.1f} s"
               + (f"; {st['capped']} particles not born (max_spawn)" if st["capped"] else "")
               + (f"; NOTE: {fit['note']}" if fit["note"] else "")
               + "\nsettings: " + json.dumps(dict(DEFAULTS, **{k: v for k, v in P.items()})))
        T = lambda a: torch.from_numpy(np.ascontiguousarray(a, np.float32))
        comp = dither(r["comp"], rng, lo=0, hi=1)
        no_glow = np.empty(r["comp"].shape, np.float32)
        for i in range(len(no_glow)):
            no_glow[i] = dither(r["comp"][i] - r["emission"][i], rng, lo=0, hi=1)
        Pd = dict(DEFAULTS, **P)
        tt = np.arange(len(r["particles"]), dtype=np.float32) / fps
        tail = np.clip(1.0 - (tt - (start_seconds + duration_seconds)) / max(float(Pd["guide_tail"]), 1e-3), 0.0, 1.0)
        guide = np.empty(r["particles"].shape, np.float32)
        for i in range(len(guide)):
            guide[i] = np.clip((r["particles"][i] + r["emission"][i]) * tail[i], 0, 1)
        return (T(comp), T(np.clip(r["particles"], 0, None)), T(r["particles_alpha"]), T(r["emission"]),
                T(r["person_matte"]), T(r["dissolve_mask"]), T(r["background"]), rep, T(no_glow), T(guide), style == "fire (LTX)")


def blur_object(frames, masks, blur=0.012, grow=0.012):
    n, H, W = frames.shape[:3]
    d = math.hypot(H, W)
    g = max(1, int(round(grow * d)))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g + 1, 2 * g + 1))
    out = np.empty_like(frames, dtype=np.float32)
    for i in range(n):
        m = masks[min(i, len(masks) - 1)]
        if m.shape != (H, W):
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
        md = cv2.dilate((m > 0.5).astype(np.uint8), ker).astype(np.float32)
        a = cv2.GaussianBlur(md, (0, 0), max(1.0, g / 4))[..., None]
        f = frames[i][..., :3].astype(np.float32)
        out[i] = f * (1 - a) + cv2.GaussianBlur(f, (0, 0), max(1.0, blur * d)) * a
    return out


class EFCleanPlateReference:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "plate": ("IMAGE",),
            "mask": ("MASK", {"tooltip": "Object mask per frame (what should vanish)."}),
            "blur": ("FLOAT", {"default": 0.012, "min": 0.0, "max": 0.1, "step": 0.001, "tooltip": "Blur of the object, share of the diagonal."}),
            "grow": ("FLOAT", {"default": 0.012, "min": 0.0, "max": 0.1, "step": 0.001, "tooltip": "Mask grown by this share of the diagonal (hair, motion blur)."}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("reference",)
    FUNCTION = "make"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Prepares the plate for the LTX Clean Plate IC-LoRA: the object is blurred heavily, so LTX removes it as a "
                   "moving subject but has no face or shape left to keep (a figure filling the frame kept its head otherwise).")

    def make(self, plate, mask, blur, grow):
        mk = _np(mask)
        mk = mk.reshape(-1, *mk.shape[-2:])
        return (torch.from_numpy(np.ascontiguousarray(blur_object(_np(plate)[..., :3], mk, blur, grow), np.float32)),)


def crop_box(masks, H, W, pad=0.08):
    m = np.asarray(masks, np.float32).reshape(-1, *np.asarray(masks).shape[-2:]).max(0) > 0.5
    if m.shape != (H, W):
        m = cv2.resize(m.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
    ys, xs = np.nonzero(m)
    if not len(xs):
        return None
    g = int(round(pad * math.hypot(H, W)))
    return max(0, xs.min() - g), max(0, ys.min() - g), min(W, xs.max() + 1 + g), min(H, ys.max() + 1 + g)


def ltx_size(cw, ch, min_px=262144, max_px=589824, mult=64):
    px = float(np.clip(cw * ch, min_px, max_px))
    k = math.sqrt(px / max(cw * ch, 1))
    return max(mult, int(round(cw * k / mult)) * mult), max(mult, int(round(ch * k / mult)) * mult)


class EFCleanPlateCrop:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "images": ("IMAGE", {"tooltip": "The clean plate reference (EF Clean Plate Reference) or the plate."}),
            "mask": ("MASK", {"tooltip": "Object mask per frame: the crop is the box around it in every frame."}),
            "padding": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01, "tooltip": "Box grown by this share of the diagonal (ring of plate for the colour match)."}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("crop", "width", "height", "crop_info")
    FUNCTION = "crop"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Clean plate sharper in the hole: cuts the box around the object out of the clip and scales it "
                   "to a generate size of about its own pixels (at most the LoRA's 1024 x 576, multiples of 64), so LTX spends "
                   "its resolution on the hole only. EF Clean Plate Uncrop puts the result back.")

    def crop(self, images, mask, padding):
        im = _np(images)[..., :3]
        n, H, W = im.shape[:3]
        box = crop_box(_np(mask), H, W, padding) or (0, 0, W, H)
        x0, y0, x1, y1 = (int(v) for v in box)
        w, h = ltx_size(x1 - x0, y1 - y0)
        out = np.stack([cv2.resize(f[y0:y1, x0:x1], (w, h), interpolation=cv2.INTER_AREA if w < x1 - x0 else cv2.INTER_LANCZOS4)
                        for f in im])
        info = json.dumps({"box": [x0, y0, x1, y1], "plate": [W, H], "generate": [w, h]})
        return (torch.from_numpy(np.ascontiguousarray(np.clip(out, 0, 1), np.float32)), w, h, info)


def soft_uncrop(pl, cl, box, masks=None, soften=0.012, match=1.0):
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    d = math.hypot(bw, bh)
    g = max(1, int(round(soften * math.hypot(*pl.shape[1:3]))))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g + 1, 2 * g + 1))
    sig = max(4.0, 0.05 * d)
    yy, xx = np.mgrid[0:bh, 0:bw]
    border = np.minimum.reduce([xx, yy, bw - 1 - xx, bh - 1 - yy]).astype(np.float32)
    rim = np.clip(border / max(2.0 * g, 1.0), 0, 1)
    for i in range(len(pl)):
        c = cv2.resize(cl[min(i, len(cl) - 1)], (bw, bh), interpolation=cv2.INTER_LANCZOS4)
        if masks is None:
            pl[i, y0:y1, x0:x1] = c
            continue
        m = np.asarray(masks[min(i, len(masks) - 1)], np.float32)
        if m.shape != pl.shape[1:3]:
            m = cv2.resize(m, (pl.shape[2], pl.shape[1]), interpolation=cv2.INTER_LINEAR)
        hole = (m[y0:y1, x0:x1] > 0.5).astype(np.uint8)
        if not hole.any():
            continue
        reg = pl[i, y0:y1, x0:x1]
        grown = cv2.dilate(hole, ker)
        if match > 0:
            w = (1 - grown).astype(np.float32)
            wb = cv2.GaussianBlur(w, (0, 0), sig)
            diff = cv2.GaussianBlur((reg - c) * w[..., None], (0, 0), sig) / np.maximum(wb, 1e-3)[..., None]
            far = np.clip(wb / 0.02, 0, 1)[..., None]
            c = c + match * diff * far
        a = cv2.GaussianBlur(grown.astype(np.float32), (0, 0), max(g / 2.0, 0.5))
        a = np.maximum(a, hole) * rim
        pl[i, y0:y1, x0:x1] = reg * (1 - a[..., None]) + c * a[..., None]
    return pl


class EFCleanPlateUncrop:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "plate": ("IMAGE", {"tooltip": "The clip (outside the box it stays as it is)."}),
            "clean": ("IMAGE", {"tooltip": "The clean plate of the crop (LTX output)."}),
            "crop_info": ("STRING", {"forceInput": True}),
        }, "optional": {
            "mask": ("MASK", {"tooltip": "The object's mask: only the hole is replaced, with a soft edge and the colours "
                                         "matched to the plate around it. Without it the whole box is pasted."}),
            "soften": ("FLOAT", {"default": 0.012, "min": 0.0, "max": 0.1, "step": 0.001,
                                 "tooltip": "Width of the soft edge around the hole, share of the diagonal (with the mask)."}),
            "match_color": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                                      "tooltip": "How far the clean plate's colours are pulled to the plate's around the hole (with the mask)."}),
        }}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("clean_plate",)
    FUNCTION = "uncrop"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Puts the clean plate of EF Clean Plate Crop back into the clip's frame (the plate around it). With the "
                   "object's mask only the hole is replaced, softly and with the colours matched to the plate.")

    def uncrop(self, plate, clean, crop_info, mask=None, soften=0.012, match_color=1.0):
        pl = _np(plate)[..., :3].copy()
        cl = _np(clean)[..., :3]
        mk = None
        if mask is not None:
            mk = _np(mask)
            mk = mk.reshape(-1, *mk.shape[-2:])
        soft_uncrop(pl, cl, tuple(int(v) for v in json.loads(crop_info)["box"]), mk, soften, match_color)
        return (torch.from_numpy(np.ascontiguousarray(np.clip(pl, 0, 1), np.float32)),)


def srgb_lin(x):
    x = np.asarray(x, np.float32)
    return np.where(x <= 0.04045, x / 12.92, ((np.maximum(x, 0) + 0.055) / 1.055) ** 2.4).astype(np.float32)


def comp_to_layer(comp, plate, mask=None, threshold=0.012, grow=0.004):
    c = np.asarray(comp, np.float32)[..., :3]
    pl = np.asarray(plate, np.float32)[..., :3]
    n, H, W = c.shape[:3]
    g = max(1, int(round(grow * math.hypot(H, W))))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * g + 1, 2 * g + 1))
    al = np.empty((n, H, W), np.float32)
    for i in range(n):
        q = pl[min(i, len(pl) - 1)]
        if q.shape[:2] != (H, W):
            q = cv2.resize(q, (W, H), interpolation=cv2.INTER_AREA)
        d = np.abs(c[i] - q).max(-1) > threshold
        m = d.astype(np.uint8)
        if mask is not None and len(mask):
            mk = np.asarray(mask[min(i, len(mask) - 1)], np.float32)
            if mk.shape != (H, W):
                mk = cv2.resize(mk, (W, H), interpolation=cv2.INTER_LINEAR)
            m |= (mk > 0.5).astype(np.uint8)
        al[i] = np.maximum(cv2.GaussianBlur(cv2.dilate(m, ker).astype(np.float32), (0, 0), max(g / 2.0, 0.5)), m)
    return srgb_lin(c) * al[..., None], al


class EFCompToLayer:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "comp": ("IMAGE", {"tooltip": "The finished comp (e.g. EF Dissolve), sRGB."}),
            "plate": ("IMAGE", {"tooltip": "The plate it was made from, sRGB."}),
            "threshold": ("FLOAT", {"default": 0.012, "min": 0.0, "max": 0.5, "step": 0.001, "tooltip": "Smallest change (sRGB) that counts; above the dither of the comp."}),
            "grow": ("FLOAT", {"default": 0.004, "min": 0.0, "max": 0.1, "step": 0.001, "tooltip": "Alpha grown by this share of the diagonal (no gaps at faint particles)."}),
        }, "optional": {
            "mask": ("MASK", {"tooltip": "Always part of the layer (e.g. the object): its pixels get alpha 1 even where the comp equals the plate."}),
        }}

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("element_linear", "alpha")
    FUNCTION = "run"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("A finished comp as an element pass over its plate (linear, premultiplied, with alpha): over the plate "
                   "it gives the comp back where it changed. Lets the app grade and layer a dissolve like any other effect.")

    def run(self, comp, plate, threshold, grow, mask=None):
        el, al = comp_to_layer(_np(comp), _np(plate), None if mask is None else _np(mask), threshold, grow)
        return (torch.from_numpy(np.ascontiguousarray(el)), torch.from_numpy(np.ascontiguousarray(al)))


class EFScreen:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "base": ("IMAGE",),
            "layer": ("IMAGE", {"tooltip": "Light on black (e.g. LTX embers); scaled to the base."}),
            "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.05}),
        }, "optional": {
            "band": ("IMAGE", {"tooltip": "Where the layer is fully used (e.g. the dissolve's glowing edge, output emission); grown and softened."}),
            "outside": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
                                  "tooltip": "Share of the layer away from the band (1 = everywhere). Lower it so LTX embers do not leave an orange haze over the whole ash."}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "screen"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Screens a light layer over the base (embers, glow): brightens without hard clipping. Dithered."

    def screen(self, base, layer, gain, band=None, outside=1.0):
        b = _np(base)[..., :3]
        lay = _np(layer)[..., :3]
        n, H, W = b.shape[:3]
        bd = None if band is None or outside >= 1.0 else _np(band)[..., :3].max(-1)
        r = max(2, int(0.03 * min(H, W)))
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        out = np.empty_like(b)
        rng = np.random.default_rng(11)
        for i in range(n):
            li = lay[min(i, len(lay) - 1)]
            if li.shape[:2] != (H, W):
                li = cv2.resize(li, (W, H), interpolation=cv2.INTER_CUBIC)
            if bd is not None:
                m = bd[min(i, len(bd) - 1)]
                m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR) if m.shape != (H, W) else m
                m = cv2.GaussianBlur(cv2.dilate((m > 0.02).astype(np.float32), ker), (0, 0), r / 2)
                li = li * (outside + (1 - outside) * m[..., None])
            out[i] = 1 - (1 - b[i]) * (1 - np.clip(li * gain, 0, 1))
        return (torch.from_numpy(dither(out, rng, lo=0, hi=1).astype(np.float32, copy=False)),)


BG_SMOOTH = 0.02
BG_CHOICES = ("auto", "smooth", "structured")


def background_structure(plate, masks, frames=5, long_side=640):
    n = len(masks)
    vals = []
    for i in np.linspace(0, n - 1, min(frames, n)).round().astype(int):
        m = np.asarray(masks[i], np.float32)
        H, W = m.shape
        s = long_side / max(H, W)
        w, h = max(8, int(round(W * s))), max(8, int(round(H * s)))
        p = cv2.resize(np.asarray(plate[min(i, len(plate) - 1)], np.float32)[..., :3], (w, h), interpolation=cv2.INTER_AREA)
        mk = cv2.resize((m > 0.5).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
        if mk.sum() < 16:
            continue
        d = math.hypot(h, w)
        ker = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
        ring = (cv2.dilate(mk, ker(max(3, int(0.08 * d)))) > 0) & (cv2.dilate(mk, ker(max(1, int(0.02 * d)))) == 0)
        if ring.sum() < 64:
            continue
        y = np.log(np.clip(p @ np.float32([0.2126, 0.7152, 0.0722]), 0, 1) + 0.03)
        band = np.abs(cv2.GaussianBlur(y, (0, 0), 1.0) - cv2.GaussianBlur(y, (0, 0), 4.0))
        vals.append(float(np.median(band[ring])))
    return float(np.median(vals)) if vals else 0.0


class EFDissolveBackground:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "plate": ("IMAGE",),
            "mask": ("MASK", {"tooltip": "The object that dissolves (per frame)."}),
            "background": ("STRING", {"default": "auto", "tooltip": "auto, smooth or structured: what is behind the object where it never moves away. smooth (a backdrop, a wall, sky): filled from the background around it, no AI run. structured (leaves, bricks, a room): LTX paints a clean plate. auto: measured from the background around the object."}),
            "clean_plate": ("BOOLEAN", {"default": True, "tooltip": "Off: never the LTX clean plate, whatever the background."}),
            "threshold": ("FLOAT", {"default": BG_SMOOTH, "min": 0.0, "max": 1.0, "step": 0.001, "tooltip": "auto: structure below this counts as smooth."}),
        }}

    RETURN_TYPES = ("BOOLEAN", "STRING")
    RETURN_NAMES = ("use_clean_plate", "report")
    FUNCTION = "decide"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Decides whether the dissolve needs the LTX clean plate for the spots that are never free: a smooth background "
                   "is filled from around the hole (cleaner there, and no AI run), a structured one gets the clean plate.")

    def decide(self, plate, mask, background="auto", clean_plate=True, threshold=BG_SMOOTH):
        background = (background or "auto").strip().lower()
        if background not in BG_CHOICES:
            raise ValueError(f"Dissolve background '{background}': use one of {', '.join(BG_CHOICES)}")
        if not clean_plate:
            return (False, "clean plate off")
        if background != "auto":
            return (background == "structured", f"background set to {background}")
        m = _np(mask)
        sc = background_structure(_np(plate), m if m.ndim == 3 else m[..., 0])
        use = sc >= threshold
        return (use, f"background structure {sc:.4f} ({'structured: clean plate' if use else 'smooth: filled without the AI'}, threshold {threshold})")

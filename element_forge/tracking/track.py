import cv2
import numpy as np
import torch

try:
    from ..simulation.particles import contrast_blend, streak_detail
except ImportError:
    import importlib.util as _ilu
    import os as _os
    _sp = _ilu.spec_from_file_location("_ef_particles", _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "simulation", "particles.py"))
    _pm = _ilu.module_from_spec(_sp)
    _sp.loader.exec_module(_pm)
    contrast_blend, streak_detail = _pm.contrast_blend, _pm.streak_detail


def to_np(images):
    return images.detach().cpu().float().numpy()


def to_t(arr):
    return torch.from_numpy(np.ascontiguousarray(arr, dtype=np.float32))


def srgb_to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((np.clip(x, 0, None) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def warp_down(src, m, size):
    m = np.asarray(m, np.float64)
    A, t = m[:, :2], m[:, 2]
    sx, sy = np.hypot(A[0, 0], A[1, 0]), np.hypot(A[0, 1], A[1, 1])
    if sx >= 1 and sy >= 1:
        return cv2.warpAffine(src, m, size, flags=cv2.INTER_LINEAR, borderValue=0)
    if min(sx, sy) < 1e-9:
        return np.zeros((size[1], size[0]) + src.shape[2:], src.dtype)
    sh, sw = src.shape[:2]
    nw, nh = max(1, int(round(sw * min(sx, 1.0)))), max(1, int(round(sh * min(sy, 1.0))))
    small = cv2.resize(src, (nw, nh), interpolation=cv2.INTER_AREA) if (nw, nh) != (sw, sh) else src
    if small.ndim < src.ndim:
        small = small[..., None]
    fx, fy = nw / sw, nh / sh
    D = np.diag([1 / fx, 1 / fy])
    o = np.array([0.5 / fx - 0.5, 0.5 / fy - 0.5])
    m2 = np.hstack([A @ D, (A @ o + t)[:, None]])
    out = cv2.warpAffine(small, m2, size, flags=cv2.INTER_LINEAR, borderValue=0)
    return out[..., None] if out.ndim < src.ndim else out


def fit_ab_window(ta, tb, aspect, room=1.0, pad=96.0):
    half = np.abs(np.asarray(ta, np.float64) - np.asarray(tb, np.float64)).max(0) / 2
    w, h = 2 * half
    extra = room * max(w, h) + pad
    w, h = w + extra, h + extra
    w = max(w, h * aspect)
    return float(w), float(w / aspect)


class EFTrackROI:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "Plate frames, e.g. from Load Video."}),
                "point_x": ("INT", {"default": 752, "min": 0, "max": 16384, "tooltip": "Point to follow in the first frame, in plate pixels (e.g. the palm)."}),
                "point_y": ("INT", {"default": 777, "min": 0, "max": 16384}),
                "track_radius": ("INT", {"default": 80, "min": 16, "max": 2048, "tooltip": "Features within this distance of the point (first frame) are tracked. Use an area that moves rigidly with the point."}),
                "frames": ("INT", {"default": 81, "min": 9, "max": 1025, "step": 8, "tooltip": "Number of frames to cut. LTX needs 8n+1."}),
                "crop_width": ("INT", {"default": 480, "min": 64, "max": 4096, "step": 8, "tooltip": "Crop size in plate pixels."}),
                "crop_height": ("INT", {"default": 640, "min": 64, "max": 4096, "step": 8, "tooltip": "If crop and roi differ in aspect, the crop height follows the roi's aspect (the width stays)."}),
                "roi_width": ("INT", {"default": 768, "min": 64, "max": 4096, "step": 32, "tooltip": "Size the crop is scaled to for generation (multiple of 32)."}),
                "roi_height": ("INT", {"default": 1024, "min": 64, "max": 4096, "step": 32}),
                "anchor_x": ("FLOAT", {"default": 0.5, "min": -4.0, "max": 5.0, "step": 0.001, "tooltip": "Where the point sits inside the crop (0..1; outside it the point lies beside the window)."}),
                "anchor_y": ("FLOAT", {"default": 0.6875, "min": -4.0, "max": 5.0, "step": 0.001}),
                "mask_offset_y": ("FLOAT", {"default": -0.146, "min": -1.0, "max": 1.0, "step": 0.005, "tooltip": "Mask ellipse centre relative to the point, in fractions of the crop height (negative = above)."}),
                "mask_width": ("FLOAT", {"default": 0.48, "min": 0.01, "max": 2.0, "step": 0.01, "tooltip": "Ellipse width as a fraction of the crop width."}),
                "mask_height": ("FLOAT", {"default": 0.578, "min": 0.01, "max": 2.0, "step": 0.01, "tooltip": "Ellipse height as a fraction of the crop height."}),
                "smoothing": ("BOOLEAN", {"default": True, "tooltip": "Light 3-tap smoothing of the track."}),
            },
            "optional": {
                "between": ("BOOLEAN", {"default": False, "tooltip": "Window between two points: the crop follows the middle between this point and track_b (anchor = the middle), so an effect from A to B (lightning, magic between two hands) stays inside. The point track itself stays A."}),
                "track_b": ("EF_TRACK", {"lazy": True, "tooltip": "Second point (Track ROI / Mask Track of point B); only read with between on."}),
                "fit_ab": ("BOOLEAN", {"default": False, "tooltip": "With between on: size the window from A and B over the whole clip (both points plus room around them, in the roi's aspect) instead of crop_width/height. The hands themselves need not fit, only the points."}),
                "still": ("BOOLEAN", {"default": False, "tooltip": "Fixed on screen: nothing is tracked, the point stays where it is in the picture in every frame (titles, lens flares)."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "EF_TRACK", "IMAGE")
    RETURN_NAMES = ("roi", "mask", "track", "plate_frames")
    FUNCTION = "track"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Follows a point through the plate (optical flow frame to frame, similarity fit), cuts a "
                   "stabilized crop around it, scales it up for generation and draws an ellipse mask where the "
                   "element should appear. The track output puts the result back into the plate.")

    @staticmethod
    def follow(gray, px, py, radius, reseeded=None):
        def seed(img, x, y, r):
            fm = np.zeros_like(img)
            fm[max(int(y - r), 0):max(int(y + r), 0), max(int(x - r), 0):max(int(x + r), 0)] = 255
            return cv2.goodFeaturesToTrack(img, 300, 0.005, 4, mask=fm)

        cur = seed(gray[0], px, py, radius)
        if cur is None or len(cur) < 8:
            raise ValueError("Too few trackable features around the point; raise track_radius or pick a textured area.")
        def step(a, b, pts):
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(21, 21), maxLevel=3)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, winSize=(21, 21), maxLevel=3)
            ok = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.linalg.norm((back - pts)[:, 0], axis=1) < 0.5)
            m, inl = (None, None) if ok.sum() < 6 else cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=1.0)
            return nxt, ok, m, inl

        acc = np.eye(3)
        track, scales, inliers = [np.array([px, py])], [1.0], []
        reseeded = [] if reseeded is None else reseeded
        wide = False
        for i in range(1, len(gray)):
            nxt, ok, m, inl = step(gray[i - 1], gray[i], cur)
            h_, w_ = gray[i - 1].shape
            for r2 in (radius * 3, max(h_, w_)):
                if m is not None:
                    break
                if r2 < max(h_, w_):
                    fresh = seed(gray[i - 1], track[-1][0], track[-1][1], r2)
                else:
                    fresh = seed(gray[i - 1], w_ / 2, h_ / 2, max(h_, w_))
                if fresh is None or len(fresh) < 8:
                    continue
                cur = fresh.astype(np.float32)
                nxt, ok, m, inl = step(gray[i - 1], gray[i], cur)
                if m is not None:
                    reseeded.append(i)
                    wide = True
            if m is None:
                raise ValueError(f"Track lost at frame {i}. Pick a more textured point or a larger track_radius.")
            acc = np.vstack([m, [0, 0, 1]]) @ acc
            pos = (acc @ np.array([px, py, 1.0]))[:2]
            track.append(pos)
            scales.append(float(np.sqrt(abs(np.linalg.det(acc[:2, :2])))))
            inliers.append(int(inl.sum()))
            cur = nxt[ok][inl[:, 0] == 1].reshape(-1, 1, 2)
            if wide:
                local = seed(gray[i], pos[0], pos[1], radius * scales[-1])
                if local is not None and len(local) >= 8:
                    cur, wide = local.astype(np.float32), False
                    continue
            if len(cur) < 40:
                extra = seed(gray[i], pos[0], pos[1], radius * scales[-1])
                if extra is not None:
                    cur = np.concatenate([cur, extra.astype(np.float32)])
        return np.array(track), scales, inliers

    def check_lazy_status(self, between=False, track_b=None, **kw):
        return ["track_b"] if between and track_b is None else []

    def track(self, plate, point_x, point_y, track_radius, frames, crop_width, crop_height, roi_width, roi_height,
              anchor_x, anchor_y, mask_offset_y, mask_width, mask_height, smoothing, between=False, track_b=None,
              fit_ab=False, still=False):
        imgs = to_np(plate[:frames])
        n = imgs.shape[0]
        if n < frames:
            raise ValueError(f"Plate has {n} frames, {frames} requested.")
        h, w = imgs.shape[1:3]
        gray = [cv2.cvtColor((im[..., :3] * 255).round().astype(np.uint8), cv2.COLOR_RGB2GRAY) for im in imgs]
        reseeded = []
        if still:
            track, scales, inliers = np.repeat([[float(point_x), float(point_y)]], n, 0), [1.0] * n, [0]
        else:
            track, scales, inliers = self.follow(gray, float(point_x), float(point_y), track_radius, reseeded)
        if smoothing and n > 2 and not still:
            sm = track.copy()
            sm[1:-1] = (track[:-2] + 2 * track[1:-1] + track[2:]) / 4
            track = sm

        centre = track
        if between and track_b is not None:
            tb = np.asarray(track_b["point_track_px"], np.float64)
            tb = np.concatenate([tb, np.repeat(tb[-1:], max(0, n - len(tb)), 0)])[:n]
            centre = (track + tb) / 2
            if fit_ab:
                crop_width, crop_height = fit_ab_window(track, tb, roi_width / roi_height)
        scale = roi_width / crop_width
        if abs(scale - roi_height / crop_height) > 1e-3:
            crop_height = crop_width * roi_height / roi_width
        anchor = np.array([anchor_x * crop_width, anchor_y * crop_height])
        full = crop_width >= w - 0.5 and crop_height >= h - 0.5
        origins, rois = [], []
        for i in range(n):
            ox, oy = ((w - crop_width) / 2, (h - crop_height) / 2) if full else centre[i] - anchor
            origins.append([float(ox), float(oy)])
            m = np.array([[scale, 0, -ox * scale], [0, scale, -oy * scale]], dtype=np.float64)
            rois.append(cv2.warpAffine(imgs[i][..., :3], m, (roi_width, roi_height), flags=cv2.INTER_LANCZOS4,
                                       borderMode=cv2.BORDER_REFLECT))
        roi = np.clip(np.stack(rois), 0, 1)

        mask = np.zeros((roi_height, roi_width), np.uint8)
        cx = anchor[0] * scale
        cy = (anchor[1] + mask_offset_y * crop_height) * scale
        cv2.ellipse(mask, (int(round(cx)), int(round(cy))),
                    (int(round(mask_width * roi_width / 2)), int(round(mask_height * roi_height / 2))), 0, 0, 360, 255, -1)
        masks = np.repeat((mask > 127).astype(np.float32)[None], n, axis=0)

        tr = {"plate_size": [w, h], "frames": n, "scale_roi_per_plate_px": float(scale), "roi_size": [roi_width, roi_height],
              "crop_origin_plate_px": origins, "point_track_px": track.round(3).tolist(), "point_scale": [round(v, 5) for v in scales], "min_inliers": int(min(inliers)), "reseeded_frames": reseeded,
              "mapping": "plate = crop_origin + roi / scale"}
        return (to_t(roi), to_t(masks), tr, plate[:frames])


class EFEffectLayer:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "with_element": ("IMAGE", {"tooltip": "Inpainted ROI with the element (flame, glow, ...)."}),
                "reference": ("IMAGE", {"tooltip": "Same ROI without the element. Best: a control run with the same seed and mask and a prompt without the element. The original ROI also works but keeps everything the model regenerated."}),
                "warm_key": ("BOOLEAN", {"default": True, "tooltip": "Keep only changes that brighten and shift toward warm (fire, embers, warm light). Off for cool or white elements."}),
                "gate_sigma": ("FLOAT", {"default": 110.0, "min": 0.0, "max": 2000.0, "step": 1.0, "tooltip": "Soft falloff around the brightest part of the element, in ROI pixels. Removes changes far from the element. 0 = off."}),
            },
            "optional": {
                "mask": ("MASK", {"tooltip": "Inpaint mask (per frame or one for all). Used for the error figures in the report and, with limit_to_mask, to keep the layer inside it."}),
                "key": (["from warm_key", "warm", "cold (lightning)", "auto (effect color)", "any change (over)", "off"], {"tooltip": "Which changes count as the element: warm (fire, embers), cold (lightning and its blue-white light: brightening that is neutral or blue; redrawn skin and cloth differ warm or dark and fall out), auto (effect color: the color of the strongest brightening over the whole clip, plus its white-hot core; works for any glowing effect), any change (over: everything the effect changed, brighter or darker, as an opaque layer for frost, paint, materials; use EF Place Layer blend 'over' with the alpha output) or off (every brightening change). 'from warm_key' keeps the old switch."}),
                "limit_to_mask": ("BOOLEAN", {"default": False, "tooltip": "Keep the layer only inside the mask (grown by 15 px, soft edge)."}),
                "mask_hull": ("BOOLEAN", {"default": False, "tooltip": "With limit_to_mask: use the convex hull of all mask parts of a frame instead of the mask itself, so an element between two objects (an arc between two hands) is kept too."}),
                "lines": ("MASK", {"tooltip": "Guide lines the element follows, in the same space (e.g. the arc lines of EF In-Plate Guides). With line_reach the layer is kept only near them."}),
                "line_reach": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1000.0, "step": 1.0, "tooltip": "Keep the layer within this distance of the lines (px; fades out over the same distance again). 0 = off. Removes face and cloth the two runs redraw differently."}),
                "line_window": ("INT", {"default": 2, "min": 0, "max": 12, "tooltip": "Lines of this many frames before and after count too (a generated bolt lingers a little)."}),
                "hdr_core": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 64.0, "step": 0.5, "tooltip": "Lifts the clipped core of the layer above 1 (x(1 + hdr_core s^3), s = soft step from 0.5 to 1). 0 = off."}),
                "warm_core": ("BOOLEAN", {"default": False, "tooltip": "Warm key: also keep the white-hot core of a flame (near white, not warm itself) and close small holes in the kept area. Without it the core of a flame in front of a dark background turns into black holes."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "IMAGE", "STRING")
    RETURN_NAMES = ("layer_linear", "alpha", "layer_rgba", "report")
    FUNCTION = "extract"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Pulls the element out as an additive layer: everything the element added on top of the reference, "
                   "in linear light (element plus the light it throws). layer_linear: premultiplied linear RGB for Add "
                   "comps and EXR. layer_rgba: straight sRGB with alpha for PNG and Screen/Add in After Effects.")

    def extract(self, with_element, reference, warm_key, gate_sigma, mask=None, key="from warm_key", limit_to_mask=False, lines=None,
                line_reach=0.0, line_window=2, hdr_core=0.0, mask_hull=False, warm_core=False):
        g_all, r_all = to_np(with_element), to_np(reference)
        n = min(len(g_all), len(r_all))
        lin_out, alphas, rgba_out = [], [], []
        pos, neg = [], []
        masks = to_np(mask) > 0.5 if mask is not None else None
        if masks is not None and masks.ndim == 2:
            masks = masks[None]
        ln = to_np(lines) > 0.5 if lines is not None else None
        if ln is not None and ln.ndim == 2:
            ln = ln[None]
        mode = key if key != "from warm_key" else ("warm" if warm_key else "off")
        cdir = None
        if mode == "auto (effect color)":
            acc = np.zeros(3, np.float64)
            for i in range(n):
                g0 = srgb_to_linear(g_all[i][..., :3])
                r0 = srgb_to_linear(r_all[i][..., :3])
                if r0.shape != g0.shape:
                    r0 = cv2.resize(r0, (g0.shape[1], g0.shape[0]), interpolation=cv2.INTER_AREA)
                d0 = g0 - r0
                lum0 = d0.mean(axis=-1)
                sel = lum0 >= max(float(np.percentile(lum0, 99.5)), 0.02)
                if sel.any():
                    acc += d0[sel].sum(axis=0)
            cdir = (acc / (np.linalg.norm(acc) + 1e-9)).astype(np.float32) if acc.any() else np.full(3, 0.577, np.float32)
        for i in range(n):
            g = srgb_to_linear(g_all[i][..., :3])
            r = srgb_to_linear(r_all[i][..., :3])
            if r.shape != g.shape:
                r = cv2.resize(r, (g.shape[1], g.shape[0]), interpolation=cv2.INTER_AREA)
            d = g - r
            layer = np.clip(d, 0, None)
            hw = (layer.shape[1], layer.shape[0])
            bright = np.clip(d.mean(axis=-1) / 0.01, 0, 1)
            if mode == "warm":
                warmth = np.clip((d[..., 0] - d[..., 2]) / 0.02, 0, 1)
                if warm_core:
                    gm = g.min(axis=-1)
                    hot = np.clip((gm - 0.55) / 0.3, 0, 1) * np.clip(d.mean(axis=-1) / 0.08, 0, 1)
                    keep = np.maximum(warmth, hot) * bright
                    keep = np.maximum(keep, cv2.morphologyEx(keep.astype(np.float32), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)))
                    layer = layer * keep[..., None]
                else:
                    layer = layer * (warmth * bright)[..., None]
            elif mode == "cold (lightning)":
                cold = np.clip((d[..., 2] - 0.9 * d[..., 0]) / 0.01, 0, 1)
                layer = layer * (cold * bright)[..., None]
            elif mode == "auto (effect color)":
                match = np.clip(((d @ cdir) / (np.linalg.norm(d, axis=-1) + 1e-6) - 0.85) / 0.1, 0, 1)
                hot = np.clip((g.min(axis=-1) - 0.55) / 0.3, 0, 1) * np.clip(d.mean(axis=-1) / 0.08, 0, 1)
                keep = np.maximum(match, hot) * bright
                keep = np.maximum(keep, cv2.morphologyEx(keep.astype(np.float32), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)))
                layer = layer * keep[..., None]
            over = None
            if mode == "any change (over)":
                over = cv2.GaussianBlur(np.clip((np.abs(d).max(axis=-1) - 0.01) / 0.05, 0, 1).astype(np.float32), (0, 0), 1.5)
                layer = g * over[..., None]
            m = None
            if masks is not None:
                m = masks[min(i, len(masks) - 1)]
                if m.shape[::-1] != hw:
                    m = cv2.resize(m.astype(np.uint8), hw, interpolation=cv2.INTER_NEAREST) > 0
                if limit_to_mask:
                    lm = m.astype(np.uint8)
                    if mask_hull and lm.any():
                        lm = cv2.fillConvexPoly(np.zeros_like(lm), cv2.convexHull(cv2.findNonZero(lm)), 1)
                    grown = cv2.GaussianBlur(cv2.dilate(lm, np.ones((31, 31), np.uint8)).astype(np.float32), (0, 0), 6)
                    layer = layer * grown[..., None]
                    over = over * grown if over is not None else None
            if ln is not None and line_reach > 0:
                win = np.zeros(layer.shape[:2], np.float32)
                for j in sorted({min(j, len(ln) - 1) for j in range(max(i - line_window, 0), i + line_window + 1)}):
                    lj = ln[j] if ln[j].shape[::-1] == hw else cv2.resize(ln[j].astype(np.uint8), hw, interpolation=cv2.INTER_NEAREST) > 0
                    if lj.any():
                        dist = cv2.distanceTransform((1 - lj.astype(np.uint8)), cv2.DIST_L2, 5)
                        win = np.maximum(win, np.clip(2 - dist / line_reach, 0, 1))
                layer = layer * win[..., None]
                over = over * win if over is not None else None
            if gate_sigma > 0:
                lum = layer.mean(axis=-1)
                core = lum > max(0.25 * lum.max(), 0.02)
                ys, xs = np.nonzero(core)
                if len(xs):
                    wts = lum[ys, xs]
                    cx, cy = (xs * wts).sum() / wts.sum(), (ys * wts).sum() / wts.sum()
                    yy, xx = np.mgrid[0:layer.shape[0], 0:layer.shape[1]]
                    gate = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * gate_sigma ** 2)).astype(np.float32)
                    layer = layer * gate[..., None]
                    over = over * gate if over is not None else None
            if hdr_core > 0 and over is None:
                sc = np.clip((layer.max(-1, keepdims=True) - 0.5) / 0.5, 0, 1)
                sc = sc * sc * (3 - 2 * sc)
                layer = layer * (1 + hdr_core * sc ** 3)
            a = np.clip(layer.max(axis=-1), 0, 1) if over is None else np.clip(over, 0, 1)
            straight = np.where(a[..., None] > 1e-6, np.clip(layer, 0, 1) / np.maximum(a[..., None], 1e-6), 0)
            lin_out.append(layer)
            alphas.append(a)
            rgba_out.append(np.concatenate([linear_to_srgb(straight), a[..., None]], axis=-1))
            if m is not None and m.shape == a.shape:
                pos.append(float(layer[m].mean()))
                neg.append(float(np.clip(-d, 0, None)[m].mean()))
        report = f"frames {n}"
        if pos:
            report += f", element energy in mask {np.mean(pos):.5f}, removed/darkened {np.mean(neg):.5f} (ratio {np.mean(neg) / (np.mean(pos) + 1e-9):.2f})"
        lin = np.stack(lin_out); del lin_out
        al = np.stack(alphas); del alphas
        rgba = np.stack(rgba_out); del rgba_out
        np.clip(rgba, 0, 1, out=rgba)
        return (to_t(lin), to_t(al), to_t(rgba), report)


class EFPlaceLayer:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE",),
                "layer_linear": ("IMAGE", {"tooltip": "Premultiplied linear layer in ROI space (EF Effect Layer)."}),
                "track": ("EF_TRACK",),
                "gain": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 16.0, "step": 0.05, "tooltip": "Brightness of the element in the comp. Above 1 gives HDR values in the linear output."}),
            },
            "optional": {
                "layer_is": (["linear premultiplied", "rgba (EF Unmult)"], {"tooltip": "linear premultiplied: EF Effect Layer. rgba: straight sRGB with alpha from EF Unmult, e.g. a guided element generated on black in the ROI."}),
                "edge_feather": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 0.5, "step": 0.01, "tooltip": "Fades the layer out towards the borders of the ROI (fraction of its shorter side), so an element that leaves the crop (a tall flame) shows no hard cut."}),
                "blend": (["add", "over", "contrast (rain)"], {"tooltip": "add: light added to the plate (glowing effects). over: opaque layer with alpha (EF Effect Layer key 'any change (over)'). contrast (rain): light on dark parts of the plate, a slightly darker, greyer streak on bright parts (rain and snow stay visible against a bright sky)."}),
                "blend_from": ("STRING", {"default": "", "tooltip": "Overrides blend when set, e.g. from EF Particles (the preset's blend: rain and snow use contrast)."}),
                "alpha": ("MASK", {"tooltip": "Alpha of the layer in ROI space, for blend 'over' (EF Effect Layer alpha)."}),
                "holdout": ("MASK", {"tooltip": "Plate-space mask multiplied into the placed layer: 0 cuts it. EF Particles: holdout (hidden behind the scene, per pixel from the particles' depth) or region (nothing outside the particles)."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("comp", "layer_plate_linear", "alpha_plate")
    FUNCTION = "place"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Puts the layer back into the full plate along the track and adds it in linear light. comp is sRGB for viewing and video."

    def place(self, plate, layer_linear, track, gain, layer_is="linear premultiplied", edge_feather=0.0, blend="add", alpha=None,
              holdout=None, blend_from=""):
        if blend_from and blend_from.strip():
            blend = blend_from.strip()
        if "scale_roi_per_plate_px" not in track or "crop_origin_plate_px" not in track:
            raise ValueError(f"EF Place Layer needs a track with a crop window (from EF Track ROI or EF Follow Crop); this one "
                             f"({track.get('source', 'point track')}) has only a point. Use EF Place Element for point tracks.")
        contrast = blend.startswith("contrast")
        if contrast:
            blend = "add"
        pl, ly = to_np(plate), to_np(layer_linear)
        ho = None if holdout is None else to_np(holdout).reshape(-1, *to_np(holdout).shape[-2:])
        al = None
        if blend == "over":
            if alpha is not None:
                al = to_np(alpha)
                al = al.reshape(-1, *al.shape[-2:])
            elif layer_is.startswith("rgba") and ly.shape[-1] == 4:
                al = ly[..., 3]
            else:
                raise ValueError("EF Place Layer: blend 'over' needs the alpha of the layer.")
        rgba = layer_is.startswith("rgba") and ly.shape[-1] == 4
        win = None
        ph, pw = pl.shape[1:3]
        cw_, ch_ = (np.asarray(track["roi_size"], np.float64) / track["scale_roi_per_plate_px"]) if "roi_size" in track else (0, 0)
        org = np.asarray(track["crop_origin_plate_px"], np.float64)
        if "scale_per_frame" not in track and len(org) and (org[:, 0] <= 0.5).all() and (org[:, 1] <= 0.5).all() \
                and (org[:, 0] + cw_ >= pw - 0.5).all() and (org[:, 1] + ch_ >= ph - 0.5).all():
            edge_feather = 0.0
        if edge_feather > 0:
            rh, rw = ly.shape[1:3]
            f = max(edge_feather * min(rh, rw), 1.0)
            ramp = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))
            win = ramp(np.minimum(np.arange(rh), rh - 1 - np.arange(rh)) / f)[:, None] * ramp(np.minimum(np.arange(rw), rw - 1 - np.arange(rw)) / f)[None, :]
            win = win[..., None].astype(np.float32)

        def layer_frame(j):
            fr = ly[j]
            fr = srgb_to_linear(fr[..., :3]) * fr[..., 3:] if rgba else fr[..., :3]
            if win is None:
                return fr
            if blend == "add":
                y = (np.max(fr, axis=-1, keepdims=True) * gain).clip(0, None)
                return fr * (win / (1.0 + y * (1.0 - win)))
            return fr * win

        def alpha_frame(j):
            a = al[min(j, len(al) - 1)]
            return a * win[..., 0] if win is not None else a
        n = min(len(pl), len(ly), track["frames"])
        s = track["scale_roi_per_plate_px"]
        k = ly.shape[2] / float(track["roi_size"][0]) if "roi_size" in track else 1.0
        h, w = pl.shape[1:3]
        comps = np.empty((n, h, w, 3), np.float32)
        layers = np.empty((n, h, w, 3), np.float32)
        alphas = np.empty((n, h, w), np.float32)
        for i in range(n):
            ox, oy = track["crop_origin_plate_px"][i]
            si = (track["scale_per_frame"][i] if "scale_per_frame" in track else s) * k
            m = np.array([[1 / si, 0, ox], [0, 1 / si, oy]], dtype=np.float64)
            lp = warp_down(np.ascontiguousarray(layer_frame(i)), m, (w, h)) * gain
            hi = None
            if ho is not None:
                hi = ho[min(i, len(ho) - 1)]
                hi = cv2.resize(hi, (w, h), interpolation=cv2.INTER_LINEAR) if hi.shape != (h, w) else hi
                lp = lp * hi[..., None]
            if al is not None:
                ap = np.clip(warp_down(np.ascontiguousarray(alpha_frame(i)), m, (w, h)), 0, 1)
                ap = ap * hi if hi is not None else ap
                comps[i] = np.clip(linear_to_srgb(srgb_to_linear(pl[i][..., :3]) * (1 - ap[..., None]) + lp), 0, 1)
                layers[i] = lp
                alphas[i] = ap
                continue
            if contrast:
                ps = pl[i][..., :3]
                comps[i] = np.clip(contrast_blend(ps, lp, streak_detail(lp, h, w)), 0, 1)
                layers[i] = lp
                alphas[i] = np.clip(lp.max(axis=-1), 0, 1)
                continue
            comps[i] = np.clip(linear_to_srgb(srgb_to_linear(pl[i][..., :3]) + lp), 0, 1)
            layers[i] = lp
            alphas[i] = np.clip(lp.max(axis=-1), 0, 1)
        return (to_t(comps), to_t(layers), to_t(alphas))

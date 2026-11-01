import json
from collections import deque

import cv2
import numpy as np
import torch

from .guide import object_shape

WORK = 720
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def to_np(t):
    return t.detach().cpu().float().numpy()


def thin(mask):
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p = [np.roll(np.roll(img, -dy, 0), -dx, 1) for dy, dx in
                 [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]]
            b = sum(p)
            a = sum(((p[k] == 0) & (p[(k + 1) % 8] == 1)) for k in range(8))
            if step == 0:
                c = (p[0] * p[2] * p[4] == 0) & (p[2] * p[4] * p[6] == 0)
            else:
                c = (p[0] * p[2] * p[6] == 0) & (p[0] * p[4] * p[6] == 0)
            kill = (img == 1) & (b >= 2) & (b <= 6) & (a == 1) & c
            if kill.any():
                img[kill] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1]


def path_lengths(lines, start):
    dist = np.full(lines.shape, -1.0, np.float32)
    n, lab = cv2.connectedComponents(lines.astype(np.uint8), connectivity=8)
    longest = 0.0
    for c in range(1, n):
        ys, xs = np.nonzero(lab == c)
        k = int(np.argmin((xs - start[0]) ** 2 + (ys - start[1]) ** 2))
        q = deque([(ys[k], xs[k])])
        dist[ys[k], xs[k]] = 0.0
        while q:
            y, x = q.popleft()
            d = dist[y, x]
            for dy, dx in N8:
                yy, xx = y + dy, x + dx
                if 0 <= yy < lines.shape[0] and 0 <= xx < lines.shape[1] and lab[yy, xx] == c and dist[yy, xx] < 0:
                    dist[yy, xx] = d + (1.4142 if dy and dx else 1.0)
                    q.append((yy, xx))
        longest = max(longest, float(dist[lab == c].max()))
    return dist, longest


class EFGuide:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "The clip: sets the number of frames and the size of the guide."}),
                "source": (["draw", "from object", "object shape"], {"tooltip": "draw: strokes painted on the first frame (drawing). from object: lines from an object mask (object_mask). object shape: the object's depth only, black elsewhere, with an attention mask around it (object_mask and depth), so the element takes the object's shape and stays free above it (the guided flame of 17.10.)."}),
                "animation": (["still", "grows", "flickers"], {"tooltip": "still: the lines as they are. grows: each line appears from its start along its length. flickers: the lines wobble and pulse every frame."}),
                "line_width": ("INT", {"default": 3, "min": 1, "max": 40, "tooltip": "Width of the guide lines in clip pixels."}),
            },
            "optional": {
                "drawing": ("MASK", {"tooltip": "Strokes on the first frame (painted = 1), e.g. Load Image with the first frame, painted in the mask editor. Any size; it is fitted to the clip."}),
                "object_mask": ("MASK", {"tooltip": "Object mask per frame (e.g. SAM3 video track): the lines follow the object by themselves."}),
                "lines_from": (["auto", "centre lines", "outline"], {"tooltip": "from object: thin objects (branches, sticks) give their centre lines, large ones their outline. auto decides by the thickness of the object."}),
                "track": ("EF_TRACK", {"tooltip": "Drawn lines move with this track: the object's (EF Track ROI, EF Follow Crop) or the scene's (EF Camera Track). Without it they stay where they were drawn. Its first point is also where growing lines start."}),
                "crop": ("EF_TRACK", {"tooltip": "Crop of EF Track ROI / EF Follow Crop: guide_roi is the guide cut into that crop (for generating in the crop)."}),
                "grow_seconds": ("FLOAT", {"default": 1.0, "min": 0.04, "max": 30.0, "step": 0.01, "tooltip": "grows: time until the longest line is complete."}),
                "trail": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "grows: 0 = the line stays; above 0 only the newest part of this length (share of the line) is drawn, a streak moving along the line."}),
                "repeat": ("BOOLEAN", {"default": False, "tooltip": "grows: start again after grow_seconds, every line with its own delay (a steady stream, e.g. sparks)."}),
                "jitter": ("FLOAT", {"default": 6.0, "min": 0.0, "max": 200.0, "step": 0.5, "tooltip": "flickers: how far the lines wobble, in clip pixels."}),
                "fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2 ** 31 - 1}),
                "depth": ("IMAGE", {"tooltip": "object shape: depth of the clip (near = bright), e.g. Video Depth Anything."}),
                "shape_grow": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 0.5, "step": 0.005, "tooltip": "object shape: the attention region is the object grown by this share of the crop width."}),
                "shape_softness": ("FLOAT", {"default": 0.02, "min": 0.0, "max": 0.2, "step": 0.005, "tooltip": "object shape: soft edge of the attention region (share of the crop width)."}),
                "shape_floor": ("FLOAT", {"default": 0.35, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "object shape: darkest value of the object, so its far side still reads as object, not as empty space."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "MASK")
    RETURN_NAMES = ("guide", "guide_roi", "report", "attention_roi")
    FUNCTION = "make"
    CATEGORY = "Element Forge/Guides"
    DESCRIPTION = ("General guide lines for the LTX Union Control IC-LoRA, for any effect: drawn strokes or the lines of an "
                   "object, moving with a track, still, growing or flickering. White lines on black, clip size; guide_roi "
                   "is the same cut into a crop. object shape: the object's depth instead of lines, with attention_roi for "
                   "LTX Add Video IC-LoRA Guide Advanced (white = the guide speaks; all white for the other sources).")

    def make(self, plate, source, animation, line_width, drawing=None, object_mask=None, lines_from="auto", track=None,
             crop=None, grow_seconds=1.0, trail=0.0, repeat=False, jitter=6.0, fps=25.0, seed=0, depth=None, shape_grow=0.04,
             shape_softness=0.02, shape_floor=0.35):
        n, h, w = plate.shape[0], plate.shape[1], plate.shape[2]
        if crop is not None:
            n = min(n, int(crop.get("frames", n)))
        if source == "object shape":
            return self.shape(n, h, w, object_mask, depth, crop, shape_grow, shape_softness, shape_floor)
        s = min(1.0, WORK / max(h, w))
        sw, sh = max(1, round(w * s)), max(1, round(h * s))
        rng = np.random.default_rng(seed)
        info = {"frames": n, "source": source, "animation": animation}

        def small(m):
            m = m if m.shape == (sh, sw) else cv2.resize(m.astype(np.float32), (sw, sh), interpolation=cv2.INTER_AREA)
            return (m > 0.5).astype(np.uint8)

        if source == "draw":
            if drawing is None:
                raise ValueError("EF Guide: source 'draw' needs a drawing (strokes painted on the first frame).")
            d = to_np(drawing)
            d = d.reshape(-1, *d.shape[-2:])[0]
            strokes = small(d)
            if not strokes.any():
                raise ValueError("EF Guide: the drawing is empty.")
            frames_lines = [thin(strokes)]
            info["lines_from"] = "drawing"
        else:
            if object_mask is None:
                raise ValueError("EF Guide: source 'from object' needs an object_mask.")
            om = to_np(object_mask)
            om = om.reshape(-1, *om.shape[-2:])
            masks = [small(om[min(i, len(om) - 1)]) for i in range(n)]
            ref = max(masks, key=lambda m: int(m.sum()))
            if not ref.any():
                raise ValueError("EF Guide: the object mask is empty in every frame. Nothing was found at the click: click on a clearer object or surface, or name it with an object word.")
            mode = lines_from
            if mode == "auto":
                dt = cv2.distanceTransform(ref, cv2.DIST_L2, 5)
                sk = thin(ref) > 0
                thick = 2.0 * float(np.median(dt[sk])) if sk.any() else 0.0
                mode = "centre lines" if thick < 0.03 * min(sw, sh) else "outline"
                info["object_thickness_px"] = round(thick / s, 1)
            info["lines_from"] = mode
            frames_lines = []
            for m in masks:
                if mode == "centre lines":
                    frames_lines.append(thin(m))
                else:
                    o = np.zeros_like(m)
                    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                    cv2.drawContours(o, cs, -1, 1, 1)
                    frames_lines.append(o)

        pts = np.array(track["point_track_px"], np.float32) if track is not None else None
        scl = np.array(track.get("point_scale") or [1.0] * len(pts), np.float32) if track is not None else None

        def start_of(i, lines):
            if pts is not None:
                k = 0 if source == "draw" else min(i, len(pts) - 1)
                return pts[k] * s
            ys, xs = np.nonzero(lines)
            k = int(np.argmax(ys)) if len(ys) else 0
            return np.array([xs[k], ys[k]], np.float32) if len(ys) else np.array([sw / 2, sh], np.float32)

        cache = {}

        def lengths(i):
            key = 0 if source == "draw" else i
            if key not in cache:
                cache[key] = path_lengths(frames_lines[key], start_of(key, frames_lines[key]))
            return cache[key]

        period = max(1.0, grow_seconds * fps)
        phases = {}
        up_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (line_width, line_width)) if line_width > 1 else None
        out, lit = [], []
        for i in range(n):
            lines = frames_lines[0 if source == "draw" else i]
            img = lines.astype(np.float32)
            if animation == "grows":
                dist, longest = lengths(i)
                if longest > 0:
                    v = longest / period
                    if repeat:
                        lab = cv2.connectedComponents(lines.astype(np.uint8), connectivity=8)[1]
                        ph = np.zeros(lines.shape, np.float32)
                        for c in np.unique(lab[lab > 0]):
                            phases.setdefault((0 if source == "draw" else i, int(c)), float(rng.uniform(0, period)))
                            ph[lab == c] = phases[(0 if source == "draw" else i, int(c))]
                        head = ((i + ph) % period) * v
                    else:
                        head = np.full(lines.shape, i * v, np.float32)
                    on = (dist >= 0) & (dist <= head)
                    if trail > 0:
                        on &= dist >= head - trail * longest
                    img = on.astype(np.float32)
            g = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
            g = (g > 0.2).astype(np.float32)
            if up_kernel is not None:
                g = cv2.dilate(g, up_kernel)
            if source == "draw" and pts is not None and i > 0:
                k = min(i, len(pts) - 1)
                f = float(scl[k] / scl[0]) if scl is not None and scl[0] else 1.0
                m = np.float32([[f, 0, pts[k, 0] - f * pts[0, 0]], [0, f, pts[k, 1] - f * pts[0, 1]]])
                g = cv2.warpAffine(g, m, (w, h), flags=cv2.INTER_LINEAR)
            if animation == "flickers" and jitter > 0:
                gs = (max(2, w // 48), max(2, h // 48))
                fx = cv2.resize(rng.normal(0, jitter, (gs[1], gs[0])).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
                fy = cv2.resize(rng.normal(0, jitter, (gs[1], gs[0])).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
                gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
                g = cv2.remap(g, gx + fx, gy + fy, cv2.INTER_LINEAR)
                pulse = cv2.resize(rng.uniform(0.25, 1.0, (max(2, h // 160), max(2, w // 160))).astype(np.float32), (w, h),
                                   interpolation=cv2.INTER_CUBIC)
                g = g * np.clip(pulse, 0, 1)
            g = cv2.GaussianBlur(np.clip(g, 0, 1), (0, 0), 0.6)
            out.append(g)
            lit.append(int((g > 0.3).sum()))
        guide = np.stack(out)
        roi = to_crop(guide, crop, n) if crop is not None else guide
        info.update({"lit_px_min": min(lit), "lit_px_max": max(lit), "empty_frames": sum(1 for v in lit if v == 0)})
        rgb = lambda a: torch.from_numpy(np.ascontiguousarray(np.repeat(a[..., None], 3, -1), dtype=np.float32))
        return (rgb(guide), rgb(roi), json.dumps(info), torch.ones(roi.shape[:3], dtype=torch.float32))

    def shape(self, n, h, w, object_mask, depth, crop, grow, softness, floor):
        if object_mask is None or depth is None:
            raise ValueError("EF Guide: source 'object shape' needs the object_mask and the depth.")
        om = to_np(object_mask)
        om = om.reshape(-1, *om.shape[-2:])
        dp = to_np(depth)[..., :3].mean(-1)
        fit = lambda a: a if a.shape == (h, w) else cv2.resize(a, (w, h), interpolation=cv2.INTER_LINEAR)
        masks = np.stack([fit(om[min(i, len(om) - 1)]) for i in range(n)])
        depths = np.stack([fit(dp[min(i, len(dp) - 1)]) for i in range(n if len(dp) > 1 else 1)])
        if not (masks > 0.5).any():
            raise ValueError("EF Guide: the object mask is empty in every frame. Nothing was found at the click: click on a clearer object or surface, or name it with an object word.")
        full, _ = object_shape(depths, masks, grow, softness, floor)
        if crop is not None:
            ctrl, att = object_shape(to_crop(depths, crop, n), to_crop(masks, crop, n), grow, softness, floor)
        else:
            ctrl, att = object_shape(depths, masks, grow, softness, floor)
        lit = [int((c[..., 0] > 0.05).sum()) for c in ctrl]
        info = {"frames": n, "source": "object shape", "grow": grow, "softness": softness, "floor": floor,
                "object_px_min": min(lit), "object_px_max": max(lit), "empty_frames": sum(1 for v in lit if v == 0)}
        t = lambda a: torch.from_numpy(np.ascontiguousarray(np.stack(a), dtype=np.float32))
        return (t(full), t(ctrl), json.dumps(info), t(att))


def to_crop(frames, crop, n):
    rw, rh = crop["roi_size"]
    scales = crop.get("scale_per_frame") or [crop["scale_roi_per_plate_px"]] * n
    rois = []
    for i in range(n):
        sc = float(scales[min(i, len(scales) - 1)])
        ox, oy = crop["crop_origin_plate_px"][min(i, len(crop["crop_origin_plate_px"]) - 1)]
        rois.append(cv2.warpAffine(frames[min(i, len(frames) - 1)], np.float64([[sc, 0, -ox * sc], [0, sc, -oy * sc]]),
                                   (int(rw), int(rh)), flags=cv2.INTER_LINEAR))
    return np.stack(rois)


GUIDES = ["particles", "drawn path", "object shape", "none"]


PLACEMENTS = ("auto", "point", "area", "object", "frame", "between")


class EFPlacement:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "placement": ("STRING", {"default": "auto", "tooltip": "auto / point / area / object / frame / between"}),
            "guided": ("BOOLEAN", {"default": False, "tooltip": "A guide image or the motion path runs (Guide or motion?)."}),
            "has_b": ("BOOLEAN", {"default": False, "tooltip": "Point B is set."}),
        }}

    RETURN_TYPES = ("BOOLEAN", "BOOLEAN")
    RETURN_NAMES = ("in_window", "between")
    FUNCTION = "choose"
    CATEGORY = "Element Forge/Guides"
    DESCRIPTION = ("Where the element goes: in_window = made in a window (an area, on the object, the whole frame, or at a point "
                   "with a guide); between = stretched from point A to point B (only without a guide: a guided element stays in its window "
                   "around A and B). auto keeps the rule from the guide and point B.")

    def choose(self, placement, guided, has_b):
        p = str(placement or "auto").strip().lower() or "auto"
        if p not in PLACEMENTS:
            raise ValueError(f"EF Placement: unknown placement '{placement}' (known: {', '.join(PLACEMENTS)}).")
        if p == "auto":
            return (bool(guided), bool(has_b) and not guided)
        return (bool(guided) or p in ("area", "object", "frame"), p == "between" and bool(has_b) and not guided)


class EFGuideChoice:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "guide": (GUIDES, {"tooltip": "particles: the particles' picture guides the AI (only while Particles run; "
                                              "without them nothing guides). drawn path: the strokes of the Guide drawing (or the "
                                              "lines of the object, EF Guide source). object shape: the object's depth near it, "
                                              "so the element takes its shape (the guided flame of 17.10.). none: the AI paints "
                                              "freely from the prompt."}),
                "particles": ("BOOLEAN", {"default": False, "tooltip": "The Particles setting: the particles run."}),
                "follows_motion": ("BOOLEAN", {"default": False, "tooltip": "The Follows motion setting: the Motion-Track LoRA "
                                                                             "gets the path of the emitter. Not with the particle "
                                                                             "guide: the particles carry the motion themselves."}),
            }
        }

    RETURN_TYPES = ("BOOLEAN",) * 7
    RETURN_NAMES = ("drawn_path", "object_shape", "particles_guide", "guided", "motion_lora", "motion_alone", "chained")
    FUNCTION = "choose"
    CATEGORY = "Element Forge/Guides"
    DESCRIPTION = ("One switch for the guide of the AI: particles / drawn path / object shape / none. guided: Union Control "
                   "runs with a guide image. motion_lora: the Motion-Track LoRA runs (Follows motion, not with the particle "
                   "guide); motion_alone without a guide image, chained behind Union Control with one, never swapped.")

    def choose(self, guide, particles, follows_motion):
        if guide not in GUIDES:
            raise ValueError(f"EF Guide Choice: unknown guide '{guide}' (known: {', '.join(GUIDES)}).")
        drawn, shape = guide == "drawn path", guide == "object shape"
        parts = guide == "particles" and bool(particles)
        guided = drawn or shape or parts
        motion = bool(follows_motion) and not parts
        return (drawn, shape, parts, guided, motion, motion and not guided, motion and guided)

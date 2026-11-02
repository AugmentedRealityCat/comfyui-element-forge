import os
import threading
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from ..tracking.track import linear_to_srgb, srgb_to_linear, to_np, to_t

LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def _box(x, r):
    return cv2.blur(x, (2 * r + 1, 2 * r + 1), borderType=cv2.BORDER_REFLECT)


def guided(I, p, r, eps):
    mI, mp = _box(I, r), _box(p, r)
    a = (_box(I * p, r) - mI * mp) / (_box(I * I, r) - mI * mI + eps)
    b = mp - a * mI
    return _box(a, r) * I + _box(b, r)


class EFDeflicker:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "The pass to clean: depth (before Depth Light, so the normals and the light get calm too), the light pass (light_linear) or any other pass aligned with the plate."}),
                "plate": ("IMAGE", {"tooltip": "The plate (sRGB) the pass belongs to. The motion is measured on it and it guides the edge-aware filter; it is not changed."}),
                "radius": ("INT", {"default": 3, "min": 0, "max": 12, "tooltip": "Neighbour frames on each side that are aligned and averaged. 0 = no temporal averaging."}),
                "strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Mix between the original pass (0) and the cleaned one (1)."}),
            },
            "optional": {
                "level_radius": ("INT", {"default": 0, "min": 0, "max": 48, "tooltip": "Also evens out the overall brightness of the pass over this many frames on each side (for light that pumps with a flickering flame). 0 = off; leave it off for depth."}),
                "edge_radius": ("INT", {"default": 0, "min": 0, "max": 64, "tooltip": "Edge-aware filter with the plate as guide, window in pixels: removes structure the plate does not show (e.g. the patch grid of Depth Anything 3, about 14 px) and keeps every edge that is in the image. 0 = off; about 6 for depth at clip resolution (larger removes more, but thin parts such as fingers can take on the depth behind them)."}),
                "edge_smoothness": ("FLOAT", {"default": 0.001, "min": 0.00001, "max": 0.1, "step": 0.0001, "tooltip": "How strongly the pass may follow the plate's edges (small = sharper edges, but more plate texture can show up in the pass)."}),
                "comp": ("IMAGE", {"tooltip": "Optional sRGB comp that contains this pass added in linear light (e.g. the comp of EF Depth Light for its light pass): the pass in it is swapped for the cleaned one. Only for additive linear passes."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("images", "comp")
    FUNCTION = "deflicker"
    CATEGORY = "Element Forge/Post"
    DESCRIPTION = ("Removes flicker from passes estimated frame by frame (depth, light): every frame is averaged with its "
                   "neighbours after aligning them with optical flow measured on the plate, so motion stays. Optional "
                   "overall level smoothing and an edge-aware filter guided by the plate (removes the Depth Anything "
                   "patch grid without losing the image's edges). The plate is never changed.")

    @staticmethod
    def flow_scale(h, w, side=640):
        return min(1.0, side / max(h, w))

    @staticmethod
    def workers():
        return max(1, min(8, (os.cpu_count() or 2) - 2))

    def temporal(self, x, gray, radius, workers=None):
        n, H, W, C = x.shape
        h, w = gray.shape[1:]
        sx, sy = W / w, H / h
        g8 = [np.clip(g * 255, 0, 255).astype(np.uint8) for g in gray]
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        GX, GY = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
        sigma_t = max(0.6 * radius, 0.5)
        out = np.empty_like(x)
        local = threading.local()

        def frame(t):
            dis = getattr(local, "dis", None)
            if dis is None:
                dis = local.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
            acc = x[t].astype(np.float32).copy()
            wsum = np.ones((H, W, 1), np.float32)
            for k in range(-radius, radius + 1):
                j = t + k
                if k == 0 or j < 0 or j >= n:
                    continue
                fl = dis.calc(g8[t], g8[j], None)
                warped_g = cv2.remap(gray[j], gx + fl[..., 0], gy + fl[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                diff = cv2.GaussianBlur(np.abs(warped_g - gray[t]), (0, 0), 1.5)
                wp = np.exp(-(diff / 0.04) ** 2) * np.exp(-k * k / (2 * sigma_t ** 2))
                fu = cv2.resize(fl, (W, H), interpolation=cv2.INTER_LINEAR)
                mx, my = GX + fu[..., 0] * sx, GY + fu[..., 1] * sy
                inside = ((mx >= 0) & (mx <= W - 1) & (my >= 0) & (my <= H - 1)).astype(np.float32)
                wf = cv2.resize(wp.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR) * inside
                wj = cv2.remap(x[j], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
                if wj.ndim == 2:
                    wj = wj[..., None]
                acc += wj * wf[..., None]
                wsum += wf[..., None]
            out[t] = acc / wsum

        workers = workers or self.workers()
        if workers == 1:
            for t in range(n):
                frame(t)
        else:
            with ThreadPoolExecutor(workers) as ex:
                list(ex.map(frame, range(n)))
        return out

    @staticmethod
    def level(x, radius):
        m = np.array([float(f.mean()) for f in x]) + 1e-8
        sm = np.empty_like(m)
        for t in range(len(m)):
            j = np.arange(max(0, t - radius), min(len(m), t + radius + 1))
            wk = np.exp(-(j - t) ** 2 / (2 * (radius / 2) ** 2))
            sm[t] = (wk * m[j]).sum() / wk.sum()
        gain = np.clip(sm / m, 0.5, 2.0).astype(np.float32)
        for t in range(len(x)):
            x[t] *= gain[t]
        return x

    def deflicker(self, images, plate, radius, strength, level_radius=0, edge_radius=0, edge_smoothness=0.001, comp=None):
        x0 = to_np(images)
        x = x0
        pl = to_np(plate)[..., :3]
        n, H, W = x.shape[:3]
        idx = np.minimum(np.arange(n), len(pl) - 1)
        gray_full = []
        for i in range(n):
            g = pl[idx[i]] @ LUMA
            if g.shape != (H, W):
                g = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA)
            gray_full.append(g.astype(np.float32))
        if radius > 0 and n > 1:
            s = self.flow_scale(H, W)
            size = (max(8, int(round(W * s))), max(8, int(round(H * s))))
            gray = np.stack([cv2.resize(g, size, interpolation=cv2.INTER_AREA) for g in gray_full])
            x = self.temporal(x, gray, radius)
        if x is x0 and (level_radius > 0 and n > 1 or edge_radius > 0):
            x = x0.copy()
        if level_radius > 0 and n > 1:
            x = self.level(x, level_radius)
        if edge_radius > 0:
            def edge(i):
                for c in range(x.shape[-1]):
                    x[i, ..., c] = guided(gray_full[i], x[i, ..., c].astype(np.float32), edge_radius, edge_smoothness)
            with ThreadPoolExecutor(self.workers()) as ex:
                list(ex.map(edge, range(n)))
        if x is x0:
            x = x0.astype(np.float32)
        else:
            for i in range(n):
                x[i] = (x0[i] + strength * (x[i] - x0[i])).astype(np.float32)
        out_comp = x
        if comp is not None:
            cp = to_np(comp)[..., :3]
            m = min(len(cp), n)
            out_comp = np.empty((m,) + cp.shape[1:3] + (3,), np.float32)
            for i in range(m):
                lin = srgb_to_linear(cp[i]) - x0[i, ..., :3] + x[i, ..., :3]
                out_comp[i] = np.clip(linear_to_srgb(lin), 0, 1)
        return (to_t(x), to_t(out_comp))


class EFMaskSteady:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "mask": ("MASK", {"tooltip": "The object's mask per frame (SAM3 track)."}),
            "plate": ("IMAGE", {"tooltip": "The plate the mask belongs to; the motion is measured on it."}),
            "radius": ("INT", {"default": 0, "min": 0, "max": 8, "tooltip": "Neighbour frames on each side that are aligned and averaged. 0 = off (the mask as it is)."}),
            "threshold": ("FLOAT", {"default": 0.5, "min": 0.05, "max": 0.95, "step": 0.05, "tooltip": "Where the averaged mask is cut again: lower keeps more of the object, higher less. Sure parts (0.15 above) keep the less sure ones (down to 0.2 below) that touch them."}),
        }}

    RETURN_TYPES = ("MASK",)
    FUNCTION = "steady"
    CATEGORY = "Element Forge/Post"
    DESCRIPTION = ("Less flicker in an object mask where the object blurs or the light is poor: every frame is averaged with its "
                   "neighbours after aligning them with the plate's optical flow, then cut sharp again with two thresholds, "
                   "so a fast object keeps its less sure edges where they touch its sure core. 0 = off.")

    def steady(self, mask, plate, radius, threshold=0.5):
        m = mask if mask.ndim == 3 else mask[None]
        n = m.shape[0]
        if radius <= 0 or n < 2:
            return (mask,)
        x = m.detach().cpu().float().numpy()[..., None].copy()
        H, W = x.shape[1:3]
        pl = to_np(plate)[..., :3]
        s = EFDeflicker.flow_scale(H, W)
        size = (max(8, int(round(W * s))), max(8, int(round(H * s))))
        gray = np.stack([cv2.resize((pl[min(i, len(pl) - 1)] @ LUMA).astype(np.float32), size, interpolation=cv2.INTER_AREA)
                         for i in range(n)])
        avg = EFDeflicker().temporal(x, gray, int(radius))[..., 0]
        return (to_t(hysteresis(avg, min(0.95, threshold + 0.15), max(0.05, threshold - 0.2)).astype(np.float32)),)


def hysteresis(avg, high, low):
    out = np.zeros(avg.shape, bool)
    for t, a in enumerate(avg):
        n, lab = cv2.connectedComponents((a >= low).astype(np.uint8), connectivity=8)
        if n > 1:
            keep = np.zeros(n, bool)
            keep[np.unique(lab[a >= high])] = True
            keep[0] = False
            out[t] = keep[lab]
    return out


class EFFreeVRAM:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"images": ("IMAGE", {"tooltip": "Passed through unchanged; connect it before the node that needs the memory."})}}

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "free"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Unloads all models from the GPU and passes the images through (before nodes that manage their own model)."

    def free(self, images):
        try:
            import comfy.model_management as mm
            mm.unload_all_models()
            mm.soft_empty_cache()
        except Exception:
            pass
        return (images,)


class EFMoGeNormals:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "moge_model": ("MOGE_MODEL",),
            "image": ("IMAGE",),
            "resolution_level": ("INT", {"default": 9, "min": 0, "max": 9, "tooltip": "0 = fastest, 9 = most detail (as in Run MoGe Inference)."}),
            "batch_size": ("INT", {"default": 2, "min": 1, "max": 64, "tooltip": "Frames per inference call; lower it if MoGe runs out of memory."}),
            "output": (["normal_opengl", "normal_directx"], {"default": "normal_opengl", "tooltip": "Normal-map convention (Depth Light expects OpenGL)."}),
        }}

    RETURN_TYPES = ("IMAGE", "FLOAT", "FLOAT")
    RETURN_NAMES = ("normals", "depth_range", "fov")
    OUTPUT_TOOLTIPS = ("The normal map per frame.",
                       "How much further the far part of the shot is than the near part (far / near, 2nd and 98th percentile "
                       "of MoGe-2's metric depth over the clip, sky left out): Depth Light's depth_range.",
                       "The camera's field of view along the longer image side (degrees, median over the clip, recovered by "
                       "MoGe-2): Depth Light's fov.")
    FUNCTION = "run"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("MoGe-2 normals in one step (Run MoGe Inference + Render MoGe Geometry) without keeping the geometry on the "
                   "GPU; also the shot's depth range and field of view for Depth Light.")

    @staticmethod
    def scene(depths, masks, intrinsics, w, h):
        import numpy as np
        vals = []
        for d, m in zip(depths, masks):
            d = d.float().cpu().numpy()
            ok = np.isfinite(d) & (d > 0)
            if m is not None:
                ok &= m.cpu().numpy().astype(bool)
            vals.append(d[ok])
        v = np.concatenate(vals) if vals else np.zeros(0)
        if len(v) < 16:
            rng = 3.0
        else:
            near, far = np.percentile(v, 2), np.percentile(v, 98)
            rng = float(np.clip(far / max(near, 1e-6), 1.05, 100.0))
        fovs = []
        for K in intrinsics:
            K = K.float().cpu().numpy()
            f = K[:, 0, 0] if w >= h else K[:, 1, 1]
            fovs += list(np.degrees(2 * np.arctan(0.5 / np.maximum(f, 1e-6))))
        fov = float(np.clip(np.median(fovs), 5.0, 150.0)) if fovs else 65.0
        return round(rng, 3), round(fov, 2)

    def run(self, moge_model, image, resolution_level, batch_size, output):
        import comfy.model_management as mm
        import comfy.utils
        import torch
        from comfy_extras.nodes_moge import MoGeInference, MoGeRender
        n, parts = image.shape[0], []
        depths, masks, intr = [], [], []
        pbar = comfy.utils.ProgressBar(n)
        for i in range(0, n, batch_size):
            geo = MoGeInference.execute(moge_model=moge_model, image=image[i:i + batch_size], resolution_level=resolution_level,
                                        fov_x_degrees=0.0, batch_size=batch_size, force_projection=True, apply_mask=False,
                                        refine_steps=0).args[0]
            try:
                if "depth" in geo:
                    depths.append(geo["depth"][:, ::4, ::4].float().cpu())
                    masks.append(geo["mask"][:, ::4, ::4].cpu() if "mask" in geo else None)
                if "intrinsics" in geo:
                    intr.append(geo["intrinsics"].float().cpu())
                parts.append(MoGeRender.execute(moge_geometry=geo, output=output).args[0])
            finally:
                geo.clear()
                del geo
                mm.soft_empty_cache()
            pbar.update_absolute(min(i + batch_size, n))
        rng, fov = self.scene(depths, masks, intr, image.shape[2], image.shape[1])
        print(f"[EF MoGe Normals] depth range {rng} (far / near), fov {fov} deg")
        return (torch.cat(parts, dim=0), rng, fov)


class EFClipFrames:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "video": ("VIDEO",),
            "frames": ("INT", {"default": 121, "min": 1, "max": 100000, "tooltip": "Frames to keep from the start; exactly these are decoded. Keep it at least as high as the frames of EF Frame Step / EF Track ROI after it."}),
        }}

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "clip"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Keeps only the first frames of a long clip before decoding (saves RAM); shorter clips pass unchanged."

    @staticmethod
    def first_pts(src, n):
        import io as _io
        import av
        try:
            with av.open(src) as c:
                st = c.streams.video[0]
                tb, pts = float(st.time_base), []
                for pkt in c.demux(st):
                    if pkt.pts is not None:
                        pts.append(pkt.pts)
                    if len(pts) >= n + 32:
                        break
        finally:
            if isinstance(src, _io.BytesIO):
                src.seek(0)
        return sorted(pts), tb

    def clip(self, video, frames):
        try:
            p, tb = self.first_pts(video.get_stream_source(), frames)
        except Exception:
            return (video,)
        if len(p) <= frames:
            return (video,)
        end = (p[frames] + 0.5) * tb
        trimmed = video.as_trimmed(0.0, end, strict_duration=False)
        return (trimmed if trimmed is not None else video,)


STILL_FPS = 24.0
STILL_EXT = (".png", ".jpg", ".jpeg", ".webp")


def load_still(path):
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("I;16", "I;16B", "I;16L", "I"):
            a = np.asarray(im, dtype=np.float32) / 65535.0
            return np.repeat(np.clip(a, 0, 1)[..., None], 3, axis=2)
        return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


class EFStillClip:

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "image": ("STRING", {"default": "", "tooltip": "A picture in ComfyUI's input folder (png, jpg, webp). Empty: the video passes."}),
            "seconds": ("FLOAT", {"default": 3.0, "min": 0.1, "max": 60.0, "step": 0.1, "tooltip": "Length of the still clip."}),
            "frames": ("INT", {"default": 161, "min": 1, "max": 100000, "tooltip": "At most this many frames (the frames of the workflow)."}),
        }, "optional": {
            "video": ("VIDEO", {"tooltip": "The clip; used when no picture is set."}),
        }}

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "clip"
    CATEGORY = "Element Forge"
    DESCRIPTION = "A picture from the input folder as a still clip of the chosen length (24 fps); without a picture the video passes."

    def clip(self, image, seconds, frames, video=None):
        name = (image or "").strip()
        if not name:
            if video is None:
                raise ValueError("EF Still Clip: neither a picture nor a video.")
            return (video,)
        import folder_paths
        import torch
        from fractions import Fraction
        try:
            from comfy_api.latest import InputImpl, Types
            make = lambda imgs: InputImpl.VideoFromComponents(Types.VideoComponents(images=imgs, audio=None, frame_rate=Fraction(STILL_FPS)))
        except ImportError:
            from comfy_api.input_impl import VideoFromComponents
            from comfy_api.util import VideoComponents
            make = lambda imgs: VideoFromComponents(VideoComponents(images=imgs, audio=None, frame_rate=Fraction(STILL_FPS)))
        path = folder_paths.get_annotated_filepath(name)
        if not name.lower().endswith(STILL_EXT) or not os.path.isfile(path):
            raise ValueError(f"EF Still Clip: no picture {name} in the input folder.")
        n = max(1, min(int(frames), int(round(float(seconds) * STILL_FPS))))
        one = torch.from_numpy(load_still(path))[None]
        return (make(one.expand(n, -1, -1, -1).contiguous()),)

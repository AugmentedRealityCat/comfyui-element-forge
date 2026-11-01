import hashlib
import json
import os
import re
import shutil
import time

import numpy as np

import folder_paths

FOLDER = ("element-forge", "clips")
SAFE = re.compile(r"[^A-Za-z0-9._ -]")
TRACK_KEY = re.compile(r"^[0-9a-f]{16}$")


def clip_folder(clip, make=False):
    name = SAFE.sub("_", os.path.basename(str(clip or ""))).strip(" .")
    if not name:
        raise ValueError("no clip")
    d = os.path.join(folder_paths.get_output_directory(), *FOLDER, name)
    if make:
        os.makedirs(d, exist_ok=True)
    return d


def clip_source(clip):
    p = os.path.join(folder_paths.get_input_directory(), os.path.basename(str(clip or "")))
    try:
        st = os.stat(p)
        return {"size": st.st_size, "mtime": round(st.st_mtime, 3)}
    except OSError:
        return None


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    part = path + f".{os.getpid()}.part"
    with open(part, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(part, path)


def analysis_info(clip, frames=None):
    try:
        d = clip_folder(clip)
    except ValueError:
        return None
    info = _read_json(os.path.join(d, "analysis.json"))
    if not info or info.get("source") != clip_source(clip):
        return None
    if frames is not None and int(info.get("frames", -1)) != int(frames):
        return None
    if "depth" in info.get("parts", []) and depth_edge_of(info) != DEPTH_EDGE:
        return None
    return info


def _q16(arr):
    lo, hi = float(arr.min()), float(arr.max())
    q = np.round((arr - lo) / max(hi - lo, 1e-12) * 65535.0).astype(np.uint16)
    return q, lo, hi


def _save16(path, arr):
    q, lo, hi = _q16(arr)
    part = path + f".{os.getpid()}.part.npy"
    np.save(part, q)
    os.replace(part, path)
    return [lo, hi]


def _load16(path, rng):
    q = np.load(path, mmap_mode="r")
    lo, hi = float(rng[0]), float(rng[1])
    return q.astype(np.float32) * np.float32((hi - lo) / 65535.0) + np.float32(lo)


def _preview(path, frames, fps):
    import av
    f, h, w = frames.shape[:3]
    w2, h2 = w + w % 2, h + h % 2
    part = path + f".{os.getpid()}.part.mp4"
    rng = np.random.default_rng(0)
    with av.open(part, "w", format="mp4") as c:
        s = c.add_stream("libx264", rate=max(1, int(round(fps))))
        s.width, s.height, s.pix_fmt = w2, h2, "yuv420p"
        s.options = {"crf": "16", "preset": "veryfast"}
        for i in range(f):
            x = np.clip(frames[i] * 255.0 + rng.uniform(-0.5, 0.5, frames[i].shape), 0, 255).astype(np.uint8)
            if (w2, h2) != (w, h):
                x = np.pad(x, ((0, h2 - h), (0, w2 - w), (0, 0)), mode="edge")
            for pkt in s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(x), format="rgb24")):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    os.replace(part, path)


def camera_motion(plate):
    import cv2
    f, h, w = plate.shape[:3]
    k = min(1.0, 640.0 / max(h, w))
    gray = [cv2.resize(cv2.cvtColor((np.clip(plate[i], 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY), None, fx=k, fy=k,
                       interpolation=cv2.INTER_AREA) for i in range(f)]
    acc = np.eye(3)
    out = [[1.0, 0.0, 0.0, 0.0]]
    for i in range(1, f):
        pts = cv2.goodFeaturesToTrack(gray[i - 1], 400, 0.01, 8)
        m = None
        if pts is not None and len(pts) >= 8:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(gray[i - 1], gray[i], pts, None, winSize=(21, 21), maxLevel=3)
            ok = st[:, 0] == 1
            if ok.sum() >= 8:
                m, _ = cv2.estimateAffinePartial2D(pts[ok], nxt[ok], method=cv2.RANSAC, ransacReprojThreshold=1.5)
        step = np.eye(3) if m is None else np.vstack([m, [0, 0, 1]])
        acc = step @ acc
        a, b = acc[0, 0], acc[1, 0]
        out.append([round(float(a), 6), round(float(b), 6), round(float(acc[0, 2] / k), 3), round(float(acc[1, 2] / k), 3)])
    return out


DEPTH_VDA, DEPTH_DC = "Video Depth Anything", "DepthCrafter"


DEPTH_EDGE = 0


def depth_edge_of(info):
    info = info or {}
    return int(info.get("depth_edge", 0 if "depth_model" in info else 6))


def depth_model_of(info):
    return (info or {}).get("depth_model") or DEPTH_VDA


class EFSaveAnalysis:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "clip": ("STRING", {"default": "", "tooltip": "The clip's file name in ComfyUI's input folder (or the picture of a still clip)."}),
                "plate": ("IMAGE", {"tooltip": "The clip's frames (for the camera's motion)."}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0}),
            },
            "optional": {
                "depth": ("IMAGE", {"tooltip": "Depth of every frame (Video Depth Anything + EF Deflicker)."}),
                "normals": ("IMAGE", {"tooltip": "Normals of every frame (EF MoGe Normals)."}),
                "depth_model": ("STRING", {"default": DEPTH_VDA, "tooltip": "The model that made the depth: a run takes the "
                                           "kept depth only if it asks for the same model."}),
                "depth_edge": ("INT", {"default": DEPTH_EDGE, "min": 0, "max": 64, "tooltip": "The edge filter of EF Deflicker that "
                                       "made the depth: an analysis with another one counts as not done."}),
            },
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Keeps the scene analysis of a clip in output/element-forge/clips/<clip>/ (depth and normals as 16 bit, "
                   "the camera's motion, MP4 previews). Later runs of the clip with the same frames take it from there.")

    def save(self, clip, plate, fps, depth=None, normals=None, depth_model=None, depth_edge=DEPTH_EDGE):
        d = clip_folder(clip, make=True)
        p = plate.detach().cpu().float().numpy()
        f, h, w = p.shape[:3]
        info = {"clip": os.path.basename(clip), "source": clip_source(clip), "frames": int(f), "width": int(w), "height": int(h),
                "fps": float(fps), "time": time.time(), "parts": [], "range": {}}
        if depth is not None:
            dep = depth.detach().cpu().float().numpy()[..., :1]
            info["range"]["depth"] = _save16(os.path.join(d, "depth.npy"), dep)
            lo, hi = float(dep.min()), float(dep.max())
            g = (dep - lo) / max(hi - lo, 1e-12)
            _preview(os.path.join(d, "depth.mp4"), np.repeat(g, 3, axis=-1), fps)
            info["parts"].append("depth")
            info["depth_model"] = depth_model or DEPTH_VDA
            info["depth_edge"] = int(depth_edge)
        if normals is not None:
            nor = normals.detach().cpu().float().numpy()[..., :3]
            info["range"]["normals"] = _save16(os.path.join(d, "normals.npy"), nor)
            _preview(os.path.join(d, "normals.mp4"), np.clip(nor, 0, 1), fps)
            info["parts"].append("normals")
        _write_json(os.path.join(d, "camera.json"), {"fps": float(fps), "frames": int(f), "motion": camera_motion(p)})
        info["parts"].append("camera")
        _write_json(os.path.join(d, "analysis.json"), info)
        return {"ui": {"text": [json.dumps({"analysis": info["clip"], "parts": info["parts"]})]}}


class EFLoadAnalysis:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "clip": ("STRING", {"default": ""}),
            "part": (["depth", "normals"], {"default": "depth"}),
            "frames": ("INT", {"default": 81, "min": 1, "max": 100000, "tooltip": "Frames of the run; the kept analysis must have exactly these."}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "load"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Depth or normals of a clip from its kept analysis (EF Save Analysis), instead of computing them again."

    @classmethod
    def IS_CHANGED(s, clip, part, frames):
        info = analysis_info(clip, frames)
        return f"{info and info.get('time')}"

    def load(self, clip, part, frames):
        import torch
        info = analysis_info(clip, frames)
        if not info or part not in info.get("parts", []) or part not in info.get("range", {}):
            raise ValueError(f"no kept {part} for {clip} with {frames} frames: analyse the scene again")
        a = _load16(os.path.join(clip_folder(clip), f"{part}.npy"), info["range"][part])
        if part == "depth":
            a = np.repeat(a, 3, axis=-1)
        return (torch.from_numpy(np.ascontiguousarray(a)),)


def own_mask_hash(name):
    if not name:
        return ""
    p = os.path.join(folder_paths.get_input_directory(), str(name).replace("\\", "/"))
    try:
        with open(p, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:16]
    except OSError:
        return "missing"


def leave_of(where):
    pts = " ".join(str(where.get("leave") or "").split())
    words = "; ".join(w.strip().lower() for w in str(where.get("leave_words") or "").replace("\n", ";").split(";") if w.strip())
    return [pts, words] if pts or words else None


def mask_frame_of(where):
    frame, pts = int(where.get("frame") or 0), " ".join(str(where.get("add") or "").split())
    words = "; ".join(w.strip().lower() for w in str(where.get("add_words") or "").replace("\n", ";").split(";") if w.strip())
    return [frame, pts, words] if frame or pts or words else None


def fixes_of(where):
    text = str(where.get("fixes") or "").strip()
    if text in ("", "[]"):
        return None
    try:
        from .mask_controls import parse_fixes
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ef_mask_controls", os.path.join(os.path.dirname(os.path.abspath(__file__)), "mask_controls.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parse_fixes = mod.parse_fixes
    fx = parse_fixes(text)
    return [[f["frame"], [[round(p["x"]), round(p["y"])] for p in f["add"]], [[round(p["x"]), round(p["y"])] for p in f["leave"]],
             [t.lower() for t in f["add_words"]], [t.lower() for t in f["leave_words"]]] for f in fx] or None


def track_key(where):
    parts = [os.path.basename(str(where.get("clip", ""))), clip_source(where.get("clip")), int(where.get("frames", 0)),
             [int(v) for v in where.get("a") or []], [int(v) for v in where.get("b") or []], str(where.get("word") or "").strip().lower(),
             bool(where.get("alike")), bool(where.get("own")), own_mask_hash(where.get("own_mask")) if where.get("own") else ""]
    if leave_of(where):
        parts.append(leave_of(where))
    if mask_frame_of(where):
        parts.append(["at", *mask_frame_of(where)])
    if fixes_of(where):
        parts.append(["fixes", fixes_of(where)])
    return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:16]


def tracks_of(clip):
    try:
        d = os.path.join(clip_folder(clip), "tracks")
    except ValueError:
        return []
    if not os.path.isdir(d):
        return []
    out = []
    for k in sorted(os.listdir(d)):
        info = _read_json(os.path.join(d, k, "track.json")) if TRACK_KEY.match(k) else None
        if info and info.get("where", {}).get("source") == clip_source(clip):
            out.append({"key": k, **info})
    return sorted(out, key=lambda t: -t.get("time", 0))


def track_info(where):
    key = track_key(where)
    try:
        info = _read_json(os.path.join(clip_folder(where.get("clip")), "tracks", key, "track.json"))
    except ValueError:
        return None
    return {"key": key, **info} if info else None


def clear_track(clip, key):
    if not TRACK_KEY.match(str(key)):
        raise ValueError("bad track key")
    d = os.path.join(clip_folder(clip), "tracks", key)
    if os.path.isdir(d):
        shutil.rmtree(d)
        return True
    return False


class EFSaveTrack:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mask": ("MASK", {"tooltip": "The object mask of point A through the clip (SAM3)."}),
                "where": ("STRING", {"default": "{}", "tooltip": "JSON: clip, frames, a, b, word, alike, own, own_mask, follows."}),
            },
            "optional": {"mask_b": ("MASK", {"tooltip": "The object mask of point B (A to B)."}),
                         "left_out": ("MASK", {"tooltip": "The parts left out of the object, through the clip (EF Leave Out (track))."})},
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "save"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Keeps the object masks of a track in output/element-forge/clips/<clip>/tracks/ for later runs (EF Load Track)."

    def save(self, mask, where, mask_b=None, left_out=None):
        w = json.loads(where or "{}")
        w["source"] = clip_source(w.get("clip"))
        key = track_key(w)
        d = os.path.join(clip_folder(w.get("clip"), make=True), "tracks", key)
        os.makedirs(d, exist_ok=True)
        for name, m in (("mask_a", mask), ("mask_b", mask_b), ("mask_left", left_out)):
            if m is None:
                continue
            q = np.round(np.clip(m.detach().cpu().float().numpy(), 0, 1) * 255).astype(np.uint8)
            part = os.path.join(d, f"{name}.{os.getpid()}.part.npz")
            np.savez_compressed(part, q=q)
            os.replace(part, os.path.join(d, f"{name}.npz"))
        _write_json(os.path.join(d, "track.json"), {"where": w, "time": time.time(), "frames": int(mask.shape[0]),
                                                    "b": mask_b is not None, "left": left_out is not None})
        return {"ui": {"text": [json.dumps({"track": key})]}}


class EFLoadTrack:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {
            "where": ("STRING", {"default": "{}"}),
            "which": (["a", "b", "left"], {"default": "a", "tooltip": "a, b: the object masks; left: the parts left out of A."}),
        }}

    RETURN_TYPES = ("MASK",)
    FUNCTION = "load"
    CATEGORY = "Element Forge"
    DESCRIPTION = "The object mask of a kept track (EF Save Track) instead of running SAM3 again."

    @classmethod
    def IS_CHANGED(s, where, which):
        info = track_info(json.loads(where or "{}"))
        return f"{info and info.get('time')}"

    def load(self, where, which):
        import torch
        w = json.loads(where or "{}")
        key = track_key(w)
        p = os.path.join(clip_folder(w.get("clip")), "tracks", key, f"mask_{which}.npz")
        if not os.path.isfile(p):
            raise ValueError("this track is not kept any more: track it again")
        with np.load(p) as z:
            q = z["q"]
        return (torch.from_numpy(q.astype(np.float32) / 255.0),)

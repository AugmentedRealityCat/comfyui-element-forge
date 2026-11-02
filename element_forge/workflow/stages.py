import copy
import hashlib
import json
import logging
import os
import time
from fractions import Fraction

import numpy as np
from PIL import Image

import folder_paths

from ..app import compact_values as cv

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.dirname(os.path.dirname(HERE))
PRESETS = os.path.join(PACK_ROOT, "element_forge", "app", "app_presets.json")
CATEGORY = "Element Forge"
OPTIONS = "Element Forge/Options"
TOOLS = "Element Forge/Tools"
STYLE = "style default"
DEFAULT = "workflow default"
STAGES = ("models", "shot", "track", "element", "place", "light", "export")

OWN_MASK = "Own object mask (off = click)"
OWN_MASK_FILE = "Own object mask: first frame, paint the object (mask editor)"
GUIDE_FILE = "Guide drawing (paint in the mask editor)"
STICKS_SCENE = "Sticks to scene (off = object)"
TRACK_MASK = "Track follows the object mask (hands, bodies)"
STILL = "Fixed on screen (Follows: Screen)"
FRONT = "Object in front (its mask hides the element)"
LOCK = "Base locked to the point (no jitter of the base)"
ALL_ALIKE = "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)"
FOLLOWS = "Follows motion"
UPSCALE = "LTX upscale x2 (latent upscaler + second pass, test)"
INPAINT_SIGMAS = "Inpaint sigmas (start 0.909 = tested default)"
AI_GUIDE = cv.GUIDE
GUIDE_SOURCE = "Guide source"
PARTICLE_SEED = "Particle seed"
PREROLL = "Particle pre-roll (s, -2 = as in the preset, -1 = auto)"
PARTICLE_EMITTER = "Particle emitter (app, JSON)"
DISSOLVE_EXTRA = "Dissolve extra (JSON)"
STILL_IMAGE = "Still image (a picture in the input folder instead of the clip)"
STILL_LENGTH = "Still image length (s)"
CHECK_ONLY = "Check track only"
FOLLOWS_VALUES = {"point": (False, False, False), "object": (False, True, False), "scene": (True, False, False),
                  "screen": (False, False, True)}
GUIDE_CHOICES = ["style default", "none", "object shape", "drawn path", "particles"]
DEPTH_MODELS = ["Video Depth Anything", "DepthCrafter"]
UNPACK = (("plate", "IMAGE"), ("depth", "IMAGE"), ("normals", "IMAGE"), ("object mask", "MASK"), ("element", "IMAGE"),
          ("element alpha", "MASK"), ("light", "IMAGE"), ("glow", "IMAGE"), ("comp", "IMAGE"), ("fps", "FLOAT"))
SOURCES = {"plate": ("169", 0), "depth": ("176", 0), "normals": ("409", 0), "object mask": ("929", 0), "element": ("407", 0),
           "light": ("411", 0), "glow": ("413", 1), "comp": ("473", 0), "fps": ("167", 2)}
DISSOLVE_SOURCES = {"element": ("476", 0), "element alpha": ("476", 1), "light": ("703", 0)}
ELEMENT_RGBA = "327"
ELEMENT_SHOWN = "328"
NEEDS = {"element": "element", "element alpha": "element", "light": "element", "glow": "element", "comp": "element",
         "object mask": "track"}
_presets = None
_stage_map = None


def presets():
    global _presets
    if _presets is None:
        with open(PRESETS, encoding="utf-8") as f:
            _presets = json.load(f)
    return _presets


def stage_map():
    global _stage_map
    if _stage_map is None:
        with open(os.path.join(PACK_ROOT, "api_workflows", "element_forge.stages.json"), encoding="utf-8") as f:
            _stage_map = json.load(f)["nodes"]
    return _stage_map


def _styles():
    return cv.effect_styles(presets())


def _particle_style(kind, style):
    st = cv.style_def(presets(), kind, style) or {}
    return bool((st.get("settings") or {}).get("Particles")) or st.get("variant") == "climb"


def _light_gain(kind, style):
    eff = next((e for e in presets().get("effects", []) if e["id"] == kind), {})
    st = cv.style_def(presets(), kind, style) or {}
    return float(st.get("light_gain", eff.get("light_gain", 1.0)))


def _light_color(kind, style):
    eff = next((e for e in presets().get("effects", []) if e["id"] == kind), {})
    st = cv.style_def(presets(), kind, style) or {}
    return str(st.get("light_color", eff.get("light_color", "")) or "")


def _light_albedo_exposure(kind, style, night):
    if night:
        return 0.0
    eff = next((e for e in presets().get("effects", []) if e["id"] == kind), {})
    st = cv.style_def(presets(), kind, style) or {}
    return float(st.get("light_albedo_exposure", eff.get("light_albedo_exposure", 0.0)))


_graph_settings = None


def _choices(setting, fallback):
    global _graph_settings
    try:
        import nodes
        if _graph_settings is None:
            with open(os.path.join(PACK_ROOT, "api_workflows", "element_forge_app.json"), encoding="utf-8") as f:
                g = json.load(f)
            with open(os.path.join(PACK_ROOT, "api_workflows", "element_forge.settings.json"), encoding="utf-8") as f:
                sets = json.load(f)["settings"]
            _graph_settings = {k: (g[t[0]]["class_type"], t[1]) for k, t in
                               ((k, t[0] if isinstance(t[0], list) else t) for k, t in sets.items()) if t[0] in g}
        cls, field = _graph_settings[setting]
        spec = nodes.NODE_CLASS_MAPPINGS[cls].INPUT_TYPES()
        for part in ("required", "optional"):
            f = spec.get(part, {}).get(field)
            if f and isinstance(f[0], list):
                return list(f[0])
    except Exception:
        pass
    return list(fallback)


def _models(kind, keys):
    try:
        names = folder_paths.get_filename_list(kind)
    except Exception:
        return []
    return [n for n in names if any(k in n.lower() for k in keys)]


def _input_dir():
    return os.path.abspath(folder_paths.get_input_directory())


def _in_input(path):
    base = _input_dir()
    path = os.path.abspath(path)
    if os.path.commonpath([base, path]) != base:
        raise ValueError("EF Shot: the clip has to be in ComfyUI's input folder")
    return os.path.relpath(path, base).replace(os.sep, "/")


def _clip_from_video(video):
    src = video.get_stream_source() if hasattr(video, "get_stream_source") else None
    if not isinstance(src, str) or not os.path.isfile(src):
        raise ValueError("EF Shot: connect Load Video (a file in ComfyUI's input folder), or frames to 'images'")
    return _in_input(src), src


def _clip_from_images(images, fps):
    import av
    a = (images.clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
    h, w = a.shape[1] // 2 * 2, a.shape[2] // 2 * 2
    a = a[:, :h, :w, :3]
    name = f"ef_frames_{hashlib.sha1(a.tobytes() + str(fps).encode()).hexdigest()[:12]}.mp4"
    path = os.path.join(_input_dir(), name)
    if not os.path.isfile(path):
        tmp = path + ".part.mp4"
        with av.open(tmp, "w") as out:
            s = out.add_stream("libx264rgb", rate=Fraction(round(float(fps or 30) * 1000), 1000))
            s.width, s.height, s.pix_fmt = w, h, "rgb24"
            s.options = {"crf": "0", "preset": "veryfast"}
            for f in a:
                for p in s.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(f), format="rgb24")):
                    out.mux(p)
            for p in s.encode():
                out.mux(p)
        os.replace(tmp, path)
    return name, path


def _picture_file(image):
    a = (image[0].clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)[..., :3]
    name = f"ef_still_{hashlib.sha1(a.tobytes()).hexdigest()[:12]}.png"
    path = os.path.join(_input_dir(), name)
    if not os.path.isfile(path):
        Image.fromarray(a, "RGB").save(path)
    return name


def _paint_file(mask, size, tag):
    m = mask[0] if mask.dim() == 3 else mask
    m = (m.clamp(0, 1).cpu().numpy() * 255).round().astype(np.uint8)
    im = Image.fromarray(m, "L")
    if size and im.size != tuple(size):
        im = im.resize(tuple(size), Image.BILINEAR)
    a = 255 - np.asarray(im)
    if not (a < 128).any():
        raise ValueError(f"the {tag} is empty")
    name = f"ef_paint_{tag}_{hashlib.sha1(a.tobytes()).hexdigest()[:10]}.png"
    path = os.path.join(_input_dir(), name)
    if not os.path.isfile(path):
        rgba = np.zeros((a.shape[0], a.shape[1], 4), np.uint8)
        rgba[..., 3] = a
        Image.fromarray(rgba, "RGBA").save(path)
    return name


class _FileVideo:

    def __init__(self, path):
        self.path = path

    def get_stream_source(self):
        return self.path


class _File:

    def __init__(self, name):
        self.name = name


def _clip_info(name, path, still=None):
    from ..app.app_routes import clip_meta, still_meta
    m = still_meta(path, still) if still is not None else clip_meta(path)
    out = {"name": name, "width": m["width"], "height": m["height"], "frames": m["frames"], "fps": m["fps"], "seconds": m["seconds"]}
    if still is not None:
        out["still"] = True
    return out


def _ground(path, x, y, still=False):
    from ..app.app_routes import first_frame
    im = first_frame(path).convert("RGB")
    a = np.asarray(im, dtype=np.float32)
    h, w = a.shape[:2]
    x, y = int(round(x)), int(round(y))
    patch = a[max(0, y - 2):min(h, y + 3), max(0, x - 2):min(w, x + 3)].reshape(-1, 3)
    return cv.luma_ground(patch.mean(0)) if len(patch) else None


def _json(text, who):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError(f"{who}: not JSON ({e})") from None


def _with(bundle, key, value, uid):
    out = dict(bundle or {})
    out[key] = value
    out["ids"] = {**(bundle or {}).get("ids", {}), key: str(uid) if uid is not None else None}
    return out


HIDDEN = {"hidden": {"unique_id": "UNIQUE_ID"}}


class EFForgeModels:
    @classmethod
    def INPUT_TYPES(cls):
        ltx = _models("diffusion_models", ("ltx",))
        if "unet_gguf" in getattr(folder_paths, "folder_names_and_paths", {}):
            ltx += [n for n in _models("unet_gguf", ("ltx",)) if n not in ltx]
        return {"required": {
            "LTX model": ([DEFAULT] + ltx, {"default": DEFAULT, "tooltip": "The LTX file that generates. workflow default = the INT8 file Element Forge was tested with; a .gguf needs ComfyUI-GGUF."}),
            "attention": (list(cv.LTX_ATTENTION), {"default": cv.LTX_ATTENTION[0], "tooltip": "comfy kitchen attention = INT8 attention: about a quarter faster with the INT8 file (not with GGUF)."}),
            "text encoder": ([DEFAULT] + _models("text_encoders", ("gemma",)), {"default": DEFAULT, "tooltip": "workflow default = the INT8 Gemma text encoder."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_MODELS",)
    RETURN_NAMES = ("models",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "Which LTX files this computer uses. Without this node EF Element takes the files Element Forge was tested with."

    def build(self, unique_id=None, **kw):
        return ({"file": "" if kw["LTX model"] == DEFAULT else kw["LTX model"],
                 "attention": "" if kw["attention"] == cv.LTX_ATTENTION[0] else kw["attention"],
                 "te": "" if kw["text encoder"] == DEFAULT else kw["text encoder"], "id": str(unique_id) if unique_id else None},)


class EFForgeShot:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "depth model": (DEPTH_MODELS, {"default": DEPTH_MODELS[0], "tooltip": "Video Depth Anything: quick, tested on every route. DepthCrafter: steadier depth over time, slower."}),
            "night": ("BOOLEAN", {"default": False, "tooltip": "Turn the clip into night (day for night) before the effect goes in."}),
        }, "optional": {
            "video": ("VIDEO", {"tooltip": "The clip, from Load Video (a file in ComfyUI's input folder)."}),
            "images": ("IMAGE", {"tooltip": "Or the clip as frames from any node (written once into the input folder as a lossless clip)."}),
            "picture": ("IMAGE", {"tooltip": "Or one picture (e.g. Load Image) held as a still clip."}),
            "fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 240.0, "step": 0.001, "advanced": True, "tooltip": "Frames per second of 'images'."}),
            "still length": ("FLOAT", {"default": 3.0, "min": 0.2, "max": 60.0, "step": 0.1, "advanced": True, "tooltip": "Seconds a picture is held."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_SHOT",)
    RETURN_NAMES = ("shot",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "The clip: frames, depth, normals and night. EF Unpack gives the plate, depth and normals to other nodes."

    def build(self, unique_id=None, video=None, images=None, picture=None, fps=30.0, **kw):
        given = [x for x in (video, images, picture) if x is not None]
        if len(given) != 1:
            raise ValueError("EF Shot: connect one of video (Load Video), images or picture")
        still = None
        if picture is not None:
            name = picture.name if isinstance(picture, _File) else _picture_file(picture)
            path = folder_paths.get_annotated_filepath(name)
            still = float(kw.get("still length", 3.0))
        elif images is not None:
            name, path = _clip_from_images(images, fps)
        else:
            name, path = _clip_from_video(video)
        shot = {"clip": _clip_info(name, path, still), "path": path, "night": bool(kw["night"]),
                "depth": "depthcrafter" if kw["depth model"] == "DepthCrafter" else ""}
        return (_with(None, "shot", shot, unique_id),)


class EFForgeTrack:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "shot": ("EF_SHOT",),
            "point A x": ("INT", {"default": -1, "min": -1, "max": 16384, "tooltip": "Point A in clip pixels: where the effect sits or starts (click into the picture above). -1 = the middle."}),
            "point A y": ("INT", {"default": -1, "min": -1, "max": 16384}),
            "point B x": ("INT", {"default": -1, "min": -1, "max": 16384, "tooltip": "Point B for effects between two points (Shift+click). -1 = none."}),
            "point B y": ("INT", {"default": -1, "min": -1, "max": 16384}),
            "object word": ("STRING", {"default": "", "tooltip": "What you clicked, in one or two words (e.g. hand). Helps the tracker find it."}),
            "follows": (["style default", "point", "object", "scene", "screen"], {"default": STYLE,
                        "tooltip": "Point: the spot you clicked. Object: the whole object. Scene: stays in the world while the camera moves. Screen: the same place in the picture. style default = what the style was tested with."}),
            "all alike": ("BOOLEAN", {"default": False, "tooltip": "Track every object like the clicked one (e.g. all sticks of a crown)."}),
            "follows motion": ("BOOLEAN", {"default": False, "tooltip": "The element is carried by the motion in the clip (AI elements)."}),
        }, "optional": {
            "own mask": ("MASK", {"tooltip": "Your own object mask (first frame, e.g. Load Image painted in the mask editor) instead of the click."}),
            "motion strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 3.0, "step": 0.05, "advanced": True, "tooltip": "How strongly the motion carries the element. 1 = as tested."}),
            "motion lag": ("FLOAT", {"default": 0.6, "min": 0.0, "max": 1.0, "step": 0.05, "advanced": True, "tooltip": "How much the element lags behind the motion. 0.6 = as tested."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_SHOT",)
    RETURN_NAMES = ("shot",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "Where the effect goes and what it follows: points A and B, object word, Follows. The track check shows on this node."

    def build(self, shot, unique_id=None, **kw):
        c = shot["shot"]["clip"]
        where = {"a": None, "b": None, "word": str(kw["object word"]).strip()}
        if kw["point A x"] >= 0 and kw["point A y"] >= 0:
            where["a"] = {"x": min(kw["point A x"], c["width"] - 1), "y": min(kw["point A y"], c["height"] - 1)}
            g = _ground(shot["shot"]["path"], where["a"]["x"], where["a"]["y"], c.get("still"))
            if g:
                where["a"]["ground"] = g
        if kw["point B x"] >= 0 and kw["point B y"] >= 0:
            where["b"] = {"x": min(kw["point B x"], c["width"] - 1), "y": min(kw["point B y"], c["height"] - 1)}
        own = kw.get("own mask")
        track = {"where": where, "follows": kw["follows"], "alike": bool(kw["all alike"]), "motion": bool(kw["follows motion"]),
                 "motion strength": float(kw.get("motion strength", 1.0)), "motion lag": float(kw.get("motion lag", 0.6)),
                 "own mask": None if own is None else own.name if isinstance(own, _File) else _paint_file(own, (c["width"], c["height"]), "mask")}
        return (_with(shot, "track", track, unique_id),)


class EFForgeElement:
    @classmethod
    def INPUT_TYPES(cls):
        styles = _styles()
        return {"required": {
            "shot": ("EF_SHOT",),
            "effect": (styles, {"default": styles[0], "tooltip": "Effect and style, as in the app (effect/style)."}),
            "how it goes in": (["style default", "overlay", "inpaint"], {"default": STYLE, "tooltip": "overlay: made alone on black and laid over the clip. inpaint: the AI paints it into the clip."}),
            "strength": (["normal", "subtle", "strong"], {"default": "normal"}),
            "describe": ("STRING", {"default": "", "tooltip": "What it is, in a few words (empty = the style's). For your own effect: the effect itself."}),
            "starts at": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 600.0, "step": 0.05, "tooltip": "Seconds into the clip where the effect starts."}),
            "quality": (["full", "preview"], {"default": "full", "tooltip": "preview = half the size, without light, glow and normals: quicker to try a look (AI styles on black)."}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 2 ** 31 - 1, "control_after_generate": True}),
        }, "optional": {
            "models": ("EF_MODELS",),
            "particles": ("EF_PARTICLES",),
            "guide": ("EF_GUIDE",),
            "dissolve": ("EF_DISSOLVE",),
            "ltx": ("EF_LTX",),
            "look words": ("STRING", {"default": "", "advanced": True, "tooltip": "How it looks (empty = the style's)."}),
            "motion words": ("STRING", {"default": "", "advanced": True, "tooltip": "How it moves (empty = the style's)."}),
            "contact words": ("STRING", {"default": "", "advanced": True, "tooltip": "Where it touches: what it does to its surroundings (empty = the style's)."}),
            "prompt": ("STRING", {"default": "", "multiline": True, "advanced": True, "tooltip": "The whole prompt by hand; empty = made from the words."}),
            "scene sentence": ("STRING", {"default": "", "advanced": True, "tooltip": "Inpaint: the shot in one sentence (place, person or object, light)."}),
            "direction": ("INT", {"default": -1, "min": -1, "max": 359, "advanced": True, "tooltip": "Direction in degrees (0 up, 90 right). -1 = the style's."}),
            "ends at": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 600.0, "step": 0.05, "advanced": True, "tooltip": "Dissolve: seconds where it is gone. -1 = the end of the clip."}),
            "area x": ("INT", {"default": -1, "min": -1, "max": 16384, "advanced": True, "tooltip": "The area the effect is made in, left edge in clip pixels. -1 = automatic (as the style)."}),
            "area y": ("INT", {"default": -1, "min": -1, "max": 16384, "advanced": True}),
            "area width": ("INT", {"default": -1, "min": -1, "max": 16384, "advanced": True}),
            "area height": ("INT", {"default": -1, "min": -1, "max": 16384, "advanced": True}),
            "round soft edge": (["style default", "on", "off"], {"default": STYLE, "advanced": True, "tooltip": "On black: a round soft edge instead of the straight edge of the generated area."}),
            "solid element": (["style default", "on", "off"], {"default": STYLE, "advanced": True, "tooltip": "Cut the element out with a matte (solid things) instead of reading alpha from its light (glowing things)."}),
            "keep original": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "advanced": True, "tooltip": "Inpaint: repaints less of the area, so it stays closer to the clip. 0 = off."}),
            "preview on node": ("BOOLEAN", {"default": True, "advanced": True, "tooltip": "Show the element with its alpha on this node after a run."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_ELEMENT",)
    RETURN_NAMES = ("element",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "The effect and its style, how it goes in, its words and timing. Makes the element (AI, particles or dissolve); the element shows on this node."

    def build(self, shot, unique_id=None, models=None, particles=None, guide=None, dissolve=None, ltx=None, **kw):
        kind, _, style = kw["effect"].partition("/")
        if not cv.style_def(presets(), kind, style):
            raise ValueError(f"EF Element: unknown effect and style {kw['effect']}")
        area = [kw.get(k, -1) for k in ("area x", "area y", "area width", "area height")]
        el = {"kind": kind, "style": style, "how": kw["how it goes in"], "strength": kw["strength"],
              "text": {"what": kw["describe"], "look": kw.get("look words", ""), "motion": kw.get("motion words", ""),
                       "contact": kw.get("contact words", "")},
              "prompt": kw.get("prompt", "") or "", "scene": kw.get("scene sentence", "") or "",
              "dir": None if kw.get("direction", -1) < 0 else int(kw["direction"]),
              "start": float(kw["starts at"]), "end": None if kw.get("ends at", -1) < 0 else float(kw["ends at"]),
              "box": None if min(area) < 0 or area[2] < 1 or area[3] < 1 else {"x": area[0], "y": area[1], "w": area[2], "h": area[3]},
              "soft edge": kw.get("round soft edge", STYLE), "solid": kw.get("solid element", STYLE),
              "keep": float(kw.get("keep original", 0.0)), "quality": kw["quality"], "seed": int(kw["seed"]),
              "preview": bool(kw.get("preview on node", True)),
              "options": {"particles": particles, "guide": guide, "dissolve": dissolve, "ltx": ltx}}
        out = _with(shot, "element", el, unique_id)
        out["models"] = models
        if models and models.get("id"):
            out["ids"]["models"] = models["id"]
        return (out,)


class EFForgePlace:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "element": ("EF_ELEMENT",),
            "size": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 10.0, "step": 0.01, "tooltip": "Size of the element in the clip (share of the generated size). -1 = the style's (or the area's)."}),
            "side": ([STYLE] + _choices("Emitter side", ["bottom", "centre"]), {"default": STYLE, "tooltip": "Which side of the element sits on point A."}),
            "depth offset": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01, "tooltip": "+ = nearer, less hidden by the scene. 0 = as tested."}),
            "blend": ([STYLE] + _choices("Blend on black (add = light, over = solid)", ["add", "over"]), {"default": STYLE, "tooltip": "add = light (fire, glow), over = solid things."}),
        }, "optional": {
            "own element": ("EF_OWN_ELEMENT", {"tooltip": "An element of your own (EF Library Element, EF Element from Images) instead of the generated one."}),
            "groups": ("STRING", {"default": "", "multiline": True, "advanced": True, "tooltip": "Several copies as JSON, e.g. [{\"x\": 0.3, \"y\": 0.6}, {\"x\": 0.7, \"y\": 0.6}]. Empty = one."}),
            "inpaint key": ([STYLE] + _choices("Inpaint key", ["auto (effect color)"]), {"default": STYLE, "advanced": True, "tooltip": "Inpaint: how the painted effect is cut out of the clip again for the passes."}),
            "inpaint blend": ([STYLE] + _choices("Inpaint blend", ["add", "over"]), {"default": STYLE, "advanced": True}),
            "object in front": ("BOOLEAN", {"default": False, "advanced": True, "tooltip": "The object's mask (click / word) hides the element wherever the object is, whatever the depth map says: a person in front of a portal."}),
            "lock base": ("BOOLEAN", {"default": False, "advanced": True, "tooltip": "The element's base stays on point A in every frame (a flame on a wick or a blossom does not jitter)."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_LAYER",)
    RETURN_NAMES = ("layer",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "Where and how the element sits in the clip: size, side, depth and blend."

    def build(self, element, unique_id=None, **kw):
        own = kw.get("own element")
        place = {"size": float(kw["size"]), "side": kw["side"], "depth": float(kw["depth offset"]), "blend": kw["blend"],
                 "groups": _json(kw.get("groups", ""), "EF Place: groups"), "key": kw.get("inpaint key", STYLE),
                 "inpaint blend": kw.get("inpaint blend", STYLE), "library": (own or {}).get("name"),
                 "front": bool(kw.get("object in front", False)), "lock": bool(kw.get("lock base", False))}
        return (_with(element, "place", place, unique_id),)


class EFForgeLight:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "layer": ("EF_LAYER,EF_ELEMENT",),
            "light": (["style default", "on", "off"], {"default": STYLE, "tooltip": "The light the effect casts on the clip (depth light)."}),
            "light strength": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.05, "tooltip": "1 = as tested."}),
            "glow": (["style default", "on", "off"], {"default": STYLE, "tooltip": "The glow around bright parts of the effect."}),
            "glow exposure": ("FLOAT", {"default": 0.0, "min": -6.0, "max": 6.0, "step": 0.1, "tooltip": "Stops brighter (+) or darker (-) than tested."}),
        }, "optional": {
            "groups in depth": ("BOOLEAN", {"default": False, "advanced": True, "tooltip": "Each group of copies gets its own depth from the scene."}),
        }, **HIDDEN}

    RETURN_TYPES = ("EF_LAYER",)
    RETURN_NAMES = ("layer",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "The light the effect casts on the clip and its glow."

    def build(self, layer, unique_id=None, **kw):
        light = {"light": kw["light"], "light strength": float(kw["light strength"]), "glow": kw["glow"],
                 "glow exposure": float(kw["glow exposure"]), "groups in depth": bool(kw.get("groups in depth", False))}
        return (_with(layer, "light", light, unique_id),)


PASS_NAMES = ("plate", "element", "light", "glow", "depth", "normals", "mask", "particles")


class EFForgeExport:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "layer": ("EF_LAYER,EF_ELEMENT",),
            "run name": ("STRING", {"default": "", "tooltip": "Folder under output/element-forge/. Empty = made from the settings (a change gives a new folder)."}),
            "EXR passes": ("BOOLEAN", {"default": True, "tooltip": "Write the passes as EXR (plate, element, light, glow, depth, normals, mask) for compositing."}),
            "track check": ("BOOLEAN", {"default": True, "tooltip": "Write a small video that shows the track on the clip (shown on EF Track)."}),
        }, "optional": {
            "save element": ("BOOLEAN", {"default": False, "advanced": True, "tooltip": "Also save the generated element (with alpha) in the element library under the run's name (AI elements on black)."}),
            "only check the track": ("BOOLEAN", {"default": False, "advanced": True, "tooltip": "Run only the track and its check video, no effect."}),
            "passes": ("STRING", {"default": "", "advanced": True, "tooltip": "Only these passes, e.g. plate, element, depth (empty = all). Names: " + ", ".join(PASS_NAMES)}),
            "then": (["new run", "make final from preview", "add passes to run"], {"default": "new run", "advanced": True,
                     "tooltip": "make final: the second, sharper LTX pass of a preview run (from run). add passes: write the passes named above into a finished run without generating again."}),
            "from run": ("STRING", {"default": "", "advanced": True, "tooltip": "The run to go on from (its folder name under output/element-forge/)."}),
        }, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("folder",)
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "Makes the run: the comp as MP4 (shown here), the passes as EXR and the track check in output/element-forge/<run>/."

    def run(self, layer, unique_id=None, **kw):
        from comfy_execution.graph_utils import GraphBuilder
        layer = _with(layer, "export", _export_opts(kw), unique_id)
        graph, run, shown = build_chain(layer, wants=())
        prefix = GraphBuilder.alloc_prefix()
        return {"result": (f"element-forge/{run}",), "expand": _expand_at_run(graph, prefix, unique_id, shown, layer.get("ids"))}


def _export_opts(kw):
    passes = [p.strip() for p in str(kw.get("passes", "") or "").split(",") if p.strip()]
    bad = [p for p in passes if p not in PASS_NAMES]
    if bad:
        raise ValueError(f"EF Export: unknown passes {', '.join(bad)} (names: {', '.join(PASS_NAMES)})")
    return {"run": str(kw.get("run name", "") or "").strip(), "exr": bool(kw.get("EXR passes", True)),
            "track check": bool(kw.get("track check", True)), "save element": bool(kw.get("save element", False)),
            "check only": bool(kw.get("only check the track", False)), "passes": passes, "then": kw.get("then", "new run"),
            "from": str(kw.get("from run", "") or "").strip()}


def _opt(spec, default, tip, adv=False):
    if isinstance(spec, list):
        return (spec, {"default": default, "tooltip": tip, **({"advanced": True} if adv else {})})
    t, extra = spec
    return (t, {"default": default, "tooltip": tip, **extra, **({"advanced": True} if adv else {})})


KEEP = -2.0
NUM = lambda lo, hi, st: ("FLOAT", {"min": lo, "max": hi, "step": st})


class EFForgeParticles:
    @classmethod
    def fields(cls):
        presets_ = [STYLE] + _choices("Particle preset", ["sparks"])
        emitters = [STYLE] + _choices("Particle emitter", ["point A"])
        return [
            ("particles", "Particles", [STYLE, "on", "off"], STYLE, "Particles in this effect (on their own, or to guide the AI).", False),
            ("preset", "Particle preset", presets_, STYLE, "What the particles do.", False),
            ("emitter", "Particle emitter", emitters, STYLE, "Where particles are born.", False),
            ("amount", "Particle amount", NUM(-2, 20, 0.05), KEEP, "Times the preset's amount. -2 = the style's.", False),
            ("speed", "Particle speed", NUM(-2, 20, 0.05), KEEP, "Times the preset's speed. -2 = the style's.", False),
            ("size", "Particle size", NUM(-2, 20, 0.05), KEEP, "Times the preset's size. -2 = the style's.", False),
            ("life", "Particle life", NUM(-2, 20, 0.05), KEEP, "Times the preset's life. -2 = the style's.", False),
            ("direction", "Particle direction (-1 = preset)", NUM(-2, 359, 1), KEEP, "Degrees (0 up). -1 = the preset's, -2 = the style's.", False),
            ("spread", "Particle spread (-1 = preset)", NUM(-2, 360, 1), KEEP, "Degrees. -1 = the preset's, -2 = the style's.", False),
            ("follow", "Particle follow (-1 = preset)", NUM(-2, 1, 0.01), KEEP, "How much they follow the track. -1 = the preset's, -2 = the style's.", False),
            ("seed", PARTICLE_SEED, ("INT", {"min": 0, "max": 2 ** 31 - 1}), 42, "Same seed, same simulation (apart from the AI seed).", False),
            ("pre-roll", PREROLL, NUM(-2, 60, 0.1), -2.0, "Seconds they run before the clip starts. -2 = the preset's, -1 = auto, 0 = none.", False),
            ("area", "Particle area", ("STRING", {}), "", "Emitter 'area': x0, y0, x1, y1 as shares of the frame. Empty = the style's.", True),
            ("premask", "Particle premask", [STYLE, "on", "off"], STYLE, "Hide particles behind the scene by depth.", True),
            ("edge fade", "Particle edge fade", NUM(-2, 1, 0.01), KEEP, "-2 = the style's.", True),
            ("tracks", "Particle tracks", ("INT", {"min": -2, "max": 256}), -2, "Number of motion tracks for the AI. -2 = the style's.", True),
            ("line hangs on", "Particle line hangs on (track / image / object)", [STYLE] + _choices("Particle line hangs on (track / image / object)", ["track"]), STYLE, "What a drawn emitter line moves with.", True),
            ("carried by motion", "Particles: carried by motion in the clip (0-1)", NUM(-2, 1, 0.05), KEEP, "-2 = the style's.", True),
            ("gravity", "Particle pro: gravity", NUM(-2, 20, 0.05), KEEP, "Times the preset's gravity. -2 = the style's.", True),
            ("turbulence", "Particle pro: turbulence", NUM(-2, 20, 0.05), KEEP, "-2 = the style's.", True),
            ("drag", "Particle pro: drag", NUM(-2, 20, 0.05), KEEP, "-2 = the style's.", True),
            ("collide", "Particle pro: collide", [STYLE] + _choices("Particle pro: collide", ["preset"]), STYLE, "What a particle does at a surface.", True),
            ("sprite", "Particle pro: sprite", [STYLE] + _choices("Particle pro: sprite", ["preset"]), STYLE, "Shape of a particle.", True),
            ("guide style", "Particle pro: guide style", [STYLE] + _choices("Particle pro: guide style", ["preset"]), STYLE, "How the particles guide the AI.", True),
            ("trail", "Particle pro: trail", ("INT", {"min": -2, "max": 60}), -2, "Frames of trail. -1 = the preset's, -2 = the style's.", True),
            ("color", "Particle pro: color", ("STRING", {}), "", "One colour as hex (#8a0a0a). Empty = the style's.", True),
            ("extra", "Particle pro: extra (JSON)", ("STRING", {"multiline": True}), "", "Any engine setting as JSON. Empty = the style's.", True),
            ("emitter panel", PARTICLE_EMITTER, ("STRING", {"multiline": True}), "", "The app's emitter panel as JSON (wins over all). Empty = none.", True),
            ("start video", "Particles: start video (seed)", [STYLE, "on", "off"], STYLE, "The particles start the AI's video (seed).", True),
            ("start sigmas", "Particle start sigmas (0.909 = tested default)", ("STRING", {}), "", "Empty = the style's.", True),
            ("direct look", "Particles: direct look (no LTX, pro)", [STYLE, "on", "off"], STYLE, "The particles as they are, no AI.", True),
            ("latent mask", "Particle latent mask (Inpaint, test)", [STYLE, "on", "off"], STYLE, "Inpaint: only where particles are.", True),
            ("also draw", "Particles: also draw (over the AI element)", [STYLE, "on", "off"], STYLE,
             "Draw the particles that guide the AI over its element as well (own pass 'particles'). Off = only the AI's element.", True),
        ]

    @classmethod
    def INPUT_TYPES(cls):
        req, opt = {}, {}
        for name, _, spec, default, tip, adv in cls.fields():
            (opt if adv else req)[name] = _opt(spec, default, tip, adv)
        return {"required": req, "optional": opt}

    RETURN_TYPES = ("EF_PARTICLES",)
    RETURN_NAMES = ("particles",)
    FUNCTION = "build"
    CATEGORY = OPTIONS
    DESCRIPTION = "Particle settings for EF Element. Every value starts at 'as the style has it' (style default, -2, empty)."

    def build(self, **kw):
        return (_settings_of(self.fields(), kw),)


def _settings_of(fields, kw):
    out = {}
    for name, setting, spec, default, _, _ in fields:
        v = kw.get(name, default)
        if v == STYLE or (isinstance(spec, tuple) and spec[0] == "STRING" and not str(v).strip()):
            continue
        if isinstance(spec, tuple) and spec[0] in ("FLOAT", "INT") and v == default and default in (KEEP, -2):
            continue
        if isinstance(spec, list) and v in ("on", "off") and "on" in spec:
            v = v == "on"
        if setting in (PARTICLE_EMITTER, "Particle pro: extra (JSON)"):
            _json(v, f"EF Options: {name}")
        out[setting] = v
    return out


class EFForgeGuide:
    @classmethod
    def fields(cls):
        gp = [STYLE] + _choices("Particle preset", ["magic dust"])
        return [
            ("guide", AI_GUIDE, [STYLE] + _choices(AI_GUIDE, GUIDE_CHOICES[1:]), STYLE, "What guides the AI: none, the object's shape, a drawn path or particles.", False),
            ("guide particles", "Particle preset", gp, STYLE, "The particles that guide the AI when the guide is particles.", False),
            ("strength", "Guide strength (on black)", NUM(-2, 5, 0.05), KEEP, "-2 = the style's.", False),
            ("reach", "Object shape: reach around the object", NUM(-2, 1, 0.01), KEEP, "Object shape: how far around the object it may go. -2 = the style's.", False),
            ("prompt addition", "Object shape: prompt addition (on black)", ("STRING", {"multiline": True}), "", "Object shape: words added to the prompt. Empty = the style's.", True),
            ("source", GUIDE_SOURCE, [STYLE] + _choices(GUIDE_SOURCE, ["draw"]), STYLE, "Drawn path: where the lines come from.", True),
            ("animation", "Guide animation", [STYLE] + _choices("Guide animation", ["still"]), STYLE, "Drawn path: still, grows or flickers.", True),
            ("grow", "Guide grow (s)", NUM(-2, 30, 0.01), KEEP, "grows: seconds until the line is complete. -2 = the style's.", True),
            ("trail", "Guide trail", NUM(-2, 1, 0.01), KEEP, "grows: only the newest part of the line. -2 = the style's.", True),
            ("repeat", "Guide repeat", [STYLE, "on", "off"], STYLE, "grows: start again (a steady stream).", True),
        ]

    @classmethod
    def INPUT_TYPES(cls):
        req, opt = {}, {"drawn path": ("MASK", {"tooltip": "The path to follow (first frame, painted = 1, e.g. Load Image in the mask editor)."})}
        for name, _, spec, default, tip, adv in cls.fields():
            (opt if adv else req)[name] = _opt(spec, default, tip, adv)
        return {"required": req, "optional": opt}

    RETURN_TYPES = ("EF_GUIDE",)
    RETURN_NAMES = ("guide",)
    FUNCTION = "build"
    CATEGORY = OPTIONS
    DESCRIPTION = "What guides the AI element (as Advanced in the app): none, object shape, a drawn path or particles."

    def build(self, **kw):
        s = _settings_of(self.fields(), kw)
        if s.get(AI_GUIDE) != "particles":
            s.pop("Particle preset", None)
        drawn = kw.get("drawn path")
        return ({"settings": s, "drawn": drawn},)


class EFForgeDissolve:
    @classmethod
    def fields(cls):
        return [
            ("amount", "Dissolve amount", NUM(-2, 1, 0.01), KEEP, "How much of the object goes. -2 = the style's.", False),
            ("glowing edge", "Dissolve glowing edge", NUM(-2, 5, 0.05), KEEP, "-2 = the style's.", False),
            ("style", "Dissolve style (plain / fire (LTX) / gold dust)", [STYLE, "plain", "fire (LTX)", "gold dust", "explodes"], STYLE, "How it goes (explodes: it bursts from the centre at the start).", False),
            ("clean plate where never free", "Dissolve: clean plate (LTX) where never free", [STYLE, "on", "off"], STYLE, "LTX paints what was always hidden behind the object.", True),
            ("sharper clean plate", "Dissolve: clean plate sharper (crop around the object, test)", [STYLE, "on", "off"], STYLE, "", True),
            ("ember prompt", "Dissolve: ember prompt", ("STRING", {"multiline": True}), "", "fire: the embers' words. Empty = the style's.", True),
            ("ember strength", "Dissolve: ember strength", NUM(-2, 5, 0.05), KEEP, "-2 = the style's.", True),
            ("embers away from the edge", "Dissolve: embers away from the edge", NUM(-2, 1, 0.01), KEEP, "-2 = the style's.", True),
            ("empty scene prompt", "Dissolve: empty scene prompt", ("STRING", {"multiline": True}), "", "The clean plate's words. Empty = the style's.", True),
            ("carried by motion", "Dissolve: carried by motion in the clip (0-1)", NUM(-2, 1, 0.05), KEEP, "-2 = the style's.", True),
            ("extra", DISSOLVE_EXTRA, ("STRING", {"multiline": True}), "", "The emitter panel's values as JSON. Empty = none.", True),
            ("background", "Dissolve: background behind the object (auto / smooth / structured)", [STYLE, "auto", "smooth", "structured"],
             STYLE, "auto: measured around the object. smooth: filled from around the hole, no LTX. structured: the clean plate (if on).", True),
        ]

    @classmethod
    def INPUT_TYPES(cls):
        req, opt = {}, {}
        for name, _, spec, default, tip, adv in cls.fields():
            (opt if adv else req)[name] = _opt(spec, default, tip, adv)
        return {"required": req, "optional": opt}

    RETURN_TYPES = ("EF_DISSOLVE",)
    RETURN_NAMES = ("dissolve",)
    FUNCTION = "build"
    CATEGORY = OPTIONS
    DESCRIPTION = "Dissolve settings for EF Element (dissolve styles). Every value starts at 'as the style has it'."

    def build(self, **kw):
        return (_settings_of(self.fields(), kw),)


class EFForgeLTX:
    @classmethod
    def fields(cls):
        return [
            ("sharper x2", UPSCALE, [STYLE, "on", "off"], STYLE, "LTX latent upscaler x2 and a second pass (test).", False),
            ("NVIDIA SR + HDR", "NVIDIA SR + HDR", [STYLE, "on", "off"], STYLE, "NVIDIA Video Super Resolution and TrueHDR on the element (RTX, needs the NVIDIA VFX pack).", False),
            ("more room", "On black: more room", NUM(-2, 2, 0.05), KEEP, "On black: a larger area around the element. -2 = the style's.", False),
            ("black margin", "On black: black margin (test)", NUM(-2, 1, 0.01), KEEP, "-2 = the style's.", True),
            ("inpaint sigmas", INPAINT_SIGMAS, ("STRING", {}), "", "Inpaint: the sigmas from where LTX repaints. Empty = the style's (or 'keep original' of EF Element).", True),
            ("inpaint starts from the element", "Inpaint: start from the element", [STYLE, "on", "off"], STYLE, "Inpaint: LTX starts from the element made on black.", True),
        ]

    @classmethod
    def INPUT_TYPES(cls):
        req, opt = {}, {}
        for name, _, spec, default, tip, adv in cls.fields():
            (opt if adv else req)[name] = _opt(spec, default, tip, adv)
        return {"required": req, "optional": opt}

    RETURN_TYPES = ("EF_LTX",)
    RETURN_NAMES = ("ltx",)
    FUNCTION = "build"
    CATEGORY = OPTIONS
    DESCRIPTION = "LTX settings for EF Element: sharper pass, NVIDIA, room around the element, inpaint start."

    def build(self, **kw):
        return (_settings_of(self.fields(), kw),)


class EFForgeLibraryElement:
    @classmethod
    def INPUT_TYPES(cls):
        from ..generation.elements import _elements
        names = _elements()
        return {"required": {"element": (names or ["(no saved elements yet)"], {"tooltip": "An element saved before (EF Export 'save element', the app's 'Save the element')."})}}

    RETURN_TYPES = ("EF_OWN_ELEMENT",)
    RETURN_NAMES = ("element",)
    FUNCTION = "build"
    CATEGORY = TOOLS
    DESCRIPTION = "An element from the library, for EF Place instead of the generated one."

    @classmethod
    def VALIDATE_INPUTS(cls, element):
        return True

    def build(self, element):
        if element.startswith("("):
            raise ValueError("EF Library Element: no saved element yet")
        return ({"name": element},)


class EFForgeFromImages:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE", {"tooltip": "The element's frames (straight colour, sRGB), from any node."}),
            "fps": ("FLOAT", {"default": 30.0, "min": 1.0, "max": 240.0, "step": 0.001}),
        }, "optional": {
            "alpha": ("MASK", {"tooltip": "Its alpha per frame (1 = solid; Load Image's mask is the other way round: Invert Mask). "
                                          "Without: the frames' own alpha, else their brightness (glowing things on black)."}),
        }}

    RETURN_TYPES = ("EF_OWN_ELEMENT",)
    RETURN_NAMES = ("element",)
    FUNCTION = "build"
    CATEGORY = TOOLS
    DESCRIPTION = "An element of your own (e.g. from another generator) for EF Place: saved once into the element library, then placed like a generated one."

    def build(self, images, fps, alpha=None):
        import torch
        from ..generation.elements import EFSaveElement, _elements, _split
        if alpha is not None:
            a = alpha if alpha.dim() == 3 else alpha.unsqueeze(0)
            n = min(images.shape[0], a.shape[0]) if a.shape[0] > 1 else images.shape[0]
            a = a[:n] if a.shape[0] > 1 else a.expand(n, -1, -1)
            if a.shape[1:] != images.shape[1:3]:
                a = torch.nn.functional.interpolate(a.unsqueeze(1), size=images.shape[1:3], mode="bilinear").squeeze(1)
            rgb = images[:n, ..., :3]
        else:
            rgb, a = _split(images, None)
        rgba = torch.cat([rgb, a.unsqueeze(-1)], -1).clamp(0, 1)
        name = "own-" + hashlib.sha1(rgba.cpu().numpy().tobytes() + str(float(fps)).encode()).hexdigest()[:12]
        if name not in _elements():
            EFSaveElement().save(rgba=rgba, name=name, fps=float(fps), overwrite=False)
        return ({"name": name},)


class EFForgeUnpack:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"from": ("EF_SHOT,EF_ELEMENT,EF_LAYER", {"tooltip": "Any Element Forge wire."})},
                "hidden": {"unique_id": "UNIQUE_ID", "prompt": "PROMPT"}}

    RETURN_TYPES = tuple(t for _, t in UNPACK)
    RETURN_NAMES = tuple(n for n, _ in UNPACK)
    FUNCTION = "run"
    CATEGORY = TOOLS
    DESCRIPTION = ("The parts of a run as ordinary outputs for other nodes: plate (sRGB), depth, normals and object mask from EF Shot "
                   "and EF Track, the element (linear, on black) with its alpha, light, glow and the comp from EF Element on. Only "
                   "what is connected is computed.")

    def run(self, unique_id=None, prompt=None, **kw):
        from comfy_execution.graph_utils import GraphBuilder
        used = _readers(prompt, str(unique_id)) if isinstance(prompt, dict) else range(len(UNPACK))
        wants = tuple(UNPACK[i][0] for i in used)
        graph, run, shown = build_chain(kw["from"], wants=wants)
        prefix = GraphBuilder.alloc_prefix()
        links = graph.pop("_wants")
        missing = [n for n in wants if not links.get(n)]
        if missing:
            raise ValueError(f"EF Unpack: {', '.join(missing)} needs a later stage (EF Element for the element, light and comp; "
                             "EF Track for the object mask)")
        return {"result": tuple([prefix + links[n][0], links[n][1]] if links.get(n) else None for n, _ in UNPACK),
                "expand": _expand_at_run(graph, prefix, unique_id, shown, kw["from"].get("ids"))}


def chain_values(b):
    p = presets()
    sh, tr, el = b["shot"], b.get("track") or {}, b.get("element")
    pl, lg = b.get("place") or {}, b.get("light") or {}
    clip = sh["clip"]
    if el is None:
        el = {"kind": "fire", "style": "flame", "how": STYLE, "strength": "normal", "text": {}, "prompt": "", "scene": "",
              "dir": None, "start": 0.0, "end": None, "box": None, "soft edge": STYLE, "solid": STYLE, "keep": 0.0,
              "quality": "full", "seed": 0, "options": {}}
    kind, style = el["kind"], el["style"]
    st = cv.style_def(p, kind, style)
    ks = f"{kind}/{style}"
    opts = el.get("options") or {}
    adv, paint = {}, {}
    if el["how"] != STYLE:
        adv[cv.INPAINT] = el["how"] == "inpaint"
    for key, setting in (("soft edge", "On black: round soft edge"), ("solid", "Solid element (Alpha Gen cut-out)")):
        if el.get(key, STYLE) != STYLE:
            adv[setting] = el[key] == "on"
    for part in ("particles", "dissolve", "ltx"):
        adv.update(opts.get(part) or {})
    g = opts.get("guide") or {}
    gs = dict(g.get("settings") or {})
    guide = gs.pop(AI_GUIDE, None)
    adv.update({k: v for k, v in gs.items() if k != "Particle preset"})
    drawn = g.get("drawn")
    guide = guide or ("drawn path" if drawn is not None else None)
    if guide:
        adv[AI_GUIDE] = guide
    if guide == "drawn path" or drawn is not None:
        adv[GUIDE_SOURCE] = "draw"
    if guide == "particles" and not (st.get("settings") or {}).get("Particles"):
        adv["Particles"] = True
        adv["Particle preset"] = gs.get("Particle preset") or _guide_particles().get(ks, "magic dust")
    if drawn is not None:
        paint[GUIDE_FILE] = drawn.name if isinstance(drawn, _File) else _paint_file(drawn, (clip["width"], clip["height"]), "guide")
    if pl.get("size", -1) >= 0:
        adv["Size in plate"] = pl["size"]
    if pl.get("side", STYLE) != STYLE:
        adv["Emitter side"] = pl["side"]
    if pl.get("blend", STYLE) != STYLE:
        adv["Blend on black (add = light, over = solid)"] = pl["blend"]
    if pl.get("front"):
        adv[FRONT] = True
    if pl.get("lock"):
        adv[LOCK] = True
    if pl.get("key", STYLE) != STYLE:
        adv["Inpaint key"] = pl["key"]
    if pl.get("inpaint blend", STYLE) != STYLE:
        adv["Inpaint blend"] = pl["inpaint blend"]
    if pl.get("groups") is not None:
        adv["Groups"] = pl["groups"]
    if pl.get("library"):
        adv["Element from library"] = True
        adv["Library element"] = pl["library"]
    if lg.get("groups in depth"):
        adv["Groups in depth"] = True
    if tr:
        adv[FOLLOWS] = bool(tr.get("motion")) and not _particle_style(kind, style)
        if adv[FOLLOWS]:
            adv["Follows motion: strength"] = tr.get("motion strength", 1.0)
            adv["Follows motion: lag"] = tr.get("motion lag", 0.6)
    effect = {"kind": kind, "style": style, "where": tr.get("where") or {"a": None, "b": None, "word": ""},
              "box": el.get("box"), "dir": el.get("dir"), "depth": pl.get("depth", 0.0), "strength": el["strength"],
              "text": el.get("text") or {}, "prompt": el["prompt"] if str(el.get("prompt") or "").strip() else None,
              "timing": {"start": el["start"], "end": el.get("end")}, "seed": el["seed"], "adv": adv}
    mode = el.get("quality") or "full"
    can_preview = st.get("cost") == "gen" and st.get("variant") == "app" and not cv.in_scene(st, effect)
    if mode == "preview" and not can_preview:
        raise ValueError("EF Element: preview works for AI styles on black only; set quality to full")
    v = cv.values_for(p, effect, {"clip": clip, "night": sh.get("night"), "scene": el.get("scene") or ""},
                      0.5 if mode == "preview" else 1.0)
    v[PARTICLE_SEED] = int((opts.get("particles") or {}).get(PARTICLE_SEED, 42))
    v[PREROLL] = float((opts.get("particles") or {}).get(PREROLL, -2.0))
    word = str((tr.get("where") or {}).get("word") or "").strip()
    if word:
        v["Object word (optional, helps the click)"] = word
    fol = FOLLOWS_VALUES.get(tr.get("follows", STYLE))
    if fol and st.get("placement") != "frame":
        v[STICKS_SCENE], v[TRACK_MASK], v[STILL] = fol
    v[OWN_MASK] = bool(tr.get("own mask"))
    if tr.get("own mask"):
        paint[OWN_MASK_FILE] = tr["own mask"]
    v[ALL_ALIKE] = bool(tr.get("alike"))
    v[UPSCALE] = bool((opts.get("ltx") or {}).get(UPSCALE, False))
    if el.get("keep", 0) > 0 and INPAINT_SIGMAS not in ((opts.get("ltx") or {})):
        k = min(1.0, max(0.0, el["keep"]))
        start = round(0.909375 - k * (0.909375 - 0.725), 6)
        v[INPAINT_SIGMAS] = "0.725, 0.421875, 0.0" if start <= 0.725 else f"{start:g}, 0.725, 0.421875, 0.0"
    v.update(paint)
    for k, name in (("light", "Light"), ("glow", "Glow")):
        if lg.get(k, STYLE) != STYLE:
            v[name] = lg[k] == "on"
    if v.get(GUIDE_SOURCE) == "draw" and GUIDE_FILE not in v and v.get(AI_GUIDE) == "drawn path":
        raise ValueError("EF Guide: the drawn path is missing; connect 'drawn path' (a painted mask)")
    if v.get("Element from library") and not str(v.get("Library element") or "").strip():
        raise ValueError("EF Place: pick a saved element (EF Library Element) or take the generated one")
    models = dict(b.get("models") or {})
    models.pop("id", None)
    if sh.get("depth"):
        models["depth"] = sh["depth"]
    look = {"light_strength": lg.get("light strength", 1.0) * _light_gain(kind, style), "glow_exposure": lg.get("glow exposure", 0.0),
            "albedo_exposure": _light_albedo_exposure(kind, style, sh.get("night")), "light_color": _light_color(kind, style)}
    return st.get("variant") or "app", mode, v, models or None, look


def _guide_particles():
    return {f"{e['id']}/{s['id']}": s["guide_particles"] for e in presets().get("effects", []) for s in e.get("styles", [])
            if s.get("guide_particles")}


def _is_output(cls):
    import nodes
    return getattr(nodes.NODE_CLASS_MAPPINGS.get(cls), "OUTPUT_NODE", False) is True


PLACED_ALPHA = {"EFPlaceElement": (1, 2), "EFPlaceBetween": (1, 2), "EFPlaceLayer": (1, 2), "EFParticles": (15, 7)}


def _alpha_of(g, ref):
    k, idx = ref
    nd = g.get(k) or {}
    if nd.get("class_type") == "ComfySwitchNode":
        key = f"unpack_alpha_{k}"
        if key not in g:
            ins = dict(nd["inputs"])
            for side in ("on_false", "on_true"):
                if _is_link(ins.get(side)):
                    ins[side] = list(_alpha_of(g, ins[side]) or ins[side])
            g[key] = {"class_type": "ComfySwitchNode", "inputs": ins}
        return key, 0
    out = PLACED_ALPHA.get(nd.get("class_type"))
    return (k, out[1]) if out and out[0] == idx else None


def build_chain(b, wants=(), dry=False):
    from ..app import app_routes as ar
    ex = b.get("export")
    variant, mode, values, ltx, look = chain_values(b)
    if ex and ex.get("check only"):
        variant, mode, values = "check", "full", {**values, CHECK_ONLY: True}
    action = (ex or {}).get("then", "new run")
    run = (ex or {}).get("run") or cv.run_id(variant, mode, values, look)
    if not ar.RUN_NAME.match(run):
        raise ValueError("EF Export: run names use letters, digits, . _ - only")
    body = {"variant": variant, "values": values, "run": run, "mode": mode, "save_element": bool((ex or {}).get("save element"))}
    if action != "new run":
        if not (ex or {}).get("from"):
            raise ValueError("EF Export: name the run to go on from ('from run')")
        body.update({"mode": "final" if action == "make final from preview" else "add", "from_run": ex["from"],
                     "passes": ex.get("passes") or []})
    out_dir = folder_paths.get_output_directory()
    variant, values, run, edit, recipe, _ = ar.app_job(body, out_dir)
    keep_saves = bool(ex)
    passes = set((ex or {}).get("passes") or PASS_NAMES)
    settings = ar._load_json("element_forge.settings.json")["settings"]

    el = b.get("element") or {}
    preview = (keep_saves and el.get("preview", True) and variant not in ("dissolve", "check") and action == "new run")
    marks = {}

    def edit_all(g):
        edit(g)
        cv.tune_look(g, look)
        if variant == "check":
            ar.keep_track(g, settings)
        if preview and ELEMENT_RGBA in g:
            shown_el = [ELEMENT_SHOWN if ELEMENT_SHOWN in g else ELEMENT_RGBA, 0]
            top = g.get(SOURCES["element"][0]) or {}
            drawn = top.get("inputs", {}).get("on_true")
            if top.get("class_type") == "ComfySwitchNode" and _is_link(drawn) and g.get(drawn[0], {}).get("class_type") == "EFParticles":
                g["el_preview_element"] = {"class_type": "ComfySwitchNode", "inputs": {
                    "switch": top["inputs"]["switch"], "on_false": shown_el, "on_true": list(drawn)}}
                shown_el = ["el_preview_element", 0]
            g["el_preview"] = {"class_type": "EFCompPreview", "inputs": {"element": shown_el, "mode": "over", "largest side": 960},
                               "_meta": {"title": "Element on a checkerboard"}}
            g["el_preview_dither"] = {"class_type": "EFDither", "inputs": {"images": ["el_preview", 0], "amount": 1.5, "seed": 0}}
            g["el_preview_video"] = {"class_type": "CreateVideo", "inputs": {"images": ["el_preview_dither", 0], "fps": ["167", 2]}}
            like = g.get(ar.VIDEO_SAVES[0]) or g.get(ar.VIDEO_SAVES[1]) or {"inputs": {"format": "mp4", "codec": "h264"}}
            g["el_preview_save"] = {"class_type": "SaveVideo", "inputs": {
                **like["inputs"], "video": ["el_preview_video", 0], "filename_prefix": f"element-forge/{run}/element_preview"},
                "_meta": {"title": "Element preview"}}
        for name in wants:
            src = (DISSOLVE_SOURCES if variant == "dissolve" else {}).get(name) or SOURCES.get(name)
            if name == "element alpha" and variant != "dissolve" and SOURCES["element"][0] in g:
                src = _alpha_of(g, SOURCES["element"])
            need = NEEDS.get(name)
            if src and src[0] in g and (need != "element" or b.get("element")) and (need != "track" or b.get("track")):
                marks[name] = f"unpack_mark_{len(marks)}"
                g[marks[name]] = {"class_type": "PreviewAny", "inputs": {"source": list(src)}}
        if not keep_saves:
            return
        if not ex.get("exr") or action == "add passes to run":
            drop = set(ar.PASS_SAVES) if not ex.get("exr") else set()
        else:
            drop = set(ar.PASS_SAVES) - passes
        for name in drop:
            g.pop(ar.PASS_SAVES[name], None)
            g.pop(ar.DISSOLVE_LIGHT_SAVES.get(name, ""), None)
        if not ex.get("track check"):
            g.pop(ar.VIDEO_SAVES[1], None)
    graph = ar.build_graph(variant, values, run, ltx, edit_all)
    shown = {}
    roots = []
    if keep_saves:
        roots += [k for k, nd in graph.items() if _is_output(nd["class_type"]) and not k.startswith("unpack_mark_")]
        shown[ar.VIDEO_SAVES[0]] = "export"
        shown[ar.VIDEO_SAVES[1]] = "track"
        if "el_preview_save" in graph:
            rest = ar.upstream(graph, [k for k in roots if k != "el_preview_save"])
            own = {"el_preview", "el_preview_video", "el_preview_save", "el_preview_element", "el_preview_dither"}
            if set(ar.upstream(graph, ["el_preview_save"])) - set(rest) - own:
                for k in own:
                    graph.pop(k, None)
                roots.remove("el_preview_save")
            else:
                shown["el_preview_save"] = "element"
    links = {name: None for name in wants}
    for name, mk in marks.items():
        if mk in graph:
            links[name] = list(graph.pop(mk)["inputs"]["source"])
            roots.append(links[name][0])
    graph = ar.upstream(graph, roots)
    if keep_saves and action == "new run" and variant != "check" and not dry:
        folder = ar._inside(out_dir, f"element-forge/{run}")
        os.makedirs(folder, exist_ok=True)
        rec = {"variant": variant, **recipe(), "recipe": None, "source": "EF Export", "time": time.time(),
               **({"models": ltx} if ltx else {}), "model_files": ar.model_files(graph)}
        with open(os.path.join(folder, "app_recipe.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
    graph["_wants"] = links
    return graph, run, shown


ORDER = {"models": ["models", "element"], "shot": ["shot", "track", "element"], "track": ["track", "shot", "element"],
         "element": ["element", "place", "light", "export", "track", "shot"], "place": ["place", "element", "light", "export"],
         "light": ["light", "place", "export", "element"], "export": ["export", "light", "place", "element", "track", "shot"]}


def _owner(b, k, shown):
    ids = b.get("ids") or {}
    stage = shown.get(k) or stage_map().get(k, "element")
    for s in ORDER.get(stage, ["element"]) + list(STAGES):
        if ids.get(s):
            return ids[s]
    return None


def _expand_at_run(graph, prefix, unique_id, shown, ids=None):
    graph.pop("_wants", None)
    out = {}
    for k, nd in graph.items():
        ins = {a: [prefix + v[0], v[1]] if _is_link(v) else v for a, v in nd["inputs"].items()}
        node = {"class_type": nd["class_type"], "inputs": ins}
        stage = shown.get(k)
        if stage != "export":
            node["override_display_id"] = (ids or {}).get(stage) or f"{unique_id}.hidden"
        out[prefix + k] = node
    return out


PRIMITIVES = {"PrimitiveInt", "PrimitiveFloat", "PrimitiveString", "PrimitiveStringMultiline", "PrimitiveBoolean"}
STAGE_CLASSES = {}
SINKS = ("EFForgeExport", "EFForgeUnpack")


class _NotHere(Exception):
    pass


def _is_link(v):
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def _value(prompt, v, seen, want=None):
    if not _is_link(v):
        return v
    nd = prompt.get(v[0]) or {}
    cls, ins = nd.get("class_type"), nd.get("inputs", {})
    if cls in PRIMITIVES and not _is_link(ins.get("value")):
        return ins["value"]
    if cls == "LoadVideo" and isinstance(ins.get("file"), str):
        path = folder_paths.get_annotated_filepath(ins["file"])
        if not os.path.isfile(path):
            raise _NotHere()
        return _FileVideo(path)
    if cls == "LoadImage" and isinstance(ins.get("image"), str) and want in ("picture", "mask"):
        if want == "picture" and v[1] != 0 or want == "mask" and v[1] != 1:
            raise _NotHere()
        name = ins["image"]
        if not os.path.isfile(folder_paths.get_annotated_filepath(name)):
            raise _NotHere()
        return _File(name)
    if cls in STAGE_CLASSES and v[1] == 0 and cls not in SINKS:
        if v[0] in seen:
            raise _NotHere()
        k = STAGE_CLASSES[cls]
        args = {}
        for a, x in ins.items():
            kind = "picture" if a == "picture" else "mask" if a in ("own mask", "drawn path") else None
            args[a] = _value(prompt, x, seen | {v[0]}, kind)
        fn = getattr(k(), k.FUNCTION)
        return fn(unique_id=v[0], **args)[0] if "unique_id" in (k.INPUT_TYPES().get("hidden") or {}) else fn(**args)[0]
    raise _NotHere()


def _readers(prompt, sid):
    return sorted({v[1] for n in prompt.values() for v in n.get("inputs", {}).values() if _is_link(v) and v[0] == sid})


def _chain_of(prompt, sid, dry):
    nd = prompt[sid]
    ins = nd.get("inputs", {})
    if nd["class_type"] == "EFForgeExport":
        b = _value(prompt, ins.get("layer"), {sid})
        b = _with(b, "export", _export_opts({a: _value(prompt, x, {sid}) for a, x in ins.items() if a != "layer"}), sid)
        wants = ()
    else:
        b = _value(prompt, ins.get("from"), {sid})
        wants = tuple(UNPACK[i][0] for i in _readers(prompt, sid))
    graph, run, shown = build_chain(b, wants, dry=dry)
    links = graph.pop("_wants")
    missing = [n for n in wants if links.get(n) is None]
    if missing:
        raise _NotHere(f"{', '.join(missing)} needs a later stage")
    return b, graph, run, shown, links


def queue_expand(prompt, dry=False):
    notes, chains = [], {}
    sinks = [k for k, nd in prompt.items() if nd.get("class_type") in SINKS]
    for sid in sinks:
        try:
            chains[sid] = _chain_of(prompt, sid, dry)
        except _NotHere as e:
            notes.append(f"{sid}: expanded when it runs ({str(e) or 'not all values are known before the run'})")
        except Exception as e:
            notes.append(f"{sid}: stays as it is ({e})")
    needed, todo = set(), [k for k in sinks if k not in chains]
    while todo:
        k = todo.pop()
        if k in needed or k not in prompt:
            continue
        needed.add(k)
        todo += [v[0] for v in prompt[k].get("inputs", {}).values() if _is_link(v)]
    stage_ids = {k for k, n in prompt.items() if n.get("class_type") in STAGE_CLASSES}
    put, renames, outputs = {}, {}, {}
    names = [u for u, _ in UNPACK]
    for sid, (b, graph, run, shown, links) in chains.items():
        ids = b.get("ids") or {}

        def name(k, b=b, shown=shown, ids=ids, sid=sid):
            st = shown.get(k)
            if st and ids.get(st) and ids[st] not in needed:
                return ids[st]
            return f"{_owner(b, k, shown) or sid}.{k}"
        added = {}
        for k, g in graph.items():
            added[name(k)] = {"class_type": g["class_type"],
                              "inputs": {a: [name(v[0]), v[1]] if _is_link(v) else v for a, v in g["inputs"].items()},
                              "_meta": {"title": f"{_stage_title(k, shown)} · {g.get('_meta', {}).get('title', g['class_type'])}"}}
        clash = {nk for nk, node in added.items()
                 if (nk in put and put[nk] != node) or (nk in prompt and nk not in stage_ids and nk not in put)}
        fix = {nk: f"{nk}#{sid}" for nk in clash}
        if fix:
            added = {fix.get(nk, nk): {**node, "inputs": {a: [fix.get(v[0], v[0]), v[1]] if _is_link(v) else v
                                                          for a, v in node["inputs"].items()}} for nk, node in added.items()}
        for n, l in links.items():
            if l:
                nk = name(l[0])
                renames[(sid, names.index(n))] = [fix.get(nk, nk), l[1]]
        put.update(added)
        outputs[sid] = [nk for nk, node in added.items() if _is_output(node["class_type"])]
        notes.append(f"{sid}: {len(added)} nodes of the app's graph, run element-forge/{run}")
    for sid in chains:
        prompt.pop(sid, None)
    for k in [k for k in put if k in prompt]:
        prompt.pop(k)
    prompt.update(put)
    for n in prompt.values():
        for a, v in list(n.get("inputs", {}).items()):
            if _is_link(v) and (v[0], v[1]) in renames:
                n["inputs"][a] = renames[(v[0], v[1])]
    while True:
        read = {v[0] for n in prompt.values() for v in n.get("inputs", {}).values() if _is_link(v)}
        gone = [k for k in prompt if k in stage_ids and k not in put and k not in read
                and prompt[k].get("class_type") not in SINKS]
        if not gone:
            break
        for k in gone:
            del prompt[k]
    return notes, outputs


TITLES = {"models": "EF Models", "shot": "EF Shot", "track": "EF Track", "element": "EF Element", "place": "EF Place",
          "light": "EF Light & Glow", "export": "EF Export"}


def _stage_title(k, shown):
    return TITLES.get(shown.get(k) or stage_map().get(k, "element"), "Element Forge")


def on_prompt(json_data):
    try:
        prompt = json_data.get("prompt") if isinstance(json_data, dict) else None
        if isinstance(prompt, dict) and any(isinstance(n, dict) and n.get("class_type") in SINKS for n in prompt.values()):
            new = copy.deepcopy(prompt)
            notes, outputs = queue_expand(new)
            json_data["prompt"] = new
            targets = json_data.get("partial_execution_targets")
            if isinstance(targets, list):
                json_data["partial_execution_targets"] = list(dict.fromkeys(
                    [t for t in targets if t in new and t not in outputs] + [o for t in targets for o in outputs.get(t, [])]))
            logging.info("[Element Forge] %s", "; ".join(notes))
    except Exception:
        logging.warning("[Element Forge] the stage nodes stay as they are (expanded when they run)", exc_info=True)
    return json_data


def register_routes(routes):
    from aiohttp import web

    @routes.post("/element-forge/api/stages/expand")
    async def ef_stages_expand(request):
        body = await request.json()
        prompt = copy.deepcopy(body.get("prompt") or {})
        notes, outputs = queue_expand(prompt, dry=True)
        return web.json_response({"prompt": prompt, "notes": notes, "outputs": outputs})

    @routes.get("/element-forge/api/stages/fields")
    async def ef_stages_fields(request):
        k = NODE_CLASS_MAPPINGS.get(request.query.get("cls", ""))
        if not hasattr(k, "fields"):
            raise web.HTTPNotFound(text="no such options node")
        return web.json_response({setting: name for name, setting, *_ in k.fields()})


NODE_CLASS_MAPPINGS = {
    "EFForgeModels": EFForgeModels, "EFForgeShot": EFForgeShot, "EFForgeTrack": EFForgeTrack, "EFForgeElement": EFForgeElement,
    "EFForgePlace": EFForgePlace, "EFForgeLight": EFForgeLight, "EFForgeExport": EFForgeExport,
    "EFForgeParticles": EFForgeParticles, "EFForgeGuide": EFForgeGuide, "EFForgeDissolve": EFForgeDissolve, "EFForgeLTX": EFForgeLTX,
    "EFForgeLibraryElement": EFForgeLibraryElement, "EFForgeFromImages": EFForgeFromImages, "EFForgeUnpack": EFForgeUnpack,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "EFForgeModels": "EF Models", "EFForgeShot": "EF Shot", "EFForgeTrack": "EF Track", "EFForgeElement": "EF Element",
    "EFForgePlace": "EF Place", "EFForgeLight": "EF Light & Glow", "EFForgeExport": "EF Export",
    "EFForgeParticles": "EF Particles", "EFForgeGuide": "EF Guide", "EFForgeDissolve": "EF Dissolve", "EFForgeLTX": "EF LTX Options",
    "EFForgeLibraryElement": "EF Library Element", "EFForgeFromImages": "EF Element from Images", "EFForgeUnpack": "EF Unpack",
}
STAGE_CLASSES.update(NODE_CLASS_MAPPINGS)

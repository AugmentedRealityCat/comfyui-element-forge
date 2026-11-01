
import hashlib
import json
import os

CATEGORY = "Element Forge/App"

SEED = "Seed"
NIGHT = "Night"
OBJECT_WORD = "Object word (optional, helps the click)"
STICKS_SCENE = "Sticks to scene (off = object)"
TRACK_MASK = "Track follows the object mask (hands, bodies)"
STILL = "Fixed on screen (Follows: Screen)"
OWN_MASK = "Own object mask (off = click)"
ALL_ALIKE = "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)"
OBJECT_IN_FRONT = "Object in front (its mask hides the element)"
LOCK_BASE = "Base locked to the point (no jitter of the base)"
DIRECT_LOOK = "Particles: direct look (no LTX, pro)"
FOLLOWS = "Follows motion"
GUIDE_SOURCE = "Guide source"
UPSCALE = "LTX upscale x2 (latent upscaler + second pass, test)"
PARTICLE_SEED = "Particle seed"
PREROLL = "Particle pre-roll (s, -2 = as in the preset, -1 = auto)"
PARTICLE_EMITTER = "Particle emitter (app, JSON)"
DISSOLVE_EXTRA = "Dissolve extra (JSON)"
AI_GUIDE = "Guide for the AI (particles / drawn path / object shape / none)"
GUIDE_CHOICES = ["style default", "none", "object shape", "drawn path", "particles"]
GUIDE_PRESETS = ["fire", "embers", "sparks", "grinding sparks", "smoke", "dust burst", "magic dust", "aura", "liquid", "debris",
                 "snow", "rain", "fireflies", "lightning", "cracks", "frost", "lightning climb", "energy A-B"]

_FALLBACK_STYLES = [
    "fire/flame", "fire/burst", "lightning/between", "lightning/climb", "lightning/climb_arcs",
    "lightning/climb_drawn", "sparks/grind", "sparks/burst", "smoke/rise", "smoke/rise_drawn",
    "magic/aura", "magic/aura_drawn", "magic/flow", "magic/orb", "weather/snow", "weather/rain",
    "weather/fireflies", "debris/debris", "debris/debris_drawn", "debris/dust", "liquid/drip",
    "dissolve/plain", "dissolve/gold", "dissolve/fire", "own/point",
]


def _preset_candidates():
    here = os.path.dirname(os.path.abspath(__file__))
    real = os.path.dirname(os.path.realpath(__file__))
    return [os.path.join(base, "..", "app", "app_presets.json") for base in (here, real)]


def load_effect_styles():
    for path in _preset_candidates():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            styles = [f"{e['id']}/{s['id']}" for e in data.get("effects", []) for s in e.get("styles", [])]
            places = {f"{e['id']}/{s['id']}": s.get("placement") for e in data.get("effects", []) for s in e.get("styles", [])}
            if styles:
                return styles, os.path.normpath(path), places
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return list(_FALLBACK_STYLES), "fallback", {"weather/snow": "frame", "weather/rain": "frame", "weather/fireflies": "frame"}


EFFECT_STYLES, EFFECT_STYLES_SOURCE, PLACEMENTS = load_effect_styles()


def load_particle_styles():
    for path in _preset_candidates():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {f"{e['id']}/{s['id']}" for e in data.get("effects", []) for s in e.get("styles", [])
                    if (s.get("settings") or {}).get("Particles") or s.get("variant") == "climb"}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return set()


PARTICLE_STYLES = load_particle_styles()


def load_guide_particles():
    for path in _preset_candidates():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {f"{e['id']}/{s['id']}": s["guide_particles"] for e in data.get("effects", []) for s in e.get("styles", [])
                    if s.get("guide_particles")}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {}


GUIDE_PARTICLES = load_guide_particles()


def load_style_settings():
    for path in _preset_candidates():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {f"{e['id']}/{s['id']}": dict(s.get("settings") or {}) for e in data.get("effects", []) for s in e.get("styles", [])}
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return {}


STYLE_SETTINGS = load_style_settings()


def start_preset(style):
    return STYLE_SETTINGS.get(style, {}).get("Particle preset") or GUIDE_PARTICLES.get(style) or "magic dust"

FOLLOWS_VALUES = {"point": (False, False, False), "object": (False, True, False), "mask": (False, True, False),
                  "scene": (True, False, False), "screen": (False, False, True)}


class AnyType(str):

    def __ne__(self, other):
        return False


ANY = AnyType("*")


def _parse_shot(shot):
    if isinstance(shot, dict):
        return shot
    try:
        data = json.loads(shot or "{}")
    except (TypeError, ValueError) as err:
        raise ValueError(f"Element Forge · Canvas: the state (shot) is not valid JSON: {err}") from err
    if not isinstance(data, dict):
        raise ValueError("Element Forge · Canvas: the state (shot) must be a JSON object.")
    return data


class EFAppEffect:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "effect_style": (EFFECT_STYLES, {"default": EFFECT_STYLES[0], "tooltip": "Effect and style (kind/style)."}),
                "mode": (["basic", "advanced"], {"default": "basic"}),
                "strength": (["subtle", "normal", "strong"], {"default": "normal"}),
                "describe": ("STRING", {"default": "", "multiline": True, "tooltip": "What the effect is."}),
                "look_words": ("STRING", {"default": "", "multiline": True}),
                "motion_words": ("STRING", {"default": "", "multiline": True}),
                "contact_words": ("STRING", {"default": "", "multiline": True}),
                "prompt_override": ("STRING", {"default": "", "multiline": True, "tooltip": "Empty = prompt from the words above."}),
                "object_word": ("STRING", {"default": "", "tooltip": "Optional, helps the click."}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 2**31 - 1, "control_after_generate": True}),
                "night": ("BOOLEAN", {"default": False}),
                "sticks_to": (["style default", "point", "object", "scene", "screen"], {"default": "style default",
                    "tooltip": "What the effect follows. Point: the spot you clicked. Object: the whole object. "
                               "Scene: stays in the world while the camera moves. Screen: the same place in the picture."}),
                "own_mask": ("BOOLEAN", {"default": False}),
                "all_alike": ("BOOLEAN", {"default": False}),
                "follows_motion": ("BOOLEAN", {"default": False}),
                "draw_path": ("BOOLEAN", {"default": False}),
                "sharper_2x": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "how_it_goes_in": (["style default", "overlay", "inpaint"], {"default": "style default",
                    "tooltip": "Overlay: made alone on black and laid over the clip (light, glow, placement stay adjustable). "
                               "Inpaint: the AI repaints that part of the clip."}),
                "shot_sentence": ("STRING", {"default": "", "multiline": True,
                    "tooltip": "Inpaint: the shot in one sentence (place, person or object, light)."}),
                "particle_seed": ("INT", {"default": 42, "min": 0, "max": 2**31 - 1,
                    "tooltip": "Seed of the particles: the same seed gives the same simulation. Apart from the AI seed."}),
                "preroll": ("FLOAT", {"default": -2.0, "min": -2.0, "max": 60.0, "step": 0.1,
                    "tooltip": "Seconds the particles run before the clip starts. -2 = as in the preset, -1 = auto, 0 = none."}),
                "emitter_values": ("STRING", {"default": "",
                    "tooltip": "The emitter panel's own values (Advanced), as JSON. Empty = as the style has them."}),
                "guide": (GUIDE_CHOICES, {"default": "style default",
                    "tooltip": "What guides the AI (Advanced, AI elements only). none: it paints freely from the prompt. "
                               "object shape: it takes the shape of the object it sits on. drawn path: it follows strokes "
                               "you paint. particles: the particles of the emitter guide it."}),
                "guide_particles": (["style default"] + GUIDE_PRESETS, {"default": "style default",
                    "tooltip": "The particles the effect starts from: they guide the AI (guide: particles) or are the "
                               "effect (Made by: particles only). Style default = the style's own."}),
                "keep_original": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05,
                    "tooltip": "Inpaint (Advanced): repaints less of the area, so it stays closer to the clip. 0 = off, "
                               "1 = keeps the most. The effect gets less room; a thin one like lightning can vanish."}),
                "object_in_front": ("BOOLEAN", {"default": False,
                    "tooltip": "The clicked object's mask hides the effect wherever the object is, whatever the depth "
                               "map says: a person in front of a portal. Sharper than the depth edge."}),
                "lock_base": ("BOOLEAN", {"default": False,
                    "tooltip": "Advanced: the AI draws the effect a little differently in every frame, so its base can "
                               "jitter by a few pixels. On: the base stays fixed on the tracked point (a flame sits calmly "
                               "on the object and still flickers above). Off: only slow drift is removed."}),
                "made_by": (["style default", "ai", "particles"], {"default": "style default",
                    "tooltip": "ai: the AI makes the element (particles, if any, guide it). particles: the particles "
                               "alone, drawn without an AI run. Style default = as the style has it."}),
            }
        }

    RETURN_TYPES = ("EF_EFFECT",)
    RETURN_NAMES = ("effect",)
    FUNCTION = "build"
    CATEGORY = CATEGORY
    DESCRIPTION = "Effect, style and prompt words of the Element Forge app."

    def build(self, **kw):
        effect = dict(kw)
        kind, _, style = str(kw.get("effect_style", "")).partition("/")
        effect["kind"] = kind
        effect["style"] = style
        return (effect,)


class EFAppStage:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot": ("STRING", {"default": "{}", "multiline": False}),
            },
            "optional": {
                "video": ("VIDEO",),
                "effect": ("EF_EFFECT",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("shot",)
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = "Canvas and timeline of the Element Forge app (the widget is drawn by the frontend)."

    def run(self, shot="{}", video=None, effect=None):
        _parse_shot(shot)
        return (shot,)


INPAINT_SIGMAS = "Inpaint sigmas (start 0.909 = tested default)"


def keep_sigmas(k):
    k = min(1.0, max(0.0, float(k)))
    start = round(0.909375 - k * (0.909375 - 0.725), 6)
    return "0.725, 0.421875, 0.0" if start <= 0.725 else f"{start:g}, 0.725, 0.421875, 0.0"


def apply_effect(values, effect):
    out = dict(values)
    if "seed" in effect:
        out[SEED] = int(effect["seed"])
    if "night" in effect:
        out[NIGHT] = bool(effect["night"])
    if "particle_seed" in effect:
        out[PARTICLE_SEED] = int(effect["particle_seed"])
    if "preroll" in effect:
        out[PREROLL] = float(effect["preroll"])
    word = str(effect.get("object_word") or "").strip()
    if word:
        out[OBJECT_WORD] = word
    follows = FOLLOWS_VALUES.get(effect.get("sticks_to", "style default"))
    if follows and PLACEMENTS.get(str(effect.get("effect_style", ""))) != "frame":
        out[STICKS_SCENE], out[TRACK_MASK], out[STILL] = follows
    out[OWN_MASK] = bool(effect.get("own_mask"))
    out[ALL_ALIKE] = bool(effect.get("all_alike"))
    if effect.get("object_in_front"):
        out[OBJECT_IN_FRONT] = True
    out[UPSCALE] = bool(effect.get("sharper_2x"))
    if effect.get("mode") == "advanced":
        out[FOLLOWS] = bool(effect.get("follows_motion"))
        own = str(effect.get("emitter_values") or "").strip()
        if own and own != "{}":
            json.loads(own)
            out[DISSOLVE_EXTRA if str(effect.get("effect_style", "")).startswith("dissolve/") else PARTICLE_EMITTER] = own
        style = str(effect.get("effect_style", ""))
        guide = str(effect.get("guide") or "style default")
        if guide == "style default" and effect.get("draw_path"):
            guide = "drawn path"
        if guide == "drawn path" or effect.get("draw_path"):
            out[GUIDE_SOURCE] = "draw"
        if effect.get("lock_base"):
            out[LOCK_BASE] = True
        keep = float(effect.get("keep_original") or 0.0)
        if keep > 0:
            out[INPAINT_SIGMAS] = keep_sigmas(keep)
        if guide != "style default":
            out[AI_GUIDE] = guide
            if guide == "particles" and style not in PARTICLE_STYLES:
                pp = str(effect.get("guide_particles") or "style default")
                out["Particles"] = True
                out["Particle preset"] = GUIDE_PARTICLES.get(style, "magic dust") if pp == "style default" else pp
    style = str(effect.get("effect_style", ""))
    made = str(effect.get("made_by") or "style default")
    pp = str(effect.get("guide_particles") or "style default")
    own = STYLE_SETTINGS.get(style, {})
    if made == "particles":
        out["Particles"] = True
        out[DIRECT_LOOK] = True
        out["Particle preset"] = pp if pp != "style default" else start_preset(style)
    elif made == "ai" and own.get(DIRECT_LOOK):
        out[DIRECT_LOOK] = False
    if pp != "style default" and (out.get("Particles") or own.get("Particles")):
        out["Particle preset"] = pp
    return out


APP_KEY = "_app"


def run_id(settings):
    blob = json.dumps(settings, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


class EFAppValues:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "shot": ("STRING", {"forceInput": True}),
                "effect": ("EF_EFFECT",),
            }
        }

    RETURN_TYPES = ("EF_SETTINGS", "STRING")
    RETURN_NAMES = ("settings", "run_prefix")
    FUNCTION = "run"
    CATEGORY = CATEGORY
    DESCRIPTION = ("Turns the canvas state and the effect widgets into the settings of the one workflow. "
                   "When the prompt is queued, the values are written into the setting nodes, so only changed "
                   "settings re-run.")

    def run(self, shot, effect):
        data = _parse_shot(shot)
        values = data.get("values") or {}
        if not isinstance(values, dict) or not values:
            raise ValueError("Element Forge: add an effect in the canvas first.")
        effect = effect or {}
        vf = data.get("values_for") or {}
        for key in ("kind", "style"):
            have, want = vf.get(key), effect.get(key)
            if have is not None and want is not None and str(have) != str(want):
                raise ValueError("Element Forge: the canvas is not on the new style yet - please press Run again.")
        if vf.get("style") is None and effect.get("style"):
            raise ValueError("Element Forge: the canvas is not on the new style yet - please press Run again.")
        settings = apply_effect(values, effect)
        if settings.get("Element from library") and not str(settings.get("Library element") or "").strip():
            raise ValueError("Element Forge: pick a saved element under Effect (From the library), or switch back to Made by the AI.")
        app = data.get("app")
        if isinstance(app, dict) and app:
            settings[APP_KEY] = {k: app[k] for k in ("mode", "skip", "effect", "ltx", "save_element") if k in app}
        return (settings, f"element-forge/{run_id(settings)}")


def _to_bool(v):
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def _to_int(v):
    return int(round(float(v)))


def _to_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _json_or_raw(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _make_pick(label, fallback_spec, out_type, convert, fallback_convert=None):
    class _Pick:
        @classmethod
        def INPUT_TYPES(cls):
            return {
                "required": {
                    "settings": ("EF_SETTINGS",),
                    "name": ("STRING", {"default": "", "tooltip": "Settings name (element_forge.settings.json)."}),
                    "fallback": fallback_spec,
                }
            }

        RETURN_TYPES = (out_type,)
        RETURN_NAMES = ("value",)
        FUNCTION = "pick"
        CATEGORY = CATEGORY
        DESCRIPTION = (f"One {label} value from the Element Forge settings (fallback if the name is missing). "
                       "When queued, the value is filled in directly, so only nodes that need it re-run.")

        def pick(self, settings, name, fallback):
            fb = fallback_convert(fallback) if fallback_convert else fallback
            v = (settings or {}).get(name)
            if v is None:
                return (fb,)
            try:
                return (convert(v),)
            except (TypeError, ValueError):
                return (fb,)

    _Pick.__name__ = f"EFAppPick{label}"
    return _Pick


EFAppPickBool = _make_pick("Bool", ("BOOLEAN", {"default": False}), "BOOLEAN", _to_bool)
EFAppPickInt = _make_pick("Int", ("INT", {"default": 0, "min": -(2**53), "max": 2**53}), "INT", _to_int)
EFAppPickFloat = _make_pick("Float", ("FLOAT", {"default": 0.0, "min": -1e9, "max": 1e9, "step": 0.001, "round": False}),
                            "FLOAT", float)
EFAppPickString = _make_pick("String", ("STRING", {"default": "", "multiline": True}), "STRING", _to_str)
EFAppPickAny = _make_pick("Any", ("STRING", {"default": "", "multiline": False, "tooltip": "JSON (or plain text)."}),
                          ANY, lambda v: v, _json_or_raw)


NODE_CLASS_MAPPINGS = {
    "EFAppEffect": EFAppEffect,
    "EFAppStage": EFAppStage,
    "EFAppValues": EFAppValues,
    "EFAppPickBool": EFAppPickBool,
    "EFAppPickInt": EFAppPickInt,
    "EFAppPickFloat": EFAppPickFloat,
    "EFAppPickString": EFAppPickString,
    "EFAppPickAny": EFAppPickAny,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EFAppEffect": "Element Forge · Effect",
    "EFAppStage": "Element Forge · Canvas & Timeline",
    "EFAppValues": "Element Forge · Settings from canvas",
    "EFAppPickBool": "Element Forge · Setting (Bool)",
    "EFAppPickInt": "Element Forge · Setting (Int)",
    "EFAppPickFloat": "Element Forge · Setting (Float)",
    "EFAppPickString": "Element Forge · Setting (String)",
    "EFAppPickAny": "Element Forge · Setting (Any)",
}

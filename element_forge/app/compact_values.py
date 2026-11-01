import hashlib
import json
import math
from decimal import ROUND_HALF_UP, Decimal
import re

MAX_FRAMES = 161
INPAINT = "Inpaint (off = on black)"
CRUMBLE = "Object crumbles under the effect (the dissolve is the plate)"
STRENGTH = {"subtle": "subtle, small and delicate", "strong": "large, intense and dramatic"}
DIRECTIONS = ["upward", "up and to the right", "to the right", "down and to the right", "downward", "down and to the left",
              "to the left", "up and to the left"]


LTX_ATTENTION = ("pytorch attention", "comfy kitchen attention")


def js_round(v):
    return math.floor(v + 0.5)


def fixed(v, n=3):
    return float(Decimal(v).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def clamp(v, a, b):
    return min(b, max(a, v))


def ltx_frames(n):
    return max(9, (min(n, MAX_FRAMES) - 1) // 8 * 8 + 1)


def style_def(presets, kind, style):
    for e in presets.get("effects", []):
        if e["id"] == kind:
            for s in e["styles"]:
                if s["id"] == style:
                    return s
    return None


DIRECT_LOOK = "Particles: direct look (no LTX, pro)"


PLACEMENT = "Placement (auto / point / area / object / frame / between)"
PL_OF = {"point": "point", "window": "area", "object": "object", "frame": "frame", "ab": "between"}
PL_TO = {"point": "point", "area": "window", "object": "object", "frame": "frame", "between": "ab"}
PL_SHAPE = {"frame": "whole frame", "object": "object mask", "between": "line A-B"}


def with_place(st, effect):
    a = effect.get("adv") or {}
    side = a.get("Emitter side")
    if side and (st.get("variant") or "app") == "app" and side != ((st.get("settings") or {}).get("Emitter side") or "bottom"):
        st = {**st, "settings": {**(st.get("settings") or {}), "Emitter side": side}}
    want = a.get(PLACEMENT)
    if not want or (st.get("variant") or "app") != "app" or want == PL_OF.get(st.get("placement"), "point") or want not in PL_TO:
        return st
    s0 = st.get("settings") or {}
    sets = dict(s0)
    if not a.get("Particle emitter"):
        if want in PL_SHAPE:
            sets["Particle emitter"] = PL_SHAPE[want]
        elif s0.get("Particle emitter") in ("whole frame", "line A-B", "object mask", "object contour", "object bottom edge"):
            sets.pop("Particle emitter", None)
    if want == "frame":
        sets["Sticks to scene (off = object)"] = s0.get("Sticks to scene (off = object)", True)
    if want == "between":
        sets["Window A-B automatic"] = True
    return {**st, "placement": PL_TO[want], "settings": sets}


def style_of(presets, effect):
    st = style_def(presets, effect["kind"], effect["style"])
    if not st:
        return st
    st = with_place(st, effect)
    a, s0 = effect.get("adv") or {}, st.get("settings") or {}
    parts = bool(a["Particles"] if "Particles" in a else s0.get("Particles"))
    direct = bool(a[DIRECT_LOOK] if DIRECT_LOOK in a else s0.get(DIRECT_LOOK))
    preset = a.get("Particle preset") or s0.get("Particle preset")
    if parts == bool(s0.get("Particles")) and direct == bool(s0.get(DIRECT_LOOK)) and preset == s0.get("Particle preset"):
        return st
    sets = {**s0, "Particles": parts, DIRECT_LOOK: direct, **({"Particle preset": preset} if preset else {})}
    return {**st, "cost": "calc" if direct and (parts or st.get("variant") == "climb") else "gen", "settings": sets}


def effect_styles(presets):
    return [f"{e['id']}/{s['id']}" for e in presets.get("effects", []) for s in e["styles"]]


def gen_size(st, aspect, guide, scale=1.0):
    gw, gh = st.get("gen") or [512, 768]
    area = gw * gh * scale * scale
    step = 64 if guide else 32
    lim = max(1.0, area / (step * 4) ** 2)
    aspect = clamp(aspect, 1 / lim, lim)
    w = math.sqrt(area * aspect)
    h = w / aspect
    r = lambda v: max(step * 4, js_round(v / step) * step)
    return [r(w), r(h)]


def gen_window(st, b, guide, scale=1.0):
    gw, gh = gen_size(st, b["w"] / b["h"], guide, scale)
    w, h = b["w"], b["h"]
    if w / h < gw / gh:
        w = h * gw / gh
    else:
        h = w * gh / gw
    return {"x": b["x"] + (b["w"] - w) / 2, "y": b["y"] + (b["h"] - h) / 2, "w": w, "h": h, "gw": gw, "gh": gh}


GUIDE = "Guide for the AI (particles / drawn path / object shape / none)"


def guide_of(st, effect=None):
    s = {**(st.get("settings") or {}), **((effect or {}).get("adv") or {})}
    if s.get(GUIDE):
        return s[GUIDE]
    if s.get("Particles"):
        return "none" if s.get("Particles: guide") is False else "particles"
    return "drawn path" if s.get("Guide") else "particles"


def uses_guide(st, effect=None):
    s = {**(st.get("settings") or {}), **((effect or {}).get("adv") or {})}
    g = guide_of(st, effect)
    return g in ("drawn path", "object shape") or (g == "particles" and bool(s.get("Particles")))


def in_window(st, effect=None):
    s = {**(st.get("settings") or {}), **((effect or {}).get("adv") or {})}
    led = uses_guide(st, effect) or bool(s.get("Follows motion"))
    if st.get("placement") == "ab":
        return led and not s.get("Particles")
    return st.get("placement") == "point" and (led or bool(s.get("Particles")))


def base_point(st, b):
    side = (st.get("settings") or {}).get("Emitter side") or "bottom"
    return {"x": b["x"] if side == "left" else b["x"] + b["w"] if side == "right" else b["x"] + b["w"] / 2,
            "y": b["y"] if side == "top" else b["y"] + b["h"] if side == "bottom" else b["y"] + b["h"] / 2}


def default_box(st, effect, clip):
    a = effect["where"].get("a") or {"x": clip["width"] / 2, "y": clip["height"] / 2}
    pl = st.get("placement")
    if pl == "window":
        s = min(clip["width"], clip["height"])
        fw, fh = st.get("win") or [0.6, 0.6]
        ex, ey = st.get("emitter") or [0.5, 0.5]
        w, h = fw * s, fh * s
        return {"x": a["x"] - ex * w, "y": a["y"] - ey * h, "w": w, "h": h}
    if pl == "point":
        gw, gh = st.get("gen") or [512, 768]
        sc = (st.get("settings") or {}).get("Size in plate", 0.3)
        w, h = gw * sc, gh * sc
        side = (st.get("settings") or {}).get("Emitter side") or "bottom"
        sh = 0.2 if guide_of(st, effect) == "object shape" else 0
        ox = 0 if side == "left" else w if side == "right" else w / 2
        oy = sh * h if side == "top" else (1 - sh) * h if side == "bottom" else h / 2
        return {"x": a["x"] - ox, "y": a["y"] - oy, "w": w, "h": h}
    b = effect["where"].get("b")
    if pl == "ab" and effect["where"].get("a") and b:
        w0, h0 = abs(a["x"] - b["x"]), abs(a["y"] - b["y"])
        extra = max(w0, h0) + 96
        gw, gh = st.get("gen") or [448, 640]
        w = max(w0 + extra, (h0 + extra) * gw / gh)
        h = w * gh / gw
        return {"x": (a["x"] + b["x"]) / 2 - w / 2, "y": (a["y"] + b["y"]) / 2 - h / 2, "w": w, "h": h}
    return None


def frame_box(st, effect, clip):
    return effect.get("box") or default_box(st, effect, clip)


def _cap(s):
    return s[0].upper() + s[1:] if s else s


def _strip(s):
    return re.sub(r"[.\s]+$", "", (s or "").strip())


def direction_words(deg):
    if deg is None:
        return ""
    return DIRECTIONS[js_round((((deg % 360) + 360) % 360) / 45) % 8]


def prompt_of(st, effect):
    p = st.get("prompt")
    a = effect["where"].get("a") or {}
    return {**p, **p["light_ground"]} if p and p.get("light_ground") and a.get("ground") == "light" else p


def changed_blocks(st, effect):
    p = prompt_of(st, effect)
    if not p:
        return []
    t = effect["text"]
    return [k for k in ("look", "motion", "contact") if (t.get(k) or "") != "" and _strip(t.get(k)) != _strip(p.get(k))]


def in_scene(st, effect):
    adv = effect.get("adv") or {}
    v = adv[INPAINT] if INPAINT in adv else (st.get("settings") or {}).get(INPAINT)
    return st.get("placement") != "frame" and bool(v)


def object_word(st, effect):
    return (effect["where"].get("word") or "").strip()


def fill_word(s, word):
    if s is None:
        return s
    return re.sub(r"\{([^{}|]*)\|([^{}]*)\}", lambda m: m.group(1).replace("%", word, 1) if word else m.group(2), str(s))


def inpaint_settings(presets, kind):
    ip = presets.get("inpaint") or {}
    return {**(ip.get("default") or {}), **(ip.get(kind) or {})}


def without_black(s):
    s = re.sub(r",?\s*(?:filmed |shot )?(?:on|against|over) (?:a )?(?:pure |plain )?black (?:background|backdrop)", "", s or "", flags=re.I)
    s = re.sub(r",?\s*surrounded by black space", "", s, flags=re.I)
    s = re.sub(r"([.!?])\s*,\s*", r"\1 ", s)
    s = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return s.strip()


def with_tail(s, tail):
    return s if not tail or re.search(r"black background", s or "", re.I) else f"{(s or '').rstrip()}{tail}"


def compose_prompt(presets, st, effect):
    return fill_word(_compose_raw(presets, st, effect), object_word(st, effect))


QUICK_COLOURS = [("orange", "#ff7a1a"), ("red", "#e8202a"), ("gold", "#ffc23a"), ("green", "#38d26a"), ("blue", "#2f7bff"),
                 ("violet", "#9b5cff"), ("white", "#f2f4ff")]
QUICK = {"amount": {"less": (0.5, "sparse"), "more": (2, "dense and abundant")},
         "speed": {"slower": (0.5, "slow and gentle"), "faster": (1.8, "fast and energetic")},
         "size": {"smaller": (0.6, "small"), "bigger": (1.6, "big")}}


def _rgb(h):
    out = []
    for i in (1, 3, 5):
        try:
            out.append(int(str(h)[i:i + 2], 16))
        except ValueError:
            out.append(0)
    return out


def colour_name(hex_):
    r, g, b = _rgb(hex_)
    best, bd = QUICK_COLOURS[0][0], float("inf")
    for n, h in QUICK_COLOURS:
        r2, g2, b2 = _rgb(h)
        d = (r - r2) ** 2 + (g - g2) ** 2 + (b - b2) ** 2
        if d < bd:
            best, bd = n, d
    return best


def quick_words(effect):
    q = effect.get("quick") or {}
    w = [f"mainly {colour_name(q['colour'])}"] if q.get("colour") else []
    for k in ("amount", "speed", "size"):
        if q.get(k) in QUICK[k]:
            w.append(QUICK[k][q[k]][1])
    return ", ".join(w)


def _compose_raw(presets, st, effect):
    p = prompt_of(st, effect)
    if not p:
        return None
    paint = in_scene(st, effect)
    tail = "" if paint else presets.get("tail_on_black") or ""
    if effect.get("prompt") is not None:
        return effect["prompt"] if paint else with_tail(effect["prompt"], tail)
    t = effect["text"]
    qw = quick_words(effect)
    untouched = not changed_blocks(st, effect) and effect.get("strength", "normal") == "normal" and effect.get("dir") is None and not qw
    if untouched and p.get("preset"):
        return without_black(p["preset"]) if paint else p["preset"]

    def block(k):
        return _strip(t[k] if t.get(k) not in (None, "") else p.get(k))
    look_changed = "look" in changed_blocks(st, effect)
    what = _strip((look_changed and p.get("what_plain")) or p.get("what") or t.get("what") or "")
    if not what:
        what = _strip(t.get("look")) or "A glowing element"
    if effect.get("strength", "normal") != "normal":
        what = f"{what}, {STRENGTH[effect['strength']]}"
    if qw:
        what = f"{what}, {qw}"
    action = block("motion")
    dw = direction_words(effect.get("dir"))
    if dw and st.get("dir") != "dissolve":
        action = f"{action}, moving {dw}" if action else f"moves {dw}"
    contact = block("contact")
    first = _cap(" ".join(x for x in (what, action) if x) + (f", and {contact}" if contact else "")) + "."
    look = block("look")
    return " ".join(x for x in (first, _cap(look) + "." if look else "") if x) + tail


def values_for(presets, effect, shot, scale=1.0):
    st = style_of(presets, effect)
    if not st:
        raise ValueError(f"unknown effect and style {effect['kind']}/{effect['style']}")
    clip = shot["clip"]
    sets = st.get("settings") or {}
    v = dict(sets)
    if clip.get("still"):
        v["Still image (a picture in the input folder instead of the clip)"] = clip["name"]
        v["Still image length (s)"] = clip["seconds"]
    else:
        v["Clip"] = clip["name"]
    v["Frames"] = ltx_frames(clip["frames"])
    a = effect["where"].get("a") or {"x": clip["width"] / 2, "y": clip["height"] / 2}
    v["Point A x"] = js_round(a["x"])
    v["Point A y"] = js_round(a["y"])
    b = effect["where"].get("b")
    if b:
        v["Point B x"] = js_round(b["x"])
        v["Point B y"] = js_round(b["y"])
    word = object_word(st, effect)
    if word:
        v["Object word (optional, helps the click)"] = word
    guide = uses_guide(st, effect)
    pl = st.get("placement")
    if pl == "window" or (pl == "ab" and effect.get("box")) or in_window(st, effect):
        w = gen_window(st, frame_box(st, effect, clip), guide, scale)
        v["Window A-B automatic"] = False
        v["Window width (plate px)"] = js_round(w["w"])
        v["Window height (plate px)"] = js_round(w["h"])
        v["Emitter x in window"] = fixed(clamp((a["x"] - w["x"]) / w["w"], -4, 5))
        v["Emitter y in window"] = fixed(clamp((a["y"] - w["y"]) / w["h"], -4, 5))
        v["Generate width"], v["Generate height"] = w["gw"], w["gh"]
    elif pl == "ab":
        v["Window A-B automatic"] = True
        g = st.get("gen") or [448, 640]
        v["Generate width"], v["Generate height"] = g if scale == 1 else gen_size({"gen": g}, g[0] / g[1], guide, scale)
    elif pl == "frame" or (pl == "object" and st.get("variant") == "app"):
        v["Window width (plate px)"] = clip["width"]
        v["Window height (plate px)"] = clip["height"]
        v["Emitter x in window"] = 0.5
        v["Emitter y in window"] = 0.5
        v["Generate width"], v["Generate height"] = gen_size(st, clip["width"] / clip["height"], guide, scale)
    elif pl == "point":
        bx = frame_box(st, effect, clip)
        gw, gh = gen_size(st, bx["w"] / bx["h"], guide, scale)
        v["Generate width"], v["Generate height"] = gw, gh
        v["Size in plate"] = fixed(min(bx["w"] / gw, bx["h"] / gh))
        p = base_point(st, bx)
        dx, dy = js_round(p["x"] - a["x"]), js_round(p["y"] - a["y"])
        if dx:
            v["Base beside A x (plate px)"] = dx
        if dy:
            v["Base beside A y (plate px)"] = dy
    timing = effect.get("timing") or {}
    if timing.get("start"):
        v["Starts at (s)"] = fixed(timing["start"], 2)
    if st.get("dir") == "dissolve":
        end = timing.get("end")
        if end is None:
            end = min(clip["seconds"], MAX_FRAMES / clip["fps"])
        v["Dissolve duration (s)"] = fixed(max(0.2, end - (timing.get("start") or 0)), 2)
        v["Dissolve direction (0 up, 90 right)"] = effect["dir"] if effect.get("dir") is not None else 90
    if st.get("dir") != "dissolve" and (effect.get("adv") or {}).get(CRUMBLE):
        end = timing.get("end")
        if end is None:
            end = min(clip["seconds"], MAX_FRAMES / clip["fps"])
        v["Dissolve duration (s)"] = fixed(max(0.2, end - (timing.get("start") or 0)), 2)
    if sets.get("Particles") and pl != "ab" and st.get("dir") != "dissolve" and effect.get("dir") is not None:
        v["Particle direction (-1 = preset)"] = js_round(effect["dir"])
    if effect.get("depth"):
        key = "Particle depth offset" if sets.get("Particles") else "Depth offset (+ = element nearer, less hidden)"
        v[key] = fixed(sets.get(key, 0) + effect["depth"])
    prompt = compose_prompt(presets, st, effect)
    if prompt:
        v["Effect prompt"] = prompt
    if shot.get("night"):
        v["Night"] = True
    if in_scene(st, effect):
        if not sets.get(INPAINT):
            v.update(inpaint_settings(presets, effect["kind"]))
        if (shot.get("scene") or "").strip():
            v["Shot description (Inpaint)"] = shot["scene"].strip()
    v["Seed"] = effect["seed"]
    v.update(effect.get("adv") or {})
    if (st.get("variant") or "app") != "app":
        v.pop(PLACEMENT, None)
    q = effect.get("quick") or {}
    if v.get("Particles"):
        for k, name in (("amount", "Particle amount"), ("speed", "Particle speed"), ("size", "Particle size")):
            if q.get(k) in QUICK[k]:
                v[name] = fixed((v.get(name) if v.get(name) is not None else 1) * QUICK[k][q[k]][0])
        if q.get("colour") and not v.get("Particle pro: color"):
            v["Particle pro: color"] = q["colour"]
    return v


def luma_ground(rgb):
    r, g, b = (js_round(c) for c in rgb)
    return "light" if (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.45 else "dark"


def run_id(variant, mode, values, look):
    blob = json.dumps([variant, mode, values, look], sort_keys=True, ensure_ascii=False, default=str)
    return "c" + hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def tune_look(graph, look):
    s, e = float(look.get("light_strength", 1.0)), float(look.get("glow_exposure", 0.0))
    a, col = float(look.get("albedo_exposure", 0.0)), str(look.get("light_color") or "")
    for nd in graph.values():
        if nd["class_type"] == "EFDepthLight" and a != 0.0:
            nd["inputs"]["albedo_exposure"] = a
        if nd["class_type"] == "EFDepthLight" and col:
            nd["inputs"]["color"], nd["inputs"]["color_amount"] = col, 1.0
        if nd["class_type"] == "EFDepthLight" and s != 1.0 and isinstance(nd["inputs"].get("strength"), (int, float)):
            nd["inputs"]["strength"] = nd["inputs"]["strength"] * s
            if s > 1.0 and isinstance(nd["inputs"].get("max_light"), (int, float)):
                nd["inputs"]["max_light"] = nd["inputs"]["max_light"] * s ** 0.5
        if nd["class_type"] == "EFGlow" and e != 0.0 and isinstance(nd["inputs"].get("exposure"), (int, float)):
            nd["inputs"]["exposure"] = nd["inputs"]["exposure"] + e

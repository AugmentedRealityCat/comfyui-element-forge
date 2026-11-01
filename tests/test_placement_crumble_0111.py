import importlib
import json
import os
import sys
import tempfile
import types

import torch

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
fp.get_input_directory = lambda: os.path.join(S, "in")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")


class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass


cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
mm.get_torch_device = lambda: torch.device("cpu")
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
M = pack.NODE_CLASS_MAPPINGS
ok = 0


def check(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("ok  ", msg)


pl = M["EFPlacement"]()
check(pl.choose("auto", True, False) == (True, False) and pl.choose("auto", False, True) == (False, True), "auto keeps the rule from the guide and B")
check(pl.choose("area", False, False) == (True, False), "an area is made in a window")
check(pl.choose("frame", False, True) == (True, False), "the whole frame: a window, B does not stretch it")
check(pl.choose("between", False, True) == (False, True), "between stretches from A to B")
check(pl.choose("between", False, False) == (False, False), "between without B is a point")
check(pl.choose("point", True, True) == (True, False), "a point with a guide is made in its window, B does not stretch it")
check(pl.choose("between", True, True) == (True, False) and pl.choose("auto", True, True) == (True, False),
      "between with a guide: made in its window, B does not stretch it (night probe 01.11.)")
try:
    pl.choose("somewhere", False, False)
    check(False, "an unknown placement stops")
except ValueError:
    check(True, "an unknown placement stops")

API = os.path.join(PACK, "api_workflows")
for name in ("element_forge.json", "element_forge_app.json"):
    G = json.load(open(os.path.join(API, name), encoding="utf-8"))
    place = [k for k, v in G.items() if v["class_type"] == "EFPlacement"]
    check(len(place) == 1, f"{name}: one EF Placement")
    feeds = [k for k, v in G.items() if any(isinstance(x, list) and x[:1] == [place[0]] for x in v["inputs"].values())]
    check(len(feeds) == 2, f"{name}: EF Placement decides the window and A to B")
    crumble = [k for k, v in G.items() if "crumbles" in (v.get("_meta", {}).get("title") or "")]
    check(crumble, f"{name}: the crumble switch is there")
SET = json.load(open(os.path.join(API, "element_forge.settings.json"), encoding="utf-8"))["settings"]
names = {s["name"] if isinstance(s, dict) else s for s in (SET.values() if isinstance(SET, dict) else SET)} if not isinstance(SET, dict) else set(SET)
check(any("Placement (auto" in n for n in names), "the settings have the placement")
check(any("Object crumbles under the effect" in n for n in names), "the settings have the crumble")

an = importlib.import_module(pack.__name__ + ".element_forge.app_mode.nodes")
opt = an.EFAppEffect.INPUT_TYPES()["optional"]
check({"placement", "sits_on", "crumble", "crumble_look", "crumble_direction"} <= set(opt), "the effect node has placement and crumble")
fr = an.apply_effect({}, {"effect_style": "fire/flame", "placement": "frame"})
check(fr.get(an.PLACEMENT) == "frame", "a flame over the whole frame")
ob = an.apply_effect({}, {"effect_style": "sparks/burst", "placement": "object"})
check(ob.get(an.PLACEMENT) == "object" and ob.get("Particle emitter") == "object mask", "sparks on the object start from its mask")
ab = an.apply_effect({}, {"effect_style": "magic/aura", "placement": "between"})
check(ab.get("Window A-B automatic") is True, "between sizes the window from A and B")
own = an.PL_OF.get(an.PLACEMENTS.get("fire/flame"), "point")
check(an.PLACEMENT not in an.apply_effect({}, {"effect_style": "fire/flame", "placement": own}), "the style's own placement sends nothing")
check(an.PLACEMENT not in an.apply_effect({}, {"effect_style": "lightning/climb", "placement": "frame"}), "the climb keeps its placement")
check(an.PLACEMENT not in an.apply_effect({}, {"effect_style": "dissolve/plain", "placement": "frame"}), "the dissolve keeps its placement")
check(an.apply_effect({}, {"effect_style": "own/point", "sits_on": "centre"}).get(an.SIDE) == "centre", "your own effect sits on A by its centre")
cr = an.apply_effect({}, {"effect_style": "fire/flame", "crumble": True, "crumble_look": "gold dust", "crumble_direction": 0})
check(cr.get(an.CRUMBLE) is True and cr.get(an.CRUMBLE_STYLE) == "gold dust" and cr.get(an.CRUMBLE_DIR) == 0, "a burning object crumbles to gold dust, upwards")
check(an.CRUMBLE not in an.apply_effect({}, {"effect_style": "dissolve/gold", "crumble": True}), "the dissolve itself does not crumble twice")
check(an.CRUMBLE not in an.apply_effect({}, {"effect_style": "fire/flame"}), "off by default")

cv = importlib.import_module(pack.__name__ + ".element_forge.app.compact_values")
presets = json.load(open(os.path.join(PACK, "element_forge", "app", "app_presets.json"), encoding="utf-8"))
st = cv.style_def(presets, "fire", "flame")
moved = cv.with_place(st, {"adv": {cv.PLACEMENT: "frame"}})
check(moved["placement"] == "frame" and moved["settings"].get("Particle emitter") == "whole frame", "the app moves a flame to the whole frame")
check(cv.with_place(st, {"adv": {}}) is st, "nothing chosen: the style as it is")
fab = {"kind": "fire", "style": "flame", "where": {"a": {"x": 1000, "y": 525}, "b": {"x": 1350, "y": 230}}, "dir": None, "depth": 0,
       "strength": "normal", "text": {"what": "", "look": "", "motion": "", "contact": ""}, "prompt": None,
       "timing": {"start": 0, "end": None}, "seed": 1, "adv": {cv.PLACEMENT: "between"}, "box": None}
clip0 = {"name": "c.mp4", "width": 1920, "height": 1080, "frames": 90, "fps": 30, "seconds": 3}
vab = cv.values_for(presets, fab, {"clip": clip0, "night": False, "scene": ""})
x0 = 1000 - vab["Emitter x in window"] * vab["Window width (plate px)"]
y0 = 525 - vab["Emitter y in window"] * vab["Window height (plate px)"]
check(vab["Window A-B automatic"] is False and x0 <= 1000 and x0 + vab["Window width (plate px)"] >= 1350
      and y0 <= 230 and y0 + vab["Window height (plate px)"] >= 525, "a guided flame between A and B: its window holds A and B")
fob = {**fab, "where": {"a": {"x": 1000, "y": 525}, "b": None, "word": "sword blade"}, "adv": {cv.PLACEMENT: "object"}}
pob = cv.values_for(presets, fob, {"clip": clip0, "night": False, "scene": ""})["Effect prompt"]
check("It covers the sword blade, following its shape." in pob and "lower half" not in pob,
      "a flame moved onto the object is told so, not to fill the lower half of the frame (night probe 01.11.)")
check("lower half" in cv.values_for(presets, {**fob, "adv": {}}, {"clip": clip0, "night": False, "scene": ""})["Effect prompt"],
      "at its own place the flame keeps its tested text")
sm = cv.values_for(presets, {**fob, "kind": "fire", "style": "smolder", "adv": {cv.PLACEMENT: "frame"}}, {"clip": clip0, "night": False, "scene": ""})
check(sm.get("Inpaint (off = on black)") is False and "black background" in sm["Effect prompt"],
      "embers moved to the whole frame are made on black (painting in needs a place to follow)")

check(cv.colour_name("#3070ff") == "blue" and cv.colour_name("#ffffff") == "white", "a picked colour has the nearest named colour for the AI")
check(cv.quick_words({"quick": {"colour": "#e8202a", "amount": "more", "size": "smaller"}}) == "mainly red, dense and abundant, small",
      "colour, amount and size become words")
fl = {"kind": "fire", "style": "flame", "where": {"a": {"x": 400, "y": 300}}, "dir": None, "depth": 0, "strength": "normal",
      "text": {"what": "", "look": "", "motion": "", "contact": ""}, "prompt": None, "timing": {"start": 0, "end": None}, "seed": 1, "adv": {},
      "box": None}
shot = {"clip": {"name": "c.mp4", "width": 1920, "height": 1080, "frames": 90, "fps": 30, "seconds": 3}, "night": False, "scene": ""}
plain = cv.values_for(presets, fl, shot)["Effect prompt"]
fast = cv.values_for(presets, {**fl, "quick": {"speed": "faster"}}, shot)
check("fast and energetic" in fast["Effect prompt"] and "fast and energetic" not in plain, "an AI flame gets the words")
check("Particle speed" not in fast, "an AI flame without particles keeps the particles as they are")
pt = cv.values_for(presets, {**fl, "quick": {"speed": "faster", "colour": "#2f7bff"},
                             "adv": {"Particles": True, "Particles: direct look (no LTX, pro)": True}}, shot)
check(pt["Particle speed"] == 1.8 and pt["Particle pro: color"] == "#2f7bff", "particles only: faster and blue particles")

AN = importlib.import_module(pack.__name__ + ".element_forge.tracking.analysis")
w0 = {"clip": "c.mp4", "frames": 89, "a": [10, 20], "b": [], "word": "", "alike": False, "own": False}
k0 = AN.track_key(w0)
check(AN.track_key({**w0, "fixes": "[]"}) == k0, "no fixes: the track keeps its key")
k1 = AN.track_key({**w0, "fixes": '[{"frame": 40, "add": "100, 200"}]'})
check(k1 != k0 and AN.track_key({**w0, "fixes": '[{"frame": 40, "add": "100, 200"}]'}) == k1, "a fix gives the track a key of its own")
G = json.load(open(os.path.join(API, "element_forge.json"), encoding="utf-8"))
check(G["962"]["class_type"] == "EFMaskFixes" and G["929"]["inputs"]["mask"] == ["962", 1] and G["930"]["inputs"]["mask"] == ["962", 0],
      "EF Mask Fixes sits before both steady masks")

PR = importlib.import_module(pack.__name__ + ".element_forge.app_mode.prompt_rewrite")
fx0 = {k: (v[1] or {}).get("default", v[0][0] if isinstance(v[0], list) else 0) for k, v in an.EFAppEffect.INPUT_TYPES()["required"].items()}
fx0.update(effect_style="fire/flame", object_word="sword blade", seed=6)
p0 = {"901": {"class_type": "EFAppEffect", "inputs": {**fx0, "crumble": True, "placement": "between", "guide": "particles"}}}
got = PR.resolve_effect(p0, ["901", 0])
check(got and got["crumble"] is True and got["placement"] == "between" and got["guide"] == "particles",
      "the rewrite reads the optional widgets (Crumble, Placement, Guide)")
check(PR.resolve_effect({"901": {"class_type": "EFAppEffect", "inputs": {**fx0}}}, ["901", 0]).get("crumble") is None,
      "a widget not sent keeps its default")
check(PR.resolve_effect({"901": {"class_type": "EFAppEffect", "inputs": {**fx0, "crumble": ["5", 0]}}}, ["901", 0]) is None,
      "an optional widget fed by a link: not known before the run")
eff = an.EFAppEffect().build(**got)[0]
st = an.apply_effect({"Point A x": 1, "Point A y": 2}, eff)
check(st.get(an.CRUMBLE) is True and st.get("Window A-B automatic") is True, "so the run crumbles and stretches from A to B")
print(f"{ok} checks passed")

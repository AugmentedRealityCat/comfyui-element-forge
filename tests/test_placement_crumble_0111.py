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
print(f"{ok} checks passed")

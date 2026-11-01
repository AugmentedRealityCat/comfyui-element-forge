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
DIRECT = "Particles: direct look (no LTX, pro)"
ok = 0


def check(cond, msg):
    global ok
    assert cond, msg
    ok += 1
    print("ok  ", msg)


an = importlib.import_module(pack.__name__ + ".element_forge.app_mode.nodes")
check("made_by" in an.EFAppEffect.INPUT_TYPES()["optional"], "the effect node has Made by")
check({"lightning climb", "energy A-B"} <= set(an.GUIDE_PRESETS), "every particle preset but the groups can be the start")
fl = an.apply_effect({}, {"effect_style": "fire/flame", "made_by": "particles"})
check(fl.get("Particles") is True and fl.get(DIRECT) is True and fl.get("Particle preset") == "fire",
      "an AI flame as particles only starts from its own particles (fire)")
sn = an.apply_effect({}, {"effect_style": "own/point", "made_by": "particles", "guide_particles": "snow"})
check(sn.get("Particle preset") == "snow" and sn.get(DIRECT) is True, "particles only from the chosen particles (snow)")
dr = an.apply_effect({}, {"effect_style": "smoke/rise_drawn", "made_by": "ai"})
check(dr.get(DIRECT) is False, "the AI on a drawn style: the particles guide it, no direct look")
sp = an.apply_effect({}, {"effect_style": "sparks/burst", "guide_particles": "embers"})
check(sp.get("Particle preset") == "embers", "a particle style starts from the chosen particles in Basic too")
same = an.apply_effect({}, {"effect_style": "sparks/burst", "made_by": "style default"})
check("Particles" not in same and DIRECT not in same and "Particle preset" not in same, "style default changes nothing")
check("Particle preset" not in an.apply_effect({}, {"effect_style": "fire/flame", "guide_particles": "snow"}),
      "chosen particles do nothing for an AI element without particles")
GUIDE = "Guide for the AI (particles / drawn path / object shape / none)"
gs = an.apply_effect({}, {"effect_style": "sparks/burst", "mode": "advanced", "guide": "object shape"})
check(gs.get(GUIDE) == "object shape" and "Particle preset" not in gs, "a particle style guided by the object's shape keeps its particles")
fm = an.apply_effect({}, {"effect_style": "sparks/burst", "mode": "advanced", "follows_motion": True})
check(fm.get("Follows motion") is True, "Follows motion counts for a particle style")
gp = an.apply_effect({}, {"effect_style": "fire/flame", "mode": "advanced", "guide": "particles"})
check(gp.get("Particles") is True and gp.get("Particle preset") == "fire", "an AI flame guided by particles starts from its own")
print(f"{ok} checks passed")

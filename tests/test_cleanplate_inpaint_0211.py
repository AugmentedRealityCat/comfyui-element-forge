import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PACK))
ok = 0
LORA = "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors"
SET = "Dissolve: clean plate with the inpaint LoRA (soft edge; off = Clean Plate LoRA)"


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


def load(name):
    return json.load(open(os.path.join(PACK, "api_workflows", name), encoding="utf-8"))


def ancestors(g, k, seen=None):
    seen = set() if seen is None else seen
    for v in g[k]["inputs"].values():
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] in g and v[0] not in seen:
            seen.add(v[0])
            ancestors(g, v[0], seen)
    return seen


settings = load("element_forge.settings.json")["settings"]
check(SET in settings and "Dissolve: inpaint mask grow (px)" in settings, "settings: the switch and the mask grow by name")
for name in ("element_forge", "element_forge_app", "element_forge_climb", "element_forge_dissolve"):
    g = load(name + ".json")
    k, field = settings[SET]
    check(g[k]["inputs"][field] is True, f"{name}: the inpaint way is on by default")
    diss = [i for i, nd in g.items() if nd.get("class_type") == "EFDissolve" and "clean_plate" in nd["inputs"]]
    check(len(diss) == 1, f"{name}: one dissolve takes a clean plate")
    sel = g[g[diss[0]]["inputs"]["clean_plate"][0]]
    check(sel["class_type"] == "ComfySwitchNode" and sel["inputs"]["switch"] == [k, 0], f"{name}: the clean plate goes through the switch")
    on, off = g[sel["inputs"]["on_true"][0]], sel["inputs"]["on_false"][0]
    check(on["class_type"] == "EFCleanPlateUncrop"
          and g[on["inputs"]["clean"][0]]["class_type"] == "LTXVLaplacianPyramidBlend",
          f"{name}: on = the blended inpaint crop back in the frame")
    up = ancestors(g, sel["inputs"]["on_true"][0])
    loras = {g[i]["inputs"].get("lora_name") for i in up if g[i]["class_type"] == "LTXICLoRALoaderModelOnly"}
    check(loras == {LORA} and any(g[i]["class_type"] == "LTXVInpaintPreprocess" for i in up),
          f"{name}: the inpaint branch uses only the In/Outpainting LoRA on the green-masked crop")
    old = ancestors(g, off) | {off}
    check(any(g[i]["class_type"] == "LTXICLoRALoaderModelOnly" and "clean-plate" in g[i]["inputs"]["lora_name"] for i in old),
          f"{name}: off = the Clean Plate LoRA as before")
    check(all(int(i) < 971 or int(i) > 994 for i in old), f"{name}: the old nodes keep their ids")

meta = load("element_forge_dissolve.inputs.json")
check(any(f.get("label", "").startswith("Clean plate with the inpaint LoRA") for f in meta["inputs"]) or
      any("inpaint LoRA" in json.dumps(f) for f in meta["inputs"]), "dissolve variant: the switch is one of its inputs")

import importlib.util
_spec = importlib.util.spec_from_file_location("ef_models", os.path.join(PACK, "element_forge", "app_mode", "models.py"))
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)
m = [x for x in M.MODELS if x["file"] == LORA]
check(len(m) == 1 and m[0]["folder"] == "loras" and m[0]["url"].endswith("/resolve/main/" + LORA), "the app lists the model with its link")
wf = json.load(open(os.path.join(PACK, "example_workflows", "Element Forge (app).json"), encoding="utf-8"))
check(any(x.get("name") == LORA for x in wf["models"]), "the app workflow names it for ComfyUI's missing-models dialog")
print(f"{ok} checks passed")

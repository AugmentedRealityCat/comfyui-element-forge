import importlib
import json
import math
import os
import sys
import tempfile
import types

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PACK))
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


from aiohttp import web

T = tempfile.mkdtemp(prefix="ef_test_licht_")
fp = types.ModuleType("folder_paths")
for name in ("get_output_directory", "get_temp_directory", "get_input_directory", "get_user_directory"):
    setattr(fp, name, lambda: T)
fp.get_annotated_filepath = lambda n: os.path.join(T, n)
sys.modules["folder_paths"] = fp
srv = types.ModuleType("server")
srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=web.RouteTableDef()))
sys.modules["server"] = srv
comfy = types.ModuleType("comfy")
cu = types.ModuleType("comfy.utils")
cu.ProgressBar = type("PB", (), {"__init__": lambda s, n: None, "update": lambda s, n=1: None, "update_absolute": lambda s, *a, **k: None})
mm = types.ModuleType("comfy.model_management")
mm.throw_exception_if_processing_interrupted = lambda: None
mm.soft_empty_cache = lambda: None
comfy.utils, comfy.model_management = cu, mm
sys.modules.update({"comfy": comfy, "comfy.utils": cu, "comfy.model_management": mm})
sys.modules[os.path.basename(PACK) + ".element_forge.bonsai.bonsai"] = types.ModuleType("bonsai")
importlib.import_module(os.path.basename(PACK))
L3 = importlib.import_module(os.path.basename(PACK) + ".element_forge.compositing.light3d")
TP = importlib.import_module(os.path.basename(PACK) + ".element_forge.compositing.temporal")
AN = importlib.import_module(os.path.basename(PACK) + ".element_forge.tracking.analysis")

d = torch.tensor([1.0, 0.5, 0.0])
lin, dis = L3.depth_to_z(d, 5.0, "linear"), L3.depth_to_z(d, 5.0, "disparity")
check(torch.allclose(lin, torch.tensor([1.0, 3.0, 5.0])), "linear: the reading before 02.11. (nearest 1, farthest = depth_range)")
check(abs(float(dis[0]) - 1) < 1e-6 and abs(float(dis[2]) - 5) < 1e-5 and abs(float(dis[1]) - 2 * 5 / 6) < 1e-5,
      f"disparity: same ends, the middle of the map is near ({float(dis[1]):.2f} instead of 3), as inverse depth is")

h, w = 40, 60
dep = torch.linspace(2.0, 10.0, w).repeat(h, 1)[None].repeat(2, 1, 1)
msk = torch.ones(2, h, w, dtype=torch.bool)
msk[:, :5] = False
dep[:, :5] = 1000.0
fx = 0.5 / math.tan(math.radians(70) / 2)
K = torch.tensor([[fx, 0, 0.5], [0, fx * w / h, 0.5], [0, 0, 1]], dtype=torch.float32)[None].repeat(2, 1, 1)
rng, fov = TP.EFMoGeNormals.scene([dep], [msk], [K], w, h)
check(4.4 < rng < 5.1 and abs(fov - 70) < 0.1, f"MoGe: far / near {rng} (2..10 m, sky out), fov {fov} along the longer side")
_, fov_p = TP.EFMoGeNormals.scene([dep], [msk], [K], h, w)
check(abs(fov_p - 2 * math.degrees(math.atan(0.5 / (fx * w / h)))) < 0.1, f"MoGe: portrait takes the height's field of view ({fov_p})")
check(TP.EFMoGeNormals.scene([], [], [], w, h) == (3.0, 65.0), "MoGe: nothing measured -> the node's defaults")
check(TP.EFMoGeNormals.RETURN_NAMES == ("normals", "depth_range", "fov"), "EF MoGe Normals gives the normals, depth range and fov")

H, W = 48, 64
plate = torch.full((1, H, W, 3), 0.3)
layer = torch.zeros(1, H, W, 3)
layer[:, 20:28, 28:36] = 2.0
depth = torch.zeros(1, H, W, 3)
depth[:, 16:32, 24:40] = 1.0
nrm_img = torch.zeros(1, H, W, 3)
nrm_img[..., 2] = 1.0
nrm_img = nrm_img * 0.5 + 0.5
node = L3.EFDepthLight()


def bg_light(depth_range, kind):
    out = node.light(plate, layer, depth, 1.0, depth_range, 65.0, 0.15, 0.25, False, 100.0, 1.0, albedo=plate,
                     normals_image=nrm_img, surface_detail=0.0, device="cpu", depth_kind=kind)[1]
    return float(out[0, 2:8, 2:12].mean()), float(out[0, 18:30, 26:38].mean())


bg_near, fg2 = bg_light(1.5, "disparity")
bg_far, fg10 = bg_light(10.0, "disparity")
check(bg_far < 0.3 * bg_near, f"a background far behind gets less light ({bg_far:.4f}) than one close behind ({bg_near:.4f})")
check(abs(fg10 - fg2) < 0.25 * fg2, "the near surface under the element keeps its light")
bg_lin, _ = bg_light(1.5, "linear")
check(0.9 < bg_near / bg_lin < 1.0, f"depth 0 or 1 only: same geometry; disparity counts distances in the light's own distance "
      f"from the camera (0.98 here), so a little less light ({bg_near / bg_lin:.3f})")
check("depth_kind" in L3.EFDepthLight.INPUT_TYPES()["optional"]
      and L3.EFDepthLight.INPUT_TYPES()["optional"]["depth_kind"][1]["default"] == "linear",
      "Depth Light: depth_kind optional, linear by default (old workflows stay as they were)")

clip = "licht.mp4"
os.makedirs(os.path.join(T, "input"), exist_ok=True)
open(os.path.join(T, clip), "wb").write(b"x" * 10)
fr = torch.rand(3, 8, 8, 3)
AN.EFSaveAnalysis().save(clip, fr, 24.0, normals=fr, depth_range=6.25, fov=58.5)
img, r_, f_ = AN.EFLoadAnalysis().load(clip, "normals", 3)
check(img.shape == fr.shape and (r_, f_) == (6.25, 58.5), "kept analysis: the normals come back with the shot's depth range and fov")
info = AN.analysis_info(clip, 3)
info.pop("scene")
json.dump(info, open(os.path.join(AN.clip_folder(clip), "analysis.json"), "w"))
check(AN.EFLoadAnalysis().load(clip, "normals", 3)[1:] == (2.0, 65.0), "kept before 02.11.: the values the app had then")

for name in ("element_forge", "element_forge_app", "element_forge_climb", "element_forge_dissolve"):
    g = json.load(open(os.path.join(PACK, "api_workflows", name + ".json"), encoding="utf-8"))
    lights = [nd for nd in g.values() if isinstance(nd, dict) and nd.get("class_type") == "EFDepthLight"]
    check(len(lights) == 2 and all(nd["inputs"]["depth_range"] == ["409", 1] and nd["inputs"]["fov"] == ["409", 2]
                                   and nd["inputs"]["depth_kind"] == "disparity" and g["409"]["class_type"] == "EFMoGeNormals"
                                   for nd in lights),
          f"{name}: both lights take the measured depth range and fov and read the depth as disparity")
print(f"{ok} checks passed")

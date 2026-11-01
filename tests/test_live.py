import importlib
import json
import os
import struct
import sys
import tempfile
import types

import numpy as np
from aiohttp import web

S = tempfile.mkdtemp(prefix="ef_test_live_")
fp = types.ModuleType("folder_paths")
for name in ("get_output_directory", "get_temp_directory", "get_input_directory", "get_user_directory"):
    setattr(fp, name, lambda: S)
fp.get_annotated_filepath = lambda n: os.path.join(S, n)
sys.modules["folder_paths"] = fp
srv = types.ModuleType("server")
srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=web.RouteTableDef()))
sys.modules["server"] = srv
comfy = types.ModuleType("comfy")
cu = types.ModuleType("comfy.utils")
cu.ProgressBar = type("PB", (), {"__init__": lambda s, n: None, "update": lambda s, n=1: None, "update_absolute": lambda s, *a, **k: None})
mm = types.ModuleType("comfy.model_management")
mm.throw_exception_if_processing_interrupted = lambda: None
comfy.utils, comfy.model_management = cu, mm
sys.modules.update({"comfy": comfy, "comfy.utils": cu, "comfy.model_management": mm})
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
sys.modules[os.path.basename(PACK) + ".element_forge.bonsai.bonsai"] = types.ModuleType("bonsai")
pack = importlib.import_module(os.path.basename(PACK))
LV = importlib.import_module(os.path.basename(PACK) + ".element_forge.app.live")
PN = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.particles_node")
pt = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.particles")
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


inp = {"plate": ["167", 0], "seed": ["805", 0], "speed": 1.0, "settings": ["229", 0], "track": ["209", 0]}
sigs = {"167": "p", "805": "s42", "229": "set", "209": "tr"}
k0 = LV.sim_key(inp, sigs, {"gravity*": 1.0}, "play", 0, 10)
check(LV.sim_key(inp, sigs, {"gravity*": 1.0, "colors": [[0, [0, 0, 1]], [1, [0, 0, 1]]], "glow": 2.0, "blob": 8, "trail": 3}, "play", 0, 10) == k0,
      "key: colours, glow, merge and trail only change the look (no new simulation)")
check(LV.sim_key(inp, sigs, {"gravity*": 2.0}, "play", 0, 10) != k0, "key: gravity simulates again")
check(LV.sim_key(inp, {**sigs, "805": "s7"}, {"gravity*": 1.0}, "play", 0, 10) != k0, "key: another particle seed simulates again")
check(LV.sim_key({**inp, "speed": 2.0}, sigs, {"gravity*": 1.0}, "play", 0, 10) != k0, "key: speed simulates again")
check(LV.sim_key(inp, sigs, {"gravity*": 1.0}, "play", 40, 6) == k0, "key: frame and seconds do not count in Play with clip")
fin = {"gravity*": 1.0, "final": {"colors": [[0, [1, 0, 0]], [1, [1, 0, 0]]], "glow": 3.0, "blob": 12}}
check(LV.sim_key(inp, sigs, fin, "play", 0, 10) == k0, "key: the emitter panel's look values draw again without a new simulation")
check(LV.sim_key(inp, sigs, {"gravity*": 1.0, "final": {"gravity": 50.0}}, "play", 0, 10) != k0, "key: the emitter panel's gravity simulates again")
check(LV.sim_key(inp, sigs, {"gravity*": 1.0}, "hold", 40, 10) != LV.sim_key(inp, sigs, {"gravity*": 1.0}, "hold", 41, 10),
      "key: in Hold frame the held frame counts")
import inspect
import re
read = set()
for fn in (pt.simulate, pt.make_paths, pt.Emitter.__init__, pt.Emitter.sample):
    read |= set(re.findall(r'P(?:\.get\(|\[)"([a-z_]+)"', inspect.getsource(fn)))
check(read and not (LV.LOOK & read), f"look-only keys: none is read by simulate, make_paths or the emitter ({len(read)} keys read there)")

tr = {"point_track_px": [[float(i), 2.0 * i] for i in range(5)], "crop_origin_plate_px": [[i, i] for i in range(5)], "fps": 30.0, "roi": [64, 64]}
h = LV.hold_track(tr, 3, 7)
check(h["point_track_px"] == [[3.0, 6.0]] * 7 and h["crop_origin_plate_px"] == [[3, 3]] * 7 and h["fps"] == 30.0 and h["roi"] == [64, 64],
      "hold: the track stands on frame 3 for 7 frames, other values unchanged")
d = np.arange(4 * 3 * 2, dtype=np.float32).reshape(4, 3, 2)
check(np.array_equal(LV.held(d, 2, 5)[4], d[2]) and LV.held(d, 9, 5).shape == (5, 3, 2), "hold: frame 2 seen 5 times; a frame past the end takes the last")
one = LV.held_one(d, 2)
check(one.shape == (1, 3, 2) and one.flags["C_CONTIGUOUS"] and pt.Depth(one, 2, 3).at(250, np.array([1.0]), np.array([2.0]))[0] == d[2, 2, 1],
      "hold: one depth map for every frame (pt.Depth takes the last map later), nothing repeated in memory")

H, W, n = 90, 160, 12
plate = np.full((n, H, W, 3), 0.3, np.float32)
args = dict(plate=plate, preset="snow", emitter="whole frame", amount=1.0, speed=1.0, size=1.0, life=1.0, direction=-1.0, spread=-1.0,
            follow=-1.0, start_seconds=0.0, fps=12.0, seed=5)
s0 = PN.setup(**args, settings={"preroll": 0.0}, cam=pt.Camera(n))
s3 = PN.setup(**args, settings={"preroll": 3.0}, cam=pt.Camera(n))
check(LV.preroll_seconds(s0["P"], s0["em"]) == 0.0 and LV.preroll_seconds(s3["P"], s3["em"]) == 3.0, "pre-roll in seconds: 0 and 3 as set")
sa = PN.setup(**args, settings={"preroll": -1.0}, cam=pt.Camera(n))
check(0 < LV.preroll_seconds(sa["P"], sa["em"]) <= 60, f"pre-roll auto: {LV.preroll_seconds(sa['P'], sa['em']):.2f} s from the engine's formula")
a0, a3 = LV.encode(s0, s0["P"]), LV.encode(s3, s3["P"])
f0, f3 = int(a0["offs"][1]), int(a3["offs"][1])
check(f3 > f0, f"pre-roll 3 s: {f3} flakes in the first frame, without it {f0}")
head = {"key": "k", "n": n, "fps": 12.0, "W": W, "H": H}
buf = LV.pack(head, a3)
hl = struct.unpack("<I", buf[:4])[0]
back = json.loads(buf[4:4 + hl])
arr = {t["name"]: np.frombuffer(buf, dtype=t["type"], count=t["length"], offset=4 + hl + t["offset"]) for t in back["arrays"]}
check(hl % 4 == 0 and all(t["offset"] % 4 == 0 for t in back["arrays"]), "answer: header and arrays on 4-byte borders (typed arrays in the page)")
check(all(np.array_equal(arr[k], a3[k]) for k in a3), "answer: every array reads back unchanged")
i = 5
fin = np.nonzero(np.isfinite(s3["rec"]["x"][i]))[0]
ids = arr["id"][arr["offs"][i]:arr["offs"][i + 1]]
check(set(ids.tolist()) <= set(fin.tolist()) and np.all(np.diff(ids.astype(np.int64)) > 0), "frame 5: only living particles, sorted by id (the page finds trails by id)")
j = int(arr["offs"][i])
pid = int(arr["id"][j])
check(abs(arr["x"][j] / 8 - s3["rec"]["x"][i, pid]) <= 1 / 16 + 1e-6 and abs(arr["y"][j] / 8 - s3["rec"]["y"][i, pid]) <= 1 / 16 + 1e-6,
      "position in 1/8 px: at most 1/16 px off")
check(LV.pack(head, None)[4:].strip().startswith(b"{") and b'"arrays": []' in LV.pack(head, None), "answer without arrays: the page has this simulation")
import cv2
DS = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.dissolve")
H, W, n = 72, 96, 14
yy, xx = np.mgrid[0:H, 0:W]
plate = np.stack([np.stack([xx / W, yy / H, np.full_like(xx, 0.4, dtype=np.float64)], -1)] * n).astype(np.float32)
masks = np.stack([((xx - 48) ** 2 + (yy - 36) ** 2 < 22 ** 2).astype(np.float32)] * n)
P, _ = DS.node_params(1.0, 1.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 0.0, 0.0, "plain", "", "inpaint per frame")
run = DS.dissolve(plate, masks, 90.0, 0.1, 0.6, 12.0, 3, dict(P), None, None)
rec = {}
DS.dissolve(plate, masks, 90.0, 0.1, 0.6, 12.0, 3, dict(P), None, None, record=rec)
same = len(rec["frames"]) == n and len(rec["gone"]) == n
worst = 0.0
for i, (pid, x, y, c, a) in enumerate(rec["frames"]):
    acc = DS.splat(n, x, y, c, a, H, W)
    if rec["blur"] > 0.35:
        acc = cv2.GaussianBlur(acc, (0, 0), rec["blur"])
    worst = max(worst, float(np.abs(np.clip(acc[..., 3], 0, 1) - run["particles_alpha"][i]).max()))
check(same and worst < 1e-5 and run["stats"]["spawned"] > 0, f"dissolve: the recorded particles redrawn give the run's layer (largest difference {worst:.1e})")
g = rec["gone"][-1].astype(np.float32) / 255
ref = cv2.resize(run["dissolve_mask"][-1], (W // 4, H // 4), interpolation=cv2.INTER_AREA)
check(np.abs(g - ref).max() <= 1 / 255 + 1e-6 and g.max() > 0.5, "dissolve: the gone part of the object, a quarter of the size, as in the run")
box = LV.mask_box(rec)
enc = LV.encode_dissolve(rec, box)
bx, by, bw, bh = box
full = np.zeros((n, H // 4, W // 4), np.uint8)
full[:, by:by + bh, bx:bx + bw] = enc["gone"].reshape(n, bh, bw)
check(len(enc["offs"]) == n + 1 and len(enc["col"]) == 3 * int(enc["offs"][-1]) and np.array_equal(full, np.stack(rec["gone"]))
      and bw * bh < (H // 4) * (W // 4), f"dissolve answer: per frame particles with colour, the masks of every frame inside box {box} only")
import asyncio


async def _no_mask(graph, nid, cls, ctx):
    return None, {"plate": [np.zeros((2, 8, 8, 3), np.float32)], "mask": None, "fps": [24.0]}, {}
LV.RUNNER.prepare, _prep = _no_mask, LV.RUNNER.prepare
sys.modules.setdefault("nodes", types.SimpleNamespace(NODE_CLASS_MAPPINGS={}))
sys.modules["nodes"].NODE_CLASS_MAPPINGS.setdefault("EFDissolve", object)
try:
    asyncio.run(LV.compute_dissolve({"9": {"inputs": {}}}, {}, {"sigs": {}, "check": lambda: None, "left_out": [], "times": {}}, 0.0, "9"))
    check(False, "dissolve preview without a mask: a hint")
except ValueError as e:
    check("track it first" in str(e), "dissolve preview without a mask: the hint to track first, not a cv2 error")
LV.RUNNER.prepare = _prep

emc = types.SimpleNamespace(n=6, fps=6.0, W=320, H=200, cam=pt.Camera(6), depth=None, z=np.full(6, 0.5),
                            a=np.tile([[160.0, 100.0]], (6, 1)))
Pc = {**pt.BASE, **pt.PRESETS["frost"], "start": 0.0, "crack_seeds": 1}
try:
    pc = pt.make_paths(Pc, emc, 3)
    tab, mats = LV.compact_cracks(pc, emc, 6)
    rows = tab.reshape(-1, 7)
    per_frame = [sum(len(np.asarray(x[0])) for x in pc[i] if np.asarray(x[0]).ndim == 3) for i in range(6)]
    check([int((rows[:, 0] <= i).sum()) for i in range(6)] == per_frame, "compact cracks: every frame draws the segments it had")
    check(len(mats) == 36 and np.all(np.diff(rows[:, 0]) >= 0), "compact cracks: sorted by first frame, a camera per frame")
    old = sum(9 * n_ for n_ in per_frame) * 4
    check(tab.nbytes + mats.nbytes < old or old < 2000, f"compact cracks: {tab.nbytes + mats.nbytes} bytes instead of {old}")
except (KeyError, AttributeError, TypeError) as e:
    check(False, f"compact cracks: the crack paths ran ({e})")

rng = np.random.default_rng(1)
N, CAP = 20, 30
recs = {k: rng.uniform(0, 100, (N, CAP)).astype(np.float32) for k in ("x", "y", "z", "vx", "vy", "size", "rot")}
recs["alpha"], recs["vis"], recs["age"] = (rng.uniform(0.2, 1, (N, CAP)).astype(np.float32) for _ in range(3))
recs["x"][rng.uniform(size=(N, CAP)) < 0.3] = np.nan
stt = {"rnd": rng.uniform(size=CAP)}
emf = types.SimpleNamespace(n=N, W=320, H=200, zref=0.5)
Pd = {"dof": 0}
whole = LV.encode({"rec": {**recs, "rnd": stt["rnd"]}, "em": emf, "paths": None}, Pd)
got = []
LV.STREAM.emit = got.append
LV.PART_GAP = 0.0
send = LV._part_sender({"W": 320, "H": 200}, Pd, True, LV.STREAM.emit)
for i in range(N):
    send(i, recs, stt, CAP)
LV.STREAM.emit = None
check(len(got) >= 2, f"stream: {len(got)} parts while the frames are simulated")
sent = LV.STREAM.sent
rest = LV.frames_from(whole, sent)
ids = []
for b in got:
    n_ = struct.unpack("<I", b[:4])[0]
    hd = json.loads(b[4:4 + n_])
    tab = {t["name"]: t for t in hd["arrays"]}
    t = tab["id"]
    ids.append(np.frombuffer(b, np.uint32, t["length"], 4 + n_ + t["offset"]))
ids.append(rest["id"])
check(np.array_equal(np.concatenate(ids), whole["id"]), "stream: the parts and the rest are the whole answer")
check(int(rest["offs"][0]) == 0 and len(rest["offs"]) == N - sent + 1, "stream: the rest starts at its first frame")
print(f"{ok} checks passed")

import importlib.util
import json
import math
import os
import re

import cv2
import numpy as np

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ef_particles", os.path.join(PACK, "element_forge/simulation/particles.py"))
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


N, FPS, W, H = 49, 24.0, 480, 270
KEYS = ("scene_height", "gravity_end", "speed_by_size", "sway", "sway_hz", "flicker_duty", "roll", "crack_angle",
        "crack_angle_var", "crack_pairs")


def sim(preset, over, n=N, seed=2):
    P = pt.params(preset, over)
    em = pt.Emitter("point A", n, FPS, W, H, P, np.random.default_rng(1), a=(240, 200))
    return pt.simulate(P, em, seed=seed), P


one = dict(rate=0.0, burst=40, burst_at=0.0, speed=0.0, speed_var=0.0, spread=0.0, drag=0.0, turbulence=0.0, inherit=0.0,
           radius=0.0, life=2.0, life_var=0.0, fine_share=0.0, children=None, collide="none")
check(all(k in pt.BASE for k in KEYS) and pt.BASE["gravity_end"] == 1.0 and pt.BASE["roll"] == 0.0 and pt.BASE["sway"] == 0.0,
      "the new keys are in BASE and off by default")
up, _ = sim("embers", {**one, "gravity": -150.0, "gravity_end": 1.0})
tip, _ = sim("embers", {**one, "gravity": -150.0, "gravity_end": -1.0})
y_up, y_tip = np.nanmean(up["y"][40]), np.nanmean(tip["y"][40])
check(y_tip > y_up + 20, f"gravity_end -1: the lift tips into falling, it ends lower ({y_tip:.0f} against {y_up:.0f} px)")
vy_end = np.nanmean(tip["vy"][40])
check(vy_end > np.nanmean(up["vy"][40]) and abs(np.nanmean(tip["vy"][3]) - np.nanmean(up["vy"][3])) < 3,
      "gravity_end: as at birth at first, the lift slows later")
slow, _ = sim("sparks", {**one, "gravity": 900.0})
real, _ = sim("sparks", {**one, "gravity": 900.0, "scene_height": 2.0})
rise, _ = sim("smoke", {**one, "gravity": -130.0, "scene_height": 2.0})
same, _ = sim("smoke", {**one, "gravity": -130.0})
check(np.nanmean(real["y"][10]) > np.nanmean(slow["y"][10]) + 30, "scene_height 2 m: what falls falls at the real 9.81 m/s²")
check(np.allclose(np.nan_to_num(rise["y"]), np.nan_to_num(same["y"])), "scene_height: rising things keep their gravity")
sz, _ = sim("rain", {**one, "speed": 600.0, "size_var": 0.8, "speed_by_size": 1.0, "gravity": 0.0, "direction": 180.0})
v = np.hypot(sz["vx"][4], sz["vy"][4])
s = sz["size"][4]
m = np.isfinite(sz["x"][4]) & (s > 0)
check(np.corrcoef(s[m], v[m])[0, 1] > 0.9, "speed_by_size 1: the bigger, the faster")
calm, _ = sim("snow", {**one, "speed": 100.0, "direction": 180.0, "gravity": 0.0})
sw, _ = sim("snow", {**one, "speed": 100.0, "direction": 180.0, "gravity": 0.0, "sway": 30.0, "sway_hz": 1.0})
dx = np.nan_to_num(sw["x"] - calm["x"])
amp = 30.0 * min(W, H) / pt.REF
check(np.abs(dx).max() > amp and np.abs(dx).max() <= 2 * amp + 0.5 and np.array_equal(np.nan_to_num(sw["y"]), np.nan_to_num(calm["y"])),
      f"sway 30 px: each swings sideways on its own, falling as before (max {np.abs(dx).max():.0f} px)")
check(np.std(dx[12]) > 0.3 * amp, "sway: each its own phase, not all together")
fl, _ = sim("fireflies", {**one, "flicker": 1.0, "flicker_hz": 1.0, "flicker_duty": 0.15, "fade_in": 0.0, "fade_out": 0.0})
al = fl["alpha"][:, :40]
dark = float((al < 0.05).mean())
check(0.7 < dark < 0.95, f"flicker_duty 0.15: dark most of the time, a short flash each beat ({dark:.2f} of the frames dark)")
check("flicker_duty" in pt.LOOK_ONLY, "flicker_duty is look only (the live preview redraws without a new simulation)")
blast = {**one, "burst": 300, "speed": 400.0, "spread": 180.0, "drag": 3.0, "gravity": -300.0, "radius": 10.0, "roll": 0.0}
flat, _ = sim("explosion", blast)
rl, _ = sim("explosion", {**blast, "roll": 1500.0})
cx = np.nanmean(rl["x"][30])
side = np.abs(rl["x"][30] - cx) > np.nanstd(rl["x"][30])
mid = np.abs(rl["x"][30] - cx) < 0.5 * np.nanstd(rl["x"][30])
check(np.nanmean(rl["vy"][30][mid]) < np.nanmean(rl["vy"][30][side]),
      "roll: up in the middle, down at the sides (a vortex ring)")
check(not np.allclose(np.nan_to_num(flat["x"]), np.nan_to_num(rl["x"])), "roll 0 = off")
pop, _ = sim("sparks", {**one, "speed": 300.0, "life": 1.0,
                        "children": dict(at_age=0.4, chance=1.0, count=4, speed=200.0, spread=180.0, life=0.1, size=0.5)})
npar = pop["stats"]["spawned"]
check(pop["stats"]["children"] == 4 * npar, f"children at_age: each spark bursts once in mid-air ({pop['stats']['children']} = {npar} x 4)")
bc = pop["born"][npar:]
check(np.allclose(bc, 0.4, atol=1.5 / (FPS * 2)), "children at_age 0.4: born at 0.4 of the life")
half, _ = sim("sparks", {**one, "speed": 300.0, "life": 1.0,
                         "children": dict(at_age=0.4, chance=0.5, count=4, speed=200.0, spread=180.0, life=0.1, size=0.5)})
check(0.25 * npar < half["stats"]["children"] / 4 < 0.75 * npar,
      f"children chance 0.5: about half burst ({half['stats']['children'] // 4} of {npar})")
none, _ = sim("sparks", {**one, "children": dict(count=4, speed=200.0)})
check(none["stats"]["children"] == 0, "without at_age: children only where one hits (as before)")


def crack_angles(over):
    P = pt.params("cracks", over)
    em = pt.Emitter("point A", N, FPS, W, H, P, np.random.default_rng(1), a=(240, 135))
    paths = pt.make_paths(P, em, 3)
    segs = np.concatenate([np.asarray(p[0]) for p in paths[-1]])
    return len(segs)


check(crack_angles({"crack_pairs": 1.0, "crack_branch": 0.2}) > crack_angles({"crack_pairs": 0.0, "crack_branch": 0.2}),
      "crack_pairs 1: more branches (one to each side)")
P = pt.params("cracks", {})
check(abs(P["crack_angle"] - 0.47) < 1e-9 and pt.params("frost", {})["crack_pairs"] == 1.0, "cracks 27°, frost in pairs (research)")
S = dict(path="strike", burst_at=0.5, strike_strokes=3, strike_gap=0.06, strike_decay=0.012, branches=4)


def lit(over):
    P = pt.params("lightning", {**S, **over})
    em = pt.Emitter("point A", N, FPS, W, H, P, np.random.default_rng(1), a=(240, 240))
    return pt.make_paths(P, em, 3)


base = lit({})
hold = lit({"strike_hold": 0.2, "strike_hold_level": 0.3})
check(sum(1 for f in hold if f) > sum(1 for f in base if f) + 2, "strike_hold: the channel glows on after the strokes")
gaps = lit({"strike_new_ground": 1.0})
ends = {tuple(np.round(p[0][-1])) for f in gaps for p in f if len(p[0]) > 10}
check(len(ends) >= 2, "strike_new_ground 1: the second stroke lands beside the first")
st = lit({"strike_streamer": 40.0})
i_b = int(round(0.5 * FPS))
check(len(st[i_b - 1]) > len(base[i_b - 1]), "strike_streamer: a streamer rises from A in the last leader frame")
one_fr = lit({"strike_strokes": 1})
peak = max(float(op.max()) for _, _, op, _ in one_fr[i_b])
after = max([float(op.max()) for _, _, op, _ in one_fr[i_b + 1]] or [0.0])
check(peak > 0.9 and after < 0.6, f"a stroke fills its own frame, the next only its afterglow ({peak:.2f} -> {after:.2f})")
E = pt.params("explosion", {})
check(E["drag"] == 6.0 and E["gravity"] < -1000 and E["gravity_end"] < 1 and E["roll"] > 0, "explosion: brakes by drag, rises, rolls")
check(pt.params("sparks", {})["children"]["at_age"] > 0 and pt.params("snow", {})["sway"] > 0
      and pt.params("fireflies", {})["flicker_duty"] > 0 and pt.params("embers", {})["gravity_end"] < 0, "presets after the research")
for name in pt.PRESETS:
    pt.params(name, {"gravity_end": 0.5, "sway": 10.0, "roll": 100.0, "speed_by_size": 0.5, "flicker_duty": 0.2, "scene_height": 3.0})
check(True, "every preset takes every new key (one engine)")
check(pt.BASE["scale"] == 1.0, "scale is 1 by default")
full, _ = sim("explosion", {**one, "speed": 600.0, "spread": 180.0})
far, _ = sim("explosion", {**one, "speed": 600.0, "spread": 180.0, "scale": 0.3})
dist = lambda r, i: np.nanmean(np.hypot(r["x"][i] - 240, r["y"][i] - 200))
k = dist(far, 6) / dist(full, 6)
check(0.25 < k < 0.35 and np.isfinite(far["x"][2]).sum() == np.isfinite(full["x"][2]).sum(),
      f"scale 0.3: the same burst at {k:.2f} of the size, born at the same time")
side, Ps = sim("explosion side", {"rate": 0.0, "burst": 60, "burst_at": 0.0, "turbulence": 0.0, "direction": 90.0})
dx = np.nanmean(side["x"][6]) - 240
check(Ps["spread"] < 90 and dx > 40, f"explosion side: a cone along the arrow (right {dx:.0f} px)")
live = open(os.path.join(PACK, "element_forge/app/live.py"), encoding="utf-8").read()
js = open(os.path.join(PACK, "web/efa/emitter.js"), encoding="utf-8").read()
miss = [k for k in KEYS + ("strike_hold", "strike_hold_level", "strike_new_ground", "strike_streamer")
        if f'"{k}"' not in live or not re.search(rf'key\("{k}"', js)]
check(not miss, f"the panel shows and sends every new key ({miss})")
check('splash("at_age"' in js and 'splash("chance"' in js, "the panel has the splash's mid-air burst")
src = open(os.path.join(PACK, "element_forge/simulation/dissolve.py"), encoding="utf-8").read()
ns = {"math": math, "json": json, "cv2": cv2, "np": np}
exec(src[src.index("def soft_uncrop"):src.index("class EFCleanPlateUncrop")], ns)
yy, xx = np.mgrid[0:270, 0:480]
plate = np.stack([0.3 + 0.4 * xx / 480, 0.5 + 0 * xx, 0.2 + 0.3 * yy / 270], -1).astype(np.float32)[None].repeat(2, 0)
mask = ((xx - 240) ** 2 + (yy - 135) ** 2 < 40 ** 2).astype(np.float32)[None].repeat(2, 0)
box = (160, 60, 320, 210)
clean = (plate[:, 60:210, 160:320] + 0.15).astype(np.float32)
hard = ns["soft_uncrop"](plate.copy(), clean, box)
soft = ns["soft_uncrop"](plate.copy(), clean, box, mask, 0.012, 1.0)
out = mask[0] < 0.5
check(np.abs(hard - plate)[:, out].max() > 0.14, "uncrop without the mask: the whole box as before (its edge shows)")
check(np.abs(soft - plate)[:, out].max() < 1e-4, "uncrop with the mask: outside the hole the clip stays as it is")
check(np.abs(soft - plate)[:, mask[0] > 0.5].mean() < 0.06, "uncrop: the clean plate's colours are matched to the plate around the hole")
gx = np.abs(np.diff(soft[0, 135, 150:330, 0]))
check(gx.max() < 0.05, f"uncrop: no hard step at the hole's edge (largest step {gx.max():.3f})")
print(f"{ok} checks passed")

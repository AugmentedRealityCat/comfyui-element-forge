import importlib.util
import os
import sys

import numpy as np

PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("ef_particles", os.path.join(PACK, "element_forge/simulation/particles.py"))
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)
n = bad = 0


def check(cond, name):
    global n, bad
    n += 1
    bad += not cond
    print("ok  " if cond else "FAIL", name)


N, FPS, W, H = 48, 24.0, 400, 300
STILL = {"point_track_px": [[200, 200]] * N}


def alive(rec):
    return np.isfinite(rec["x"]) & (rec["alpha"] > 0)


def run(preset, over=None, seed=1):
    P = pt.params(preset, over)
    em = pt.Emitter("point A", N, FPS, W, H, P, np.random.default_rng(1), a=STILL)
    return pt.simulate(P, em, seed=seed), P


def speeds(rec, lo, hi):
    v = np.hypot(rec["vx"], rec["vy"])
    age = rec["age"]
    m = alive(rec) & (age >= lo) & (age < hi)
    return v[m]


base, _ = run("magic dust")
same, _ = run("magic dust", {"spread_falloff": 0.0, "speed_end": 1.0, "max_speed": 0.0, "turb_fade": 0.3, "turb_drag": 0.0})
check(all(np.array_equal(base[k], same[k], equal_nan=base[k].dtype.kind == "f") for k in base if isinstance(base[k], np.ndarray)),
      "all off: the same particles as the preset")

calm = {"turbulence": 0.0, "gravity": 0.0, "drag": 0.0, "fine_share": 0.0, "children": None}
r1, _ = run("sparks", {**calm, "speed_end": 1.0})
r2, _ = run("sparks", {**calm, "speed_end": 0.2})
s1, s2 = np.median(speeds(r1, 0.8, 1.0)), np.median(speeds(r2, 0.8, 1.0))
check(s2 < 0.45 * s1, f"speed_end 0.2: slow at the end of the life ({s2:.0f} against {s1:.0f} px/s)")
y1, y2 = np.median(speeds(r1, 0.0, 0.1)), np.median(speeds(r2, 0.0, 0.1))
check(y2 > 0.8 * y1, f"speed_end 0.2: as fast at birth ({y2:.0f} against {y1:.0f} px/s)")

r3, P3 = run("sparks", {**calm, "max_speed": 300.0})
ps = min(W, H) / pt.REF
top = np.nanmax(speeds(r3, 0.0, 1.01))
check(top <= 300.0 * ps * 1.6 + 1e-6, f"max_speed 300: no particle much faster on screen ({top:.0f} px/s, limit {300 * ps:.0f} at this size)")
check(np.nanmax(speeds(r1, 0.0, 1.01)) > top * 1.5, "without the limit they are faster")


def angles(rec):
    a = np.degrees(np.arctan2(rec["vx"], -rec["vy"]))
    return a[alive(rec) & (rec["age"] < 0.15)]


r4, _ = run("sparks", {**calm, "spread": 60.0})
r5, _ = run("sparks", {**calm, "spread": 60.0, "spread_falloff": 1.0})
check(np.std(angles(r5)) < 0.7 * np.std(angles(r4)), f"spread_falloff 1: the directions bunch to the axis (std {np.std(angles(r5)):.1f}° against {np.std(angles(r4)):.1f}°)")
check(np.max(np.abs(angles(r5))) <= 61.0, "spread_falloff keeps the cone")

r6, _ = run("smoke", {"spin": 0.0})
def turns(r):
    same_p = alive(r)[1:] & alive(r)[:-1] & (r["age"][1:] > r["age"][:-1])
    return np.abs(np.diff(r["rot"], axis=0))[same_p]


check(np.max(turns(r6)) < 1e-9, "spin 0: the particles do not turn")
r7, _ = run("smoke", {"spin": 360.0})
r8, _ = run("smoke")
turn = lambda r: np.median(turns(r))
check(turn(r7) > 2.5 * turn(r8), f"spin 360: turn faster than the preset ({turn(r7):.3f} against {turn(r8):.3f} rad per frame)")


def jitter(rec):
    a = np.unwrap(np.arctan2(rec["vx"], rec["vy"]), axis=0)
    d = np.abs(np.diff(a, axis=0))
    return np.nanmean(d)


r9, _ = run("fireflies")
r10, _ = run("fireflies", {"turb_drag": 1.0, "drag": 1.5})
r11, _ = run("fireflies", {"drag": 1.5})
check(jitter(r10) < 0.8 * jitter(r11), f"turb_drag 1: the drag calms the swirl too ({jitter(r10):.3f} against {jitter(r11):.3f})")
r12, _ = run("fireflies", {"turb_fade": 0.5})
young = lambda r: np.nanmean(np.abs(np.diff(np.unwrap(np.arctan2(r["vx"], r["vy"]), axis=0), axis=0))[(r["age"][1:] < 0.1)])
check(young(r12) < young(r9), "turb_fade 0.5: calm while young")

print(f"{n - bad}/{n} passed")
sys.exit(1 if bad else 0)

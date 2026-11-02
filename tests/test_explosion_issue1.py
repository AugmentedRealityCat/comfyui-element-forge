import importlib.util
import json
import os

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


N, FPS, W, H = 81, 20.0, 400, 300


def run(preset, over=None, seed=1):
    P = pt.params(preset, over)
    em = pt.Emitter("point A", N, FPS, W, H, P, np.random.default_rng(seed), a=(200, 150))
    return pt.simulate(P, em, seed=seed), P


f = pt.rate_curve_at
check(f([], 0.3) == 1.0, "no curve: an even rate")
c = [[0.0, 1.0], [0.5, 0.0], [1.0, 0.5]]
check(f(c, 0.0) == 1.0 and abs(f(c, 0.25) - 0.5) < 1e-9 and f(c, 0.5) == 0.0 and abs(f(c, 0.75) - 0.25) < 1e-9, "straight between the points")
check(f(c, -1) == 1.0 and f(c, 2) == 0.5 and f([[0.2, 3.0]], 0.5) == 1.0, "flat outside, never above 1")
check(abs(f([[0.7, 0.0], [0.1, 1.0]], 0.4) - 0.5) < 1e-9, "points in any order")

base = dict(rate=400.0, life=0.2, life_var=0.0, preroll=0.0, turbulence=0.0)
even, _ = run("embers", base)
half, _ = run("embers", {**base, "rate_curve": [[0.0, 1.0], [0.5, 1.0], [0.501, 0.0]]})
n_even, n_half = even["stats"]["spawned"], half["stats"]["spawned"]
check(abs(n_half - n_even / 2) <= 0.03 * n_even, f"a curve that stops halfway gives half the particles ({n_half} of {n_even})")
check(np.nanmax(half["born"]) <= 2.05, f"none born after the curve drops to 0 (last at {np.nanmax(half['born']):.2f} s)")
late, _ = run("embers", {**base, "start": 1.0, "rate_curve": [[0.0, 0.0], [0.499, 0.0], [0.5, 1.0]]})
check(np.nanmin(late["born"]) >= 2.45, f"the curve spans start to the clip's end (first at {np.nanmin(late['born']):.2f} s, start 1 s)")
pulse, _ = run("embers", {**base, "end": 2.0, "rate_curve": [[0.0, 0.0], [0.25, 1.0], [0.5, 0.0], [0.75, 1.0], [1.0, 0.0]]})
b = pulse["born"]
check(np.nanmax(b) <= 2.05 and ((b > 0.9) & (b < 1.1)).sum() < ((b > 0.4) & (b < 0.6)).sum() / 3,
      "with an end the curve spans start to end: two pulses, nothing in between")
again, _ = run("embers", {**base, "rate_curve": [[0.0, 1.0], [0.5, 1.0], [0.501, 0.0]]})
check(np.array_equal(np.nan_to_num(half["x"]), np.nan_to_num(again["x"])), "same curve and seed, same particles")

ex, Pe = run("explosion", {"preroll": 0.0})
be = ex["born"]
first = (be < 0.5).sum() / max(1, np.isfinite(be).sum())
check(first > 0.8, f"an explosion fires most of its particles at once ({first:.0%} in the first 0.5 s of a 4 s effect)")
check(Pe["spread"] >= 180 and Pe["drag"] > 1 and Pe["burst"] > 0, "in all directions, braking hard, with a first flash")
x0, y0 = ex["x"][3], ex["y"][3]
m = np.isfinite(x0)
ang = np.degrees(np.arctan2(y0[m] - 150, x0[m] - 200))
hist = np.histogram(ang, bins=8, range=(-180, 180))[0]
check(hist.min() > 0.3 * hist.mean(), f"it spreads round the point, no empty side ({hist.tolist()})")

presets = json.load(open(os.path.join(PACK, "element_forge", "app", "app_presets.json"), encoding="utf-8"))
fire = {s["id"]: s for e in presets["effects"] if e["id"] == "fire" for s in e["styles"]}
check("explosion" in fire and fire["explosion"]["settings"].get("Particle preset") == "explosion"
      and fire["explosion"]["cost"] == "gen", "Fire has an explosion the AI paints, guided by the explosion's particles")
check("explosion_drawn" in fire and fire["explosion_drawn"]["cost"] == "calc"
      and fire["explosion_drawn"]["settings"].get("Particles: direct look (no LTX, pro)") is True, "and the same made by the particles alone")

import re
js = open(os.path.join(PACK, "web", "efa", "emitter.js"), encoding="utf-8").read()
block = js[js.index("const CURVES = ["):js.index("const SVGNS")]
named = {k: json.loads(v) for k, v in re.findall(r'\["([a-z ]+)", "[^"]+", (\[\[.*?\]\])\]', block)}
named["even"] = []
check(named == pt.RATE_CURVES, f"the panel offers the engine's curves by the same names ({sorted(named)})")
check(pt.RATE_CURVES["explosion"] == pt.PRESETS["explosion"]["rate_curve"], "the explosion preset uses the shared curve")
nsrc = open(os.path.join(PACK, "element_forge", "simulation", "particles_node.py"), encoding="utf-8").read()
check('"rate_over_time": (["preset"] + list(pt.RATE_CURVES)' in nsrc and 'o["rate_curve"] = pt.RATE_CURVES[rate_over_time]' in nsrc,
      "EF Particle Settings offers the same curves (rate_over_time)")
for name in pt.PRESETS:
    pt.params(name, {"rate_curve": pt.RATE_CURVES["pulses"]})
check(True, "every preset takes a rate curve (one engine, the same settings)")
print(f"{ok} checks passed")

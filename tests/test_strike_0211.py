import importlib.util
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


N, FPS, W, H = 49, 24.0, 480, 270


def em_for(P, n=N):
    return pt.Emitter("point A", n, FPS, W, H, P, np.random.default_rng(1), a=(240, 240))


P = pt.params("sparks", {"rate": 0.0, "burst": 30, "burst_at": 0.25, "burst_every": 0.5, "life": 0.1, "life_var": 0.0})
check(pt.burst_times(P, N, FPS) == [0.25, 0.75, 1.25, 1.75], f"bursts at 0.25 s and every 0.5 s ({pt.burst_times(P, N, FPS)})")
r = pt.simulate(P, em_for(P), seed=2)
born = r["born"][np.isfinite(r["born"])]
groups = [((born > t - 0.05) & (born < t + 0.1)).sum() for t in (0.25, 0.75, 1.25, 1.75)]
check(min(groups) >= 20 and len(born) == sum(groups), f"each burst brings its own particles ({groups})")
once = pt.params("sparks", {"rate": 0.0, "burst": 30, "burst_at": 0.25, "life": 0.1, "life_var": 0.0})
check(pt.burst_times(once, N, FPS) == [0.25], "without Burst every: once, as before")
r1 = pt.simulate(once, em_for(once), seed=2)
first = r["born"][np.isfinite(r["born"])] < 0.5
check(np.allclose(np.sort(r1["born"][np.isfinite(r1["born"])]), np.sort(r["born"][np.isfinite(r["born"])][first])),
      "the first burst is the same particles with or without Burst every")
end = pt.params("sparks", {"rate": 0.0, "burst": 5, "burst_every": 0.3, "end": 1.0})
check(max(pt.burst_times(end, N, FPS)) <= 1.0 + 1e-9, "the bursts stop at the end")

S = pt.params("lightning", {"path": "strike", "burst_at": 0.5, "strike_leader": 0.05, "strike_strokes": 3, "strike_gap": 0.06,
                            "strike_decay": 0.035, "branches": 5})
em = em_for(S)
paths = pt.make_paths(S, em, 3)
lit = [i for i in range(N) if paths[i]]
i_b = int(round(0.5 * FPS))
check(lit and min(lit) >= i_b - 2 and max(lit) <= i_b + int((0.06 * 1.5 * 2 + 3 * 0.035) * FPS) + 2,
      f"it lights only around the burst ({lit}, burst frame {i_b})")
peak = max(lit, key=lambda i: max(float(op.max()) for _, _, op, _ in paths[i]))
check(peak == i_b, f"the return stroke is brightest at the burst's frame ({peak})")
main = paths[i_b][0][0]
check(np.hypot(*(main[-1] - np.array([240, 240]))) < 1.0 and main[0][1] < 0, "the channel runs from above the frame down onto A")
before = [i for i in lit if i < i_b]
check(all(max(float(op.max()) for _, _, op, _ in paths[i]) <= 0.31 for i in before), "the leader before it is faint")
later = [i for i in lit if i > i_b + 1]
same = all(np.array_equal(paths[i][0][0], main) for i in later)
check(same, "later strokes light the same channel")
check(len(paths[i_b]) > 1 and all(len(paths[i]) <= len(paths[i_b]) for i in lit), "the branches glow with the first stroke")
storm = pt.params("lightning", {"path": "strike", "burst_at": 0.1, "burst_every": 0.6, "strike_spread": 100.0})
sp = pt.make_paths(storm, em_for(storm), 3)
ends = {tuple(np.round(sp[int(round(t * FPS))][0][0][-1])) for t in pt.burst_times(storm, N, FPS)}
check(len(pt.burst_times(storm, N, FPS)) == 4 and len(ends) == 4, f"Burst every makes a storm, each strike lands elsewhere ({len(ends)})")
again = pt.make_paths(S, em_for(S), 3)
check(all(len(a) == len(b) and all(np.array_equal(x[0], y[0]) for x, y in zip(a, b)) for a, b in zip(paths, again)),
      "same seed, same strike")
for name in pt.PRESETS:
    pt.params(name, {"path": "strike", "burst_every": 0.5})
check(True, "every preset takes the strike path and Burst every (one engine)")
tall = pt.params("lightning strike", {"strike_new_ground": 1.0})
tops, shared = [], []
for seed in range(8):
    e2 = pt.Emitter("point A", 20, FPS, 448, 768, tall, np.random.default_rng(1), a=(224, 722))
    pp = pt.make_paths(tall, e2, seed)
    i1 = int(round(tall["burst_at"] * FPS))
    main = max(pp[i1], key=lambda x: x[1])[0]
    tops.append(main[0][0])
    late_ = [max(f, key=lambda x: x[1])[0] for f in pp[i1 + 2:] if f]
    if late_:
        sec = late_[0]
        k = 0
        while k < min(len(sec), len(main)) and np.allclose(sec[k], main[k]):
            k += 1
        shared.append(k / len(main))
check(all(0.2 * 448 <= x <= 0.8 * 448 for x in tops), f"the channel starts inside the window ({[round(x) for x in tops]})")
check(shared and min(shared) >= 0.5, f"a second ground point shares the upper channel ({[round(x, 2) for x in shared]})")
inside = []
for seed in range(8):
    e3 = pt.Emitter("point A", 20, FPS, 1920, 1080, tall, np.random.default_rng(1), a=(1240, 1000))
    e3.view = (np.full(20, 970.0), np.full(20, 1510.0))
    pp = pt.make_paths(tall, e3, seed)
    m3 = max(pp[int(round(tall["burst_at"] * FPS))], key=lambda x: x[1])[0]
    inside.append(float(np.mean((m3[:, 0] >= 970) & (m3[:, 0] <= 1510))))
check(min(inside) == 1.0, f"in a window of the plate the channel stays inside it ({[round(x, 2) for x in inside]})")
print(f"{ok} checks passed")

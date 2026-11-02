import importlib.util
import math
import os
import sys

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


N, FPS, W, H = 41, 20.0, 400, 300


def run(preset, kind="point A", over=None, a=None, b=None, depth=None, masks=None, seed=1, n=N, **kw):
    P = pt.params(preset, over)
    rng = np.random.default_rng(seed)
    em = pt.Emitter(kind, n, FPS, W, H, P, rng, a=a, b=b, masks=masks, depth=pt.Depth(depth, W, H) if depth is not None else None, **kw)
    return pt.simulate(P, em, seed=seed), P, em


r1, P, _ = run("embers")
r2, _, _ = run("embers")
check(np.array_equal(np.nan_to_num(r1["x"]), np.nan_to_num(r2["x"])), "same settings and seed give the same particles")
exp = P["rate"] * (N - 1) / FPS
check(abs(r1["stats"]["spawned"] - exp) <= 2, f"count = rate x duration ({r1['stats']['spawned']} vs {exp:.0f})")
r3, _, _ = run("embers", seed=2)
check(not np.array_equal(np.nan_to_num(r1["x"]), np.nan_to_num(r3["x"])), "another seed gives other particles")
rb, _, _ = run("dust burst", over={"burst_at": 1.0})
born = rb["born"]
check(rb["stats"]["spawned"] == 150 and np.all(np.abs(born - 1.0) < 1 / FPS), "burst: 150 particles at once at 1.0 s")

f = pt.fade(np.array([0.0, 0.05, 0.1, 0.5, 0.85, 1.0]), 0.1, 0.3)
check(f[0] == 0 and 0 < f[1] < 1 and f[2] == 1 and f[3] == 1 and 0 < f[4] < 1 and f[5] == 0, "fade in, hold, fade out")

over = dict(rate=0, burst=1, speed=0.0, speed_var=0, radius=0, turbulence=0, drag=0, gravity=400.0, life=5, inherit=0, fade_in=0)
rg, _, _ = run("sparks", over=over, a={"point_track_px": [[200, 50]] * N})
y = rg["y"][:, 0]
t = np.arange(N) / FPS
ps = min(W, H) / pt.REF
check(np.nanmax(np.abs(y[:21] - (50 + 0.5 * 400 * ps * t[:21] ** 2))) < 2.0, "gravity: y follows the parabola of free fall")

mv = {"point_track_px": [[50 + 6 * i, 150] for i in range(N)]}
over_i = dict(turbulence=0, gravity=0, drag=0, spread=0, direction=0.0, speed=50.0, speed_var=0)
ri, _, _ = run("embers", over=dict(over_i, inherit=1.0), a=mv)
r0, _, _ = run("embers", over=dict(over_i, inherit=0.0), a=mv)
vx1, vx0 = np.nanmean(ri["vx"][ri["alpha"] > 0]), np.nanmean(r0["vx"][r0["alpha"] > 0])
check(vx1 > 80 and abs(vx0) < 5, f"particle drag: inherit 1 moves with the emitter ({vx1:.0f} px/s), inherit 0 not ({vx0:.0f})")

cn = pt.CurlNoise(np.random.default_rng(0), 50.0, 100.0, 0.3)
xs, ys = np.meshgrid(np.linspace(0, 300, 40), np.linspace(0, 300, 40))
h = 0.01
u1, _ = cn(xs.ravel() + h, ys.ravel(), 0.0)
u0, _ = cn(xs.ravel() - h, ys.ravel(), 0.0)
_, v1 = cn(xs.ravel(), ys.ravel() + h, 0.0)
_, v0 = cn(xs.ravel(), ys.ravel() - h, 0.0)
div = (u1 - u0 + v1 - v0) / (2 * h)
u, v = cn(xs.ravel(), ys.ravel(), 0.0)
check(np.abs(div).max() < 1e-3 * np.hypot(u, v).max() and 30 < np.sqrt(np.mean(u ** 2 + v ** 2)) < 70,
      "curl noise: divergence-free, rms speed near the strength")

m = np.zeros((N, H, W), np.float32)
m[:, 100:200, 150:250] = 1
rc, _, emc = run("magic dust", kind="object contour", masks=m, over=dict(radius=0, turbulence=0, gravity=0, inherit=0))
first = np.array([[rc["x"][np.nonzero(np.isfinite(rc["x"][:, j]))[0][0], j], rc["y"][np.nonzero(np.isfinite(rc["x"][:, j]))[0][0], j]]
                  for j in range(rc["x"].shape[1])])
on_edge = (np.minimum.reduce([np.abs(first[:, 0] - 150), np.abs(first[:, 0] - 249), np.abs(first[:, 1] - 100), np.abs(first[:, 1] - 199)]) < 12)
check(on_edge.mean() > 0.9, f"contour emitter: births on the outline ({on_edge.mean():.0%})")
cx = (first[:, 0] - 200) * rc["vx"][0:1].mean() if False else None
born_vx = np.array([rc["vx"][np.nonzero(np.isfinite(rc["x"][:, j]))[0][0], j] for j in range(len(first))])
born_vy = np.array([rc["vy"][np.nonzero(np.isfinite(rc["x"][:, j]))[0][0], j] for j in range(len(first))])
outward = ((first[:, 0] - 200) * born_vx + (first[:, 1] - 150) * born_vy) > 0
check(outward.mean() > 0.85, f"contour emitter: particles fly outward ({outward.mean():.0%})")

ra, _, _ = run("magic dust", kind="line A-B", a={"point_track_px": [[100, 150]] * N}, b={"point_track_px": [[300, 150]] * N},
               over=dict(radius=0, direction_mode="angle", speed=0, speed_var=0, gravity=0, turbulence=0, inherit=0))
fx = np.array([ra["x"][np.nonzero(np.isfinite(ra["x"][:, j]))[0][0], j] for j in range(ra["x"].shape[1])])
check(fx.min() >= 99 and fx.max() <= 301 and fx.std() > 40, "line A-B: births spread between the two points")

d = np.full((N, H, W), 0.3, np.float32)
d[:, :, 200:] = 0.8
over_d = dict(rate=0, burst=200, speed=0, speed_var=0, radius=600, turbulence=0, gravity=0, inherit=0, fade_in=0, life=5)
rd, _, _ = run("embers", over=over_d, a={"point_track_px": [[120, 150]] * N}, depth=d)
x5, v5 = rd["x"][5], rd["vis"][5]
ok_l, ok_r = v5[x5 < 190], v5[x5 > 210]
check(ok_l.mean() > 0.95 and ok_r.mean() < 0.05, "depth: particles behind the near wall are hidden, the others visible")

ramp = np.tile(np.linspace(0.2, 0.9, H, dtype=np.float32)[:, None], (1, W))
d2 = np.repeat(ramp[None], N, 0)
over_s = dict(rate=0, burst=1, preroll=0, band="volume", depth_offset=0.3, speed=200.0, speed_var=0, spread=0, radius=0, turbulence=0,
              life=10, land_fade=10, inherit=0)
rs, _, ems = run("snow", over=over_s, a={"point_track_px": [[200, 20]] * 121}, depth=np.repeat(ramp[None], 121, 0), n=121)
zp = rs["z"][0, 0]
y_floor = np.interp(zp, ramp[:, 0], np.arange(H))
yl = rs["y"][-1, 0]
check(rs["stats"]["landed"] == 1 and abs(yl - y_floor) < 6 and abs(rs["y"][-1, 0] - rs["y"][-5, 0]) < 0.5 and rs["vis"][-1, 0] > 0.6,
      f"depth: a falling flake lands on the floor at its depth (y {yl:.0f} vs {y_floor:.0f}) and stays visible")

over_b = dict(rate=0, burst=1, speed=0, speed_var=0, radius=0, turbulence=0, drag=0, life=6, inherit=0, gravity=900.0, depth_offset=0.3,
              restitution=0.5, fade_out=0, fine_share=0.0, children=None)
rbn, _, _ = run("sparks", over=over_b, a={"point_track_px": [[200, 40]] * 81}, depth=np.repeat(ramp[None], 81, 0), n=81)
yy = rbn["y"][:, 0]
check(2 <= rbn["stats"]["bounced"] <= 12 and np.nanmin(yy[40:]) > 60 and np.nanmax(yy) < np.interp(rbn["z"][0, 0], ramp[:, 0], np.arange(H)) + 6,
      f"bounce: the spark bounces ({rbn['stats']['bounced']}x) and does not fall through the floor")

over_r = dict(rate=200.0, preroll=0.5, band="top")
rr, _, _ = run("rain", kind="whole frame", over=over_r, depth=d2)
check(rr["stats"]["children"] > 0 and rr["stats"]["children"] == 3 * (rr["stats"]["children"] // 3), "rain: drops hitting the floor make splashes")

rsn, _, _ = run("snow", kind="whole frame")
ys0 = rsn["y"][0][np.isfinite(rsn["y"][0])]
check(len(ys0) > 50 and (ys0 > H * 0.5).mean() > 0.2, "snow with preroll: flakes everywhere already in frame 0")

re, _, _ = run("energy A-B", a={"point_track_px": [[60, 150]] * N}, b=None, target={"point_track_px": [[340, 150]] * N}) \
    if False else (None, None, None)
P = pt.params("energy A-B", dict(turbulence=0))
em = pt.Emitter("point A", N, FPS, W, H, P, np.random.default_rng(1), a={"point_track_px": [[60, 150]] * N})
re = pt.simulate(P, em, seed=1, target={"point_track_px": [[340, 150]] * N})
xe = re["x"][-1][np.isfinite(re["x"][-1])]
check(re["stats"]["killed_by_target"] > 10 and np.median(xe) > 120, "energy A-B: particles fly to B and vanish there")

def trails(r):
    out = set()
    for j in range(r["x"].shape[1]):
        f = np.nonzero(np.isfinite(r["x"][:, j]))[0]
        if len(f):
            out.add((int(f[0]), round(float(r["x"][f[0], j]), 2), round(float(r["y"][f[0], j]), 2),
                     round(float(r["x"][f[-1], j]), 2), round(float(r["y"][f[-1], j]), 2)))
    return out


for pre in ("sparks", "dust burst"):
    Pa = pt.params(pre)
    ra = pt.simulate(Pa, pt.Emitter("point A", N, FPS, W, H, Pa, np.random.default_rng(1)), seed=1, amount=1.0)
    rb = pt.simulate(Pa, pt.Emitter("point A", N, FPS, W, H, Pa, np.random.default_rng(1)), seed=1, amount=1.6)
    ta, tb = trails(ra), trails(rb)
    check(len(ta) > 20 and len(ta & tb) >= 0.98 * len(ta) and len(tb) > 1.4 * len(ta),
          f"{pre}: amount 1.0 -> 1.6 keeps {len(ta & tb)}/{len(ta)} particles unchanged and adds {len(tb) - len(ta)}")

dgr = np.repeat(np.tile(np.linspace(0.1, 1.0, H, dtype=np.float32)[:, None], (1, W))[None], N, 0)
rf, Pf, emf = run("fireflies", "whole frame", depth=dgr)
sharp = pt.render_frames(dict(Pf, dof=0.0), rf, emf, None, pt.Raster(W, H), "seed")
soft = pt.render_frames(dict(Pf, dof=40.0), rf, emf, None, pt.Raster(W, H), "seed")
ratio = float(soft[..., 3].sum() / max(sharp[..., 3].sum(), 1e-6))
check(0.6 < ratio < 1.5 and float(soft[..., 3].max()) < float(sharp[..., 3].max()) and Pf["dof"] > 0,
      f"fireflies depth of field: softer (peak {float(soft[..., 3].max()):.2f} vs {float(sharp[..., 3].max()):.2f}), light kept ({ratio:.2f})")

mk = np.zeros((N, H, W), np.float32); mk[:, 40:260, 80:320] = 1
def crack_spread(over):
    Pc = pt.params("frost", over)
    emc = pt.Emitter("object mask", N, FPS, W, H, Pc, np.random.default_rng(1), masks=mk, a={"point_track_px": [[200, 150]] * N})
    pa = pt.make_paths(Pc, emc, 1)
    pts = np.concatenate([seg[0].reshape(-1, 2) for seg in pa[-1]])
    return float(pts[:, 0].std() + pts[:, 1].std()), len(pts)
one, n1 = crack_spread({"crack_seeds": 1})
many, n5 = crack_spread(None)
check(many > 1.2 * one and n5 > n1, f"frost: 5 start points cover more of the object (spread {many:.0f} vs {one:.0f} px, {n5} vs {n1} points)")

pl_h = np.full((2, 120, 160, 3), 0.05, np.float32); sd_h = np.zeros((2, 120, 160, 4), np.float32); sd_h[:, 60, 80] = [1, 1, 1, 1]
hv_h = np.ones((2, 120, 160), np.float32)
l0, _ = pt.direct_look(pl_h, sd_h, hv_h, "add", 1.0, np.random.default_rng(0))
l1, _ = pt.direct_look(pl_h, sd_h, hv_h, "add", 1.0, np.random.default_rng(0), halo=1.0)
g0, g1 = float(l0[0, 60, 95].mean()), float(l1[0, 60, 95].mean())
check(g1 > g0 + 0.02 and abs(float(l0[0, 5, 5].mean()) - float(l1[0, 5, 5].mean())) < 0.02 and pt.PRESETS["aura"].get("halo", 0) > 0,
      f"halo: glow 15 px from a spark {g0:.3f} -> {g1:.3f}, far corner unchanged; aura preset uses it")

def crack_widths(taper):
    Pc = pt.params("cracks", {"crack_taper": taper})
    emc = pt.Emitter("point A", N, FPS, W, H, Pc, np.random.default_rng(1), masks=mk, a={"point_track_px": [[200, 150]] * N})
    return [seg[1] for seg in pt.make_paths(Pc, emc, 1)[-1]]
w0, w1 = crack_widths(0.0), crack_widths(1.0)
check(max(w1) > 2.5 * max(w0) and min(w1) <= 1.05 * max(w0) and pt.PRESETS["cracks"].get("crack_taper", 0) == 0,
      f"crack taper: widest {max(w0):.1f} -> {max(w1):.1f} px, tips stay thin ({min(w1):.1f} px); off in the cracks preset (p8g: LTX drew a coral)")
img_g = np.full((60, 60, 3), 0.4, np.float32); a_g = np.zeros((60, 60), np.float32); a_g[30, 10:50] = 1.0
gr = pt.groove(img_g, a_g, 1.0, 1.5)
check(float(gr[31:33, 30].mean()) > 0.41 and float(gr[26, 30].mean()) < 0.39 and abs(float(gr[5, 5].mean()) - 0.4) < 0.01,
      f"groove: lit lip below {gr[31:33, 30].mean():.3f}, dark rim above {gr[26, 30].mean():.3f}, far away unchanged")
d_s = np.full((60, 80), 0.3, np.float32); d_s[:, 25:35] = 0.8
seg = np.array([[[10.0, 30.0], [50.0, 30.0]]])
hs = pt.surface_hold([(seg, 2.0, np.ones(1), np.array([0.3]))], d_s, 60, 80, 0.02)
hs_far = pt.surface_hold([(seg, 2.0, np.ones(1), np.array([0.3]))], np.full((60, 80), 0.32, np.float32), 60, 80, 0.02)
check(hs is not None and hs[30, 30] < 0.05 and hs[30, 15] > 0.95 and hs[5, 30] == 1.0 and float(hs_far.min()) > 0.95
      and pt.surface_hold([(np.zeros((3, 2)), 2.0, np.ones(3), 0.3)], d_s, 60, 80, 0.02) is None,
      f"surface hold: crack hidden behind the knee ({hs[30, 30]:.2f}), visible beside it, small depth drift keeps it; polylines untouched")

bad = []
for fps_b in (24.0, 25.0, 30.0):
    for start in [round(0.05 * k, 2) for k in range(1, 31)]:
        for preset, ba in (("dust burst", 0.0), ("debris", 0.0), ("dust burst", 0.3)):
            Pb = pt.params(preset, {"start": start, "burst_at": ba})
            emb = pt.Emitter("point A", int((start + ba) * fps_b) + 3, fps_b, W, H, Pb, np.random.default_rng(1))
            rb_ = pt.simulate(Pb, emb, seed=1)
            tb = start + ba
            if rb_["stats"]["spawned"] != Pb["burst"] or not np.all((rb_["born"] >= tb - 1e-6) & (rb_["born"] < tb + 1 / fps_b)):
                bad.append((fps_b, start, preset, ba, rb_["stats"]["spawned"]))
check(not bad, f"burst: fires once at its time for every start 0.05..1.5 s at 24/25/30 fps (misses/doubles: {bad[:4]})")

ramp_r = np.repeat(ramp[None], 81, 0)
Pr = pt.params("rain", {"max_particles": 1500})
emr = pt.Emitter("whole frame", 81, FPS, W, H, Pr, np.random.default_rng(1), depth=pt.Depth(ramp_r, W, H))
rr2 = pt.simulate(Pr, emr, seed=1)
born_m = rr2["born"][rr2["kind"] == 0]
rate_r = Pr["rate"] * W / pt.REF
alive_r = int(np.isfinite(rr2["x"]).sum(1).max())
check(((born_m >= 3.0) & (born_m < 4.0)).sum() > 0.9 * rate_r and alive_r <= 1500 and rr2["stats"]["children"] > 1500,
      f"max_particles: rain keeps falling to the end of a 4 s clip ({((born_m >= 3.0) & (born_m < 4.0)).sum()} drops in the last "
      f"second, rate {rate_r:.0f}), at most {alive_r} of 1500 alive at once")
re_, Pe, _ = run("embers", over={"max_particles": 40}, n=121)
alive_e = np.isfinite(re_["x"]).sum(1)
check(alive_e.max() <= 40 and ((re_["born"] > 4.0).sum() > 10) and re_["stats"]["capped"] > 0,
      f"max_particles 40: never more alive ({alive_e.max()}), births go on as others die ({(re_['born'] > 4.0).sum()} after 4 s)")

pk = []
for s_ in (0.5 * 1.3 ** 5.49, 0.5 * 1.3 ** 5.51, 0.5 * 1.3 ** 6.0, 0.5 * 1.3 ** 6.49, 0.5 * 1.3 ** 6.51):
    sp_ = pt.Splats(); sp_.points(np.array([50.0]), np.array([50.0]), s_, [1, 1, 1], 0.5)
    o_ = sp_.render(100, 100)[..., 3]
    pk.append((float(o_.max()), float(o_.sum()) / (0.5 * 2 * np.pi * s_ ** 2)))
check(abs(pk[0][0] - pk[1][0]) < 0.01 and abs(pk[3][0] - pk[4][0]) < 0.01 and all(0.9 < p[0] / 0.5 < 1.1 and 0.97 < p[1] < 1.03 for p in pk),
      f"splats: no jump at a size class border (peak {pk[0][0]:.3f} / {pk[1][0]:.3f}), mass kept")


class _Count:
    def __init__(self, cv):
        self.cv, self.n = cv, 0

    def __getattr__(self, k):
        f = getattr(self.cv, k)
        if k in ("line", "polylines"):
            def g(*a, **kw):
                self.n += 1
                return f(*a, **kw)
            return g
        return f


rg_ = np.random.default_rng(3)
gx, gy = np.meshgrid(np.arange(20, 380, 12.0), np.arange(20, 280, 12.0))
sg = np.stack([np.stack([gx.ravel(), gy.ravel()], 1), np.stack([gx.ravel() + 6, gy.ravel() + 3], 1)], 1)
zg = rg_.uniform(0.40, 0.46, len(sg))
dg = np.full((H, W), 0.5, np.float32)
ref = np.ones((H, W), np.float32)
for (p0, p1), z_ in zip(np.round(sg).astype(int), zg):
    mm = np.zeros((H, W), np.uint8)
    pt.cv2.line(mm, tuple(map(int, p0)), tuple(map(int, p1)), 1, 3)
    ref[mm > 0] = np.clip((z_ + 0.05 - 0.5) / 0.05 + 1.0, 0, 1)
cv_ = pt.cv2
pt.cv2 = _Count(cv_)
try:
    hg = pt.surface_hold([(sg, 0.5, np.ones(len(sg)), zg)], dg, H, W, 0.02)
    calls = pt.cv2.n
finally:
    pt.cv2 = cv_
check(np.abs(hg - ref).max() <= 1 / 128 + 1e-6 and calls < len(sg) / 4 and float(ref.min()) < 0.3,
      f"surface hold: {calls} draw calls for {len(sg)} segments, same hold (max diff {np.abs(hg - ref).max():.4f})")
Pf_ = pt.params("frost")
emf_ = pt.Emitter("object mask", N, FPS, W, H, Pf_, np.random.default_rng(1), masks=mk, a={"point_track_px": [[200, 150]] * N},
                  depth=pt.Depth(np.repeat(ramp[None], N, 0), W, H))
nat = [0]
at0 = emf_.depth.at
emf_.depth.at = lambda *a: (nat.__setitem__(0, nat[0] + 1), at0(*a))[1]
paf = pt.make_paths(Pf_, emf_, 1)
segf = np.concatenate([q[0].reshape(-1, 4) for q in paf[-1]])
zseg = np.concatenate([q[3] for q in paf[-1]])
dfx = emf_.depth.d[0]
zchk = dfx[np.clip((segf[:, 1] * emf_.depth.sy).astype(int), 0, dfx.shape[0] - 1), np.clip((segf[:, 0] * emf_.depth.sx).astype(int), 0, dfx.shape[1] - 1)]
check(nat[0] <= 5 and len(segf) > 1000 and np.array_equal(zseg, zchk),
      f"crack building: {nat[0]} depth lookups for {len(segf)} segments (was 3 per segment), segment depth = depth at its start")

Hg, Wg = 1080, 1200


def groove_profile(op=0.9, knot=False, hold_=None):
    sp_ = pt.Splats()
    sp_.lines(np.array([300.0]), np.array([500.0]), np.array([800.0]), np.array([500.0]), 1.1, [0.08] * 3, op)
    if knot:
        r_ = np.random.default_rng(0)
        x0, y0, an = r_.uniform(950, 1150, 300), r_.uniform(400, 600, 300), r_.uniform(0, 2 * np.pi, 300)
        sp_.lines(x0, y0, x0 + 6 * np.cos(an), y0 + 6 * np.sin(an), 1.1, [0.08] * 3, op)
    sd_ = sp_.render(Hg, Wg)[None]
    pl_ = np.full((1, Hg, Wg, 3), 0.4, np.float32)
    hv_ = np.ones((1, Hg, Wg), np.float32) if hold_ is None else hold_
    o1, _ = pt.direct_look(pl_, sd_, hv_, "over", 1.0, np.random.default_rng(0), relief=1.0, line_width=2.2)
    o0, _ = pt.direct_look(pl_, sd_, hv_, "over", 1.0, np.random.default_rng(0), relief=0.0)
    return (o1 - o0)[0, ..., 0] / 0.4


g1, gk, gf = groove_profile(), groove_profile(knot=True), groove_profile(op=0.1)
col = g1[:, 550]
off_ = np.r_[0:497, 504:Hg]
lip_dy = int(off_[col[off_].argmax()]) - 500
check(np.abs(gk[:, 550] - col).max() < 1e-3 and np.abs(gf[:, 550]).max() < 0.2 * np.abs(col).max() and 1 <= lip_dy <= 6
      and -0.45 < col[off_].min() < -0.3 and 0.28 < col.max() < 0.42,
      f"groove: same with a dense knot elsewhere, faint line shades less ({np.abs(gf[:, 550]).max():.3f} vs {np.abs(col).max():.3f}), "
      f"lit lip {lip_dy} px below the line, strength {col[off_].min():+.2f} / {col.max():+.2f} (before -0.38 / +0.35)")
hk = np.ones((1, Hg, Wg), np.float32); hk[:, :, 540:660] = 0.0
gh = groove_profile(hold_=hk)
check(np.abs(gh[:, 545:655]).max() < 1e-6 and np.abs(gh[:, 400]).max() > 0.2,
      f"groove: nothing shaded on what covers the wall ({np.abs(gh[:, 545:655]).max():.4f}), the wall beside it keeps its groove")

sd2 = np.zeros((2, 300, 400, 4), np.float32)
sd2[:, 150, 100] = 1.0
r2_ = np.random.default_rng(1)
for _ in range(80):
    sd2[1, r2_.integers(100, 200), r2_.integers(300, 390)] = 1.0
pl2, hv2 = np.full((2, 300, 400, 3), 0.05, np.float32), np.ones((2, 300, 400), np.float32)
lh, _ = pt.direct_look(pl2, sd2, hv2, "add", 1.0, np.random.default_rng(0), halo=1.0)
ln_, _ = pt.direct_look(pl2, sd2, hv2, "add", 1.0, np.random.default_rng(0), halo=0.0)
hl0, hl1 = float((lh - ln_)[0, 150, 70].mean()), float((lh - ln_)[1, 150, 70].mean())
hcl = float((lh - ln_)[1, 150, 280].mean())
check(abs(hl0 - hl1) < 2e-3 and hcl > 5 * hl0,
      f"halo: a lone spark glows the same with 80 sparks elsewhere ({hl0:.3f} / {hl1:.3f}), the dense group glows more ({hcl:.3f})")

dh_ = np.full((1, 120, 160), 0.5, np.float32)
rgh = np.random.default_rng(4)
xh = np.concatenate([rgh.uniform(2, 150, 400), np.full(300, -200.0)])
yh = np.concatenate([rgh.uniform(10, 110, 400), rgh.uniform(10, 110, 300)])
zh = np.concatenate([np.full(400, 0.6), np.full(300, 0.05)])
rech = {"x": xh[None], "y": yh[None], "z": zh[None], "alpha": np.ones((1, 700)), "size": np.full((1, 700), 2.0)}
emh = type("E", (), {"depth": type("D", (), {"d": dh_})()})()
_, hh = pt.masks_from(np.ones((1, 120, 160), np.float32), rech, emh, {"depth_softness": 0.05})
check(float(hh[0, 10:110, 0:3].min()) > 0.9,
      f"holdout: particles far outside the frame do not hide the border ({float(hh[0, 10:110, 0:3].min()):.2f})")
ms_ = np.zeros((1, 120, 160), np.float32); ms_[0, 30:100, 60:100] = 1
sl_ = pt.shell_light(ms_, 12, [0.6, 0.5, 1.0], 1.0, 25.0, seed=1)
near_, far_, ins_ = float(sl_[0, 60, 103].mean()), float(sl_[0, 60, 150].mean()), float(sl_[0, 60, 80].mean())
mv_ = float(np.abs(sl_[11] - sl_[0]).mean()) / max(float(sl_[0].mean()), 1e-6)
check(near_ > 5 * far_ and ins_ < 0.1 * near_ and sl_[0, 60, 103, 2] > sl_[0, 60, 103, 0] and mv_ > 0.05,
      f"shell: glows outside the outline ({near_:.3f} near, {far_:.4f} far, {ins_:.4f} inside), blue-violet, the wisps move")
import cv2
n_, Wl, Hl = 21, 400, 300


def skate_M(i):
    M = cv2.getRotationMatrix2D((120, 200), 1.5 * i, 1.0)
    M[0, 2] += 5 * i
    return M


def skate(i, lift=0):
    base = np.zeros((Hl, Wl), np.float32)
    cv2.rectangle(base, (60, 180), (180, 219), 1.0, -1)
    m = cv2.warpAffine(base, skate_M(i), (Wl, Hl), flags=cv2.INTER_NEAREST)
    if lift:
        cv2.rectangle(m, (300, 180 - lift), (360, 214 - lift), 1.0, -1)
    tex = cv2.GaussianBlur(np.random.default_rng(3).uniform(0.0, 1.0, (Hl, Wl, 3)).astype(np.float32), (0, 0), 2)
    return m, cv2.warpAffine(tex, skate_M(i), (Wl, Hl), borderMode=cv2.BORDER_REFLECT)


mk_ = np.stack([skate(i, lift=30)[0] for i in range(n_)])
fr_ = np.stack([skate(i)[1] for i in range(n_)])
Pl = pt.params("sparks")
eb = pt.Emitter("object bottom edge", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), masks=mk_)
p0, nb = eb.pts[0], eb.nrm[0]
lifted = p0[p0[:, 0] > 290]
check(len(p0) > 50 and (nb[:, 1] > 0.5).all() and abs(float(p0[p0[:, 0] < 290][:, 1].mean()) - 220) < 3
      and len(lifted) > 10 and abs(float(lifted[:, 1].mean()) - 185) < 3,
      f"bottom edge: only the lower edge of each part, normals down, the lifted part keeps its own edge ({len(p0)} points)")
dr_ = np.zeros((1, Hl, Wl), np.float32); cv2.line(dr_[0], (80, 232), (160, 232), 1.0, 3)
ei = pt.Emitter("drawing", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), drawing=dr_, attach="image",
                a={"point_track_px": [[120 + 5 * i, 200] for i in range(n_)]})
pi_, _, _ = ei.sample(1.0, 50, np.random.default_rng(2).uniform(0, 1, (50, 5)))
check(abs(float(pi_[:, 1].mean()) - 232) < 2 and pi_[:, 0].min() >= 78 and pi_[:, 0].max() <= 162,
      "drawing hung on the image: stays where it was drawn while A moves")
et = pt.Emitter("drawing", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), drawing=dr_,
                a={"point_track_px": [[120 + 5 * i, 200] for i in range(n_)]})
pt_, _, _ = et.sample(1.0, 50, np.random.default_rng(2).uniform(0, 1, (50, 5)))
check(et.dpath is None and abs(float(pt_[:, 0].mean()) - (120 + 100)) < 4, "drawing on the track (default): moves with A as before")
bpath = {"point_track_px": [[120 + 60 * math.cos(math.radians(9 * i)), 200 + 60 * math.sin(math.radians(9 * i))] for i in range(n_)]}
eab = pt.Emitter("drawing", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), drawing=dr_, a={"point_track_px": [[120, 200]] * n_}, b=bpath)
d20 = eab.dpath[20] - [120, 200]
d0 = eab.dpath[0] - [120, 200]
rot = math.degrees(float((np.arctan2(d20[:, 1], d20[:, 0]) - np.arctan2(d0[:, 1], d0[:, 0])).mean()) % (2 * math.pi))
check(abs(rot - 180) < 3 and np.allclose(np.hypot(*d20.T), np.hypot(*d0.T), atol=0.5),
      f"drawing on the track with B: turns with the line A-B ({rot:.1f} deg after B went half round)")
eo = pt.Emitter("drawing", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), drawing=dr_, masks=mk_, frames=fr_, attach="object")
dist_ = [float(cv2.distanceTransform((1 - (mk_[i] > 0.5)).astype(np.uint8), cv2.DIST_L2, 3)[
    eo.dpath[i][:, 1].round().astype(int).clip(0, Hl - 1), eo.dpath[i][:, 0].round().astype(int).clip(0, Wl - 1)].max()) for i in range(n_)]
def local(p, i):
    Mi = cv2.invertAffineTransform(skate_M(i))
    return p @ Mi[:, :2].T + Mi[:, 2]
drift = float(np.abs(local(eo.dpath[-1], n_ - 1) - local(eo.dpath[0], 0)).max(1).mean())
check(max(dist_) <= 2.5 and drift < 8 and (eo.dnrm[0][:, 1] > 0.3).mean() > 0.8,
      f"drawing hung on the object: snapped onto its edge in every frame (max {max(dist_):.1f} px off) and carried "
      f"with it (drift {drift:.1f} px over {n_} frames while it moves 100 px and tilts 30 deg)")
eo2 = pt.Emitter("drawing", n_, FPS, Wl, Hl, Pl, np.random.default_rng(1), drawing=np.zeros((1, Hl, Wl), np.float32), masks=mk_, attach="object")
check(eo2.kind == "object bottom edge", "hung on the object without a drawing: the object's bottom edge")
rs_ = pt.simulate(Pl, eo, seed=1)
check(rs_["stats"]["spawned"] > 10 and np.isfinite(rs_["x"]).any(), f"sparks from the object-hung line ({rs_['stats']['spawned']} born)")
nm, Wm, Hm = 21, 320, 200
bgm = cv2.GaussianBlur(np.random.default_rng(11).uniform(0, 1, (Hm + 40, Wm + 200, 3)).astype(np.float32), (0, 0), 1.5)
blk = cv2.GaussianBlur(np.random.default_rng(12).uniform(0, 1, (60, 60, 3)).astype(np.float32), (0, 0), 1.5)


def carry_plate(block_dx=6, pan=0, x_start=40):
    fr = np.zeros((nm, Hm, Wm, 3), np.float32)
    for i in range(nm):
        fr[i] = bgm[20:20 + Hm, 60 + pan * i:60 + pan * i + Wm]
        x0 = x_start + block_dx * i - pan * i
        fr[i, 70:130, x0:x0 + 60] = blk
    return fr


Pm_over = dict(rate=0, burst=150, burst_at=0.0, start=0.0, speed=0.0, speed_var=0.0, gravity=0.0, drag=0.0, turbulence=0.0,
               inherit=0.0, life=10.0, life_var=0.0, preroll=0.0, wind=[0.0, 0.0])


def carry_run(fr, area, carry, cam=None):
    P = pt.params("embers", dict(Pm_over, motion_carry=carry))
    em = pt.Emitter("area", nm, FPS, Wm, Hm, P, np.random.default_rng(1), area=area, cam=cam)
    r = pt.simulate(P, em, seed=1, flow=pt.PlateFlow(fr) if carry > 0 else None)
    k = np.isfinite(r["x"][0]) & np.isfinite(r["x"][10])
    return float((r["x"][10][k] - r["x"][0][k]).mean()), float(np.abs(r["y"][10][k] - r["y"][0][k]).mean()), int(k.sum())


frm = carry_plate()
on_blk = (0.16, 0.4, 0.28, 0.6)
dx1, dy1, k1 = carry_run(frm, on_blk, 1.0)
dx0, _, _ = carry_run(frm, on_blk, 0.0)
dxs, _, _ = carry_run(frm, (0.75, 0.2, 0.9, 0.4), 1.0)
check(k1 > 50 and abs(dx1 - 60) < 9 and dy1 < 4 and abs(dx0) < 0.5 and abs(dxs) < 1.5,
      f"motion carry: particles on a block moving 6 px/frame go with it ({dx1:.1f} px in 10 frames, block 60), "
      f"without carry they stay ({dx0:.1f}), on the still background carry leaves them ({dxs:.1f})")
frp = carry_plate(block_dx=0, pan=4, x_start=200)
camp = pt.Camera.from_plate(frp)
on_blk2 = (0.66, 0.4, 0.78, 0.6)
dxp1, _, _ = carry_run(frp, on_blk2, 1.0, cam=camp)
dxp0, _, _ = carry_run(frp, on_blk2, 0.0, cam=camp)
check(abs(dxp1 - dxp0) < 3 and abs(dxp0 + 40) < 4,
      f"motion carry: a camera pan alone carries nothing (on screen {dxp1:.1f} px with carry, {dxp0:.1f} without, scene -40)")
frf = carry_plate(block_dx=4, pan=4)
camf = pt.Camera.from_plate(frf)
dxf1, _, _ = carry_run(frf, on_blk, 1.0, cam=camf)
dxf0, _, _ = carry_run(frf, on_blk, 0.0, cam=camf)
check(abs(dxf1) < 6 and abs(dxf0 + 40) < 4,
      f"motion carry: the camera follows the block - carried particles stay on it ({dxf1:.1f} px on screen), "
      f"the others stay in the scene ({dxf0:.1f})")
import time as _time
def _splat(sig, coarse):
    old = pt.COARSE_SIG
    pt.COARSE_SIG = coarse
    sp = pt.Splats()
    sp.points([300.3, 520.7, 900.0], [200.2, 400.6, 50.0], sig, [[1, .5, .2], [.2, 1, .3], [1, 1, 1]], [0.6, 0.3, 0.9])
    t = _time.time()
    im = sp.render(540, 960)
    pt.COARSE_SIG = old
    return im, _time.time() - t
ex, _ = _splat(60.0, 1e9)
co, _ = _splat(60.0, pt.COARSE_SIG)
check(np.abs(ex - co).max() < 1 / 255 and abs(ex[..., 3].sum() / co[..., 3].sum() - 1) < 0.002,
      f"big splats on the coarse grid match the exact blur (max diff {np.abs(ex - co).max():.4f} < 1/255)")
big, tb = _splat(950.0, pt.COARSE_SIG)
check(tb < 2.0 and big[..., 3].max() > 0.05, f"a splat of sigma 950 (a group's guide blob) renders in {tb:.2f} s")
nk_, Wk_, Hk_ = 31, 400, 240
bgk_ = cv2.GaussianBlur(np.random.default_rng(11).uniform(0, 1, (Hk_, Wk_ + 300, 3)).astype(np.float32), (0, 0), 1.5)
skk_ = cv2.GaussianBlur(np.random.default_rng(12).uniform(0, 1, (50, 80, 3)).astype(np.float32), (0, 0), 1.5)
frk_ = np.stack([bgk_[:, 60:60 + Wk_].copy() for _ in range(nk_)])
for i_ in range(nk_):
    frk_[i_, 140:190, 40 + 6 * i_:120 + 6 * i_] = skk_
ak_ = [[80 + 6 * i_, 190] for i_ in range(nk_)]


def kick(carry, free):
    P = pt.params("dust burst", dict(motion_carry=carry, carry_free=free))
    em = pt.Emitter("point A", nk_, 25.0, Wk_, Hk_, P, np.random.default_rng(1), a={"point_track_px": ak_})
    r = pt.simulate(P, em, seed=1, flow=pt.PlateFlow(frk_) if carry > 0 else None)
    k = np.isfinite(r["x"][25])
    return float(np.median(np.hypot(r["x"][25][k] - ak_[25][0], r["y"][25][k] - ak_[25][1])))


d0_, dold_, dnew_ = kick(0.0, 120.0), kick(0.6, 0.0), kick(0.6, 120.0)
check(dold_ < 0.4 * d0_ and dnew_ > 0.85 * d0_,
      f"motion carry: dust from a moving skate spreads as without carry ({dnew_:.0f} px from it, without carry {d0_:.0f}); "
      f"carried by the skate's own motion it piled up ({dold_:.0f})")

Nf_, Hf_, Wf_ = 61, 360, 640
floor_ = np.repeat(((0.2 + 0.6 * np.arange(Hf_) / Hf_)[:, None].repeat(Wf_, 1).astype(np.float32))[None], Nf_, 0)


def landed_rows(over):
    P_ = pt.params("debris", over)
    em_ = pt.Emitter("point A", Nf_, 25.0, Wf_, Hf_, P_, np.random.default_rng(1), a={"point_track_px": [[320, 220]] * Nf_},
                     depth=pt.Depth(floor_, Wf_, Hf_))
    r_ = pt.simulate(P_, em_, seed=1)
    a_ = np.isfinite(r_["x"][-1]) & (r_["alpha"][-1] > 0.02)
    return r_["y"][-1][a_]


y0_, yd_ = landed_rows({"depth_spread": 0.0}), landed_rows(None)
check(y0_.std() < 1 and yd_.std() > 8 and len(yd_) > 0.6 * len(y0_),
      f"debris lands spread over the floor, not on one row (row spread {yd_.std():.1f} px, at one depth {y0_.std():.1f}; "
      f"{len(yd_)} of {len(y0_)} chunks visible)")

Nr_, Hr_, Wr_ = 21, 270, 480
dr_ = np.repeat((0.05 + 0.25 * np.arange(Hr_) / Hr_)[:, None].repeat(Wr_, 1).astype(np.float32)[None], Nr_, 0)
cv2.circle(dr_[0], (240, 150), 50, 0.9, -1)
dr_[:] = dr_[0]
rr_, Pr_, er_ = run("rain", kind="whole frame", depth=dr_, n=Nr_)
sp_ = pt.render_frames(Pr_, rr_, er_, None, pt.Raster(Wr_, Hr_), "seed", True, 0.08)
reg_, hol_ = pt.masks_from(sp_[..., 3], rr_, er_, Pr_, True)
nh_ = cv2.connectedComponents((hol_[-1] < 0.5).astype(np.uint8))[0] - 1
check(reg_.min() == 1.0 and nh_ <= 2 and hol_[-1][150, 240] < 0.3 and hol_[-1][20, 20] > hol_[-1][150, 240] + 0.3,
      f"rain over the whole frame: region 1 everywhere, {nh_} hidden area(s) (the near disc), behind it "
      f"{hol_[-1][150, 240]:.2f}, far corner {hol_[-1][20, 20]:.2f}")
bimg = np.zeros((120, 200, 4), np.float32)
for cx in (60, 72):
    cv2.circle(bimg, (cx, 60), 5, (0.8, 0.1, 0.1, 1.0), -1)
cv2.circle(bimg, (170, 60), 1, (0.8, 0.1, 0.1, 1.0), -1)
bm = pt.blob_merge(bimg, 6.0, 0.35, 0.12)
ncomp = cv2.connectedComponents((bm[..., 3] > 0.3).astype(np.uint8))[0] - 1
col = bm[60, 66, :3] / max(bm[60, 66, 3], 1e-6)
check(ncomp == 1 and bm[60, 170, 3] < 0.05 and bm[60, 66, 3] > 0.5 and abs(col[0] - 0.8) < 0.02,
      f"blob: two close dots flow into one body ({ncomp} part), a lone speck vanishes ({bm[60, 170, 3]:.2f}), colour kept")
bs = pt.blob_merge(bimg * 0.3, 6.0, 0.35, 0.12, opacity=0.3, fill=0.0)
check(bs[..., 3].max() <= 0.3 + 1e-4 and bs[60, 66, 3] > 0.05, f"blob fill 0: the body keeps the blur's density (max {bs[..., 3].max():.2f})")
P0 = pt.params("embers")
em0 = pt.Emitter("point A", 21, FPS, W, H, P0, np.random.default_rng(1), a=[[200, 150]] * 21)
r0 = pt.simulate(P0, em0, seed=1)
f0 = pt.render_frames(P0, r0, em0, None, pt.Raster(W, H), "seed", frames=[15])[15]
check(pt.PRESETS["embers"].get("blob", 0) == 0 and f0[..., 3].max() > 0, "blob off: presets without it render as before")

def spread_x(over):
    Pf = pt.params("embers", dict(over, turbulence=0.0, wind=[0.0, 0.0]))
    emf = pt.Emitter("point A", 31, FPS, W, H, Pf, np.random.default_rng(1), a=[[200, 150]] * 31)
    rf = pt.simulate(Pf, emf, seed=1)
    xs = rf["x"][30][np.isfinite(rf["x"][30])]
    return float(np.std(xs)), rf
s_off, ra = spread_x({"flock": 0.0})
s_on, rb = spread_x({"flock": 1.0, "flock_cohesion": 40.0, "flock_separation": 0.0, "flock_radius": 200.0})
_, rc = spread_x({"flock": 1.0, "flock_cohesion": 40.0, "flock_separation": 0.0, "flock_radius": 200.0})
check(s_on < 0.8 * s_off, f"flocking: cohesion pulls the embers together (x spread {s_on:.1f} px, without {s_off:.1f})")
check(np.array_equal(np.nan_to_num(rb["x"]), np.nan_to_num(rc["x"])), "flocking: same seed gives the same particles")
rl, Pl, eml = run("liquid", a=[[200, 20]] * N)
xl = rl["x"][N - 1][np.isfinite(rl["x"][N - 1])]
check(pt.PRESETS["liquid"]["flock"] > 0 and np.std(xl) > 4.0,
      f"liquid: turbulence and flocking - the stream wanders (x spread {np.std(xl):.1f} px, was a straight line)")
def start_speeds(var):
    Pv = pt.params("sparks", {"speed_var": var, "gravity": 0.0, "drag": 0.0, "turbulence": 0.0, "spread": 0.0, "inherit": 0.0,
                              "fine_share": 0.0, "children": None})
    emv = pt.Emitter("point A", 6, FPS, W, H, Pv, np.random.default_rng(1), a=[[200, 150]] * 6)
    rv = pt.simulate(Pv, emv, seed=1)
    a = np.isfinite(rv["x"][3]) & np.isfinite(rv["x"][2])
    return np.hypot(rv["vx"][3][a], rv["vy"][3][a]), Pv
s0, Pv = start_speeds(0.0)
s6, _ = start_speeds(0.6)
s15, _ = start_speeds(1.5)
check(np.std(s0) / np.mean(s0) < 0.01 and 0.25 < np.std(s6) / np.mean(s6) < 0.45 and s15.min() >= 0,
      f"speed variation: 0 = all alike ({np.std(s0) / np.mean(s0):.3f}), 0.6 = spread {np.std(s6) / np.mean(s6):.2f}, 1.5 none backwards")
mk_l = np.zeros((N, H, W), np.float32); mk_l[:, 40:280, 196:204] = 1
def climb_look(over):
    Pl = pt.params("lightning climb", over)
    eml = pt.Emitter("object mask", N, FPS, W, H, Pl, np.random.default_rng(1), masks=mk_l, a={"point_track_px": [[200, 150]] * N})
    pa = pt.make_paths(Pl, eml, 3)
    segs = [seg[0] for fr in pa for seg in fr if len(seg[0]) > 2]
    dev = []
    for q in segs:
        d_ = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(q, axis=0).T))])
        if d_[-1] < 30:
            continue
        u_ = np.arange(0, d_[-1], 1.0)
        r_ = np.stack([np.interp(u_, d_, q[:, 0]), np.interp(u_, d_, q[:, 1])], 1)
        sm = np.stack([np.convolve(np.pad(r_[:, c], 7, mode="edge"), np.ones(15) / 15, "valid") for c in (0, 1)], 1)
        dev.append(np.hypot(*(r_ - sm).T)[7:-7])
    return len(segs), float(np.mean(np.concatenate(dev)))
n_a, t_a = climb_look({"fork_depth": 1, "fine_rough": 0.0, "climb_zigzag": 0.0})
n_b, t_b = climb_look(None)
Pd = pt.params("lightning climb", None)
check(n_b > 1.2 * n_a and t_b > 1.1 * t_a and Pd["fork_depth"] == 2 and Pd["fine_rough"] == 0.28 and Pd["climb_zigzag"] == 5.0
      and Pd["branches"] == 4 and Pd["climb_pitch"] == 0.03 and pt.BASE["fork_depth"] == 1,
      f"lightning climb, old look (the preset since 29.10.): {n_b} strokes instead of {n_a} without it (forks fork again), small "
      f"jags {t_b:.2f} instead of {t_a:.2f} px off the stroke; other presets keep the defaults")
def fly_run(fly):
    mats = []
    for i in range(N):
        s_ = 1.0 + 0.3 * i / (N - 1)
        mats.append(np.array([[s_, 0, (1 - s_) * W / 2], [0, s_, (1 - s_) * H / 2], [0, 0, 1]]))
    Pf2 = pt.params("fireflies", {"fly": fly, "depth_spread": 0.3, "depth_spread_near": True, "speed": 0.0, "turbulence": 0.0,
                                  "life": 10.0, "fade_in": 0.0, "fade_out": 0.0, "flicker": 0.0})
    em2 = pt.Emitter("whole frame", N, FPS, W, H, Pf2, np.random.default_rng(1), depth=pt.Depth(np.full((N, H, W), 0.3, np.float32), W, H),
                     cam=pt.Camera(N, mats))
    r = pt.simulate(Pf2, em2, seed=1)
    k = np.isfinite(r["x"][0]) & np.isfinite(r["x"][-1]) & (r["alpha"][0] > 0)
    zoom = np.hypot(r["x"][-1][k] - W / 2, r["y"][-1][k] - H / 2) / np.maximum(np.hypot(r["x"][0][k] - W / 2, r["y"][0][k] - H / 2), 1)
    far, near = r["z"][0][k] < 0.32, r["z"][0][k] > 0.5
    return zoom, far, near, r["size"][-1][k] / np.maximum(r["size"][0][k], 1e-6)
zf, far_f, near_f, gf = fly_run(1.0)
z0, far_0, near_0, g0 = fly_run(0.0)
check(abs(np.median(zf[far_f]) - 1.3) < 0.05 and np.median(zf[near_f]) > 1.6 and np.median(gf[near_f]) > 1.6
      and abs(np.median(z0[near_0]) - 1.3) < 0.05 and np.allclose(g0, 1.0, atol=0.01),
      f"fly through: at the scene's depth the zoom of the plate ({np.median(zf[far_f]):.2f}), nearer particles spread "
      f"{np.median(zf[near_f]):.2f}x and grow {np.median(gf[near_f]):.2f}x; fly 0 all as the plate ({np.median(z0[near_0]):.2f}), sizes kept")
dfar = np.tile(np.linspace(0.05, 1.0, W, dtype=np.float32)[None, None], (N, H, 1))
def far_run(far):
    Pd = pt.params("fireflies", {"depth_far": far, "rate": 200.0})
    emd = pt.Emitter("whole frame", N, FPS, W, H, Pd, np.random.default_rng(1), depth=pt.Depth(dfar, W, H))
    rd = pt.simulate(Pd, emd, seed=1)
    return rd["z"][-1][np.isfinite(rd["x"][-1])]
zd0, zd6 = far_run(0.0), far_run(0.6)
check(zd0.max() > 0.8 and zd6.max() < 0.5 and len(zd6) > 20,
      f"depth_far 0.6: farthest 40 % of the depths only (max {zd6.max():.2f}, without {zd0.max():.2f})")
print(f"{ok} checks passed")

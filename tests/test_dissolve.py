import importlib
import json
import math
import os
import sys
import tempfile
import types

import numpy as np
import torch

S = tempfile.mkdtemp(prefix="ef_test_")
fp = types.ModuleType("folder_paths"); fp.get_output_directory = lambda: os.path.join(S, "out"); fp.get_temp_directory = lambda: os.path.join(S, "out")
sys.modules["folder_paths"] = fp
comfy = types.ModuleType("comfy"); cu = types.ModuleType("comfy.utils")


class PB:
    def __init__(self, n): pass
    def update(self, n=1): pass
    def update_absolute(self, *a, **k): pass


cu.repeat_to_batch_size = lambda t, n: t.repeat((n + len(t) - 1) // len(t), *([1] * (t.dim() - 1)))[:n]
cu.ProgressBar = PB; comfy.utils = cu; sys.modules["comfy"] = comfy; sys.modules["comfy.utils"] = cu
mm = types.ModuleType("comfy.model_management"); mm.throw_exception_if_processing_interrupted = lambda: None
comfy.model_management = mm; sys.modules["comfy.model_management"] = mm
PACK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK))
dv = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.dissolve")
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


n, H, W, fps = 30, 120, 200, 10.0
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
import cv2
tex = cv2.GaussianBlur(np.random.default_rng(1).uniform(0, 1, (H, W)).astype(np.float32), (0, 0), 1.5) * 0.4
bgimg = np.stack([0.2 + 0.4 * xx / W + tex, 0.4 + tex, 0.3 + 0.2 * yy / H + tex], -1).astype(np.float32)
plate = np.repeat(bgimg[None], n, 0).copy()
masks = np.zeros((n, H, W), np.float32)
X0 = lambda i: 40 + 3 * i
for i in range(n):
    x0 = X0(i)
    plate[i, 30:90, x0:x0 + 15] = (0.9, 0.1, 0.1)
    plate[i, 30:90, x0 + 15:x0 + 30] = (0.1, 0.1, 0.9)
    masks[i, 30:90, x0:x0 + 30] = 1.0
start, dur = 0.5, 1.5
r = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3})

check(np.abs(r["comp"][3] - plate[3]).max() < 1e-5 and r["particles_alpha"][3].max() == 0, "dissolve: before the start the plate is unchanged")
i = 25; x0 = X0(i)
clear = r["particles_alpha"][i, 30:90, x0:x0 + 30] < 0.01
err = np.abs(r["comp"][i, 30:90, x0:x0 + 30] - bgimg[30:90, x0:x0 + 30])[clear].mean()
check(err < 0.03 and r["person_matte"][i].max() < 1e-3, f"dissolve: after the end the background is back (mean error {err:.3f})")
i = 12; x0 = X0(i)
g = r["dissolve_mask"][i, 30:90]
gl, gr = g[:, x0:x0 + 15].mean(), g[:, x0 + 15:x0 + 30].mean()
check(gl > gr + 0.3, f"dissolve: front runs left to right (gone left {gl:.2f}, right {gr:.2f})")
f = r["field"]
s1 = (f.times(8)[30:90, X0(8):X0(8) + 30]); s2 = (f.times(16)[30:90, X0(16):X0(16) + 30])
check(np.abs(s1 - s2).mean() < 0.05 * dur, f"dissolve: dissolve times travel with the object ({np.abs(s1 - s2).mean():.3f} s)")
i = 9
pa, pc = r["particles_alpha"][i], r["particles"][i]
w = pa > 0.05
red, blue = pc[w][:, 0].mean() / max(pa[w].mean(), 1e-6), pc[w][:, 2].mean() / max(pa[w].mean(), 1e-6)
check(w.sum() > 10 and red > 2 * blue, f"dissolve: early particles are red like the left half (r {red:.2f}, b {blue:.2f})")
check(r["stats"]["spawned"] > 100, f"dissolve: {r['stats']['spawned']} particles born")
P0 = dict(dv.DEFAULTS, density=1.0, push=0, lift=0, spread=0, inherit=0, gravity=0, turbulence=0, size=0, edge_noise=0.3)
r0 = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P=P0)
import cv2
ever = np.maximum.accumulate(masks, 0)
outside = sum(int(((r0["particles_alpha"][i] > 0) & (cv2.dilate(ever[i], np.ones((3, 3), np.uint8)) < 0.5)).sum()) for i in range(n))
check(outside == 0, "dissolve: without motion every particle stays where it was born, inside the object")
rh = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.7})
ratio = rh["stats"]["spawned"] / r["stats"]["spawned"]
check(1.7 < ratio < 2.3, f"dissolve: density 0.7 vs 0.35 gives {ratio:.2f}x particles")
rs = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "push": 200, "turbulence": 0})
check(rs["stats"]["spawned"] == r["stats"]["spawned"] and np.array_equal(rs["dissolve_mask"], r["dissolve_mask"]),
      "dissolve: changing the motion keeps the dissolve and the born particles (hash per pixel, no running generator)")
r2 = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3})
check(np.array_equal(r2["comp"], r["comp"]), "dissolve: same seed, same result")
cp = np.zeros_like(plate); cp[..., 1] = 1.0
rc = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": 0, "background": "clean"}, background=cp)
i = 25; x0 = X0(i)
check(rc["comp"][i, 40:80, x0 + 5:x0 + 25, 1].mean() > 0.95 and "clean plate" in rc["bg_info"], "dissolve: clean plate fills the hole")
cp2 = np.repeat(bgimg[None], n, 0) + np.array([0.06, -0.04, 0.05], np.float32)
e = {}
for mt in (0.0, 0.1):
    rr = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": mt, "background": "clean"}, background=cp2)
    e[mt] = float(np.abs(rr["comp"][25, 40:80, X0(25) + 5:X0(25) + 25] - bgimg[40:80, X0(25) + 5:X0(25) + 25]).mean())
check(e[0.0] > 0.04 and e[0.1] < 0.01, f"dissolve: clean plate colour matched to the plate (error {e[0.0]:.3f} -> {e[0.1]:.3f})")
rw = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": 0}, background=cp)
i = 25; x0 = X0(i)
real = float(np.abs(rw["comp"][i, 40:80, x0 + 5:x0 + 25] - bgimg[40:80, x0 + 5:x0 + 25]).mean())
pst = np.repeat(bgimg[None], n, 0).copy(); pst[:, 30:90, 80:110] = (0.9, 0.1, 0.1)
mst = np.zeros((n, H, W), np.float32); mst[:, 30:90, 80:110] = 1
rst = dv.dissolve(pst, mst, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": 0}, background=cp)
check(real < 0.01 and rst["comp"][25, 40:80, 85:105, 1].mean() > 0.95 and "clean plate where never free" in rw["bg_info"],
      f"dissolve: other frames first (walking: error {real:.3f} to the real background), clean plate where never free")
pmv = plate.copy()
for i in range(n):
    pmv[i, 40:80, 20:60] = (0.1, 0.9, 0.1) if (i // 3) % 2 else (0.9, 0.9, 0.1)
mfix = np.zeros((n, H, W), np.float32); mfix[:, 35:85, 15:65] = 1; mfix[:12] = 0; mfix[12:, 40:80, 20:60] = 1
cpr = np.repeat(bgimg[None], n, 0)
rv = dv.dissolve(pmv, mfix, 90.0, 1.4, 0.5, fps, seed=4, P={"edge_noise": 0.0, "density": 0.0, "cp_match": 0}, background=cpr)
dv_ = np.abs(rv["comp"][25, 45:75, 25:55] - bgimg[45:75, 25:55]).max(-1)
err_v, p99 = float(dv_.mean()), float(np.percentile(dv_, 99))
check(err_v < 0.08 and p99 < 0.25, f"dissolve: a moving unmasked thing in the other frames is not pasted in (mean {err_v:.3f}, p99 {p99:.3f})")
cpk = np.repeat(bgimg[None], n, 0).copy()
cpk[:, 30:60, 80:110] = pst[:, 30:60, 80:110]
rk = dv.dissolve(pst, mst, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": 0}, background=cpk)
red_left = float(rk["comp"][25, 35:55, 85:105, 0].mean() - rk["comp"][25, 35:55, 85:105, 1].mean())
check(red_left < 0.2, f"dissolve: where the clean plate kept the object it is filled in instead (red excess {red_left:.2f})")
rg = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "glow": 1.0})
check(rg["emission"][12].max() > 0.3 and rg["emission"][25].max() < 1e-3 and rg["emission"][3].max() < 1e-3,
      "dissolve: glowing edge at the front only while it runs")
u = dv.hash_u(np.arange(100000), seed=3)
check(abs(u.mean() - 0.5) < 0.01 and u.min() >= 0 and u.max() < 1 and np.array_equal(u[:10], dv.hash_u(np.arange(10), seed=3)),
      "hash: uniform 0..1 and the same for the same key")
from simpleeval import simple_eval
cpx = "max(64, round(a * (589824 / (a * b)) ** 0.5 / 64) * 64)"
cps = lambda a, b: (int(simple_eval(cpx, names={"a": a, "b": b}, functions={"max": max, "round": round})),
                    int(simple_eval(cpx, names={"a": b, "b": a}, functions={"max": max, "round": round})))
check((cps(2048, 1080), cps(1080, 1716), cps(1920, 1080)) == ((1088, 576), (640, 960), (1024, 576)),
      "clean plate size: aspect of the plate, ~1024x576 pixels, multiples of 64")
ref, = pack.NODE_CLASS_MAPPINGS["EFCleanPlateReference"]().make(torch.from_numpy(plate), torch.from_numpy(masks), 0.03, 0.01)
ref = ref.numpy()
inside_std = float(ref[10, 40:80, X0(10) + 3:X0(10) + 27].std(axis=(0, 1)).mean())
orig_std = float(plate[10, 40:80, X0(10) + 3:X0(10) + 27].std(axis=(0, 1)).mean())
check(inside_std < 0.6 * orig_std and np.abs(ref[10, :, :10] - plate[10, :, :10]).max() < 1e-5,
      f"clean plate reference: object blurred (std {orig_std:.2f} -> {inside_std:.2f}), the rest unchanged")
import warnings
rs_ = np.random.default_rng(5)
sm_ = rs_.uniform(0, 1, (12, 6, 7, 3)).astype(np.float32); va_ = rs_.uniform(0, 1, (12, 6, 7)) < 0.4
med_, spr_, cnt_ = dv.first_k_median(sm_, va_, 5)
ref_ = sm_.copy(); ref_[~(va_ & (np.cumsum(va_, 0) <= 5))] = np.nan
with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    rm_, rsd_ = np.nanmedian(ref_, 0), np.nanmean(np.nanstd(ref_, 0), -1)
ok_ = np.isnan(rm_) == np.isnan(med_)
check(ok_.all() and np.allclose(med_[~np.isnan(med_)], rm_[~np.isnan(rm_)]) and np.allclose(spr_[cnt_ > 0], rsd_[cnt_ > 0], atol=1e-5),
      "fast first-k median and spread equal nanmedian / nanstd")
D = pack.NODE_CLASS_MAPPINGS["EFDissolve"]
out = D().run(torch.from_numpy(plate), torch.from_numpy(masks), 90.0, start, dur, 1.0, 1.0, 1.0, 1.0, 0.3, 0.5, fps, 4)
sc, = pack.NODE_CLASS_MAPPINGS["EFScreen"]().screen(out[8], out[9][:, ::2, ::2], 1.0)
c0_, ng_, em_ = out[0].numpy(), out[8].numpy(), out[3].numpy()
unclipped = (c0_ < 0.97) & (ng_ + em_ < 0.97)
check(np.abs(c0_ - ng_ - em_)[unclipped].max() < 0.02 and tuple(sc.shape) == (n, H, W, 3)
      and float(sc.numpy().min()) >= 0 and float((sc.numpy() + 0.01 >= out[8].numpy()).mean()) > 0.999,
      "dissolve node: comp_no_glow = comp - emission; screen brightens only, scales the layer")
check(len(out) == 11 and tuple(out[0].shape) == (n, H, W, 3) and tuple(out[2].shape) == (n, H, W) and "particles" in out[7]
      and "other frames" in out[7] and out[10] is False, "dissolve node: outputs in plate size, report, plain = no LTX embers")
_sty = lambda st, g=0.0, ex="": D().run(torch.from_numpy(plate), torch.from_numpy(masks), 90.0, start, dur, 1.0, 1.0, 1.0, 1.0,
                                        0.3, g, fps, 4, extra=ex, style=st)
_set = lambda o_: json.loads(o_[7].split("settings: ", 1)[1])
fi, gd, fo = _sty("fire (LTX)"), _sty("Gold"), _sty("fire", 0.8, '{"tint": 0.2}')
try:
    _sty("smoke")
    bad_ = False
except ValueError as e_:
    bad_ = "gold dust" in str(e_)
check(bad_ and dv.style_name("") == "plain" and dv.style_name(" Fire (ltx) ") == "fire (LTX)", "dissolve style: short names, unknown name lists the choices")
check(fi[10] is True and gd[10] is False and _set(fi)["glow"] == 1.5 and _set(fi)["tint"] == 0.7 and _set(gd)["tint"] == 0.7
      and _set(fo)["glow"] == 0.8 and _set(fo)["tint"] == 0.2 and fi[7].startswith("style fire (LTX)")
      and float(gd[3].numpy().max()) > float(_sty("plain")[3].numpy().max()),
      "dissolve style: fire/gold dust = glow 1.5 + tint 0.7, fire = LTX embers; own glow and extra tint win")
bb = torch.zeros((2, 64, 96, 3)); lay = torch.full((2, 64, 96, 3), 0.5); band = torch.zeros((2, 64, 96, 3)); band[:, 30:34, 10:20] = 1
s1, = pack.NODE_CLASS_MAPPINGS["EFScreen"]().screen(bb, lay, 1.0, band=band, outside=0.2)
s0, = pack.NODE_CLASS_MAPPINGS["EFScreen"]().screen(bb, lay, 1.0, band=band)
near, far = float(s1[0, 32, 15, 0]), float(s1[0, 5, 80, 0])
check(near > 0.45 and abs(far - 0.1) < 0.02 and abs(float(s0[0, 5, 80, 0]) - 0.5) < 0.02,
      f"screen band: full at the edge ({near:.2f}), 0.2 away ({far:.2f}); outside 1 = as before")
rng_f = np.random.default_rng(3)
pl_f = np.full((6, 80, 120, 3), 0.4, np.float32) + rng_f.uniform(-0.01, 0.01, (6, 80, 120, 3)).astype(np.float32)
pl_f[0] += 0.1
mk_f = np.zeros((6, 80, 120), np.float32)
for j in range(6):
    mk_f[j, 30:50, 10 + 15 * j:30 + 15 * j] = 1
need_f = np.zeros((80, 120), bool); need_f[30:50, 10:30] = True
f0 = dv.SceneFill(pl_f, mk_f, 2, match=0.0).frame(0, need_f)
f1 = dv.SceneFill(pl_f, mk_f, 2, match=0.02).frame(0, need_f)
a0, a1 = float(f0[35:45, 15:25].mean()), float(f1[35:45, 15:25].mean())
check(abs(a0 - 0.4) < 0.02 and abs(a1 - 0.5) < 0.02 and float(np.abs(f1[5:20, 60:100] - pl_f[0, 5:20, 60:100]).max()) < 1e-6,
      f"scene fill light match: hole {a0:.3f} (other frames) -> {a1:.3f} (this frame 0.5), outside the hole untouched")
rng_g = np.random.default_rng(5)
pl_g = (0.4 + rng_g.normal(0, 0.03, (80, 120, 1)).astype(np.float32)).repeat(3, -1)
soft_g = np.full((80, 120, 3), 0.4, np.float32)
need_g = np.zeros((80, 120), np.float32); need_g[20:60, 30:90] = 1
around_g = need_g == 0
out_g = dv.regrain(soft_g, pl_g, need_g, around_g, 1.0, np.random.default_rng(1))
sharp_g = dv.regrain(pl_g.copy(), pl_g, need_g, around_g, 1.0, np.random.default_rng(1))
sd_in = float(out_g[30:50, 40:80, 0].std()); sd_pl = float(pl_g[30:50, 40:80, 0].std())
check(0.5 * sd_pl < sd_in < 1.6 * sd_pl and float(np.abs(out_g[5:15, 5:20] - soft_g[5:15, 5:20]).max()) < 1e-6
      and float(np.abs(sharp_g - pl_g).mean()) < 0.006,
      f"regrain: soft fill gets grain {sd_in:.3f} (plate {sd_pl:.3f}), outside untouched, a sharp fill hardly changes")
gd_ = out[9].numpy(); pa_ = out[1].numpy()
end_f = int(np.ceil((start + dur + 0.3) * fps)) + 1
late = [i for i in range(end_f, n) if pa_[i].max() > 0.02]
mid = int((start + 0.5 * dur) * fps)
check((not late or max(float(gd_[i].max()) for i in late) < 0.02)
      and float(gd_[mid].max()) > 0.05,
      f"ember guide: particles leave it {0.3} s after the end ({len(late)} late frames with particles), full during the dissolve")
out_t = D().run(torch.from_numpy(plate), torch.from_numpy(masks), 90.0, start, dur, 1.0, 1.0, 1.0, 1.0, 0.3, 1.5, fps, 4,
               extra='{"tint": 0.7}')
gd_t = out_t[9].numpy(); late_t = [i for i in range(end_f, n) if out_t[1].numpy()[i].max() > 0.02]
check(bool(late_t) and max(float(gd_t[i].max()) for i in late_t) < 0.02 and float(out_t[3].numpy()[late_t].max()) > 0.05,
      f"ember guide with tinted particles: their glow in the emission leaves the guide too ({len(late_t)} late frames)")
Pf = dict(dv.DEFAULTS)
f1 = dv.fit_duration(81, 30.0, 0.8, 2.0, Pf)
f2 = dv.fit_duration(81, 25.0, 0.8, 2.0, Pf)
f3 = dv.fit_duration(81, 30.0, 3.0, 1.0, Pf)
f4 = dv.fit_duration(81, 30.0, 0.8, 2.0, dict(Pf, fit_clip=0.0))
f5 = dv.fit_duration(30, 10.0, 1.0, 2.0, Pf)
end1 = 0.8 + f1["duration"] * (1 + Pf["softness"] / 2) + Pf["guide_tail"]
check(abs(end1 - 80 / 30) < 1e-6 and "shortened" in f1["note"] and f2["duration"] == 2.0 and f2["note"] == ""
      and "starts at" in f3["note"] and f4["duration"] == 2.0 and "still burning" in f4["note"] and f5["duration"] < 2.0,
      f"duration fitted to the clip: statue 2.0 -> {f1['duration']:.2f} s (ends with the ember fade at the last frame), "
      "25 fps unchanged, start after the clip noted, fit_clip 0 keeps it, a 3.0 s end in a 2.9 s clip counts")
out_l = D().run(torch.from_numpy(plate), torch.from_numpy(masks), 90.0, start, n / fps, 1.0, 1.0, 1.0, 1.0, 0.3, 0.0, fps, 4)
check("shortened" in out_l[7] and "NOTE" not in out[7], "the node shortens a too long dissolve and says so in the report")
mk_e = np.zeros((40, 60, 80), np.float32); mk_e[10:, 20:40, 60:70] = 1
fe = dv.Field(mk_e, 90.0, 0.5, 1.0, dict(dv.DEFAULTS), 1, 25.0)
check(abs(float(fe.c[10, 0]) - 64.5) < 0.6 and abs(float(fe.c[0, 0]) - 64.5) < 0.6,
      f"front centre with empty first frames: frame 10 at x {fe.c[10, 0]:.1f} (object 64.5), not pulled to the centre")
mk_g = np.zeros((50, 60, 120), np.float32); mk_g[:, 25:35, 55:65] = 1; mk_g[30:, 25:35, 20:110] = 1
fg = dv.Field(mk_g, 90.0, 1.4, 0.4, dict(dv.DEFAULTS, edge_noise=0.0, grain=0.0), 1, 25.0)
tg = fg.times(40)[30, 20:110]
check(float((tg <= 1.4 + 1e-4).mean()) < 0.05 and float((tg >= 1.8 - 1e-4).mean()) < 0.05,
      f"front spans the object at dissolve time: {float((tg <= 1.4001).mean()):.0%} at the start, "
      f"{float((tg >= 1.7999).mean()):.0%} at the end in one frame")
dif_ = np.zeros((540, 960, 3), np.float32); dif_[:270] = 0.08
w_ = np.ones((540, 960), np.float32); w_[100:460, 280:680] = 0
off_ = dv.lowfreq_offset(dif_, w_, 0.02 * np.hypot(540, 960))
jump = float(np.abs(np.diff(off_[100:460, 280:680, 0], axis=0)).max()) * 255
check(jump < 1.0, f"light/colour match without a seam in a large hole: largest step {jump:.2f}/255 (was 11-19)")
g_ = np.tile(np.linspace(0.2, 0.25, 200, dtype=np.float32), (100, 1))[..., None].repeat(3, -1)
h_ = np.zeros((100, 200), bool); h_[40:60, 80:120] = True
ip_ = dv.inpaint_f(g_, h_, 5)[h_]
check(float(np.abs(ip_ * 255 - np.round(ip_ * 255)).max()) > 0.05, "inpaint of the hole in float, not snapped to 8-bit steps")
big_ = cv2.GaussianBlur(np.random.default_rng(0).uniform(0.1, 0.3, (180, 320, 3)).astype(np.float32), (0, 0), 4)
bh_ = np.zeros((180, 320), bool); bh_[50:140, 100:160] = True
bi_ = dv.inpaint_f(big_, bh_, 5)[bh_]
check(float(bi_.min()) >= float(big_.min()) - 0.01 and float(bi_.max()) <= float(big_.max()) + 0.01,
      f"inpaint of a large hole stays in the image's range ({bi_.min():.3f}..{bi_.max():.3f})")
base_ = np.full((120, 200, 3), 0.1, np.float32)
for x_ in range(-200, 260, 23):
    cv2.line(base_, (x_, 0), (x_ + 60, 119), (0.3, 0.55, 1.0), 2, cv2.LINE_AA)
cur_ = base_.copy()
src_ = np.roll(base_, 3, 1)
nd_ = np.zeros((120, 200), bool); nd_[30:90, 70:130] = True
cur_[nd_] = 0.05
al_ = dv.seam_align(cur_, src_, ~nd_, 1.0, math.hypot(120, 200))
edge_ = nd_ & ~cv2.erode(nd_.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
e0_ = float(np.abs(src_ - base_)[edge_].mean()); e1_ = float(np.abs(np.nan_to_num(al_) - base_)[edge_].mean())
check(e1_ < 0.4 * e0_ and dv.DEFAULTS["fill_align"] == 0,
      f"fill_align (off by default): a 3 px shifted fill laid onto the frame at the hole's edge (error {e0_:.3f} -> {e1_:.3f})")
pc0 = np.random.default_rng(5).uniform(0, 1, (4, 1080, 1920, 3)).astype(np.float32)
mc0 = np.zeros((4, 1080, 1920), np.float32)
for j in range(4):
    mc0[j, 400:700, 800 + 40 * j:1000 + 40 * j] = 1
cr, cw_, ch_, inf_ = pack.NODE_CLASS_MAPPINGS["EFCleanPlateCrop"]().crop(torch.from_numpy(pc0), torch.from_numpy(mc0), 0.08)
bx_ = json.loads(inf_)["box"]
gen_ = cr.numpy() * 0 + 0.5
un_, = pack.NODE_CLASS_MAPPINGS["EFCleanPlateUncrop"]().uncrop(torch.from_numpy(pc0), torch.from_numpy(gen_), inf_)
un_ = un_.numpy()
x0_, y0_, x1_, y1_ = bx_
check(cw_ % 64 == 0 and ch_ % 64 == 0 and cw_ * ch_ <= 589824 * 1.1 and x0_ < 800 and x1_ > 1120 and y0_ < 400 and y1_ > 700
      and abs((cw_ / ch_) - (x1_ - x0_) / (y1_ - y0_)) < 0.15 and np.allclose(un_[:, y0_:y1_, x0_:x1_], 0.5, atol=1e-3)
      and np.array_equal(un_[:, :y0_], pc0[:, :y0_]) and (x1_ - x0_) * (y1_ - y0_) < 0.5 * 1920 * 1080,
      f"clean plate crop: box {bx_} around the object in every frame, generate {cw_}x{ch_}, put back in place, plate outside")
pl_ = np.random.default_rng(6).uniform(0.05, 0.95, (3, 90, 160, 3)).astype(np.float32)
cp_ = pl_ + np.random.default_rng(7).integers(-1, 2, pl_.shape).astype(np.float32) / 255
cp_[:, 30:60, 50:90] = 0.2
cp_[:, 10, 120] += 0.08
cp_ = np.clip(cp_, 0, 1)
mk_ = np.zeros((3, 90, 160), np.float32); mk_[:, 25:65, 45:95] = 1
el_, al_ = pack.NODE_CLASS_MAPPINGS["EFCompToLayer"]().run(torch.from_numpy(cp_), torch.from_numpy(pl_), 0.012, 0.004, torch.from_numpy(mk_))
el_, al_ = el_.numpy(), al_.numpy()
re_ = dv.srgb_lin(pl_) * (1 - al_[..., None]) + el_
err_ = np.abs(re_ - dv.srgb_lin(np.clip(cp_, 0, 1)))
check(err_[:, 30:60, 50:90].max() < 1e-5 and err_[:, 10, 120].max() < 1e-5 and err_.max() < 0.01 and al_[:, 25:65, 45:95].min() == 1
      and al_[:, 75:, :30].max() == 0 and el_.shape == (3, 90, 160, 3),
      f"comp to layer: the layer over the plate gives the comp back (hole and faint particle exact, elsewhere at most "
      f"{err_.max():.4f} linear = one sRGB step of dither near white), alpha 1 over the object mask, 0 far away")
flow_ = lambda i: dv.flow_field(plate[i], plate[min(i + 1, n - 1)]) if i + 1 < n else dv.flow_field(plate[i - 1], plate[i])
rc0 = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P=dict(P0, motion_carry=0.0), flow=flow_)
rc1 = dv.dissolve(plate, masks, 90.0, start, dur, fps, seed=4, P=dict(P0, motion_carry=1.0), flow=flow_)
i = 20
on_obj = lambda r: float((r["particles_alpha"][i] * cv2.dilate(masks[i], np.ones((5, 5), np.uint8))).sum() / max(r["particles_alpha"][i].sum(), 1e-6))
cx_ = lambda r: float((r["particles_alpha"][i] * xx).sum() / max(r["particles_alpha"][i].sum(), 1e-6))
check(on_obj(rc1) > 0.8 and on_obj(rc0) < 0.6 and cx_(rc1) > cx_(rc0) + 8 and rc1["stats"]["spawned"] == rc0["stats"]["spawned"],
      f"dissolve motion carry: the walking object carries its particles along ({on_obj(rc1):.0%} on it at frame {i}, "
      f"without carry {on_obj(rc0):.0%}; centre x {cx_(rc1):.0f} vs {cx_(rc0):.0f}), same particles born")
rna = dv.dissolve(pst, mst, 90.0, start, dur, fps, seed=4, P={"edge_noise": 0.3, "density": 0.0, "cp_match": 0, "fill_align": 1.0}, background=cp)
check(all(np.isfinite(rna[k]).all() for k in ("comp", "background")) and float(rna["comp"][-1].mean()) > 0.1,
      "fill_align with a clean plate: the comp stays finite (no NaN from the shifted fill)")
n_r, H_r, W_r = 6, 120, 120
pl_r = np.zeros((n_r, H_r, W_r, 3), np.float32); pl_r[..., 0] = 0.6; pl_r[..., 1] = 0.1; pl_r[..., 2] = 0.1
mk_r = np.zeros((n_r, H_r, W_r), np.float32); mk_r[:, 30:60, 40:80] = 1; mk_r[:, 60:110, 56:64] = 1
pl_r[:, 60:110, 56:64] = (0.1, 0.5, 0.1)
pl_r[:, 30:60, 40:80] = (0.4, 0.0, 0.05)
sf_r = dv.SceneFill(pl_r, mk_r, 3, match=0.02)
need_r = np.zeros((H_r, W_r), bool); need_r[30:60, 40:80] = True
f_r = sf_r.frame(2, need_r)[30:60, 40:80]
green = float((f_r[..., 1] - f_r[..., 0]).max())
check(green < -0.3 and sf_r.holes > 0.99, f"never free hole inpainted from the background only: no green from the stem (green - red at most {green:.2f})")
rng_b = np.random.default_rng(3)
n_b, H_b, W_b = 5, 180, 320
mk_b = np.zeros((n_b, H_b, W_b), np.float32); mk_b[:, 60:120, 130:190] = 1
smooth_b = np.full((n_b, H_b, W_b, 3), 0.45, np.float32) + np.linspace(0, 0.1, W_b, dtype=np.float32)[None, None, :, None]
smooth_b += rng_b.normal(0, 0.004, smooth_b.shape).astype(np.float32)
leaves_b = np.clip(cv2.GaussianBlur(rng_b.random((H_b, W_b)).astype(np.float32), (0, 0), 1.2) * 1.4 - 0.2, 0.02, 1)
leaves_b = np.repeat(np.repeat(leaves_b[None, ..., None], n_b, 0), 3, 3)
sc_s, sc_l = dv.background_structure(smooth_b, mk_b), dv.background_structure(leaves_b, mk_b)
bgn = dv.EFDissolveBackground()
t_ = lambda a: torch.from_numpy(np.ascontiguousarray(a))
d_s, d_l = bgn.decide(t_(smooth_b), t_(mk_b))[0], bgn.decide(t_(leaves_b), t_(mk_b))[0]
d_set = (bgn.decide(t_(smooth_b), t_(mk_b), " Structured ")[0], bgn.decide(t_(leaves_b), t_(mk_b), "smooth")[0],
         bgn.decide(t_(leaves_b), t_(mk_b), "structured", clean_plate=False)[0])
try:
    bgn.decide(t_(smooth_b), t_(mk_b), "sky")
    bad_b = False
except ValueError as ex:
    bad_b = "smooth" in str(ex)
check(sc_s < dv.BG_SMOOTH <= sc_l and d_s is False and d_l is True and d_set == (True, False, False) and bad_b,
      f"dissolve background: smooth {sc_s:.4f} -> filled without the AI, leaves {sc_l:.4f} -> clean plate; a set choice wins, "
      f"clean plate off always wins, an unknown name lists the choices")
Pe, sty_e = dv.node_params(1.0, 1.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 1.0, 0.0, "expl", "", "scene")
check(sty_e == "explodes" and Pe["radial"] == 1.0 and Pe["burst"] == 0.12 and Pe["push"] == 900.0
      and dv.node_params(1.0, 2.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 1.0, 0.0, "explodes", "", "scene")[0]["push"] == 1800.0
      and dv.node_params(1.0, 1.0, 1.0, 1.0, 0.5, 0.0, "#ff8c26", 1.0, 0.0, "plain", "", "scene")[0].get("radial", 0) == 0,
      "explodes: the style brings radial and burst, its speeds follow the node's speed; plain stays as it was")
ne = 24
pex = np.repeat(bgimg[None], ne, 0).copy()
mex = np.zeros((ne, H, W), np.float32)
disk = (xx - 100) ** 2 + (yy - 60) ** 2 < 25 ** 2
pex[:, disk] = (0.8, 0.8, 0.2)
mex[:, disk] = 1.0
Px = dict(Pe, edge_noise=0.0, grain=0.0)
re_ = dv.dissolve(pex, mex, 90.0, 0.5, 1.5, fps, seed=4, P=Px)
tx = re_["field"].times(10)
check(tx[disk].max() <= 0.5 + 0.12 + 1e-3 and tx[60, 100] < tx[60, 122],
      f"explodes: the whole object breaks within the burst ({tx[disk].max() - 0.5:.3f} s), the centre first")
check(re_["dissolve_mask"][8][disk].min() > 0.99 and re_["person_matte"][8].max() < 1e-3,
      "explodes: after the burst the object is gone")
pa_ = re_["particles_alpha"][7]
left, right, up_ = pa_[:, :70].sum(), pa_[:, 130:].sum(), pa_[:30].sum()
rp = dv.dissolve(pex, mex, 90.0, 0.5, 1.5, fps, seed=4, P=dict(Px, radial=0.0))["particles_alpha"][7]
check(left > 0.2 * right and right > 0.2 * left and up_ > 0 and rp[:, :70].sum() < 0.2 * rp[:, 130:].sum(),
      f"explodes: the pieces fly out to every side (left {left:.0f}, right {right:.0f}); without radial they go with the direction")
Hh, Ww = 400, 300
gy, gx = np.mgrid[0:Hh, 0:Ww]
smooth_bg = np.stack([0.08 + 0.05 * gx / Ww + 0.03 * gy / Hh] * 3, -1).astype(np.float32)
wide = np.zeros((Hh, Ww), bool)
wide[150:400, 90:210] = True
pp, te = dv.pushpull_fill(smooth_bg, wide), dv.inpaint_f(smooth_bg, wide, 5)
step = lambda x: float(np.abs(np.diff(x[300, 95:205, 0])).max())
check(step(pp) < 0.3 * step(te) and np.abs(pp - smooth_bg)[wide].mean() < 0.01 and np.array_equal(pp[~wide], smooth_bg[~wide]),
      f"wide hole: push-pull fill without a seam (largest step {step(pp):.5f}, TELEA {step(te):.5f}), the rest untouched")
print(f"{ok} checks passed")

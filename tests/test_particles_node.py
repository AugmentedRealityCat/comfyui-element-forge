import importlib
import json
import os
import sys

import cv2
import numpy as np
import torch

import tempfile
import types

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

import json as _json
EFParticles = pack.NODE_CLASS_MAPPINGS["EFParticles"]
EFParticleSettings = pack.NODE_CLASS_MAPPINGS["EFParticleSettings"]
EFPlaceLayer = pack.NODE_CLASS_MAPPINGS["EFPlaceLayer"]
ok = 0


def check(cond, msg):
    global ok
    if not cond:
        raise AssertionError(msg)
    ok += 1
    print("ok  ", msg)


n, H, W = 25, 240, 320
rng = np.random.default_rng(0)
plate = torch.from_numpy((rng.uniform(0.2, 0.4, (n, H, W, 3))).astype(np.float32))
trA = {"plate_size": [W, H], "frames": n, "point_track_px": [[100 + 2 * i, 150] for i in range(n)]}
trB = {"plate_size": [W, H], "frames": n, "point_track_px": [[260, 80]] * n}
win = {"plate_size": [W, H], "frames": n, "crop_origin_plate_px": [[40, 40]] * n, "scale_roi_per_plate_px": 2.0, "roi_size": [256, 256]}
depth = torch.from_numpy(np.repeat(np.tile(np.linspace(0.2, 0.9, H, dtype=np.float32)[:, None], (1, W))[None, ..., None], n, 0).repeat(3, -1))
args = dict(amount=1.0, speed=1.0, size=1.0, life=1.0, direction=-1.0, spread=-1.0, follow=-1.0, start_seconds=0.0, fps=25.0, seed=3)
out = EFParticles().run(plate, "sparks", "point A", track=trA, depth=depth, window=win, camera="fixed", **args)
g, tracks, w, h, sd, sa, sop, al, reg, hold, prev, rep, _isig, _blend, _look, _look_l = out
check(g.shape == (n, 256, 256, 3) and sd.shape == (n, 256, 256, 3) and (w, h) == (256, 256), "particles: guide and seed in the window raster")
check(sop.shape == plate.shape and al.shape == (n, H, W) and reg.shape == (n, H, W) and hold.shape == (n, H, W), "particles: plate masks in plate size")
check(_look_l.shape == plate.shape and float(_look_l.abs().max()) == 0 and _look_l.untyped_storage().nbytes() == H * W * 3 * 4,
      "particles: without the direct look the look layer is black, one frame of memory for the whole clip")
tr = _json.loads(tracks)
check(len(tr) > 0 and all(len(t) >= 8 and {"x", "y"} <= set(t[0]) for t in tr), f"particles: {len(tr)} tracks in LTXVDrawTracks format")
check(float(g.max()) > 0.5 and float(sa.max()) > 0.5 and float(reg.max()) > 0.5, "particles: guide, seed alpha and region not empty")
check("sparks" in rep and "settings:" in rep, "particles: report lists the settings")
st, = EFParticleSettings().make(1.5, 1.0, 1.0, 1.0, 1.0, -1.0, 0.4, -1.0, "stick", "preset", "volume", 3, "#ff0000", -1.0, -1, '{"vortex": 200}')
check(st == {"gravity*": 1.5, "fade_out": 0.4, "collide": "stick", "guide_style": "volume", "trail": 3, "colors": [[0.0, [1.0, 0.0, 0.0]], [1.0, [1.0, 0.0, 0.0]]], "vortex": 200}, "particle settings: only changed values")
out2 = EFParticles().run(plate, "magic dust", "line A-B", track=trA, track_b=trB, settings=st, camera="follow the plate", **args)
check(out2[0].shape[1:3] == (H, W) and "magic dust" in out2[11], "particles: line A-B without window draws in the plate, camera follows")
m = torch.zeros((n, H, W)); m[:, 80:160, 120:220] = 1
out3 = EFParticles().run(plate, "magic dust", "object contour", mask=m, depth=depth, **args)
check(float(out3[7].max()) > 0.3, "particles: contour emitter from a mask")
out4 = EFParticles().run(plate, "lightning", "point A", track=trA, track_b=trB, **args)
check(float(out4[0].max()) > 0.5 and float(out4[4].max()) > 0.3, "particles: lightning bolt from A to B")
out5 = EFParticles().run(plate, "snow", "whole frame", depth=depth, **args)
check(float(out5[7].mean()) > 0.003 and "landed" in out5[11], "particles: snow over the whole frame")
lay = torch.ones((n, 64, 64, 3)) * 0.5
track = {"frames": n, "crop_origin_plate_px": [[0, 0]] * n, "scale_roi_per_plate_px": 0.2, "roi_size": [64, 64]}
c1, l1, a1 = EFPlaceLayer().place(plate, lay, track, 1.0)
ho = torch.ones((n, H, W)); ho[:, :, : W // 2] = 0
c2, l2, a2 = EFPlaceLayer().place(plate, lay, track, 1.0, holdout=ho)
check(float(l2[:, :, : W // 2].max()) == 0 and float(l2[:, :, W // 2:].mean()) == float(l1[:, :, W // 2:].mean()), "place layer: holdout cuts the layer")
spr = torch.zeros((3, 16, 16, 4)); spr[:, 4:12, 4:12] = torch.tensor([1.0, 0.0, 0.0, 1.0])
out6 = EFParticles().run(plate, "embers", "point A", track=trA, sprite=spr, settings={"size*": 4.0, "sprite": "custom"}, **args)
sd6 = out6[4].numpy()
red = (sd6[..., 0] > 0.3) & (sd6[..., 1] < 0.1)
check(red.sum() > 50, "particles: own sprite (red square flipbook) appears in the seed")
trA7 = {"plate_size": [W, H], "frames": n, "point_track_px": [[160, 220]] * n}
out7 = EFParticles().run(plate, "smoke", "point A", track=trA7, camera="fixed", **args)
a7 = out7[5].numpy()[-1]
ys, xs = np.nonzero(a7 > 0.02)
check(len(ys) > 200 and ys.min() < 190, f"particles: smoke (wisp sprite) rises as a plume (top {ys.min()} px, emitter at 220)")
core = a7[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
check(core.std() > 0.04, f"particles: smoke has wisps and holes, not one smooth blob (alpha std {core.std():.3f})")
roi_ab = pack.NODE_CLASS_MAPPINGS["EFTrackROI"]().track(plate, 100, 150, 30, n, 96, 96, 64, 64, 0.5, 0.5, 0.0, 0.3, 0.3, False,
                                                         between=True, track_b=trB)[2]
o_ab = np.asarray(roi_ab["crop_origin_plate_px"][0]); p_ab = np.asarray(roi_ab["point_track_px"][0])
check(np.allclose(o_ab + 48, (p_ab + np.array([260, 80])) / 2, atol=1.0) and np.allclose(p_ab, [100, 150], atol=2.0),
      "track roi: window between A and B, the point track stays A")
roi_fit = pack.NODE_CLASS_MAPPINGS["EFTrackROI"]().track(plate, 100, 150, 30, n, 96, 96, 64, 64, 0.5, 0.5, 0.0, 0.3, 0.3, False,
                                                          between=True, track_b=trB, fit_ab=True)[2]
o_f = np.asarray(roi_fit["crop_origin_plate_px"]); p_f = np.asarray(roi_fit["point_track_px"]); side = 64 / roi_fit["scale_roi_per_plate_px"]
inside = all(o_f[i, 0] < p[0] < o_f[i, 0] + side and o_f[i, 1] < p[1] < o_f[i, 1] + side
             for i in range(n) for p in (p_f[i], np.array([260, 80])))
check(inside and side > 2 * 160, f"track roi: fit_ab sizes the window from A and B ({side:.0f} px), both points inside in every frame")
aura_on = EFParticles().run(plate, "aura", "object contour", mask=m, depth=depth, **args)
aura_up = EFParticles().run(plate, "aura", "object contour", mask=m, depth=depth, depth_offset=0.15, **args)
md_up = EFParticles().run(plate, "magic dust", "object contour", mask=m, depth=depth, **args)
check("aura" in aura_on[11] and float(aura_on[8].sum()) < float(aura_up[8].sum())
      and abs(float(aura_up[8].sum()) - float(md_up[8].sum())) < 1e-3 * max(1.0, float(md_up[8].sum())),
      "particles: aura preset sits behind (-0.15), the node offset is added (aura +0.15 = magic dust)")
rnd = "max(32 * (1 + max(b, c)), round(a / (32 * (1 + max(b, c)))) * 32 * (1 + max(b, c)))"
from simpleeval import simple_eval
val = lambda a, b, c: int(simple_eval(rnd, names={"a": a, "b": b, "c": c}, functions={"max": max, "round": round}))
check((val(480, False, False), val(480, True, False), val(672, True, False), val(700, False, True), val(10, True, False))
      == (480, 512, 640, 704, 64), "generate size rounding: 32 without guide, 64 with guide or inpaint, never below one step")
ptm = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.particles")
Hh, Wh = 120, 160
dmap = np.full((1, Hh, Wh), 0.2, np.float32); dmap[:, :, :60] = 0.9
rg = np.random.default_rng(2)
px_ = np.concatenate([rg.uniform(10, 150, 400), rg.uniform(100, 140, 6)])
py_ = np.concatenate([rg.uniform(20, 100, 400), rg.uniform(40, 80, 6)])
pz_ = np.concatenate([np.full(400, 0.5), np.full(6, 0.05)])
rec_ = {"x": px_[None], "y": py_[None], "z": pz_[None], "alpha": np.ones((1, 406)), "size": np.full((1, 406), 2.0)}
em_ = types.SimpleNamespace(depth=types.SimpleNamespace(d=dmap))
reg_, hold_ = ptm.masks_from(np.ones((1, Hh, Wh), np.float32), rec_, em_, {"depth_softness": 0.05})
wall, open_ = hold_[0, 30:90, 10:50], hold_[0, 30:90, 100:140]
check(wall.max() < 0.05 and open_.min() > 0.9, f"holdout: wall cuts sharply ({wall.max():.2f}), no holes from stray hidden particles ({open_.min():.2f})")
VLM = pack.NODE_CLASS_MAPPINGS["EFVideoLatentMask"]
lat = {"samples": torch.zeros((1, 128, 3, 8, 8))}
mk = torch.zeros((17, 256, 256)); mk[12, 0:40, 0:40] = 1
lm, = VLM().make(lat, mk, grow=0, floor=0.0)
nm = lm["noise_mask"]
check(tuple(nm.shape) == (1, 1, 3, 8, 8) and float(nm[0, 0, 2, 0, 0]) == 1.0 and float(nm[0, 0, 1].max()) == 0.0
      and float(nm[0, 0, 2, 4, 4]) == 0.0, "video latent mask: 5D, union over the 8 pixel frames of a latent frame")
ptn = importlib.import_module(os.path.basename(PACK) + ".element_forge.simulation.particles")
oc = EFParticles().run(plate, "cracks", "point A", track=trA, **args)
of = EFParticles().run(plate, "frost", "point A", track=trA, **args)
ou = EFParticles().run(plate, "frost", "point A", track=trA, inpaint_sigmas="0.95, 0.5, 0.0", **args)
osp = EFParticles().run(plate, "sparks", "point A", track=trA, **args)
check(oc[12] == ptn.STRONG_INPAINT and of[12] == ptn.STRONG_INPAINT and ou[12] == "0.95, 0.5, 0.0" and osp[12] == ptn.STANDARD_INPAINT
      and float(of[4].max()) > 0.3, "inpaint start: cracks/frost 0.9875 from the preset, own value wins, others standard; frost draws")
dco = np.full((1, 60, 80), 0.2, np.float32); dco[:, :, :32] = 0.9
gpl = np.full((1, Hh, Wh, 3), 0.15, np.float32); gpl[:, :, :66] = 0.8
pxg, pyg = rg.uniform(10, 150, 800), rg.uniform(20, 100, 800)
recg = {"x": pxg[None], "y": pyg[None], "z": np.full((1, 800), 0.5), "alpha": np.ones((1, 800)), "size": np.full((1, 800), 2.0)}
emg = types.SimpleNamespace(depth=types.SimpleNamespace(d=dco))
_, hg0 = ptm.masks_from(np.ones((1, Hh, Wh), np.float32), recg, emg, {"depth_softness": 0.05})
_, hg1 = ptm.masks_from(np.ones((1, Hh, Wh), np.float32), recg, emg, {"depth_softness": 0.05}, guide=gpl)
cross = lambda h: float(np.interp(0.5, h[0, 40:80, 50:85].mean(0), np.arange(50, 85)))
check(abs(cross(hg1) - 66) < 1.0 and abs(cross(hg1) - 66) < 0.5 * abs(cross(hg0) - 66) and float(hg1[0, 60, 20]) < 0.05 and float(hg1[0, 60, 140]) > 0.95,
      f"holdout follows the plate edge: cut at x {cross(hg1):.1f} with the plate (edge 66), {cross(hg0):.1f} from depth alone")
half = torch.full((n, H, W, 3), 0.1); half[:, :, W // 2:] = 0.9
xd, xb = W // 4, 3 * W // 4
lay_r = torch.zeros((n, H, W, 3)); lay_r[:, :, xd - 1:xd + 1] = 0.6; lay_r[:, :, xb - 1:xb + 1] = 0.6
tr_r = {"frames": n, "crop_origin_plate_px": [[0, 0]] * n, "scale_roi_per_plate_px": 1.0, "roi_size": [W, H]}
cr = EFPlaceLayer().place(half, lay_r, tr_r, 1.0, blend_from="contrast (rain)")[0][0, 100, :, 0].numpy()
ca = EFPlaceLayer().place(half, lay_r, tr_r, 1.0)[0][0, 100, :, 0].numpy()
rain_o = EFParticles().run(plate, "rain", "whole frame", depth=depth, **args)
spark_o = EFParticles().run(plate, "sparks", "point A", track=trA, **args)
blob = torch.zeros((n, H, W, 3)); blob[:, 60:180, 180:300] = 0.4
cbl = EFPlaceLayer().place(half, blob, tr_r, 1.0, blend_from="contrast (rain)")[0][0, 120, 240, 0].item()
check(cbl > 0.88 and cr[xd] > 0.3 and cr[xb] < 0.8 and ca[xb] > 0.89 and abs(cr[xd] - ca[xd]) < 1e-4
      and rain_o[13] == "contrast (rain)" and spark_o[13] == "add",
      f"contrast blend: streak lighter on dark ({cr[xd]:.2f}), darker on bright ({cr[xb]:.2f}, add {ca[xb]:.2f}), haze not darkened ({cbl:.2f}); rain preset uses it")
lk = EFParticles().run(plate, "sparks", "point A", track=trA, window=win, camera="fixed", direct_look=True, **args)
lo = lk[14].numpy()
la = EFParticles().run(plate, "sparks", "point A", track=trA, camera="fixed", **args)[7].numpy()
dd = lo - plate.numpy()
far = np.stack([cv2.distanceTransform((x < 0.01).astype(np.uint8), cv2.DIST_L2, 3) > 40 for x in la])
bright = float(dd[la > 0.3].mean())
bright_b = np.ones((n, H, W, 3), np.float32) * 0.9
sm = EFParticles().run(torch.from_numpy(bright_b), "smoke", "point A", track=trA, camera="fixed", direct_look=True, **args)
sd_ = sm[14].numpy() - bright_b
rn = EFParticles().run(half, "rain", "whole frame", camera="fixed", direct_look=True, **args)
rd, ra = rn[14].numpy() - half.numpy(), rn[7].numpy()
rdark, rbright = float(rd[:, :, : W // 2][ra[:, :, : W // 2] > 0.2].mean()), float(rd[:, :, W // 2:][ra[:, :, W // 2:] > 0.2].mean())
check(torch.equal(spark_o[14], plate) and float(spark_o[15].abs().max()) == 0 and lk[15].shape == plate.shape
      and float(lk[15].numpy()[far].max()) < 1e-3 and float(lk[15].max()) > 0.1 and bright > 0.05 and float(np.abs(dd[far]).max()) < 3 / 255
      and float(sd_[sm[7].numpy() > 0.3].mean()) < -0.03 and rdark > 0.02 and rbright < -0.02,
      f"direct look: off = plate; sparks +{bright:.2f} (far {float(np.abs(dd[far]).max()) * 255:.1f}/255); smoke over bright "
      f"{float(sd_[sm[7].numpy() > 0.3].mean()):+.2f}; rain dark {rdark:+.2f}, bright {rbright:+.2f}")
dark_b = np.ones((n, H, W, 3), np.float32) * 0.08
smd = EFParticles().run(torch.from_numpy(dark_b), "smoke", "point A", track=trA, camera="fixed", direct_look=True, **dict(args, amount=4.0))
dl_ = smd[14].numpy()[..., 0]
reg = smd[7].numpy() > 0.3
cov = (dl_[reg] - 0.08) / max(float(dl_[reg].max()) - 0.08, 1e-6)
check(reg.any() and float(dl_[reg].mean()) < 0.2 and float(np.mean(cov > 0.97)) < 0.15,
      f"smoke look on dark: dim ({float(dl_[reg].mean()):.2f}), not one flat shape ({float(np.mean(cov > 0.97)):.0%} at the top value)")
mm_, = pack.NODE_CLASS_MAPPINGS["EFMarginMask"]().make(256, 320, 17, 0.25)
lm2, = VLM().make({"samples": torch.zeros((1, 128, 3, 10, 8))}, mm_, grow=0, floor=0.0)
nm2 = lm2["noise_mask"][0, 0]
check(float(nm2[:, 0].max()) == 0 and float(nm2[:, :, 0].max()) == 0 and float(nm2[:, 5, 4].min()) == 1,
      "margin mask: border latent cells kept, inside free")

nl, Hl, Wl = 12, 150, 200
pl_l = torch.full((nl, Hl, Wl, 3), 0.1)
ratios = []
for ef in (0.08, 0.0):
    lo_ = EFParticles().run(pl_l, "rain", "whole frame", camera="fixed", direct_look=True, edge_fade=ef, **args)
    dl2 = (lo_[14].numpy() - 0.1).mean(-1)
    ratios.append(float(np.concatenate([dl2[:, :, :6].ravel(), dl2[:, :, -6:].ravel()]).mean() / dl2[:, :, Wl // 2 - 30:Wl // 2 + 30].mean()))
    sa_ = lo_[5].numpy()
check(ratios[0] > 0.6 and abs(ratios[0] - ratios[1]) < 0.1,
      f"direct look without window: rain reaches the plate border with edge fade 0.08 too (border/centre {ratios[0]:.2f}, without fade {ratios[1]:.2f})")


def _try(f):
    try:
        return f(), None
    except ValueError as e:
        return None, str(e)


lp_s = torch.from_numpy(np.stack([np.full((60, 80, 3), 0.1 * (k + 1), np.float32) for k in range(3)]))
o9, e9 = _try(lambda: EFParticles().run(plate, "sparks", "point A", track=trA, camera="fixed", look_plate=lp_s, **args))
o9b, e9b = _try(lambda: EFParticles().run(plate, "sparks", "point A", track=trA, camera="fixed", look_plate=lp_s, direct_look=True, **args))
check(o9 is not None and o9b is not None and tuple(o9[14].shape) == tuple(plate.shape) and tuple(o9b[14].shape) == tuple(plate.shape)
      and abs(float(o9[14][-1].mean()) - 0.3) < 1e-4 and abs(float(o9[14][1].mean()) - 0.2) < 1e-4,
      f"look plate 80x60, 3 frames: scaled to the plate, last frame held ({e9 or e9b or 'ok'})")
st3, e3 = _try(lambda: EFParticleSettings().make(1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, "preset", "preset", "preset", -1, "#f80", -1.0, -1, ""))
_, ec = _try(lambda: EFParticleSettings().make(1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, "preset", "preset", "preset", -1, "#12", -1.0, -1, ""))
_, ea = _try(lambda: EFParticles().run(plate, "smoke", "area", area="0.1, 0.2", **args))
oa, _ = _try(lambda: EFParticles().run(plate, "smoke", "point A", track=trA, area="0.1, 0.2", **args))
check(st3 is not None and np.allclose(st3[0]["colors"][0][1], [1.0, 0x88 / 255, 0.0]) and ec is not None and "#f80" in ec
      and ea is not None and "four numbers" in ea and oa is not None,
      f"settings: colour #f80 works, wrong colour and area give a clear message ({ec}; {ea})")
pc_ = np.zeros((n, H, W, 3), np.float32); pc_[:, :, :W // 2] = [0.25, 0.35, 0.6]; pc_[:, :, W // 2:] = [0.7, 0.2, 0.15]
trL = {"plate_size": [W, H], "frames": n, "point_track_px": [[W // 4, H - 40]] * n}
odb = EFParticles().run(torch.from_numpy(pc_), "debris", "point A", track=trL, camera="fixed", direct_look=True, **args)
lk_ = odb[14].numpy(); ch_ = np.abs(lk_ - pc_).max(-1) > 0.05
cm_ = lk_[ch_].mean(0)
odb0 = EFParticles().run(torch.from_numpy(pc_), "debris", "point A", track=trL, camera="fixed", direct_look=True,
                         settings={"plate_color": 0.0}, **args)
lk0_ = odb0[14].numpy(); cm0_ = lk0_[np.abs(lk0_ - pc_).max(-1) > 0.05].mean(0)
check(ch_.any() and cm_[2] > cm_[0] + 0.1 and cm_.max() < 0.6 and float(np.abs(cm_ - cm0_).max()) > 0.1,
      f"debris: chunks take the ground's colour where they break off ({np.round(cm_, 2).tolist()}; off: {np.round(cm0_, 2).tolist()})")
ng_, Hg_, Wg_ = 12, 120, 200
plg_ = np.full((ng_, Hg_, Wg_, 3), 0.1, np.float32)
dpg_ = np.full((ng_, Hg_, Wg_, 3), 0.2, np.float32); dpg_[:, :, 140:160] = 0.9
spr_ = np.zeros((6, 30, 20, 3), np.float32); spa_ = np.zeros((6, 30, 20), np.float32)
for f_ in range(6):
    spr_[f_] = [0.3, 0.24, 0.1]; spa_[f_, 5:25, 4:16] = 0.4 + 0.1 * f_
grp_ = [{"x": 0.25, "y": 0.5, "depth": 0.5, "scale": 0.1, "offset": 0}, {"x": 0.75, "y": 0.5, "depth": 0.5, "scale": 0.1, "offset": 3}]
trG = {"plate_size": [Wg_, Hg_], "frames": ng_, "point_track_px": [[100, 60]] * ng_}
ogr = EFParticles().run(torch.from_numpy(plg_), "groups", "groups", track=trG, depth=torch.from_numpy(dpg_), camera="fixed",
                        direct_look=True, settings={"groups": grp_}, sprite=torch.from_numpy(spr_), sprite_alpha=torch.from_numpy(spa_),
                        **dict(args, fps=25.0))
lg_ = ogr[14].numpy()
lit_ = np.abs(lg_[0] - plg_[0]).max(-1) > 0.15
ysg, xsg = np.nonzero(lit_[:, :100])
w_, h_ = (xsg.max() - xsg.min() + 1, ysg.max() - ysg.min() + 1) if len(xsg) else (0, 0)
right_ = float(np.abs(lg_[0][:, 140:160] - plg_[0][:, 140:160]).max())
a0_ = float(np.abs(lg_[0][60, 50] - plg_[0][60, 50]).max()); a5_ = float(np.abs(lg_[5][60, 50] - plg_[0][60, 50]).max())
check(len(xsg) and abs(np.mean(xsg) - 50) < 3 and abs(np.mean(ysg) - 60) < 3 and h_ > 1.3 * w_ and right_ < 0.02 and a5_ > a0_,
      f"groups: one element per group at its place, tall like the element ({w_}x{h_} px), hidden behind the near trunk ({right_:.3f}), playing ({a0_:.2f} -> {a5_:.2f})")
import math as _m
nc_, Hc_, Wc_ = 24, 270, 480
plc_ = np.full((nc_, Hc_, Wc_, 3), 0.05, np.float32)
mkc_ = np.zeros((nc_, Hc_, Wc_), np.float32)
for i_ in range(nc_):
    m_ = np.zeros((Hc_, Wc_), np.uint8)
    for a_ in np.linspace(-160, -20, 7):
        r_ = _m.radians(a_)
        cv2.line(m_, (int(240 + 35 * _m.cos(r_)), int(170 + 35 * _m.sin(r_))), (int(240 + 100 * _m.cos(r_)), int(170 + 100 * _m.sin(r_))), 1, 3)
    mkc_[i_] = m_
occ_ = EFParticles().run(torch.from_numpy(plc_), "lightning climb", "object mask", mask=torch.from_numpy(mkc_), camera="fixed",
                         **dict(args, fps=25.0))
gc_ = occ_[0].numpy()[..., 0]
nearc_ = np.stack([cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0 for m in mkc_])
lit_frames_ = int((gc_.reshape(nc_, -1).max(1) > 0.3).sum())
on_ = float(gc_[nearc_].sum() / max(gc_.sum(), 1e-6))
off_ = float(gc_[~nearc_].sum() / max(gc_.sum(), 1e-6))
check(lit_frames_ >= nc_ - 2 and on_ > 0.6 and off_ > 0.02,
      f"lightning climb: charge on the thin parts in {lit_frames_}/{nc_} frames ({on_:.0%} on the sticks), jumps off the tips ({off_:.0%} beside them)")
gs_ = EFParticles().run(torch.from_numpy(plc_), "lightning climb", "object mask", mask=torch.from_numpy(mkc_), camera="fixed",
                        settings={"climb_short": 0.0}, **dict(args, fps=25.0))[0].numpy()[..., 0]
check(gc_.sum() < 0.95 * gs_.sum() and on_ > 0.6,
      f"lightning climb: short stretches dimmer (guide {gc_.sum() / max(gs_.sum(), 1e-6):.0%} of climb_short 0)")
st_ = np.zeros((Hc_, Wc_), np.uint8)
cv2.line(st_, (40, 240), (440, 40), 1, 5)
hd_ = np.zeros((Hc_, Wc_), np.uint8)
cv2.rectangle(hd_, (210, 100), (240, 190), 1, -1)
mks_ = np.repeat((st_ * (1 - hd_)).astype(np.float32)[None], nc_, 0)
dps_ = np.where(hd_ > 0, 0.6, np.where(st_ > 0, 0.5, 0.3)).astype(np.float32)
dps_ = torch.from_numpy(np.repeat(np.repeat(dps_[None, ..., None], nc_, 0), 3, -1))
yy_, xx_ = np.mgrid[:Hc_, :Wc_]
ring_ = (np.hypot(xx_ - 208, yy_ - 156) < 70) & ~(cv2.dilate(st_, np.ones((9, 9), np.uint8)) > 0)


def cut_jumps(st, dp=dps_):
    return sum(float(EFParticles().run(torch.from_numpy(plc_), "lightning climb", "object mask", mask=torch.from_numpy(mks_), depth=dp,
                                       camera="fixed", settings=st, **dict(args, fps=25.0, seed=sd))[0].numpy()[..., 0][:, ring_].sum())
               for sd in (1, 2, 3))


FORKS_2210 = {"roughness": 0.22, "branches": 2, "climb_pitch": 0.08, "fork_depth": 1, "fine_rough": 0.0, "climb_zigzag": 0.0}
cj_off_ = cut_jumps({**FORKS_2210, "climb_cover": 9.0, "climb_gap": 0.0})
cj_z_, cj_g_ = cut_jumps({**FORKS_2210, "climb_gap": 0.0}), cut_jumps({**FORKS_2210, "climb_cover": 9.0}, None)
check(cj_z_ < 0.3 * cj_off_ and cj_g_ < 0.3 * cj_off_,
      f"lightning climb: no jumps from a covered tip over the hand (by depth {cj_z_:.0f}, by the staff going on past it {cj_g_:.0f}, "
      f"{cj_off_:.0f} without the checks)")
cp_off_, cp_on_ = cut_jumps({"climb_cover": 9.0, "climb_gap": 0.0}), cut_jumps({})
check(cp_on_ < 0.45 * cp_off_,
      f"lightning climb, the preset with the old look: the checks keep most light off the hand ({cp_on_:.0f} against {cp_off_:.0f})")
try:
    EFParticles().run(torch.from_numpy(plc_), "lightning climb", "point A", camera="fixed", **dict(args, fps=25.0))
    check(False, "lightning climb without an object mask must say so")
except ValueError as e_:
    check("object mask" in str(e_), f"lightning climb without an object mask says so ({e_})")
ng_, Hg_, Wg_ = 30, 270, 480
plg2_ = np.full((ng_, Hg_, Wg_, 3), 0.08, np.float32)
mkg_ = np.zeros((ng_, Hg_, Wg_), np.float32)
for i_ in range(ng_):
    mkg_[i_, 150:210, 80 + 8 * i_:110 + 8 * i_] = 1
og_ = EFParticles().run(torch.from_numpy(plg2_), "grinding sparks", "object bottom edge", mask=torch.from_numpy(mkg_), camera="fixed",
                        **dict(args, fps=25.0))
gg_ = og_[0].numpy()[20, ..., 0]
ysg2, xsg2 = np.nonzero(gg_ > 0.2)
ox_ = 80 + 8 * 20 + 15
back_ = float((xsg2 < ox_ - 15).mean()) if len(xsg2) else 0.0
up_ = int(210 - ysg2.min()) if len(ysg2) else 0
check(back_ > 0.6 and up_ > 25, f"grinding sparks: sprayed backwards ({back_:.0%} behind the object) and up over the ground ({up_} px)")
nk_, Hk_, Wk_ = 30, 270, 480
plk_ = np.full((nk_, Hk_, Wk_, 3), 0.08, np.float32)
gnd_ = np.where(np.arange(Hk_)[:, None] >= 100, 0.3 + 0.6 * (np.arange(Hk_)[:, None] - 100) / 170.0, 0.2) * np.ones((1, Wk_))
dpk_ = np.repeat(gnd_[None].astype(np.float32), nk_, 0)
mkk_ = np.zeros((nk_, Hk_, Wk_), np.float32)
air_ = np.zeros(nk_, bool)
air_[10:20] = True
for i_ in range(nk_):
    yc_ = 220
    lift_ = 60 if air_[i_] else 0
    x0_ = 60 + 8 * i_
    mkk_[i_, yc_ - 40 - lift_:yc_ - lift_, x0_:x0_ + 30] = 1
    dpk_[i_, yc_ - 40 - lift_:yc_ - lift_, x0_:x0_ + 30] = gnd_[yc_ - 1, 0]
okc_ = EFParticles().run(torch.from_numpy(plk_), "grinding sparks", "object bottom edge", mask=torch.from_numpy(mkk_),
                         depth=torch.from_numpy(dpk_[..., None].repeat(3, -1)), camera="fixed",
                         settings={"contact_only": 1.0}, **dict(args, fps=25.0))
gk_ = okc_[0].numpy()[..., 0]
def _at_edge(i_):
    e_ = 220 - (60 if air_[i_] else 0)
    x0_ = 60 + 8 * i_
    return gk_[i_, max(e_ - 8, 0):e_ + 12, max(x0_ - 25, 0):x0_ + 40].max() > 0.2
new_air_ = sum(_at_edge(i_) for i_ in range(14, 20))
on_ground_ = sum(_at_edge(i_) for i_ in range(3, 9))
check(on_ground_ >= 5 and new_air_ == 0, f"contact only: sparks while touching ({on_ground_}/6 frames), none in the air ({new_air_}/6)")
pd_ = torch.from_numpy(np.full((n, H, W, 3), 0.5, np.float32))
def solid_(settings):
    o_ = EFParticles().run(pd_, "debris", "point A", track=trA, camera="fixed", settings=settings, **dict(args, start_seconds=0.2))
    a_ = o_[7].numpy()
    return float((a_ > 0.9).sum() / max((a_ > 0.05).sum(), 1)), o_[0].numpy(), int((a_ > 0.05).sum())
sc_, gc_, ac_ = solid_({"shutter": 0.0})
sf_, _, _ = solid_({"sprite": "flake", "trail": 3, "guide_style": "lines"})
sb_, _, ab_ = solid_(None)
check(sc_ > 0.25 and sc_ > 1.6 * sf_ and float(gc_.max()) > 0.3 and ab_ > 1.15 * ac_ and sb_ < sc_,
      f"debris chunks: solid fragments ({sc_:.0%} of the covered area opaque, flakes {sf_:.0%}), shown in the guide; "
      f"motion blur spreads them ({ab_ / max(ac_, 1):.2f}x the area)")
hm_ = np.zeros((n, H, W), np.float32)
for i_ in range(n):
    cy_ = int(H * (0.75 - 0.45 * i_ / max(n - 1, 1)))
    cv2.circle(hm_[i_], (int(W * 0.3), cy_), int(H * 0.08), 1.0, -1)
    cv2.circle(hm_[i_], (int(W * 0.7), cy_), int(H * 0.08), 1.0, -1)
y0_ = H * 0.75
tA_ = {"plate_size": [W, H], "frames": n, "point_track_px": [[W * 0.3 + H * 0.08, y0_]] * n}
tB_ = {"plate_size": [W, H], "frames": n, "point_track_px": [[W * 0.7 - H * 0.08, y0_]] * n}
pt_ = sys.modules[pack.__name__ + ".element_forge.simulation.particles"]
ea_, eb_ = pt_.ends_on_objects(hm_, n, W, H, a0=tA_["point_track_px"][0])
def boly_(settings):
    o_ = EFParticles().run(torch.from_numpy(np.full((n, H, W, 3), 0.1, np.float32)), "lightning", "line A-B", track=tA_, track_b=tB_,
                           mask=torch.from_numpy(hm_), camera="fixed", settings=settings, **dict(args, start_seconds=0.0))
    g_ = o_[0].numpy()[-1].mean(-1)
    g_ = cv2.resize(g_, (W, H))
    ys_, xs_ = np.nonzero(g_ > 0.3)
    return float(ys_.mean()) if len(ys_) else -1.0
yon_, yoff_ = boly_({"ab_on_objects": 1}), boly_(None)
def boly_a_(settings):
    o_ = EFParticles().run(torch.from_numpy(np.full((n, H, W, 3), 0.1, np.float32)), "lightning", "point A", track=tA_, track_b=tB_,
                           mask=torch.from_numpy(hm_), camera="fixed", settings=settings, **dict(args, start_seconds=0.0))
    g_ = cv2.resize(o_[0].numpy()[-1].mean(-1), (W, H))
    ys_, xs_ = np.nonzero(g_ > 0.3)
    return float(ys_.mean()) if len(ys_) else -1.0
ypa_, ypa0_ = boly_a_({"ab_on_objects": 1}), boly_a_(None)
ylast_ = H * 0.30
check(abs(ea_[-1][1] - ylast_) < 0.05 * H and ea_[-1][0] < eb_[-1][0] and abs(yon_ - ylast_) < 0.12 * H and abs(yoff_ - y0_) < 0.12 * H,
      f"line A-B on two objects: ends follow the gap (last frame y {ea_[-1][1]:.0f}, discs at {ylast_:.0f}), bolt at y {yon_:.0f} "
      f"(without: {yoff_:.0f}, clicked at {y0_:.0f})")
check(abs(ypa_ - ylast_) < 0.12 * H and abs(ypa0_ - y0_) < 0.12 * H,
      f"point A with target B on two objects: bolt at y {ypa_:.0f} (without: {ypa0_:.0f})")
dn_ = np.full((n, H, W), 0.2, np.float32)
dn_[:, 60:200, 120:200] = 0.95
rf_ = EFParticles().run(plate, "rain", "whole frame", camera="fixed",
                        depth=torch.from_numpy(np.repeat(dn_[..., None], 3, -1)), **args)
gf_ = rf_[0].numpy().max(-1)
gin_, gout_ = float(gf_[:, 80:180, 130:190].mean()), float(gf_[:, 80:180, 20:80].mean())
hin_ = float(rf_[9].numpy()[:, 80:180, 130:190].mean())
check(gin_ > 0.5 * gout_ and hin_ < 0.5,
      f"rain over the whole frame: drops behind a near figure stay in the guide ({gin_:.4f} vs {gout_:.4f} beside it), "
      f"the holdout hides them there ({hin_:.2f})")
def _cx(o):
    a = o[7].numpy().reshape(n, H, W)[n // 2:]
    return float((a.sum(0) * np.arange(W)[None, :]).sum() / max(a.sum(), 1e-6))


aura_ = lambda d, **kw: EFParticles().run(plate, "aura", "object contour", mask=m, depth=depth, premask=False,
                                          **{**args, "direction": d}, **kw)
ar_, al_ = _cx(aura_(90.0)), _cx(aura_(270.0))
old_ = abs(_cx(aura_(90.0, settings={"direction_mode": "outward"})) - _cx(aura_(270.0, settings={"direction_mode": "outward"})))
check(ar_ > al_ + 4 and old_ < 1, f"aura with the arrow: to the right x {ar_:.1f}, to the left x {al_:.1f} "
      f"(outward as before: {old_:.2f} px apart, the arrow did nothing)")
pt_ = sys.modules[pack.__name__ + ".element_forge.simulation.particles"]
calls_, keep_ = [0], pt_.interrupted


class _Stopped(Exception):
    pass


def _stop_after_5():
    calls_[0] += 1
    if calls_[0] > 5:
        raise _Stopped()


pt_.interrupted = _stop_after_5
try:
    EFParticles().run(plate, "sparks", "point A", track=trA, depth=depth, window=win, camera="fixed", **args)
    stopped_ = False
except _Stopped:
    stopped_ = True
finally:
    pt_.interrupted = keep_
pn_ = sys.modules[pack.__name__ + ".element_forge.simulation.particles_node"]
check(stopped_ and calls_[0] == 6 and keep_ is pn_._check and pn_._stop_check is mm.throw_exception_if_processing_interrupted,
      "Stop: the particle node asks ComfyUI's stop check while it works and ends at the next check")
seen_ = []
keep_stop_ = pn_._stop_check
pn_._stop_check = lambda: seen_.append("queue")
pn_.LIVE.check = lambda: seen_.append("live")
try:
    pt_.interrupted()
finally:
    del pn_.LIVE.check
pt_.interrupted()
pn_._stop_check = keep_stop_
check(seen_ == ["live", "queue"], f"live preview: its own stop check in its thread, the queue's elsewhere ({seen_})")
sd_, = EFParticleSettings().make(2.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0, "preset", "preset", "preset", -1, "", -1.0, -1, '{"radius": 40}',
                                 emitter='{"gravity": 123.0, "speed": 500.0, "colors": [[0, [1, 0, 0]], [1, [0, 0, 1]]], "sprite": "custom"}')
over_, final_ = pn_.split_final(sd_)
Pd_ = pn_.params_for("sparks", sd_, 2.0, 1.0, 1.0, 0.0, 0.0, -1.0, -1.0, -1.0, 0.0)
Pp_ = pt_.PRESETS["sparks"]
check("final" in sd_ and "final" not in over_ and over_["gravity*"] == 2.0 and Pd_["gravity"] == 123.0 and Pd_["speed"] == 500.0
      and Pd_["radius"] == 40 and Pd_["colors"][0][1] == [1, 0, 0] and Pd_["drag"] == Pp_["drag"],
      "emitter panel: own values win over the preset, the fine settings (gravity x2) and the node's speed x2; the rest stays")
check(pn_.params_for("sparks", over_, 2.0, 1.0, 1.0, 0.0)["speed"] == 2 * Pp_["speed"], "emitter panel: without its values the node's speed counts again")
check(pack.NODE_CLASS_MAPPINGS["EFParticles"]().check_lazy_status("sparks", settings=sd_, sprite=None, sprite_alpha=None) == ["sprite", "sprite_alpha"],
      "emitter panel: a custom sprite set there asks for the sprite input")
try:
    pn_.params_for("sparks", {"final": {"no_such": 1}}, 1.0, 1.0, 1.0, 0.0)
    bad_ = None
except ValueError as err_:
    bad_ = str(err_)
check(bad_ and "no_such" in bad_, "emitter panel: an unknown name is named in the error")
dg = EFParticles().run(plate, "sparks", "point A", track=trA, mask=m, depth=depth, camera="fixed", settings={"guide_style": "depth"}, **args)
dv = EFParticles().run(plate, "sparks", "point A", track=trA, mask=m, depth=depth, camera="fixed", settings={"guide_style": "volume"}, **args)
g_d = dg[0].numpy()
check(g_d.shape == (n, H, W, 3) and np.allclose(g_d[..., 0], g_d[..., 2]) and float(g_d[:, 100, 150, 0].min()) > 0.05
      and float(g_d[:, 20, 20].max()) == 0, "depth guide: the object's depth inside its mask, black outside it")
check(np.array_equal(dg[4].numpy(), dv[4].numpy()) and np.array_equal(dg[9].numpy(), dv[9].numpy()), "depth guide: seed and holdout as with any other guide")
ds = EFParticles().run(plate, "sparks", "point A", track=trA, mask=m, depth=depth, camera="fixed",
                       settings={"guide_style": "depth", "depth_guide": "scene"}, **args)[0].numpy()
check(float(ds[:, 20, 20].min()) > 0.05, "depth guide of the scene: depth everywhere")
de = EFParticles().run(plate, "sparks", "point A", track=trA, mask=m, depth=depth, camera="fixed",
                       settings={"guide_style": "depth", "depth_edge": 2}, **args)[0].numpy()
inside = (dv[0].numpy()[..., 0] == 0)[:, 90:150, 130:210]
check(float(de[:, 90:150, 130:210, 0][inside].max()) == 0 and float(g_d[:, 90:150, 130:210, 0][inside].min()) > 0.05
      and float(de[:, 81, 200, 0].min()) > 0.05, "depth guide, inner edge: of the object only its edge")
db = EFParticles().run(plate, "lightning", "point A", track=trA, track_b=trB, mask=m, depth=depth, settings={"guide_style": "depth"}, **args)[0]
check(float(db.max()) > 0.5, "depth guide with a path: the bolt drawn over it as lines")
try:
    EFParticles().run(plate, "sparks", "point A", track=trA, depth=depth, settings={"guide_style": "depth"}, **args)
    bad_ = None
except ValueError as err_:
    bad_ = str(err_)
check(bad_ and "object" in bad_, "depth guide of the object without a mask: says to click the object")
print(f"{ok} checks passed")

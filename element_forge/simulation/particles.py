import collections
import json
import math

import cv2
import numpy as np

REF = 1080.0

interrupted = lambda: None
frame_done = lambda i, rec, st, used: None

SPIN = 114.59155902616465
BASE = dict(
    path="particles",
    blend="add", look="",
    halo=0.0,
    ambient=0.0,
    relief=0.0,
    shell=0.0,
    plate_color=0.0,
    dof=0.0, focus=-1.0,
    bloom=1.0,
    rate=0.0, burst=0, burst_at=0.0, start=0.0, end=-1.0, preroll=0.0,
    burst_every=0.0,
    rate_curve=[],
    life=1.0, life_var=0.3,
    speed=100.0, speed_var=0.3, direction=0.0, spread=30.0, direction_mode="angle",
    lift=0.0,
    contact_only=0.0,
    contact_gap=0.015, contact_tol=0.04,
    ab_on_objects=0.0,
    motion_carry=0.0,
    carry_free=120.0,
    inherit=0.5, radius=6.0, band="volume",
    size=4.0, size_var=0.3, size_start=1.0, size_end=1.0,
    fade_in=0.1, fade_out=0.3, opacity=1.0, flicker=0.0, flicker_hz=2.0,
    flicker_size=0.0,
    fine_share=0.0,
    fine_size=0.4,
    fine_speed=1.8,
    fine_life=0.6,
    gravity=0.0, wind=[0.0, 0.0], drag=0.0,
    turbulence=0.0, turb_scale=150.0, turb_speed=0.3,
    vortex=0.0, attract=0.0, kill_radius=12.0,
    collide="none", restitution=0.4, friction=0.7, land_fade=2.0, land_tol=0.06,
    children=None,
    depth_offset=0.0, depth_spread=0.0, depth_spread_near=False, depth_softness=0.02,
    depth_far=0.0,
    fly=0.0,
    sprite="soft", shutter=0.0, trail=0,
    colors=[[0.0, [1.0, 1.0, 1.0]], [1.0, [1.0, 1.0, 1.0]]], color_var=0.1,
    glow=1.0, guide_style="lines",
    depth_guide="object", depth_edge=0.0,
    max_particles=20000, substeps=2,
    roughness=0.22, branches=3, reroll_frames=2, grow_seconds=0.0, width=2.0,
    strike_leader=0.05,
    strike_strokes=3,
    strike_gap=0.06,
    strike_decay=0.012,
    strike_hold=0.0,
    strike_hold_level=0.3,
    strike_new_ground=0.0,
    strike_streamer=0.0,
    strike_lean=0.25,
    strike_spread=0.0,
    climb_seconds=0.4,
    climb_from="bottom",
    climb_pitch=0.0,
    climb_rough=1.0,
    climb_head=0.0,
    climb_short=0.0,
    climb_cover=0.03,
    climb_gap=160.0,
    fine_rough=0.0,
    fork_depth=1,
    climb_zigzag=0.0,
    crack_step=6.0, crack_turn=0.35, crack_branch=0.12, crack_length=900.0, crack_speed=300.0,
    crack_seeds=1,
    crack_taper=0.0,
    ring_speed=900.0, ring_squash=0.35,
    groups=None,
    group_size=1.0,
    group_perspective=0.0,
    sprite_play="life",
    sprite_aspect=0.0,
    sprite_occlude=0.0,
    sprite_gain=1.0,
    flock=0.0,
    flock_radius=40.0,
    flock_cohesion=4.0,
    flock_align=2.0,
    flock_separation=6.0,
    blob=0.0,
    blob_choke=0.35,
    blob_soft=0.12,
    blob_fill=1.0,
    spread_falloff=0.0,
    speed_end=1.0,
    max_speed=0.0,
    spin=SPIN,
    turb_fade=0.0,
    turb_drag=0.0,
    blob_life=0.0,
    scale=1.0,
    scene_height=0.0,
    gravity_end=1.0,
    speed_by_size=0.0,
    sway=0.0,
    sway_hz=0.7,
    flicker_duty=0.0,
    roll=0.0,
    crack_angle=0.8,
    crack_angle_var=0.3,
    crack_pairs=0.0,
)

FIRE = [[0.0, [1.0, 0.95, 0.8]], [0.25, [1.0, 0.75, 0.3]], [0.55, [1.0, 0.4, 0.08]], [0.8, [0.6, 0.12, 0.03]],
        [1.0, [0.12, 0.1, 0.09]]]
SPARK = [[0.0, [1.0, 1.0, 0.9]], [0.3, [1.0, 0.85, 0.45]], [0.7, [1.0, 0.5, 0.12]], [1.0, [0.7, 0.15, 0.03]]]
BLAST = [[0.0, [1.0, 0.97, 0.85]], [0.12, [1.0, 0.78, 0.35]], [0.35, [1.0, 0.42, 0.08]], [0.6, [0.45, 0.14, 0.05]],
         [1.0, [0.1, 0.09, 0.09]]]
BLAST_SOOT = [[0.0, [1.0, 0.97, 0.85]], [0.08, [1.0, 0.78, 0.35]], [0.22, [1.0, 0.42, 0.08]], [0.4, [0.3, 0.11, 0.05]],
              [0.7, [0.12, 0.1, 0.1]], [1.0, [0.08, 0.08, 0.08]]]

STANDARD_INPAINT = "0.909375, 0.725, 0.421875, 0.0"
STRONG_INPAINT = "0.9875, 0.975, 0.909375, 0.725, 0.421875, 0.0"
PRESETS = {
    "sparks": dict(rate=120.0, life=0.6, life_var=0.5, speed=1400.0, speed_var=0.4, spread=70.0, inherit=0.6, size=1.6,
                   size_end=0.4, fade_in=0.0, fade_out=0.4, gravity=1400.0, drag=3.5, turbulence=30.0, collide="bounce",
                   restitution=0.25, sprite="spark", shutter=0.75, fine_share=0.4, fine_size=0.5, fine_life=0.5,
                   children=dict(at_age=0.4, chance=0.3, count=5, speed=600.0, spread=180.0, direction=0.0, life=0.08, size=0.6),
                   colors=SPARK, guide_style="lines"),
    "grinding sparks": dict(rate=420.0, life=0.45, life_var=0.55, speed=4000.0, speed_var=0.25, direction_mode="against motion",
                            lift=25.0, spread=25.0, inherit=0.3, size=2.0, size_end=0.5, fade_in=0.0, fade_out=0.35, gravity=900.0,
                            drag=6.0, turbulence=0.0, collide="bounce", restitution=0.25, sprite="spark", shutter=0.75, glow=1.6,
                            fine_share=0.4, fine_size=0.5, fine_life=0.5,
                            colors=SPARK, guide_style="lines"),
    "explosion": dict(rate=1400.0, rate_curve=[[0.0, 1.0], [0.04, 1.0], [0.12, 0.2], [0.3, 0.0]], burst=120, life=2.2,
                      life_var=0.4, speed=1800.0, speed_var=0.6, spread=180.0, spread_falloff=0.0, inherit=0.2, radius=18.0,
                      size=18.0, size_var=0.5, size_start=0.8, size_end=3.2, fade_in=0.0, fade_out=0.6, speed_end=1.0,
                      gravity=-1500.0, gravity_end=0.3, roll=1500.0, drag=6.0, turbulence=80.0, turb_scale=70.0, turb_speed=1.0,
                      sprite="puff", colors=BLAST_SOOT, flicker=0.2, flicker_hz=2.0, flicker_size=1.0, fine_share=0.3,
                      fine_size=0.25, fine_speed=2.2, fine_life=0.5,
                      blob=8.0, blob_life=0.45, blob_choke=0.3, blob_soft=0.15, blob_fill=0.0, guide_style="temperature"),
    "embers": dict(rate=25.0, life=2.5, life_var=0.4, speed=90.0, speed_var=0.5, spread=40.0, inherit=0.3, size=2.2,
                   size_end=0.6, fade_in=0.1, fade_out=0.5, gravity=-150.0, gravity_end=-1.33, drag=1.5, turbulence=70.0,
                   turb_scale=120.0, sprite="soft", trail=6, colors=SPARK[1:], flicker=0.3, flicker_size=1.0, guide_style="lines"),
    "fire": dict(rate=110.0, life=0.8, life_var=0.3, speed=170.0, spread=16.0, inherit=0.5, radius=10.0, size=16.0,
                 size_var=0.3, size_end=0.2, fade_in=0.08, fade_out=0.55, gravity=-650.0, drag=0.35, turbulence=120.0,
                 turb_scale=55.0, turb_speed=1.2, sprite="puff", colors=FIRE, guide_style="temperature", flicker=0.25,
                 flicker_hz=4.0, flicker_size=1.0, fine_share=0.45, fine_size=0.4, fine_speed=1.8, fine_life=0.6,
                 blob=6.0, blob_life=0.5, blob_choke=0.3, blob_soft=0.15, blob_fill=0.0),
    "smoke": dict(look="over", ambient=1.0, rate=40.0, life=3.0, speed=130.0, speed_var=0.4, spread=12.0, spread_falloff=0.5,
                  turb_fade=0.2, inherit=0.3, radius=12.0, size=20.0,
                  size_var=0.4, size_start=0.6, size_end=3.5, fade_in=0.15, fade_out=0.6, opacity=0.22, gravity=-130.0,
                  drag=0.7, turbulence=90.0, turb_scale=90.0, sprite="wisp", colors=[[0.0, [0.55, 0.55, 0.55]], [1.0, [0.4, 0.4, 0.42]]],
                  guide_style="volume", preroll=2.0),
    "dust burst": dict(look="over", ambient=1.0, burst=150, life=1.6, life_var=0.4, speed=260.0, speed_var=0.5, spread=85.0, inherit=0.4,
                       radius=14.0, size=13.0, size_var=0.5, size_start=0.5, size_end=2.5, fade_in=0.05, fade_out=0.7,
                       opacity=0.6, gravity=60.0, drag=3.0, speed_end=0.3, turbulence=40.0, turb_scale=120.0, sprite="wisp",
                       colors=[[0.0, [0.62, 0.58, 0.52]], [1.0, [0.55, 0.52, 0.48]]], guide_style="volume"),
    "snow": dict(blend="contrast (rain)", rate=140.0, life=40.0, life_var=0.2, preroll=-1.0, speed=110.0, speed_var=0.3, direction=180.0, spread=15.0,
                 inherit=0.0, band="top", size=3.5, size_var=0.5, fade_in=0.05, fade_out=0.05, turbulence=60.0,
                 turb_scale=80.0, turb_speed=0.3, sway=25.0, sway_hz=0.7, collide="stick", land_fade=2.5, sprite="flake",
                 colors=[[0.0, [0.95, 0.96, 1.0]], [1.0, [0.95, 0.96, 1.0]]], guide_style="volume"),
    "rain": dict(blend="contrast (rain)", rate=900.0, life=3.0, life_var=0.1, preroll=-1.0, speed=1500.0, speed_var=0.35,
                 speed_by_size=0.5, direction=172.0,
                 spread=3.0, inherit=0.0, band="top", size=1.0, size_var=0.3, fade_in=0.02, fade_out=0.02, opacity=0.5,
                 collide="die", children=dict(count=3, speed=250.0, spread=70.0, direction=0.0, life=0.12, size=1.2,
                                              gravity=2200.0, drag=0.0),
                 sprite="streak", shutter=1.0, colors=[[0.0, [0.75, 0.8, 0.85]], [1.0, [0.75, 0.8, 0.85]]],
                 guide_style="lines"),
    "fireflies": dict(dof=15.0, rate=18.0, life=6.0, preroll=4.0, speed=25.0, direction_mode="random", inherit=0.0, size=3.0,
                      fade_in=0.2, fade_out=0.2, flicker=1.0, flicker_hz=0.25, flicker_duty=0.15, drag=0.5, turbulence=35.0,
                      turb_scale=150.0, turb_speed=0.4, sprite="soft", glow=2.0,
                      colors=[[0.0, [0.9, 1.0, 0.35]], [1.0, [0.9, 1.0, 0.35]]], guide_style="volume"),
    "magic dust": dict(rate=160.0, life=1.2, life_var=0.4, speed=60.0, direction_mode="outward", spread=25.0,
                       inherit=0.8, size=2.2, fade_in=0.2, fade_out=0.5, gravity=-40.0, drag=1.0, turbulence=25.0,
                       turb_scale=200.0, turb_fade=0.3, flicker=0.5, flicker_hz=8.0, flicker_size=1.0,
                       sprite="soft", trail=4, glow=1.5,
                       colors=[[0.0, [0.75, 1.0, 1.0]], [1.0, [0.6, 0.35, 1.0]]], guide_style="lines"),
    "aura": dict(rate=160.0, life=1.2, life_var=0.4, speed=60.0, direction_mode="outward", spread=25.0,
                 inherit=0.8, size=2.2, fade_in=0.2, fade_out=0.5, gravity=-40.0, drag=1.0, turbulence=25.0,
                 turb_scale=200.0, turb_fade=0.3, sprite="soft", trail=4, glow=1.5, depth_offset=-0.15, halo=1.0, shell=1.0,
                 colors=[[0.0, [0.75, 1.0, 1.0]], [1.0, [0.6, 0.35, 1.0]]], guide_style="lines"),
    "liquid": dict(look="over", rate=220.0, life=2.0, speed=120.0, speed_var=0.5, direction=180.0, spread=14.0, inherit=0.7,
                   radius=25.0, size=4.0, size_var=0.2, size_end=0.8, fade_in=0.02, fade_out=0.1, gravity=1600.0, drag=0.8,
                   turbulence=500.0, turb_scale=40.0, flock=1.0, flock_radius=25.0, flock_cohesion=40.0, flock_separation=15.0,
                   collide="die", children=dict(count=2, speed=220.0, spread=75.0, direction=0.0, life=0.35, size=2.5,
                                                gravity=1600.0, drag=0.0),
                   sprite="soft", trail=3, colors=[[0.0, [0.75, 0.82, 0.9]], [1.0, [0.75, 0.82, 0.9]]],
                   opacity=0.8, guide_style="lines"),
    "lightning": dict(path="bolt", roughness=0.22, branches=3, reroll_frames=2, width=2.5, glow=2.0,
                      colors=[[0.0, [0.85, 0.92, 1.0]], [1.0, [0.85, 0.92, 1.0]]], guide_style="lines"),
    "lightning strike": dict(path="strike", burst_at=0.3, roughness=0.08, fine_rough=0.3, branches=8, fork_depth=2,
                             width=2.5, glow=2.2, strike_strokes=4, strike_gap=0.06, strike_decay=0.012, strike_hold=0.1,
                             strike_hold_level=0.3, strike_new_ground=0.6, strike_streamer=30.0,
                             colors=[[0.0, [0.88, 0.92, 1.0]], [1.0, [0.88, 0.92, 1.0]]], guide_style="lines"),
    "lightning climb": dict(path="climb", roughness=0.3, branches=4, reroll_frames=2, width=1.5, glow=1.2, climb_seconds=0.4,
                            climb_pitch=0.03, climb_rough=3.0, climb_head=0.8, climb_short=200.0,
                            fork_depth=2, fine_rough=0.28, climb_zigzag=5.0,
                            colors=[[0.0, [0.85, 0.92, 1.0]], [1.0, [0.85, 0.92, 1.0]]], guide_style="lines"),
    "cracks": dict(look="over", path="crack", crack_speed=300.0, crack_branch=0.06, crack_turn=0.1, crack_step=6.0,
                   crack_angle=0.47, crack_angle_var=0.1,
                   crack_length=500.0, width=2.2, opacity=0.9, relief=1.0,
                   colors=[[0.0, [0.08, 0.07, 0.06]], [1.0, [0.08, 0.07, 0.06]]], guide_style="lines",
                   inpaint_sigmas=STRONG_INPAINT),
    "frost": dict(look="over", path="crack", crack_speed=200.0, crack_branch=0.15, crack_turn=0.08, crack_step=6.0,
                  crack_angle=1.05, crack_angle_var=0.05, crack_pairs=1.0,
                  crack_length=420.0, crack_seeds=5, width=1.4, opacity=0.85,
                  colors=[[0.0, [0.85, 0.93, 1.0]], [1.0, [0.7, 0.85, 1.0]]], guide_style="lines",
                  inpaint_sigmas=STRONG_INPAINT),
    "energy A-B": dict(rate=200.0, life=1.0, speed=120.0, direction_mode="random", inherit=0.6, attract=2600.0,
                       drag=1.5, turbulence=40.0, size=2.0, trail=5, glow=1.8, kill_radius=15.0,
                       colors=[[0.0, [0.8, 0.95, 1.0]], [1.0, [0.45, 0.7, 1.0]]], guide_style="lines"),
    "debris": dict(look="over", burst=60, life=1.8, speed=520.0, speed_var=0.5, spread=60.0, inherit=0.3, radius=10.0, size=8.0,
                   size_var=0.75, fade_in=0.0, fade_out=0.15, gravity=1500.0, drag=0.2, collide="bounce", restitution=0.3,
                   sprite="chunk", shutter=0.5, trail=0, plate_color=1.0, colors=[[0.0, [1.0, 1.0, 1.0]], [1.0, [0.9, 0.9, 0.9]]],
                   guide_style="volume", depth_spread=0.03, depth_spread_near=True),
    "groups": dict(rate=0.0, burst=0, life=1e6, life_var=0.0, speed=0.0, speed_var=0.0, spread=0.0, inherit=0.0, radius=0.0,
                   size_var=0.0, fade_in=0.0, fade_out=0.0, gravity=0.0, drag=0.0, turbulence=0.0, color_var=0.0,
                   sprite="custom", sprite_play="loop", sprite_aspect=1.0, sprite_occlude=1.0, sprite_gain=1.5, glow=1.0, preroll=0.0,
                   bloom=0.0, dof=12.0, focus=0.6,
                   max_particles=64, guide_style="volume"),
}
PRESETS["explosion side"] = dict(PRESETS["explosion"], spread=45.0, spread_falloff=0.3, direction=90.0, gravity=-900.0, roll=0.0)
EMITTERS = ["point A", "line A-B", "drawing", "object mask", "object contour", "object bottom edge", "area", "whole frame", "groups"]
OBJECT_EMITTERS = ("object mask", "object contour", "object bottom edge")
LINE_ATTACH = ["track", "image", "object"]


def params(preset, overrides=None):
    p = json.loads(json.dumps(BASE))
    p.update(json.loads(json.dumps(PRESETS[preset])))
    for k, v in (overrides or {}).items():
        key = k[:-1] if k.endswith("*") else k
        if key not in p:
            raise ValueError(f"unknown particle setting '{key}' (known: {', '.join(sorted(p))})")
        p[key] = p[key] * v if k.endswith("*") else v
    return p


def hash_u(*keys, seed=0):
    h = np.full(np.broadcast(*keys).shape, (seed * 0x9E3779B1 + 0x7F4A7C15) & 0xFFFFFFFF, np.uint64)
    for k in keys:
        h = (h ^ (np.asarray(k).astype(np.int64).astype(np.uint64) & 0xFFFFFFFF)) & 0xFFFFFFFF
        h = (h ^ (h >> 16)) * 0x7FEB352D & 0xFFFFFFFF
        h = (h ^ (h >> 15)) * 0x846CA68B & 0xFFFFFFFF
        h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float32) / float(0x1000000)


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def turb_calm(P, age, life, drag):
    if P["turb_fade"] <= 0 and P["turb_drag"] <= 0:
        return None
    k = np.ones(len(age))
    if P["turb_fade"] > 0:
        k *= smoothstep(age / (life * P["turb_fade"]))
    if P["turb_drag"] > 0:
        k *= np.exp(-P["turb_drag"] * drag * age)
    return k


def fade(age, fade_in, fade_out):
    a = np.ones_like(age)
    if fade_in > 0:
        a = np.minimum(a, smoothstep(age / fade_in))
    if fade_out > 0:
        a = np.minimum(a, smoothstep((1.0 - age) / fade_out))
    return a


def gradient(stops, t):
    pos = np.array([s[0] for s in stops], np.float32)
    col = np.array([s[1] for s in stops], np.float32)
    return np.stack([np.interp(t, pos, col[:, c]) for c in range(3)], -1)


class CurlNoise:

    def __init__(self, rng, strength, scale, speed, k=12):
        ang = rng.uniform(0, 2 * np.pi, k)
        mag = 2 * np.pi / max(scale, 1e-3) * rng.uniform(0.6, 1.5, k)
        self.kx, self.ky = mag * np.cos(ang), mag * np.sin(ang)
        self.w = 2 * np.pi * speed * rng.uniform(0.5, 1.5, k)
        self.ph = rng.uniform(0, 2 * np.pi, k)
        a = 1.0 / mag
        rms = math.sqrt(float(np.sum((a * mag) ** 2)) / 2.0)
        self.a = a * strength / max(rms, 1e-9)
        self.on = strength > 0

    def __call__(self, x, y, t):
        if not self.on or len(x) == 0:
            return np.zeros_like(x), np.zeros_like(y)
        c = np.multiply.outer(self.kx, x)
        c += np.multiply.outer(self.ky, y)
        c += (t * self.w)[:, None]
        c += self.ph[:, None]
        np.cos(c, out=c)
        c *= self.a[:, None]
        c = np.ascontiguousarray(c.T)
        return c @ self.ky, -(c @ self.kx)


class Camera:

    def __init__(self, n, mats=None):
        self.m = [np.eye(3) for _ in range(n)] if mats is None else mats
        self.inv = [np.linalg.inv(m) for m in self.m]

    @staticmethod
    def from_plate(plate, avoid=None):
        n = len(plate)
        h, w = plate.shape[1:3]
        k = min(1.0, 540.0 / min(h, w))
        gray = [cv2.cvtColor(cv2.resize((np.clip(plate[i][..., :3], 0, 1) * 255).astype(np.uint8), None, fx=k, fy=k,
                                        interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY) for i in range(n)]
        mats = [np.eye(3)]
        lk = dict(winSize=(31, 31), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 40, 0.01))
        for i in range(1, n):
            mask = np.full(gray[0].shape, 255, np.uint8)
            if avoid is not None:
                a = avoid[min(i - 1, len(avoid) - 1)]
                a = cv2.resize((a > 0.5).astype(np.uint8), (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)
                mask[cv2.dilate(a, np.ones((15, 15), np.uint8)) > 0] = 0
            step = np.eye(3)
            c0 = cv2.goodFeaturesToTrack(gray[i - 1], 600, 0.01, 8, mask=mask)
            if c0 is not None and len(c0) >= 8:
                c1, st, _ = cv2.calcOpticalFlowPyrLK(gray[i - 1], gray[i], c0, None, **lk)
                good = st.ravel() == 1
                if good.sum() >= 8:
                    M, _ = cv2.estimateAffinePartial2D(c0[good] / k, c1[good] / k, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    if M is not None:
                        step[:2] = M
            mats.append(step @ mats[-1])
        return Camera(n, mats)

    def _frame(self, t, fps):
        return int(np.clip(round(t * fps), 0, len(self.m) - 1))

    def to_screen(self, x, y, i):
        m = self.m[i]
        return m[0, 0] * x + m[0, 1] * y + m[0, 2], m[1, 0] * x + m[1, 1] * y + m[1, 2]

    def to_world(self, x, y, i):
        m = self.inv[i]
        return m[0, 0] * x + m[0, 1] * y + m[0, 2], m[1, 0] * x + m[1, 1] * y + m[1, 2]


class PlateFlow:

    def __init__(self, plate, max_side=640, keep=False):
        self.keep = keep
        self.n, self.H, self.W = plate.shape[:3]
        self.k = min(1.0, max_side / max(self.H, self.W))
        self.g = [cv2.cvtColor(cv2.resize((np.clip(f[..., :3], 0, 1) * 255).astype(np.uint8), None, fx=self.k, fy=self.k,
                                          interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY) for f in plate]
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.cache = {}

    def field(self, i):
        i = int(np.clip(i, 0, self.n - 1))
        if i not in self.cache:
            a, b = (i, i + 1) if i + 1 < self.n else (i - 1, i)
            if not self.keep:
                self.cache.clear()
            self.cache[i] = np.zeros(self.g[0].shape + (2,), np.float32) if a < 0 else                 self.dis.calc(self.g[a], self.g[b], None) / self.k
        return self.cache[i]

    def at(self, i, x, y):
        f = self.field(i)
        xi = np.clip((np.nan_to_num(x) * self.k).astype(np.int64), 0, f.shape[1] - 1)
        yi = np.clip((np.nan_to_num(y) * self.k).astype(np.int64), 0, f.shape[0] - 1)
        return f[yi, xi, 0], f[yi, xi, 1]


def carry_weight(d, ps):
    return smoothstep((d / max(ps, 1e-6) - 0.3) / 1.2)


class Depth:

    def __init__(self, maps, W, H):
        self.d = None if maps is None else np.ascontiguousarray(maps, np.float32)
        if self.d is not None:
            self.sx, self.sy = self.d.shape[2] / W, self.d.shape[1] / H

    def __bool__(self):
        return self.d is not None

    def at(self, i, x, y):
        if self.d is None:
            return np.ones_like(x)
        i = min(max(int(i), 0), len(self.d) - 1)
        xi = np.clip((x * self.sx).astype(np.int64), 0, self.d.shape[2] - 1)
        yi = np.clip((y * self.sy).astype(np.int64), 0, self.d.shape[1] - 1)
        return self.d[i][yi, xi]


def _mask_box(mb, step=1, pad=8, align=64):
    x, y, w, h = cv2.boundingRect(mb)
    if w == 0 or h == 0:
        return None
    H, W = mb.shape
    al = align * step
    return (max(y - pad, 0) // step * step, min(y + h + pad, H), max(x - pad, 0) // al * al,
            min(-(-(x + w + pad) // al) * al, W))


def _mask_points(m, contour, step=2, mb=None):
    mb = (m > 0.5).astype(np.uint8) if mb is None else mb
    box = _mask_box(mb, step)
    if box is None:
        return np.zeros((0, 2), np.float32), (np.zeros((0, 2), np.float32) if contour else None)
    y0, y1, x0, x1 = box
    mb = mb[y0:y1, x0:x1]
    if contour:
        edge = mb - cv2.erode(mb, np.ones((3, 3), np.uint8))
        ys, xs = np.nonzero(edge)
        dist = cv2.distanceTransform(1 - mb, cv2.DIST_L2, 3) - cv2.distanceTransform(mb, cv2.DIST_L2, 3)
        gx = cv2.Sobel(dist, cv2.CV_32F, 1, 0, ksize=5)
        gy = cv2.Sobel(dist, cv2.CV_32F, 0, 1, ksize=5)
        nx, ny = gx[ys, xs], gy[ys, xs]
        ln = np.maximum(np.hypot(nx, ny), 1e-6)
        return np.stack([xs + x0, ys + y0], 1).astype(np.float32), np.stack([nx / ln, ny / ln], 1).astype(np.float32)
    ys, xs = np.nonzero(mb[::step, ::step])
    return np.stack([xs * step + x0, ys * step + y0], 1).astype(np.float32), None


def _bottom_points(m):
    mb = (m > 0.5).astype(np.uint8)
    p, nr = _mask_points(m, True, mb=mb)
    if not len(p):
        return p, nr
    y0, y1, x0, x1 = _mask_box(mb)
    _, lab, st, _ = cv2.connectedComponentsWithStats(np.ascontiguousarray(mb[y0:y1, x0:x1]), connectivity=8)
    li = lab[p[:, 1].astype(np.int64) - y0, p[:, 0].astype(np.int64) - x0]
    top, hgt = (st[li, cv2.CC_STAT_TOP] + y0).astype(np.float32), st[li, cv2.CC_STAT_HEIGHT].astype(np.float32)
    keep = (nr[:, 1] > 0.5) & (p[:, 1] >= top + 0.65 * hgt - 1)
    return p[keep], nr[keep]


def _snap(pts, contour):
    from scipy.spatial import cKDTree
    return cKDTree(contour).query(pts)[1]


def attach_to_object(pts0, masks, frames=None, max_pts=300):
    m = np.asarray(masks, np.float32)
    n = len(m)
    if len(pts0) > max_pts:
        pts0 = pts0[np.linspace(0, len(pts0) - 1, max_pts).round().astype(np.int64)]
    pos = np.zeros((n, len(pts0), 2), np.float32)
    nrm = np.zeros((n, len(pts0), 2), np.float32)
    nrm[..., 1] = 1.0
    cur, prev_c = np.asarray(pts0, np.float32), None
    gray = None
    if frames is not None:
        f = np.asarray(frames, np.float32)
        k = min(1.0, 640.0 / max(f.shape[2], 1))
        gray = [cv2.resize(cv2.cvtColor(np.clip(x[..., :3] * 255, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY), None, fx=k, fy=k,
                           interpolation=cv2.INTER_AREA) for x in f]
        fs = (m.shape[2] / gray[0].shape[1], m.shape[1] / gray[0].shape[0])
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    for i in range(n):
        mi = m[min(i, len(m) - 1)]
        c, cn = _mask_points(mi, True)
        if i > 0:
            if gray is not None:
                a, b = gray[min(i - 1, len(gray) - 1)], gray[min(i, len(gray) - 1)]
                fl = dis.calc(a, b, None)
                gx = np.clip((cur[:, 0] / fs[0]).astype(np.int64), 0, fl.shape[1] - 1)
                gy = np.clip((cur[:, 1] / fs[1]).astype(np.int64), 0, fl.shape[0] - 1)
                cur = cur + fl[gy, gx] * [fs[0], fs[1]]
            elif len(c) and prev_c is not None:
                cur = cur + (c.mean(0) - prev_c)
        if len(c):
            j = _snap(cur, c)
            cur, prev_c = c[j].astype(np.float32), c.mean(0)
            nrm[i] = cn[j]
        elif i > 0:
            nrm[i] = nrm[i - 1]
        pos[i] = cur
    return pos, nrm


def ends_on_objects(masks, n, W, H, a0=None, long_side=512):
    m = np.asarray(masks, np.float32).reshape(-1, *np.asarray(masks).shape[-2:])
    s = min(1.0, long_side / max(m.shape[1:]))
    w, h = max(1, round(m.shape[2] * s)), max(1, round(m.shape[1] * s))
    fx, fy = W / w, H / h
    pa = np.full((n, 2), np.nan)
    pb = np.full((n, 2), np.nan)
    prev = None if a0 is None else np.asarray(a0, np.float64)
    for i in range(n):
        mi = cv2.resize(m[min(i, len(m) - 1)], (w, h), interpolation=cv2.INTER_AREA) > 0.4
        k, lab, st, _ = cv2.connectedComponentsWithStats(mi.astype(np.uint8))
        objs = sorted((j for j in range(1, k) if st[j, 4] >= max(8, 0.0005 * w * h)), key=lambda j: -st[j, 4])
        if len(objs) < 2:
            continue
        cs = []
        for j in objs[:2]:
            c, _ = cv2.findContours((lab == j).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cs.append(np.concatenate(c)[:, 0].astype(np.float64))
        d2 = ((cs[0][:, None] - cs[1][None]) ** 2).sum(-1)
        ka, kb = np.unravel_index(d2.argmin(), d2.shape)
        p, q = cs[0][ka] * (fx, fy), cs[1][kb] * (fx, fy)
        if prev is not None and np.hypot(*(q - prev)) < np.hypot(*(p - prev)):
            p, q = q, p
        pa[i], pb[i], prev = p, q, p
    ok = np.isfinite(pa[:, 0])
    if not ok.any():
        return None, None
    idx = np.maximum.accumulate(np.where(ok, np.arange(n), -1))
    idx[idx < 0] = np.nonzero(ok)[0][0]
    return pa[idx], pb[idx]


class Emitter:

    def __init__(self, kind, n, fps, W, H, P, rng, a=None, b=None, masks=None, drawing=None, area=None, depth=None,
                 cam=None, attach="track", frames=None, memo=None):
        self.kind, self.n, self.fps, self.W, self.H, self.P, self.rng = kind, n, fps, W, H, P, rng
        self.memo = memo
        self.cam = cam or Camera(n)
        self.depth = depth or Depth(None, W, H)
        self.a = self._path(a, n, (W / 2, H / 2))
        self.b = self._path(b, n, None) if b is not None else None
        self.area = area or [0.4, 0.4, 0.6, 0.6]
        self.pts = self.nrm = None
        self.dpath = self.dnrm = None
        self.attach = attach if attach in LINE_ATTACH else "track"
        self.groups = None
        self.masks = None if masks is None else np.asarray(masks, np.float32).reshape(-1, *np.asarray(masks).shape[-2:])
        self.has_a = a is not None
        if kind == "groups":
            g = P.get("groups")
            g = json.loads(g) if isinstance(g, str) else g
            if not g:
                raise ValueError("emitter 'groups' needs a list of groups (x, y, depth, scale, offset), e.g. in the settings' extra JSON")
            self.groups = [dict(x=float(e.get("x", 0.5)), y=float(e.get("y", 0.5)), depth=float(e.get("depth", 0.5)),
                                scale=float(e.get("scale", 1.0)), offset=float(e.get("offset", 0))) for e in g]
            self.a = np.tile([np.mean([e["x"] for e in self.groups]) * W, np.mean([e["y"] for e in self.groups]) * H], (n, 1))
        drawn = drawing is not None and float(np.max(drawing)) > 0.5
        if kind == "drawing" and not drawn and self.attach == "object" and masks is not None:
            kind = self.kind = "object bottom edge"
        if kind in OBJECT_EMITTERS:
            if masks is None:
                raise ValueError(f"emitter '{kind}' needs an object mask")
            m = np.asarray(masks, np.float32).reshape(-1, *np.asarray(masks).shape[-2:])
            sy, sx = H / m.shape[1], W / m.shape[2]
            key = ("points", kind, n, W, H, m.shape)
            if memo is not None and key in memo:
                self.pts, self.nrm = list(memo[key][0]), list(memo[key][1])
            else:
                self.pts, self.nrm = [], []
                last = None
                for i in range(n):
                    mi = m[min(i, len(m) - 1)]
                    at = (mi.__array_interface__["data"][0], mi.strides)
                    if last is None or last[0] != at:
                        p, nr = _bottom_points(mi) if kind == "object bottom edge" else _mask_points(mi, kind == "object contour")
                        last = (at, p * [sx, sy], nr)
                    self.pts.append(last[1])
                    self.nrm.append(last[2])
                if memo is not None:
                    memo[key] = (list(self.pts), list(self.nrm))
        elif kind == "drawing":
            if not drawn:
                raise ValueError("emitter 'drawing' needs a drawing (strokes painted in the mask editor)")
            d = np.asarray(drawing, np.float32).reshape(-1, *np.asarray(drawing).shape[-2:])[0]
            p, _ = _mask_points(d, False, step=1)
            self.pts = [p * [W / d.shape[1], H / d.shape[0]]]
            p0 = self.pts[0]
            if self.attach == "image":
                self.dpath = np.repeat(p0[None], n, 0)
            elif self.attach == "object":
                if masks is None:
                    raise ValueError("a drawing hung on the object needs the object mask")
                m = np.asarray(masks, np.float32).reshape(-1, *np.asarray(masks).shape[-2:])
                sx, sy = W / m.shape[2], H / m.shape[1]
                key = ("attached", n, W, H, m.shape, frames is None, p0.shape, p0.tobytes())
                if memo is not None and key in memo:
                    pm, self.dnrm = memo[key]
                else:
                    pm, self.dnrm = attach_to_object(p0 / [sx, sy], m[:n] if len(m) >= n else
                                                     np.concatenate([m, np.repeat(m[-1:], n - len(m), 0)]), frames)
                    if memo is not None:
                        memo[key] = (pm, self.dnrm)
                self.dpath = pm * [sx, sy]
            elif self.b is not None:
                v0 = self.b[0] - self.a[0]
                l0 = max(float(np.hypot(*v0)), 1e-6)
                path = []
                for i in range(n):
                    v = self.b[i] - self.a[i]
                    s = float(np.hypot(*v)) / l0
                    ang = math.atan2(v[1], v[0]) - math.atan2(v0[1], v0[0])
                    R = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]]) * s
                    path.append(self.a[i] + (p0 - self.a[0]) @ R.T)
                self.dpath = np.array(path, np.float64)
        self.contact = self._contact() if (kind == "object bottom edge" and P.get("contact_only", 0)) else None
        self.center = self._centers()
        self.z = self._depths()
        zs = self.z[np.isfinite(self.z)]
        if kind == "whole frame" or kind == "area":
            dd = self.depth.d[0] if self.depth else None
            if dd is not None:
                self.zlo, self.zhi = float(np.quantile(dd, 0.05)), float(np.quantile(dd, 0.995))
                self.zhi = self.zlo + (self.zhi - self.zlo) * (1.0 - float(np.clip(P.get("depth_far", 0.0), 0.0, 0.95)))
                self.zref = float(np.median(dd))
            else:
                self.zlo = self.zhi = self.zref = 1.0
        elif kind == "groups":
            self.zref = float(np.median([e["depth"] for e in self.groups]))
        else:
            self.zref = float(zs[0]) if len(zs) else 1.0
        self.vel = self._velocity()

    def _contact(self):
        if not self.depth:
            return None
        H, P = self.H, self.P
        on = np.zeros(self.n, bool)
        for i in range(self.n):
            p = self.pts[i]
            if not len(p):
                continue
            ze = self.depth.at(i, p[:, 0], np.maximum(p[:, 1] - 0.01 * H, 0))
            zb = self.depth.at(i, p[:, 0], np.minimum(p[:, 1] + P["contact_gap"] * H, H - 1))
            on[i] = float(np.median(ze - zb)) < P["contact_tol"]
        k = np.pad(on.astype(np.float32), 2, mode="edge")
        return np.array([np.median(k[i:i + 5]) > 0.5 for i in range(self.n)])

    @staticmethod
    def _path(tr, n, default):
        if tr is None:
            return None if default is None else np.tile(np.array(default, np.float64), (n, 1))
        p = np.array(tr["point_track_px"] if isinstance(tr, dict) else tr, np.float64).reshape(-1, 2)[:n]
        if len(p) < n:
            p = np.concatenate([p, np.repeat(p[-1:], n - len(p), 0)])
        return p

    def _centers(self):
        if self.kind in OBJECT_EMITTERS:
            c = [p.mean(0) if len(p) else np.array([np.nan, np.nan]) for p in self.pts]
            c = np.array(c, np.float64)
            ok = np.isfinite(c[:, 0])
            if not ok.any():
                raise ValueError("the object mask is empty in every frame. Nothing was found at the click: click on a clearer object or surface, or name it with an object word.")
            for j in range(2):
                c[:, j] = np.interp(np.arange(self.n), np.nonzero(ok)[0], c[ok, j])
            return c
        if self.kind == "line A-B" and self.b is not None:
            return (self.a + self.b) / 2
        if self.kind in ("area", "whole frame"):
            x0, y0, x1, y1 = self.area if self.kind == "area" else (0, 0, 1, 1)
            return np.tile([(x0 + x1) / 2 * self.W, (y0 + y1) / 2 * self.H], (self.n, 1)).astype(np.float64)
        if self.kind == "drawing" and self.dpath is not None:
            return np.asarray(self.dpath, np.float64).mean(1)
        if self.kind == "drawing":
            off = self.a - self.a[0]
            return self.pts[0].mean(0)[None] + off
        return self.a.copy()

    def _depths(self):
        off = self.P.get("depth_offset", 0.0)
        if not self.depth:
            return np.ones(self.n)
        z = np.zeros(self.n)
        for i in range(self.n):
            if self.kind in OBJECT_EMITTERS:
                p = self.pts[i]
                z[i] = np.median(self.depth.at(i, p[:, 0], p[:, 1])) if len(p) else np.nan
            else:
                c = self.center[i]
                z[i] = self.depth.at(i, np.array([c[0]]), np.array([c[1]]))[0]
        ok = np.isfinite(z)
        if ok.any() and not ok.all():
            z = np.interp(np.arange(self.n), np.nonzero(ok)[0], z[ok])
        return z + off

    def _velocity(self):
        wx, wy = np.zeros(self.n), np.zeros(self.n)
        for i in range(self.n):
            wx[i], wy[i] = self.cam.to_world(self.center[i, 0], self.center[i, 1], i)
        v = np.stack([np.gradient(wx), np.gradient(wy)], 1) * self.fps if self.n > 1 else np.zeros((self.n, 2))
        k = np.array([1, 2, 3, 2, 1], np.float64)
        k /= k.sum()
        return np.stack([np.convolve(np.pad(v[:, j], 2, mode="edge"), k, mode="valid") for j in range(2)], 1)

    def frame(self, t):
        return min(max(int(round(t * self.fps)), 0), self.n - 1)

    def _lerp(self, path, t):
        f = np.clip(t * self.fps, 0, self.n - 1)
        i0 = int(np.floor(f))
        i1 = min(i0 + 1, self.n - 1)
        w = f - i0
        return path[i0] * (1 - w) + path[i1] * w

    def sample(self, t, k, u=None):
        i, ps = self.frame(t), min(self.W, self.H) / REF * float(self.P.get("scale", 1.0))
        u = self.rng.uniform(0, 1, (k, 5)) if u is None else np.asarray(u, np.float64)
        nrm = None
        if self.kind == "point A" or (self.kind == "line A-B" and self.b is None):
            pos = np.repeat(self._lerp(self.a, t)[None], k, 0)
        elif self.kind == "line A-B":
            w = u[:, :1]
            pos = self._lerp(self.a, t)[None] * (1 - w) + self._lerp(self.b, t)[None] * w
        elif self.kind == "drawing" and self.dpath is not None:
            dp = self.dpath
            j = np.minimum((u[:, 0] * dp.shape[1]).astype(np.int64), dp.shape[1] - 1)
            f = float(np.clip(t * self.fps, 0, self.n - 1))
            i0 = int(np.floor(f))
            i1, w = min(i0 + 1, self.n - 1), f - i0
            pos = (dp[i0, j] * (1 - w) + dp[i1, j] * w).astype(np.float64)
            nrm = self.dnrm[i0, j] if self.dnrm is not None else None
        elif self.kind == "drawing":
            p = self.pts[0]
            pos = p[np.minimum((u[:, 0] * len(p)).astype(np.int64), len(p) - 1)] + (self._lerp(self.a, t) - self.a[0])[None]
        elif self.kind in OBJECT_EMITTERS:
            p = self.pts[i]
            if len(p) == 0:
                return np.zeros((0, 2)), None, np.zeros(0)
            j = np.minimum((u[:, 0] * len(p)).astype(np.int64), len(p) - 1)
            pos = p[j].astype(np.float64)
            nrm = self.nrm[i][j] if self.nrm[i] is not None else None
        elif self.kind == "area":
            x0, y0, x1, y1 = self.area
            pos = np.stack([(x0 + (x1 - x0) * u[:, 0]) * self.W, (y0 + (y1 - y0) * u[:, 1]) * self.H], 1)
        else:
            if self.P.get("band") == "top":
                y = (-0.15 + 0.13 * u[:, 1]) * self.H
            else:
                y = (-0.05 + 1.1 * u[:, 1]) * self.H
            pos = np.stack([(-0.1 + 1.2 * u[:, 0]) * self.W, y], 1)
        r = self.P["radius"] * ps
        if r > 0:
            a, rr = 2 * np.pi * u[:, 2], r * np.sqrt(u[:, 3])
            pos = pos + np.stack([np.cos(a) * rr, np.sin(a) * rr], 1)
        if self.kind in ("area", "whole frame"):
            z = self.zlo + (self.zhi - self.zlo) * u[:, 4] ** 2 if self.depth else np.ones(k)
        elif self.kind in OBJECT_EMITTERS + ("drawing", "line A-B") and self.depth:
            z = self.depth.at(i, pos[:, 0], pos[:, 1]) + self.P.get("depth_offset", 0.0)
        else:
            z = np.full(k, self.z[i])
        return pos, nrm, z


def sfac0(em):
    if em.kind in ("area", "whole frame") and em.depth:
        return float(np.clip((em.zlo + (em.zhi - em.zlo) / 3) / max(em.zref, 1e-3), 0.15, 4.0))
    return 1.0


RATE_CURVES = {"even": [], "explosion": [[0.0, 1.0], [0.04, 1.0], [0.12, 0.2], [0.3, 0.0]],
               "pulses": [[0.0, 0.0], [0.08, 1.0], [0.2, 0.0], [0.4, 0.0], [0.48, 1.0], [0.6, 0.0], [0.8, 0.0], [0.88, 1.0],
                          [1.0, 0.0]],
               "grows": [[0.0, 0.0], [1.0, 1.0]], "dies down": [[0.0, 1.0], [1.0, 0.0]]}


def rate_curve_at(curve, u):
    if not curve:
        return 1.0
    pts = sorted((float(a), float(b)) for a, b in curve)
    if u <= pts[0][0]:
        return min(1.0, max(0.0, pts[0][1]))
    for (a, va), (b, vb) in zip(pts, pts[1:]):
        if u <= b:
            k = 0.0 if b - a <= 1e-9 else (u - a) / (b - a)
            return min(1.0, max(0.0, va + (vb - va) * k))
    return min(1.0, max(0.0, pts[-1][1]))


def burst_times(P, n, fps):
    t = P["start"] + P["burst_at"]
    end = P["end"] if P["end"] > 0 else (n - 1) / fps
    if P.get("burst_every", 0.0) <= 0:
        return [t]
    out = []
    while t <= end + 1e-9 and len(out) < 1000:
        out.append(t)
        t += P["burst_every"]
    return out or [P["start"] + P["burst_at"]]


def _capacity(P, duration):
    every = P.get("burst_every", 0.0)
    k = P["rate"] * duration * 1.15 + P["burst"] * (int(duration / every) + 1 if every > 0 else 1) + 16
    ch = P.get("children")
    if ch:
        k *= 1 + ch.get("count", 0)
    return int(max(16, k))


def _cell_means(x, y, vx, vy, R, off):
    kx = np.floor((x + off[0]) / R).astype(np.int64)
    ky = np.floor((y + off[1]) / R).astype(np.int64)
    _, inv, cnt = np.unique(kx * 4_000_037 + ky, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    m = [np.bincount(inv, v) / cnt for v in (x, y, vx, vy)]
    return [v[inv] for v in m] + [cnt[inv]]


def flock_accel(x, y, vx, vy, unit, P, ps, rng):
    R = max(P["flock_radius"] * ps, 1.0)
    mx, my, mvx, mvy, c = _cell_means(x, y, vx, vy, R, rng.uniform(0, R, 2))
    nb = (c > 1).astype(np.float64)
    ax = nb * (P["flock_cohesion"] * (mx - x) / unit + P["flock_align"] * (mvx - vx))
    ay = nb * (P["flock_cohesion"] * (my - y) / unit + P["flock_align"] * (mvy - vy))
    r = R / 3
    sx, sy, _, _, c3 = _cell_means(x, y, vx, vy, r, rng.uniform(0, r, 2))
    crowd = np.maximum(c3 - 1, 0)
    ax += P["flock_separation"] * crowd * (x - sx) / unit
    ay += P["flock_separation"] * crowd * (y - sy) / unit
    return P["flock"] * ax, P["flock"] * ay


def _dolly(P, cam, dep, n, W, H):
    if P.get("fly", 0) <= 0 or not dep or n < 2:
        return None
    sc = np.array([math.sqrt(abs(np.linalg.det(m[:2, :2]))) for m in cam.m])
    m = cam.m[-1]
    if abs(sc[-1] - 1.0) < 0.02:
        return None
    foe = np.linalg.solve(np.eye(2) - m[:2, :2], m[:2, 2])
    foe = np.clip(foe, [0.0, 0.0], [W, H])
    zb = max(float(np.median(dep.d[0])), 1e-3)
    return foe, zb, P["fly"] * (1.0 - 1.0 / sc), sc


LOOK_ONLY = ("size", "size_var", "fine_size", "size_start", "size_end", "opacity", "fade_in", "fade_out", "flicker",
             "flicker_hz", "flicker_size", "flicker_duty")


def _record_look(P, t, age, lt, land_t, size0, phase, sz, ps):
    al = P["opacity"] * fade(age, P["fade_in"], P["fade_out"])
    if lt.any():
        tl = t[lt] if np.ndim(t) else t
        al[lt] = P["opacity"] * np.clip(1 - (tl - land_t[lt]) / max(P["land_fade"], 1e-3), 0, 1)
    if P["flicker"] > 0:
        hz = P["flicker_hz"]
        if P.get("flicker_size", 0) > 0:
            hz = hz * (P["size"] / np.maximum(size0, 1e-3)) ** (0.5 * P["flicker_size"])
        if P.get("flicker_duty", 0) > 0:
            d = min(P["flicker_duty"], 1.0)
            u = np.mod(hz * t + phase / (2 * np.pi), 1.0)
            e = 0.1 * d
            on = np.clip(np.minimum(u, d - u) / max(e, 1e-6) + 0.5, 0, 1)
            al *= 1 - P["flicker"] * (1 - on)
        else:
            al *= 1 - P["flicker"] * 0.5 * (1 + np.sin(2 * np.pi * hz * t + phase))
    size = size0 * (P["size_start"] + (P["size_end"] - P["size_start"]) * age) * sz * ps
    return size, al


def relook(rec, P):
    lk = rec.get("_look")
    if lk is None or lk["dolly"]:
        return None
    fi, a = np.nonzero(lk["on"])
    size0 = lk["size0"].copy()
    m = lk["main"]
    size0[m] = P.get("size", 4.0) * (1 + P.get("size_var", 0.0) * lk["sym5"][m])
    size0[m & lk["fine"]] *= P["fine_size"]
    t = lk["t"][fi]
    age = np.clip((t - lk["born"][a]) / lk["life"][a], 0, 1)
    sz = lk["sz"][fi, a] if lk["sz"] is not None else np.ones(len(a))
    size, al = _record_look(P, t, age, lk["lt"][fi, a], lk["land_t"][a], size0[a], lk["phase"][a], sz, lk["ps"])
    out = dict(rec)
    out["size"], out["alpha"] = np.zeros_like(rec["size"]), np.zeros_like(rec["alpha"])
    out["size"][fi, a], out["alpha"][fi, a] = size, al
    return out


def simulate(P, em, seed=0, amount=1.0, target=None, flow=None, look_state=False):
    n, fps, W, H, cam, dep = em.n, em.fps, em.W, em.H, em.cam, em.depth
    rng = np.random.default_rng(seed)
    ps = min(W, H) / REF * float(P.get("scale", 1.0))
    sub = max(1, int(P["substeps"]))
    dt = 1.0 / (fps * sub)
    pre = P["preroll"]
    if pre < 0:
        v = max(P["speed"] * ps * (1 - P["speed_var"]) * sfac0(em), 1.0)
        pre = min(60.0, P["life"], 1.1 * (H if em.kind == "whole frame" and P.get("band") == "top" else min(W, H)) / v)
    t0 = P["start"] - (pre if P["start"] <= 0 else 0.0)
    t_end = P["end"] if P["end"] > 0 else 1e9
    pre_steps = int(math.ceil(max(0.0, -t0) * fps * sub))
    steps = pre_steps + (n - 1) * sub + 1
    rate = P["rate"] * amount * (W / REF if em.kind == "whole frame" else 1.0)
    burst = int(round(P["burst"] * amount))
    cap = _capacity(dict(P, rate=rate, burst=burst), max(0.0, min(t_end, (n - 1) / fps) - t0) + dt)
    amax = max(8.0, amount)
    keep_q = amount / amax
    rate_c = rate / max(amount, 1e-9) * amax if amount > 0 else 0.0
    burst_c = int(round(P["burst"] * amax))
    off = float(hash_u(0, seed=seed))
    kept = lambda ids, ns: ids[np.mod(ids * 0.6180339887498949 + off + 0.5 * ns, 1.0) < keep_q]
    zr = max(em.zref, 1e-3)
    dolly = _dolly(P, cam, dep, n, W, H)
    noise = CurlNoise(rng, P["turbulence"], P["turb_scale"], P["turb_speed"])
    frng = np.random.default_rng(seed + 7919)
    tgt = None if target is None else Emitter._path(target, n, None)

    max_alive = int(P["max_particles"])
    st = {k: np.zeros(cap) for k in ("x", "y", "z", "vx", "vy", "born", "life", "size0", "rot", "spin", "rnd", "phase",
                                      "land_t", "grav", "drag", "px", "py", "rid", "foff", "sym5", "main", "fine", "pop")}
    alive = np.zeros(cap, bool)
    landed = np.zeros(cap, bool)
    behind = np.zeros(cap, bool)
    kind = np.zeros(cap, np.int8)
    used = 0
    rec = {k: np.full((n, cap), np.nan if k == "x" else 0.0, np.float32)
           for k in ("x", "y", "z", "vx", "vy", "size", "alpha", "vis", "age", "rot") + (("zd",) if dolly is not None else ())}
    stats = dict(spawned=0, children=0, landed=0, bounced=0, killed_by_target=0, capacity=max_alive, capped=0)
    look = None
    if look_state:
        look = dict(t=np.zeros(n), on=np.zeros((n, cap), bool), lt=np.zeros((n, cap), bool), sz=np.zeros((n, cap)) if dep else None)

    def grow(need):
        nonlocal cap, alive, landed, behind, kind
        if need <= cap:
            return
        new = max(need, int(cap * 1.5) + 16)
        for k in st:
            st[k] = np.concatenate([st[k], np.zeros(new - cap)])
        alive, landed, behind = (np.concatenate([v, np.zeros(new - cap, bool)]) for v in (alive, landed, behind))
        kind = np.concatenate([kind, np.zeros(new - cap, np.int8)])
        for k in rec:
            rec[k] = np.concatenate([rec[k], np.full((n, new - cap), np.nan if k == "x" else 0.0, np.float32)], 1)
        if look is not None:
            for k in ("on", "lt", "sz"):
                if look[k] is not None:
                    look[k] = np.concatenate([look[k], np.zeros((n, new - cap), look[k].dtype)], 1)
        cap = new

    def sfac(z):
        return np.clip(z / zr, 0.15, 4.0) if dep else np.ones_like(z)

    def spawn(t, ids, ns, at=None, z_at=None, ch=None):
        nonlocal used
        k = int(max(0, min(len(ids), max_alive - int(np.count_nonzero(alive[:used])))))
        stats["capped"] += len(ids) - k
        if k <= 0:
            return
        grow(used + k)
        ids = np.asarray(ids[:k], np.int64)
        hu = hash_u(ids[None], ns, np.arange(17)[:, None], seed=seed).astype(np.float64)
        U = lambda c: hu[c]
        idx = np.arange(used, used + k)
        used += k
        if at is None:
            pos, nrm, zz = em.sample(t, k, np.stack([U(c) for c in range(10, 15)], 1))
            k2 = len(pos)
            if k2 < k:
                used -= k - k2
                idx, k = idx[:k2], k2
                if k == 0:
                    return
            fi = em.frame(t)
            if em.kind == "area":
                wx, wy = pos[:, 0], pos[:, 1]
            else:
                wx, wy = cam.to_world(pos[:, 0], pos[:, 1], fi)
            src = P
        else:
            wx, wy, zz, nrm, src = at[:k, 0], at[:k, 1], z_at[:k], None, ch
        mode = src.get("direction_mode", "angle")
        spr = np.radians(src.get("spread", 30.0))
        sym = lambda c: 2 * U(c) - 1
        if src.get("spread_falloff", 0.0) > 0:
            base_sym, k_fall = sym, 1.0 + 3.0 * min(1.0, src["spread_falloff"])
            sym = lambda c: (lambda u: np.sign(u) * np.abs(u) ** k_fall)(base_sym(c)) if c == 0 else base_sym(c)
        if mode == "random":
            th = 2 * np.pi * U(0)
        elif mode == "outward" and nrm is not None:
            th = np.arctan2(nrm[:, 0], -nrm[:, 1]) + spr * sym(0)
        elif mode == "against motion" and at is None:
            v = em.vel[em.frame(t)]
            moving = float(np.hypot(*v)) > 40.0 * ps
            base = math.atan2(-v[0], v[1]) if moving else np.radians(src.get("direction", 0.0))
            if moving:
                base -= math.copysign(min(np.radians(src.get("lift", 0.0)), abs(base)), math.sin(base))
            th = base + spr * sym(0)
        else:
            th = np.radians(src.get("direction", 0.0)) + spr * sym(0)
        sp = src.get("speed", 100.0) * np.maximum(1 + src.get("speed_var", 0.0) * sym(1), 0.0)
        st["vx"][idx], st["vy"][idx] = np.sin(th) * sp, -np.cos(th) * sp
        gauss = np.sqrt(-2 * np.log(np.maximum(U(2), 1e-7))) * np.cos(2 * np.pi * U(3))
        st["z"][idx] = np.clip(zz + P["depth_spread"] * (np.abs(gauss) if P.get("depth_spread_near") else gauss), 1e-3, 1.5)
        st["rid"][idx] = ids
        if at is None and P["inherit"] > 0:
            fi = em.frame(t)
            sz = sfac(st["z"][idx])
            st["vx"][idx] += P["inherit"] * em.vel[fi, 0] / (ps * sz)
            st["vy"][idx] += P["inherit"] * em.vel[fi, 1] / (ps * sz)
        st["x"][idx], st["y"][idx] = wx, wy
        st["born"][idx] = t
        st["life"][idx] = np.maximum(0.05, src.get("life", 1.0) * (1 + src.get("life_var", 0.0) * sym(4)))
        s5 = sym(5)
        st["size0"][idx] = src.get("size", 4.0) * (1 + src.get("size_var", 0.0) * s5)
        st["sym5"][idx], st["main"][idx], st["fine"][idx] = s5, src is P, 0.0
        if src is P and P["speed_by_size"] > 0:
            ks = np.maximum(1 + min(P["speed_by_size"], 1.0) * s5, 0.05)
            st["vx"][idx] *= ks
            st["vy"][idx] *= ks
        if src is P and P.get("fine_share", 0) > 0:
            fine = U(16) < P["fine_share"]
            st["fine"][idx] = fine
            st["size0"][idx[fine]] *= P["fine_size"]
            st["life"][idx[fine]] *= P["fine_life"]
            st["vx"][idx[fine]] *= P["fine_speed"]
            st["vy"][idx[fine]] *= P["fine_speed"]
        if P["max_speed"] > 0:
            vl = np.hypot(st["vx"][idx], st["vy"][idx])
            lim = np.minimum(1.0, P["max_speed"] / np.maximum(vl, 1e-9))
            st["vx"][idx] *= lim
            st["vy"][idx] *= lim
        st["rot"][idx] = 2 * np.pi * U(6)
        st["spin"][idx] = sym(7)
        st["rnd"][idx] = U(8)
        st["phase"][idx] = 2 * np.pi * U(9)
        g = src.get("gravity", P["gravity"])
        if P["scene_height"] > 0 and g > 0:
            g = 9.81 * REF / P["scene_height"]
        st["grav"][idx] = g
        st["pop"][idx] = 0.0
        st["drag"][idx] = src.get("drag", P["drag"])
        alive[idx] = True
        landed[idx] = False
        kind[idx] = 1 if (at is not None and ns in (2, 4)) else 0
        fi = em.frame(t)
        sx, sy = cam.to_screen(wx, wy, fi)
        behind[idx] = (dep.at(fi, sx, sy) - st["z"][idx]) > 0.002 if dep else False
        stats["children" if (at is not None and ns in (2, 4)) else "spawned"] += k

    def children(h, t, z_front, ns=2):
        ch = P.get("children")
        c = int(ch.get("count", 0)) if ch else 0
        if c <= 0 or len(h) == 0:
            return
        at = np.repeat(np.stack([st["px"][h], st["py"][h]], 1), c, 0)
        ids = (np.repeat(st["rid"][h].astype(np.int64), c) * c + np.tile(np.arange(c), len(h)))
        spawn(t, ids, ns, at=at, z_at=np.repeat(z_front, c), ch=ch)

    ch_age = float((P.get("children") or {}).get("at_age", 0.0) or 0.0)
    ch_chance = float((P.get("children") or {}).get("chance", 1.0))

    if em.kind == "groups":
        gs = em.groups
        f0 = em.frame(max(t0, 0.0))
        wxy = np.array([cam.to_world(np.array([e["x"] * W]), np.array([e["y"] * H]), f0) for e in gs], np.float64).reshape(-1, 2)
        zg = np.array([e["depth"] for e in gs], np.float64)
        u0 = used
        spawn(t0, np.arange(len(gs)), 3, at=wxy, z_at=zg, ch=dict(P, speed=0.0, speed_var=0.0, life=1e6, life_var=0.0, size_var=0.0))
        idx = np.arange(u0, used)
        if len(idx):
            st["z"][idx] = np.clip(zg[:len(idx)], 1e-3, 1.5)
            w_px = np.array([e["scale"] for e in gs][:len(idx)]) * P["group_size"] * W
            gp = float(P["group_perspective"])
            per = sfac(st["z"][idx]) ** gp if gp > 0 else np.ones(len(idx))
            st["size0"][idx] = w_px / 2 / (np.maximum(sfac(st["z"][idx]), 1e-6) * ps) * per
            st["rot"][idx] = 0.0
            st["spin"][idx] = 0.0
            st["foff"][idx] = [e["offset"] for e in gs][:len(idx)]
            st["vx"][idx] = 0.0
            st["vy"][idx] = 0.0
            behind[idx] = False

    acc = 0.0
    cid = 0
    t_bursts = burst_times(P, n, fps)
    nb = 0
    curve = P.get("rate_curve") or []
    c_end = P["end"] if P["end"] > 0 else (n - 1) / fps
    c_len = max(c_end - P["start"], 1e-6)
    rec_noise = None
    for s in range(steps):
        if s % 16 == 0:
            interrupted()
        t = (s - pre_steps) * dt
        fi = min(max(int(round(t * fps)), 0), n - 1)
        if t0 - 1e-9 <= t <= t_end and (em.contact is None or em.contact[fi]):
            acc += rate_c * dt * (rate_curve_at(curve, (t - P["start"]) / c_len) if curve else 1.0)
            kc = int(acc)
            acc -= kc
            groups = []
            if kc:
                ids = np.arange(cid, cid + kc)
                cid += kc
                groups.append((kept(ids, 0), 0))
            while burst and nb < len(t_bursts) and t >= t_bursts[nb] - 1e-9:
                ids = np.arange(nb * burst_c, (nb + 1) * burst_c)
                nb += 1
                groups.append((kept(ids, 1), 1))
            for ids, ns in groups:
                if len(ids):
                    spawn(t, ids, ns)
        a = np.nonzero(alive[:used])[0]
        if len(a):
            age = (t - st["born"][a]) / st["life"][a]
            gone = (age >= 1.0) & ~landed[a]
            gone |= landed[a] & (t - st["land_t"][a] >= P["land_fade"])
            sx, sy = cam.to_screen(st["x"][a], st["y"][a], fi)
            gone |= (sx < -0.6 * W) | (sx > 1.6 * W) | (sy < -0.6 * H) | (sy > 1.6 * H)
            alive[a[gone]] = False
        if s >= pre_steps and (s - pre_steps) % sub == 0:
            i = (s - pre_steps) // sub
            a = np.nonzero(alive[:used] & (st["born"][:used] <= t + 1e-9))[0]
            if len(a):
                sx, sy = cam.to_screen(st["x"][a], st["y"][a], i)
                z = st["z"][a]
                if dolly is not None:
                    foe, zb, tz, sc = dolly
                    den = 1.0 - tz[i] * z / zb
                    kd = 1.0 / np.maximum(den, 0.05)
                    sx = foe[0] + (sx - foe[0]) * kd / sc[i]
                    sy = foe[1] + (sy - foe[1]) * kd / sc[i]
                sz = sfac(z)
                fx, fy = noise(st["x"][a] / ps, st["y"][a] / ps, t)
                rec_noise = (s, a, fx, fy)
                k = turb_calm(P, t - st["born"][a], st["life"][a], st["drag"][a])
                if k is not None:
                    fx, fy = fx * k, fy * k
                age = np.clip((t - st["born"][a]) / st["life"][a], 0, 1)
                lt = landed[a]
                size, al = _record_look(P, t, age, lt, st["land_t"][a], st["size0"][a], st["phase"][a], sz, ps)
                if look is not None:
                    look["t"][i] = t
                    look["on"][i, a], look["lt"][i, a] = True, lt
                    if look["sz"] is not None:
                        look["sz"][i, a] = sz
                if dolly is not None:
                    size = size * kd
                    al = al * np.clip((den - 0.05) / 0.15, 0, 1)
                    rec["zd"][i, a] = z * kd
                vis = np.clip((z - dep.at(i, sx, sy)) / max(P["depth_softness"], 1e-4) + 1.0, 0, 1) if dep else 1.0
                still = lt.astype(np.float64)
                rec["x"][i, a], rec["y"][i, a], rec["z"][i, a] = sx, sy, z
                rec["vx"][i, a] = (st["vx"][a] + fx) * sz * ps * (1 - still)
                rec["vy"][i, a] = (st["vy"][a] + fy) * sz * ps * (1 - still)
                rec["size"][i, a], rec["alpha"][i, a], rec["vis"][i, a] = size, al, vis
                rec["age"][i, a], rec["rot"][i, a] = age, st["rot"][a]
            frame_done(i, rec, st, used)
        live = np.nonzero(alive[:used] & ~landed[:used])[0]
        if len(live):
            x, y, z, vx, vy = (st[k][live] for k in ("x", "y", "z", "vx", "vy"))
            st["px"][live], st["py"][live] = x, y
            ax = np.full(len(live), P["wind"][0], np.float64) - st["drag"][live] * vx
            g = st["grav"][live]
            if P["gravity_end"] != 1.0:
                g = g * (1 + (P["gravity_end"] - 1) * np.clip((t - st["born"][live]) / st["life"][live], 0, 1))
            ay = g + P["wind"][1] - st["drag"][live] * vy
            if P["roll"] and len(live) > 2:
                cxr, cyr = float(x.mean()), float(y.mean())
                r = max(float(np.std(x)) * 0.8, 10.0 * ps)
                side = np.where(x >= cxr, 1.0, -1.0)
                rx, ry = x - (cxr + side * r), y - cyr
                rl = np.maximum(np.hypot(rx, ry), 1e-6)
                wr = np.minimum(1.0, rl / (0.3 * r)) * np.exp(-np.maximum(rl - r, 0.0) / r)
                ax += P["roll"] * wr * side * -ry / rl
                ay += P["roll"] * wr * side * rx / rl
            if P["vortex"] or P["attract"]:
                cx, cy = cam.to_world(em.center[fi, 0], em.center[fi, 1], fi)
                if P["vortex"]:
                    rx, ry = x - cx, y - cy
                    rl = np.maximum(np.hypot(rx, ry), 1e-6)
                    ax += P["vortex"] * -ry / rl
                    ay += P["vortex"] * rx / rl
                if P["attract"] and tgt is not None:
                    bx, by = cam.to_world(tgt[fi, 0], tgt[fi, 1], fi)
                    dx, dy = bx - x, by - y
                    dl = np.maximum(np.hypot(dx, dy), 1e-6)
                    ax += P["attract"] * dx / dl
                    ay += P["attract"] * dy / dl
                    hit = dl < P["kill_radius"] * ps
                    if hit.any():
                        alive[live[hit]] = False
                        stats["killed_by_target"] += int(hit.sum())
            if P.get("flock", 0) > 0 and len(live) > 1:
                fax, fay = flock_accel(x, y, vx, vy, sfac(z) * ps, P, ps, frng)
                ax += fax
                ay += fay
            nvx = vx + ax * dt
            nvy = vy + ay * dt
            if rec_noise is not None and rec_noise[0] == s and np.array_equal(rec_noise[1], live):
                fx, fy = rec_noise[2], rec_noise[3]
            else:
                fx, fy = noise(x / ps, y / ps, t)
            sz = sfac(z)
            if flow is not None and P["motion_carry"] > 0:
                sx, sy = cam.to_screen(x, y, fi)
                ux, uy = flow.at(fi, sx, sy)
                wx, wy = cam.to_world(sx + ux, sy + uy, fi + 1 if fi + 1 < n else fi)
                dx, dy = wx - x, wy - y
                if em.has_a and P["carry_free"] > 0:
                    fj = fi + 1 if fi + 1 < n else fi
                    e0 = cam.to_world(em.a[fi:fi + 1, 0], em.a[fi:fi + 1, 1], fi)
                    e1 = cam.to_world(em.a[fj:fj + 1, 0], em.a[fj:fj + 1, 1], fj)
                    near = np.exp(-((x - e0[0][0]) ** 2 + (y - e0[1][0]) ** 2) / (P["carry_free"] * ps) ** 2)
                    dx, dy = dx - near * (e1[0][0] - e0[0][0]), dy - near * (e1[1][0] - e0[1][0])
                w = carry_weight(np.hypot(dx, dy), ps) * (1 - (1 - min(P["motion_carry"], 1.0)) ** (1.0 / sub))
                nvx = nvx + w * (dx * fps / (sz * ps) - nvx)
                nvy = nvy + w * (dy * fps / (sz * ps) - nvy)
            age = t - st["born"][live]
            if P["speed_end"] != 1.0:
                lf = st["life"][live]
                m0 = 1 + (P["speed_end"] - 1) * np.clip(age / lf, 0, 1)
                m1 = 1 + (P["speed_end"] - 1) * np.clip((age + dt) / lf, 0, 1)
                k = np.maximum(m1, 1e-3) / np.maximum(m0, 1e-3)
                nvx, nvy = nvx * k, nvy * k
            if P["max_speed"] > 0:
                vl = np.hypot(nvx, nvy)
                k = np.minimum(1.0, P["max_speed"] / np.maximum(vl, 1e-9))
                nvx, nvy = nvx * k, nvy * k
            k = turb_calm(P, age, st["life"][live], st["drag"][live])
            if k is not None:
                fx, fy = fx * k, fy * k
            st["vx"][live], st["vy"][live] = nvx, nvy
            st["x"][live] = x + (0.5 * (vx + nvx) + fx) * dt * sz * ps
            st["y"][live] = y + (0.5 * (vy + nvy) + fy) * dt * sz * ps
            if P["sway"] > 0:
                w = 2 * np.pi * P["sway_hz"] * (0.7 + 0.6 * st["rnd"][live])
                ph = st["phase"][live]
                st["x"][live] += P["sway"] * sz * ps * (np.sin(w * (t + dt) + ph) - np.sin(w * t + ph))
            if ch_age > 0:
                due = (st["pop"][live] == 0) & (kind[live] == 0) & ((t + dt - st["born"][live]) / st["life"][live] >= ch_age)
                if due.any():
                    h = live[due]
                    st["pop"][h] = 1.0
                    st["px"][h], st["py"][h] = st["x"][h], st["y"][h]
                    go = hash_u(st["rid"][h].astype(np.int64), 4, 99, seed=seed) < ch_chance
                    children(h[go], t + dt, st["z"][h[go]], 4)
            vx, vy = nvx, nvy
            st["rot"][live] += st["spin"][live] * dt * (2.0 if P["spin"] == SPIN else math.radians(P["spin"]))
            if dep and P["collide"] != "none":
                sx, sy = cam.to_screen(st["x"][live], st["y"][live], fi)
                gap = dep.at(fi, sx, sy) - z
                now = gap > 0.002
                hitm = now & ~behind[live] & (gap < P["land_tol"]) & (vy > 0) & (kind[live] == 0)
                behind[live] = now
                if hitm.any():
                    h = live[hitm]
                    mode = P["collide"]
                    if mode == "stick":
                        landed[h] = True
                        st["land_t"][h] = t
                        st["z"][h] = z[hitm] + gap[hitm] + 0.004
                        st["vx"][h] = st["vy"][h] = 0.0
                        stats["landed"] += len(h)
                    elif mode == "bounce":
                        st["x"][h], st["y"][h] = st["px"][h], st["py"][h]
                        st["vy"][h] = -np.abs(st["vy"][h]) * P["restitution"]
                        st["vx"][h] *= P["friction"]
                        behind[h] = False
                        stats["bounced"] += len(h)
                        rest = h[np.abs(st["vy"][h]) < 40.0]
                        landed[rest] = True
                        st["land_t"][rest] = t
                        st["vx"][rest] = st["vy"][rest] = 0.0
                    elif mode == "slide":
                        st["y"][h] = st["py"][h]
                        st["vy"][h] = 0.0
                        st["vx"][h] *= P["friction"]
                        behind[h] = False
                    else:
                        alive[h] = False
                        children(h, t, z[hitm] + gap[hitm] + 0.004)
    for k in rec:
        rec[k] = rec[k][:, :used]
    rec["rnd"], rec["kind"], rec["born"] = st["rnd"][:used], kind[:used], st["born"][:used]
    rec["foff"] = st["foff"][:used]
    stats["used"] = used
    rec["stats"] = stats
    if look is not None:
        rec["_look"] = dict(t=look["t"], on=look["on"][:, :used], lt=look["lt"][:, :used],
                            sz=None if look["sz"] is None else look["sz"][:, :used], ps=ps, dolly=dolly is not None,
                            **{k: st[k][:used].copy() for k in ("born", "life", "size0", "phase", "land_t", "sym5")},
                            main=st["main"][:used] > 0, fine=st["fine"][:used] > 0)
    return rec



COARSE_SIG = 12.0


class Splats:

    def __init__(self):
        self.parts = []
        self.chunk_parts = []

    def chunks(self, x, y, r, rgb, a, rot, rnd, dx=0.0, dy=0.0):
        m = len(x)
        if m:
            f = lambda v, k: np.broadcast_to(np.asarray(v, np.float64), (m,) + k)
            self.chunk_parts.append((f(x, ()), f(y, ()), f(r, ()), f(rgb, (3,)), f(a, ()), f(rot, ()), f(rnd, ()),
                                     f(dx, ()), f(dy, ())))

    def points(self, x, y, sig, rgb, a):
        m = len(x)
        if m:
            sig = np.broadcast_to(np.asarray(sig, np.float64), (m,))
            mass = np.broadcast_to(np.asarray(a, np.float64), (m,)) * 2 * np.pi * sig ** 2
            self.parts.append((np.asarray(x, np.float64), np.asarray(y, np.float64), sig,
                               np.broadcast_to(np.asarray(rgb, np.float64), (m, 3)), mass))

    def lines(self, x0, y0, x1, y1, sig, rgb, a0, a1=None):
        m = len(x0)
        if not m:
            return
        x0, y0, x1, y1 = (np.asarray(v, np.float64) for v in (x0, y0, x1, y1))
        sig = np.broadcast_to(np.asarray(sig, np.float64), (m,))
        a0 = np.broadcast_to(np.asarray(a0, np.float64), (m,))
        a1 = a0 if a1 is None else np.broadcast_to(np.asarray(a1, np.float64), (m,))
        rgb = np.broadcast_to(np.asarray(rgb, np.float64), (m, 3))
        ln = np.hypot(x1 - x0, y1 - y0)
        step = np.maximum(0.6 * sig, 0.5)
        k = np.clip(np.ceil(ln / step).astype(np.int64), 1, 400)
        idx = np.repeat(np.arange(m), k)
        u = (np.arange(len(idx)) - np.repeat(np.cumsum(k) - k, k) + 0.5) / np.repeat(k, k)
        d = ln[idx] / k[idx]
        aa = a0[idx] + (a1[idx] - a0[idx]) * u
        mass = aa * np.maximum(d, 1e-3) * math.sqrt(2 * np.pi) * sig[idx]
        short = ln[idx] < 0.5 * sig[idx]
        mass = np.where(short, aa * 2 * np.pi * sig[idx] ** 2 / k[idx], mass)
        self.parts.append((x0[idx] + (x1[idx] - x0[idx]) * u, y0[idx] + (y1[idx] - y0[idx]) * u, sig[idx], rgb[idx], mass))

    def polyline(self, pts, sig, rgb, a):
        pts = np.asarray(pts, np.float64)
        if len(pts) < 2:
            return
        a = np.broadcast_to(np.asarray(a, np.float64), (len(pts),))
        sig = np.broadcast_to(np.asarray(sig, np.float64), (len(pts),))
        self.lines(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1], (sig[:-1] + sig[1:]) / 2, rgb, a[:-1], a[1:])

    def render(self, H, W):
        out = np.zeros((H, W, 4), np.float32)
        if not self.parts:
            self._chunks(out)
            return out
        x, y, sig, rgb, mass = (np.concatenate([p[i] for p in self.parts]) for i in range(5))
        keep = (mass > 1e-6) & (x > -4 * sig - 2) & (x < W + 4 * sig + 2) & (y > -4 * sig - 2) & (y < H + 4 * sig + 2)
        x, y, sig, rgb, mass = x[keep], y[keep], sig[keep], rgb[keep], mass[keep]
        if not len(x):
            self._chunks(out)
            return out
        cf = np.clip(np.log(np.maximum(sig, 0.5) / 0.5) / np.log(1.3), 0, 40)
        c0 = np.floor(cf).astype(np.int64)
        f1 = cf - c0
        two = f1 > 1e-6
        x, y, rgb = np.concatenate([x, x[two]]), np.concatenate([y, y[two]]), np.concatenate([rgb, rgb[two]])
        mass = np.concatenate([mass * (1 - f1), (mass * f1)[two]])
        cls = np.concatenate([c0, c0[two] + 1])
        for c in np.unique(cls):
            s = cls == c
            sg = 0.5 * 1.3 ** c
            if sg > COARSE_SIG:
                self._coarse(out, x[s], y[s], rgb[s], mass[s], sg)
                continue
            pad = int(math.ceil(3 * sg)) + 2
            Hp, Wp = H + 2 * pad, W + 2 * pad
            xx, yy = x[s] + pad, y[s] + pad
            x0, y0 = np.floor(xx).astype(np.int64), np.floor(yy).astype(np.int64)
            fx, fy = xx - x0, yy - y0
            ok = (x0 >= 0) & (y0 >= 0) & (x0 < Wp - 1) & (y0 < Hp - 1)
            if not ok.any():
                continue
            g = int(math.ceil(4 * sg)) + 2
            bx0, by0 = max(int(x0[ok].min()) - g, 0), max(int(y0[ok].min()) - g, 0)
            bx1, by1 = min(int(x0[ok].max()) + 2 + g, Wp), min(int(y0[ok].max()) + 2 + g, Hp)
            bw, bh = bx1 - bx0, by1 - by0
            w4 = np.concatenate([rgb[s] * mass[s, None], mass[s, None]], 1)[ok]
            lx, ly, fxo, fyo = x0[ok] - bx0, y0[ok] - by0, fx[ok], fy[ok]
            flat = np.concatenate([(ly + dy) * bw + (lx + dx) for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1))])
            wt = np.concatenate([(1 - fxo) * (1 - fyo), fxo * (1 - fyo), (1 - fxo) * fyo, fxo * fyo])
            img = np.zeros((bh, bw, 4), np.float32)
            for ch in range(4):
                img[..., ch] = np.bincount(flat, weights=np.tile(w4[:, ch], 4) * wt, minlength=bh * bw).reshape(bh, bw)
            img = cv2.GaussianBlur(img, (0, 0), sg, borderType=cv2.BORDER_CONSTANT)
            ox0, oy0 = max(bx0, pad), max(by0, pad)
            ox1, oy1 = min(bx1, pad + W), min(by1, pad + H)
            if ox0 < ox1 and oy0 < oy1:
                out[oy0 - pad:oy1 - pad, ox0 - pad:ox1 - pad] += img[oy0 - by0:oy1 - by0, ox0 - bx0:ox1 - bx0]
        over = np.maximum(out[..., 3:4], 1.0)
        out[..., :3] /= over
        out[..., 3] = np.clip(out[..., 3], 0, 1)
        self._chunks(out)
        return out

    def _chunks(self, out, ss=4):
        if not self.chunk_parts:
            return
        H, W = out.shape[:2]
        x, y, r, rgb, a, rot, rnd, mx, my = (np.concatenate([p[i] for p in self.chunk_parts]) for i in range(9))
        for j in np.argsort(-r):
            rj = max(float(r[j]), 0.6)
            if a[j] < 1e-3 or not (-rj < x[j] < W + rj and -rj < y[j] < H + rj):
                continue
            K = 4 + int(rnd[j] * 997) % 3
            q = np.arange(K)
            ang = 2 * np.pi * (q + 0.3 * np.sin(rnd[j] * 37 * (q + 1))) / K
            rad = rj * (0.6 + 0.4 * np.abs(np.sin(rnd[j] * 53 + q * 2.3)))
            squash = 0.35 + 0.65 * abs(math.cos(rot[j] * 0.8 + rnd[j] * 11))
            px, py = np.cos(ang) * rad, np.sin(ang) * rad * squash
            c, s_ = math.cos(rot[j]), math.sin(rot[j])
            vx, vy = px * c - py * s_, px * s_ + py * c
            b = int(math.ceil(rj)) + 2
            x0, y0 = int(math.floor(x[j])) - b, int(math.floor(y[j])) - b
            n = 2 * b + 1
            pts = np.stack([(vx + x[j] - x0) * ss, (vy + y[j] - y0) * ss], 1)
            hi = np.zeros((n * ss, n * ss), np.uint8)
            cv2.fillPoly(hi, [np.round(pts).astype(np.int32)], 255)
            cov = cv2.resize(hi, (n, n), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            if cov.max() <= 0:
                continue
            inner = cv2.erode(cov, np.ones((3, 3), np.uint8)) if rj > 2.5 else cov
            yy = (np.arange(n, dtype=np.float32)[:, None] - (y[j] - y0)) / rj
            shade = (1.08 - 0.3 * np.clip(yy, -1, 1)) * (0.85 + 0.2 * math.cos(rot[j] * 1.3 + rnd[j] * 9))
            shade = shade * (1 - 0.35 * np.clip(cov - inner, 0, 1))
            colp = (rgb[j][None, None, :] * shade[..., None] * cov[..., None]).astype(np.float32)
            L = math.hypot(mx[j], my[j])
            if L >= 1.0:
                mb = int(math.ceil(L / 2)) + 1
                kk = np.zeros((2 * mb + 1, 2 * mb + 1), np.float32)
                for t in np.linspace(-0.5, 0.5, int(math.ceil(L)) * 2 + 1):
                    px_, py_ = mb + t * mx[j], mb + t * my[j]
                    ix, iy = int(math.floor(px_)), int(math.floor(py_))
                    fx, fy = px_ - ix, py_ - iy
                    for ddy, ddx, w_ in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
                        if 0 <= iy + ddy < kk.shape[0] and 0 <= ix + ddx < kk.shape[1]:
                            kk[iy + ddy, ix + ddx] += w_
                kk /= kk.sum()
                cov = cv2.filter2D(cv2.copyMakeBorder(cov, mb, mb, mb, mb, cv2.BORDER_CONSTANT, value=0), -1, kk,
                                   borderType=cv2.BORDER_CONSTANT)
                colp = cv2.filter2D(cv2.copyMakeBorder(colp, mb, mb, mb, mb, cv2.BORDER_CONSTANT, value=0), -1, kk,
                                    borderType=cv2.BORDER_CONSTANT)
                x0, y0, n = x0 - mb, y0 - mb, n + 2 * mb
            ox0, oy0, ox1, oy1 = max(x0, 0), max(y0, 0), min(x0 + n, W), min(y0 + n, H)
            if ox0 >= ox1 or oy0 >= oy1:
                continue
            sl = (slice(oy0 - y0, oy1 - y0), slice(ox0 - x0, ox1 - x0))
            A = (cov[sl] * float(a[j]))[..., None]
            dst = out[oy0:oy1, ox0:ox1]
            dst[..., :3] = dst[..., :3] * (1 - A) + colp[sl] * float(a[j])
            dst[..., 3:] = dst[..., 3:] * (1 - A) + A


    @staticmethod
    def _coarse(out, x, y, rgb, mass, sg):
        H, W = out.shape[:2]
        q = float(sg) / COARSE_SIG
        g = int(math.ceil(4 * COARSE_SIG)) + 2
        cx, cy = x / q, y / q
        keep = (cx > -g) & (cy > -g) & (cx < W / q + g) & (cy < H / q + g)
        if not keep.any():
            return
        cx, cy, rgb, mass = cx[keep] + g, cy[keep] + g, rgb[keep], mass[keep]
        cw, ch_ = int(math.ceil(W / q)) + 2 * g + 2, int(math.ceil(H / q)) + 2 * g + 2
        x0, y0 = np.floor(cx).astype(np.int64), np.floor(cy).astype(np.int64)
        fx, fy = cx - x0, cy - y0
        w4 = np.concatenate([rgb * mass[:, None], mass[:, None]], 1) / (q * q)
        flat = np.concatenate([(y0 + dy) * cw + (x0 + dx) for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1))])
        wt = np.concatenate([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy])
        img = np.zeros((ch_, cw, 4), np.float32)
        for k in range(4):
            img[..., k] = np.bincount(flat, weights=np.tile(w4[:, k], 4) * wt, minlength=ch_ * cw).reshape(ch_, cw)
        img = cv2.GaussianBlur(img, (0, 0), COARSE_SIG, borderType=cv2.BORDER_CONSTANT)
        mx = np.broadcast_to((np.arange(W, dtype=np.float32) / q + g)[None], (H, W))
        my = np.broadcast_to((np.arange(H, dtype=np.float32) / q + g)[:, None], (H, W))
        out += cv2.remap(img, np.ascontiguousarray(mx, np.float32), np.ascontiguousarray(my, np.float32), cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT)


class Raster:

    def __init__(self, W, H, window=None, scale=1.0):
        self.window = window if (window is not None and "crop_origin_plate_px" in window) else None
        if self.window is not None:
            n = int(window.get("frames", len(window["crop_origin_plate_px"])))
            self.org = np.array(window["crop_origin_plate_px"], np.float64)
            self.sc = np.array(window.get("scale_per_frame", [window["scale_roi_per_plate_px"]] * n), np.float64).ravel()
            self.w, self.h = int(window["roi_size"][0]), int(window["roi_size"][1])
        else:
            self.k = scale
            self.w, self.h = int(round(W * scale)), int(round(H * scale))

    def scale(self, i):
        return self.k if self.window is None else self.sc[min(i, len(self.sc) - 1)]

    def map(self, i, x, y):
        if self.window is None:
            return x * self.k, y * self.k
        j = min(i, len(self.org) - 1)
        return (x - self.org[j, 0]) * self.sc[j], (y - self.org[j, 1]) * self.sc[j]

    def edge(self, x, y, share):
        if share <= 0:
            return np.ones_like(x)
        d = np.minimum.reduce([x, y, self.w - 1 - x, self.h - 1 - y])
        return smoothstep(d / (share * min(self.w, self.h)))


def plate_colours(rec, plate, sigma=0.004):
    n, cap = rec["x"].shape
    out = np.full((cap, 3), 0.5, np.float32)
    if cap == 0:
        return out
    fin = np.isfinite(rec["x"])
    has = fin.any(0)
    first = np.argmax(fin, 0)
    H, W = plate.shape[1:3]
    sg = max(1.0, sigma * float(np.hypot(H, W)))
    for f in np.unique(first[has]):
        a = np.nonzero(has & (first == f))[0]
        img = cv2.GaussianBlur(plate[min(int(f), len(plate) - 1)][..., :3].astype(np.float32), (0, 0), sg)
        x = np.clip(np.round(rec["x"][f, a]).astype(int), 0, W - 1)
        y = np.clip(np.round(rec["y"][f, a]).astype(int), 0, H - 1)
        out[a] = img[y, x]
    return out


def particle_colors(P, rec, i, a):
    c = gradient(P["colors"], rec["age"][i, a])
    m = float(P.get("plate_color", 0.0) or 0.0)
    if m > 0 and "pcol" in rec:
        c = c * (1 - m) + rec["pcol"][a] * c * m
    if P["color_var"] > 0:
        c = c * (1 + P["color_var"] * (rec["rnd"][a, None] - 0.5) * 2)
    return np.clip(c, 0, 4)


def draw_particles(sp, P, rec, i, a, rx, ry, rs, al, style, fps, k=1.0, zmax=1.0):
    if not len(a):
        return
    vx, vy = rec["vx"][i, a] * k, rec["vy"][i, a] * k
    sh = max(P["shutter"], 1.0) / fps
    if style == "temperature":
        lum = particle_colors(P, rec, i, a) @ np.array([0.2126, 0.7152, 0.0722])
        top = max(float(np.max(np.array([c for _, c in P["colors"]]) @ np.array([0.2126, 0.7152, 0.0722]))), 1e-3)
        v = 0.15 + 0.85 * np.clip(lum / top, 0, 1)
        sp.points(rx, ry, np.maximum(0.6 * rs, 1.0), np.stack([v, v, v], 1), al)
        return
    if style == "volume":
        v = 0.35 + 0.65 * np.clip(rec["z"][i, a] / max(zmax, 1e-3), 0, 1)
        if P["sprite"] == "chunk":
            sp.chunks(rx, ry, np.maximum(rs, 1.0), np.stack([v, v, v], 1), al, rec["rot"][i, a], rec["rnd"][a],
                      vx * P["shutter"] / fps, vy * P["shutter"] / fps)
            return
        sp.points(rx, ry, np.maximum(0.6 * rs, 1.0), np.stack([v, v, v], 1), al)
        return
    if style == "lines":
        moving = np.hypot(vx, vy) * sh > 1.5
        m = moving
        sp.lines(rx[m] - vx[m] * sh, ry[m] - vy[m] * sh, rx[m], ry[m], 0.8, [1, 1, 1], 0.3 * al[m], al[m])
        sp.points(rx[~m], ry[~m], np.clip(rs[~m], 1.0, 3.0), [1, 1, 1], al[~m])
        return
    col = particle_colors(P, rec, i, a) * P["glow"]
    spr = P["sprite"]
    if spr == "dot":
        sp.points(rx, ry, np.maximum(0.5 * rs, 0.6), col, al)
    elif spr == "chunk":
        s3 = P["shutter"] / fps
        sp.chunks(rx, ry, np.maximum(rs, 0.8), col, al, rec["rot"][i, a], rec["rnd"][a], vx * s3, vy * s3)
    elif spr == "flake":
        sp.points(rx, ry, np.maximum(0.45 * rs, 0.6), col, al)
        sp.points(rx, ry, np.maximum(rs, 1.0), col, 0.3 * al)
    elif spr == "puff":
        rot, rnd = rec["rot"][i, a], rec["rnd"][a]
        sp.points(rx, ry, np.maximum(0.7 * rs, 0.8), col, 0.6 * al)
        for q in range(4):
            ang = rot + q * np.pi / 2 + rnd * 1.3
            off = rs * (0.45 + 0.25 * np.sin(rnd * 7 + q))
            sp.points(rx + np.cos(ang) * off, ry + np.sin(ang) * off, np.maximum(0.5 * rs, 0.6), col, 0.45 * al)
    elif spr in ("streak", "spark"):
        s2 = max(P["shutter"], 0.3) / fps
        sp.lines(rx - vx * s2, ry - vy * s2, rx, ry, np.maximum(0.5 * rs, 0.5), col, 0.15 * al, al)
        if spr == "spark":
            sp.points(rx, ry, np.maximum(0.8 * rs, 0.7), col, al)
    else:
        sp.points(rx, ry, np.maximum(0.6 * rs, 0.6), col, al)


def draw_trails(sp, P, rec, i, a, raster, style, k):
    T = int(P["trail"])
    if T <= 0 or not len(a):
        return
    j0 = max(0, i - T)
    xs, ys = rec["x"][j0:i + 1, a], rec["y"][j0:i + 1, a]
    al = rec["alpha"][i, a] * (rec["vis"][i, a] if P.get("_premask", True) else 1.0)
    col = np.ones((len(a), 3)) if style != "seed" else particle_colors(P, rec, i, a) * P["glow"]
    sig = 0.8 if style != "seed" else np.maximum(0.45 * rec["size"][i, a] * k, 0.5)
    for s in range(xs.shape[0] - 1):
        x0, y0 = raster.map(j0 + s, xs[s], ys[s])
        x1, y1 = raster.map(j0 + s + 1, xs[s + 1], ys[s + 1])
        ok = np.isfinite(x0) & np.isfinite(x1)
        f0 = (s + 1) / (xs.shape[0])
        f1 = (s + 2) / (xs.shape[0])
        sp.lines(x0[ok], y0[ok], x1[ok], y1[ok], np.broadcast_to(sig, (len(a),))[ok], col[ok], 0.6 * al[ok] * f0, 0.6 * al[ok] * f1)



def _midpoints(q, g, rough, levels, fine=None):
    j = 0
    for lv in range(levels):
        r = rough * (1.0 - 0.45 * lv / max(levels - 1, 1)) if fine is None else rough + (fine - rough) * lv / max(levels - 1, 1)
        a, b = q[:, :-1], q[:, 1:]
        d = b - a
        L = np.hypot(d[..., 0], d[..., 1]) + 1e-6
        nrm = np.stack([-d[..., 1], d[..., 0]], -1) / L[..., None]
        k = a.shape[1]
        mid = (a + b) / 2 + nrm * g[:, j:j + k, None] * r * L[..., None]
        j += k
        new = np.empty((len(q), 2 * q.shape[1] - 1, 2))
        new[:, 0::2], new[:, 1::2] = q, mid
        q = new
    return q


def bolt_path(p0, p1, rng, rough, levels=6, fine=None):
    q = np.array([[np.asarray(p0, np.float64), np.asarray(p1, np.float64)]])
    return _midpoints(q, rng.normal(size=(1, 2 ** levels - 1)), rough, levels, fine)[0]


def _ground_point(em, i, p0, length):
    if not em.depth:
        return p0 + [0, length]
    z0 = em.z[i]
    for s in np.linspace(0.05, 1.0, 40):
        q = p0 + [0, length * s]
        if em.depth.at(i, np.array([q[0]]), np.array([q[1]]))[0] - z0 > 0.02:
            return q
    return p0 + [0, length]


def thin(m):
    ys, xs = np.nonzero(m)
    out = np.zeros(m.shape, bool)
    if len(xs) == 0:
        return out
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    img = m[y0:y1, x0:x1].astype(np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            p = np.pad(img, 1)
            P2, P3, P4, P5 = p[:-2, 1:-1], p[:-2, 2:], p[1:-1, 2:], p[2:, 2:]
            P6, P7, P8, P9 = p[2:, 1:-1], p[2:, :-2], p[1:-1, :-2], p[:-2, :-2]
            B = P2 + P3 + P4 + P5 + P6 + P7 + P8 + P9
            seq = [P2, P3, P4, P5, P6, P7, P8, P9, P2]
            A = sum(((seq[k] == 0) & (seq[k + 1] == 1)).astype(np.uint8) for k in range(8))
            c = ((P2 * P4 * P6 == 0) & (P4 * P6 * P8 == 0)) if step == 0 else ((P2 * P4 * P8 == 0) & (P2 * P6 * P8 == 0))
            kill = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if kill.any():
                img[kill] = 0
                changed = True
    out[y0:y1, x0:x1] = img.astype(bool)
    return out


def climb_parts(m, hub=None, max_side=480, max_tips=16):
    H, W = m.shape
    k = min(1.0, max_side / max(H, W))
    ms = m.astype(np.uint8)
    if k < 1:
        ms = cv2.resize(ms, (max(1, int(W * k)), max(1, int(H * k))), interpolation=cv2.INTER_NEAREST)
    if not ms.any():
        return []
    sk = thin(ms > 0)
    ys, xs = np.nonzero(ms)
    cen = np.array([xs.mean(), ys.mean()])
    nl, lab = cv2.connectedComponents(sk.astype(np.uint8), connectivity=8)
    nbr = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    out = []
    for c in range(1, nl):
        py, px = np.nonzero(lab == c)
        if len(px) < 6:
            continue
        if hub is None:
            b = int(np.argmax(py - 1e-3 * np.abs(px - cen[0])))
        else:
            b = int(np.argmin(np.hypot(px - hub[0] * k, py - hub[1] * k)))
        idx = {(int(y), int(x)): j for j, (y, x) in enumerate(zip(py, px))}
        dist = np.full(len(px), -1, np.int64)
        par = np.full(len(px), -1, np.int64)
        deg = np.zeros(len(px), np.int64)
        dist[b] = 0
        dq = collections.deque([b])
        while dq:
            j = dq.popleft()
            for dy, dx in nbr:
                q = idx.get((int(py[j]) + dy, int(px[j]) + dx))
                if q is None:
                    continue
                deg[j] += 1
                if dist[q] < 0:
                    dist[q] = dist[j] + 1
                    par[q] = j
                    dq.append(q)
        far = dist.max()
        if far < 4:
            continue
        for e in np.nonzero((deg <= 1) & (dist >= max(4, 0.35 * far)))[0]:
            path, j = [], int(e)
            while j >= 0:
                path.append((px[j], py[j]))
                j = int(par[j])
            path = np.array(path[::-1], np.float64) / k
            ang = math.atan2(path[-1, 1] - cen[1] / k, path[-1, 0] - cen[0] / k)
            out.append((path, ang, len(path)))
    out.sort(key=lambda q: -q[2])
    return [(p, a) for p, a, _ in out[:max_tips]]


def _sub_path(path, ua, ub):
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
    L = max(d[-1], 1e-6)
    u = np.linspace(ua * L, ub * L, max(2, int((ub - ua) * len(path)) + 1))
    return np.stack([np.interp(u, d, path[:, 0]), np.interp(u, d, path[:, 1])], 1)


def _jag(path, rng, rough, ps, pitch=0.0):
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
    m = max(2, int(d[-1] / max(10 * ps, pitch)) + 1)
    u = np.linspace(0, d[-1], m)
    s = np.stack([np.interp(u, d, path[:, 0]), np.interp(u, d, path[:, 1])], 1)
    q = _midpoints(np.stack([s[:-1], s[1:]], 1), rng.normal(size=(len(s) - 1, 7)), rough, 3)
    return np.concatenate([s[:1], q[:, 1:].reshape(-1, 2)])


def _forks(out_i, pts, rng, nk, w, z, R, rel, depth=1, fine=None, val=0.8):
    L = float(np.hypot(*(pts[-1] - pts[0])))
    for _ in range(nk):
        if len(pts) < 4:
            return
        j = int(rng.integers(len(pts) // 6, max(len(pts) // 6 + 1, len(pts) - 2)))
        d = pts[min(j + 2, len(pts) - 1)] - pts[j]
        ang = math.atan2(d[1], d[0]) + rng.choice([-1, 1]) * rng.uniform(0.3, 0.9)
        ln = max(L, 20.0) * rng.uniform(0.5, 1.0) * rel
        br = bolt_path(pts[j], pts[j] + ln * np.array([math.cos(ang), math.sin(ang)]), rng, R * 1.2, 5, fine)
        out_i.append((br, w * 0.5, np.linspace(val, 0.0, len(br)), z))
        if depth > 1 and rng.random() < 0.6:
            _forks(out_i, br, rng, int(rng.integers(1, 3)), w * 0.8, z, R, 0.7, depth - 1, fine, val * 0.85)


def _zigzag(pts, rng, amp, ps):
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    if amp <= 0 or d[-1] < 1e-3:
        return pts
    u = np.linspace(0, d[-1], max(2, int(d[-1] / (2 * ps)) + 1))
    s = np.stack([np.interp(u, d, pts[:, 0]), np.interp(u, d, pts[:, 1])], 1)
    t = np.gradient(s, axis=0)
    nrm = np.stack([-t[:, 1], t[:, 0]], 1) / np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-6)[:, None]
    off = np.zeros(len(u))
    for cell, a in ((17 * ps, amp), (6 * ps, amp * 0.34)):
        k = int(d[-1] / cell) + 2
        off += np.interp(u, np.arange(k) * cell, rng.uniform(-a, a, k))
    return s + nrm * off[:, None]


def _down_forks(main, rng, nk, rough, depth, fine, val=0.8):
    out = []
    way = main[-1] - main[0]
    H = float(np.hypot(*way))
    base = math.atan2(way[1], way[0])
    for _ in range(nk):
        j = int(rng.integers(len(main) // 10, max(len(main) // 10 + 1, int(len(main) * 0.75))))
        left = 1.0 - j / len(main)
        ang = base + rng.choice([-1, 1]) * math.radians(rng.uniform(15, 45))
        ln = H * left * rng.uniform(0.25, 0.6)
        br = bolt_path(main[j], main[j] + ln * np.array([math.cos(ang), math.sin(ang)]), rng, rough * 1.1, 5, fine)
        out.append((br, 0.5, np.linspace(val, 0.0, len(br)), 0.0))
        if depth > 1 and rng.random() < 0.6:
            for br2 in _down_forks(br, rng, int(rng.integers(1, 3)), rough, depth - 1, fine, val * 0.8):
                out.append(br2)
    return out


def _strikes(P, em, seed, out, tgt, ps):
    n, fps, H = em.n, em.fps, em.H
    L, dec = max(P["strike_leader"], 1e-3), max(P["strike_decay"], 1e-3)
    k3 = math.log(3.0) / dec
    fine = P["fine_rough"] if P["fine_rough"] > 0 else None
    for e, tb in enumerate(burst_times(P, n, fps)):
        rng = np.random.default_rng(seed * 7919 + 104729 * (e + 1))
        i0 = min(max(int(round(tb * fps)), 0), n - 1)
        side = rng.uniform(-1.0, 1.0) * P["strike_spread"] * ps
        gaps = [P["strike_gap"] * float(np.clip(math.exp(rng.normal(0.0, 0.6)), 0.15, 5.0))
                for _ in range(max(0, int(P["strike_strokes"]) - 1))]
        t_st = [tb] + list(tb + np.cumsum(gaps))
        amp = [1.0] + [rng.uniform(0.55, 0.9) for _ in gaps]
        hold_from = t_st[-2] if len(t_st) > 1 and P["strike_hold"] > 0 else None
        flares = rng.uniform(0.0, max(P["strike_hold"], 1e-6), int(rng.integers(2, 5))) if hold_from is not None else []
        new_ground = len(t_st) > 1 and rng.random() < P["strike_new_ground"]
        t_last = t_st[-1] + 6 * dec + (P["strike_hold"] if hold_from is not None else 0.0)
        chan = None
        for i in range(max(0, int(math.floor((tb - L) * fps)) - 1), min(n, int(math.ceil(t_last * fps)) + 2)):
            t = i / fps
            lo = t - 1.0 / fps
            if t < tb - L - 1e-9 or lo > t_last + 1e-9:
                continue
            if chan is None:
                a = em.a[i0] + [side, 0.0]
                b = tgt[i0] if tgt is not None else (em.b[i0] if em.b is not None else None)
                if b is None or np.hypot(*(b - a)) < 2.0:
                    top = -0.04 * H
                    hgt = max(a[1] - top, 0.2 * H)
                    b = np.array([a[0] + rng.choice([-1, 1]) * rng.uniform(0.3, 1.0) * P["strike_lean"] * hgt, a[1] - hgt])
                main = bolt_path(b, a, rng, P["roughness"], 7, fine)
                forks = _down_forks(main, rng, int(P["branches"]), P["roughness"], int(P["fork_depth"]), fine)
                ln = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(main, axis=0).T))])
                second = main
                if new_ground:
                    j = int(len(main) * rng.uniform(0.3, 0.6))
                    hh = float(np.hypot(*(main[-1] - main[0])))
                    g2 = a + [rng.choice([-1, 1]) * rng.uniform(0.1, 0.3) * hh, 0.0]
                    second = np.concatenate([main[:j], bolt_path(main[j], g2, rng, P["roughness"], 6, fine)[1:]])
                up = None
                if P["strike_streamer"] > 0:
                    s_len = P["strike_streamer"] * ps
                    up = bolt_path(a, a + [rng.uniform(-0.3, 0.3) * s_len, -s_len], rng, P["roughness"] * 2, 4, fine)
                chan = (main, forks, ln / max(ln[-1], 1e-6), second, up)
            main, forks, u, second, up = chan
            w = P["width"] * ps
            z = em.z[min(i, n - 1)]
            if t < tb - 1e-9:
                g = (t - (tb - L)) / L
                keep = max(2, int(np.searchsorted(u, g)))
                out[i].append((main[:keep], w * 0.45, np.full(keep, 0.3), z))
                for br, bw, op, _ in forks:
                    j = int(np.argmin(np.hypot(*(main - br[0]).T)))
                    if j < keep:
                        kk = max(2, int(len(br) * min(1.0, (keep - j) / max(len(main) * 0.25, 1.0))))
                        out[i].append((br[:kk], w * 0.3, op[:kk] * 0.3, z))
                if up is not None and t + 1.0 / fps >= tb - 1e-9:
                    out[i].append((up, w * 0.4, np.linspace(0.45, 0.1, len(up)), z))
                continue
            light = [0.0] * len(t_st)
            for k, (ts, am) in enumerate(zip(t_st, amp)):
                if ts > t + 1e-9:
                    continue
                if ts > lo + 1e-9:
                    light[k] = am
                else:
                    x0, x1 = lo - ts, t - ts
                    light[k] = am * (math.exp(-k3 * x0) - math.exp(-k3 * x1)) / (k3 * (x1 - x0))
            hold = 0.0
            if hold_from is not None and hold_from <= t and lo <= hold_from + P["strike_hold"]:
                hold = P["strike_hold_level"]
                for f in flares:
                    if lo <= hold_from + f <= t:
                        hold = max(hold, min(1.0, P["strike_hold_level"] * 2.0))
            first = light[0]
            rest = max(light[1:] + [0.0])
            for path_, val in ((main, max(first, hold if not new_ground else 0.0, rest if not new_ground else 0.0)),
                               (second, max(rest, hold) if new_ground else 0.0)):
                if val >= 0.04:
                    out[i].append((path_, w * (0.6 + 0.4 * val), np.full(len(path_), min(1.0, val)), z))
            if first > 0.04:
                for br, bw, op, _ in forks:
                    out[i].append((br, w * 0.5, op * first, z))


def make_paths(P, em, seed, target=None):
    n, fps, W, H, cam = em.n, em.fps, em.W, em.H, em.cam
    em.crack_table = None
    ps = min(W, H) / REF * float(P.get("scale", 1.0))
    out = [[] for _ in range(n)]
    kind = P["path"]
    t0 = P["start"]
    t1 = P["end"] if P["end"] > 0 else 1e9
    tgt = None if target is None else Emitter._path(target, n, None)
    if kind == "bolt":
        rr = max(1, int(P["reroll_frames"]))
        for i in range(n):
            t = i / fps
            if not (t0 <= t <= t1):
                continue
            rng = np.random.default_rng(seed * 7919 + i // rr)
            a = em.a[i]
            b = tgt[i] if tgt is not None else (em.b[i] if em.b is not None else None)
            if b is None or np.hypot(*(b - a)) < 2.0:
                b = _ground_point(em, i, a, 0.35 * H)
            main = bolt_path(a, b, rng, P["roughness"], 6, P["fine_rough"] if P["fine_rough"] > 0 else None)
            grow = 1.0 if P["grow_seconds"] <= 0 else np.clip((t - t0) / P["grow_seconds"], 0, 1)
            flick = 0.65 + 0.35 * rng.uniform()
            L = np.hypot(*(b - a))
            keep = max(2, int(len(main) * grow))
            out[i].append((main[:keep], P["width"] * ps, np.full(keep, flick), em.z[i]))
            for _ in range(int(P["branches"])):
                j = rng.integers(len(main) // 6, max(len(main) // 6 + 1, keep - 1))
                d = main[min(j + 2, len(main) - 1)] - main[j]
                ang = math.atan2(d[1], d[0]) + rng.choice([-1, 1]) * rng.uniform(0.3, 0.8)
                ln = L * rng.uniform(0.15, 0.35)
                br = bolt_path(main[j], main[j] + ln * np.array([math.cos(ang), math.sin(ang)]), rng, P["roughness"] * 1.2, 5)
                out[i].append((br, P["width"] * ps * 0.5, np.linspace(flick, 0.0, len(br)), em.z[i]))
    elif kind == "strike":
        _strikes(P, em, seed, out, tgt, ps)
    elif kind == "climb":
        if em.masks is None:
            raise ValueError("a climbing path needs the object mask (the thin parts it climbs): click the object in Position and track it")
        rr = max(1, int(P["reroll_frames"]))
        cf = max(2.0, P["climb_seconds"] * fps)
        R = P["roughness"]
        fine = P["fine_rough"] if P["fine_rough"] > 0 else None
        w = P["width"] * ps
        memo = em.memo if em.memo is not None else {}
        last = None
        for i in range(n):
            t = i / fps
            if not (t0 <= t <= t1):
                continue
            mk = em.masks[min(i, len(em.masks) - 1)]
            sx, sy = W / mk.shape[1], H / mk.shape[0]
            hub = em.a[i] / [sx, sy] if (em.has_a and P["climb_from"] == "center") else None
            key = ("climb", i, len(em.masks), mk.shape, None if hub is None else hub.tobytes())
            at = (mk.__array_interface__["data"][0], mk.strides, key[4])
            if key in memo:
                parts = memo[key]
            elif last is not None and last[0] == at:
                parts = memo[key] = last[1]
            else:
                parts = memo[key] = climb_parts(mk > 0.5, hub)
            last = (at, parts)
            if not parts:
                continue
            rng = np.random.default_rng(seed * 7919 + i // rr)
            grow = 1.0 if P["grow_seconds"] <= 0 else np.clip((t - t0) / P["grow_seconds"], 0, 1)
            tops = []
            for path, ang in parts:
                path = path * [sx, sy]
                L = float(np.hypot(*np.diff(path, axis=0).T).sum())
                f = (((t - t0) * fps / cf + (ang / (2 * np.pi) * 7.3) % 1.0) % 1.0) * 1.35 * grow
                ua, ub = max(f - 0.5, 0.0), min(f, 1.0)
                if (ub - ua) * L > 4 * ps:
                    seg = _sub_path(path, ua, ub)
                    sh = 1.0 if P["climb_short"] <= 0 else min(1.0, (ub - ua) * L / (P["climb_short"] * ps))
                    for _ in range(1 + int(rng.random() < 0.35)):
                        pts = _jag(seg, rng, rng.uniform(0.03, 0.08) * R / 0.22 * P["climb_rough"], ps, P["climb_pitch"] * L)
                        pts = _zigzag(pts, rng, P["climb_zigzag"] * ps, ps)
                        lum = (0.65 + 0.35 * rng.uniform()) * (0.3 + 0.7 * sh)
                        out[i].append((pts, w, lum * np.linspace(1.0 - P["climb_head"], 1.0, len(pts)), em.z[i]))
                        _forks(out[i], pts, rng, int(rng.integers(0, int(P["branches"]) + 1) * sh), w, em.z[i], R, 0.35,
                               int(P["fork_depth"]), fine)
                top = f >= 0.95
                u = path[-1] - path[max(0, len(path) - 1 - max(6, len(path) // 6))]
                u = u / max(float(np.hypot(*u)), 1e-6)
                if top and P["climb_gap"] > 0:
                    dd = np.arange(2.0, P["climb_gap"], 2.0) * ps
                    gx = np.clip(((path[-1, 0] + u[0] * dd) / sx).astype(int), 0, mk.shape[1] - 1)
                    gy = np.clip(((path[-1, 1] + u[1] * dd) / sy).astype(int), 0, mk.shape[0] - 1)
                    inside = mk[gy, gx] > 0.5
                    top = not ((~inside).any() and inside[int(np.argmax(~inside)):].any())
                if top and em.depth:
                    bx = path[-1, 0] + u[0] * np.array([6.0, 10.0, 14.0]) * ps
                    by = path[-1, 1] + u[1] * np.array([6.0, 10.0, 14.0]) * ps
                    zt = float(em.depth.at(i, path[-3:, 0], path[-3:, 1]).max())
                    top = not (float(em.depth.at(i, bx, by).max()) > zt + P["climb_cover"])
                tops.append((path[-1], ang, top, L))
            tops.sort(key=lambda q: q[1])
            for k, (tip, ang, top, L) in enumerate(tops):
                if not top:
                    continue
                nb = [tops[j][0] for j in (k - 1, k + 1)
                      if 0 <= j < len(tops) and 12 * ps < np.hypot(*(tops[j][0] - tip)) < max(140 * ps, 0.6 * L)]
                if nb and rng.random() < 0.7:
                    q, rough = nb[int(rng.integers(len(nb)))], rng.uniform(0.1, 0.2)
                else:
                    a2 = ang + rng.uniform(-0.6, 0.6)
                    q = tip + rng.uniform(0.15, 0.4) * max(L, 40 * ps) * np.array([math.cos(a2), math.sin(a2)])
                    rough = rng.uniform(0.12, 0.22)
                pts = bolt_path(tip, q, rng, rough * R / 0.22, 6, fine)
                out[i].append((pts, w, np.linspace(1.0, 0.6, len(pts)), em.z[i]))
                _forks(out[i], pts, rng, int(rng.integers(1, int(P["branches"]) + 2)), w, em.z[i], R, 0.4, int(P["fork_depth"]), fine)
    elif kind == "crack":
        rng = np.random.default_rng(seed)
        dd = em.depth.d[0] if em.depth else None
        if dd is not None:
            dsx, dsy, dh, dw = em.depth.sx, em.depth.sy, dd.shape[0] - 1, dd.shape[1] - 1
            zat = lambda px, py: dd[min(max(int(py * dsy), 0), dh), min(max(int(px * dsx), 0), dw)]
        segs = []
        tp = float(P.get("crack_taper", 0.0) or 0.0)
        x0, y0 = cam.to_world(em.a[0, 0], em.a[0, 1], 0) if tgt is None else (em.a[0, 0], em.a[0, 1])
        starts = [(x0, y0)]
        ns = int(P.get("crack_seeds", 1))
        if ns > 1:
            pos, _, _ = em.sample(0.0, ns - 1, rng.uniform(0, 1, (ns - 1, 5)))
            starts += [tuple(cam.to_world(px, py, 0)) for px, py in pos]
        tips = collections.deque()
        for sx, sy in starts:
            a0 = rng.uniform(0, 2 * np.pi)
            tips += [(float(sx), float(sy), a0 + k * 2 * np.pi / 3, 0.0, 0) for k in range(3)]
        step = P["crack_step"] * ps
        zr = em.z[0] if em.depth else 1.0
        while tips and len(segs) < 6000 * min(len(starts), 3):
            x, y, a, ln, g = tips.popleft()
            if ln > P["crack_length"] * ps * (0.6 ** g):
                continue
            sc, zi = 1.0, 0.0
            if dd is not None:
                zi = zat(x, y)
                sc = float(np.clip(zi / max(zr, 1e-3), 0.25, 3.0))
            a2 = a + rng.normal() * P["crack_turn"] + (rng.choice([-1, 1]) * rng.uniform(0.4, 0.8) if rng.uniform() < 0.08 else 0.0)
            nx, ny = x + math.cos(a2) * step * sc, y + math.sin(a2) * step * sc * 0.6
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if dd is not None:
                if abs(zat(nx, ny) - zi) > 0.03 * max(sc, 1.0):
                    continue
            born = t0 + (ln + step * sc) / (P["crack_speed"] * ps)
            wf = 0.75 ** g
            if tp > 0:
                wf *= (1 + 3.0 * tp * max(0.0, 1 - ln / (P["crack_length"] * ps * (0.6 ** g)))) * sc
            segs.append((x, y, nx, ny, born, wf, zi))
            tips.append((nx, ny, a2, ln + step * sc, g))
            if rng.uniform() < P["crack_branch"] and g < 3:
                sgn = rng.choice([-1, 1])
                ang = P["crack_angle"] + P["crack_angle_var"] * (2 * rng.uniform() - 1)
                tips.append((nx, ny, a2 + sgn * ang, ln + step * sc, g + 1))
                if P["crack_pairs"] > 0 and rng.uniform() < P["crack_pairs"]:
                    tips.append((nx, ny, a2 - sgn * ang, ln + step * sc, g + 1))
        segs = np.array(segs, np.float64).reshape(-1, 7)
        f0 = np.searchsorted(np.arange(n) / fps, segs[:, 4], side="left")
        keep = f0 < n
        em.crack_table = np.stack([f0[keep], P["width"] * ps * (np.round(segs[keep, 5] * 8) / 8), np.full(int(keep.sum()), P["opacity"]),
                                   segs[keep, 0], segs[keep, 1], segs[keep, 2], segs[keep, 3]], 1)
        for i in range(n):
            t = i / fps
            s = segs[segs[:, 4] <= t]
            if not len(s):
                continue
            ax, ay = cam.to_screen(s[:, 0], s[:, 1], i)
            bx, by = cam.to_screen(s[:, 2], s[:, 3], i)
            wq = np.round(s[:, 5] * 8) / 8
            for wv in np.unique(wq):
                g = wq == wv
                w = P["width"] * ps * wv
                out[i].append((np.stack([np.stack([ax[g], ay[g]], 1), np.stack([bx[g], by[g]], 1)], 1), w,
                               np.full(int(g.sum()), P["opacity"]), s[g, 6] if em.depth else em.z[i]))
    elif kind == "ring":
        for i in range(n):
            t = i / fps
            age = (t - t0) / max(P["life"], 1e-3)
            if not (0 <= age <= 1):
                continue
            r = P["ring_speed"] * ps * (t - t0)
            ang = np.linspace(0, 2 * np.pi, 96)
            c = em.a[i]
            pts = np.stack([c[0] + np.cos(ang) * r, c[1] + np.sin(ang) * r * P["ring_squash"]], 1)
            out[i].append((pts, P["width"] * ps * (1 + 2 * age), np.full(len(pts), P["opacity"] * (1 - age) ** 1.5), em.z[i]))
    return out


def _draw_paths(sp, paths_i, raster, i, style, P, depth_vis=None):
    k = raster.scale(i)
    col = [1, 1, 1] if style != "seed" else (gradient(P["colors"], np.array([0.0]))[0] * P["glow"])
    for pts, w, a, z in paths_i:
        if pts.ndim == 3:
            x0, y0 = raster.map(i, pts[:, 0, 0], pts[:, 0, 1])
            x1, y1 = raster.map(i, pts[:, 1, 0], pts[:, 1, 1])
            sig = 0.8 if style != "seed" else max(0.5, 0.5 * w * k)
            sp.lines(x0, y0, x1, y1, sig, col, a)
            continue
        x, y = raster.map(i, pts[:, 0], pts[:, 1])
        if style == "seed":
            sp.polyline(np.stack([x, y], 1), max(0.5, 0.5 * w * k), col, a)
            sp.polyline(np.stack([x, y], 1), max(2.0, 2.5 * w * k), col, 0.1 * a)
        else:
            sp.polyline(np.stack([x, y], 1), 0.9, [1, 1, 1], a)



def frame_alpha(P, rec, i, a, raster, edge, premask=True, edge_raster=None):
    al = rec["alpha"][i, a].astype(np.float64)
    if premask:
        al = al * rec["vis"][i, a]
    er = edge_raster or raster
    ex, ey = er.map(i, rec["x"][i, a].astype(np.float64), rec["y"][i, a].astype(np.float64))
    return al * er.edge(ex, ey, edge)


def stamp_sprites(img, sprite, rx, ry, rs, al, age, rot, tint=None, optical=False, fidx=None, aspect=False, occ=None, gain=1.0,
                  blur=None):
    Hh, Ww = img.shape[:2]
    acc = np.zeros_like(img)
    nf = len(sprite)
    tints = None
    if tint is not None and np.ndim(tint) == 2:
        tints, tint = np.asarray(tint, np.float32), None
    for j, (x, y, r, a, ag, ro) in enumerate(zip(rx, ry, rs, al, age, rot)):
        d = int(max(3, round(2 * r)))
        spr = sprite[int(fidx[j]) % nf] if fidx is not None else sprite[min(int(ag * nf), nf - 1)]
        dh = int(max(3, round(d * spr.shape[0] / spr.shape[1]))) if aspect else d
        if x + d < 0 or y + dh < 0 or x - d >= Ww or y - dh >= Hh:
            continue
        s = cv2.resize(spr, (d, dh), interpolation=cv2.INTER_AREA if d < spr.shape[1] else cv2.INTER_LINEAR)
        if ro:
            m = cv2.getRotationMatrix2D((d / 2, dh / 2), float(np.degrees(ro)), 1.0)
            s = cv2.warpAffine(s, m, (d, dh), flags=cv2.INTER_LINEAR, borderValue=0)
        x0, y0 = int(round(x - d / 2)), int(round(y - dh / 2))
        if blur is not None and blur[j] >= 0.5:
            pb = int(math.ceil(2.5 * blur[j]))
            s = cv2.GaussianBlur(cv2.copyMakeBorder(s, pb, pb, pb, pb, cv2.BORDER_CONSTANT, value=0), (0, 0), float(blur[j]))
            x0, y0, d, dh = x0 - pb, y0 - pb, d + 2 * pb, dh + 2 * pb
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(Ww, x0 + d), min(Hh, y0 + dh)
        if xa >= xb or ya >= yb:
            continue
        piece = s[ya - y0:yb - y0, xa - x0:xb - x0]
        alpha = piece[..., 3:4] * a
        if occ is not None:
            alpha = alpha * np.clip((occ[1][j] - occ[0][ya:yb, xa:xb]) / occ[2] + 1.0, 0, 1)[..., None]
        if tints is not None:
            rgb = tints[j][None, None] * piece[..., :3].mean(-1, keepdims=True)
        else:
            rgb = piece[..., :3] if tint is None else np.asarray(tint, np.float32)[None, None] * piece[..., :3].mean(-1, keepdims=True)
        acc[ya:yb, xa:xb, :3] += rgb * (alpha * gain)
        acc[ya:yb, xa:xb, 3:4] += alpha
    if optical:
        dens = acc[..., 3:4].copy()
        acc[..., 3:4] = 1 - np.exp(-1.6 * dens)
        acc[..., :3] *= acc[..., 3:4] / np.maximum(dens, 1e-6)
    else:
        over = np.maximum(acc[..., 3:4], 1.0)
        acc[..., :3] /= over
        acc[..., 3] = np.clip(acc[..., 3], 0, 1)
    img[..., :3] = img[..., :3] * (1 - acc[..., 3:4]) + acc[..., :3]
    img[..., 3] = 1 - (1 - img[..., 3]) * (1 - acc[..., 3])
    return img


def wisp_sprite(size=96, frames=8, seed=7):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    r = np.hypot(xx - size / 2 + 0.5, yy - size / 2 + 0.5) / (size / 2)
    fall = np.clip(1.0 - r, 0, 1) ** 1.6
    out = []
    base = [rng.standard_normal((size * 2, size * 2)).astype(np.float32) for _ in range(4)]
    for f in range(frames):
        acc = np.zeros((size, size), np.float32)
        for o, b in enumerate(base):
            sig = size / (3.0 * 2 ** o)
            sh = int(round(f * size / (frames * (1.5 + o))))
            fld = cv2.GaussianBlur(b, (0, 0), sig)[sh:sh + size, sh // 2:sh // 2 + size]
            acc += fld / (fld.std() + 1e-6) * 0.55 ** o
        acc = (acc - acc.min()) / (np.ptp(acc) + 1e-6)
        a = np.clip((acc - 0.25) / 0.6, 0, 1) ** 1.3 * fall
        out.append(np.concatenate([np.ones((size, size, 3), np.float32), a[..., None]], -1))
    return np.stack(out)


def render_frames(P, rec, em, paths, raster, style, premask=True, edge=0.08, edge_raster=None, frames=None, sprite=None,
                  optical=False):
    n, fps = em.n, em.fps
    zmax = float(np.nanmax(rec["z"])) if rec["z"].size else 1.0
    out = np.zeros((n, raster.h, raster.w, 4), np.float32)
    wisp = sprite is None and style == "seed" and P["sprite"] == "wisp"
    if wisp:
        sprite = wisp_sprite()
    own = sprite is not None and style == "seed"
    for i in (range(n) if frames is None else frames):
        interrupted()
        sp = Splats()
        a = np.nonzero(np.isfinite(rec["x"][i]))[0] if rec["x"].size else np.zeros(0, np.int64)
        stamp = None
        if len(a):
            k = raster.scale(i)
            rx, ry = raster.map(i, rec["x"][i, a].astype(np.float64), rec["y"][i, a].astype(np.float64))
            rs = rec["size"][i, a] * k
            al = frame_alpha(P, rec, i, a, raster, edge, premask, edge_raster)
            coc = None
            if style == "seed" and P.get("dof", 0) > 0:
                foc = P["focus"] if P.get("focus", -1) >= 0 else float(em.zref)
                coc = P["dof"] * min(em.W, em.H) / REF * P.get("scale", 1.0) * k * np.abs(rec["zd" if "zd" in rec else "z"][i, a] - foc)
                if not own or wisp:
                    rs_e = np.sqrt(rs ** 2 + coc ** 2)
                    al = al * (rs / np.maximum(rs_e, 1e-6)) ** 2
                    rs = rs_e
                    coc = None
            if P.get("blob", 0) > 0 and P.get("blob_life", 0) > 0 and not own:
                young = np.clip((P["blob_life"] - rec["age"][i, a]) / (0.5 * P["blob_life"]), 0, 1)
                free = (al * (1 - young), al * young)
                al = free[1]
            else:
                free = None
            vis = al > 1e-3
            a2 = a[vis]
            if own:
                one = P["colors"][0][1] == P["colors"][-1][1] and P.get("_tinted", False)
                tint = particle_colors(P, rec, i, a2) * P["glow"] if wisp else (P["colors"][0][1] if one else None)
                stamp = (rx[vis], ry[vis], 1.6 * rs[vis] if wisp else rs[vis], al[vis], rec["age"][i, a2], rec["rot"][i, a2], tint)
                ex = {"aspect": bool(P.get("sprite_aspect", 0)), "gain": float(P.get("sprite_gain", 1.0))}
                if coc is not None:
                    ex["blur"] = coc[vis] / 2
                if P.get("sprite_play") == "loop" and "foff" in rec:
                    ex["fidx"] = np.floor(i - rec["born"][a2] * fps + rec["foff"][a2] + 1e-6).astype(np.int64)
                if P.get("sprite_occlude", 0) and em.depth and raster.window is None:
                    dd = cv2.resize(em.depth.d[min(i, len(em.depth.d) - 1)], (raster.w, raster.h), interpolation=cv2.INTER_LINEAR)
                    ex["occ"] = (dd, rec["z"][i, a2], max(P["depth_softness"], 1e-4))
                stamp = stamp + (ex,)
            else:
                draw_particles(sp, P, rec, i, a2, rx[vis], ry[vis], rs[vis], al[vis], style, fps, k, zmax)
            draw_trails(sp, dict(P, _premask=premask), rec, i, a2, raster, style, k)
        if paths is not None and paths[i]:
            _draw_paths(sp, paths[i], raster, i, style, P)
        out[i] = sp.render(raster.h, raster.w)
        if stamp is not None:
            out[i] = stamp_sprites(out[i], sprite, *stamp[:6], tint=stamp[6], optical=optical, **(stamp[7] if len(stamp) > 7 else {}))
        if P.get("blob", 0) > 0:
            out[i] = blob_merge(out[i], P["blob"] * min(em.W, em.H) / REF * P.get("scale", 1.0) * raster.scale(i), P["blob_choke"], P["blob_soft"],
                                P["opacity"], P["blob_fill"])
        if len(a) and free is not None and not own:
            v2 = free[0] > 1e-3
            if v2.any():
                sp2 = Splats()
                draw_particles(sp2, P, rec, i, a[v2], rx[v2], ry[v2], rs[v2], free[0][v2], style, fps, k, zmax)
                o2 = sp2.render(raster.h, raster.w)
                out[i] = out[i] + o2 * (1 - out[i][..., 3:4]) if P["blend"] == "over" else out[i] + o2
    return out


def blob_merge(img, sigma, choke, soft, opacity=1.0, fill=1.0):
    b = cv2.GaussianBlur(img, (0, 0), max(sigma, 0.3))
    a = b[..., 3:4]
    op = max(opacity, 1e-3)
    x = np.clip((a / op - (choke - soft)) / max(2 * soft, 1e-3), 0.0, 1.0)
    a2 = x * x * (3 - 2 * x) * (fill * op + (1 - fill) * np.clip(a, 0.0, 1.0))
    return np.concatenate([b[..., :3] / np.maximum(a, 1e-3) * a2, a2], -1).astype(np.float32)


def snap_to_edges(h, img, r):
    hb = (h > 0.5).astype(np.uint8)
    band = (((h > 0.02) & (h < 0.98)) | (cv2.morphologyEx(hb, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0)).astype(np.uint8)
    if not band.any():
        return h
    ys, xs = np.nonzero(band)
    g = 3 * r + 2
    y0, y1, x0, x1 = max(ys.min() - g, 0), min(ys.max() + g + 1, h.shape[0]), max(xs.min() - g, 0), min(xs.max() + g + 1, h.shape[1])
    if (y1 - y0) * (x1 - x0) < 0.8 * h.size:
        out = h.copy()
        out[y0:y1, x0:x1] = snap_to_edges(h[y0:y1, x0:x1], img[y0:y1, x0:x1], r)
        return out
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    band = cv2.dilate(band, ker) > 0
    k = (4 * r + 1, 4 * r + 1)
    m0, m1 = (h < 0.02).astype(np.float32), (h > 0.98).astype(np.float32)
    w0, w1 = cv2.boxFilter(m0, -1, k), cv2.boxFilter(m1, -1, k)
    c0 = cv2.boxFilter(img * m0[..., None], -1, k) / np.maximum(w0, 1e-6)[..., None]
    c1 = cv2.boxFilter(img * m1[..., None], -1, k) / np.maximum(w1, 1e-6)[..., None]
    d0 = np.linalg.norm(img - c0, axis=-1)
    d1 = np.linalg.norm(img - c1, axis=-1)
    t = cv2.GaussianBlur(d0 / (d0 + d1 + 1e-6), (0, 0), 1.0)
    conf = np.clip(np.linalg.norm(c0 - c1, axis=-1) / 0.12, 0, 1) * (w0 > 0.02) * (w1 > 0.02)
    hn = conf * t + (1 - conf) * h
    return np.where(band, hn, h).astype(np.float32)


def surface_hold(paths_i, d, H, W, soft):
    items = [(np.round(pts).astype(np.int64), max(3, int(round(2 * w)) + 2), np.asarray(z, np.float64))
             for pts, w, a, z in paths_i if pts.ndim == 3 and np.ndim(z) == 1 and len(z)]
    if not items:
        return None
    sp = max(soft, 0.05)
    q = sp / 64.0
    allp = np.concatenate([p.reshape(-1, 2) for p, _, _ in items])
    g = max(t for _, t, _ in items)
    x0, y0 = max(int(allp[:, 0].min()) - g, 0), max(int(allp[:, 1].min()) - g, 0)
    x1, y1 = min(int(allp[:, 0].max()) + g + 1, W), min(int(allp[:, 1].max()) + g + 1, H)
    if x0 >= x1 or y0 >= y1:
        return None
    zi = np.full((y1 - y0, x1 - x0), np.nan, np.float32)
    p = (np.concatenate([p for p, _, _ in items]) - [x0, y0]).astype(np.int32)
    tk = np.concatenate([np.full(len(p), t) for p, t, _ in items])
    zk = np.concatenate([np.round(z / q).astype(np.int64) for _, _, z in items])
    for v, t in sorted(set(zip(zk.tolist(), tk.tolist()))):
        cv2.polylines(zi, p[(zk == v) & (tk == t)], False, float(v * q), t)
    m = np.isfinite(zi)
    if not m.any():
        return None
    out = np.ones((H, W), np.float32)
    out[y0:y1, x0:x1] = np.where(m, np.clip((np.nan_to_num(zi) + 0.05 - d[y0:y1, x0:x1]) / sp + 1.0, 0, 1), 1.0)
    return out


def masks_from(alpha_plate, rec, em, P, premask=True, grow=0.02, guide=None, paths=None):
    n, H, W = alpha_plate.shape[:3]
    r = max(2, int(grow * min(W, H)))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    region = np.zeros((n, H, W), np.float32)
    hold = np.ones((n, H, W), np.float32)
    soft = max(P["depth_softness"], 1e-4)
    for i in range(n):
        if getattr(em, "kind", None) == "whole frame":
            region[i] = 1.0
        else:
            m = (alpha_plate[i] > 0.02).astype(np.uint8)
            region[i] = cv2.GaussianBlur(cv2.dilate(m, ker).astype(np.float32), (0, 0), r / 2)
        if not em.depth:
            continue
        d = cv2.resize(em.depth.d[min(i, len(em.depth.d) - 1)], (W, H), interpolation=cv2.INTER_LINEAR)
        hs = surface_hold(paths[i], d, H, W, soft) if paths is not None and paths[i] else None
        a = np.nonzero(np.isfinite(rec["x"][i]) & (rec["alpha"][i] > 0.02))[0] if rec["x"].size else np.zeros(0, np.int64)
        if not len(a) and hs is None:
            continue
        h = np.ones((H, W), np.float32) if hs is None else hs
        if len(a):
            rad = float(np.clip(np.median(rec["size"][i, a]) * 1.5 + 2, 2, r))
            pd = int(math.ceil(6 * rad)) + 1
            xi = np.floor(rec["x"][i, a]).astype(np.int64) + pd
            yi = np.floor(rec["y"][i, a]).astype(np.int64) + pd
            inb = (xi >= 0) & (yi >= 0) & (xi < W + 2 * pd) & (yi < H + 2 * pd)
            wgt = rec["alpha"][i, a][inb].astype(np.float32)
            zs = np.zeros((H + 2 * pd, W + 2 * pd), np.float32)
            ws = np.zeros((H + 2 * pd, W + 2 * pd), np.float32)
            np.add.at(zs, (yi[inb], xi[inb]), rec["z"][i, a][inb].astype(np.float32) * wgt)
            np.add.at(ws, (yi[inb], xi[inb]), wgt)
            zs = cv2.GaussianBlur(zs, (0, 0), 2 * rad, borderType=cv2.BORDER_CONSTANT)[pd:pd + H, pd:pd + W]
            ws = cv2.GaussianBlur(ws, (0, 0), 2 * rad, borderType=cv2.BORDER_CONSTANT)[pd:pd + H, pd:pd + W]
            cover = ws > 1e-4 * max(float(ws.max()), 1e-9)
            zf = np.where(cover, zs / np.maximum(ws, 1e-12), 0.0)
            if getattr(em, "kind", None) == "whole frame":
                zw = rec["z"][i, a].astype(np.float64)
                ow = np.argsort(zw)
                cw = np.cumsum(rec["alpha"][i, a][ow].astype(np.float64))
                cw /= max(cw[-1], 1e-12)
                k = np.searchsorted(zw[ow], d.astype(np.float64) - soft)
                h = np.minimum(h, (1.0 - np.where(k > 0, cw[np.clip(k - 1, 0, len(cw) - 1)], 0.0)).astype(np.float32))
            else:
                h = np.minimum(h, np.where(cover, np.clip((zf - d) / soft + 1.0, 0, 1), 1.0).astype(np.float32))
        if guide is not None and h.min() < 0.99:
            g = guide[min(i, len(guide) - 1)][..., :3].astype(np.float32)
            g = cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA) if g.shape[:2] != (H, W) else g
            h = np.clip(snap_to_edges(h, g, max(2, int(round(0.006 * min(W, H))))), 0, 1)
        hold[i] = cv2.GaussianBlur(h, (0, 0), 1.5)
    return region, hold


def tracks_json(rec, raster, count, P, edge=0.08, min_frames=8):
    if count <= 0 or not rec["x"].size:
        return "[]", 0
    n, N = rec["x"].shape
    seen = np.zeros((n, N), bool)
    for i in range(n):
        a = np.nonzero(np.isfinite(rec["x"][i]))[0]
        if len(a):
            rx, ry = raster.map(i, rec["x"][i, a].astype(np.float64), rec["y"][i, a].astype(np.float64))
            al = rec["alpha"][i, a] * rec["vis"][i, a] * raster.edge(rx, ry, edge)
            seen[i, a] = (al > 0.2) & (rx >= 0) & (ry >= 0) & (rx < raster.w) & (ry < raster.h)
    good = np.nonzero(seen.sum(0) >= min_frames)[0]
    if not len(good):
        return "[]", 0
    good = good[np.argsort(rec["born"][good], kind="stable")]
    pick = good[np.unique(np.linspace(0, len(good) - 1, min(count, len(good))).round().astype(np.int64))]
    out = []
    for j in pick:
        fr = np.nonzero(np.isfinite(rec["x"][:, j]))[0]
        f0, f1 = fr[0], fr[-1]
        pts = []
        for i in range(f1 + 1):
            src = max(i, f0)
            x, y = raster.map(i, np.array([rec["x"][src, j]], np.float64), np.array([rec["y"][src, j]], np.float64))
            pts.append({"x": round(float(np.clip(x[0], 0, raster.w - 1)), 2), "y": round(float(np.clip(y[0], 0, raster.h - 1)), 2)})
        out.append(pts)
    return json.dumps(out), len(out)


def preview(plate, seed_plate, em, window=None, k=0.5):
    n = len(seed_plate)
    H, W = plate.shape[1:3]
    w, h = int(W * k), int(H * k)
    out = np.zeros((n, h, w, 3), np.float32)
    lw = max(1, int(round(min(w, h) / 360)))
    for i in range(n):
        pl = cv2.resize(plate[min(i, len(plate) - 1)][..., :3].astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
        sd = cv2.resize(seed_plate[i], (w, h), interpolation=cv2.INTER_AREA)
        img = pl * (1 - sd[..., 3:4]) + sd[..., :3]
        c = em.center[min(i, len(em.center) - 1)] * k
        cv2.circle(img, (int(c[0]), int(c[1])), 4 * lw, (1.0, 0.75, 0.1), lw, cv2.LINE_AA)
        if window is not None and "crop_origin_plate_px" in window:
            r = Raster(W, H, window)
            j = min(i, len(r.org) - 1)
            x0, y0 = r.org[j]
            x1, y1 = x0 + r.w / r.sc[j], y0 + r.h / r.sc[j]
            cv2.rectangle(img, (int(x0 * k), int(y0 * k)), (int(x1 * k), int(y1 * k)), (1.0, 1.0, 1.0), lw, cv2.LINE_AA)
        out[i] = np.clip(img, 0, 1)
    return out


def dither(img, rng, amount=1.0 / 255, lo=None, hi=None):
    img = np.asarray(img)
    out = np.empty(img.shape, np.result_type(img.dtype, np.float32))
    for i in (range(len(img)) if img.ndim == 4 else [Ellipsis]):
        f = img[i]
        out[i] = f + (rng.random(f.shape, dtype=np.float32) - rng.random(f.shape, dtype=np.float32)) * np.float32(amount)
        if lo is not None:
            np.clip(out[i], lo, hi, out=out[i])
    return out


def _lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((np.maximum(x, 0) + 0.055) / 1.055) ** 2.4)


def _srgb(x):
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.maximum(x, 0) ** (1 / 2.4) - 0.055)


def contrast_blend(ps, lp, detail=None):
    e = np.clip(lp.max(axis=-1, keepdims=True), 0, 1) if detail is None else np.clip(detail, 0, 1)
    lum = (ps * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1, keepdims=True)
    t = np.clip((lum - 0.35) / 0.45, 0, 1)
    wb = t * t * (3 - 2 * t)
    lighter = _srgb(_lin(ps) + lp)
    darker = ps + np.clip(e * 0.9, 0, 1) * (np.minimum(ps, lum * 0.92) * 0.62 - ps)
    return lighter * (1 - wb) + darker * wb


def streak_detail(lp, H, W):
    e = np.clip(lp.max(axis=-1), 0, 1).astype(np.float32)
    sg = max(1.5, 0.004 * min(H, W))
    return np.clip(e - cv2.GaussianBlur(e, (0, 0), sg), 0, 1)[..., None] * 1.6


def _groove_terms(a, sb, sr):
    b = cv2.GaussianBlur(a, (0, 0), sb)
    dy = np.zeros_like(b)
    dy[1:-1] = 0.5 * (b[2:] - b[:-2])
    return np.clip(-dy, 0, None) * (1 - a), cv2.GaussianBlur(a, (0, 0), sr)


def groove(img, a, relief, w=None, hold=None):
    H, W = a.shape
    w = 2.0 * min(H, W) / REF if w is None else max(float(w), 0.5)
    sl = max(0.5, 0.5 * w)
    sb, sr = max(1.0, 1.5 * w), 2.5 * max(1.5, 0.008 * min(H, W))
    L = 2 * int(math.ceil(4 * (sr + sl))) + 9
    yy = np.arange(L, dtype=np.float32)[:, None] - L // 2
    ref = np.repeat(0.9 * np.exp(-0.5 * (yy / sl) ** 2), 5, 1).astype(np.float32)
    lip_r, rim_r = _groove_terms(ref, sb, sr)
    lip, rim = _groove_terms(a.astype(np.float32), sb, sr)
    lip = np.clip(lip / max(float(lip_r.max()), 1e-9), 0, 1)
    rim = np.clip(rim / max(float(rim_r.max()), 1e-9), 0, 1)
    f = relief * (0.35 * lip - 0.4 * rim * (1 - a) * (1 - lip))
    if hold is not None:
        f = f * hold
    return img * (1 + f)[..., None]


HALO_GAIN = 9.0


def shell_light(masks, n, colour, amount, fps, seed=0, width=0.035, speed=0.12, gain=0.45):
    m0 = masks[0]
    H, W = m0.shape
    w = max(2.0, width * min(H, W))
    rng = np.random.default_rng(seed + 17)
    nz = []
    for sc in (1.5 * w, 0.6 * w):
        f = cv2.GaussianBlur(rng.standard_normal((2 * H, W)).astype(np.float32), (0, 0), sc)
        f = (f - f.mean()) / max(float(f.std()), 1e-6)
        nz.append(np.concatenate([f, f], 0))
    col = _lin(np.asarray(colour, np.float32).reshape(1, 1, 3))
    out = np.zeros((n, H, W, 3), np.float32)
    for i in range(n):
        m = (masks[min(i, len(masks) - 1)] > 0.5).astype(np.uint8)
        if not m.any():
            continue
        d = cv2.distanceTransform(1 - m, cv2.DIST_L2, 5)
        band = np.exp(-d / w) * (1 - cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.15 * w))
        t = i / max(fps, 1e-3)
        o1, o2 = int(t * speed * H) % (2 * H), int(t * speed * 1.7 * H) % (2 * H)
        wisp = 0.55 * nz[0][o1:o1 + H] + 0.45 * nz[1][o2:o2 + H]
        band = band * np.clip(0.75 + 0.6 * wisp, 0, 2.5)
        out[i] = band[..., None] * col * (amount * gain)
    return out


def direct_look(plate, seed, hold, mode, glow, rng, ambient=0.0, halo=0.0, relief=0.0, line_width=None, shell=None, bloom=1.0):
    n, H, W = seed.shape[:3]
    out = np.empty((n, H, W, 3), np.float32)
    lay = np.zeros((n, H, W, 3), np.float32)
    r = max(1.5, 0.008 * min(H, W))
    sh = 0.06 * min(H, W)
    for i in range(n):
        ps = plate[min(i, len(plate) - 1)][..., :3].astype(np.float32)
        hv = hold[min(i, len(hold) - 1)][..., None]
        a = np.clip(seed[i][..., 3:4] * hv, 0, 1)
        rgb = np.maximum(seed[i][..., :3], 0) * hv
        if mode == "over":
            if ambient > 0:
                lum = cv2.GaussianBlur(ps @ np.float32([0.2126, 0.7152, 0.0722]), (0, 0), 0.06 * min(H, W))[..., None]
                rgb = rgb * (1 - ambient + ambient * np.clip(0.35 + 0.65 * lum / 0.5, 0.35, 1.6))
            out[i] = ps * (1 - a) + np.minimum(rgb, a)
            if relief > 0 and a.max() > 1e-5:
                out[i] = groove(out[i], a[..., 0], relief, line_width, hv[..., 0])
            lay[i] = _lin(np.minimum(rgb, a))
            continue
        on = a[..., 0] > 1e-5
        em = np.zeros_like(rgb)
        em[on] = _lin(np.clip(rgb[on] / a[on], 0, 4)) * a[on]
        if mode.startswith("contrast"):
            lay[i] = em
            dt = streak_detail(em, H, W)
        else:
            lay[i] = em
            if bloom > 0:
                lay[i] = em + (cv2.GaussianBlur(em, (0, 0), r) * 0.5 + cv2.GaussianBlur(em, (0, 0), 4 * r) * 0.25) * (1 + 0.3 * glow) * bloom
            if halo > 0:
                lay[i] += cv2.GaussianBlur(em, (0, 0), sh) * (halo * HALO_GAIN)
            if shell is not None:
                lay[i] += shell[min(i, len(shell) - 1)] * hv
            on = lay[i].max(-1) > 1e-5
        out[i] = ps
        if on.any():
            out[i][on] = contrast_blend(ps[on], lay[i][on], dt[on]) if mode.startswith("contrast") else _srgb(_lin(ps[on]) + lay[i][on])
    return dither(out, rng, lo=0, hi=1).astype(np.float32, copy=False), lay

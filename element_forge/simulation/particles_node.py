import json
import threading
import time

import cv2
import numpy as np
import torch

from . import particles as pt

try:
    from comfy.model_management import throw_exception_if_processing_interrupted as _stop_check
except ImportError:
    _stop_check = None
LIVE = threading.local()


def _check():
    own = getattr(LIVE, "check", None)
    if own is not None:
        own()
    elif _stop_check is not None:
        _stop_check()


pt.interrupted = _check


def _frame_done(i, rec, st, used):
    own = getattr(LIVE, "on_frame", None)
    if own is not None:
        own(i, rec, st, used)


pt.frame_done = _frame_done


def _np(t):
    return t.detach().cpu().float().numpy() if torch.is_tensor(t) else np.asarray(t, np.float32)


def _mask3(m):
    a = _np(m)
    return a.reshape(-1, *a.shape[-2:])


def _hex_rgb(color):
    h = color.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        if len(h) != 6:
            raise ValueError
        return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        raise ValueError(f"color '{color}': give a hex colour like #8a0a0a or #f80") from None


def _area(area):
    try:
        ar = [float(v) for v in area.replace(";", ",").split(",") if v.strip()]
    except ValueError:
        ar = []
    if len(ar) < 4:
        raise ValueError(f"area '{area}': give four numbers x0, y0, x1, y1 as shares of the frame, e.g. 0.4, 0.4, 0.6, 0.6")
    return ar[:4]


def _fit_plate(img, n, H, W):
    img = img[:n]
    if img.shape[1:3] != (H, W):
        ip = cv2.INTER_AREA if img.shape[1] > H else cv2.INTER_LINEAR
        img = np.stack([cv2.resize(f, (W, H), interpolation=ip) for f in img])
    if len(img) < n:
        img = np.concatenate([img, np.repeat(img[-1:], n - len(img), 0)])
    return img


class EFParticleSettings:
    @classmethod
    def INPUT_TYPES(s):
        mult = lambda tip: ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": tip + " 1 = as in the preset."})
        absval = lambda tip, mx=1.0: ("FLOAT", {"default": -1.0, "min": -1.0, "max": mx, "step": 0.01, "tooltip": tip + " -1 = as in the preset."})
        return {
            "required": {
                "gravity": mult("Times the preset's gravity (negative presets rise: smoke, fire)."),
                "turbulence": mult("Times the preset's swirling (curl noise)."),
                "turbulence_size": mult("Times the size of the swirls."),
                "drag": mult("Times the air resistance."),
                "rate": mult("Times the particles per second."),
                "fade_in": absval("Share of the life used to fade in."),
                "fade_out": absval("Share of the life used to fade out."),
                "depth_spread": absval("Random spread of the particles' depth around the emitter (depth map units).", 0.5),
                "collide": (["preset", "none", "stick", "bounce", "die", "slide"], {"tooltip": "What a particle does when it meets a surface of the depth map while falling: stick (snow), bounce (sparks), die (rain, with splashes if the preset has children), slide."}),
                "sprite": (["preset", "soft", "dot", "flake", "puff", "wisp", "streak", "spark", "chunk", "custom"], {"tooltip": "Shape of a particle in the seed (start video). wisp: soft noise puff with holes (smoke, dust). chunk: solid angular fragment that tumbles (debris), also in the volume guide. custom: the sprite connected to EF Particles (own image or library element)."}),
                "guide_style": (["preset", "lines", "volume", "temperature", "depth"], {"tooltip": "lines: paths as thin strokes (like canny edges). volume: soft blobs, brighter when nearer (like a depth map). temperature: soft blobs, bright where the particle is hot (its colour over life; fire). depth: the clip's depth of the object with the particles where they are nearer (needs depth and the object mask; extra settings depth_guide object/scene, depth_edge)."}),
                "trail": ("INT", {"default": -1, "min": -1, "max": 60, "tooltip": "Frames of trail behind each particle. -1 = as in the preset."}),
                "color": ("STRING", {"default": "", "tooltip": "One colour for all particles as hex (#8a0a0a for blood). Empty = the preset's colours over the life."}),
                "roughness": absval("Lightning: jaggedness of the bolt.", 1.0),
                "branches": ("INT", {"default": -1, "min": -1, "max": 20, "tooltip": "Lightning: number of side branches. -1 = as in the preset."}),
                "extra": ("STRING", {"default": "", "multiline": True, "tooltip": "Any further setting as JSON, e.g. {\"wind\": [80, 0], \"vortex\": 300}. The report of EF Particles lists all settings and their values."}),
            },
            "optional": {
                "speed_variation": absval("Random spread of each particle's start speed: 0 = all equally fast, 0.5 = each between half and one and a half times the speed.", 1.0),
                "preroll": ("FLOAT", {"default": -2.0, "min": -2.0, "max": 60.0, "step": 0.1, "tooltip": "Seconds the particles run before the clip starts, so the frame is already full at frame 0. -2 = as in the preset, -1 = auto (long enough to cross the frame), 0 = none."}),
                "emitter": ("STRING", {"default": "", "tooltip": "The app's emitter panel: settings as JSON with their own value, e.g. {\"gravity\": 900}. They win over the preset, the settings above and the main controls of EF Particles."}),
            },
        }

    RETURN_TYPES = ("EF_PARTICLE_SETTINGS",)
    RETURN_NAMES = ("settings",)
    FUNCTION = "make"
    CATEGORY = "Element Forge"
    DESCRIPTION = "Fine settings of EF Particles for pros. Every value starts at 'as in the preset'."

    def make(self, gravity, turbulence, turbulence_size, drag, rate, fade_in, fade_out, depth_spread, collide, sprite,
             guide_style, trail, color, roughness, branches, extra, speed_variation=-1.0,
             preroll=-2.0, emitter=""):
        o = {"gravity*": gravity, "turbulence*": turbulence, "turb_scale*": turbulence_size, "drag*": drag, "rate*": rate}
        o = {k: v for k, v in o.items() if v != 1.0}
        for k, v in (("fade_in", fade_in), ("fade_out", fade_out), ("depth_spread", depth_spread), ("roughness", roughness),
                     ("speed_var", speed_variation)):
            if v >= 0:
                o[k] = v
        for k, v in (("collide", collide), ("sprite", sprite), ("guide_style", guide_style)):
            if v != "preset":
                o[k] = v
        if trail >= 0:
            o["trail"] = trail
        if branches >= 0:
            o["branches"] = branches
        if preroll >= -1:
            o["preroll"] = preroll
        if color.strip():
            rgb = _hex_rgb(color)
            o["colors"] = [[0.0, rgb], [1.0, rgb]]
        if extra.strip():
            o.update(json.loads(extra))
        if emitter.strip():
            o["final"] = json.loads(emitter)
        return (o,)


def split_final(settings):
    over = dict(settings or {})
    return over, dict(over.pop("final", None) or {})


def apply_final(P, final):
    for k, v in (final or {}).items():
        if k not in P:
            raise ValueError(f"unknown particle setting '{k}' (known: {', '.join(sorted(P))})")
        P[k] = json.loads(json.dumps(v))
    return P


def params_for(preset, settings, speed, size, life, start_seconds, depth_offset=0.0, direction=-1.0, spread=-1.0, follow=-1.0,
               motion_carry=0.0):
    over, final = split_final(settings)
    over.update({"speed*": speed, "size*": size, "life*": life, "start": float(start_seconds),
                 "depth_offset": pt.PRESETS[preset].get("depth_offset", 0.0) + depth_offset})
    if direction >= 0:
        over["direction"] = direction
        if "direction_mode" not in over and pt.PRESETS[preset].get("direction_mode") in ("outward", "random"):
            over["direction_mode"] = "angle"
    if spread >= 0:
        over["spread"] = spread
    if follow >= 0:
        over["inherit"] = follow
    if motion_carry > 0:
        over["motion_carry"] = motion_carry
    return apply_final(pt.params(preset, over), final)


def setup(plate, preset, emitter, amount, speed, size, life, direction, spread, follow, start_seconds, fps, seed,
          track=None, track_b=None, mask=None, drawing=None, depth=None, settings=None, area="0.4, 0.4, 0.6, 0.6",
          depth_offset=0.0, premask=True, edge_fade=0.08, camera="follow the plate", look_plate=None, line_attach="track",
          motion_carry=0.0, screen_fixed=False, cam=None, memo=None):
    if screen_fixed:
        camera = "fixed"
    if emitter == "whole frame":
        edge_fade = 0.0
        premask = False
    pl = _np(plate)[..., :3]
    n, H, W = pl.shape[:3]
    P = params_for(preset, settings, speed, size, life, start_seconds, depth_offset, direction, spread, follow, motion_carry)
    rng = np.random.default_rng(seed)
    dmaps = None
    if depth is not None:
        d = _np(depth)
        dmaps = d[..., 0] if d.ndim == 4 else d
    dep = pt.Depth(dmaps, W, H) if dmaps is not None else None
    avoid = _mask3(mask) if mask is not None else None
    if cam is None:
        cam = pt.Camera.from_plate(pl, avoid) if camera.startswith("follow") and n > 1 else pt.Camera(n)
    ar = _area(area) if area and emitter == "area" else None
    if emitter in ("point A", "line A-B") and track_b is not None and avoid is not None and P.get("ab_on_objects", 0):
        a0 = pt.Emitter._path(track, 1, None)
        ea, eb = pt.ends_on_objects(avoid, n, W, H, a0=None if a0 is None else a0[0])
        if ea is not None:
            track, track_b = {"point_track_px": ea.tolist()}, {"point_track_px": eb.tolist()}
    em = pt.Emitter(emitter, n, fps, W, H, P, rng, a=track, b=track_b, masks=avoid,
                    drawing=_mask3(drawing) if drawing is not None else None, area=ar, depth=dep, cam=cam,
                    attach=line_attach, frames=pl if line_attach == "object" else None, memo=memo)
    target = track_b if (P["attract"] or P["path"] == "bolt") else None
    flow = None
    if P["motion_carry"] > 0 and n > 1:
        flow = memo.get(("flow", n, H, W)) if memo is not None else None
        if flow is None:
            flow = pt.PlateFlow(pl, keep=memo is not None)
            if memo is not None:
                memo[("flow", n, H, W)] = flow
    rec = pt.simulate(P, em, seed=seed, amount=amount, target=target, flow=flow, look_state=memo is not None)
    if P.get("plate_color"):
        rec["pcol"] = pt.plate_colours(rec, pl if look_plate is None else _fit_plate(_np(look_plate)[..., :3], n, H, W))
    paths = pt.make_paths(P, em, seed, target=target) if P["path"] != "particles" else None
    return {"pl": pl, "n": n, "H": H, "W": W, "P": P, "em": em, "avoid": avoid, "target": target, "rec": rec, "paths": paths,
            "premask": premask, "edge_fade": edge_fade, "cam": cam}


def depth_guide(s, depth, mask, win, P):
    from .particle_depth_ops import inner_edge, make_guides, path_lines
    if depth is None:
        raise ValueError("the depth guide needs the clip's depth")
    scene = P.get("depth_guide", "object") == "scene"
    if not scene and mask is None:
        raise ValueError("the depth guide of the object needs the object's mask: click the object in Position")
    out = make_guides(s, _np(depth)[..., 0], None if scene else _mask3(mask), win, pt)
    edge = int(round(float(P.get("depth_edge", 0) or 0)))
    if edge > 0 and not scene:
        out["merged"] = np.where(out["coverage"] > 0.001, out["particle"], out["scene"] * inner_edge(out["object_mask"], edge))
    g = out["merged"]
    if s["paths"] is not None:
        g = np.maximum(g, path_lines(s["paths"], win, pt, s["n"], P))
    res = np.zeros(g.shape + (4,), np.float32)
    res[..., 3] = g
    return res


class EFParticles:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "The clip (frame count, size; camera motion is measured from it)."}),
                "preset": (list(pt.PRESETS), {"tooltip": "What the particles do. The prompt still decides what LTX makes of them."}),
                "emitter": (pt.EMITTERS, {"tooltip": "Where particles are born: the tracked point A, the line between A and B (e.g. magic between two hands), a drawing (see line_attach), the object mask (area, contour or bottom edge: where it meets the ground, e.g. sparks under the wheels), a fixed area, the whole frame (snow, rain), or groups: one particle per entry of the setting 'groups' (x, y, depth, scale, offset), with the preset groups and the element as own sprite (groups in depth)."}),
                "amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": "Times the preset's number of particles."}),
                "speed": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 20.0, "step": 0.05, "tooltip": "Times the preset's speed."}),
                "size": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 20.0, "step": 0.05, "tooltip": "Times the preset's particle size."}),
                "life": ("FLOAT", {"default": 1.0, "min": 0.05, "max": 20.0, "step": 0.05, "tooltip": "Times the preset's lifetime."}),
                "direction": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 360.0, "step": 1.0, "tooltip": "Direction in degrees (0 up, 90 right, 180 down). -1 = as in the preset."}),
                "spread": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 180.0, "step": 1.0, "tooltip": "Half angle of the cone. -1 = as in the preset."}),
                "follow": ("FLOAT", {"default": -1.0, "min": -1.0, "max": 1.0, "step": 0.05, "tooltip": "Particle drag: share of the emitter's motion the particles take along (0 none, 1 all). -1 = as in the preset."}),
                "start_seconds": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 600.0, "step": 0.05, "tooltip": "Second at which the emitter starts (and a burst goes off)."}),
                "fps": ("FLOAT", {"default": 25.0, "min": 1.0, "max": 240.0, "step": 0.001}),
                "seed": ("INT", {"default": 1, "min": 0, "max": 2 ** 31 - 1}),
            },
            "optional": {
                "track": ("EF_TRACK", {"tooltip": "Track of point A (emitter point, start of a line, the drawing follows it)."}),
                "track_b": ("EF_TRACK", {"tooltip": "Track of point B (end of a line, target of 'energy A-B' and lightning)."}),
                "mask": ("MASK", {"tooltip": "Object mask(s) per frame for the emitters 'object mask', 'object contour', 'object bottom edge' and a drawing hung on the object."}),
                "drawing": ("MASK", {"tooltip": "Strokes painted on the first frame (mask editor) for the emitter 'drawing'."}),
                "line_attach": (pt.LINE_ATTACH, {"default": "track", "tooltip": "What the drawing hangs on. track: moves with point A (with B also turns and scales with the line A-B). image: stays where it was drawn. object: carried by the object mask and the motion inside it, snapped onto the object's contour in every frame (draw roughly under the wheels: the sparks stay at the wheels). object without a drawing: the object's bottom edge."}),
                "motion_carry": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "How strongly moving things in the clip carry the particles along (optical flow of the plate, measured here): 0 off, 1 the particles move with whatever moves under them. Still parts and the camera's own motion leave them to their physics; once out of the moving part they keep the speed they took."}),
                "depth": ("IMAGE", {"tooltip": "Depth map per frame (Video Depth Anything, larger = nearer): occlusion per particle, landing on surfaces, perspective size."}),
                "window": ("EF_TRACK", {"tooltip": "The window LTX generates in (EF Track ROI / EF Follow Crop): guide, tracks and seed are drawn in it; particles fade out before its border."}),
                "settings": ("EF_PARTICLE_SETTINGS", {"tooltip": "Fine settings (EF Particle Settings)."}),
                "area": ("STRING", {"default": "0.4, 0.4, 0.6, 0.6", "tooltip": "Emitter 'area': x0, y0, x1, y1 as shares of the frame."}),
                "depth_offset": ("FLOAT", {"default": 0.0, "min": -1.0, "max": 1.0, "step": 0.01, "tooltip": "Added to the preset's offset (aura: -0.15, others 0). + = particles nearer than the emitter's surface (less hidden), - = behind it (an aura around a figure)."}),
                "premask": ("BOOLEAN", {"default": True, "tooltip": "Particles hidden by the scene are left out of guide, tracks and seed already (LTX gets no control there)."}),
                "edge_fade": ("FLOAT", {"default": 0.08, "min": 0.0, "max": 0.5, "step": 0.01, "tooltip": "Particles fade out over this share of the window before its border: nothing gets cut by the frame."}),
                "track_count": ("INT", {"default": 16, "min": 0, "max": 64, "tooltip": "Number of particle paths for LTXVDrawTracks."}),
                "camera": (["follow the plate", "fixed"], {"tooltip": "follow the plate: particles live in the scene (the camera motion of the plate is measured). fixed: screen space."}),
                "sprite": ("IMAGE", {"lazy": True, "tooltip": "Own sprite for pros, used when the sprite setting is custom: an image or a short clip (flipbook over the particle's life), e.g. a library element (EF Load Element rgba). Replaces the built-in shape in the seed; the guide stays."}),
                "sprite_alpha": ("MASK", {"lazy": True, "tooltip": "Alpha of the sprite (Load Image: the mask output is 1 - alpha, invert it). Without it: RGBA input or brightness."}),
                "direct_look": ("BOOLEAN", {"default": False, "tooltip": "Pro: the particles as a finished look without LTX (output look): light presets glow, smoke, dust, cracks and frost lie over the plate, rain and snow use contrast. Off = look is just the plate (nothing rendered)."}),
                "look_plate": ("IMAGE", {"tooltip": "Plate for the look (e.g. after a night grade); default the plate."}),
                "inpaint_sigmas": ("STRING", {"default": pt.STANDARD_INPAINT, "tooltip": "Inpaint start sigmas. At the standard, presets that must change the surface (cracks, frost) bring their own (from 0.9875); any other value wins."}),
                "screen_fixed": ("BOOLEAN", {"default": False, "tooltip": "Fixed on screen (Follows: Screen): the camera of the plate is not followed, as with camera fixed."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT", "INT", "IMAGE", "MASK", "IMAGE", "MASK", "MASK", "MASK", "IMAGE", "STRING", "STRING", "STRING", "IMAGE", "IMAGE")
    RETURN_NAMES = ("guide", "tracks", "width", "height", "seed", "seed_alpha", "seed_over_plate", "alpha", "region",
                    "holdout", "preview", "report", "inpaint_sigmas", "blend", "look", "look_layer")
    FUNCTION = "run"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("A particle emitter that steers LTX. guide: lines or soft volumes for the union IC-LoRA. tracks: particle "
                   "paths for LTXVDrawTracks (motion-track IC-LoRA). seed: soft sprites as a start video (sample from sigma "
                   "0.909), on black in the window; seed_over_plate for Inpaint. alpha, region, holdout: plate masks for "
                   "the comp (holdout = hidden behind the scene, per pixel from the particles' depth).")

    def check_lazy_status(self, preset, settings=None, sprite=None, sprite_alpha=None, **kw):
        try:
            over, final = split_final(settings)
            custom = apply_final(pt.params(preset, over), final)["sprite"] == "custom"
        except Exception:
            custom = True
        return [k for k, v in (("sprite", sprite), ("sprite_alpha", sprite_alpha)) if custom and v is None]

    def run(self, plate, preset, emitter, amount, speed, size, life, direction, spread, follow, start_seconds, fps, seed,
            track=None, track_b=None, mask=None, drawing=None, depth=None, window=None, settings=None, area="0.4, 0.4, 0.6, 0.6",
            depth_offset=0.0, premask=True, edge_fade=0.08, track_count=16, camera="follow the plate", sprite=None,
            sprite_alpha=None, inpaint_sigmas=pt.STANDARD_INPAINT, direct_look=False, look_plate=None, line_attach="track",
            motion_carry=0.0, screen_fixed=False):
        t_0 = time.time()
        s = setup(plate, preset, emitter, amount, speed, size, life, direction, spread, follow, start_seconds, fps, seed,
                  track, track_b, mask, drawing, depth, settings, area, depth_offset, premask, edge_fade, camera, look_plate,
                  line_attach, motion_carry, screen_fixed)
        pl, n, H, W, P, em, avoid, target, rec, paths = (s[k] for k in ("pl", "n", "H", "W", "P", "em", "avoid", "target", "rec", "paths"))
        premask, edge_fade = s["premask"], s["edge_fade"]
        t_sim = time.time() - t_0
        spr = None
        if sprite is not None and P["sprite"] == "custom":
            sp_ = _np(sprite)
            if sprite_alpha is not None:
                al_ = _mask3(sprite_alpha)
                al_ = np.stack([al_[min(j, len(al_) - 1)] for j in range(len(sp_))])
                spr = np.concatenate([sp_[..., :3], al_[..., None]], -1)
            elif sp_.shape[-1] == 4:
                spr = sp_
            else:
                spr = np.concatenate([sp_[..., :3], sp_[..., :3].max(-1, keepdims=True)], -1)
            P["_tinted"] = bool(settings and ("colors" in settings or "colors" in (settings.get("final") or {})))
        win = pt.Raster(W, H, window)
        plate_r = pt.Raster(W, H)
        if P["guide_style"] == "depth":
            guide = depth_guide(s, depth, mask, win, P)
        else:
            guide = pt.render_frames(P, rec, em, paths, win, P["guide_style"], premask, edge_fade)
        seed_w = pt.render_frames(P, rec, em, paths, win, "seed", premask, edge_fade, sprite=spr)
        seed_p = pt.render_frames(P, rec, em, paths, plate_r, "seed", premask, edge_fade, edge_raster=win if window else None,
                                  sprite=spr)
        region, hold = pt.masks_from(seed_p[..., 3], rec, em, P, premask, guide=pl, paths=paths)
        tracks, nt = pt.tracks_json(rec, win, track_count, P, edge_fade)
        prev = pt.preview(pl, seed_p, em, window)
        T = lambda a: torch.from_numpy(np.ascontiguousarray(a, np.float32))
        drng = np.random.default_rng(seed + 1)
        g = guide[..., 3:4] if P["guide_style"] in ("lines", "depth") else guide[..., :3]
        g = np.repeat(g, 3, -1) if g.shape[-1] == 1 else g
        out_g = T(np.clip(g, 0, 1))
        del guide, g
        out_sw = T(pt.dither(seed_w[..., :3], drng, lo=0, hi=1))
        out_swa = T(seed_w[..., 3])
        del seed_w
        sop = np.empty(pl.shape, np.float32)
        for i in range(n):
            sop[i] = pt.dither(pl[i] * (1 - seed_p[i, ..., 3:4]) + seed_p[i, ..., :3], drng, lo=0, hi=1)
        out_spa = T(seed_p[..., 3])
        lp = pl if look_plate is None else _fit_plate(_np(look_plate)[..., :3], n, H, W)
        if direct_look:
            mode = P.get("look") or P.get("blend", "add")
            opt = mode == "over"
            same = window is None and not opt and edge_fade <= 0
            if same:
                seed_l = seed_p
            else:
                del seed_p
                seed_l = pt.render_frames(P, rec, em, paths, plate_r, "seed", premask, 0.0, sprite=spr, optical=opt)
            shl = None
            if float(P.get("shell", 0.0) or 0.0) > 0 and avoid is not None and mode == "add":
                shl = pt.shell_light(avoid, n, np.mean([c[1] for c in P["colors"]], 0), float(P["shell"]), fps, seed)
            look, look_l = pt.direct_look(lp, seed_l, hold, mode, float(P.get("glow", 0.0) or 0.0), drng,
                                          float(P.get("ambient", 0.0) or 0.0), float(P.get("halo", 0.0) or 0.0),
                                          float(P.get("relief", 0.0) or 0.0), line_width=float(P["width"]) * min(W, H) / pt.REF,
                                          shell=shl, bloom=float(P.get("bloom", 1.0)))
            del seed_l
        else:
            look, look_l = lp, None
        st = rec["stats"]
        alive = int(np.isfinite(rec["x"]).sum(1).max()) if rec["x"].size else 0
        hidden = float(1 - np.nanmean(np.where(np.isfinite(rec["x"]), rec["vis"], np.nan))) if rec["x"].size else 0.0
        rep = (f"{preset}, emitter {emitter}: {st['spawned']} particles (+{st['children']} children), up to {alive} at once; "
               f"landed {st['landed']}, bounced {st['bounced']}; hidden by the scene {hidden:.0%}; {nt} tracks; "
               f"raster {win.w}x{win.h}; {t_sim:.1f} s simulation, {time.time() - t_0:.1f} s total"
               + (f"; capacity reached, {st['capped']} particles not born" if st["capped"] else "")
               + "\nsettings: " + json.dumps({k: v for k, v in P.items() if not k.startswith("_")}))
        isig = inpaint_sigmas
        if " ".join(inpaint_sigmas.split()) == " ".join(pt.STANDARD_INPAINT.split()) and P.get("inpaint_sigmas"):
            isig = P["inpaint_sigmas"]
        return (out_g, tracks, int(win.w), int(win.h), out_sw, out_swa, T(sop), out_spa,
                T(region), T(hold), T(prev), rep, isig, P.get("blend", "add"), T(look),
                T(look_l) if look_l is not None else torch.zeros((1, H, W, 3)).expand(n, H, W, 3))

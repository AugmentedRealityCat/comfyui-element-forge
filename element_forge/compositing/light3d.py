import numpy as np
import torch
import torch.nn.functional as F

LUMA = torch.tensor([0.2126, 0.7152, 0.0722])
REF = 0.1


def srgb_to_linear(x):
    return torch.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055).clamp(min=0).pow(2.4))


def linear_to_srgb(x):
    return torch.where(x <= 0.0031308, x * 12.92, 1.055 * x.clamp(min=0).pow(1 / 2.4) - 0.055)


def pick_device(choice):
    if choice == "cpu":
        return torch.device("cpu")
    try:
        import comfy.model_management as mm
        dev = mm.get_torch_device()
    except Exception:
        dev = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    return dev if isinstance(dev, torch.device) and dev.type in ("cuda", "xpu", "mps") else torch.device("cpu")


def depth_to_z(d, depth_range, kind="linear"):
    if kind == "disparity":
        r = 1.0 / depth_range
        return 1.0 / (r + d * (1.0 - r))
    return 1.0 + (1.0 - d) * (depth_range - 1.0)


def gaussian_blur(x, sigma):
    if sigma <= 0:
        return x
    r = max(1, int(3 * sigma))
    k = torch.exp(-0.5 * (torch.arange(-r, r + 1, dtype=x.dtype, device=x.device) / sigma) ** 2)
    k = k / k.sum()
    c = x.shape[1]
    x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="replicate"), k.view(1, 1, 1, -1).repeat(c, 1, 1, 1), groups=c)
    return F.conv2d(F.pad(x, (0, 0, r, r), mode="replicate"), k.view(1, 1, -1, 1).repeat(c, 1, 1, 1), groups=c)


class EFDepthLight:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "plate": ("IMAGE", {"tooltip": "Plate the light is added to (sRGB), e.g. the night-graded plate. All passes come out at its resolution."}),
                "layer_plate_linear": ("IMAGE", {"tooltip": "The placed element in plate space, linear (EF Place Element)."}),
                "depth": ("IMAGE", {"tooltip": "Depth map, e.g. DA3 Render (min_max), ideally at the clip resolution (DA3 resolution = longer side). Normalized per clip."}),
                "strength": ("FLOAT", {"default": 5.0, "min": 0.0, "max": 1000.0, "step": 0.05, "tooltip": "Brightness of the light: 1 = irradiance 1 at a distance of 0.1 scene units (nearest point = 1). Follows the flicker of the element."}),
                "depth_range": ("FLOAT", {"default": 3.0, "min": 1.05, "max": 100.0, "step": 0.05, "tooltip": "How much further the farthest point is than the nearest one (far / near). Sets how strongly the light falls off into the depth. EF MoGe Normals measures it per clip (its depth_range output)."}),
                "fov": ("FLOAT", {"default": 65.0, "min": 5.0, "max": 150.0, "step": 1.0, "tooltip": "Field of view of the camera along the longer image side (degrees). Phones: about 65-75. EF MoGe Normals measures it per clip (its fov output)."}),
                "light_size": ("FLOAT", {"default": 0.15, "min": 0.001, "max": 1.0, "step": 0.005, "tooltip": "Size of the light source in scene units (nearest point = 1). Larger = softer falloff right next to it."}),
                "wrap": ("FLOAT", {"default": 0.25, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "Lets the light wrap a little around edges (rough surfaces, inaccurate normals). 0 = hard Lambert."}),
                "shadows": ("BOOLEAN", {"default": True, "tooltip": "Screen-space shadows: surfaces hidden from the light by something in front get no light."}),
                "max_light": ("FLOAT", {"default": 0.8, "min": 0.01, "max": 100.0, "step": 0.05, "tooltip": "Soft upper limit of the irradiance. 1 = a lit surface gets at most as bright as its albedo (keeps texture, no white blob near the light). Higher only for very hot sources."}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.05, "tooltip": "Color of the light: 0 = white, 1 = the element's color."}),
            },
            "optional": {
                "track": ("EF_TRACK", {"tooltip": "Track of the anchor (EF Track ROI). The lights sit at the depth of the tracked point. Without it: at the nearest surface under the element."}),
                "light_offset": ("FLOAT", {"default": 0.02, "min": -1.0, "max": 1.0, "step": 0.005, "tooltip": "Moves the light towards the camera (scene units), e.g. a flame hovering in front of the palm."}),
                "albedo": ("IMAGE", {"tooltip": "Surface color for the light (sRGB). For night shots: the day plate. Without it: the plate."}),
                "receiver": ("MASK", {"tooltip": "Limits the light to these surfaces (1)."}),
                "lights": ("INT", {"default": 6, "min": 1, "max": 32, "tooltip": "Number of point lights sampled from the element (more = softer, slower)."}),
                "color": ("STRING", {"default": "", "tooltip": "Color of the light, hex like #ff9a50 (fire is warmer than its bright core looks). Empty = the element's color."}),
                "color_amount": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
                "element_depth": ("MASK", {"tooltip": "Depth of the element per pixel (same scale as the depth map, near = 1), e.g. EF Scatter Swarms element_depth. Each light then sits at the depth of the emission it comes from (swarms at several depths). Overrides track."}),
                "albedo_exposure": ("FLOAT", {"default": 0.0, "min": -4.0, "max": 8.0, "step": 0.25, "tooltip": "Brightens the albedo in stops. For night plates without a day version: the plate itself is far darker than the surfaces' real colour."}),
                "shadow_thickness": ("FLOAT", {"default": 0.15, "min": 0.01, "max": 10.0, "step": 0.01, "tooltip": "How deep an object reaches behind its visible surface for shadows (scene units, nearest point = 1). Without a limit a person near the camera would shadow everything behind it."}),
                "surface_detail": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 3.0, "step": 0.05, "tooltip": "Fine relief from the albedo (bump), so folds and chisel edges catch the light where the depth map is too coarse. 0 = depth only. Painted patterns, stains and cast shadows also read as relief: use 0 on painted or stained floors and walls."}),
                "normals": (["smooth surfaces", "raw depth"], {"default": "smooth surfaces", "tooltip": "smooth surfaces: normals from an edge-aware smoothed depth at reduced resolution, one-sided at depth edges (no relief from depth noise, no embossed rims around people). raw depth: per-pixel differences of the depth map."}),
                "normals_image": ("IMAGE", {"tooltip": "Normals from a normal estimator instead of the depth map, encoded OpenGL style (0.5 + 0.5 n: +X right, +Y up, +Z towards the camera), e.g. MoGe Render 'normal_opengl' (MoGe-2). Sharper shapes, flat floors stay flat, painted patterns do not become relief. Resized to the plate."}),
                "normal_resolution": ("INT", {"default": 540, "min": 128, "max": 2048, "step": 2, "tooltip": "smooth surfaces: longer side in px at which normals are computed. Lower = smoother surfaces, higher = more shape detail (and more depth noise)."}),
                "device": (["auto", "cpu"], {"default": "auto", "tooltip": "auto: computes frame by frame on ComfyUI's GPU (one frame at a time, a few hundred MB; falls back to the CPU if the GPU is full). cpu: always on the CPU. The result is the same up to float rounding."}),
                "depth_kind": (["linear", "disparity"], {"default": "linear", "tooltip": "How the depth map is read. disparity: inverse depth (Video Depth Anything, DA3 min_max): the background is far behind and gets little light from a source in the front, as it should; distances count in the light's own distance from the camera, so a shot with something very near the lens is not darker. linear: the map is taken as linear depth (as in earlier versions)."}),
                "add_element": ("BOOLEAN", {"default": True, "tooltip": "On: comp = plate + light + element. Off: comp = plate + light only, for a plate that already holds its glowing element (e.g. the finished dissolve lit by its own embers)."}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "IMAGE")
    RETURN_NAMES = ("comp", "light_linear", "normals")
    FUNCTION = "light"
    CATEGORY = "Element Forge"
    DESCRIPTION = ("Lights the plate with the element as a 3D light source: point cloud and normals from the depth map, "
                   "inverse-square falloff, Lambert shading and screen-space shadows. Separate linear light pass for "
                   "compositing (Add).")

    def light(self, plate, layer_plate_linear, depth, strength, depth_range, fov, light_size, wrap, shadows, max_light,
              saturation, track=None, light_offset=0.02, albedo=None, receiver=None, lights=6, color="", color_amount=1.0,
              surface_detail=0.5, element_depth=None, albedo_exposure=0.0, shadow_thickness=0.15,
              normals="smooth surfaces", normal_resolution=540, normals_image=None, device="auto", depth_kind="linear",
              add_element=True):
        pl = plate[..., :3].float()
        ly = layer_plate_linear[..., :3].float()
        n = min(len(pl), len(ly))
        h, w = pl.shape[1:3]
        dp = depth[..., :3].float().mean(-1)
        if dp.shape[1:] != (h, w):
            dp = F.interpolate(dp[:, None], size=(h, w), mode="bicubic", align_corners=False)[:, 0]
        d_lo, d_hi = float(dp.min()), float(dp.max())
        if d_hi - d_lo < 1e-3:
            d_lo, d_hi = 0.0, 1.0
        dp = (dp - d_lo) / (d_hi - d_lo)
        ab_src = albedo if albedo is not None else plate

        def ab_frame(j):
            a = srgb_to_linear(ab_src[min(j, len(ab_src) - 1), ..., :3].float().clamp(0, 1)) * (2.0 ** albedo_exposure)
            return a.clamp(max=0.9)
        if element_depth is not None:
            ed_all = element_depth.float()
            if ed_all.shape[1:] != (h, w):
                ed_all = F.interpolate(ed_all[:, None], size=(h, w), mode="bilinear", align_corners=False)[:, 0]
        s = max(1, int(round(max(h, w) / 480)))
        hs, ws = h // s, w // s
        f = float((max(w, h) / 2) / np.tan(np.radians(fov) / 2))
        f_s = f / s
        cx, cy = (w - 1) / 2, (h - 1) / 2
        cxs, cys = (ws - 1) / 2, (hs - 1) / 2
        tint = None
        if color and color.strip():
            t = color.strip().lstrip("#")
            if len(t) != 6:
                raise ValueError(f"color must be a hex value like #ff9a50, got {color!r}")
            tint = srgb_to_linear(torch.tensor([int(t[k:k + 2], 16) / 255 for k in (0, 2, 4)]))
            tint = tint / (tint * LUMA).sum().clamp(min=1e-8)

        consts = {}

        def on(dev):
            if dev not in consts:
                vv, uu = torch.meshgrid(torch.arange(h, dtype=torch.float32, device=dev), torch.arange(w, dtype=torch.float32, device=dev), indexing="ij")
                vs, us = torch.meshgrid(torch.arange(hs, dtype=torch.float32, device=dev), torch.arange(ws, dtype=torch.float32, device=dev), indexing="ij")
                consts[dev] = dict(uu=uu, vv=vv, us=us, vs=vs, L=LUMA.to(dev), flip=torch.tensor([1.0, -1.0, -1.0], device=dev),
                                   tint=None if tint is None else tint.to(dev))
            return consts[dev]
        lights_out, normals_out, comps = (torch.empty((n, h, w, 3), dtype=torch.float32) for _ in range(3))
        energy = (ly[:n] * LUMA).sum(-1).flatten(1).sum(1)
        mean_energy = float(energy.mean()).__abs__() or 1.0

        def frame(i, dev):
            c = on(dev)
            uu, vv, us, vs, Ld, flip, tint_d = c["uu"], c["vv"], c["us"], c["vs"], c["L"], c["flip"], c["tint"]
            abi = ab_frame(i).to(dev)
            pli, lyi = pl[i].to(dev), ly[i].to(dev)
            d = gaussian_blur(dp[min(i, len(dp) - 1)].to(dev)[None, None], 1.0)[0, 0]
            z = depth_to_z(d, depth_range, depth_kind)
            P = torch.stack(((uu - cx) / f * z, (vv - cy) / f * z, z), -1)
            if normals_image is not None:
                ni = normals_image[min(i, len(normals_image) - 1), ..., :3].float().to(dev)
                if ni.shape[:2] != (h, w):
                    ni = F.interpolate(ni.permute(2, 0, 1)[None], size=(h, w), mode="bilinear", align_corners=False)[0].permute(1, 2, 0)
                nrm = (ni * 2 - 1) * flip
                nrm = nrm / nrm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
            elif normals == "raw depth":
                nrm = self.normals(P)
            else:
                nrm = self.normals_smooth(z, f, normal_resolution)
            if surface_detail > 0:
                lum = (abi * Ld).sum(-1)[None, None]
                base = gaussian_blur(lum, 8.0)
                hgt = gaussian_blur((lum - base) / (base + 0.05), 1.0)[0, 0]
                gu = torch.zeros_like(hgt)
                gv = torch.zeros_like(hgt)
                gu[:, 1:-1] = (hgt[:, 2:] - hgt[:, :-2]) / 2
                gv[1:-1] = (hgt[2:] - hgt[:-2]) / 2
                k = surface_detail * 4.0
                nrm = nrm + torch.stack((-k * gu, -k * gv, torch.zeros_like(gu)), -1) * (-nrm[..., 2:3]).clamp(min=0)
                nrm = nrm / nrm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
            zs = F.interpolate(z[None, None], size=(hs, ws), mode="area")[0, 0]
            Ps = torch.stack(((us - cxs) / f_s * zs, (vs - cys) / f_s * zs, zs), -1)
            e = F.interpolate(lyi.permute(2, 0, 1)[None], size=(hs, ws), mode="area")[0].permute(1, 2, 0) * (s * s)
            lum_e = (e * Ld).sum(-1)
            total = float(lum_e.sum())
            E = torch.zeros(h, w, 3, device=dev)
            if total > 1e-6:
                g = 4
                gh, gw = (hs + g - 1) // g, (ws + g - 1) // g
                pad = (0, gw * g - ws, 0, gh * g - hs)
                cell = F.pad(lum_e, pad).view(gh, g, gw, g).sum((1, 3))
                R = 2
                free = torch.ones(gh, gw, device=dev)
                cw = cell.clone()
                thr = 0.02 * float(cell.max())
                picks = []
                for _ in range(lights):
                    t = int(torch.argmax(cw))
                    r, c = divmod(t, gw)
                    if float(cw[r, c]) <= thr:
                        break
                    r0, r1, c0, c1 = max(0, r - R), min(gh, r + R + 1), max(0, c - R), min(gw, c + R + 1)
                    picks.append((r0, r1, c0, c1, free[r0:r1, c0:c1].clone()))
                    free[r0:r1, c0:c1] = 0
                    cw[r0:r1, c0:c1] = 0
                if track is not None:
                    tx, ty = track["point_track_px"][min(i, len(track["point_track_px"]) - 1)]
                    zi = z[int(np.clip(ty, 0, h - 1)), int(np.clip(tx, 0, w - 1))]
                else:
                    zi = torch.quantile(zs[lum_e > 0.05 * lum_e.max()], 0.1)
                zl = float(zi) - light_offset
                lum_pp = F.pad(lum_e, pad)
                e_pp = F.pad(e.permute(2, 0, 1), pad)
                if element_depth is not None:
                    eds = F.interpolate(ed_all[min(i, len(ed_all) - 1)].to(dev)[None, None], size=(hs, ws), mode="area")[0, 0]
                    ed_pp = F.pad(eds, pad)
                for r0, r1, c0, c1, m in picks:
                    mm = m.repeat_interleave(g, 0).repeat_interleave(g, 1)
                    wgt = lum_pp[r0 * g:r1 * g, c0 * g:c1 * g] * mm
                    wsum = float(wgt.sum())
                    if wsum <= 0:
                        continue
                    yy, xx = torch.meshgrid(torch.arange(r0 * g, r1 * g, device=dev), torch.arange(c0 * g, c1 * g, device=dev), indexing="ij")
                    ul, vl = float((xx * wgt).sum() / wsum), float((yy * wgt).sum() / wsum)
                    col = (e_pp[:, r0 * g:r1 * g, c0 * g:c1 * g] * mm).sum((1, 2))
                    col = col / max(float((col * Ld).sum()), 1e-8)
                    col = 1.0 + (col - 1.0) * saturation
                    if tint_d is not None:
                        col = col * (1 - color_amount) + tint_d * color_amount
                    zli = zl
                    if element_depth is not None:
                        edw = (float((ed_pp[r0 * g:r1 * g, c0 * g:c1 * g] * wgt).sum() / wsum) - d_lo) / (d_hi - d_lo)
                        zli = depth_to_z(edw, depth_range, depth_kind) - light_offset
                    Lp = torch.tensor([(ul - cxs) / f_s * zli, (vl - cys) / f_s * zli, zli], device=dev)
                    vec = Lp - P
                    dist2 = (vec * vec).sum(-1)
                    ldir = vec / dist2.sqrt()[..., None].clamp(min=1e-6)
                    if depth_kind == "disparity":
                        dist2 = dist2 / max(zli, 1e-3) ** 2
                    ndl = (((nrm * ldir).sum(-1) + wrap) / (1 + wrap)).clamp(min=0)
                    if shadows:
                        vis = self.visibility(Ps, Lp, zs, f_s, cxs, cys, thickness=shadow_thickness)
                        vis = F.interpolate(vis[None, None], size=(h, w), mode="bilinear", align_corners=False)[0, 0]
                    else:
                        vis = 1.0
                    E += (wsum / total) * col * (ndl * vis / (dist2 + light_size ** 2))[..., None]
                E = E * (float(energy[i]) / mean_energy) * REF ** 2
            E = E * strength
            L = (E * Ld).sum(-1, keepdim=True)
            E = E * (max_light * torch.tanh(L / max_light) / L.clamp(min=1e-8))
            if receiver is not None:
                rc = receiver[min(i, len(receiver) - 1)].float().to(dev)
                if rc.shape != (h, w):
                    rc = F.interpolate(rc[None, None], size=(h, w), mode="bilinear", align_corners=False)[0, 0]
                E = E * rc[..., None]
            lt = abi * E
            lights_out[i] = lt.cpu()
            comps[i] = linear_to_srgb((srgb_to_linear(pli.clamp(0, 1)) + lt + (lyi.clamp(min=0) if add_element else 0)).clamp(min=0)).cpu()
            normals_out[i] = (nrm * flip * 0.5 + 0.5).clamp(0, 1).cpu()

        dev = pick_device(device)
        for i in range(n):
            if dev.type != "cpu":
                try:
                    frame(i, dev)
                    continue
                except torch.OutOfMemoryError:
                    print(f"[Element Forge] EF Depth Light: GPU out of memory at frame {i}, going on on the CPU")
                    consts.clear()
                    dev = torch.device("cpu")
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
            frame(i, dev)

        return (comps, lights_out, normals_out)

    @staticmethod
    def _shift(x, dy, dx):
        h, w = x.shape[:2]
        yy = (torch.arange(h, device=x.device) - dy).clamp(0, h - 1)
        xx = (torch.arange(w, device=x.device) - dx).clamp(0, w - 1)
        return x[yy][:, xx]

    @classmethod
    def normals_smooth(cls, z, f, work=540, rel=0.02, iters=3, rad=3, nsmooth=2):
        sh = cls._shift
        h, w = z.shape
        s = max(1.0, max(h, w) / work)
        hs, ws = max(2, int(round(h / s))), max(2, int(round(w / s)))
        zl = F.interpolate(z[None, None], size=(hs, ws), mode="area")[0, 0]
        g = torch.exp(-torch.arange(-rad, rad + 1, dtype=torch.float32, device=z.device) ** 2 / (2 * (rad / 1.5) ** 2))
        for _ in range(iters):
            acc = torch.zeros_like(zl)
            wsum = torch.zeros_like(zl)
            for dy in range(-rad, rad + 1):
                for dx in range(-rad, rad + 1):
                    zn = sh(zl, dy, dx)
                    wgt = g[dy + rad] * g[dx + rad] * torch.exp(-((zn - zl) / (rel * zl)) ** 2)
                    acc += wgt * zn
                    wsum += wgt
            zl = acc / wsum
        fs = f * ws / w
        v, u = torch.meshgrid(torch.arange(hs, dtype=torch.float32, device=z.device), torch.arange(ws, dtype=torch.float32, device=z.device), indexing="ij")
        P = torch.stack(((u - (ws - 1) / 2) / fs * zl, (v - (hs - 1) / 2) / fs * zl, zl), -1)
        fu, bu = sh(P, 0, -1) - P, P - sh(P, 0, 1)
        fv, bv = sh(P, -1, 0) - P, P - sh(P, 1, 0)
        du = torch.where((fu[..., 2].abs() < bu[..., 2].abs())[..., None], fu, bu)
        dv = torch.where((fv[..., 2].abs() < bv[..., 2].abs())[..., None], fv, bv)
        n = torch.cross(dv, du, dim=-1)
        n = n / n.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        n = torch.where((n * P).sum(-1, keepdim=True) > 0, -n, n)
        for _ in range(nsmooth):
            acc = torch.zeros_like(n)
            wsum = torch.zeros_like(zl)
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    wgt = torch.exp(-((sh(zl, dy, dx) - zl) / (rel * zl)) ** 2) * float(np.exp(-(dy * dy + dx * dx) / 4.5))
                    acc += wgt[..., None] * sh(n, dy, dx)
                    wsum += wgt
            n = acc / wsum[..., None]
            n = n / n.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        if (hs, ws) == (h, w):
            return n
        nu = F.interpolate(n.permute(2, 0, 1)[None], size=(h, w), mode="bilinear", align_corners=False)[0].permute(1, 2, 0)
        zu = F.interpolate(zl[None, None], size=(h, w), mode="bilinear", align_corners=False)[0, 0]
        st = int(round(s))
        acc = torch.zeros_like(nu)
        wsum = torch.zeros_like(z)
        for dy in (-st, 0, st):
            for dx in (-st, 0, st):
                wgt = torch.exp(-((sh(zu, dy, dx) - z) / (rel * z)) ** 2) + 1e-4
                acc += wgt[..., None] * sh(nu, dy, dx)
                wsum += wgt
        n = acc / wsum[..., None]
        return n / n.norm(dim=-1, keepdim=True).clamp(min=1e-8)

    @staticmethod
    def normals(P):
        du = torch.zeros_like(P)
        dv = torch.zeros_like(P)
        du[:, 1:-1] = (P[:, 2:] - P[:, :-2]) / 2
        dv[1:-1] = (P[2:] - P[:-2]) / 2
        du[:, 0], du[:, -1], dv[0], dv[-1] = du[:, 1], du[:, -2], dv[1], dv[-2]
        nrm = torch.cross(dv, du, dim=-1)
        nrm = nrm / nrm.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return torch.where((nrm * P).sum(-1, keepdim=True) > 0, -nrm, nrm)

    @staticmethod
    def visibility(P, Lp, z, f_s, cx, cy, steps=16, thickness=0.15):
        hs, ws = z.shape
        vis = torch.ones(hs, ws, device=z.device)
        zmap = z[None, None]
        for t in torch.linspace(0.08, 0.92, steps).tolist():
            Q = P + t * (Lp - P)
            qz = Q[..., 2].clamp(min=1e-3)
            u = Q[..., 0] / qz * f_s + cx
            v = Q[..., 1] / qz * f_s + cy
            grid = torch.stack((u / (ws - 1) * 2 - 1, v / (hs - 1) * 2 - 1), -1)[None]
            zs = F.grid_sample(zmap, grid, mode="bilinear", padding_mode="border", align_corners=True)[0, 0]
            bias = 0.03 * qz
            occ = torch.sigmoid((qz - zs - bias) / (0.02 * qz)) * torch.sigmoid((zs + thickness - qz) / (0.02 * qz))
            vis = vis * (1 - occ)
        return gaussian_blur(vis[None, None], 2.0)[0, 0]

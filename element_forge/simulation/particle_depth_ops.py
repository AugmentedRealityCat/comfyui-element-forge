"""Particle surface depth for LTX guidance. Relative inverse depth, larger is nearer."""
import numpy as np
import cv2


def crop_frames(frames, raster):
    out = []
    yy, xx = np.mgrid[:raster.h, :raster.w].astype(np.float32)
    for i, frame in enumerate(frames):
        scale = raster.scale(i)
        origin = raster.org[min(i, len(raster.org)-1)] if raster.window is not None else (0, 0)
        out.append(cv2.remap(frame, (xx / scale + float(origin[0])).astype(np.float32), (yy / scale + float(origin[1])).astype(np.float32),
                             cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT))
    return np.stack(out)


def particle_surfaces(sim, raster, pt, minimum_radius=1.5):
    """Nearest particle surface and separate coverage. No opacity or density in Z.

    Sphere sprites are an approximation of transparent particles, not volumetric depth.
    Uses current camera-adjusted zd when present, rather than birth-space z.
    """
    rec, P = sim['rec'], sim['P']
    zs = rec.get('zd', rec['z'])
    depth = np.zeros((sim['n'], raster.h, raster.w), np.float32)
    coverage = np.zeros_like(depth)
    for i in range(sim['n']):
        pt.interrupted()
        ids = np.flatnonzero(np.isfinite(rec['x'][i]) & np.isfinite(zs[i]))
        alpha = pt.frame_alpha(P, rec, i, ids, raster, sim['edge_fade'], premask=False)
        rx, ry = raster.map(i, rec['x'][i, ids], rec['y'][i, ids])
        radii = np.maximum(rec['size'][i, ids] * raster.scale(i) * .6, minimum_radius)
        # Near surfaces overwrite farther surfaces; their coverage remains independent.
        for j in np.argsort(zs[i, ids]):
            if alpha[j] <= .02:
                continue
            x, y, r = float(rx[j]), float(ry[j]), float(radii[j])
            x0, x1 = max(0, int(np.floor(x-r-1))), min(raster.w, int(np.ceil(x+r+2)))
            y0, y1 = max(0, int(np.floor(y-r-1))), min(raster.h, int(np.ceil(y+r+2)))
            if x1 <= x0 or y1 <= y0:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1]
            a = np.clip(r + .5 - np.hypot(xx-x, yy-y), 0, 1) * min(float(alpha[j]), 1)
            valid = a > .02
            zview, cview = depth[i, y0:y1, x0:x1], coverage[i, y0:y1, x0:x1]
            zview[valid] = zs[i, ids[j]]
            cview[valid] = 1 - (1-cview[valid]) * (1-a[valid])
    return depth, coverage


def combine_depth(scene, particle, coverage, object_mask=None, tolerance=.01):
    """One clip-wide scale for both branches; Z-test before masked guide composition."""
    scene = np.asarray(scene, np.float32)
    particle = np.asarray(particle, np.float32)
    coverage = np.clip(np.asarray(coverage, np.float32), 0, 1)
    if scene.shape != particle.shape or scene.shape != coverage.shape:
        raise ValueError('Scene depth, particle depth and coverage must have identical frame/size alignment.')
    valid = (coverage > .02) & np.isfinite(particle)
    sv = scene[np.isfinite(scene)]
    pv = particle[valid]
    if not len(sv):
        raise ValueError('Scene depth contains no finite values.')
    lo = min(float(sv.min()), float(pv.min()) if len(pv) else float(sv.min()))
    hi = max(float(sv.max()), float(pv.max()) if len(pv) else float(sv.max()))
    span = max(hi-lo, 1e-6)
    norm = lambda x: .05 + .95 * np.clip((np.nan_to_num(x, nan=lo)-lo)/span, 0, 1)
    visible = valid & np.isfinite(scene) & (particle >= scene - float(tolerance)*span)
    cov = coverage * visible
    scene_n, particle_n = norm(scene), norm(particle)
    obj = np.ones_like(scene) if object_mask is None else np.clip(object_mask, 0, 1)
    if obj.shape != scene.shape:
        raise ValueError('Object mask must align with depth frames.')
    # The guide is an image representation. Raw Z is available separately.
    obj_guide = scene_n * obj
    part_guide = particle_n * cov
    merged = obj_guide * (1-cov) + part_guide
    return dict(scene=obj_guide, particle=part_guide, merged=merged, coverage=cov,
                raw_particle_depth=particle, raw_coverage=coverage,
                depth_range=[lo, hi], hidden_fraction=float(np.count_nonzero(valid & ~visible)/max(np.count_nonzero(valid),1)))


def make_guides(sim, scene_depth, object_mask, raster, pt, minimum_radius=1.5, tolerance=.01):
    def aligned(a):
        a = np.asarray(a, np.float32)
        if not len(a):
            raise ValueError('An empty depth or mask sequence cannot guide a clip.')
        return np.stack([cv2.resize(a[min(i,len(a)-1)], (sim['W'],sim['H']), interpolation=cv2.INTER_LINEAR)
                         for i in range(sim['n'])])
    raw, cov = particle_surfaces(sim, raster, pt, minimum_radius)
    scene = crop_frames(aligned(scene_depth), raster)
    mask = crop_frames(aligned(object_mask), raster) if object_mask is not None else None
    result = combine_depth(scene, raw, cov, mask, tolerance)
    result['object_mask'] = np.ones_like(scene) if mask is None else mask
    return result

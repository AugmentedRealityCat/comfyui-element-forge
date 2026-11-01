"""Keep the selected original surface while fading the effect outside its edge."""
import cv2
import numpy as np
import torch

from ..tracking.mask_controls import fit_mask


def visibility_outside(mask, grow_pixels=1, feather_pixels=2.0, threshold=0.5):
    result = []
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow_pixels * 2 + 1, grow_pixels * 2 + 1))
    for frame in mask.detach().cpu().numpy():
        solid = (frame >= threshold).astype(np.uint8)
        if grow_pixels:
            solid = cv2.dilate(solid, kernel)
        outside = 1 - solid
        if feather_pixels > 0 and solid.any():
            distance = cv2.distanceTransform(outside, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
            t = np.clip(distance / feather_pixels, 0, 1)
            outside = t * t * (3 - 2 * t)
        result.append(outside.astype(np.float32))
    return torch.from_numpy(np.stack(result))


class EFObjectProtection:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'object_mask': ('MASK',),
            'grow_pixels': ('INT', {'default': 1, 'min': 0, 'max': 128}),
            'feather_pixels': ('FLOAT', {'default': 2.0, 'min': 0.0, 'max': 128.0, 'step': 0.5}),
            'threshold': ('FLOAT', {'default': 0.5, 'min': 0.001, 'max': 1.0, 'step': 0.01}),
        }, 'optional': {'visibility': ('MASK',)}}

    RETURN_TYPES = ('MASK', 'MASK')
    RETURN_NAMES = ('effect_visibility', 'protected')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('Zero effect inside the original object. Feathering is outside only. '
                   'Connect effect_visibility to EF Place Layer holdout. Optional visibility multiplies '
                   'the particle region and depth visibility. This does not repair inaccurate input masks.')

    def run(self, object_mask, grow_pixels=1, feather_pixels=2.0, threshold=0.5, visibility=None):
        mask = object_mask if object_mask.ndim == 3 else object_mask[None]
        n = max(len(mask), len(visibility) if visibility is not None and visibility.ndim == 3 else 1)
        h, w = mask.shape[-2:]
        outside = visibility_outside(fit_mask(mask, n, h, w), grow_pixels, feather_pixels, threshold)
        protected = 1 - outside
        if visibility is not None:
            outside *= fit_mask(visibility, n, h, w)
        return outside, protected


class EFRestoreProtectedObject:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'composite': ('IMAGE',), 'plate': ('IMAGE',), 'protected': ('MASK',)}}

    RETURN_TYPES = ('IMAGE',)
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('Optional final restoration after glow. Use the same graded plate as the comp. '
                   'Fully protected pixels are exactly the original plate pixels, including colour. '
                   'Leave this node out if light should still alter the protected surface.')

    def run(self, composite, plate, protected):
        if composite.shape != plate.shape:
            raise ValueError('Composite and plate must have identical frame count, size and channels.')
        n, h, w = composite.shape[:3]
        keep = fit_mask(protected, n, h, w).to(device=composite.device, dtype=composite.dtype)[..., None]
        return (composite * (1 - keep) + plate.to(composite.device) * keep,)

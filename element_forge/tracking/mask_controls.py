"""Explicit mask exclusions and reference-frame selection. No generated geometry."""
import json
import re

import torch


def fit_mask(mask, count, height, width):
    mask = mask.detach().cpu().float()
    if mask.ndim == 2:
        mask = mask.unsqueeze(0)
    if mask.ndim != 3 or mask.shape[0] not in (1, count):
        raise ValueError('A mask must have one frame or exactly the clip frame count.')
    if mask.shape[1:] != (height, width):
        mask = torch.nn.functional.interpolate(mask[:, None], size=(height, width),
                                               mode='bilinear', align_corners=False)[:, 0]
    return mask.expand(count, -1, -1).clamp(0, 1)


def subtract_masks(selected, excluded):
    return selected.clamp(0, 1) * (1 - excluded.clamp(0, 1))


def track_from_frame(images, initial, reference_frame, track):
    """Track both directions, retain the actual selection at the anchor frame."""
    n = len(images)
    if not 0 <= reference_frame < n:
        raise ValueError(f'reference_frame must be between 0 and {n - 1}.')
    parts = []
    if reference_frame:
        before = track(images[:reference_frame + 1].flip(0), initial).flip(0)
        parts.append(before[:-1])
    parts.append(initial)
    if reference_frame < n - 1:
        parts.append(track(images[reference_frame:], initial)[1:])
    return torch.cat(parts, dim=0)


class EFMaskPoint:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'x': ('FLOAT', {'default': 0.5, 'min': 0.0, 'max': 32768.0, 'step': 0.001}),
            'y': ('FLOAT', {'default': 0.5, 'min': 0.0, 'max': 32768.0, 'step': 0.001}),
            'action': (['include', 'exclude'],),
            'coordinates': (['normalized', 'pixels'], {'default': 'normalized'}),
        }, 'optional': {'previous': ('EF_MASK_POINTS',)}}

    RETURN_TYPES = ('EF_MASK_POINTS',)
    FUNCTION = 'make'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('A positive or negative selection point at the reference frame. Chain nodes for more points. '
                   'Normalized coordinates run from 0 to 1 across the original image, not the generation crop.')

    def make(self, x, y, action, coordinates='normalized', previous=None):
        if coordinates == 'normalized' and (x > 1 or y > 1):
            raise ValueError('Normalized point coordinates must be between 0 and 1.')
        return ((list(previous or []) + [{'x': x, 'y': y, 'action': action, 'coordinates': coordinates}]),)


class EFSelectObjectMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'images': ('IMAGE',), 'model': ('MODEL',),
            'reference_frame': ('INT', {'default': 0, 'min': 0, 'max': 100000,
                                       'tooltip': 'Select a frame where the object is visible. Tracking runs both ways.'}),
            'include_words': ('STRING', {'default': '', 'multiline': True,
                                        'tooltip': 'One object per line or semicolon. Used if no positive points or initial mask are supplied.'}),
            'exclude_words': ('STRING', {'default': '', 'multiline': True,
                                        'tooltip': 'One excluded object per line or semicolon, e.g. hand; handle; sheath. Tracked separately and subtracted.'}),
            'threshold': ('FLOAT', {'default': 0.4, 'min': 0.0, 'max': 1.0, 'step': 0.05}),
            'refine_iterations': ('INT', {'default': 1, 'min': 1, 'max': 10}),
            'track_video': ('BOOLEAN', {'default': True}),
        }, 'optional': {'clip': ('CLIP',), 'points': ('EF_MASK_POINTS',),
                        'initial_mask': ('MASK',), 'exclude_mask': ('MASK',)}}

    RETURN_TYPES = ('MASK', 'MASK', 'IMAGE', 'STRING')
    RETURN_NAMES = ('selection', 'excluded', 'preview', 'report')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('SAM3 selection with explicit exclusions. Positive points take precedence over include words '
                   'to avoid text detection adding excluded objects back. Check the preview before rendering. '
                   'An initial mask is interpreted at reference_frame. Exclude mask may cover the full clip.')

    def run(self, images, model, reference_frame, include_words='', exclude_words='', threshold=0.4,
            refine_iterations=1, track_video=True, clip=None, points=None, initial_mask=None, exclude_mask=None):
        from comfy_extras.nodes_sam3 import SAM3_Detect, SAM3_VideoTrack, SAM3_TrackToMask

        n, h, w = images.shape[:3]
        if not 0 <= reference_frame < n:
            raise ValueError(f'reference_frame must be between 0 and {n - 1}.')
        frame = images[reference_frame:reference_frame + 1]
        positive, negative = [], []
        for p in points or []:
            x, y = float(p['x']), float(p['y'])
            if p['coordinates'] == 'normalized':
                x, y = x * (w - 1), y * (h - 1)
            if not 0 <= x < w or not 0 <= y < h:
                raise ValueError('A selection point is outside the original image.')
            (positive if p['action'] == 'include' else negative).append({'x': x, 'y': y})

        def detect(pos=None, neg=None, word=None):
            conditioning = None
            if word:
                if clip is None:
                    raise ValueError('Word selection needs the CLIP output of the SAM3 loader.')
                conditioning = clip.encode_from_tokens_scheduled(clip.tokenize(word))
            result = SAM3_Detect.execute(model=model, image=frame, conditioning=conditioning,
                                        positive_coords=json.dumps(pos or []), negative_coords=json.dumps(neg or []),
                                        threshold=threshold, refine_iterations=refine_iterations, individual_masks=False)[0]
            return fit_mask(result, 1, h, w)

        def words_mask(text):
            union = torch.zeros((1, h, w))
            for word in filter(None, (v.strip() for v in re.split(r'[;\n]+', text))):
                union = torch.maximum(union, detect(word=word))
            return union

        if initial_mask is not None:
            selected = fit_mask(initial_mask, n, h, w)[reference_frame:reference_frame + 1]
            source = 'initial mask'
        elif positive:
            selected = detect(positive, negative)
            source = 'positive and negative points'
        elif include_words.strip():
            selected = words_mask(include_words)
            source = 'include words'
        else:
            raise ValueError('Supply positive points, include words, or an initial mask.')
        excluded = words_mask(exclude_words)
        # For a word/mask selection, negative points select objects to subtract explicitly.
        # In point mode they are native negative constraints, not a second text union.
        if not positive or initial_mask is not None:
            for p in negative:
                excluded = torch.maximum(excluded, detect([p]))
        selected = subtract_masks(selected, excluded)

        def track(batch, mask):
            if not torch.any(mask > 0.5):
                return torch.zeros((len(batch), h, w))
            data = SAM3_VideoTrack.execute(images=batch, model=model, initial_mask=mask,
                                          detection_threshold=threshold, max_objects=1, detect_interval=1)[0]
            return fit_mask(SAM3_TrackToMask.execute(track_data=data, object_indices='')[0], len(batch), h, w)

        if track_video and n > 1:
            selected = track_from_frame(images, selected, reference_frame, track)
            excluded = track_from_frame(images, excluded, reference_frame, track)
            shown = images
        else:
            shown = frame
        count = len(selected)
        if exclude_mask is not None:
            external = fit_mask(exclude_mask, n, h, w)
            if count == 1:
                external = external[reference_frame:reference_frame + 1]
            excluded = torch.maximum(excluded, external)
        selected = subtract_masks(selected, excluded)
        preview = shown.detach().cpu().float()[..., :3].clone()
        tint = selected[..., None] * torch.tensor([0.1, 0.9, 0.35]) + excluded[..., None] * torch.tensor([1.0, 0.1, 0.1])
        opacity = torch.maximum(selected, excluded)[..., None] * 0.45
        preview = preview * (1 - opacity) + tint * 0.45
        return selected, excluded, preview.clamp(0, 1), json.dumps({
            'reference_frame': reference_frame, 'frames': count, 'source': source,
            'positive_points': len(positive), 'negative_points': len(negative),
            'exclude_words': exclude_words, 'empty_frames': torch.where(selected.flatten(1).sum(1) == 0)[0].tolist(),
            'note': 'Mask prediction, not an exact boundary guarantee. Inspect all frames before generation.'})

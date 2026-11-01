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


def parse_points(text):
    out = []
    for part in filter(None, (p.strip() for p in re.split(r'[;\n]+', text or ''))):
        xy = [float(v) for v in re.split(r'[,\s]+', part) if v]
        if len(xy) != 2:
            raise ValueError(f'A leave-out point is "x, y" in pixels of the clip, not "{part}".')
        out.append({'x': xy[0], 'y': xy[1]})
    return out


def split_words(text):
    return [w for w in (v.strip() for v in re.split(r'[;\n,]+', text or '')) if w]


class EFLeaveOutParts:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'image': ('IMAGE', {'tooltip': 'The frame the object was clicked on (the first frame in the app).'}),
            'model': ('MODEL',),
            'points': ('STRING', {'default': '', 'tooltip': 'Parts to leave out as "x, y; x, y" in pixels of the clip. The app sets them by Alt-click.'}),
            'words': ('STRING', {'default': '', 'tooltip': 'Parts to leave out as words, e.g. "hand; handle; sheath".'}),
            'threshold': ('FLOAT', {'default': 0.4, 'min': 0.0, 'max': 1.0, 'step': 0.05}),
        }, 'optional': {'clip': ('CLIP', {'tooltip': 'The CLIP of the SAM3 loader, for the words.'}),
                        'keep_coords': ('STRING', {'forceInput': True, 'tooltip': 'The object\'s own point(s) as SAM3 JSON (EF Points positive_coords): kept apart from the parts.'})}}

    RETURN_TYPES = ('MASK', 'STRING')
    RETURN_NAMES = ('left_out', 'negative_coords')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('Parts of the clicked object to leave out (a hand, a handle): their mask on the reference frame for EF Leave '
                   'Out (track), and the points as negative points for the click\'s SAM3 Detect. Nothing set: an empty mask.')

    def run(self, image, model, points='', words='', threshold=0.4, clip=None, keep_coords=None):
        h, w = image.shape[1:3]
        pts, names = parse_points(points), split_words(words)
        neg = json.dumps([{'x': round(p['x']), 'y': round(p['y'])} for p in pts])
        if not pts and not names:
            return torch.zeros((1, h, w)), neg
        from comfy_extras.nodes_sam3 import SAM3_Detect
        keep = json.loads(keep_coords) if keep_coords else []
        frame = image[:1]

        def detect(pos=None, neg_=None, word=None):
            cond = None
            if word:
                if clip is None:
                    raise ValueError('Leaving out by a word needs the CLIP output of the SAM3 loader.')
                cond = clip.encode_from_tokens_scheduled(clip.tokenize(word))
            m = SAM3_Detect.execute(model=model, image=frame, conditioning=cond, positive_coords=json.dumps(pos or []),
                                    negative_coords=json.dumps(neg_ or []), threshold=threshold, refine_iterations=2,
                                    individual_masks=False)[0]
            return fit_mask(m, 1, h, w)

        out = torch.zeros((1, h, w))
        for p in pts:
            if not (0 <= p['x'] < w and 0 <= p['y'] < h):
                raise ValueError(f'A leave-out point ({p["x"]:.0f}, {p["y"]:.0f}) is outside the clip ({w} x {h}).')
            out = torch.maximum(out, detect([{'x': round(p['x']), 'y': round(p['y'])}], keep))
        for word in names:
            out = torch.maximum(out, detect(word=word))
        return out, neg


class EFLeaveOutTrack:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'mask': ('MASK', {'tooltip': 'The object\'s mask per frame (its track).'}),
            'left_out': ('MASK', {'tooltip': 'The parts to leave out on the reference frame (EF Leave Out Parts), tracked here; or of every frame (EF Mask At Frame), taken out as they are.'}),
            'images': ('IMAGE', {'tooltip': 'The clip.'}),
            'model': ('MODEL',),
            'reference_frame': ('INT', {'default': 0, 'min': 0, 'max': 100000, 'tooltip': 'The frame of the leave-out mask (the app: the first).'}),
        }}

    RETURN_TYPES = ('MASK', 'MASK')
    RETURN_NAMES = ('mask', 'left_out')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('The object\'s mask without the parts left out: they are tracked through the clip (SAM3, both ways from the '
                   'reference frame) and subtracted. Nothing left out: the mask goes through unchanged, without tracking.')

    def run(self, mask, left_out, images, model, reference_frame=0):
        n, h, w = images.shape[:3]
        sel = fit_mask(mask, n, h, w) if mask.shape[0] in (1, n) else fit_mask(mask[:1], n, h, w)
        if n > 1 and left_out.ndim == 3 and left_out.shape[0] == n:
            part = fit_mask(left_out, n, h, w)
            if not torch.any(part > 0.5):
                return mask, torch.zeros((1, h, w))
            return subtract_masks(sel, part), part
        part = fit_mask(left_out[:1], 1, h, w)
        if not torch.any(part > 0.5):
            return mask, torch.zeros((1, h, w))
        from comfy_extras.nodes_sam3 import SAM3_TrackToMask, SAM3_VideoTrack

        def track(batch, m):
            data = SAM3_VideoTrack.execute(images=batch, model=model, initial_mask=m, detection_threshold=0.5, max_objects=1,
                                           detect_interval=1)[0]
            return fit_mask(SAM3_TrackToMask.execute(track_data=data, object_indices='')[0], len(batch), h, w)

        ref = min(max(int(reference_frame), 0), n - 1)
        part = track_from_frame(images, part, ref, track) if n > 1 else part
        clean = subtract_masks(sel, part)
        before, after = float(sel.sum()), float(clean.sum())
        if before > 0 and after < 0.02 * before:
            raise ValueError('Leaving out took away the whole object in every frame: click the part itself (not the object) '
                             'or use a word for the part only.')
        return clean, part


def mask_mode(frame, add_points='', add_words=''):
    return int(frame or 0) > 0 or bool(parse_points(add_points)) or bool(split_words(add_words))


class EFMaskMode:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'mask_frame': ('INT', {'default': 0, 'min': 0, 'max': 100000}),
                             'add_points': ('STRING', {'default': ''}), 'add_words': ('STRING', {'default': ''})}}

    RETURN_TYPES = ('BOOLEAN',)
    RETURN_NAMES = ('at_frame',)
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = 'True when the mask is set on a later frame or with added points or words (EF Mask At Frame).'

    def run(self, mask_frame, add_points='', add_words=''):
        return (mask_mode(mask_frame, add_points, add_words),)


class EFMaskAtFrame:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'images': ('IMAGE', {'tooltip': 'The clip.'}),
            'model': ('MODEL',),
            'mask_frame': ('INT', {'default': 0, 'min': 0, 'max': 100000, 'tooltip': 'The frame the points are set on, where the object is fully visible. Tracking runs both ways from it.'}),
            'add_points': ('STRING', {'default': '', 'tooltip': 'Points on the object, "x, y; x, y" in pixels of the clip on the mask frame.'}),
            'word': ('STRING', {'default': '', 'tooltip': 'The object word ("What is it?").'}),
            'add_words': ('STRING', {'default': '', 'tooltip': 'More objects or parts to take, e.g. "blade; tip".'}),
            'leave_points': ('STRING', {'default': '', 'tooltip': 'Points on parts to leave out, on the mask frame.'}),
            'leave_words': ('STRING', {'default': '', 'tooltip': 'Parts to leave out as words, e.g. "hand; handle".'}),
            'threshold': ('FLOAT', {'default': 0.4, 'min': 0.0, 'max': 1.0, 'step': 0.05}),
            'track_video': ('BOOLEAN', {'default': True, 'tooltip': 'Off: the mask frame alone (a quick look before tracking).'}),
            'use_own_mask': ('BOOLEAN', {'default': False, 'tooltip': 'On: the painted mask (own_mask) is the object on the mask frame.'}),
        }, 'optional': {'clip': ('CLIP',),
                        'a_coords': ('STRING', {'forceInput': True, 'tooltip': 'Point A (EF Points positive_coords): one more point to add when the mask frame is the first.'}),
                        'own_mask': ('MASK', {'tooltip': 'A painted mask of the object on the mask frame; used instead of the points to add.'})}}

    RETURN_TYPES = ('MASK', 'MASK')
    RETURN_NAMES = ('mask', 'left_out')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('The object on a frame of your choice: points and words to add, points and words to leave out; both tracked '
                   'through the clip from that frame. mask is all that was added, left_out the parts to take out of it '
                   '(EF Leave Out (track)).')

    def run(self, images, model, mask_frame=0, add_points='', word='', add_words='', leave_points='', leave_words='',
            threshold=0.4, track_video=True, use_own_mask=False, clip=None, a_coords=None, own_mask=None):
        from comfy_extras.nodes_sam3 import SAM3_Detect, SAM3_TrackToMask, SAM3_VideoTrack
        n, h, w = images.shape[:3]
        ref = min(max(int(mask_frame), 0), n - 1)
        frame = images[ref:ref + 1]

        def pts_of(text):
            out = []
            for p in parse_points(text):
                if not (0 <= p['x'] < w and 0 <= p['y'] < h):
                    raise ValueError(f'A mask point ({p["x"]:.0f}, {p["y"]:.0f}) is outside the clip ({w} x {h}).')
                out.append({'x': round(p['x']), 'y': round(p['y'])})
            return out

        pos, neg = pts_of(add_points), pts_of(leave_points)
        if ref == 0 and a_coords:
            pos = json.loads(a_coords) + pos
        words = split_words(word) + split_words(add_words)

        def detect(p=None, ng=None, text=None):
            cond = None
            if text:
                if clip is None:
                    raise ValueError('Words need the CLIP output of the SAM3 loader.')
                cond = clip.encode_from_tokens_scheduled(clip.tokenize(text))
            m = SAM3_Detect.execute(model=model, image=frame, conditioning=cond, positive_coords=json.dumps(p or []),
                                    negative_coords=json.dumps(ng or []), threshold=threshold, refine_iterations=2,
                                    individual_masks=False)[0]
            return fit_mask(m, 1, h, w)

        if use_own_mask and own_mask is not None:
            sel = fit_mask(own_mask[:1], 1, h, w)
        else:
            sel = detect(pos, neg) if pos else torch.zeros((1, h, w))
            for t in words:
                sel = torch.maximum(sel, detect(text=t))
        if not torch.any(sel > 0.5):
            raise ValueError(f'Nothing found on the mask frame ({ref}): click the object there (or add a word) first.')
        left = torch.zeros((1, h, w))
        for p in neg:
            left = torch.maximum(left, detect([p], pos))
        for t in split_words(leave_words):
            left = torch.maximum(left, detect(text=t))
        if not track_video or n == 1:
            return sel, left

        def track(batch, m):
            if not torch.any(m > 0.5):
                return torch.zeros((len(batch), h, w))
            data = SAM3_VideoTrack.execute(images=batch, model=model, initial_mask=m, detection_threshold=0.5, max_objects=1,
                                           detect_interval=1)[0]
            return fit_mask(SAM3_TrackToMask.execute(track_data=data, object_indices='')[0], len(batch), h, w)

        return track_from_frame(images, sel, ref, track), track_from_frame(images, left, ref, track)

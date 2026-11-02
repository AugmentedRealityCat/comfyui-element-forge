import copy
import json

import numpy as np
import torch

from . import particles_node as engine
from .particle_depth_ops import inner_edge, make_guides, path_lines


class EFParticleDepthGuides:
    @classmethod
    def INPUT_TYPES(cls):
        fields = copy.deepcopy(engine.EFParticles.INPUT_TYPES())
        fields['required']['seed'][1]['control_after_generate'] = True
        fields['required']['depth'] = fields['optional'].pop('depth')
        fields['required']['depth'][1]['tooltip'] = 'Full scene inverse depth, larger = nearer. Do not multiply by the emitter mask.'
        fields['optional']['mask'][1]['tooltip'] = 'Emitter selection. Only this object emits particles. Scene depth and collisions remain intact outside this mask.'
        for key in ('sprite', 'sprite_alpha', 'direct_look', 'inpaint_sigmas', 'track_count'):
            fields['optional'].pop(key)
        fields['required'].update({
            'guide_content': (['selected object', 'full scene'], {'default': 'selected object',
                              'tooltip': 'What LTX sees in the depth guide. Independent of the emitter mask. Full scene may also make LTX reconstruct the background.'}),
            'object_shape': (['full object', 'inner edge'], {'default': 'full object'}),
            'edge_width': ('INT', {'default': 2, 'min': 1, 'max': 64,
                                 'tooltip': 'Inner band width in guide pixels. Particle guidance stays unchanged.'}),
            'minimum_radius': ('FLOAT', {'default': 1.5, 'min': 0.0, 'max': 64.0, 'step': 0.5}),
            'depth_tolerance': ('FLOAT', {'default': 0.01, 'min': 0.0, 'max': 1.0, 'step': 0.001}),
        })
        return fields

    RETURN_TYPES = ('IMAGE', 'IMAGE', 'IMAGE', 'MASK', 'IMAGE', 'MASK', 'STRING')
    RETURN_NAMES = ('object_guide', 'particle_guide', 'merged_guide', 'visible_coverage',
                    'raw_particle_depth', 'raw_coverage', 'report')
    FUNCTION = 'run'
    CATEGORY = 'Element Forge/Tools'
    DESCRIPTION = ('Experimental depth guidance for particle sprites. Merged and separate outputs share one '
                   'clip-wide inverse-depth scale. Larger values are nearer. Not volumetric depth. '
                   'Use the same seed and settings as EF Particles. No extra model required.')

    def run(self, depth, guide_content='selected object', object_shape='full object', edge_width=2, minimum_radius=1.5,
            depth_tolerance=0.01, window=None, **simulation):
        sim = engine.setup(depth=depth, window=window, **simulation)
        mask = simulation.get('mask')
        guide_mask = None if guide_content == 'full scene' or mask is None else engine._mask3(mask)
        out = make_guides(sim, engine._np(depth)[..., 0], guide_mask,
                          engine.pt.Raster(sim['W'], sim['H'], window), engine.pt,
                          minimum_radius, depth_tolerance)
        if object_shape == 'inner edge':
            if guide_content == 'full scene':
                raise ValueError('Inner-edge guidance is for the selected object. Choose full object with a full-scene guide.')
            if mask is None:
                raise ValueError('Inner-edge guidance needs an object mask.')
            out['scene'] *= inner_edge(out['object_mask'], edge_width)
            out['merged'] = np.where(out['coverage'] > 0.001, out['particle'], out['scene'])
        if sim['paths'] is not None:
            lines = path_lines(sim['paths'], engine.pt.Raster(sim['W'], sim['H'], window), engine.pt, sim['n'], sim['P'])
            out['particle'], out['merged'] = np.maximum(out['particle'], lines), np.maximum(out['merged'], lines)
        rgb = lambda key: torch.from_numpy(np.repeat(out[key][..., None], 3, -1))
        return (rgb('scene'), rgb('particle'), rgb('merged'), torch.from_numpy(out['coverage']),
                rgb('raw_particle_depth'), torch.from_numpy(out['raw_coverage']),
                json.dumps({'depth_range': out['depth_range'], 'hidden_fraction': out['hidden_fraction'],
                            'object_shape': object_shape, 'guide_content': guide_content,
                            'scene_depth_for_simulation': 'full scene, independent of emitter mask',
                            'z_convention': 'relative inverse depth, larger nearer',
                            'geometry': 'particle sprite surfaces, not volumes'}))

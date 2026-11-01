import importlib
from pathlib import Path
import sys
import types
import unittest

import torch

ROOT = Path(__file__).resolve().parents[1] / 'element_forge'
package = types.ModuleType('_ef_mask_tests')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
m = importlib.import_module(package.__name__ + '.tracking.mask_controls')
p = importlib.import_module(package.__name__ + '.compositing.object_protection')
d = importlib.import_module(package.__name__ + '.simulation.particle_depth_node')


class MaskTests(unittest.TestCase):
    def test_track_order_and_anchor(self):
        images = torch.arange(5.)[:, None, None, None].expand(5, 2, 3, 3)
        initial = torch.full((1, 2, 3), 0.9)
        calls = []
        def tracker(batch, mask):
            calls.append(batch[:, 0, 0, 0].tolist())
            return batch[..., 0] / 10
        out = m.track_from_frame(images, initial, 2, tracker)
        self.assertEqual(calls, [[2, 1, 0], [2, 3, 4]])
        torch.testing.assert_close(out[:, 0, 0], torch.tensor([0., .1, .9, .3, .4]))

    def test_track_boundaries_no_duplicate_frame(self):
        images = torch.zeros((4, 2, 2, 3))
        for anchor in (0, 3):
            out = m.track_from_frame(images, torch.ones((1, 2, 2)), anchor,
                                     lambda batch, mask: torch.ones((len(batch), 2, 2)))
            self.assertEqual(out.shape, (4, 2, 2))

    def test_mask_frame_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            m.fit_mask(torch.ones(2, 3, 4), 4, 3, 4)

    def test_exclusions_never_add_pixels(self):
        selected = torch.rand(3, 8, 8)
        excluded = torch.zeros_like(selected); excluded[:, 1:5, 1:5] = 1
        out = m.subtract_masks(selected, excluded)
        self.assertTrue(torch.all(out <= selected))
        self.assertEqual(out[:, 1:5, 1:5].count_nonzero().item(), 0)

    def test_point_chain_does_not_mutate_previous(self):
        first = m.EFMaskPoint().make(.2, .3, 'include')[0]
        second = m.EFMaskPoint().make(.4, .5, 'exclude', previous=first)[0]
        self.assertEqual(len(first), 1)
        self.assertEqual([x['action'] for x in second], ['include', 'exclude'])
        with self.assertRaises(ValueError):
            m.EFMaskPoint().make(2, .1, 'include')

    def test_feather_never_leaks_into_protected_surface(self):
        mask = torch.zeros((1, 17, 17)); mask[:, 6:11, 6:11] = 1
        outside, protected = p.EFObjectProtection().run(mask, grow_pixels=1, feather_pixels=3)
        self.assertEqual(outside[:, 5:12, 6:11].count_nonzero().item(), 0)
        self.assertTrue(0 < outside[0, 4, 8] < 1)
        self.assertEqual(outside[0, 0, 0].item(), 1)
        torch.testing.assert_close(outside + protected, torch.ones_like(mask))

    def test_restoration_is_exact_after_glow(self):
        plate = torch.rand(3, 8, 8, 3)
        comp = torch.rand_like(plate) + 4
        protected = torch.zeros((1, 8, 8)); protected[:, 2:6, 2:6] = 1
        out = p.EFRestoreProtectedObject().run(comp, plate, protected)[0]
        self.assertTrue(torch.equal(out[:, 2:6, 2:6], plate[:, 2:6, 2:6]))
        self.assertTrue(torch.equal(out[:, 0], comp[:, 0]))

    def test_empty_and_full_protection(self):
        for value in (0, 1):
            out, keep = p.EFObjectProtection().run(torch.full((1, 8, 8), float(value)))
            self.assertTrue(torch.all(out == 1 - value))
            self.assertTrue(torch.all(keep == value))

    def test_depth_node_regular_controls_and_edge_output(self):
        fields = d.EFParticleDepthGuides.INPUT_TYPES()
        args = {k: spec[1]['default'] if len(spec) > 1 and 'default' in spec[1] else spec[0][0]
                for k, spec in fields['required'].items() if k not in ('plate', 'depth')}
        self.assertNotIn('simulation', fields['required'])
        args.update(preset='magic dust', emitter='object contour', camera='fixed', amount=.1)
        plate = torch.zeros(5, 40, 48, 3)
        depth = torch.full_like(plate, .5)
        mask = torch.zeros(5, 40, 48); mask[:, 10:30, 10:35] = 1
        full = d.EFParticleDepthGuides().run(plate=plate, depth=depth, mask=mask, **args)
        args['object_shape'] = 'inner edge'
        edge = d.EFParticleDepthGuides().run(plate=plate, depth=depth, mask=mask, **args)
        self.assertEqual(full[2].shape, plate.shape)
        self.assertTrue(torch.equal(full[1], edge[1]))
        self.assertLess(edge[0].sum(), full[0].sum())
        self.assertEqual(edge[0][:, 15:25, 15:30].count_nonzero().item(), 0)
        args.update(guide_content='full scene', object_shape='full object')
        scene = d.EFParticleDepthGuides().run(plate=plate, depth=depth, mask=mask, **args)
        self.assertTrue(torch.equal(full[4], scene[4]))
        self.assertTrue(torch.equal(full[5], scene[5]))
        self.assertGreater(scene[0][:, 0, 0].sum().item(), 0)
        self.assertEqual(full[0][:, 0, 0].sum().item(), 0)


if __name__ == '__main__':
    unittest.main()

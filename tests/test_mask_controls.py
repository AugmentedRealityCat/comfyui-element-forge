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


class FakeSAM3:
    calls = []

    class SAM3_Detect:
        @staticmethod
        def execute(model, image, conditioning=None, positive_coords='[]', negative_coords='[]', **kw):
            import json
            FakeSAM3.calls.append(('detect', json.loads(positive_coords), json.loads(negative_coords), conditioning))
            h, w = image.shape[1:3]
            out = torch.zeros((1, h, w))
            for p in json.loads(positive_coords):
                out[0, max(p['y'] - 2, 0):p['y'] + 2, max(p['x'] - 2, 0):p['x'] + 2] = 1
            if conditioning is not None:
                out[0, :, :w // 2] = 1
            return (out,)

    class SAM3_VideoTrack:
        @staticmethod
        def execute(images, model, initial_mask, **kw):
            FakeSAM3.calls.append(('track', len(images)))
            return (initial_mask.expand(len(images), -1, -1),)

    class SAM3_TrackToMask:
        @staticmethod
        def execute(track_data, object_indices=''):
            return (track_data,)


class FakeClip:
    def tokenize(self, word):
        return word

    def encode_from_tokens_scheduled(self, tokens):
        return 'cond:' + tokens


class LeaveOutTests(unittest.TestCase):
    def setUp(self):
        sys.modules['comfy_extras'] = types.ModuleType('comfy_extras')
        sys.modules['comfy_extras.nodes_sam3'] = FakeSAM3
        FakeSAM3.calls = []

    def test_nothing_left_out_runs_no_sam3(self):
        img = torch.zeros((1, 16, 20, 3))
        left, neg = m.EFLeaveOutParts().run(img, None, '', ' ', keep_coords='[{"x": 3, "y": 3}]')
        self.assertEqual((left.shape, float(left.sum()), neg), ((1, 16, 20), 0.0, '[]'))
        mask = torch.ones((5, 16, 20))
        out, part = m.EFLeaveOutTrack().run(mask, left, torch.zeros((5, 16, 20, 3)), None)
        self.assertIs(out, mask)
        self.assertEqual(FakeSAM3.calls, [])

    def test_point_keeps_the_clicked_point_apart(self):
        img = torch.zeros((1, 16, 20, 3))
        left, neg = m.EFLeaveOutParts().run(img, None, '12, 8', '', keep_coords='[{"x": 3, "y": 3}]')
        self.assertEqual(FakeSAM3.calls, [('detect', [{'x': 12, 'y': 8}], [{'x': 3, 'y': 3}], None)])
        self.assertEqual(neg, '[{"x": 12, "y": 8}]')
        self.assertEqual(float(left[0, 8, 12]), 1.0)

    def test_words_need_the_clip_and_are_split(self):
        img = torch.zeros((1, 16, 20, 3))
        with self.assertRaises(ValueError):
            m.EFLeaveOutParts().run(img, None, '', 'hand')
        left, _ = m.EFLeaveOutParts().run(img, None, '', 'hand; handle', clip=FakeClip())
        self.assertEqual([c[3] for c in FakeSAM3.calls], ['cond:hand', 'cond:handle'])
        self.assertEqual(float(left[0, :, :10].min()), 1.0)

    def test_point_outside_the_clip_is_named(self):
        with self.assertRaises(ValueError):
            m.EFLeaveOutParts().run(torch.zeros((1, 16, 20, 3)), None, '25, 4', '')
        with self.assertRaises(ValueError):
            m.parse_points('12; 4')

    def test_track_takes_the_parts_out_of_every_frame(self):
        mask = torch.ones((5, 16, 20))
        part = torch.zeros((1, 16, 20)); part[0, :, :5] = 1
        out, left = m.EFLeaveOutTrack().run(mask, part, torch.zeros((5, 16, 20, 3)), None)
        self.assertEqual(out.shape, (5, 16, 20))
        self.assertEqual(float(out[:, :, :5].max()), 0.0)
        self.assertEqual(float(out[:, :, 5:].min()), 1.0)
        self.assertEqual([c[0] for c in FakeSAM3.calls], ['track'])

    def test_all_left_out_on_the_first_frame_only_is_fine(self):
        mask = torch.zeros((3, 8, 8)); mask[0, :, :4] = 1; mask[1:] = 1
        part = torch.zeros((1, 8, 8)); part[0, :, :4] = 1
        out, _ = m.EFLeaveOutTrack().run(mask, part, torch.zeros((3, 8, 8, 3)), None)
        self.assertEqual(float(out[0].sum()), 0.0)
        self.assertGreater(float(out[1].sum()), 0.0)

    def test_leaving_out_everything_is_an_error(self):
        with self.assertRaises(ValueError):
            m.EFLeaveOutTrack().run(torch.ones((3, 8, 8)), torch.ones((1, 8, 8)), torch.zeros((3, 8, 8, 3)), None)


class MaskAtFrameTests(unittest.TestCase):
    def setUp(self):
        sys.modules['comfy_extras'] = types.ModuleType('comfy_extras')
        sys.modules['comfy_extras.nodes_sam3'] = FakeSAM3
        FakeSAM3.calls = []

    def test_mode(self):
        self.assertFalse(m.mask_mode(0, ' ', ' ; '))
        self.assertTrue(m.mask_mode(3))
        self.assertTrue(m.mask_mode(0, '4, 5'))
        self.assertTrue(m.EFMaskMode().run(0, '', 'blade')[0])

    def test_points_on_a_later_frame_tracked_both_ways(self):
        imgs = torch.arange(5.)[:, None, None, None].expand(5, 16, 20, 3).clone()
        whole, left = m.EFMaskAtFrame().run(imgs, None, mask_frame=3, add_points='4, 4; 12, 8', leave_points='17, 12',
                                             a_coords='[{"x": 1, "y": 1}]')
        detects = [c for c in FakeSAM3.calls if c[0] == 'detect']
        self.assertEqual(detects[0][1:3], ([{'x': 4, 'y': 4}, {'x': 12, 'y': 8}], [{'x': 17, 'y': 12}]))
        self.assertEqual(detects[1][1:3], ([{'x': 17, 'y': 12}], [{'x': 4, 'y': 4}, {'x': 12, 'y': 8}]))
        self.assertEqual([c[1] for c in FakeSAM3.calls if c[0] == 'track'], [4, 2, 4, 2])
        self.assertEqual((whole.shape, left.shape), ((5, 16, 20), (5, 16, 20)))
        self.assertEqual(float(left[0, 12, 17]), 1.0)

    def test_points_and_words_add_up(self):
        imgs = torch.zeros((2, 16, 20, 3))
        whole, _ = m.EFMaskAtFrame().run(imgs, None, mask_frame=1, add_points='16, 8', word='sword', clip=FakeClip(), track_video=False)
        self.assertEqual(float(whole[0, 8, 16]), 1.0)
        self.assertEqual(float(whole[0, 2, 2]), 1.0)

    def test_point_a_counts_on_the_first_frame_only(self):
        imgs = torch.zeros((3, 16, 20, 3))
        m.EFMaskAtFrame().run(imgs, None, mask_frame=0, add_points='4, 4', a_coords='[{"x": 1, "y": 1}]', track_video=False)
        self.assertEqual(FakeSAM3.calls[0][1], [{'x': 1, 'y': 1}, {'x': 4, 'y': 4}])

    def test_words_alone_and_nothing_found(self):
        imgs = torch.zeros((3, 16, 20, 3))
        whole, _ = m.EFMaskAtFrame().run(imgs, None, mask_frame=2, word='sword', add_words='blade', clip=FakeClip(), track_video=False)
        self.assertEqual([c[3] for c in FakeSAM3.calls], ['cond:sword', 'cond:blade'])
        self.assertEqual(whole.shape, (1, 16, 20))
        with self.assertRaises(ValueError):
            m.EFMaskAtFrame().run(imgs, None, mask_frame=2, track_video=False)

    def test_tracked_parts_are_only_taken_out(self):
        mask = torch.ones((4, 8, 8))
        part = torch.zeros((4, 8, 8)); part[2, :, :3] = 1
        out, _ = m.EFLeaveOutTrack().run(mask, part, torch.zeros((4, 8, 8, 3)), None, reference_frame=2)
        self.assertEqual(FakeSAM3.calls, [])
        self.assertEqual(float(out[2, :, :3].max()), 0.0)
        self.assertEqual(float(out[0].min()), 1.0)


class SteadyTests(unittest.TestCase):
    def test_a_dropped_frame_is_filled_and_off_passes(self):
        t = importlib.import_module(package.__name__ + '.compositing.temporal')
        plate = torch.rand((7, 32, 40, 3))
        plate[:] = plate[:1]
        mask = torch.zeros((7, 32, 40)); mask[:, 8:24, 10:30] = 1
        mask[3] = 0
        mask[5, 8:24, 10:12] = 0
        off, = t.EFMaskSteady().steady(mask, plate, 0)
        self.assertIs(off, mask)
        out, = t.EFMaskSteady().steady(mask, plate, 2)
        self.assertEqual(float(out[3, 8:24, 10:30].min()), 1.0)
        self.assertEqual(float(out[5, 8:24, 10:12].min()), 1.0)
        self.assertEqual(float(out[:, :8].max()), 0.0)


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

import importlib.util
from pathlib import Path
import unittest
import numpy as np

PACK = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('particle_depth_ops', PACK/'element_forge/simulation/particle_depth_ops.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class DepthTests(unittest.TestCase):
    def test_occlusion_uses_scene_outside_object_mask(self):
        d = np.array([[[.8,.2]]],np.float32)
        o = m.combine_depth(d,np.full_like(d,.5),np.ones_like(d),np.zeros_like(d),0)
        self.assertEqual(o['coverage'][0,0,0],0)
        self.assertEqual(o['coverage'][0,0,1],1)
        self.assertEqual(o['hidden_fraction'],.5)

    def test_shared_scale_is_not_per_frame(self):
        d=np.array([[[.2,.8]],[[.4,.6]]],np.float32)
        p=np.full_like(d,.6)
        o=m.combine_depth(d,p,np.ones_like(d),tolerance=1)
        self.assertAlmostEqual(o['particle'][0,0,0],o['particle'][1,0,1])
        self.assertEqual(o['depth_range'],[float(d.min()),float(d.max())])

    def test_empty_particle_frame_preserves_object(self):
        d=np.ones((2,3,4),np.float32)*.5
        o=m.combine_depth(d,np.zeros_like(d),np.zeros_like(d))
        np.testing.assert_array_equal(o['merged'],o['scene'])
        self.assertTrue(np.isfinite(o['merged']).all())

    def test_coverage_does_not_change_raw_depth(self):
        d=np.zeros((1,1,2),np.float32);p=np.ones_like(d)*.7
        o=m.combine_depth(d,p,np.array([[[.1,1]]],np.float32))
        np.testing.assert_array_equal(o['raw_particle_depth'],p)
        self.assertAlmostEqual(o['particle'][0,0,0]/o['coverage'][0,0,0],o['particle'][0,0,1],places=6)

    def test_near_particle_wins_and_current_depth_is_used(self):
        class R:
            h=w=5
            def scale(self,i):return 1
            def map(self,i,x,y):return x,y
        class P:
            interrupted=staticmethod(lambda:None)
            frame_alpha=staticmethod(lambda p,r,i,a,*args,**kw:r['alpha'][i,a])
        a=lambda x:np.array([x],np.float32)
        rec=dict(x=a([2,2]),y=a([2,2]),z=a([.9,.8]),zd=a([.3,.6]),alpha=a([1,.3]),size=a([2,2]))
        z,c=m.particle_surfaces(dict(rec=rec,P={},n=1,edge_fade=0),R(),P)
        self.assertAlmostEqual(z[0,2,2],.6,places=6)
        self.assertEqual(c[0,2,2],1)

    def test_crop_tracks_origin_and_float64_scale(self):
        class R:
            h=w=2
            window=True
            org=np.array([[1,1]],np.float64)
            def scale(self,i):return np.float64(.5)
        a=np.arange(25,dtype=np.float32).reshape(1,5,5)
        np.testing.assert_array_equal(m.crop_frames(a,R()),np.array([[[6,8],[16,18]]]))

if __name__=='__main__':unittest.main()

from .generation.unmult import EFUnmult
from .compositing.preview import EFCompPreview
from .output.export import EFSaveEXR
from .compositing.light3d import EFDepthLight
from .compositing.post import EFAddLayers, EFDither, EFGlow
from .compositing.temporal import EFClipFrames, EFDeflicker, EFFreeVRAM, EFMoGeNormals, EFStillClip
from .tracking.analysis import EFLoadAnalysis, EFLoadTrack, EFSaveAnalysis, EFSaveTrack
from .tracking.follow_crop import EFFollowCrop
from .generation.inplate import EFInPlateGuides
from .app.app_nodes import EFFinishStack, EFLoadRunLatent, EFPassPreview, EFRunLatent
from .generation.hdr import EFHDRMerge
from .compositing.look import EFNightGrade
from .compositing.place import EFAnchor, EFMaskTrack, EFPlaceBetween, EFPlaceElement, EFTrackKeepAlike
from .tracking.motion import EFMotionTracks
from .tracking.track import EFEffectLayer, EFPlaceLayer, EFTrackROI
from .generation.elements import EFLoadElement, EFSaveElement
from .generation.guides import EFGuide, EFGuideChoice
from .workflow.timing import EFMarginMask, EFPoints, EFStartAt, EFTrackPreview, EFVideoLatentMask
from .simulation.particles_node import EFParticles, EFParticleSettings
from .simulation.particle_depth_node import EFParticleDepthGuides
from .tracking.mask_controls import EFMaskPoint, EFSelectObjectMask
from .compositing.object_protection import EFObjectProtection, EFRestoreProtectedObject
from .simulation.dissolve import EFCleanPlateCrop, EFCleanPlateReference, EFCleanPlateUncrop, EFCompToLayer, EFDissolve, EFDissolveBackground, EFScreen

NODE_CLASS_MAPPINGS = {
    "EFUnmult": EFUnmult,
    "EFParticles": EFParticles,
    "EFParticleSettings": EFParticleSettings,
    "EFParticleDepthGuides": EFParticleDepthGuides,
    "EFMaskPoint": EFMaskPoint,
    "EFSelectObjectMask": EFSelectObjectMask,
    "EFObjectProtection": EFObjectProtection,
    "EFRestoreProtectedObject": EFRestoreProtectedObject,
    "EFDissolve": EFDissolve,
    "EFCleanPlateReference": EFCleanPlateReference,
    "EFCleanPlateCrop": EFCleanPlateCrop,
    "EFCompToLayer": EFCompToLayer,
    "EFCleanPlateUncrop": EFCleanPlateUncrop,
    "EFScreen": EFScreen,
    "EFDissolveBackground": EFDissolveBackground,
    "EFCompPreview": EFCompPreview,
    "EFTrackROI": EFTrackROI,
    "EFEffectLayer": EFEffectLayer,
    "EFPlaceLayer": EFPlaceLayer,
    "EFSaveEXR": EFSaveEXR,
    "EFAnchor": EFAnchor,
    "EFPlaceElement": EFPlaceElement,
    "EFMotionTracks": EFMotionTracks,
    "EFDepthLight": EFDepthLight,
    "EFGlow": EFGlow,
    "EFDeflicker": EFDeflicker,
    "EFFreeVRAM": EFFreeVRAM,
    "EFMoGeNormals": EFMoGeNormals,
    "EFClipFrames": EFClipFrames,
    "EFStillClip": EFStillClip,
    "EFSaveAnalysis": EFSaveAnalysis,
    "EFLoadAnalysis": EFLoadAnalysis,
    "EFSaveTrack": EFSaveTrack,
    "EFLoadTrack": EFLoadTrack,
    "EFDither": EFDither,
    "EFAddLayers": EFAddLayers,
    "EFFollowCrop": EFFollowCrop,
    "EFInPlateGuides": EFInPlateGuides,
    "EFPassPreview": EFPassPreview,
    "EFFinishStack": EFFinishStack,
    "EFRunLatent": EFRunLatent,
    "EFLoadRunLatent": EFLoadRunLatent,
    "EFHDRMerge": EFHDRMerge,
    "EFNightGrade": EFNightGrade,
    "EFMaskTrack": EFMaskTrack,
    "EFTrackKeepAlike": EFTrackKeepAlike,
    "EFPlaceBetween": EFPlaceBetween,
    "EFSaveElement": EFSaveElement,
    "EFLoadElement": EFLoadElement,
    "EFGuide": EFGuide,
    "EFGuideChoice": EFGuideChoice,
    "EFStartAt": EFStartAt,
    "EFPoints": EFPoints,
    "EFVideoLatentMask": EFVideoLatentMask,
    "EFMarginMask": EFMarginMask,
    "EFTrackPreview": EFTrackPreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "EFMarginMask": "Element Forge · Margin Mask",
    "EFParticles": "Element Forge · Particles",
    "EFParticleSettings": "Element Forge · Particle Settings",
    "EFDissolve": "Element Forge · Dissolve",
    "EFCleanPlateReference": "Element Forge · Clean Plate Reference",
    "EFCleanPlateCrop": "Element Forge · Clean Plate Crop",
    "EFCompToLayer": "Element Forge · Comp To Layer",
    "EFCleanPlateUncrop": "Element Forge · Clean Plate Uncrop",
    "EFScreen": "Element Forge · Screen",
    "EFDissolveBackground": "Element Forge · Dissolve Background",
    "EFUnmult": "Element Forge · Unmult",
    "EFCompPreview": "Element Forge · Comp Preview",
    "EFTrackROI": "Element Forge · Track ROI",
    "EFEffectLayer": "Element Forge · Effect Layer",
    "EFPlaceLayer": "Element Forge · Place Layer",
    "EFSaveEXR": "Element Forge · Save EXR",
    "EFAnchor": "Element Forge · Anchor",
    "EFPlaceElement": "Element Forge · Place Element",
    "EFMotionTracks": "Element Forge · Motion Tracks (LTX)",
    "EFDepthLight": "Element Forge · Depth Light",
    "EFGlow": "Element Forge · Glow",
    "EFDeflicker": "Element Forge · Deflicker",
    "EFFreeVRAM": "Element Forge · Free VRAM",
    "EFMoGeNormals": "Element Forge · MoGe Normals",
    "EFClipFrames": "Element Forge · Clip Frames",
    "EFStillClip": "Element Forge · Still Clip",
    "EFSaveAnalysis": "Element Forge · Save Analysis",
    "EFLoadAnalysis": "Element Forge · Load Analysis",
    "EFSaveTrack": "Element Forge · Save Track",
    "EFLoadTrack": "Element Forge · Load Track",
    "EFDither": "Element Forge · Dither",
    "EFAddLayers": "Element Forge · Add Layers",
    "EFFollowCrop": "Element Forge · Follow Crop",
    "EFInPlateGuides": "Element Forge · In-Plate Guides",
    "EFPassPreview": "Element Forge · Pass Preview (App)",
    "EFFinishStack": "Element Forge · Finish Stack (App, several runs)",
    "EFRunLatent": "Element Forge · Keep Run Latent (App)",
    "EFLoadRunLatent": "Element Forge · Load Run Latent (App)",
    "EFHDRMerge": "Element Forge · HDR Merge",
    "EFNightGrade": "Element Forge · Night Grade",
    "EFMaskTrack": "Element Forge · Mask Track",
    "EFTrackKeepAlike": "Element Forge · Track: Keep Objects Alike",
    "EFPlaceBetween": "Element Forge · Place Between",
    "EFSaveElement": "Element Forge · Save Element",
    "EFLoadElement": "Element Forge · Load Element",
    "EFGuide": "Element Forge · Guide",
    "EFGuideChoice": "Element Forge · Guide Choice",
    "EFStartAt": "Element Forge · Start At",
    "EFPoints": "Element Forge · Points",
    "EFVideoLatentMask": "Element Forge · Video Latent Mask",
    "EFTrackPreview": "Element Forge · Track Preview",
}

from .workflow.stages import NODE_CLASS_MAPPINGS as _STAGES, NODE_DISPLAY_NAME_MAPPINGS as _STAGE_NAMES
NODE_CLASS_MAPPINGS.update(_STAGES)
NODE_DISPLAY_NAME_MAPPINGS.update(_STAGE_NAMES)
try:
    from server import PromptServer as _PS
    from .workflow.stages import on_prompt as _stages_on_prompt, register_routes as _stage_routes
    if getattr(_PS, "instance", None) is not None and not getattr(_PS.instance, "_ef_stages_on_prompt", False):
        _PS.instance.add_on_prompt_handler(_stages_on_prompt)
        _stage_routes(_PS.instance.routes)
        _PS.instance._ef_stages_on_prompt = True
except Exception:
    pass

_TOOLS = {"EFLoadElement": "EF Load Element", "EFSaveElement": "EF Save Element", "EFGlow": "EF Glow", "EFDepthLight": "EF Depth Light",
          "EFDeflicker": "EF Deflicker", "EFDither": "EF Dither", "EFUnmult": "EF Unmult", "EFMoGeNormals": "EF MoGe Normals"}
_TOOLS.update({"EFParticleDepthGuides": "EF Particle Depth Guides", "EFMaskPoint": "EF Mask Point",
               "EFSelectObjectMask": "EF Select Object Mask", "EFObjectProtection": "EF Object Protection",
               "EFRestoreProtectedObject": "EF Restore Protected Object"})
for _name, _cls in NODE_CLASS_MAPPINGS.items():
    if _name in _TOOLS:
        _cls.CATEGORY = "Element Forge/Tools"
        NODE_DISPLAY_NAME_MAPPINGS[_name] = _TOOLS[_name]
    elif _name not in _STAGES:
        _cls.DEV_ONLY = True

from .memory_guard import guard_class as _guard_class
for _cls in NODE_CLASS_MAPPINGS.values():
    _guard_class(_cls)
try:
    from server import PromptServer as _PS
    from .memory_guard import on_prompt as _gpu_room_on_prompt
    if getattr(_PS, "instance", None) is not None and not getattr(_PS.instance, "_ef_gpu_room", False):
        _PS.instance.add_on_prompt_handler(_gpu_room_on_prompt)
        _PS.instance._ef_gpu_room = True
except Exception:
    pass

try:
    import os as _os

    import folder_paths as _fp
    _blank = _os.path.join(_fp.get_input_directory(), "ef_guide_blank.png")
    if not _os.path.isfile(_blank):
        import numpy as _np
        from PIL import Image as _Image
        _os.makedirs(_os.path.dirname(_blank), exist_ok=True)
        _Image.fromarray(_np.zeros((64, 64, 3), _np.uint8)).save(_blank)
except Exception as e:
    print(f"[Element Forge] could not create input/ef_guide_blank.png: {e}")

try:
    from .app import app_routes
except Exception as e:
    print(f"[Element Forge] app routes not loaded: {e}")
try:
    from .app import live
except Exception as e:
    print(f"[Element Forge] live preview not loaded: {e}")

try:
    from .app_mode import NODE_CLASS_MAPPINGS as _APP_NODES, NODE_DISPLAY_NAME_MAPPINGS as _APP_NAMES
    NODE_CLASS_MAPPINGS.update(_APP_NODES)
    NODE_DISPLAY_NAME_MAPPINGS.update(_APP_NAMES)
except Exception as e:
    print(f"[Element Forge] App-mode nodes not loaded: {e}")

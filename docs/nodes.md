# Node reference

[README](../README.md) · [Setup](setup.md) · [Usage](usage.md) · [Licenses](licenses.md)

Start with the supplied workflow. Add options and tools when you need more control. Nodes appear under **Element Forge** in ComfyUI; advanced inputs are available from the node menu in the Vue view.

## Main workflow

| Node | Purpose |
|---|---|
| EF Models | Select the LTX model, attention mode and text encoder. |
| EF Shot | Load the footage and compute scene analysis; choose depth and night settings. |
| EF Track | Set points, tracking mode, object selection and masks; inspect the track. |
| EF Element | Select the effect, style, prompt, timing, quality and generation mode. |
| EF Place | Position, size, blend and occlude the element; optionally lock its base. |
| EF Light & Glow | Control the effect's scene lighting and glow. |
| EF Export | Run the composition and save the composite, passes and settings. |

## Options

Connect these to EF Element. Values left at **style default** use the selected style's settings.

| Node | Adds |
|---|---|
| EF Particles | Emitter, preset, amount, motion, collision, appearance and particle guidance. |
| EF Guide | Guidance from particles, an object's shape or a drawn path. |
| EF Dissolve | Dissolve timing, glowing edge, particles and clean-plate controls. |
| EF LTX Options | Sharper x2, optional NVIDIA upscale/HDR and generation margins. |

Particle guidance can steer AI generation or create a finished drawn effect. Start with the style's defaults. **Guide** uses particle paths or volume; **start video** uses rendered particles. A custom sprite is used through the start-video route. The best choice depends on the effect and footage.

## Compositing and reuse

| Tool | Purpose |
|---|---|
| EF Unpack | Expose the footage, element, alpha and available passes from a run. |
| EF Element from Images | Bring generated frames and optional alpha into the placement workflow. |
| EF Library Element | Place a previously saved element. |
| EF Save Element / EF Load Element | Save and reload an element sequence with its manifest. |
| EF Unmult | Recover colour and alpha from an element rendered on black or white. |
| EF Glow | Create a glow and separate glow pass in linear light. |
| EF Depth Light | Light the footage using scene depth, surface normals and the element's position. *depth_kind* *disparity* reads Video Depth Anything's map as inverse depth; *depth_range* and *fov* can come from EF MoGe Normals. |
| EF Deflicker | Reduce temporal variation in estimated passes. |
| EF Dither | Reduce visible banding in low-bit-depth output. |
| EF MoGe Normals | Estimate surface normals for lighting, and the shot's depth range (far / near) and field of view for EF Depth Light. |

## Building blocks

These support custom graphs and the supplied app routes. Their inputs expose the detailed controls.

| Area | Nodes and role |
|---|---|
| Tracking and framing | Track ROI and Follow Crop prepare a moving area; Motion Tracks (LTX) creates motion guidance; Place and Place Between position an element. |
| Particles and dissolve | Particles, Particle Settings and Dissolve create motion, guidance and drawn effects. Clean Plate Reference and Clean Plate Crop / Uncrop help replace the background behind a removed object. |
| Guidance and masks | Guide, Guide Choice, Points, Margin Mask, Video Latent Mask and In-Plate Guides define positions and regions. Start At offsets an effect in time. |
| Compositing | Comp To Layer, Screen, Effect Layer / Place Layer and Night Grade combine or grade footage and elements. |
| Preview and export | Track Preview, Comp Preview, Pass Preview and Save EXR provide checks, previews and output. |
| App versions | Keep Run Latent / Load Run Latent support finishing previews and adding passes. Finish Stack combines several effects on a clip. |

### Pass conventions

Footage is supplied as sRGB. Element and light passes used for compositing are scene-linear. EXR preserves that working space; take care not to apply a second display conversion in your compositing application.

Use the exported alpha and the matching element pass together. Additive light passes and ordinary image layers need different blend operations.

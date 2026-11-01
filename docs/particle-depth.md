# Particle depth and mask tools (experimental)

These nodes are available under **Element Forge / Tools**. They do not yet replace the app's selection panel or its saved-track cache. The example workflow **Particle Depth Tools** prepares masks and guides; connect its outputs to your LTX workflow after reviewing them.

## Keep four different jobs separate

| Data | Purpose | What an exclusion changes |
| --- | --- | --- |
| Emitter mask | Where particles are born, such as the exposed blade | Removes the hand, handle or sheath as emission sources |
| Full scene depth | Particle depth, collision and visibility against the surroundings | Nothing. Never multiply this depth map by the emitter mask |
| LTX guide | What spatial information the video model receives | Independently choose selected object or full scene, with visible particles merged in |
| Protection / compositing visibility | Preserve original surfaces and place the effect in front of or behind them | A separate artistic decision; emission exclusions are not automatically holdouts |

Particles may leave the selected object and travel across other parts of the image. The full depth map still controls their interaction with the scene. This is estimated relative depth, not reconstructed physical geometry; it does not guarantee accurate collision or occlusion.

## Select the emission source

1. Connect the original image sequence and the MODEL output of a SAM3 loader to **EF Select Object Mask**. For words, also connect the loader's CLIP output.
2. Choose `reference_frame` where the required surface is visible. For a drawing sword, this can be a later frame. The node tracks forward and backward from that frame.
3. Chain **EF Mask Point** nodes, each marked `include` or `exclude`. Coordinates refer to the original image, either normalized from 0 to 1 or pixels. No JSON file is needed.
4. Alternatively, leave positive points disconnected and use `include_words`. Add unwanted objects in `exclude_words`, one per line or separated by semicolons. An explicit `exclude_mask` is also accepted.
5. Check the green selection and red exclusions in the preview. Connect `selection` to the particle emitter's `mask` input.

Positive points take precedence over include words. SAM's combined text/point detector unions its results; passing both blindly can add excluded objects back. Word exclusions are detected separately and subtracted after tracking. With a word or manual-mask selection, negative points select objects to subtract. With positive points, they act as native negative segmentation constraints.

The automatic result needs inspection. Word detection can select clothing when asked for a hand or handle. Negative points at the reference frame are not repeated annotations on every later frame, so a tracker can still drift. An empty selection remains empty; the node does not invent a replacement. `track_video=false` returns only the selected reference frame for a quick check.

## Guide LTX with particle depth

**EF Particle Depth Guides** shares the existing particle engine, preset controls and `EF_PARTICLE_SETTINGS` input. Use the same plate, mask, depth, seed, timing, tracks, window and settings as EF Particles. The prototype recomputes the deterministic simulation; it does not change EF Particles' existing output signature.

- `merged_guide`: one guide combining object/scene depth with visible particle surfaces.
- `object_guide` and `particle_guide`: two aligned guides that can be connected to separate LTX IC-LoRA reference nodes. The first is a full scene when `guide_content=full scene`.
- `visible_coverage`: particle coverage after testing against the full scene depth.
- `raw_particle_depth` and `raw_coverage`: separate relative inverse Z and coverage. Larger Z means nearer. These are not opacity-weighted volume depth or an alpha matte.
- `guide_content`: selected object or full scene. This never changes the emission mask or simulation depth.
- `object_shape`: full selected object or a narrow inner edge. Edge width is measured in guide pixels; use full object for a full-scene guide.

Both depth branches use one fixed scale across the clip. Particle surfaces behind the scene are removed before the guides are combined. The inner-edge option changes only the object's guidance; particle guidance is unchanged. Sprite surfaces are approximated as discs. Bolt, climb and crack path renderers are not supported by this depth node and produce an explicit error.

Full-scene guides may encourage LTX to reconstruct the surrounding person or background. The full-scene option has been checked for guide construction and unchanged particle simulation, not established as better by a paired LTX comparison. Selected-object merged guidance remains the tested starting point. Two separate guides can impose a much stronger combined constraint.

## Preserve the original object

**EF Object Protection** creates effect visibility that is exactly zero inside the thresholded protected surface. Grow expands the protected area; feather softens only outside it. Connect an existing particle region/depth visibility mask to `visibility` to multiply the two. Connect `effect_visibility` to the holdout input of EF Place Layer.

The protected object can be broader than the emitter. For example, only the blade emits while the whole original sword is protected. Do not automatically turn every emission exclusion into a permanent holdout: a particle may legitimately travel in front of it.

Optional **EF Restore Protected Object**, placed after glow, restores fully protected pixels exactly from the supplied plate. Use the same graded plate as the composition. This also removes added light and glow within those pixels. Leave it out if the protected surface should receive light, or supply an approved lit plate. It is an explicit strict-preservation option, not a relighting model.

An inaccurate mask still gives an inaccurate edge. These nodes prevent generated geometry from replacing protected pixels; they do not turn a coarse segmentation into perfect rotoscoping.

## Reproduce the compared mechanisms

| Recipe | Generation | Guide | Compositing |
| --- | --- | --- | --- |
| Existing merged render | Reuse a saved effect | No new LTX call | Unmult, reduced gain, object protection, depth light and glow |
| Sparse merged | Prompt asks for short detached discharges and gaps | Full selected-object merged guide, attention 1.0 | Same composition |
| Sparse edge | Same sparse prompt | Inner-edge merged guide, attention 0.8 | Same composition |
| Seed comparison | Same as sparse edge | Same guide; another seed | Same composition |

Example prompt: `An isolated VFX pass of sparse delicate cyan electrical sparks peeling away from a moving diagonal edge. Short irregular branching filaments and tiny detached sparks, separated by large empty black gaps. The source itself is invisible. No filled luminous body, no solid sword or handle, no person, no fog. Pure black background. Static camera.`

Tested composition used black point 0.03, linear additive placement, effect gain 0.65, soft ROI edges and separate depth light and glow. The old protection experiment retained 4 percent of the effect inside its mask; the new protection node defaults to complete removal there. These are separate controls, not one universal preset.

Total pipeline durations include model loading, text encoding, cached nodes, generation and compositing. Reusing an effect skips LTX entirely. Do not interpret those totals as a controlled guide-speed benchmark.

## App integration still required

The app should expose emission selection and its exclusions on the canvas, a reference-frame selector, mask preview/corrections, guide content/shape and independent original-object protection. Keep full scene depth connected to simulation, visibility and lighting. All new selection inputs must enter both frontend and backend saved-track cache keys. Changes to points, exclusion words, reference frame or manual masks must invalidate stale selection results. This branch adds ordinary node controls and callable implementations; it does not claim that these controls are already in the app panel.

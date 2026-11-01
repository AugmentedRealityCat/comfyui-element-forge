<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/branding/logo-on-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/branding/logo-on-light.svg">
    <img src="docs/assets/branding/logo-on-light.svg" alt="Element Forge" width="560">
  </picture>
</h1>

<p align="center"><strong>AI effects you control, right in the shot.</strong></p>

<p align="center">
  <a href="#control-not-just-generation">Control</a> ·
  <a href="#get-started">Get started</a> ·
  <a href="#your-first-effect">Your first effect</a> ·
  <a href="#make-your-own-effects">Your own effects</a> ·
  <a href="#more-examples">Examples</a> ·
  <a href="#documentation">Documentation</a>
</p>

Add fire, lightning, smoke and particles to your own footage in ComfyUI, and decide where they start, which way they move and what they touch. Element Forge simulates particles in your shot first, with its depth, objects and motion, and lets **LTX-2.5** generate the effect along them, locally. Then adjust light and colour and export the result or separate EXR passes.

Use the app for a guided workflow, or connect the nodes in your own graph. The particles also work without AI, as a finished effect of their own.

https://github.com/user-attachments/assets/468b014c-f544-41fe-b26f-fd6da37d78a3

<p align="center"><em>The release video.</em> <a href="https://youtu.be/Cz7dW70VSNg">Watch it on YouTube</a><br><sub>AI-generated effects; stock footage.</sub></p>

<br>

## Control, not just generation

A prompt alone decides little: the AI guesses where the effect goes, how big it is and how it moves. In Element Forge you set that yourself, and the AI fills in the look.

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>Particles that know the scene</h3>
      <p>A <b>live simulation on your clip</b>: the clip's depth hides particles behind nearer objects, they bounce, slide or stick on surfaces and move with the tracked object and the camera. Amount, speed, direction, life and forces are yours to set, and you see them <b>before any AI run</b>.</p>
    </td>
    <td width="50%" valign="top">
      <h3>The AI follows your particles</h3>
      <p>The simulation is drawn for LTX-2.5 as a <b>guide</b>: as lines, heat, volume or depth. The generated effect takes the particles' <b>path, timing and spread</b> instead of inventing its own.</p>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>Exactly where it belongs</h3>
      <p><b>Every style can go anywhere</b>: at a point (standing on it or centred), in an area you size, on the whole object, between two points or over the whole frame; the particles start in that shape. The frame that is generated can be moved and sized <b>independently</b> of the point, so nothing is cut off.</p>
    </td>
    <td width="50%" valign="top">
      <h3>Masks you can correct</h3>
      <p>Set the object's mask on <b>any frame</b>, add and leave out parts with clicks or words, <b>fix it on the frames where the track slips</b> with one more click, and keep it <b>steady</b> where the object blurs. The effect goes behind the object or in front of it.</p>
    </td>
  </tr>
</table>

Effects combine with the object they touch: turn on <b>The object crumbles</b> and a statue falls apart into particles under its own flames, with the scene behind it filled in, and its pieces keep their own forces. Colour, amount, speed and size are one click for every style: words for the AI, and the same values for the particles that guide it.

Light, glow, colour, placement and timing stay adjustable <b>after the run, without generating again</b>, and every run is kept as a version to compare.

<br>

## What you can do

Choose from fire, lightning, sparks, smoke, magic, weather, debris, liquid and dissolve styles, or describe your own effect. The app identifies experimental styles before you generate.

The app guides you through five steps:

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>1 · Clip</h3>
      <p>Load a <b>video or a picture</b>. <b>Depth, normals and camera motion</b> are worked out once per clip.</p><br>
    </td>
    <td width="33%" valign="top">
      <h3>2 · Position & Track</h3>
      <p>Click where the effect belongs. It follows a <b>point, an object or the camera</b>, and <b>hides behind the object</b> with its mask.</p><br>
    </td>
    <td width="33%" valign="top">
      <h3>3 · Effect · Basic</h3>
      <p>Choose one of <b>26 styles</b> or <b>describe your own</b>. <b>LTX-2.5</b> generates it on your clip; drawn styles need no AI.</p><br>
    </td>
  </tr>
  <tr>
    <td width="33%" valign="top">
      <h3>3 · Effect · Advanced</h3>
      <p>Build particle simulations <b>live, without AI</b>. Depth, masks and tracks let them <b>hide, collide and move with the scene</b>.</p><br>
    </td>
    <td width="33%" valign="top">
      <h3>4 · Scene & finish</h3>
      <p>Change light, glow, colour and placement <b>live, without a new run</b>. Combine <b>several effects</b> on one clip.</p><br>
    </td>
    <td width="33%" valign="top">
      <h3>5 · Output</h3>
      <p>Compare versions and export video or <b>scene-linear EXR passes</b>, with <b>NVIDIA × 2 or HDR</b>, even for the clip alone.</p><br>
    </td>
  </tr>
</table>

### All features

<details>
<summary><b>1 · Clip</b> &nbsp;·&nbsp; load, analyse</summary>
<br>

- **Sources**<br>Load a video or a still picture. In a node graph, EF Shot also accepts frames with a frame rate.
- **Analysis**<br>Depth, surface normals and camera motion are worked out once per clip. Every effect on the clip reuses them.

</details>

<details>
<summary><b>2 · Position & Track</b> &nbsp;·&nbsp; points, objects, camera, masks</summary>
<br>

- **What it follows**<br>Click where the effect belongs. It follows that **point**, the whole **object**, the **scene** while the camera moves, or stays fixed on **screen**.
- **Two points**<br>Shift-click a second point for effects that connect two positions, such as lightning or energy.
- **Track check**<br>An object word helps find what to follow. The track check shows the path and the object's mask before you generate.
- **Masks**<br>Hide an effect behind the selected object with its mask, or keep the base of an effect on its tracked point. Set the mask on any frame of the clip (a blade drawn only later), add parts and leave parts out with clicks or words; the track runs from that frame both ways.

</details>

<details>
<summary><b>3 · Effect · Basic</b> &nbsp;·&nbsp; 26 styles, your words, overlay or inpaint</summary>
<br>

- **Styles**<br>26 styles in ten groups, from flames and lightning to snow, liquid and dissolve, plus your own effect.
- **Words**<br>Describe the look, motion and contact. **Enhance** can refine them when a language model is installed. With the optional Bonsai model, **Describe what you want** suggests a style and its words; you see each change before you apply it. For particle styles, **Particles in your words** turns a sentence such as *slow green sparks that spiral up* into emitter values.
- **From a picture**<br>Add up to three pictures of an effect you like. Bonsai sees them beside your clip with the chosen place marked, proposes the style and its words for that spot, and then sets the particles to match the pictures.
- **Three routes**<br>**Overlay** generates the element separately. **Inpaint** generates it inside the footage for contact with surfaces. **Particles only** draws any style with its particles, without AI generation.
- **Several effects**<br>**＋ Effect** adds another effect to the same clip, each with its own settings and versions.

</details>

<details>
<summary><b>3 · Effect · Advanced</b> &nbsp;·&nbsp; live particle simulation, guides for the AI</summary>
<br>

- **Live, without AI**<br>The **Emitter** shows the same controls for every style: a preset only sets their values. The live preview simulates the particles on your clip with the same engine and seed as the run.
- **Part of the scene**<br>The clip's depth hides particles behind nearer objects and lets them bounce, stick, slide or die on surfaces. The object's mask and track carry the emitter; the clip's motion and the camera move them along.
- **Three uses**<br>Keep the simulation as the finished effect, let it guide LTX-2.5, or draw it over the AI element.
- **Guides for the AI**<br>Besides the particles, the AI can follow the object's shape or a path you paint on the canvas.
- **Out of the box**<br>Every particle style starts from tested values, marked on each slider. Changed values are highlighted and go back one by one.
- **Fill from the prompt**<br>With the optional Bonsai model, **✦ Fill from the prompt** reads the effect's words and proposes the emitter values to change, each with its reason. You tick what to apply and undo it in one step.
- **Calm or lively**<br>Speed at the end, a speed limit, spin and turbulence that fades in or is calmed by drag make slow, drifting particles as easy as fast bursts.
- **Keep it**<br>**Save as my effect** stores the emitter values for every clip. See [Make your own effects](#make-your-own-effects).

</details>

<details>
<summary><b>4 · Scene & finish</b> &nbsp;·&nbsp; light, glow, placement, timing, clip grade</summary>
<br>

- **Light and colour**<br>Set the light the effect throws on the scene, its glow, brightness and colour. An effect can also be **lit by the other effects**, such as smoke near a flame.
- **Placement and timing**<br>Move, scale and rotate the effect in the canvas. The timeline sets start, end and fades; Advanced adds keyframes.
- **Clip grade**<br>Brightness, warmth, colour strength and a depth blur that keeps the focus on the effect.

</details>

<details>
<summary><b>5 · Output</b> &nbsp;·&nbsp; preview, versions, formats, EXR passes, NVIDIA</summary>
<br>

- **Preview and final**<br>Start with a fast **Preview**, then **Make final** for the full-size version. **Add passes** creates missing passes without generating the effect again.
- **Versions**<br>Every run becomes a version. Show and compare versions and restore their settings.
- **Formats**<br>Export the composite as MP4, ProRes, H.265 10-bit, PNG or EXR.
- **Passes**<br>Export separate scene-linear EXR passes for your compositor: effect passes, plate, depth, normals and the object's mask, each on its own.
- **The clip alone**<br>Export a clip without an effect, with its passes, NVIDIA upscaling or HDR.
- **Upscaling and HDR**<br>**LTX × 2** adds detail in a second pass; **NVIDIA × 2** is fast. In the export, NVIDIA upscaling and HDR run on the plate only, with the effects kept as they are, or on the finished comp.
- **Element library**<br>Save an AI element to a library and place it in other shots without generating it again.

</details>

<details>
<summary><b>Node graph</b> &nbsp;·&nbsp; the same graphs as ordinary nodes</summary>
<br>

- **Template**<br>The **Element Forge** template uses the same graphs as the app, as ordinary ComfyUI nodes.
- **Building blocks**<br>**EF Unpack** exposes the footage, element, alpha and passes. Compositing tools include glow, depth light, unmult, deflicker and dither.
- **Other generators**<br>Bring frames from another generator into the placement workflow with **EF Element from Images**.
- **Scripting**<br>The graphs in `api_workflows/` can be used for scripting.

</details>

<br>

## Get started

> [!NOTE]
> **Requirements**<br>**ComfyUI 0.41.2 or newer**, the two node packs below and the [required models](docs/setup.md#default-models).
>
> **Tested hardware**<br>The AI routes have been tested with NVIDIA GPUs from **11 GB VRAM** on Windows and Linux. This is a tested configuration, not a confirmed minimum. Other GPU platforms have not been tested.
>
> **Disk and memory**<br>Allow about **45 GB** for the default models; RAM use varies with the models and clip size.

### 1. Install

With ComfyUI's Python environment active, run this from the ComfyUI folder. For **Windows portable**, use the [embedded-Python instructions](docs/setup.md#install-the-node-packs).

```bash
cd custom_nodes
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything
git clone https://github.com/Lightricks/ComfyUI-LTXVideo
git clone https://github.com/Zitroffi/comfyui-element-forge
python -m pip install -r ComfyUI-Video-Depth-Anything/requirements.txt
python -m pip install -r ComfyUI-LTXVideo/requirements.txt
python -m pip install -r comfyui-element-forge/requirements.txt
```

### 2. Add the models

Follow the [model list](docs/setup.md#default-models) for filenames, download links and folders, then restart ComfyUI. The app's gear menu shows each model's status and source.

Prompt enhancement, Bonsai, NVIDIA upscaling and HDR are optional. You can add them later through the [setup guide](docs/setup.md#optional-additions).

<br>

## Your first effect

Start with a short clip and an overlay effect.

1. **Open the app**<br>**Templates → Extensions → comfyui-element-forge → Element Forge (app)**.
2. **Clip**<br>Load your clip.
3. **Position & Track**<br>Click where the effect belongs and choose what it follows. Check the track before generating.
4. **Effect**<br>Choose a style and describe what you want. Use **Preview** quality when available, then **Run**.
5. **Scene & finish**<br>Adjust the result. Light and glow controls depend on the passes available in the selected version.
6. **Output**<br>Export a finished video or image sequence, with separate EXR passes when needed.

> [!TIP]
> **Versions**<br>The app keeps versions so you can compare results and restore their settings. For supported previews, **Make final** creates a full-size version; **Add passes** provides missing layers without another effect generation.
>
> **Prefer a node graph?**<br>Open the **Element Forge** template instead. It uses the same underlying graphs as the app. See [the workflow guide](docs/usage.md#use-the-workflow).

<br>

## Make your own effects

1. **Describe it**<br>Choose **Your own effect** and describe any element in words. It is generated with LTX-2.5 and stays on the point you click. Things that glow work best.
2. **Shape it with particles**<br>Switch the app to **Advanced**. In **Effect**, the **Emitter** shows the same controls for every style; a preset only sets their values. Changed values are highlighted and can be reset one by one. **✦ Fill from the prompt** sets them from your words with the optional Bonsai model. The **live preview** simulates the particles on your clip with the same engine and seed as the run. It needs no AI, and the particles already react to the scene: they hide behind nearer objects, collide with surfaces and move with the clip.
3. **Keep it**<br>**Save as my effect** stores the style, its words, the emitter values and the switches. Clip, position and track stay with the shot. Your saved effects appear under **My effects** for every clip, ready to load, rename or delete.

### Particles in detail

<details>
<summary><b>How the particle simulation works</b> &nbsp;·&nbsp; emitter, forces, depth, look</summary>
<br>

Element Forge has its own particle engine. It uses the clip's analysis, so particles behave like part of the scene.

| Stage | What happens |
|:---|:---|
| **Emitter** | Particles start at a point, between two points, along a drawn path, in an area, across the whole frame, on an object, along its outline or bottom edge, or in groups placed in depth. |
| **Birth** | Each particle gets a life, size, speed and direction: at an angle, outward from the object, against the emitter's motion (grinding sparks) or random. Rate and bursts decide when they appear. Pre-roll runs the simulation before the clip starts, so snow or rain already fills the first frame. |
| **Forces** | Every step applies gravity, wind, drag, swirling turbulence (curl noise), a vortex around the emitter, attraction to point B and flocking, where neighbours pull together into streams and drops. |
| **Motion from the clip** | Particles take on part of the emitter's movement. Optical flow of the footage lets moving things carry them along, such as a hand sweeping through smoke. The measured camera motion keeps them in place in the scene while the camera moves. |
| **Depth and contact** | Each particle has a depth in the scene. Nearer objects hide it, and where it meets a surface it can bounce, stick, slide or die. Rain and liquid drops splash on impact. |
| **Look** | Sprites (soft, dot, flake, puff, wisp, streak, spark or chunk), colour and size over the particle's life, trails, motion blur, flicker and glow. **Merge into one body** blurs neighbouring particles together for liquid edges or fire tongues. |
| **Paths** | Lightning is drawn as jagged, branching bolts that change shape every few frames. Climbing arcs run along the thin parts of an object. Cracks and frost grow across a surface. |
| **Dissolve** | The object's mask crumbles into particles while the background behind it is filled in. Any other effect can crumble its object too (**Crumble** in the emitter). |
| **Seed** | The same particle seed gives the same particles in the live preview and in the run. **New seed** tries other particles with the same settings. |

</details>

<details>
<summary><b>Particles and the AI</b> &nbsp;·&nbsp; drawn, guiding, or both</summary>
<br>

Particles can be the whole effect or steer the AI.

| Route | What happens |
|:---|:---|
| **Particles only** | The simulation is the finished effect. No AI generation; the fastest route. |
| **Particles guide the AI** | The particles set where and how the element moves. LTX-2.5 paints its look. |
| **Also draw the particles** | Drawn particles are added over the AI element. |

The AI can also follow an object's shape (a flame wraps round a fist) or a path you paint, or work from the prompt alone. **Guide strength** sets how closely it follows.

</details>

<details>
<summary><b>Emitter controls</b> &nbsp;·&nbsp; every control by group</summary>
<br>

| Group | Controls |
|:---|:---|
| **Source** | Guide for the AI and how the particles are drawn for it (lines, volume, heat, depth of the object with the particles in front), the particles it starts from, also draw them over the AI's element, emitter shape and size, maximum particles alive at once |
| **Emission** | Rate, burst, timing, pre-roll |
| **Motion** | Direction and spread, bunching to the centre, speed and its variation, speed at the end, speed limit, how far the particles follow the emitter and the clip, the AI's Follows motion |
| **Particle** | Look (glowing, solid or contrast), life, size and colour over life, the clip's colour, lit by the clip, colour variation, sprite, trail, glow, flicker, fades, motion blur, opacity, spin, a second class of small particles |
| **Merge** | Blur, choke, edge and fill of a single body |
| **Forces** | Gravity, wind, drag, turbulence (fades in, calmed by drag), vortex, attraction to B, flocking (reach, pull) |
| **Contact & depth** | Collision, bounce, friction, lying time, a splash where particles hit, depth offset and spread, hidden by the scene |
| **Paths** | None, a bolt from A to B, a charge climbing the object, or cracks spreading from A, drawn over the particles: width, jaggedness, branches and each path's own values |

With the optional Bonsai model, **✦ Fill from the prompt** proposes these values from the effect's words; you tick what to apply.

In a node graph, connect **EF Particles** to EF Element for the same settings. See the [node reference](docs/nodes.md#options).

</details>

<br>

## More examples

The effects below are AI-generated with LTX-2.5, except the fireflies, which are drawn particles. Footage comes from Pexels and Mixkit.

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/examples/orb.gif" alt="Energy around a moving ball" width="160"><br><strong>Energy around a moving ball</strong><br><a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/orb.mp4">Download MP4</a>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/examples/rose-flame.gif" alt="Flame following a rose" width="160"><br><strong>Flame following a rose</strong><br><a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/rose-flame.mp4">Download MP4</a>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/assets/examples/dress-sparks.gif" alt="Sparks from a spinning dress" width="160"><br><strong>Sparks from a spinning dress</strong><br><a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/dress-sparks.mp4">Download MP4</a>
    </td>
    <td align="center" width="50%">
      <img src="docs/assets/examples/fireflies.gif" alt="Fireflies over a lake" width="160"><br><strong>Fireflies over a lake</strong><br><a href="https://github.com/Zitroffi/comfyui-element-forge/releases/download/examples/fireflies.mp4">Download MP4</a>
    </td>
  </tr>
</table>

All clips, stills and GIFs are available in the [examples release](https://github.com/Zitroffi/comfyui-element-forge/releases/tag/examples).

<br>

## Documentation

- **[Setup and troubleshooting](docs/setup.md)**<br>Dependencies, models and optional additions.
- **[Usage guide](docs/usage.md)**<br>Tracking, masks, generation modes, versions, export and reusable elements.
- **[Node reference](docs/nodes.md)**<br>Extend the supplied workflow or build your own.
- **[Report an issue](https://github.com/Zitroffi/comfyui-element-forge/issues)**<br>Include the error and steps to reproduce it.

## License

The code, app and workflows use the [MIT License](LICENSE). Models retain their own licenses and conditions. See the [model license summary](docs/licenses.md) before using or publishing their outputs.

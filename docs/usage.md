# Using Element Forge

[README](../README.md) · [Setup](setup.md) · [Nodes](nodes.md) · [Licenses](licenses.md)

Everything about working with Element Forge: the app step by step, tracking, effects and particles, finishing, export and the workflow. For installation and models, see [Setup](setup.md).

## Contents

| Part | Sections |
|:---|:---|
| **The app** | [Overview](#overview) · [Canvas and timeline](#canvas-and-timeline) · [Keyboard shortcuts](#keyboard-shortcuts) · [This computer and the models](#this-computer-and-the-models) |
| **Step by step** | [1 Clip](#1-clip) · [2 Position and tracking](#2-position-and-tracking) · [3 Effect](#3-effect) · [4 Scene and finish](#4-scene-and-finish) · [5 Output](#5-output) |
| **Effects** | [Effects and styles](#effects-and-styles) · [Overlay or Inpaint](#overlay-or-inpaint) · [Several effects on one clip](#several-effects-on-one-clip) |
| **Your own effects** | [Make your own effects](#make-your-own-effects) · [Particles and the AI](#particles-and-the-ai) · [Which particles for which effect](#which-particles-for-which-effect) · [Emitter controls](#emitter-controls) |
| **Results** | [Versions](#versions) · [Export](#export) · [Files and folders](#files-and-folders) · [Run times](#run-times) |
| **Workflow** | [Use the workflow](#use-the-workflow) · [Effect keys](#effect-keys) · [Reuse an element](#reuse-an-element) · [Build a custom graph](#build-a-custom-graph) |

<br>

# The app

## Overview

Open **Templates → Extensions → comfyui-element-forge → Element Forge (app)**. The template opens in ComfyUI's **App mode**: the steps on the right, your clip as a canvas in the middle, a timeline below. ComfyUI may show its own App-mode tour first; **Skip** closes it.

| Step | What you do there |
|:---|:---|
| **1 Clip** | Choose a video or a picture. **Analysis** works out depth, normals and camera motion once per clip. |
| **2 Position & Track** | Click where the effect belongs, choose what it follows and check the track. |
| **3 Effect** | Choose effect and style, describe it, decide how it goes in. Advanced shows the emitter. |
| **4 Scene & finish** | Change light, glow, colour, placement and the look of the clip live, without a new run. |
| **5 Output** | Quality, upscale and passes, **Run**, the versions, and **Export**: the comp as you see it, or the clip alone with its passes, NVIDIA × 2 or HDR. |

**Basic** and **Advanced** at the top of the panel switch how many controls the steps show. Every job goes into ComfyUI's own queue; no extra server runs.

> [!TIP]
> Start with a short clip, an overlay effect and **Preview** quality. Check the track before you generate.

## Canvas and timeline

- **Canvas**<br>Moves like ComfyUI's graph and follows its settings: by default the mouse wheel zooms, dragging empty space pans, Space-drag and the middle button pan too, `.` fits the clip.
- **Transform box**<br>The effect's area and the finished result share one box. Drag inside to move it, a corner or an edge to size it freely (Shift keeps its shape, Alt sizes from the centre), just outside a corner of the result to turn it (Shift: 15° steps).
- **Area and point apart**<br>Once you move or size the area, it stays where you put it: moving the point does not move the area, and the area does not move the point. The point may lie outside the area, for particles that fly away from where they start. The effect keeps following the point's track.
- **Timeline**<br>Shows the clip as a filmstrip and the bar of the selected effect: start, end, fade in and fade out. *Start here* and *End here* use the playhead. Advanced adds keyframes for position and brightness.
- **Views**<br>The switch at the bottom right shows the clip, depth, normals, the track check or the result. Each step opens on its own view: Position and Effect on the clip with the live particles, Light & glow and Export on the result. A view that hides the particles says so in the canvas, with **Back to the clip**.

## Keyboard shortcuts

Press **?** in the app for this list. Keys work while the canvas has focus (click into it).

| Key | Action |
|:---|:---|
| Click | Set the point (Shift-click: second point) · select an area |
| Drag inside an area | Move it (Shift: one direction, Ctrl: no snapping) |
| Drag a corner or an edge | Size it freely (Shift: keep its shape, Alt: from the centre) |
| Drag the arrow | Direction (Shift: 15° steps) |
| Mouse wheel | Zoom at the cursor, or move the view, as set in ComfyUI |
| Space (hold) + drag, middle button | Move the view |
| `.` · double-click | Fit the clip |
| Alt+= · Alt+− | Zoom in · out |
| H · P · F · D | Hand · point · area · direction |
| B · M · E | Brush (Advanced) · move the result · take a colour |
| [ ] | Brush size |
| Arrow keys | Move the selected (Shift: 10×) |
| + − | The selected larger · smaller |
| Delete | Reset what you clicked |
| Esc | Cancel a drag |
| Space (tap) | Play / pause |
| J · K · L | Back · pause · play (L again: faster) |
| Page Up · Page Down | One frame back · forward (Shift: 10) |
| Ctrl+← · Ctrl+→ | Previous · next key or edge |
| I · O | Selected effect starts · ends at the playhead |
| Ctrl+Z · Ctrl+Shift+Z | Undo · redo in the canvas |
| Ctrl+Enter | Run |

## This computer and the models

The gear at the top of the panel shows this computer's choices and every model with its status, size, folder and source. These are settings of this computer, not of the shot: another PC that opens the workflow uses its own.

| Setting | What it does |
|:---|:---|
| **LTX model** | INT8 is the default. GGUF Q4 needs about 8 GB less memory and is slower on RTX 20 cards. |
| **INT8 attention** | Faster on cards like the RTX 2080 Ti, about a quarter off the LTX time. Not with GGUF. |
| **Text encoder** | The text encoder file LTX uses. |
| **Text model** | Writes **Enhance**, the scene sentence for Inpaint and **Describe what you want**; Bonsai also fills the particle values from the prompt. Bonsai 2 runs beside ComfyUI's queue and can look at the clip; Gemma 4 E2B is a short ComfyUI job. |
| **NVIDIA** | Super Resolution and TrueHDR. Greyed out without an RTX card and ComfyUI's NVIDIA nodes. |
| **Depth model** | Video Depth Anything, or DepthCrafter when its nodes are installed: clean edges without a fringe, much slower (about 15 more minutes for 81 frames on an RTX 2080 Ti), non-commercial licence. A run reuses the kept depth only when the same model is chosen. |

<sub>[↑ Contents](#contents)</sub>

<br>

# Step by step

## 1 Clip

- **Choose a clip**<br>A video or a picture from ComfyUI's `input` folder, from your computer, dropped onto the canvas, or dragged from ComfyUI's Assets library. The list can show tiles or names, and **analysed** filters it to clips that are already analysed.
- **Pictures**<br>A still picture is held for **Length in seconds**; the effect moves over it.
- **Large clips**<br>For a clip or picture larger than 1080p, the app offers **Use a 1080p copy** (`<name>_1080p.mp4` next to it in `input`) or **Keep the full size**. Depth, light and normals are computed at the clip's resolution, so memory grows with it.
- **Short clips**<br>Clips shorter than 2 seconds have not been tested; results may vary.
- **Analysis**<br>**Analyse the scene** works out depth (Video Depth Anything), surface normals (MoGe) and the camera's motion once per clip. The canvas can then show depth and normals, and every later run of the clip reuses them. Without an analysis, the run works them out itself.

## 2 Position and tracking

### What the effect follows

Click where the effect belongs, then choose under **Follows**:

| Follows | Behaviour |
|:---|:---|
| **Point** | The exact spot you clicked, e.g. the tip of a sword. Can slip on fast, blurry motion. |
| **Object** | The whole object. Steady on fast hands and bodies; sits on the object, not on one spot. |
| **Scene** | Stays in place in the world while the camera moves, e.g. fire on the ground. |
| **Screen** | Stays at the same place in the picture. Nothing is tracked. |

### The object

- **Object word**<br>Optional. A word such as *hand* or *staff* helps the click find the right object.
- **All alike**<br>Follows every object that matches the word, e.g. all candles or all points of a crown. Off, only the clicked one is followed.
- **Paint it yourself**<br>When the click misses parts (a raised arm, a crown), paint the object in the first frame with the brush. The track follows your mask.
- **Mask frame**<br>The frame the mask is set on; normally the first. When the object is not fully in view there (a blade still in its sheath), move the playhead to a frame where it is and press **Use this frame**; **Go there** brings the playhead back to it. The track then runs from that frame to the start and to the end of the clip. The points below belong to the mask frame; choosing another frame clears them.
- **Add**<br>More of the object: words (*blade; tip*), or **Click to add** and click each part in the canvas; **Ctrl-click** works at any time. Green rings; a click on a ring takes it away. Words and points add up.
- **Leave out**<br>Parts of the object that should not give off the effect: a hand on a handle, a sheath. Words (*hand; handle*), or **Click to leave out** and click each part; **Alt-click** works at any time. Red rings. The mask frame shows what is tracked in blue and the parts left out in red. They are tracked through the clip and taken out of the object's mask; the depth and the rest of the clip stay as they are, so particles still fly over the hand.
- **Steady mask**<br>Off, **Light** (the default) or **Strong**: each frame's mask is averaged with its neighbours along the motion, so it flickers less where the object blurs or the light is poor, and a frame that loses the object takes it from its neighbours. Less sure edges stay where they touch the sure part of the object, so a fast hand does not fall apart. **Light** suits fast, small objects; **Strong** smooths large, soft ones most (a fluttering dress) but can lose a fast, small part for a frame. The kept track stays as it was tracked.
- **In front of the effect**<br>The object's mask cuts the effect out wherever the object is, whatever the depth says: a person in front of a portal. Works for every placement; in the area the effect fades out over a few pixels outside the object. With parts left out, **The parts left out are in front too** decides whether the whole object hides the effect (on) or only what is left (off).
- **Base stays on the point** <sub>Advanced</sub><br>The AI draws an effect a little differently in every frame, so its base can jitter. On, the base stays fixed on the tracked point while the effect still moves above it.

### Two points

Shift-click a second point **B** for effects that connect two positions, such as lightning or energy between the hands. Give the effect area enough room around both points, else the effect is cut at its edge.

With point B and an object word (e.g. *hand*), the word is found again in every frame and up to two objects are followed, so crossing hands are not lost. Particles then hang on the two objects, at the nearest points of their outlines.

### Track check and saved tracks

- **Track check**<br>Shows the tracked path and the object's mask before anything is generated. **Track it** and **Track it again** run only the track. The panel and the canvas name each step: finding the object, following it, drawing the mask, saving the video. The canvas shows the check as soon as its video is saved.
- **Saved tracks**<br>The object masks of a track are kept per click, word and mask. Choosing a saved track puts the points and the word back; a painted mask stays as you have it.

> [!NOTE]
> Fast motion, crossings and silhouettes without texture can lose any kind of track. On an all-black figure against a bright wall, a hand that crosses the body can be lost. Change the point, the object word or the mode, or paint the object.

### Shape of the emitter

Particle styles also ask where the particles start. Some need a click, others the object's mask:

| Shape | Needs |
|:---|:---|
| Point | A click |
| Between two points | Click A, Shift-click B |
| Drawn path | The brush (Advanced) |
| Area | The area dragged in the canvas |
| Whole frame | Nothing |
| On the object · Object outline · Object bottom edge | The object's mask: track it first |
| Groups in depth | A list of places, one per line: x, y (share of the picture), depth (0 far, 1 near), size |

## 3 Effect

### Choose and describe

- **Style**<br>Choose an effect and a style from the tiles. Styles marked **Experimental** have no tested description yet; see [Effects and styles](#effects-and-styles).
- **Strength**<br>Subtle, Normal or Strong.
- **Your effect in words**<br>The description, split into **Look**, **Motion** and **Contact** with suggestions to click. The AI follows best below 200 words.
- **✦ Enhance**<br>Rewrites your words with the text model.
- **Describe what you want** <sub>Bonsai</sub><br>Type a sentence such as *blue sparks flying off the skateboard*. Bonsai reads it with the clip's first frame and proposes a style and its words. You see each change and **Apply** it as one undo step, or **Discard** it.
- **Particles in your words** <sub>Bonsai</sub><br>Basic, particle styles: type how the particles should behave, such as *slow green sparks that spiral up*, and press **✦ Fill in**. The proposal shows each value with its reason; **Apply** sets the ticked ones, **Undo** takes them back. In Advanced the set values are marked in the emitter.
- **AI seed**<br>**Keep it** to repeat a result; off, every run uses a new seed.
- **Night or dark clip**<br>Darkens the clip for night and lets the effect light it. The AI and the light pass are made on the darkened clip, so run again to see a change.

### Where the element comes from

- **Made by: AI**<br>The AI makes a new element at **Run**. Particles, if the style or the guide has them, steer it.
- **Made by: Particles only**<br>Every style can be drawn by its particles alone, without an AI run, in about a minute. They start from the style's particles; in Advanced, **Particles** in the emitter's Source picks others (snow, sparks, smoke …).
- **Made by: Library**<br>An element you kept with **Save the element** is placed again, without a new AI run. Position, size, light and glow follow this style; the words are not used. Only on black.

### Placement

- **Placement**<br>Basic and Advanced, every style except Dissolve and Climbs: where the element goes. **Point** stands on point A and follows it; **Area** makes it in the frame around A that you size in the canvas; **Object** covers the clicked object and moves with it; **Frame** puts it over the whole picture, no point needed; **A–B** stretches it from A to B (Shift-click B). The style's own placement is marked in the tooltip; choosing another one also starts the particles in that shape (the whole frame, the object, the line A–B) unless you set the shape yourself.
- **Sits on A by**<br>With **Point**: the element's **Bottom** edge stands on A (a flame, a plant), or its **Centre** is on A (a glow, a swirl).

### Guide for the AI

| Guide | What the AI does |
|:---|:---|
| **Free** | Paints the element freely from the prompt. |
| **Object shape** | Shapes the element to the object it sits on (a flame wraps round the fist). The object's depth guides it, only near the object. Needs the object: click it in Position. |
| **Drawn path** | Follows the strokes you paint on the canvas while this step is open. |
| **Particles** | The emitter shapes where and how it moves; the AI paints the look. |

**Guide strength** <sub>Advanced</sub> sets how closely the AI follows. Each style brings the guide it was tested with; every style can take any guide.

- **The same emitter for every style** <sub>Advanced</sub><br>The emitter shows the same groups and controls whatever the style: a preset only sets their values. An AI element shows the particles it would start from; they come in when they guide the AI, are drawn over its element (**Also draw the particles**) or make it (**Made by: Particles only**). **Let them guide the AI** switches the guide in one click.
- **AI element** <sub>Advanced</sub><br>**Solid element** cuts the element out with its own matte (liquid, dust, stones) instead of its brightness. **Particles start the AI's video** lets the AI start from the particles' picture as well as be guided by it. Both for every style.
- **Paths** <sub>Advanced</sub><br>Any style can draw a path over its particles: a **Bolt** from A to B (without B it strikes down), a charge that **Climbs** the thin parts of the tracked object, or **Cracks** spreading from A. Each path's own values are under **More path settings**.

### Live preview

For particle styles, the **live preview** simulates the particles on your clip with the same engine and seed as the run.

- **Play with clip** · **Hold frame**<br>The particles play with the clip, or the clip stands on the playhead while the emitter keeps running.
- **Pre-roll**<br>**Preset**, **Auto** (long enough for the particles to cross the frame) or your own **Seconds**. The particles run this long before the clip starts, so snow or rain already fills the first frame.
- **Particle seed**<br>The same seed gives the same particles in the preview and in the run. **New seed** tries others; **Lock** keeps it.

Without an analysis, nothing in the clip hides the particles yet; without a kept track, they hang on your point. The particles show in the **Clip** view; when another view hides them, the canvas says so and offers **Back to the clip**.

## 4 Scene and finish

After a run, these controls change the result at once, without a new run. A changed control shows **Reset**.

### The effect

| Control | What it does |
|:---|:---|
| **Light on the scene** | Off, Low, Medium or High: the light the effect throws onto the clip. Needs a light pass; with Inpaint the light is already part of the picture. |
| **Glow** | Soft glow around the bright parts of the effect. |
| **Lit by the other effects** | The light of the other effects brightens this one where it falls, e.g. smoke near a flame. Shown with several effects. |
| **Colour** | Original, a swatch, your own colour, or a colour taken from your clip (E). Tints the effect, its light and its glow. |
| **Brightness** | − and +, at the playhead when brightness keys are set. |
| **Placement** | Move, size or turn the effect in the canvas. **Back to where it was made** resets it. |

### The clip (all effects)

| Control | What it does |
|:---|:---|
| **Brightness of the clip** | In stops. |
| **Warmth** | Warmer or cooler. |
| **Colour strength** <sub>Advanced</sub> | Saturation of the clip. |
| **Depth blur** | The focus stays on the effect as it moves; the farther something is in depth from it, the softer. |
| **Sharp around the effect** <sub>Advanced</sub> | How wide the sharp zone around the effect is. |

Light controls use the passes of the selected version. If they are missing, add a light pass to that version or choose one that has it.

## 5 Output

| Setting | Choices |
|:---|:---|
| **Quality** | **Preview (fast)**: half the size, without light, glow and normals, for AI elements in Overlay. **Full**: full size with all passes. |
| **Upscale** | Off · **LTX × 2** (a second LTX pass at twice the size: more detail, takes longer) · **NVIDIA × 2** (RTX Super Resolution: fast, draws nothing new). |
| **Passes** | Light · Glow · Depth · Normals · Mask (the object's mask per frame). Plate and element with its alpha are always written. A preview writes plate, element and depth only. |
| **Save the element** | Also keeps an AI element with its alpha in the element library, to place it again without a new run. |

Then **Run**. The result lands in the versions of the effect; see [Versions](#versions) and [Export](#export).

<sub>[↑ Contents](#contents)</sub>

<br>

# Effects

## Effects and styles

*AI* styles are made with LTX-2.5 and take minutes. *No AI* styles are drawn by the particle engine and are fast. Styles marked ⚗ are experimental: no tested description yet, and the app says so before you generate.

| Effect | Styles |
|:---|:---|
| **Fire** | Flame on the object · Short burst · Smoldering ground ⚗ |
| **Lightning** | Between two points · Climbs an object: fine filaments · Climbs an object: blue arcs ⚗ · Climbs an object: particles only *(no AI)* |
| **Sparks** | From a moving object ⚗ · Burst from a point |
| **Smoke** | Rises from a point · Rises from a point: particles only *(no AI)* |
| **Magic & energy** | Aura around a figure · Aura: particles only *(no AI)* · Energy between two points ⚗ · Energy ball |
| **Snow, rain & fireflies** | Snow · Rain · Fireflies *(no AI)* |
| **Dust & debris** | Debris burst · Debris burst: particles only *(no AI)* · Dust burst |
| **Liquid** | Drips from a point |
| **Dissolve** | Crumbles into particles · Gold dust · Burns away |
| **Your own effect** | At a point ⚗: describe any element yourself |

- **Dissolve**<br>Runs its own graph. The clicked object, or a mask you paint, crumbles away while the background behind it is filled in (**Background**: auto, smooth or structured). *Gold dust* and *Burns away* light the scene from their glowing edge and particles; *Crumbles into particles* does not glow and writes no light.
- **Climbs an object**<br>Runs its own graph. Click the thin object and give a word (*thin stick*, *staff*, *snake*). For all sticks of a crown, turn on **All alike**.

## Overlay or Inpaint

**How it goes in** chooses the route for AI effects at a place in the clip. It does not apply to Snow and Rain, the *Climbs an object* styles or Dissolve.

| | Overlay | Inpaint |
|:---|:---|:---|
| **How** | The effect is made alone on black and laid over your clip. | The AI repaints that part of your clip with the effect. |
| **Afterwards** | Light, glow, colour and placement stay adjustable. | Light and place are part of the picture. |
| **Best for** | Glowing effects. Start here. | Contact with surfaces; the effect takes on the light of the scene. |
| **Preview quality** | Yes | No, always full size |

- **Scene sentence**<br>For Inpaint, the text model writes one sentence about the area around the effect when you run, or you type it yourself. It keeps the repainted area the same scene.
- **Keep the original** <sub>Advanced</sub><br>Repaints less of the area, so it stays closer to the clip. The effect gets less room; a thin one like lightning can vanish.
- **Two points**<br>Painted in between two points, the track holds better with a word for the objects. When the word field is empty, the app sends *hand*.
- **Tested**<br>Inpaint worked for sparks from a moving object, smoke, a flame, and lightning and energy between the hands. For most other styles, Overlay gave the clearer result.

Glowing effects are keyed by their colour and added; solid ones (smoke, debris, liquid) are laid over. With the light switched off, no light and normals passes are written; the light pass can be added later.

## Several effects on one clip

**＋ Effect** in the strip at the top adds another effect to the same clip. Each effect has its own settings, runs and versions. In **Scene & finish**, **Lit by the other effects** lets the light of the others fall on it, in the live view and in the export. The export renders all effects with a shown version together.

<sub>[↑ Contents](#contents)</sub>

<br>

# Your own effects

## Make your own effects

1. **Describe it**<br>Choose **Your own effect** and describe any element in words. It is generated with LTX-2.5 and stays on the point you click. Things that glow work best.
2. **Shape it with particles**<br>Switch the app to **Advanced**. In **Effect**, the **Emitter** shows every control of a particle style. Changed values are highlighted and can be reset one by one or with **Reset all**. The [live preview](#live-preview) shows the result on your clip.
3. **Keep it**<br>**Save as my effect** stores the style, its words, the emitter values and the switches. Clip, position and track stay with the shot. Your saved effects appear under **My effects** for every clip, ready to load, rename or delete. They are kept in ComfyUI's user folder under `element-forge/my-effects/`.

## Particles and the AI

Element Forge has its own particle engine. It uses the clip's analysis, so particles behave like part of the scene.

| Route | What happens |
|:---|:---|
| **Particles only** | The simulation is the finished effect. No AI generation; the fastest route. |
| **Particles guide the AI** | The particle paths, as lines or volume, set where and how the element moves. LTX-2.5 paints its look. |
| **Start video** | The rendered particles are the start of the generation. A custom sprite acts only here. |
| **Also draw the particles** | Drawn particles are added over the AI element. |

<details>
<summary><b>How the simulation works</b> &nbsp;·&nbsp; emitter, forces, depth, look</summary>
<br>

| Stage | What happens |
|:---|:---|
| **Emitter** | Particles start at a point, between two points, along a drawn path, in an area, across the whole frame, on an object, along its outline or bottom edge, or in groups placed in depth. |
| **Birth** | Each particle gets a life, size, speed and direction: at an angle, outward from the object, against the emitter's motion (grinding sparks) or random. Rate and bursts decide when they appear. |
| **Forces** | Every step applies gravity, wind, drag, swirling turbulence (curl noise), a vortex around the emitter, attraction to point B and flocking, where neighbours pull together into streams and drops. |
| **Motion from the clip** | Particles take on part of the emitter's movement. Optical flow of the footage lets moving things carry them along, such as a hand sweeping through smoke. The measured camera motion keeps them in place in the scene while the camera moves. |
| **Depth and contact** | Each particle has a depth in the scene. Nearer objects hide it, and where it meets a surface it can bounce, stick, slide or die. Rain and liquid drops splash on impact. |
| **Look** | Sprites (soft, dot, flake, puff, wisp, streak, spark or chunk), colour and size over the particle's life, trails, motion blur, flicker and glow. **Merge into one body** blurs neighbouring particles together for liquid edges or fire tongues. |
| **Paths** | Lightning is drawn as jagged, branching bolts that change shape every few frames. Climbing arcs run along the thin parts of an object. Cracks and frost grow across a surface. |
| **Seed** | The same particle seed gives the same particles in the live preview and in the run. |

</details>

## Which particles for which effect

Tested with the same graphs. In the workflow, these are the settings of **EF Guide** (*guide*: particles, *guide particles*: the preset) and **EF Particles**.

<details>
<summary><b>Test results by preset</b> &nbsp;·&nbsp; sparks, lightning, smoke, snow, debris and more</summary>
<br>

| Preset | Works best with | Notes |
|:---|:---|:---|
| **sparks** | Guide (lines) | Long sparks flying off a skate wheel or a hand; as start video only a short burst. |
| **lightning, energy A-B** | Guide, window between A and B | Give the window room around both points (e.g. 800×1200), else the bolt is cut at its edge. |
| **lightning climb** | Guide, or particles only | The charge crawls along the object and jumps from its tips. With LTX, describe **hair-thin filaments**; "lightning arcs" made LTX paint a wide, clipped plasma tube. On a bright plate the filaments almost vanish; there use particles only or the arcs style. |
| **magic dust, line A-B** | Guide | A dense glowing band between two hands; lower the amount for a finer band. |
| **rain** | Guide | Prompt "many fast bright streaks … no fog". Rain adds light, so it shows on dark plates, hardly on bright ones. |
| **liquid** | Guide, collision none | A guided stream; with collision the stream bursts at once on the surface below. |
| **smoke** | Guide (volume) | A thin, curling, translucent plume; as start video (sprite *wisp*) a denser but blob-like column. |
| **snow** | Start video (soft flakes), or Guide with a "heavy snowfall" prompt | Start video: clean but sparse, more than ×1 turns into bokeh discs. Guide: dense, with a few dark specks. |
| **dust burst** | Start video or Guide (volume) | Both work; stays small. |
| **aura** | Guide, on black over the whole figure | A glowing halo with rising strands behind head and shoulders; the face stays clear. Inpaint gives only glassy streaks. Particles only: a glowing envelope with rising wisps just outside the outline. |
| **fireflies** | Guide | Soft glowing points across the whole frame, near ones bigger; as start video nothing showed. |
| **embers** | Guide | Glowing embers with curved trails from a hand. |
| **fire (on a hand)** | – | The guide gives glowing embers, not flames; use the flame element. |
| **frost** | Guide, Inpaint | Sharp pale blue crystal clusters over the object. Prompt *crystals grow along thin branching lines, the stone between them stays clearly visible*; "the whole statue frozen" lays a grey glassy veil over it. |
| **cracks** | Particles only, on a hard surface | Dark grooves with a lit lower edge that stay on the surface and hide behind what moves in front. With LTX they come out as painted glowing lines; on soft ground they read as twigs. |
| **debris** | Guide | Chips and a dust cloud burst up where a skate hits the ground. Describe a dull, dusty, matte material in daylight; hot colour words made LTX paint glowing embers. Without LTX the chunks take the colour of the ground. |
| **own sprite** | Start video | A custom sprite acts only in the start video. |

</details>

## Emitter controls

Shown in **Effect** in Advanced mode. Values left alone keep the style's tested settings.

- **Closed**<br>Each group shows its main values in one line, and a badge counts the values you changed.
- **Open**<br>A changed value has a bar in the accent colour; **×** takes it back to the style's value, which the small tick under the slider marks. **More … settings** at the end of a group names what it holds.
- **✦ Fill from the prompt** <sub>Bonsai</sub><br>Bonsai reads the effect's words against the style's own and proposes the emitter values that change, each with its reason, about 20 s. Untick what you do not want, then **Apply**; **Undo** takes all of them back. Every value stays within its slider's range and at most five times or a fifth of the value now.
- **While you change a value**<br>Colour, glow, trail, opacity, motion blur and Merge draw at once, even while you drag. A value that changes the simulation keeps its place in the panel; the old particles dim and **Updating the particles…** shows in the canvas until the new simulation is there.

| Group | Controls |
|:---|:---|
| **Source** | Guide for the AI and how the particles are drawn for it (lines, volume, heat, depth), the particles it starts from, emitter shape and size, maximum particles alive at once |
| **Emission** | Rate, burst and when it comes, timing, pre-roll |
| **Motion** | Direction mode (angle, outward, against motion, random) and direction, spread, speed and its variation, lift; how far the particles follow the emitter (strength, lag) and how much the clip carries them; bunch to the centre of the spread, speed at the end of the life, speed limit |
| **Particle** | Life, size and their variation, size at birth and at the end, colour over life and its variation, sprite, trail, glow, flicker (speed, by size), small particles (share, size, speed, life), fade in and out, motion blur, opacity, spin |
| **Merge** | Merge into one body: blur, choke, edge, fill, only while young |
| **Forces** | Gravity, wind (sideways, up and down), drag, turbulence (size, change, fades in, calmed by drag), vortex, attraction to B, flocking (reach, pull) |
| **Contact & depth** | Collision (none, bounce, stick, slide, die), bounce, friction, lying time of sticking particles, depth offset and spread, hidden by the scene |

**Calm particles**: lower the speed, set **Speed at the end** below 1 so they come to rest, a **Speed limit**, **Spin** 0, and **Drag calms turbulence** or **Turbulence fades in** so the swirl does not take over. For AI styles (fire, orb, your own effect) the speed is set by the AI; set the guide to **Particles** to get the emitter's speed.

**Drawn for the AI as: Depth** gives the AI the clip's depth of the clicked object, with the particles' surfaces wherever they are in front of it: one guide from the same simulation. **Depth shows** picks the object or the whole scene (the AI may then redraw the background); **Object as** the whole object or only a thin **Inner edge** (width in pixels), so the AI follows the outline and builds less of a body. It needs the object's track; a bolt, a climb or cracks are drawn over it as lines.

Lightning paths have their own look (width, glow, jaggedness, branches, new shape every few frames); Dissolve has its own emission, motion, particle and force controls.

**Crumble** (every style except Dissolve): turn on **The object crumbles** and the clicked object falls apart into particles under the effect while the scene behind it appears, for example a statue that burns away while the flames rise. **Look** is *Crumbles* (the object's own colours), *Gold dust* or *Burns away* (embers painted by the AI); **Direction** is the way the pieces fly; **Background** fills the place behind it. The pieces keep values of their own (emission, motion, particle, forces) under **More**, so the falling stone and the rising flames do not share one gravity. The crumbling runs over the effect's time in the timeline. It is the clip under the effect, so it shows when this effect is the first in the list; the live preview shows the effect's particles, the crumbling shows after the run.

<sub>[↑ Contents](#contents)</sub>

<br>

# Results

## Versions

Every run of an effect becomes a version. Under **Versions** in Output:

- **Show**<br>Shows a version on the canvas and in Scene & finish.
- **Compare N with**<br>Splits the canvas: one version left of the line, the other right of it.
- **Use the settings of version N**<br>Brings back the style, the words, the seed and the place it was made with. Light, glow, colour and placement in Scene & finish stay. Ctrl+Z undoes it.
- **Make version N final (× 2)**<br>Goes on from a preview with LTX's second pass (latent upscaler × 2): twice the size, sharper, same shape and motion. It comes as a new version with all passes.
- **Add passes**<br>**Light pass**, **Glow pass** or **Normals** for a version that lacks them, decoded again from its kept latent, without generating the effect again. A light pass takes about a minute.

## Export

**Export** in Output renders at full size:

- **With a shown version**<br>The comp as you see it: all effects with a shown version, with the values of Scene & finish.
- **Without a run**<br>The clip alone, as graded in Scene & finish. Use it for the clip's passes, NVIDIA × 2 or HDR without generating an effect. Output opens for this as soon as a clip is chosen.

| Setting | Choices |
|:---|:---|
| **Format** | **MP4** (H.264, 8 bit: plays everywhere) · **ProRes** (422 HQ .mov, 10 bit: for editing, no banding in glow) · **H.265** (10 bit: small files without banding) · **PNG** (8 or 16 bit per frame) · **EXR** (half float, linear Rec.709, for compositing) |
| **Frames** | **Whole clip** or **Where the effects are** (from the effects' bars in the timeline). Shown when there are effects. |
| **Passes as EXR** | Each on its own: **Effect passes** (light, element, smoke and glow of every effect, as they go into the comp) · **Plate** · **Depth** · **Normals** · **Object mask**. Half float, scene-linear, in `layers/`. |
| **NVIDIA × 2** | RTX Super Resolution at twice the size. With effects: **Plate only** (only the clip gets new detail; the effects are scaled up as they are, so light and glow keep their look) or **With the effects** (the finished comp). Without effects: **On**. The passes come at the same size. |
| **HDR (NVIDIA TrueHDR)** | With H.265 on an RTX card: HDR10 (PQ, BT.2020). With effects, **HDR on** chooses **With the effects** (TrueHDR expands the finished comp) or **Plate only** (TrueHDR expands the clip; the effects keep their own brightness on top). |
| **Folder name** | Optional; the clip's name otherwise |

**Play it** shows the finished export in the app.

> [!TIP]
> **Depth and normals of the clip alone**<br>Without an analysis, the export works them out first (a few minutes). With an analysis, it uses the kept one.<br>
> **Object mask**<br>Without a run, it needs a point: click the object in **Position & Track**. With a run, normals and the mask come from the shown versions, so turn them on under **Passes** before the run.

> [!NOTE]
> Element and light passes are scene-linear. EXR keeps that working space; do not apply a second display conversion in your compositing application. Use the exported alpha with the matching element pass; additive light passes and ordinary layers need different blend modes.

## Files and folders

Everything lands in ComfyUI's output folder:

| Folder | Contents |
|:---|:---|
| `element-forge/<run>/` | One run: comp MP4, the passes as EXR (`plate`, `element`, `light`, `glow`, `depth`, `normals`, `mask`), the settings |
| `element-forge/app-export-<name>-<time>/` | One export: the comp in the chosen format, `layers/` with the passes |
| `element-forge/clips/<clip>/` | The clip's kept analysis and tracks |
| `element-forge/elements/<name>/` | The element library |

## Run times

<details>
<summary><b>Measured run times</b> &nbsp;·&nbsp; RTX 2080 Ti 11 GB and RTX PRO 4500 32 GB</summary>
<br>

Effect *Fire · Flame on the object*, from queueing to the finished comp with all passes. From the second row of a clip on, its analysis was reused, as the app does for every further run; on the 32 GB card both clips were analysed before. *Cold*: the first run after starting ComfyUI, including loading the models.

| Clip | Element | Quality | RTX 2080 Ti 11 GB | RTX PRO 4500 32 GB |
|:---|:---|:---|:---|:---|
| Katana, 1920×1012, 89 frames | AI element on black, overlay | Preview | 3.8 min (cold) | 1.1 min |
| Katana, 1920×1012, 89 frames | AI element on black, overlay | Full | 4.2 min | 1.9 min |
| Katana, 1920×1012, 89 frames | AI element in the plate (inpaint) | Full | 5.3 min | 1.9 min |
| Katana, 1920×1012, 89 frames | AI element guided by particles | Preview | 2.6 min | 1.7 min |
| Katana, 1920×1012, 89 frames | AI element guided by particles | Full | 4.9 min | 4.0 min |
| Glowing ball, 720×1280, 160 frames | AI element on black, overlay | Preview | 2.2 min | 1.6 min |
| Glowing ball, 720×1280, 160 frames | AI element on black, overlay | Full | 5.5 min | 2.5 min |
| Glowing ball, 720×1280, 160 frames | AI element in the plate (inpaint) | Full | 6.6 min | 2.6 min |
| Glowing ball, 720×1280, 160 frames | AI element guided by particles | Preview | 2.2 min | 1.8 min |
| Glowing ball, 720×1280, 160 frames | AI element guided by particles | Full | 5.3 min | 4.9 min |

Earlier on the 2080 Ti, each including the analysis: a 161-frame portrait clip with a climbing bolt took 12.5 minutes, a dissolve 14.5 minutes. A place-only shot from the element library took about 5 minutes. Changing only the light took 1.5–3 minutes.

</details>

<sub>[↑ Contents](#contents)</sub>

<br>

# Workflow

## Use the workflow

Open **Element Forge** from the same template list, or drag [Element Forge.json](../example_workflows/Element%20Forge.json) onto ComfyUI's canvas. Put your clip into ComfyUI's `input` folder and choose it in **Load Video** (the template names `my_clip.mp4`).

**Load Video → EF Shot → EF Track → EF Element → EF Place → EF Light & Glow → EF Export**

| Node | Step |
|:---|:---|
| **EF Shot** | The clip, depth model, night |
| **EF Track** | Click into the first frame for point A, Shift-click for B; object word, what it follows |
| **EF Element** | Effect and style, overlay or inpaint, words, timing, quality (the template starts on preview) |
| **EF Place** | Size, side, depth, blend |
| **EF Light & Glow** | Light and glow on the scene |
| **EF Export** | Run name, EXR passes, track check |

**EF Models** sets which LTX files this computer uses. Then **Run**. The comp shows on EF Export, the track check on EF Track, the element on EF Element.

- **Options**<br>**EF Particles**, **EF Guide** (with a Load Image for a drawn path), **EF Dissolve**, **EF LTX Options**, a Load Image for your own object mask and **EF Library Element** are in the workflow but bypassed. Select one and press **Ctrl+B** to use it.
- **Style defaults**<br>Every value of an option starts at **style default** (numbers: −2), the style's tested value. Set only what you want to change.
- **Advanced inputs**<br>Rarely used fields are hidden in the Vue node view until you choose *Show advanced inputs* in the node's menu; the classic view shows them all.
- **Same graph as the app**<br>When the run is queued, the chain of EF nodes is replaced by the graph the app runs. The template, the app and a chain you build yourself give the same graph for the same settings.
- **Cache**<br>Change only the light strength or the glow and run again: the element comes from ComfyUI's cache while memory allows. Element Forge frees the cache when the computer's memory runs short.

## Effect keys

<details>
<summary><b>The value of <i>effect</i> on EF Element</b> &nbsp;·&nbsp; and its name in the app</summary>
<br>

| `effect` | In the app | |
|:---|:---|:---|
| `fire/flame` | Fire · Flame on the object | AI |
| `fire/burst` | Fire · Short burst | AI |
| `fire/smolder` | Fire · Smoldering ground | AI ⚗ |
| `lightning/between` | Lightning · Between two points | AI |
| `lightning/climb` | Lightning · Climbs an object: fine filaments | AI |
| `lightning/climb_arcs` | Lightning · Climbs an object: blue arcs | AI ⚗ |
| `lightning/climb_drawn` | Lightning · Climbs an object: particles only | no AI |
| `sparks/grind` | Sparks · From a moving object | AI ⚗ |
| `sparks/burst` | Sparks · Burst from a point | AI |
| `smoke/rise` | Smoke · Rises from a point | AI |
| `smoke/rise_drawn` | Smoke · Rises from a point: particles only | no AI |
| `magic/aura` | Magic & energy · Aura around a figure | AI |
| `magic/aura_drawn` | Magic & energy · Aura: particles only | no AI |
| `magic/flow` | Magic & energy · Energy between two points | AI ⚗ |
| `magic/orb` | Magic & energy · Energy ball | AI |
| `weather/snow` | Snow, rain & fireflies · Snow | AI |
| `weather/rain` | Snow, rain & fireflies · Rain | AI |
| `weather/fireflies` | Snow, rain & fireflies · Fireflies | no AI |
| `debris/debris` | Dust & debris · Debris burst | AI |
| `debris/debris_drawn` | Dust & debris · Debris burst: particles only | no AI |
| `debris/dust` | Dust & debris · Dust burst | AI |
| `liquid/drip` | Liquid · Drips from a point | AI |
| `dissolve/plain` | Dissolve · Crumbles into particles | AI |
| `dissolve/gold` | Dissolve · Gold dust | AI |
| `dissolve/fire` | Dissolve · Burns away | AI |
| `own/point` | Your own effect · At a point | AI ⚗ |

</details>

## Reuse an element

Generating an element with LTX is the slow part; placing a saved one skips it. Tracking, lighting and compositing still run as needed.

- **In the app**<br>Turn on **Save the element** in Output for an Overlay run. Later choose **From the library** in Effect.
- **In the workflow**<br>*save element* in **EF Export** keeps it; connect **EF Library Element** to EF Place's *own element* input to place it.
- **From another generator**<br>**EF Element from Images** turns frames from another generator, with an optional alpha, into an element for EF Place. It is saved once into the library and then placed like a generated one.
- **By hand**<br>**EF Save Element** keeps an element as a 16-bit RGBA sequence with a manifest in `output/element-forge/elements/<name>/`; **EF Load Element** brings it back and checks every frame against the manifest.

## Build a custom graph

- **EF Unpack**<br>Exposes the parts of a run as ordinary outputs: plate, depth, normals and object mask from EF Shot and EF Track, the element (linear, on black) with its alpha, light, glow and the comp. Only what is connected is computed.
- **EF Shot**<br>Accepts a video, frames from other nodes (*images* with *fps*) or a single picture (*picture*, held for *still length*).
- **Compositing tools**<br>EF Glow, EF Depth Light, EF Deflicker, EF Dither, EF Unmult, EF MoGe Normals, EF Save Element and EF Load Element, under Element Forge in the node list. See the [node reference](nodes.md).
- **Scripting**<br>`api_workflows/` holds the graphs the app and the workflow run, in API format: `element_forge_app.json`, `element_forge_climb.json` (lightning that climbs an object), `element_forge_dissolve.json` and `element_forge.json` (the track check). Their values come from `element_forge.settings.json`; `element_forge.stages.json` maps their nodes to the EF stage nodes.

<sub>[↑ Contents](#contents)</sub>

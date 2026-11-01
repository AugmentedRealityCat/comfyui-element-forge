# Setup

[README](../README.md) · [Usage](usage.md) · [Nodes](nodes.md) · [Licenses](licenses.md)

## Before you start

Use ComfyUI 0.41.2 or newer and the Python environment that runs it. The AI routes have been tested on NVIDIA GPUs with 11 GB VRAM and above, on Windows and Linux. A lower VRAM limit has not been established; Apple, AMD and Intel GPUs have not been tested.

Allow about 45 GB for the default models. System RAM use depends on the models, clip resolution and enabled passes. A minimum RAM requirement has not been established. Start with a short clip at 1080p or below and use Preview quality.

## Install the node packs

From your ComfyUI folder, with its Python environment active:

```bash
cd custom_nodes
git clone https://github.com/yuvraj108c/ComfyUI-Video-Depth-Anything
git clone https://github.com/Lightricks/ComfyUI-LTXVideo
git clone https://github.com/Zitroffi/comfyui-element-forge
python -m pip install -r ComfyUI-Video-Depth-Anything/requirements.txt
python -m pip install -r ComfyUI-LTXVideo/requirements.txt
python -m pip install -r comfyui-element-forge/requirements.txt
```

For **Windows portable**, clone the same repositories into `ComfyUI/custom_nodes`. Then run these commands from the `ComfyUI_windows_portable` folder:

```bat
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-Video-Depth-Anything\requirements.txt
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-LTXVideo\requirements.txt
python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\comfyui-element-forge\requirements.txt
```

Restart ComfyUI after installation. The templates appear under **Templates → Extensions → comfyui-element-forge**.

## Default models

Folders below are inside `ComfyUI/models`. Keep the listed filenames. Some model providers require you to sign in and accept their terms before downloading.

The gear at the top of the Element Forge app lists model status, size, destination and source. It also lets you choose another installed LTX model.

| File | Folder | Source |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | `diffusion_models` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `text_encoders` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) |
| `ltx-2.5-video-vae-conv-bf16.safetensors` | `vae` | [LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `ltx-2.5-audio-vae-bf16.safetensors` | `vae` | [LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `latent_upscale_models` | [LTX-2.5-GGUF](https://huggingface.co/unsloth/LTX-2.5-GGUF) |
| `sam3.1_multiplex_fp16.safetensors` | `checkpoints` | [Comfy-Org/SAM 3.1](https://huggingface.co/Comfy-Org/sam3.1) |
| `video_depth_anything_vits.pth` | `videodepthanything` | [Video Depth Anything Small](https://huggingface.co/depth-anything/Video-Depth-Anything-Small); also downloads on first use |
| `moge_2_vitl_normal_fp16.safetensors` | `geometry_estimation` | [Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe) |
| `ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors` | `loras` | [Motion Track Control](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control) |
| `ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors` | `loras` | [Alpha Gen](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen) |
| `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` | `loras` | [Union Control](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control); the 2.5 workflow uses this 2.3 LoRA |
| `ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors` | `loras` | [Clean Plate](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate), used by Dissolve |

After adding the models, open **Element Forge (app)** and follow [Your first effect](../README.md#your-first-effect).

## Optional additions

Start with the defaults. Add these only when you need their features.

| Feature | Addition |
|---|---|
| Prompt enhancement | `gemma4_e2b_it_int8_convrot.safetensors` from [Comfy-Org/Gemma 4](https://huggingface.co/Comfy-Org/gemma-4) in `text_encoders`, or Bonsai 2 below. The LTX text encoder is separate. |
| Smaller LTX model | `ltx-2.5-22b-distilled-transformer-bf16-Q4_K_M.gguf` from [LTX-2.5-Comfy-GGUF](https://huggingface.co/agosh/LTX-2.5-Comfy-GGUF) in `unet`. Requires [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF). Leave INT8 attention off with GGUF. |
| NVIDIA upscale and HDR | [NVIDIA VFX nodes](https://github.com/Comfy-Org/ComfyUI_Nvidia_VFX_Nodes) and their requirements; RTX 20 series or newer. |
| Alternative depth | [DepthCrafter nodes](https://github.com/akatz-ai/ComfyUI-DepthCrafter-Nodes). The model has a non-commercial license. |

### Bonsai 2

Bonsai adds prompt help, **Describe what you want**, which can set up an effect from a sentence and the clip's first frame, and **✦ Fill from the prompt**, which sets the particle values from the effect's words.

In the app, open **Advanced → Effect → Description → Install Bonsai 2**. The installer shows the download size and filenames, checks their published hashes, and installs the model and runtime. No restart is needed.

The app's gear menu selects the language model when more than one is installed.

## Troubleshooting

- **Templates or nodes missing:** check ComfyUI's startup log for import errors. Install requirements with ComfyUI's Python, then restart.
- **Missing models:** use the app's model list to check the exact filename and folder. Video Depth Anything Small may download on its first run.
- **Running out of memory:** use a shorter or smaller clip, Preview quality and fewer passes. **The object crumbles** together with an AI effect runs a second LTX pass for the background behind the object; on a 1080p clip of 89 frames it took about 70 GB of system RAM in testing, so start it on a freshly started ComfyUI. ComfyUI's `--cache-none` option can reduce retained results, at the cost of recomputing them. On Windows, a small page file can also limit available memory.
- **`cv2` package conflict:** `opencv-python` and `opencv-python-headless` provide the same module; avoid keeping conflicting installations in the same environment.
- **NVIDIA VFX fails to import:** check that its dependencies installed successfully. Errors such as `wheel_stub.buildapi` or missing `nvvfx` affect the optional NVIDIA feature; leave it disabled while resolving the installation.
- **Bonsai reports `no CUDA backend`:** check that the installed runtime matches the CUDA version used by ComfyUI. The model may otherwise run on the CPU.

For a reproducible issue, include the error, ComfyUI version, operating system, chosen model and relevant settings in [an issue](https://github.com/Zitroffi/comfyui-element-forge/issues).

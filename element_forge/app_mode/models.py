import os

MODELS = [
    {"file": "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors", "folder": "diffusion_models", "gb": 21.5,
     "source": "https://huggingface.co/Lightricks/LTX-2.5", "for": "Makes the effects (LTX-2.5, INT8)", "group": "ltx", "need": "yes"},
    {"file": "ltx-2.5-22b-distilled-transformer-bf16-Q4_K_M.gguf", "folder": "unet", "gb": 12.2,
     "source": "https://huggingface.co/agosh/LTX-2.5-Comfy-GGUF", "for": "LTX with less memory (GGUF Q4, needs ComfyUI-GGUF); slower on RTX 20",
     "group": "ltx", "need": "option"},
    {"file": "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors", "folder": "text_encoders", "gb": 15.4,
     "source": "https://huggingface.co/Lightricks/LTX-2.5", "for": "Reads the prompt for LTX (Gemma 12B, INT8)", "group": "te", "need": "yes"},
    {"file": "gemma4-12b-with-proj-ltx-2.5-bf16.safetensors", "folder": "text_encoders", "gb": 26.3,
     "source": "https://huggingface.co/unsloth/LTX-2.5-GGUF", "for": "The same text encoder in bf16: 11 GB more, same result in our test",
     "group": "te", "need": "option"},
    {"file": "ltx-2.5-video-vae-conv-bf16.safetensors", "folder": "vae", "gb": 1.45,
     "source": "https://huggingface.co/unsloth/LTX-2.5-GGUF", "for": "LTX video decoder", "group": None, "need": "yes"},
    {"file": "ltx-2.5-audio-vae-bf16.safetensors", "folder": "vae", "gb": 0.36,
     "source": "https://huggingface.co/unsloth/LTX-2.5-GGUF", "for": "LTX audio decoder (the graph loads it with the video one)", "group": None, "need": "yes"},
    {"file": "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors", "folder": "latent_upscale_models", "gb": 1.0,
     "source": "https://huggingface.co/unsloth/LTX-2.5-GGUF", "for": "Upscale LTX × 2 and Make final", "group": None, "need": "some"},
    {"file": "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors", "folder": "loras", "gb": 0.65,
     "source": "https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control", "for": "Guide for the AI (particles, drawn path, object shape)",
     "group": None, "need": "some"},
    {"file": "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors", "folder": "loras", "gb": 0.33,
     "source": "https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Motion-Track-Control", "for": "Follows motion", "group": None, "need": "some"},
    {"file": "ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors", "folder": "loras", "gb": 0.33,
     "source": "https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Clean-Plate", "for": "Dissolve: the background behind the object",
     "group": None, "need": "some"},
    {"file": "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors", "folder": "loras", "gb": 1.22,
     "source": "https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-In-Outpainting",
     "for": "Dissolve: the background behind the object with a soft edge (the default)", "group": None, "need": "some"},
    {"file": "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors", "folder": "loras", "gb": 1.31,
     "source": "https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen", "for": "Effects from a clip with alpha", "group": None, "need": "some"},
    {"file": "sam3.1_multiplex_fp16.safetensors", "folder": "checkpoints", "gb": None,
     "source": "https://huggingface.co/Comfy-Org/sam3.1", "for": "Object masks and tracks (SAM 3.1)", "group": None, "need": "yes"},
    {"file": "video_depth_anything_vits.pth", "folder": "videodepthanything", "gb": 0.12,
     "source": "https://huggingface.co/depth-anything/Video-Depth-Anything-Small", "for": "Depth (the node fetches it on first use)",
     "group": None, "need": "yes"},
    {"file": "moge_2_vitl_normal_fp16.safetensors", "folder": "geometry_estimation", "gb": 0.66,
     "source": "https://huggingface.co/Comfy-Org/MoGe", "for": "Surface normals for the light on the scene", "group": None, "need": "some"},
    {"file": "gemma4_e2b_it_int8_convrot.safetensors", "folder": "text_encoders", "gb": 4.8,
     "source": "https://huggingface.co/Comfy-Org/gemma-4", "for": "Text model for Enhance when Bonsai 2 is not set up", "group": "lm", "need": "option"},
]
REPO_PATH = {
    "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors": "diffusion_models/",
    "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors": "text_encoders/",
    "gemma4_e2b_it_int8_convrot.safetensors": "text_encoders/",
    "ltx-2.5-video-vae-conv-bf16.safetensors": "vae/",
    "ltx-2.5-audio-vae-bf16.safetensors": "vae/",
    "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors": "latent_upscale_models/",
    "ltx-2.5-22b-ic-lora-alpha-gen-0.9.safetensors": "",
    "ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors": "",
    "ltx-2.3-22b-ic-lora-in-outpainting-0.9.safetensors": "",
    "ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors": "",
    "ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors": "",
    "sam3.1_multiplex_fp16.safetensors": "checkpoints/",
    "moge_2_vitl_normal_fp16.safetensors": "geometry_estimation/",
    "video_depth_anything_vits.pth": "",
    "ltx-2.5-22b-distilled-transformer-bf16-Q4_K_M.gguf": "",
}
for _m in MODELS:
    if _m["file"] in REPO_PATH:
        _m["url"] = f"{_m['source']}/resolve/main/{REPO_PATH[_m['file']]}{_m['file']}"


def find(folder, file):
    try:
        import folder_paths
    except ImportError:
        return None
    try:
        p = folder_paths.get_full_path(folder, file)
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    p = os.path.join(folder_paths.models_dir, folder, file)
    return p if os.path.isfile(p) else None


def listing():
    out = []
    for m in MODELS:
        p = find(m["folder"], m["file"])
        out.append({**m, "present": bool(p), "covered": bool(p) or covered(m), "size_gb": round(os.path.getsize(p) / 1e9, 2) if p else m["gb"]})
    return out


def register():
    try:
        import server
        from aiohttp import web
    except ImportError:
        return
    srv = getattr(server.PromptServer, "instance", None)
    if srv is None or getattr(srv, "_efa_models", False):
        return
    srv._efa_models = True

    @srv.routes.get("/element-forge/app/models")
    async def efa_models(request):
        import asyncio
        return web.json_response({"models": await asyncio.to_thread(listing)})


def needed():
    return [m for m in MODELS if m.get("url") and m["need"] != "option"]


def widget_name(m):
    import re
    return re.sub(r"[^a-z0-9]+", "_", os.path.splitext(m["file"])[0].lower()).strip("_")[:48]


def covered(m):
    alts = [x for x in MODELS if m.get("group") and x.get("group") == m["group"]] or [m]
    return any(find(x["folder"], x["file"]) for x in alts)


MODEL_EXT = (".safetensors", ".sft", ".pth", ".pt", ".ckpt", ".gguf", ".bin")
ATTENTION = ("pytorch attention", "comfy kitchen attention")
DEPTH = ("Video Depth Anything", "DepthCrafter")
EXTRA = {
    "attention": (list(ATTENTION), {"default": ATTENTION[0], "tooltip": "comfy kitchen attention = INT8 attention: about a quarter "
                                    "faster with the INT8 LTX file on cards like the RTX 2080 Ti; not with GGUF (slower there)."}),
    "depth_model": (list(DEPTH), {"default": DEPTH[0], "tooltip": "DepthCrafter: cleaner edges, much slower, non-commercial licence; "
                                  "needs ComfyUI-DepthCrafter-Nodes."}),
}


def files_in(folder):
    try:
        import folder_paths
    except ImportError:
        return []
    try:
        return list(folder_paths.get_filename_list(folder))
    except Exception:
        d = os.path.join(folder_paths.models_dir, folder)
        return sorted(f for f in os.listdir(d) if f.lower().endswith(MODEL_EXT)) if os.path.isdir(d) else []


def choices(m):
    if m.get("group") == "ltx":
        have = [f for f in files_in("diffusion_models") + files_in("unet_gguf") + files_in("unet") if "ltx" in f.lower()]
    else:
        have = files_in(m["folder"])
    have = list(dict.fromkeys(have))
    if m["file"] not in have and covered(m):
        have.insert(0, m["file"])
    return have


def installed_ltx():
    return [f for f in dict.fromkeys(files_in("diffusion_models") + files_in("unet_gguf") + files_in("unet")) if "ltx" in f.lower()]


def run_choice(values):
    values = values if isinstance(values, dict) else {}
    ltx, swaps = {}, {}
    for m in needed():
        v = values.get(widget_name(m))
        if not isinstance(v, str) or not v or v == m["file"] and m.get("group") != "ltx":
            continue
        if m.get("group") == "ltx":
            have = installed_ltx()
            if have and v not in have:
                v = have[0]
            if v != m["file"]:
                ltx["file"] = v
        elif m.get("group") == "te":
            ltx["te"] = v
        else:
            swaps[m["file"]] = v
    if values.get("attention") in ATTENTION[1:] and not str(ltx.get("file", "")).lower().endswith(".gguf"):
        ltx["attention"] = values["attention"]
    if values.get("depth_model") == DEPTH[1]:
        ltx["depth"] = "depthcrafter"
    return ltx, swaps


def swap_files(graph, swaps):
    if not swaps:
        return graph
    for nd in graph.values():
        ins = nd.get("inputs") or {}
        for a, v in ins.items():
            if isinstance(v, str) and v in swaps:
                ins[a] = swaps[v]
    return graph


class EFAppModels:

    @classmethod
    def INPUT_TYPES(cls):
        req = {}
        for m in needed():
            need = "needed" if m["need"] == "yes" else "for some styles"
            req[widget_name(m)] = (choices(m), {"default": m["file"], "tooltip": f"{m['for']} ({need}). models/{m['folder']}/, {m['source']}"})
        req.update(EXTRA)
        return {"required": req}

    RETURN_TYPES = ("EF_MODELS",)
    RETURN_NAMES = ("models",)
    FUNCTION = "pick"
    CATEGORY = "Element Forge/App"
    DESCRIPTION = ("The models of the app: which file the run loads for each job, INT8 attention and the depth model. ComfyUI "
                   "marks the files this computer does not have and offers their download when the workflow opens.")

    def pick(self, **values):
        return (values,)

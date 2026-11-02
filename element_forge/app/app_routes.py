import asyncio
import collections
import hashlib
import io
import json
import os
import re
import threading
import time

from aiohttp import web

import folder_paths
import server

from ..tracking import analysis as AN
from ..bonsai import bonsai
from ..bonsai import bonsai_rt
from ..bonsai import setup_bonsai as SB
from .app_graph import without_unused
from . import particle_assist as PA

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.dirname(os.path.dirname(HERE))
API_WORKFLOWS = os.path.join(PACK_ROOT, "api_workflows")
VIDEO_EXT = (".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
STILL_FPS, STILL_SECONDS = 24.0, 3.0
STILL_IMAGE = "Still image (a picture in the input folder instead of the clip)"
WORK_FILE = re.compile(r"^ef_|_(mask|roi)(_v\d+)?\.[^.]+$", re.I)
MEDIA_ROOTS = {"input": folder_paths.get_input_directory, "output": folder_paths.get_output_directory,
               "temp": folder_paths.get_temp_directory}
_meta_cache = {}

routes = server.PromptServer.instance.routes


def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _inside(base, rel):
    if not rel or "\\" in rel or ":" in rel or rel.startswith("/") or "\0" in rel:
        return None
    base = os.path.realpath(base)
    try:
        p = os.path.normpath(os.path.join(base, rel))
        if os.path.commonpath([base, p]) != base:
            return None
        p = os.path.realpath(p)
        return p if os.path.commonpath([base, p]) == base else None
    except ValueError:
        return None


def _clip_path(name, stills=False):
    if not name or os.path.basename(name) != name or not name.lower().endswith(VIDEO_EXT + (IMAGE_EXT if stills else ())):
        return None
    p = _inside(folder_paths.get_input_directory(), name)
    return p if p and os.path.isfile(p) else None


def is_still(path):
    return str(path).lower().endswith(IMAGE_EXT)


def still_meta(path, seconds=STILL_SECONDS):
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        w, h = ImageOps.exif_transpose(im).size
    frames = max(1, int(round(max(0.1, float(seconds)) * STILL_FPS)))
    return {"fps": STILL_FPS, "frames": frames, "width": w, "height": h, "seconds": round(frames / STILL_FPS, 3), "codec": None,
            "still": True}


def still_video(path, seconds):
    st = os.stat(path)
    m = still_meta(path, seconds)
    tag = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}|{m['frames']}".encode()).hexdigest()[:16]
    cache = os.path.join(folder_paths.get_temp_directory(), "element-forge", "stills")
    out = os.path.join(cache, tag + ".mp4")
    if os.path.isfile(out):
        return out
    import av
    import numpy as np
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.width + im.width % 2, im.height + im.height % 2
    rgb = np.asarray(im)
    if (w, h) != im.size:
        rgb = np.pad(rgb, ((0, h - im.height), (0, w - im.width), (0, 0)), mode="edge")
    os.makedirs(cache, exist_ok=True)
    part = out + f".{os.getpid()}.part"
    with av.open(part, "w", format="mp4") as c:
        s = c.add_stream("libx264", rate=int(STILL_FPS))
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        s.options = {"crf": "16", "preset": "veryfast"}
        frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
        for _ in range(m["frames"]):
            for pkt in s.encode(frame):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    os.replace(part, out)
    return out


def clip_meta(path):
    key = (path, os.path.getmtime(path))
    if key in _meta_cache:
        return _meta_cache[key]
    import av
    with av.open(path) as c:
        s = c.streams.video[0]
        fps = float(s.average_rate or s.guessed_rate or 25)
        dur = float(s.duration * s.time_base) if s.duration else (c.duration / 1e6 if c.duration else 0.0)
        frames = s.frames or int(round(dur * fps))
        if not frames:
            frames = sum(1 for _ in c.decode(video=0))
            c.seek(0)
        w, h = s.codec_context.width, s.codec_context.height
        codec = s.codec_context.name
        if _quadrant(c) % 2:
            w, h = h, w
    m = {"fps": round(fps, 3), "frames": int(frames), "width": w, "height": h, "seconds": round(frames / fps, 3), "codec": codec}
    _meta_cache[key] = m
    return m


def clip_seconds(path):
    key = (path, os.path.getmtime(path))
    if key in _meta_cache:
        return _meta_cache[key]["seconds"]
    if ("s",) + key in _meta_cache:
        return _meta_cache[("s",) + key]
    import av
    with av.open(path) as c:
        s = c.streams.video[0]
        dur = float(s.duration * s.time_base) if s.duration else (c.duration / 1e6 if c.duration else 0.0)
    _meta_cache[("s",) + key] = round(dur, 2)
    return round(dur, 2)


def _rotation(frame):
    r = getattr(frame, "rotation", 0) or 0
    return int(round(r // 90)) % 4


def _quadrant(container):
    try:
        for f in container.decode(video=0):
            q = _rotation(f)
            break
        else:
            q = 0
        container.seek(0)
        return q
    except Exception:
        return 0


def filmstrip(path, count, height):
    if is_still(path):
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im = im.resize((max(1, round(im.width * height / im.height)), height))
        sheet = Image.new("RGB", (im.width * count, height))
        for i in range(count):
            sheet.paste(im, (i * im.width, 0))
        import io
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=82)
        return buf.getvalue()
    st = os.stat(path)
    tag = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}|{count}|{height}".encode()).hexdigest()[:16]
    cache = os.path.join(folder_paths.get_temp_directory(), "element-forge", "filmstrips")
    out = os.path.join(cache, tag + ".jpg")
    if os.path.isfile(out):
        return out
    import av
    from PIL import Image
    meta = clip_meta(path)
    want = sorted({int((i + 0.5) * meta["frames"] / count) for i in range(count)})
    tiles = []
    with av.open(path) as c:
        s = c.streams.video[0]
        s.thread_type = "AUTO"
        i = 0
        for f in c.decode(video=0):
            if want and i == want[len(tiles)]:
                im = f.to_image()
                if _rotation(f):
                    im = im.rotate(90 * _rotation(f), expand=True)
                tiles.append(im.resize((max(1, round(im.width * height / im.height)), height)))
                if len(tiles) == len(want):
                    break
            i += 1
    if not tiles:
        raise ValueError("no frames")
    while len(tiles) < len(want):
        tiles.append(tiles[-1])
    sheet = Image.new("RGB", (sum(t.width for t in tiles), height))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    os.makedirs(cache, exist_ok=True)
    sheet.save(out, quality=82)
    return out


def _unique_input_name(name):
    stem, ext = os.path.splitext(re.sub(r"[^A-Za-z0-9._ -]+", "_", os.path.basename(name)).strip() or "clip.mp4")
    if WORK_FILE.search(stem + ext):
        stem = "clip_" + stem if stem.lower().startswith("ef_") else stem + "_clip"
    base = folder_paths.get_input_directory()
    cand, n = stem + ext, 1
    while os.path.exists(os.path.join(base, cand)) or os.path.exists(os.path.join(base, cand + ".part")):
        n += 1
        cand = f"{stem}_{n}{ext}"
    return cand


@routes.get("/element-forge/api/status")
async def ef_status(request):
    import comfy.model_management as mm
    q = server.PromptServer.instance.prompt_queue
    running, pending = q.get_current_queue_volatile() if hasattr(q, "get_current_queue_volatile") else q.get_current_queue()
    dev = mm.get_torch_device()
    try:
        import psutil
        ram_total = psutil.virtual_memory().total
    except Exception:
        ram_total = None
    return web.json_response({
        "ok": True,
        "device": str(dev), "ram_total": ram_total,
        "vram_total": mm.get_total_memory(dev), "vram_free": mm.get_free_memory(dev),
        "queue_running": len(running), "queue_pending": len(pending),
        "input_dir": folder_paths.get_input_directory(), "output_dir": folder_paths.get_output_directory(),
    })


@routes.get("/element-forge/api/clips")
async def ef_clips(request):
    base = folder_paths.get_input_directory()
    out = []
    for f in sorted(os.listdir(base)):
        p = os.path.join(base, f)
        if f.lower().endswith(VIDEO_EXT + IMAGE_EXT) and not WORK_FILE.search(f) and os.path.isfile(p):
            st = os.stat(p)
            kept = {"analysis": True} if AN.analysis_info(f) else {}
            n = len(AN.tracks_of(f))
            sec = None
            if not is_still(f):
                try:
                    sec = await asyncio.to_thread(clip_seconds, p)
                except Exception:
                    sec = None
            out.append({"name": f, "bytes": st.st_size, "mtime": st.st_mtime, **({"still": True} if is_still(f) else {}), **kept,
                        **({"tracks": n} if n else {}), **({"seconds": sec} if sec else {})})
    out.sort(key=lambda c: -c["mtime"])
    return web.json_response({"clips": out})


@routes.get("/element-forge/api/clip-meta")
async def ef_clip_meta(request):
    p = _clip_path(request.query.get("name", ""), stills=True)
    if not p:
        raise web.HTTPNotFound(text="no such clip in the input folder")
    try:
        if is_still(p):
            return web.json_response(await asyncio.to_thread(still_meta, p, float(request.query.get("seconds") or STILL_SECONDS)))
        return web.json_response(await asyncio.to_thread(clip_meta, p))
    except Exception as e:
        return web.json_response({"error": f"cannot read this video: {e}"}, status=422)


@routes.get("/element-forge/api/filmstrip")
async def ef_filmstrip(request):
    p = _clip_path(request.query.get("name", ""), stills=True)
    if not p:
        raise web.HTTPNotFound()
    count = min(max(int(request.query.get("count", 12)), 1), 40)
    height = min(max(int(request.query.get("height", 56)), 16), 240)
    try:
        out = await asyncio.to_thread(filmstrip, p, count, height)
        if isinstance(out, bytes):
            return web.Response(body=out, content_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        return web.FileResponse(out, headers={"Cache-Control": "max-age=3600"})
    except Exception as e:
        return web.json_response({"error": f"cannot read this video: {e}"}, status=422)


@routes.get("/element-forge/api/still-video")
async def ef_still_video(request):
    p = _clip_path(request.query.get("name", ""), stills=True)
    if not p or not is_still(p):
        raise web.HTTPNotFound()
    try:
        return web.FileResponse(await asyncio.to_thread(still_video, p, float(request.query.get("seconds") or STILL_SECONDS)))
    except Exception as e:
        return web.json_response({"error": f"cannot read this picture: {e}"}, status=422)


@routes.post("/element-forge/api/upload")
async def ef_upload(request):
    reader = await request.multipart()
    field = await reader.next()
    while field is not None and field.name != "file":
        field = await reader.next()
    if field is None or not field.filename:
        return web.json_response({"error": "no file"}, status=400)
    if not field.filename.lower().endswith(VIDEO_EXT):
        return web.json_response({"error": "please upload a video (mp4, mov, webm, mkv)"}, status=415)
    name = _unique_input_name(field.filename)
    dst = os.path.join(folder_paths.get_input_directory(), name)
    part = dst + ".part"
    size = 0
    try:
        with open(part, "xb") as f:
            while True:
                chunk = await field.read_chunk(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                size += len(chunk)
        os.replace(part, dst)
    except Exception:
        if os.path.exists(part):
            os.remove(part)
        raise
    try:
        meta = await asyncio.to_thread(clip_meta, dst)
    except Exception as e:
        os.remove(dst)
        return web.json_response({"error": f"this file is not a readable video: {e}"}, status=422)
    return web.json_response({"name": name, "bytes": size, **meta})


FIT_SHORT = 1080


def fit_copy(name, short=FIT_SHORT):
    import av
    import numpy as np
    from PIL import Image
    src = _clip_path(name, stills=True)
    if not src:
        raise ValueError("the clip is not in ComfyUI's input folder")
    stem, ext = os.path.splitext(os.path.basename(name))
    still = ext.lower() in IMAGE_EXT
    out_name = f"{stem}_{short}p{'.png' if still else '.mp4'}"
    dst = os.path.join(folder_paths.get_input_directory(), out_name)
    if os.path.exists(dst):
        return out_name

    def size(w, h):
        k = short / min(w, h)
        return (max(2, int(round(w * k / 2)) * 2), max(2, int(round(h * k / 2)) * 2)) if k < 1 else (w, h)
    part = dst + ".part"
    try:
        if still:
            from PIL import ImageOps
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.resize(size(*im.size), Image.LANCZOS).save(part, format="PNG")
        else:
            with av.open(src) as c, av.open(part, "w", format="mp4") as o:
                s = c.streams.video[0]
                rate = s.average_rate or s.guessed_rate or 25
                v = None
                for f in c.decode(video=0):
                    im = f.to_image()
                    if _rotation(f):
                        im = im.rotate(90 * _rotation(f), expand=True)
                    w, h = size(*im.size)
                    if v is None:
                        v = o.add_stream("libx264", rate=rate)
                        v.width, v.height, v.pix_fmt = w, h, "yuv420p"
                        v.options = {"crf": "14", "preset": "medium"}
                    fr = av.VideoFrame.from_ndarray(np.asarray(im.resize((w, h), Image.LANCZOS)), format="rgb24")
                    for pkt in v.encode(fr):
                        o.mux(pkt)
                if v is not None:
                    for pkt in v.encode():
                        o.mux(pkt)
        os.replace(part, dst)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return out_name


@routes.post("/element-forge/api/clip/fit")
async def ef_clip_fit(request):
    body = await request.json()
    try:
        name = await asyncio.to_thread(fit_copy, str(body.get("clip") or ""))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        return web.json_response({"error": f"the copy could not be made: {e}"}, status=422)
    return web.json_response({"name": name})


VARIANTS = {"app": "element_forge_app.json", "climb": "element_forge_climb.json", "dissolve": "element_forge_dissolve.json",
            "check": "element_forge.json"}
MODEL_EXT = (".safetensors", ".gguf", ".pt", ".pth", ".ckpt", ".bin", ".onnx", ".sft")
RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


def _load_json(name):
    with open(os.path.join(HERE, name) if name == "app_presets.json" else os.path.join(API_WORKFLOWS, name), encoding="utf-8") as f:
        return json.load(f)


def runnable(graph):
    import nodes
    return without_unused(graph, nodes.NODE_CLASS_MAPPINGS, lambda c: getattr(nodes.NODE_CLASS_MAPPINGS[c], "OUTPUT_NODE", False) is True)


def missing_for(graph):
    import nodes
    classes = sorted({nd["class_type"] for nd in graph.values() if nd["class_type"] not in nodes.NODE_CLASS_MAPPINGS})
    models = set()
    combos = {}
    for nd in graph.values():
        cls = nodes.NODE_CLASS_MAPPINGS.get(nd["class_type"])
        for k, v in nd["inputs"].items():
            if not (cls and isinstance(v, str) and v.lower().endswith(MODEL_EXT)):
                continue
            if nd["class_type"] not in combos:
                try:
                    t = cls.INPUT_TYPES()
                    combos[nd["class_type"]] = {**t.get("required", {}), **t.get("optional", {})}
                except Exception:
                    combos[nd["class_type"]] = {}
            spec = combos[nd["class_type"]].get(k)
            options = None
            if isinstance(spec, (list, tuple)) and spec:
                extra = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                options = spec[0] if isinstance(spec[0], (list, tuple)) else extra.get("options") if spec[0] == "COMBO" else None
            if options is not None and v not in options:
                models.add(v)
    return {"nodes": classes, "models": sorted(models)}


@routes.get("/element-forge/api/presets")
async def ef_presets(request):
    presets = _load_json("app_presets.json")
    status = {}
    for v, f in VARIANTS.items():
        try:
            status[v] = missing_for(runnable(_load_json(f)))
        except FileNotFoundError:
            status[v] = {"nodes": [], "models": [], "error": f"{f} is missing in the pack"}
    presets["missing"] = status
    return web.json_response(presets)


from .compact_values import LTX_ATTENTION
CLEAN_PLATE_STRENGTH = {"int8": 1.5, "gguf": 1.0}


DEPTHCRAFTER_FILES = {"tencent_DepthCrafter": ("config.json", "diffusion_pytorch_model.safetensors"),
                      "stabilityai_stable-video-diffusion-img2vid-xt": ("model_index.json", "unet/diffusion_pytorch_model.fp16.safetensors",
                                                                         "vae/diffusion_pytorch_model.fp16.safetensors")}


def depthcrafter_half_loaded():
    base = os.path.join(folder_paths.models_dir, "depthcrafter")
    for sub, files in DEPTHCRAFTER_FILES.items():
        d = os.path.join(base, sub)
        if os.path.isdir(d) and not all(os.path.isfile(os.path.join(d, f)) for f in files):
            return d
    return ""


def use_depthcrafter(graph):
    import nodes as comfy_nodes
    if "DepthCrafter" not in comfy_nodes.NODE_CLASS_MAPPINGS:
        raise ValueError("DepthCrafter is chosen in the gear, but ComfyUI-DepthCrafter-Nodes is not installed")
    half = depthcrafter_half_loaded()
    if half:
        raise ValueError(f"DepthCrafter's download stopped half way: delete {half} and run again (it loads again, ~4.5 GB)")
    for k, nd in list(graph.items()):
        src = nd["inputs"].get("image")
        if nd["class_type"] != "ImageScale" or not isinstance(src, list) or graph.get(src[0], {}).get("class_type") != "VideoDepthAnythingOutput":
            continue
        process = graph[graph[src[0]]["inputs"]["depths"][0]]
        frames = process["inputs"]["images"]
        graph["dc_load"] = {"class_type": "DownloadAndLoadDepthCrafterModel", "_meta": {"title": "DepthCrafter model"},
                            "inputs": {"enable_model_cpu_offload": True, "enable_sequential_cpu_offload": False}}
        graph["dc_size"] = {"class_type": "GetImageSize", "inputs": {"image": frames}}
        graph["dc_factor"] = {"class_type": "ComfyMathExpression", "inputs": {"expression": "576 / min(a, b)",
                              "values.a": ["dc_size", 0], "values.b": ["dc_size", 1]}}
        graph["dc_in"] = {"class_type": "ImageScaleBy", "inputs": {"image": frames, "upscale_method": "area", "scale_by": ["dc_factor", 0]}}
        graph["dc"] = {"class_type": "DepthCrafter", "_meta": {"title": "Depth (DepthCrafter)"},
                       "inputs": {"depthcrafter_model": ["dc_load", 0], "images": ["dc_in", 0], "force_size": True,
                                  "num_inference_steps": 5, "guidance_scale": 1.0, "window_size": 110, "overlap": 25}}
        nd["inputs"]["image"] = ["dc", 0]
    return graph


def use_ltx(graph, ltx):
    f, att = (ltx or {}).get("file") or "", (ltx or {}).get("attention") or ""
    te = (ltx or {}).get("te") or ""
    if (ltx or {}).get("depth") == "depthcrafter":
        use_depthcrafter(graph)
    if te:
        if te not in folder_paths.get_filename_list("text_encoders"):
            raise ValueError(f"the text encoder {te} is not in models/text_encoders")
        for nd in graph.values():
            if nd["class_type"] == "CLIPLoader" and "gemma4-12b" in str(nd["inputs"].get("clip_name", "")):
                nd["inputs"]["clip_name"] = te
    if f:
        gguf = f.lower().endswith(".gguf")
        known = folder_paths.get_filename_list("unet_gguf") if gguf and "unet_gguf" in folder_paths.folder_names_and_paths \
            else folder_paths.get_filename_list("diffusion_models")
        if f not in known:
            raise ValueError(f"the LTX file {f} is not in models/diffusion_models")
        for nd in graph.values():
            if nd["class_type"] in ("UNETLoader", "UnetLoaderGGUF") and "ltx" in str(nd["inputs"].get("unet_name", "")).lower():
                nd["class_type"], nd["inputs"] = ("UnetLoaderGGUF", {"unet_name": f}) if gguf \
                    else ("UNETLoader", {"unet_name": f, "weight_dtype": "default"})
        for nd in graph.values():
            if nd["class_type"] == "LTXICLoRALoaderModelOnly" and "clean-plate" in str(nd["inputs"].get("lora_name", "")):
                nd["inputs"]["strength_model"] = CLEAN_PLATE_STRENGTH["gguf" if gguf else "int8"]
    if att and att != LTX_ATTENTION[0]:
        if att not in LTX_ATTENTION:
            raise ValueError(f"unknown attention backend {att}")
        for src in [k for k, nd in graph.items() if nd["class_type"] == "ModelComputeDtype"]:
            new = f"{src}_att"
            for nd in graph.values():
                for a, v in nd["inputs"].items():
                    if v == [src, 0]:
                        nd["inputs"][a] = [new, 0]
            graph[new] = {"class_type": "ModelAttentionBackend", "inputs": {"model": [src, 0], "attention": att}}
    return graph


STAGES = {"pass1": {"plain": ("273", 0, "274"), "guided": ("281", 2, "282")},
          "final": {"plain": ("290", 0, "291"), "guided": ("298", 2, "299")}}
UPSAMPLERS = {"plain": "284", "guided": "285"}
UPSCALE = "LTX upscale x2 (latent upscaler + second pass, test)"
PASS_SAVES = {"plate": "489", "element": "490", "light": "491", "glow": "492", "depth": "493", "normals": "494",
              "mask": "852",
              "particles": "495"}
ALSO_DRAW = "Particles: also draw (over the AI element)"
DIRECT_LOOK = "Particles: direct look (no LTX, pro)"
VIDEO_SAVES = ("475", "222")
PREVIEW_SKIPS = ("light", "glow", "normals")
PASS_SWITCH = {"light": "Light", "glow": "Glow"}
PASS_SWITCH_NODES = {"light": "142", "glow": "143"}
INPAINT_SWITCH = "103"
INPAINT_NO_LIGHT_SKIPS = ("light", "normals")
DISSOLVE_LIGHT_SAVES = {"light": "705", "normals": "706"}
MODES = ("full", "preview", "final", "add")


def _stage_of(graph):
    return "final" if graph.get("140", {}).get("inputs", {}).get("value") is True else "pass1"


def keep_latents(graph, run, stage):
    for path, (src, idx, dec) in STAGES[stage].items():
        if graph.get(src, {}).get("class_type") in ("LTXVSeparateAVLatent", "LTXVCropGuides") and graph.get(dec, {}).get("class_type") == "VAEDecodeTiled":
            graph[f"{dec}_keep"] = {"class_type": "EFRunLatent", "inputs": {"samples": [src, idx], "run_folder": f"element-forge/{run}", "name": f"{stage}_{path}"}}
            graph[dec]["inputs"]["samples"] = [f"{dec}_keep", 0]


def load_latents(graph, from_run, stage, into):
    for path, (src, idx, dec) in STAGES[stage].items():
        target = dec if into == "decode" else UPSAMPLERS[path]
        if target in graph:
            graph[f"{target}_load"] = {"class_type": "EFLoadRunLatent", "inputs": {"run_folder": f"element-forge/{from_run}", "name": f"{stage}_{path}"}}
            graph[target]["inputs"]["samples"] = [f"{target}_load", 0]


def upscaled_size(graph):
    nd = graph.get("127")
    if nd and nd["class_type"] == "PrimitiveFloat" and isinstance(nd["inputs"].get("value"), (int, float)):
        nd["inputs"]["value"] = nd["inputs"]["value"] / 2


def kept_latents(folder, stage):
    return [p for p in STAGES[stage] if os.path.isfile(os.path.join(folder, f"latent_{stage}_{p}.safetensors"))]


def pass_files(folder):
    return {name for name in PASS_SAVES if any(f.startswith(name + "_") and f.lower().endswith(".exr") for f in os.listdir(folder))}


def renamed_settings(values, settings):
    base = lambda k: k.split(" (", 1)[0]
    out = {}
    for k, v in values.items():
        if k not in settings:
            same = [s for s in settings if base(s) == base(k)]
            k = same[0] if len(same) == 1 else k
        out[k] = v
    return out


GUIDE = "Guide for the AI (particles / drawn path / object shape / none)"


def old_guide(values):
    if "Guide" not in values and "Particles: guide" not in values:
        return values
    out = {k: v for k, v in values.items() if k not in ("Guide", "Particles: guide")}
    if GUIDE not in out:
        if out.get("Particles"):
            if values.get("Particles: guide") is False:
                out[GUIDE] = "none"
        elif values.get("Guide"):
            out[GUIDE] = "drawn path"
    return out


def build_graph(variant, values, run, ltx=None, edit=None, kept=True):
    graph = use_ltx(_load_json(VARIANTS[variant]), ltx)
    settings = _load_json("element_forge.settings.json")["settings"]
    values = renamed_settings(old_guide(values), settings)
    unknown = [k for k in values if k not in settings]
    if unknown:
        raise ValueError(f"unknown settings: {', '.join(unknown)}")
    for name, value in values.items():
        targets = settings[name] if isinstance(settings[name][0], list) else [settings[name]]
        for nid, field in targets:
            if nid in graph:
                graph[nid]["inputs"][field] = value
    for nd in graph.values():
        for k, v in nd["inputs"].items():
            if isinstance(v, str) and "{run}" in v:
                nd["inputs"][k] = v.replace("{run}", run)
    if values.get(STILL_IMAGE):
        without_clip(graph, settings["Clip"][0])
    if kept:
        use_kept(graph, settings)
    if edit:
        edit(graph)
    return runnable(graph)


KEPT_DEPTH, KEPT_NORMALS, KEPT_MASK, KEPT_MASK_B = "176", "409", "197", "204"
KEPT_CLEAN, LEFT_PARTS = "904", "903"
KEPT_WHOLE, MASK_AT = "926", "925"
MASK_STEADY = "929"
MASK_FIXES = "962"
KEPT_CLASSES = {KEPT_DEPTH: "EFDeflicker", KEPT_NORMALS: "EFMoGeNormals", KEPT_MASK: "ComfySwitchNode", KEPT_MASK_B: "SAM3_TrackToMask"}
WHERE = {"a": ("Point A x", "Point A y"), "b": ("Point B x", "Point B y"), "word": "Object word (optional, helps the click)",
         "alike": "Object word: all alike objects (e.g. all sticks of a crown; off = the clicked one)",
         "own": "Own object mask (off = click)", "own_mask": "Own object mask: first frame, paint the object (mask editor)",
         "leave": "Leave out: points (x, y; Alt-click in the app)", "leave_words": "Leave out: words (e.g. hand; handle)",
         "frame": "Mask frame (the frame the mask is set on; 0 = the first)", "add": "Mask: add points (x, y; Ctrl-click in the app)",
         "add_words": "Mask: add words (e.g. blade; tip)",
         "fixes": "Mask fixes (JSON: frame, add, leave; Ctrl/Alt-click on another frame in the app)"}


def mask_at_frame(values):
    return bool(int(values.get(WHERE["frame"]) or 0) > 0 or str(values.get(WHERE["add"]) or "").strip()
                or str(values.get(WHERE["add_words"]) or "").strip(" ;\n"))


def _value(graph, settings, name):
    t = settings[name] if not isinstance(settings[name][0], list) else settings[name][0]
    nd = graph.get(t[0])
    return None if nd is None else nd["inputs"].get(t[1])


def where_of(graph, settings):
    v = lambda n: _value(graph, settings, n)
    clip = v(STILL_IMAGE) or v("Clip")
    if not clip or any(isinstance(v(n), list) for n in ("Frames", *WHERE["a"], *WHERE["b"])):
        return None
    b = [v(WHERE["b"][0]), v(WHERE["b"][1])]
    w = {"clip": clip, "frames": v("Frames"), "a": [v(WHERE["a"][0]), v(WHERE["a"][1])], "b": b if b[0] is not None and b[0] >= 0 else [],
         "word": v(WHERE["word"]) or "", "alike": bool(v(WHERE["alike"])), "own": bool(v(WHERE["own"])), "own_mask": v(WHERE["own_mask"]) or ""}
    if any(WHERE[k] in settings and isinstance(v(WHERE[k]), list) for k in ("leave", "leave_words", "frame", "add", "add_words", "fixes")):
        return None
    for k in ("leave", "leave_words", "add", "add_words"):
        if WHERE[k] in settings and str(v(WHERE[k]) or "").strip():
            w[k] = str(v(WHERE[k])).strip()
    if WHERE["frame"] in settings and int(v(WHERE["frame"]) or 0) > 0:
        w["frame"] = int(v(WHERE["frame"]))
    if WHERE["fixes"] in settings and str(v(WHERE["fixes"]) or "").strip() not in ("", "[]"):
        w["fixes"] = str(v(WHERE["fixes"])).strip()
    return w


def _rewire(graph, old, new):
    for nd in graph.values():
        for k, val in (nd.get("inputs") or {}).items():
            if val == old:
                nd["inputs"][k] = list(new)


def depth_model(graph):
    return AN.DEPTH_DC if graph.get("dc", {}).get("class_type") == "DepthCrafter" else AN.DEPTH_VDA


def use_kept(graph, settings):
    if any(graph.get(k, {}).get("class_type") not in (c, "EFLoadAnalysis", "EFLoadTrack") for k, c in KEPT_CLASSES.items()):
        return graph
    w = where_of(graph, settings)
    if not w:
        return graph
    info = AN.analysis_info(w["clip"], w["frames"])
    for nid, part in ((KEPT_DEPTH, "depth"), (KEPT_NORMALS, "normals")):
        if part == "depth" and AN.depth_model_of(info) != depth_model(graph):
            continue
        if part == "normals" and info and "scene" not in info:
            continue
        if info and part in info.get("parts", []) and part in info.get("range", {}):
            graph[nid] = {"class_type": "EFLoadAnalysis", "inputs": {"clip": w["clip"], "part": part, "frames": w["frames"]},
                          "_meta": {"title": f"Kept {part} of the clip"}}
    tr = AN.track_info(w)
    if tr:
        s = json.dumps(w)
        graph[KEPT_MASK] = {"class_type": "EFLoadTrack", "inputs": {"where": s, "which": "a"}, "_meta": {"title": "Kept object mask"}}
        _rewire(graph, [KEPT_WHOLE, 0], [KEPT_MASK, 0])
        if tr.get("b") and w["b"]:
            graph[KEPT_MASK_B] = {"class_type": "EFLoadTrack", "inputs": {"where": s, "which": "b"}, "_meta": {"title": "Kept object mask B"}}
        if graph.get(KEPT_CLEAN, {}).get("class_type") == "EFLeaveOutTrack":
            if tr.get("left") and AN.leave_of(w):
                graph["kept_left"] = {"class_type": "EFLoadTrack", "inputs": {"where": s, "which": "left"},
                                      "_meta": {"title": "Kept parts left out"}}
                graph[KEPT_CLEAN] = {"class_type": "MaskComposite", "inputs": {"destination": [KEPT_MASK, 0], "source": ["kept_left", 0],
                                     "x": 0, "y": 0, "operation": "subtract"}, "_meta": {"title": "Kept object mask without the parts left out"}}
            elif not AN.leave_of(w):
                _rewire(graph, [KEPT_CLEAN, 0], [KEPT_MASK, 0])
        fix = graph.get(MASK_FIXES)
        if fix and fix.get("class_type") == "EFMaskFixes":
            _rewire(graph, [MASK_FIXES, 0], fix["inputs"]["whole"])
            _rewire(graph, [MASK_FIXES, 1], fix["inputs"]["clean"])
    return graph


def keep_track(graph, settings):
    w = where_of(graph, settings)
    if not w or graph.get(KEPT_MASK, {}).get("class_type") != "ComfySwitchNode":
        return graph
    left = AN.leave_of(w) and graph.get(KEPT_CLEAN, {}).get("class_type") == "EFLeaveOutTrack"
    whole = [MASK_FIXES, 0] if w.get("fixes") and graph.get(MASK_FIXES, {}).get("class_type") == "EFMaskFixes"         else [KEPT_WHOLE if KEPT_WHOLE in graph else KEPT_MASK, 0]
    graph["track_keep"] = {"class_type": "EFSaveTrack", "inputs": {"mask": whole, "where": json.dumps(w),
                                                                    **({"mask_b": [KEPT_MASK_B, 0]} if w["b"] else {}),
                                                                    **({"left_out": [KEPT_CLEAN, 1]} if left else {})},
                           "_meta": {"title": "Keep the track"}}
    return graph


MODEL_EXT = (".safetensors", ".gguf", ".pth", ".pt", ".ckpt", ".bin", ".sft")


def model_files(graph):
    return sorted({v for nd in graph.values() if isinstance(nd, dict) and nd.get("class_type") != "EFAppModels"
                   for v in (nd.get("inputs") or {}).values() if isinstance(v, str) and v.lower().endswith(MODEL_EXT)})


def upstream(graph, roots):
    keep, todo = set(), list(roots)
    while todo:
        k = todo.pop()
        if k in keep or k not in graph:
            continue
        keep.add(k)
        todo += [v[0] for v in graph[k]["inputs"].values() if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)]
    return {k: graph[k] for k in graph if k in keep}


def analysis_graph(values, ltx=None):
    clip_values = {k: values[k] for k in ("Clip", STILL_IMAGE, "Still image length (s)", "Frames") if k in values}
    clip = clip_values.get(STILL_IMAGE) or clip_values.get("Clip")

    def edit(g):
        g["analysis_keep"] = {"class_type": "EFSaveAnalysis", "inputs": {
            "clip": clip or g["101"]["inputs"]["file"], "plate": ["167", 0], "fps": ["167", 2], "depth": [KEPT_DEPTH, 0],
            "normals": [KEPT_NORMALS, 0], "depth_range": [KEPT_NORMALS, 1], "fov": [KEPT_NORMALS, 2], "depth_model": depth_model(g),
            "depth_edge": int(g.get(KEPT_DEPTH, {}).get("inputs", {}).get("edge_radius", AN.DEPTH_EDGE))},
            "_meta": {"title": "Keep the scene analysis"}}
    graph = upstream(build_graph("check", clip_values, "analysis", ltx=ltx, edit=edit, kept=False), ["analysis_keep"])
    return graph, graph["analysis_keep"]["inputs"]["clip"]


def export_graph(values, export, ltx=None):
    want = {str(p) for p in export.get("passes") or []} & {"plate", "depth", "normals", "mask"}
    common = export.get("common") or {}
    blur = float((common.get("dof") or {}).get("amount", 0) or 0) > 0
    if "mask" in want and not (isinstance(values.get(WHERE["a"][0]), (int, float)) and values[WHERE["a"][0]] >= 0):
        raise ValueError("the object's mask needs a point: click the object in Position first")
    b = isinstance(values.get(WHERE["b"][0]), (int, float)) and values[WHERE["b"][0]] >= 0

    def edit(g):
        inp = {"layers": "[]", "common": json.dumps(common), "out_folder": str(export["out"]), "write_exr": bool(export.get("exr")),
               "fps": ["167", 2], "chunk": 8, "comp_name": str(export.get("name") or "Element Forge shot"),
               "format": str(export.get("format") or "mp4"), "frame_start": int(export.get("frame_start") or 0),
               "frame_end": int(export.get("frame_end", -1)), "hdr": bool(export.get("hdr")), "passes": ",".join(sorted(want)),
               "upscale": "plate" if export.get("upscale") in ("plate", "comp") else "off", "hdr_on": "comp", "plate": ["167", 0]}
        if "depth" in want or blur:
            inp["depth"] = [KEPT_DEPTH, 0]
        if "normals" in want:
            inp["normals"] = [KEPT_NORMALS, 0]
        if "mask" in want:
            inp["mask"] = [next(k for k in (MASK_STEADY, KEPT_CLEAN, KEPT_MASK) if k in g), 0]
            if b:
                inp["mask_b"] = [KEPT_MASK_B, 0]
        g["clip_export"] = {"class_type": "EFFinishStack", "inputs": inp, "_meta": {"title": "Export the clip"}}
    return upstream(build_graph("check", values, "export", ltx=ltx, edit=edit), ["clip_export"])


def without_clip(graph, clip_id):
    for nd in graph.values():
        for k, v in list(nd["inputs"].items()):
            if isinstance(v, list) and len(v) == 2 and str(v[0]) == str(clip_id):
                del nd["inputs"][k]
    graph.pop(str(clip_id), None)
    return graph


ELEMENT_SAVE = "861"


def app_job(body, out_dir):
    variant, values, run, edit, recipe, extra = _app_job(body, out_dir)
    v = values
    save = (bool(body.get("save_element")) and variant == "app" and (body.get("mode") or "full") == "full"
            and not v.get("Inpaint (off = on black)") and not v.get("Element from library")
            and not v.get(DIRECT_LOOK))
    drawn = variant == "app" and bool(v.get("Particles")) and bool(v.get(ALSO_DRAW)) and not v.get(DIRECT_LOOK)

    def edit_save(g):
        edit(g)
        if not save:
            g.pop(ELEMENT_SAVE, None)
        if not drawn:
            g.pop(PASS_SAVES["particles"], None)
    return (variant, values, run, edit_save, (lambda: {**recipe(), "element_saved": run}) if save else recipe, extra)


def _app_job(body, out_dir):
    variant, run, mode = body.get("variant", "app"), body.get("run", ""), body.get("mode") or "full"
    values = dict(body.get("values") or {})
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    if mode == "full":
        found = {}

        def edit(g):
            found["stage"] = _stage_of(g)
            if variant == "app":
                keep_latents(g, run, found["stage"])
                if found["stage"] == "final":
                    upscaled_size(g)
                if g.get(PASS_SWITCH_NODES["light"], {}).get("inputs", {}).get("value") is False:
                    for name in INPAINT_NO_LIGHT_SKIPS:
                        g.pop(PASS_SAVES[name], None)
                    found["skipped"] = list(INPAINT_NO_LIGHT_SKIPS)
            if variant == "dissolve" and g.get(PASS_SWITCH_NODES["light"], {}).get("inputs", {}).get("value") is False:
                for nid in DISSOLVE_LIGHT_SAVES.values():
                    g.pop(nid, None)
                found["skipped"] = list(DISSOLVE_LIGHT_SAVES)
        return (variant, values, run, edit,
                lambda: {"mode": "full", "stage": found.get("stage"), "values": values, **({"skipped": found["skipped"]} if "skipped" in found else {})}, {})
    if variant != "app":
        raise ValueError(f"{mode} works with the app workflow only")

    def inpaint(v):
        return v.get("Inpaint (off = on black)", _load_json(VARIANTS["app"])["103"]["inputs"]["value"])
    if mode == "preview":
        intended = values
        values = {**values, UPSCALE: False, "Light": False, "Glow": False}
        if inpaint(values):
            raise ValueError("Preview and final are not ready for inpaint styles yet")

        def edit(g):
            for name in PREVIEW_SKIPS:
                g.pop(PASS_SAVES[name], None)
            keep_latents(g, run, "pass1")
        return (variant, values, run, edit, lambda: {"mode": "preview", "stage": "pass1", "values": intended, "effective": values},
                {"stage": "pass1"})
    src = body.get("from_run", "")
    if not RUN_NAME.match(src):
        raise ValueError("from_run: the run to go on from is missing")
    src_dir = _inside(out_dir, f"element-forge/{src}")
    try:
        with open(os.path.join(src_dir, "app_recipe.json"), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, TypeError, ValueError):
        raise ValueError(f"run {src} has no recipe (app_recipe.json)") from None
    stage = rec.get("stage")
    if rec.get("variant") != "app" or not stage:
        raise ValueError(f"run {src} was made before runs kept their latent; make it again")
    if mode == "final":
        if stage != "pass1" or rec.get("mode") != "preview":
            raise ValueError(f"run {src} is not a preview")
        if not kept_latents(src_dir, "pass1"):
            raise ValueError(f"run {src} has no kept latent")
        intended = {**rec["values"], **{k: values[k] for k in ("Light", "Glow") if k in values}}
        values = {**intended, UPSCALE: True}
        if inpaint(values):
            raise ValueError("Preview and final are not ready for inpaint styles yet")

        def edit(g):
            load_latents(g, src, "pass1", "upsample")
            keep_latents(g, run, "final")
            upscaled_size(g)
        return (variant, values, run, edit, lambda: {"mode": "final", "stage": "final", "from": src, "values": intended, "effective": values},
                {"stage": "final"})
    passes = [p for p in body.get("passes") or [] if p in PASS_SAVES and p != "particles"]
    if not passes:
        raise ValueError("add: name the passes to add (light, glow, depth, normals, mask)")
    have = pass_files(src_dir)
    if any(p in have for p in passes):
        raise ValueError(f"run {src} has {', '.join(p for p in passes if p in have)} already")
    if not kept_latents(src_dir, stage):
        raise ValueError(f"run {src} has no kept latent")
    values = {**(rec.get("effective") or rec["values"]), UPSCALE: stage == "final"}
    for p, name in PASS_SWITCH.items():
        if p in passes:
            values[name] = True

    def edit(g):
        for name, nid in PASS_SAVES.items():
            if name not in passes:
                g.pop(nid, None)
        for nid in VIDEO_SAVES:
            g.pop(nid, None)
        load_latents(g, src, stage, "decode")
        if stage == "final":
            upscaled_size(g)

    def recipe():
        rec.setdefault("added", []).append({"passes": passes, "time": time.time()})
        return rec
    return variant, values, src, edit, recipe, {"stage": stage, "passes": passes}


@routes.post("/element-forge/api/build")
async def ef_build(request):
    body = await request.json()
    variant, run = body.get("variant", "app"), body.get("run", "")
    if variant not in VARIANTS:
        return web.json_response({"error": f"unknown variant {variant}"}, status=400)
    if body.get("mode") == "add":
        run = body.get("from_run", "")
    if not RUN_NAME.match(run):
        return web.json_response({"error": "run names use letters, digits, . _ - only"}, status=400)
    clip = (body.get("values") or {}).get("Clip")
    still = (body.get("values") or {}).get(STILL_IMAGE)
    if still and not _clip_path(still, stills=True):
        return web.json_response({"error": f"the picture {still} is not in ComfyUI's input folder"}, status=400)
    if clip is not None and not still and not _clip_path(clip):
        return web.json_response({"error": f"the clip {clip} is not in ComfyUI's input folder"}, status=400)
    out_dir = folder_paths.get_output_directory()
    try:
        variant, values, run, edit, recipe, extra = app_job(body, out_dir)
        if variant == "check" and values.get("Check track only"):
            settings = _load_json("element_forge.settings.json")["settings"]

            def check_edit(g, e=edit):
                if e:
                    e(g)
                keep_track(g, settings)
                g.pop(VIDEO_SAVES[0], None)
            edit = check_edit
            extra = {**extra, "show": VIDEO_SAVES[1]}
        graph = build_graph(variant, values, run, body.get("ltx"), edit)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    if variant != "check" and not body.get("dry"):
        folder = _inside(out_dir, f"element-forge/{run}")
        os.makedirs(folder, exist_ok=True)
        rec = recipe()
        if body.get("mode") != "add":
            rec = {"variant": variant, **rec, "recipe": body.get("recipe"), "time": time.time()}
        with open(os.path.join(folder, "app_recipe.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, indent=1)
    return web.json_response({"prompt": graph, "run": run, "folder": f"element-forge/{run}", **extra})


@routes.get("/element-forge/api/analysis")
async def ef_analysis(request):
    clip = request.query.get("clip", "")
    if not _clip_path(clip, stills=True):
        raise web.HTTPNotFound(text="no such clip in the input folder")
    frames = request.query.get("frames")
    info = await asyncio.to_thread(AN.analysis_info, clip, int(frames) if frames else None)
    out = {"clip": clip, "analysis": None, "tracks": await asyncio.to_thread(AN.tracks_of, clip)}
    if info:
        rel = os.path.relpath(AN.clip_folder(clip), folder_paths.get_output_directory()).replace("\\", "/")
        out["analysis"] = {**info, "previews": {p: f"/element-forge/media/output/{rel}/{p}.mp4" for p in ("depth", "normals")
                                                if p in info.get("parts", [])}}
    return _no_cache(web.json_response(out))


@routes.post("/element-forge/api/analysis/build")
async def ef_analysis_build(request):
    body = await request.json()
    values = dict(body.get("values") or {})
    still, clip = values.get(STILL_IMAGE), values.get("Clip")
    if still and not _clip_path(still, stills=True) or not still and (not clip or not _clip_path(clip)):
        return web.json_response({"error": "the clip is not in ComfyUI's input folder"}, status=400)
    try:
        graph, name = analysis_graph(values, body.get("ltx"))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"prompt": graph, "clip": name})


@routes.post("/element-forge/api/export/build")
async def ef_export_build(request):
    body = await request.json()
    values = dict(body.get("values") or {})
    export = dict(body.get("export") or {})
    still, clip = values.get(STILL_IMAGE), values.get("Clip")
    if still and not _clip_path(still, stills=True) or not still and (not clip or not _clip_path(clip)):
        return web.json_response({"error": "the clip is not in ComfyUI's input folder"}, status=400)
    if not str(export.get("out") or "").startswith("element-forge/") or ".." in str(export.get("out")):
        return web.json_response({"error": "bad export folder"}, status=400)
    try:
        graph = export_graph(values, export, body.get("ltx"))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"prompt": graph})


FIRST_MASK, FIRST_MASK_B = "187", "202"


def first_mask_graph(values):
    left = any(str(values.get(WHERE[k]) or "").strip() for k in ("leave", "leave_words"))
    at = mask_at_frame(values)

    def edit(g):
        if at and MASK_AT in g:
            g[MASK_AT]["inputs"]["track_video"] = False
            g["first_a_clean"] = {"class_type": "MaskComposite", "inputs": {"destination": [MASK_AT, 0], "source": [MASK_AT, 1],
                                                                            "x": 0, "y": 0, "operation": "subtract"}}
            for tag, src in (("a", ["first_a_clean", 0]), ("left", [MASK_AT, 1])):
                g[f"first_{tag}_img"] = {"class_type": "MaskToImage", "inputs": {"mask": src}}
                g[f"first_{tag}"] = {"class_type": "PreviewImage", "inputs": {"images": [f"first_{tag}_img", 0]},
                                     "_meta": {"title": f"Mask frame: {'the object' if tag == 'a' else 'parts left out'}"}}
        for nid, tag in ((FIRST_MASK, "a"), (FIRST_MASK_B, "b")):
            if tag == "a" and at and MASK_AT in g:
                continue
            if tag == "b" and not (isinstance(g.get("108", {}).get("inputs", {}).get("b_x"), int) and g["108"]["inputs"]["b_x"] >= 0):
                continue
            src = [nid, 0]
            if tag == "a" and left:
                g["first_a_clean"] = {"class_type": "MaskComposite", "inputs": {"destination": src, "source": [LEFT_PARTS, 0],
                                                                                "x": 0, "y": 0, "operation": "subtract"}}
                src = ["first_a_clean", 0]
                g["first_left_img"] = {"class_type": "MaskToImage", "inputs": {"mask": [LEFT_PARTS, 0]}}
                g["first_left"] = {"class_type": "PreviewImage", "inputs": {"images": ["first_left_img", 0]},
                                   "_meta": {"title": "First frame: parts left out"}}
            g[f"first_{tag}_img"] = {"class_type": "MaskToImage", "inputs": {"mask": src}}
            g[f"first_{tag}"] = {"class_type": "PreviewImage", "inputs": {"images": [f"first_{tag}_img", 0]},
                                 "_meta": {"title": f"First frame mask {tag.upper()}"}}
    g = build_graph("check", values, "first-mask", edit=edit, kept=False)
    return upstream(g, [k for k in g if k in ("first_a", "first_b", "first_left")])


@routes.post("/element-forge/api/first-mask/build")
async def ef_first_mask(request):
    body = await request.json()
    try:
        return web.json_response({"prompt": first_mask_graph(dict(body.get("values") or {}))})
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)


@routes.post("/element-forge/api/tracks/clear")
async def ef_tracks_clear(request):
    body = await request.json()
    clip = body.get("clip", "")
    if not _clip_path(clip, stills=True):
        return web.json_response({"error": "no such clip"}, status=404)
    try:
        gone = await asyncio.to_thread(AN.clear_track, clip, body.get("key", ""))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    return web.json_response({"cleared": gone, "tracks": await asyncio.to_thread(AN.tracks_of, clip)})


@routes.post("/element-forge/api/tracks/key")
async def ef_track_key(request):
    body = await request.json()
    try:
        graph = build_graph("check", dict(body.get("values") or {}), "key", kept=False)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    w = where_of(graph, _load_json("element_forge.settings.json")["settings"])
    info = AN.track_info(w) if w else None
    return web.json_response({"key": AN.track_key(w) if w else None, "kept": bool(info)})


@routes.get("/element-forge/api/run-files")
async def ef_run_files(request):
    run = request.query.get("run", "")
    if not RUN_NAME.match(run):
        return web.json_response({"error": "bad run name"}, status=400)
    d = _inside(folder_paths.get_output_directory(), f"element-forge/{run}")
    if not d or not os.path.isdir(d):
        return web.json_response({"error": "no such run"}, status=404)
    out = {"folder": d}
    for name in ("plate", "element", "light", "glow", "depth", "normals"):
        fs = sorted(f for f in os.listdir(d) if f.startswith(name + "_") and f.lower().endswith(".exr"))
        if fs:
            out[name] = os.path.join(d, fs[0])
    return web.json_response(out)


def first_frame(path, seconds=0.0):
    if is_still(path):
        from PIL import Image, ImageOps
        with Image.open(path) as im:
            return ImageOps.exif_transpose(im).convert("RGB")
    import av
    im = None
    with av.open(path) as c:
        for f in c.decode(video=0):
            im = f.to_image().rotate(90 * _rotation(f), expand=True) if _rotation(f) else f.to_image()
            if f.time is None or f.time + 1e-3 >= seconds:
                return im
    if im is None:
        raise ValueError("no frames")
    return im


def crop_box(im, box):
    try:
        x, y, w, h = (float(v) for v in box)
    except (TypeError, ValueError):
        return im
    x0, y0 = max(0, int(round(x))), max(0, int(round(y)))
    x1, y1 = min(im.width, int(round(x + w))), min(im.height, int(round(y + h)))
    return im.crop((x0, y0, x1, y1)) if x1 - x0 >= 16 and y1 - y0 >= 16 else im


@routes.get("/element-forge/api/bonsai")
async def ef_bonsai_status(request):
    return web.json_response(await asyncio.to_thread(bonsai.status))


@routes.post("/element-forge/api/bonsai")
async def ef_bonsai(request):
    body = await request.json()
    image = None
    if body.get("clip"):
        p = _clip_path(body["clip"], stills=True)
        if not p:
            return web.json_response({"error": "no such clip in the input folder"}, status=404)
        image = await asyncio.to_thread(first_frame, p, max(0.0, float(body.get("time") or 0)))
        if body.get("box"):
            image = crop_box(image, body["box"])
    try:
        text, secs, tps = await asyncio.to_thread(bonsai.chat, str(body.get("text", "")), str(body.get("system", "")), image,
                                                  body.get("schema"), int(body.get("max_tokens", 400)),
                                                  float(body.get("temperature", 0.7)), bool(body.get("keep", True)))
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=503)
    return web.json_response({"text": text, "seconds": secs, "tokens_per_second": tps})


REF_SHEETS = collections.OrderedDict()


def _picture(data_url):
    import base64
    from PIL import Image, ImageOps
    head, _, b64 = str(data_url).partition(",")
    if not head.startswith("data:image/") or not b64:
        raise ValueError("a reference must be a picture (PNG, JPEG or WebP)")
    raw = base64.b64decode(b64)
    if len(raw) > 12 * 1024 * 1024:
        raise ValueError("a reference picture is larger than 12 MB")
    with Image.open(io.BytesIO(raw)) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def reference_sheet(refs, frame, a=None, box=None, side=1024):
    from PIL import Image, ImageDraw
    H = side * 9 // 16
    lw, rw = side * 2 // 5, side - side * 2 // 5
    sheet = Image.new("RGB", (side, H), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    refs = list(refs)[:3]
    k = max(1, len(refs))
    for i, im in enumerate(refs):
        cell_h = (H - 24) // k
        t = im.copy()
        t.thumbnail((lw - 16, cell_h - 8))
        sheet.paste(t, (8 + (lw - 16 - t.width) // 2, 24 + i * cell_h + (cell_h - t.height) // 2))
    d.text((8, 6), "REFERENCE: the look to make", fill=(255, 255, 255))
    if frame is not None:
        f = frame.copy()
        f.thumbnail((rw - 16, H - 32))
        s = f.width / frame.width
        x0, y0 = lw + 8 + (rw - 16 - f.width) // 2, 24 + (H - 32 - f.height) // 2
        sheet.paste(f, (x0, y0))
        if box:
            bx, by, bw, bh = (float(v) for v in box)
            d.rectangle([x0 + bx * s, y0 + by * s, x0 + (bx + bw) * s, y0 + (by + bh) * s], outline=(255, 210, 60), width=2)
        if a:
            ax, ay = x0 + float(a[0]) * s, y0 + float(a[1]) * s
            for r, col, w in ((15, (0, 0, 0), 6), (14, (255, 210, 60), 3)):
                d.ellipse([ax - r, ay - r, ax + r, ay + r], outline=col, width=w)
        d.text((lw + 8, 6), "YOUR CLIP: the effect goes at the yellow mark", fill=(255, 210, 60))
    d.line([(lw, 0), (lw, H)], fill=(90, 90, 90), width=2)
    return sheet


@routes.post("/element-forge/api/bonsai/reference")
async def ef_bonsai_reference(request):
    body = await request.json()
    try:
        refs = [_picture(u) for u in (body.get("images") or [])[:3]]
    except (ValueError, OSError) as e:
        return web.json_response({"error": str(e)}, status=400)
    if not refs:
        return web.json_response({"error": "add a picture of the effect first"}, status=400)
    frame = None
    if body.get("clip"):
        p = _clip_path(body["clip"], stills=True)
        if not p:
            return web.json_response({"error": "no such clip in the input folder"}, status=404)
        frame = await asyncio.to_thread(first_frame, p, max(0.0, float(body.get("time") or 0)))
    sheet = await asyncio.to_thread(reference_sheet, refs, frame, body.get("a"), body.get("box"))
    ref = hashlib.sha1(sheet.tobytes()).hexdigest()[:12]
    REF_SHEETS[ref] = sheet
    while len(REF_SHEETS) > 4:
        REF_SHEETS.popitem(last=False)
    try:
        text, secs, tps = await asyncio.to_thread(bonsai.chat, str(body.get("text", "")), str(body.get("system", "")), sheet,
                                                  body.get("schema"), int(body.get("max_tokens", 600)), 0.2, True)
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=503)
    return web.json_response({"text": text, "seconds": secs, "tokens_per_second": tps, "ref": ref})


@routes.get("/element-forge/api/bonsai/reference/{ref}")
async def ef_bonsai_reference_sheet(request):
    sheet = REF_SHEETS.get(request.match_info["ref"])
    if sheet is None:
        return web.json_response({"error": "gone"}, status=404)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=85)
    return web.Response(body=buf.getvalue(), content_type="image/jpeg", headers={"Cache-Control": "no-store"})


@routes.post("/element-forge/api/bonsai/particles")
async def ef_bonsai_particles(request):
    body = await request.json()
    try:
        system, text, sch, controls = PA.request(body)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    image = REF_SHEETS.get(str(body.get("ref") or ""))
    if image is not None:
        system = PA.PICTURE_SYSTEM
    elif body.get("clip"):
        p = _clip_path(body["clip"], stills=True)
        if p:
            image = await asyncio.to_thread(first_frame, p, max(0.0, float(body.get("time") or 0)))
    try:
        answer, secs, tps = await asyncio.to_thread(bonsai.chat, text, system, image, sch, 900, 0.2, True)
        out = PA.read(answer, controls, body.get("now") or {}, body.get("stops"))
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=503)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=502)
    return web.json_response({**out, "seconds": secs, "tokens_per_second": tps})


_bonsai_setup = {"state": "idle"}


def _llm_dir():
    return folder_paths.get_folder_paths("LLM")[0]


def _bonsai_have(name):
    return folder_paths.get_full_path("LLM", name) is not None


def _bonsai_rt_ok():
    named = bonsai.status().get("runtime")
    return (lambda folder: True) if named else bonsai_rt.is_runtime


@routes.get("/element-forge/api/bonsai/setup")
async def ef_bonsai_setup_status(request):
    out = dict(_bonsai_setup)
    if out["state"] != "running":
        try:
            todo = await asyncio.to_thread(lambda: SB.plan(True, False, _llm_dir(), _bonsai_have, _bonsai_rt_ok()))
            out["plan"] = [{"name": n, "bytes": b, "kind": k} for n, _, b, k in todo]
        except SystemExit as e:
            out["plan"], out["unsupported"] = [], str(e)
    return web.json_response(out)


@routes.post("/element-forge/api/bonsai/setup")
async def ef_bonsai_setup(request):
    if _bonsai_setup.get("state") == "running":
        return web.json_response(_bonsai_setup)
    _bonsai_setup.clear()
    _bonsai_setup.update({"state": "running", "phase": "Starting", "file": None, "done": 0, "total": 0})

    def progress(name, done, total):
        _bonsai_setup.update({"file": name, "done": done, "total": total})

    def phase(text):
        _bonsai_setup["phase"] = text

    def work():
        try:
            SB.install(True, False, _llm_dir(), _bonsai_have, progress, phase, _bonsai_rt_ok())
            _bonsai_setup.update({"state": "done", "phase": "Done"})
        except Exception as e:
            _bonsai_setup.update({"state": "failed", "error": str(e) or e.__class__.__name__})

    threading.Thread(target=work, name="element-forge-bonsai-setup", daemon=True).start()
    return web.json_response(_bonsai_setup)


@routes.post("/element-forge/api/bonsai/stop")
async def ef_bonsai_stop(request):
    await asyncio.to_thread(bonsai.stop)
    return web.json_response({"ok": True})


@routes.get("/element-forge/media/{root}/{tail:.+}")
async def ef_media(request):
    root = request.match_info["root"]
    tail = request.match_info["tail"]
    if root not in MEDIA_ROOTS:
        raise web.HTTPForbidden()
    base = MEDIA_ROOTS[root]()
    p = _inside(base, tail)
    if p and root == "output" and not os.path.relpath(p, os.path.realpath(base)).replace("\\", "/").split("/")[0].startswith("element-forge"):
        raise web.HTTPForbidden()
    if not p or not os.path.isfile(p):
        raise web.HTTPNotFound()
    return _no_cache(web.FileResponse(p))

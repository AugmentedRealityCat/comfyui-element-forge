
import copy
import logging

try:
    from . import nodes as N
    from . import run_node as R
except ImportError:
    import importlib.util
    import os

    def _load(name, file):
        spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(os.path.abspath(__file__)), file))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    N = _load("efa_nodes_for_rewrite", "nodes.py")
    R = _load("efa_run_for_rewrite", "run_node.py")

PICK_CLASSES = {"EFAppPickBool", "EFAppPickInt", "EFAppPickFloat", "EFAppPickString", "EFAppPickAny"}
STAGE_CLASS = "EFAppStage"
EFFECT_CLASS = "EFAppEffect"
VALUES_CLASS = "EFAppValues"
RUN_CLASS = R.RUN_CLASS
LOG_PREFIX = "[Element Forge App]"
STILL_IMAGE = "Still image (a picture in the input folder instead of the clip)"


def is_link(v):
    return (isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int)) and not isinstance(v[0], bool)
            and isinstance(v[1], (int, float)) and not isinstance(v[1], bool))


def _node(prompt, link):
    if not is_link(link):
        return None
    n = prompt.get(str(link[0]))
    return n if isinstance(n, dict) else None


def _unwrap(v):
    if isinstance(v, dict) and "__value__" in v:
        return v["__value__"]
    return v


def resolve_shot(prompt, value):
    if isinstance(value, str):
        return value
    src = _node(prompt, value)
    if not src or src.get("class_type") != STAGE_CLASS or int(value[1]) != 0:
        return None
    shot = (src.get("inputs") or {}).get("shot")
    return shot if isinstance(shot, str) else None


def resolve_effect(prompt, value):
    src = _node(prompt, value)
    if not src or src.get("class_type") != EFFECT_CLASS or int(value[1]) != 0:
        return None
    inputs = src.get("inputs") or {}
    out = {}
    types = N.EFAppEffect.INPUT_TYPES()
    for name in types["required"]:
        if name not in inputs:
            return None
        v = _unwrap(inputs[name])
        if is_link(v):
            return None
        out[name] = v
    for name in types.get("optional", {}):
        if name in inputs:
            v = _unwrap(inputs[name])
            if is_link(v):
                return None
            out[name] = v
    return out


def rewrite_prompt(prompt):
    notes = []
    if not isinstance(prompt, dict):
        return notes
    for vid, vnode in list(prompt.items()):
        if not isinstance(vnode, dict) or vnode.get("class_type") != VALUES_CLASS:
            continue
        inputs = vnode.get("inputs") or {}
        shot = resolve_shot(prompt, inputs.get("shot"))
        if shot is None:
            notes.append(f"{vid}: unchanged (shot not reachable as a constant)")
            continue
        fx = resolve_effect(prompt, inputs.get("effect"))
        if fx is None:
            notes.append(f"{vid}: unchanged (Effect values not reachable as constants)")
            continue
        try:
            effect = N.EFAppEffect().build(**fx)[0]
            settings, run_prefix = N.EFAppValues().run(shot, effect)
        except (ValueError, TypeError) as err:
            notes.append(f"{vid}: unchanged ({err})")
            continue
        picks = prefixes = 0
        for tnode in prompt.values():
            if not isinstance(tnode, dict):
                continue
            tin = tnode.get("inputs")
            if not isinstance(tin, dict):
                continue
            for key, val in list(tin.items()):
                if not is_link(val) or str(val[0]) != str(vid):
                    continue
                slot = int(val[1])
                if slot == 0 and key == "settings" and tnode.get("class_type") in PICK_CLASSES:
                    name = tin.get("name")
                    if not isinstance(name, str):
                        continue
                    v = settings.get(name)
                    tin["settings"] = {name: v} if v is not None else {}
                    picks += 1
                elif slot == 0 and key == "settings" and tnode.get("class_type") == RUN_CLASS:
                    tin["settings"] = dict(settings)
                    picks += 1
                elif slot == 1:
                    tin[key] = run_prefix
                    prefixes += 1
        notes.append(f"{vid}: {picks} settings inputs as constants, {prefixes} run_prefix inputs ({run_prefix})")
        if settings.get(STILL_IMAGE):
            notes += drop_clip_node(prompt)
    return notes


def drop_clip_node(prompt):
    notes = []
    for sid, snode in list(prompt.items()):
        if not isinstance(snode, dict) or snode.get("class_type") != STAGE_CLASS:
            continue
        link = (snode.get("inputs") or {}).get("video")
        src = _node(prompt, link)
        if not src or src.get("class_type") != "LoadVideo":
            continue
        cid = str(link[0])
        for n in prompt.values():
            ins = n.get("inputs") if isinstance(n, dict) else None
            if isinstance(ins, dict):
                for k, v in list(ins.items()):
                    if is_link(v) and str(v[0]) == cid:
                        del ins[k]
        prompt.pop(cid, None)
        notes.append(f"{sid}: still image, clip node {cid} dropped")
    return notes


def effect_of(prompt, link):
    fx = resolve_effect(prompt, link)
    if fx is None:
        return None
    try:
        return N.EFAppEffect().build(**fx)[0]
    except (ValueError, TypeError):
        return None


def expand_runs(new, json_data):
    before = set(new)
    notes = R.queue_expand(new, lambda link: effect_of(new, link))
    targets = json_data.get("partial_execution_targets")
    if isinstance(targets, list):
        added = [k for k in new if k not in before and any(k.startswith(f"{t}.") for t in targets)]
        json_data["partial_execution_targets"] = targets + added
    return notes


def on_prompt(json_data):
    try:
        prompt = json_data.get("prompt") if isinstance(json_data, dict) else None
        if not isinstance(prompt, dict):
            return json_data
        if not any(isinstance(n, dict) and n.get("class_type") in (VALUES_CLASS, RUN_CLASS) for n in prompt.values()):
            return json_data
        new = copy.deepcopy(prompt)
        notes = rewrite_prompt(new)
        if any(isinstance(n, dict) and n.get("class_type") == RUN_CLASS for n in new.values()):
            notes += expand_runs(new, json_data)
        json_data["prompt"] = new
        logging.info("%s %s", LOG_PREFIX, "; ".join(notes) or "keine EFAppValues-Node")
    except Exception:
        logging.warning("%s Umschreibung fehlgeschlagen, Prompt bleibt unveraendert", LOG_PREFIX, exc_info=True)
    return json_data

import json

MAX_CHANGES = 10
MAX_FACTOR = 5.0
COLOURS = {
    "white": [1.0, 1.0, 1.0], "warm white": [1.0, 0.93, 0.8], "yellow": [1.0, 0.9, 0.25], "gold": [1.0, 0.75, 0.25],
    "orange": [1.0, 0.5, 0.1], "red": [0.95, 0.15, 0.08], "deep red": [0.55, 0.05, 0.03], "pink": [1.0, 0.5, 0.75],
    "magenta": [0.95, 0.2, 0.85], "purple": [0.6, 0.25, 0.95], "blue": [0.2, 0.45, 1.0], "light blue": [0.6, 0.85, 1.0],
    "cyan": [0.3, 0.95, 1.0], "teal": [0.1, 0.65, 0.6], "green": [0.25, 0.9, 0.3], "lime": [0.7, 1.0, 0.2],
    "dark green": [0.06, 0.28, 0.08], "dark blue": [0.05, 0.12, 0.4], "dark purple": [0.25, 0.08, 0.4],
    "brown": [0.45, 0.3, 0.18], "light grey": [0.75, 0.75, 0.75], "grey": [0.5, 0.5, 0.5], "dark grey": [0.22, 0.22, 0.23],
    "black": [0.04, 0.04, 0.04],
}
KEEP = "keep"

SYSTEM = """You tune the particle simulation of Element Forge so that it matches the effect's prompt. The prompt is what the video model is told to paint; the particles are the guide it follows, so their amount, speed, size, life, colour and forces should fit its words.
Rules:
- The values now fit the style's own prompt. Compare the prompt now with it and change only what the different words ask for or clearly imply (slow, fast, many, few, tiny, huge, long trails, swirling, heavy, rising, falling, wind, bouncing, colour ...). Words that are the same as in the style's own prompt need no change. Keep every other value. If the prompt asks for nothing new, answer with no changes.
- Prefer few changes: the three to six values that matter most for the new words. No value at the end of its range unless the prompt says "extreme".
- Values must stay inside the given range. Scale from the value now: "a bit" about 1.3x, plain words like "slow" or "many" about 2x, "very" or "huge" 3x, never more than 5x or less than a fifth.
- Units: px at a 1080 px picture, s = seconds. Rate is particles per second, burst particles at once. wind: + to the right.
- direction is where they fly off: 0 up, 90 right, 180 down, 270 left. Change it only when the prompt names a way (up, down, to the left, sideways ...), the user set it in the picture. gravity is the world's pull: + falls, - rises (smoke, fire, embers, magic). To shoot something up, change direction and speed, not the sign of gravity.
- colour_birth and colour_end: when the prompt names a colour that differs from the colours now, choose the nearest names (birth = when it appears, end = when it fades); else "keep".
- mode, collide, sprite: "keep" unless the prompt asks for something else.
- why: at most 8 words, the prompt's words that ask for the change.
- note: one short sentence to the user about what the particles will do now."""

PICTURE_SYSTEM = """You tune the particle simulation of Element Forge so that the particles look and move like the effect in the reference pictures. The picture is a collage: on the left the reference pictures, on the right the user's clip; the effect goes at the yellow mark. The particles are the guide the video model follows.
Rules:
- Look at the reference: how many particles, how big, how fast and which way they move (long streaks mean fast or long trails), how long they live, how wide they spread, their colour when they appear and when they fade. Change the values where the reference differs from the values now, keep the ones that already fit. The prompt now says what the user wants on top of it.
- Prefer few changes: the three to six values that matter most for the look. No value at the end of its range unless the reference is extreme.
- Values must stay inside the given range. Scale from the value now: a bit about 1.3x, clearly 2x, very 3x, never more than 5x or less than a fifth.
- Units: px at a 1080 px picture, s = seconds. Rate is particles per second, burst particles at once. wind: + to the right.
- direction is where they fly off: 0 up, 90 right, 180 down, 270 left; change it only when the reference clearly moves one way. gravity: + falls, - rises.
- colour_birth and colour_end: the nearest names to the reference's colours (birth = when they appear, end = when they fade); "keep" when the colours now already fit.
- mode, collide, sprite: "keep" unless the reference clearly shows something else (sprite: the particles' shape).
- why: at most 8 words, what the reference shows.
- note: one short sentence to the user about what the particles will do now. The yellow mark and the collage are not seen by the user: do not mention them."""


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def clean_controls(controls):
    out = []
    for c in controls or []:
        k, lo, hi, now = str(c.get("k") or ""), _num(c.get("min")), _num(c.get("max")), _num(c.get("now"))
        if not k or lo is None or hi is None or now is None or hi <= lo:
            continue
        out.append({**c, "k": k, "min": min(lo, now), "max": max(hi, now), "now": now})
    return out


def schema(controls, modes, collides, sprites):
    keys = [c["k"] for c in controls]
    return {
        "type": "object", "additionalProperties": False, "x-compact": True,
        "properties": {
            "colour_birth": {"type": "string", "enum": [KEEP, *COLOURS]},
            "colour_end": {"type": "string", "enum": [KEEP, *COLOURS]},
            "mode": {"type": "string", "enum": [KEEP, *modes]},
            "collide": {"type": "string", "enum": [KEEP, *collides]},
            "sprite": {"type": "string", "enum": [KEEP, *sprites]},
            "changes": {"type": "array", "maxItems": MAX_CHANGES, "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"key": {"type": "string", "enum": keys}, "value": {"type": "number"},
                               "why": {"type": "string", "maxLength": 60}},
                "required": ["key", "value", "why"]}},
            "note": {"type": "string", "maxLength": 160},
        },
        "required": ["colour_birth", "colour_end", "mode", "collide", "sprite", "changes", "note"],
    }


def nearest(rgb):
    return min(COLOURS, key=lambda n: sum((COLOURS[n][i] - float(rgb[i])) ** 2 for i in range(3)))


def colour_words(stops):
    try:
        return f"{nearest(stops[0][1])} at birth, {nearest(stops[-1][1])} at the end"
    except (TypeError, IndexError, ValueError):
        return ""


def _fmt(v):
    return str(round(v, 3)).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def _words(prompt):
    return [f"- {k}: {str(prompt[k]).strip()}" for k in ("what", "look", "motion", "contact") if str(prompt.get(k) or "").strip()]


def text(prompt, style, controls, now, own=None):
    lines = [f"Style: {style or 'particles'}", ""]
    if own and _words(own):
        lines += ["The style's own prompt (the values now fit it):", *_words(own), ""]
    lines += ["Prompt now:", *(_words(prompt) or ["- (none)"])]
    lines += ["", "Values now (key: now [min..max] unit - what it is):"]
    for c in controls:
        tip = f" ({c['tip']})" if c.get("tip") else ""
        lines.append(f"{c['k']}: {_fmt(c['now'])} [{_fmt(c['min'])}..{_fmt(c['max'])}] {c.get('unit') or ''} - {c.get('label', c['k'])}{tip}")
    lines += ["", f"mode now: {now.get('mode')}; collide now: {now.get('collide')}; sprite now: {now.get('sprite')}",
              f"colours now: {colour_words(now.get('stops')) or 'as the style'}"]
    return "\n".join(lines)


def request(body):
    controls = clean_controls(body.get("controls"))
    if not controls:
        raise ValueError("no particle controls to fill")
    now = {**(body.get("now") or {}), "stops": body.get("stops")}
    sch = schema(controls, [str(x) for x in body.get("modes") or []], [str(x) for x in body.get("collides") or []],
                 [str(x) for x in body.get("sprites") or []])
    return SYSTEM, text(body.get("prompt") or {}, str(body.get("style") or ""), controls, now, body.get("style_prompt")), sch, controls


def _luma(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def gradient(stops, birth, end):
    if birth == KEEP and end == KEEP:
        return None
    stops = stops if isinstance(stops, list) and len(stops) >= 2 else [[0.0, [1, 1, 1]], [1.0, [1, 1, 1]]]
    l0, l1 = max(1e-3, _luma(stops[0][1])), _luma(stops[-1][1])
    a = COLOURS.get(birth)
    b = COLOURS.get(end)
    if a is None:
        a = [min(1.0, x * l0 / max(1e-3, l1)) for x in b]
    if b is None:
        b = [x * min(1.0, l1 / l0) for x in a]
    out = []
    for t, _ in stops:
        t = float(t)
        out.append([t, [round(a[i] + (b[i] - a[i]) * t, 4) for i in range(3)]])
    return out


def read(answer, controls, now, stops=None):
    try:
        p = json.loads(answer)
    except (TypeError, ValueError):
        raise ValueError("Bonsai did not answer in the expected form. Try again.")
    by = {c["k"]: c for c in controls}
    off = {k for k, other in (("rate", "burst"), ("burst", "rate")) if k in by and other in by and by[k]["now"] == 0 and by[other]["now"] > 0}
    out, seen = [], set()
    for ch in (p.get("changes") or [])[:MAX_CHANGES]:
        c = by.get(str(ch.get("key")))
        v = _num(ch.get("value"))
        if not c or v is None or c["k"] in seen or c["k"] in off:
            continue
        if c["now"] > 0 and c["min"] >= 0 and not c.get("angle"):
            v = min(c["now"] * MAX_FACTOR, max(c["now"] / MAX_FACTOR, v))
        v = min(c["max"], max(c["min"], v))
        v = round(v) if c.get("int") else round(v, 4)
        step = _num(c.get("step")) or 0
        if abs(v - c["now"]) <= max(1e-6, step / 2):
            continue
        seen.add(c["k"])
        out.append({"key": c["k"], "label": c.get("label", c["k"]), "from": c["now"], "to": v,
                    "why": str(ch.get("why") or "").strip()[:60]})
    res = {"changes": out, "note": str(p.get("note") or "").strip()[:160]}
    for k in ("mode", "collide", "sprite"):
        v = str(p.get(k) or KEEP)
        res[k] = v if v != KEEP and v != now.get(k) else None
    res["colors"] = gradient(stops, str(p.get("colour_birth") or KEEP), str(p.get("colour_end") or KEEP))
    res["colour_names"] = [nearest(res["colors"][0][1]), nearest(res["colors"][-1][1])] if res["colors"] else None
    return res

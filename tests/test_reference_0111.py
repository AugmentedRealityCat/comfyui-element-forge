import ast
import base64
import io
import os

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_funcs(fname, names, extra):
    src = open(os.path.join(HERE, fname), encoding="utf-8").read()
    nodes = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names]
    g = dict(extra)
    exec(compile(ast.Module(nodes, []), fname, "exec"), g)
    return g


g = load_funcs("element_forge/app/app_routes.py", {"reference_sheet", "_picture"}, {"io": io})
sheet, picture = g["reference_sheet"], g["_picture"]

ref = Image.new("RGB", (600, 800), (0, 0, 255))
frame = Image.new("RGB", (1920, 1080), (0, 128, 0))
s = sheet([ref, ref, ref, ref], frame, [960, 540], [700, 300, 520, 480])
assert s.size == (1024, 576)
assert s.getpixel((150, 120))[2] > 200
assert s.getpixel((700, 200))[1] > 100
lw, rw = 1024 * 2 // 5, 1024 - 1024 * 2 // 5
k = (rw - 16) / 1920
x0, y0 = lw + 8 + (rw - 16 - round(1920 * k)) // 2, 24 + (576 - 32 - round(1080 * k)) // 2
ring = [s.getpixel((round(x0 + 960 * k + dx), round(y0 + 540 * k))) for dx in range(-16, 17)]
assert any(p[0] > 200 and p[1] > 180 and p[2] < 120 for p in ring)
print("reference_sheet: references left (at most three), the clip right, the place ringed in yellow")

s2 = sheet([ref], None)
assert s2.size == (1024, 576)
print("reference_sheet: without a clip only the references")


def url(im, fmt="PNG"):
    b = io.BytesIO()
    im.save(b, fmt)
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(b.getvalue()).decode()


assert picture(url(ref)).size == (600, 800)
assert picture(url(ref.convert("L"), "JPEG")).mode == "RGB"
for bad in ("data:text/plain;base64,AAAA", "no picture", "data:image/png;base64,"):
    try:
        picture(bad)
        raise AssertionError(bad)
    except ValueError:
        pass
print("_picture: PNG and JPEG data URLs read as RGB, other things refused")

src = open(os.path.join(HERE, "element_forge/app/app_routes.py"), encoding="utf-8").read()
assert "system = PA.PICTURE_SYSTEM" in src and '"/element-forge/api/bonsai/reference"' in src
pa = open(os.path.join(HERE, "element_forge/app/particle_assist.py"), encoding="utf-8").read()
tree = ast.parse(pa)
names = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
assert {"SYSTEM", "PICTURE_SYSTEM"} <= names
print("particle fill: from a picture with its own instructions (the reference decides)")
print("all passed")

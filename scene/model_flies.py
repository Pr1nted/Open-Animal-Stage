"""Drosophila models for the stage: adult female, adult male, third-instar larva.

Run with Blender 2.93 headless:
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        --python scene/model_flies.py -- --out web/models --previews data/raw/previews/flies

Writes web/models/drosophila_{female,male,larva}.glb and, unless --no-previews,
three preview renders per animal plus contact.png (the three .glb files
imported back and rendered side by side). docs/models.md is the contract.

Built from Open Fly's fly (Open-Fly/scene/fly_at_computer.py): its Voronoi
ommatidia became a baked hex normal map (glTF carries no procedural nodes), its
UV-sphere blobs became lofted surfaces with real sections, its stick legs became
coxa / trochanter / femur / tibia / five tarsomeres, its shell-patch wings
became a veined Drosophila wing outline.

The adults are modelled in millimetres (life size, head facing +Y, Z up) under
a root node that scales them to stage metres; the larva is built in metres.
glTF export turns Blender's (+Z up, +Y forward) into the page's (+Y up, -Z
forward). The fly's left is Blender -X.
"""
import argparse
import math
import os
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", default="web/models")
ap.add_argument("--previews", default="data/raw/previews/flies")
ap.add_argument("--only", default="", help="comma list of species ids to build")
ap.add_argument("--samples", type=int, default=32)
ap.add_argument("--res", default="960x720")
ap.add_argument("--no-previews", action="store_true")
ap.add_argument("--no-contact", action="store_true")
args = ap.parse_args(argv)

OUT = os.path.abspath(args.out)
PREV = os.path.abspath(args.previews)
os.makedirs(OUT, exist_ok=True)
os.makedirs(PREV, exist_ok=True)
TMP = tempfile.mkdtemp(prefix="flies_")

FLY_BODY_M = 0.30          # female, front of head to abdomen tip, stage metres
MALE_K = 0.90              # the male is a smaller fly
LARVA_M = 0.30


# ── small maths ──────────────────────────────────────────────────────────────
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))


def srgb(r, g, b):
    return (r / 255.0, g / 255.0, b / 255.0, 1.0)


def interp(keys, x):
    """Catmull-Rom through (x, v1, v2, ...) keys sorted by x."""
    if x <= keys[0][0]:
        return list(keys[0][1:])
    if x >= keys[-1][0]:
        return list(keys[-1][1:])
    i = 0
    while keys[i + 1][0] < x:
        i += 1
    k0, k1, k2, k3 = keys[max(i - 1, 0)], keys[i], keys[i + 1], keys[min(i + 2, len(keys) - 1)]
    t = (x - k1[0]) / (k2[0] - k1[0])
    out = []
    for c in range(1, len(k1)):
        p0, p1, p2, p3 = k0[c], k1[c], k2[c], k3[c]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return out


def perp_frame(d):
    d = d.normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    n = d.cross(ref).normalized()
    b = d.cross(n).normalized()
    return n, b


# ── mesh builder: many parts, one object, per-vertex colour and uv ───────────
class MB:
    def __init__(self):
        self.co, self.col, self.uv, self.faces, self.fmat, self.mats = [], [], [], [], [], []
        self.groups = []          # per vertex: list of (group name, weight)

    def mat(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def vert(self, p, c, uv=(0.0, 0.0)):
        self.co.append((p[0], p[1], p[2]))
        self.col.append(c if len(c) == 4 else (*c, 1.0))
        self.uv.append(uv)
        self.groups.append(None)
        return len(self.co) - 1

    def face(self, idx, m):
        self.faces.append(tuple(idx))
        self.fmat.append(m)

    def rings(self, R, C, mat, U=None, pole0=None, pole1=None, closed=True):
        """R: rings of points; C: matching colours; pole = (point, colour)."""
        m = self.mat(mat)
        n = len(R[0])
        ids = [[self.vert(R[i][j], C[i][j], U[i][j] if U else (0, 0)) for j in range(n)] for i in range(len(R))]
        span = n if closed else n - 1
        for i in range(len(R) - 1):
            for j in range(span):
                j2 = (j + 1) % n
                self.face((ids[i][j], ids[i][j2], ids[i + 1][j2], ids[i + 1][j]), m)
        if pole0:
            v = self.vert(pole0[0], pole0[1], pole0[2] if len(pole0) > 2 else (0, 0))
            for j in range(span):
                self.face((v, ids[0][(j + 1) % n], ids[0][j]), m)
        if pole1:
            v = self.vert(pole1[0], pole1[1], pole1[2] if len(pole1) > 2 else (0, 0))
            for j in range(span):
                self.face((v, ids[-1][j], ids[-1][(j + 1) % n]), m)
        return ids

    def build(self, name, origin=(0, 0, 0), uv=False):
        o = Vector(origin)
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(Vector(c) - o) for c in self.co], [], self.faces)
        me.polygons.foreach_set("material_index", self.fmat)
        me.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        for m in self.mats:
            me.materials.append(m)
        lv = np.zeros(len(me.loops), dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv)
        vc = me.vertex_colors.new(name="Col")
        col = np.array(self.col, dtype=np.float32)[lv]
        vc.data.foreach_set("color", col.ravel())
        if uv:
            uvl = me.uv_layers.new(name="UVMap")
            uva = np.array(self.uv, dtype=np.float32)[lv]
            uvl.data.foreach_set("uv", uva.ravel())
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
        me.update()
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = o
        return ob


def loft(mb, f, nu, nth, mat, colfn, uvfn=None, cos_u=False):
    """A closed surface f(u, th) with poles at u = 0 and u = 1."""
    us = [(1 - math.cos(math.pi * i / nu)) / 2 if cos_u else i / nu for i in range(1, nu)]
    ths = [2 * math.pi * j / nth for j in range(nth)]
    R, C, U = [], [], []
    for u in us:
        ring = [f(u, th) for th in ths]
        R.append(ring)
        C.append([colfn(u, th, p) for th, p in zip(ths, ring)])
        U.append([uvfn(u, th, p) if uvfn else (0, 0) for th, p in zip(ths, ring)])
    p0, p1 = f(0.0, 0.0), f(1.0, 0.0)
    return mb.rings(R, C, mat, U,
                    pole0=(p0, colfn(0.0, 0.0, p0), uvfn(0.0, 0.0, p0) if uvfn else (0, 0)),
                    pole1=(p1, colfn(1.0, 0.0, p1), uvfn(1.0, 0.0, p1) if uvfn else (0, 0)))


def surf_frame(f, u, th, eps=1e-3):
    """Point, outward normal on a lofted surface."""
    p = f(u, th)
    du = f(min(u + eps, 1 - 1e-4), th) - f(max(u - eps, 1e-4), th)
    dt = f(u, th + eps) - f(u, th - eps)
    n = du.cross(dt).normalized()
    centre = (f(u, 0.0) + f(u, math.pi)) * 0.5
    if n.dot(p - centre) < 0:
        n = -n
    return p, n


def tube(mb, path, radii, n, mat, col, cap0=True, cap1=True):
    """A tube along a polyline, parallel-transported frames; radius 0 at an end is a point."""
    P = [Vector(p) for p in path]
    T = []
    for i in range(len(P)):
        a, b = P[max(i - 1, 0)], P[min(i + 1, len(P) - 1)]
        T.append((b - a).normalized())
    N, _ = perp_frame(T[0])
    R, C = [], []
    first, last = 0, len(P)
    pole0 = pole1 = None
    if radii[0] <= 1e-9:
        pole0 = (P[0], col if not callable(col) else col(0.0))
        first = 1
    if radii[-1] <= 1e-9:
        pole1 = (P[-1], col if not callable(col) else col(1.0))
        last = len(P) - 1
    prevT = T[0]
    for i in range(len(P)):
        q = prevT.rotation_difference(T[i])
        N = (q @ N).normalized()
        prevT = T[i]
        if i < first or i >= last:
            continue
        B = T[i].cross(N).normalized()
        ring = [P[i] + (N * math.cos(2 * math.pi * j / n) + B * math.sin(2 * math.pi * j / n)) * radii[i] for j in range(n)]
        R.append(ring)
        c = col(i / (len(P) - 1)) if callable(col) else col
        C.append([c] * n)
    if pole0 is None and cap0:
        pole0 = (P[0] - T[0] * radii[0] * 0.3, C[0][0])
    if pole1 is None and cap1:
        pole1 = (P[-1] + T[-1] * radii[-1] * 0.3, C[-1][0])
    return mb.rings(R, C, mat, pole0=pole0, pole1=pole1)


def capsule(mb, a, b, rfn, n, nl, mat, col, over=0.5):
    """A rounded leg segment from a to b; rfn(t) its radius profile; ends overlap by over*r."""
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    a2 = a - d * rfn(0.0) * over
    b2 = b + d * rfn(1.0) * over
    path, radii = [], []
    for k in range(nl + 1):
        t = (1 - math.cos(math.pi * k / nl)) / 2
        path.append(a2 + (b2 - a2) * t)
        end = max(0.0, 1 - abs(2 * t - 1) ** 5) ** 0.5
        radii.append(rfn(t) * end)
    return tube(mb, path, radii, n, mat, col)


def bezier(p0, p1, p2, k):
    return [p0 * (1 - t) ** 2 + p1 * 2 * t * (1 - t) + p2 * t * t for t in (i / k for i in range(k + 1))]


def bristle(mb, root, normal, lean, length, r0, mat, col, n=4, k=4):
    """A tapering, slightly curved bristle rooted just under the surface."""
    normal, lean = Vector(normal).normalized(), Vector(lean).normalized()
    d0 = (normal * 0.55 + lean * 0.45).normalized()
    d1 = (normal * 0.1 + lean).normalized()
    p0 = Vector(root) - normal * r0 * 1.5
    p1 = p0 + d0 * length * 0.55
    p2 = p1 + d1 * length * 0.5
    pts = bezier(p0, p1, p2, k)
    radii = [r0 * (1 - i / k) ** 0.8 for i in range(k + 1)]
    radii[-1] = 0.0
    tube(mb, pts, radii, n, mat, col)


# ── materials ────────────────────────────────────────────────────────────────
def vc_material(name, rough=0.4, spec=0.5, alpha=None, cull=True, clearcoat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    vc = nt.nodes.new("ShaderNodeVertexColor")
    vc.layer_name = "Col"
    nt.links.new(vc.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular"].default_value = spec
    b.inputs["Clearcoat"].default_value = clearcoat
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.shadow_method = "HASHED"
        m.show_transparent_back = False
    m.use_backface_culling = cull
    return m


def flat_material(name, color, rough=0.4, metal=0.0, alpha=None, cull=True, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular"].default_value = spec
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.shadow_method = "HASHED"
        m.show_transparent_back = False
    m.use_backface_culling = cull
    return m


def hex_normal_map(path, size=512, across=34, strength=2.2):
    """Ommatidia: a hexagonal lattice of domes, as a tangent-space normal map."""
    a = size / across
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64) + 0.5
    best = np.full(xx.shape, 1e9)
    h3 = a * math.sqrt(3)
    for ox, oy in ((0.0, 0.0), (a / 2, h3 / 2)):
        cx = np.round((xx - ox) / a) * a + ox
        cy = np.round((yy - oy) / h3) * h3 + oy
        best = np.minimum(best, np.hypot(xx - cx, yy - cy))
    r = best / (a * 0.577)
    h = np.cos(np.clip(r, 0, 1) * math.pi / 2) ** 0.8
    gy, gx = np.gradient(h)
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(h)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
    img = bpy.data.images.new("eye_facets", size, size, alpha=False)
    px = np.concatenate([rgb, np.ones((size, size, 1))], -1).astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.colorspace_settings.name = "Non-Color"
    return img


def eye_material(img):
    m = bpy.data.materials.new("compound_eye")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.42, 0.012, 0.008, 1)
    b.inputs["Roughness"].default_value = 0.32
    b.inputs["Specular"].default_value = 0.55
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.9
    nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    m.use_backface_culling = True
    return m


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.objects, bpy.data.armatures):
        for x in list(coll):
            try:
                coll.remove(x)
            except Exception:
                pass


# ── the adult fly ────────────────────────────────────────────────────────────
# Units: mm, fly facing +Y, Z up, right side +X. The front of the head is at
# y = 1.0; the female abdomen tip near y = -1.66.

C_THORAX = srgb(132, 96, 60)
C_THORAX_DARK = srgb(98, 70, 44)
C_PLEURA = srgb(170, 128, 80)
C_ABD = srgb(200, 148, 74)
C_ABD_VENT = srgb(214, 184, 128)
C_BAND = srgb(46, 30, 20)
C_LEG = srgb(186, 138, 80)
C_LEG_DARK = srgb(130, 90, 50)
C_BRISTLE = srgb(24, 17, 12)
C_FRONS = srgb(186, 104, 46)
C_FACE = srgb(206, 164, 104)
C_OCCIPUT = srgb(128, 88, 52)
C_OCELLUS = srgb(90, 35, 18)
C_HALTERE = srgb(222, 204, 160)

TH_KEYS = [  # y, half width, top z, bottom z, widest z
    (-0.40, 0.06, 0.88, 0.74, 0.82),
    (-0.34, 0.21, 0.99, 0.63, 0.82),
    (-0.25, 0.30, 1.10, 0.54, 0.81),
    (-0.12, 0.36, 1.18, 0.48, 0.80),
    (0.05, 0.385, 1.22, 0.46, 0.80),
    (0.25, 0.38, 1.21, 0.47, 0.80),
    (0.42, 0.33, 1.15, 0.52, 0.81),
    (0.55, 0.24, 1.07, 0.61, 0.84),
    (0.62, 0.13, 0.99, 0.75, 0.88),
    (0.66, 0.04, 0.94, 0.86, 0.90),
]

ABD_KEYS = {  # y, half width, top z, bottom z
    "female": [(-1.66, 0.00, 0.64, 0.62), (-1.60, 0.07, 0.70, 0.56), (-1.50, 0.16, 0.79, 0.49),
               (-1.36, 0.28, 0.90, 0.43), (-1.18, 0.38, 1.00, 0.39), (-0.95, 0.44, 1.07, 0.37),
               (-0.70, 0.44, 1.11, 0.39), (-0.45, 0.38, 1.10, 0.46), (-0.32, 0.26, 1.02, 0.56),
               (-0.24, 0.06, 0.90, 0.72)],
    "male": [(-1.25, 0.00, 0.74, 0.70), (-1.21, 0.13, 0.84, 0.56), (-1.13, 0.24, 0.93, 0.48),
             (-1.00, 0.33, 1.00, 0.44), (-0.80, 0.37, 1.05, 0.43), (-0.60, 0.37, 1.07, 0.45),
             (-0.44, 0.33, 1.06, 0.49), (-0.32, 0.24, 1.00, 0.57), (-0.24, 0.06, 0.90, 0.72)],
}
# Tergite boundaries (A1/A2 onwards), front to back.
TERGITES = {
    "female": [-0.30, -0.47, -0.66, -0.86, -1.06, -1.25, -1.42, -1.55],
    "male": [-0.30, -0.47, -0.65, -0.83, -0.99, -1.12],
}


def superellipse(c, s, p=2.4):
    return (math.copysign(abs(c) ** (2 / p), c), math.copysign(abs(s) ** (2 / p), s))


def end_round(u, k=8):
    return max(0.0, 1 - abs(2 * u - 1) ** k) ** 0.5


def thorax_f(u, th):
    y = TH_KEYS[-1][0] + (TH_KEYS[0][0] - TH_KEYS[-1][0]) * u
    w, zt, zb, zm = interp(TH_KEYS, y)
    e = end_round(u)
    cx, sz = superellipse(math.cos(th), math.sin(th))
    h = (zt - zm) if sz > 0 else (zm - zb)
    return Vector((w * e * cx, y, zm + h * e * sz))


def make_abdomen_f(sex):
    keys = ABD_KEYS[sex]
    y0, y1 = keys[-1][0], keys[0][0]
    bounds = TERGITES[sex]

    def tergite_phase(y):
        for i in range(len(bounds) - 1):
            if bounds[i + 1] <= y <= bounds[i]:
                return i, (bounds[i] - y) / (bounds[i] - bounds[i + 1])
        return -1, 0.0

    def f(u, th):
        y = y0 + (y1 - y0) * u
        w, zt, zb = interp(keys, y)
        zm = (zt + zb) / 2
        e = end_round(u, 6)
        i, ph = tergite_phase(y)
        # shingled tergites: each rises towards its hind edge, then steps down
        shingle = 1.0 + (0.035 * smooth(0.0, 0.9, ph) - 0.03 * smooth(0.9, 1.0, ph)) if i >= 0 else 1.0
        dorsal = smooth(-0.6, 0.2, math.sin(th))
        s = 1 + (shingle - 1) * dorsal
        cx, sz = superellipse(math.cos(th), math.sin(th), 2.2)
        h = (zt - zm)
        return Vector((w * e * s * cx, y, zm + h * e * s * sz))

    f.phase = tergite_phase
    return f


def abdomen_colour(sex, f):
    last = len(TERGITES[sex]) - 2

    def col(u, th, p):
        i, ph = f.phase(p.y)
        s = math.sin(th)
        dorsal = smooth(-0.55, 0.05, s)             # tergites wrap down the sides
        base = mix(C_ABD_VENT, C_ABD, smooth(-0.8, -0.2, s))
        dark = 0.0
        if sex == "female":
            if i >= 0:
                dark = smooth(0.52, 0.64, ph) * (1 - smooth(0.97, 1.0, ph) * 0.3)
                dark *= 0.85 + 0.15 * abs(math.cos(th))  # the band thins at the midline
                if i == last:
                    dark = max(dark, smooth(0.3, 0.6, ph))
            if p.y < TERGITES[sex][-1]:
                dark = 0.8                          # ovipositor plates
        else:
            if i >= 0:
                dark = smooth(0.5, 0.62, ph)
                if i >= last - 1:                   # A5 and A6: fused solid black
                    dark = 1.0
            if p.y < TERGITES[sex][-1]:
                dark = 1.0
        dark *= dorsal if not (sex == "male" and (i >= last - 1 or p.y < TERGITES[sex][-1])) else smooth(-0.9, -0.3, s)
        return mix(base, C_BAND, clamp(dark))

    return col


def thorax_colour(u, th, p):
    s = math.sin(th)
    c = mix(C_PLEURA, C_THORAX, smooth(0.1, 0.6, s))
    # faint darker dorsocentral stripes, as in the real scutum
    stripe = math.exp(-((abs(p.x) - 0.17) / 0.06) ** 2) * smooth(0.5, 0.9, s) * smooth(-0.35, 0.2, p.y)
    c = mix(c, C_THORAX_DARK, 0.35 * stripe)
    # the notopleural suture: a thin darker line along the side
    sut = math.exp(-((p.z - 1.02) / 0.02) ** 2) * smooth(0.25, 0.45, abs(math.cos(th)))
    return mix(c, C_THORAX_DARK, 0.4 * sut)


HEAD_C = Vector((0.0, 0.81, 0.95))


def head_semi(d):
    return (0.34, 0.22 if d.y > 0 else 0.17, 0.34 if d.z > 0 else 0.30)


def ellipsoid_f(c, semi, rot=None):
    c = Vector(c)
    rot = rot or Matrix.Identity(3)

    def f(u, th):
        phi = math.pi * u
        d = Vector((-math.cos(phi), math.sin(phi) * math.cos(th), math.sin(phi) * math.sin(th)))
        ax, ay, az = semi(d) if callable(semi) else semi
        return c + rot @ Vector((d.x * ax, d.y * ay, d.z * az))

    return f


def ellipsoid_point(c, semi, d, rot=None):
    """Point and outward normal on an ellipsoid along a parameter direction d."""
    d = Vector(d).normalized()
    ax, ay, az = semi(d) if callable(semi) else semi
    rot = rot or Matrix.Identity(3)
    p = Vector(c) + rot @ Vector((d.x * ax, d.y * ay, d.z * az))
    n = rot @ Vector((d.x / ax, d.y / ay, d.z / az))
    return p, n.normalized()


def head_colour(u, th, p):
    q = p - HEAD_C
    c = C_OCCIPUT
    front = smooth(-0.02, 0.12, q.y)
    c = mix(c, C_FACE, front)
    frons = front * smooth(-0.05, 0.12, q.z) * (1 - smooth(0.12, 0.2, abs(q.x)))
    c = mix(c, C_FRONS, frons)
    # the ocellar triangle and the vertex
    tri = smooth(0.22, 0.28, q.z) * (1 - smooth(0.05, 0.12, abs(q.x))) * (1 - smooth(-0.02, 0.1, q.y))
    c = mix(c, srgb(90, 62, 40), tri * 0.8)
    return c


def build_fly(sex):
    female = sex == "female"
    CUT = vc_material("cuticle", rough=0.36, spec=0.55, clearcoat=0.25)
    LEGM = vc_material("leg_cuticle", rough=0.45, spec=0.5)
    WING = flat_material("wing_membrane", (0.58, 0.58, 0.56, 1), rough=0.08, alpha=0.4, cull=False, spec=0.9)
    VEIN = flat_material("wing_vein", (0.16, 0.10, 0.05, 1), rough=0.4, cull=True, spec=0.3)
    EYE = eye_material(hex_normal_map(os.path.join(TMP, "eye_facets.png")))

    root = bpy.data.objects.new(f"drosophila_{sex}", None)
    bpy.context.scene.collection.objects.link(root)

    # ─ body: thorax, scutellum, abdomen, halteres, mid and hind legs ─
    body = MB()
    loft(body, thorax_f, 56, 36, CUT, thorax_colour)
    SC_C, SC_S = (0.0, -0.30, 1.105), (0.20, 0.15, 0.085)
    rot_sc = Matrix.Rotation(math.radians(-18), 3, "X")
    loft(body, ellipsoid_f(SC_C, SC_S, rot_sc), 20, 28, CUT,
         lambda u, th, p: mix(C_THORAX, C_THORAX_DARK, 0.25))
    abd_f = make_abdomen_f(sex)
    loft(body, abd_f, 96 if female else 80, 36, CUT, abdomen_colour(sex, abd_f))

    # macrochaetae of the notum: (y, angle from the top, lean, length)
    for sx in (-1, 1):
        for y, ang, lean, ln in ((0.44, 1.15, (0.6, -0.6, 0.9), 0.20),      # humeral
                                 (0.26, 1.30, (0.8, -0.6, 1.0), 0.22),      # notopleurals
                                 (0.10, 1.30, (0.8, -0.6, 1.0), 0.24),
                                 (-0.02, 1.00, (0.3, -1, 0.5), 0.24),     # supra-alar
                                 (-0.18, 0.90, (0.3, -1, 0.3), 0.26),     # post-alar
                                 (0.04, 0.36, (0.05, -1, 0.35), 0.30),    # dorsocentrals
                                 (-0.16, 0.33, (0.05, -1, 0.3), 0.34)):
            u = (TH_KEYS[-1][0] - y) / (TH_KEYS[-1][0] - TH_KEYS[0][0])
            th = math.pi / 2 - sx * ang
            p, n = surf_frame(thorax_f, u, th)
            bristle(body, p, n, Vector(lean) * Vector((sx, 1, 1)), ln, 0.014, CUT, C_BRISTLE)
        # scutellars: the apicals cross behind
        for d, lean, ln in (((sx * 0.55, 0.3, 0.8), (-sx * 0.25, -1, 0.25), 0.34),
                            ((sx * 0.3, -0.8, 0.6), (-sx * 0.35, -1, 0.35), 0.44)):
            p, n = ellipsoid_point(SC_C, SC_S, d, rot_sc)
            bristle(body, p, n, lean, ln, 0.014, CUT, C_BRISTLE)
    # microchaetae in rows over the scutum
    for row in range(-5, 6):
        for k in range(9):
            y = 0.48 - k * 0.08
            u = (TH_KEYS[-1][0] - y) / (TH_KEYS[-1][0] - TH_KEYS[0][0])
            th = math.pi / 2 + row * 0.12 + 0.02 * ((k * 7) % 3 - 1)
            p, n = surf_frame(thorax_f, u, th)
            bristle(body, p, n, (0, -1, 0), 0.05, 0.006, CUT, C_BRISTLE, n=3, k=2)
    # abdomen: a row of hairs along each tergite's hind edge
    bounds = TERGITES[sex]
    for i in range(1, len(bounds) - 1 + (1 if female else 0)):
        y = bounds[i] + 0.035
        keys = ABD_KEYS[sex]
        u = (y - keys[0][0]) / (keys[-1][0] - keys[0][0])
        for k in range(15):
            th = math.pi / 2 + (k - 7) * 0.19
            p, n = surf_frame(abd_f, u, th)
            bristle(body, p, n, (0, -1, -0.2), 0.09, 0.008, CUT, C_BRISTLE, n=3, k=2)

    # halteres
    for sx in (-1, 1):
        a, b = Vector((sx * 0.30, -0.27, 0.86)), Vector((sx * 0.44, -0.40, 0.80))
        capsule(body, a, b, lambda t: 0.02, 8, 8, LEGM, C_HALTERE)
        capsule(body, b - (b - a).normalized() * 0.02, b + (b - a).normalized() * 0.07,
                lambda t: 0.042 * math.sin(math.pi * (0.15 + 0.7 * t)), 12, 10, LEGM, srgb(196, 166, 112))

    # ─ legs ─
    LEGS = {  # coxa base, coxa end, trochanter end, knee, tibia end, tarsus tip; radii
        "front": ([(0.10, 0.52, 0.58), (0.16, 0.66, 0.38), (0.20, 0.70, 0.35), (0.40, 0.90, 0.56),
                   (0.49, 1.02, 0.08), (0.56, 1.38, 0.025)], (0.075, 0.05, 0.056, 0.037, 0.032)),
        "mid": ([(0.20, 0.14, 0.50), (0.28, 0.13, 0.37), (0.32, 0.12, 0.35), (0.72, 0.14, 0.62),
                 (0.93, 0.10, 0.08), (1.28, -0.03, 0.025)], (0.062, 0.045, 0.052, 0.035, 0.030)),
        "hind": ([(0.18, -0.12, 0.52), (0.27, -0.18, 0.40), (0.31, -0.21, 0.38), (0.62, -0.50, 0.63),
                  (0.78, -0.86, 0.08), (0.95, -1.22, 0.025)], (0.066, 0.048, 0.056, 0.037, 0.031)),
    }

    def leg(mb, pair, sx):
        J, (rc, rt, rf, rti, rta) = LEGS[pair]
        J = [Vector((sx * x, y, z)) for x, y, z in J]
        col_leg = C_LEG
        capsule(mb, J[0], J[1], lambda t: rc * (0.9 + 0.2 * math.sin(math.pi * t)), 14, 12, LEGM, col_leg)
        capsule(mb, J[1], J[2], lambda t: rt, 12, 8, LEGM, col_leg)
        capsule(mb, J[2], J[3], lambda t: rf * (0.78 + 0.32 * math.sin(math.pi * t) ** 0.7), 14, 14, LEGM, col_leg)
        capsule(mb, J[3], J[4], lambda t: rti * (0.8 + 0.25 * t), 12, 14, LEGM, col_leg)
        # five tarsomeres, the first the longest, arching down onto the surface
        fr = [0.0, 0.40, 0.57, 0.71, 0.83, 1.0]
        tar = []
        for k, f in enumerate(fr):
            p = J[4].lerp(J[5], f)
            p.z = J[4].z + (J[5].z - J[4].z) * smooth(0.0, 0.45, f) + 0.012 * math.sin(math.pi * f)
            tar.append(p)
        for k in range(5):
            r0 = rta * (1 - 0.05 * k)
            c = mix(col_leg, C_LEG_DARK, k / 5)
            capsule(mb, tar[k], tar[k + 1], lambda t, r0=r0: r0 * (0.85 + 0.2 * t), 10, 8, LEGM, c, over=0.35)
        # claws and pulvilli
        tip = tar[-1]
        dirv = (tar[-1] - tar[-2]).normalized()
        side = dirv.cross(Vector((0, 0, 1))).normalized()
        for s in (-1, 1):
            p0 = tip + side * s * 0.012
            pts = bezier(p0, p0 + dirv * 0.05 + side * s * 0.01, p0 + dirv * 0.06 + Vector((0, 0, -0.03)), 4)
            tube(mb, pts, [0.009, 0.008, 0.006, 0.004, 0.0], 5, LEGM, C_BRISTLE)
        capsule(mb, tip, tip + dirv * 0.035 + Vector((0, 0, -0.008)), lambda t: 0.013, 8, 6, LEGM, srgb(196, 170, 120))
        # rows of spines on femur and tibia
        for (a, b, r, cnt) in ((J[2], J[3], rf, 7), (J[3], J[4], rti, 7)):
            d = (b - a)
            n1, n2 = perp_frame(d)
            for row, ang in enumerate((0.6, 2.7, 4.8)):
                for k in range(cnt):
                    t = 0.15 + 0.75 * (k + 0.5 * (row % 2)) / cnt
                    out = n1 * math.cos(ang) + n2 * math.sin(ang)
                    root_p = a + d * t + out * r * 0.95
                    bristle(mb, root_p, out, d.normalized() + out * 0.6, 0.065, 0.0045, LEGM, C_BRISTLE, n=3, k=2)
        # tarsal hairs underneath
        for k in range(4):
            a, b = tar[k], tar[k + 1]
            d = b - a
            for s in (-1, 1):
                out = (side * s * 0.8 + Vector((0, 0, -0.4))).normalized()
                bristle(mb, a + d * 0.6 + out * rta * 0.9, out, d.normalized(), 0.045, 0.005, LEGM, C_BRISTLE, n=3, k=2)
        if pair == "front" and not female:
            # sex comb: a transverse row of thick black teeth on the basitarsus
            a, b = tar[0], tar[1]
            d = b - a
            fwd = Vector((sx * 0.2, 1, 0)).normalized()
            n_out = (side * -sx * 0.3 + Vector((0, 0, -0.9))).normalized()
            for k in range(11):
                t = 0.35 + 0.6 * k / 10
                base = a + d * t + n_out * rta * 0.85
                bristle(mb, base, n_out, fwd.cross(d).normalized() * -sx + n_out * 0.3, 0.05, 0.011,
                        LEGM, srgb(10, 7, 5), n=4, k=2)
        return J[0]

    front = {}
    for sx in (-1, 1):
        for pair in ("mid", "hind"):
            leg(body, pair, sx)
        mb = MB()
        origin = leg(mb, "front", sx)
        front[sx] = (mb, origin)

    body_ob = body.build("body")
    body_ob.parent = root
    for sx, (mb, origin) in front.items():
        ob = mb.build("leg_front_" + ("L" if sx < 0 else "R"), origin)
        ob.parent = root

    # ─ head ─
    hd = MB()
    loft(hd, ellipsoid_f(HEAD_C, head_semi), 40, 44, CUT, head_colour)
    EYE_C, EYE_S = (0.215, 0.85, 0.975), (0.19, 0.245, 0.31)
    for sx in (-1, 1):
        rot = (Matrix.Rotation(math.radians(-sx * 14), 3, "Z") @ Matrix.Rotation(math.radians(sx * 10), 3, "Y"))
        c = Vector((sx * EYE_C[0], EYE_C[1], EYE_C[2]))
        # pole pointing outwards: u runs from the inside (-X local) to the outside (+X local)
        flip = Matrix.Scale(-1, 3, Vector((1, 0, 0))) if sx < 0 else Matrix.Identity(3)
        R = rot @ flip

        def euv(u, th, p, c=c, R=R):
            q = R.inverted() @ (p - c)
            return (0.5 + 0.5 * q.y / EYE_S[1], 0.5 + 0.5 * q.z / EYE_S[2])

        loft(hd, ellipsoid_f(c, EYE_S, R), 30, 40, EYE, lambda u, th, p: (1, 1, 1, 1), euv)

    # ocelli
    for d in ((0, 0.02, 1), (-0.12, -0.14, 1), (0.12, -0.14, 1)):
        p, n = ellipsoid_point(HEAD_C, head_semi, d)
        capsule(hd, p - n * 0.02, p + n * 0.012, lambda t: 0.022, 10, 6, CUT, C_OCELLUS)
    # head bristles: (direction on the head, lean, length)
    for sx in (-1, 1):
        for d, lean, ln in (((0.36, 0.55, 0.76), (0.1, -0.6, 1), 0.13),     # orbitals
                            ((0.38, 0.30, 0.87), (0.15, -1, 0.6), 0.16),
                            ((0.40, 0.05, 0.92), (0.1, -1, 0.4), 0.13),
                            ((0.30, -0.45, 0.85), (-0.2, -1, 0.6), 0.2),    # inner vertical
                            ((0.55, -0.55, 0.62), (0.5, -1, 0.3), 0.18),    # outer vertical
                            ((0.10, -0.08, 1.0), (0.4, 0.8, 0.7), 0.15),    # ocellar
                            ((0.10, -0.75, 0.66), (-0.5, -1, 0.3), 0.12),   # postvertical
                            ((0.30, 0.85, -0.45), (0.2, 1, -0.4), 0.15),    # vibrissa
                            ((0.22, 0.9, -0.36), (0.1, 1, -0.3), 0.08)):
            p, n = ellipsoid_point(HEAD_C, head_semi, (sx * d[0], d[1], d[2]))
            bristle(hd, p, n, (sx * lean[0], lean[1], lean[2]), ln, 0.012, CUT, C_BRISTLE)
    # antennae: scape, pedicel, the oval third segment, the plumose arista
    for sx in (-1, 1):
        base = Vector((sx * 0.075, 0.985, 1.02))
        a1 = base + Vector((sx * 0.02, 0.04, 0.0))
        capsule(hd, base, a1, lambda t: 0.034, 10, 6, CUT, C_FRONS)
        a2 = a1 + Vector((sx * 0.015, 0.05, -0.03))
        capsule(hd, a1, a2, lambda t: 0.036 * (0.8 + 0.3 * t), 12, 8, CUT, srgb(160, 96, 46))
        a3 = a2 + Vector((sx * 0.02, 0.05, -0.17))
        capsule(hd, a2, a3, lambda t: 0.047 * math.sin(math.pi * (0.1 + 0.8 * t)) ** 0.6, 14, 12, CUT, srgb(176, 106, 50))
        ar0 = a2.lerp(a3, 0.3) + Vector((sx * 0.045, 0.02, 0.0))
        ar1 = ar0 + Vector((sx * 0.10, 0.12, 0.08))
        ar2 = ar1 + Vector((sx * 0.06, 0.13, 0.05))
        shaft = bezier(ar0, ar1, ar2, 6)
        tube(hd, shaft, [0.012, 0.010, 0.008, 0.006, 0.005, 0.003, 0.0], 5, CUT, C_BRISTLE)
        for k in range(1, 6):
            p = shaft[k]
            d = (shaft[k + 1] - shaft[k - 1]).normalized()
            up = Vector((0, 0, 1)) - d * d.z
            for s, ln in ((1, 0.09 - 0.01 * k), (-1, 0.05 - 0.006 * k)):
                if s < 0 and k > 3:
                    continue
                tip = p + (up.normalized() * s * 0.8 + d * 0.6).normalized() * ln
                tube(hd, [p, p.lerp(tip, 0.5), tip], [0.004, 0.003, 0.0], 3, CUT, C_BRISTLE)
    # proboscis, folded under the head, and its labellum
    capsule(hd, Vector((0, 0.84, 0.72)), Vector((0, 0.90, 0.60)), lambda t: 0.075, 14, 10, CUT, srgb(200, 160, 105))
    for s in (-1, 1):
        capsule(hd, Vector((s * 0.035, 0.88, 0.58)), Vector((s * 0.05, 0.96, 0.56)),
                lambda t: 0.045, 12, 8, CUT, srgb(214, 184, 132))
    head_ob = hd.build("head", (0.0, 0.66, 0.92), uv=True)
    head_ob.parent = root

    # ─ wings ─
    L = 1.85 if female else 1.72
    A_KEYS = [(0.0, 0.015), (0.1, 0.05), (0.3, 0.10), (0.5, 0.14), (0.7, 0.165), (0.82, 0.168),
              (0.9, 0.155), (0.96, 0.12), (0.99, 0.07), (1.0, 0.03)]
    P_KEYS = [(0.0, -0.005), (0.05, -0.05), (0.09, -0.095), (0.115, -0.09), (0.14, -0.13), (0.2, -0.18),
              (0.3, -0.24), (0.45, -0.29), (0.6, -0.305), (0.72, -0.285), (0.83, -0.235), (0.91, -0.17),
              (0.96, -0.105), (0.99, -0.04), (1.0, 0.03)]
    VEINS = [  # (points in wing units, radius)
        ([(0.0, 0.01), (0.1, 0.048), (0.3, 0.098), (0.5, 0.138), (0.7, 0.162), (0.82, 0.165), (0.9, 0.152),
          (0.96, 0.117), (0.99, 0.068), (0.995, 0.02)], 0.013),                                 # costa
        ([(0.02, 0.005), (0.18, 0.05), (0.33, 0.092), (0.42, 0.11)], 0.0095),                    # L1
        ([(0.12, 0.0), (0.3, 0.035), (0.5, 0.08), (0.7, 0.125), (0.85, 0.16)], 0.0085),           # L2
        ([(0.04, -0.01), (0.25, 0.0), (0.5, 0.02), (0.75, 0.035), (0.97, 0.045)], 0.0085),        # L3
        ([(0.04, -0.025), (0.25, -0.055), (0.5, -0.08), (0.75, -0.085), (0.975, -0.07)], 0.0085), # L4
        ([(0.04, -0.04), (0.2, -0.1), (0.4, -0.16), (0.6, -0.205), (0.78, -0.255)], 0.0085),     # L5
        ([(0.04, -0.06), (0.14, -0.12), (0.26, -0.2)], 0.007),                                  # L6
        ([(0.40, 0.012), (0.40, -0.072)], 0.007),                                                # anterior crossvein
        ([(0.58, -0.083), (0.625, -0.20)], 0.007),                                              # posterior crossvein
    ]
    akeys = ABD_KEYS[sex]
    ytip = akeys[0][0]

    def envelope(x, y):
        """The height a folded wing lies at: just over the abdomen's back, sloping on past its tip."""
        yy = max(y, ytip + 0.12)
        w, zt, zb = interp(akeys, yy)
        zm = (zt + zb) / 2
        t = min(1.0, abs(x) / (max(w, 0.36) + 0.22))
        z = zm + (zt - zm) * (1 - t ** 2.2) ** (1 / 2.2)
        if y < ytip + 0.12:
            z -= 0.25 * (ytip + 0.12 - y)
        return z

    ang = math.radians(1.5)
    for sx in (-1, 1):
        hinge = Vector((sx * 0.26, -0.12, 1.12))
        D = Vector((sx * math.sin(ang), -math.cos(ang), 0))
        A = Vector((sx * math.cos(ang), math.sin(ang), 0))
        clear = 0.075 if sx > 0 else 0.035       # the right wing lies over the left

        def W(u, v, lift=0.0, D=D, A=A, hinge=hinge, clear=clear):
            ul, vl = u * L, v * L
            p = hinge + D * ul + A * vl
            k = smooth(0.0, 0.5, ul)
            p.z = hinge.z * (1 - k) + (envelope(p.x, p.y) + clear) * k + lift
            return p

        wm = MB()
        nu, nv = 70, 16
        R, C = [], []
        for i in range(nu + 1):
            u = (1 - math.cos(math.pi * i / nu)) / 2 * 0.998 + 0.001
            a_, = interp(A_KEYS, u)
            p_, = interp(P_KEYS, u)
            R.append([W(u, p_ + (a_ - p_) * j / nv) for j in range(nv + 1)])
            C.append([(1, 1, 1, 1)] * (nv + 1))
        wm.rings(R, C, WING, closed=False)
        for pts, r in VEINS:
            dense = []
            for k in range(len(pts) - 1):
                for s in range(3):
                    t = s / 3
                    dense.append((pts[k][0] + (pts[k + 1][0] - pts[k][0]) * t, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * t))
            dense.append(pts[-1])
            path = [W(u, v, 0.004) for u, v in dense]
            rad = [r * (1 - 0.35 * k / len(path)) for k in range(len(path))]
            tube(wm, path, rad, 5, VEIN, (1, 1, 1, 1))
        # the marginal fringe along the hind edge
        for i in range(8, nu - 2, 2):
            u = (1 - math.cos(math.pi * i / nu)) / 2
            p_, = interp(P_KEYS, u)
            a = W(u, p_)
            b = W(u, p_ - 0.02, -0.002)
            tube(wm, [a, b], [0.004, 0.0], 3, VEIN, (1, 1, 1, 1))
        wob = wm.build("wing_" + ("L" if sx < 0 else "R"), hinge)
        wob.parent = root
    return root


# ── the larva ────────────────────────────────────────────────────────────────
# Metres, head at +Y, belly on z = 0. 12 segments: head, T1-T3, A1-A8.
SEG_LEN = [0.055, 0.075, 0.075, 0.08] + [0.083] * 7 + [0.134]
_tot = sum(SEG_LEN)
SEG_B = [0.0]
for _l in SEG_LEN:
    SEG_B.append(SEG_B[-1] + _l / _tot)
R_KEYS = [(0.0, 0.10), (0.02, 0.30), (0.055, 0.50), (0.13, 0.72), (0.21, 0.86), (0.30, 0.95), (0.45, 1.0),
          (0.7, 1.0), (0.85, 0.97), (0.92, 0.90), (0.965, 0.78), (0.99, 0.55), (1.0, 0.0)]
LR = 0.031           # max radius
C_CUT = srgb(246, 240, 222)


def larva_R(s):
    r = interp(R_KEYS, s)[0] * LR
    for b in SEG_B[1:-1]:
        r *= 1 - 0.038 * math.exp(-((s - b) / 0.011) ** 2)
    return max(r, 0.0)


def larva_zc(s):
    return 0.74 * larva_R(max(s, 0.03)) if s < 0.03 else 0.74 * larva_R(s)


def larva_y(s):
    return LARVA_M / 2 - s * LARVA_M


def larva_f(u, th):
    s = u
    r = larva_R(s) * end_round(u, 14)
    zc = 0.74 * LR * interp(R_KEYS, max(0.03, min(0.97, s)))[0]
    top, bot = 0.96, 0.74
    return Vector((1.04 * r * math.cos(th), larva_y(s), zc + r * math.sin(th) * (top if math.sin(th) > 0 else bot)))


def larva_axis(s):
    zc = 0.74 * LR * interp(R_KEYS, max(0.03, min(0.97, s)))[0]
    return Vector((0, larva_y(s), zc))


def seg_of(s):
    for i in range(12):
        if s < SEG_B[i + 1]:
            return i, (s - SEG_B[i]) / (SEG_B[i + 1] - SEG_B[i])
    return 11, 1.0


def larva_colour(u, th, p):
    i, ph = seg_of(u)
    c = C_CUT
    groove = 0.0
    for b in SEG_B[1:-1]:
        groove = max(groove, math.exp(-((u - b) / 0.006) ** 2))
    c = mix(c, srgb(226, 214, 186), 0.6 * groove)
    ventral = smooth(-0.3, -0.75, math.sin(th))
    if i >= 1 and ph < 0.28:           # denticle belts, front of each segment, underneath
        c = mix(c, srgb(176, 150, 110), 0.55 * ventral * smooth(0.0, 0.05, ph) * (1 - smooth(0.2, 0.28, ph)))
    if u < 0.04:
        c = mix(c, srgb(220, 200, 170), 1 - u / 0.04)
    return c


def build_larva():
    CUT = vc_material("larva_cuticle", rough=0.22, spec=0.5, alpha=0.36, cull=True, clearcoat=0.15)
    ORG = vc_material("larva_organs", rough=0.5, spec=0.3)
    TRACH = flat_material("trachea", (0.86, 0.88, 0.92, 1), rough=0.12, metal=0.7)
    DARK = vc_material("sclerite", rough=0.3, spec=0.6)

    mb = MB()
    loft(mb, larva_f, 190, 30, CUT, larva_colour)

    # denticle belts: at the front of each segment, underneath, rows of fine teeth lying on the cuticle
    for i in range(1, 12):
        s0, s1 = SEG_B[i], SEG_B[i + 1]
        for row in range(4):
            sa = s0 + (s1 - s0) * (0.05 + 0.055 * row)
            sb = sa + (s1 - s0) * 0.03
            ths = [-math.pi / 2 + (k - 12) * 0.075 for k in range(25)]
            R, C = [], []
            for sv in (sa, sb):
                ring = []
                for th in ths:
                    p, n = surf_frame(larva_f, sv, th)
                    ring.append(p + n * 0.00035)
                R.append(ring)
                C.append([mix(srgb(150, 118, 76), srgb(200, 178, 140), abs(k - 12) / 12) for k in range(25)])
            mb.rings(R, C, DARK, closed=False)

    # tracheal trunks: two silvery dorsal tubes, anterior to posterior spiracle, with segmental branches
    for sx in (-1, 1):
        path, rad = [], []
        for k in range(80):
            s = 0.11 + (0.985 - 0.11) * k / 79
            r = larva_R(s)
            a = larva_axis(s)
            wob = 0.03 * math.sin(s * 80)
            path.append(a + Vector((sx * r * (0.52 + wob), 0, r * 0.80)))
            rad.append(r * 0.055 * (1 - 0.3 * smooth(0.9, 0.985, s)))
        # rise to the anterior spiracle, run into the posterior one
        tube(mb, path, rad, 8, TRACH, (1, 1, 1, 1))
        for i in range(2, 12):
            s = (SEG_B[i] + SEG_B[i + 1]) / 2
            r, a = larva_R(s), larva_axis(s)
            p0 = a + Vector((sx * r * 0.52, 0, r * 0.80))
            p1 = a + Vector((sx * r * 0.78, -0.003, r * 0.55))
            p2 = a + Vector((sx * r * 0.93, -0.005, r * 0.12))
            tube(mb, bezier(p0, p1, p2, 4), [r * 0.022] * 4 + [0.0], 4, TRACH, (1, 1, 1, 1))
        # dorsal anastomosis to the other side, once per segment
    for i in range(3, 11, 2):
        s = SEG_B[i]
        r, a = larva_R(s), larva_axis(s)
        pts = [a + Vector((x * r * 0.52, 0, r * (0.80 + 0.1 * (1 - x * x)))) for x in (-1, -0.5, 0, 0.5, 1)]
        tube(mb, pts, [r * 0.03] * 5, 5, TRACH, (1, 1, 1, 1))

    # The gut: a meandering tube through the middle. It is not modelled as a tube (it would be
    # hidden in the fat body); it is painted onto the fat body wherever it runs close under it,
    # which is how a feeding larva's gut shows: soft yellow-brown loops through milky tissue.
    gut = []
    for k in range(400):
        s = 0.1 + 0.84 * k / 399
        r, a = larva_R(s), larva_axis(s)
        out = 0.3 + 0.58 * smooth(0.14, 0.3, s) * (1 - smooth(0.85, 0.94, s))
        gx = math.sin(s * 23 + 0.7) * 0.8 + 0.2 * math.sin(s * 57)
        gz = math.sin(s * 31 + 1.9) * 0.7
        gut.append((a + Vector((1.04 * r * out * gx, 0, 0.8 * r * out * gz)), s))
    G = np.array([tuple(p) for p, _ in gut])
    GS = np.array([sv for _, sv in gut])

    def fat_colour(u, th, p):
        sf = 0.12 + 0.87 * u
        r = larva_R(sf) + 1e-6
        d = np.sqrt(((G - np.array(tuple(p))) ** 2).sum(1)).min() / r
        g = math.exp(-(d / 0.42) ** 2)
        food = mix(srgb(196, 142, 58), srgb(128, 84, 34), smooth(0.3, 0.8, sf))
        base = mix(srgb(242, 236, 218), srgb(232, 222, 196), 0.5 + 0.5 * math.sin(sf * 90 + th * 2))
        return mix(base, food, min(1.0, 1.1 * g))

    def fat_f(u, th):
        sf = 0.12 + 0.87 * u
        a = larva_axis(sf)
        return a + (larva_f(sf, th) - a) * 0.92 * end_round(u, 3)

    loft(mb, fat_f, 110, 28, ORG, fat_colour)

    # the cephalopharyngeal skeleton: black mouth hooks, and the H-piece and pharyngeal
    # sclerites behind them, dark through the cuticle
    tipa = larva_axis(0.0)
    for sx in (-1, 1):
        p0 = larva_axis(0.035) + Vector((sx * 0.0012, 0, -0.0005))
        p1 = tipa + Vector((sx * 0.0016, 0.006, 0.0008))
        p2 = tipa + Vector((sx * 0.0014, 0.0085, -0.0045))
        tube(mb, bezier(p0, p1, p2, 7), [0.0021, 0.0021, 0.0019, 0.0016, 0.0012, 0.0008, 0.0004, 0.0], 6, DARK, srgb(10, 8, 6))
        h0 = larva_axis(0.035) + Vector((sx * 0.0016, 0, 0))
        h1 = larva_axis(0.06) + Vector((sx * 0.0018, 0, -0.0005))
        capsule(mb, h0, h1, lambda t: 0.0017, 6, 6, DARK, srgb(14, 10, 8))
        # dorsal and ventral cornua of the pharyngeal sclerite
        for dz, ln in ((0.006, 0.075), (-0.002, 0.085)):
            q0 = h1
            q2 = larva_axis(0.06 + ln * 0.8) + Vector((sx * 0.003, 0, dz))
            q1 = q0.lerp(q2, 0.5) + Vector((0, 0, dz * 0.4))
            pts = bezier(q0, q1, q2, 8)
            rad = [0.0024 * (1 - 0.6 * k / 8) for k in range(9)]
            rad[-1] = 0.0
            tube(mb, pts, rad, 6, DARK, lambda t: mix(srgb(16, 12, 9), srgb(70, 52, 36), t))

    # posterior spiracles: two stalks on the blunt end, dark spiracular plates
    for sx in (-1, 1):
        s = 0.975
        p, n = surf_frame(larva_f, s, math.pi / 2 - sx * 0.55)
        d = (n + Vector((0, -0.8, 0.25))).normalized()
        capsule(mb, p - d * 0.001, p + d * 0.006, lambda t: 0.0032 * (1 - 0.2 * t), 10, 8, DARK, srgb(196, 140, 60))
        capsule(mb, p + d * 0.0058, p + d * 0.0072, lambda t: 0.0034, 10, 4, DARK, srgb(60, 38, 20))
    # anterior spiracles: small fans behind the head, on T1
    for sx in (-1, 1):
        s = SEG_B[2] - 0.012
        p, n = surf_frame(larva_f, s, math.pi / 2 - sx * 0.95)
        stalk = p + n * 0.003
        capsule(mb, p - n * 0.001, stalk, lambda t: 0.0014, 8, 6, DARK, srgb(214, 160, 80))
        side = Vector((0, 1, 0)).cross(n).normalized()
        for k in range(8):
            a = (k - 3.5) * 0.28
            tip = stalk + (n * math.cos(a) + side * math.sin(a)) * 0.0028
            capsule(mb, stalk, tip, lambda t: 0.0006, 5, 4, DARK, srgb(206, 150, 70))

    # the rig: bones run tail to head, spine_11 the root, so bending spine_0..2 swings the head
    bpy.ops.object.select_all(action="DESELECT")
    arm = bpy.data.armatures.new("rig")
    rig = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    prev = None
    centres = []
    for i in range(11, -1, -1):
        b = arm.edit_bones.new(f"spine_{i}")
        s_tail, s_head = SEG_B[i + 1], SEG_B[i]
        b.head = larva_axis(s_tail)
        b.tail = larva_axis(s_head)
        b.roll = 0.0
        if prev is not None:
            b.parent = prev
            b.use_connect = True
        prev = b
    bpy.ops.object.mode_set(mode="OBJECT")
    for i in range(12):
        centres.append((SEG_B[i] + SEG_B[i + 1]) / 2)

    ob = mb.build("larva")
    ob.parent = rig
    mod = ob.modifiers.new("rig", "ARMATURE")
    mod.object = rig
    vg = [ob.vertex_groups.new(name=f"spine_{i}") for i in range(12)]
    for vi, co in enumerate(mb.co):
        s = clamp((LARVA_M / 2 - co[1]) / LARVA_M)
        if s <= centres[0]:
            vg[0].add([vi], 1.0, "REPLACE")
            continue
        if s >= centres[-1]:
            vg[11].add([vi], 1.0, "REPLACE")
            continue
        for i in range(11):
            if centres[i] <= s <= centres[i + 1]:
                t = smooth(0, 1, (s - centres[i]) / (centres[i + 1] - centres[i]))
                vg[i].add([vi], 1 - t, "REPLACE")
                vg[i + 1].add([vi], t, "REPLACE")
                break
    return rig


# ── export, previews ─────────────────────────────────────────────────────────
def world_bbox(objs):
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    bpy.context.view_layer.update()
    for ob in objs:
        if ob.type != "MESH":
            continue
        mw = ob.matrix_world
        for v in ob.data.vertices:
            p = mw @ v.co
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return lo, hi


def export(path):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_apply=True, export_yup=True,
                              export_colors=True, export_normals=True, export_texcoords=True,
                              export_skins=True, export_animations=False, export_cameras=False,
                              export_lights=False, export_extras=False, export_def_bones=False)
    print("exported", path, os.path.getsize(path), "bytes")


def stage_lights(size):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    w, h = (int(v) for v in args.res.split("x"))
    scene.render.resolution_x, scene.render.resolution_y = w, h
    scene.eevee.taa_render_samples = args.samples
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = size * 0.2
    scene.eevee.use_soft_shadows = True
    scene.eevee.use_ssr = True
    scene.eevee.shadow_cube_size = "2048"
    scene.eevee.shadow_cascade_size = "2048"
    scene.view_settings.look = "Medium High Contrast"
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.20, 0.22, 0.25, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45
    scene.world = world
    bpy.ops.mesh.primitive_plane_add(size=size * 40, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "_ground"
    gm = flat_material("_ground", (0.42, 0.42, 0.44, 1), rough=0.7)
    ground.data.materials.append(gm)
    for loc, energy, sz, col in (((size * 2, -size * 1.5, size * 3), 440, size * 2, (1, 0.96, 0.9)),
                                 ((-size * 3, size * 1.0, size * 1.5), 170, size * 3, (0.8, 0.88, 1.0)),
                                 ((0, size * 3, size * 2), 220, size * 1.5, (1, 1, 1))):
        bpy.ops.object.light_add(type="AREA", location=loc)
        L = bpy.context.object
        L.name = "_light"
        L.data.energy = energy * size * size
        L.data.size = sz
        L.data.color = col
        d = Vector((0, 0, size * 0.2)) - Vector(loc)
        L.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def render_views(tag, lo, hi, views=("front34", "side", "top"), extra=""):
    scene = bpy.context.scene
    centre = (lo + hi) / 2
    size = max((hi - lo).x, (hi - lo).y, (hi - lo).z)
    cam_data = bpy.data.cameras.new("_cam")
    cam_data.lens = 70
    cam = bpy.data.objects.new("_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    fov = 2 * math.atan(36 / 2 / cam_data.lens)
    dist = size * 0.62 / math.tan(fov / 2) + size * 0.5
    dirs = {"front34": Vector((0.75, 1.0, 0.55)), "side": Vector((-1.0, 0.02, 0.12)),
            "top": Vector((0.0, -0.0001, 1.0)), "rear34": Vector((-0.8, -1.0, 0.7)),
            "front": Vector((0.0, 1.0, 0.18))}
    for v in views:
        d = dirs[v].normalized()
        cam.location = centre + d * dist
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y" if v != "top" else "Y").to_euler()
        if v == "top":
            cam.rotation_euler = (0, 0, 0)
        scene.render.filepath = os.path.join(PREV, f"{tag}_{v}{extra}.png")
        bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)


def closeup(tag, target, dist, d):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("_cam")
    cam_data.lens = 70
    cam = bpy.data.objects.new("_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    d = d.normalized()
    cam.location = target + d * dist * 2.2
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(PREV, f"{tag}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)


def finish_adult(root, sex):
    """Scale mm to stage metres; origin at the centre of where the feet stand."""
    scale = FLY_BODY_M / 2.66 * (1.0 if sex == "female" else MALE_K)
    root.scale = (scale,) * 3
    bpy.context.view_layer.update()
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo, hi = world_bbox(objs)
    root.location = (-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)
    bpy.context.view_layer.update()
    return world_bbox(objs)


def run(species):
    reset_scene()
    if species == "drosophila_larva":
        rig = build_larva()
        objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        lo, hi = world_bbox(objs)
    else:
        sex = species.split("_")[1]
        root = build_fly(sex)
        lo, hi = finish_adult(root, sex)
    print(species, "bbox", tuple(round(x, 4) for x in lo), tuple(round(x, 4) for x in hi))
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in bpy.context.scene.objects if o.type == "MESH")
    print(species, "triangles", tris)
    export(os.path.join(OUT, species + ".glb"))
    if not args.no_previews:
        size = max((hi - lo).x, (hi - lo).y)
        stage_lights(size)
        render_views(species, lo, hi)
        if species == "drosophila_larva":
            # prove the skin: bend it and look
            for i, pb in enumerate(rig.pose.bones):
                k = int(pb.name.split("_")[1])
                pb.rotation_mode = "XYZ"
                pb.rotation_euler = (0, 0, 0.16 * math.sin(k * 0.6))
            bpy.context.view_layer.update()
            render_views(species, lo, hi, views=("top",), extra="_bent")
            closeup(species + "_head", Vector((0, 0.12, 0.012)), 0.035, Vector((0.9, 0.6, 0.35)))
        elif species == "drosophila_male":
            closeup(species + "_comb", Vector((-0.06, 0.17, 0.02)), 0.08, Vector((-0.7, 0.9, 0.2)))
        else:
            closeup(species + "_head", Vector((0, 0.15, 0.1)), 0.14, Vector((0.5, 1.0, 0.3)))


def contact():
    reset_scene()
    xs = {"drosophila_female": 0.40, "drosophila_male": 0.0, "drosophila_larva": -0.40}
    for sp, x in xs.items():
        path = os.path.join(OUT, sp + ".glb")
        if not os.path.exists(path):
            continue
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.context.scene.objects if o not in before]
        for o in new:
            if o.parent is None:
                o.location.x += x
                o.rotation_mode = "XYZ"
                o.rotation_euler.z += math.radians(28)
    bpy.context.view_layer.update()
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo, hi = world_bbox(objs)
    size = max((hi - lo).x, (hi - lo).y) * 0.5
    stage_lights(size)
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = 1800, 760
    cam_data = bpy.data.cameras.new("_cam")
    cam_data.lens = 60
    cam = bpy.data.objects.new("_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    centre = (lo + hi) / 2
    d = Vector((0.0, 1.0, 0.62)).normalized()
    cam.location = centre + d * 1.9
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = os.path.join(PREV, "contact.png")
    bpy.ops.render.render(write_still=True)


ALL = ["drosophila_female", "drosophila_male", "drosophila_larva"]
todo = [s for s in args.only.split(",") if s] or ALL
for sp in todo:
    run(sp)
if not args.no_previews and not args.no_contact and not args.only:
    contact()
print("done")

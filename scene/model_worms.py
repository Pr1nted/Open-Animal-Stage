"""The worms and the sea squirt larva: c_elegans_herm, c_elegans_male, ciona_larva.

Every surface is built analytically (swept tubes, ellipsoids, sheets) at the
density it will be shown at, smooth shaded, then skinned to one armature `rig`
whose bones point straight up, so a bone's local Y is the world's up axis and a
rotation about it bends the body sideways (docs/models.md).

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        --python scene/model_worms.py -- --out web/models --previews data/raw/previews/worms

Axes while building (Blender): +Z up, the animal faces +Y. The glTF exporter's
+Y-up conversion turns that into +Y up, facing -Z.

The worm lies on its side, as it does on agar: dorsal is +X, ventral -X, and the
lateral lines (with the alae) run along the top and the bottom. Its
dorso-ventral bends are therefore the sideways bends the page drives.
"""
import argparse
import json
import math
import os
import struct
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", default="web/models")
ap.add_argument("--previews", default="data/raw/previews/worms")
ap.add_argument("--only", default="", help="comma-separated species ids (default: all three)")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--res", default="1400x600")
ap.add_argument("--samples", type=int, default=48)
args = ap.parse_args(argv)

TAU = 2 * math.pi
SPECIES = ["c_elegans_herm", "c_elegans_male", "ciona_larva"]
TMP = tempfile.mkdtemp(prefix="oas_worms_")


# ── small maths ─────────────────────────────────────────────────────────────
def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def gauss(x, mu, sig):
    return np.exp(-((np.asarray(x, float) - mu) / sig) ** 2)


class Noise:
    """Sum of random plane waves: smooth, isotropic, roughly in [-1, 1]."""

    def __init__(self, seed, freq, n=14, spread=2.2):
        rng = np.random.default_rng(seed)
        d = rng.normal(size=(n, 3))
        d /= np.linalg.norm(d, axis=1)[:, None]
        self.k = d * (freq * rng.uniform(1.0, spread, size=n))[:, None]
        self.ph = rng.uniform(0, TAU, n)
        self.a = 1.5 / math.sqrt(n)

    def __call__(self, P):
        return np.sin(np.asarray(P) @ self.k.T + self.ph).sum(1) * self.a


def bspline(x):
    """Uniform cubic B-spline basis, support [-2, 2], partitions unity."""
    ax = np.abs(x)
    return np.where(ax < 1, 2 / 3 - ax ** 2 + ax ** 3 / 2, np.where(ax < 2, (2 - ax) ** 3 / 6, 0.0))


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


# ── meshes ──────────────────────────────────────────────────────────────────
def grid_tube(rings, pole0, pole1, wrap_dup):
    """rings: (nr, ncol, 3). wrap_dup: the last column duplicates the first (a UV seam)."""
    nr, ncol, _ = rings.shape
    n = ncol - 1 if wrap_dup else ncol
    V = np.vstack([pole0[None], rings.reshape(-1, 3), pole1[None]])
    idx = lambda k, j: 1 + k * ncol + (j if wrap_dup else j % ncol)
    F = []
    for j in range(n):
        F.append((0, idx(0, j + 1), idx(0, j)))
    for k in range(nr - 1):
        for j in range(n):
            F.append((idx(k, j), idx(k, j + 1), idx(k + 1, j + 1), idx(k + 1, j)))
    last = len(V) - 1
    for j in range(n):
        F.append((last, idx(nr - 1, j), idx(nr - 1, j + 1)))
    return V, F


def frames(P, ref=(0, 0, 1)):
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    ref = np.array(ref, float)
    N = np.zeros_like(P)
    n0 = ref - T[0] * T[0].dot(ref)
    if np.linalg.norm(n0) < 1e-6:
        n0 = np.array([1.0, 0, 0]) - T[0] * T[0][0]
    N[0] = n0 / np.linalg.norm(n0)
    for k in range(1, len(P)):
        nk = N[k - 1] - T[k] * T[k].dot(N[k - 1])
        N[k] = nk / np.linalg.norm(nk)
    B = np.cross(T, N)
    return T, N, B


def sweep(P, R, n=16, ref=(0, 0, 1)):
    """A closed tube along the path P (m, 3). R: (m,) or (m, 2) = (horizontal, vertical)
    half-widths. The first and last path points become poles, so R there is unused and the
    profile should close towards them. Returns V, F and per-vertex (t along, theta)."""
    P = np.asarray(P, float)
    R = np.asarray(R, float)
    if R.ndim == 1:
        R = np.stack([R, R], 1)
    T, N, B = frames(P, ref)
    th = TAU * np.arange(n) / n
    c, s = np.cos(th), np.sin(th)
    rings = (P[1:-1, None, :] + R[1:-1, 0, None, None] * c[None, :, None] * B[1:-1, None, :]
             + R[1:-1, 1, None, None] * s[None, :, None] * N[1:-1, None, :])
    V, F = grid_tube(rings, P[0], P[-1], wrap_dup=False)
    m = len(P)
    t = np.concatenate([[0.0], np.repeat(np.arange(1, m - 1) / (m - 1), n), [1.0]])
    theta = np.concatenate([[0.0], np.tile(th, m - 2), [0.0]])
    return V, F, t, theta


def rounded(prof, arc, rc0, rc1):
    """Multiply a radius profile by hemispherical caps of radii rc0/rc1 at the two ends."""
    d0 = arc - arc[0]
    d1 = arc[-1] - arc
    cap = lambda d, rc: np.sqrt(np.clip(1 - (1 - np.clip(d / max(rc, 1e-9), 0, 1)) ** 2, 0, 1))
    c = cap(d0, rc0) * cap(d1, rc1)
    prof = np.asarray(prof, float)
    return prof * (c[:, None] if prof.ndim == 2 else c)


def arclen(P):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


def spow(x, e):
    return np.sign(x) * np.abs(x) ** e


def ellipsoid(center, axes, rot=None, nu=24, nv=14, eps=1.0):
    """eps < 1 squares the ellipsoid off along its local z (a superellipsoid: a coin, a cell)."""
    ph = np.pi * np.arange(1, nv) / nv
    th = TAU * np.arange(nu) / nu
    sp, cp = spow(np.sin(ph), eps), spow(np.cos(ph), eps)
    rings = np.stack([sp[:, None] * np.cos(th)[None], sp[:, None] * np.sin(th)[None],
                      cp[:, None] * np.ones_like(th)[None]], -1)
    V, F = grid_tube(rings, np.array([0, 0, 1.0]), np.array([0, 0, -1.0]), wrap_dup=False)
    U = V.copy()                              # unit-sphere coordinates, for colouring
    V = V * np.asarray(axes, float)
    if rot is not None:
        V = V @ np.asarray(rot).T
    return V + np.asarray(center, float), F, U


def add_obj(name, V, F, mat, cols=None, uvs=None, merge=False, closed=True, origin=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(np.asarray(V).tolist(), [], [tuple(int(i) for i in f) for f in F])
    me.update()
    li = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", li)
    if uvs is not None:
        ul = me.uv_layers.new(name="UVMap")
        ul.data.foreach_set("uv", np.asarray(uvs, np.float32)[li].ravel())
    if cols is not None:
        cols = np.clip(np.asarray(cols, float), 0, 1)
        vl = me.vertex_colors.new(name="Col")
        c4 = (cols if cols.shape[1] == 4 else np.hstack([cols, np.ones((len(cols), 1))]))[li]
        vl.data.foreach_set("color", c4.astype(np.float32).ravel())
    bm = bmesh.new()
    bm.from_mesh(me)
    if merge:
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-9)
    if closed:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if origin is not None:
        o = Vector(origin)
        me.transform(Matrix.Translation(-o))
        ob.location = o
    return ob


# ── materials ───────────────────────────────────────────────────────────────
def material(name, color, rough=0.45, alpha=1.0, spec=0.5, vcol=False, normal_img=None,
             normal_strength=1.0, double=False, valpha=False):
    """valpha: the alpha comes from the vertex colours' alpha (three.js honours an RGBA COLOR_0
    when the material uses vertex colours); the RGB of those colours is left white."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular"].default_value = spec
    if vcol:
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        nt.links.new(vc.outputs["Color"], b.inputs["Base Color"])
    if valpha:
        va = nt.nodes.new("ShaderNodeVertexColor")
        va.layer_name = "Col"
        nt.links.new(va.outputs["Alpha"], b.inputs["Alpha"])
        alpha = min(alpha, 0.999)
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
        m.shadow_method = "HASHED"
        m.show_transparent_back = False
    m.use_backface_culling = not double
    if normal_img is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = normal_img
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    m.diffuse_color = (*color, alpha)
    return m


def cuticle_normal_map(annuli_per_tile=4, w=512, h=64, alae=True):
    """Tile of the cuticle: transverse annuli (grooves) along v, and the lateral alae (three
    fine ridges) along u = 0.25 and 0.75, where the annuli are interrupted."""
    u = (np.arange(w) + 0.5) / w
    v = (np.arange(h) + 0.5) / h
    U, Vv = np.meshgrid(u, v)                  # (h, w)
    fr = (Vv * annuli_per_tile) % 1.0
    groove = -np.exp(-((fr - 0.5) / 0.13) ** 2)
    hgt = groove.copy()
    if alae:
        mask = np.zeros_like(U)
        ridges = np.zeros_like(U)
        for uc in (0.25, 0.75):
            du = (U - uc + 0.5) % 1.0 - 0.5
            mask = np.maximum(mask, np.exp(-(du / 0.022) ** 2))
            for off in (-0.011, 0.0, 0.011):
                ridges += np.exp(-((du - off) / 0.0042) ** 2)
        hgt = groove * (1 - mask) + 0.9 * ridges
    gy, gx = np.gradient(hgt)
    k = 1.6
    nx, ny, nz = -gx * k, -gy * k, np.ones_like(hgt)
    ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    rgb = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
    img = bpy.data.images.new("cuticle_normal", w, h, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    px = np.concatenate([rgb, np.ones((h, w, 1))], -1).astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    path = os.path.join(TMP, "cuticle_normal.png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.source = "FILE"
    img.reload()
    return img


# ── rig and skinning ────────────────────────────────────────────────────────
BONE_LEN = 0.008


def make_rig(bones):
    """bones: list of (name, head xyz, parent name or None). Each bone points up (+Z), roll 0:
    local Y = world up, local X = world +X."""
    arm = bpy.data.armatures.new("rig")
    rig = bpy.data.objects.new("rig", arm)
    bpy.context.scene.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, head, parent in bones:
        eb = arm.edit_bones.new(name)
        eb.head = Vector(head)
        eb.tail = Vector(head) + Vector((0, 0, BONE_LEN))
        eb.roll = 0.0
        if parent:
            eb.parent = arm.edit_bones[parent]
            eb.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    for pb in rig.pose.bones:
        pb.rotation_mode = "XYZ"
    return rig


def skin(ob, rig, names, q_of_world, gate=None):
    """Weights from a scalar coordinate q (bone k is centred at q = k + 0.5), a cubic B-spline
    over neighbouring bones, folded at the chain ends. gate(q) -> (nv, nb) optional override."""
    wm = np.array(ob.matrix_world)
    nv = len(ob.data.vertices)
    co = np.empty(nv * 3)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ wm[:3, :3].T + wm[:3, 3]
    q = q_of_world(co)
    nb = len(names)
    W = np.zeros((nv, nb))
    for k in range(-3, nb + 3):
        w = bspline(q - (k + 0.5))
        W[:, min(max(k, 0), nb - 1)] += w
    if gate is not None:
        W = gate(q, W)
    W[W < 1e-3] = 0
    W /= W.sum(1, keepdims=True)
    for k, name in enumerate(names):
        vg = ob.vertex_groups.new(name=name)
        idx = np.nonzero(W[:, k])[0]
        for i in idx:
            vg.add([int(i)], float(W[i, k]), "REPLACE")
    ob.parent = rig
    ob.matrix_parent_inverse = Matrix.Identity(4)
    mod = ob.modifiers.new("rig", "ARMATURE")
    mod.object = rig


def set_pose(rig, angles):
    for name, a in angles.items():
        rig.pose.bones[name].rotation_euler = (0.0, a, 0.0)
    bpy.context.view_layer.update()


def clear_pose(rig):
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()


def wave_angles(names, waves, amp_curv, seg_len, phase=0.0, ramp=None):
    """Relative bone angles for a travelling sine of curvature; the first angle is chosen so the
    body's mean heading stays along the rest axis."""
    n = len(names)
    i = np.arange(n)
    env = np.ones(n) if ramp is None else ramp(i / (n - 1))
    rel = amp_curv * seg_len * env * np.sin(TAU * waves * i / n + phase)
    rel[0] = 0.0
    heading = np.cumsum(rel)
    rel[0] = -heading.mean()
    return dict(zip(names, rel.tolist()))


# ── C. elegans ──────────────────────────────────────────────────────────────
L_W = 0.26
NB_W = 24


def ys(s):
    return L_W / 2 - np.asarray(s, float) * L_W


class Worm:
    def __init__(self, male):
        self.male = male
        self.R = 0.0066 if male else 0.0086
        self.RP = 0.0076 if male else 0.0086     # pharynx scale: the male pharynx is nearly as big
        self.s_end = 0.985 if male else 1.0

    def prof(self, s):
        """Body radius / R, without the end caps."""
        s = np.asarray(s, float)
        f = 0.58 + 0.42 * smoothstep(0.0, 0.2, s)
        if self.male:
            f = f * (1 - 0.60 * smoothstep(0.83, self.s_end, s))
        else:
            f = f * (1 - 0.10 * smoothstep(0.6, 0.86, s))
            t = np.clip((1 - s) / 0.2, 0, 1)
            f = f * np.where(s > 0.8, np.sin(np.pi / 2 * t) ** 1.25, 1.0)
        return f

    def zc(self, s):
        return self.R * np.maximum(self.prof(s), 0.3)

    def at(self, s, dx=0.0, dz=0.0):
        """World point at body fraction s, offset dx (dorsal +) and dz (up) in metres."""
        s = np.asarray(s, float)
        return np.stack(np.broadcast_arrays(np.asarray(dx, float) + 0 * s, ys(s),
                                            self.zc(s) + dz), -1)

    def radius(self, S, TH):
        R = self.R
        f = self.prof(S)
        # blunt, rounded head: a hemispherical cap on the nose
        rc = 0.58 * R / L_W
        f = f * np.sqrt(np.clip(1 - (1 - np.clip(S / rc, 0, 1)) ** 2, 0, 1))
        # six lips around the mouth
        f = f * (1 + 0.075 * np.cos(6 * TH) * (1 - smoothstep(0.0, 0.014, S)))
        # a faint constriction behind the lips (the head/cephalic region boundary)
        f = f * (1 - 0.03 * gauss(S, 0.02, 0.006))
        vent = np.maximum(-np.cos(TH), 0)
        if not self.male:
            f = f + 0.16 * gauss(S, 0.5, 0.0085) * vent ** 3         # vulva
            f = f - 0.07 * gauss(S, 0.5, 0.0022) * vent ** 10        # its slit
            f = f - 0.05 * gauss(S, 0.865, 0.004) * vent ** 8        # anus
        else:
            f = f - 0.06 * gauss(S, 0.935, 0.004) * vent ** 8        # cloaca
            rc = 0.40 * R / L_W                                      # blunt tail tip, inside the fan
            f = f * np.sqrt(np.clip(1 - (1 - np.clip((self.s_end - S) / rc, 0, 1)) ** 2, 0, 1))
        return R * np.maximum(f, 0.012)

    # the cuticle ------------------------------------------------------------
    def body(self, mat):
        n_s, n_th = 280, 28
        u = np.linspace(0, 1, n_s)
        s = self.s_end * (0.75 * u + 0.25 * (0.5 - 0.5 * np.cos(np.pi * u)))
        th = TAU * np.arange(n_th + 1) / n_th
        S, TH = np.meshgrid(s[1:-1], th, indexing="ij")
        r = self.radius(S, TH)
        rings = np.stack([r * np.cos(TH), ys(S), self.zc(S) + r * np.sin(TH)], -1)
        p0 = self.at(0.0)
        p1 = self.at(self.s_end)
        V, F = grid_tube(rings, p0, p1, wrap_dup=True)
        tile = L_W / 380 * 4                        # 380 annuli along the body, 4 per tile
        uvs = np.concatenate([[[0.5, 0]], np.stack([TH / TAU, S * L_W / tile], -1).reshape(-1, 2),
                              [[0.5, self.s_end * L_W / tile]]])
        return add_obj("cuticle", V, F, mat, uvs=uvs, merge=True, origin=(0, 0, 0.06))

    # the pharynx ------------------------------------------------------------
    def pharynx(self, mat):
        s0, s1 = 0.004, 0.128
        s = np.linspace(s0, s1, 120)
        # procorpus, oval metacorpus, narrow isthmus, round terminal bulb; smooth-max of the parts
        base = 0.21 + 0.035 * smoothstep(0.004, 0.035, s) - 0.075 * smoothstep(0.058, 0.07, s)
        ell = lambda c, w, h: h * np.sqrt(np.clip(1 - ((s - c) / w) ** 2, 1e-6, 1))
        meta = ell(0.052, 0.0125, 0.44)
        term = ell(0.1135, 0.0175, 0.56)
        k = 28.0
        p = np.log(np.exp(k * base) + np.exp(k * meta) + np.exp(k * term)) / k
        p = (p - np.log(3) / k * 0.35) * self.RP
        P = self.at(s)
        a = arclen(P)
        p = rounded(p, a, 0.2 * self.RP, 0.18 * self.RP)
        V, F, t, th = sweep(P, p, n=16)
        # colour: pinkish muscle, a dark lumen line, a dark grinder in the terminal bulb
        yb = ys(0.1135)
        col = np.tile([0.80, 0.69, 0.63], (len(V), 1))
        lumen = np.exp(-(V[:, 0] / (0.06 * self.RP)) ** 2) * (1 - smoothstep(0.1, 0.11, (ys(0.004) - V[:, 1]) / L_W))
        col = col * (1 - 0.35 * lumen[:, None])
        d = np.sqrt(V[:, 0] ** 2 + (V[:, 1] - yb) ** 2)
        # the grinder: a dark, refractile triradiate plate in the middle of the bulb
        ang = np.arctan2(V[:, 1] - yb, V[:, 0])
        tri = 0.6 + 0.4 * np.cos(3 * ang) ** 2
        grind = np.exp(-(d / (0.26 * self.RP * tri)) ** 4)
        col = col * (1 - grind[:, None]) + np.array([0.20, 0.13, 0.08]) * grind[:, None]
        ym = ys(0.052)
        dm = np.sqrt(V[:, 0] ** 2 + (V[:, 1] - ym) ** 2)
        valve = np.exp(-(dm / (0.13 * self.RP)) ** 2)
        col = col * (1 - 0.35 * valve[:, None])
        # radial muscle striation of the bulbs
        col = col * (1 - 0.07 * (0.5 + 0.5 * np.cos(th * 18)))[:, None]
        return add_obj("pharynx", V, F, mat, cols=col)

    def nerve_ring(self, mat):
        s = 0.087
        c = self.at(s)
        rr = 0.30 * self.RP
        ph = TAU * np.arange(40) / 40
        P = np.stack([rr * np.cos(ph), np.zeros_like(ph), rr * np.sin(ph)], -1)
        P[:, 1] += 0.012 * self.R * np.sin(ph * 2)
        P = np.vstack([P, P[:1]]) + c
        # a closed ring: sweep an open loop then let the seam close by merging
        th = TAU * np.arange(10) / 10
        T, N, B = frames(P, ref=(0, 1, 0))
        rw = 0.06 * self.R
        rings = P[:-1, None, :] + rw * (np.cos(th)[None, :, None] * N[:-1, None, :] + np.sin(th)[None, :, None] * B[:-1, None, :])
        nr = len(rings)
        V = rings.reshape(-1, 3)
        F = []
        for k in range(nr):
            k2 = (k + 1) % nr
            for j in range(10):
                F.append((k * 10 + j, k * 10 + (j + 1) % 10, k2 * 10 + (j + 1) % 10, k2 * 10 + j))
        return add_obj("nerve_ring", V, F, mat)

    # the intestine ----------------------------------------------------------
    def intestine(self, mat):
        R = self.R
        if self.male:
            s0, s1, sa = 0.13, 0.925, 0.925
            dx = 0.30 * R * smoothstep(0.2, 0.32, np.linspace(s0, s1, 260)) * (1 - smoothstep(0.84, 0.9, np.linspace(s0, s1, 260)))
        else:
            s0, s1, sa = 0.13, 0.862, 0.862
            dx = 0.33 * R * smoothstep(0.2, 0.3, np.linspace(s0, s1, 260)) * (1 - smoothstep(0.7, 0.8, np.linspace(s0, s1, 260)))
        s = np.linspace(s0, s1, 260)
        dx = dx - 0.55 * R * smoothstep(sa - 0.035, sa, s)
        rad = 0.52 * R * self.prof(s)
        if self.male:
            rad = rad * (1 - 0.18 * smoothstep(0.3, 0.4, s) * (1 - smoothstep(0.8, 0.86, s)))
        else:
            rad = rad * (1 - 0.22 * smoothstep(0.26, 0.34, s) * (1 - smoothstep(0.66, 0.74, s)))
        rad = rad * (0.62 + 0.38 * smoothstep(s0, s0 + 0.02, s))
        rad = rad * (1 - 0.72 * smoothstep(sa - 0.04, sa, s))
        # the nine rings of intestinal cells show as faint constrictions
        rad = rad * (1 - 0.06 * np.cos(TAU * 9 * (s - s0) / (s1 - s0)) ** 8)
        P = self.at(s, dx=dx)
        P[:, 2] -= 0.05 * R
        rad = rounded(rad, arclen(P), 0.25 * R, 0.1 * R)
        V, F, t, th = sweep(P, rad, n=16)
        # lumpy, granular surface
        nz = Noise(11, freq=1 / (0.35 * R))
        ctr = P[np.clip(np.round(t * (len(P) - 1)).astype(int), 0, len(P) - 1)]
        off = V - ctr
        V = ctr + off * (1 + 0.07 * nz(V))[:, None]
        rng = np.random.default_rng(3)
        gran = rng.uniform(0.5, 1.35, len(V))
        big = Noise(12, freq=1 / (0.8 * R))(V)
        mid = Noise(13, freq=1 / (0.25 * R), n=24)(V)
        shade = np.clip(gran * (0.9 + 0.18 * big + 0.28 * mid), 0.35, 1.5)
        col = np.array([0.30, 0.19, 0.10])[None] * shade[:, None]
        # the lumen: a pale wavy line along the upper and lower surface
        wav = ctr[:, 0] + 0.08 * R * np.sin(ctr[:, 1] / (0.9 * R))
        lum = np.exp(-((V[:, 0] - wav) / (0.07 * R)) ** 2)
        col = col * (1 - lum[:, None]) + np.array([0.62, 0.50, 0.36]) * lum[:, None]
        return add_obj("intestine", V, F, mat, cols=col)

    # herm gonad -------------------------------------------------------------
    def herm_gonad_arm(self, sign, mats, rng):
        """sign +1: the anterior arm; -1 the posterior (mirrored about the vulva)."""
        R = self.R
        S = lambda s: 0.5 - sign * (0.5 - s)          # map anterior-arm coordinates
        objs = []
        # sheath: from the oocyte end, round the loop, out to the distal tip (dorsal)
        s_turn, rho = 0.272, 0.40 * R
        seg1 = np.linspace(0.300, s_turn, 8)[:-1]
        P1 = self.at(S(seg1), dx=-rho)
        ph = np.linspace(0, np.pi, 26)
        yc = ys(S(s_turn))
        loop = np.stack([-rho * np.cos(ph), yc + sign * rho * 1.2 * np.sin(ph),
                         self.zc(S(s_turn)) + 0.10 * R * (1 - np.cos(ph))], -1)
        seg2s = np.linspace(s_turn, 0.435, 60)[1:]
        dz2 = 0.20 * R + 0.0 * seg2s
        P2 = self.at(S(seg2s), dx=0.42 * R + 0.03 * R * np.sin(seg2s * 90), dz=dz2)
        P = np.vstack([P1, loop, P2])
        a = arclen(P)
        rad = np.interp(a, [0, a[-1] * 0.25, a[-1]], [0.34 * R, 0.29 * R, 0.21 * R])
        rad = rounded(rad, a, 0.34 * R, 0.21 * R)
        V, F, t, th = sweep(P, rad, n=14)
        # germ nuclei: pale discs with darker rims
        col = np.tile([0.84, 0.80, 0.72], (len(V), 1))
        nuc = V[rng.choice(len(V), 90, replace=False)]
        d = np.min(np.linalg.norm(V[:, None, :] - nuc[None], axis=2), axis=1)
        rim = np.exp(-((d - 0.09 * R) / (0.035 * R)) ** 2)
        col = col * (1 - 0.28 * rim[:, None])
        objs.append(add_obj("gonad_%s" % ("ant" if sign > 0 else "post"), V, F, mats["gonad"], cols=col))
        # oocytes: stacked like coins, largest next to the spermatheca
        for k, s in enumerate([0.300, 0.318, 0.336, 0.354]):
            sc = 0.86 + 0.06 * k
            c = self.at(S(s), dx=-0.38 * R + 0.02 * R * k)
            Vo, Fo, U = ellipsoid(c, (0.44 * R * sc, 0.25 * R * sc, 0.43 * R * sc),
                                  rot=rot_z(rng.uniform(-0.15, 0.15)), nu=22, nv=12)
            co = np.tile([0.88, 0.84, 0.75], (len(Vo), 1))
            # nucleus: a clear disc with a dark nucleolus, seen from above
            dn = np.linalg.norm(U[:, :2] - np.array([0.15 * sign, 0.0]), axis=1)
            topw = np.clip(U[:, 2], 0, 1)
            nucl = np.exp(-(dn / 0.45) ** 2) * topw
            co = co * (1 + 0.10 * nucl[:, None])
            nclo = np.exp(-(dn / 0.14) ** 2) * topw
            co = co * (1 - 0.55 * nclo[:, None])
            objs.append(add_obj("oocyte_%s%d" % ("a" if sign > 0 else "p", k), Vo, Fo, mats["oocyte"], cols=co))
        # spermatheca, with sperm
        c = self.at(S(0.373), dx=-0.30 * R)
        Vs, Fs, U = ellipsoid(c, (0.33 * R, 0.36 * R, 0.33 * R), nu=18, nv=10)
        co = np.tile([0.72, 0.66, 0.60], (len(Vs), 1)) * rng.uniform(0.7, 1.1, (len(Vs), 1))
        objs.append(add_obj("spermatheca_%s" % ("a" if sign > 0 else "p"), Vs, Fs, mats["oocyte"], cols=co))
        return objs

    def eggs(self, mats, rng):
        R = self.R
        objs = []
        ss = [0.404, 0.427, 0.450, 0.474, 0.526, 0.550, 0.573, 0.596]
        for k, s in enumerate(ss):
            tilt = (0.95 if k % 2 == 0 else -0.95) + rng.uniform(-0.25, 0.25)
            rot = rot_z(tilt) @ rot_y(rng.uniform(-0.3, 0.3))
            # long axis along local x before the tilt
            c = self.at(s, dx=-0.10 * R + rng.uniform(-0.05, 0.05) * R)
            axes = np.array([0.57, 0.36, 0.37]) * R * rng.uniform(0.95, 1.05)
            V, F, U = ellipsoid(c, axes, rot=rot, nu=26, nv=16)
            # the embryo inside: a few large cells (early cleavage), pale with dark borders
            ncell = int(rng.integers(4, 13))
            seeds = rng.normal(size=(ncell, 3))
            seeds /= np.linalg.norm(seeds, axis=1)[:, None]
            d = np.linalg.norm(U[:, None, :] - seeds[None], axis=2)
            d.sort(axis=1)
            border = np.exp(-((d[:, 1] - d[:, 0]) / 0.12) ** 2)
            which = np.argmin(np.linalg.norm(U[:, None, :] - seeds[None], axis=2), axis=1)
            tone = rng.uniform(0.86, 1.0, ncell)[which]
            col = np.array([0.86, 0.82, 0.70])[None] * tone[:, None]
            col = col * (1 - 0.45 * border[:, None])
            # the eggshell: a pale rim at the silhouette is left to the material's gloss
            objs.append(add_obj("egg_%d" % k, V, F, mats["egg"], cols=col))
        return objs

    # male reproductive system ----------------------------------------------
    def male_gonad(self, mats, rng):
        R = self.R
        s_turn, rho = 0.285, 0.34 * R
        seg1 = np.linspace(0.46, s_turn, 40)[:-1]
        P1 = self.at(seg1, dx=0.36 * R, dz=0.18 * R)
        ph = np.linspace(0, np.pi, 24)
        loop = np.stack([rho * np.cos(ph) + 0.01 * R, ys(s_turn) + rho * 1.2 * np.sin(ph),
                         self.zc(s_turn) + 0.18 * R * np.cos(ph / 2) ** 2], -1)
        seg2 = np.linspace(s_turn, 0.90, 120)[1:]
        P2 = self.at(seg2, dx=-0.33 * R - 0.2 * R * smoothstep(0.84, 0.9, seg2))
        seg3 = np.linspace(0.90, 0.93, 8)[1:]
        P3 = self.at(seg3, dx=-0.53 * R - 0.25 * R * smoothstep(0.9, 0.93, seg3))
        P = np.vstack([P1, loop, P2, P3])
        a = arclen(P)
        sP = (L_W / 2 - P[:, 1]) / L_W
        rad = (0.26 * R + 0.10 * R * smoothstep(0.30, 0.40, sP) + 0.16 * R * smoothstep(0.5, 0.6, sP)
               * (1 - smoothstep(0.76, 0.82, sP)) - 0.18 * R * smoothstep(0.82, 0.86, sP))
        loopmask = np.zeros(len(P))
        loopmask[len(P1):len(P1) + len(loop)] = 1
        rad = np.where(loopmask > 0, 0.27 * R, rad)
        rad = rad * np.minimum(1.0, self.prof(sP) / 0.9)
        rad = rounded(rad, a, 0.22 * R, 0.08 * R)
        V, F, t, th = sweep(P, rad, n=14)
        sV = (L_W / 2 - V[:, 1]) / L_W
        base = np.tile([0.84, 0.80, 0.72], (len(V), 1))
        # testis: nuclei; seminal vesicle: packed, darker, granular spermatids
        sv = smoothstep(0.48, 0.55, sV) * (1 - smoothstep(0.8, 0.84, sV)) * (t > len(P1) / len(P))
        gran = rng.uniform(0.55, 1.05, len(V))
        col = base * (1 - sv[:, None]) + (np.array([0.62, 0.58, 0.54]) * gran[:, None]) * sv[:, None]
        nuc = V[rng.choice(len(V), 60, replace=False)]
        d = np.min(np.linalg.norm(V[:, None, :] - nuc[None], axis=2), axis=1)
        rim = np.exp(-((d - 0.08 * R) / 0.03 / R) ** 2) * (1 - sv)
        col = col * (1 - 0.25 * rim[:, None])
        return [add_obj("gonad", V, F, mats["gonad"], cols=col)]

    def fan(self, mats):
        """The bursa: a cupped, transparent fan round the tail tip with 9 pairs of rays, laid
        flat (a ventral view, as it is always drawn) so it reads from above; and the spicules."""
        R = self.R
        objs = []
        sf0, sf1 = 0.893, 1.0
        yc = ys(0.945)
        ay = (sf1 - sf0) * L_W / 2 * 1.02
        ax = 1.6 * R
        z0 = self.zc(0.93)
        yc = (ys(sf0) + ys(sf1)) / 2

        def outline(phi):
            # anterior end narrows into the body sides; posterior end blunt and broad
            x = ax * np.cos(phi)
            yy = ay * np.sin(phi)
            front = np.clip(np.sin(phi), 0, 1)
            x = x * (1 - 0.30 * front ** 2)
            back = np.clip(-np.sin(phi), 0, 1)
            x = x * (1 + 0.08 * back)
            return x, yc + yy

        n_phi, n_r = 72, 12
        phi = TAU * np.arange(n_phi) / n_phi
        rr = np.linspace(0, 1, n_r + 1)[1:]
        ox, oy = outline(phi)
        X = rr[:, None] * ox[None]
        Y = yc + rr[:, None] * (oy[None] - yc)
        Z = z0 + 0.35 * R * rr[:, None] ** 2 + 0.02 * R * np.cos(phi * 18)[None] * rr[:, None] ** 4
        V = np.vstack([[0, yc, z0], np.stack([X, Y, Z], -1).reshape(-1, 3)])
        F = []
        for j in range(n_phi):
            F.append((0, 1 + j, 1 + (j + 1) % n_phi))
        for k in range(n_r - 1):
            for j in range(n_phi):
                a, b = 1 + k * n_phi + j, 1 + k * n_phi + (j + 1) % n_phi
                F.append((a, a + n_phi, b + n_phi, b))
        objs.append(add_obj("fan", V, F, mats["fan"], closed=False, origin=(0, yc, 0.045)))

        def fan_z(x, y):
            # the fan's height at a point, to lay the rays in it
            px, py = x, y - yc
            ang = np.arctan2(py, px)
            oxx, oyy = outline(ang)
            rmax = np.hypot(oxx, oyy - yc)
            r = np.clip(np.hypot(px, py) / rmax, 0, 1)
            return z0 + 0.35 * R * r ** 2

        # rays: bases along the tail's sides, tips short of the margin, fanning back
        for side in (1, -1):
            for k in range(9):
                sb = 0.912 + 0.0088 * k
                yb = ys(sb)
                xb = side * self.R * self.prof(sb) * 0.8
                ang = np.radians(-22 + 11.5 * k)            # 0 = straight out, + = backwards
                d = np.array([side * math.cos(ang), -math.sin(ang)])
                # march to the outline
                tmax = 0.0
                for tt in np.linspace(0, 4 * R, 400):
                    x, y = xb + d[0] * tt, yb + d[1] * tt
                    a2 = np.arctan2(y - yc, x)
                    oxx, oyy = outline(a2)
                    if np.hypot(x, y - yc) > np.hypot(oxx, oyy - yc):
                        break
                    tmax = tt
                frac = 0.80 if k == 5 else 0.93
                tt = np.linspace(0, tmax * frac, 18)
                xs, yy = xb + d[0] * tt, yb + d[1] * tt
                # a gentle curve
                bend = 0.12 * R * np.sin(np.pi * tt / max(tt[-1], 1e-9)) * side
                xs = xs + bend * d[1] * side
                zs = fan_z(xs, yy) + 0.04 * R
                Pr = np.stack([xs, yy, zs], -1)
                a = arclen(Pr)
                rad = np.interp(a, [0, a[-1] * 0.8, a[-1]], [0.085 * R, 0.055 * R, 0.075 * R])
                rad = rounded(rad, a, 0.05 * R, 0.07 * R)
                Vr, Fr, _, _ = sweep(Pr, rad, n=8)
                objs.append(add_obj("ray_%s%d" % ("L" if side > 0 else "R", k + 1), Vr, Fr, mats["ray"]))
        # spicules: two dark curved rods in the midline, tips at the cloaca
        for side in (1, -1):
            s = np.linspace(0.872, 0.942, 26)
            dx = -0.12 * R + side * 0.07 * R + 0.1 * R * np.sin(np.pi * (s - 0.872) / 0.07)
            Ps = self.at(s, dx=dx, dz=0.28 * R - 0.25 * R * ((s - 0.872) / 0.07) ** 2)
            a = arclen(Ps)
            rad = np.interp(a, [0, a[-1] * 0.2, a[-1]], [0.10 * R, 0.085 * R, 0.02 * R])
            rad = rounded(rad, a, 0.09 * R, 0.02 * R)
            Vs, Fs, _, _ = sweep(Ps, rad, n=8)
            objs.append(add_obj("spicule_%s" % ("L" if side > 0 else "R"), Vs, Fs, mats["spicule"]))
        return objs


def build_worm(male):
    w = Worm(male)
    nimg = cuticle_normal_map()
    mats = {
        "cuticle": material("cuticle", (0.80, 0.80, 0.76), rough=0.2, alpha=0.33, spec=0.6,
                            normal_img=nimg, normal_strength=0.45),
        "pharynx": material("pharynx", (1, 1, 1), rough=0.35, vcol=True),
        "nerve": material("nerve_ring", (0.66, 0.58, 0.48), rough=0.6),
        "intestine": material("intestine", (1, 1, 1), rough=0.55, vcol=True),
        "gonad": material("gonad", (1, 1, 1), rough=0.4, vcol=True),
        "oocyte": material("oocyte", (1, 1, 1), rough=0.35, vcol=True),
        "egg": material("egg", (1, 1, 1), rough=0.25, spec=0.6, vcol=True),
        "fan": material("fan", (0.88, 0.86, 0.80), rough=0.25, alpha=0.30, spec=0.6, double=True),
        "ray": material("ray", (0.70, 0.66, 0.58), rough=0.35),
        "spicule": material("spicule", (0.16, 0.10, 0.05), rough=0.25, spec=0.7),
    }
    rng = np.random.default_rng(7 if male else 5)
    objs = [w.body(mats["cuticle"]), w.pharynx(mats["pharynx"]), w.nerve_ring(mats["nerve"]),
            w.intestine(mats["intestine"])]
    if male:
        objs += w.male_gonad(mats, rng)
        objs += w.fan(mats)
    else:
        objs += w.herm_gonad_arm(+1, mats, rng)
        objs += w.herm_gonad_arm(-1, mats, rng)
        objs += w.eggs(mats, rng)
    names = ["spine_%d" % i for i in range(NB_W)]
    bones = []
    for i, n in enumerate(names):
        s = i / NB_W
        bones.append((n, (0.0, float(ys(s)), float(w.zc(max(s, 0.02)))), names[i - 1] if i else None))
    rig = make_rig(bones)
    q = lambda co: (L_W / 2 - co[:, 1]) / L_W * NB_W
    for ob in objs:
        skin(ob, rig, names, q)
    seg = L_W / NB_W
    poses = {"wave": wave_angles(names, waves=1.35, amp_curv=5.2 / L_W, seg_len=seg, phase=0.6)}
    return rig, objs, poses


# ── Ciona intestinalis larva ────────────────────────────────────────────────
L_C = 0.24
NB_C = 12


def voronoi_shade(U, seeds, width):
    """Cell pattern on a unit-sphere direction field: (border 0..1, index of the nearest seed)."""
    d = np.linalg.norm(U[:, None, :] - seeds[None], axis=2)
    which = np.argmin(d, axis=1)
    d.sort(axis=1)
    return np.exp(-((d[:, 1] - d[:, 0]) / width) ** 2), which


def build_ciona():
    rng = np.random.default_rng(21)
    mats = {
        "tunic": material("tunic", (0.93, 0.94, 0.92), rough=0.12, alpha=0.08, spec=0.7, valpha=True),
        "epidermis": material("trunk_epidermis", (0.78, 0.74, 0.60), rough=0.3, alpha=0.5, spec=0.6, valpha=True),
        "tail_epi": material("tail_epidermis", (0.86, 0.84, 0.76), rough=0.25, alpha=0.20, spec=0.6),
        "fin": material("fin", (0.88, 0.91, 0.92), rough=0.15, alpha=0.36, spec=0.7, double=True),
        "fin_rim": material("fin_rim", (0.66, 0.70, 0.72), rough=0.2, alpha=0.5),
        "papilla": material("papilla", (0.74, 0.70, 0.57), rough=0.35),
        "endoderm": material("endoderm", (1, 1, 1), rough=0.6, vcol=True),
        "vesicle": material("sensory_vesicle", (0.86, 0.90, 0.92), rough=0.1, alpha=0.05, spec=0.7),
        "pigment": material("pigment", (0.008, 0.007, 0.006), rough=0.7, spec=0.15),
        "lens": material("lens", (0.86, 0.86, 0.80), rough=0.15),
        "neural": material("neural", (0.64, 0.62, 0.55), rough=0.5),
        "notochord": material("notochord", (1, 1, 1), rough=0.18, spec=0.6, vcol=True),
        "muscle": material("muscle", (0.70, 0.56, 0.48), rough=0.45, alpha=0.55),
        "cord": material("nerve_cord", (0.74, 0.72, 0.64), rough=0.5),
    }
    objs = []
    yT, aT, bx, bz = 0.0795, 0.035, 0.0175, 0.0215
    tun_x, tun_z, tun_y = 0.0022, 0.0022, 0.003
    # trunk: an ovoid, broad behind, the dorsal outline more convex than the ventral
    t = np.cos(np.linspace(0, np.pi, 72))           # +1 front .. -1 back
    prof = np.sqrt(np.clip(1 - t ** 2, 0, 1)) ** 0.92 * (1 - 0.16 * t)
    zc = (bz + tun_z) * prof.max() * 0.96          # the lowest point of the tunic rests on y = 0
    dorsal_shift = 0.0025 * np.sqrt(np.clip(1 - t ** 2, 0, 1))
    P = np.stack([0 * t, yT + aT * t, zc + dorsal_shift * 0.5], -1)
    V, F, tt, th = sweep(P, np.stack([bx * prof, bz * prof], 1), n=40)
    # the sensory vesicle's position, needed here: the epidermis is clearer over it (it is, in
    # the animal), so the two pigment spots read black from above and from the side
    vc = np.array([0.0012, yT + 0.006, zc + 0.0108])
    near_side = np.exp(-((V[:, 1] - vc[1]) / 0.011) ** 2 - ((V[:, 2] - vc[2]) / 0.009) ** 2)
    near_top = np.exp(-((V[:, 1] - vc[1]) / 0.011) ** 2 - ((V[:, 0] - vc[0]) / 0.008) ** 2) * (V[:, 2] > zc)
    clear = np.clip(near_side + near_top, 0, 1)
    ea = 0.52 - 0.47 * clear
    objs.append(add_obj("trunk", V, F, mats["epidermis"], cols=np.stack([np.ones_like(ea)] * 3 + [ea], 1),
                        origin=(0, yT, zc + 0.05)))
    P2 = np.stack([0 * t, yT - 0.0008 + (aT + tun_y) * t, zc + dorsal_shift * 0.5], -1)
    V, F, _, _ = sweep(P2, np.stack([bx * prof + tun_x, bz * prof + tun_z], 1), n=40)
    near_side = np.exp(-((V[:, 1] - vc[1]) / 0.011) ** 2 - ((V[:, 2] - vc[2]) / 0.009) ** 2)
    near_top = np.exp(-((V[:, 1] - vc[1]) / 0.011) ** 2 - ((V[:, 0] - vc[0]) / 0.008) ** 2) * (V[:, 2] > zc)
    ta = 0.09 - 0.07 * np.clip(near_side + near_top, 0, 1)
    objs.append(add_obj("tunic", V, F, mats["tunic"], cols=np.stack([np.ones_like(ta)] * 3 + [ta], 1),
                        origin=(0, yT, zc + 0.08)))

    def trunk_r(y):
        tq = np.clip((y - yT) / aT, -1, 1)
        pr = np.sqrt(np.clip(1 - tq ** 2, 0, 1)) ** 0.92 * (1 - 0.16 * tq)
        return bx * pr, bz * pr

    # three adhesive papillae: two dorsal, one ventral; broad-based cones with a rounded,
    # slightly swollen tip, splayed a little
    for k, (px, pz) in enumerate([(-0.0062, 0.0058), (0.0062, 0.0058), (0.0, -0.0068)]):
        base = np.array([px * 0.55, yT + aT * 0.80, zc + pz * 0.55])
        tip = np.array([px * 1.10, yT + aT + 0.0040, zc + pz * 1.0])
        u = np.linspace(0, 1, 22)
        Pp = base[None] + (tip - base)[None] * u[:, None]
        rad = 0.0030 * (1 - u) ** 1.5 + 0.0010 + 0.0004 * gauss(u, 0.86, 0.12)
        rad = rounded(rad, arclen(Pp), 0.002, 0.0015)
        Vp, Fp, _, _ = sweep(Pp, rad, n=16)
        objs.append(add_obj("papilla_%d" % k, Vp, Fp, mats["papilla"], origin=(tip[0], tip[1], tip[2] + 0.03)))

    # the dense interior: one mass of cells filling the trunk just inside the epidermis - yolky
    # endoderm behind, greyer pharyngeal endoderm and mesenchyme in front - hollowed dorsally
    # where the clear sensory vesicle sits
    Pi = np.stack([0 * t, yT - 0.001 + (aT - 0.0035) * t, zc - 0.0012 + dorsal_shift * 0.3], -1)
    Vi, Fi, ti, thi = sweep(Pi, np.stack([(bx - 0.0022) * prof, (bz - 0.0026) * prof], 1), n=40)
    Vi = Vi + (Vi - Pi[np.clip(np.round(ti * (len(Pi) - 1)).astype(int), 0, len(Pi) - 1)]) \
        * 0.03 * Noise(5, freq=1 / 0.006)(Vi)[:, None]
    dent = np.exp(-((Vi[:, 1] - vc[1]) / 0.0095) ** 2 - ((Vi[:, 0] - vc[0]) / 0.0055) ** 2)
    floor = vc[2] - 0.0068
    Vi[:, 2] = Vi[:, 2] - dent * np.maximum(0.0, Vi[:, 2] - floor)
    seeds = np.stack([rng.uniform(-bx, bx, 90), rng.uniform(yT - aT, yT + aT, 90), rng.uniform(zc - bz, zc + bz, 90)], 1)
    d = np.linalg.norm(Vi[:, None, :] - seeds[None], axis=2)
    which = np.argmin(d, axis=1)
    d.sort(axis=1)
    border = np.exp(-((d[:, 1] - d[:, 0]) / 0.0007) ** 2)
    tone = rng.uniform(0.86, 1.06, len(seeds))[which]
    gr = rng.uniform(0.85, 1.08, len(Vi))
    front = smoothstep(yT - 0.004, yT + 0.018, Vi[:, 1])
    base = np.array([0.66, 0.54, 0.34])[None] * (1 - front)[:, None] + np.array([0.68, 0.63, 0.52])[None] * front[:, None]
    col = base * (tone * gr)[:, None] * (1 - 0.28 * border)[:, None]
    objs.append(add_obj("endoderm", Vi, Fi, mats["endoderm"], cols=col))
    for side in ():
        mc = np.array([side * 0.0092, yT - 0.017, zc + 0.001])
        Vm, Fm, U = ellipsoid(mc, (0.0055, 0.010, 0.0085), rot=rot_z(side * 0.25), nu=22, nv=14)
        gm = rng.uniform(0.6, 1.1, len(Vm))
        col = np.array([0.58, 0.48, 0.32])[None] * gm[:, None]
        objs.append(add_obj("mesenchyme_%s" % ("L" if side > 0 else "R"), Vm, Fm, mats["endoderm"], cols=col))
    # the sensory vesicle, dorsal and a little to the right, with the two pigment cells: the
    # otolith (a black ball on a stalk, anterior, on the floor of the vesicle) and the ocellus (a
    # black cup, posterior-dorsal, with its three lens cells)
    Vv, Fv, _ = ellipsoid(vc, (0.0058, 0.0085, 0.0052), nu=26, nv=14)
    objs.append(add_obj("sensory_vesicle", Vv, Fv, mats["vesicle"], origin=(vc[0], vc[1], vc[2] + 0.02)))
    oto = vc + np.array([-0.0010, 0.0036, 0.0006])
    Vo, Fo, _ = ellipsoid(oto, (0.0026, 0.0026, 0.0025), nu=22, nv=12)
    objs.append(add_obj("otolith", Vo, Fo, mats["pigment"]))
    Ps = np.stack([np.full(6, oto[0]), np.full(6, oto[1]), np.linspace(oto[2] - 0.0042, oto[2] - 0.001, 6)], -1)
    Vs, Fs, _, _ = sweep(Ps, rounded(np.full(6, 0.0007), arclen(Ps), 0.0003, 0.0003), n=8)
    objs.append(add_obj("otolith_stalk", Vs, Fs, mats["lens"]))
    oc = vc + np.array([0.0016, -0.0032, 0.0012])
    # the cup: a hemispherical shell of pigment opening to the right and forwards
    ph = np.linspace(0, np.pi * 0.62, 10)
    thc = TAU * np.arange(20) / 20
    rc_o, rc_i = 0.0034, 0.0024
    outer = np.stack([np.sin(ph)[:, None] * np.cos(thc), np.sin(ph)[:, None] * np.sin(thc),
                      np.cos(ph)[:, None] * np.ones_like(thc)], -1)
    V_out = (outer * rc_o).reshape(-1, 3)
    V_in = (outer * rc_i).reshape(-1, 3)
    nph, nth = len(ph), len(thc)
    Vc = np.vstack([V_out, V_in])
    Fc = []
    off = nph * nth
    for i in range(nph - 1):
        for j in range(nth):
            a0, a1 = i * nth + j, i * nth + (j + 1) % nth
            b0, b1 = a0 + nth, a1 + nth
            Fc.append((a0, a1, b1, b0))
            Fc.append((off + a0, off + b0, off + b1, off + a1))
    for j in range(nth):                             # the rim
        a0, a1 = (nph - 1) * nth + j, (nph - 1) * nth + (j + 1) % nth
        Fc.append((a0, off + a0, off + a1, a1))
    # the cup's axis (local +z) points backwards-left, so it opens forwards-right
    Rc = rot_z(-0.9) @ rot_x(-1.25)
    Vc = Vc @ Rc.T + oc
    objs.append(add_obj("ocellus", Vc, Fc, mats["pigment"], merge=True))
    opening = Rc @ np.array([0, 0, -1.0])
    for k in range(3):
        lc = oc + opening * 0.0013 + Rc @ np.array([(k - 1) * 0.0013, 0.0004 * (k % 2), 0])
        Vl, Fl, _ = ellipsoid(lc, (0.0010, 0.0010, 0.0010), nu=12, nv=8)
        objs.append(add_obj("lens_%d" % k, Vl, Fl, mats["lens"]))
    # the neural tube behind the vesicle (visceral ganglion) running into the tail's nerve cord
    Pn = np.stack([np.linspace(0.001, 0, 12), np.linspace(vc[1] - 0.006, yT - aT + 0.002, 12),
                   np.linspace(vc[2] - 0.001, zc + 0.004, 12)], -1)
    rn = rounded(np.interp(np.arange(12), [0, 3, 11], [0.0022, 0.0016, 0.0010]), arclen(Pn), 0.002, 0.001)
    Vn, Fn, _, _ = sweep(Pn, rn, n=12)
    objs.append(add_obj("visceral_ganglion", Vn, Fn, mats["neural"]))

    # tail -------------------------------------------------------------------
    y0t = yT - aT + 0.002          # where the tail leaves the trunk (tail_0's pivot)
    ytip = -0.1155
    y_in = yT - 0.022              # the tail tube starts inside the trunk
    zt = zc - 0.0015

    def tail_hw(yv):
        tl = np.clip((y0t - yv) / (y0t - ytip), 0, 1)
        return 0.0056 * (1 - 0.25 * tl - 0.55 * smoothstep(0.6, 1.0, tl)) + 0.0003

    u = np.linspace(0, 1, 140)
    yt = y_in + (ytip - y_in) * u
    hw = tail_hw(yt)
    Pt = np.stack([0 * yt, yt, zt + 0 * yt], -1)
    rad = rounded(np.stack([hw, hw * 1.18], 1), arclen(Pt), 0.004, 0.0012)
    V, F, _, _ = sweep(Pt, rad, n=20)
    objs.append(add_obj("tail", V, F, mats["tail_epi"], origin=(0, -0.03, zc + 0.05)))
    # notochord: a single file of 40 coin-shaped cells, stacked like a roll of coins
    n_cells = 40
    yn0, yn1 = y0t + 0.003, ytip + 0.004
    step = (yn0 - yn1) / n_cells
    for k in range(n_cells):
        y = yn0 - (k + 0.5) * step
        r = 0.56 * tail_hw(y)
        Vn, Fn, U = ellipsoid((0, y, zt), (r, r * 1.04, step * 0.47), rot=rot_x(math.pi / 2), nu=14, nv=8,
                              eps=0.45)
        # a vacuole-clear centre and a greyer rim, as in DIC
        rim = np.clip(np.abs(U[:, 2]), 0, 1) ** 3
        c = np.array([0.76, 0.78, 0.74])[None] * (1 - 0.22 * rim)[:, None] * rng.uniform(0.95, 1.02)
        objs.append(add_obj("notochord_%02d" % k, Vn, Fn, mats["notochord"], cols=c))
    # muscle bands either side of the notochord, faintly segmented into cells
    for side in (1, -1):
        um = np.linspace(0, 1, 100)
        ym = (y0t + 0.001) + (ytip + 0.002 - y0t - 0.001) * um
        hwm = tail_hw(ym)
        Pm = np.stack([side * hwm * 0.60, ym, zt + 0 * ym], -1)
        rm = np.stack([hwm * 0.30, hwm * 0.95], 1)
        rm = rm * (1 - 0.07 * np.cos(np.pi * 13 * um) ** 10)[:, None]
        rm = rounded(rm, arclen(Pm), 0.0012, 0.0005)
        Vm, Fm, _, _ = sweep(Pm, rm, n=10)
        objs.append(add_obj("muscle_%s" % ("L" if side > 0 else "R"), Vm, Fm, mats["muscle"],
                            origin=(side * 0.004, -0.03, zc + 0.03)))
    # dorsal nerve cord and ventral endodermal strand
    for name, dz, rr in (("nerve_cord", 0.72, 0.11), ("endodermal_strand", -0.72, 0.10)):
        uc = np.linspace(0, 1, 90)
        yc_ = (y0t + 0.003) + (ytip + 0.004 - y0t - 0.003) * uc
        hh = tail_hw(yc_) * 1.18
        Pc = np.stack([0 * yc_, yc_, zt + dz * hh], -1)
        rc = rounded(rr * hh, arclen(Pc), 0.0005, 0.0003)
        Vc2, Fc2, _, _ = sweep(Pc, rc, n=8)
        objs.append(add_obj(name, Vc2, Fc2, mats["cord"]))
    # the fin fold: a thin median sheet of tunic above and below the tail and round its tip
    nu_, nv_ = 120, 18
    yfa, yfb = y0t - 0.006, ytip - 0.0045
    uf = np.linspace(0, 1, nu_)
    yf = yfa + (yfb - yfa) * uf
    tf = np.clip((y0t - yf) / (y0t - ytip), 0, 1)
    # low beside the trunk, deepest over the middle of the tail, then a lanceolate taper that
    # closes a little beyond the tip
    H = (tail_hw(yf) * 1.18 * (1 - smoothstep(0.93, 1.0, uf))
         + 0.0092 * smoothstep(0.0, 0.32, uf) * (1 - smoothstep(0.5, 1.0, uf) ** 1.2))
    H = H * np.sqrt(np.clip(1 - smoothstep(0.96, 1.0, uf), 0, 1))
    H[-1] = 0.0
    vv = np.linspace(-1, 1, nv_)
    Z = zt + vv[None] * H[:, None] * np.where(vv[None] < 0, 0.9, 1.0)
    Y = np.repeat(yf[:, None], nv_, 1)
    X = 0.0002 * np.cos(np.pi * vv / 2)[None] * np.ones((nu_, 1))
    Vf = np.stack([X, Y, Z], -1).reshape(-1, 3)
    Ff = []
    for i in range(nu_ - 1):
        for j in range(nv_ - 1):
            a0 = i * nv_ + j
            Ff.append((a0, a0 + 1, a0 + nv_ + 1, a0 + nv_))
    objs.append(add_obj("fin", Vf, Ff, mats["fin"], closed=False, origin=(0, -0.03, zc + 0.07)))
    # a slightly denser rim along the fin's edge, which is what shows in a micrograph
    top = np.stack([0 * yf, yf, zt + H], -1)
    bot = np.stack([0 * yf, yf, zt - 0.9 * H], -1)[::-1]
    edge = np.vstack([top[:-1], bot])
    edge = edge[np.concatenate([[True], np.linalg.norm(np.diff(edge, axis=0), axis=1) > 1e-6])]
    re = rounded(np.full(len(edge), 0.00022), arclen(edge), 0.0002, 0.0002)
    Ve2, Fe2, _, _ = sweep(edge, re, n=6, ref=(1, 0, 0))
    objs.append(add_obj("fin_rim", Ve2, Fe2, mats["fin_rim"], origin=(0, -0.03, zc + 0.075)))

    # rig ----------------------------------------------------------------------
    seg = (y0t - (ytip - 0.0045)) / NB_C
    names = ["tail_%d" % i for i in range(NB_C)]
    bones = [("trunk", (0.0, yT, zc), None)]
    for i, n in enumerate(names):
        bones.append((n, (0.0, y0t - i * seg, zt), "trunk" if i == 0 else names[i - 1]))
    rig = make_rig(bones)
    all_names = ["trunk"] + names

    def q(co):
        return 1.0 + (y0t - co[:, 1]) / seg

    def gate(qv, W):
        # inside the trunk, hand the tail's share back to the trunk: the trunk stays rigid
        g = smoothstep(0.6, 1.05, qv)
        W[:, 1:] *= g[:, None]
        W[:, 0] += 1 - W.sum(1)
        return W

    for ob in objs:
        skin(ob, rig, all_names, q, gate=gate)
    poses = {"wave": wave_angles(names, waves=0.9, amp_curv=10.0 / L_C, seg_len=seg, phase=1.2,
                                 ramp=lambda x: 0.35 + 0.65 * x)}
    poses["wave"]["trunk"] = 0.0
    return rig, objs, poses


# ── staging, rendering, export ──────────────────────────────────────────────
def stage(kind):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    w, h = (int(v) for v in args.res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.film_transparent = False
    sc.eevee.taa_render_samples = args.samples
    sc.eevee.use_gtao = True
    sc.eevee.gtao_distance = 0.02
    sc.eevee.use_ssr = True
    sc.eevee.use_soft_shadows = True
    sc.eevee.shadow_cube_size = "1024"
    sc.eevee.shadow_cascade_size = "2048"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "Medium High Contrast"
    world = bpy.data.worlds.new("world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.33, 0.34, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sc.world = world
    me = bpy.data.meshes.new("ground")
    me.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", me)
    sc.collection.objects.link(g)
    gcol = (0.40, 0.39, 0.35) if kind == "worm" else (0.30, 0.36, 0.42)
    g.data.materials.append(material("ground", gcol, rough=0.6))
    key = bpy.data.lights.new("key", "AREA")
    key.energy = 2.0
    key.size = 0.5
    ko = bpy.data.objects.new("key", key)
    ko.location = (0.25, -0.2, 0.55)
    ko.rotation_euler = (Vector((0, 0, 0.0)) - ko.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(ko)
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 1.0
    sun.angle = math.radians(8)
    so = bpy.data.objects.new("sun", sun)
    so.rotation_euler = (math.radians(35), math.radians(-20), math.radians(30))
    sc.collection.objects.link(so)
    fill = bpy.data.lights.new("fill", "AREA")
    fill.energy = 0.7
    fill.size = 0.8
    fo = bpy.data.objects.new("fill", fill)
    fo.location = (-0.35, 0.25, 0.3)
    fo.rotation_euler = (Vector((0, 0, 0.0)) - fo.location).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(fo)
    return [g, ko, so, fo]


def camera(name, loc=None, target=(0, 0, 0.01), ortho=None, lens=60, top_center=None):
    cd = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(cam)
    cd.clip_start = 0.005
    cd.clip_end = 5
    if ortho is not None:
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
        cx, cy = top_center if top_center else (0, 0)
        cam.location = (cx, cy, 0.6)
        cam.rotation_euler = (0, 0, math.radians(90))   # head (+Y) to the right of the frame
    else:
        cd.lens = lens
        cam.location = loc
        cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return cam


def render(cam, path):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = os.path.abspath(path)
    bpy.ops.render.render(write_still=True)
    print("rendered", path)


def render_species(sid, rig, poses, kind):
    os.makedirs(args.previews, exist_ok=True)
    extras = stage(kind)
    cams = {
        "top": camera("cam_top", ortho=0.285 if kind == "worm" else 0.265),
        "34": (camera("cam_34", loc=(0.30, -0.26, 0.24), target=(0, 0.0, 0.0), lens=58) if kind == "worm"
               else camera("cam_34", loc=(0.30, -0.20, 0.25), target=(0, 0.0, 0.012), lens=55)),
    }
    if kind == "worm":
        cams["head"] = camera("cam_head", ortho=0.075, top_center=(0, 0.095))
        cams["mid"] = camera("cam_mid", ortho=0.085, top_center=(0, 0.0))
        cams["tail"] = camera("cam_tail", ortho=0.075, top_center=(0, -0.095))
        cams["head34"] = camera("cam_head34", loc=(0.07, 0.03, 0.05), target=(0, 0.1, 0.006), lens=60)
    else:
        cams["trunk"] = camera("cam_trunk", ortho=0.09, top_center=(0, 0.075))
        cams["trunk34"] = camera("cam_trunk34", loc=(0.11, 0.0, 0.1), target=(0, 0.08, 0.02), lens=60)
        cams["side"] = camera("cam_side", loc=(0.55, 0.0, 0.03), target=(0, 0.0, 0.025), lens=60)
    clear_pose(rig)
    for cname, cam in cams.items():
        render(cam, os.path.join(args.previews, "%s_rest_%s.png" % (sid, cname)))
    set_pose(rig, poses["wave"])
    for cname in ("top", "34"):
        render(cams[cname], os.path.join(args.previews, "%s_wave_%s.png" % (sid, cname)))
    clear_pose(rig)
    for ob in list(cams.values()) + extras:
        bpy.data.objects.remove(ob, do_unlink=True)


def export(sid, rig, objs):
    clear_pose(rig)
    bpy.ops.object.select_all(action="DESELECT")
    for ob in [rig] + objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = rig
    path = os.path.abspath(os.path.join(args.out, sid + ".glb"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_apply=False, export_animations=False, export_yup=True,
                              export_cameras=False, export_lights=False, export_skins=True,
                              export_colors=True, export_normals=True, export_texcoords=True,
                              export_tangents=False, export_materials="EXPORT")
    print("exported", path)
    return path


# ── verification of the written file ───────────────────────────────────────
def quat_mat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def verify(path, required, length):
    data = open(path, "rb").read()
    magic, ver, total = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a glb"
    jlen, jtype = struct.unpack_from("<II", data, 12)
    gj = json.loads(data[20:20 + jlen])
    nodes = gj["nodes"]
    names = [n.get("name", "") for n in nodes]
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i

    def local(i):
        n = nodes[i]
        M = np.eye(4)
        if "matrix" in n:
            return np.array(n["matrix"]).reshape(4, 4).T
        M[:3, :3] = quat_mat(n.get("rotation", [0, 0, 0, 1])) * np.array(n.get("scale", [1, 1, 1]))
        M[:3, 3] = n.get("translation", [0, 0, 0])
        return M

    def world(i):
        M = local(i)
        while i in parent:
            i = parent[i]
            M = local(i) @ M
        return M

    lo, hi = np.full(3, 1e9), np.full(3, -1e9)
    tris = 0
    for i, n in enumerate(nodes):
        if "mesh" not in n:
            continue
        W = world(i)
        for prim in gj["meshes"][n["mesh"]]["primitives"]:
            acc = gj["accessors"][prim["attributes"]["POSITION"]]
            mn, mx = np.array(acc["min"]), np.array(acc["max"])
            corners = np.array([[a, b, c] for a in (mn[0], mx[0]) for b in (mn[1], mx[1]) for c in (mn[2], mx[2])])
            wc = corners @ W[:3, :3].T + W[:3, 3]
            lo, hi = np.minimum(lo, wc.min(0)), np.maximum(hi, wc.max(0))
            if "indices" in prim:
                tris += gj["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += acc["count"] // 3
    missing = [r for r in required if r not in names]
    skins = gj.get("skins", [])
    joint_names = [nodes[j]["name"] for j in skins[0]["joints"]] if skins else []
    up_ok = True
    for r in required:
        if r in names and r in joint_names:
            Y = world(names.index(r))[:3, 1]
            up_ok &= bool(abs(Y[1] - 1) < 1e-3)
    size = os.path.getsize(path)
    ext = hi - lo
    rep = {
        "file": path, "bytes": size, "triangles": tris, "missing": missing,
        "skins": len(skins), "joints": joint_names, "rig_node": "rig" in names,
        "bbox_min": lo.round(4).tolist(), "bbox_max": hi.round(4).tolist(),
        "extent": ext.round(4).tolist(), "bones_local_y_is_up": up_ok,
        "images": [im.get("mimeType") for im in gj.get("images", [])],
        "materials": [(m["name"], m.get("alphaMode", "OPAQUE")) for m in gj.get("materials", [])],
    }
    ok = (not missing and skins and size <= 2 * 1024 * 1024 and tris <= 60000 and up_ok
          and abs(ext[2] - length) < 0.01 * length + 0.002 and abs(lo[1]) < 1e-3 and ext[2] > ext[0])
    rep["ok"] = bool(ok)
    print("VERIFY", json.dumps(rep))
    return rep


def contact_sheet(path):
    rows = []
    for sid in SPECIES:
        row = []
        for tag in ("rest_top", "rest_34", "wave_top", "wave_34"):
            f = os.path.join(args.previews, "%s_%s.png" % (sid, tag))
            if not os.path.exists(f):
                row = None
                break
            img = bpy.data.images.load(os.path.abspath(f))
            w, h = img.size
            px = np.empty(w * h * 4, np.float32)
            img.pixels.foreach_get(px)
            a = px.reshape(h, w, 4)[::-1]
            a = a[: h // 2 * 2, : w // 2 * 2].reshape(h // 2, 2, w // 2, 2, 4).mean((1, 3))
            row.append(a)
            bpy.data.images.remove(img)
        if row:
            gap = np.ones((row[0].shape[0], 6, 4), np.float32)
            rows.append(np.concatenate(sum([[r, gap] for r in row], [])[:-1], 1))
    if not rows:
        return
    gap = np.ones((6, rows[0].shape[1], 4), np.float32)
    sheet = np.concatenate(sum([[r, gap] for r in rows], [])[:-1], 0)
    H, W = sheet.shape[:2]
    out = bpy.data.images.new("contact", W, H, alpha=False)
    out.pixels.foreach_set(sheet[::-1].ravel())
    out.filepath_raw = os.path.abspath(path)
    out.file_format = "PNG"
    out.save()
    print("contact sheet", path)


def main():
    only = [s for s in args.only.split(",") if s] or SPECIES
    reports = []
    for sid in only:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if sid == "ciona_larva":
            rig, objs, poses = build_ciona()
            req = ["rig"] + ["tail_%d" % i for i in range(NB_C)]
            length, kind = L_C, "ciona"
        else:
            rig, objs, poses = build_worm(male=(sid == "c_elegans_male"))
            req = ["rig"] + ["spine_%d" % i for i in range(NB_W)]
            length, kind = L_W, "worm"
        path = export(sid, rig, objs)
        reports.append(verify(path, req, length))
        if not args.no_render:
            render_species(sid, rig, poses, kind)
    if not args.no_render:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        contact_sheet(os.path.join(args.previews, "contact.png"))
    for r in reports:
        print("SUMMARY %s ok=%s %.0f KB %d tris extent=%s" % (os.path.basename(r["file"]), r["ok"],
              r["bytes"] / 1024, r["triangles"], r["extent"]))


if __name__ == "__main__":
    main()

"""The two vertebrates of Open Animal Stage, built in Blender by script.

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup \
        --python scene/model_vertebrates.py -- --out web/models \
        --previews data/raw/previews/vertebrates

zebrafish_larva.glb  a 7 dpf Danio rerio larva (what Fish1 is), 0.36 m long.
mouse_v1.glb         an adult C57BL/6J mouse (black, slightly lighter belly),
                     sitting up on its haunches, 0.30 m body + 0.25 m tail.

Contract: docs/models.md. Blender is Z-up and the glTF exporter turns it Y-up,
so the animals are built facing Blender +Y (= glTF -Z), their left at -X.
Every shape is lofted from anatomical profiles (fish) or grown from metaballs
and remeshed (mouse); pigment, fur and scales are small textures computed here
in numpy or baked from procedural shaders. After export each file is imported
back into an empty scene, checked against the contract and rendered from three
angles, so the previews show what the page will load.
"""
import argparse
import json
import math
import os
import shutil
import struct
import sys
import tempfile

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

TAU = 2 * math.pi


# ---------------------------------------------------------------- small helpers
def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="web/models")
    p.add_argument("--previews", default="data/raw/previews/vertebrates")
    p.add_argument("--only", default="", help="fish | mouse (default both)")
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--res", type=int, default=640)
    p.add_argument("--no-render", action="store_true")
    return p.parse_args(argv)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x, float) - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sgnpow(x, e):
    return np.sign(x) * np.abs(x) ** e


def normalize(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def pchip(xk, yk, x):
    """Monotone cubic through knots (Fritsch-Carlson): smooth, no overshoot."""
    xk = np.asarray(xk, float); yk = np.asarray(yk, float); x = np.asarray(x, float)
    h = np.diff(xk); d = np.diff(yk) / h
    m = np.zeros_like(yk)
    for k in range(1, len(xk) - 1):
        if d[k - 1] * d[k] > 0:
            w1 = 2 * h[k] + h[k - 1]; w2 = h[k] + 2 * h[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0] = d[0]; m[-1] = d[-1]
    i = np.clip(np.searchsorted(xk, x) - 1, 0, len(h) - 1)
    t = np.clip((x - xk[i]) / h[i], 0, 1)
    t2 = t * t; t3 = t2 * t
    return ((2 * t3 - 3 * t2 + 1) * yk[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
            + (-2 * t3 + 3 * t2) * yk[i + 1] + (t3 - t2) * h[i] * m[i + 1])


def rot(ax, deg):
    return Matrix.Rotation(math.radians(deg), 3, ax)


# ---------------------------------------------------------------- meshes
def mesh_obj(name, verts, faces, face_uvs=None, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    if face_uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for k, li in enumerate(poly.loop_indices):
                uvl.data[li].uv = face_uvs[poly.index][k]
    for p in me.polygons:
        p.use_smooth = smooth
    return link(bpy.data.objects.new(name, me))


def signed_volume(verts, faces):
    v = np.asarray(verts, float); vol = 0.0
    for f in faces:
        for k in range(1, len(f) - 1):
            vol += np.dot(v[f[0]], np.cross(v[f[k]], v[f[k + 1]]))
    return vol / 6.0


def loft(name, rings, us=None, pole_front=None, pole_back=None, closed=True, outward=True):
    """Quad mesh through rings (R x N x 3); u runs along the rings, v around.
    Poles close the ends; faces are flipped so the normals point outward."""
    rings = np.asarray(rings, float); R, N, _ = rings.shape
    us = np.linspace(0, 1, R) if us is None else np.asarray(us, float)
    verts = [tuple(p) for p in rings.reshape(-1, 3)]
    faces, fuv = [], []
    M = N if closed else N - 1
    dv = 1.0 / (N if closed else N - 1)
    for i in range(R - 1):
        for j in range(M):
            j2 = (j + 1) % N
            faces.append((i * N + j, (i + 1) * N + j, (i + 1) * N + j2, i * N + j2))
            fuv.append([(us[i], j * dv), (us[i + 1], j * dv), (us[i + 1], (j + 1) * dv), (us[i], (j + 1) * dv)])
    if pole_front is not None:
        pf = len(verts); verts.append(tuple(pole_front))
        for j in range(M):
            j2 = (j + 1) % N
            faces.append((pf, j, j2)); fuv.append([(0.0, (j + 0.5) * dv), (us[0], j * dv), (us[0], (j + 1) * dv)])
    if pole_back is not None:
        pb = len(verts); verts.append(tuple(pole_back)); b = (R - 1) * N
        for j in range(M):
            j2 = (j + 1) % N
            faces.append((pb, b + j2, b + j)); fuv.append([(1.0, (j + 0.5) * dv), (us[-1], (j + 1) * dv), (us[-1], j * dv)])
    if closed and outward and pole_front is not None and pole_back is not None:
        if signed_volume(verts, faces) < 0:
            faces = [tuple(reversed(f)) for f in faces]; fuv = [list(reversed(u)) for u in fuv]
    return mesh_obj(name, verts, faces, fuv)


def frames_along(pts, up=(0, 0, 1)):
    """Parallel-transport frames (T, N, B) along a polyline."""
    pts = np.asarray(pts, float)
    T = normalize(np.gradient(pts, axis=0))
    up = np.asarray(up, float)
    n = up - T[0] * np.dot(up, T[0])
    if np.linalg.norm(n) < 1e-6:
        n = np.array([1.0, 0, 0]) - T[0] * T[0][0]
    n = normalize(n); Ns = [n]
    for i in range(1, len(pts)):
        n = Ns[-1] - T[i] * np.dot(Ns[-1], T[i]); n = normalize(n); Ns.append(n)
    Ns = np.array(Ns); Bs = np.cross(T, Ns)
    return T, Ns, Bs


def tube(name, pts, radii, n=12, up=(0, 0, 1), caps=True, squash=None, us=None):
    pts = np.asarray(pts, float); radii = np.asarray(radii, float)
    T, Ns, Bs = frames_along(pts, up)
    th = np.linspace(0, TAU, n, endpoint=False)
    sq = np.ones(len(pts)) if squash is None else np.asarray(squash, float)
    rings = (pts[:, None, :] + radii[:, None, None] * (np.cos(th)[None, :, None] * Ns[:, None, :]
             + sq[:, None, None] * np.sin(th)[None, :, None] * Bs[:, None, :]))
    if us is None:
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        us = np.concatenate([[0], np.cumsum(seg)]); us = us / us[-1]
    pf = pts[0] - T[0] * radii[0] * 0.7 if caps else None
    pb = pts[-1] + T[-1] * radii[-1] * 0.7 if caps else None
    return loft(name, rings, us, pf, pb)


def ellipsoid(name, center, radii, rotm=None, nu=24, nv=24):
    """UV-sphere-like loft along local Z; u = 0 at -Z pole, 1 at +Z pole."""
    rotm = np.eye(3) if rotm is None else np.array(rotm)
    t = np.linspace(0, 1, nu + 1)[1:-1]
    lat = -math.pi / 2 + t * math.pi
    th = np.linspace(0, TAU, nv, endpoint=False)
    local = np.stack([np.cos(lat)[:, None] * np.cos(th)[None, :] * radii[0],
                      np.cos(lat)[:, None] * np.sin(th)[None, :] * radii[1],
                      np.repeat(np.sin(lat)[:, None] * radii[2], nv, axis=1)], axis=-1)
    c = np.asarray(center, float)
    rings = local @ rotm.T + c
    pf = c + rotm @ np.array([0, 0, -radii[2]]); pb = c + rotm @ np.array([0, 0, radii[2]])
    return loft(name, rings, t, pf, pb)


def apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data; ob.modifiers.clear(); ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return ob


def subdivide(ob, levels=1):
    m = ob.modifiers.new("sub", "SUBSURF"); m.levels = levels; m.render_levels = levels
    m.quality = 3
    return apply_modifiers(ob)


def set_active(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True); bpy.context.view_layer.objects.active = ob


def join(obs, name):
    set_active(obs[0])
    for o in obs:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = name; ob.data.name = name
    return ob


def tris_of(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


# ---------------------------------------------------------------- images, materials
TEXDIR = tempfile.mkdtemp(prefix="oas_tex_")


def np_image(name, arr, fmt="PNG", noncolor=False):
    """arr: H x W x 4 floats in display (sRGB) space, row 0 at the bottom."""
    arr = np.clip(np.asarray(arr, np.float32), 0, 1)
    h, w, _ = arr.shape
    img = bpy.data.images.new(name, w, h, alpha=True)
    if noncolor:
        img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(arr.ravel())
    ext = "png" if fmt == "PNG" else "jpg"
    img.filepath_raw = os.path.join(TEXDIR, f"{name}.{ext}"); img.file_format = fmt
    img.save()
    img.reload()
    return img


def material(name, color=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, alpha=1.0, base_tex=None,
             tex_alpha=False, normal_tex=None, normal_strength=1.0, mr_tex=None,
             blend=False, double=False, spec=0.5, clip=False):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree; b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb_to_lin(color), 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular"].default_value = spec
    b.inputs["Alpha"].default_value = alpha
    if base_tex is not None:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = base_tex; t.location = (-500, 300)
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
        if tex_alpha:
            nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
    if mr_tex is not None:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = mr_tex; t.location = (-700, 0)
        sep = nt.nodes.new("ShaderNodeSeparateRGB"); sep.location = (-400, 0)
        nt.links.new(t.outputs["Color"], sep.inputs["Image"])
        nt.links.new(sep.outputs["G"], b.inputs["Roughness"])
        nt.links.new(sep.outputs["B"], b.inputs["Metallic"])
    if normal_tex is not None:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = normal_tex; t.location = (-700, -300)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-400, -300)
        nm.inputs["Strength"].default_value = normal_strength
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    if clip:
        mat.blend_method = "CLIP"; mat.alpha_threshold = 0.5; mat.shadow_method = "CLIP"
    elif blend or alpha < 1.0 or tex_alpha:
        mat.blend_method = "BLEND"; mat.shadow_method = "HASHED"
        mat.show_transparent_back = False
    mat.use_backface_culling = not double
    return mat


def srgb_to_lin(c):
    c = np.asarray(c, float)
    return tuple(np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4))


def assign(ob, *mats):
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)
    return ob


# ---------------------------------------------------------------- rig
def make_rig(bones):
    """bones: list of (name, head, tail, parent, connect)."""
    arm = bpy.data.armatures.new("rig")
    ob = link(bpy.data.objects.new("rig", arm))
    set_active(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, h, t, parent, connect in bones:
        eb = arm.edit_bones.new(name); eb.head = Vector(h); eb.tail = Vector(t); eb.roll = 0.0
        if parent:
            eb.parent = arm.edit_bones[parent]; eb.use_connect = connect
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def skin(ob, rig, weights):
    """weights: {bone name: per-vertex array}; normalised here."""
    names = list(weights)
    W = np.stack([np.asarray(weights[n], float) for n in names], axis=1)
    W = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
    for k, n in enumerate(names):
        vg = ob.vertex_groups.new(name=n)
        for i in np.nonzero(W[:, k] > 1e-3)[0]:
            vg.add([int(i)], float(W[i, k]), "REPLACE")
    ob.parent = rig
    m = ob.modifiers.new("rig", "ARMATURE"); m.object = rig
    return ob


def parent_to_bone(ob, rig, bone):
    mw = ob.matrix_world.copy()
    ob.parent = rig; ob.parent_type = "BONE"; ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = mw


def vert_array(ob):
    a = np.zeros(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


# ================================================================= ZEBRAFISH LARVA
# A 7 dpf larva, ~3.9 mm standard length, drawn at 0.36 m. s runs from the snout
# (0) to the end of the caudal fin fold (1); the notochord ends at s = 0.93.
FL = 0.36
S_TIP = 0.93
S_END = 0.933


def fy(s):
    return 0.18 - FL * np.asarray(s, float)


#            snout cap ends                                                          notochord tip
KN_S = [0.045, 0.07, 0.10, 0.13, 0.16, 0.19, 0.23, 0.28, 0.33, 0.38, 0.44, 0.50, 0.58, 0.66, 0.74, 0.82, 0.87, 0.905, 0.93]
KN_H = [0.032, 0.039, 0.0435, 0.0445, 0.0445, 0.045, 0.046, 0.045, 0.041, 0.035, 0.029, 0.0250, 0.0218, 0.0188, 0.0155, 0.0115, 0.0085, 0.0052, 0.0022]
KN_W = [0.027, 0.031, 0.033, 0.033, 0.032, 0.032, 0.031, 0.028, 0.024, 0.020, 0.0165, 0.0138, 0.0118, 0.0098, 0.0080, 0.0060, 0.0046, 0.0030, 0.0016]
KN_C = [-0.0022, -0.0005, 0.0012, 0.0014, 0.0004, -0.0022, -0.0038, -0.0038, -0.0028, -0.0018, -0.0008, 0.0, 0.0005, 0.0008, 0.0010, 0.0012, 0.0014, 0.0016, 0.0018]
KN_N = [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 1.95, 1.9, 1.85, 1.8, 1.75, 1.7, 1.65, 1.62, 1.6, 1.6, 1.6, 1.6]


def fish_prof(s):
    s = np.asarray(s, float)
    sc = np.clip(s, KN_S[0], KN_S[-1])
    H = pchip(KN_S, KN_H, sc); W = pchip(KN_S, KN_W, sc)
    C = pchip(KN_S, KN_C, sc); N = pchip(KN_S, KN_N, sc)
    cap = s < KN_S[0]
    f = np.sqrt(np.clip(1 - (1 - s / KN_S[0]) ** 2, 0, 1))
    H = np.where(cap, KN_H[0] * f, H); W = np.where(cap, KN_W[0] * f, W)
    return H, W, C, N


def fish_P(s, th):
    s = np.asarray(s, float); th = np.asarray(th, float)
    H, W, C, N = fish_prof(s)
    e = 2.0 / N
    x = 0.5 * W * sgnpow(np.cos(th), e)
    z = C + 0.5 * H * sgnpow(np.sin(th), e)
    return np.stack([x, fy(s) * np.ones_like(x), z], axis=-1)


def fish_frame(s, th):
    """Surface point, outward normal, metres per unit s and per radian."""
    ds, dt = 1e-4, 1e-3
    P = fish_P(s, th)
    Ps = (fish_P(s + ds, th) - fish_P(s - ds, th)) / (2 * ds)
    Pt = (fish_P(s, th + dt) - fish_P(s, th - dt)) / (2 * dt)
    n = normalize(np.cross(Pt, Ps))
    return P, n, np.linalg.norm(Ps, axis=-1), np.linalg.norm(Pt, axis=-1)


def fish_notochord_z(s):
    """Dorsal of centre in the trunk (the swim bladder and gut lie below it),
    near the middle of the tail."""
    H, W, C, N = fish_prof(s)
    return C + H * (0.04 + 0.14 * (1 - smoothstep(0.34, 0.56, s)))


def fish_body_texture():
    """RGBA skin in (s, around) space. Almost clear: what the eye picks out is
    the myotome chevrons, the myosepta and the edges, a yellow xanthophore wash
    and a denser head; melanophores are geometry (fish_decals)."""
    Wt, Ht = 512, 256
    rng = np.random.default_rng(7)
    u = (np.arange(Wt) + 0.5) / Wt; v = (np.arange(Ht) + 0.5) / Ht
    s = u * S_END; th = v * TAU
    H, W, C, N = fish_prof(s)
    S, TH = np.meshgrid(s, th)                       # rows = v, cols = u
    Hm = np.broadcast_to(H, S.shape); Nm = np.broadcast_to(N, S.shape)
    zrel = sgnpow(np.sin(TH), 2.0 / Nm); d = np.abs(zrel)
    rgb = np.ones(S.shape + (3,)) * np.array([0.60, 0.62, 0.60])
    head = 1 - smoothstep(0.12, 0.19, S)
    trunk = smoothstep(0.16, 0.2, S) * (1 - smoothstep(S_TIP - 0.03, S_TIP, S))
    alpha = 0.045 + 0.02 * trunk * (1 - smoothstep(0.6, 0.9, S)) + 0.07 * head
    # edges: the dorsal and ventral midlines (neural tube above, gut/fold below)
    alpha = alpha + 0.05 * smoothstep(0.86, 0.99, d)
    rgb = rgb * (1 - 0.2 * head[..., None]) + 0.2 * head[..., None] * np.array([0.62, 0.63, 0.62])
    # xanthophores: a yellow wash dorsally, strongest on the head
    yw = (0.24 * np.clip(zrel, 0, 1) ** 1.3 * (1 - 0.6 * smoothstep(0.4, 0.9, S)) + 0.30 * head * np.clip(zrel + 0.3, 0, 1))
    rgb = rgb * (1 - yw[..., None]) + yw[..., None] * np.array([0.93, 0.76, 0.28])
    alpha = alpha + 0.07 * yw
    # myotomes: chevrons pointing forward, one per somite (~30), and the
    # horizontal myoseptum along the lateral midline
    per = (S_TIP - 0.02 - 0.20) / 30.0
    s_eff = S - 1.0 * d * (Hm * 0.5) / FL
    ph = np.mod(s_eff - 0.20, per)
    dist = np.minimum(ph, per - ph) * FL
    line = np.exp(-(dist / 0.00062) ** 2) * trunk * (1 - smoothstep(0.80, 0.95, d))
    hm = np.exp(-(d * Hm * 0.5 / 0.0006) ** 2) * trunk
    fib = 0.5 + 0.5 * np.sin(TH * 140 + np.sin(S * 300) * 2)      # faint muscle fibres
    mus = trunk * (1 - smoothstep(0.8, 0.95, d)) * 0.025 * fib
    L = np.clip(line + 0.45 * hm, 0, 1)
    rgb = rgb * (1 - 0.35 * L[..., None]) + 0.35 * L[..., None] * np.array([0.84, 0.84, 0.81])
    alpha = alpha + 0.085 * L + mus
    # scattered xanthophore dots (yellow), dorsal half and head
    circ_m = TAU * 0.25 * (H + W)                    # approx metres per unit v
    mpu = S_END * FL / Wt                            # metres per pixel along
    for _ in range(170):
        ss = rng.uniform(0.02, 0.85); tt = rng.uniform(0.2, 0.8) * math.pi
        if rng.random() < 0.2:
            tt = rng.uniform(-0.3, 1.3) * math.pi
        cu = ss / S_END * Wt; cv = (tt % TAU) / TAU * Ht
        mpv = circ_m[int(min(Wt - 1, cu))] / Ht
        r_m = rng.uniform(0.0006, 0.0011)
        ru = int(r_m / mpu * 2.5) + 2; rv = min(int(r_m / mpv * 2.5) + 2, Ht // 2)
        ui = np.arange(int(cu) - ru, int(cu) + ru + 1); vi = np.arange(int(cv) - rv, int(cv) + rv + 1)
        ui = ui[(ui >= 0) & (ui < Wt)]
        if len(ui) == 0:
            continue
        UU, VV = np.meshgrid(ui, vi)
        g = np.exp(-(((UU + 0.5 - cu) * mpu) ** 2 + ((VV + 0.5 - cv) * mpv) ** 2) / r_m ** 2)
        VV = VV % Ht
        k = 0.6 * g[..., None]
        rgb[VV, UU] = rgb[VV, UU] * (1 - k) + k * np.array([0.94, 0.72, 0.22])
        alpha[VV, UU] = alpha[VV, UU] + 0.14 * g
    img = np.concatenate([rgb, np.clip(alpha, 0, 0.9)[..., None]], axis=-1)
    return np_image("fish_body", img, "PNG")


def fin_texture(name, w, h, rays, along_u=True, base=0.035, ray_a=0.03, edge=True, inner_fade=True):
    u = (np.arange(w) + 0.5) / w; v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    if along_u:          # rays at constant u (running across v)
        r = (0.5 + 0.5 * np.cos(TAU * rays * U)) ** 6 * smoothstep(0.1, 0.5, V)
        a = base + ray_a * r
        if edge:
            a = a + 0.08 * smoothstep(0.86, 1.0, V)
        if inner_fade:
            a = a * smoothstep(0.0, 0.18, V)
    else:                # rays at constant v, running along u
        r = (0.5 + 0.5 * np.cos(TAU * rays * V)) ** 6 * smoothstep(0.15, 0.5, U)
        a = base + ray_a * r + (0.05 * smoothstep(0.9, 1.0, U) if edge else 0)
    rgb = np.ones((h, w, 3)) * np.array([0.93, 0.93, 0.90])
    rgb = rgb * (1 - 0.2 * r[..., None]) + 0.2 * r[..., None]
    return np_image(name, np.concatenate([rgb, a[..., None]], axis=-1), "PNG")


def fish_eye_textures():
    """Near-black retina and pupil; golden and silvery iridophore flecks on the
    iris, a thin gold ring round the pupil. Columns run pole to pole (u, as the
    loft lays them), the pupil at u = 1."""
    w, h = 256, 64                                   # u (cols) pole to pole, v (rows) around
    rng = np.random.default_rng(3)
    u = (np.arange(w) + 0.5) / w
    A = np.repeat((math.pi * (1 - u))[None, :], h, axis=0)          # angle from the pupil centre
    TH = np.repeat(((np.arange(h) + 0.5) / h * TAU)[:, None], w, axis=1)
    pupil = 1 - smoothstep(0.38, 0.47, A)
    rim = np.zeros_like(A)
    iris = smoothstep(0.44, 0.6, A) * (1 - smoothstep(1.35, 1.6, A))
    fleck = (rng.random((h, w)) > 0.9).astype(float)
    ventral = 0.5 + 0.5 * -np.sin(TH)
    periph = smoothstep(0.85, 1.25, A)                # the iridophore ring round the iris edge
    sil = iris * (fleck * (0.18 + 0.2 * ventral) + 0.16 * periph * (0.5 + 0.5 * ventral))
    rgb = np.ones((h, w, 3)) * np.array([0.045, 0.036, 0.03])
    gold = np.array([0.62, 0.50, 0.26]); silver = np.array([0.55, 0.58, 0.60])
    tint = gold * (1 - ventral[..., None]) + silver * ventral[..., None]
    rgb = rgb * (1 - sil[..., None]) + sil[..., None] * tint
    rgb = rgb * (1 - 0.8 * rim[..., None]) + 0.8 * rim[..., None] * gold
    rgb = rgb * (1 - pupil[..., None]) + pupil[..., None] * np.array([0.01, 0.012, 0.018])
    base = np_image("fish_eye", np.concatenate([rgb, np.ones((h, w, 1))], axis=-1), "PNG")
    rough = 0.16 + 0.1 * sil - 0.08 * pupil
    metal = np.zeros_like(rough)            # no environment map on the page: keep it dielectric
    mr = np.stack([np.zeros_like(rough), np.clip(rough, 0.04, 1), metal, np.ones_like(rough)], axis=-1)
    return base, np_image("fish_eye_mr", mr, "PNG", noncolor=True)


def swim_bladder_texture():
    """Gas-filled and iridophore-lined: bright along its flanks, dark where it
    turns away above and below (the refractive edge), and capped dorsally by a
    sheet of melanophores. u runs along the bladder, v around it; the loft's
    v = 0.25 faces up."""
    w, h = 128, 128
    rng = np.random.default_rng(9)
    u = (np.arange(w) + 0.5) / w; v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    th = V * TAU
    flank = np.abs(np.cos(th)) ** 0.7                    # 1 on the sides
    ends = 1 - smoothstep(0.3, 0.5, np.abs(U - 0.5))
    bright = flank * (0.55 + 0.45 * ends)
    rgb = np.array([0.18, 0.19, 0.21]) * (1 - bright[..., None]) + np.array([0.68, 0.70, 0.73]) * bright[..., None]
    sheen = np.exp(-((np.abs(np.cos(th)) - 0.85) / 0.12) ** 2) * ends
    rgb = rgb + 0.08 * sheen[..., None] * np.array([1.0, 0.9, 0.7])
    top = np.sin(th)                                    # +1 on top
    edge = 0.55 + 0.08 * np.sin(U * 40) + 0.05 * rng.normal(0, 1, U.shape)
    cap = smoothstep(edge - 0.08, edge + 0.08, top) * smoothstep(0.02, 0.15, U) * (1 - smoothstep(0.85, 0.98, U))
    rgb = rgb * (1 - cap[..., None]) + cap[..., None] * np.array([0.04, 0.035, 0.03])
    return np_image("fish_bladder", np.concatenate([rgb, np.ones((h, w, 1))], axis=-1), "PNG")


def notochord_texture():
    w, h = 512, 32
    u = (np.arange(w) + 0.5) / w; v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    jit = np.cumsum(np.random.default_rng(4).uniform(0.7, 1.3, 90)); jit = jit / jit[-1]
    cell = np.interp(U, np.concatenate([[0], jit]), np.arange(91))
    coins = np.exp(-((np.mod(cell, 1.0) - 0.5) / 0.07) ** 2)
    a = 0.04 + 0.08 * coins
    rgb = np.ones((h, w, 3)) * np.array([0.78, 0.79, 0.77])
    rgb = rgb * (1 - 0.4 * coins[..., None]) + 0.4 * coins[..., None]
    return np_image("fish_notochord", np.concatenate([rgb, a[..., None]], axis=-1), "PNG")


def star_polygon(rng, R, elong=1.0, narms=None, arm=(0.3, 1.0)):
    """A melanophore outline: a dark body with irregular dendrites, some of
    them forked at the tip."""
    n = narms or int(rng.integers(6, 11))
    angs = np.sort(rng.uniform(0, TAU, n))
    gaps = np.diff(np.concatenate([angs, [angs[0] + TAU]]))
    pts = []
    for k in range(n):
        a = angs[k]; half_prev = gaps[k - 1] / 2
        Lk = R * rng.uniform(*arm); hw = R * rng.uniform(0.06, 0.13)
        mid = a - half_prev
        pts.append((rng.uniform(0.2, 0.32) * R * math.cos(mid), rng.uniform(0.2, 0.32) * R * math.sin(mid)))
        bend = rng.normal(0, 0.12)
        off = math.atan2(hw, 0.45 * Lk)
        pts.append((0.45 * Lk * math.cos(a - off), 0.45 * Lk * math.sin(a - off)))
        if Lk > 0.6 * R and rng.random() < 0.55:              # forked dendrite
            f = rng.uniform(0.18, 0.3)
            pts.append((Lk * math.cos(a + bend - f), Lk * math.sin(a + bend - f)))
            pts.append((0.68 * Lk * math.cos(a + bend), 0.68 * Lk * math.sin(a + bend)))
            L2 = Lk * rng.uniform(0.7, 0.95)
            pts.append((L2 * math.cos(a + bend + f), L2 * math.sin(a + bend + f)))
        else:
            pts.append((Lk * math.cos(a + bend), Lk * math.sin(a + bend)))
        pts.append((0.45 * Lk * math.cos(a + off), 0.45 * Lk * math.sin(a + off)))
    p = np.array(pts)
    p[:, 0] *= elong; p[:, 1] /= math.sqrt(elong)
    return p


def fish_decals():
    """Melanophores (stellate, near black) and iridophores (small, silver) laid on
    the skin as thin conforming decals: the stripes of a 7 dpf larva."""
    rng = np.random.default_rng(11)
    spots = []   # (s, th, R, elong, kind)
    up, down = math.pi / 2, 3 * math.pi / 2
    s = 0.19
    while s < S_TIP - 0.02:                          # dorsal stripe
        spots.append((s + rng.uniform(-0.004, 0.004), up + rng.normal(0, 0.05), rng.uniform(0.0030, 0.0042), 2.2, "mel"))
        s += rng.uniform(0.018, 0.028)
    s = 0.49
    while s < S_TIP - 0.02:                          # ventral stripe, behind the vent
        spots.append((s + rng.uniform(-0.004, 0.004), down + rng.normal(0, 0.05), rng.uniform(0.0030, 0.0040), 2.2, "mel"))
        s += rng.uniform(0.016, 0.024)
    s = 0.12
    while s < 0.47:                                  # yolk-sac / ventral trunk stripe, two rows
        for side in (-1, 1):
            spots.append((s + rng.uniform(-0.004, 0.004), down + side * rng.uniform(0.2, 0.4), rng.uniform(0.0032, 0.0042), 1.8, "mel"))
        s += rng.uniform(0.014, 0.02)
    for th0 in (0.0, math.pi):                       # lateral stripe: sparse, along the myoseptum
        for ss in rng.choice([0.36, 0.44, 0.52, 0.59, 0.66, 0.73, 0.80, 0.86], 5, replace=False):
            spots.append((ss + rng.uniform(-0.01, 0.01), th0 + rng.normal(0, 0.04), rng.uniform(0.0038, 0.005), 1.2, "mel"))
    for _ in range(15):                              # head: large stellate cells on top
        spots.append((rng.uniform(0.025, 0.165), up + rng.uniform(-0.75, 0.75), rng.uniform(0.0045, 0.0065), 1.0, "mel"))
    s = 0.2
    while s < 0.9:                                   # iridophores between the dorsal/ventral melanophores
        spots.append((s, up + rng.normal(0, 0.03), 0.0011, 1.8, "iri"))
        if s > 0.5:
            spots.append((s + 0.01, down + rng.normal(0, 0.03), 0.0010, 1.8, "iri"))
        s += rng.uniform(0.035, 0.05)
    verts, faces, mats = [], [], []
    for ss, tt, R, el, kind in spots:
        if kind == "mel":
            poly = (star_polygon(rng, R, el) if el < 1.5 else
                    star_polygon(rng, R, el, narms=int(rng.integers(3, 6)), arm=(0.45, 0.85)))
        else:
            a = np.linspace(0, TAU, 10, endpoint=False)
            poly = np.stack([R * el * np.cos(a), R / el * np.sin(a)], axis=1)
        pts2 = np.vstack([[0, 0], poly])
        P0, n0, ms, mt = fish_frame(np.array([ss]), np.array([tt]))
        sv = ss + pts2[:, 0] / ms[0]; tv = tt + pts2[:, 1] / mt[0]
        sv = np.clip(sv, 0.003, S_TIP - 0.004)
        P, n, _, _ = fish_frame(sv, tv)
        P = P + n * (0.00045 if kind == "mel" else 0.0006)
        base = len(verts); verts.extend(P.tolist())
        m = len(poly)
        flip = None
        for k in range(m):
            f = (base, base + 1 + k, base + 1 + (k + 1) % m)
            if flip is None:
                fn = np.cross(P[f[1] - base] - P[0], P[f[2] - base] - P[0])
                flip = np.dot(fn, n0[0]) < 0
            faces.append(tuple(reversed(f)) if flip else f); mats.append(0 if kind == "mel" else 1)
    ob = mesh_obj("pigment", verts, faces, smooth=False)
    ob["mats"] = mats
    return ob


def fish_fin_fold():
    """The median fin fold: a sheet in the sagittal plane that starts low on the
    dorsal mid-trunk, deepens backwards, rounds the tail as a paddle past the
    notochord tip and runs forward below, notched at the vent, to the yolk."""
    S_A = 0.86                                     # the rounded caudal paddle starts here

    def fd(s):
        return 0.0015 + 0.0175 * smoothstep(0.36, 0.72, s)

    def fv(s):
        pre = 0.0055 * smoothstep(0.30, 0.40, s) * (1 - smoothstep(0.45, 0.475, s))
        return pre + 0.0015 * smoothstep(0.47, 0.5, s) + 0.0165 * smoothstep(0.49, 0.72, s)
    Ht, Wt, Ct, Nt = fish_prof(S_TIP)

    def half(s, f):
        H, W, C, N = fish_prof(min(s, S_TIP))
        g = 0.5 * H + f(s)
        if s > S_A:
            H2, _, _, _ = fish_prof(S_A)
            ga = 0.5 * H2 + f(S_A)
            g = ga * math.sqrt(max(0.0, 1 - ((s - S_A) / (1.0 - S_A)) ** 2))
        return g
    tail = np.linspace(0.80, 1.0, 24)
    rows = 5
    verts, faces, fuv = [], [], []
    for sign, f, s0, u0 in ((1, fd, 0.36, 0.0), (-1, fv, 0.30, 0.5)):
        cols = np.concatenate([np.linspace(s0, 0.80, 26)[:-1], tail])
        base = len(verts); n = len(cols)
        for s in cols:
            H, W, C, N = fish_prof(min(s, S_TIP))
            y = float(fy(s))
            zin = (C + sign * 0.36 * H) if s <= S_TIP else Ct
            zc = C if s <= S_TIP else Ct
            zout = zc + sign * max(half(s, f), 0.36 * H if s <= S_TIP else 0.0)
            for k in range(rows):
                t = k / (rows - 1)
                verts.append((0.0, y, zin + (zout - zin) * t))
        for i in range(n - 1):
            for k in range(rows - 1):
                q = (base + i * rows + k, base + (i + 1) * rows + k, base + (i + 1) * rows + k + 1, base + i * rows + k + 1)
                if sign < 0:
                    q = tuple(reversed(q))
                faces.append(q)
                uv = [(u0 + 0.5 * i / (n - 1), k / (rows - 1)), (u0 + 0.5 * (i + 1) / (n - 1), k / (rows - 1)),
                      (u0 + 0.5 * (i + 1) / (n - 1), (k + 1) / (rows - 1)), (u0 + 0.5 * i / (n - 1), (k + 1) / (rows - 1))]
                fuv.append(list(reversed(uv)) if sign < 0 else uv)
    ob = mesh_obj("fin_fold", verts, faces, fuv)
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-7)
    bm.to_mesh(ob.data); bm.free()
    return ob


def fish_pec_fin(side):
    """A small round paddle behind the ear, held back against the flank."""
    s0 = 0.20
    H, W, C, N = fish_prof(s0)
    base = np.array([side * 0.42 * W, float(fy(s0)), C - 0.05 * H])
    d = normalize(np.array([side * 0.45, -1.0, -0.10]))
    e1 = normalize(np.array([0.0, 0.25, 1.0]) - d * np.dot(d, [0.0, 0.25, 1.0]))   # fin plane ~ vertical
    e2 = normalize(np.cross(d, e1))
    Lf, wmax, thick = 0.019, 0.0082, 0.0006
    t = np.linspace(0.0, 1.0, 14)[1:-1]
    th = np.linspace(0, TAU, 20, endpoint=False)
    w = wmax * np.sqrt(np.clip(1 - ((t - 0.6) / 0.6) ** 2, 0.03, 1))
    rings = (base[None, None] + (t * Lf)[:, None, None] * d[None, None]
             + (w[:, None] * np.cos(th)[None, :])[..., None] * e1[None, None]
             + (thick * np.sin(th)[None, :] * np.ones_like(t)[:, None])[..., None] * e2[None, None])
    return loft(f"pec_fin_{'L' if side < 0 else 'R'}", rings, t, base - d * 0.0004, base + d * Lf)


def build_fish():
    reset()
    # ---- body
    s_front = KN_S[0] * (1 - np.cos(np.linspace(0.07, 1, 12) * math.pi / 2))
    s_main = np.linspace(KN_S[0], S_TIP, 104)[1:]
    ss = np.concatenate([s_front, s_main])
    th = np.linspace(0, TAU, 36, endpoint=False)
    rings = fish_P(ss[:, None], th[None, :])
    body = loft("fish_body", rings, ss / S_END,
                pole_front=(0.0, float(fy(0.0)), KN_C[0]),
                pole_back=(0.0, float(fy(S_END)), KN_C[-1]))
    body_mat = material("fish_skin", base_tex=fish_body_texture(), tex_alpha=True, rough=0.18, spec=0.6)
    assign(body, body_mat)
    # ---- median fin fold and pectoral fins
    fold = fish_fin_fold(); subdivide(fold, 1)
    fold_mat = material("fin_fold", base_tex=fin_texture("fish_fold", 512, 64, 150), tex_alpha=True, rough=0.2, double=True)
    assign(fold, fold_mat)
    pec_mat = material("pec_fin", base_tex=fin_texture("fish_pec", 128, 64, 7, along_u=False, base=0.04, ray_a=0.06), tex_alpha=True, rough=0.2, double=True)
    pecs = []
    for side in (-1, 1):
        p = fish_pec_fin(side); assign(p, pec_mat); pecs.append(p)
    # ---- organs seen through the body
    organs = []
    silver = material("swim_bladder", base_tex=swim_bladder_texture(), rough=0.12, spec=1.0)
    sb_s = 0.29; H, W, C, N = fish_prof(sb_s)
    sb_top = float(fish_notochord_z(sb_s)) - 0.0032 - 0.0012
    sb_r = (0.0088, 0.0086, 0.0180)
    sb_c = (0.0, float(fy(sb_s)), sb_top - sb_r[1])
    sb_rot = np.array(rot("X", 90 + 8))            # long axis (local Z) along +Y, front tipped up
    o = ellipsoid("swim_bladder", sb_c, sb_r, sb_rot, 20, 20); assign(o, silver); organs.append(o)
    melanin = material("melanophore", (0.015, 0.012, 0.011), rough=0.85, spec=0.25)
    yk_s = 0.215; H, W, C, N = fish_prof(yk_s)
    yolk = ellipsoid("yolk", (0.0, float(fy(yk_s)), float(C - 0.30 * H)), (0.0055, 0.0045, 0.008), np.array(rot("X", 90)), 16, 16)
    assign(yolk, material("yolk", (0.85, 0.72, 0.42), rough=0.35, alpha=0.4)); organs.append(yolk)
    gs = np.linspace(0.21, 0.485, 30); H, W, C, N = fish_prof(gs)
    gut_pts = np.stack([np.zeros_like(gs), fy(gs), C - H * (0.37 - 0.05 * smoothstep(0.36, 0.485, gs))], axis=1)
    gut = tube("gut", gut_pts, 0.0032 - 0.0013 * smoothstep(0.25, 0.48, gs), 10)
    assign(gut, material("gut", (0.62, 0.53, 0.36), rough=0.4, alpha=0.15)); organs.append(gut)
    ns = np.linspace(0.165, S_TIP - 0.003, 60)
    no_pts = np.stack([np.zeros_like(ns), fy(ns), fish_notochord_z(ns)], axis=1)
    noto = tube("notochord", no_pts, 0.0032 - 0.0021 * smoothstep(0.3, S_TIP, ns), 12)
    assign(noto, material("notochord", base_tex=notochord_texture(), tex_alpha=True, rough=0.3)); organs.append(noto)
    ot_s = 0.172; H, W, C, N = fish_prof(ot_s)
    otic_mat = material("otic_vesicle", (0.80, 0.83, 0.85), rough=0.1, alpha=0.08)
    otolith_mat = material("otolith", (0.97, 0.96, 0.92), rough=0.3)
    for side in (-1, 1):
        oc = np.array([side * 0.26 * W, float(fy(ot_s)), C + 0.12 * H])
        o = ellipsoid(f"otic_{side}", oc, (0.0045, 0.0045, 0.0065), np.array(rot("X", 90)), 12, 12)
        assign(o, otic_mat); organs.append(o)
        for dy in (0.003, -0.0028):
            o = ellipsoid(f"otolith_{side}_{dy}", oc + np.array([0, dy, -0.0008]), (0.0012, 0.0012, 0.0012), None, 8, 8)
            assign(o, otolith_mat); organs.append(o)
    ht_s = 0.13; H, W, C, N = fish_prof(ht_s)
    heart = ellipsoid("heart", (0.0, float(fy(ht_s)), C - 0.34 * H), (0.0038, 0.0034, 0.0052), np.array(rot("X", 60)), 12, 12)
    assign(heart, material("heart", (0.72, 0.30, 0.28), rough=0.4, alpha=0.35)); organs.append(heart)
    organs_ob = join(organs, "organs")
    # ---- pigment
    pig = fish_decals()
    irid = material("iridophore", (0.52, 0.54, 0.56), rough=0.15, spec=1.0)
    assign(pig, melanin, irid)
    for p, mi in zip(pig.data.polygons, pig["mats"]):
        p.material_index = mi
    del pig["mats"]
    # ---- eyes: lofted along local +Z (pupil at +Z), then turned to look out
    eye_base, eye_mr = fish_eye_textures()
    eye_mat = material("fish_eye", base_tex=eye_base, mr_tex=eye_mr, rough=0.3)
    eyes = []
    es = 0.088; H, W, C, N = fish_prof(es)
    for side, nm in ((-1, "eye_L"), (1, "eye_R")):
        center = Vector((side * 0.0192, float(fy(es)), 0.0022))
        look = Vector((side * 1.0, 0.35, -0.08)).normalized()
        R = look.to_track_quat("Z", "Y").to_matrix()
        o = ellipsoid(nm, (0, 0, 0), (0.0158, 0.0158, 0.0125), np.array(R), 22, 24)
        o.location = center
        assign(o, eye_mat); eyes.append(o)
    # ---- rig: spine_0 behind the head ... spine_11 near the tail tip
    st = np.linspace(0.165, 0.99, 13)
    zb = fish_notochord_z(np.minimum(st, S_TIP))
    bones = []
    for k in range(12):
        bones.append((f"spine_{k}", (0.0, float(fy(st[k])), float(zb[k])), (0.0, float(fy(st[k + 1])), float(zb[k + 1])),
                      f"spine_{k - 1}" if k else None, k > 0))
    rig = make_rig(bones)
    mids = 0.5 * (st[:-1] + st[1:])

    def weights_for(ob):
        y = vert_array(ob)[:, 1]
        s = (0.18 - y) / FL
        out = {}
        for k in range(12):
            if k == 0:
                w = 1 - smoothstep(mids[0], mids[1], s)
            elif k == 11:
                w = smoothstep(mids[10], mids[11], s)
            else:
                w = np.minimum(smoothstep(mids[k - 1], mids[k], s), 1 - smoothstep(mids[k], mids[k + 1], s))
            out[f"spine_{k}"] = w
        return out
    for ob in (body, fold, organs_ob, pig):
        skin(ob, rig, weights_for(ob))
    for ob in eyes + pecs:
        parent_to_bone(ob, rig, "spine_0")
    return [body, fold, organs_ob, pig] + eyes + pecs


# ================================================================= MOUSE
# An adult C57BL/6J (black, belly a little lighter) sitting up on its haunches
# looking forward, forepaws raised before the chest. ~9 cm body x 3.3 = 0.30 m.
MB_K = 0.575          # a lone metaball's surface sits at 0.575 x its radius


def mb_family(name, res):
    mb = bpy.data.metaballs.new(name); mb.resolution = res; mb.render_resolution = res
    mb.threshold = 0.6; mb.update_method = "UPDATE_ALWAYS"
    return link(bpy.data.objects.new(name, mb)), mb


def mb_ell(mb, co, axes, rot_deg=(0, 0, 0), stiff=2.0, neg=False):
    """An ellipsoid element whose isolated surface has semi-axes `axes`."""
    a = np.asarray(axes, float); r = a.max() / MB_K
    e = mb.elements.new(type="ELLIPSOID"); e.co = co; e.radius = r; e.stiffness = stiff
    e.size_x, e.size_y, e.size_z = (a / a.max()).tolist()
    e.rotation = rot("Z", rot_deg[2]).to_4x4().to_quaternion() @ rot("Y", rot_deg[1]).to_4x4().to_quaternion() @ rot("X", rot_deg[0]).to_4x4().to_quaternion()
    e.use_negative = neg
    return e


def mb_limb(mb, a, b, r0, r1, n=None, stiff=2.0):
    """A tapered chain of balls from a to b (surface radii r0 -> r1)."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    L = np.linalg.norm(b - a)
    n = n or max(2, int(L / (0.7 * min(r0, r1))) + 1)
    for t in np.linspace(0, 1, n):
        r = r0 + (r1 - r0) * t
        e = mb.elements.new(type="BALL"); e.co = (a + (b - a) * t).tolist(); e.radius = r / MB_K; e.stiffness = stiff


def mb_to_mesh(ob, name):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    mo = link(bpy.data.objects.new(name, me))
    fam = ob.name.split(".")[0]
    for o in list(bpy.data.objects):
        if o.type == "META" and o.name.split(".")[0] == fam:
            d = o.data; bpy.data.objects.remove(o); bpy.data.metaballs.remove(d)
    return mo


def remesh(ob, voxel, smooth_iter=0, decimate=None):
    m = ob.modifiers.new("remesh", "REMESH"); m.mode = "VOXEL"; m.voxel_size = voxel; m.use_smooth_shade = True
    if smooth_iter:
        s = ob.modifiers.new("smooth", "SMOOTH"); s.iterations = smooth_iter; s.factor = 0.5
    if decimate:
        d = ob.modifiers.new("dec", "DECIMATE"); d.ratio = decimate
    apply_modifiers(ob)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


MOUSE = dict(
    neck=(0.0, 0.050, 0.128),
    head_c=(0.0, 0.080, 0.150),
    nose=(0.0, 0.1505, 0.1385),
    eye=(0.0232, 0.101, 0.1575),
    ear_base=(0.0215, 0.060, 0.1705),
    pad=(0.0122, 0.127, 0.1385),
    wrist=(0.0140, 0.098, 0.094),
    tail_base=(0.0, -0.074, 0.020),
)


def decimate_to(ob, target_tris):
    t = tris_of(ob)
    if t > target_tris:
        d = ob.modifiers.new("dec", "DECIMATE"); d.ratio = target_tris / t
        apply_modifiers(ob)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def mouse_body_metaballs():
    """One continuous furred surface: haunches, belly, chest, shoulders, head,
    snout, whisker pads and the forelimbs down to the wrist."""
    ob, mb = mb_family("MouseBody", 0.0035)
    E = lambda co, ax, r=(0, 0, 0), st=2.0, neg=False: mb_ell(mb, co, ax, r, st, neg)
    # haunches and rump, resting on the desk
    E((0.0, -0.030, 0.045), (0.041, 0.050, 0.044))
    for sx in (-1, 1):
        E((sx * 0.026, -0.008, 0.033), (0.022, 0.040, 0.030), (-12, 0, sx * 8))
    # belly and flank leaning forward, chest, shoulders: the back one long curve
    E((0.0, -0.002, 0.078), (0.037, 0.046, 0.054), (-48, 0, 0))
    E((0.0, 0.028, 0.107), (0.035, 0.040, 0.040), (-50, 0, 0))
    E((0.0, 0.046, 0.131), (0.032, 0.040, 0.032), (-35, 0, 0))
    # head: cranium, cheeks, snout, chin
    E(MOUSE["head_c"], (0.027, 0.040, 0.026), (-12, 0, 0))
    for sx in (-1, 1):
        E((sx * 0.017, 0.091, 0.143), (0.015, 0.024, 0.017), (-12, 0, 0))
        E((sx * 0.0100, 0.120, 0.1385), (0.0090, 0.015, 0.0095), (-10, 0, 0))    # whisker pads
    E((0.0, 0.115, 0.1435), (0.0160, 0.026, 0.0145), (-14, 0, 0))              # snout
    E((0.0, 0.1375, 0.1395), (0.0085, 0.0120, 0.0085), (-12, 0, 0))            # snout tip
    E((0.0, 0.107, 0.1310), (0.0110, 0.021, 0.0078), (-6, 0, 0))              # chin / lower jaw
    # forelimbs (furred to the wrist)
    for sx in (-1, 1):
        sh = (sx * 0.025, 0.050, 0.108); el = (sx * 0.024, 0.066, 0.086)
        wr = (sx * MOUSE["wrist"][0], MOUSE["wrist"][1], MOUSE["wrist"][2])
        mb_limb(mb, sh, el, 0.0095, 0.0066)
        mb_limb(mb, el, wr, 0.0060, 0.0042)
        # hind ankle, in fur, from under the haunch towards the foot
        mb_limb(mb, (sx * 0.034, -0.026, 0.016), (sx * 0.038, 0.000, 0.008), 0.0100, 0.0062)
    E(MOUSE["tail_base"], (0.011, 0.014, 0.011))
    return ob


def mouse_fur_bake(body):
    """UV the body, then bake a fur colour and a fur normal map from procedural
    shaders whose streaks follow a per-vertex hair direction."""
    me = body.data
    set_active(body)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.006)
    bpy.ops.object.mode_set(mode="OBJECT")
    uv_main = me.uv_layers[0]; uv_main.name = "UVMap"
    co = vert_array(body)
    nrm = np.zeros(len(co) * 3); me.vertices.foreach_get("normal", nrm); nrm = nrm.reshape(-1, 3)
    # factors: belly (lighter), and hair direction (tangent to the surface)
    hc = np.array(MOUSE["head_c"])
    dh = (co - hc) / np.array([0.042, 0.075, 0.036]); headness = 1 - smoothstep(0.8, 1.2, np.linalg.norm(dh, axis=1))
    belly = smoothstep(0.05, 0.6, nrm @ normalize(np.array([0.0, 0.8, -0.6]))) * (1 - headness)
    belly *= smoothstep(0.035, 0.06, co[:, 2]) * (1 - smoothstep(0.125, 0.14, co[:, 2]))
    throat = smoothstep(0.2, 0.7, -nrm[:, 2]) * headness * 0.7
    belly = np.clip(belly + throat, 0, 1)
    flow_body = normalize(np.array([0.0, -0.55, -0.83]))
    flow = np.where(headness[:, None] > 0.5, np.array([0.0, -1.0, -0.15]), flow_body)
    armness = (co[:, 2] < 0.12) & (co[:, 1] > 0.045) & (np.abs(co[:, 0]) > 0.008)
    flow[armness] = normalize(np.array([0.0, 0.6, -0.8]))
    flow = normalize(flow - nrm * np.sum(flow * nrm, axis=1, keepdims=True))
    lay_a = me.uv_layers.new(name="F_A"); lay_b = me.uv_layers.new(name="F_B")
    li = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", li)
    ua = np.stack([belly[li], (flow[li, 0] + 1) / 2], axis=1)
    ub = np.stack([(flow[li, 1] + 1) / 2, (flow[li, 2] + 1) / 2], axis=1)
    lay_a.data.foreach_set("uv", ua.ravel()); lay_b.data.foreach_set("uv", ub.ravel())
    me.uv_layers.active = uv_main; uv_main.active_render = True

    col_img = bpy.data.images.new("mouse_fur", 512, 512, alpha=False)
    nrm_img = bpy.data.images.new("mouse_fur_n", 512, 512, alpha=False)
    nrm_img.colorspace_settings.name = "Non-Color"
    mat = bpy.data.materials.new("bake"); mat.use_nodes = True
    nt = mat.node_tree; N = nt.nodes; Lk = nt.links.new
    for n in list(N):
        N.remove(n)
    out = N.new("ShaderNodeOutputMaterial")
    tc = N.new("ShaderNodeTexCoord")
    ua_n = N.new("ShaderNodeUVMap"); ua_n.uv_map = "F_A"
    ub_n = N.new("ShaderNodeUVMap"); ub_n.uv_map = "F_B"
    sa = N.new("ShaderNodeSeparateXYZ"); Lk(ua_n.outputs["UV"], sa.inputs[0])
    sb = N.new("ShaderNodeSeparateXYZ"); Lk(ub_n.outputs["UV"], sb.inputs[0])
    comb = N.new("ShaderNodeCombineXYZ")
    Lk(sa.outputs["Y"], comb.inputs["X"]); Lk(sb.outputs["X"], comb.inputs["Y"]); Lk(sb.outputs["Y"], comb.inputs["Z"])
    dmul = N.new("ShaderNodeVectorMath"); dmul.operation = "MULTIPLY"
    Lk(comb.outputs[0], dmul.inputs[0]); dmul.inputs[1].default_value = (2, 2, 2)
    dvec = N.new("ShaderNodeVectorMath"); dvec.operation = "ADD"
    Lk(dmul.outputs[0], dvec.inputs[0]); dvec.inputs[1].default_value = (-1, -1, -1)
    dnorm = N.new("ShaderNodeVectorMath"); dnorm.operation = "NORMALIZE"; Lk(dvec.outputs[0], dnorm.inputs[0])

    def streak_coords(k_iso, k_along):
        dot = N.new("ShaderNodeVectorMath"); dot.operation = "DOT_PRODUCT"
        Lk(tc.outputs["Object"], dot.inputs[0]); Lk(dnorm.outputs[0], dot.inputs[1])
        m = N.new("ShaderNodeMath"); m.operation = "MULTIPLY"; Lk(dot.outputs["Value"], m.inputs[0]); m.inputs[1].default_value = k_along - k_iso
        sc = N.new("ShaderNodeVectorMath"); sc.operation = "SCALE"; Lk(dnorm.outputs[0], sc.inputs[0]); Lk(m.outputs[0], sc.inputs["Scale"])
        iso = N.new("ShaderNodeVectorMath"); iso.operation = "SCALE"; Lk(tc.outputs["Object"], iso.inputs[0]); iso.inputs["Scale"].default_value = k_iso
        add = N.new("ShaderNodeVectorMath"); add.operation = "ADD"; Lk(iso.outputs[0], add.inputs[0]); Lk(sc.outputs[0], add.inputs[1])
        return add.outputs[0]
    # fine hairs, and the clumps they lie in, both combed along the flow
    p1 = streak_coords(1300.0, 120.0)
    n1 = N.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 1.0; n1.inputs["Detail"].default_value = 3.0; n1.inputs["Roughness"].default_value = 0.5
    Lk(p1, n1.inputs["Vector"])
    p2 = streak_coords(420.0, 50.0)
    n2 = N.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 1.0; n2.inputs["Detail"].default_value = 2.0
    Lk(p2, n2.inputs["Vector"])
    # colour: black-brown back, a greyer brown belly; hair tips and clump crests lighter
    ramp_mix = N.new("ShaderNodeMixRGB"); ramp_mix.blend_type = "MIX"
    ramp_mix.inputs["Color1"].default_value = (*srgb_to_lin((0.064, 0.055, 0.049)), 1)
    ramp_mix.inputs["Color2"].default_value = (*srgb_to_lin((0.17, 0.148, 0.135)), 1)
    Lk(sa.outputs["X"], ramp_mix.inputs["Fac"])
    var = N.new("ShaderNodeMath"); var.operation = "MULTIPLY_ADD"
    Lk(n1.outputs["Fac"], var.inputs[0]); var.inputs[1].default_value = 1.6; var.inputs[2].default_value = 0.2
    var2 = N.new("ShaderNodeMath"); var2.operation = "MULTIPLY_ADD"
    Lk(n2.outputs["Fac"], var2.inputs[0]); var2.inputs[1].default_value = 1.2; var2.inputs[2].default_value = 0.4
    vv = N.new("ShaderNodeMath"); vv.operation = "MULTIPLY"; Lk(var.outputs[0], vv.inputs[0]); Lk(var2.outputs[0], vv.inputs[1])
    col = N.new("ShaderNodeMixRGB"); col.blend_type = "MULTIPLY"; col.inputs["Fac"].default_value = 1.0
    Lk(ramp_mix.outputs[0], col.inputs["Color1"])
    vcol = N.new("ShaderNodeCombineRGB")
    for c in "RGB":
        Lk(vv.outputs[0], vcol.inputs[c])
    Lk(vcol.outputs[0], col.inputs["Color2"])
    emit = N.new("ShaderNodeEmission"); Lk(col.outputs[0], emit.inputs["Color"])
    # normal: bump from the same streaks
    hsum = N.new("ShaderNodeMath"); hsum.operation = "MULTIPLY_ADD"
    Lk(n2.outputs["Fac"], hsum.inputs[0]); hsum.inputs[1].default_value = 0.5; Lk(n1.outputs["Fac"], hsum.inputs[2])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 1.0; bump.inputs["Distance"].default_value = 0.0008
    Lk(hsum.outputs[0], bump.inputs["Height"])
    bsdf = N.new("ShaderNodeBsdfPrincipled"); Lk(bump.outputs["Normal"], bsdf.inputs["Normal"])
    tex = N.new("ShaderNodeTexImage")
    body.data.materials.clear(); body.data.materials.append(mat)
    sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 4
    sc.render.bake.margin = 6
    set_active(body)
    N.active = tex; tex.select = True
    for shader, img, kind in ((emit, col_img, "EMIT"), (bsdf, nrm_img, "NORMAL")):
        Lk(shader.outputs[0], out.inputs["Surface"]); tex.image = img
        if kind == "NORMAL":
            bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", margin=6, use_clear=True)
        else:
            bpy.ops.object.bake(type="EMIT", margin=6, use_clear=True)
    for img, nm in ((col_img, "mouse_fur"), (nrm_img, "mouse_fur_n")):
        img.filepath_raw = os.path.join(TEXDIR, nm + ".jpg"); img.file_format = "JPEG"; img.save(); img.reload()
    cpx = np.array(col_img.pixels[:], np.float32).reshape(-1, 4)[:, :3]
    skin_avg = np.median(cpx[cpx.sum(1) > 0.05], axis=0)          # ignore the empty UV background
    tips_img = hair_tip_tile(skin_avg)
    me.uv_layers.remove(me.uv_layers["F_A"]); me.uv_layers.remove(me.uv_layers["F_B"])
    bpy.data.materials.remove(mat)
    fur = material("mouse_fur", base_tex=col_img, normal_tex=nrm_img, normal_strength=0.7, rough=0.75, spec=0.3)
    tips_mat = material("mouse_fur_tips", base_tex=tips_img, tex_alpha=True, rough=0.85, spec=0.25, clip=True)
    tips_mat.alpha_threshold = 0.45     # above the tile's mean alpha: when mipmapped far away the shell drops out, leaving the skin
    assign(body, fur)
    return fur, tips_mat


FUR_TILE = 14.0      # the hair-tip tile repeats this many times across the body's UV square


def hair_tip_tile(color):
    """A tileable stipple of hair tips (short, slightly elongated dots) for the
    outer fur shell: alpha is the hair, colour a little lighter than the skin."""
    n = 256
    rng = np.random.default_rng(17)
    a = np.zeros((n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    for _ in range(1500):
        cx, cy = rng.uniform(0, n, 2); ang = rng.uniform(0, math.pi)
        r = rng.uniform(1.4, 2.4); el = rng.uniform(1.4, 2.6)
        dx = (xx - cx + n / 2) % n - n / 2; dy = (yy - cy + n / 2) % n - n / 2
        u = dx * math.cos(ang) + dy * math.sin(ang); v = -dx * math.sin(ang) + dy * math.cos(ang)
        a = np.maximum(a, np.exp(-((u / (r * el)) ** 2 + (v / r) ** 2)))
    a = np.round(np.clip(a * 1.15, 0, 1) * 16) / 16
    print(f"hair tile: mean alpha {a.mean():.3f}, texels over the cut {np.mean(a > 0.45):.3f}")
    rgb = np.ones((n, n, 3)) * np.asarray(color) * 0.75
    return np_image("mouse_fur_tips", np.concatenate([rgb, a[..., None]], axis=-1), "PNG")


def mouse_tail_textures():
    w, h = 512, 64
    u = (np.arange(w) + 0.5) / w; v = (np.arange(h) + 0.5) / h
    U, V = np.meshgrid(u, v)
    rings = 150
    ph = U * rings
    stagger = np.floor(ph) % 2 * 0.5
    ring_d = np.abs(np.mod(ph, 1.0) - 0.5) * 2                       # 0 mid-scale, 1 at groove
    scales_around = 22
    pv = V * scales_around + stagger
    scale_d = np.abs(np.mod(pv, 1.0) - 0.5) * 2
    height = (1 - ring_d ** 3) * 0.8 + (1 - scale_d ** 6) * 0.2
    under = 0.5 + 0.5 * np.cos((V - 0.75) * TAU)                   # v = 0.75 faces the desk
    base = np.array([0.22, 0.18, 0.17]) * (1 - under[..., None]) + np.array([0.38, 0.29, 0.28]) * under[..., None]
    rgb = base * (0.78 + 0.22 * height[..., None])
    rgb += np.random.default_rng(5).normal(0, 0.012, rgb.shape)
    col = np_image("mouse_tail", np.concatenate([rgb, np.ones((h, w, 1))], axis=-1), "JPEG")
    # tangent-space normal from the height (u along the tail, v around)
    k = 2.2
    du = np.gradient(height, axis=1) * k * 3.0; dv = np.gradient(height, axis=0) * k * 0.6
    n = normalize(np.stack([-du, -dv, np.ones_like(du)], axis=-1))
    nimg = np_image("mouse_tail_n", np.concatenate([n * 0.5 + 0.5, np.ones((h, w, 1))], axis=-1), "JPEG", noncolor=True)
    return col, nimg


def mouse_tail_path():
    """Tail lying on the desk behind the mouse: a gentle S, 0.25 m long."""
    ctrl = np.array([[0.0, -0.060, 0.030], [0.0, -0.080, 0.016], [0.004, -0.105, 0.0085],
                     [0.018, -0.150, 0.007], [0.028, -0.200, 0.006], [0.018, -0.250, 0.005],
                     [-0.010, -0.290, 0.004], [-0.040, -0.315, 0.003]])
    # Catmull-Rom through the control points, then resample by arc length
    P = np.vstack([ctrl[0] * 2 - ctrl[1], ctrl, ctrl[-1] * 2 - ctrl[-2]])
    dense = []
    for i in range(1, len(P) - 2):
        for t in np.linspace(0, 1, 40, endpoint=False):
            p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(ctrl[-1]); dense = np.array(dense)
    seg = np.linalg.norm(np.diff(dense, axis=0), axis=1); arc = np.concatenate([[0], np.cumsum(seg)])
    return dense, arc


def mouse_tail():
    dense, arc = mouse_tail_path()
    total_visible = 0.25
    start = 0.018                                   # the first 18 mm are inside the rump
    L = min(arc[-1], start + total_visible)
    a = np.linspace(0, L, 150)
    pts = np.stack([np.interp(a, arc, dense[:, k]) for k in range(3)], axis=1)
    t = a / L
    radii = 0.0088 * (1 - t) ** 0.75 + 0.0019 * t
    # sits on the desk: centre height = radius past the rump
    ground = smoothstep(0.08, 0.2, t)
    pts[:, 2] = pts[:, 2] * (1 - ground) + radii * ground
    ob = tube("tail", pts, radii, 12, up=(0, 0, 1), squash=np.ones_like(t))
    col, nimg = mouse_tail_textures()
    assign(ob, material("mouse_tail", base_tex=col, normal_tex=nimg, normal_strength=1.0, rough=0.5, spec=0.4))
    return ob, pts, a


def ear_texture():
    """Thin pink skin: darker and denser at the base, veins fanning up from it,
    the rim paler and more translucent."""
    n = 128
    rng = np.random.default_rng(31)
    v, u = np.mgrid[0:n, 0:n] / (n - 1.0)
    r = np.sqrt(((u - 0.5) * 2) ** 2 + ((v - 0.5) * 2) ** 2)
    rgb = np.ones((n, n, 3)) * np.array([0.80, 0.58, 0.58])
    base = 1 - smoothstep(0.05, 0.45, v)
    rgb = rgb * (1 - 0.35 * base[..., None]) + 0.35 * base[..., None] * np.array([0.45, 0.33, 0.33])
    rim = smoothstep(0.8, 0.98, r)
    rgb = rgb * (1 - 0.3 * rim[..., None]) + 0.3 * rim[..., None] * np.array([0.90, 0.72, 0.70])
    vein = np.zeros((n, n))
    for k in range(5):
        x, y = 0.5 + rng.normal(0, 0.05), 0.04
        ang = math.pi / 2 + (k - 2) * 0.32 + rng.normal(0, 0.08)
        for step in range(46):
            ang += rng.normal(0, 0.12); x += 0.018 * math.cos(ang); y += 0.018 * math.sin(ang)
            w = 1.3 * (1 - step / 60)
            vein = np.maximum(vein, np.exp(-(((u - x) * n) ** 2 + ((v - y) * n) ** 2) / w ** 2) * (1 - step / 55))
            if step in (14, 26):
                bx, by, ba = x, y, ang + rng.choice([-0.7, 0.7])
                for st2 in range(18):
                    ba += rng.normal(0, 0.15); bx += 0.016 * math.cos(ba); by += 0.016 * math.sin(ba)
                    vein = np.maximum(vein, 0.6 * np.exp(-(((u - bx) * n) ** 2 + ((v - by) * n) ** 2)) * (1 - st2 / 20))
    rgb = rgb * (1 - 0.45 * vein[..., None]) + 0.45 * vein[..., None] * np.array([0.62, 0.30, 0.34])
    alpha = 0.93 - 0.13 * rim
    return np_image("mouse_ear", np.concatenate([rgb, alpha[..., None]], axis=-1), "PNG")


def mouse_ear(side):
    base = np.array(MOUSE["ear_base"]) * np.array([side, 1, 1])
    up = normalize(np.array([side * 0.55, -0.25, 1.0]))
    fwd = normalize(np.array([side * 0.95, 1.0, 0.15]))            # the ear opening looks forward-out
    fwd = normalize(fwd - up * np.dot(fwd, up))
    lat = np.cross(up, fwd) * side
    Rx, Ry = 0.0215, 0.0235
    nr, nphi = 6, 26
    verts, faces = [], []
    for i in range(nr + 1):
        r = i / nr
        for j in range(nphi):
            phi = j / nphi * TAU
            X = Rx * r * math.cos(phi); Y = Ry + Ry * r * math.sin(phi)
            narrow = 0.72 + 0.28 * smoothstep(0.0, 0.9, Y / (2 * Ry))
            X *= narrow
            cup = -0.0075 * (1 - r * r) * smoothstep(0.0, 0.5, Y / (2 * Ry) + 0.2)
            rim = 0.0022 * smoothstep(0.82, 1.0, r)
            p = base + X * lat + (Y - 0.004) * up + (cup + rim) * fwd
            verts.append(p)
    for i in range(nr):
        for j in range(nphi):
            j2 = (j + 1) % nphi
            faces.append((i * nphi + j, i * nphi + j2, (i + 1) * nphi + j2, (i + 1) * nphi + j))
    ob = mesh_obj(f"ear_{'L' if side < 0 else 'R'}", verts, faces)
    bm = bmesh.new(); bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    # make the front (the concave opening) face forward
    bm.normal_update()
    fsum = sum((f.normal for f in bm.faces), Vector())
    if fsum.dot(Vector(fwd)) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(ob.data); bm.free()
    for p in ob.data.polygons:
        p.use_smooth = True
    # planar UVs across the pinna: u across, v from the base up
    co = vert_array(ob) - base
    uvx = 0.5 + (co @ lat) / (2 * Rx); uvy = ((co @ up) + 0.004) / (2 * Ry)
    me = ob.data; lay = me.uv_layers.new(name="UVMap")
    li = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", li)
    lay.data.foreach_set("uv", np.stack([uvx[li], uvy[li]], axis=1).ravel())
    sol = ob.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.0011; sol.offset = -1
    sol.material_offset = 1; sol.use_rim = True; sol.material_offset_rim = 1
    sub = ob.modifiers.new("sub", "SUBSURF"); sub.levels = 1
    # the origin at the ear's base, so the page can flick it there
    ob.data.transform(Matrix.Translation(-Vector(base)))
    ob.location = Vector(base)
    return ob


def mouse_whiskers(side):
    pad = np.array(MOUSE["pad"]) * np.array([side, 1, 1])
    rng = np.random.default_rng(21 if side < 0 else 22)
    rows = [4, 5, 6, 6, 6]                           # A..E, dorsal to ventral
    verts, faces, fuv = [], [], []
    for r, ncol in enumerate(rows):
        for c in range(ncol):
            cn = c / max(1, ncol - 1)                # 0 = caudal (long), 1 = rostral (short)
            base = pad + np.array([side * 0.001, -0.0055 + 0.0105 * cn, 0.0052 - 0.0026 * r])
            length = (0.086 - 0.058 * cn) * (0.9 + 0.1 * math.sin(r * 1.3)) * rng.uniform(0.92, 1.05)
            d = normalize(np.array([side * 1.0, -0.38 + 0.85 * cn, 0.30 - 0.15 * r + rng.normal(0, 0.03)]))
            bend = normalize(np.array([0.0, 1.0, -0.25]) - d * np.dot(d, [0, 1, -0.25]))
            n = 10
            ts = np.linspace(0, 1, n)
            pts = base[None] + d[None] * (length * ts)[:, None] + bend[None] * (0.16 * length * ts ** 2)[:, None]
            radii = 0.00055 * (1 - ts) + 0.00007 * ts
            T, Ns, Bs = frames_along(pts, (0, 0, 1))
            k0 = len(verts)
            for i in range(n):
                for q in range(3):
                    a = q / 3 * TAU
                    verts.append(pts[i] + radii[i] * (math.cos(a) * Ns[i] + math.sin(a) * Bs[i]))
            tip = len(verts); verts.append(pts[-1] + T[-1] * 0.0008)
            for i in range(n - 1):
                for q in range(3):
                    q2 = (q + 1) % 3
                    faces.append((k0 + i * 3 + q, k0 + (i + 1) * 3 + q, k0 + (i + 1) * 3 + q2, k0 + i * 3 + q2))
                    fuv.append([(ts[i], 0.5), (ts[i + 1], 0.5), (ts[i + 1], 0.5), (ts[i], 0.5)])
            for q in range(3):
                q2 = (q + 1) % 3
                faces.append((k0 + (n - 1) * 3 + q, tip, k0 + (n - 1) * 3 + q2))
                fuv.append([(1.0, 0.5)] * 3)
    ob = mesh_obj(f"whiskers_{'L' if side < 0 else 'R'}", verts, faces, fuv)
    bm = bmesh.new(); bm.from_mesh(ob.data); bmesh.ops.recalc_face_normals(bm, faces=bm.faces); bm.to_mesh(ob.data); bm.free()
    ob.data.transform(Matrix.Translation(-Vector(pad))); ob.location = Vector(pad)
    return ob


def whisker_material():
    w = 64
    u = (np.arange(w) + 0.5) / w
    col = np.array([0.06, 0.055, 0.05]) * (1 - u[:, None] ** 1.5) + np.array([0.42, 0.40, 0.37]) * u[:, None] ** 1.5
    img = np.repeat(np.concatenate([col, np.ones((w, 1))], axis=1)[None], 4, axis=0)
    return material("whisker", base_tex=np_image("mouse_whisker", img, "PNG"), rough=0.35, spec=0.5)


def keep_largest_part(ob):
    """Drop any loose fragment a remesh may leave behind."""
    bm = bmesh.new(); bm.from_mesh(ob.data); bm.verts.ensure_lookup_table()
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, part = [v], []
        seen.add(v.index)
        while stack:
            x = stack.pop(); part.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o.index not in seen:
                    seen.add(o.index); stack.append(o)
        parts.append(part)
    parts.sort(key=len, reverse=True)
    kill = [v for p in parts[1:] for v in p]
    if kill:
        bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(ob.data); bm.free()
    return len(parts)


def digit(name, pts, r0, r1):
    pts = np.asarray(pts, float)
    # resample the few control points into a smooth curve
    t = np.linspace(0, 1, 10)
    k = np.linspace(0, 1, len(pts))
    P = np.stack([pchip(k, pts[:, j], t) if len(pts) > 2 else np.interp(t, k, pts[:, j]) for j in range(3)], axis=1)
    return tube(name, P, r0 + (r1 - r0) * t, 10)


def fuse(parts, name, voxel, tris):
    ob = join(parts, name)
    remesh(ob, voxel, smooth_iter=2)
    keep_largest_part(ob)
    decimate_to(ob, tris)
    return ob


def mouse_forepaw(side):
    """Held up before the chest, wrist bent, four fingers curled down and a
    stub of a thumb on the inside. Pink skin."""
    wr = np.array(MOUSE["wrist"]) * np.array([side, 1, 1])
    d = normalize(np.array([-side * 0.25, 0.70, -0.60]))           # the hand hangs forward-down, a little inward
    med = normalize(np.array([-side * 1.0, 0.0, 0.0]) - d * np.dot(d, [-side * 1.0, 0, 0]))   # towards the thumb
    palm_n = normalize(np.cross(d, med)) * (1 if side > 0 else -1)
    if palm_n[1] > 0:                                               # palm faces back towards the chest
        palm_n = -palm_n
    parts = []
    palm_c = wr + d * 0.0045
    M = np.stack([med, d, palm_n], axis=1)
    parts.append(ellipsoid("palm", palm_c, (0.0048, 0.0058, 0.0028), M, 12, 14))
    parts.append(tube("wristskin", np.array([wr - d * 0.004, wr + d * 0.002]), np.array([0.0038, 0.0040]), 12))
    for k, off in enumerate((0.0036, 0.0012, -0.0012, -0.0036)):
        L = 0.0075 if k in (1, 2) else 0.0063
        spread = normalize(d - med * off * 40)
        a0 = palm_c + d * 0.003 + med * off
        a1 = a0 + spread * L * 0.5 + palm_n * 0.0006
        a2 = a1 + normalize(spread + palm_n * 0.8) * L * 0.45
        a3 = a2 + normalize(spread * 0.4 + palm_n) * L * 0.3
        parts.append(digit(f"f{k}", [a0, a1, a2, a3], 0.0016, 0.0011))
    t0 = palm_c + med * 0.0045 - d * 0.001
    parts.append(digit("thumb", [t0, t0 + normalize(med + d) * 0.0022, t0 + normalize(med + d + palm_n) * 0.0035], 0.0014, 0.001))
    ob = fuse(parts, f"forepaw_{'L' if side < 0 else 'R'}", 0.0004, 1500)
    co = vert_array(ob); co = wr + (co - wr) * 0.95; ob.data.vertices.foreach_set("co", co.ravel())
    return ob


def mouse_hindfoot(side):
    """Plantigrade, flat on the desk beside the haunch: a long sole and five
    splayed toes, the middle three longest."""
    heel = np.array([side * 0.037, -0.022, 0.0035])
    d = normalize(np.array([side * 0.20, 1.0, 0.0]))
    lat = normalize(np.cross([0, 0, 1], d))
    parts = []
    sole = np.array([heel, heel + d * 0.02, heel + d * 0.044])
    parts.append(tube("sole", sole + np.array([0, 0, 0.0004]), np.array([0.0042, 0.0046, 0.0043]), 12, squash=np.array([0.7, 0.62, 0.6])))
    front = heel + d * 0.046
    offs = [-0.0056, -0.0028, 0.0, 0.0028, 0.0056]
    lens = [0.0085, 0.0125, 0.0135, 0.0125, 0.0092]
    angs = [-0.55, -0.2, 0.0, 0.2, 0.5]
    for k in range(5):
        start = front + lat * offs[k] - d * 0.002
        dk = normalize(d * math.cos(angs[k]) + lat * math.sin(angs[k]))
        mid = start + dk * lens[k] * 0.55 + np.array([0, 0, 0.0006])
        tip = start + dk * lens[k] + np.array([0, 0, -0.0006])
        parts.append(digit(f"t{k}", [start, mid, tip], 0.0019, 0.0014))
    ob = fuse(parts, f"hindfoot_{'L' if side < 0 else 'R'}", 0.0005, 1700)
    co = vert_array(ob); co[:, 2] -= co[:, 2].min(); ob.data.vertices.foreach_set("co", co.ravel())
    return ob


def mouse_nose():
    c = np.array(MOUSE["nose"])
    ob, mb = mb_family("Nose", 0.0004)
    mb_ell(mb, c.tolist(), (0.0062, 0.0052, 0.0050), (-10, 0, 0))
    for sx in (-1, 1):   # the rhinarium's two lobes, and the nostrils cut into them
        mb_ell(mb, (c + np.array([sx * 0.0028, 0.0022, 0.0004])).tolist(), (0.0032, 0.0028, 0.0034))
    mb_ell(mb, (c + np.array([0, 0.0038, -0.0035])).tolist(), (0.0012, 0.0025, 0.0028), neg=True, stiff=3)  # philtrum groove
    mo = mb_to_mesh(ob, "nose")
    remesh(mo, 0.0005, smooth_iter=1)
    decimate_to(mo, 900)
    nos = []
    for sx in (-1, 1):
        n = ellipsoid(f"nostril_{sx}", c + np.array([sx * 0.0036, 0.0045, 0.0003]), (0.0011, 0.0009, 0.0017), np.array(rot("Z", sx * 30)), 8, 8)
        nos.append(n)
    pink = material("mouse_nose", (0.80, 0.52, 0.55), rough=0.3, spec=0.55)
    dark = material("nostril", (0.16, 0.08, 0.09), rough=0.6)
    assign(mo, pink)
    for n in nos:
        assign(n, dark)
    mo = join([mo] + nos, "nose")
    mo.data.transform(Matrix.Translation(-Vector(c))); mo.location = Vector(c)
    return mo


def build_mouse():
    reset()
    bpy.context.scene.render.engine = "CYCLES"
    mb = mouse_body_metaballs()
    body = mb_to_mesh(mb, "mouse_body")
    remesh(body, 0.0024, smooth_iter=3)
    decimate_to(body, 18000)
    fur, tips_mat = mouse_fur_bake(body)
    # one shell of hair tips 1.4 mm out, alpha-tested: a soft, broken silhouette
    shell = body.copy(); shell.data = body.data.copy(); link(shell)
    decimate_to(shell, 11000)
    bm = bmesh.new(); bm.from_mesh(shell.data)               # no hair over the pink hands
    wr = [np.array(MOUSE["wrist"]) * np.array([sx, 1, 1]) for sx in (-1, 1)]
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if min(np.linalg.norm(np.array(v.co) - w) for w in wr) < 0.0075], context="VERTS")
    bm.to_mesh(shell.data); bm.free()
    co = vert_array(shell)
    nrm = np.zeros(len(co) * 3); shell.data.vertices.foreach_get("normal", nrm)
    co = co + nrm.reshape(-1, 3) * 0.0014
    co[:, 2] = np.maximum(co[:, 2], 0.0004)
    shell.data.vertices.foreach_set("co", co.ravel())
    uvd = shell.data.uv_layers["UVMap"].data
    uv = np.zeros(len(uvd) * 2); uvd.foreach_get("uv", uv); uvd.foreach_set("uv", uv * FUR_TILE)
    assign(shell, tips_mat)
    body = join([body, shell], "mouse_body")
    skin_mat = material("mouse_skin", (0.86, 0.64, 0.62), rough=0.45, spec=0.45)
    paws = []
    for side in (-1, 1):
        for p in (mouse_forepaw(side), mouse_hindfoot(side)):
            assign(p, skin_mat); paws.append(p)
    paws_ob = join(paws, "paws")
    eyes = []
    eye_mat = material("mouse_eye", (0.008, 0.008, 0.01), rough=0.06, spec=0.6)
    for side in (-1, 1):
        c = np.array(MOUSE["eye"]) * np.array([side, 1, 1])
        look = Vector((side * 1.0, 0.5, 0.3)).normalized()
        R = np.array(look.to_track_quat("Z", "Y").to_matrix())
        e = ellipsoid(f"eye_{side}", c, (0.0086, 0.0086, 0.0074), R, 18, 24); assign(e, eye_mat); eyes.append(e)
    eyes_ob = join(eyes, "eyes")
    nose = mouse_nose()
    wmat = whisker_material()
    whisk = []
    for side in (-1, 1):
        w = mouse_whiskers(side); assign(w, wmat); whisk.append(w)
    ear_front = material("ear_inner", base_tex=ear_texture(), tex_alpha=True, rough=0.5, spec=0.35)
    ear_back = material("ear_outer", (0.22, 0.18, 0.17), rough=0.7, spec=0.3)
    ears = []
    for side in (-1, 1):
        e = mouse_ear(side); assign(e, ear_front, ear_back); apply_modifiers(e); ears.append(e)
    tail, tail_pts, tail_a = mouse_tail()
    # ---- rig
    neck = np.array(MOUSE["neck"])
    L = tail_a[-1]
    kn = np.linspace(0.012, L, 13)
    tp = np.stack([np.interp(kn, tail_a, tail_pts[:, k]) for k in range(3)], axis=1)
    bones = [("body", (0, -0.02, 0.03), (0, -0.02, 0.08), None, False),
             ("head", tuple(neck), tuple(neck + np.array([0, 0, 0.03])), "body", False)]
    for k in range(12):
        bones.append((f"tail_{k}", tuple(tp[k]), tuple(tp[k + 1]), "body" if k == 0 else f"tail_{k - 1}", k > 0))
    rig = make_rig(bones)
    co = vert_array(body)
    hc = np.array(MOUSE["head_c"]) + np.array([0, 0.012, 0])
    en = np.linalg.norm((co - hc) / np.array([0.045, 0.072, 0.036]), axis=1)
    w_head = (1 - smoothstep(0.8, 1.1, en)) * smoothstep(-0.012, 0.012, (co - neck) @ normalize(np.array([0, 0.75, 0.66])))
    skin(body, rig, {"body": 1 - w_head, "head": w_head})
    tco = vert_array(tail)
    # arc position of each tail vertex: nearest point on the centre line
    d2 = ((tco[:, None, :] - tail_pts[None, :, :]) ** 2).sum(-1)
    ta = tail_a[np.argmin(d2, axis=1)]
    mids = 0.5 * (kn[:-1] + kn[1:])
    tw = {"body": 1 - smoothstep(0.0, mids[0], ta)}
    for k in range(12):
        lo = mids[k - 1] if k else 0.0
        hi = mids[k + 1] if k < 11 else None
        w = smoothstep(lo, mids[k], ta) if k else smoothstep(0.0, mids[0], ta)
        if hi is not None:
            w = np.minimum(w, 1 - smoothstep(mids[k], hi, ta))
        tw[f"tail_{k}"] = w
    skin(tail, rig, tw)
    paws_ob.parent = rig
    for ob in [eyes_ob, nose] + whisk + ears:
        parent_to_bone(ob, rig, "head")
    return [body, paws_ob, eyes_ob, nose, tail] + whisk + ears


# ================================================================= export, check, render
def export(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", export_image_format="AUTO",
                              export_texcoords=True, export_normals=True, export_tangents=False,
                              export_materials="EXPORT", export_colors=False, export_cameras=False,
                              export_lights=False, export_apply=True, export_yup=True, export_skins=True,
                              export_all_influences=False, export_animations=False, export_morph=False,
                              use_selection=False)


def glb_json(path):
    with open(path, "rb") as f:
        data = f.read()
    ln, typ = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + ln]), len(data)


def check_glb(path, species):
    need = {"zebrafish_larva": ["rig", "eye_L", "eye_R"] + [f"spine_{k}" for k in range(12)],
            "mouse_v1": ["rig", "head", "nose", "whiskers_L", "whiskers_R", "ear_L", "ear_R"] + [f"tail_{k}" for k in range(12)]}[species]
    g, size = glb_json(path)
    names = [n.get("name", "") for n in g["nodes"]]
    missing = [n for n in need if n not in names]
    tris = 0
    for m in g["meshes"]:
        for p in m["primitives"]:
            tris += g["accessors"][p["indices"]]["count"] // 3
    joints = [g["nodes"][j]["name"] for s in g.get("skins", []) for j in s["joints"]]
    report = dict(file=path, bytes=size, triangles=tris, skins=len(g.get("skins", [])), joints=joints,
                  missing=missing, nodes=names, images=len(g.get("images", [])),
                  materials=[(m["name"], m.get("alphaMode", "OPAQUE")) for m in g.get("materials", [])])
    return report


def world_bbox(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type != "MESH":
            continue
        oe = o.evaluated_get(dg); me = oe.to_mesh()
        a = np.zeros(len(me.vertices) * 3); me.vertices.foreach_get("co", a); a = a.reshape(-1, 3)
        M = np.array(oe.matrix_world)
        pts.append(a @ M[:3, :3].T + M[:3, 3]); oe.to_mesh_clear()
    P = np.vstack(pts)
    return P.min(0), P.max(0)


def look_at(cam, target, direction, dist, up=(0, 0, 1)):
    d = Vector(direction).normalized()
    pos = Vector(target) + d * dist
    f = (Vector(target) - pos).normalized()
    u = Vector(up)
    if abs(f.dot(u)) > 0.99:
        u = Vector((0, 1, 0))
    r = f.cross(u).normalized(); u2 = r.cross(f)
    M = Matrix((r, u2, -f)).transposed()
    cam.matrix_world = Matrix.Translation(pos) @ M.to_4x4()


def render_previews(glb, prefix, species, args):
    reset()
    bpy.ops.import_scene.gltf(filepath=glb)
    objs = [o for o in bpy.context.scene.objects]
    lo, hi = world_bbox(objs)
    for m in bpy.data.materials:       # glTF MASK is a hard cut; Cycles would blend it
        if m.blend_method == "CLIP" and m.node_tree:
            nt = m.node_tree; b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if b and b.inputs["Alpha"].is_linked:
                src = b.inputs["Alpha"].links[0].from_socket
                g = nt.nodes.new("ShaderNodeMath"); g.operation = "GREATER_THAN"; g.inputs[1].default_value = m.alpha_threshold
                nt.links.new(src, g.inputs[0]); nt.links.new(g.outputs[0], b.inputs["Alpha"])
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.samples = args.samples; sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 8; sc.cycles.transparent_max_bounces = 24
    sc.render.resolution_x = sc.render.resolution_y = args.res
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "Filmic"; sc.view_settings.look = "Medium High Contrast"
    world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    fish = species == "zebrafish_larva"
    bg.inputs["Color"].default_value = (0.10, 0.14, 0.17, 1) if fish else (0.16, 0.16, 0.17, 1)
    bg.inputs["Strength"].default_value = 1.0
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2
    if not fish:
        me = bpy.data.meshes.new("desk")
        me.from_pydata([(-2, -2, 0), (2, -2, 0), (2, 2, 0), (-2, 2, 0)], [], [(0, 1, 2, 3)])
        desk = link(bpy.data.objects.new("desk", me))
        assign(desk, material("desk", (0.40, 0.36, 0.32), rough=0.7))
    k = 0.7 if fish else 0.55
    for nm, loc, energy, size in (("key", (-0.8, 0.9, 1.1), 90 * k, 0.6), ("fill", (0.9, 0.5, 0.4), 30 * k, 0.8), ("rim", (0.2, -1.0, 0.9), 70 * k, 0.5)):
        ld = bpy.data.lights.new(nm, "AREA"); ld.energy = energy; ld.size = size
        lo_ = link(bpy.data.objects.new(nm, ld))
        look_at(lo_, center, loc, 1.4 * max(radius * 3, 0.5))
    cd = bpy.data.cameras.new("cam"); cd.lens = 70; cd.sensor_width = 36
    cam = link(bpy.data.objects.new("cam", cd)); sc.camera = cam
    fov = 2 * math.atan(18 / 70)
    views = {"front34": (-0.85, 1.0, 0.55), "side": (-1.0, 0.0, 0.1), "top": (0.0, -0.0001, 1.0)}
    out = []
    for vname, d in views.items():
        dist = radius / math.tan(fov / 2) * 1.05
        look_at(cam, center, d, dist, up=(0, 0, 1) if vname != "top" else (0, 1, 0))
        if vname == "top":
            cam.matrix_world = Matrix.Translation(Vector(center) + Vector((0, 0, dist)))
        path = os.path.abspath(f"{prefix}_{vname}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        out.append(path)
    # a close look at the head, for review (not on the contact sheet)
    target, d, dist = (((0.0, 0.095, 0.125), (-0.9, 1.0, 0.35), 0.30) if not fish else
                       ((0.0, 0.10, 0.0), (-1.0, 0.6, 0.45), 0.24))
    look_at(cam, target, d, dist)
    sc.render.filepath = os.path.abspath(f"{prefix}_closeup.png")
    bpy.ops.render.render(write_still=True)
    return out, (lo, hi)


def contact_sheet(paths, out_path, cols=3):
    imgs = [bpy.data.images.load(p) for p in paths if os.path.exists(p)]
    if not imgs:
        return
    w = h = 600
    rows = (len(imgs) + cols - 1) // cols
    sheet = np.ones((rows * h, cols * w, 4), np.float32)
    for k, im in enumerate(imgs):
        iw, ih = im.size
        a = np.array(im.pixels[:], np.float32).reshape(ih, iw, 4)
        a = a[(np.arange(h) * ih // h)][:, (np.arange(w) * iw // w)]
        r = rows - 1 - k // cols; c = k % cols
        sheet[r * h:(r + 1) * h, c * w:(c + 1) * w] = a
    img = bpy.data.images.new("contact", cols * w, rows * h, alpha=True)
    img.pixels.foreach_set(sheet.ravel()); img.filepath_raw = out_path; img.file_format = "PNG"; img.save()


def main():
    args = parse_args()
    os.makedirs(args.out, exist_ok=True); os.makedirs(args.previews, exist_ok=True)
    todo = [("zebrafish_larva", build_fish), ("mouse_v1", build_mouse)]
    if args.only:
        todo = [t for t in todo if args.only in t[0]]
    reports = {}
    for species, build in todo:
        objs = build()
        for o in objs:
            if o.type == "MESH":
                print(f"[{species}] {o.name}: {tris_of(o)} tris (before export modifiers)")
        path = os.path.abspath(os.path.join(args.out, f"{species}.glb"))
        export(path)
        rep = check_glb(path, species)
        reports[species] = rep
        print(f"[{species}] CHECK", json.dumps({k: v for k, v in rep.items() if k != "nodes"}))
        if not args.no_render:
            imgs, (lo, hi) = render_previews(path, os.path.join(args.previews, species), species, args)
        else:
            reset(); bpy.ops.import_scene.gltf(filepath=path)
            lo, hi = world_bbox(list(bpy.context.scene.objects))
        # Blender (x, y, z) -> glTF (x, z, -y)
        print(f"[{species}] BBOX blender min {np.round(lo, 4)} max {np.round(hi, 4)} size {np.round(hi - lo, 4)}")
    order = [os.path.join(args.previews, f"{sp}_{v}.png") for sp in ("zebrafish_larva", "mouse_v1") for v in ("front34", "side", "top")]
    if not args.no_render:
        contact_sheet(order, os.path.abspath(os.path.join(args.previews, "contact.png")))
    shutil.rmtree(TEXDIR, ignore_errors=True)


main()

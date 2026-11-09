"""Blender script: builds one fish species as a 3D model and renders its swim
cycle as transparent sprite frames.

    blender -b --factory-startup -P fish3d.py -- <species.json> <texture.png> <outdir> [frames] [samples]

The body is lofted from the side profile; the whole fish bends along a
travelling wave with its length kept, so the tail really swings toward and
away from the camera.  Fins are thin translucent sheets; the side-view
texture from art/export.py is mapped onto everything by UV.
"""
import json
import math
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
JSON, TEX, OUTDIR = [os.path.abspath(a) for a in argv[:3]]
FRAMES = int(argv[3]) if len(argv) > 3 else 12
SAMPLES = int(argv[4]) if len(argv) > 4 else 64
TURN = int(argv[5]) if len(argv) > 5 else 12      # frames of the turn-around
D = json.load(open(JSON))

U = D['u']
TOP, BOT = D['top'], D['bot']
UEND = U[-1]
XP = D['peduncle']
TEXU0, TEXU1, TEXY = D['tex_u0'], D['tex_u1'], D['tex_y']
AMP = {'shark': 0.068, 'barracuda': 0.055}.get(D['name'], 0.075)
SKIN = D.get('skin', {})
YAW = math.radians(-9)         # head turned a little toward the camera
PITCH = math.radians(6)        # seen slightly from above


def interp(xs, ys, x):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        m = (lo + hi) // 2
        if xs[m] <= x:
            lo = m
        else:
            hi = m
    t = (x - xs[lo]) / (xs[hi] - xs[lo])
    return ys[lo] * (1 - t) + ys[hi] * t


def top(u):
    return max(interp(U, TOP, u), 0.0)


def bot(u):
    return max(interp(U, BOT, u), 0.0)


def uv(u, z):
    return ((u - TEXU0) / (TEXU1 - TEXU0), (z + TEXY) / (2 * TEXY))


# ------------------------------------------------------------ the bend

N_CL = 160
CL_U = [1.08 * i / (N_CL - 1) for i in range(N_CL)]


def centerline(phase, curl=0.0):
    """Centerline points (x, y) and angle per CL_U sample for this phase.
    curl bends the whole body into a C, as a fish does when it turns."""
    def lateral(u):
        env = 0.10 + 0.90 * min(u, 1.0) ** 2
        return AMP * env * math.sin(phase - 2 * math.pi * 0.85 * u) + curl * (u - 0.35) ** 2
    ang = []
    for u in CL_U:
        e = 1e-3
        ang.append(math.atan2(lateral(u + e) - lateral(u - e), 2 * e))
    xs, ys = [0.0], [lateral(0)]
    for i in range(1, N_CL):
        du = CL_U[i] - CL_U[i - 1]
        a = 0.5 * (ang[i] + ang[i - 1])
        xs.append(xs[-1] + du * math.cos(a))
        ys.append(ys[-1] + du * math.sin(a))
    # keep the point at u = 0.3 still, so the fish does not jitter
    ax = interp(CL_U, xs, 0.3) - 0.3
    ay = interp(CL_U, ys, 0.3)
    return [x - ax for x in xs], [y - ay for y in ys], ang


FLEX = 1.0


def place(cl, u, s, z):
    """A point on the straight fish (u along, s across, z up) -> bent position."""
    xs, ys, ang = cl
    cx, cy, a = interp(CL_U, xs, u), interp(CL_U, ys, u), interp(CL_U, ang, u)
    return (cx - s * math.sin(a), cy + s * math.cos(a), z)


# ------------------------------------------------------------ meshes

NR = 40     # around the body


def body_rest():
    pts, uvs = [], []
    for u in U:
        r = (top(u) + bot(u)) / 2
        c = (top(u) - bot(u)) / 2
        w = r * D['thick']
        # the head is rounder than the flattened body
        w = w + (r - w) * 0.35 * max(0.0, 1 - u / 0.15)
        for j in range(NR):
            th = 2 * math.pi * j / NR
            s = w * math.sin(th)
            z = c + r * math.cos(th)
            pts.append((u, s, z))
    faces = []
    nu = len(U)
    for i in range(nu - 1):
        for j in range(NR):
            a = i * NR + j
            b = i * NR + (j + 1) % NR
            faces.append((a, b, b + NR, a + NR))
    # cap the cut at the peduncle (the tail fin covers it)
    end = len(pts)
    pts.append((U[-1], 0.0, (top(U[-1]) - bot(U[-1])) / 2))
    for j in range(NR):
        a = (nu - 1) * NR + j
        b = (nu - 1) * NR + (j + 1) % NR
        faces.append((a, end, b))
    return pts, faces


def fin_sheet(fin, phase):
    us, hs = fin['u'], fin['h']
    rows = 8
    pts = []
    for i, u in enumerate(us):
        h = hs[i] * (1 + 0.07 * math.sin(phase - u * 12))
        base = top(u) - 0.012 if fin['sign'] > 0 else -bot(u) + 0.012
        for k in range(rows):
            q = k / (rows - 1)
            z = base + fin['sign'] * (0.012 + h) * q
            # the free edge trails the body's stroke and curls with the water
            lag = 0.55 * h * q ** 2 * math.sin(phase - 2 * math.pi * 0.85 * u - 1.3)
            pts.append((u, lag * FLEX, z))
    faces = []
    for i in range(len(us) - 1):
        for k in range(rows - 1):
            a = i * rows + k
            faces.append((a, a + rows, a + rows + 1, a + 1))
    return pts, faces


def tail_sheet(phase=0.0):
    nt, ns = 14, 25
    pc, ph, sp = D['pc'], D['ph'], D['tail_spread']
    tlen = 1.0 - XP
    fork = D['tail_fork']
    pts = []
    for i in range(nt):
        t = i / (nt - 1)
        for j in range(ns):
            s = -1 + 2 * j / (ns - 1)
            lobe = (D['tail_upper'] if s > 0 else D['tail_lower']) * sp
            spread = ph + (lobe - ph) * t ** 0.7
            rr = abs(s)
            if fork >= 0:
                te = 1 - fork * (1 - rr) ** 1.3
            else:
                te = 1 - (-fork) * rr ** 2
            te *= D.get('tail_lower_len', 1.0) if s < 0 else 1.0
            u = XP - 0.015 + (tlen + 0.015) * t * te
            z = pc + s * spread
            # the fin is flexible: its trailing edge lags behind the stroke and
            # the lobe tips lag more than the middle, so the tail cups
            wph = phase - 2 * math.pi * 0.85 * u
            lag = (0.10 * (t * te) ** 1.6 + 0.035 * abs(s) ** 2 * t) * math.sin(wph - 1.1) * (tlen / 0.2)
            pts.append((u, lag * FLEX, z))
    faces = []
    for i in range(nt - 1):
        for j in range(ns - 1):
            a = i * ns + j
            faces.append((a, a + ns, a + ns + 1, a + 1))
    return pts, faces


def pectoral_pts(phase):
    pu0, pv0, pl, pw = D['pectoral']
    a = math.radians(D['pectoral_angle'])
    r = (top(pu0) + bot(pu0)) / 2
    w = r * D['thick']
    side = -(w * 0.92 + 0.004)            # on the camera side (camera looks along +y)
    flap = math.radians(40 + 25 * math.cos(phase * 2)) if not D['pectoral_tri'] else math.radians(18)
    pts = []
    na, nc = 10, 7
    for i in range(na):
        q = i / (na - 1)
        along = pl * q
        for j in range(nc):
            k = -1 + 2 * j / (nc - 1)
            if D['pectoral_tri']:
                across = pw * (1 - q) ** 0.9 * (k + 1) / 2 - pw * 0.15 * (1 - q)
            else:
                across = pw * math.sqrt(max(0.0, 1 - (2 * q - 1) ** 2)) * k * 0.9
            u = pu0 + along * math.cos(a) - across * math.sin(a)
            z = pv0 + along * math.sin(a) + across * math.cos(a)
            s = side - along * math.sin(flap)
            # bends along its length and twists a little with each beat
            s -= 0.35 * pl * q * q * (0.6 + 0.4 * math.sin(phase * 2 - 0.8))
            z -= 0.10 * pl * q * q * math.sin(phase * 2)
            pts.append((u, s, z))
    faces = []
    for i in range(na - 1):
        for j in range(nc - 1):
            p = i * nc + j
            faces.append((p, p + nc, p + nc + 1, p + 1))
    return pts, faces


def make_obj(name, pts, faces, uvs, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts, [], faces)
    me.update()
    layer = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            layer.data[li].uv = uvs[vi]
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def set_coords(ob, pts):
    flat = [c for p in pts for c in p]
    ob.data.vertices.foreach_set('co', flat)
    ob.data.update()


# ------------------------------------------------------------ build & render

def main():
    common.reset_scene()
    tex = bpy.data.images.load(os.path.abspath(TEX))
    tex.alpha_mode = 'STRAIGHT'
    aspect = (2 * TEXY) / (TEXU1 - TEXU0)
    body_mat = common.fish_body_material('body', tex, aspect, SKIN)
    fin_mat = common.fish_fin_material('fin', tex, SKIN)
    pec_mat = common.flat_fin_material('pectoral', D['pectoral_color'], D['pectoral_alpha'], D['dark_tips'])
    eye_mat = common.eye_material('eye', D['iris'])

    rig = bpy.data.objects.new('rig', None)
    bpy.context.collection.objects.link(rig)

    rest_b, faces_b = body_rest()
    body = make_obj('body', rest_b, faces_b, [uv(p[0], p[2]) for p in rest_b], body_mat)
    sub = body.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    rest_t, faces_t = tail_sheet()
    tail = make_obj('tail', rest_t, faces_t, [uv(p[0], p[2]) for p in rest_t], fin_mat)
    fins = []
    for fin in D['fins']:
        p, f = fin_sheet(fin, 0)
        fins.append((fin, make_obj(fin['name'], p, f, [uv(q[0], q[2]) for q in p], fin_mat)))
    p, f = pectoral_pts(0)
    pec = make_obj('pec', p, f, [(0.5, 0.5)] * len(p), pec_mat)
    pec2 = make_obj('pec2', p, f, [(0.5, 0.5)] * len(p), pec_mat)   # the far side

    ex, ey, er = D['eye']
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1.0)
    eye = bpy.context.active_object
    eye.data.materials.append(eye_mat)
    eye.data.shade_smooth()
    eye.scale = (er, er * 0.55, er)
    eye2 = eye.copy()
    eye2.data = eye.data
    bpy.context.collection.objects.link(eye2)

    if SKIN.get('fin_thick'):
        # real fins have thickness; paper-thin sheets look like cutouts
        for ob in [tail, pec, pec2] + [o for _, o in fins]:
            m = ob.modifiers.new('thick', 'SOLIDIFY')
            m.thickness = SKIN['fin_thick']
            m.offset = 0.0
            m2 = ob.modifiers.new('sub', 'SUBSURF')
            m2.levels = m2.render_levels = 1
    for ob in [body, tail, pec, pec2, eye, eye2] + [o for _, o in fins]:
        ob.parent = rig
    rig.rotation_euler = (0, 0, YAW)

    w, h, pad = D['width'], D['height'], D['pad']
    tops = max(TOP)
    bots = max(BOT)
    zc = -(tops - bots) * 0.25 * -1
    common.sprite_camera(center=(0.5, zc), ortho_width=1.0 / (1 - 2 * pad) * 1.02,
                         res=(w, h), pitch=PITCH)
    common.underwater_lights()
    common.render_settings(SAMPLES, transparent=True)

    # turn about the middle of the fish, not the nose
    PIV = 0.42
    rig.location = (PIV, 0, 0)
    for ob in [body, tail, pec, pec2, eye, eye2] + [o for _, o in fins]:
        ob.matrix_parent_inverse.identity()
        ob.matrix_parent_inverse[0][3] = -PIV

    def pose(phase, curl):
        cl = centerline(phase, curl)
        set_coords(body, [place(cl, *q) for q in rest_b])
        p, _ = tail_sheet(phase)
        set_coords(tail, [place(cl, *q) for q in p])
        for fin, ob in fins:
            p, _ = fin_sheet(fin, phase)
            set_coords(ob, [place(cl, *q) for q in p])
        p, _ = pectoral_pts(phase)
        set_coords(pec, [place(cl, *q) for q in p])
        set_coords(pec2, [place(cl, q[0], -q[1], q[2]) for q in p])
        r = (top(ex) + bot(ex)) / 2
        wv = r * D['thick']
        wv = wv + (r - wv) * 0.35 * max(0.0, 1 - ex / 0.15)
        c = (top(ex) - bot(ex)) / 2
        cosv = max(-1.0, min(1.0, (ey - c) / max(r, 1e-4)))
        s_surf = wv * math.sqrt(max(0.0, 1 - cosv * cosv))
        eye.location = place(cl, ex, -(s_surf * 0.80), ey)
        eye2.location = place(cl, ex, (s_surf * 0.80), ey)
        eye.rotation_euler = eye2.rotation_euler = (0, 0, interp(CL_U, cl[2], ex))

    os.makedirs(OUTDIR, exist_ok=True)
    for k in range(FRAMES):
        phase = 2 * math.pi * k / FRAMES
        rig.rotation_euler = (0, 0, YAW)
        pose(phase, 0.0)
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_%02d.png' % (D['name'], k))
        bpy.ops.render.render(write_still=True)

    # the turn: from facing left to facing right (the mirror image of frame 0),
    # swinging the head toward the viewer, body curled, beating faster
    for k in range(TURN):
        p = k / (TURN - 1)
        e = 0.5 - 0.5 * math.cos(math.pi * p)
        phase = 2 * math.pi * 1.6 * p
        rig.rotation_euler = (0, 0, YAW - e * (math.pi + 2 * YAW))
        pose(phase * (1 - abs(2 * p - 1) * 0) , 0.55 * math.sin(math.pi * p))
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_turn%02d.png' % (D['name'], k))
        bpy.ops.render.render(write_still=True)

main()

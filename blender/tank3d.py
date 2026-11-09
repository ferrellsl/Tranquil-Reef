"""Blender script: the reef tank, seen head-on, wider than the screen (the
channel pans across it).

    blender -b --factory-startup -P tank3d.py -- <textures dir> <out dir> [samples] [--quick]

A strip of coral gravel at the bottom, one dense wall of live rock across the
tank with many kinds of coral on it, a moray's cave low on the left, open water
above.  Writes the same passes as reef3d.py (beauty, sand = floor without the
light net, mask, position/normal, one image per swaying coral, scene.json),
at TANK_W x 1080.
"""
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import reef3d as R  # noqa: E402  (materials, rocks, corals, render passes)

TANK_W = 2688            # 1.4 screens
R.W = TANK_W
QUICK = '--quick' in sys.argv
BARE = '--bare' in sys.argv      # rock, gravel and cave only: the corals are photos laid on later
MID, FRONT, SAND = R.MID, R.FRONT, R.SAND


# ------------------------------------------------------------ more corals

def brain(name, loc, radius, seed, c1, c2, flat=0.70):
    ob = R.brain_coral(name, loc, radius, seed, MID)
    ob.scale.z = flat
    ob.data.materials.clear()
    ob.data.materials.append(R.coral_material(name, c1, c2, sss=0.4, pointy=True, bumpscale=90))
    return ob


def bubble_coral(name, loc, radius, seed):
    """A cluster of pearly bubbles."""
    r = random.Random(seed)
    mat = R.coral_material(name, (0.45, 0.40, 0.55), (0.85, 0.80, 0.95), sss=0.3, rough=0.25, bumpscale=20)
    obs = []
    for k in range(70):
        a = r.uniform(0, 2 * math.pi)
        e = r.uniform(0, 1.2)
        d = radius * (0.25 + 0.75 * r.random() ** 0.5)
        p = Vector(loc) + Vector((math.cos(a) * math.cos(e) * d, math.sin(a) * math.cos(e) * d * 0.8, math.sin(e) * d * 0.9))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=radius * r.uniform(0.13, 0.22), location=p)
        b = bpy.context.active_object
        b.data.shade_smooth()
        b.data.materials.append(mat)
        b.pass_index = MID
        obs.append(b)
    return obs


def leather(name, loc, radius, seed, c1, c2, tilt=(0.25, 0.0)):
    """A leather (toadstool) coral: a thick stalk and a wide frilly cap."""
    r = random.Random(seed)
    bm = bmesh.new()
    rings, segs = 14, 72
    verts = []
    for i in range(rings + 1):
        t = i / rings
        row = []
        for j in range(segs):
            a = 2 * math.pi * j / segs
            rr = radius * t
            frill = 0.10 * radius * t ** 3 * math.sin(a * 7 + r.uniform(0, 0.3)) + 0.05 * radius * t ** 2 * math.sin(a * 13)
            z = radius * 0.18 * (1 - t ** 2) + frill
            row.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
        verts.append(row)
    for i in range(rings):
        for j in range(segs):
            bm.faces.new((verts[i][j], verts[i][(j + 1) % segs], verts[i + 1][(j + 1) % segs], verts[i + 1][j]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    cap = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(cap)
    sol = cap.modifiers.new('sol', 'SOLIDIFY')
    sol.thickness = radius * 0.06
    sub = cap.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 2
    cap.location = Vector(loc) + Vector((0, 0, radius * 0.45))
    cap.rotation_euler = (tilt[0], tilt[1], r.uniform(0, 6.28))
    mat = R.coral_material(name, c1, c2, sss=0.5, bumpscale=160)
    cap.data.materials.append(mat)
    cap.data.shade_smooth()
    cap.pass_index = MID
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius * 0.22, depth=radius * 0.55,
                                        location=Vector(loc) + Vector((0, 0, radius * 0.2)))
    st = bpy.context.active_object
    st.data.materials.append(mat)
    st.pass_index = MID
    return [cap, st]


def anemone(name, loc, radius, seed, col=(0.75, 0.30, 0.08), tip=(0.95, 0.65, 0.30)):
    """Long soft tentacles from a disc (the clownfish's home)."""
    r = random.Random(seed)
    verts, edges, radii = [], [], []
    for k in range(70):
        a = r.uniform(0, 2 * math.pi)
        d = radius * r.uniform(0.1, 1.0) ** 0.5
        base = Vector((math.cos(a) * d, math.sin(a) * d, 0))
        out = Vector((math.cos(a), math.sin(a), 0)) * r.uniform(0.3, 0.9) + Vector((0, 0, r.uniform(0.7, 1.2)))
        out.normalize()
        ln = radius * r.uniform(0.9, 1.5)
        prev = len(verts)
        verts.append(base)
        radii.append(radius * 0.05)
        n = 6
        for s in range(1, n + 1):
            q = s / n
            droop = Vector((0, 0, -0.35 * q * q * ln))
            verts.append(base + out * ln * q + droop + Vector((r.uniform(-1, 1), r.uniform(-1, 1), 0)) * 0.02 * ln * q)
            radii.append(radius * 0.05 * (1 - 0.55 * q))
            edges.append((prev, len(verts) - 1))
            prev = len(verts) - 1
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    sk = ob.modifiers.new('skin', 'SKIN')
    for i, sv in enumerate(me.skin_vertices[0].data):
        sv.radius = (radii[i], radii[i])
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    ob.location = loc
    ob.data.materials.append(R.coral_material(name, col, tip, sss=0.7, rough=0.35, bumpscale=60))
    ob.pass_index = MID
    return ob


def finger_coral(name, base, seed, scale, c1, c2):
    ob = R.branch_mesh(name, base, seed, 3, 0.10 * scale, 0.045 * scale, 0.45, up=0.6)
    ob.data.materials.append(R.coral_material(name, c1, c2, sss=0.5, bumpscale=120))
    ob.pass_index = MID
    return ob


def zoanthids(name, center, normal, spread, seed, col, n=80):
    """A colony of small polyp discs on a rock face."""
    r = random.Random(seed)
    nrm = Vector(normal).normalized()
    t1 = nrm.orthogonal().normalized()
    t2 = nrm.cross(t1)
    mat = R.coral_material(name, tuple(c * 0.5 for c in col), col, sss=0.6, rough=0.3, bumpscale=50)
    for k in range(n):
        p = Vector(center) + t1 * r.gauss(0, spread) + t2 * r.gauss(0, spread * 0.7)
        bpy.ops.mesh.primitive_cylinder_add(vertices=14, radius=r.uniform(0.010, 0.017), depth=r.uniform(0.01, 0.03), location=p)
        z = bpy.context.active_object
        z.rotation_euler = nrm.to_track_quat('Z', 'Y').to_euler()
        z.data.materials.append(mat)
        z.pass_index = MID


PALETTE = [  # linear colors: the small channels must be really small, or they come out pastel
    ((0.05, 0.25, 0.01), (0.25, 0.75, 0.05)), ((0.30, 0.02, 0.18), (0.85, 0.12, 0.55)),
    ((0.45, 0.08, 0.01), (1.00, 0.35, 0.03)), ((0.01, 0.06, 0.35), (0.08, 0.35, 0.95)),
    ((0.40, 0.28, 0.01), (1.00, 0.75, 0.05)), ((0.35, 0.03, 0.02), (0.90, 0.15, 0.08)),
    ((0.02, 0.25, 0.22), (0.10, 0.80, 0.65)), ((0.15, 0.05, 0.35), (0.50, 0.25, 0.95))]


def plate(name, loc, normal, radius, seed, c1, c2):
    """An encrusting / plating coral: a thin wavy shelf growing out of a rock face."""
    r = random.Random(seed)
    bm = bmesh.new()
    rings, segs = 8, 48
    rows = []
    for i in range(rings + 1):
        t = i / rings
        row = []
        for j in range(segs):
            a = 2 * math.pi * j / segs
            rr = radius * t * (1 + 0.15 * math.sin(a * 3 + seed))
            z = 0.06 * radius * t ** 2 * math.sin(a * 6 + r.uniform(0, 1))
            row.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z)))
        rows.append(row)
    for i in range(rings):
        for j in range(segs):
            bm.faces.new((rows[i][j], rows[i][(j + 1) % segs], rows[i + 1][(j + 1) % segs], rows[i + 1][j]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    sol = ob.modifiers.new('sol', 'SOLIDIFY')
    sol.thickness = radius * 0.08
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    n = Vector(normal)
    n = (n + Vector((0, 0, 1.4))).normalized()          # shelves tilt up toward the light
    ob.location = loc
    ob.rotation_euler = n.to_track_quat('Z', 'Y').to_euler()
    ob.data.materials.append(R.coral_material(name, c1, c2, sss=0.5, bumpscale=180))
    ob.data.shade_smooth()
    ob.pass_index = MID
    return ob


def scatter_corals(seed, x0, x1, n_top=80, n_front=75):
    """Cover the rock: coral heads on the tops, plates and polyp colonies on the faces."""
    r = random.Random(seed)
    k = 0
    for i in range(n_top):
        x = r.uniform(x0, x1)
        y = r.uniform(0.70, 1.10)
        p, nrm, ob = surface(x, y)
        if ob is None or ob.name.startswith('gravel') or nrm.z < 0.45:
            continue
        c1, c2 = r.choice(PALETTE)
        kind = r.random()
        name = 'sc%d' % k
        k += 1
        if kind < 0.38:
            brain(name, tuple(p - Vector((0, 0, 0.04))), r.uniform(0.11, 0.24), 300 + k, c1, c2, flat=r.uniform(0.55, 0.85))
        elif kind < 0.62:
            finger_coral(name, tuple(p - Vector((0, 0, 0.03))), 400 + k, r.uniform(1.0, 1.7), c1, c2)
        elif kind < 0.74:
            leather(name, tuple(p - Vector((0, 0, 0.02))), r.uniform(0.12, 0.22), 500 + k, c1, c2,
                    tilt=(r.uniform(0.1, 0.4), r.uniform(-0.2, 0.2)))
        elif kind < 0.86:
            zoanthids(name, tuple(p), tuple(nrm), r.uniform(0.04, 0.07), 600 + k, c2, n=40)
        else:
            plate(name, tuple(p + Vector((0, 0, 0.02))), (0, -0.3, 1), r.uniform(0.12, 0.22), 700 + k, c1, c2)
    for i in range(n_front):
        x = r.uniform(x0, x1)
        z = r.uniform(0.12, 0.85)
        p, nrm = front_face(x, z)
        if p is None or nrm.y > -0.2:
            continue
        c1, c2 = r.choice(PALETTE)
        name = 'sf%d' % k
        k += 1
        if r.random() < 0.55:
            plate(name, tuple(p), tuple(nrm), r.uniform(0.14, 0.26), 800 + k, c1, c2)
        else:
            zoanthids(name, tuple(p), tuple(nrm), r.uniform(0.04, 0.07), 900 + k, c2, n=45)


def gravel_material():
    mat, nt, out = R.nodes('gravel')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    d = R.boxtex(nt, R.tex('coral_gravel_diff'), 1.4, tc.outputs['Object'])
    b = R.boxtex(nt, R.tex('coral_gravel_disp', 'Non-Color'), 1.4, tc.outputs['Object'])
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = 0.45
    hsv.inputs['Value'].default_value = 1.6
    L.new(d.outputs['Color'], hsv.inputs['Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.9
    bump.inputs['Distance'].default_value = 0.01
    L.new(b.outputs['Color'], bump.inputs['Height'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(hsv.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.85
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def gravel_floor():
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=400, y_subdivisions=200, size=1, location=(0, 0.5, 0))
    ob = bpy.context.active_object
    ob.name = 'gravel'
    ob.scale = (12, 7, 1)
    R.apply_all(ob)
    R.displace(ob, 'CLOUDS', 1.2, 0.05, 2, noise_depth=3)
    R.apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(gravel_material())
    ob.pass_index = SAND
    return ob


def water_world():
    """Open water behind the reef: deep navy overhead, lighter toward the reef.
    The camera sees the full gradient; the light it casts is much dimmer, so
    the reef keeps dark crevices and strong shading."""
    w = bpy.data.worlds.new('tankwater')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    out = nt.nodes['World Output']
    bg = nt.nodes['Background']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    # (the camera sees directions only about 8 degrees above and below level)
    ramp.color_ramp.elements[0].position = 0.47
    ramp.color_ramp.elements[0].color = (0.025, 0.170, 0.360, 1)
    ramp.color_ramp.elements[1].position = 0.575
    ramp.color_ramp.elements[1].color = (0.002, 0.012, 0.065, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    dim = nt.nodes.new('ShaderNodeBackground')
    nt.links.new(ramp.outputs['Color'], dim.inputs['Color'])
    dim.inputs['Strength'].default_value = 0.30
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
    nt.links.new(dim.outputs['Background'], mix.inputs[1])
    nt.links.new(bg.outputs['Background'], mix.inputs[2])
    nt.links.new(mix.outputs['Shader'], out.inputs['Surface'])


def tank_water():
    ob = R.water_volume()
    # only the tank itself holds water: a long stretch of haze behind the reef
    # turned the water gradient into one flat blue
    ob.location = (0, -3.5, 2.0)
    ob.scale = (20, 13, 5)
    mat = ob.data.materials[0]
    for n in mat.node_tree.nodes:
        if n.type == 'SCATTER':
            n.inputs['Density'].default_value = 0.002
            n.inputs['Color'].default_value = (0.30, 0.65, 1.0, 1)
        if n.type == 'ABSORPTION':
            n.inputs['Density'].default_value = 0.012
    return ob


# ------------------------------------------------------------ the tank

def surface(x, y, top=4.0):
    """Where a coral dropped at (x, y) lands on the rock or gravel, and the
    surface normal there."""
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, nrm, _, ob, _ = bpy.context.scene.ray_cast(dg, Vector((x, y, top)), Vector((0, 0, -1)))
    if not hit:
        return Vector((x, y, 0.0)), Vector((0, 0, 1)), None
    return loc, nrm, ob


def front_face(x, z, y0=-3.0):
    """The first rock surface seen from the front at (x, z)."""
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, nrm, _, ob, _ = bpy.context.scene.ray_cast(dg, Vector((x, y0, z)), Vector((0, 1, 0)))
    return (loc, nrm) if hit else (None, None)


def craggy_rock(name, loc, scale, seed, mat, index):
    """A rough, porous piece of live rock: deep pits and cracks, not a cobble."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.rotation_euler = (random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), random.uniform(0, 6.3))
    R.displace(ob, 'VORONOI', 0.45, 0.55, seed, distance_metric='DISTANCE')
    R.displace(ob, 'STUCCI', 0.20, 0.22, seed, turbulence=6.0)
    R.displace(ob, 'CLOUDS', 0.12, 0.14, seed, noise_depth=4)
    R.displace(ob, 'VORONOI', 0.07, -0.10, seed, distance_metric='DISTANCE')   # pits
    R.apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(mat)
    ob.pass_index = index
    return ob


def build():
    common.reset_scene()
    random.seed(11)
    rockA = R.rock_material('rockA', 'rock_04', coralline=(0.85, 0.35, 0.65), algae=(0.25, 0.55, 0.15), seed=1, tile=0.9, cover=0.40)
    rockB = R.rock_material('rockB', 'coast_sand_rocks_02', coralline=(0.75, 0.30, 0.70), algae=(0.30, 0.60, 0.20), seed=2, tile=0.8, cover=0.40)
    rockC = R.rock_material('rockC', 'rock_04', coralline=(0.90, 0.45, 0.55), algae=(0.20, 0.50, 0.25), seed=3, tile=0.7, cover=0.40)
    gravel_floor()

    # the wall: a base course of wide, low pieces, then smaller pieces piled
    # irregularly on top, leaving gaps and ledges; it rises toward two peaks
    r = random.Random(7)
    mats = [rockA, rockB, rockC]
    pieces = []
    x = -3.9
    while x < 3.9:
        w = r.uniform(0.45, 0.75)
        pieces.append((x + w / 2, r.uniform(0.75, 1.05), r.uniform(0.0, 0.08), w * 0.65, r.uniform(0.40, 0.55), r.uniform(0.32, 0.48)))
        x += w * r.uniform(0.70, 0.90)
    def height_at(x):
        return 0.55 + 0.35 * math.exp(-((x + 1.6) / 1.1) ** 2) + 0.45 * math.exp(-((x - 1.4) / 0.9) ** 2)
    x = -3.6
    while x < 3.6:
        h = height_at(x)
        z = 0.35
        while z < h:
            w = r.uniform(0.30, 0.55)
            pieces.append((x + r.uniform(-0.1, 0.1), r.uniform(0.85, 1.25), z, w * 0.6, r.uniform(0.28, 0.40), r.uniform(0.18, 0.28)))
            z += r.uniform(0.18, 0.28)
        x += r.uniform(0.32, 0.50)
    rocks = []
    for i, (px, py, pz, sx, sy, sz) in enumerate(pieces):
        rocks.append(craggy_rock('wall%d' % i, (px, py, pz), (sx, sy, sz), 200 + i, mats[i % 3], MID))
    bpy.context.view_layer.update()

    # the moray's cave, low in a base piece left of center
    mouth_x = -2.0
    loc, nrm = front_face(mouth_x, 0.30)
    cave = min(rocks, key=lambda o: (o.location - Vector((mouth_x, 0.9, 0.1))).length)
    mouth = (loc if loc is not None else Vector((mouth_x, 0.4, 0.30))) + Vector((0, -0.02, 0))
    R.cut_cave(cave, mouth + Vector((-0.15, 0.20, 0.0)), (0.70, -0.70, 0.05), 0.15, 0.9)
    bpy.context.view_layer.update()

    def on_rock(x, y=0.9, sink=0.07):
        p, n, ob = surface(x, y)
        return p - Vector((0, 0, sink))

    if BARE:
        tank_water()
        return finish(rockA, mouth)

    # corals, each dropped onto the rock where it grows
    R.staghorn('stagG', tuple(on_rock(-1.65, 0.9)), 31, 1.7, (0.40, 0.17, 0.03), (0.95, 0.55, 0.15), MID)
    R.sea_fan('fanP', tuple(on_rock(1.55, 1.15)), 61, 1.35, (0.60, 0.03, 0.45), 0.05, MID)
    R.sea_fan('fanO', tuple(on_rock(-3.35, 1.10)), 62, 1.15, (0.90, 0.20, 0.05), -0.10, MID)
    bubble_coral('bubble', tuple(on_rock(-0.35, 0.85) + Vector((0, 0, 0.10))), 0.26, 41)
    brain('brainG', tuple(on_rock(0.55, 0.80)), 0.24, 21, (0.08, 0.30, 0.03), (0.35, 0.80, 0.10))
    brain('brainR', tuple(on_rock(2.55, 0.80)), 0.22, 22, (0.35, 0.04, 0.03), (0.85, 0.20, 0.12))
    brain('brainT', tuple(on_rock(-2.70, 0.75)), 0.22, 23, (0.35, 0.22, 0.05), (0.85, 0.60, 0.20))
    brain('brainB', tuple(on_rock(3.40, 0.85)), 0.20, 25, (0.03, 0.10, 0.40), (0.15, 0.45, 0.95))
    leather('leatherA', tuple(on_rock(-0.95, 1.05)), 0.32, 51, (0.30, 0.25, 0.08), (0.75, 0.62, 0.25), tilt=(0.25, 0.10))
    leather('leatherB', tuple(on_rock(2.10, 1.05)), 0.28, 52, (0.06, 0.30, 0.08), (0.30, 0.80, 0.25), tilt=(0.30, -0.15))
    leather('leatherC', tuple(on_rock(0.05, 1.10)), 0.24, 53, (0.35, 0.08, 0.25), (0.85, 0.35, 0.65), tilt=(0.30, 0.05))
    anemone('anemone', tuple(on_rock(1.00, 0.75)), 0.18, 71)
    finger_coral('fingerP', tuple(on_rock(-2.30, 1.0)), 81, 1.5, (0.30, 0.04, 0.32), (0.85, 0.20, 0.85))
    finger_coral('fingerY', tuple(on_rock(2.95, 1.0)), 82, 1.3, (0.45, 0.30, 0.01), (1.0, 0.80, 0.05))
    finger_coral('fingerB', tuple(on_rock(1.25, 1.05)), 83, 1.2, (0.02, 0.12, 0.45), (0.10, 0.50, 1.0))
    R.tube_sponge('tubesL', tuple(on_rock(-3.0, 0.55, 0.0)), 91, MID, col=(1.0, 0.45, 0.05))
    R.tube_sponge('tubesR', tuple(on_rock(3.70, 0.70, 0.0)), 92, MID, col=(0.95, 0.80, 0.10))
    for k, (zx, zz, col) in enumerate(((0.20, 0.32, (0.35, 0.95, 0.55)), (2.30, 0.28, (1.0, 0.55, 0.15)),
                                        (-1.20, 0.40, (0.95, 0.40, 0.75)), (3.10, 0.45, (0.40, 0.85, 1.0)))):
        p, n = front_face(zx, zz)
        if p is not None:
            zoanthids('zoa%d' % k, tuple(p), tuple(n), 0.07, 101 + k, col)

    scatter_corals(5, -3.9, 3.9)

    tank_water()
    R.surface_cookie()
    return finish(rockA, mouth)


def finish(rockA, mouth):
    if not BARE:
        R.rock('frontL', (-3.9, -2.0, -0.10), (0.45, 0.35, 0.28), 120, rockA, FRONT)
    else:
        R.surface_cookie()
    cam = bpy.data.cameras.new('cam')
    cam.lens = 50
    cam.sensor_width = 36
    camob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(camob)
    camob.location = (0, -9.6, 1.30)
    camob.rotation_euler = (math.radians(88.5), 0, 0)
    bpy.context.scene.camera = camob
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = TANK_W, 1080
    return camob, mouth


def lights():
    water_world()
    common.sun('key', (0.10, 0.25, -1.0), 13.0, (1.0, 0.98, 0.94), angle=1.0)
    common.sun('fill', (0.0, 1.0, -0.35), 0.6, (0.85, 0.93, 1.0), angle=25)
    bpy.context.scene.view_settings.exposure = 0.0
    # saturated living tissue: little light scattering through the corals
    for m in bpy.data.materials:
        if m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == 'BSDF_PRINCIPLED' and n.inputs['Subsurface Weight'].default_value > 0.15:
                    n.inputs['Subsurface Weight'].default_value = 0.12


def main():
    os.makedirs(R.OUT, exist_ok=True)
    camob, mouth = build()
    lights()
    R.SWAY[:] = [] if BARE else ['stagG', 'fanP', 'fanO', 'anemone']
    if QUICK:
        common.render_settings(32, transparent=False)
        sc = bpy.context.scene
        sc.cycles.volume_bounces = 1
        sc.cycles.volume_step_rate = 6.0
        sc.render.filepath = os.path.join(R.OUT, 'tank_quick.png')
        bpy.ops.render.render(write_still=True)
        return
    import json
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    p = world_to_camera_view(sc, camob, mouth)
    p2 = world_to_camera_view(sc, camob, mouth + Vector((1, 0, 0)))
    info = {'width': TANK_W, 'cave_mouth': [p.x * TANK_W, (1 - p.y) * 1080, p.z],
            'px_per_m_at_cave': (p2.x - p.x) * TANK_W,
            'camera': {'loc': list(camob.location), 'rot': list(camob.rotation_euler),
                       'lens': camob.data.lens, 'sensor': camob.data.sensor_width}}
    for n in R.SWAY:
        bpy.data.objects[n].hide_render = True
    R.render_beauty(os.path.join(R.OUT, 'scene_beauty.png'))
    R.render_sand(os.path.join(R.OUT, 'scene_sand.png'))
    R.render_mask(os.path.join(R.OUT, 'scene_mask.png'))
    R.render_posnrm(os.path.join(R.OUT, 'scene_posnrm.png'))
    for n in R.SWAY:
        bpy.data.objects[n].hide_render = False
    sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
    info['corals'] = R.render_corals(camob, R.OUT)
    json.dump(info, open(os.path.join(R.OUT, 'scene.json'), 'w'), indent=1)


main()

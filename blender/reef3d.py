"""Blender script: builds the reef and renders the tank's still layers.

    blender -b --factory-startup -P reef3d.py -- <textures dir> <out dir> [samples]

Writes:
  scene_beauty.png   the whole reef, water haze and light shafts (the background)
  scene_mask.png     R = middle reef, G = front rocks, B = sand (for cutting layers)
  scene.json         camera and the screen position of the moray cave

The middle and front layers are cut from the one beauty render with the mask,
so every layer has exactly the same light.
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector, Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
TEX, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
SAMPLES = int(argv[2]) if len(argv) > 2 else 256
W, H = 1920, 1080

MID, FRONT, SAND = 1, 2, 3


def tex(name, colorspace='sRGB'):
    for ext in ('jpg', 'png'):
        p = os.path.join(TEX, name + '.' + ext)
        if os.path.exists(p):
            im = bpy.data.images.load(p, check_existing=True)
            im.colorspace_settings.name = colorspace
            return im
    raise FileNotFoundError(name)


def apply_all(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def displace(ob, kind, size, strength, seed, **kw):
    t = bpy.data.textures.new('%s_%s' % (ob.name, kind), kind)
    t.noise_scale = size
    for k, v in kw.items():
        setattr(t, k, v)
    m = ob.modifiers.new('d_' + kind, 'DISPLACE')
    m.texture = t
    m.strength = strength
    m.texture_coords = 'GLOBAL'
    return m


# ------------------------------------------------------------ materials

def nodes(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return mat, nt, nt.nodes.new('ShaderNodeOutputMaterial')


def boxtex(nt, image, scale, coords):
    m = nt.nodes.new('ShaderNodeMapping')
    m.inputs['Scale'].default_value = (scale, scale, scale)
    nt.links.new(coords, m.inputs['Vector'])
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = image
    t.projection = 'BOX'
    t.projection_blend = 0.35
    nt.links.new(m.outputs['Vector'], t.inputs['Vector'])
    return t


def rock_material(name, base_tex, coralline=(0.55, 0.20, 0.42), algae=(0.18, 0.30, 0.10), tile=0.9, seed=0, cover=0.0):
    mat, nt, out = nodes(name)
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    pos = tc.outputs['Object']
    diff = boxtex(nt, tex(base_tex + '_diff'), tile, pos)
    rough = boxtex(nt, tex(base_tex + '_rough', 'Non-Color'), tile, pos)
    disp = boxtex(nt, tex(base_tex + '_disp', 'Non-Color'), tile, pos)
    # patches of pink coralline algae and green turf
    n1 = nt.nodes.new('ShaderNodeTexNoise')
    n1.inputs['Scale'].default_value = 1.8
    n1.inputs['Detail'].default_value = 8
    n1.noise_dimensions = '4D'
    n1.inputs['W'].default_value = seed
    L.new(pos, n1.inputs['Vector'])
    r1 = nt.nodes.new('ShaderNodeValToRGB')
    r1.color_ramp.elements[0].position = 0.56 - 0.22 * cover
    r1.color_ramp.elements[1].position = 0.72 - 0.22 * cover
    L.new(n1.outputs['Fac'], r1.inputs['Fac'])
    m1 = nt.nodes.new('ShaderNodeMix')
    m1.data_type = 'RGBA'
    m1.blend_type = 'MULTIPLY'
    L.new(r1.outputs['Color'], m1.inputs['Factor'])
    L.new(diff.outputs['Color'], m1.inputs['A'])
    m1.inputs['B'].default_value = (*[c * 1.45 for c in coralline], 1)
    n2 = nt.nodes.new('ShaderNodeTexNoise')
    n2.inputs['Scale'].default_value = 3.5
    n2.inputs['Detail'].default_value = 6
    n2.noise_dimensions = '4D'
    n2.inputs['W'].default_value = seed + 7
    L.new(pos, n2.inputs['Vector'])
    r2 = nt.nodes.new('ShaderNodeValToRGB')
    r2.color_ramp.elements[0].position = 0.55 - 0.15 * cover
    r2.color_ramp.elements[1].position = 0.68 - 0.15 * cover
    L.new(n2.outputs['Fac'], r2.inputs['Fac'])
    # algae grows on the tops (normal pointing up)
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L.new(geo.outputs['Normal'], sep.inputs['Vector'])
    up = nt.nodes.new('ShaderNodeMath')
    up.operation = 'MULTIPLY'
    L.new(sep.outputs['Z'], up.inputs[0])
    L.new(r2.outputs['Color'], up.inputs[1])
    m2 = nt.nodes.new('ShaderNodeMix')
    m2.data_type = 'RGBA'
    L.new(up.outputs['Value'], m2.inputs['Factor'])
    L.new(m1.outputs['Result'], m2.inputs['A'])
    m2.inputs['B'].default_value = (*algae, 1)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(m2.outputs['Result'], bsdf.inputs['Base Color'])
    L.new(rough.outputs['Color'], bsdf.inputs['Roughness'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.2
    bump.inputs['Distance'].default_value = 0.04
    L.new(disp.outputs['Color'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def sand_material():
    mat, nt, out = nodes('sand')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    pos = tc.outputs['Object']
    d1 = boxtex(nt, tex('dense_sand_diff'), 0.7, pos)
    d2 = boxtex(nt, tex('coral_ground_02_diff'), 0.5, pos)
    b1 = boxtex(nt, tex('dense_sand_disp', 'Non-Color'), 0.7, pos)
    b2 = boxtex(nt, tex('coral_ground_02_disp', 'Non-Color'), 0.5, pos)
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 0.35
    n.inputs['Detail'].default_value = 6
    L.new(pos, n.inputs['Vector'])
    r = nt.nodes.new('ShaderNodeValToRGB')
    r.color_ramp.elements[0].position = 0.50
    r.color_ramp.elements[1].position = 0.62
    L.new(n.outputs['Fac'], r.inputs['Fac'])
    mx = nt.nodes.new('ShaderNodeMix')
    mx.data_type = 'RGBA'
    L.new(r.outputs['Color'], mx.inputs['Factor'])
    L.new(d1.outputs['Color'], mx.inputs['A'])
    L.new(d2.outputs['Color'], mx.inputs['B'])
    # bleach toward reef-sand white
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = 0.75
    hsv.inputs['Value'].default_value = 1.35
    L.new(mx.outputs['Result'], hsv.inputs['Color'])
    hm = nt.nodes.new('ShaderNodeMix')
    L.new(r.outputs['Color'], hm.inputs['Factor'])
    L.new(b1.outputs['Color'], hm.inputs['A'])
    L.new(b2.outputs['Color'], hm.inputs['B'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    bump.inputs['Distance'].default_value = 0.02
    L.new(hm.outputs['Result'], bump.inputs['Height'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(hsv.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.9
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def coral_material(name, base, tip, sss=0.35, rough=0.55, bumpscale=40.0, pointy=False):
    """Living tissue: color from base to tip by height, subsurface glow, fine polyp bumps."""
    mat, nt, out = nodes(name)
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L.new(tc.outputs['Generated'], sep.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*base, 1)
    ramp.color_ramp.elements[1].color = (*tip, 1)
    ramp.color_ramp.elements[0].position = 0.15
    ramp.color_ramp.elements[1].position = 0.95
    L.new(sep.outputs['Z'], ramp.inputs['Fac'])
    col = ramp.outputs['Color']
    if pointy:      # grooves darker (brain coral)
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        pr = nt.nodes.new('ShaderNodeValToRGB')
        pr.color_ramp.elements[0].position = 0.45
        pr.color_ramp.elements[0].color = (0.25, 0.25, 0.25, 1)
        pr.color_ramp.elements[1].position = 0.56
        L.new(geo.outputs['Pointiness'], pr.inputs['Fac'])
        mm = nt.nodes.new('ShaderNodeMix')
        mm.data_type = 'RGBA'
        mm.blend_type = 'MULTIPLY'
        mm.inputs['Factor'].default_value = 1.0
        L.new(col, mm.inputs['A'])
        L.new(pr.outputs['Color'], mm.inputs['B'])
        col = mm.outputs['Result']
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(col, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Subsurface Weight'].default_value = sss
    bsdf.inputs['Subsurface Scale'].default_value = 0.02
    L.new(col, bsdf.inputs['Subsurface Radius'])
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = bumpscale
    L.new(tc.outputs['Object'], vor.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.35
    bump.inputs['Distance'].default_value = 0.004
    L.new(vor.outputs['Distance'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


# ------------------------------------------------------------ objects

def rock(name, loc, scale, seed, mat, index, rot=0.0, sub=6):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    ob.rotation_euler = (0, 0, rot)
    r = random.Random(seed)
    ob.location = (loc[0], loc[1], loc[2])
    displace(ob, 'VORONOI', 0.55 + r.random() * 0.3, 0.38, seed, distance_metric='DISTANCE')
    displace(ob, 'CLOUDS', 0.22, 0.18, seed, noise_depth=5)
    displace(ob, 'CLOUDS', 0.06, 0.04, seed, noise_depth=3)
    apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(mat)
    ob.pass_index = index
    return ob


def cut_cave(ob, center, direction, radius, depth):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=radius, depth=depth, location=center)
    cyl = bpy.context.active_object
    cyl.rotation_euler = Vector(direction).to_track_quat('Z', 'Y').to_euler()
    cyl.scale = (1.0, 0.75, 1.0)
    displace(cyl, 'CLOUDS', 0.15, 0.06, 3)
    apply_all(cyl)
    m = ob.modifiers.new('cave', 'BOOLEAN')
    m.operation = 'DIFFERENCE'
    m.object = cyl
    m.solver = 'EXACT'
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier='cave')
    bpy.data.objects.remove(cyl)


def brain_coral(name, loc, radius, seed, index):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=160, ring_count=80, radius=radius, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (1.0, 1.0, 0.72)
    t = bpy.data.textures.new(name + '_m', 'MARBLE')
    t.marble_type = 'SHARP'
    t.noise_basis_2 = 'SIN'
    t.noise_scale = 0.035 * radius / 0.3
    t.turbulence = 9.0
    t.noise_depth = 3
    m = ob.modifiers.new('grooves', 'DISPLACE')
    m.texture = t
    m.strength = 0.05 * radius / 0.3
    m.texture_coords = 'GLOBAL'
    apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(coral_material(name, (0.40, 0.42, 0.10), (0.85, 0.78, 0.30), sss=0.4, pointy=True, bumpscale=90))
    ob.pass_index = index
    return ob


def branch_mesh(name, base, seed, levels, length, radius, spread, planar=False, up=0.0):
    r = random.Random(seed)
    verts, edges, radii = [], [], []

    def grow(p, d, ln, rad, lv, parent):
        q = p + d * ln
        verts.append(q)
        radii.append(rad)
        idx = len(verts) - 1
        edges.append((parent, idx))
        if lv == 0:
            return
        n = 2 if r.random() < 0.75 else 3
        for i in range(n):
            if planar:
                ang = (i - (n - 1) / 2) * spread + r.uniform(-0.12, 0.12)
                nd = Matrix.Rotation(ang, 3, 'Y') @ d
            else:
                axis = Vector((r.uniform(-1, 1), r.uniform(-1, 1), 0)).normalized()
                nd = Matrix.Rotation(spread * r.uniform(0.6, 1.2), 3, axis) @ d
            nd = (nd + Vector((0, 0, up))).normalized()
            grow(q, nd, ln * r.uniform(0.70, 0.86), rad * 0.78, lv - 1, idx)

    verts.append(Vector(base))
    radii.append(radius * 1.2)
    trunks = 4 if not planar else 1
    for k in range(trunks):
        if planar:
            d = Vector((0, 0, 1))
        else:
            d = Vector((r.uniform(-0.5, 0.5), r.uniform(-0.5, 0.5), 1)).normalized()
        grow(Vector(base), d, length, radius, levels, 0)
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], edges, [])
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    skin = ob.modifiers.new('skin', 'SKIN')
    for i, sv in enumerate(me.skin_vertices[0].data):
        sv.radius = (radii[i], radii[i])
    me.skin_vertices[0].data[0].use_root = True
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 2
    return ob


def staghorn(name, base, seed, scale, base_col, tip_col, index):
    ob = branch_mesh(name, base, seed, 5, 0.16 * scale, 0.035 * scale, 0.55, up=0.35)
    ob.data.materials.append(coral_material(name, base_col, tip_col, sss=0.55, rough=0.45, bumpscale=140))
    ob.pass_index = index
    return ob


def sea_fan(name, base, seed, scale, col, rot, index):
    ob = branch_mesh(name, (0, 0, 0), seed, 10, 0.20 * scale, 0.012 * scale, 0.27, planar=True, up=0.12)
    ob.location = base
    ob.rotation_euler = (0, 0, rot)
    ob.data.materials.append(coral_material(name, tuple(c * 0.75 for c in col), col, sss=0.6, bumpscale=200))
    ob.pass_index = index
    return ob


def tube_sponge(name, base, seed, index, col=(0.75, 0.35, 0.06)):
    r = random.Random(seed)
    obs = []
    for k in range(4):
        h = r.uniform(0.55, 1.05)
        rad = r.uniform(0.08, 0.13)
        off = Vector((r.uniform(-0.15, 0.15), r.uniform(-0.12, 0.12), 0))
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=rad, depth=h,
                                            location=Vector(base) + off + Vector((0, 0, h / 2 - 0.05)))
        ob = bpy.context.active_object
        ob.rotation_euler = (r.uniform(-0.2, 0.2), r.uniform(-0.2, 0.2), 0)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        top = [f for f in bm.faces if f.normal.z > 0.9]
        bmesh.ops.delete(bm, geom=top, context='FACES_ONLY')
        bm.to_mesh(ob.data)
        bm.free()
        sol = ob.modifiers.new('sol', 'SOLIDIFY')
        sol.thickness = 0.018
        displace(ob, 'CLOUDS', 0.05, 0.012, seed + k)
        sub = ob.modifiers.new('sub', 'SUBSURF')
        sub.levels = sub.render_levels = 2
        apply_all(ob)
        ob.data.shade_smooth()
        ob.data.materials.append(coral_material(name, tuple(c * 0.7 for c in col), col, sss=0.3, bumpscale=60))
        ob.pass_index = index
        obs.append(ob)
    return obs


def sand(mat):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=500, y_subdivisions=500, size=60, location=(0, 18, 0))
    ob = bpy.context.active_object
    ob.name = 'sand'
    displace(ob, 'CLOUDS', 3.0, 0.35, 1, noise_depth=3)
    t = bpy.data.textures.new('ripples', 'WOOD')
    t.wood_type = 'BANDNOISE'
    t.noise_scale = 0.4
    t.turbulence = 6
    m = ob.modifiers.new('ripples', 'DISPLACE')
    m.texture = t
    m.strength = 0.025
    m.texture_coords = 'GLOBAL'
    apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(mat)
    ob.pass_index = SAND
    return ob


def rubble(mat, n, seed, area):
    """Broken coral and shell bits lying on the sand."""
    r = random.Random(seed)
    for i in range(n):
        x = r.uniform(area[0], area[1])
        y = r.uniform(area[2], area[3])
        s = r.uniform(0.010, 0.035) * (1 + 1.5 * r.random() ** 6)
        ob = rock('rubble%d' % i, (x, y, s * 0.1), (s * r.uniform(1.0, 2.5), s, s * 0.45), seed + i, mat, 0, sub=3)
        ob.rotation_euler = (r.uniform(-0.3, 0.3), r.uniform(-0.3, 0.3), r.uniform(0, 6.3))


def water_volume():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 15, 2.0))
    ob = bpy.context.active_object
    ob.name = 'water'
    ob.scale = (80, 80, 5.0)
    mat, nt, out = nodes('water')
    sc = nt.nodes.new('ShaderNodeVolumeScatter')
    sc.inputs['Color'].default_value = (0.22, 0.55, 0.95, 1)
    sc.inputs['Density'].default_value = 0.075
    sc.inputs['Anisotropy'].default_value = 0.70
    ab = nt.nodes.new('ShaderNodeVolumeAbsorption')
    ab.inputs['Color'].default_value = (0.30, 0.66, 0.95, 1)
    ab.inputs['Density'].default_value = 0.09
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(sc.outputs['Volume'], add.inputs[0])
    nt.links.new(ab.outputs['Volume'], add.inputs[1])
    nt.links.new(add.outputs['Shader'], out.inputs['Volume'])
    ob.data.materials.append(mat)
    return ob


def surface_cookie():
    """An invisible, dappled sheet at the water surface: its shadow makes the
    shafts of light in the water and the bright net on the sand."""
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 15, 4.4))
    ob = bpy.context.active_object
    ob.name = 'surface'
    mat, nt, out = nodes('surface')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    v = nt.nodes.new('ShaderNodeTexVoronoi')
    v.feature = 'DISTANCE_TO_EDGE'
    v.inputs['Scale'].default_value = 1.6
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.6
    mixv = nt.nodes.new('ShaderNodeVectorMath')
    mixv.operation = 'ADD'
    L.new(tc.outputs['Object'], mixv.inputs[0])
    L.new(nz.outputs['Color'], mixv.inputs[1])
    L.new(mixv.outputs['Vector'], v.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1, 1, 1, 1)     # light passes at the cell edges
    ramp.color_ramp.elements[1].position = 0.08
    ramp.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)
    L.new(v.outputs['Distance'], ramp.inputs['Fac'])
    tp = nt.nodes.new('ShaderNodeBsdfTransparent')
    L.new(ramp.outputs['Color'], tp.inputs['Color'])
    L.new(tp.outputs['BSDF'], out.inputs['Surface'])
    ob.data.materials.append(mat)
    ob.visible_camera = False
    return ob


# ------------------------------------------------------------ the tank

def build():
    common.reset_scene()
    random.seed(5)
    rockA = rock_material('rockA', 'coast_sand_rocks_02', seed=1, tile=0.7)
    rockB = rock_material('rockB', 'rock_04', coralline=(0.60, 0.30, 0.50), seed=2, tile=0.8)
    rockC = rock_material('rockC', 'lichen_rock', coralline=(0.50, 0.30, 0.40), seed=3, tile=0.6)
    sandm = sand_material()
    sand(sandm)

    # far rocks, lost in the haze
    for i, (x, y, s) in enumerate(((-9, 16, 3.0), (-3, 20, 2.5), (5, 18, 3.5), (11, 14, 2.6), (1, 26, 4))):
        rock('far%d' % i, (x, y, 0.2), (s, s * 0.8, s * 0.55), 40 + i, rockC, 0)

    # the left formation, with the moray's cave
    cave = rock('caveRock', (-2.9, 1.2, 0.15), (1.35, 1.0, 1.05), 11, rockA, MID, rot=0.3)
    cave_mouth = Vector((-2.35, 0.40, 0.70))
    cut_cave(cave, cave_mouth + Vector((-0.20, 0.17, 0.0)), (0.75, -0.65, 0.05), 0.20, 0.9)
    rock('leftTop', (-3.4, 1.9, 1.35), (0.9, 0.8, 0.55), 12, rockB, MID, rot=1.1)
    rock('leftBack', (-4.6, 3.2, 0.3), (1.4, 1.2, 1.3), 13, rockB, MID)
    brain_coral('brainL', (-2.6, 1.6, 1.62), 0.42, 21, MID)
    staghorn('stagL', (-3.6, 2.0, 1.70), 31, 2.1, (0.55, 0.28, 0.08), (1.00, 0.78, 0.35), MID)
    tube_sponge('tubeL', (-1.75, 1.6, 0.25), 51, MID, col=(1.0, 0.42, 0.04))

    # the right formation
    rock('rightBase', (3.0, 1.6, 0.1), (1.5, 1.1, 0.95), 14, rockB, MID, rot=-0.4)
    rock('rightTop', (3.3, 2.0, 1.0), (0.85, 0.75, 0.75), 15, rockA, MID, rot=0.6)
    rock('rightBack', (4.8, 3.6, 0.4), (1.3, 1.1, 1.6), 16, rockC, MID)
    sea_fan('fanR', (3.6, 2.5, 1.55), 61, 2.4, (0.85, 0.10, 0.60), 0.15, MID)
    staghorn('stagR', (2.5, 1.3, 0.95), 32, 2.4, (0.28, 0.08, 0.50), (0.78, 0.50, 1.00), MID)
    brain_coral('brainR', (2.25, 0.9, 0.45), 0.30, 22, MID)
    tube_sponge('tubeR', (3.9, 1.0, 0.35), 52, MID, col=(1.0, 0.82, 0.08))

    # a small outcrop out in the middle distance
    rock('midRock', (0.6, 5.5, 0.05), (0.9, 0.7, 0.45), 17, rockA, MID)
    staghorn('stagM', (0.6, 5.5, 0.4), 33, 1.6, (0.08, 0.38, 0.22), (0.45, 1.00, 0.60), MID)

    # dark rocks close to the glass in the bottom corners
    rock('frontL', (-2.25, -3.2, -0.25), (1.05, 0.7, 0.62), 18, rockB, FRONT)
    brain_coral('brainF', (-1.75, -3.25, 0.15), 0.22, 23, FRONT)

    rub = rock_material('rubble', 'coral_ground_02', coralline=(0.55, 0.45, 0.42), algae=(0.35, 0.38, 0.25), tile=4.0, seed=9)
    rubble(rub, 90, 300, (-4, 4, -2.5, 6))
    water_volume()
    surface_cookie()

    cam = bpy.data.cameras.new('cam')
    cam.lens = 30
    cam.sensor_width = 36
    camob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(camob)
    camob.location = (0, -6.0, 1.05)
    camob.rotation_euler = (math.radians(87), 0, 0)
    bpy.context.scene.camera = camob
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = W, H
    return camob, cave_mouth


def lights():
    w = bpy.data.worlds.new('deep')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs['Color'].default_value = (0.002, 0.02, 0.07, 1)
    bg.inputs['Strength'].default_value = 1.0
    common.sun('key', (0.12, 0.30, -1.0), 11.0, (1.0, 0.98, 0.92), angle=0.8)


def render_beauty(path):
    common.render_settings(SAMPLES, transparent=False)
    sc = bpy.context.scene
    sc.cycles.volume_bounces = 1
    sc.cycles.volume_step_rate = 4.0
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def render_sand(path):
    """The same view without the dappled surface: the sand without the light
    net, which the channel animates on top instead."""
    bpy.data.objects['surface'].hide_render = True
    bpy.data.objects['key'].data.energy *= 0.55
    sc = bpy.context.scene
    sc.cycles.samples = max(64, SAMPLES // 2)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects['key'].data.energy /= 0.55


SWAY = ['stagL', 'stagR', 'fanR', 'stagM']     # corals that move with the current: own animated layers
SWAY_FRAMES = 1      # one still image each; the channel sways it


def emission_override(name, color_socket_fn):
    mat, nt, out = nodes(name)
    em = nt.nodes.new('ShaderNodeEmission')
    color_socket_fn(nt, em.inputs['Color'])
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return mat


def raw_settings(samples):
    sc = bpy.context.scene
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'


def render_mask(path):
    for name in ('water', 'surface'):
        bpy.data.objects[name].hide_render = True

    def fn(nt, sock):
        oi = nt.nodes.new('ShaderNodeObjectInfo')
        comb = nt.nodes.new('ShaderNodeCombineColor')
        for ch, idx in (('Red', MID), ('Green', FRONT), ('Blue', SAND)):
            c = nt.nodes.new('ShaderNodeMath')
            c.operation = 'COMPARE'
            c.inputs[1].default_value = idx
            c.inputs[2].default_value = 0.1
            nt.links.new(oi.outputs['Object Index'], c.inputs[0])
            nt.links.new(c.outputs['Value'], comb.inputs[ch])
        nt.links.new(comb.outputs['Color'], sock)
    bpy.context.view_layer.material_override = emission_override('maskmat', fn)
    bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0
    raw_settings(16)
    sc = bpy.context.scene
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def render_posnrm(path):
    """Where every pixel is on the ground plan (x, y) and how much it faces up:
    the caustics are drawn from this, on rocks as well as sand.
    R = (x + 20) / 40, G = (y + 10) / 60, B = normal z * 0.5 + 0.5, 16 bit, no color transform."""
    def fn(nt, sock):
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        sp = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(geo.outputs['Position'], sp.inputs['Vector'])
        sn = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(geo.outputs['Normal'], sn.inputs['Vector'])
        comb = nt.nodes.new('ShaderNodeCombineColor')
        for ch, src, add, mul in (('Red', sp.outputs['X'], 20.0, 1 / 40), ('Green', sp.outputs['Y'], 10.0, 1 / 60),
                                  ('Blue', sn.outputs['Z'], 1.0, 0.5)):
            a = nt.nodes.new('ShaderNodeMath')
            a.operation = 'MULTIPLY_ADD'
            nt.links.new(src, a.inputs[0])
            a.inputs[1].default_value = mul
            a.inputs[2].default_value = add * mul
            nt.links.new(a.outputs['Value'], comb.inputs[ch])
        nt.links.new(comb.outputs['Color'], sock)
    bpy.context.view_layer.material_override = emission_override('posmat', fn)
    sc = bpy.context.scene
    raw_settings(8)
    sc.view_settings.view_transform = 'Raw'
    sc.render.film_transparent = False
    sc.render.image_settings.color_depth = '16'
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    sc.render.image_settings.color_depth = '8'
    sc.view_settings.view_transform = 'Standard'


def coral_rest(obs):
    """Bake the skin/subdivision into plain meshes and keep their rest shape."""
    rest = {}
    for ob in obs:
        bpy.context.view_layer.objects.active = ob
        for o in bpy.context.view_layer.objects:
            o.select_set(o == ob)
        bpy.ops.object.convert(target='MESH')
        co = [ob.matrix_world @ v.co for v in ob.data.vertices]
        z0 = min(c.z for c in co)
        z1 = max(c.z for c in co)
        rest[ob.name] = ([v.co.copy() for v in ob.data.vertices], z0, z1)
    return rest


def sway(ob, rest, phase):
    """Bend a coral with the current: tips move most, base not at all."""
    vs, z0, z1 = rest[ob.name]
    mw = ob.matrix_world
    inv = mw.inverted()
    amp = 0.035 * (z1 - z0)
    for v, r in zip(ob.data.vertices, vs):
        w = mw @ r
        h = max(0.0, (w.z - z0) / max(z1 - z0, 1e-6))
        k = h ** 1.6
        dx = amp * k * (math.sin(phase + h * 1.2) + 0.3 * math.sin(2 * phase + 0.7))
        dy = 0.6 * amp * k * math.cos(phase + h * 0.9)
        v.co = inv @ (w + Vector((dx, dy, -0.15 * amp * k * k)))
    ob.data.update()


def screen_box(sc, cam, ob, margin=0.06):
    pts = [world_to_camera_view(sc, cam, ob.matrix_world @ Vector(c)) for c in ob.bound_box]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    x0, x1 = max(0.0, min(xs) - margin), min(1.0, max(xs) + margin)
    y0, y1 = max(0.0, min(ys) - margin), min(1.0, max(ys) + margin)
    return x0, x1, y0, y1


def render_corals(camob, outdir):
    """Each swaying coral alone, at SWAY_FRAMES phases of one sway, the rest of
    the reef held out (so it is hidden behind rock where it should be) and the
    water haze in front of it.  A second, plain pass of each frame gives its
    exact outline."""
    sc = bpy.context.scene
    obs = [bpy.data.objects[n] for n in SWAY]
    rest = coral_rest(obs)
    info = {}
    white = emission_override('white', lambda nt, sock: setattr(sock, 'default_value', (1, 1, 1, 1)))
    others = [o for o in sc.objects if o.type == 'MESH' and o.name not in SWAY and o.name not in ('water', 'surface')]
    for o in others:
        o.is_holdout = True
    for ob in obs:
        for o2 in obs:
            o2.hide_render = o2 is not ob
            o2.is_holdout = False
        x0, x1, y0, y1 = screen_box(sc, camob, ob)
        sc.render.use_border = True
        sc.render.use_crop_to_border = True
        sc.render.border_min_x, sc.render.border_max_x = x0, x1
        sc.render.border_min_y, sc.render.border_max_y = y0, y1
        info[ob.name] = {'x': round(x0 * W), 'y': round((1 - y1) * H), 'w': round((x1 - x0) * W), 'h': round((y1 - y0) * H),
                         'frames': SWAY_FRAMES}
        for k in range(SWAY_FRAMES):
            sway(ob, rest, 2 * math.pi * k / SWAY_FRAMES)
            # with the water and the light from the surface
            bpy.context.view_layer.material_override = None
            for n in ('water', 'surface'):
                bpy.data.objects[n].hide_render = False
            sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
            common.render_settings(max(96, SAMPLES // 2), transparent=True)
            sc.cycles.volume_bounces = 1
            sc.cycles.volume_step_rate = 4.0
            sc.render.filepath = os.path.join(outdir, 'coral_%s_%02d.png' % (ob.name, k))
            bpy.ops.render.render(write_still=True)
            # its outline
            for n in ('water', 'surface'):
                bpy.data.objects[n].hide_render = True
            bpy.context.view_layer.material_override = white
            sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0
            raw_settings(16)
            sc.render.filepath = os.path.join(outdir, 'coralmask_%s_%02d.png' % (ob.name, k))
            bpy.ops.render.render(write_still=True)
    sc.render.use_border = False
    bpy.context.view_layer.material_override = None
    return info


def main():
    os.makedirs(OUT, exist_ok=True)
    camob, mouth = build()
    lights()
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    p = world_to_camera_view(sc, camob, mouth)
    info = {'cave_mouth': [p.x * W, (1 - p.y) * H, p.z],
            'camera': {'loc': list(camob.location), 'rot': list(camob.rotation_euler),
                       'lens': camob.data.lens, 'sensor': camob.data.sensor_width}}
    # how big 1 m looks at the cave, for scaling the moray sprite
    p2 = world_to_camera_view(sc, camob, mouth + Vector((1, 0, 0)))
    info['px_per_m_at_cave'] = (p2.x - p.x) * W
    if '--blend' in sys.argv:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'reef.blend'))
    # the still layers, without the swaying corals (they are drawn on top, moving)
    for n in SWAY:
        bpy.data.objects[n].hide_render = True
    render_beauty(os.path.join(OUT, 'scene_beauty.png'))
    render_sand(os.path.join(OUT, 'scene_sand.png'))
    render_mask(os.path.join(OUT, 'scene_mask.png'))
    render_posnrm(os.path.join(OUT, 'scene_posnrm.png'))
    for n in SWAY:
        bpy.data.objects[n].hide_render = False
    info['corals'] = render_corals(camob, OUT)
    json.dump(info, open(os.path.join(OUT, 'scene.json'), 'w'), indent=1)


if __name__ == "__main__":
    main()

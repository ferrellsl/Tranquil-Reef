"""Blender script: the reef tank as one lit 3D scene, with the photo corals
in it as relief models (photos/inflate.py), so one light from above lights
everything: corals cast shadows on the rock and each other, overhangs shade
what is under them, caves between the rocks go dark.

    blender -b --factory-startup -P reeftank.py -- <textures dir> <out dir> [samples] [--quick]

Writes the same passes as tank3d.py into <out dir>: scene_beauty, scene_sand,
scene_mask (R reef incl. corals, G things in front: the gravel's face against
the glass and corals out on the gravel, B gravel top), scene_posnrm, scene.json.
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import reef3d as R  # noqa: E402
import photo3d_mesh as PM  # noqa: E402

TANK_W = 2688
R.W = TANK_W
QUICK = '--quick' in sys.argv
MID, FRONT, SAND = R.MID, R.FRONT, R.SAND
PHOTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'photo')

# the corals: (cut-out, x, y (depth: negative = nearer the glass), height in m, where)
#   where: 'top' on the rock under (x, y); 'face' on the rock face seen from the front at height z=y;
#          'gravel' on the gravel (in front of the reef: drawn in front of the fish too)
LAYOUT = [
    ('elkhorn4', 1.20, 0.95, 1.30, 'top'),
    ('elkhorn1', -2.25, 0.95, 0.80, 'top'),
    ('pillar1', -0.55, 1.00, 1.15, 'top'),
    ('sponge3', -1.25, 1.25, 1.20, 'top'),
    ('staghorn1', 2.80, 1.15, 0.85, 'top'),
    ('bubble1', 0.20, 0.80, 0.45, 'top'),
    ('brain1', 0.65, 0.75, 0.52, 'top'),
    ('brain4', 3.10, 0.80, 0.50, 'top'),
    ('sponge2', -3.15, 0.90, 0.75, 'top'),
    ('sponge1', 3.65, 0.95, 0.75, 'top'),
    ('elkhorn3', 2.05, 1.05, 0.62, 'top'),
    ('sponge4', -1.75, 0.85, 0.60, 'top'),
    ('brain6', -2.85, 0.75, 0.40, 'top'),
    ('plate2', 1.85, 0.30, 0.48, 'face'),
    ('brain2', -0.20, 0.25, 0.42, 'face'),
    ('finger4', 0.95, 0.20, 0.40, 'face'),
    ('anemone1', -3.20, -0.75, 0.80, 'gravel'),
    ('brain3', -1.35, -0.80, 0.58, 'gravel'),
    ('brain5', 2.35, -0.90, 0.50, 'gravel'),
    ('elkhorn3', -0.30, -0.95, 0.42, 'gravel'),
]
BANK_FRONT = -2.6        # the glass: where the gravel bank's front face is
CAVE_X = 0.50             # the moray's cave, along the reef (clear of the corals on the gravel)


def porous_rock(name, loc, scale, seed, mat, index):
    """Grey-white porous live rock, full of deep holes."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=1.0, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = scale
    r = random.Random(seed)
    ob.rotation_euler = (r.uniform(-0.3, 0.3), r.uniform(-0.3, 0.3), r.uniform(0, 6.3))
    R.displace(ob, 'VORONOI', 0.45, 0.50, seed, distance_metric='DISTANCE')
    R.displace(ob, 'STUCCI', 0.20, 0.20, seed, turbulence=6.0)
    R.displace(ob, 'VORONOI', 0.10, -0.22, seed + 1, distance_metric='DISTANCE')    # holes
    R.displace(ob, 'VORONOI', 0.045, -0.08, seed + 2, distance_metric='DISTANCE')   # pores
    R.apply_all(ob)
    ob.data.shade_smooth()
    ob.data.materials.append(mat)
    ob.pass_index = index
    return ob


def rock_mat():
    """Grey-white limestone with a little coralline pink and turf, dark in its pores."""
    mat = R.rock_material('liverock', 'rock_04', coralline=(0.70, 0.42, 0.50), algae=(0.35, 0.42, 0.25),
                          seed=4, tile=0.8, cover=0.15)
    for n in mat.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Roughness'].default_value = 0.9
    # lighten the stone toward grey-white
    nt = mat.node_tree
    bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    src = bsdf.inputs['Base Color'].links[0].from_socket
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = 0.70
    hsv.inputs['Value'].default_value = 0.95
    nt.links.new(src, hsv.inputs['Color'])
    nt.links.new(hsv.outputs['Color'], bsdf.inputs['Base Color'])
    return mat


def gravel_mat():
    mat, nt, out = R.nodes('gravel')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # wobble the texture coordinates a little with noise, so the tiles never line up into a repeat
    wob = nt.nodes.new('ShaderNodeTexNoise')
    wob.inputs['Scale'].default_value = 1.7
    wob.inputs['Detail'].default_value = 2
    L.new(tc.outputs['Object'], wob.inputs['Vector'])
    wsc = nt.nodes.new('ShaderNodeVectorMath')
    wsc.operation = 'SCALE'
    wsc.inputs['Scale'].default_value = 0.12
    L.new(wob.outputs['Color'], wsc.inputs[0])
    wadd = nt.nodes.new('ShaderNodeVectorMath')
    wadd.operation = 'ADD'
    L.new(tc.outputs['Object'], wadd.inputs[0])
    L.new(wsc.outputs['Vector'], wadd.inputs[1])
    coords = wadd.outputs['Vector']
    d = R.boxtex(nt, R.tex('coral_gravel_diff'), 5.0, coords)
    b = R.boxtex(nt, R.tex('coral_gravel_disp', 'Non-Color'), 5.0, coords)
    # patches of slightly different gravel, so it never reads as one repeat
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.8
    nz.inputs['Detail'].default_value = 4
    L.new(coords, nz.inputs['Vector'])
    pr = nt.nodes.new('ShaderNodeMix')
    pr.data_type = 'RGBA'
    pr.blend_type = 'MULTIPLY'
    pr.inputs['Factor'].default_value = 0.35
    d2 = R.boxtex(nt, R.tex('coral_gravel_diff'), 3.1, coords)
    mix2 = nt.nodes.new('ShaderNodeMix')
    mix2.data_type = 'RGBA'
    L.new(nz.outputs['Fac'], mix2.inputs['Factor'])
    L.new(d.outputs['Color'], mix2.inputs['A'])
    L.new(d2.outputs['Color'], mix2.inputs['B'])
    d = mix2
    L.new(mix2.outputs['Result'], pr.inputs['A'])
    L.new(nz.outputs['Color'], pr.inputs['B'])
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    # grain contrast: individual pebbles light and dark, not a smooth wash
    cr = nt.nodes.new('ShaderNodeValToRGB')
    cr.color_ramp.elements[0].position = 0.18
    cr.color_ramp.elements[0].color = (0.38, 0.35, 0.31, 1)
    cr.color_ramp.elements[1].position = 0.78
    cr.color_ramp.elements[1].color = (1.0, 0.97, 0.92, 1)
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    L.new(pr.outputs['Result'], bw.inputs['Color'])
    L.new(bw.outputs['Val'], cr.inputs['Fac'])
    tint = nt.nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 0.45
    L.new(cr.outputs['Color'], tint.inputs['A'])
    L.new(pr.outputs['Result'], tint.inputs['B'])
    hsv.inputs['Saturation'].default_value = 0.50
    hsv.inputs['Value'].default_value = 1.55
    L.new(tint.outputs['Result'], hsv.inputs['Color'])
    warm = nt.nodes.new('ShaderNodeMix')
    warm.data_type = 'RGBA'
    warm.blend_type = 'MULTIPLY'
    warm.inputs['Factor'].default_value = 1.0
    warm.inputs['B'].default_value = (1.0, 0.94, 0.84, 1)
    L.new(hsv.outputs['Color'], warm.inputs['A'])
    hsv = warm
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.0
    bump.inputs['Distance'].default_value = 0.025
    L.new(b.outputs['Color'], bump.inputs['Height'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(hsv.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.85
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def gravel_bank(mat):
    """The gravel: a top surface from the glass back under the reef, and its face against the glass."""
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=500, y_subdivisions=200, size=1, location=(0, 1.0, 0))
    top = bpy.context.active_object
    top.name = 'gravel'
    top.scale = (12, 7.2, 1)
    R.apply_all(top)
    oy = top.location.y                  # (the mesh is offset: compare in world y)
    for v in top.data.vertices:          # the front edge exactly at the glass
        v.co.y = max(v.co.y, BANK_FRONT - oy)
    front_ix = [v.index for v in top.data.vertices if abs(v.co.y - (BANK_FRONT - oy)) < 1e-5]
    R.displace(top, 'CLOUDS', 0.9, 0.04, 2, noise_depth=3)
    R.displace(top, 'CLOUDS', 1.0, 0.42, 9, noise_depth=1)        # mounds and dips, not a level floor
    R.apply_all(top)
    for v in top.data.vertices:          # and banked up a little toward the back, against the reef
        v.co.z += 0.12 * min(1.0, max(0.0, (v.co.y + oy - BANK_FRONT) / 3.6))
    top.data.shade_smooth()
    top.data.materials.append(mat)
    top.pass_index = SAND
    # the gravel against the glass: its top edge follows the gravel's own front edge (a hair above it,
    # so no water shows between), rising and dipping with the floor instead of a ruled line
    vs = top.data.vertices
    for i in front_ix:                   # (the mounds pushed them a little off the glass: back onto it)
        vs[i].co.y = BANK_FRONT - oy
    top.data.update()
    front = sorted((vs[i].co.x, vs[i].co.z) for i in front_ix)
    verts, faces = [], []
    for i, (x, z) in enumerate(front):
        verts += [(x, BANK_FRONT - 0.01, -1.12), (x, BANK_FRONT - 0.01, z + 0.012)]
        if i:
            faces.append((2 * i - 2, 2 * i, 2 * i + 1, 2 * i - 1))
    me = bpy.data.meshes.new('gravelface')
    me.from_pydata(verts, [], faces)
    face = bpy.data.objects.new('gravelface', me)
    bpy.context.collection.objects.link(face)
    face_mat = mat.copy()
    for n in face_mat.node_tree.nodes:
        if n.type == 'HUE_SAT':
            n.inputs['Value'].default_value = 1.45
    face.data.materials.append(face_mat)
    face.pass_index = FRONT
    return top, face


def surface(x, y, top=4.0, skip=()):
    dg = bpy.context.evaluated_depsgraph_get()
    o = Vector((x, y, top))
    while True:
        hit, loc, nrm, _, ob, _ = bpy.context.scene.ray_cast(dg, o, Vector((0, 0, -1)))
        if not hit:
            return Vector((x, y, 0.0)), None
        if ob.name not in skip:
            return loc, ob
        o = loc - Vector((0, 0, 0.001))


def front_face(x, z, y0=-2.5):
    dg = bpy.context.evaluated_depsgraph_get()
    hit, loc, nrm, _, ob, _ = bpy.context.scene.ray_cast(dg, Vector((x, y0, z)), Vector((0, 1, 0)))
    return loc if hit and ob.name.startswith('wall') else None


def coral(key, x, y, height, where, seed):
    """A photo coral as a relief model, standing where it grows, facing the viewer."""
    path = os.path.join(PHOTO, 'coral_%s.json' % key)
    if not os.path.exists(path):
        print('no relief for', key)
        return
    G = json.load(open(path))
    ob, rest, fins = PM.build(G)
    ob.data.materials.append(PM.material(G['tex']))
    asp = G['aspect']
    s = height / asp                      # the model is 1 wide and asp high
    ob.scale = (s, s, s)
    r = random.Random(seed)
    if where == 'face':
        p = front_face(x, y)
        if p is None:
            p = Vector((x, 0.2, y))
        base = p + Vector((0, -0.04, -0.35 * height))
    elif where == 'gravel':
        p, _ = surface(x, y, skip=('wall',))
        base = p + Vector((0, 0, -0.12 * height))
    else:
        p, _ = surface(x, y)
        # branching corals' photos have empty space under the coral: set them deeper
        sink = 0.34 if key.startswith(('elkhorn', 'staghorn')) else 0.18
        base = p + Vector((0, 0, -sink * height))
    # the model's bottom middle at the base point (its x runs 0..1, z -asp/2..asp/2)
    ob.location = base + Vector((-0.5 * s, 0, 0.5 * asp * s))
    ob.rotation_euler = (0, 0, math.radians(r.uniform(-12, 12)))
    ob.pass_index = FRONT if where == 'gravel' else MID
    return ob


def build():
    common.reset_scene()
    random.seed(11)
    rock = rock_mat()
    gravel_bank(gravel_mat())
    # the rock: a base course, then pieces piled into two masses with a gap and caves between them
    r = random.Random(7)
    pieces = []
    x = -3.95
    while x < 3.95:
        w = r.uniform(0.50, 0.80)
        pieces.append((x + w / 2, r.uniform(0.75, 1.05), r.uniform(0.02, 0.10), w * 0.62, r.uniform(0.42, 0.55), r.uniform(0.34, 0.50)))
        x += w * r.uniform(0.75, 0.95)
    height_at = lambda x: 0.55 + 0.40 * math.exp(-((x + 1.6) / 1.0) ** 2) + 0.55 * math.exp(-((x - 1.2) / 0.8) ** 2)
    x = -3.6
    while x < 3.6:
        h = height_at(x)
        z = 0.38
        while z < h:
            w = r.uniform(0.30, 0.55)
            pieces.append((x + r.uniform(-0.1, 0.1), r.uniform(0.85, 1.25), z, w * 0.6, r.uniform(0.28, 0.40), r.uniform(0.18, 0.28)))
            z += r.uniform(0.17, 0.27)
        x += r.uniform(0.34, 0.52)
    for i, (px, py, pz, sx, sy, sz) in enumerate(pieces):
        porous_rock('wall%d' % i, (px, py, pz), (sx, sy, sz), 300 + i, rock, MID)
    bpy.context.view_layer.update()
    # the moray's cave: cut into a base rock where nothing stands in front of it
    global MOUTH
    # its own rock, standing on the gravel at the foot of the reef, the cave cut straight into it
    # (a hole cut into the wall itself opened onto the rocks behind and never read as a cave)
    cave_rock = porous_rock('wallcave', (CAVE_X, 0.05, 0.22), (0.62, 0.48, 0.42), 777, rock, MID)
    bpy.context.view_layer.update()
    mouth = front_face(CAVE_X + 0.05, 0.24, y0=-2.4)
    if mouth is None:
        mouth = Vector((CAVE_X, -0.35, 0.24))
    R.cut_cave(cave_rock, mouth + Vector((-0.12, 0.14, 0.0)), (0.72, -0.69, 0.04), 0.17, 0.62)
    MOUTH = mouth.copy()
    bpy.context.view_layer.update()
    # sea fans behind the reef
    R.sea_fan('fanP', (-3.40, 1.75, 0.65), 61, 1.25, (0.70, 0.12, 0.42), 0.05, MID)
    R.sea_fan('fanO', (0.55, 1.85, 0.85), 62, 1.05, (0.85, 0.30, 0.20), -0.10, MID)
    bpy.context.view_layer.update()
    for i, (key, x, y, hgt, where) in enumerate(LAYOUT):
        coral(key, x, y, hgt, where, 50 + i)
        bpy.context.view_layer.update()
    R.water_volume()
    for n in bpy.data.objects['water'].data.materials[0].node_tree.nodes:
        if n.type in ('SCATTER', 'ABSORPTION'):
            n.inputs['Density'].default_value = 0.003
    w = bpy.data.objects['water']
    w.location = (0, -3.5, 2.0)
    w.scale = (20, 13, 5)
    R.surface_cookie()

    cam = bpy.data.cameras.new('cam')
    cam.lens = 60
    cam.sensor_width = 36
    camob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(camob)
    # level, from about the middle of the tank's height, far enough back to see the glass face of the gravel
    camob.location = (0, -12.2, 1.02)
    camob.rotation_euler = (math.radians(90.0), 0, 0)
    bpy.context.scene.camera = camob
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = TANK_W, 1080
    return camob, MOUTH


def lights():
    import tank3d_world as TW
    TW.water_world()
    common.sun('key', (0.18, 0.32, -1.0), 16.0, (1.0, 0.99, 0.96), angle=2.0)
    bpy.context.scene.view_settings.exposure = 0.0
    common.sun('fill', (0.0, 1.0, -0.35), 0.25, (0.85, 0.93, 1.0), angle=25)


def main():
    os.makedirs(R.OUT, exist_ok=True)
    camob, mouth = build()
    lights()
    R.SWAY[:] = []
    sc = bpy.context.scene
    if QUICK:
        common.render_settings(48, transparent=False)
        sc.cycles.volume_bounces = 1
        sc.render.filepath = os.path.join(R.OUT, 'tank_quick.png')
        bpy.ops.render.render(write_still=True)
        return
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    p = world_to_camera_view(sc, camob, mouth)
    p2 = world_to_camera_view(sc, camob, mouth + Vector((1, 0, 0)))
    info = {'width': TANK_W, 'photo_reef': True, 'cave_mouth': [p.x * TANK_W, (1 - p.y) * 1080, p.z],
            'px_per_m_at_cave': (p2.x - p.x) * TANK_W,
            'camera': {'loc': list(camob.location), 'rot': list(camob.rotation_euler),
                       'lens': camob.data.lens, 'sensor': camob.data.sensor_width}}
    R.render_beauty(os.path.join(R.OUT, 'scene_beauty.png'))
    R.render_sand(os.path.join(R.OUT, 'scene_sand.png'))
    R.render_mask(os.path.join(R.OUT, 'scene_mask.png'))
    R.render_posnrm(os.path.join(R.OUT, 'scene_posnrm.png'))
    json.dump(info, open(os.path.join(R.OUT, 'scene.json'), 'w'), indent=1)


if __name__ == "__main__":
    main()

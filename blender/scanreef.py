"""Blender script: the reef built from real 3D scans.

    blender -b --factory-startup -P scanreef.py -- <textures dir> <out dir> [samples] [--quick]

Corals: Smithsonian NMNH coral specimens (CC0, 3d.si.edu).  They are bleached
museum skeletons on display bases, so each has its base cut away and is given
living tissue color (a multiply over the scan's own surface, darker at the base).
Rock: Poly Haven rock scans (CC0), toned toward live rock.  Clam: the
Smithsonian Tridacna squamosa scan.

Same camera, light, gravel and passes as reeftank.py, so build.py and the
channel take the output unchanged (scene_beauty, scene_sand, scene_mask,
scene_posnrm, scene.json).
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import reef3d as R  # noqa: E402
import reeftank as RT  # noqa: E402

QUICK = '--quick' in sys.argv
HAZE = False                       # the blue water volume between camera and reef
KEY_DIR = (0.20, 0.90, -0.80)     # direction the key light travels
RAKE_DIR = (0.95, 0.25, -0.22)    # the gravel's own low light, from the left
RAKE_POWER = 2.5
MID, FRONT, SAND = R.MID, R.FRONT, R.SAND
SCANS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scans')
SI = os.path.join(SCANS, 'si')
PH = os.path.join(SCANS, 'ph')

# living tissue colors (base, tips): browns, olives, tans, a little pink and purple - a real reef, not a rainbow
TINTS = {
    'gold':   ((0.30, 0.18, 0.06), (0.85, 0.62, 0.30)),
    'olive':  ((0.16, 0.24, 0.06), (0.55, 0.62, 0.22)),
    'tan':    ((0.32, 0.22, 0.12), (0.88, 0.74, 0.52)),
    'brown':  ((0.20, 0.11, 0.05), (0.62, 0.40, 0.20)),
    'pink':   ((0.40, 0.20, 0.22), (0.95, 0.72, 0.70)),
    'purple': ((0.20, 0.10, 0.18), (0.62, 0.42, 0.58)),
    'green':  ((0.10, 0.22, 0.10), (0.42, 0.66, 0.36)),
    'cream':  ((0.42, 0.38, 0.30), (0.95, 0.90, 0.78)),
    'teal':   ((0.12, 0.20, 0.20), (0.50, 0.66, 0.62)),
    'yellow': ((0.34, 0.28, 0.06), (0.92, 0.84, 0.40)),
}

# (scan, x, y, height, turn degrees): the rock the corals grow on - mostly hidden under them
ROCKS = [
    ('coast_land_rocks_03', -2.10, 2.15, 0.75, 10),
    ('coast_land_rocks_03', 2.10, 2.20, 0.75, 190),
    ('namaqualand_boulder_02', -2.35, 1.05, 0.80, 0),
    ('namaqualand_boulder_02', 2.60, 1.15, 0.75, 160),
    ('coast_rocks_05', 1.20, 1.20, 0.95, 30),
    ('coast_rocks_05', -3.45, 1.30, 0.70, 200),
    ('boulder_01', 1.40, 1.65, 1.35, 120),
    ('boulder_01', -1.60, 1.55, 1.25, 250),
    ('boulder_01', 3.40, 1.75, 1.05, 30),
    ('boulder_01', -3.60, 1.85, 1.00, 300),
    ('namaqualand_boulder_02', -0.15, 1.30, 0.75, 80),
    ('rock_07', 3.35, 0.35, 0.35, 0),
    ('rock_07', -3.05, 0.25, 0.30, 140),
]
CAVE = ('boulder_01', -0.55, 0.15, 1.05, 15)
CAVE_AXIS = Vector((-0.42, 0.91, 0.05)).normalized()       # the moray's rock, on the gravel at the foot of the reef
CLAM = (1.75, -1.55, 0.85, -8)                    # x, y, width, turn
CLAM_TILT = 45                                    # degrees, its opening tipped toward the viewer


def scan_path(name):
    for p in (os.path.join(SI, name + '.glb'), os.path.join(SCANS, name + '.glb'),
              os.path.join(PH, name, name + '.gltf'), os.path.join(SCANS, name + '.gltf'),
              os.path.join(SCANS, 'gigas', name + '.glb'), os.path.join(SCANS, 'nhmw', name + '.glb')):
        if os.path.exists(p):
            return p
    raise FileNotFoundError(name)


def import_scan(name):
    """Import a scan as one mesh object (joined, transforms applied, origin at the bottom middle)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=scan_path(name))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    for o in bpy.context.view_layer.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw                # (keep what the importer's parent nodes did to it)
    for o in new:
        try:
            if o is not ob and o.name in bpy.data.objects:
                bpy.data.objects.remove(o)
        except ReferenceError:          # (joined into ob already)
            pass
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.rotation_mode = 'XYZ'       # (glTF imports use quaternions: rotation_euler was ignored)
    ob.rotation_euler = (0, 0, 0)
    ob.name = name
    return ob


def cut_base(ob, frac):
    if frac <= 0:
        return
    zs = [v.co.z for v in ob.data.vertices]
    lo, hi = min(zs), max(zs)
    cut = lo + frac * (hi - lo)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < cut], context='VERTS')
    bm.to_mesh(ob.data)
    bm.free()


def fit(ob, height=None, width=None):
    """Scale to a height (or width), origin to the bottom middle."""
    co = [v.co for v in ob.data.vertices]
    lo = Vector([min(c[i] for c in co) for i in range(3)])
    hi = Vector([max(c[i] for c in co) for i in range(3)])
    s = height / max(hi.z - lo.z, 1e-9) if height else width / max(hi.x - lo.x, 1e-9)
    mid = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in ob.data.vertices:
        v.co = (v.co - mid) * s
    ob.data.update()
    return s


def living(mat, base_col, tip_col, sss=0.25):
    """Keep the scan's own surface detail; color it as living tissue, darker at the base."""
    nt = mat.node_tree
    bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    link = bsdf.inputs['Base Color'].links
    scan = link[0].from_socket if link else None
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*base_col, 1)
    ramp.color_ramp.elements[1].color = (*tip_col, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Factor'].default_value = 1.0
    if scan is not None:
        nt.links.new(scan, mul.inputs['A'])
    else:
        mul.inputs['A'].default_value = (0.8, 0.8, 0.8, 1)
    nt.links.new(ramp.outputs['Color'], mul.inputs['B'])
    nt.links.new(mul.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Subsurface Weight'].default_value = sss
    bsdf.inputs['Subsurface Scale'].default_value = 0.01
    bsdf.inputs['Roughness'].default_value = 0.55
    for n in nt.nodes:          # no shine off the scan's own roughness map
        if n.type == 'BSDF_PRINCIPLED':
            for l in list(n.inputs['Roughness'].links):
                nt.links.remove(l)


def live_rock(mat, seed):
    """Tone a rock scan toward live rock: greyer, patches of coralline pink-purple and turf."""
    nt = mat.node_tree
    L = nt.links
    bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    link = bsdf.inputs['Base Color'].links
    if not link:
        return
    src = link[0].from_socket
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = 0.45
    hsv.inputs['Value'].default_value = 1.15
    L.new(src, hsv.inputs['Color'])
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 2.2
    nz.inputs['Detail'].default_value = 6
    nz.noise_dimensions = '4D'
    nz.inputs['W'].default_value = seed
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = (0.78, 0.50, 0.62, 1)      # coralline
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.62, 0.66, 0.42, 1)      # turf
    L.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    # tops get the growth, faces and undersides stay stone
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    L.new(geo.outputs['Normal'], sep.inputs['Vector'])
    up = nt.nodes.new('ShaderNodeMapRange')
    up.inputs['From Min'].default_value = 0.1
    up.inputs['From Max'].default_value = 0.8
    up.inputs['To Max'].default_value = 0.75
    L.new(sep.outputs['Z'], up.inputs['Value'])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    L.new(up.outputs['Result'], mix.inputs['Factor'])
    L.new(hsv.outputs['Color'], mix.inputs['A'])
    L.new(ramp.outputs['Color'], mix.inputs['B'])
    L.new(mix.outputs['Result'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.9
    for l in list(bsdf.inputs['Roughness'].links):
        L.remove(l)


def place_rock(name, x, y, height, turn, seed):
    ob = import_scan(name)
    fit(ob, height=height)
    ob.location = (x, y, -0.06 * height)
    ob.rotation_euler = (0, 0, math.radians(turn))
    for i, m in enumerate(ob.data.materials):
        m = m.copy()
        ob.data.materials[i] = m
        live_rock(m, seed)
    ob.pass_index = MID
    ob.name = 'wall_' + name
    return ob


# scans not standing as they grow: ('x', degrees) turns the mesh about x first; 'auto' stands it
# along its long axis with the wider end (the branch tips) up
ORIENT = {'agaricia_lamarcki': ('y', 141),      # a plate scanned upside down: turned in its plane, its flat base edge down
          'lobophyllia_wellsi': 'auto'}         # a branch bundle scanned lying diagonally, tips down


def orient(ob, how):
    import numpy as np
    from mathutils import Matrix
    if how == 'auto':
        n = len(ob.data.vertices)
        co = np.zeros(n * 3, np.float32)
        ob.data.vertices.foreach_get('co', co)
        co = co.reshape(n, 3)
        c = co - co.mean(axis=0)
        axis = np.linalg.svd(c, full_matrices=False)[2][0]
        t = c @ axis
        lo, hi = np.quantile(t, 0.15), np.quantile(t, 0.85)
        spread = lambda m: np.linalg.norm(c[m] - np.outer(t[m], axis), axis=1).mean()
        if spread(t < lo) > spread(t > hi):
            axis = -axis
        rot = Vector(axis.tolist()).rotation_difference(Vector((0, 0, 1))).to_matrix().to_4x4()
    else:
        rot = Matrix.Rotation(math.radians(how[1]), 4, how[0].upper())
    ob.data.transform(rot)
    ob.data.update()


def place_coral(spec, seed):
    name, cut, x, y, height, where, tint, turn = spec
    ob = import_scan(name)
    if name in ORIENT:
        orient(ob, ORIENT[name])
    cut_base(ob, cut)
    fit(ob, height=height)
    if where == 'gravel':
        p, _ = RT.surface(x, y, skip=())
        base = p + Vector((0, 0, -0.06 * height))
    else:
        p, _ = RT.surface(x, y)
        if p.z + 0.88 * height > REEF_TOP:       # on a tall rock: smaller, so it stays inside the tank
            height = max(0.35, (REEF_TOP - p.z) / 0.88)
            fit(ob, height=height)
        base = p + Vector((0, 0, -0.12 * height))
    ob.location = base
    ob.rotation_euler = (0, 0, math.radians(turn + random.Random(seed).uniform(-15, 15)))
    for i, m in enumerate(ob.data.materials):
        m = m.copy()
        ob.data.materials[i] = m
        living(m, *TINTS[tint])
    ob.pass_index = FRONT if where == 'gravel' else MID
    ob.name = 'coral_' + name
    bpy.context.view_layer.update()
    return ob


def mantle_material():
    """Tridacna mantle: teal-blue and gold-brown mottling, dark spots, a paler rim."""
    mat, nt, out = R.nodes('mantle')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 7.0
    nz.inputs['Detail'].default_value = 5
    L.new(tc.outputs['Object'], nz.inputs['Vector'])
    base = nt.nodes.new('ShaderNodeValToRGB')
    base.color_ramp.elements[0].position = 0.40
    base.color_ramp.elements[0].color = (0.30, 0.22, 0.07, 1)
    base.color_ramp.elements[1].position = 0.60
    base.color_ramp.elements[1].color = (0.05, 0.22, 0.26, 1)
    L.new(nz.outputs['Fac'], base.inputs['Fac'])
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 140.0
    vor.inputs['Randomness'].default_value = 1.0
    vor.feature = 'F1'
    L.new(tc.outputs['Object'], vor.inputs['Vector'])
    spots = nt.nodes.new('ShaderNodeMapRange')
    spots.inputs['From Min'].default_value = 0.18
    spots.inputs['From Max'].default_value = 0.32
    spots.inputs['To Min'].default_value = 0.30
    spots.inputs['To Max'].default_value = 1.0
    L.new(vor.outputs['Distance'], spots.inputs['Value'])
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Factor'].default_value = 1.0
    L.new(base.outputs['Color'], mul.inputs['A'])
    L.new(spots.outputs['Result'], mul.inputs['B'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15
    L.new(vor.outputs['Distance'], bump.inputs['Height'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(mul.outputs['Result'], bsdf.inputs['Base Color'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    bsdf.inputs['Roughness'].default_value = 0.35
    bsdf.inputs['Subsurface Weight'].default_value = 0.2
    bsdf.inputs['Subsurface Scale'].default_value = 0.01
    bsdf.inputs['Coat Weight'].default_value = 0.12
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


MANTLE_CELL = 0.006     # the mantle's grid, as a share of the clam's length


def lip_profile(clam):
    """A map of the zigzag gap, seen from straight above the clam (local axes): over the gap you
    look down into the shell, so the highest surface there is far below the lips around it."""
    import numpy as np
    from scipy import ndimage
    co = np.array([v.co[:] for v in clam.data.vertices])
    x0, x1 = co[:, 0].min(), co[:, 0].max()
    y0, y1 = co[:, 1].min(), co[:, 1].max()
    cell = MANTLE_CELL * CLAM[2]
    nx, ny = int((x1 - x0) / cell) + 1, int((y1 - y0) / cell) + 1
    hm = np.full((ny, nx), np.nan)
    ix = ((co[:, 0] - x0) / cell).astype(int)
    iy = ((co[:, 1] - y0) / cell).astype(int)
    flat = np.full(nx * ny, -np.inf)
    np.maximum.at(flat, iy * nx + ix, co[:, 2])
    hm = flat.reshape(ny, nx)
    inside = ndimage.binary_fill_holes(ndimage.binary_closing(np.isfinite(hm), iterations=3))
    hm[~np.isfinite(hm)] = np.nan
    filled = np.where(np.isnan(hm), np.nanmin(hm), hm)
    hmax = co[:, 2].max()
    edge = ndimage.maximum_filter(filled, size=7)                       # the lips' height around each spot
    gap = inside & (filled < edge - 0.18 * hmax) & (edge > 0.6 * hmax)  # deep below the lips: the gap
    gap = ndimage.binary_opening(gap, iterations=1)
    lab, n = ndimage.label(gap)                                         # only the long zigzag, not stray pits
    if n:
        sizes = ndimage.sum(gap, lab, range(1, n + 1))
        gap = np.isin(lab, [i + 1 for i, sz in enumerate(sizes) if sz >= 0.25 * sizes.max()])
    ring = ndimage.binary_dilation(gap, iterations=2) & ~gap & inside   # the lip edges right beside it
    depth = ndimage.distance_transform_edt(gap)
    depth = depth / max(depth.max(), 1)
    return {'x0': x0, 'y0': y0, 'cell': cell, 'gap': gap, 'ring': ring, 'hm': filled, 'edge': edge,
            'depth': depth, 'hmax': hmax}


def mantle_points(prof, openness):
    """The mantle: in the gap it swells up out of the shell when open and sinks into it when
    shut; on the lips beside the gap it lies just on them when open, under them when shut."""
    import numpy as np
    P = prof
    keep = P['gap'] | P['ring']
    ys, xs = np.nonzero(keep)
    hmax = P['hmax']
    pts = []
    for j, i in zip(ys, xs):
        if P['gap'][j, i]:
            open_z = P['edge'][j, i] + (0.02 + 0.10 * P['depth'][j, i] ** 0.6) * hmax
            shut_z = P['edge'][j, i] - 0.08 * hmax
        else:
            open_z = P['hm'][j, i] + 0.006 * hmax
            shut_z = P['hm'][j, i] - 0.03 * hmax
        z = shut_z + (open_z - shut_z) * openness
        pts.append((P['x0'] + (i + 0.5) * P['cell'], P['y0'] + (j + 0.5) * P['cell'], z))
    return pts


def mantle_faces(prof):
    import numpy as np
    keep = prof['gap'] | prof['ring']
    index = -np.ones(keep.shape, int)
    ys, xs = np.nonzero(keep)
    index[ys, xs] = np.arange(len(xs))
    faces = []
    for j in range(keep.shape[0] - 1):
        for i in range(keep.shape[1] - 1):
            q = (index[j, i], index[j, i + 1], index[j + 1, i + 1], index[j + 1, i])
            if min(q) >= 0:
                faces.append(q)
    return faces


def add_mantle(clam, openness):
    prof = lip_profile(clam)
    pts = mantle_points(prof, openness)
    me = bpy.data.meshes.new('mantle')
    me.from_pydata(pts, [], mantle_faces(prof))
    me.shade_smooth()
    ob = bpy.data.objects.new('mantle', me)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mantle_material())
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    ob.parent = clam
    ob.pass_index = FRONT
    return ob, prof


# species for each row: (scan, cut, tints it may have, height range)
BACK = [('acropora_cervicornis', 0.00, ('tan', 'brown', 'purple'), (1.0, 1.3)),
        ('acropora_secale', 0.32, ('gold', 'tan', 'cream'), (0.9, 1.1)),
        ('porites_lobata', 0.02, ('yellow', 'tan', 'purple'), (0.9, 1.2)),
        ('porites_cylindrica', 0.02, ('teal', 'cream', 'yellow'), (0.8, 1.0)),
        ('madracis_auretenra', 0.02, ('gold', 'yellow'), (0.8, 1.0)),
        ('seriatopora_hystrix', 0.30, ('pink', 'cream'), (0.7, 0.9)),
        ('goniopora_columna', 0.27, ('green', 'olive'), (0.7, 0.9)),
        ('pocillopora_damicornis', 0.02, ('brown', 'pink', 'tan'), (0.6, 0.8)),
        ('turbinaria_heronensis', 0.02, ('olive', 'yellow'), (0.7, 0.9))]
MIDROW = [('pocillopora_meandrina', 0.02, ('pink', 'cream', 'tan'), (0.5, 0.65)),
          ('lobophyllia_wellsi', 0.02, ('olive', 'green', 'brown'), (0.5, 0.65)),
          ('pavona_cactus', 0.02, ('brown', 'olive', 'cream'), (0.5, 0.65)),
          ('montipora_danae', 0.25, ('purple', 'brown', 'olive'), (0.45, 0.6)),
          ('agaricia_lamarcki', 0.02, ('brown', 'tan'), (0.5, 0.65)),
          ('turbinaria_heronensis', 0.02, ('yellow', 'olive'), (0.5, 0.6)),
          ('pocillopora_damicornis', 0.02, ('pink', 'brown'), (0.45, 0.55))]
GRAVEL = [
    ('diploria_labyrinthiformis', 0.02, -2.55, -1.35, 0.55, 'gravel', 'tan', 0),
    ('astreopora_profunda', 0.30, -1.70, -0.95, 0.45, 'gravel', 'cream', 0),
    ('physogyra_gravieri', 0.02, 2.80, -1.35, 0.42, 'gravel', 'cream', 0),
    ('agaricia_lamarcki', 0.02, 0.95, -0.55, 0.55, 'gravel', 'olive', 0),
    ('montipora_danae', 0.25, -0.80, 0.45, 0.40, 'top', 'purple', 0),          # on the cave rock
    ('pocillopora_damicornis', 0.02, -0.20, 0.55, 0.42, 'top', 'tan', 0),
    ('lobophyllia_wellsi', 0.02, -3.15, -0.30, 0.50, 'gravel', 'green', 0),
]


REEF_TOP = 1.95          # m: nothing on the reef reaches higher (the tall back corals touched the top)
FLAT_BACK = {'favia_danai': 180}      # turn (degrees) that puts a scan's flat side away from the glass


def layout():
    """Rows of corals along the reef, each species well apart from its last use."""
    r = random.Random(23)
    out = []
    last = {}
    used = {}
    cap = {'goniopora_columna': 1, 'pocillopora_meandrina': 2, 'gemmipora_brassica': 2, 'acropora_cervicornis': 2,
           'seriatopora_hystrix': 2, 'favia_danai': 1, 'agaricia_lamarcki': 1, 'lobophyllia_wellsi': 1}
    for row, y, step, rows_species in ((0, 1.85, 0.62, BACK), (1, 1.25, 0.58, BACK + MIDROW), (2, 0.72, 0.62, MIDROW)):
        x = -4.15 + r.uniform(0, 0.3)
        while x < 4.15:
            px = x + r.uniform(-0.1, 0.1)
            if row == 2 and abs(px - CAVE[1]) < 0.65:      # keep the cave clear
                x += step
                continue
            choices = [c for c in rows_species if abs(px - last.get(c[0], -99)) > 3.2
                       and used.get(c[0], 0) < cap.get(c[0], 4)]
            if not choices:
                choices = [c for c in rows_species if used.get(c[0], 0) < cap.get(c[0], 4)
                           and abs(px - last.get(c[0], -99)) > 1.6] or rows_species
            name, cut, tints, (h0, h1) = r.choice(choices)
            last[name] = px
            used[name] = used.get(name, 0) + 1
            turn = r.uniform(0, 360)
            if name in FLAT_BACK:          # specimens scanned against a board: flat side to the back
                turn = FLAT_BACK[name] + r.uniform(-20, 20)
            out.append((name, cut, px, y + r.uniform(-0.12, 0.12), r.uniform(h0, h1), 'top', r.choice(tints), turn))
            x += step * r.uniform(0.85, 1.15)
    return out + GRAVEL


CLAM_OPEN, CLAM_SHUT = 4.0, -7.0    # degrees each valve is turned about the hinge from the scan's own pose:
                                     # open (the mantle swelling between them) and shut (the zigzag edges interlocked)
CLAMDATA = {}


def make_clam_mirrored():
    """The giant clam from the Smithsonian scan, which is ONE valve (lying dome up, hinge toward
    -y, its rim on the plane of its lowest point): the other valve is its mirror image across the
    rim, as in the real animal.  Stood up as it lives, hinge down, opening up."""
    import numpy as np
    from mathutils import Matrix
    clam = import_scan('tridacna_squamosa')
    clam.name = 'clam'
    bm = bmesh.new()
    bm.from_mesh(clam.data)
    bm.verts.ensure_lookup_table()
    n_a = len(bm.verts)
    # the valve's rim: the boundary of its largest connected piece (the scan has loose crumbs)
    seen, best = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        isl, stack = [], [v]
        while stack:
            q = stack.pop()
            if q.index in seen:
                continue
            seen.add(q.index)
            isl.append(q)
            stack.extend(e.other_vert(q) for e in q.link_edges)
        if len(isl) > len(best):
            best = isl
    # the rim's plane: the "lid" of the cup - the biggest flat part of the valve's convex hull,
    # on the side the cup opens (the scan lies dome up, so it opens downward)
    hb = bmesh.new()
    for v in best:
        hb.verts.new(v.co)
    bmesh.ops.convex_hull(hb, input=hb.verts[:])
    faces = [(f.normal.copy(), f.calc_area(), [q.co.copy() for q in f.verts]) for f in hb.faces]
    hb.free()
    big = max((f for f in faces if f[0].z < -0.3), key=lambda f: f[1])
    lid = [f for f in faces if f[0].dot(big[0]) > 0.97]
    nrm = sum((f[0] * f[1] for f in lid), Vector()).normalized()   # out of the cup's opening
    pts = [q for f in lid for q in f[2]]
    off = sum(q.dot(nrm) for q in pts) / len(pts)
    n = np.array(nrm)
    c = np.array(nrm * off) + (np.array([v.co[:] for v in best]).mean(axis=0) -
                               (np.array([v.co[:] for v in best]).mean(axis=0) @ n) * n)
    geom = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])['geom']
    nv = Vector(n)
    cv = Vector(c)
    for g in geom:
        if isinstance(g, bmesh.types.BMVert):
            g.co = g.co - 2 * (g.co - cv).dot(nv) * nv           # the other valve: mirrored across the rim
    bmesh.ops.reverse_faces(bm, faces=[g for g in geom if isinstance(g, bmesh.types.BMFace)])
    bm.to_mesh(clam.data)
    bm.free()
    # stand it up: rim plane vertical (valve A toward -y), hinge (the umbo, toward the scan's -y) down
    yax = nv
    d = Vector((0, -1, 0))
    u = (d - d.dot(nv) * nv).normalized()                   # toward the hinge, in the rim's plane
    zax = -u
    xax = yax.cross(zax)
    M = Matrix((list(xax) + [0], list(yax) + [0], list(zax) + [0], [0, 0, 0, 1]))
    clam.data.transform(M @ Matrix.Translation(-cv))
    fit(clam, width=CLAM[2])
    co = np.array([v.co[:] for v in clam.data.vertices])
    a_side = co[:n_a, 1].mean() < co[n_a:, 1].mean()        # valve A on the -y side?
    CLAMDATA.update({'n_a': n_a, 'rest': co, 'yp': (co[:n_a, 1].mean() + co[n_a:, 1].mean()) / 2,
                     'zb': co[:, 2].min(), 'sign': 1.0 if a_side else -1.0})
    set_gape(clam, CLAM_SHUT)
    return clam


NHMW = True             # the Vienna museum's painted giant clam (mantle open), CC BY-NC
NHMW_TURN = 47          # degrees: its long axis along the tank


def make_clam_nhmw():
    """The giant clam: the Natural History Museum Vienna's model of Tridacna gigas with its
    mantle open (CC BY-NC).  It stands in a sand tray on a board: everything below the sand's
    surface (plus a little) is cut away, and the stones left loose on the sand with it."""
    import numpy as np
    clam = import_scan('giant_clam_nhmw-zoo-mo-1104208')
    clam.name = 'clam'
    co = np.array([v.co[:] for v in clam.data.vertices])
    z = co[:, 2] - co[:, 2].min()
    h, e = np.histogram(z, bins=60)
    sand = e[np.argmax(h[:20])]                         # the flat sand: the busiest low height
    cut = co[:, 2].min() + sand + 0.075 * (z.max())
    bm = bmesh.new()
    bm.from_mesh(clam.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < cut], context='VERTS')
    # keep the clam: the biggest connected pieces (stones on the sand are now loose bits)
    seen, isl = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        part, stack = [], [v]
        while stack:
            q = stack.pop()
            if q.index in seen:
                continue
            seen.add(q.index)
            part.append(q)
            stack.extend(e_.other_vert(q) for e_ in q.link_edges)
        isl.append(part)
    # the stones on the sand: pieces that stay low; the mantle's many patches all sit high up
    top = max(v.co.z for v in bm.verts)
    low_line = cut + 0.30 * (top - cut)
    gone = [q for part in isl if max(p_.co.z for p_ in part) < low_line for q in part]
    bmesh.ops.delete(bm, geom=gone, context='VERTS')
    bm.to_mesh(clam.data)
    bm.free()
    # it sat at 45 degrees on its board: along the tank instead
    from mathutils import Matrix
    clam.data.transform(Matrix.Rotation(math.radians(NHMW_TURN), 4, 'Z'))
    fit(clam, width=CLAM[2])
    mantle_weights(clam)
    return clam


def mantle_weights(clam):
    """Which vertices are mantle: blue-green in the model's own painted texture."""
    import numpy as np
    mat = clam.data.materials[0]
    img = [n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image][0]
    w_, h_ = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h_, w_, img.channels)[..., :3]
    me = clam.data
    uv = np.zeros(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get('uv', uv)
    uv = uv.reshape(-1, 2)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get('vertex_index', lv)
    ix = np.clip((uv[:, 0] % 1.0) * w_, 0, w_ - 1).astype(int)
    iy = np.clip((uv[:, 1] % 1.0) * h_, 0, h_ - 1).astype(int)
    c = px[iy, ix]
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    green = ((g > r * 1.15) & (np.maximum(g, b) > 0.08)).astype(np.float32)
    acc = np.zeros(len(me.vertices), np.float32)
    cnt = np.zeros(len(me.vertices), np.float32)
    np.add.at(acc, lv, green)
    np.add.at(cnt, lv, 1)
    w = acc / np.maximum(cnt, 1)
    # smooth it over the surface, so neighbors move together (the painted edge is ragged)
    ed = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get('vertices', ed)
    ed = ed.reshape(-1, 2)
    deg = np.bincount(ed.ravel(), minlength=len(w)).astype(np.float32) + 1
    for _ in range(25):
        nb = np.zeros_like(w)
        np.add.at(nb, ed[:, 0], w[ed[:, 1]])
        np.add.at(nb, ed[:, 1], w[ed[:, 0]])
        w = (w + nb) / deg
    w = np.clip((w - 0.15) / 0.6, 0, 1)
    co = np.array([v.co[:] for v in me.vertices])
    CLAMDATA.update({'rest': co, 'mw': w, 'yc': co[:, 1].mean(), 'H': co[:, 2].max() - co[:, 2].min()})
    print('mantle share of vertices: %.2f' % (w > 0.5).mean())


CLAM_CLOSE = 0.80      # how far the valves close in the flinch (fraction of the gap, at the lips)


def set_mantle(clam, s):
    import numpy as np
    """s = 0 as modeled, below 0 swelled a little, 1 drawn in toward the gap and down."""
    d = CLAMDATA
    co = d['rest'].copy()
    w = d['mw']
    # the valves swing shut about the hinge at the bottom: the higher a point, the more it
    # moves toward the gap (as a fraction of its distance from it, so the lips never cross)
    hz = np.clip((co[:, 2] - co[:, 2].min()) / d['H'], 0, 1) ** 1.3
    shut = CLAM_CLOSE * max(s, 0.0) * hz
    co[:, 1] -= (co[:, 1] - d['yc']) * (shut + 0.14 * s * w * (1 - shut))
    co[:, 2] -= 0.08 * d["H"] * s * w
    if os.environ.get('CLAM_DEBUG'):
        dd = np.abs(co - d['rest'])
        r = d['rest']
        print('CLAMDBG s', s, 'max move', dd.max(axis=0), 'extent', r.max(axis=0) - r.min(axis=0), 'yc', d['yc'], 'H', d['H'])
    clam.data.vertices.foreach_set('co', co.ravel())
    clam.data.update()


CLAM_STATIC = True      # the gigas specimen: the shell stays put, only the mantle moves


def make_clam():
    """The giant clam: a complete Tridacna gigas specimen, both valves (Museo [UV] Historia
    Natural, Universitat de Valencia, CC BY), scanned standing on end with its zigzag gap
    facing -y: laid down as it lives, hinge down, gap up, thinned to a sensible size."""
    from mathutils import Matrix
    clam = import_scan('tridacna_gigas')
    clam.name = 'clam'
    clam.data.transform(Matrix.Rotation(math.radians(180), 4, 'X') @
                        Matrix.Rotation(math.radians(-90), 4, 'Y') @ Matrix.Rotation(math.radians(90), 4, 'Z') @
                        Matrix.Rotation(math.radians(-90), 4, 'X'))
    dec = clam.modifiers.new('thin', 'DECIMATE')
    dec.ratio = 0.15
    bpy.context.view_layer.objects.active = clam
    bpy.ops.object.modifier_apply(modifier='thin')
    fit(clam, width=CLAM[2])
    return clam


def set_gape(clam, deg):
    """Open the valves about the hinge (a line along x at the bottom) by deg each."""
    import numpy as np
    if NHMW:                # the painted mantle moves, not the valves: 1 - deg/CLAM_OPEN-ish
        return
    if CLAM_STATIC:
        return
    d = CLAMDATA
    co = d['rest'].copy()
    n = d['n_a']
    for sl, sgn in ((slice(0, n), d['sign']), (slice(n, None), -d['sign'])):
        g = math.radians(deg) * sgn
        y = co[sl, 1] - d['yp']
        z = co[sl, 2] - d['zb']
        co[sl, 1] = d['yp'] + y * math.cos(g) - z * math.sin(g)
        co[sl, 2] = d['zb'] + y * math.sin(g) + z * math.cos(g)
    clam.data.vertices.foreach_set('co', co.ravel())
    clam.data.update()


def build():
    common.reset_scene()
    random.seed(11)
    RT.gravel_bank(RT.gravel_mat())
    for i, r in enumerate(ROCKS):
        place_rock(*r, seed=10 + i)
    bpy.context.view_layer.update()
    # the moray's cave, cut straight into its own rock
    name, cx, cy, ch, cturn = CAVE
    cave = place_rock(name, cx, cy, ch, cturn, 99)
    cave.name = 'wallcave'
    bpy.context.view_layer.update()
    mouth = RT.front_face(cx + 0.10, 0.36, y0=-2.4)
    if mouth is None:
        mouth = Vector((cx + 0.10, cy - 0.5, 0.36))
    axis = CAVE_AXIS                                     # back into the rock and to the left: room for the eel's body
    depth = 1.0
    R.cut_cave(cave, mouth + axis * (depth / 2 - 0.08), tuple(axis), 0.22, depth)
    bpy.context.view_layer.update()
    for i, c in enumerate(layout()):
        place_coral(c, 50 + i)
    # the giant clam (posed open; reefclam_scan.py animates it) and a conch on the gravel
    clam = make_clam_nhmw() if NHMW else make_clam()
    clam.rotation_euler = (math.radians(CLAM_TILT), 0, math.radians(CLAM[3]))
    p, _ = RT.surface(CLAM[0], CLAM[1], skip=())
    bpy.context.view_layer.update()
    low = min((clam.matrix_world @ v.co).z for v in clam.data.vertices) - clam.location.z
    clam.location = p + Vector((0, 0, -low - 0.05))        # bedded a little into the gravel
    clam.pass_index = FRONT
    if NHMW:
        set_mantle(clam, float(os.environ.get('CLAM_S', '1.0')))
    global MANTLE
    if not NHMW:
        MANTLE = add_mantle(clam, 0.0)    # closed in the still; the channel draws it opening
    bpy.context.view_layer.update()

    R.water_volume()
    for n in bpy.data.objects['water'].data.materials[0].node_tree.nodes:
        if n.type in ('SCATTER', 'ABSORPTION'):
            n.inputs['Density'].default_value = 0.003
    w = bpy.data.objects['water']
    w.location = (0, -3.5, 2.0)
    w.scale = (20, 13, 5)
    w.hide_render = not HAZE            # no haze: the reef as clear as in a real tank's glass
    R.surface_cookie()
    cam = bpy.data.cameras.new('cam')
    cam.lens = 60
    cam.sensor_width = 36
    camob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(camob)
    camob.location = (0, -12.2, 1.02)
    camob.rotation_euler = (math.radians(90.0), 0, 0)
    bpy.context.scene.camera = camob
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = RT.TANK_W, 1080
    return camob, mouth


MORAY_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'work', 'photo', 'moray.json')
EEL_LEN = 0.95           # m of moray across the model
EEL_YAW = 22             # degrees it turns its head, from straight out toward the open side only
                         # (turning the other way swung it into a spur of the cave's rim)
EEL_TURN = -65           # degrees: body back along the cave, head out toward the viewer and right
EEL_LOOP, EEL_SLIDE = (4, 3) if ("--moraytest" in sys.argv or "--moraydebug" in sys.argv) else (48, 24)


OPAQUE = '--opaque' in sys.argv     # the same frames lit in the full scene, water and all: their color


def sprite_pass(keep, catch, shade=()):
    """Render only `keep`: `catch` objects catch its shadow, everything else held out (still
    hiding it).  Only `shade` objects still cast shadows on it - shadows of the rest are
    already in the still picture, and a catcher would double them."""
    if OPAQUE:
        return
    for o in bpy.context.scene.objects:
        if o.type != 'MESH' or o in keep:
            continue
        if o.name in ('water', 'surface'):
            o.hide_render = True
            continue
        if o.name in catch:
            o.is_shadow_catcher = True
        else:
            o.is_holdout = True
        if o.name not in shade:
            o.visible_shadow = False


def set_border(camob, obs_points):
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    pts = [world_to_camera_view(sc, camob, c) for c in obs_points]
    x0 = max(0.0, min(p.x for p in pts) - 0.02)
    x1 = min(1.0, max(p.x for p in pts) + 0.03)
    y0 = max(0.0, min(p.y for p in pts) - 0.04)
    y1 = min(1.0, max(p.y for p in pts) + 0.02)
    sc.render.use_border = True
    sc.render.use_crop_to_border = True
    sc.render.border_min_x, sc.render.border_max_x = x0, x1
    sc.render.border_min_y, sc.render.border_max_y = y0, y1
    W, H = sc.render.resolution_x, sc.render.resolution_y
    return {'crop': True, 'x': round(x0 * W), 'y': round((1 - y1) * H), 'w': round((x1 - x0) * W),
            'h': round((y1 - y0) * H)}


# the clam's frames: the first half its slow breathing (mantle swelled out over the lips, then
# settling back), the second half the flinch shut.  The channel blends neighboring frames.
# (breathing stays at s <= 0, where only the mantle moves: past 0 the valves start to close, and
# their lips jumped from frame to frame)
CLAM_STATES = [-0.45 + 0.45 * k / 5 for k in range(6)] + [0.20 + 0.80 * k / 5 for k in range(6)]


def render_clam(camob, samples, frames=len(CLAM_STATES)):
    clam = bpy.data.objects['clam']
    if NHMW:
        mantle, prof = None, None
        sprite_pass([clam], ())
    else:
        mantle, prof = MANTLE
        sprite_pass([clam, mantle], ())        # (its shadow is in the still)
    common.render_settings(samples, transparent=not OPAQUE)
    bpy.context.view_layer.update()
    set_gape(clam, CLAM_OPEN)
    bpy.context.view_layer.update()
    if NHMW:
        set_mantle(clam, CLAM_STATES[0])          # (the border must hold the most swelled pose)
        bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in (clam,) for c in o.bound_box]
    pts += [p + Vector((0, 0, 0.10)) for p in pts]          # room for the mantle above the lips
    info = set_border(camob, pts)
    outdir = os.path.join(R.OUT, 'clamframes' + ('_rgb' if OPAQUE else ''))
    os.makedirs(outdir, exist_ok=True)
    for f in range(frames):
        c = f / (frames - 1)
        c = c * c * (3 - 2 * c)
        if NHMW:
            set_mantle(clam, CLAM_STATES[f])
        else:
            set_gape(clam, CLAM_OPEN * (1 - c) + CLAM_SHUT * c)
            p = mantle_points(prof, 1.0 - c)
            mantle.data.vertices.foreach_set('co', [k for q in p for k in q])
            mantle.data.update()
        bpy.context.scene.render.filepath = os.path.join(outdir, 'clam_%02d.png' % f)
        bpy.ops.render.render(write_still=True)
    info['frames'] = frames
    info['in_background'] = True
    if not OPAQUE:
        json.dump(info, open(os.path.join(R.OUT, 'clam.json'), 'w'), indent=1)


def render_moray(camob, mouth, samples):
    """The moray in its cave: EEL_LOOP frames out of the hole turning its head, then
    EEL_SLIDE frames backing from there into the hole (the channel plays them both ways)."""
    import numpy as np
    from mathutils import Matrix
    import photo3d_mesh as PM
    G = json.load(open(MORAY_JSON))
    # (PM.build's mirror flips the shape but not the texture: build it as photographed, head on the
    #  left, and turn it round - its back shows the photo mirrored, head to the right)
    ob, rest, fins = PM.build(G, mirror=False)
    mat = PM.material(G['tex'])
    ob.data.materials.append(mat)
    ob.name = 'moray'
    for n in mat.node_tree.nodes:           # a little less gaudy than the photo, like the rock around it
        if n.type == 'BSDF_PRINCIPLED' and n.inputs['Base Color'].links:
            src = n.inputs['Base Color'].links[0].from_socket
            hsv = mat.node_tree.nodes.new('ShaderNodeHueSaturation')
            hsv.inputs['Saturation'].default_value = 0.8
            hsv.inputs['Value'].default_value = 0.75
            mat.node_tree.links.new(src, hsv.inputs['Color'])
            mat.node_tree.links.new(hsv.outputs['Color'], n.inputs['Base Color'])
    rest = np.array(rest)
    asp = G['aspect']
    base = np.array([0.92, 0.0, -0.45 * asp])            # the body, deep in the hole
    pivot = np.array([0.60, 0.0, -0.05 * asp])
    d = rest - base
    w = np.clip((-d[:, 0] * 0.8 + d[:, 2] * 0.6) / 0.9, 0, 1) ** 1.5
    anchor = Vector((0.40, 0.0, -0.05 * asp))            # the neck: at the cave mouth when fully out
    ob.scale = (EEL_LEN,) * 3
    ob.rotation_euler = (0, 0, math.radians(180 + EEL_TURN))
    rot = ob.rotation_euler.to_matrix()
    out_dir = rot @ Vector((-1, 0, 0))                   # the way it comes out (head first)
    axis = CAVE_AXIS
    out_loc = mouth - axis * 0.03 - rot @ (anchor * EEL_LEN)
    hide = -0.85 * EEL_LEN                               # backed this far into the hole it is gone
    if '--moraydebug' in sys.argv:
        common.render_settings(samples, transparent=False)
    else:
        sprite_pass([ob], (), shade=('wallcave',))
        common.render_settings(samples, transparent=not OPAQUE)

    def pose(yaw, pitch, ext):
        out = np.empty_like(rest)
        for i in range(len(rest)):
            m = Matrix.Rotation(yaw * w[i], 3, 'Z') @ Matrix.Rotation(pitch * w[i], 3, 'Y')
            out[i] = np.array(m @ Vector(rest[i] - pivot)) + pivot
        ob.data.vertices.foreach_set('co', out.ravel())
        ob.data.update()
        ob.location = out_loc + out_dir * ext - axis * 0.0
        bpy.context.view_layer.update()

    pose(0, 0, 0)
    pts = []
    for yaw, ext in ((math.radians(EEL_YAW) * 0.2, 0), (math.radians(EEL_YAW), 0), (math.radians(EEL_YAW) * 0.6, hide * 0.5)):
        pose(yaw, 0, ext)
        pts += [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    info = set_border(camob, pts)
    outdir = os.path.join(R.OUT, 'eelframes' + ('_rgb' if OPAQUE else ''))
    os.makedirs(outdir, exist_ok=True)
    k = 0
    for f in range(EEL_LOOP):
        ph = 2 * math.pi * f / EEL_LOOP
        pose(math.radians(EEL_YAW) * (0.6 + 0.4 * math.sin(ph)), math.radians(5) * math.sin(2 * ph), 0)
        bpy.context.scene.render.filepath = os.path.join(outdir, 'eel_%02d.png' % k)
        bpy.ops.render.render(write_still=True)
        k += 1
    for f in range(1, EEL_SLIDE + 1):
        t = f / EEL_SLIDE
        pose(math.radians(EEL_YAW) * 0.6, math.radians(4) * math.sin(math.pi * t), hide * t * t * (3 - 2 * t))
        bpy.context.scene.render.filepath = os.path.join(outdir, 'eel_%02d.png' % k)
        bpy.ops.render.render(write_still=True)
        k += 1
    info.update({'loop': EEL_LOOP, 'slide': EEL_SLIDE, 'frames': k})
    if not OPAQUE:
        json.dump(info, open(os.path.join(R.OUT, 'eel.json'), 'w'), indent=1)


def main():
    os.makedirs(R.OUT, exist_ok=True)
    camob, mouth = build()
    RT.lights()
    # the key light out toward the viewer (about 40 degrees above the front, not overhead),
    # so the corals' faces are lit, not just their tops
    key = bpy.data.objects['key']
    key.rotation_euler = Vector(KEY_DIR).to_track_quat('-Z', 'Y').to_euler()
    # a low raking light on the gravel alone (and only the gravel shadowing it), so its mounds
    # and dips show: the front key light alone left the floor looking flat
    rake = common.sun('rake', RAKE_DIR, RAKE_POWER, (1.0, 0.97, 0.92), angle=3.0)
    gc = bpy.data.collections.new('gravel_only')
    bpy.context.scene.collection.children.link(gc)
    gc.objects.link(bpy.data.objects['gravel'])
    rake.light_linking.receiver_collection = gc
    rake.light_linking.blocker_collection = gc
    sc = bpy.context.scene
    if '--whereis' in sys.argv:            # each coral's place in the 2688x1080 picture, then stop
        from bpy_extras.object_utils import world_to_camera_view
        bpy.context.view_layer.update()
        print('CAM', sc.camera.name if sc.camera else None, camob.location, camob.rotation_euler, sc.render.resolution_x, sc.render.resolution_y)
        for o in sc.objects:
            if o.name.startswith('coral_'):
                pts = [world_to_camera_view(sc, sc.camera, o.matrix_world @ Vector(c)) for c in o.bound_box]
                x0, x1 = min(p.x for p in pts) * 2688, max(p.x for p in pts) * 2688
                y0, y1 = (1 - max(p.y for p in pts)) * 1080, (1 - min(p.y for p in pts)) * 1080
                print('WHERE %-32s x %4d-%4d  y %4d-%4d' % (o.name, x0, x1, y0, y1))
        return
    if '--clamtest' in sys.argv or '--cavetest' in sys.argv:
        common.render_settings(64, transparent=False)
        c = bpy.data.objects['clam'].matrix_world.translation if '--clamtest' in sys.argv else mouth
        if '--camview' in sys.argv:            # from the real camera's place, zoomed in
            if NHMW:
                st = float(os.environ.get('CLAMSTATE', '-0.12'))
                set_mantle(bpy.data.objects['clam'], st)
            if not NHMW:
                set_gape(bpy.data.objects['clam'], CLAM_OPEN)
                bpy.data.objects['mantle'].data.vertices.foreach_set('co', [k for q in mantle_points(MANTLE[1], 1.0) for k in q])
                bpy.data.objects['mantle'].data.update()
            camob.data.lens = 240
            d = (c + Vector((0, 0, 0.15)) - camob.location).normalized()
            camob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
            sc.render.resolution_x, sc.render.resolution_y = 900, 600
            sc.render.filepath = os.path.join(R.OUT, 'clam_test.png')
            bpy.ops.render.render(write_still=True)
            return
        print('MOUTH', mouth)
        camob.location = c + Vector((0, -2.2, 0.9))
        camob.rotation_euler = (math.radians(70), 0, 0)
        sc.render.resolution_x, sc.render.resolution_y = 900, 600
        sc.render.filepath = os.path.join(R.OUT, 'clam_test.png')
        bpy.ops.render.render(write_still=True)
        return
    samples = int(sys.argv[sys.argv.index('--') + 3]) if len(sys.argv) > sys.argv.index('--') + 3 and         sys.argv[sys.argv.index('--') + 3].isdigit() else 128
    if '--clam' in sys.argv:
        render_clam(camob, samples)
        return
    if '--moray' in sys.argv:
        render_moray(camob, mouth, samples)
        return
    if '--moraytest' in sys.argv or '--moraydebug' in sys.argv:
        render_moray(camob, mouth, 32)
        return
    if '--edgetest' in sys.argv:          # close on the gravel's front edge, bottom left
        common.render_settings(48, transparent=False)
        bpy.data.objects['surface'].hide_render = True
        camob.data.lens = 200
        tgt = Vector((-3.0, -2.6, 0.0))
        d = (tgt - camob.location).normalized()
        camob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        sc.render.resolution_x, sc.render.resolution_y = 900, 400
        sc.render.filepath = os.path.join(R.OUT, 'edge_test.png')
        bpy.ops.render.render(write_still=True)
        return
    if '--sandtest' in sys.argv:          # the floor as the channel shows it (no baked light net)
        common.render_settings(48, transparent=False)
        bpy.data.objects['surface'].hide_render = True
        bpy.data.objects['key'].data.energy *= 0.55
        sc.render.resolution_percentage = 50
        sc.render.filepath = os.path.join(R.OUT, 'sand_quick.png')
        bpy.ops.render.render(write_still=True)
        return
    if QUICK:
        common.render_settings(48, transparent=False)
        sc.cycles.volume_bounces = 1
        sc.render.resolution_percentage = 50
        sc.render.filepath = os.path.join(R.OUT, 'scan_quick.png')
        bpy.ops.render.render(write_still=True)
        return
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    p = world_to_camera_view(sc, camob, mouth)
    p2 = world_to_camera_view(sc, camob, mouth + Vector((1, 0, 0)))
    info = {'width': RT.TANK_W, 'photo_reef': True, 'cave_mouth': [p.x * RT.TANK_W, (1 - p.y) * 1080, p.z],
            'px_per_m_at_cave': (p2.x - p.x) * RT.TANK_W,
            'camera': {'loc': list(camob.location), 'rot': list(camob.rotation_euler),
                       'lens': camob.data.lens, 'sensor': camob.data.sensor_width}}
    R.render_beauty(os.path.join(R.OUT, 'scene_beauty.png'))
    R.render_sand(os.path.join(R.OUT, 'scene_sand.png'))
    R.render_mask(os.path.join(R.OUT, 'scene_mask.png'))
    R.render_posnrm(os.path.join(R.OUT, 'scene_posnrm.png'))
    json.dump(info, open(os.path.join(R.OUT, 'scene.json'), 'w'), indent=1)



if __name__ == "__main__":
    main()

"""Blender script: the giant clam, rendered inside the reef scene.

    blender -b --factory-startup -P reefclam.py -- <textures dir> <out dir> <samples> <mantle texture>

Builds the same tank as reeftank.py, sets the clam (clam3d.py's model) on the
gravel, and renders only the clam - every other object held out, the gravel
catching its shadow - with the reef's own camera, light and perspective, at
16 stages from open to closed.  The frames drop into the picture pixel for
pixel.  Writes <out dir>/clamframes/clam_NN.png and <out dir>/clam.json.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
argv_all = sys.argv[sys.argv.index('--') + 1:]
import reeftank as RT  # noqa: E402  (reads <textures dir> <out dir> itself)
import common  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402

TEX, OUT = [os.path.abspath(a) for a in argv_all[:2]]
SAMPLES = int(argv_all[2])
MANTLE = os.path.abspath(argv_all[3])
FRAMES = 16
CLAM_X, CLAM_Y, CLAM_W = 1.60, -1.55, 0.62       # where on the gravel, and how wide (m)

# clam3d reads its own arguments when imported
sys.argv = [sys.argv[0], '--', MANTLE, os.path.join(TEX, 'rock_04_diff.jpg'), os.path.join(OUT, 'clamframes')]
import clam3d as C  # noqa: E402


def main():
    camob, mouth = RT.build()
    RT.lights()
    sc = bpy.context.scene
    ground, _ = RT.surface(CLAM_X, CLAM_Y, skip=('wall',))
    shell_m = C.material_tex('shell', C.SHELL, 0.85, 0.0, tint=(0.95, 0.93, 0.90))
    mantle_m = C.material_tex('mantle', C.MANTLE, 0.55, 0.06, sss=0.08, tint=(0.9, 1.0, 1.15))
    OPEN = math.radians(24)
    pf, uf = C.valve_pts(1, OPEN)
    pb, ub = C.valve_pts(-1, OPEN)
    front = C.grid_mesh('clamfront', pf, C.NU, C.NV, uf)
    back = C.grid_mesh('clamback', pb, C.NU, C.NV, ub)
    pm, um, nm = C.mantle_pts(OPEN, 0.10)
    mantle = C.grid_mesh('clammantle', pm, C.NU, nm, um)
    rig = bpy.data.objects.new('clamrig', None)
    bpy.context.collection.objects.link(rig)
    s = CLAM_W / (2 * C.L)
    rig.scale = (s, s, s)
    rig.location = ground + Vector((0, 0, -0.02))
    rig.rotation_euler = (0, 0, math.radians(-6))
    clam_parts = [front, back, mantle]
    for ob, m in ((front, shell_m), (back, shell_m), (mantle, mantle_m)):
        ob.data.materials.append(m)
        if ob is not mantle:
            sol = ob.modifiers.new('sol', 'SOLIDIFY')
            sol.thickness = 0.045
        sub = ob.modifiers.new('sub', 'SUBSURF')
        sub.levels = sub.render_levels = 1
        ob.parent = rig
    bpy.context.view_layer.update()

    # only the clam: everything else held out, the gravel catching its shadow, no haze volume
    for o in sc.objects:
        if o.type != 'MESH' or o in clam_parts:
            continue
        if o.name in ('water', 'surface'):
            o.hide_render = True
        elif o.name == 'gravel':
            o.is_shadow_catcher = True
        else:
            o.is_holdout = True
    common.render_settings(SAMPLES, transparent=True)
    # the part of the picture the clam (and its shadow) can occupy
    corners = []
    for o in clam_parts:
        corners += [o.matrix_world @ Vector(c) for c in o.bound_box]
    pts = [world_to_camera_view(sc, camob, c) for c in corners]
    W, H = sc.render.resolution_x, sc.render.resolution_y
    x0 = max(0.0, min(p.x for p in pts) - 0.03)
    x1 = min(1.0, max(p.x for p in pts) + 0.05)
    y0 = max(0.0, min(p.y for p in pts) - 0.05)
    y1 = min(1.0, max(p.y for p in pts) + 0.03)
    sc.render.use_border = True
    sc.render.use_crop_to_border = True
    sc.render.border_min_x, sc.render.border_max_x = x0, x1
    sc.render.border_min_y, sc.render.border_max_y = y0, y1
    outdir = os.path.join(OUT, 'clamframes')
    os.makedirs(outdir, exist_ok=True)
    for f in range(FRAMES):
        c = f / (FRAMES - 1)
        c = c * c * (3 - 2 * c)
        a = OPEN * (1 - c) + math.radians(1.5) * c
        for ob, side in ((front, 1), (back, -1)):
            p, _ = C.valve_pts(side, a)
            ob.data.vertices.foreach_set('co', [k for q in p for k in q])
            ob.data.update()
        p, _, _ = C.mantle_pts(a, 0.10 * (1 - c) - 0.05 * c)
        mantle.data.vertices.foreach_set('co', [k for q in p for k in q])
        mantle.data.update()
        sc.render.filepath = os.path.join(outdir, 'clam_%02d.png' % f)
        bpy.ops.render.render(write_still=True)
    json.dump({'crop': True, 'x': round(x0 * W), 'y': round((1 - y1) * H), 'w': round((x1 - x0) * W),
               'h': round((y1 - y0) * H), 'frames': FRAMES}, open(os.path.join(OUT, 'clam.json'), 'w'), indent=1)


main()

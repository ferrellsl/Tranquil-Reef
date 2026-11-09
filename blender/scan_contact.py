"""Renders a thumbnail of every scan in a folder (front and top), so shapes, up axis and bases can be checked.
    blender -b --factory-startup -P scan_contact.py -- <file list> <out dir>
"""
import math, os, sys, json
import bpy
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
argv = sys.argv[sys.argv.index('--') + 1:]
files = [l.strip() for l in open(argv[0]) if l.strip()]
OUT = os.path.abspath(argv[1])
info = {}
for path in files:
    common.reset_scene()
    bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.data.objects if o.type == 'MESH']
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in ms for c in o.bound_box]
    lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
    size = hi - lo; c = (lo + hi) / 2; r = size.length / 2
    nv = sum(len(o.data.vertices) for o in ms)
    key = os.path.splitext(os.path.basename(path))[0]
    info[key] = {'size': [round(v, 4) for v in size], 'verts': nv}
    common.sun('key', (0.3, 0.5, -1.0), 4.0, (1, 1, 1), angle=10)
    w = bpy.context.scene.world or bpy.data.worlds.new('w'); bpy.context.scene.world = w
    w.use_nodes = True; w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.6
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); bpy.context.collection.objects.link(cam)
    cam.data.type = 'ORTHO'; cam.data.ortho_scale = max(size) * 1.1
    sc = bpy.context.scene; sc.camera = cam
    sc.render.resolution_x = sc.render.resolution_y = 360
    common.render_settings(16, transparent=False)
    for view, loc, rot in (('front', c + Vector((0, -3 * r, 0)), (math.radians(90), 0, 0)),
                           ('top', c + Vector((0, 0, 3 * r)), (0, 0, 0))):
        cam.location = loc; cam.rotation_euler = rot
        sc.render.filepath = os.path.join(OUT, key + '_' + view + '.png')
        bpy.ops.render.render(write_still=True)
json.dump(info, open(os.path.join(OUT, 'info.json'), 'w'), indent=1)

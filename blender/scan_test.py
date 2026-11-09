"""Test: a Smithsonian coral scan (CC0) on a Poly Haven rock scan (CC0), lit
like the tank, the coral given living tissue colour.

    blender -b --factory-startup -P scan_test.py -- <scans dir> <out.png>
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
SCANS, OUTPNG = os.path.abspath(argv[0]), os.path.abspath(argv[1])
CORAL = argv[2] if len(argv) > 2 else 'acropora_secale.glb'
ROCK = argv[3] if len(argv) > 3 else 'coast_rocks_05.gltf'
TINT = [float(v) for v in argv[4].split(',')] if len(argv) > 4 else [0.30, 0.18, 0.06, 0.85, 0.62, 0.30]
CHEIGHT = float(argv[5]) if len(argv) > 5 else 0.55
CUT = float(argv[6]) if len(argv) > 6 else 0.22


def import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    return new, meshes


def bounds(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def fit(objs, roots, height, base):
    """Scale and move an imported model so it stands `height` tall with its bottom middle at base."""
    for r in roots:
        r.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    s = height / max(hi.z - lo.z, 1e-6)
    for r in roots:
        r.scale = (s, s, s)
    bpy.context.view_layer.update()
    lo, hi = bounds(objs)
    mid = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for r in roots:
        r.location += base - mid
    bpy.context.view_layer.update()


def living(mat, base_col, tip_col):
    """Keep the scan's own surface detail; colour it as living tissue, paler at the tips."""
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
    bsdf.inputs['Subsurface Weight'].default_value = 0.25
    bsdf.inputs['Subsurface Scale'].default_value = 0.01
    bsdf.inputs['Roughness'].default_value = 0.55


def main():
    common.reset_scene()
    rk_all, rk = import_gltf(os.path.join(SCANS, ROCK))
    fit(rk_all, [o for o in rk_all if o.parent is None], 0.9, Vector((0, 0, 0)))
    lo, hi = bounds(rk)
    co_all, co = import_gltf(os.path.join(SCANS, CORAL))
    # museum specimens sit on a display block: cut away the bottom of the model
    import bmesh
    for o in co:
        lo_, hi_ = bounds([o])
        cut = lo_.z + CUT * (hi_.z - lo_.z)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        mw = o.matrix_world
        gone = [v for v in bm.verts if (mw @ v.co).z < cut]
        bmesh.ops.delete(bm, geom=gone, context='VERTS')
        bm.to_mesh(o.data)
        bm.free()
    fit(co_all, [o for o in co_all if o.parent is None], CHEIGHT, Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z - 0.08)))
    for o in co:
        for m in o.data.materials:
            living(m, tuple(TINT[:3]), tuple(TINT[3:]))
    # gravel floor
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    fl = bpy.context.active_object
    fm = bpy.data.materials.new('floor')
    fm.use_nodes = True
    fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.75, 0.70, 0.62, 1)
    fl.data.materials.append(fm)
    import tank3d_world as TW
    TW.water_world()
    common.sun('key', (0.18, 0.32, -1.0), 16.0, (1.0, 0.99, 0.96), angle=2.0)
    common.sun('fill', (0.0, 1.0, -0.35), 0.25, (0.85, 0.93, 1.0), angle=25)
    cam = bpy.data.cameras.new('cam')
    cam.lens = 50
    camob = bpy.data.objects.new('cam', cam)
    bpy.context.collection.objects.link(camob)
    CAM = [float(v) for v in argv[7].split(',')] if len(argv) > 7 else [0, -4.6, 1.05, 86]
    camob.location = tuple(CAM[:3])
    camob.rotation_euler = (math.radians(CAM[3]), 0, 0)
    bpy.context.scene.camera = camob
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    common.render_settings(128, transparent=False)
    sc.render.filepath = OUTPNG
    bpy.ops.render.render(write_still=True)


main()

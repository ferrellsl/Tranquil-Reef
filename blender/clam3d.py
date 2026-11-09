"""Blender script: a giant clam (Tridacna) that opens and closes.

    blender -b --factory-startup -P clam3d.py -- <mantle texture> <shell texture> <outdir> [frames] [samples]

Two thick ribbed valves hinged along the bottom, their lips folded into the
zigzag of a Tridacna; between them the mantle, textured from a public-domain
photo of a clam's mantle.  Frame 0 is fully open, the last frame closed: the
valves turn together about the hinge and the mantle draws down between them.
Seen from the front and a little above, as on a tank floor.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
MANTLE, SHELL, OUTDIR = [os.path.abspath(a) for a in argv[:3]]
FRAMES = int(argv[3]) if len(argv) > 3 else 16
SAMPLES = int(argv[4]) if len(argv) > 4 else 64

L = 1.0          # half length along the hinge
D = 0.42         # how far each valve bulges out
HGT = 0.55       # height of a valve, hinge to lip
FOLDS = 5        # big folds along the lip
NU, NV = 120, 40


def lip_wave(x):
    """The zigzag of the lip: big folds, fading toward the ends."""
    return 0.11 * math.sin((x / L) * FOLDS * math.pi + math.pi / 2) * (1 - (x / L) ** 2) ** 0.5


def valve_point(x, v, side, open_a):
    """A point on one valve: x along the hinge, v from hinge (0) to lip (1)."""
    env = (1 - (x / L) ** 2) ** 0.5                   # the valve narrows to its ends
    phi = v * math.pi * 0.62
    y = -side * D * env * math.sin(phi) * (1 + 0.25 * lip_wave(x) / 0.11 * v)
    z = HGT * env ** 0.6 * (1 - math.cos(phi)) / (1 - math.cos(math.pi * 0.62))
    # ribs running from the hinge to the lip
    rib = 0.025 * math.sin((x / L) * FOLDS * 2 * math.pi) * v
    y -= side * rib
    z += lip_wave(x) * v ** 2
    # open: the valve turns about the hinge (the x axis)
    a = side * open_a
    yr = y * math.cos(a) - z * math.sin(a)
    zr = y * math.sin(a) + z * math.cos(a)
    return (x, yr, zr)


def grid_mesh(name, pts, nu, nv, uvs):
    faces = []
    for i in range(nu - 1):
        for j in range(nv - 1):
            a = i * nv + j
            faces.append((a, a + nv, a + nv + 1, a + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(ob)
    return ob


def valve_pts(side, open_a):
    pts, uvs = [], []
    for i in range(NU):
        x = -L * 0.995 + 2 * L * 0.995 * i / (NU - 1)
        for j in range(NV):
            v = j / (NV - 1)
            pts.append(valve_point(x, v, side, open_a))
            uvs.append(((x + L) / (2 * L), v))
    return pts, uvs


def mantle_pts(open_a, swell):
    """The mantle: from the front lip over to the back lip, swelling up between them."""
    pts, uvs = [], []
    nm = 16
    for i in range(NU):
        x = -L * 0.995 + 2 * L * 0.995 * i / (NU - 1)
        f = Vector(valve_point(x, 0.97, 1, open_a))
        b = Vector(valve_point(x, 0.97, -1, open_a))
        env = (1 - (x / L) ** 2) ** 0.5
        for j in range(nm):
            s = j / (nm - 1)
            p = f.lerp(b, s)
            p.z += swell * env * math.sin(math.pi * s) - 0.02
            pts.append(tuple(p))
            uvs.append(((x + L) / (2 * L), s))
    return pts, uvs, nm


def material_tex(name, path, rough, coat, sss=0.0, tint=(1, 1, 1)):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes['Principled BSDF']
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(path)
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Factor'].default_value = 1.0
    nt.links.new(img.outputs['Color'], mul.inputs['A'])
    mul.inputs['B'].default_value = (*tint, 1)
    nt.links.new(mul.outputs['Result'], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = coat
    b.inputs['Subsurface Weight'].default_value = sss
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.4
    nt.links.new(img.outputs['Color'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return mat


def main():
    common.reset_scene()
    # an encrusted grey-white shell like the reef rock; a rich, matte mantle
    shell_m = material_tex('shell', SHELL, 0.85, 0.0, tint=(0.95, 0.93, 0.90))
    mantle_m = material_tex('mantle', MANTLE, 0.55, 0.06, sss=0.08, tint=(0.9, 1.0, 1.15))
    OPEN = math.radians(24)
    pf, uf = valve_pts(1, OPEN)
    pb, ub = valve_pts(-1, OPEN)
    front = grid_mesh('front', pf, NU, NV, uf)
    back = grid_mesh('back', pb, NU, NV, ub)
    pm, um, nm = mantle_pts(OPEN, 0.10)
    mantle = grid_mesh('mantle', pm, NU, nm, um)
    for ob, m in ((front, shell_m), (back, shell_m), (mantle, mantle_m)):
        ob.data.materials.append(m)
        if ob is not mantle:
            sol = ob.modifiers.new('sol', 'SOLIDIFY')
            sol.thickness = 0.045
        sub = ob.modifiers.new('sub', 'SUBSURF')
        sub.levels = sub.render_levels = 1

    cam = common.sprite_camera(center=(0.0, 0.25), ortho_width=2.5, res=(760, 420))
    target = Vector((0.0, 0.0, 0.20))
    dv = Vector((0.0, -math.cos(math.radians(36)), math.sin(math.radians(36))))
    cam.location = target + dv * 6.0
    cam.rotation_euler = (-dv).to_track_quat('-Z', 'Y').to_euler()
    # the same light as the reef (reeftank.py): strong sun from above, dim water round about
    import tank3d_world as TW
    TW.water_world()
    common.sun('key', (0.18, 0.32, -1.0), 16.0, (1.0, 0.99, 0.96), angle=2.0)
    common.sun('fill', (0.0, 1.0, -0.35), 0.25, (0.85, 0.93, 1.0), angle=25)
    # a floor that only catches its shadow: the frames carry its real contact shadow
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, 0, 0.0))
    catcher = bpy.context.active_object
    catcher.is_shadow_catcher = True
    common.render_settings(SAMPLES, transparent=True)
    os.makedirs(OUTDIR, exist_ok=True)
    for f in range(FRAMES):
        c = f / (FRAMES - 1)
        c = c * c * (3 - 2 * c)
        a = OPEN * (1 - c) + math.radians(1.5) * c
        p, _ = valve_pts(1, a)
        front.data.vertices.foreach_set('co', [k for q in p for k in q])
        front.data.update()
        p, _ = valve_pts(-1, a)
        back.data.vertices.foreach_set('co', [k for q in p for k in q])
        back.data.update()
        p, _, _ = mantle_pts(a, 0.10 * (1 - c) - 0.05 * c)
        mantle.data.vertices.foreach_set('co', [k for q in p for k in q])
        mantle.data.update()
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, 'clam_%02d.png' % f)
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()

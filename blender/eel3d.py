"""Blender script: a moray eel leaning out of its hole, breathing.

    blender -b --factory-startup -P eel3d.py -- <outdir> [frames] [samples]

Renders <outdir>/moray_NN.png: the front part of the eel, head to the right,
the body running off to the left (the channel clips it at the cave mouth).
The lower jaw hinges open and shut like a moray pumping water over its
gills, and the head sways a little.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
OUTDIR = os.path.abspath(argv[0])
FRAMES = int(argv[1]) if len(argv) > 1 else 24
SAMPLES = int(argv[2]) if len(argv) > 2 else 64
WPX, HPX = 820, 300

NS, NR = 140, 36
HINGE = 0.875            # where the jaws meet, along the body
S0 = -0.15               # the body starts off-screen to the left


def radius(s):
    if s < 0.68:
        return 0.064
    if s < 0.85:                      # the heavy head behind the eyes
        t = (s - 0.68) / 0.17
        return 0.064 + 0.020 * math.sin(t * math.pi / 2)
    t = (s - 0.85) / 0.15             # tapering snout, rounded at the tip
    return 0.084 * math.sqrt(max(0.0, 1 - t ** 2.0)) * (1 - 0.50 * t) + 0.003


def centerline(phase):
    """(x, z, angle) along s: the body rises out of the hole and the head
    is held up, with a slow sway."""
    pts = []
    x, z = S0, 0.0
    prev = None
    ds = (1.04 - S0) / (NS - 1)
    for i in range(NS):
        s = S0 + i * ds
        bend = 0.20 * math.exp(-((s - 0.45) / 0.25) ** 2) - 0.10 * math.exp(-((s - 0.85) / 0.12) ** 2)
        sway = 0.035 * math.sin(phase + s * 3.0) * max(0.0, s)
        ang = bend + sway
        if prev is not None:
            a = 0.5 * (ang + prev)
            x += ds * math.cos(a)
            z += ds * math.sin(a)
        pts.append((s, x, z, ang))
        prev = ang
    return pts


def build_rest():
    """Vertex list per (ring i, j) as (s, theta) and faces; the faces that
    cross the mouth line in the head are left out, so the jaws can part."""
    faces = []
    for i in range(NS - 1):
        s = S0 + i * (1.04 - S0) / (NS - 1)
        for j in range(NR):
            a = i * NR + j
            b = i * NR + (j + 1) % NR
            th_a = 2 * math.pi * j / NR
            th_b = 2 * math.pi * ((j + 1) % NR) / NR
            if s >= HINGE - 0.005 and (is_lower(th_a) != is_lower(th_b)):
                continue
            faces.append((a, b, b + NR, a + NR))
    return faces


def is_lower(th):
    # the mouth line sits a little below the middle of the snout
    return math.cos(th) < -0.15


def ring_point(s, th, gape, cl_row):
    _, cx, cz, ang = cl_row
    r = radius(s)
    hz = r * 1.18 * math.cos(th)
    hy = r * 0.85 * math.sin(th)
    # lower jaw rotates down about the hinge
    if s >= HINGE - 0.04 and is_lower(th):
        w = min(1.0, max(0.0, (s - (HINGE - 0.04)) / 0.05))
        g = gape * w
        ls = s - HINGE
        lz = hz + r * 0.15
        ls, lz = ls * math.cos(-g) - lz * math.sin(-g), ls * math.sin(-g) + lz * math.cos(-g)
        s_eff = HINGE + ls
        hz = lz - r * 0.15
        # move along the centerline by the change in s
        cx += (s_eff - s) * math.cos(ang)
        cz += (s_eff - s) * math.sin(ang)
    nx, nz = -math.sin(ang), math.cos(ang)
    return (cx + nx * hz, hy, cz + nz * hz)


def eel_material():
    mat = bpy.data.materials.new('moray')
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    L = nt.links
    tc = nt.nodes.new('ShaderNodeTexCoord')
    # dense dark freckles over an olive-green body, paler on the throat
    v = nt.nodes.new('ShaderNodeTexVoronoi')
    v.inputs['Scale'].default_value = 120
    v.inputs['Randomness'].default_value = 1.0
    L.new(tc.outputs['Object'], v.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (0.035, 0.035, 0.015, 1)
    ramp.color_ramp.elements[1].position = 0.30
    ramp.color_ramp.elements[1].color = (0.16, 0.20, 0.045, 1)
    L.new(v.outputs['Distance'], ramp.inputs['Fac'])
    n = nt.nodes.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = 6
    n.inputs['Detail'].default_value = 6
    L.new(tc.outputs['Object'], n.inputs['Vector'])
    mx = nt.nodes.new('ShaderNodeMix')
    mx.data_type = 'RGBA'
    mx.blend_type = 'MULTIPLY'
    mx.inputs['Factor'].default_value = 0.6
    L.new(ramp.outputs['Color'], mx.inputs['A'])
    L.new(n.outputs['Color'], mx.inputs['B'])
    bright = nt.nodes.new('ShaderNodeMath')
    bright.operation = 'MULTIPLY'
    bright.inputs[1].default_value = 1.8
    hsv = nt.nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Value'].default_value = 1.9
    L.new(mx.outputs['Result'], hsv.inputs['Color'])
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(hsv.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.45
    bsdf.inputs['Coat Weight'].default_value = 0.4      # slime
    bsdf.inputs['Coat Roughness'].default_value = 0.08
    bsdf.inputs['Subsurface Weight'].default_value = 0.08
    bsdf.inputs['Subsurface Scale'].default_value = 0.01
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.003
    L.new(n.outputs['Fac'], bump.inputs['Height'])
    L.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    return mat


def simple_material(name, color, rough=0.5, coat=0.0, emit=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    b = mat.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*color, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = coat
    return mat


def main():
    common.reset_scene()
    faces = build_rest()
    rows = [(S0 + i * (1.04 - S0) / (NS - 1)) for i in range(NS)]
    cl = centerline(0)
    pts = [ring_point(s, 2 * math.pi * j / NR, 0.1, cl[i]) for i, s in enumerate(rows) for j in range(NR)]
    me = bpy.data.meshes.new('moray')
    me.from_pydata(pts, [], faces)
    me.shade_smooth()
    body = bpy.data.objects.new('moray', me)
    bpy.context.collection.objects.link(body)
    body.data.materials.append(eel_material())
    sub = body.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1

    # the low fin along the back
    fin_rows = [s for s in rows if s < 0.80]
    def fin_pts(cl):
        out = []
        for s in fin_rows:
            i = rows.index(s)
            for k in range(4):
                q = k / 3
                th = 0.0
                p = ring_point(s, th, 0, cl[i])
                _, _, _, ang = cl[i]
                hgt = (0.002 + 0.016 * q) * min(1.0, (0.80 - s) / 0.08)
                out.append((p[0] - math.sin(ang) * hgt, 0.0, p[2] + math.cos(ang) * hgt - 0.010))
        return out
    ff = []
    for a in range(len(fin_rows) - 1):
        for k in range(3):
            i = a * 4 + k
            ff.append((i, i + 4, i + 5, i + 1))
    fme = bpy.data.meshes.new('fin')
    fme.from_pydata(fin_pts(cl), [], ff)
    fin = bpy.data.objects.new('fin', fme)
    bpy.context.collection.objects.link(fin)
    fin.data.materials.append(eel_material())
    sol = fin.modifiers.new('sol', 'SOLIDIFY')
    sol.thickness = 0.004

    # inside of the mouth: dark pink throat
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
    throat = bpy.context.active_object
    throat.data.materials.append(simple_material('throat', (0.18, 0.03, 0.03), 0.5, 0.6))
    throat.data.shade_smooth()

    # eyes: small and bright, set high on the head
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
    eye = bpy.context.active_object
    eye.data.materials.append(common.eye_material('eye', (0.85, 0.70, 0.20)))
    eye.data.shade_smooth()

    # teeth along both jaws
    teeth = []
    tooth_mat = simple_material('tooth', (0.85, 0.83, 0.75), 0.3, 0.5)
    for k in range(0):
        for jaw in (0, 1):
            bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.0045, radius2=0.0, depth=0.014)
            t = bpy.context.active_object
            t.data.materials.append(tooth_mat)
            teeth.append((t, k, jaw))

    cam = common.sprite_camera(center=(0.45, 0.08), ortho_width=1.10, res=(WPX, HPX))
    # from a little in front of the head and above, for a glimpse of the face
    target = Vector((0.45, 0.0, 0.10))
    d = Vector((math.sin(math.radians(16)), -math.cos(math.radians(16)), math.sin(math.radians(5)))).normalized()
    cam.location = target + d * 5.0
    cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    common.underwater_lights()
    common.render_settings(SAMPLES, transparent=True)

    os.makedirs(OUTDIR, exist_ok=True)
    for f in range(FRAMES):
        ph = 2 * math.pi * f / FRAMES
        gape = 0.05 + 0.30 * (0.5 - 0.5 * math.cos(ph)) ** 1.5
        cl = centerline(ph)
        pts = [ring_point(s, 2 * math.pi * j / NR, gape, cl[i]) for i, s in enumerate(rows) for j in range(NR)]
        body.data.vertices.foreach_set('co', [c for p in pts for c in p])
        body.data.update()
        fin.data.vertices.foreach_set('co', [c for p in fin_pts(cl) for c in p])
        fin.data.update()

        def at(s, th, frac=1.0, g=gape):
            i = min(range(NS), key=lambda k: abs(rows[k] - s))
            return Vector(ring_point(rows[i], th, g, cl[i]))

        hi = min(range(NS), key=lambda k: abs(rows[k] - 0.93))
        _, hx, hz, hang = cl[hi]
        throat.location = (hx, 0, hz - 0.012)
        throat.scale = (0.080, 0.040, 0.028 + 0.06 * gape)
        throat.rotation_euler = (0, -hang + gape * 0.5, 0)
        e = at(0.905, math.radians(40))
        eye.location = (e.x, -0.042, e.z + 0.004)
        eye.scale = (0.010, 0.007, 0.010)
        for t, k, jaw in teeth:
            s = 0.90 + k * 0.0145
            th = math.radians(180 - 68) if jaw == 0 else math.radians(180 + 68)
            if jaw == 0:   # upper teeth hang from the upper lip, pointing down
                p = at(s, math.radians(118), g=gape)
                t.location = (p.x, -0.012 - 0.006 * (k % 2), p.z - 0.005)
                t.rotation_euler = (math.pi, 0, 0)
            else:          # lower teeth stand on the lower jaw, pointing up
                p = at(s, math.radians(205), g=gape)
                t.location = (p.x, -0.012 - 0.006 * (k % 2), p.z + 0.006)
                t.rotation_euler = (0, -(hang - gape), 0)
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, 'moray_%02d.png' % f)
        bpy.ops.render.render(write_still=True)


main()

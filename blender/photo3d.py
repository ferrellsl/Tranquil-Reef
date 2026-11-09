"""Blender script: a 3D fish from a photo, swimming and turning.

    blender -b --factory-startup -P photo3d.py -- <grid.json> <outdir> <width px> [frames] [samples] [turn frames] [amp]

The grid (photos/inflate.py) gives the silhouette, the thickness and the
fin-ness at each point of the photo.  The front and back surfaces are built
from it with the photo as their skin, sealed along the edge.  The whole fish
bends along a travelling wave (length kept, so the tail really swings), fin
areas lag and curl behind the stroke, and a turn-around is rendered too.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
G = json.load(open(argv[0]))
OUTDIR = os.path.abspath(argv[1])
WPX = int(argv[2])
FRAMES = int(argv[3]) if len(argv) > 3 else 12
SAMPLES = int(argv[4]) if len(argv) > 4 else 64
TURN = int(argv[5]) if len(argv) > 5 else 20
AMP = float(argv[6]) if len(argv) > 6 else 0.075
NAME = G['key']
YAW = math.radians(-9)
PITCH = math.radians(6)

N_CL = 160
CL_U = np.linspace(-0.05, 1.10, N_CL)


def centerline(phase, curl=0.0):
    u = CL_U
    env = 0.10 + 0.90 * np.clip(u, 0, 1) ** 2
    lat = AMP * env * np.sin(phase - 2 * math.pi * 0.85 * u) + curl * (u - 0.35) ** 2
    ang = np.arctan(np.gradient(lat, u))
    du = np.diff(u)
    a = 0.5 * (ang[1:] + ang[:-1])
    xs = np.concatenate([[u[0]], u[0] + np.cumsum(du * np.cos(a))])
    ys = np.concatenate([[lat[0]], lat[0] + np.cumsum(du * np.sin(a))])
    ax = np.interp(0.3, u, xs) - 0.3
    ay = np.interp(0.3, u, ys)
    return xs - ax, ys - ay, ang


def build():
    cols, rows = G['cols'], G['rows']
    asp = G['aspect']
    inside = np.array(G['inside'], bool).reshape(rows, cols)
    z = np.array(G['z'], np.float32).reshape(rows, cols)
    fin = np.array(G['fin'], np.float32).reshape(rows, cols)
    idx = -np.ones((2, rows, cols), int)
    verts, uvs, fins, rest = [], [], [], []
    for side, sgn in ((0, -1), (1, 1)):          # front faces the camera (at -y)
        for j in range(rows):
            for i in range(cols):
                if not inside[j, i]:
                    continue
                u = i / (cols - 1)
                y = (0.5 - j / (rows - 1)) * asp
                idx[side, j, i] = len(verts)
                rest.append((u, sgn * float(z[j, i]), y))
                verts.append((u, sgn * float(z[j, i]), y))
                uvs.append((u, 1 - j / (rows - 1)))
                fins.append(float(fin[j, i]))
    faces = []
    for j in range(rows - 1):
        for i in range(cols - 1):
            q = [idx[0, j, i], idx[0, j, i + 1], idx[0, j + 1, i + 1], idx[0, j + 1, i]]
            if min(q) < 0:
                continue
            faces.append((q[0], q[3], q[2], q[1]))
            b = [idx[1, j, i], idx[1, j, i + 1], idx[1, j + 1, i + 1], idx[1, j + 1, i]]
            faces.append((b[0], b[1], b[2], b[3]))
    me = bpy.data.meshes.new(NAME)
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name='UVMap')
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    at = me.attributes.new('fin', 'FLOAT', 'POINT')
    at.data.foreach_set('value', fins)
    me.shade_smooth()
    ob = bpy.data.objects.new(NAME, me)
    bpy.context.collection.objects.link(ob)
    return ob, np.array(rest, np.float32), np.array(fins, np.float32)


def material(tex_path):
    mat = bpy.data.materials.new('skin')
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    L = nt.links
    uvn = nt.nodes.new('ShaderNodeUVMap')
    img = nt.nodes.new('ShaderNodeTexImage')
    img.image = bpy.data.images.load(tex_path)
    img.image.alpha_mode = 'STRAIGHT'
    img.interpolation = 'Cubic'
    L.new(uvn.outputs['UV'], img.inputs['Vector'])
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_name = 'fin'
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    L.new(img.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.45
    # wet sheen on the body, less on the fins
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    L.new(attr.outputs['Fac'], inv.inputs[1])
    coat = nt.nodes.new('ShaderNodeMath')
    coat.operation = 'MULTIPLY'
    coat.inputs[1].default_value = 0.30
    L.new(inv.outputs['Value'], coat.inputs[0])
    L.new(coat.outputs['Value'], bsdf.inputs['Coat Weight'])
    bsdf.inputs['Coat Roughness'].default_value = 0.15
    bsdf.inputs['Specular IOR Level'].default_value = 0.35
    # fins let light through
    tr = nt.nodes.new('ShaderNodeBsdfTranslucent')
    L.new(img.outputs['Color'], tr.inputs['Color'])
    fmix = nt.nodes.new('ShaderNodeMath')
    fmix.operation = 'MULTIPLY'
    fmix.inputs[1].default_value = 0.45
    L.new(attr.outputs['Fac'], fmix.inputs[0])
    m1 = nt.nodes.new('ShaderNodeMixShader')
    L.new(fmix.outputs['Value'], m1.inputs['Fac'])
    L.new(bsdf.outputs['BSDF'], m1.inputs[1])
    L.new(tr.outputs['BSDF'], m1.inputs[2])
    tp = nt.nodes.new('ShaderNodeBsdfTransparent')
    m2 = nt.nodes.new('ShaderNodeMixShader')
    L.new(img.outputs['Alpha'], m2.inputs['Fac'])
    L.new(tp.outputs['BSDF'], m2.inputs[1])
    L.new(m1.outputs['Shader'], m2.inputs[2])
    L.new(m2.outputs['Shader'], out.inputs['Surface'])
    return mat


def pose(ob, rest, fins, phase, curl=0.0):
    xs, ys, ang = centerline(phase, curl)
    u, s, y = rest[:, 0], rest[:, 1].copy(), rest[:, 2]
    # fins trail the stroke and curl at their free edges; the tail most
    lag = (0.035 + 0.06 * np.clip((u - 0.6) / 0.4, 0, 1)) * np.sin(phase - 2 * math.pi * 0.85 * u - 1.2)
    s = s + fins ** 1.5 * lag
    cx = np.interp(u, CL_U, xs)
    cy = np.interp(u, CL_U, ys)
    a = np.interp(u, CL_U, ang)
    out = np.stack([cx - s * np.sin(a), cy + s * np.cos(a), y], axis=1)
    ob.data.vertices.foreach_set('co', out.ravel())
    ob.data.update()


def main():
    common.reset_scene()
    ob, rest, fins = build()
    ob.data.materials.append(material(G['tex']))
    sub = ob.modifiers.new('sub', 'SUBSURF')
    sub.levels = sub.render_levels = 1
    # seal the front and back along the edge (both lie at thickness 0 there)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(ob.data)
    bm.free()
    # remove_doubles renumbers vertices: rebuild the rest positions from the mesh
    n = len(ob.data.vertices)
    co = np.zeros(n * 3, np.float32)
    ob.data.vertices.foreach_get('co', co)
    rest = co.reshape(n, 3)
    fv = np.zeros(n, np.float32)
    ob.data.attributes['fin'].data.foreach_get('value', fv)
    fins = fv

    rig = bpy.data.objects.new('rig', None)
    bpy.context.collection.objects.link(rig)
    PIV = 0.45
    rig.location = (PIV, 0, 0)
    ob.parent = rig
    ob.matrix_parent_inverse.identity()
    ob.matrix_parent_inverse[0][3] = -PIV

    asp = G['aspect']
    margin_w, margin_h = 1.10, 1.30
    width = margin_w
    height = max(asp * margin_h, 0.30)
    hpx = int(round(WPX * height / width))
    common.sprite_camera(center=(0.5, 0.0), ortho_width=max(width, height), res=(WPX, hpx), pitch=PITCH)
    common.underwater_lights()
    common.render_settings(SAMPLES, transparent=True)

    os.makedirs(OUTDIR, exist_ok=True)
    for k in range(FRAMES):
        phase = 2 * math.pi * k / FRAMES
        rig.rotation_euler = (0, 0, YAW)
        pose(ob, rest, fins, phase)
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_%02d.png' % (NAME, k))
        bpy.ops.render.render(write_still=True)
    for k in range(TURN):
        p = k / max(1, TURN - 1)
        # nearly even pace: a cosine ease bunched most of the rotation into a few frames
        e = 0.75 * p + 0.25 * (0.5 - 0.5 * math.cos(math.pi * p))
        rig.rotation_euler = (0, 0, YAW - e * (math.pi + 2 * YAW))
        pose(ob, rest, fins, 2 * math.pi * 1.6 * p, 0.55 * math.sin(math.pi * p))
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_turn%02d.png' % (NAME, k))
        bpy.ops.render.render(write_still=True)


main()

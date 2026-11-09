"""Blender script: a fish from a ready-made 3D model (glTF), swimming and turning.

    blender -b --factory-startup -P model3d.py -- <model.glb> <name> <outdir> <width px> [frames] [samples] [turn frames] [amp] [axes]

The same swim as photo3d.py (a travelling wave along the body, length kept,
fins lagging behind the stroke), the same camera, lights and frame names, so
build.py treats it like any other species.  <axes> says how the model lies:
the model axis the fish runs along from head to tail, and the one that is up,
e.g. "-y,z" (head toward -y, back toward +z; the default).
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
MODEL = os.path.abspath(argv[0])
NAME = argv[1]
OUTDIR = os.path.abspath(argv[2])
WPX = int(argv[3])
FRAMES = int(argv[4]) if len(argv) > 4 else 12
SAMPLES = int(argv[5]) if len(argv) > 5 else 64
TURN = int(argv[6]) if len(argv) > 6 else 20
AMP = float(argv[7]) if len(argv) > 7 else 0.05
AXES = (argv[8] if len(argv) > 8 else '-y,z').split(',')
BRIGHT = float(argv[9]) if len(argv) > 9 else 1.0      # lift a scan's dim texture (value), with a little more color
WHITEN_BLUE = len(argv) > 10 and argv[10] == 'whiten-blue'   # blue-painted body -> silvery white (copperband)
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


def axis_vec(s):
    sign = -1.0 if s.startswith('-') else 1.0
    return sign, 'xyz'.index(s[-1])


def load():
    """The model as one mesh in its own units, laid out like photo3d's fish: head at x=0, tail
    at x=1, its side toward the camera (-y), back up (+z), centered on its middle height."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=MODEL)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    # (stray bits some models carry, e.g. a tiny marker cube: not part of the fish)
    biggest = max(len(o.data.vertices) for o in meshes)
    for o in [o for o in meshes if len(o.data.vertices) < 0.002 * biggest]:
        meshes.remove(o)
        new.remove(o)
        bpy.data.objects.remove(o)
    bpy.context.view_layer.update()
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.rotation_mode = 'XYZ'
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        try:                                # (objects merged by the join are gone already)
            if o != ob and o.name in bpy.data.objects:
                bpy.data.objects.remove(o)
        except ReferenceError:
            pass
    ob.name = NAME
    n = len(ob.data.vertices)
    co = np.zeros(n * 3, np.float32)
    ob.data.vertices.foreach_get('co', co)
    co = co.reshape(n, 3)
    ls, li = axis_vec(AXES[0])
    us, ui = axis_vec(AXES[1])
    si = 3 - li - ui
    along = ls * co[:, li]
    up = us * co[:, ui]
    side = co[:, si]
    L = along.max() - along.min()
    x = (along - along.min()) / L
    z = (up - 0.5 * (up.max() + up.min())) / L
    y = (side - 0.5 * (side.max() + side.min())) / L
    rest = np.stack([x, y, z], axis=1).astype(np.float32)
    ob.data.vertices.foreach_set('co', rest.ravel())
    ob.data.update()
    # fin-ness: how far a point stands out from the body's core (spines and fins move most)
    r = np.sqrt(y ** 2 + z ** 2)
    fins = np.clip((r - 0.10) / 0.25, 0, 1).astype(np.float32)
    return ob, rest, fins, float(z.max() - z.min())


def unlit(m):
    """Some models (scans) come "unlit": their texture shown flat, as emission, ignoring the
    lights.  Give them an ordinary surface, so the tank's lights shape them like the other fish."""
    nt = m.node_tree
    if any(n.type == 'BSDF_PRINCIPLED' for n in nt.nodes):
        return
    tex = [n for n in nt.nodes if n.type == 'TEX_IMAGE']
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL']
    if not tex or not out:
        return
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.45
    nt.links.new(tex[0].outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out[0].inputs['Surface'])


def whiten_blue(m):
    """Where the texture is blue, take the color out and lighten it: silver-white instead."""
    nt = m.node_tree
    bsdf = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED']
    if not bsdf or not bsdf[0].inputs['Base Color'].links:
        return
    bsdf = bsdf[0]
    src = bsdf.inputs['Base Color'].links[0].from_socket
    sep = nt.nodes.new('ShaderNodeSeparateColor')
    sep.mode = 'HSV'
    nt.links.new(src, sep.inputs['Color'])
    # mask: 1 near blue-violet hue (0.58-0.80), fading out over 0.06
    d = nt.nodes.new('ShaderNodeMath')
    d.operation = 'SUBTRACT'
    d.inputs[1].default_value = 0.69
    nt.links.new(sep.outputs['Red'], d.inputs[0])
    ab = nt.nodes.new('ShaderNodeMath')
    ab.operation = 'ABSOLUTE'
    nt.links.new(d.outputs['Value'], ab.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.11
    mr.inputs['From Max'].default_value = 0.17
    mr.inputs['To Min'].default_value = 1.0
    mr.inputs['To Max'].default_value = 0.0
    nt.links.new(ab.outputs['Value'], mr.inputs['Value'])
    sat = nt.nodes.new('ShaderNodeMath')
    sat.operation = 'MULTIPLY_ADD'          # s * (1 - 0.9 mask)
    neg = nt.nodes.new('ShaderNodeMath')
    neg.operation = 'MULTIPLY_ADD'
    neg.inputs[1].default_value = -0.9
    neg.inputs[2].default_value = 1.0
    nt.links.new(mr.outputs['Result'], neg.inputs[0])
    sat.inputs[2].default_value = 0.0
    nt.links.new(sep.outputs['Green'], sat.inputs[0])
    nt.links.new(neg.outputs['Value'], sat.inputs[1])
    # value a little lifted where blue, so dark marks (eyespot, band edges) stay dark
    gain = nt.nodes.new('ShaderNodeMath')
    gain.operation = 'MULTIPLY_ADD'
    gain.inputs[1].default_value = 0.20
    gain.inputs[2].default_value = 1.0
    nt.links.new(mr.outputs['Result'], gain.inputs[0])
    val = nt.nodes.new('ShaderNodeMath')
    val.operation = 'MULTIPLY'
    val.use_clamp = True
    nt.links.new(sep.outputs['Blue'], val.inputs[0])
    nt.links.new(gain.outputs['Value'], val.inputs[1])
    comb = nt.nodes.new('ShaderNodeCombineColor')
    comb.mode = 'HSV'
    nt.links.new(sep.outputs['Red'], comb.inputs['Red'])
    nt.links.new(sat.outputs['Value'], comb.inputs['Green'])
    nt.links.new(val.outputs['Value'], comb.inputs['Blue'])
    nt.links.new(comb.outputs['Color'], bsdf.inputs['Base Color'])


def pose(ob, rest, fins, phase, curl=0.0):
    xs, ys, ang = centerline(phase, curl)
    u, s, y = rest[:, 0], rest[:, 1].copy(), rest[:, 2]
    lag = (0.025 + 0.04 * np.clip((u - 0.6) / 0.4, 0, 1)) * np.sin(phase - 2 * math.pi * 0.85 * u - 1.2)
    s = s + fins ** 1.5 * lag
    cx = np.interp(u, CL_U, xs)
    cy = np.interp(u, CL_U, ys)
    a = np.interp(u, CL_U, ang)
    out = np.stack([cx - s * np.sin(a), cy + s * np.cos(a), y], axis=1)
    ob.data.vertices.foreach_set('co', out.ravel())
    ob.data.update()


def main():
    common.reset_scene()
    ob, rest, fins, tall = load()
    for m in ob.data.materials:
        unlit(m)
        if WHITEN_BLUE:
            whiten_blue(m)
        for nd in m.node_tree.nodes:
            if nd.type == 'BSDF_PRINCIPLED' and BRIGHT != 1.0 and nd.inputs['Base Color'].links:
                nt = m.node_tree
                src = nd.inputs['Base Color'].links[0].from_socket
                hsv = nt.nodes.new('ShaderNodeHueSaturation')
                hsv.inputs['Value'].default_value = BRIGHT
                hsv.inputs['Saturation'].default_value = 1.0 + 0.5 * (BRIGHT - 1.0)
                nt.links.new(src, hsv.inputs['Color'])
                nt.links.new(hsv.outputs['Color'], nd.inputs['Base Color'])
            if nd.type == 'BSDF_PRINCIPLED':
                nd.inputs['Coat Weight'].default_value = 0.2        # wet, like the photo fish
                nd.inputs['Coat Roughness'].default_value = 0.15
    rig = bpy.data.objects.new('rig', None)
    bpy.context.collection.objects.link(rig)
    PIV = 0.45
    rig.location = (PIV, 0, 0)
    ob.parent = rig
    ob.matrix_parent_inverse = Matrix.Translation((-PIV, 0, 0))

    margin_w, margin_h = 1.10, 1.15
    width = margin_w
    height = max(tall * margin_h, 0.30)
    hpx = int(round(WPX * height / width))
    common.sprite_camera(center=(0.5, 0.0), ortho_width=max(width, height), res=(WPX, hpx), pitch=PITCH)
    common.underwater_lights()
    common.render_settings(SAMPLES, transparent=True)

    os.makedirs(OUTDIR, exist_ok=True)
    only = os.environ.get('MODEL3D_ONLY')        # (a test: just this one swim frame)
    for k in range(FRAMES):
        if only is not None and k != int(only):
            continue
        rig.rotation_euler = (0, 0, YAW)
        pose(ob, rest, fins, 2 * math.pi * k / FRAMES)
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_%02d.png' % (NAME, k))
        bpy.ops.render.render(write_still=True)
    if only is not None:
        return
    for k in range(TURN):
        p = k / max(1, TURN - 1)
        e = 0.75 * p + 0.25 * (0.5 - 0.5 * math.cos(math.pi * p))
        rig.rotation_euler = (0, 0, YAW - e * (math.pi + 2 * YAW))
        pose(ob, rest, fins, 2 * math.pi * 1.6 * p, 0.55 * math.sin(math.pi * p))
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, '%s_turn%02d.png' % (NAME, k))
        bpy.ops.render.render(write_still=True)


main()

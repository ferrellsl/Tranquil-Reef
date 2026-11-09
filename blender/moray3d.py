"""Blender script: the moray as a 3D body made from its photo, head moving.

    blender -b --factory-startup -P moray3d.py -- <grid.json> <outdir> [frames] [samples]

The grid comes from photos/inflate.py (the moray cutout, head on the left in
the photo; mirrored here so it faces right, out of its cave).  The body base
(lower left, in the hole) stays put; the neck and head turn toward and away
from the viewer and nod, the turn growing along the body, so the head
foreshortens and the light moves across it like on the real animal.
"""
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import photo3d_mesh as PM  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:]
G = json.load(open(argv[0]))
OUTDIR = os.path.abspath(argv[1])
FRAMES = int(argv[2]) if len(argv) > 2 else 24
SAMPLES = int(argv[3]) if len(argv) > 3 else 64
WPX = 820


def main():
    common.reset_scene()
    ob, rest, fins = PM.build(G, mirror=False)   # (the build step mirrors the frames)
    ob.data.materials.append(PM.material(G['tex']))
    asp = G['aspect']
    # the body base sits at the lower left; the head is at the upper right
    base = np.array([0.92, 0.0, -0.45 * asp])
    pivot = np.array([0.60, 0.0, -0.05 * asp])
    d = rest - base
    reach = np.clip((-d[:, 0] * 0.8 + d[:, 2] * 0.6) / 0.9, 0, 1)
    w = reach ** 1.5                               # how much each point follows the head
    common.sprite_camera(center=(0.5, 0.0), ortho_width=1.15, res=(WPX, int(WPX * (asp * 1.15 + 0.1) / 1.15)))
    cam = bpy.context.scene.camera
    # a little from the front left, so turning toward the viewer shows
    target = Vector((0.5, 0.0, 0.0))
    dv = Vector((math.sin(math.radians(12)), -math.cos(math.radians(12)), math.sin(math.radians(5)))).normalized()
    cam.location = target + dv * 5.0
    cam.rotation_euler = (-dv).to_track_quat('-Z', 'Y').to_euler()
    common.underwater_lights()
    common.render_settings(SAMPLES, transparent=True)
    os.makedirs(OUTDIR, exist_ok=True)
    for f in range(FRAMES):
        ph = 2 * math.pi * f / FRAMES
        yaw = math.radians(20) * math.sin(ph)               # turning its head
        pitch = math.radians(6) * math.sin(2 * ph + 0.6)    # and nodding
        out = np.empty_like(rest)
        for i in range(len(rest)):
            a = w[i]
            m = Matrix.Rotation(yaw * a, 3, 'Z') @ Matrix.Rotation(pitch * a, 3, 'Y')
            p = Vector(rest[i] - pivot)
            out[i] = np.array(m @ p) + pivot
        ob.data.vertices.foreach_set('co', out.ravel())
        ob.data.update()
        bpy.context.scene.render.filepath = os.path.join(OUTDIR, 'moray_%02d.png' % f)
        bpy.ops.render.render(write_still=True)


main()

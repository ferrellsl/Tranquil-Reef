"""Turns a fish cutout (photos/cut/<key>.png, head on the left) into the data
Blender needs to build a 3D fish from it: a grid over the picture saying
where the fish is, how thick it is there, and how much of a fin it is.

Thickness: the silhouette blurred heavily is high in the middle of the body
and low on thin parts (fins, the tail), so the body comes out round and the
fins thin; it also falls to zero at the very edge.

    python photos/inflate.py yellowtang 0.30      (key, thickness factor)
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
CUT = os.path.join(HERE, 'cut')
OUT = os.path.join(HERE, '..', 'work', 'photo')


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def inflate(key, thick, cols=200, pad=0.02, src=None):
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(src or os.path.join(CUT, key + '.png')).convert('RGBA')
    # a little transparent margin all round, so the edge of the fish is inside the grid
    pw, ph = int(im.width * pad) + 2, int(im.height * pad) + 2
    canvas = Image.new('RGBA', (im.width + 2 * pw, im.height + 2 * ph), (0, 0, 0, 0))
    canvas.paste(im, (pw, ph))
    canvas.save(os.path.join(OUT, key + '_tex.png'))
    W = 1024
    H = max(8, int(round(W * canvas.height / canvas.width)))
    a = np.asarray(canvas.getchannel('A').resize((W, H), Image.BILINEAR), np.float32) / 255
    mask = a > 0.5
    # how much body is around each point: blur the silhouette
    B = ndimage.gaussian_filter(mask.astype(np.float32), sigma=0.055 * W)
    B /= max(B[mask].max(), 1e-6)
    d = ndimage.distance_transform_edt(mask) / W
    col_extent = mask.sum(axis=0).max() / W          # tallest column, in lengths
    T = thick * col_extent * 0.5
    z = T * smoothstep(0.42, 0.97, B) ** 0.9 * np.clip(d / 0.02, 0, 1) ** 0.5
    z = ndimage.gaussian_filter(z, sigma=2.0) * mask
    fin = 1 - smoothstep(0.40, 0.75, B)
    inside = ndimage.binary_dilation(mask, iterations=3)

    rows = max(8, int(round(cols * H / W)))
    gx = np.linspace(0, W - 1, cols).round().astype(int)
    gy = np.linspace(0, H - 1, rows).round().astype(int)
    sub = lambda arr: arr[np.ix_(gy, gx)]
    data = {
        'key': key, 'cols': cols, 'rows': rows, 'aspect': H / W,
        'inside': sub(inside).astype(np.uint8).ravel().tolist(),
        'z': [round(float(v), 5) for v in sub(z).ravel()],
        'fin': [round(float(v), 3) for v in sub(fin).ravel()],
        'tex': os.path.abspath(os.path.join(OUT, key + '_tex.png')),
    }
    with open(os.path.join(OUT, key + '.json'), 'w') as f:
        json.dump(data, f)
    return data


if __name__ == '__main__':
    inflate(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.35)

"""Exports each species for the Blender renderer: a color+alpha texture in
side view (u across, y up) and the shape as dense samples in JSON.

The texture holds the body pattern and, in the fin areas, the fin colors
with their rays in the alpha channel; Blender projects it onto the 3D body
and fin meshes from the side."""
import json
import math
import os
import numpy as np
from PIL import Image

from . import fish
from .fish import spline, C
from .noise import mix, smoothstep, fractal

U0, U1 = -0.03, 1.03


def extent(sp):
    tops = max(p[1] for p in sp.profile)
    bots = max(p[2] for p in sp.profile)
    up = tops + max([0] + [h for _, h in (sp.dorsal or [])])
    dn = bots + max([0] + [h for _, h in (sp.anal or [])])
    tail = sp.tail_spread * max(sp.tail_upper, sp.tail_lower)
    return max(up, dn, tail) + 0.03


def export(sp, outdir, tw=1536):
    Y = extent(sp)
    th = int(tw * 2 * Y / (U1 - U0))
    u = np.linspace(U0, U1, tw, dtype=np.float32)[None, :].repeat(th, 0)
    y = np.linspace(Y, -Y, th, dtype=np.float32)[:, None].repeat(tw, 1)

    pu = [p[0] for p in sp.profile]
    tops = [p[1] for p in sp.profile]
    bots = [p[2] for p in sp.profile]
    uc = np.clip(u, 0, pu[-1])
    top = np.maximum(spline(list(zip(pu, tops)), uc), 0)
    bot = np.maximum(spline(list(zip(pu, bots)), uc), 0)
    r = np.maximum((top + bot) / 2, 1e-4)
    c = (top - bot) / 2
    nv = np.clip((y - c) / r, -1, 1)

    col = sp.body_color(u, y, nv, top, bot).astype(np.float32)
    # natural unevenness: faint mottling so no area is one flat color
    mott = fractal(tw, th, hash(sp.name) % 1000, base=12, octaves=5)
    col = col * (1 + sp.mottle * mott)[..., None]
    alpha = np.ones(u.shape, np.float32)
    edge_col = C(sp.fin_edge()) if hasattr(sp, 'fin_edge') else None
    dark_tips = hasattr(sp, 'tip_dark') and sp.tip_dark()
    fins = np.zeros(u.shape, bool)

    # tail
    xp = sp.peduncle
    pc = float(spline(list(zip(pu, [(a - b) / 2 for a, b in zip(tops, bots)])), np.array([xp]))[0])
    ph = float(spline(list(zip(pu, [(a + b) / 2 for a, b in zip(tops, bots)])), np.array([xp]))[0])
    tlen = 1.0 - xp
    t = (u - (xp - 0.015)) / (tlen + 0.015)
    lobe = np.where(y > pc, sp.tail_upper, sp.tail_lower) * sp.tail_spread
    ry = np.abs(y - pc)
    spread = ph + (lobe - ph) * np.clip(t, 0, 1) ** 0.7
    # everything behind the peduncle is tail fin (forked meshes reach further than t says)
    tail = u > xp + 0.004
    ang = np.arctan2(y - pc, u - (xp - 0.03))
    rays = (0.5 + 0.5 * np.cos(ang * sp.rays_tail * 0.7)) ** 2 if sp.rays else np.full(u.shape, 0.8, np.float32)
    tc = sp.fin_color(u, y, 'tail') * (0.9 + 0.1 * rays)[..., None]
    rr = np.clip(ry / np.maximum(lobe, 1e-4), 0, 1)
    tedge = 1 - sp.tail_fork * (1 - rr) ** 1.3 if sp.tail_fork >= 0 else 1 - (-sp.tail_fork) * rr ** 2
    outer = np.clip(t / np.maximum(tedge, 1e-3), 0, 1.2)
    if edge_col is not None:
        near = smoothstep(0.86, 1.0, outer) + smoothstep(0.85, 1.0, ry / np.maximum(spread, 1e-3))
        tc = mix(tc, edge_col, np.clip(near, 0, 1) * 0.8)
    if dark_tips:
        tc = mix(tc, C('#26241f'), 0.85 * np.clip(smoothstep(0.62, 0.98, outer) * smoothstep(0.3, 0.85, rr) * (y < pc) +
                 smoothstep(0.70, 0.99, outer) * (y > pc) * smoothstep(0.45, 0.95, rr), 0, 1))
    ta = sp.fin_alpha * (0.70 + 0.30 * rays) * (1 - 0.30 * np.clip(t, 0, 1))
    if not sp.rays:
        ta = np.full(u.shape, 0.97, np.float32)
    col = np.where(tail[..., None], tc, col)
    alpha = np.where(tail, ta, alpha)
    fins |= tail

    for which, pts, sign in (('dorsal', sp.dorsal, 1), ('dorsal', sp.dorsal2, 1), ('anal', sp.anal, -1)):
        if not pts:
            continue
        lo, hi = pts[0][0], pts[-1][0]
        fh = spline(pts, np.clip(u, lo, hi))
        base_edge = top if sign > 0 else -bot
        d = (y - base_edge) * sign
        inside = (u >= lo - 0.01) & (u <= hi + 0.01) & (d >= -0.003) & (d <= fh * 1.1 + 0.004)
        s = u + d * 0.8
        frays = (0.5 + 0.5 * np.cos(s * 150)) ** 2 if sp.rays else np.full(u.shape, 0.9, np.float32)
        fc = sp.fin_color(u, y, which) * (0.92 + 0.10 * frays)[..., None]
        q = d / np.maximum(fh, 1e-3)
        if edge_col is not None:
            fc = mix(fc, edge_col, smoothstep(0.72, 1.0, q) * 0.85)
        if dark_tips:
            fc = mix(fc, C('#26241f'), 0.85 * smoothstep(0.50, 0.97, q))
        fa = sp.fin_alpha * (0.80 + 0.20 * frays) * (1 - 0.3 * np.clip(q, 0, 1))
        if not sp.rays:
            fa = np.full(u.shape, 0.98, np.float32)
        col = np.where(inside[..., None], fc, col)
        alpha = np.where(inside, fa, alpha)
        fins |= inside

    img = np.concatenate([np.clip(col, 0, 1), np.clip(alpha, 0, 1)[..., None]], axis=2)
    Image.fromarray((img * 255 + 0.5).astype(np.uint8), 'RGBA').save(os.path.join(outdir, sp.name + '_tex.png'))

    # shape samples for the meshes
    us = np.linspace(0, pu[-1], 90)
    dense = lambda pts, xs: [float(v) for v in spline(pts, np.asarray(xs, np.float32))]
    fins_out = []
    for which, pts, sign in (('dorsal', sp.dorsal, 1), ('dorsal2', sp.dorsal2, 1), ('anal', sp.anal, -1)):
        if pts:
            xs = np.linspace(pts[0][0], pts[-1][0], 24)
            fins_out.append({'name': which, 'sign': sign, 'u': [float(v) for v in xs], 'h': dense(pts, xs)})
    pcol = sp.fin_color(np.zeros((1, 1)), np.zeros((1, 1)), 'pectoral').reshape(-1, 3)[0]
    data = {
        'name': sp.name, 'width': sp.width, 'height': sp.height, 'pad': sp.pad,
        'thick': sp.thick, 'u': [float(v) for v in us],
        'top': dense(list(zip(pu, tops)), us), 'bot': dense(list(zip(pu, bots)), us),
        'peduncle': xp, 'pc': pc, 'ph': ph, 'tail_spread': sp.tail_spread,
        'tail_upper': sp.tail_upper, 'tail_lower_len': sp.tail_lower_len, 'tail_lower': sp.tail_lower, 'tail_fork': sp.tail_fork,
        'fins': fins_out,
        'pectoral': list(sp.pectoral), 'pectoral_angle': sp.pectoral_angle,
        'pectoral_tri': sp.pectoral_tri, 'pectoral_color': [float(v) for v in pcol],
        'pectoral_alpha': 0.95 if sp.pectoral_tri else 0.28, 'dark_tips': dark_tips,
        'eye': list(sp.eye), 'skin': sp.skin, 'iris': [float(v) for v in C(sp.iris)],
        'tex_u0': U0, 'tex_u1': U1, 'tex_y': Y, 'rays': sp.rays,
    }
    with open(os.path.join(outdir, sp.name + '.json'), 'w') as f:
        json.dump(data, f)
    return data


def export_all(outdir):
    os.makedirs(outdir, exist_ok=True)
    return [export(sp, outdir) for sp in fish.ALL]

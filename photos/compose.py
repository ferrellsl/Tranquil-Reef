"""Lays the photo corals onto the rendered rock wall and paints the open water.

    python photos/compose.py [seed]

Reads work/tankscene/scene_beauty.png and scene_mask.png (from tank3d.py
--bare) and photos/coralcut/*.png; writes
    work/tankscene/composed_beauty.png   the reef with its corals, water gradient
    work/tankscene/composed_mask.png     the mask with the corals added to R (the reef)
    work/tankscene/sway_<key>.png + sway.json   the corals that sway (drawn by the channel)

Each coral is colour-corrected (the photo's green-blue underwater cast taken
out, brightness evened, colours kept natural), lit from above with a darker
base, given a soft contact shadow, and stood on the top edge of the reef or
on a rock face.
"""
import json
import os
import random
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SCENE = os.path.join(HERE, '..', 'work', 'tankscene')
CUT = os.path.join(HERE, 'coralcut')
CAVE = os.path.join(HERE, '..', 'work', 'moraycave')
MOUTH_X = None
CAVE_SCALE = 0.40          # the cave photo patch, at this size on the tank

# how tall each kind stands, in pixels of the 1080-high tank
HEIGHT = {'brain': (95, 150), 'elkhorn': (170, 250), 'fan': (260, 320), 'bubble': (95, 130), 'pillar': (200, 270),
          'finger': (110, 170), 'sponge': (150, 240), 'plate': (110, 150), 'staghorn': (150, 210), 'anemone': (120, 150)}
SWAY = ('fan', 'anemone')         # soft: they bend with the water (the channel sways them)


def smooth(a, n):
    k = np.ones(n) / n
    return np.convolve(np.pad(a, n // 2, mode='edge'), k, mode='valid')[:len(a)]


def correct(im):
    """Underwater photo -> as if under the tank's white light, colours natural."""
    a = np.asarray(im, np.float32) / 255
    rgb, al = a[..., :3], a[..., 3]
    al = np.clip((al - 0.30) / 0.70, 0, 1)          # drop the faint haze of old background a cut-out keeps
    m = al > 0.5
    if m.sum() < 50:
        return im
    px = rgb[m]
    # take out the colour cast: scale channels so the coral's mid tones come out neutral-ish,
    # but only part of the way (corals are not grey)
    mean = px.mean(axis=0)
    gain = (mean.mean() / np.maximum(mean, 1e-3)) ** 0.75
    rgb = rgb * gain
    # even out brightness: median luminance to about 0.42
    lum = (rgb[m] * [0.3, 0.59, 0.11]).sum(axis=1)
    rgb = rgb * (0.42 / max(np.median(lum), 1e-3))
    # gentle contrast, no saturation boost
    rgb = np.clip((rgb - 0.5) * 1.08 + 0.5, 0, 1)
    return Image.fromarray((np.concatenate([rgb, al[..., None]], axis=2) * 255).astype(np.uint8), 'RGBA')


def light(im, base_dark=0.45):
    """Lit from above: the top a little brighter, the base in shadow."""
    a = np.asarray(im, np.float32) / 255
    h = a.shape[0]
    y = np.linspace(0, 1, h)[:, None]
    shade = 1.10 - (1.10 - base_dark) * y ** 1.6
    a[..., :3] = np.clip(a[..., :3] * shade[..., None], 0, 1)
    # trim the fringe a cut-out leaves (a pixel of old background)
    al = Image.fromarray((a[..., 3] * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))
    a[..., 3] = np.asarray(al, np.float32) / 255
    return Image.fromarray((a * 255).astype(np.uint8), 'RGBA')


def shadow(canvas, im, x, y, strength=0.55):
    """A soft dark shadow just below and behind a coral, on whatever is there."""
    al = im.getchannel('A').point(lambda v: 255 if v > 128 else 0).filter(ImageFilter.GaussianBlur(9))
    sh = Image.new('RGBA', im.size, (0, 0, 0, 0))
    sh.putalpha(al.point(lambda v: int(v * strength)))
    canvas.alpha_composite(sh, (int(x + 6), int(y + 10)))


def main(seed=3, corals=True):
    r = random.Random(seed)
    global MOUTH_X
    try:
        MOUTH_X = json.load(open(os.path.join(SCENE, 'scene.json')))['cave_mouth'][0]
    except Exception:
        MOUTH_X = None
    beauty = Image.open(os.path.join(SCENE, 'scene_beauty.png')).convert('RGBA')
    mask = Image.open(os.path.join(SCENE, 'scene_mask.png')).convert('RGB')
    W, H = beauty.size
    m = np.asarray(mask, np.float32) / 255
    reef = np.maximum(m[..., 0], m[..., 1])
    solid = np.maximum(reef, m[..., 2])
    # the reef's top edge in each column
    top = np.array([np.argmax(reef[:, x] > 0.5) if (reef[:, x] > 0.5).any() else H for x in range(W)], np.float32)
    top_raw = top.copy()
    top = smooth(top, 31)

    # ---- open water: deep navy, almost black overhead, blue near the reef
    yy = np.linspace(0, 1, H)[:, None, None]
    reef_line = np.median(top) / H
    t = np.clip(yy / max(reef_line, 0.3), 0, 1.3)
    # lighter near the surface at the top, darker the deeper it goes toward the reef
    surf, mid, deep = np.array([0.10, 0.38, 0.62]), np.array([0.040, 0.165, 0.360]), np.array([0.012, 0.050, 0.140])
    # one smooth curve through the three colors (straight segments left visible bands at the joins)
    from scipy.interpolate import PchipInterpolator
    knots = [0.0, 0.6, 1.0, 1.3]
    cols = np.stack([surf, mid, deep, deep + (deep * 0.5 - deep)])
    curve = PchipInterpolator(knots, cols, axis=0)
    tt = np.clip(t, 0, 1.3)[..., 0]
    grad = curve(tt)
    grad = np.broadcast_to(grad, (H, W, 3))
    b = np.asarray(beauty, np.float32)[..., :3] / 255
    water = (1 - solid)[..., None]
    b = grad * water + b * (1 - water)
    # the bare rock: more contrast and a little more colour, so it does not look hazy next to the photos
    rk = reef[..., None]
    lumr = (b * [0.3, 0.59, 0.11]).sum(axis=2, keepdims=True)
    rock = np.clip((b - 0.5) * 1.30 + 0.5 - 0.05, 0, 1)
    rock = np.clip(lumr + (rock - lumr) * 1.20, 0, 1)
    if corals:
        b = rock * rk + b * (1 - rk)
    # a little dither in the water, so the dark gradient does not band in 8 bits
    b = b + water * (np.random.default_rng(5).random(b.shape) - 0.5) * (1.6 / 255)
    canvas = Image.fromarray((np.clip(b, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB').convert('RGBA')
    reef_alpha = Image.fromarray((reef * 255).astype(np.uint8), 'L')

    # the moray's cave (photos/moray_cave.py): low on the reef, left of center
    cave = None
    if corals and os.path.exists(os.path.join(CAVE, 'back.png')):
        back = Image.open(os.path.join(CAVE, 'back.png'))
        back = back.resize((int(back.width * CAVE_SCALE), int(back.height * CAVE_SCALE)), Image.LANCZOS)
        frows = np.where(m[..., 2].max(axis=1) > 0.5)[0]
        floor_y = float(np.median([np.argmax(m[:, x, 2] > 0.5) for x in range(0, W, 16) if (m[:, x, 2] > 0.5).any()])) if len(frows) else H * 0.86
        cy = int(floor_y - back.height * (0.95 if corals else 0.80))
        # a stretch of rock face with nothing standing in front of it (G: things on the gravel)
        best, cx = None, int(W * 0.24)
        for c in range(int(W * 0.10), int(W * 0.60), 16):
            x0_, x1_ = max(0, c - back.width // 2), min(W, c + back.width // 2)
            cover = m[cy:cy + back.height, x0_:x1_, 1].mean() + 0.0004 * abs(c - W * 0.24) / 16
            if best is None or cover < best:
                best, cx = cover, c
        cave = {'x': cx - back.width // 2, 'y': cy, 'w': back.width, 'h': back.height, 'scale': CAVE_SCALE}
        canvas.alpha_composite(back, (cave['x'], cave['y']))
        reef_alpha.paste(255, (cave['x'], cave['y']), back.getchannel('A'))

    if not corals:
        # the reef was rendered with its corals: only the clam's place and shadow are left to do
        return finish_plain(canvas, mask, reef_alpha, cave, W, H, m, r)
    kinds = json.load(open(os.path.join(CUT, 'kinds.json')))
    cuts = {k: Image.open(os.path.join(CUT, k + '.png')).convert('RGBA') for k in kinds if os.path.exists(os.path.join(CUT, k + '.png'))}
    if not cuts:
        raise SystemExit('no coral cut-outs in ' + CUT)
    kind_of = lambda k: ''.join(c for c in k if not c.isdigit())

    # ---- where things go: tall pieces spread along the top, then the rest filling in, then faces
    plan = []
    talls = [k for k in cuts if kinds[k] == 'tall']
    tops = [k for k in cuts if kinds[k] == 'top']
    talls = [k for k in talls if kinds[k] != 'floor']
    faces = [k for k in cuts if kinds[k] == 'face']
    xs_tall = np.linspace(0.04, 0.96, max(1, len(talls))) * W
    r.shuffle(talls)
    for k, x in zip(talls, xs_tall):
        plan.append((k, x + r.uniform(-60, 60), 'tall'))
    for k in talls:                                      # and each tall one again somewhere else
        plan.append((k, r.uniform(0.03, 0.97) * W, 'tall'))
    for k in tops:                                       # top corals: brain domes twice, the rest three times
        for i in range(3 if kind_of(k) == 'brain' else 4):
            plan.append((k, r.uniform(0.02, 0.98) * W, 'top'))
    facers = faces + [k for k in tops if kind_of(k) in ('finger', 'bubble', 'anemone')] + talls
    brains = [k for k in tops if kind_of(k) == 'brain']
    for i in range(40):                                  # and corals down the rock faces, few of them domes
        pool = brains if (brains and r.random() < 0.25) else facers
        plan.append((r.choice(pool), r.uniform(0.03, 0.97) * W, 'face'))

    sway = []
    placed = []
    clam = None
    # far (higher on the reef) first, nearer (lower) last
    order = []
    for k, x, where in plan:
        lo, hi = HEIGHT.get(kind_of(k), (110, 160))
        h = r.uniform(lo, hi) * (0.8 if where == 'top' and r.random() < 0.5 else 1.0)
        im = cuts[k]
        if r.random() < 0.5 and kind_of(k) not in ('fan',):
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        im = im.resize((max(8, int(im.width * h / im.height)), int(h)), Image.LANCZOS)
        x0_, x1_ = int(np.clip(x - im.width * 0.3, 0, W - 1)), int(np.clip(x + im.width * 0.3, 1, W))
        ground = float(top_raw[x0_:x1_].min())          # stands on the highest rock under it
        if where == 'face':
            h *= r.uniform(0.55, 0.85)
            y = ground + r.uniform(0.25, 0.75) * (H * 0.86 - ground)     # somewhere down the face
            sink = 0.30 * h
        elif where == 'top':
            y = ground + r.uniform(-0.05, 0.35) * (H * 0.86 - ground)    # on the top or a ledge below it
            sink = 0.22 * h
        else:
            y = ground
            sink = 0.20 * h
        order.append((y, k, im, x - im.width / 2, y - h + sink, where))
    order.sort(key=lambda o: o[0])
    used = {}                      # where each photo already went: copies must be far apart
    MIN_GAP = 650
    for y, k, im, px, py, where in order:
        cxp = px + im.width / 2
        if any(abs(cxp - u) < MIN_GAP for u in used.get(k, [])):
            continue
        used.setdefault(k, []).append(cxp)
        if len(used[k]) > 1:
            # a repeat: shift its tone a little so it is not an exact copy
            arr = np.asarray(im, np.float32)
            arr[..., :3] *= np.array([r.uniform(0.88, 1.08), r.uniform(0.88, 1.06), r.uniform(0.88, 1.05)]) * r.uniform(0.85, 1.05)
            im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGBA')
        if cave and where != 'tall' and cave['x'] < px + im.width / 2 < cave['x'] + cave['w'] \
                and cave['y'] < py + im.height / 2 < cave['y'] + cave['h']:
            continue
        im = light(correct(im))
        if kind_of(k) in SWAY:
            name = 'sway_%s_%d.png' % (k, len(sway))
            im.save(os.path.join(SCENE, name))
            shadow(canvas, im, px, py, 0.35)
            sway.append({'file': name, 'x': int(px), 'y': int(py), 'w': im.width, 'h': im.height})
            # a swaying coral still belongs to the reef layer (fish pass behind it)
            reef_alpha.paste(255, (int(px), int(py)), im.getchannel('A'))
            continue
        shadow(canvas, im, px, py)
        canvas.alpha_composite(im, (int(px), int(py)))
        reef_alpha.paste(255, (int(px), int(py)), im.getchannel('A'))
        placed.append(k)

    # on the gravel: small corals along the foot of the reef, shells out on the floor
    floor_rows = np.where(m[..., 2].max(axis=1) > 0.5)[0]
    ftop = int(floor_rows.min()) if len(floor_rows) else int(H * 0.86)
    fbot = H - 60                                         # the glass band starts below this
    small = [k for k in cuts if kind_of(k) in ('brain', 'finger', 'bubble', 'sponge', 'anemone')]
    shells = [k for k in cuts if kinds.get(k) == 'floor']
    items = []
    for i in range(12):
        items.append((r.choice(small), r.uniform(0.02, 0.98) * W, ftop + r.uniform(4, 16), r.uniform(45, 85)))
    # the giant clam (blender/clam3d.py, drawn by the channel): a soft shadow under where it sits
    clam = {'cx': int(W * 0.56), 'base': int(ftop + 0.55 * (fbot - ftop)), 'w': 250}
    sh = Image.new('L', (clam['w'] + 60, 60), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(sh).ellipse((20, 18, clam['w'] + 40, 50), fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    sl = Image.new('RGBA', sh.size, (0, 0, 0, 0))
    sl.putalpha(sh)
    canvas.alpha_composite(sl, (clam['cx'] - sh.width // 2, clam['base'] - 34))
    items.sort(key=lambda t: t[2])
    for k, x, y, size in items:
        im = cuts[k]
        if r.random() < 0.5:
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        sc = size / max(im.width, im.height)
        im = im.resize((max(6, int(im.width * sc)), max(6, int(im.height * sc))), Image.LANCZOS)
        if kinds.get(k) == 'floor':
            im = im.rotate(r.uniform(-18, 18), resample=Image.BICUBIC, expand=True)
        # (shells stay as bright as they are: the colour correction would turn them grey)
        im = light(im if kinds.get(k) == 'floor' else correct(im), base_dark=0.7)
        px, py = int(x - im.width / 2), int(y - im.height * 0.85)
        # a soft shadow on the gravel just below it
        sh = im.getchannel('A').point(lambda v: 255 if v > 128 else 0).resize((im.width, max(2, im.height // 3)))
        sh = sh.filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.5))
        sl = Image.new('RGBA', sh.size, (0, 0, 0, 0))
        sl.putalpha(sh)
        canvas.alpha_composite(sl, (px + 3, int(py + im.height * 0.78)))
        canvas.alpha_composite(im, (px, py))
        reef_alpha.paste(255, (px, py), im.getchannel('A').point(lambda v: 255 if v > 100 else 0))

    canvas.convert('RGB').save(os.path.join(SCENE, 'composed_beauty.png'))
    out = np.asarray(mask).copy()
    out[..., 0] = np.maximum(out[..., 0], np.asarray(reef_alpha))
    Image.fromarray(out, 'RGB').save(os.path.join(SCENE, 'composed_mask.png'))
    json.dump(sway, open(os.path.join(SCENE, 'sway.json'), 'w'), indent=1)
    json.dump(cave, open(os.path.join(SCENE, 'cave.json'), 'w'), indent=1)
    json.dump(clam, open(os.path.join(SCENE, 'clam.json'), 'w'), indent=1)
    print('placed %d corals, %d swaying' % (len(placed), len(sway)))


def finish_plain(canvas, mask, reef_alpha, cave, W, H, m, r):
    from PIL import ImageDraw
    floor_rows = np.where(m[..., 2].max(axis=1) > 0.5)[0]
    ftop = int(floor_rows.min()) if len(floor_rows) else int(H * 0.86)
    # the top of the gravel's glass face: the first row the front layer covers across (nearly) the whole width
    face_rows = np.where(m[..., 1].mean(axis=1) > 0.8)[0]
    fbot = int(face_rows.min()) if len(face_rows) else H - 60
    # the visible floor line (the median, not its farthest-back point) and a clear spot on the gravel
    ftop = int(np.median([np.argmax(m[:, x, 2] > 0.5) for x in range(0, W, 16) if (m[:, x, 2] > 0.5).any()]))
    base = int(ftop + 0.50 * (fbot - ftop))
    best, cx = None, int(W * 0.58)
    for c in range(int(W * 0.35), int(W * 0.90), 16):
        if cave and abs(c - (cave['x'] + cave['w'] / 2)) < cave['w']:
            continue
        if MOUTH_X is not None and abs(c - MOUTH_X) < 380:
            continue
        cover = m[base - 120:base, max(0, c - 140):min(W, c + 140), 1].mean() + 0.0003 * abs(c - W * 0.58) / 16
        if best is None or cover < best:
            best, cx = cover, c
    clam = {'cx': int(cx), 'base': base, 'w': 270}
    sh = Image.new('L', (clam['w'] + 60, 60), 0)
    ImageDraw.Draw(sh).ellipse((20, 18, clam['w'] + 40, 50), fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(10))
    sl = Image.new('RGBA', sh.size, (0, 0, 0, 0))
    sl.putalpha(sh)
    canvas.convert('RGB').save(os.path.join(SCENE, 'composed_beauty.png'))
    out = np.asarray(mask).copy()
    out[..., 0] = np.maximum(out[..., 0], np.asarray(reef_alpha))
    Image.fromarray(out, 'RGB').save(os.path.join(SCENE, 'composed_mask.png'))
    json.dump([], open(os.path.join(SCENE, 'sway.json'), 'w'))
    json.dump(cave, open(os.path.join(SCENE, 'cave.json'), 'w'), indent=1)
    cj = os.path.join(SCENE, 'clam.json')
    prior = (json.load(open(cj)) or {}) if os.path.exists(cj) else {}
    if not (prior.get('crop') or prior.get('static')):     # (a clam rendered in the scene wins)
        json.dump(clam, open(cj, 'w'), indent=1)
    print('water, cave and clam shadow done (corals are in the render)')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    main(int(args[0]) if args else 3, corals='--no-corals' not in sys.argv)

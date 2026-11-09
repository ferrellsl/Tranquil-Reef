"""Builds the Tranquil Reef Roku screensaver from the Blender renders.

    sh render_all.sh        (once, or after changing a model: renders work/)
    python build.py         channel/ + out/TranquilReef.zip + out/preview.png

All art comes from code (art/, blender/) plus CC0 surface textures that
fetch_textures.py downloads from Poly Haven.
"""
import json
import math
import os
import random
import re
import shutil
import sys
import zipfile

from PIL import Image, ImageChops

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from art import scene  # noqa: E402  (light rays and the bubble)

WORK = os.path.join(ROOT, 'work')
FRAMES = os.path.join(WORK, 'frames')
CHANNEL = os.path.join(ROOT, 'channel')
IMAGES = os.path.join(CHANNEL, 'images')
OUT = os.path.join(ROOT, 'out')
TEMPLATE = os.path.join(ROOT, 'template')
# the head-on tank (tank3d.py --bare + photos/compose.py) if it has been made, else the older seabed scene
SCENE = os.path.join(WORK, 'tankscene') if os.path.exists(os.path.join(WORK, 'tankscene', 'scene.json')) else os.path.join(WORK, 'scene')

# count, role, display size (1 = as rendered), largest on-screen scale,
# speed (px/s at full size), swim-cycle frames per second
SPECIES = {
    'yellowtang': dict(count=2, role='fish', size=0.55, maxs=1.0, speed=80, fps=11),
    'bluetang':   dict(count=2, role='fish', size=0.55, maxs=1.0, speed=85, fps=12),
    'clown':      dict(count=2, role='fish', size=0.55, maxs=1.0, speed=65, fps=14),
    'angel':      dict(count=1, role='fish', visitor=True, size=0.60, maxs=1.0, speed=55, fps=9),
    'butterfly':  dict(count=1, role='fish', visitor=True, size=0.55, maxs=1.0, speed=65, fps=11),
    'queenangel': dict(count=1, role='fish', visitor=True, size=0.60, maxs=1.0, speed=55, fps=9),
    'chromis':    dict(count=5, role='school', size=0.60, maxs=1.0, speed=110, fps=16),
    'wrasse':     dict(count=2, role='fish', size=0.60, maxs=1.0, speed=95, fps=13),
    'lionfish':   dict(count=1, role='fish', visitor=True, size=0.60, maxs=0.72, speed=35, fps=7),     # from a 3D model (model3d.py)
    'parrotfish': dict(count=1, role='fish', visitor=True, size=0.60, maxs=0.85, speed=60, fps=8),   # 3D model (model3d.py)
    'darkangel':  dict(count=1, role='fish', visitor=True, size=0.60, maxs=0.85, speed=50, fps=9),    # 3D model (model3d.py)
    'copperband': dict(count=1, role='fish', visitor=True, size=0.55, maxs=1.0, speed=60, fps=11),                  # 3D model (model3d.py)
    'puffer':     dict(count=1, role='fish', visitor=True, size=0.55, maxs=1.0, speed=40, fps=10),    # 3D model (model3d.py)
    'barracuda':  dict(count=0, role='cruiser', size=0.80, maxs=0.60, speed=120, fps=8),
    'shark':      dict(count=0, role='cruiser', size=0.80, maxs=0.60, speed=95, fps=6),
}
TURN_TIME = 1.6
EEL_SPRITE_PX_PER_M = 1190              # moray3d.py: 820 px across 1.15 units; the goldentail is about 0.6 m of eel
EEL_FLIP = True                         # moray3d renders it facing left; it faces out of the cave to the right


def save(im, name, quality=None):
    path = os.path.join(IMAGES, name)
    if quality:
        im.convert('RGB').save(path, quality=quality, optimize=True)
    else:
        im.save(path, optimize=True)
    return 'pkg:/images/' + name


def bbox_union(paths, pad=4):
    box = None
    for p in paths:
        b = Image.open(p).getchannel('A').point(lambda v: 255 if v > 3 else 0).getbbox()
        if b is None:
            continue
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    w, h = Image.open(paths[0]).size
    return (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))


def save_tiles(im, name, x0=0, y0=0, quality=None):
    """An image wider than a texture may be -> side-by-side tiles."""
    tiles = []
    n = -(-im.width // MAX_TEX)
    tw = -(-im.width // n)
    for i in range(n):
        part = im.crop((i * tw, 0, min(im.width, (i + 1) * tw), im.height))
        ext = '.jpg' if quality else '.png'
        uri = save(part, '%s_%d%s' % (name, i, ext), quality=quality)
        tiles.append({'uri': uri, 'x': x0 + i * tw, 'y': y0, 'w': part.width, 'h': part.height})
    return tiles


def layer_from_mask(beauty, mask, channel, name):
    """Cut one reef layer out of the beauty render; crop to what it covers."""
    a = mask.getchannel(channel)
    box = a.point(lambda v: 255 if v > 8 else 0).getbbox()
    im = beauty.convert('RGBA')
    im.putalpha(a)
    if not box:
        return []
    im = im.crop(box)
    return save_tiles(im, name.replace('.png', ''), box[0], box[1])


GRADE = None
HAZE_FREE = True       # scanreef.py renders without the water volume (HAZE = False)
MAX_TEX = 2040     # keep every texture within 2048 px, which all Rokus take


GUTTER = 24        # empty pixels between sheet frames, so a tilted window never shows a neighbor


def sheet(frames, name, gutter=GUTTER):
    """Frames (same size) -> one sprite sheet image; returns (uri, cols, rows).
    Frame k sits at ((k % cols) * (fw + gutter), (k // cols) * (fh + gutter))."""
    fw, fh = frames[0].size
    pw, ph = fw + gutter, fh + gutter
    cols = max(1, min(len(frames), MAX_TEX // pw))
    rows = -(-len(frames) // cols)
    while rows * ph > MAX_TEX and cols < len(frames):
        cols += 1
        rows = -(-len(frames) // cols)
    if cols * pw > MAX_TEX + gutter or rows * ph > MAX_TEX + gutter:
        raise SystemExit('%s: %d frames of %dx%d do not fit in one texture' % (name, len(frames), fw, fh))
    im = Image.new('RGBA', (cols * pw, rows * ph), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        im.paste(f, ((i % cols) * pw, (i // cols) * ph))
    return save(im, name), cols, rows


def lit_frames(fdir, x, y):
    """The sprite's frames: shape (alpha) from the held-out pass, color from the same frame lit in
    the full scene (<fdir>_rgb, water haze and all), graded like the picture around it."""
    import numpy as np
    names = sorted(f for f in os.listdir(fdir) if f.endswith('.png'))
    frames = [Image.open(os.path.join(fdir, f)).convert('RGBA') for f in names]
    rdir = fdir + '_rgb'
    if not os.path.isdir(rdir):
        return frames
    out = []
    for f, n in zip(frames, names):
        rgb = np.asarray(Image.open(os.path.join(rdir, n)).convert('RGB'), np.float32)
        if GRADE is not None:
            g = GRADE[y:y + rgb.shape[0], x:x + rgb.shape[1]]
            rgb = rgb * g[:g.shape[0], :g.shape[1]] if g.shape[:2] == rgb.shape[:2] else rgb
        a = np.asarray(f.getchannel('A'))[..., None]
        out.append(Image.fromarray(np.concatenate([np.clip(rgb, 0, 255).astype(np.uint8), a], axis=2), 'RGBA'))
    return out


def changing_part(frames, x, y, pad=4):
    """Crop frames to where they differ from the last one (the closed clam, which is in the background)."""
    import numpy as np
    last = np.asarray(frames[-1], np.int16)
    diff = np.zeros(last.shape[:2], bool)
    for f in frames[:-1]:
        diff |= np.abs(np.asarray(f, np.int16) - last).max(axis=2) > 6
    ys, xs = np.where(diff)
    if not len(xs):
        return frames, x, y
    b = (int(max(0, xs.min() - pad)), int(max(0, ys.min() - pad)), int(min(last.shape[1], xs.max() + pad + 1)), int(min(last.shape[0], ys.max() + pad + 1)))
    return [f.crop(b) for f in frames], x + b[0], y + b[1]


def fit_sheet(frames, name, x, y):
    """In-scene sprite frames (rendered at their place in the picture): trim the empty margin
    they all share, shrink them a little if they still do not fit one texture (the channel
    scales them back up).  Returns sheet info with the frames' place on screen."""
    box = None
    for f in frames:
        b = f.getchannel('A').point(lambda v: 255 if v > 3 else 0).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box:
        frames = [f.crop(box) for f in frames]
        x, y = x + box[0], y + box[1]
    fw, fh = frames[0].size
    k = 1.0
    while True:
        tw, th = int(fw * k), int(fh * k)
        cols = max(1, MAX_TEX // (tw + GUTTER))
        if cols * (MAX_TEX // (th + GUTTER)) >= len(frames):
            break
        k *= 0.94
    small = frames if k == 1.0 else [f.resize((tw, th), Image.LANCZOS) for f in frames]
    print('  %s: %d frames %dx%d at %.2f' % (name, len(frames), fw, fh, k))
    uri, cols, rows = sheet(small, name)
    info = sheet_info(uri, cols, rows, tw, th, fw, fh)
    info.update({'frames': len(frames), 'x': x, 'y': y})
    return info


def sheet_info(uri, cols, rows, tw, th, dw, dh, gutter=GUTTER):
    """What the channel needs to show frame k at display size dw x dh."""
    kx, ky = dw / tw, dh / th
    return {'sheet': uri, 'cols': cols, 'w': dw, 'h': dh,
            'pitchX': (tw + gutter) * kx, 'pitchY': (th + gutter) * ky,
            'sheetW': cols * (tw + gutter) * kx, 'sheetH': rows * (th + gutter) * ky}


def build_species():
    """Each species becomes one sheet: 12 swim frames facing left, the same
    12 mirrored (facing right), then the turn from left to right.  Changing
    a Poster's picture every frame made the Roku reload it (the fish
    flashed), and a negative scale turned fish upside down; a sheet slid
    behind a clipping window avoids both."""
    out = []
    for name, cfg in SPECIES.items():
        if cfg['count'] == 0:          # left out (kept in the table so it is easy to bring back)
            continue
        swim = sorted(f for f in os.listdir(FRAMES) if f.startswith(name + '_') and 'turn' not in f)
        turn = sorted(f for f in os.listdir(FRAMES) if f.startswith(name + '_turn'))
        if not swim:
            print('  (no frames for %s, left out)' % name)
            continue
        paths = [os.path.join(FRAMES, f) for f in swim + turn]
        box = bbox_union(paths)
        w0, h0 = box[2] - box[0], box[3] - box[1]
        dw, dh = int(round(w0 * cfg['size'])), int(round(h0 * cfg['size']))
        tw, th = max(8, int(round(dw * cfg['maxs']))), max(8, int(round(dh * cfg['maxs'])))
        load = lambda f: Image.open(os.path.join(FRAMES, f)).crop(box).resize((tw, th), Image.LANCZOS)
        sw = [load(f) for f in swim]
        frames = sw + [f.transpose(Image.FLIP_LEFT_RIGHT) for f in sw] + [load(f) for f in turn]
        uri, cols, rows = sheet(frames, name + '.png')
        info = sheet_info(uri, cols, rows, tw, th, dw, dh)
        info.update({'name': name, 'frames': len(swim), 'turnFrames': len(turn),
                    'count': cfg['count'], 'role': cfg['role'], 'speed': cfg['speed'] * cfg['size'],
                    'fps': cfg['fps'], 'turnTime': TURN_TIME, 'visitor': cfg.get('visitor', False)})
        out.append(info)
        print('  %-10s %d+%d frames, %dx%d on screen, sheet %dx%d' % (name, len(swim), len(turn), dw, dh, cols * (tw + GUTTER), rows * (th + GUTTER)))
    return out


def build_clam():
    """The giant clam: frames from open (0) to closed (last), on the gravel where compose.py put its shadow."""
    cj = os.path.join(SCENE, 'clam.json')
    cdir = os.path.join(WORK, 'clam')
    if not (os.path.exists(cj) and os.path.isdir(cdir)):
        return None
    place = json.load(open(cj))
    if not place or place.get('static'):       # (static: it is in the picture itself)
        return None
    if place.get('crop'):
        # rendered inside the reef scene (reefclam.py): the frames fit the picture as they are
        fdir = os.path.join(SCENE, 'clamframes')
        frames, cx, cy = lit_frames(fdir, place['x'], place['y']), place['x'], place['y']
        if place.get('in_background'):
            frames, cx, cy = changing_part(frames, cx, cy)
        return fit_sheet(frames, 'clam.png', cx, cy)
    paths = [os.path.join(cdir, f) for f in sorted(os.listdir(cdir)) if f.endswith('.png')]
    box = bbox_union(paths, pad=2)
    dw = place['w']
    dh = int(round(dw * (box[3] - box[1]) / (box[2] - box[0])))
    frames = [Image.open(p).crop(box).resize((dw, dh), Image.LANCZOS) for p in paths]
    uri, cols, rows = sheet(frames, 'clam.png')
    info = sheet_info(uri, cols, rows, dw, dh, dw, dh)
    info.update({'frames': len(frames), 'x': place['cx'] - dw / 2, 'y': place['base'] - dh * 0.92})
    return info


def build_eel(info):
    """The moray (moray3d.py frames) in its cave (photos/moray_cave.py, laid
    into the reef by compose.py).  The frames are fitted onto where the eel
    lay in the cave photo; the photo's own rock in front of it and the dark of
    the hole go on top (eelFront), so as it backs in it disappears into the hole."""
    ej = os.path.join(SCENE, 'eel.json')
    if os.path.exists(ej):
        # rendered inside the reef scene (scanreef.py --moray): the rock hides it where it should;
        # frames: `loop` out of the hole turning its head, then `slide` backing into the hole
        e = json.load(open(ej))
        fdir = os.path.join(SCENE, 'eelframes')
        sinfo = fit_sheet(lit_frames(fdir, e['x'], e['y']), 'moray.png', e['x'], e['y'])
        blank = Image.new('RGBA', (4, 4), (0, 0, 0, 0))
        sinfo.update({'crop': True, 'loop': e['loop'], 'slide': e['slide'], 'fps': 12, 'outMax': 0, 'clipX': 0, 'clipBottom': 1080,
                      'front': {'uri': save(blank, 'hole_front.png'), 'x': 0, 'y': 0, 'w': 4, 'h': 4}})
        return sinfo
    cj = os.path.join(SCENE, 'cave.json')
    meta_p = os.path.join(WORK, 'moraycave', 'meta.json')
    if not (os.path.exists(cj) and os.path.exists(meta_p)):
        return build_eel_old(info)
    cave = json.load(open(cj))
    if not cave:
        return build_eel_old(info)
    meta = json.load(open(meta_p))
    S = cave['scale']
    ex0, ey0, ex1, ey1 = meta['eel_box']
    files = sorted(f for f in os.listdir(FRAMES) if f.startswith('moray_'))
    paths = [os.path.join(FRAMES, f) for f in files]
    box = bbox_union(paths, pad=0)
    # the rendered eel's own outline (frame 0) is fitted to where the eel lay in the photo
    dw = int(round((ex1 - ex0) * S))
    dh = int(round(dw * (box[3] - box[1]) / (box[2] - box[0])))
    frames = [Image.open(p).crop(box).resize((dw, dh), Image.LANCZOS) for p in paths]
    if EEL_FLIP:
        frames = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames]
    uri, cols, rows = sheet(frames, 'moray.png')
    sinfo = sheet_info(uri, cols, rows, dw, dh, dw, dh)
    x0 = cave['x'] + ex0 * S
    y0 = cave['y'] + ey0 * S - (dh - (ey1 - ey0) * S) / 2
    front = Image.open(os.path.join(WORK, 'moraycave', 'front.png'))
    front = front.resize((cave['w'], cave['h']), Image.LANCZOS)
    sinfo.update({'frames': len(files), 'fps': 4 * len(files) / 24.0, 'x': x0, 'y': y0,
                  'outMin': -0.04 * dw, 'outMax': 0.02 * dw, 'hidden': -0.55 * dw,
                  'clipX': cave['x'] + (ex0 - 20) * S, 'clipBottom': cave['y'] + cave['h'],
                  'front': {'uri': save(front, 'hole_front.png'), 'x': cave['x'], 'y': cave['y'],
                            'w': cave['w'], 'h': cave['h']}})
    return sinfo


def build_eel_old(info):
    """The moray from its photo frames, set into the cave mouth.  Its neck sits
    in the hole: the body gets darker the deeper it is in the hole and fades
    out toward the hole's back and bottom, so it seems to come out of the dark.
    The darkening is baked at its place on screen; the channel only moves it
    a little in and out and fades it when it hides."""
    import numpy as np
    files = sorted(f for f in os.listdir(FRAMES) if f.startswith('moray_'))
    paths = [os.path.join(FRAMES, f) for f in files]
    box = bbox_union(paths)
    pxm = abs(info['px_per_m_at_cave'])
    scale = pxm / EEL_SPRITE_PX_PER_M
    w0, h0 = box[2] - box[0], box[3] - box[1]
    dw, dh = max(8, int(round(w0 * scale))), max(8, int(round(h0 * scale)))
    mx, my = info['cave_mouth'][0], info['cave_mouth'][1]
    hole_rx, hole_ry = (0.26 * pxm, 0.13 * pxm) if 'width' in info else (0.33 * pxm, 0.15 * pxm)
    # sprite placement: the head just out of the hole on the right, the body back into it
    x0 = mx + 0.55 * hole_rx - dw
    y0 = my - 0.55 * dh
    sx = x0 + np.arange(dw)[None, :] + 0.5
    sy = y0 + np.arange(dh)[:, None] + 0.5
    ss = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))
    frames = [Image.open(p).crop(box).resize((dw, dh), Image.LANCZOS) for p in paths]
    if EEL_FLIP:
        frames = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in frames]
    uri, cols, rows = sheet(frames, 'moray.png')
    sinfo = sheet_info(uri, cols, rows, dw, dh, dw, dh)
    sinfo.update({'frames': len(files), 'fps': 5, 'x': x0, 'y': y0,
                  'mouthX': mx, 'mouthY': my, 'outMin': -0.06 * dw, 'outMax': 0.04 * dw, 'hidden': -0.65 * dw,
                  'clipX': mx - 1.05 * hole_rx, 'clipBottom': my + 1.6 * hole_ry})
    sinfo.update({'rx': hole_rx, 'ry': hole_ry})
    return sinfo


def hole_front(still, e):
    """What lies in front of the moray: the rock around the hole where its body
    passes behind the rim (below and left of the hole), and the darkness inside
    the hole, deepest at the back.  As the eel backs in, its head goes dark."""
    import numpy as np
    mx, my, rx, ry = e['mouthX'], e['mouthY'], e['rx'], e['ry']
    x0, y0 = int(mx - 3.2 * rx), int(my - 2.6 * ry)
    x1, y1 = int(mx + 1.6 * rx), int(my + 2.4 * ry)
    rock = np.asarray(still.convert('RGB').crop((x0, y0, x1, y1)), np.float32) / 255
    sx = x0 + np.arange(x1 - x0)[None, :] + 0.5
    sy = y0 + np.arange(y1 - y0)[:, None] + 0.5
    ss = lambda e0, e1, x: (lambda t: t * t * (3 - 2 * t))(np.clip((x - e0) / (e1 - e0), 0, 1))
    inside = ((sx - mx) / rx) ** 2 + ((sy - my) / ry) ** 2
    # the rim: rock outside the hole, below it or to its left (the eel's neck goes over the top right)
    behind = np.maximum(ss(my + 0.3 * ry, my + 0.8 * ry, sy), ss(mx + 0.2 * rx, mx - 0.5 * rx, sx))
    rim = ss(0.85, 1.25, inside) * behind
    rim *= ss(x0, x0 + 0.3 * rx, sx) * ss(x1, x1 - 0.3 * rx, sx) * ss(y1, y1 - 0.3 * ry, sy) * ss(y0, y0 + 0.5 * ry, sy)
    # the dark inside: none at the front right of the hole, nearly black at its back left
    dark = ss(1.10, 0.70, inside) * (0.35 + 0.60 * ss(mx + 0.6 * rx, mx - 0.7 * rx, sx))
    a = np.maximum(rim, dark)
    rgb = np.where(rim[..., None] >= dark[..., None], rock, rock * 0.0 + 0.01)
    img = np.concatenate([rgb, a[..., None]], axis=2)
    uri = save(Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), 'RGBA'), 'hole_front.png')
    return {'uri': uri, 'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0}


def caustics(info, mask, n=24, seed=7, margin=16, down=5, still=None):
    """The net of light, on the sand and on the rocks: a few different nets,
    each evaluated at every pixel's place on the ground plan (from the
    position pass), brightest on lit, upward-facing surfaces.  The channel
    scrolls them smoothly in different directions at changing speeds; where
    they overlap the light flows and shifts like real caustics.  (Crossfading
    animation frames always pulsed.)  The margins leave room to scroll."""
    import numpy as np
    W_, H_ = mask.size
    import cv2     # (Pillow reads a 16-bit RGB PNG as 8 bits, which made the net blocky)
    P = cv2.imread(os.path.join(SCENE, 'scene_posnrm.png'), cv2.IMREAD_UNCHANGED)
    P = P[..., ::-1].astype(np.float32) / (65535.0 if P.dtype == np.uint16 else 255.0)
    m = np.asarray(mask, np.float32) / 255
    where = np.clip(np.maximum(m[..., 0], m[..., 2]) - m[..., 1], 0, 1)        # reef (corals too) or floor, not the front rocks
    rws = np.where(where.max(axis=1) > 0.05)[0]
    y0 = int(rws.min()) if len(rws) else 600
    y0 -= y0 % down
    # how lit each pixel is: from the finished picture (the photo corals included)
    lum_src = still if still is not None else Image.open(os.path.join(SCENE, 'scene_sand.png'))
    lum = np.asarray(lum_src.convert('L'), np.float32) / 255
    lit_ref = np.percentile(lum[where > 0.5], 95) if (where > 0.5).any() else 1.0
    # the photo corals are not in the position pass: they get the place of the rock behind them,
    # or above the rock a place worked out from the screen, and count as facing half up
    bare_p = os.path.join(SCENE, 'scene_mask.png')
    coral = np.zeros(where.shape, np.float32)
    if os.path.exists(bare_p) and still is not None:
        bare = np.asarray(Image.open(bare_p).convert('RGB'), np.float32) / 255
        coral = np.clip(m[..., 0] - bare[..., 0], 0, 1)
    cam = info['camera']

    def grid(a):
        """full-resolution map -> the caustic grid (with margins left and right)"""
        a = np.pad(a, ((0, 0), (margin, margin)) + ((0, 0),) * (a.ndim - 2), mode='edge')
        a = a[y0:]
        hh, ww = a.shape[0] // down, a.shape[1] // down
        a = a[:hh * down, :ww * down]
        return a.reshape(hh, down, ww, down, *a.shape[2:]).mean(axis=(1, 3))

    G = grid(P)
    GX = G[..., 0] * 40 - 20
    GY = G[..., 1] * 60 - 10
    NZ = G[..., 2] * 2 - 1
    C = grid(coral)
    empty = G.sum(axis=2) < 0.02                     # nothing in the position pass (coral tips above the rock)
    ppm = abs(info.get('px_per_m_at_cave', 250.0))
    hh_, ww_ = GX.shape
    sx = ((np.arange(ww_) + 0.5) * down - margin)[None, :].repeat(hh_, 0)
    sy = (y0 + (np.arange(hh_) + 0.5) * down)[:, None].repeat(ww_, 1)
    GX = np.where(empty, (sx - W_ / 2) / ppm, GX)
    GY = np.where(empty, 1.0 + (H_ - sy) / ppm * 0.5, GY)
    NZ = np.where(C > 0.3, 0.7, NZ)
    wgt = grid(where) * np.clip(NZ, 0, 1) ** 0.8
    lit = np.clip((grid(lum) / lit_ref - 0.25) / 0.5, 0, 1)
    dist = np.hypot(GX - cam['loc'][0], GY - cam['loc'][1])
    fade = np.clip(1.2 - dist / 14.0, 0, 1) ** 1.5
    if 'width' in info:
        # the tank: everything is about the same distance away, and the reef is
        # judged against the reef (the bright gravel made it all look dim)
        fade = np.ones_like(dist)
        reef_g = grid(np.clip(m[..., 0] - m[..., 1], 0, 1)) > 0.5
        ref_r = np.percentile(grid(lum)[reef_g], 92) if reef_g.any() else lit_ref
        lit_reef = np.clip((grid(lum) / max(ref_r, 1e-3) - 0.15) / 0.55, 0, 1)
        lit = np.where(reef_g, lit_reef, lit)
    weight = wgt * lit * fade
    hh, hw = weight.shape
    r = np.random.default_rng(seed)
    tile, k = 3.0, 70
    bx, by = r.uniform(0, tile, k), r.uniform(0, tile, k)
    rad, pha = r.uniform(0.04, 0.09, k), r.uniform(0, 6.283, k)
    frames = []
    # one looping animation: the light's outline (weight) stays put, only the
    # net moves inside it - each frame a little on from the last, so crossfading flows
    for f in range(n):
        ang = 2 * math.pi * f / n
        cxp = np.mod(bx + rad * np.cos(ang + pha), tile)
        cyp = np.mod(by + rad * np.sin(ang + pha * 1.7), tile)
        wx = GX + 0.09 * np.sin(2.3 * GY + 1.4 * np.sin(1.7 * GX + ang) + ang) + 0.04 * np.sin(5.1 * GY - ang)
        wy = GY + 0.09 * np.sin(2.9 * GX + 1.2 * np.sin(1.3 * GY - ang) - ang) + 0.04 * np.sin(4.7 * GX + ang)
        gx = np.mod(wx, tile)
        gy = np.mod(wy, tile)
        d1 = np.full(gx.shape, 1e9, np.float32)
        d2 = np.full(gx.shape, 1e9, np.float32)
        for i in range(k):
            ddx = np.abs(gx - cxp[i])
            ddx = np.minimum(ddx, tile - ddx)
            ddy = np.abs(gy - cyp[i])
            ddy = np.minimum(ddy, tile - ddy)
            d = np.sqrt(ddx * ddx + ddy * ddy)
            mm = d < d1
            d2 = np.where(mm, d1, np.minimum(d2, d))
            d1 = np.where(mm, d, d1)
        gap = d2 - d1
        edge = 0.85 * np.exp(-gap / 0.020) + 0.30 * np.exp(-gap / 0.075)
        a = np.clip(edge * weight * 1.05, 0, 1)
        img_ = np.zeros((hh, hw, 4), np.uint8)
        img_[..., 0], img_[..., 1], img_[..., 2] = 235, 250, 255
        img_[..., 3] = (a * 255).astype(np.uint8)
        frames.append(Image.fromarray(img_, 'RGBA'))
    uri, cols, rows_ = sheet(frames, 'caustics.png', gutter=2)
    info_ = sheet_info(uri, cols, rows_, hw, hh, hw, hh, gutter=2)
    info_.update({'frames': n, 'fps': 8.0 * n / 32, 'x': -margin, 'y': y0, 'scale': down, 'margin': margin})
    return info_


def build_corals(info):
    """The corals that sway: their frames, each cut out by its outline pass."""
    import numpy as np
    out = []
    for name, c in (info.get('corals') or {}).items():
        frames = []
        for k in range(c['frames']):
            col = Image.open(os.path.join(SCENE, 'coral_%s_%02d.png' % (name, k))).convert('RGBA')
            msk = Image.open(os.path.join(SCENE, 'coralmask_%s_%02d.png' % (name, k))).convert('L')
            col.putalpha(msk)
            frames.append(col)
        boxes = [f.getchannel('A').point(lambda v: 255 if v > 6 else 0).getbbox() for f in frames]
        boxes = [b for b in boxes if b]
        if not boxes:
            continue
        bx = (min(b[0] for b in boxes) - 2, min(b[1] for b in boxes) - 2, max(b[2] for b in boxes) + 2, max(b[3] for b in boxes) + 2)
        frames = [f.crop(bx) for f in frames]
        fw, fh = frames[0].size
        uri, cols, rows = sheet(frames, 'coral_%s.png' % name, gutter=4)
        si = sheet_info(uri, cols, rows, fw, fh, fw, fh, gutter=4)
        si.update({'name': name, 'x': c['x'] + bx[0], 'y': c['y'] + bx[1]})
        out.append(si)
        print('  coral %s %dx%d' % (name, fw, fh))
    return out


GLASS_BAND = 50      # pixels at the bottom: the gravel banked against the front glass, seen side-on


def warm_grade(bg, mask):
    """The rendered reef comes out a little cold: creamier gravel, richer coral colour."""
    import numpy as np
    m = np.asarray(mask, np.float32) / 255
    b = np.asarray(bg, np.float32) / 255
    gravel = np.clip(m[..., 2] + (m[..., 1] * (np.arange(b.shape[0])[:, None] > b.shape[0] * 0.80)), 0, 1)[..., None]
    reef = np.clip(m[..., 0] + m[..., 1], 0, 1)[..., None] * (1 - gravel)
    lum = b.mean(axis=2, keepdims=True)
    if HAZE_FREE:
        # rendered without the water haze: the color is already there, only a light touch
        warm = np.clip(b * np.array([1.02, 1.00, 0.97]), 0, 1)
        rich = np.clip(lum + (b - lum) * 1.08, 0, 1)
        curve = lambda x: np.clip(x + 0.35 * x * (1 - x) * (x - 0.45), 0, 1)
        rich = curve(rich)
    else:
        warm = np.clip(b * np.array([1.10, 1.03, 0.88]) * 1.02, 0, 1)
        rich = np.clip(lum + (b - lum) * 1.35, 0, 1) * np.array([1.05, 1.01, 0.94])
        # S-curve: deeper shadows, the lights kept
        curve = lambda x: np.clip(x + 0.9 * x * (1 - x) * (x - 0.45), 0, 1)
        rich = curve(np.clip(rich * 0.95, 0, 1))
        warm = curve(warm)
    out = warm * gravel + rich * reef + b * (1 - gravel - reef)
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), 'RGB')


def grade_floor(bg, mask):
    """The tank floor: coarse crushed-coral gravel, mostly white and cream with
    darker grains, patchy and gently uneven, laid in true perspective from the
    position pass; and at the bottom the gravel against the front glass, seen
    side-on, under its irregular top line."""
    import numpy as np
    import cv2
    W, H = bg.size
    m = np.asarray(mask, np.float32) / 255
    floor = np.clip(m[..., 2] - m[..., 0], 0, 1)
    rows = np.where(floor.max(axis=1) > 0.5)[0]
    if not len(rows):
        return bg
    y0 = int(rows.min())
    b = np.asarray(bg, np.float32) / 255
    P = cv2.imread(os.path.join(SCENE, 'scene_posnrm.png'), cv2.IMREAD_UNCHANGED)[..., ::-1].astype(np.float32) / 65535.0
    GX, GY = P[..., 0] * 40 - 20, P[..., 1] * 60 - 10
    tex = np.asarray(Image.open(os.path.join(ROOT, 'textures', 'coral_gravel_diff.jpg')).convert('RGB'), np.float32) / 255
    th, tw = tex.shape[:2]
    ppm = tw / 0.45                                  # coarse: one tile covers 0.45 m of floor
    mx = np.mod(GX * ppm, tw).astype(np.float32)
    my = np.mod(GY * ppm, th).astype(np.float32)
    near = cv2.remap(tex, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    far = cv2.remap(cv2.GaussianBlur(tex, (0, 0), 5), mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
    q = np.clip((np.arange(H) - y0) / max(1, H - y0), 0, 1)[:, None, None]
    g = far + (near - far) * q ** 0.6
    # whiten toward crushed coral: lift and desaturate, keep the grain contrast
    lumg = g.mean(axis=2, keepdims=True)
    g = lumg + (g - lumg) * 0.55
    g = (g - g[y0:].mean()) * 1.5 + np.array([0.88, 0.85, 0.79])
    # patches and gentle undulation
    rng = np.random.default_rng(12)
    patch = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 40)
    patch /= np.abs(patch).max() + 1e-6
    wave = np.sin(GX * 3.1 + 0.7 * np.sin(GY * 2.3)) * 0.5 + np.sin(GX * 7.3 - GY * 5.1) * 0.25
    g = g * (1 + 0.08 * patch[..., None] + 0.035 * wave[..., None])
    # the light that falls on it (the rendered floor's shading), and dimmer toward the back
    lum = b.mean(axis=2, keepdims=True)
    g = g * (0.80 + 0.20 * np.clip(lum / max(float(lum[y0:].mean()), 1e-3), 0.5, 1.5)) * (0.86 + 0.14 * q)
    f = floor[..., None]
    out = g * f + b * (1 - f)

    # the gravel against the front glass: grains seen side-on, in the shade of the bank
    top = H - GLASS_BAND + (6 * np.sin(np.arange(W) * 0.013) + 4 * np.sin(np.arange(W) * 0.041 + 1.0)
                            + 3 * cv2.GaussianBlur(rng.normal(0, 1, (1, W)).astype(np.float32), (0, 0), 6)[0]).astype(np.float32)
    ys = np.arange(H)[:, None].astype(np.float32)
    band = np.clip((ys - top[None, :]) / 2.0, 0, 1)
    side = cv2.resize(tex, (int(tw * 0.55), int(th * 0.55)))
    sh_, sw_ = side.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    sideimg = side[(yy % sh_), (xx % sw_)]
    ls = sideimg.mean(axis=2, keepdims=True)
    sideimg = ls + (sideimg - ls) * 0.5
    depth = np.clip((ys - top[None, :]) / GLASS_BAND, 0, 1)[..., None]
    sideimg = (sideimg - 0.5) * 1.4 + np.array([0.80, 0.78, 0.73])
    sideimg = sideimg * (0.92 - 0.14 * depth) * np.array([0.95, 0.98, 1.03])   # a touch of blue through the glass
    out = out * (1 - band[..., None]) + sideimg * band[..., None]
    # a thin bright line where the gravel surface meets the glass, a soft shade just under it
    line = np.exp(-((ys - top[None, :] - 1.5) / 1.6) ** 2)
    shade = np.exp(-((ys - top[None, :] - 8) / 6.0) ** 2) * (ys > top[None, :])
    out = out + 0.10 * line[..., None] - 0.10 * shade[..., None]
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), 'RGB')


def build():
    import numpy as np
    if os.path.exists(IMAGES):
        shutil.rmtree(IMAGES)
    os.makedirs(IMAGES)
    info = json.load(open(os.path.join(SCENE, 'scene.json')))
    composed = os.path.exists(os.path.join(SCENE, 'composed_beauty.png'))
    beauty = Image.open(os.path.join(SCENE, 'composed_beauty.png' if composed else 'scene_beauty.png')).convert('RGB')
    mask = Image.open(os.path.join(SCENE, 'composed_mask.png' if composed else 'scene_mask.png')).convert('RGB')
    W, H = beauty.size

    data = {'width': W}
    print('reef layers...')
    sand_path = os.path.join(SCENE, 'scene_sand.png')
    m = np.asarray(mask, np.float32) / 255
    if os.path.exists(sand_path):
        # the floor without the baked light net (the channel animates it), but not where corals stand on it
        sand = Image.open(sand_path).convert('RGB')
        floor = Image.fromarray((np.clip(m[..., 2] - m[..., 0], 0, 1) * 255).astype(np.uint8), 'L')
        bg = Image.composite(sand, beauty, floor)
        if not info.get('photo_reef'):
            bg = grade_floor(bg, mask)
        else:
            bg = warm_grade(bg, mask)
        print('caustics...')
        # (a taller reef needs more rows: coarser steps until all frames fit one texture)
        for down in (6, 7, 8):          # (5 was finer, but the Roku's own images leave the reef only ~80 MB)
            try:
                data['caustics'] = caustics(info, mask, still=bg, down=down)
                break
            except SystemExit as e:
                print('  ', e, '- trying a coarser grid')
    else:
        bg = beauty
    # how the picture was graded after rendering (compose's water, warm_grade), per pixel: the
    # in-scene sprites (clam, moray), rendered lit in the full scene, get the same treatment
    global GRADE
    raw_p = os.path.join(SCENE, 'scene_beauty.png')
    if os.path.exists(raw_p):
        from PIL import ImageFilter
        ref = warm_grade(beauty, mask) if info.get('photo_reef') else beauty
        raw = np.asarray(Image.open(raw_p).convert('RGB').filter(ImageFilter.GaussianBlur(6)), np.float32) + 4
        ref = np.asarray(ref.filter(ImageFilter.GaussianBlur(6)), np.float32) + 4
        GRADE = np.clip(ref / raw, 0.3, 3.0)
    data['background'] = save_tiles(bg, 'background', quality=93)
    data['reefMid'] = layer_from_mask(bg, mask, 'R', 'reef_mid.png')
    # the clam first: the front layer holds the still clam, so cut the animated clam out of it
    print('clam...')
    data['clam'] = build_clam()
    if data['clam']:
        c = data['clam']
        sh = Image.open(os.path.join(IMAGES, os.path.basename(c['sheet']))).getchannel('A')
        k_ = sh.width / c['sheetW']
        hole = np.zeros((H, W), np.uint8)
        for f in range(c['frames']):
            x0, y0 = (f % c['cols']) * c['pitchX'] * k_, (f // c['cols']) * c['pitchY'] * k_
            fa = np.asarray(sh.crop((int(x0), int(y0), int(x0 + c['w'] * k_), int(y0 + c['h'] * k_))).resize((int(c['w']), int(c['h']))))
            cx, cy = int(c['x']), int(c['y'])
            reg = hole[cy:cy + fa.shape[0], cx:cx + fa.shape[1]]
            np.maximum(reg, fa[:reg.shape[0], :reg.shape[1]], out=reg)
        mk = np.asarray(mask).copy()
        mk[..., 1] = (mk[..., 1].astype(np.float32) * (1 - hole / 255.0)).astype(np.uint8)
        mask_front = Image.fromarray(mk, 'RGB')
    else:
        mask_front = mask
    data['reefFront'] = layer_from_mask(bg, mask_front, 'G', 'reef_front.png')
    # the open water, for the slow change of light (the channel tints it)
    water = np.clip(1 - m.max(axis=2), 0, 1)
    water *= np.clip(1.0 - np.arange(H)[:, None] / (0.55 * H), 0.25, 1)    # (the light changes most near the surface)
    wimg = Image.fromarray((water * 255).astype(np.uint8), 'L').resize((W // 2, H // 2), Image.BILINEAR)
    wl = Image.new('RGBA', wimg.size, (255, 255, 255, 0))
    wl.putalpha(wimg)
    data['water'] = {'uri': save(wl, 'water.png'), 'w': W, 'h': H}
    # corals that sway with the water (photos/compose.py)
    data['corals'] = []
    sj = os.path.join(SCENE, 'sway.json')
    if os.path.exists(sj):
        for c in json.load(open(sj)):
            uri = save(Image.open(os.path.join(SCENE, c['file'])), c['file'].replace('sway_', 'coral_'))
            data['corals'].append({'sheet': uri, 'x': c['x'], 'y': c['y'], 'w': c['w'], 'h': c['h']})
    data['rays'] = []
    save(scene.bubble(), 'bubble.png')
    print('fish...')
    data['species'] = build_species()
    print('moray...')
    data['eel'] = build_eel(info)
    still = bg.convert('RGBA')
    for t in data['reefMid']:
        still.alpha_composite(Image.open(os.path.join(IMAGES, os.path.basename(t['uri']))), (t['x'], t['y']))
    data['eelFront'] = data['eel'].pop('front') if 'front' in data['eel'] else hole_front(still, data['eel'])
    # the aerator: a column of bubbles rising from the gravel behind the reef, toward the right
    floor_top = int(np.median([np.argmax(m[:, x, 2] > 0.5) for x in range(0, W, 16) if (m[:, x, 2] > 0.5).any()] or [H - 120]))
    data['bubbleSource'] = [int(W * 0.80), floor_top - 10]
    with open(os.path.join(OUT, 'tank.json'), 'w') as f:
        json.dump(data, f, indent=1)
    return data


def preview(data, seed=2, path=None):
    """A still of the whole tank laid out the way the channel draws it."""
    r = random.Random(seed)
    img = lambda n: Image.open(os.path.join(IMAGES, os.path.basename(n))).convert('RGBA')
    W = data.get('width', 1920)
    im = Image.new('RGBA', (W, 1080))
    for t in data['background']:
        im.alpha_composite(img(t['uri']), (t['x'], t['y']))
    sheets = {}

    def frame_of(sp, k):
        if sp['name'] not in sheets:
            sheets[sp['name']] = img(sp['sheet'])
        sh = sheets[sp['name']]
        kx, ky = sh.width / sp['sheetW'], sh.height / sp['sheetH']
        c, rr = k % sp['cols'], k // sp['cols']
        x0, y0 = c * sp['pitchX'] * kx, rr * sp['pitchY'] * ky
        return sh.crop((int(x0), int(y0), int(x0 + sp['w'] * kx), int(y0 + sp['h'] * ky)))

    def put(sp, far):
        k = r.randrange(sp['frames']) + (sp['frames'] if r.random() < 0.5 else 0)
        f = frame_of(sp, k)
        d = r.uniform(0.55, 0.75) if far else r.uniform(0.75, 1.0)
        s_ = 0.42 + 0.58 * d
        f = f.resize((max(1, int(sp['w'] * s_)), max(1, int(sp['h'] * s_))), Image.LANCZOS)
        im.alpha_composite(f, (r.randrange(40, W - f.width - 40), r.randrange(120, 760)))

    if 'caustics' in data:
        c = data['caustics']
        sh = img(c['sheet'])
        fr = sh.crop((0, 0, int(c['w']), int(c['h']))).resize((int(c['w'] * c['scale']), int(c['h'] * c['scale'])), Image.BILINEAR)
        layer = Image.new('RGBA', (W + 2 * int(c['margin']), 1080))
        layer.alpha_composite(fr, (0, c['y']))
        im.alpha_composite(layer.crop((-c['x'], 0, -c['x'] + W, 1080)))
    for sp in data['species']:
        if sp['role'] != 'cruiser':
            for i in range(sp['count']):
                if r.random() < 0.35:
                    put(sp, True)
    for t in data['reefMid']:
        im.alpha_composite(img(t['uri']), (t['x'], t['y']))
    for c in data.get('corals', []):
        im.alpha_composite(img(c['sheet']), (c['x'], c['y']))
    e = data['eel']
    sh = img(e['sheet'])
    kx = sh.width / e['sheetW']
    eel = sh.crop((0, 0, int(e['w'] * kx), int(e['h'] * kx))).resize((int(e['w']), int(e['h'])))
    im.alpha_composite(eel, (int(e['x'] + e['outMax']), int(e['y'])))
    f = data['eelFront']
    im.alpha_composite(img(f['uri']), (f['x'], f['y']))
    if data.get('clam'):
        c = data['clam']
        sh = img(c['sheet'])
        k_ = sh.width / c['sheetW']
        im.alpha_composite(sh.crop((0, 0, int(c['w'] * k_), int(c['h'] * k_))).resize((int(c['w']), int(c['h']))), (int(c['x']), int(c['y'])))
    for sp in data['species']:
        if sp['role'] != 'cruiser':
            for i in range(sp['count']):
                if r.random() < 0.65:
                    put(sp, False)
    for t in data['reefFront']:
        im.alpha_composite(img(t['uri']), (t['x'], t['y']))
    b = img('bubble.png')
    bx, by = data['bubbleSource']
    for i in range(40):
        sz = 5 + (i * 7) % 10
        im.alpha_composite(b.resize((sz, sz)), (bx + int(10 * math.sin(i * 1.7)), by - i * 24))
    if path:
        im.convert('RGB').save(path)
    return im


def icons(data):
    pv = preview(data, seed=5)
    crop = pv.crop((300, 0, 300 + 1440, 1080))
    crop.resize((540, 405), Image.LANCZOS).save(os.path.join(IMAGES, 'icon_fhd.png'))
    crop.resize((290, 218), Image.LANCZOS).save(os.path.join(IMAGES, 'icon_hd.png'))
    pv.crop((0, 0, 1920, 1080)).convert('RGB').save(os.path.join(IMAGES, 'splash_fhd.jpg'), quality=88)


def package(data):
    for sub in ('source', 'components'):
        dst = os.path.join(CHANNEL, sub)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(os.path.join(TEMPLATE, sub), dst)
    # every build gets its own build_version (the Roku reports it), so a stale install is easy to spot
    import time
    man = open(os.path.join(TEMPLATE, 'manifest'), encoding='utf-8').read()
    stamp = time.strftime('%m%d%H%M')
    man = re.sub(r'build_version=\d+', 'build_version=' + stamp, man)
    with open(os.path.join(CHANNEL, 'manifest'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(man)
    print('build', stamp)
    os.makedirs(os.path.join(CHANNEL, 'data'), exist_ok=True)
    with open(os.path.join(CHANNEL, 'data', 'tank.json'), 'w') as f:
        json.dump(data, f)
    zpath = os.path.join(OUT, 'TranquilReef.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(CHANNEL):
            for fn in sorted(files):
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, CHANNEL).replace(os.sep, '/'))
    print('wrote', zpath, '%.1f MB' % (os.path.getsize(zpath) / 1e6))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    data = build()
    preview(data, path=os.path.join(OUT, 'preview.png'))
    icons(data)
    package(data)

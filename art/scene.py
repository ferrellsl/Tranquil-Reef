"""The tank: water, sand, rock and coral layers, plants, light rays, caustics
and bubbles.  Everything is generated from noise with fixed seeds, so a
build always gives the same pictures."""
import math
import numpy as np
from PIL import Image, ImageDraw
from .noise import fractal, smoothstep, blur, mix, hexcol as C, to_rgba_image, to_rgb_image, rng

W, H = 1920, 1080
SAND_TOP = 850          # where the sand meets the back of the tank


def water_color(y):
    """Color of open water at screen row y (array), used for haze too."""
    t = np.clip(y / H, 0, 1)
    top, mid, low = C('#2c8fc4'), C('#0f5c96'), C('#073056')
    a = mix(top, mid, smoothstep(0.0, 0.55, t)[..., None] if np.ndim(t) else smoothstep(0.0, 0.55, t))
    return mix(a, low, smoothstep(0.45, 1.0, t)[..., None] if np.ndim(t) else smoothstep(0.45, 1.0, t))


def lit_heightfield(height, colors, light=(-0.45, -0.75, 0.55), strength=6.0, spec=0.15):
    """Shade an RGB image with normals from a height map (y down in image)."""
    gy, gx = np.gradient(height)
    nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(height)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly, lz = light
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    d = np.clip((nx * lx + ny * ly + nz * lz) / (n * ln), 0, 1)
    hx, hy, hz = lx / ln, ly / ln, lz / ln + 1
    hn = math.sqrt(hx * hx + hy * hy + hz * hz)
    s = np.clip((nx * hx + ny * hy + nz * hz) / (n * hn), 0, 1) ** 20
    return colors * (0.30 + 0.85 * d)[..., None] + spec * s[..., None]


# ------------------------------------------------------------ background

def background():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    col = water_color(yy)
    # brighter where the light comes in near the top middle
    glow = np.exp(-(((xx - W * 0.55) / (W * 0.45)) ** 2) - ((yy / (H * 0.55)) ** 2))
    col = col + glow[..., None] * C('#2a6f8f') * 0.55
    col = col * (1 + 0.04 * fractal(W, H, 11, base=3, octaves=5))[..., None]

    # distant reef silhouettes, two ridges fading into the water
    for i, (base_y, amp, haze, seed) in enumerate(((735, 70, 0.82, 21), (790, 60, 0.66, 22))):
        ridge = base_y - amp * (0.5 + 0.5 * fractal(W, 1, seed, base=5, octaves=6)[0]) \
            - 50 * np.exp(-((np.arange(W) - (500 if i else 1450)) / 260.0) ** 2)
        lumps = fractal(W, H, seed + 50, base=18, octaves=4)
        mask = smoothstep(-1.5, 1.5, yy - ridge[None, :] + lumps * 18)
        rock = mix(C('#5a4a6a'), C('#3b5a50'), smoothstep(-0.3, 0.3, lumps))
        rock = rock * (0.75 + 0.35 * smoothstep(40, 0, yy - ridge[None, :]))[..., None]
        rock = mix(rock, water_color(yy), np.full((H, W), haze, np.float32))
        col = mix(col, rock, mask)

    # sand with perspective: ripples get finer toward the back
    s = np.clip((yy - SAND_TOP) / (H - SAND_TOP), 0, 1)
    edge = SAND_TOP + 14 * fractal(W, 1, 31, base=6, octaves=5)[0][None, :]
    sandmask = smoothstep(-2, 2, yy - edge)
    depth = 0.25 + 0.75 * s
    warp = fractal(W, H, 32, base=6, octaves=4) * 40
    ripple = np.sin((yy - SAND_TOP + warp) / (2.5 + 9 * depth) * 3.0 + xx * 0.004)
    grain = fractal(W, H, 33, base=200, octaves=2)
    patches = fractal(W, H, 34, base=5, octaves=5)
    sand = mix(C('#b49f78'), C('#e2d3ae'), smoothstep(-0.5, 0.6, patches))
    sand = sand * (0.88 + 0.10 * ripple + 0.08 * grain)[..., None]
    pebbles = smoothstep(0.55, 0.75, fractal(W, H, 35, base=90, octaves=2))
    sand = mix(sand, C('#7e7466'), pebbles * 0.6)
    sand = mix(sand, water_color(np.full_like(yy, SAND_TOP)), (1 - depth)[..., None] * 0.55)
    sand = sand * (0.55 + 0.45 * depth)[..., None]
    col = mix(col, sand, sandmask)

    # vignette
    v = ((xx / W - 0.5) ** 2 * 1.2 + (yy / H - 0.45) ** 2)
    col = col * (1 - 0.55 * smoothstep(0.12, 0.55, v))[..., None]
    return to_rgb_image(col)


# ------------------------------------------------------------ rocks & coral

def rock_mound(w, h, seed, palette, ss=1):
    """A lumpy live-rock mound filling a w x h box -> (rgb, alpha) arrays."""
    w, h = w * ss, h * ss
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / w - 0.5) * 2
    ny = (yy / h)
    outline = 1 - np.abs(nx) ** 2.2
    shape = ny - (1 - outline * (0.75 + 0.25 * fractal(w, 1, seed, base=4, octaves=5)[0][None, :]))
    shape = shape + 0.10 * fractal(w, h, seed + 1, base=8, octaves=5)
    mask = smoothstep(-0.004, 0.004, shape) * (ny < 1.01)
    height = blur(mask, 22 * ss) + 0.25 * mask * fractal(w, h, seed + 2, base=24, octaves=5)
    holes = smoothstep(0.35, 0.55, fractal(w, h, seed + 3, base=16, octaves=4)) * mask
    height = height - 0.3 * holes
    c1, c2, c3, c4 = [C(p) for p in palette]
    n1 = fractal(w, h, seed + 4, base=10, octaves=5)
    n2 = fractal(w, h, seed + 5, base=30, octaves=4)
    col = mix(c1, c2, smoothstep(-0.25, 0.25, n1))
    col = mix(col, c3, smoothstep(0.2, 0.45, n2))          # coralline patches
    col = mix(col, c4, smoothstep(0.3, 0.6, -n1) * 0.8)   # algae
    col = lit_heightfield(height, col, strength=40 / ss)
    col = col * (1 - 0.6 * holes)[..., None]
    # darker toward the base where it sits in shadow
    col = col * (0.55 + 0.45 * smoothstep(1.0, 0.45, ny))[..., None]
    return col, mask


def draw_branching(draw, x, y, ang, length, width, depth, r, color_fn, tips):
    if depth == 0 or length < 3:
        tips.append((x, y, width))
        return
    x2 = x + math.cos(ang) * length
    y2 = y - math.sin(ang) * length
    draw.line([(x, y), (x2, y2)], fill=color_fn(depth), width=max(1, int(width)))
    draw.ellipse([x2 - width / 2, y2 - width / 2, x2 + width / 2, y2 + width / 2], fill=color_fn(depth))
    n = 2 if r.random() < 0.8 else 3
    for i in range(n):
        da = (i - (n - 1) / 2) * r.uniform(0.35, 0.6) + r.uniform(-0.15, 0.15)
        draw_branching(draw, x2, y2, ang + da, length * r.uniform(0.68, 0.82), width * 0.78,
                       depth - 1, r, color_fn, tips)


def branching_coral(w, h, seed, base, tip, ss=2):
    """Staghorn-like coral -> RGBA image of size (w, h)."""
    r = np.random.default_rng(seed)
    import random
    rr = random.Random(seed)
    img = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cb, ct = C(base), C(tip)

    def color_fn(depth):
        t = 1 - depth / 7
        c = cb * (1 - t) + ct * t
        return tuple(int(v * 255) for v in c) + (255,)

    tips = []
    for k in range(5):
        draw_branching(d, w * ss * rr.uniform(0.35, 0.65), h * ss, math.pi / 2 + rr.uniform(-0.5, 0.5),
                       h * ss * 0.22, 18 * ss, 7, rr, color_fn, tips)
    for (x, y, wd) in tips:
        d.ellipse([x - wd, y - wd, x + wd, y + wd], fill=tuple(int(v * 255) for v in ct) + (255,))
    a = np.asarray(img, np.float32) / 255
    rgb, alpha = a[..., :3], a[..., 3]
    height = blur(alpha, 3 * ss)
    rgb = lit_heightfield(height, rgb, strength=8.0, spec=0.25)
    return to_rgba_image(rgb, alpha, ss)


def sea_fan(w, h, seed, color, ss=2):
    import random
    rr = random.Random(seed)
    img = Image.new('RGBA', (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = tuple(int(v * 255) for v in C(color))

    def br(x, y, ang, ln, wd, depth):
        if depth == 0:
            return
        x2 = x + math.cos(ang) * ln
        y2 = y - math.sin(ang) * ln
        d.line([(x, y), (x2, y2)], fill=c + (255,), width=max(1, int(wd)))
        for da in (-0.32, 0.30):
            br(x2, y2, ang + da + rr.uniform(-0.12, 0.12), ln * rr.uniform(0.74, 0.86), wd * 0.8, depth - 1)

    br(w * ss / 2, h * ss, math.pi / 2, h * ss * 0.2, 7 * ss, 9)
    # the fine mesh between branches
    a = np.asarray(img, np.float32) / 255
    alpha = a[..., 3]
    mesh_region = blur(alpha, 14 * ss) > 0.06
    yy, xx = np.mgrid[0:h * ss, 0:w * ss]
    mesh = (np.sin(xx * 0.45 / ss + yy * 0.2 / ss) > 0.82) | (np.sin(xx * 0.2 / ss - yy * 0.45 / ss) > 0.82)
    alpha = np.maximum(alpha, (mesh & mesh_region) * 0.55)
    rgb = np.broadcast_to(C(color), alpha.shape + (3,)) * (0.8 + 0.3 * (1 - yy / (h * ss)))[..., None]
    return to_rgba_image(rgb, alpha, ss)


def brain_coral(w, h, seed, c1, c2, ss=2):
    w2, h2 = w * ss, h * ss
    yy, xx = np.mgrid[0:h2, 0:w2].astype(np.float32)
    nx = (xx / w2 - 0.5) * 2
    ny = (yy / h2 - 1.0)              # dome sitting on its base
    dome = 1 - nx * nx - ny * ny
    alpha = smoothstep(0.0, 0.01, dome)
    n = fractal(w2, h2, seed, base=10, octaves=3)
    groove = np.abs(np.sin(n * 14 + xx * 0.02))
    height = np.sqrt(np.clip(dome, 0, 1)) * 1.0 + 0.04 * groove
    col = mix(C(c1), C(c2), smoothstep(0.2, 0.9, groove))
    col = lit_heightfield(height * 60 / ss, col, strength=1.0, spec=0.2)
    return to_rgba_image(col, alpha, ss)


def tube_sponge(w, h, seed, color, ss=2):
    import random
    rr = random.Random(seed)
    img_rgb = np.zeros((h * ss, w * ss, 3), np.float32)
    img_a = np.zeros((h * ss, w * ss), np.float32)
    yy, xx = np.mgrid[0:h * ss, 0:w * ss].astype(np.float32)
    for k in range(4):
        cx = w * ss * (0.2 + 0.2 * k) + rr.uniform(-10, 10) * ss
        top = h * ss * rr.uniform(0.05, 0.45)
        rad = w * ss * rr.uniform(0.07, 0.10)
        lean = rr.uniform(-0.15, 0.15)
        x0 = cx + (yy - h * ss) * lean
        d = (xx - x0) / rad
        body = (np.abs(d) < 1) & (yy > top)
        nz = np.sqrt(np.clip(1 - d * d, 0, 1))
        shade = 0.35 + 0.75 * np.clip(-0.5 * d + 0.7 * nz, 0, 1)
        rim = (np.abs(d) < 1) & (np.abs(yy - top) < rad * 0.35)
        col = C(color) * shade[..., None]
        col = np.where(rim[..., None], C(color) * 0.25, col)
        m = body | rim
        img_rgb = np.where(m[..., None], col, img_rgb)
        img_a = np.maximum(img_a, m.astype(np.float32))
    return to_rgba_image(img_rgb, img_a, ss)


def paste(canvas, im, x, y):
    canvas.alpha_composite(im, (int(x), int(y)))


def tinted(im, amount, color):
    """Mix an RGBA image toward a water color (distance haze)."""
    a = np.asarray(im, np.float32) / 255
    rgb = a[..., :3] * (1 - amount) + C(color) * amount
    out = np.concatenate([rgb, a[..., 3:]], axis=2)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA')


def reef_mid():
    """Rock and coral at middle distance, on both sides; fish swim in front and behind."""
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pal = ('#6d5a6e', '#8a6f5c', '#b05a8a', '#4f7a4a')
    for (x, y, w, h, seed) in ((-80, 560, 720, 420, 101), (1280, 600, 760, 380, 102)):
        rgb, a = rock_mound(w, h, seed, pal)
        paste(canvas, tinted(to_rgba_image(rgb, a), 0.30, '#1a5a8a'), x, y)
    for (x, y, w, h, s, b, t) in ((120, 360, 300, 300, 201, '#c06a40', '#ffd2a0'),
                                  (1520, 420, 260, 260, 202, '#8a5ab0', '#e0c0ff')):
        paste(canvas, tinted(branching_coral(w, h, s, b, t), 0.28, '#1a5a8a'), x, y)
    paste(canvas, tinted(sea_fan(320, 360, 301, '#a2408a'), 0.3, '#1a5a8a'), 1660, 280)
    paste(canvas, tinted(brain_coral(220, 120, 401, '#7a8a40', '#c8d080'), 0.25, '#1a5a8a'), 380, 560)
    paste(canvas, tinted(tube_sponge(180, 260, 501, '#d07a2a'), 0.25, '#1a5a8a'), 1360, 380)
    return canvas


def reef_front():
    """Dark close rocks in the bottom corners, in front of every fish."""
    canvas = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    pal = ('#4a3a48', '#6a5040', '#9a3a6a', '#3a6a3a')
    for (x, y, w, h, seed) in ((-160, 820, 640, 300, 111), (1540, 800, 560, 320, 112)):
        rgb, a = rock_mound(w, h, seed, pal)
        paste(canvas, to_rgba_image(rgb * 0.85, a), x, y)
    paste(canvas, brain_coral(260, 140, 402, '#a06a50', '#f0c0a0'), 230, 880)
    paste(canvas, branching_coral(240, 260, 203, '#2a8a8a', '#a0fff0'), 1620, 640)
    return canvas


# ------------------------------------------------------------ plants

def seaweed_frames(w, h, seed, color, n=16, blades=7, ss=2):
    """Swaying blades of sea grass; n frames of one sway cycle."""
    import random
    rr = random.Random(seed)
    specs = [(rr.uniform(0.25, 0.75), rr.uniform(0.55, 1.0), rr.uniform(0, 6.28), rr.uniform(6, 11))
             for _ in range(blades)]
    frames = []
    yy, xx = np.mgrid[0:h * ss, 0:w * ss].astype(np.float32)
    for k in range(n):
        ph = 2 * math.pi * k / n
        rgb = np.zeros((h * ss, w * ss, 3), np.float32)
        al = np.zeros((h * ss, w * ss), np.float32)
        for (bx, bl, bp, bw) in specs:
            t = 1 - yy / (h * ss)                   # 0 at the root, 1 at the top
            sway = (np.sin(ph + bp) * 0.16 * t ** 1.6 + np.sin(ph * 2 + bp + t * 3) * 0.03 * t) * w * ss
            cx = bx * w * ss + sway
            half = bw * ss * (1 - 0.8 * (t / bl)) * 0.5
            inside = (np.abs(xx - cx) < half) & (t < bl)
            side = (xx - cx) / np.maximum(half, 1e-3)
            shade = 0.6 + 0.4 * (1 - np.abs(side)) + 0.15 * np.sin(ph + bp) * side
            c = mix(C(color) * 0.55, C(color), smoothstep(0, 0.8, t)[..., None] * np.ones(3)) * shade[..., None]
            rgb = np.where(inside[..., None], c, rgb)
            al = np.maximum(al, inside * 0.95)
        frames.append(to_rgba_image(rgb, al, ss))
    return frames


# ------------------------------------------------------------ light

def light_rays(seed):
    r = rng(seed)
    yy, xx = np.mgrid[0:H // 2, 0:W // 2].astype(np.float32) * 2
    a = np.zeros(yy.shape, np.float32)
    for _ in range(7):
        x0 = r.uniform(0.1, 1.0) * W
        slope = r.uniform(-0.30, -0.18)
        wid = r.uniform(25, 90)
        cx = x0 + slope * yy
        a += np.exp(-((xx - cx) / wid) ** 2) * r.uniform(0.4, 1.0)
    a = a * (1 - smoothstep(0, H * 0.95, yy)) * 0.22
    a = blur(a, 6)
    img = to_rgba_image(np.broadcast_to(C('#d8f4ff'), a.shape + (3,)), a)
    return img                          # half size; the channel scales it up


def caustic_frames(n=16, w=960, h=180, seed=7):
    """Looping caustic net for the sand: moving Voronoi cell edges."""
    r = rng(seed)
    k = 70
    px, py = r.uniform(0, w, k), r.uniform(0, h, k)
    rad = r.uniform(6, 18, k)
    pha = r.uniform(0, 6.28, k)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    frames = []
    for f in range(n):
        t = 2 * math.pi * f / n
        cx = (px + rad * np.cos(t + pha)) % w
        cy = (py + rad * np.sin(t * 1 + pha * 1.3)) % h
        d1 = np.full(yy.shape, 1e9, np.float32)
        d2 = np.full(yy.shape, 1e9, np.float32)
        for i in range(k):
            dx = np.abs(xx - cx[i]); dx = np.minimum(dx, w - dx)
            dy = np.abs(yy - cy[i]); dy = np.minimum(dy, h - dy)
            d = np.sqrt(dx * dx + dy * dy * 4)       # flattened by perspective
            m = d < d1
            d2 = np.where(m, d1, np.minimum(d2, d))
            d1 = np.where(m, d, d1)
        edge = np.exp(-(d2 - d1) / 2.2)
        fade = smoothstep(0, 40, yy) * (0.6 + 0.4 * yy / h)
        a = np.clip(edge * fade * 0.38, 0, 1)
        frames.append(to_rgba_image(np.broadcast_to(C('#e8fbff'), a.shape + (3,)), a))
    return frames


def bubble(size=40, ss=3):
    s = size * ss
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    d = np.sqrt((xx - s / 2) ** 2 + (yy - s / 2) ** 2) / (s / 2)
    ring = smoothstep(0.70, 0.95, d) * smoothstep(1.0, 0.95, d)
    hl = np.exp(-(((xx - s * 0.35) ** 2 + (yy - s * 0.32) ** 2) / (s * 0.08) ** 2))
    a = np.clip(ring * 0.75 + 0.10 * (d < 1) + hl * 0.9, 0, 1)
    return to_rgba_image(np.broadcast_to(C('#eaf8ff'), a.shape + (3,)), a, ss)

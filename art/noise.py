"""Small numpy helpers for procedural art: fractal noise, smoothstep, blur."""
import numpy as np
from PIL import Image, ImageFilter


def rng(seed):
    return np.random.default_rng(seed)


def smooth_resize(a, w, h):
    """Bicubic upscale of a float array to (h, w)."""
    im = Image.fromarray(a.astype(np.float32), mode='F')
    return np.asarray(im.resize((w, h), Image.BICUBIC), dtype=np.float32)


def fractal(w, h, seed, base=4, octaves=6, gain=0.5, tile=False):
    """Fractal value noise in about [-1, 1], shape (h, w)."""
    r = rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = base * (2 ** o)
        gw = max(2, cells)
        gh = max(2, int(round(cells * h / w)) or 2)
        g = r.uniform(-1, 1, (gh + 3, gw + 3)).astype(np.float32)
        if tile:
            g[:, -3:] = g[:, :3]
            g[-3:, :] = g[:3, :]
        big = smooth_resize(g, int(w * (gw + 3) / gw), int(h * (gh + 3) / gh))
        out += amp * big[:h, :w]
        total += amp
        amp *= gain
    return out / total


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def blur(a, radius):
    """Gaussian blur of a float array (any range) or an RGBA uint8 image."""
    if isinstance(a, Image.Image):
        return a.filter(ImageFilter.GaussianBlur(radius))
    # three box blurs approximate a gaussian (Pillow cannot blur float images)
    out = a.astype(np.float32)
    r = max(1, int(round(radius * 0.87)))
    for axis in (0, 1):
        for _ in range(3):
            out = _box(out, r, axis)
    return out


def _box(a, r, axis):
    pad = [(0, 0), (0, 0)]
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode='edge')
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    n = a.shape[axis]
    hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return ((hi - lo) / (2 * r + 1)).astype(np.float32)


def mix(a, b, t):
    t = np.asarray(t, np.float32)
    a = np.asarray(a, np.float32)
    b = np.asarray(b, np.float32)
    # a 2-D weight with colors (1-D) or images (3-D) mixes per pixel
    if t.ndim == 2 and (a.ndim in (1, 3) or b.ndim in (1, 3)):
        t = t[..., None]
    return a * (1 - t) + b * t


def hexcol(s):
    s = s.lstrip('#')
    return np.array([int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)], np.float32)


def to_rgba_image(rgb, alpha, ss=1):
    """float rgb (h,w,3) 0..1 and alpha (h,w) -> PIL RGBA, downsampled by ss."""
    a = np.clip(alpha, 0, 1)[..., None]
    pre = np.clip(rgb, 0, 1) * a  # premultiply for clean downsampling
    arr = np.concatenate([pre, a], axis=2)
    h, w = alpha.shape
    if ss > 1:
        arr = arr[:h - h % ss, :w - w % ss]
        arr = arr.reshape(h // ss, ss, w // ss, ss, 4).mean(axis=(1, 3))
    a = arr[..., 3:4]
    rgb = np.where(a > 1e-4, arr[..., :3] / np.maximum(a, 1e-4), 0)
    out = np.concatenate([rgb, a], axis=2)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGBA')


def to_rgb_image(rgb, ss=1):
    h, w, _ = rgb.shape
    arr = rgb
    if ss > 1:
        arr = arr[:h - h % ss, :w - w % ss].reshape(h // ss, ss, w // ss, ss, 3).mean(axis=(1, 3))
    return Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), 'RGB')

"""Procedural reef fish, drawn side-on with fake 3D lighting.

Each species is a body profile, fins and a color pattern, all evaluated as
numpy functions over a supersampled grid.  The swim cycle is made by
warping the coordinates frame by frame: the tail fin is foreshortened as it
sweeps toward and away from the viewer, the pectoral fin flaps and the
dorsal and anal fins ripple.

Coordinates: u runs from the nose (0) to the tail tip (1); y is up, in the
same units as u, so circles stay circles.
"""
import math
import numpy as np
from .noise import hexcol, mix, smoothstep, to_rgba_image, fractal


# ---------------------------------------------------------------- curves

def spline(points, u):
    """Catmull-Rom through (u, v) points, sampled at u (clamped outside)."""
    pts = sorted(points)
    xs = np.array([p[0] for p in pts], np.float64)
    vs = np.array([p[1] for p in pts], np.float64)
    dense_u, dense_v = [], []
    n = len(pts)
    for i in range(n - 1):
        p0 = vs[max(i - 1, 0)]
        p1, p2 = vs[i], vs[i + 1]
        p3 = vs[min(i + 2, n - 1)]
        for t in np.linspace(0, 1, 24, endpoint=False):
            t2, t3 = t * t, t * t * t
            v = 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            dense_u.append(xs[i] + (xs[i + 1] - xs[i]) * t)
            dense_v.append(v)
    dense_u.append(xs[-1])
    dense_v.append(vs[-1])
    return np.interp(u, dense_u, dense_v).astype(np.float32)


C = hexcol


# ---------------------------------------------------------------- species

def band(u, center, half, soft=0.006):
    return smoothstep(half + soft, half - soft, np.abs(u - center))


class Species:
    name = 'fish'
    width = 360           # final pixel width of one frame (the fish length + margins)
    height = 240
    pad = 0.04            # margin on each side, fraction of width
    profile = []          # (u, top, bottom)
    peduncle = 0.80       # where the tail fin begins
    tail_spread = 0.20    # half height of the tail fin at its tip
    tail_fork = 0.15      # >0 forked/lunate, <0 rounded
    dorsal = None         # [(u, height above back)], heights 0 at both ends
    anal = None
    pectoral = (0.30, -0.03, 0.12, 0.05)   # u, y, length, width
    eye = (0.12, 0.05, 0.028)               # u, y, radius
    iris = '#d9a441'
    fin_alpha = 0.85
    gill = 0.22
    rays_tail = 26
    rays = True            # fin rays drawn (sharks have none)
    scales = True
    tail_upper = 1.0       # upper / lower tail lobe size (a shark's upper lobe is longer)
    tail_lower = 1.0
    dorsal2 = None
    pectoral_angle = -18
    pectoral_tri = False   # triangular pectoral fin instead of a fan
    pectoral_alpha = 0.35
    tail_lower_len = 1.0    # length of the lower tail lobe relative to the upper
    skin = {}               # material overrides: rough, coat, bump, bumpscale, sss, translucency, fin_thick
    mottle = 0.07
    thick = 0.4             # body width / height for the 3D model

    # the pattern of the body and the fins; override
    def body_color(self, u, y, nv, top, bot):
        return np.broadcast_to(C('#888888'), u.shape + (3,)).copy()

    def fin_color(self, u, y, which):
        return np.broadcast_to(C('#999999'), u.shape + (3,)).copy()


class YellowTang(Species):
    name = 'yellowtang'
    thick = 0.30
    width, height = 340, 300
    profile = [(0, 0, 0), (0.02, 0.03, 0.03), (0.07, 0.10, 0.07), (0.16, 0.20, 0.17),
               (0.32, 0.27, 0.25), (0.50, 0.24, 0.23), (0.66, 0.14, 0.13), (0.78, 0.05, 0.05),
               (0.81, 0.045, 0.045)]
    peduncle = 0.80
    tail_spread = 0.15
    tail_fork = 0.12
    dorsal = [(0.20, 0), (0.26, 0.10), (0.42, 0.12), (0.58, 0.10), (0.72, 0.06), (0.78, 0)]
    anal = [(0.36, 0), (0.42, 0.10), (0.56, 0.10), (0.70, 0.06), (0.77, 0)]
    pectoral = (0.28, -0.02, 0.10, 0.045)
    eye = (0.13, 0.075, 0.03)
    iris = '#2a2a10'
    gill = 0.21

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#ffd51a'), C('#ffe96b'), smoothstep(0.6, -0.8, nv))
        spine = band(u, 0.765, 0.012) * smoothstep(0.03, 0.0, np.abs(y))  # white spine
        return mix(base, C('#fffbe8'), spine)

    def fin_color(self, u, y, which):
        return np.broadcast_to(C('#ffcc00'), u.shape + (3,)).copy()


class PaletteTang(Species):
    name = 'bluetang'
    thick = 0.36
    width, height = 380, 250
    profile = [(0, 0, 0), (0.02, 0.04, 0.04), (0.08, 0.11, 0.09), (0.20, 0.17, 0.15),
               (0.38, 0.19, 0.17), (0.56, 0.16, 0.14), (0.70, 0.10, 0.09), (0.80, 0.05, 0.05),
               (0.83, 0.045, 0.045)]
    peduncle = 0.82
    tail_spread = 0.14
    tail_fork = 0.10
    dorsal = [(0.18, 0), (0.24, 0.07), (0.50, 0.075), (0.74, 0.05), (0.80, 0)]
    anal = [(0.40, 0), (0.46, 0.06), (0.66, 0.055), (0.79, 0)]
    pectoral = (0.27, -0.03, 0.12, 0.05)
    eye = (0.12, 0.05, 0.026)
    iris = '#1a1a1a'

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#1846d8'), C('#3f8cff'), smoothstep(0.7, -0.9, nv))
        # the dark band: from behind the eye along the upper body to the tail,
        # and a dark oval loop below it with blue inside
        line = 0.075 - 0.10 * (u - 0.15) - 0.05 * np.sin((u - 0.15) * 4.5)
        stripe = smoothstep(0.030, 0.018, np.abs(y - line)) * smoothstep(0.13, 0.18, u) * smoothstep(0.80, 0.72, u)
        e = ((u - 0.50) / 0.17) ** 2 + ((y + 0.005) / 0.075) ** 2
        ring = smoothstep(1.25, 1.0, e) * smoothstep(0.45, 0.6, e)
        dark = np.maximum(stripe, ring)
        col = mix(base, C('#0b0f2b'), dark * 0.95)
        tailbase = smoothstep(0.72, 0.80, u)
        return mix(col, C('#ffd21f'), tailbase * 0.9)

    def fin_color(self, u, y, which):
        if which == 'tail':
            edge = smoothstep(0.08, 0.13, np.abs(y))
            return mix(C('#ffd21f'), C('#101533'), edge)
        if which == 'pectoral':
            return np.broadcast_to(C('#ffd84a'), u.shape + (3,)).copy()
        return np.broadcast_to(C('#0d143a'), u.shape + (3,)).copy()

    def fin_edge(self):
        return '#62a8ff'


class Clownfish(Species):
    name = 'clown'
    thick = 0.48
    width, height = 280, 190
    profile = [(0, 0, 0), (0.02, 0.05, 0.05), (0.08, 0.12, 0.10), (0.22, 0.17, 0.15),
               (0.40, 0.17, 0.155), (0.60, 0.13, 0.12), (0.74, 0.08, 0.075), (0.80, 0.07, 0.07)]
    peduncle = 0.79
    tail_spread = 0.13
    tail_fork = -0.25
    dorsal = [(0.22, 0), (0.28, 0.09), (0.38, 0.07), (0.44, 0.045), (0.50, 0.08), (0.66, 0.08), (0.75, 0)]
    anal = [(0.48, 0), (0.54, 0.08), (0.66, 0.08), (0.74, 0)]
    pectoral = (0.30, -0.03, 0.10, 0.05)
    eye = (0.12, 0.05, 0.03)
    iris = '#e2731b'

    def _bands(self, u, y):
        b1 = 0.205 + 0.03 * np.abs(y) * 4
        bands = [(b1, 0.028), (0.50 - 0.04 * y * 3, 0.035), (0.775, 0.016)]
        white = np.zeros_like(u)
        black = np.zeros_like(u)
        for c, h in bands:
            white = np.maximum(white, band(u, c, h, 0.004))
            black = np.maximum(black, band(u, c, h + 0.012, 0.004))
        return white, black

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#f0620f'), C('#ff9a3c'), smoothstep(0.6, -0.8, nv))
        white, black = self._bands(u, y)
        col = mix(base, C('#16100c'), black * 0.95)
        return mix(col, C('#fbfaf5'), white)

    def fin_color(self, u, y, which):
        return np.broadcast_to(C('#f26a12'), u.shape + (3,)).copy()

    def fin_edge(self):
        return '#141010'


class Angelfish(Species):
    name = 'angel'
    thick = 0.28
    width, height = 380, 330
    profile = [(0, 0, 0), (0.02, 0.04, 0.035), (0.08, 0.13, 0.10), (0.20, 0.25, 0.22),
               (0.36, 0.30, 0.28), (0.54, 0.27, 0.25), (0.68, 0.17, 0.16), (0.78, 0.07, 0.07),
               (0.81, 0.06, 0.06)]
    peduncle = 0.80
    tail_spread = 0.15
    tail_fork = -0.15
    dorsal = [(0.30, 0), (0.40, 0.06), (0.60, 0.09), (0.74, 0.08), (0.79, 0)]
    anal = [(0.40, 0), (0.50, 0.06), (0.66, 0.08), (0.78, 0)]
    pectoral = (0.30, -0.04, 0.11, 0.05)
    eye = (0.12, 0.07, 0.028)
    iris = '#d8c040'
    gill = 0.23

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#123a9a'), C('#2d68d0'), smoothstep(0.7, -0.9, nv))
        # yellow stripes running slightly diagonal along the body
        s = (y + (u - 0.2) * 0.35) * 26
        stripes = smoothstep(0.55, 0.85, np.cos(s * math.pi * 2) * 0.5 + 0.5)
        stripes *= smoothstep(0.18, 0.28, u) * smoothstep(0.80, 0.70, u)
        col = mix(base, C('#ffd23a'), stripes)
        # dark mask through the eye and a dark patch behind the gill
        mask = smoothstep(0.030, 0.018, np.abs(u - 0.12 + 0.12 * (y - 0.07)))
        col = mix(col, C('#08122e'), mask * smoothstep(-0.1, 0.0, y + 0.10))
        gill = smoothstep(0.035, 0.012, np.abs(u - 0.22)) * smoothstep(0.08, 0.0, y)
        col = mix(col, C('#0a1440'), gill)
        face = smoothstep(0.10, 0.04, u) * smoothstep(0.02, -0.04, y)
        return mix(col, C('#9fc6ff'), face * 0.8)

    def fin_color(self, u, y, which):
        if which == 'tail':
            return np.broadcast_to(C('#ffcc22'), u.shape + (3,)).copy()
        if which in ('dorsal', 'anal'):
            s = smoothstep(0.4, 0.8, np.cos((u * 40 + y * 20)) * 0.5 + 0.5)
            return mix(C('#1a3fa6'), C('#ffd23a'), s * 0.6)
        return np.broadcast_to(C('#ffe27a'), u.shape + (3,)).copy()

    def fin_edge(self):
        return '#79b8ff'


class Butterflyfish(Species):
    name = 'butterfly'
    thick = 0.28
    width, height = 330, 260
    profile = [(0, 0.01, 0.01), (0.03, 0.025, 0.02), (0.10, 0.07, 0.05), (0.20, 0.18, 0.15),
               (0.36, 0.25, 0.23), (0.54, 0.24, 0.22), (0.70, 0.15, 0.14), (0.80, 0.06, 0.06),
               (0.82, 0.055, 0.055)]
    peduncle = 0.81
    tail_spread = 0.13
    tail_fork = -0.05
    dorsal = [(0.24, 0), (0.30, 0.07), (0.52, 0.09), (0.74, 0.07), (0.80, 0)]
    anal = [(0.44, 0), (0.50, 0.06), (0.70, 0.06), (0.79, 0)]
    pectoral = (0.30, -0.03, 0.10, 0.045)
    eye = (0.15, 0.06, 0.026)
    iris = '#1a1a1a'

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#f4f1e6'), C('#ffffff'), smoothstep(0.5, -0.8, nv))
        lines = smoothstep(0.75, 0.95, np.cos(((u - 0.25) * 1.0 + np.abs(y - 0.02) * 0.9) * 90) * 0.5 + 0.5)
        lines *= smoothstep(0.20, 0.28, u) * smoothstep(0.72, 0.62, u)
        col = mix(base, C('#6a6458'), lines * 0.6)
        back = smoothstep(0.3, 0.9, nv) + smoothstep(0.62, 0.78, u)
        col = mix(col, C('#ffd21a'), np.clip(back, 0, 1))
        eyeband = band(u, 0.15 - 0.10 * (y - 0.06), 0.018, 0.004)
        col = mix(col, C('#141414'), eyeband)
        spot = np.sqrt(((u - 0.66) / 1.0) ** 2 + ((y - 0.07) / 1.0) ** 2)
        col = mix(col, C('#fbf7e8'), smoothstep(0.036, 0.030, spot))
        col = mix(col, C('#0d0d0d'), smoothstep(0.028, 0.022, spot))
        snout = smoothstep(0.08, 0.02, u)
        return mix(col, C('#f2d8a0'), snout * 0.6)

    def fin_color(self, u, y, which):
        if which == 'tail':
            return np.broadcast_to(C('#fff0b0'), u.shape + (3,)).copy()
        return np.broadcast_to(C('#ffcf1a'), u.shape + (3,)).copy()

    def fin_edge(self):
        return '#1a1a1a'


class Gramma(Species):
    name = 'gramma'
    thick = 0.50
    width, height = 220, 130
    profile = [(0, 0, 0), (0.02, 0.04, 0.04), (0.08, 0.09, 0.08), (0.24, 0.12, 0.11),
               (0.46, 0.115, 0.105), (0.66, 0.085, 0.08), (0.80, 0.055, 0.055)]
    peduncle = 0.80
    tail_spread = 0.10
    tail_fork = 0.06
    dorsal = [(0.20, 0), (0.26, 0.05), (0.60, 0.07), (0.76, 0.06), (0.80, 0)]
    anal = [(0.50, 0), (0.56, 0.05), (0.74, 0.05), (0.79, 0)]
    pectoral = (0.28, -0.02, 0.09, 0.035)
    eye = (0.10, 0.035, 0.024)
    iris = '#c8a030'

    def body_color(self, u, y, nv, top, bot):
        t = smoothstep(0.40, 0.56, u + y * 0.4)
        front = mix(C('#7a1fb8'), C('#b04ae0'), smoothstep(0.6, -0.8, nv))
        back = mix(C('#f0b400'), C('#ffd84a'), smoothstep(0.6, -0.8, nv))
        col = mix(front, back, t)
        eyeline = smoothstep(0.008, 0.002, np.abs(y - 0.035 - (u - 0.10) * 0.15)) * smoothstep(0.02, 0.05, u) * smoothstep(0.18, 0.12, u)
        return mix(col, C('#3a0a5a'), eyeline)

    def fin_color(self, u, y, which):
        t = smoothstep(0.40, 0.56, u)
        return mix(C('#8a2ad0'), C('#ffc81a'), t)


class Chromis(Species):
    name = 'chromis'
    thick = 0.45
    width, height = 170, 110
    profile = [(0, 0, 0), (0.02, 0.04, 0.035), (0.10, 0.10, 0.09), (0.28, 0.14, 0.13),
               (0.46, 0.13, 0.12), (0.64, 0.08, 0.075), (0.74, 0.045, 0.045)]
    peduncle = 0.73
    tail_spread = 0.16
    tail_fork = 0.65
    dorsal = [(0.22, 0), (0.28, 0.06), (0.52, 0.07), (0.68, 0.05), (0.72, 0)]
    anal = [(0.44, 0), (0.50, 0.05), (0.66, 0.05), (0.71, 0)]
    pectoral = (0.28, -0.03, 0.09, 0.035)
    eye = (0.11, 0.04, 0.03)
    iris = '#7fd0d0'
    rays_tail = 18

    def body_color(self, u, y, nv, top, bot):
        return mix(C('#2a9fae'), C('#9fe8e8'), smoothstep(0.7, -0.9, nv))

    def fin_color(self, u, y, which):
        return np.broadcast_to(C('#6fd6e0'), u.shape + (3,)).copy()


class Wrasse(Species):
    name = 'wrasse'
    thick = 0.62
    width, height = 380, 150
    profile = [(0, 0, 0), (0.02, 0.025, 0.025), (0.08, 0.06, 0.05), (0.22, 0.085, 0.075),
               (0.44, 0.085, 0.075), (0.66, 0.065, 0.06), (0.82, 0.04, 0.04), (0.86, 0.038, 0.038)]
    peduncle = 0.85
    tail_spread = 0.08
    tail_fork = -0.10
    dorsal = [(0.20, 0), (0.24, 0.03), (0.70, 0.035), (0.82, 0.03), (0.85, 0)]
    anal = [(0.46, 0), (0.50, 0.03), (0.78, 0.03), (0.84, 0)]
    pectoral = (0.22, -0.01, 0.08, 0.03)
    eye = (0.08, 0.025, 0.017)
    iris = '#e05050'
    rays_tail = 16

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#1fa070'), C('#7fe0b0'), smoothstep(0.6, -0.9, nv))
        mid = smoothstep(0.012, 0.004, np.abs(y - 0.005 + 0.02 * np.sin(u * 9)))
        low = smoothstep(0.010, 0.004, np.abs(y + 0.035 + 0.01 * np.sin(u * 7 + 1)))
        col = mix(base, C('#ff6aa0'), np.maximum(mid, low) * smoothstep(0.05, 0.12, u))
        head = smoothstep(0.20, 0.10, u)
        col = mix(col, C('#2b6fe0'), head * 0.7)
        return col

    def fin_color(self, u, y, which):
        if which == 'tail':
            return np.broadcast_to(C('#ff8ab0'), u.shape + (3,)).copy()
        return mix(C('#2fc090'), C('#ff7aa8'), 0.4 * np.ones_like(u))



class Barracuda(Species):
    name = 'barracuda'
    width, height = 620, 170
    thick = 0.70
    profile = [(0, 0, 0), (0.015, 0.012, 0.016), (0.06, 0.030, 0.034), (0.16, 0.050, 0.050),
               (0.34, 0.058, 0.055), (0.55, 0.050, 0.047), (0.74, 0.030, 0.028), (0.84, 0.020, 0.020),
               (0.86, 0.019, 0.019)]
    peduncle = 0.855
    tail_spread = 0.085
    tail_fork = 0.55
    dorsal = [(0.38, 0), (0.40, 0.045), (0.43, 0.035), (0.46, 0)]
    dorsal2 = [(0.66, 0), (0.68, 0.030), (0.71, 0.022), (0.73, 0)]
    anal = [(0.67, 0), (0.69, 0.028), (0.72, 0.020), (0.74, 0)]
    pectoral = (0.20, -0.01, 0.06, 0.018)
    eye = (0.075, 0.012, 0.012)
    iris = '#c8c090'
    gill = 0.15
    rays = False

    def body_color(self, u, y, nv, top, bot):
        base = mix(C('#3a4a52'), C('#c8d2d6'), smoothstep(0.55, -0.1, nv))
        base = mix(base, C('#f2f5f4'), smoothstep(-0.2, -0.8, nv))
        # dark slanted bars on the upper body
        bars = smoothstep(0.35, 0.8, np.cos((u * 60 - y * 25) * 1.0) * 0.5 + 0.5)
        bars *= smoothstep(0.0, 0.5, nv) * smoothstep(0.20, 0.30, u) * smoothstep(0.82, 0.72, u)
        col = mix(base, C('#1f2a30'), bars * 0.55)
        # scattered black spots toward the tail on the belly side
        spots = smoothstep(0.75, 0.9, np.sin(u * 230) * np.sin(y * 260 + u * 40))
        spots *= smoothstep(0.55, 0.75, u) * smoothstep(0.1, -0.5, nv)
        return mix(col, C('#151a1c'), spots * 0.8)

    def fin_color(self, u, y, which):
        if which == 'tail':
            return np.broadcast_to(C('#3a4448'), u.shape + (3,)).copy()
        return np.broadcast_to(C('#4a5458'), u.shape + (3,)).copy()


class ReefShark(Species):
    name = 'shark'
    width, height = 760, 300
    thick = 0.85
    profile = [(0, 0.0, 0.0), (0.008, 0.013, 0.008), (0.035, 0.036, 0.023), (0.09, 0.062, 0.047),
               (0.18, 0.081, 0.066), (0.30, 0.092, 0.077), (0.45, 0.082, 0.064), (0.60, 0.054, 0.042),
               (0.70, 0.032, 0.026), (0.745, 0.022, 0.020)]
    skin = {'rough': 0.62, 'coat': 0.04, 'bump': 0.10, 'bumpscale': 700, 'sss': 0.04,
            'translucency': 0.06, 'fin_thick': 0.007, 'spec': 0.25}
    mottle = 0.13
    peduncle = 0.74
    tail_spread = 0.10
    tail_fork = 0.45
    tail_upper = 1.75
    tail_lower = 0.80
    tail_lower_len = 0.55
    dorsal = [(0.30, 0), (0.335, 0.075), (0.37, 0.140), (0.385, 0.128), (0.40, 0.06), (0.43, 0)]
    dorsal2 = [(0.62, 0), (0.635, 0.030), (0.65, 0.022), (0.665, 0)]
    anal = [(0.615, 0), (0.63, 0.028), (0.645, 0.020), (0.66, 0)]
    pectoral = (0.235, -0.055, 0.145, 0.072)
    pectoral_angle = -30
    pectoral_tri = True
    eye = (0.072, 0.018, 0.0125)
    iris = '#2c3230'
    gill = 0.20
    rays = False
    scales = False
    rays_tail = 1

    def body_color(self, u, y, nv, top, bot):
        # bronze-gray back fading through a soft wavy line into a white belly
        wave = 0.025 * np.sin(u * 23) + 0.012 * np.sin(u * 71 + 1.3)
        upper = mix(C('#5d5a50'), C('#86837a'), smoothstep(0.95, 0.0, nv))
        col = mix(upper, C('#e9e6de'), smoothstep(-0.02 + wave, -0.34 + wave, nv))
        # a faint pale flank streak, as many reef sharks have
        streak = smoothstep(0.05, 0.0, np.abs(nv + 0.12 - 0.3 * (u - 0.5))) * smoothstep(0.45, 0.55, u) * smoothstep(0.72, 0.62, u)
        col = mix(col, C('#d8d4ca'), streak * 0.5)
        # five gill slits, soft
        for k in range(5):
            gx = 0.170 + k * 0.0135
            col = mix(col, C('#4e4b44'), 0.45 * smoothstep(0.0020, 0.0007, np.abs(u - gx - nv * 0.012)) *
                      smoothstep(0.38, 0.22, np.abs(nv + 0.05)))
        # mouth line under the snout
        mouth = smoothstep(0.004, 0.0015, np.abs(nv + 0.80 - 2.5 * (u - 0.09) ** 2 * 0)) * smoothstep(0.035, 0.05, u) * smoothstep(0.125, 0.10, u)
        col = mix(col, C('#3a3732'), mouth * 0.6)
        # darker snout tip
        return mix(col, C('#4a473f'), smoothstep(0.03, 0.0, u) * 0.5)

    def fin_color(self, u, y, which):
        return np.broadcast_to(C('#6c695f'), u.shape + (3,)).copy()

    def tip_dark(self):
        return True


ALL = [YellowTang(), PaletteTang(), Clownfish(), Angelfish(), Butterflyfish(),
       Gramma(), Chromis(), Wrasse(), Barracuda(), ReefShark()]


# ---------------------------------------------------------------- renderer

def render_frame(sp, phase, ss=3):
    """One frame of the swim cycle at phase 0..2pi -> PIL RGBA (facing left)."""
    W, H = sp.width * ss, sp.height * ss
    L = W * (1 - 2 * sp.pad)
    px = np.arange(W, dtype=np.float32) + 0.5
    py = np.arange(H, dtype=np.float32) + 0.5
    PX, PY = np.meshgrid(px, py)
    u0 = (PX - W * sp.pad) / L
    y = (H / 2 - PY) / L

    # body sits a little off-center vertically so tall fins fit
    tops = [p[1] for p in sp.profile]
    bots = [p[2] for p in sp.profile]
    y = y + (max(tops) - max(bots)) * 0.25

    theta = 0.62 * math.sin(phase)                  # tail sweep angle
    fore = max(0.55, math.cos(theta * 1.3))         # its foreshortening
    xp = sp.peduncle
    u = np.where(u0 > xp, xp + (u0 - xp) / fore, u0)
    # the rear body swings too: a little foreshortening behind the middle
    rear = 1 - 0.035 * (1 - math.cos(theta))
    u = np.where((u0 > 0.55) & (u0 <= xp), 0.55 + (u0 - 0.55) / rear, u)
    u = np.where(u0 > xp, np.maximum(u, xp + (u0 - xp) / fore), u)

    pu = [p[0] for p in sp.profile]
    top = spline(list(zip(pu, tops)), np.clip(u, 0, pu[-1]))
    bot = spline(list(zip(pu, bots)), np.clip(u, 0, pu[-1]))
    top = np.maximum(top, 0.0)
    bot = np.maximum(bot, 0.0)
    r = np.maximum((top + bot) / 2, 1e-4)
    c = (top - bot) / 2
    nv = (y - c) / r

    body = (u >= 0) & (u <= pu[-1]) & (np.abs(nv) <= 1)
    alpha = np.zeros(u.shape, np.float32)
    rgb = np.zeros(u.shape + (3,), np.float32)

    edge_col = C(sp.fin_edge()) if hasattr(sp, 'fin_edge') else None

    def paint(mask, col, a):
        nonlocal rgb, alpha
        a = np.where(mask, a, 0).astype(np.float32)
        # "over" compositing, fins drawn first then body over them
        out_a = a + alpha * (1 - a)
        rgb = np.where(out_a[..., None] > 0,
                       (col * a[..., None] + rgb * (alpha * (1 - a))[..., None]) / np.maximum(out_a, 1e-6)[..., None],
                       rgb)
        alpha = out_a

    # ---- tail fin
    pc = spline(list(zip(pu, [(t - b) / 2 for t, b in zip(tops, bots)])), np.array([xp]))[0]
    ph = spline(list(zip(pu, [(t + b) / 2 for t, b in zip(tops, bots)])), np.array([xp]))[0]
    tlen = 1.0 - xp
    t = (u - (xp - 0.015)) / (tlen + 0.015)
    ry = np.abs(y - pc)
    lobe = np.where(y > pc, sp.tail_upper, sp.tail_lower) * sp.tail_spread
    spread = ph + (lobe - ph) * np.clip(t, 0, 1) ** 0.7
    rr = np.clip(ry / np.maximum(lobe, 1e-4), 0, 1)
    if sp.tail_fork >= 0:
        tedge = 1 - sp.tail_fork * (1 - rr) ** 1.3
    else:
        tedge = 1 - (-sp.tail_fork) * rr ** 2
    tail = (t >= 0) & (t <= tedge) & (ry <= spread)
    ang = np.arctan2(y - pc, u - (xp - 0.03))
    rays = 0.5 + 0.5 * np.cos(ang * sp.rays_tail) if sp.rays else np.full(u.shape, 0.8, np.float32)
    tc = sp.fin_color(u, y, 'tail')
    tshade = (0.80 + 0.20 * math.cos(theta * 1.3)) * (0.9 + 0.1 * rays)
    tcol = tc * tshade[..., None]
    if edge_col is not None:
        near = smoothstep(0.88, 1.0, t / np.maximum(tedge, 1e-3)) + smoothstep(0.85, 1.0, ry / np.maximum(spread, 1e-3))
        tcol = mix(tcol, edge_col, np.clip(near, 0, 1) * 0.8)
    ta = sp.fin_alpha * (0.70 + 0.30 * rays) * (1 - 0.35 * np.clip(t, 0, 1))
    paint(tail, tcol, ta)

    # ---- dorsal and anal fins (behind the body edge)
    for which, pts, sign in (('dorsal', sp.dorsal, 1), ('dorsal', sp.dorsal2, 1), ('anal', sp.anal, -1)):
        if not pts:
            continue
        lo, hi = pts[0][0], pts[-1][0]
        fh = spline(pts, np.clip(u, lo, hi)) * (1 + 0.07 * np.sin(phase - u * 12))
        base_edge = top if sign > 0 else -bot
        d = (y - base_edge) * sign
        inside = (u >= lo) & (u <= hi) & (d >= -0.02) & (d <= fh)
        s = u + d * 0.8
        frays = 0.5 + 0.5 * np.cos(s * 260) if sp.rays else np.full(u.shape, 0.9, np.float32)
        fc = sp.fin_color(u, y, which) * (0.88 + 0.12 * frays)[..., None]
        if edge_col is not None:
            fc = mix(fc, edge_col, smoothstep(0.72, 1.0, d / np.maximum(fh, 1e-3)) * 0.85)
        fa = sp.fin_alpha * (0.75 + 0.25 * frays) * (1 - 0.3 * np.clip(d / np.maximum(fh, 1e-3), 0, 1))
        paint(inside, fc, fa)

    # ---- body
    col = sp.body_color(u, y, nv, top, bot)
    # scales
    sc = 0.5 + 0.5 * np.sin(u * 420 + y * 300) * np.sin(u * 420 - y * 300)
    if sp.scales:
        col = col * (0.96 + 0.06 * sc)[..., None]
    ny = np.clip(nv, -1, 1)
    nz = np.sqrt(np.clip(1 - ny * ny, 0, 1))
    # the head is rounded too: lean the normal forward near the nose
    nu = -smoothstep(0.18, 0.0, u) * 0.8
    nlen = np.sqrt(nu * nu + ny * ny + nz * nz)
    Lx, Ly, Lz = -0.25, 0.75, 0.62
    diff = np.clip((nu * Lx + ny * Ly + nz * Lz) / nlen, 0, 1)
    Hx, Hy, Hz = Lx, Ly, Lz + 1
    hn = math.sqrt(Hx * Hx + Hy * Hy + Hz * Hz)
    spec = np.clip((nu * Hx + ny * Hy + nz * Hz) / (nlen * hn), 0, 1) ** 28
    shade = 0.42 + 0.68 * diff
    col = col * shade[..., None] + spec[..., None] * 0.35
    # gill cover line
    gl = smoothstep(0.006, 0.0, np.abs(u - sp.gill - 0.05 * nv * nv)) * (np.abs(nv) < 0.85)
    col = col * (1 - 0.30 * gl)[..., None]
    # rim darkening for roundness
    col = col * (1 - 0.25 * smoothstep(0.80, 1.0, np.abs(nv)))[..., None]
    bodya = np.clip((1 - np.abs(nv)) * r * L / ss * 2.0, 0, 1)   # soft edge, ~half a pixel
    paint(body, col, bodya)

    # ---- pectoral fin, over the body, flapping
    pu0, pv0, pl, pw = sp.pectoral
    flap = 0.55 + 0.45 * math.cos(phase * 2)
    if sp.pectoral_tri:
        flap = 0.85 + 0.15 * math.cos(phase)
    a_ = math.radians(sp.pectoral_angle)
    du, dv = u0 - pu0, y - pv0
    along = du * math.cos(a_) - dv * math.sin(a_)
    across = du * math.sin(a_) + dv * math.cos(a_)
    if sp.pectoral_tri:
        q = np.clip(along / pl, 0, 1)
        pec = (along >= 0) & (along <= pl) & (across <= pw * flap * (1 - q) ** 0.9) & (across >= -pw * 0.25 * (1 - q))
        pcol = sp.fin_color(u0, y, 'pectoral') * (0.75 + 0.25 * (1 - q))[..., None]
        paint(pec, pcol, np.full(u.shape, 0.97, np.float32))
    else:
        # a fan seen nearly edge-on: long and narrow, faint
        e = (along / pl - 0.5) ** 2 * 4 + (across / (pw * 0.6 * flap)) ** 2
        pec = (e <= 1) & (along >= 0)
        prays = 0.5 + 0.5 * np.cos(np.arctan2(across, along + 0.02) * 40)
        pcol = sp.fin_color(u0, y, 'pectoral') * (0.95 + 0.15 * prays)[..., None]
        paint(pec, pcol, sp.pectoral_alpha * (0.8 + 0.2 * prays) * (1 - 0.6 * np.clip(along / pl, 0, 1)))

    # ---- eye
    ex, ey, er = sp.eye
    d = np.sqrt((u0 - ex) ** 2 + (y - ey) ** 2)
    socket = d <= er * 1.18
    paint(socket, np.broadcast_to(C('#1a1a1a'), u.shape + (3,)) * 0 + rgb * 0.55, 0.9)
    iris = d <= er
    irc = C(sp.iris) * (0.7 + 0.5 * smoothstep(er, er * 0.3, d))[..., None]
    paint(iris, irc, 1.0)
    pupil = d <= er * 0.58
    paint(pupil, np.broadcast_to(C('#050505'), u.shape + (3,)), 1.0)
    hl = np.sqrt((u0 - ex + er * 0.28) ** 2 + (y - ey - er * 0.30) ** 2) <= er * 0.22
    paint(hl, np.broadcast_to(C('#ffffff'), u.shape + (3,)), 0.95)

    # mouth
    mouth = (u0 >= 0.0) & (u0 <= 0.03) & (np.abs(y - (c - r * 0.05)) < 0.004) & body
    paint(mouth, np.broadcast_to(C('#2a1a10'), u.shape + (3,)), 0.6)

    return to_rgba_image(rgb, alpha, ss)


FRAMES = 12


def render_species(sp, ss=3):
    return [render_frame(sp, 2 * math.pi * k / FRAMES, ss) for k in range(FRAMES)]

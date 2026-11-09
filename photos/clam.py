"""The giant clam on the tank floor, from a CC0 photo ("Living giant clam
(Tridacna gigas), Waikiki Aquarium", Wikimedia Commons).

    python photos/clam.py

Writes work/clam/clam_NN.png: 16 frames from fully open (0) to closed (15).
Closing: the mantle lips over the shell edge draw down toward the shell and
the gape between them darkens.  The channel plays a slow breathing pulse on
the first frames and now and then closes it quickly and reopens it slowly.
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'orig', 'clam_c5.jpg')
OUT = os.path.join(HERE, '..', 'work', 'clam')
FRAMES = 16


def main():
    from rembg import remove, new_session
    from prepare import largest_blob
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(SRC).convert('RGB')
    cut = largest_blob(remove(im, session=new_session('isnet-general-use'), post_process_mask=True))
    cut = cut.crop(cut.getchannel('A').point(lambda v: 255 if v > 30 else 0).getbbox())
    a = np.asarray(cut, np.float32) / 255
    a[..., 3] = np.clip((a[..., 3] - 0.3) / 0.7, 0, 1)
    H, W = a.shape[:2]
    base = 0.70 * H                 # about where the shell's thick lower part begins
    for f in range(FRAMES):
        c = f / (FRAMES - 1)        # 0 open .. 1 closed
        squash = 1 - 0.38 * c       # the mantle above the base draws down
        out = np.zeros_like(a)
        ys = np.arange(H, dtype=np.float32)
        # destination row y takes source row: above the base, stretched from the base upward
        src_y = np.where(ys < base, base - (base - ys) / squash, ys)
        valid = src_y >= 0
        sy = np.clip(src_y, 0, H - 1)
        y0 = np.floor(sy).astype(int)
        y1 = np.minimum(y0 + 1, H - 1)
        t = (sy - y0)[:, None, None]
        rows = a[y0] * (1 - t) + a[y1] * t
        rows[~valid] = 0
        out = rows
        # the gape darkens as the lips come together (the middle band of the mantle)
        band = np.exp(-((ys - (base - 0.10 * H * (1 - c))) / (0.12 * H)) ** 2)[:, None]
        out[..., :3] *= (1 - 0.45 * c * band)[..., None] if out.ndim == 3 else 1
        Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8), 'RGBA').save(os.path.join(OUT, 'clam_%02d.png' % f))
    print('clam', W, H)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, HERE)
    main()

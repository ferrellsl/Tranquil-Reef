"""The moray from its photo: flipped so it leans out of the cave to the right,
with a slow sway of the head (24 frames, looping)."""
import math
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def main(outdir, frames=24, width=820):
    im = Image.open(os.path.join(HERE, 'cut', 'moray.png')).convert('RGBA').transpose(Image.FLIP_LEFT_RIGHT)
    im = im.resize((width, int(width * im.height / im.width)), Image.LANCZOS)
    pad = 40
    base = Image.new('RGBA', (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    base.paste(im, (pad, pad))
    os.makedirs(outdir, exist_ok=True)
    # sway about the lower left, where the body comes out of the hole
    pivot = (pad + int(im.width * 0.15), pad + im.height)
    for k in range(frames):
        a = 1.8 * math.sin(2 * math.pi * k / frames)
        fr = base.rotate(a, resample=Image.BICUBIC, center=pivot)
        fr.save(os.path.join(outdir, 'moray_%02d.png' % k))


if __name__ == '__main__':
    main(sys.argv[1])

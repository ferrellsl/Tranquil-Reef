"""Downloads the chosen public-domain / CC0 photos, cuts the animal out of
its background (rembg) and writes photos/cut/<key>.png plus CREDITS.md.

    python photos/prepare.py

The choices (candidate lists from contact.py) are in CHOSEN.  Each photo's
license was checked through the Commons API; CREDITS.md records author,
license and source page for every one.
"""
import io
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_photos as fp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(HERE, 'cand')
ORIG = os.path.join(HERE, 'orig')
CUT = os.path.join(HERE, 'cut')

CHOSEN = {
    # key: (candidate list, index, flip so the head is on the left, rotate degrees ccw, keep largest blob)
    'yellowtang': ('yellowtang', 3, False, 0, True),
    'bluetang':   ('bluetang', 2, True, 18, True),
    'clown':      ('clown', 14, False, 0, True),
    'angel':      ('angel', 14, True, 0, True),
    'butterfly':  ('butterfly', 1, True, 0, True),
    'queenangel': ('angel', 21, True, 0, True),
    'chromis':    ('chromis', 6, False, 0, True),
    'wrasse':     ('wrasse', 0, False, 0, True),
    'barracuda':  ('barracuda', 0, True, 0, True),
    'shark':      ('shark', 3, False, 0, True),
    'moray':      ('moray', 2, False, 0, True),
}


# parts of a photo to cut away before the background removal, as fractions (left, top, right, bottom)
KEEP = {'barracuda': (0.0, 0.0, 1.0, 0.56)}


def largest_blob(im):
    """Keep only the biggest connected shape of the cutout (drops bits of reef)."""
    import numpy as np
    from scipy import ndimage
    a = np.asarray(im.getchannel('A'))
    lab, n = ndimage.label(a > 40)
    if n <= 1:
        return im
    sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
    keep = ndimage.binary_dilation(lab == (1 + int(np.argmax(sizes))), iterations=2)
    arr = np.asarray(im).copy()
    arr[..., 3] = np.where(keep, arr[..., 3], 0)
    return Image.fromarray(arr, 'RGBA')


def strip_html(s):
    import re
    return re.sub(r'<[^>]+>', '', s or '').strip()


def main(keys):
    from rembg import remove, new_session
    session = new_session('isnet-general-use')
    os.makedirs(ORIG, exist_ok=True)
    os.makedirs(CUT, exist_ok=True)
    credits = []
    for key, (lst, idx, flip, rot, blob) in CHOSEN.items():
        c = json.load(open(os.path.join(CAND, lst + '.json')))[idx]
        credits.append((key, c))
        if keys and key not in keys:
            continue
        src = os.path.join(ORIG, key + '.jpg')
        if not os.path.exists(src):
            data = fp.fetch(c['url'])
            Image.open(io.BytesIO(data)).convert('RGB').save(src, quality=95)
        im = Image.open(src).convert('RGB')
        if max(im.size) > 2400:
            im.thumbnail((2400, 2400), Image.LANCZOS)
        if key in KEEP:
            l, t, r, b = KEEP[key]
            im = im.crop((int(l * im.width), int(t * im.height), int(r * im.width), int(b * im.height)))
        cut = remove(im, session=session, post_process_mask=True)
        if blob:
            cut = largest_blob(cut)
        if rot:
            cut = cut.rotate(rot, resample=Image.BICUBIC, expand=True)
        if flip:
            cut = cut.transpose(Image.FLIP_LEFT_RIGHT)      # every fish faces left, as the renderer expects
        cut = cut.crop(cut.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox())
        cut.save(os.path.join(CUT, key + '.png'))
        print(key, cut.size, c['license'])
    with open(os.path.join(HERE, '..', 'CREDITS.md'), 'w', encoding='utf-8') as f:
        f.write('# Photo credits\n\nThe fish are textured with these photographs, all in the public domain '
                'or released under CC0, from Wikimedia Commons:\n\n')
        f.write('| Animal | Photo | Author | License |\n|---|---|---|---|\n')
        for key, c in credits:
            f.write('| %s | [%s](%s) | %s | %s |\n' % (key, c['title'].replace('File:', ''), c['page'],
                                                   strip_html(c['artist']) or 'unknown', c['license']))
        f.write('\nRock and sand surfaces: CC0 textures from [Poly Haven](https://polyhaven.com).\n')


if __name__ == '__main__':
    main(sys.argv[1:])

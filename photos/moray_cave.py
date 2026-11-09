"""The moray's cave, from a public-domain NOAA photo (Florida Keys National
Marine Sanctuary, "FKNMS Moray eel", goldentail moray in a hole).

    python photos/moray_cave.py

Writes work/moraycave/:
    back.png    the cave and the rock round it, with the eel taken out (the hole filled in)
    front.png   the rock that lies in front of the eel (it backs in behind this) and the
                darkness of the hole, as an overlay
    eel.png     the eel, cut out, head on the right
    meta.json   where the eel sat in the patch
and photos/cut/moray.png (the eel, head on the left, for inflate.py / moray3d.py).
"""
import json
import os

import cv2
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'orig', 'moray_c27.jpg')
OUT = os.path.join(HERE, '..', 'work', 'moraycave')
CROP = (110, 180, 1130, 780)            # the eel, its hole and the reef round them


def main():
    from rembg import remove, new_session
    os.makedirs(OUT, exist_ok=True)
    photo = Image.open(SRC).convert('RGB').crop(CROP)
    W, H = photo.size
    # the eel: the background remover finds the animal; keep its biggest piece
    cut = remove(photo, session=new_session('isnet-general-use'), post_process_mask=True)
    a = np.asarray(cut.getchannel('A'))
    from scipy import ndimage
    lab, n = ndimage.label(a > 100)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        keep = lab == (1 + int(np.argmax(sizes)))
        a = np.where(ndimage.binary_dilation(keep, iterations=2), a, 0).astype(np.uint8)
    eel_mask = a > 100
    box = Image.fromarray(a).getbbox()
    eel = photo.convert('RGBA')
    eel.putalpha(Image.fromarray(a))
    eel = eel.crop(box)
    eel.save(os.path.join(OUT, 'eel.png'))
    eel.transpose(Image.FLIP_LEFT_RIGHT).save(os.path.join(HERE, 'cut', 'moray.png'))

    # the cave without the eel: fill where it was from the dark hole round it
    rgb = np.asarray(photo)
    hole = ndimage.binary_dilation(eel_mask, iterations=6).astype(np.uint8) * 255
    filled = cv2.inpaint(rgb[..., ::-1].copy(), hole, 9, cv2.INPAINT_TELEA)[..., ::-1].astype(np.float32)
    # where the eel was is the inside of the hole: deep brown-black, fading in from its edges
    lum = rgb.mean(axis=2) / 255
    inner = ndimage.gaussian_filter(hole.astype(np.float32) / 255, 10)
    cave = np.array([16, 11, 8], np.float32)
    filled = (filled * (1 - inner[..., None]) + cave * inner[..., None]).astype(np.uint8)
    back = Image.fromarray(filled, 'RGB')

    # the patch fades into whatever reef is around it
    yy, xx = np.mgrid[0:H, 0:W]
    e = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    rough = ndimage.gaussian_filter(np.random.default_rng(4).normal(0, 1, (H, W)), 18)
    rough = rough / (np.abs(rough).max() + 1e-6)
    feather = np.clip((1.0 - e + 0.45 * rough) / 0.30, 0, 1)      # an irregular edge, not an oval
    back_rgba = back.convert('RGBA')
    back_rgba.putalpha(Image.fromarray((feather * 255).astype(np.uint8)))
    back_rgba.save(os.path.join(OUT, 'back.png'))

    # in front of the eel: the photo's rock where the eel is not, and the dark of the hole.
    # (the eel slides left, into the hole; the rock left of and below it covers it)
    darkness = ndimage.gaussian_filter((lum < 0.18).astype(np.float32), 4)
    rock = (~ndimage.binary_dilation(eel_mask, iterations=1)) & (darkness < 0.5)
    front = np.zeros((H, W, 4), np.uint8)
    front[..., :3] = rgb
    alpha = rock.astype(np.float32) * feather
    # only the rock left of the eel's head matters (the eel never moves right of where it was)
    head_x = box[2]
    alpha *= np.clip((head_x - 40 - xx) / 60.0, 0, 1)
    dark_a = darkness * 0.95 * np.clip((head_x - 120 - xx) / 120.0, 0, 1)
    front[..., :3] = np.where((dark_a > alpha)[..., None], 5, front[..., :3])
    front[..., 3] = (np.maximum(alpha, dark_a) * 255).astype(np.uint8)
    Image.fromarray(front, 'RGBA').save(os.path.join(OUT, 'front.png'))
    json.dump({'size': [W, H], 'eel_box': list(box)}, open(os.path.join(OUT, 'meta.json'), 'w'))
    print('eel', box, 'patch', W, H)


if __name__ == '__main__':
    main()

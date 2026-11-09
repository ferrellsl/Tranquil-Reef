"""Makes tranquil_reef.ico from the channel icon (run after build.py)."""
import os
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, '..', 'channel', 'images', 'icon_fhd.png')
im = Image.open(src).convert('RGBA')
side = min(im.size)
im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
im.save(os.path.join(here, 'tranquil_reef.ico'), sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

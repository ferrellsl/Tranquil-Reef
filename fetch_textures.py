"""Downloads the CC0 surface textures the renders use, from Poly Haven.

    python fetch_textures.py

Poly Haven assets are CC0 (public domain): https://polyhaven.com/license
They are fetched at build time rather than kept in the repository.
"""
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(ROOT, 'textures')
UA = {'User-Agent': 'TranquilReef-build'}

TEXTURES = ['coast_sand_rocks_02', 'rock_04', 'lichen_rock', 'coral_ground_02', 'dense_sand', 'coral_gravel']
HIRES = {'coast_sand_rocks_02', 'rock_04', 'lichen_rock'}   # big on screen: 4k
MAPS = {'Diffuse': 'diff', 'nor_gl': 'nor', 'Rough': 'rough', 'Displacement': 'disp'}
RES = '2k'


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r:
        return r.read()


def main():
    os.makedirs(DEST, exist_ok=True)
    for name in TEXTURES:
        files = json.loads(get('https://api.polyhaven.com/files/' + name))
        for key, short in MAPS.items():
            if key not in files:
                continue
            fmt = files[key]['4k' if name in HIRES and '4k' in files[key] else RES]
            ext = 'jpg' if 'jpg' in fmt else 'png'
            path = os.path.join(DEST, '%s_%s.%s' % (name, short, ext))
            if os.path.exists(path):
                continue
            print('  ', os.path.basename(path))
            with open(path, 'wb') as f:
                f.write(get(fmt[ext]['url']))
    print('textures in', DEST)


if __name__ == '__main__':
    main()

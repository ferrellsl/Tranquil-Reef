"""Downloads the chosen public-domain / CC0 coral photos, cuts each coral out
(rembg) and writes photos/coralcut/<key>.png; adds them to CORAL-CREDITS.md.

    python photos/prepare_corals.py [keys...]
"""
import io
import json
import re
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_photos as fp  # noqa: E402
from prepare import largest_blob, strip_html  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(HERE, 'cand')
ORIG = os.path.join(HERE, 'coralorig')
CUT = os.path.join(HERE, 'coralcut')

# key: (candidate list, index, kind)  -  kind says where it grows: 'top' on the rock, 'tall' sticks up, 'face' on a side
CHOSEN = {
    'brain1': ('c_brain', 0, 'top'), 'brain2': ('c_brain', 25, 'top'), 'brain3': ('c_brain', 32, 'top'),
    'brain4': ('c_brain', 34, 'top'), 'brain5': ('c_brain', 36, 'top'), 'brain6': ('c_brain', 19, 'top'),
    'elkhorn1': ('c_elkhorn', 1, 'tall'), 'elkhorn2': ('c_elkhorn', 12, 'tall'), 'elkhorn3': ('c_elkhorn', 23, 'tall'),
    'elkhorn4': ('c_elkhorn', 25, 'tall'),
    'fan1': ('c_fan', 1, 'tall'),
    'bubble1': ('c_bubble', 3, 'top'), 'bubble2': ('c_bubble', 4, 'top'),
    'pillar1': ('c_pillar', 1, 'tall'), 'pillar2': ('c_pillar', 2, 'tall'),
    'finger1': ('c_finger', 8, 'top'), 'finger2': ('c_finger', 26, 'top'), 'finger3': ('c_finger', 27, 'top'),
    'finger4': ('c_finger', 20, 'tall'),
    'sponge1': ('c_sponge', 0, 'tall'), 'sponge2': ('c_sponge', 2, 'tall'), 'sponge3': ('c_sponge', 5, 'tall'),
    'sponge4': ('c_sponge', 9, 'tall'), 'sponge5': ('c_sponge', 31, 'top'),
    'plate1': ('c_plate', 4, 'face'), 'plate2': ('c_plate', 0, 'face'),
    'staghorn1': ('c_staghorn', 0, 'tall'),
    'anemone1': ('c_anemone', 1, 'top'),
    'shell1': ('s_shell', 14, 'floor'), 'shell2': ('s_shell', 21, 'floor'), 'shell3': ('s_shell', 26, 'floor'),
    'shell4': ('s_shell', 29, 'floor'),
}


def main(keys):
    from rembg import remove, new_session
    session = new_session('isnet-general-use')
    os.makedirs(ORIG, exist_ok=True)
    os.makedirs(CUT, exist_ok=True)
    credits, kinds = [], {}
    for key, (lst, idx, kind) in CHOSEN.items():
        c = json.load(open(os.path.join(CAND, lst + '.json')))[idx]
        credits.append((key, c))
        kinds[key] = kind
        if keys and key not in keys:
            continue
        src = os.path.join(ORIG, key + '.jpg')
        if not os.path.exists(src):
            # a 1280-pixel thumbnail (the thumbnail server is far less strict than the originals')
            # (only the standard thumbnail widths are served)
            size = max([w for w in (330, 500, 960, 1280) if w < c['w']] or [330])
            url = re.sub(r'/(\d+)px-', '/%dpx-' % size, c['thumb'])
            Image.open(io.BytesIO(fp.fetch(url))).convert('RGB').save(src, quality=95)
        im = Image.open(src).convert('RGB')
        if max(im.size) > 2000:
            im.thumbnail((2000, 2000), Image.LANCZOS)
        cut = largest_blob(remove(im, session=session, post_process_mask=True))
        box = cut.getchannel('A').point(lambda v: 255 if v > 20 else 0).getbbox()
        if not box:
            print(key, 'nothing found')
            continue
        cut = cut.crop(box)
        cut.save(os.path.join(CUT, key + '.png'))
        print(key, cut.size, c['license'])
    json.dump(kinds, open(os.path.join(CUT, 'kinds.json'), 'w'), indent=1)
    with open(os.path.join(HERE, '..', 'CORAL-CREDITS.md'), 'w', encoding='utf-8') as f:
        f.write('# Coral photo credits\n\nThe corals are cut from these photographs, all public domain or CC0, '
                'from Wikimedia Commons:\n\n| Coral | Photo | Author | License |\n|---|---|---|---|\n')
        for key, c in credits:
            f.write('| %s | [%s](%s) | %s | %s |\n' % (key, c['title'].replace('File:', ''), c['page'],
                                                   strip_html(c['artist']) or 'unknown', c['license']))


if __name__ == '__main__':
    main(sys.argv[1:])

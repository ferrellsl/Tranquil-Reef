"""Candidate photos per species -> photos/cand/<key>.json and a numbered
contact sheet photos/cand/<key>.jpg for choosing."""
import io
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import find_photos as fp  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'cand')

TERMS = {
    'yellowtang': ['Zebrasoma flavescens'],
    'bluetang': ['Paracanthurus hepatus', 'Acanthurus coeruleus'],
    'clown': ['Amphiprion ocellaris', 'Amphiprion percula', 'clownfish'],
    'angel': ['Pomacanthus imperator', 'Pomacanthus', 'Holacanthus ciliaris', 'Pygoplites diacanthus'],
    'butterfly': ['Chaetodon auriga', 'Chaetodon', 'butterflyfish'],
    'gramma': ['Gramma loreto', 'royal gramma'],
    'chromis': ['Chromis cyanea', 'Chromis viridis', 'Chromis'],
    'wrasse': ['Thalassoma bifasciatum', 'Thalassoma lunare', 'Thalassoma'],
    'barracuda': ['Sphyraena barracuda', 'great barracuda'],
    'shark': ['Carcharhinus melanopterus', 'Carcharhinus amblyrhynchos', 'Triaenodon obesus', 'reef shark'],
    'moray': ['Gymnothorax funebris', 'Gymnothorax javanicus', 'Gymnothorax moringa', 'moray eel'],
    # corals
    'c_brain': ['Diploria labyrinthiformis', 'Pseudodiploria strigosa', 'Platygyra', 'brain coral'],
    'c_staghorn': ['Acropora cervicornis', 'staghorn coral'],
    'c_elkhorn': ['Acropora palmata', 'elkhorn coral'],
    'c_fan': ['Gorgonia ventalina', 'sea fan coral', 'Gorgonia flabellum'],
    'c_bubble': ['Plerogyra sinuosa', 'bubble coral'],
    'c_leather': ['Sarcophyton', 'leather coral', 'Sinularia'],
    'c_plate': ['Turbinaria reniformis', 'Montipora capricornis', 'Agaricia', 'plate coral'],
    'c_pillar': ['Dendrogyra cylindrus', 'pillar coral'],
    'c_finger': ['Porites porites', 'finger coral', 'Porites furcata'],
    'c_anemone': ['Heteractis magnifica', 'Stichodactyla', 'Condylactis gigantea', 'sea anemone'],
    'c_sponge': ['Aplysina fistularis', 'tube sponge', 'Callyspongia vaginalis', 'Xestospongia muta'],
    'c_whip': ['Plexaura', 'sea rod coral', 'Pseudopterogorgia', 'sea plume'],
    'c_star': ['Orbicella', 'Montastraea cavernosa', 'boulder star coral'],
    'c_clam': ['Tridacna', 'giant clam'],
    's_shell': ['Lobatus gigas shell', 'Cypraea tigris shell', 'cowrie shell', 'scallop shell', 'conch shell', 'Murex shell', 'cockle shell', 'Strombus shell'],
}


def get(url):
    return fp.fetch(url)


def main(keys):
    os.makedirs(OUT, exist_ok=True)
    for key in keys:
        if os.path.exists(os.path.join(OUT, key + '.jpg')):
            continue
        seen, cands = set(), []
        for term in TERMS[key]:
            for r in fp.search(term, limit=50):
                if r['title'] in seen or not r['thumb']:
                    continue
                seen.add(r['title'])
                cands.append(r)
        cands = cands[:40]
        json.dump(cands, open(os.path.join(OUT, key + '.json'), 'w'), indent=1)
        tw, th, cols = 300, 200, 6
        rows = max(1, -(-len(cands) // cols))
        sheet = Image.new('RGB', (cols * tw, rows * th), (30, 30, 30))
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(cands):
            try:
                im = Image.open(io.BytesIO(get(r['thumb']))).convert('RGB')
            except Exception:
                continue
            im.thumbnail((tw - 6, th - 22))
            x, y = (i % cols) * tw, (i // cols) * th
            sheet.paste(im, (x + 3, y + 20))
            d.text((x + 4, y + 3), '%d  %dx%d' % (i, r['w'], r['h']), fill=(255, 255, 0))
        sheet.save(os.path.join(OUT, key + '.jpg'), quality=85)
        print(key, len(cands))


if __name__ == '__main__':
    main(sys.argv[1:] or list(TERMS))

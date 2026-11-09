"""Searches Wikimedia Commons for public-domain / CC0 photos of each species
and lists candidates with their license, author and size.

    python photos/find_photos.py "Zebrasoma flavescens" [more terms...]

Only files whose license is public domain (e.g. US-government NOAA/NPS/USFWS
work) or CC0 are listed.
"""
import json
import ssl
import sys
import urllib.parse
import urllib.request

API = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'TranquilReef-build/1.0 (open-source screensaver; photo license check)'}
OK = ('public domain', 'cc0', 'pd-')
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CTX = None


def fetch(url, tries=10):
    """GET with a pause before each request and backing off when told to slow down."""
    import time
    import urllib.error
    wait = 6.0
    for _ in range(tries):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            wait = min(wait * 2.0, 150)
        except (urllib.error.URLError, OSError):
            wait = min(wait * 2.0, 60)       # the network dropped for a moment
    raise RuntimeError('rate limited: ' + url)


def api(**params):
    params.update(format='json')
    return json.loads(fetch(API + '?' + urllib.parse.urlencode(params)))


def search(term, limit=40):
    d = api(action='query', generator='search', gsrsearch='filetype:bitmap ' + term, gsrnamespace=6,
            gsrlimit=limit, prop='imageinfo', iiprop='url|size|extmetadata', iiurlwidth=480)
    out = []
    for p in (d.get('query', {}).get('pages', {}) or {}).values():
        ii = (p.get('imageinfo') or [{}])[0]
        meta = ii.get('extmetadata', {})
        lic = (meta.get('LicenseShortName', {}).get('value', '') or '').strip()
        if not any(k in lic.lower() for k in OK):
            continue
        artist = meta.get('Artist', {}).get('value', '')
        out.append({'title': p['title'], 'license': lic, 'w': ii.get('width'), 'h': ii.get('height'),
                    'url': ii.get('url'), 'thumb': ii.get('thumburl'),
                    'artist': artist[:120], 'page': ii.get('descriptionurl')})
    return out


if __name__ == '__main__':
    for term in sys.argv[1:]:
        res = search(term)
        print('==', term, len(res))
        for r in res:
            print(json.dumps(r))

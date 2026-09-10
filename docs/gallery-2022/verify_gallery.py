#!/usr/bin/env python3
"""Verify gallery integrity, metadata removal, coverage and local Markdown links."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image


def main():
    gallery = Path(__file__).resolve().parent
    repo = gallery.parents[1]
    manifest = json.loads((gallery / 'manifest.json').read_text())
    entries = manifest['media']
    assert Counter(Path(e['source']).suffix.lower() for e in entries) == manifest['source_counts']
    assert manifest['source_counts'] == {'.heic': 8, '.mp4': 6}
    assert len({e['source'] for e in entries}) == 14
    photos = [e for e in entries if e['published']]
    assert len(photos) == 8
    assert {p.name for p in gallery.glob('*.jpg')} == {e['output'] for e in photos}
    for entry in photos:
        path = gallery / entry['output']
        assert entry['source'].endswith('.HEIC')
        assert path.stat().st_size == entry['bytes'] < 800_000
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
        with Image.open(path) as image:
            image.load()
            assert image.format == 'JPEG' and image.mode == 'RGB'
            assert list(image.size) == entry['dimensions'] and max(image.size) <= 1920
            assert not image.getexif(), f'EXIF found: {path}'
            assert not any(marker == 'APP1' for marker, _ in getattr(image, 'applist')), f'EXIF/XMP APP1 found: {path}'
            assert not ({'exif', 'xmp', 'icc_profile', 'comment'} & image.info.keys())
            assert image.info.get('progressive') or image.info.get('progression')
    links = 0
    for markdown in [repo / 'README.md', gallery / 'README.md', repo / 'history.md']:
        text = markdown.read_text()
        assert '/home/' not in text
        assert text.count('```') % 2 == 0
        for label in re.findall(r'!\[([^\]]*)\]\(', text):
            assert label.strip(), 'Missing image alt text'
        for url in re.findall(r'\]\(([^)]+)\)', text):
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc:
                continue
            target = markdown.parent / unquote(parsed.path) if parsed.path else markdown
            assert target.exists(), f'Broken link: {markdown}: {url}'
            if parsed.fragment:
                content = target.read_text()
                headings = re.findall(r'^#+ (.+)$', content, flags=re.M)
                anchors = {re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings}
                assert parsed.fragment in anchors, f'Broken anchor: {url}'
            links += 1
    gallery_text = (gallery / 'README.md').read_text()
    for entry in photos:
        assert f"]({entry['output']})" in gallery_text
    assert '/home/' not in (gallery / 'manifest.json').read_text()
    assert not any(p.suffix.lower() in {'.heic', '.mov', '.mp4'} for p in gallery.iterdir())
    print(json.dumps({'photos_verified': len(photos), 'source_counts': manifest['source_counts'],
                      'jpeg_bytes': sum(e['bytes'] for e in photos),
                      'largest_jpeg_bytes': max(e['bytes'] for e in photos),
                      'local_links_verified': links, 'metadata': 'no EXIF/GPS/XMP/ICC/comments',
                      'result': 'PASS'}, indent=2))


if __name__ == '__main__':
    main()

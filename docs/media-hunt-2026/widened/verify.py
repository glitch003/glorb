#!/usr/bin/env python3
"""Recompute the widened snapshot without fetching or redistributing media."""
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent

def main():
    load = lambda name: json.loads((ROOT / name).read_text())
    sources, queries = load('sources.json'), load('queries.json')
    photos, images = load('flickr-photos.json'), load('sfgate-images.json')
    frames, candidates = load('video-frames.json'), load('lookalikes.json')
    summary = dict(
        input_source_records=sum(len(r['research_lanes']) for r in sources),
        deduplicated_source_records=len(sources),
        confirmed_2026_glorb_media=sum(r['confirmed_2026_glorb_media'] for r in sources),
        query_counts=dict(Counter(r['lane'] for r in queries)),
        unique_query_strings=len({r['query'] for r in queries}),
        query_status_counts=dict(Counter(r['status'] for r in queries)),
        result_url_occurrences=sum(len(r['result_urls']) for r in queries),
        unique_result_urls_exact=len({u for r in queries for u in r['result_urls']}),
        flickr_unique_photo_ids=len({r['id'] for r in photos}),
        flickr_unique_thumbnail_hashes=len({r['sha256'] for r in photos}),
        flickr_contact_sheets=len({r['review_batch'] for r in photos}),
        sfgate_unique_image_urls=len({r['url'] for r in images}),
        jurvetson_photos=sum(r.get('image_count_screened', 0) for r in sources if r.get('kind') == 'photo'),
        still_image_screenings=len(photos) + len(images) + sum(r.get('image_count_screened', 0) for r in sources if r.get('kind') == 'photo'),
        flickr_enlarged_checks=sum('flickr_id' in r for r in candidates),
        video_frames=len(frames),
        sampled_clips=len({r['source'] for r in frames}),
        frames_by_source=dict(Counter(r['source'] for r in frames)),
        source_status_counts=dict(Counter(r['status'] for r in sources)),
    )
    assert summary == load('summary.json')
    assert len(sources) == len({r['url'] for r in sources})
    assert len(photos) == summary['flickr_unique_photo_ids'] == summary['flickr_unique_thumbnail_hashes']
    assert len(images) == summary['sfgate_unique_image_urls']
    assert len(frames) == len({(r['source'], r['pts_seconds']) for r in frames})
    assert summary['confirmed_2026_glorb_media'] == 0
    for photo in photos:
        assert re.fullmatch(r'[0-9a-f]{64}', photo['sha256'])
        assert photo['photo_url'] == f"https://www.flickr.com/photos/flight0001/{photo['id']}/"
        assert photo['status'] == 'screened_no_match'
    for candidate in candidates:
        if 'flickr_id' in candidate:
            assert candidate['flickr_id'] in {r['id'] for r in photos}
    for source in sources:
        samples = [r for r in frames if r['source'] == source.get('id')]
        assert len(samples) == source.get('sample_count', 0)
        if samples:
            assert min(r['pts_seconds'] for r in samples) == source['sample_first_pts']
            assert max(r['pts_seconds'] for r in samples) == source['sample_last_pts']
            assert all(r['visually_inspected'] and r['interval_seconds'] == source['sample_interval_seconds'] for r in samples)
            assert all(0 <= r['pts_seconds'] < source['duration_seconds'] for r in samples)
    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and value.startswith(('http:', 'https:')):
            parsed = urlsplit(value)
            assert parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password
    links = 0
    for path in ROOT.iterdir():
        assert path.is_file() and path.suffix in {'.json', '.md', '.py'}
        if path.suffix == '.py':
            continue
        text = path.read_text()
        assert not re.search(r'/home/|/tmp/|mailto:|local_file|local_evidence|evidence_files|api_key|access_token', text)
        if path.suffix == '.json':
            walk(json.loads(text))
        else:
            for url in re.findall(r'\]\(([^)]+)\)', text):
                parsed = urlsplit(url)
                if parsed.scheme:
                    walk(url)
                else:
                    assert (path.parent / unquote(parsed.path)).exists(), url
                links += 1
    print(json.dumps({'result': 'PASS', 'markdown_links_checked': links, **summary}, indent=2))

if __name__ == '__main__':
    main()

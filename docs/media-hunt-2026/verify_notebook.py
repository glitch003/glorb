#!/usr/bin/env python3
"""Check notebook counts, schema, publication scope and relative Markdown links."""
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main():
    root = Path(__file__).resolve().parent
    repo = root.parents[1]
    load = lambda name: json.loads((root / name).read_text())
    summary = load('summary.json')
    sources = load('sources.json')
    logs = {lane: load(lane + '-queries.json') for lane in ('social', 'video')}
    assert summary['query_counts'] == {k: len(v) for k, v in logs.items()}
    queries = [r for rows in logs.values() for r in rows]
    assert summary['unique_query_strings'] == len({r['query'] for r in queries})
    for row in queries:
        assert set(row) == {'query', 'retrieved_at', 'result_urls'}
        assert datetime.fromisoformat(row['retrieved_at']).tzinfo
        assert len(row['result_urls']) == len(set(row['result_urls']))
        assert all(urlsplit(u).scheme in ('http', 'https') for u in row['result_urls'])
    assert summary['result_url_occurrences'] == sum(len(r['result_urls']) for r in queries)
    assert summary['unique_result_urls_exact'] == len({u for r in queries for u in r['result_urls']})
    assert summary['deduplicated_source_records'] == len(sources) == len({r['url'] for r in sources})
    assert summary['input_source_records'] == sum(len(r['research_lanes']) for r in sources)
    assert summary['status_counts'] == dict(Counter(r['status'] for r in sources))
    assert summary['confirmed_2026_glorb_media'] == sum(r['confirmed_2026_glorb_media'] for r in sources) == 0
    assert all(r.get('glorb_timecode') is None for r in sources)
    assert summary['reported_video_frames_sampled'] == sum(r.get('sampled_frames', 0) for r in sources)
    assert summary['reported_gallery_image_entries'] == sum(r.get('image_count', 0) for r in sources)
    assert summary['reported_unique_gallery_images'] <= summary['reported_gallery_image_entries']
    text = (root / 'README.md').read_text()
    for status, count in summary['status_counts'].items():
        assert f'| `{status}` | {count} |' in text
    for path in root.iterdir():
        if path.is_file():
            assert path.suffix in {'.json', '.md', '.py'}
            if path.suffix != '.py':
                assert not re.search(r'/home/|/tmp/|evidence_file|image_manifest|mailto:', path.read_text())
    links = 0
    for markdown in [repo / 'README.md', root / 'README.md', repo / 'docs/gallery-2026/README.md']:
        for url in re.findall(r'\]\(([^)]+)\)', markdown.read_text()):
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc:
                continue
            target = markdown.parent / unquote(parsed.path) if parsed.path else markdown
            assert target.exists(), (markdown, url)
            if parsed.fragment:
                if target.is_dir():
                    target /= 'README.md'
                headings = re.findall(r'^#+ (.+)$', target.read_text(), flags=re.M)
                anchors = {re.sub(r'[^\w\- ]', '', h.lower()).replace(' ', '-') for h in headings}
                assert parsed.fragment in anchors, url
            links += 1
    print(json.dumps({'result': 'PASS', 'queries': len(queries), 'sources': len(sources),
                      'relative_links_verified': links, 'status_counts': summary['status_counts']}, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Build metadata-free gallery JPEGs from an owner-supplied ZIP (see README)."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

import pillow_heif
from PIL import Image, ImageDraw, ImageOps


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--work-dir', type=Path, required=True,
                        help='Empty extraction directory outside the repository')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    work = args.work_dir.resolve()
    if work == repo or repo in work.parents:
        parser.error('Extraction directory must be outside the repository')
    work.mkdir(parents=True, exist_ok=False)
    args.output.mkdir(parents=True, exist_ok=True)
    pillow_heif.register_heif_opener()
    entries = []
    names = set()
    with ZipFile(args.archive) as archive:
        import shutil
        import stat
        members = archive.infolist()
        if sum(e.file_size for e in members) > shutil.disk_usage(work).free:
            raise ValueError("Insufficient extraction space")
        checked = set()
        for e in members:
            member = PurePosixPath(e.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in e.filename or stat.S_ISLNK(e.external_attr >> 16):
                raise ValueError("Unsafe archive member")
            if not e.is_dir():
                if member.name in checked:
                    raise ValueError("Duplicate basename")
                checked.add(member.name)
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            member = PurePosixPath(entry.filename)
            if member.is_absolute() or '..' in member.parts or '\\' in entry.filename:
                raise ValueError(f'Unsafe archive member: {entry.filename}')
            name = member.name
            if name in names:
                raise ValueError(f'Duplicate basename: {name}')
            names.add(name)
            target = work / name
            with archive.open(entry) as source, target.open('xb') as dest:
                import shutil
                shutil.copyfileobj(source, dest)
            entries.append({'source': name, 'source_bytes': target.stat().st_size,
                            'source_sha256': sha256(target)})
    photos = []
    for entry in sorted(entries, key=lambda item: item['source']):
        source = work / entry['source']
        if source.suffix.lower() != '.heic':
            entry['published'] = False
            continue
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
            entry['oriented_source_dimensions'] = list(image.size)
            image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
            # Fresh pixel-only image: do not copy EXIF, GPS, XMP or ICC metadata.
            clean = Image.new('RGB', image.size)
            clean.paste(image)
            filename = source.stem.lower().replace('img_', 'glorb-2022-') + '.jpg'
            output = args.output / filename
            clean.save(output, quality=82, optimize=True, progressive=True, subsampling=2)
            entry.update(published=True, output=filename, dimensions=list(clean.size),
                         bytes=output.stat().st_size, sha256=sha256(output))
            photos.append((filename, clean.copy()))
    manifest = {'credit': 'Photos supplied by the project owner; photographer not specified.',
                'collection': 'Glorb original version, 2022 (owner-supplied archive; attendance confirmed by Chris, not inferred from metadata)',
                'source_counts': dict(sorted(Counter(Path(e['source']).suffix.lower() for e in entries).items())),
                'conversion': {'Pillow': Image.__version__, 'pillow_heif': pillow_heif.__version__,
                               'max_edge': 1920, 'jpeg_quality': 82, 'progressive': True,
                               'subsampling': 2, 'metadata': 'pixel-only; EXIF/GPS/XMP/ICC omitted'},
                'media': sorted(entries, key=lambda item: item['source'])}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    sheet = Image.new('RGB', (1200, ((len(photos) + 3) // 4) * 330), '#161616')
    draw = ImageDraw.Draw(sheet)
    for i, (name, image) in enumerate(photos):
        image.thumbnail((290, 295))
        x, y = (i % 4) * 300, (i // 4) * 330
        sheet.paste(image, (x + (300-image.width)//2, y))
        draw.text((x+8, y+303), name, fill='white')
    sheet.save(work / 'contact-sheet.jpg', quality=90)
    print(json.dumps({'source_counts': manifest['source_counts'], 'photos': len(photos),
                      'jpeg_bytes': sum(e.get('bytes', 0) for e in entries),
                      'contact_sheet': str(work / 'contact-sheet.jpg')}, indent=2))


if __name__ == '__main__':
    main()

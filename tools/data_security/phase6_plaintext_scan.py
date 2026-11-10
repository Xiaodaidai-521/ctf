"""Offline exact-marker scan of an explicitly inventoried, frozen B2 snapshot.

Never prints marker values or matching snippets. ZIP/gzip content is scanned in
memory; nothing is extracted or executed. Images/PDFs and opaque/nested archives
remain unscanned, not a zero-hit claim. This is not a new PII detector or OCR.
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile


RUNTIME_CATEGORIES = frozenset(('private', 'media', 'temporary', 'executor-legacy',
    'backups', 'logs', 'evidence', 'screenshots', 'production-source'))
_OPAQUE = frozenset(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.pdf', '.7z', '.rar', '.xz', '.bz2', '.zst', '.tar'))
_ARCHIVES = frozenset(('.zip', '.xlsx', '.gz', '.tgz'))
_ENCODED_MAGIC = (b'PK\x03\x04', b'\x1f\x8b', b'\x89PNG', b'\xff\xd8\xff', b'GIF8', b'%PDF',
    b'PGDMP', b'7z\xbc\xaf', b'Rar!', b'\xfd7zXZ', b'BZh', b'\x28\xb5\x2f\xfd', b'SQLite format 3')


def _scan_stream(stream, needles, *, limit=None):
    overlap = max(len(value) for _, value in needles) - 1
    digest, previous, size, hits, prefix = hashlib.sha256(), b'', 0, set(), b''
    while chunk := stream.read(1024 * 1024):
        if not size:
            prefix = chunk[:512]
        size += len(chunk)
        if limit is not None and size > limit:
            raise ValueError('expanded-limit')
        digest.update(chunk)
        data = previous + chunk
        for name, value in needles:
            if value in data:
                hits.add(name)
        previous = data[-overlap:] if overlap else b''
    return {'bytes': size, 'sha256': digest.hexdigest(), 'marker_ids': sorted(hits),
        'encoded_content': prefix.startswith(_ENCODED_MAGIC) or prefix[257:262] == b'ustar'
            or (prefix.startswith(b'RIFF') and prefix[8:12] == b'WEBP')}


def scan_manifest(manifest, markers):
    """Inputs are an operator-owned inventory and synthetic markers, not evidence text."""
    if (type(manifest) is not dict or set(manifest) != {'schema_version', 'scope', 'targets', 'max_expanded_bytes'}
            or manifest['schema_version'] != 'ds.b2-plaintext-scan.v1'
            or manifest['scope'] not in ('runtime', 'source-only')
            or type(manifest['targets']) is not list or not manifest['targets']
            or type(manifest['max_expanded_bytes']) is not int or manifest['max_expanded_bytes'] <= 0):
        raise ValueError('invalid-manifest')
    if type(markers) is not dict or not 1 <= len(markers) <= 100:
        raise ValueError('invalid-markers')
    needles = []
    for name, value in markers.items():
        if (type(name) is not str or re.fullmatch(r'[a-z0-9-]{1,64}', name) is None or type(value) is not str
                or not 8 <= len(value.encode('utf-8')) <= 4096):
            raise ValueError('invalid-marker')
        for encoded in {value.encode('utf-8'), value.encode('utf-16-le'), value.encode('utf-16-be'),
                        json.dumps(value, ensure_ascii=True)[1:-1].encode(), base64.b64encode(value.encode('utf-8'))}:
            needles.append((name, encoded))
    targets, categories = [], set()
    for target in manifest['targets']:
        if (type(target) is not dict or set(target) != {'category', 'path'}
                or target['category'] not in RUNTIME_CATEGORIES or type(target['path']) is not str):
            raise ValueError('invalid-target')
        path = Path(target['path'])
        if not path.is_absolute():
            raise ValueError('absolute-target-required')
        targets.append((target['category'], path))
        categories.add(target['category'])
    report = {'schema_version': 'ds.b2-plaintext-scan-result.v1', 'scope': manifest['scope'],
        'manifest_sha256': hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
        'marker_ids': sorted(markers), 'files': [], 'unscanned': [], 'missing_categories': [],
        'plaintext_marker_values_in_report': False, 'database_started': False, 'declared_inventory_only': True}
    if manifest['scope'] == 'runtime':
        report['missing_categories'] = sorted(RUNTIME_CATEGORIES - categories)
    elif categories != {'production-source'}:
        raise ValueError('source-only-category-mismatch')
    seen = set()
    for category, target in targets:
        candidates = []
        if target.resolve() != target:
            report['unscanned'].append({'category': category, 'reason': 'noncanonical-target'})
            continue
        if target.is_dir() and not target.is_symlink():
            for directory, dirs, files in os.walk(target, followlinks=False,
                    onerror=lambda error: report['unscanned'].append({'category': category, 'reason': 'unreadable-directory'})):
                parent = Path(directory)
                for name in list(dirs):
                    if (parent / name).is_symlink():
                        candidates.append(parent / name)
                        dirs.remove(name)
                candidates.extend(parent / name for name in files)
        else:
            candidates.append(target)
        for path in sorted(candidates):
            file_id = hashlib.sha256(str(path).encode()).hexdigest()
            identity = (category, str(path))
            if identity in seen:
                continue
            seen.add(identity)
            item = {'category': category, 'file_id': file_id}
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode) or path.resolve() != path:
                    report['unscanned'].append({**item, 'reason': 'nonregular-or-symlink'})
                    continue
                with path.open('rb') as stream:
                    magic = stream.read(8)
                    stream.seek(0)
                    item.update(_scan_stream(stream, needles))
                item['filename_marker_ids'] = sorted({name for name, needle in needles if needle in str(path).encode()})
                item['members'] = []
                suffix = path.suffix.lower()
                if magic.startswith(b'PK\x03\x04') or suffix in ('.zip', '.xlsx'):
                    with zipfile.ZipFile(path) as archive:
                        members = archive.infolist()
                        if len(members) > 10000 or sum(member.file_size for member in members) > manifest['max_expanded_bytes']:
                            raise ValueError('expanded-limit')
                        for member in members:
                            if member.is_dir():
                                continue
                            member_id = hashlib.sha256(member.filename.encode()).hexdigest()
                            with archive.open(member) as stream:
                                result = _scan_stream(stream, needles, limit=manifest['max_expanded_bytes'])
                            item['members'].append({'member_id': member_id, **result})
                            if result['encoded_content'] or Path(member.filename).suffix.lower() in _OPAQUE | _ARCHIVES:
                                report['unscanned'].append({**item, 'members': [], 'member_id': member_id,
                                    'reason': 'nested-or-visual-content'})
                elif magic.startswith(b'\x1f\x8b') or suffix in ('.gz', '.tgz'):
                    with gzip.open(path, 'rb') as stream:
                        result = _scan_stream(stream, needles, limit=manifest['max_expanded_bytes'])
                        item['members'].append({'member_id': 'gzip-stream', **result})
                    if result['encoded_content']:
                        report['unscanned'].append({**item, 'members': [], 'reason': 'nested-or-visual-content'})
                elif suffix in _OPAQUE or item['encoded_content']:
                    report['unscanned'].append({**item, 'members': [], 'reason': 'visual-or-opaque-content'})
                after = path.stat()
                if (after.st_size, after.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
                    report['unscanned'].append({**item, 'members': [], 'reason': 'snapshot-changed'})
                report['files'].append(item)
            except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile):
                report['unscanned'].append({**item, 'reason': 'unreadable-or-invalid-archive'})
    report['marker_hit_files'] = sum(bool(item['marker_ids'] or item['filename_marker_ids'] or
        any(member['marker_ids'] for member in item['members'])) for item in report['files'])
    report['complete'] = not report['unscanned'] and not report['missing_categories']
    report['passed'] = report['complete'] and report['marker_hit_files'] == 0
    report['runtime_scope_verified'] = manifest['scope'] == 'runtime' and report['passed']
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--markers', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Marker/inventory files stay outside scanned artifacts; the result contains hashes only.
    manifest = json.loads(args.manifest.read_bytes())
    markers = json.loads(args.markers.read_bytes())
    result = scan_manifest(manifest, markers)
    with args.output.open('x', encoding='utf-8') as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(result, output, ensure_ascii=True, sort_keys=True, indent=2)
        output.write('\n')
    print(json.dumps({key: result[key] for key in ('scope', 'complete', 'passed',
        'runtime_scope_verified', 'marker_hit_files')}))
    return int(not result['passed'])


if __name__ == '__main__':
    raise SystemExit(main())

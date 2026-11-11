"""Standalone collection and staging. Python standard library only; no app imports."""

import argparse
import fnmatch
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = HERE.parent / 'datasets' / 'knowledge_base'
PARSER_VERSION = 'kb-markdown-1'
MAX_ARCHIVE = 150 * 1024 * 1024
MAX_DOCUMENT = 4 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sources_from(path):
    config = read_json(path)
    sources = config['sources']
    ids = set()
    for source in sources:
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*', source['id']) or source['id'] in ids:
            raise ValueError('Source ids must be unique safe directory names')
        ids.add(source['id'])
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source['repository']):
            raise ValueError('Invalid GitHub repository')
        if not re.fullmatch(r'[0-9a-f]{40}', source['commit']):
            raise ValueError('Each source must pin a full commit SHA')
        safe_relative(source['license_path'])
        if source['license_id'] != 'CC-BY-SA-4.0':
            raise ValueError('This collector currently supports CC-BY-SA-4.0 sources only')
    return sources


def safe_relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in value or ':' in value:
        raise ValueError(f'Unsafe relative path: {value}')
    return path


def blob_url(source, path):
    return f"https://github.com/{source['repository']}/blob/{source['commit']}/{urllib.parse.quote(path)}"


def selected(source, path):
    return (fnmatch.fnmatchcase(path, source['include'])
            and PurePosixPath(path).name not in source['exclude_names'])


def download_archive(source, destination):
    if destination.exists():
        return
    url = f"https://codeload.github.com/{source['repository']}/zip/{source['commit']}"
    req = urllib.request.Request(url, headers={'User-Agent': 'ctf-knowledge-collection/1.0'})
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.partial')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=45) as response, temporary.open('wb') as output:
                size = 0
                while block := response.read(1024 * 1024):
                    size += len(block)
                    if size > MAX_ARCHIVE:
                        raise ValueError('Archive exceeds configured size limit')
                    output.write(block)
            with zipfile.ZipFile(temporary) as archive:
                if not archive.namelist():
                    raise ValueError('Empty archive')
            temporary.replace(destination)
            return
        except (OSError, urllib.error.URLError, zipfile.BadZipFile):
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def collect(source, data_root):
    raw_root = data_root / 'raw' / source['id'] / source['commit']
    archive_path = data_root / 'raw' / '_archives' / f"{source['id']}-{source['commit']}.zip"
    download_archive(source, archive_path)
    captured_at = datetime.now(timezone.utc).isoformat()
    documents = []
    license_found = False
    with zipfile.ZipFile(archive_path) as archive:
        for member in sorted(archive.infolist(), key=lambda m: m.filename):
            if member.is_dir():
                continue
            parts = PurePosixPath(member.filename).parts
            if len(parts) < 2:
                continue
            relative = '/'.join(parts[1:])
            safe_relative(relative)
            is_license = relative == source['license_path']
            if not is_license and not selected(source, relative):
                continue
            if member.file_size > MAX_DOCUMENT:
                raise ValueError(f'Document too large: {relative}')
            content = archive.read(member)
            destination = raw_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            if is_license:
                license_found = True
                continue
            documents.append({'path': relative, 'raw_sha256': sha256(content), 'bytes': len(content)})
    if not license_found or not documents:
        raise ValueError('Source must contain the configured license and matching documents')
    write_json(raw_root / 'manifest.json', {
        'schema_version': 1, 'source': source, 'captured_at': captured_at,
        'archive_sha256': sha256(archive_path.read_bytes()),
        'documents': documents,
    })
    print(f"Collected {source['id']}: {len(documents)} documents", flush=True)


def resolve_link(source, document_path, target):
    if not target or target.startswith('#') or urllib.parse.urlsplit(target).scheme or target.startswith('//'):
        return target
    base = blob_url(source, document_path)
    if target.startswith('/'):
        base = f"https://github.com/{source['repository']}/blob/{source['commit']}/"
        target = target.lstrip('/')
    return urllib.parse.urljoin(base, target)


def normalize_markdown(raw, source, document_path):
    """Conservative cleaning: retain HTML examples, inline code, tables and fences."""
    text = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    lines = text.split('\n')
    if lines and lines[0] == '---':
        end = next((i for i in range(1, len(lines)) if lines[i] in ('---', '...')), None)
        if end is not None:
            lines = lines[end + 1:]
    output = []
    fence = None
    for line in lines:
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[marker.end():].strip():
                fence = None
            output.append(line)
            continue
        if fence is not None or line.startswith(('    ', '\t')):
            output.append(line)
            continue
        # Protect inline code: security examples may themselves contain Markdown syntax.
        segments = re.split(r'(`+[^`]*`+)', line)
        for i in range(0, len(segments), 2):
            segments[i] = re.sub(
                r'(!?\[[^\]\n]*\]\()([^\s()]+)(\s+"[^"\n]*")?(\))',
                lambda m: m[1] + resolve_link(source, document_path, m[2]) + (m[3] or '') + m[4],
                segments[i],
            )
        line = ''.join(segments)
        reference = re.match(r'^( {0,3}\[[^\]]+\]:\s+)(\S+)(.*)$', line)
        if reference:
            line = reference[1] + resolve_link(source, document_path, reference[2]) + reference[3]
        if line or not output or output[-1] != '':
            output.append(line)
    return '\n'.join(output).strip('\n') + '\n'


def document_title(text, path):
    heading = re.search(r'^#\s+(.+)', text, flags=re.MULTILINE)
    return heading[1].strip() if heading else PurePosixPath(path).stem.replace('_', ' ')


def clean(sources, data_root, min_chars=300):
    records, rejected, duplicates = [], [], []
    seen = {}
    manifests = []
    for source in sources:
        raw_root = data_root / 'raw' / source['id'] / source['commit']
        manifest = read_json(raw_root / 'manifest.json')
        if manifest['source'] != source:
            raise ValueError(f"Source configuration changed; recollect {source['id']} first")
        license_bytes = (raw_root / source['license_path']).read_bytes()
        manifests.append((source, manifest, license_bytes))
        for item in manifest['documents']:
            path = str(safe_relative(item['path']))
            raw = (raw_root / path).read_bytes()
            if sha256(raw) != item['raw_sha256']:
                raise ValueError(f'Raw content hash mismatch: {path}')
            try:
                original_text = raw.decode('utf-8-sig')
                text = normalize_markdown(raw, source, path)
            except UnicodeDecodeError:
                rejected.append({'source': source['id'], 'path': path, 'reason': 'invalid_utf8'})
                continue
            retired = (document_title(text, path).upper().startswith('DEPRECATED:')
                       or (len(original_text) < 1000 and re.search(
                           r'This (?:content has been (?:merged|removed)|information has been moved)',
                           original_text, flags=re.IGNORECASE)))
            if retired:
                rejected.append({'source': source['id'], 'path': path, 'reason': 'redirect_or_retired'})
                continue
            # Expanded GitHub URLs do not count as additional teaching content.
            if '\x00' in text or min(len(original_text.strip()), len(text.strip())) < min_chars:
                rejected.append({'source': source['id'], 'path': path, 'reason': 'too_short_or_binary'})
                continue
            content_hash = sha256(text.encode('utf-8'))
            record_id = source['id'] + '-' + sha256(path.encode('utf-8'))[:16]
            # Deduplicate within a source, preserving independently licensed source records.
            duplicate_key = (source['id'], content_hash)
            if duplicate_key in seen:
                duplicates.append({'source': source['id'], 'path': path, 'same_as': seen[duplicate_key]})
                continue
            seen[duplicate_key] = record_id
            records.append({
                'schema_version': 1, 'id': record_id, 'source_id': source['id'],
                'title': document_title(text, path), 'publisher': source['publisher'],
                'source_url': blob_url(source, path), 'repository_path': path,
                'source_version': source['commit'], 'source_ref': source['ref'],
                'snapshot_date': source['snapshot_date'], 'source_date': None,
                'source_date_note': '原文发布日期未知；snapshot_date 仅为仓库提交日期。',
                'captured_at': manifest['captured_at'], 'verified_at': None,
                'language': source['language'], 'raw_sha256': item['raw_sha256'],
                'source_hash': content_hash, 'source_snapshot': text,
                'license_id': source['license_id'], 'license_url': source['license_url'],
                'license_source_url': blob_url(source, source['license_path']),
                'license_sha256': sha256(license_bytes),
                'attribution_text': f"{source['publisher']}; {source['repository']}@{source['commit']}; {blob_url(source, path)}; CC BY-SA 4.0. Cleaned by {PARSER_VERSION}.",
                'reuse_scope': '按 CC BY-SA 4.0 署名、标注修改，并对改编的资料使用相同许可；代码和第三方示例按原文说明单独核对。',
                'change_note': 'UTF-8/BOM 和换行规范化、移除开头 front matter、合并正文多余空行、将可识别的相对链接固定到来源版本；保留代码及 HTML 示例。',
                'applicability': source['applicability'], 'parser_version': PARSER_VERSION,
                'review_status': 'pending', 'published': False,
                'markdown_path': f'markdown/{record_id}.md',
            })
    if not records:
        raise ValueError('No documents passed cleaning')
    # Fresh directory prevents leftovers from older source selections appearing in a bundle.
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    working = data_root / '.working' / run_id
    working.mkdir(parents=True)
    for source, manifest, license_bytes in manifests:
        license_path = working / 'licenses' / f"{source['id']}.txt"
        license_path.parent.mkdir(parents=True, exist_ok=True)
        license_path.write_bytes(license_bytes)
    for record in records:
        md = working / record['markdown_path']
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_bytes(record['source_snapshot'].encode('utf-8'))
    jsonl = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records)
    (working / 'documents.jsonl').write_bytes(jsonl.encode('utf-8'))
    report = {
        'schema_version': 1, 'parser_version': PARSER_VERSION,
        'collected': sum(len(m['documents']) for _, m, _ in manifests),
        'accepted': len(records), 'rejected': rejected, 'duplicates': duplicates,
        'by_source': {s['id']: sum(r['source_id'] == s['id'] for r in records) for s in sources},
        'documents_sha256': sha256(jsonl.encode('utf-8')),
        'review_status': 'pending', 'published': False,
        'needs_review': ['尚未人工审校或绑定课程', '原文发布日期待补充',
                         '英文材料尚未翻译', '第三方示例与代码的独立许可需按原文核对'],
    }
    write_json(working / 'quality_report.json', report)
    write_json(working / 'sources.lock.json', {
        'schema_version': 1,
        'sources': [{**s, 'captured_at': m['captured_at'],
                     'archive_sha256': m['archive_sha256'],
                     'license_sha256': sha256(license_bytes)} for s, m, license_bytes in manifests],
    })
    verify(working)
    staged = data_root / 'staged'
    if staged.exists():
        staged.rename(data_root / '.working' / f'previous-{run_id}')
    working.rename(staged)
    print(json.dumps({'staged': str(staged), 'accepted': len(records), 'rejected': len(rejected),
                      'duplicates': len(duplicates)}, ensure_ascii=False), flush=True)


def verify(staged):
    raw = (staged / 'documents.jsonl').read_bytes()
    report = read_json(staged / 'quality_report.json')
    if sha256(raw) != report['documents_sha256']:
        raise ValueError('JSONL bundle hash mismatch')
    records = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if len(records) != report['accepted'] or not records:
        raise ValueError('Record count mismatch')
    ids = set()
    expected_paths = set()
    for record in records:
        if record['id'] in ids or record['review_status'] != 'pending' or record['published'] is not False:
            raise ValueError('Duplicate id or invalid staging status')
        ids.add(record['id'])
        md_path = safe_relative(record['markdown_path'])
        expected_paths.add(str(md_path))
        content = (staged / str(md_path)).read_bytes()
        if content != record['source_snapshot'].encode('utf-8') or sha256(content) != record['source_hash']:
            raise ValueError(f"Markdown hash mismatch: {record['id']}")
        license_data = (staged / 'licenses' / f"{record['source_id']}.txt").read_bytes()
        if sha256(license_data) != record['license_sha256']:
            raise ValueError('License hash mismatch')
    actual_paths = {p.relative_to(staged).as_posix() for p in (staged / 'markdown').rglob('*.md')}
    if actual_paths != expected_paths:
        raise ValueError('Markdown bundle contains missing or extra files')
    return len(records)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['collect', 'clean', 'run', 'verify'])
    parser.add_argument('--sources', type=Path, default=HERE / 'sources.json')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--min-chars', type=int, default=300)
    args = parser.parse_args(argv)
    if args.min_chars < 1:
        parser.error('--min-chars must be positive')
    try:
        if args.action == 'verify':
            print(f'Verified {verify(args.data_dir / "staged")} staged documents')
            return 0
        sources = sources_from(args.sources)
        if args.action in ('collect', 'run'):
            for source in sources:
                collect(source, args.data_dir)
        if args.action in ('clean', 'run'):
            clean(sources, args.data_dir, args.min_chars)
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

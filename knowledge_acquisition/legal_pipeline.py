"""Collect official Chinese laws into a separate offline, review-pending bundle."""

import argparse
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from pipeline import DEFAULT_DATA, HERE, read_json, safe_relative, sha256

BASE = 'https://flk.npc.gov.cn'
PARSER_VERSION = 'cn-official-law-1'
LICENSE_ID = 'CN-OFFICIAL-LEGAL-TEXT'
LICENSE_URL = BASE + '/law-search/search/flfgDetails?bbbs=ff808081752b7d430175e4766bab1557'
LICENSE_NOTE = (
    '本包仅收录法律、行政法规的官方正文及明确标注的节选。\n'
    '依据《中华人民共和国著作权法》第五条第一项：\n'
    '本法不适用于：法律、法规，国家机关的决议、决定、命令和其他具有立法、行政、司法性质的文件，及其官方正式译文。\n'
    '来源：' + LICENSE_URL + '\n'
    '保留发布机关、官方来源、版本和清洗说明；本标识不表示网站整体、新闻解读、图片或第三方材料均可任意复用。\n'
).encode('utf-8')
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ARTICLE = re.compile(r'^第([一二三四五六七八九十百千零〇两0-9]+)条(?:\s|$)')
HEADING = re.compile(r'^第[一二三四五六七八九十百千零〇两0-9]+[编章节](?:\s|$)')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


def load_config(path):
    config = read_json(path)
    date.fromisoformat(config['as_of_date'])
    ids = set()
    for source in config['sources']:
        if not re.fullmatch(r'cn-[a-z0-9-]+', source['id']) or source['id'] in ids:
            raise ValueError('Invalid or duplicate source id')
        ids.add(source['id'])
        if not re.fullmatch(r'[a-zA-Z0-9]{20,40}', source['bbbs']):
            raise ValueError('Invalid pinned law version id')
        date.fromisoformat(source['published_date'])
        date.fromisoformat(source['effective_date'])
        if source['document_type'] not in ('law', 'regulation'):
            raise ValueError('Only official laws and administrative regulations are supported')
    return config


def request(url, body=None, limit=8 * 1024 * 1024):
    host = urllib.parse.urlsplit(url).hostname
    if host not in ('flk.npc.gov.cn', 'flkoss.obs-bj2.cucloud.cn'):
        raise ValueError('Unexpected official download host')
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={
        'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/',
        'Content-Type': 'application/json;charset=UTF-8',
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                final_host = urllib.parse.urlsplit(response.url).hostname
                if final_host not in ('flk.npc.gov.cn', 'flkoss.obs-bj2.cucloud.cn'):
                    raise ValueError('Unexpected official response host')
                content = response.read(limit + 1)
                if len(content) > limit:
                    raise ValueError('Official response exceeds size limit')
                return content
        except OSError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def api(path, body=None):
    data = json.loads(request(BASE + path, body))
    if data.get('code') != 200:
        raise ValueError('Official API did not return success')
    return data


def collect(source, data_root):
    details_bytes = request(BASE + '/law-search/search/flfgDetails?' + urllib.parse.urlencode({'bbbs': source['bbbs']}))
    payload = json.loads(details_bytes)
    if payload.get('code') != 200:
        raise ValueError('Official law metadata unavailable')
    details = payload['data']
    for expected, actual in [('title', 'title'), ('published_date', 'gbrq'), ('effective_date', 'sxrq')]:
        if details.get(actual) != source[expected]:
            raise ValueError(f"Pinned official metadata mismatch: {source['id']} / {expected}")
    if details.get('sxx') != 3:
        raise ValueError('Pinned law version is no longer marked effective by the official source')
    result = api('/law-search/download/pc?' + urllib.parse.urlencode({'bbbs': source['bbbs'], 'format': 'docx'}))
    download_url = result['data']['url']
    attachment = request(download_url)
    if not attachment.startswith(b'PK'):
        raise ValueError('Official attachment is not a DOCX archive')
    # Signed download URLs are short-lived; save the stable public path, never the signature.
    location = urllib.parse.urlsplit(download_url)
    stable_url = urllib.parse.urlunsplit((location.scheme, location.netloc, location.path, '', ''))
    raw_root = data_root / 'raw' / 'chinese_laws' / source['id'] / source['bbbs']
    raw_root.mkdir(parents=True, exist_ok=True)
    (raw_root / 'source.docx').write_bytes(attachment)
    (raw_root / 'details.json').write_bytes(details_bytes)
    write_json(raw_root / 'manifest.json', {
        'schema_version': 1, 'source': source,
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'attachment_sha256': sha256(attachment), 'details_sha256': sha256(details_bytes),
        'attachment_url': stable_url,
    })
    print(f"Collected official law: {source['title']}", flush=True)


def chinese_number(text):
    if text.isascii() and text.isdigit():
        return int(text)
    digits = dict(zip('零〇一二三四五六七八九两', [0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2]))
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in '十百千':
            total += (current or 1) * {'十': 10, '百': 100, '千': 1000}[char]
            current = 0
        else:
            raise ValueError('Unsupported Chinese article number')
    return total + current


def paragraphs_from_docx(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        member = archive.getinfo('word/document.xml')
        if member.file_size > 12 * 1024 * 1024:
            raise ValueError('Document XML exceeds size limit')
        xml = archive.read(member)
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ValueError('Unsupported document XML declaration')
    root = ElementTree.fromstring(xml)
    paragraphs = []
    for paragraph in root.iter(W + 'p'):
        pieces = []
        for node in paragraph.iter():
            if node.tag == W + 't':
                pieces.append(node.text or '')
            elif node.tag == W + 'tab':
                pieces.append('\t')
            elif node.tag in (W + 'br', W + 'cr'):
                pieces.append('\n')
        text = ''.join(pieces).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def split_articles(paragraphs):
    articles = []
    current = None
    chapter = []
    for paragraph in paragraphs:
        if HEADING.match(paragraph):
            # End the preceding article before the next heading, retaining its original text.
            current = None
            chapter.append(paragraph)
            continue
        match = ARTICLE.match(paragraph)
        if match:
            current = {'article_number': chinese_number(match[1]), 'article_label': match[0].strip(),
                       'chapter': chapter[-1] if chapter else '', 'paragraphs': [paragraph]}
            articles.append(current)
        elif current is not None:
            current['paragraphs'].append(paragraph)
    for article in articles:
        article['text'] = '\n\n'.join(article.pop('paragraphs'))
    return articles


def normalize(source, paragraphs):
    if source['title'] not in '\n'.join(paragraphs[:5]):
        raise ValueError('Official attachment title mismatch')
    all_articles = split_articles(paragraphs)
    numbers = [article['article_number'] for article in all_articles]
    if numbers != list(range(1, source['expected_articles'] + 1)):
        raise ValueError(f"Article sequence incomplete or duplicated: {source['id']} ({len(numbers)} articles)")
    articles = all_articles
    if 'article_range' in source:
        start, end = source['article_range']
        articles = [article for article in articles if start <= article['article_number'] <= end]
        paragraphs = [source.get('display_title', source['title'])] + [article['text'] for article in articles]
    lines = []
    for index, paragraph in enumerate(paragraphs):
        if index == 0 and paragraph in (source['title'], source.get('display_title')):
            paragraph = '# ' + paragraph
        elif paragraph == source['title']:
            paragraph = '# ' + paragraph
        elif HEADING.match(paragraph):
            paragraph = '## ' + paragraph
        lines.append(paragraph)
    return '\n\n'.join(lines) + '\n', articles


def clean(config, data_root):
    records, clauses, locked = [], [], []
    for source in config['sources']:
        raw_root = data_root / 'raw' / 'chinese_laws' / source['id'] / source['bbbs']
        manifest = read_json(raw_root / 'manifest.json')
        if manifest['source'] != source:
            raise ValueError('Configuration changed; recollect the official source first')
        attachment = (raw_root / 'source.docx').read_bytes()
        details_bytes = (raw_root / 'details.json').read_bytes()
        if sha256(attachment) != manifest['attachment_sha256'] or sha256(details_bytes) != manifest['details_sha256']:
            raise ValueError('Raw official source hash mismatch')
        details = json.loads(details_bytes)['data']
        text, articles = normalize(source, paragraphs_from_docx(attachment))
        title = source.get('display_title', source['title'])
        # File names are Chinese so users can identify each law without decoding ids.
        filename = title + '.md'
        safe_relative(filename)
        source_url = BASE + '/law-search/search/flfgDetails?bbbs=' + source['bbbs']
        records.append({
            'schema_version': 1, 'id': source['id'], 'source_id': 'cn-official-laws',
            'title': title, 'original_title': source['title'], 'document_type': source['document_type'],
            'publisher': details['zdjgName'], 'jurisdiction': 'CN', 'source_name': '国家法律法规数据库',
            'source_url': source_url, 'source_version': source['bbbs'],
            'version_label': source['published_date'], 'source_date': source['published_date'],
            'published_date': source['published_date'], 'effective_date': source['effective_date'],
            'date_basis': '官方数据库gbrq/sxrq；修订法末条原始施行日期不覆盖本版本生效日期。',
            'official_status_code': details['sxx'], 'version_checked_at': manifest['captured_at'],
            'dataset_as_of_date': config['as_of_date'],
            'captured_at': manifest['captured_at'], 'verified_at': None, 'language': 'zh-CN',
            'raw_sha256': manifest['attachment_sha256'], 'source_hash': sha256(text.encode('utf-8')),
            'source_snapshot': text, 'article_count': len(articles),
            'scope': 'excerpt' if 'article_range' in source else 'full_text',
            'article_range': source.get('article_range', [1, source['expected_articles']]),
            'license_id': LICENSE_ID, 'license_url': LICENSE_URL,
            'license_sha256': sha256(LICENSE_NOTE),
            'attribution_text': f"{details['zdjgName']}；{source['title']}；版本{source['published_date']}；{source_url}",
            'reuse_scope': '限法律及行政法规官方正文；依据著作权法第五条第一项，保留来源和版本，不扩展至网站其他内容。',
            'change_note': '从官方DOCX提取段落，保留原文措辞、条号及项号，转换为UTF-8 Markdown；节选范围另行明确标注。',
            'applicability': '中国网络与数据安全教学参考，待人工审核和课程绑定。',
            'summary': source['summary'], 'parser_version': PARSER_VERSION,
            'review_status': 'pending', 'published': False, 'markdown_path': 'markdown/' + filename,
        })
        for article in articles:
            clauses.append({**article, 'schema_version': 1, 'document_id': source['id'],
                            'source_url': source_url, 'source_version': source['bbbs'],
                            'text_hash': sha256(article['text'].encode('utf-8')),
                            'review_status': 'pending', 'published': False})
        locked.append({**source, **{k: manifest[k] for k in ('captured_at', 'attachment_sha256', 'details_sha256', 'attachment_url')}})
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    working = data_root / '.working' / ('legal-' + run_id)
    (working / 'markdown').mkdir(parents=True)
    (working / 'licenses').mkdir()
    (working / 'licenses' / 'cn-official-laws.txt').write_bytes(LICENSE_NOTE)
    for record in records:
        (working / record['markdown_path']).write_bytes(record['source_snapshot'].encode('utf-8'))
    for filename, values in [('documents.jsonl', records), ('clauses.jsonl', clauses)]:
        (working / filename).write_bytes((''.join(json.dumps(value, ensure_ascii=False) + '\n' for value in values)).encode('utf-8'))
    write_json(working / 'sources.lock.json', {'schema_version': 1, 'as_of_date': config['as_of_date'], 'sources': locked})
    write_json(working / 'quality_report.json', {
        'schema_version': 1, 'parser_version': PARSER_VERSION, 'accepted': len(records),
        'article_count': len(clauses), 'by_document': {r['title']: r['article_count'] for r in records},
        'documents_sha256': sha256((working / 'documents.jsonl').read_bytes()),
        'clauses_sha256': sha256((working / 'clauses.jsonl').read_bytes()),
        'pending_sources': config.get('pending_sources', []), 'review_status': 'pending', 'published': False,
        'needs_review': ['待人工审校及课程绑定', '数据库现行性状态仅反映采集时点，后续需复查',
                         '民法典仅节选1032—1039条，完整原始DOCX另存raw'],
    })
    index = ['# 中文法规阅读目录', '', '本批来自国家法律法规数据库的官方正文。所有资料待人工审核，尚未入库或发布。', '',
             '| 法规 | 发布/修订日期 | 本版本生效日期 | 条数 |', '| --- | --- | --- | ---: |']
    for record in records:
        relative = urllib.parse.quote(record['markdown_path'])
        index.append(f"| [{record['title']}]({relative}) | {record['published_date']} | {record['effective_date']} | {record['article_count']} |")
    index += ['', '## 每份资料主要讲什么', '']
    index += [f"- **{r['title']}**：{r['summary']}" for r in records]
    index += ['', '《网络安全法》采用2025年修正版，本版本自2026年1月1日起施行。原文末条保留的2017年6月1日是原法施行日期，两者分别记录。', '',
              '民法典文件为明确标注的节选，不包含其他编章。条款JSONL保留原条号，适用于后续检索和引用。', '', '## 待采集资料', '']
    index += [f"- {item['title']}：{item['reason']}" for item in config.get('pending_sources', [])]
    (working / '阅读目录.md').write_bytes(('\n'.join(index) + '\n').encode('utf-8'))
    verify(working)
    destination = data_root / 'staged_legal'
    if destination.exists():
        destination.rename(data_root / '.working' / ('previous-legal-' + run_id))
    working.rename(destination)
    print(f'Staged {len(records)} Chinese legal documents and {len(clauses)} articles', flush=True)


def verify(root):
    report = read_json(root / 'quality_report.json')
    collections = {}
    for name in ('documents', 'clauses'):
        content = (root / (name + '.jsonl')).read_bytes()
        if sha256(content) != report[name + '_sha256']:
            raise ValueError(f'{name} bundle hash mismatch')
        collections[name] = [json.loads(line) for line in content.decode('utf-8').splitlines() if line.strip()]
    documents, clauses = collections['documents'], collections['clauses']
    if len(documents) != report['accepted'] or len(clauses) != report['article_count'] or not documents:
        raise ValueError('Legal bundle record count mismatch')
    by_id = {document['id']: document for document in documents}
    if len(by_id) != len(documents):
        raise ValueError('Duplicate legal document id')
    paths = set()
    for document in documents:
        path = str(safe_relative(document['markdown_path']))
        paths.add(path)
        content = (root / path).read_bytes()
        if content != document['source_snapshot'].encode('utf-8') or sha256(content) != document['source_hash']:
            raise ValueError('Legal Markdown hash mismatch')
        if sha256((root / 'licenses' / 'cn-official-laws.txt').read_bytes()) != document['license_sha256']:
            raise ValueError('Official-text license note hash mismatch')
        found = [clause for clause in clauses if clause['document_id'] == document['id']]
        start, end = document['article_range']
        if [clause['article_number'] for clause in found] != list(range(start, end + 1)) or len(found) != document['article_count']:
            raise ValueError('Legal article sequence mismatch')
    for clause in clauses:
        if clause['document_id'] not in by_id or sha256(clause['text'].encode('utf-8')) != clause['text_hash']:
            raise ValueError('Legal article hash or document reference mismatch')
        if clause['text'] not in by_id[clause['document_id']]['source_snapshot']:
            raise ValueError('Legal article text differs from the full document')
    for record in documents + clauses:
        if record['review_status'] != 'pending' or record['published'] is not False:
            raise ValueError('Invalid legal staging status')
    if {p.relative_to(root).as_posix() for p in (root / 'markdown').glob('*.md')} != paths:
        raise ValueError('Legal Markdown file set mismatch')
    return len(documents), len(clauses)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['collect', 'clean', 'run', 'verify'])
    parser.add_argument('--sources', type=Path, default=HERE / 'legal_sources.json')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    args = parser.parse_args(argv)
    try:
        if args.action == 'verify':
            print('Verified Chinese legal documents/articles: %s / %s' % verify(args.data_dir / 'staged_legal'))
            return 0
        config = load_config(args.sources)
        if args.action in ('collect', 'run'):
            for source in config['sources']:
                collect(source, args.data_dir)
        if args.action in ('clean', 'run'):
            clean(config, args.data_dir)
        return 0
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

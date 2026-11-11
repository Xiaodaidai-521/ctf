"""Offline corpus audit against raw sources; downloaded articles are data, not instructions."""

import argparse
import io
import json
import re
import subprocess
import unicodedata
import urllib.parse
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from markdown_it import MarkdownIt

import legal_pipeline
import pipeline

PARSER = MarkdownIt('commonmark')


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def signature(text):
    """Compare visible wording and exact code/HTML payloads, ignoring rewritten URL targets."""
    result = []
    for token in PARSER.parse(text):
        if token.type in ('fence', 'code_block', 'html_block'):
            result.append((token.type, token.content, token.info))
        for child in token.children or []:
            if child.type in ('text', 'code_inline', 'html_inline'):
                result.append((child.type, child.content))
            elif child.type == 'image':
                result.append(('image_alt', child.content))
    return result


def link_stats(items):
    counts = Counter()
    relative, blob_images, targets = [], [], []
    for item in items:
        for token in PARSER.parse(item['source_snapshot']):
            if token.type in ('fence', 'code_block'):
                counts[token.type] += 1
            for child in token.children or []:
                if child.type not in ('link_open', 'image'):
                    continue
                target = child.attrGet('src' if child.type == 'image' else 'href') or ''
                counts[child.type] += 1
                detail = {'title': item['title'], 'type': child.type, 'url': target,
                          'source_id': item['source_id'], 'source_version': item['source_version']}
                targets.append(detail)
                parsed = urllib.parse.urlsplit(target)
                if target and not parsed.scheme and not target.startswith(('#', '//')):
                    relative.append(detail)
                if child.type == 'image' and parsed.hostname == 'github.com' and '/blob/' in parsed.path:
                    blob_images.append(detail)
    return dict(counts), relative, blob_images, targets


def original_legal_paragraphs(content):
    # Inspect original XML directly instead of running the cleaning function again.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        xml = ElementTree.fromstring(archive.read('word/document.xml'))
    paragraphs = []
    for paragraph in xml.iter(legal_pipeline.W + 'p'):
        pieces = []
        for node in paragraph.iter():
            if node.tag == legal_pipeline.W + 't':
                pieces.append(node.text or '')
            elif node.tag == legal_pipeline.W + 'tab':
                pieces.append('\t')
            elif node.tag in (legal_pipeline.W + 'br', legal_pipeline.W + 'cr'):
                pieces.append('\n')
        if ''.join(pieces).strip():
            paragraphs.append(''.join(pieces).strip())
    return paragraphs


def inspect(data_root, baseline_ref=None):
    pipeline.verify(data_root / 'staged')
    legal_pipeline.verify(data_root / 'staged_legal')
    owasp = records(data_root / 'staged' / 'documents.jsonl')
    laws = records(data_root / 'staged_legal' / 'documents.jsonl')
    clauses = records(data_root / 'staged_legal' / 'clauses.jsonl')
    findings = []
    archives = {}
    sources = {s['id']: s for s in pipeline.sources_from(pipeline.HERE / 'sources.json')}
    for source in sources.values():
        archive_path = data_root / 'raw' / '_archives' / f"{source['id']}-{source['commit']}.zip"
        raw_root = data_root / 'raw' / source['id'] / source['commit']
        manifest = pipeline.read_json(raw_root / 'manifest.json')
        content = archive_path.read_bytes()
        if pipeline.sha256(content) != manifest['archive_sha256']:
            raise ValueError('Original repository archive hash mismatch')
        archive = zipfile.ZipFile(io.BytesIO(content))
        index = {'/'.join(Path(name).as_posix().split('/')[1:]): name for name in archive.namelist() if not name.endswith('/')}
        archives[source['id']] = (archive, index)
    clean_words = clean_payloads = 0
    for item in owasp:
        original_path = data_root / 'raw' / item['source_id'] / item['source_version'] / item['repository_path']
        original = original_path.read_bytes()
        archive, index = archives[item['source_id']]
        if original != archive.read(index[item['repository_path']]) or pipeline.sha256(original) != item['raw_sha256']:
            raise ValueError('Extracted raw Markdown differs from the pinned archive')
        if signature(original.decode('utf-8-sig')) != signature(item['source_snapshot']):
            raise ValueError('Markdown wording or code changed: ' + item['title'])
        clean_words += 1
        clean_payloads += sum(token.type in ('fence', 'code_block') for token in PARSER.parse(item['source_snapshot']))
    stats, relative, blob_images, targets = link_stats(owasp)
    missing = []
    for target in targets:
        source = sources[target['source_id']]
        parsed = urllib.parse.urlsplit(target['url'])
        parts = urllib.parse.unquote(parsed.path).strip('/').split('/')
        repo_parts = source['repository'].split('/')
        relative_path = None
        if parsed.hostname == 'github.com' and parts[:2] == repo_parts and len(parts) > 4 and parts[2] == 'blob' and parts[3] == source['commit']:
            relative_path = '/'.join(parts[4:])
        elif parsed.hostname == 'raw.githubusercontent.com' and parts[:2] == repo_parts and len(parts) > 3 and parts[2] == source['commit']:
            relative_path = '/'.join(parts[3:])
        if relative_path is not None and relative_path not in archives[source['id']][1]:
            missing.append(target)
    if relative or blob_images:
        raise ValueError('Unresolved Markdown links or GitHub HTML image pages remain')
    for item in owasp + laws:
        text = item['source_snapshot']
        if '\ufffd' in text or '\x00' in text:
            raise ValueError('Replacement character or NUL byte: ' + item['title'])
        if re.match(r'^#.*\(Historical\)', text, re.I):
            findings.append({'kind': 'historical_reference', 'title': item['title'],
                             'note': '上游明确标注历史资料，保留来源，入库前人工决定是否仅作历史参考。'})
        controls = sorted({ord(char) for char in text if unicodedata.category(char) == 'Cc' and char not in '\n\t\r'})
        if controls:
            findings.append({'kind': 'intentional_payload_control_character', 'title': item['title'],
                             'codepoints': controls, 'note': '原始资料中同样存在，正文/代码对比通过；保留教学载荷，不按乱码删除。'})
    checked_articles = 0
    removed_toc = []
    for law in laws:
        raw_root = data_root / 'raw' / 'chinese_laws' / law['id'] / law['source_version']
        content = (raw_root / 'source.docx').read_bytes()
        manifest = pipeline.read_json(raw_root / 'manifest.json')
        details_bytes = (raw_root / 'details.json').read_bytes()
        details = json.loads(details_bytes)['data']
        if pipeline.sha256(content) != law['raw_sha256'] or pipeline.sha256(details_bytes) != manifest['details_sha256']:
            raise ValueError('Raw official document or metadata hash mismatch')
        if details['gbrq'] != law['published_date'] or details['sxrq'] != law['effective_date'] or details['title'] != law['original_title']:
            raise ValueError('Official law title/date mismatch')
        paragraphs = original_legal_paragraphs(content)
        raw_articles, active = {}, None
        for paragraph in paragraphs:
            article = re.match(r'^第([一二三四五六七八九十百千零〇两0-9]+)条(?:\s|$)', paragraph)
            if article:
                active = legal_pipeline.chinese_number(article[1])
                if active in raw_articles:
                    raise ValueError('Repeated original article number')
                raw_articles[active] = [paragraph]
            elif re.match(r'^第[一二三四五六七八九十百千零〇两0-9]+[编章节](?:\s|$)', paragraph):
                active = None
            elif active is not None:
                raw_articles[active].append(paragraph)
        for clause in (clause for clause in clauses if clause['document_id'] == law['id']):
            expected = '\n\n'.join(raw_articles[clause['article_number']])
            if expected != clause['text']:
                raise ValueError('Article differs from the original XML: ' + law['title'])
            checked_articles += 1
        if law['scope'] == 'full_text' and any(re.sub(r'\s', '', paragraph) == '目录' for paragraph in paragraphs):
            if re.search(r'^目\s*录$', law['source_snapshot'], re.M):
                raise ValueError('Duplicate original TOC remains in law text')
            removed_toc.append(law['title'])
    baseline = None
    if baseline_ref:
        raw = subprocess.check_output(['git', 'show', baseline_ref + ':datasets/knowledge_base/staged/documents.jsonl'], cwd=pipeline.HERE.parent)
        previous = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
        previous_stats, previous_relative, previous_images, _ = link_stats(previous)
        baseline = {'ref': baseline_ref, 'unresolved_links': len(previous_relative),
                    'github_blob_images': len(previous_images), 'link_counts': previous_stats}
    for archive, _ in archives.values():
        archive.close()
    return {
        'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'cleaning_status': 'passed_with_source_limitations' if missing else 'passed',
        'human_review_status': 'pending', 'owasp_documents': len(owasp), 'legal_documents': len(laws),
        'legal_articles_compared_to_original': checked_articles,
        'markdown_documents_compared_to_archive': clean_words, 'code_blocks_preserved': clean_payloads,
        'replacement_characters': 0, 'broken_local_relative_links': 0, 'github_blob_image_links': 0,
        'link_counts': stats, 'baseline': baseline, 'removed_duplicate_toc': removed_toc,
        'missing_upstream_paths': missing, 'source_findings': findings,
        'limits': ['外部网站链接未逐一联网验证；固定仓库内文件路径已按原始ZIP核对。',
                   '图片仍通过外部链接显示，未下载为离线图片。',
                   'OWASP资料仍为英文，部分领域及历史资料需要按课程人工筛选。',
                   '官方法规日期与保存的官方元数据一致，未在此次离线检查中重新查询现行性。',
                   '此次是清洗和来源一致性检查，不表示每篇技术结论都经过人工审校。'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=pipeline.DEFAULT_DATA)
    parser.add_argument('--baseline-ref')
    args = parser.parse_args(argv)
    report = inspect(args.data_dir, args.baseline_ref)
    destination = args.data_dir / 'audit'
    legal_pipeline.write_json(destination / 'cleaning_audit.json', report)
    lines = ['# 知识库清洗检查报告', '',
             '结论：正文完整性和清洗格式检查通过；已修正链接、图片和法规标题排版问题。所有资料仍待人工审核，尚未入库或合并。', '',
             '| 检查项 | 结果 |', '| --- | --- |',
             f"| OWASP正文与固定原始仓库对比 | {report['owasp_documents']}篇通过，文字及代码/HTML示例未改变 |",
             f"| 代码块保留 | {report['code_blocks_preserved']}个 |",
             f"| 中文法规与原始DOCX对比 | {report['legal_documents']}份、{report['legal_articles_compared_to_original']}条通过 |",
             '| 乱码替代字符和NUL字节 | 0 |',
             '| 未转换的本地相对链接 | 0 |', '| 图片指向GitHub网页 | 0 |',
             '| 法规版本和日期 | 与保存的官方元数据一致；网络安全法为2025修正版，本版本2026-01-01生效 |', '',
             '## 本次已修正', '']
    if report['baseline']:
        lines += [f"- 修正{report['baseline']['unresolved_links']}个未转换的正文链接，覆盖缩进列表、带代码的链接文字等情况。",
                  f"- 将{report['baseline']['github_blob_images']}个GitHub图片网页链接改为图片原始文件链接。"]
    lines += [f"- 删除{len(report['removed_duplicate_toc'])}份核心法律中重复的目录，并区分章与节的标题层级。",
              '- 分条元数据同时保留章、节和完整标题路径，避免只剩“第一节”而失去所属章。', '', '## 上游资料的待处理项', '']
    if report['missing_upstream_paths']:
        lines += [f"- 原始仓库中找不到的目标路径共{len(report['missing_upstream_paths'])}处；正文保留原始引用，详细URL见JSON报告，后续需查找正确来源。"]
    lines += [f"- **{finding['title']}**：{finding['note']}" for finding in report['source_findings']]
    lines += ['', '## 检查边界', ''] + ['- ' + limit for limit in report['limits']]
    destination.mkdir(parents=True, exist_ok=True)
    (destination / '清洗检查报告.md').write_bytes(('\n'.join(lines) + '\n').encode('utf-8'))
    print(json.dumps({k: report[k] for k in ['cleaning_status', 'owasp_documents', 'legal_documents',
                                          'legal_articles_compared_to_original', 'code_blocks_preserved']}, ensure_ascii=False))
    print('Missing upstream target paths:', len(report['missing_upstream_paths']))


if __name__ == '__main__':
    main()

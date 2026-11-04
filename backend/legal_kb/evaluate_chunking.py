"""Offline round-two probe with frozen v2 behavior and original sample texts.

Run: PYTHONPATH=backend python -m legal_kb.evaluate_chunking
Add --rag to include both document-upload paths (requires project dependencies).
No embedding, database writes or network calls are made.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re

from .services.chunking_service import ChunkingService


SAMPLE_PATH = Path(__file__).with_name('evaluation') / 'chunk_samples.json'
SENT_END = re.compile(r'[。！？!?；;”’"\']$')
V2_BOUNDARY = re.compile(r'\n\s*\n|\n|[。！？!?；;]+[”’"\']*|\.(?=\s|$)')
ARTICLE = r'(第[零〇一二三四五六七八九十百千万0-9０-９]+条)'


def v2_plain(text, max_chars=1200, overlap=160):
    """Frozen boundary-overlap-v2; do not tune this baseline with production."""
    text = text.strip()
    chunks = []
    start, previous_end = 0, 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            minimum = max(start + max_chars // 2, previous_end + 1, start + overlap + 1)
            boundaries = [
                match.end() for match in V2_BOUNDARY.finditer(text, start, end)
                if match.end() >= minimum
            ]
            if boundaries:
                end = boundaries[-1]
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        previous_end = end
        start = end - overlap
    return chunks


def v2_legal(text):
    text = text.strip()
    for pattern, minimum_count in ((r'(?m)^' + ARTICLE, 2), (ARTICLE, 1)):
        parts = re.split(pattern, text)
        chunks = [
            parts[index].strip() + parts[index + 1].strip()
            for index in range(1, len(parts), 2)
        ]
        if len(chunks) >= minimum_count:
            return chunks
    return v2_plain(text)


def stats(texts):
    sizes = [len(text) for text in texts]
    return {
        'chunks': len(sizes),
        'sizes': sizes,
        'min_chars': min(sizes, default=0),
        'max_chars': max(sizes, default=0),
        'tiny_under_50': sum(size < 50 for size in sizes),
        'under_120': sum(size < 120 for size in sizes),
        'tail_under_120': bool(sizes and sizes[-1] < 120),
        'over_850': sum(size > 850 for size in sizes),
        'sentence_end_rate': sum(bool(SENT_END.search(text)) for text in texts) / len(texts) if texts else 0,
    }


def evaluate(include_rag=False):
    data = SAMPLE_PATH.read_bytes()
    samples = json.loads(data)
    modes = {
        'v2_plain_1200_160': lambda text: v2_plain(text),
        'v2_teaching_800_100': lambda text: v2_plain(text, 800, 100),
        'v2_legal_1200_160': v2_legal,
        'v3_teaching_800_100': lambda text: [
            chunk.text for chunk in ChunkingService.split_plain_text(text, max_chars=800, overlap=100)
        ],
        'v3_legal_1200_160': lambda text: [
            chunk.text for chunk in ChunkingService.split_legal_text(text)
        ],
    }
    results = {mode: {name: stats(split(text)) for name, text in samples.items()} for mode, split in modes.items()}
    if include_rag:
        import os
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctf_backend.settings')
        import django
        django.setup()
        from django.test import override_settings
        from rag_ingestion.chunking import StructureAwareChunker

        for enabled, name in ((True, 'rag_langchain_enabled'), (False, 'rag_builtin')):
            with override_settings(RAG_INGESTION_USE_LANGCHAIN_SPLITTER=enabled):
                chunker = StructureAwareChunker(chunk_size=800, chunk_overlap=100)
                results[name] = {
                    sample: stats([chunk.text for chunk in chunker.split(text)])
                    for sample, text in samples.items()
                }
    return {
        'sample_sha256': hashlib.sha256(data).hexdigest(),
        'chunking_version': ChunkingService.VERSION,
        'tail_tolerance_chars': ChunkingService.tail_tolerance(800),
        'sentence_end_pattern': SENT_END.pattern,
        'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rag', action='store_true', help='Also evaluate installed optional and built-in upload paths')
    args = parser.parse_args()
    print(json.dumps(evaluate(include_rag=args.rag), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

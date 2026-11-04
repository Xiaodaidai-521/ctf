"""Offline smoke evaluation: PYTHONPATH=backend python -m learning_knowledge.evaluate_retrieval.

No Django setup, database, credentials, network, or third-party dependencies.
The baseline is frozen from services.py at b69b15e (including non-overlapping
Chinese pairs and ID tie-breaking); both rankers see exactly the same chunks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .ranking import Candidate, RANKING_VERSION, rank_candidates

DEFAULT_DATASET = Path(__file__).with_name('evaluation') / 'golden.json'


def baseline_rank(candidates, query, limit=12):
    tokens = set(re.findall(r'[a-z0-9_]+|[一-鿿]{2}', query.lower()))
    ranked = []
    for item in candidates:
        score = sum(token in (item.title + ' ' + item.text).lower() for token in tokens)
        if not query.strip() or score:
            ranked.append((score, item.id))
    return [pk for _, pk in sorted(ranked, key=lambda row: (-row[0], row[1]))[:limit]]


def validate_dataset(data):
    if not isinstance(data, dict) or not isinstance(data.get('version'), str):
        raise ValueError('Dataset must declare a version.')
    documents, questions = data.get('documents'), data.get('questions')
    if not isinstance(documents, list) or not documents or not isinstance(questions, list) or not questions:
        raise ValueError('Dataset requires nonempty documents and questions.')
    for rows, fields in ((documents, ('id', 'title', 'text')), (questions, ('id', 'category', 'query'))):
        ids = set()
        for row in rows:
            if not isinstance(row, dict) or any(not isinstance(row.get(field), str) or not row[field].strip() for field in fields):
                raise ValueError('Dataset contains missing or invalid string fields.')
            if row['id'] in ids:
                raise ValueError('Dataset IDs must be unique.')
            ids.add(row['id'])
    known = {row['id'] for row in documents}
    for question in questions:
        expected = question.get('expected')
        if (not isinstance(expected, list) or any(not isinstance(value, str) for value in expected)
                or len(set(expected)) != len(expected) or not set(expected).issubset(known)):
            raise ValueError('Expected IDs must be unique known document IDs.')
    if not any(question['expected'] for question in questions):
        raise ValueError('Dataset must contain answerable questions.')


def metrics(rows, k):
    positives = [row for row in rows if row['expected']]
    negatives = [row for row in rows if not row['expected']]
    return {
        'answerable': len(positives),
        'unanswerable': len(negatives),
        f'recall@{k}': sum(row['recall'] for row in positives) / len(positives) if positives else None,
        f'hit_rate@{k}': sum(bool(row['recall']) for row in positives) / len(positives) if positives else None,
        f'mrr@{k}': sum(row['reciprocal_rank'] for row in positives) / len(positives) if positives else None,
        'negative_empty_rate': sum(not row['retrieved'] for row in negatives) / len(negatives) if negatives else None,
    }


def evaluate(data, k=5):
    validate_dataset(data)
    if not 1 <= k <= 12:
        raise ValueError('k must be between 1 and the production candidate limit (12).')
    candidates = [Candidate(index, row['title'], row['text']) for index, row in enumerate(data['documents'])]
    labels = {index: row['id'] for index, row in enumerate(data['documents'])}
    report = {'dataset_version': data['version'], 'ranking_version': RANKING_VERSION,
              'documents': len(candidates), 'questions': len(data['questions']), 'k': k}
    for name, ranker in (('baseline_b69b15e', baseline_rank), ('improved', rank_candidates)):
        rows = []
        for question in data['questions']:
            expected = set(question['expected'])
            retrieved = [labels[pk] for pk in ranker(candidates, question['query'], limit=k)]
            rows.append({
                'id': question['id'], 'category': question['category'],
                'expected': sorted(expected), 'retrieved': retrieved,
                'recall': len(expected.intersection(retrieved)) / len(expected) if expected else None,
                'reciprocal_rank': next((1 / index for index, value in enumerate(retrieved, 1) if value in expected), 0),
            })
        report[name] = {
            'overall': metrics(rows, k),
            'categories': {category: metrics([row for row in rows if row['category'] == category], k)
                           for category in sorted({row['category'] for row in rows})},
            'per_question': rows,
        }
    report[f'recall@{k}_delta'] = report['improved']['overall'][f'recall@{k}'] - report['baseline_b69b15e']['overall'][f'recall@{k}']
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--k', type=int, default=5)
    args = parser.parse_args(argv)
    try:
        raw = args.dataset.read_bytes()
        report = evaluate(json.loads(raw), k=args.k)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    report['dataset_sha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    main()

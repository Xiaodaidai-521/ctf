"""Deterministic in-memory fixtures. Never dump payloads into test evidence."""
from dataclasses import dataclass
import hashlib

from data_security.contracts import Category


@dataclass(frozen=True, slots=True, repr=False)
class Sample:
    sample_id: str
    category: Category
    positive: bool
    text: str
    teaching: str | None = None
    source_ref: str | None = None
    source_version: str | None = None
    expected_exception: bool = False

    def __repr__(self):
        return 'Sample(<synthetic-payload-omitted>)'


def _candidate(index):
    # Fixture checksum construction, not a detector or issuer/region recognizer.
    length = 13 + index % 7
    base = '999' + str(index).zfill(length - 4)
    total = 0
    for i, char in enumerate(reversed(base)):
        number = int(char) * (2 if i % 2 == 0 else 1)
        total += number - 9 if number > 9 else number
    return base + str((-total) % 10)


def samples():
    result = []
    for i in range(50):
        marker = hashlib.sha256(('never-activated-fixture-' + str(i)).encode()).hexdigest()
        card = _candidate(i * 7919 + i)
        pairs = {
            Category.EMAIL: (f'contact unit.{i}+case@example.invalid', f'contact unit.{i} at example dot invalid'),
            Category.IPV4: (f'endpoint 192.0.2.{i + 1}', f'version 192.0.2.{i + 256}'),
            Category.CARD: (card, card[:-1] + str((int(card[-1]) + 1) % 10)),
            Category.SECRET: ('api_key=DS_TEST_ONLY_' + marker, 'api_key_ref=provider/test/v' + str(i + 1)),
        }
        for category, pair in pairs.items():
            for positive, text in zip((True, False), pair):
                result.append(Sample(f'{category.value}-{i:02d}-{int(positive)}', category, positive, text))
        for trusted in (True, False):
            result.append(Sample(
                f'teaching-{i:02d}-{int(trusted)}', Category.IPV4, True,
                f'teaching endpoint 198.51.100.{i + 1}',
                teaching='trusted-published' if trusted else 'self-asserted-upload',
                source_ref=f'fixture/source-{i}', source_version='v1', expected_exception=trusted,
            ))
    return tuple(result)


def dataset_fingerprint():
    result = hashlib.sha256()
    for sample in samples():
        for value in (sample.sample_id, sample.category.value, str(sample.positive), sample.text,
                      str(sample.teaching), str(sample.source_ref), str(sample.source_version),
                      str(sample.expected_exception)):
            encoded = value.encode('utf-8')
            result.update(len(encoded).to_bytes(4, 'big'))
            result.update(encoded)
    return result.hexdigest()

"""Client for official laws from the National Laws and Regulations Database."""

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from xml.etree import ElementTree

import requests


FLK_BASE_URL = 'https://flk.npc.gov.cn'
FLK_SOURCE_NAME = '国家法律法规数据库'


@dataclass(frozen=True)
class OfficialLawTarget:
    """A legal source that should be fetched from flk.npc.gov.cn."""

    key: str
    search_content: str
    expected_title: str
    document_type: str = 'law'
    scope: str = 'full'


DEFAULT_OFFICIAL_LAW_TARGETS = [
    OfficialLawTarget(
        key='personal_information_protection_law',
        search_content='个人信息保护法',
        expected_title='中华人民共和国个人信息保护法',
    ),
    OfficialLawTarget(
        key='data_security_law',
        search_content='数据安全法',
        expected_title='中华人民共和国数据安全法',
    ),
    OfficialLawTarget(
        key='cybersecurity_law',
        search_content='网络安全法',
        expected_title='中华人民共和国网络安全法',
    ),
    OfficialLawTarget(
        key='civil_code_privacy_personal_information',
        search_content='民法典',
        expected_title='中华人民共和国民法典',
        scope='civil_code_privacy_personal_information',
    ),
    OfficialLawTarget(
        key='critical_information_infrastructure_security_regulation',
        search_content='关键信息基础设施安全保护条例',
        expected_title='关键信息基础设施安全保护条例',
        document_type='regulation',
    ),
]


class FlkClientError(RuntimeError):
    """Raised when official law retrieval fails."""


class FlkClient:
    """Small API client for flk.npc.gov.cn search, detail, and docx download."""

    def __init__(
        self,
        *,
        base_url: str = FLK_BASE_URL,
        timeout: int = 30,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
            ),
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json;charset=UTF-8',
            'Origin': self.base_url,
            'Referer': f'{self.base_url}/',
        })

    def search(self, search_content: str, *, page_size: int = 10) -> List[Dict[str, Any]]:
        """Search official laws with the same request shape used by the FLK SPA."""
        body = {
            'searchRange': 1,
            'sxrq': [],
            'gbrq': [],
            'sxx': [],
            'searchType': 2,
            'xgzlSearch': False,
            'searchContent': search_content,
            'orderByParam': {'order': '-1', 'sort': ''},
            'flfgCodeId': [],
            'zdjgCodeId': [],
            'gbrqYear': [],
            'pageNum': 1,
            'pageSize': page_size,
        }
        response = self.session.post(
            f'{self.base_url}/law-search/search/list',
            data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('code') != 200:
            raise FlkClientError(f'FLK search failed for {search_content}: {payload}')
        return payload.get('rows') or []

    def get_details(self, bbbs: str) -> Dict[str, Any]:
        """Fetch official metadata for one law version."""
        response = self.session.get(
            f'{self.base_url}/law-search/search/flfgDetails',
            params={'bbbs': bbbs},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('code') != 200:
            raise FlkClientError(f'FLK detail failed for {bbbs}: {payload}')
        return payload.get('data') or {}

    def get_download_url(self, bbbs: str, *, file_format: str = 'docx') -> str:
        """Return the official public file URL for a law attachment."""
        response = self.session.get(
            f'{self.base_url}/law-search/download/pc',
            params={'bbbs': bbbs, 'format': file_format},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('code') != 200:
            raise FlkClientError(f'FLK download URL failed for {bbbs}: {payload}')
        url = (payload.get('data') or {}).get('url')
        if not url:
            raise FlkClientError(f'FLK download URL missing for {bbbs}')
        return url

    def download_docx(self, url: str) -> bytes:
        """Download a docx attachment from the official object-storage URL."""
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        if not response.content.startswith(b'PK'):
            raise FlkClientError('Official download did not return a docx archive.')
        return response.content

    def fetch_target(self, target: OfficialLawTarget) -> Dict[str, Any]:
        """Fetch and normalize one official target into a LegalDocument payload."""
        rows = self.search(target.search_content)
        row = self._select_row(rows, target.expected_title)
        if not row:
            raise FlkClientError(f'No official law matched: {target.expected_title}')

        bbbs = row.get('bbbs')
        if not bbbs:
            raise FlkClientError(f'FLK search row missing bbbs: {row}')

        details = self.get_details(bbbs)
        download_url = self.get_download_url(bbbs, file_format='docx')
        docx_bytes = self.download_docx(download_url)
        full_text = self.extract_docx_text(docx_bytes)
        if target.scope == 'civil_code_privacy_personal_information':
            full_text = self.extract_civil_code_privacy_scope(full_text)

        if len(full_text.strip()) < 200:
            raise FlkClientError(f'Official text is unexpectedly short for {target.expected_title}')

        title = details.get('title') or self._strip_html(row.get('title') or target.expected_title)
        if target.scope == 'civil_code_privacy_personal_information':
            title = '中华人民共和国民法典（人格权编隐私权和个人信息保护条款节选）'

        return {
            'title': title,
            'document_type': target.document_type,
            'jurisdiction': 'CN',
            'issuing_authority': details.get('zdjgName') or row.get('zdjgName') or '',
            'version_label': details.get('gbrq') or row.get('gbrq') or '',
            'source_url': f'{self.base_url}/law-search/search/flfgDetails?bbbs={bbbs}',
            'source_name': FLK_SOURCE_NAME,
            'full_text': full_text,
            'status': 'active',
            'effective_date': details.get('sxrq') or row.get('sxrq') or None,
            'published_date': details.get('gbrq') or row.get('gbrq') or None,
            'metadata': {
                'official_source': FLK_SOURCE_NAME,
                'bbbs': bbbs,
                'flxz': details.get('flxz') or row.get('flxz') or '',
                'sxx': details.get('sxx') or row.get('sxx'),
                'target_key': target.key,
                'target_scope': target.scope,
                'original_title': details.get('title') or self._strip_html(row.get('title') or ''),
                'download_url': download_url,
                'oss_file': details.get('ossFile') or {},
                'fetched_at': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
            },
        }

    @classmethod
    def extract_docx_text(cls, docx_bytes: bytes) -> str:
        """Extract paragraph text from a docx archive using the Python stdlib."""
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
            try:
                document_xml = archive.read('word/document.xml')
            except KeyError as exc:
                raise FlkClientError('docx archive is missing word/document.xml') from exc

        root = ElementTree.fromstring(document_xml)
        namespace = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs: List[str] = []
        for paragraph in root.findall('.//w:p', namespace):
            pieces = [
                node.text or ''
                for node in paragraph.findall('.//w:t', namespace)
                if node.text
            ]
            line = ''.join(pieces).strip()
            if line:
                paragraphs.append(line)
        return cls._normalize_lines(paragraphs)

    @classmethod
    def extract_civil_code_privacy_scope(cls, text: str) -> str:
        """Keep the Civil Code privacy and personal information protection chapter."""
        clean_text = text.strip()
        chapter_matches = list(re.finditer(r'第六章\s*隐私权和个人信息保护', clean_text))
        for chapter_match in chapter_matches:
            probe = clean_text[chapter_match.end():chapter_match.end() + 12000]
            if '第一千零三十二条' not in probe and '第一千零三十四条' not in probe:
                continue
            tail = clean_text[chapter_match.start():]
            end_match = re.search(r'(?=第七章|第五编|附\s*则|$)', tail[chapter_match.end() - chapter_match.start():])
            if end_match:
                end_index = chapter_match.end() - chapter_match.start() + end_match.start()
                section = tail[:end_index].strip()
            else:
                section = tail.strip()
            if '第一千零三十二条' in section or '第一千零三十四条' in section:
                return cls._normalize_lines([
                    '中华人民共和国民法典',
                    '第四编 人格权',
                    section,
                ])

        article_matches = list(re.finditer(r'第[零〇一二三四五六七八九十百千万]+条', clean_text))
        selected: List[str] = []
        for index, article_match in enumerate(article_matches):
            article_text = clean_text[
                article_match.start(): article_matches[index + 1].start() if index + 1 < len(article_matches) else len(clean_text)
            ].strip()
            if any(keyword in article_text for keyword in ('隐私', '个人信息', '私密')):
                selected.append(article_text)
        if selected:
            return cls._normalize_lines([
                '中华人民共和国民法典',
                '第四编 人格权 隐私权和个人信息保护相关条款',
                *selected,
            ])

        raise FlkClientError('Could not extract Civil Code privacy/personal-information provisions.')

    @classmethod
    def _select_row(cls, rows: Iterable[Dict[str, Any]], expected_title: str) -> Optional[Dict[str, Any]]:
        normalized_expected = cls._strip_html(expected_title)
        for row in rows:
            row_title = cls._strip_html(row.get('title') or '')
            if row_title == normalized_expected or normalized_expected in row_title or row_title in normalized_expected:
                return row
        return None

    @staticmethod
    def _strip_html(value: str) -> str:
        return re.sub(r'<[^>]+>', '', value or '').strip()

    @staticmethod
    def _normalize_lines(lines: Iterable[str]) -> str:
        normalized: List[str] = []
        previous = ''
        for line in lines:
            stripped = re.sub(r'\s+', ' ', line or '').strip()
            if stripped and stripped != previous:
                normalized.append(stripped)
                previous = stripped
        return '\n'.join(normalized)

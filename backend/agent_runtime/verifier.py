import re
from typing import Any, Dict, List


class AgentRuntimeVerifier:
    """Verification checks for runtime-managed agent responses."""

    ACTION_TERMS = {
        'study',
        'practice',
        'review',
        'learn',
        'next',
        'exercise',
        'lab',
        'guidance',
        '建议',
        '学习',
        '练习',
        '复习',
        '下一步',
        '实验',
    }

    def verify_learning_response(
        self,
        *,
        final_result: Dict[str, Any],
        retrieved_docs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        content = str(final_result.get('content') or '').strip()
        checks = [
            self._check_non_empty_content(content),
            self._check_evidence_alignment(content, retrieved_docs),
            self._check_actionable_learning_advice(content),
        ]
        return {
            'passed': all(check['passed'] for check in checks if check.get('required', True)),
            'checks': checks,
        }

    def _check_non_empty_content(self, content: str) -> Dict[str, Any]:
        return {
            'name': 'non_empty_content',
            'passed': bool(content),
            'required': True,
            'message': '' if content else 'Learning response content is empty.',
            'remediation': '' if content else 'Regenerate the response with non-empty learning guidance.',
        }

    def _check_evidence_alignment(
        self,
        content: str,
        retrieved_docs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not retrieved_docs:
            return {
                'name': 'evidence_alignment',
                'passed': True,
                'required': True,
                'message': 'No retrieved learning sources were available.',
                'matched_sources': [],
                'remediation': '',
            }

        cited_sources = self._cited_sources(content, retrieved_docs)
        if cited_sources:
            return {
                'name': 'evidence_alignment',
                'passed': True,
                'required': True,
                'message': '',
                'matched_sources': cited_sources[:5],
                'citation_mode': 'explicit_source_ref',
                'remediation': '',
            }

        overlapping_sources = []
        content_terms = self._terms(content)
        for doc in retrieved_docs:
            title_terms = self._terms(str(doc.get('title') or ''))
            excerpt_terms = self._terms(str(doc.get('excerpt') or ''))
            candidate_terms = (title_terms | excerpt_terms) - {'student', 'learning', 'profile'}
            if content_terms & candidate_terms:
                overlapping_sources.append({
                    'source_ref': doc.get('source_ref'),
                    'source_type': doc.get('source_type'),
                    'source_id': doc.get('source_id'),
                    'title': doc.get('title'),
                })

        return {
            'name': 'evidence_alignment',
            'passed': False,
            'required': True,
            'message': 'Response does not cite retrieved learning context with source references.',
            'matched_sources': [],
            'overlapping_sources': overlapping_sources[:5],
            'citation_mode': 'none',
            'remediation': 'Regenerate the answer and cite at least one valid source reference such as [S1].',
        }

    def _check_actionable_learning_advice(self, content: str) -> Dict[str, Any]:
        lowered = content.lower()
        has_action = any(term in lowered or term in content for term in self.ACTION_TERMS)
        return {
            'name': 'actionable_learning_advice',
            'passed': has_action,
            'required': True,
            'message': '' if has_action else 'Learning response lacks an actionable study step.',
            'remediation': '' if has_action else 'Add a concrete next learning action such as review, practice, or a lab step.',
        }

    def _terms(self, value: str) -> set:
        return {
            term.lower()
            for term in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9_+#.-]{3,}', value)
            if term.strip()
        }

    def _cited_sources(
        self,
        content: str,
        retrieved_docs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        cited_refs = {
            match.upper()
            for match in re.findall(r'\[(S\d+)\]', content, flags=re.IGNORECASE)
        }
        if not cited_refs:
            return []

        matched = []
        for doc in retrieved_docs:
            source_ref = str(doc.get('source_ref') or '').upper()
            if source_ref in cited_refs:
                matched.append({
                    'source_ref': doc.get('source_ref'),
                    'source_type': doc.get('source_type'),
                    'source_id': doc.get('source_id'),
                    'title': doc.get('title'),
                })
        return matched

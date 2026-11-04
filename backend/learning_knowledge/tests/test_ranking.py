import io
import json
from contextlib import redirect_stdout
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import NotFound

from learning_knowledge.evaluate_retrieval import DEFAULT_DATASET, baseline_rank, evaluate, main
from learning_knowledge.models import CourseGrant, MaterialChunk
from learning_knowledge.policy import Scope
from learning_knowledge.ranking import Candidate, RANKING_VERSION, features, rank_candidates
from learning_knowledge.services import search
from legal_kb.services.knowledge_retrieval_service import SafeKnowledgeRetrievalService
from .helpers import material, setup_case


class LexicalRankingTests(SimpleTestCase):
    def test_overlapping_chinese_pairs_recover_boundary_loss(self):
        candidates = [Candidate(1, '', '书面授权要求')]
        self.assertEqual(baseline_rank(candidates, '先授权'), [])
        self.assertEqual(rank_candidates(candidates, '先授权'), [1])
        self.assertIn('pair:授权', features('先授权'))

    def test_aliases_are_local_and_ascii_aliases_have_word_boundaries(self):
        candidates = [Candidate(1, '', '口令管理要求')]
        self.assertEqual(baseline_rank(candidates, '密码'), [])
        self.assertEqual(rank_candidates(candidates, '密码'), [1])
        self.assertFalse(any(term.startswith('alias:') for term in features('passwordless')))
        self.assertEqual(rank_candidates([Candidate(2, '', '跨站脚本')], 'ＸＳＳ'), [2])

    def test_rare_terms_outweigh_repeated_common_terms(self):
        candidates = [Candidate(1, '', '检查 ' * 100), Candidate(2, '', '检查 备份恢复')]
        candidates += [Candidate(index, '', '检查') for index in range(3, 10)]
        self.assertEqual(rank_candidates(candidates, '检查 备份恢复', limit=1), [2])

    def test_static_order_ties_empty_and_limit(self):
        candidates = [Candidate(9, '', 'alpha'), Candidate(2, '', 'alpha')]
        self.assertEqual(rank_candidates(candidates, 'alpha'), [2, 9])
        self.assertEqual(rank_candidates(candidates, ' '), [2, 9])
        self.assertEqual(rank_candidates(candidates, '!!!'), [])
        self.assertEqual(rank_candidates(candidates, 'unmatched'), [])
        self.assertEqual(rank_candidates(candidates, '', limit=0), [])
        self.assertEqual(rank_candidates(candidates, 'alpha', limit=1), [2])
        self.assertEqual(rank_candidates([], 'alpha'), [])

    def test_frozen_baseline_matches_old_nonoverlapping_substring_scoring(self):
        candidates = [Candidate(4, 'ALPHA', '授权'), Candidate(2, '', 'alpha beta'), Candidate(1, '', '无关')]
        self.assertEqual(baseline_rank(candidates, 'alpha beta'), [2, 4])
        self.assertEqual(baseline_rank(candidates, ''), [1, 2, 4])


class OfflineEvaluationTests(SimpleTestCase):
    def test_golden_set_is_deterministic_and_reports_both_rankers(self):
        data = json.loads(DEFAULT_DATASET.read_text())
        with patch('socket.socket', side_effect=AssertionError('offline only')):
            report = evaluate(data)
        self.assertEqual(report, evaluate(data))
        before, after = (report[name]['overall'] for name in ('baseline_b69b15e', 'improved'))
        self.assertGreater(after['recall@5'], before['recall@5'])
        self.assertEqual(after['negative_empty_rate'], 1)
        self.assertEqual(report['ranking_version'], RANKING_VERSION)
        self.assertEqual(len(report['improved']['per_question']), len(data['questions']))

    def test_metrics_handle_multiple_expected_ids_and_negatives(self):
        data = {'version': 'unit', 'documents': [
            {'id': 'a', 'title': 'alpha', 'text': 'alpha'},
            {'id': 'b', 'title': 'beta', 'text': 'beta'},
        ], 'questions': [
            {'id': 'one', 'category': 'positive', 'query': 'alpha', 'expected': ['a', 'b']},
            {'id': 'two', 'category': 'negative', 'query': 'unmatched', 'expected': []},
        ]}
        report = evaluate(data)
        for name in ('baseline_b69b15e', 'improved'):
            self.assertEqual(report[name]['overall']['recall@5'], 0.5)
            self.assertEqual(report[name]['overall']['hit_rate@5'], 1)
            self.assertEqual(report[name]['overall']['mrr@5'], 1)
            self.assertEqual(report[name]['overall']['negative_empty_rate'], 1)

    def test_invalid_dataset_fails_instead_of_publishing_misleading_metrics(self):
        original = json.loads(DEFAULT_DATASET.read_text())
        for expected in (['unknown'], ['scope', 'scope'], 'scope', [None]):
            data = deepcopy(original)
            data['questions'][0]['expected'] = expected
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                evaluate(data)
        data = deepcopy(original)
        data['documents'].append(data['documents'][0])
        with self.assertRaises(ValueError):
            evaluate(data)
        for k in (0, 13):
            with self.assertRaises(ValueError):
                evaluate(original, k=k)

    def test_cli_emits_machine_readable_report_and_dataset_fingerprint(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main([])
        report = json.loads(output.getvalue())
        self.assertEqual(len(report['dataset_sha256']), 64)
        self.assertIn('recall@5_delta', report)


class AuthorizedRankingTests(TestCase):
    def setUp(self):
        setup_case(self)
        cache.clear()

    def test_only_authorized_integrity_checked_text_enters_ranker_without_network(self):
        allowed = material(self, text='口令使用规则')
        for kind in ('teacher_answer', 'grading_secret', 'student_analysis'):
            material(self, kind, text='SECRET 密码')
        material(self, 'hint', text='SECRET 密码', level=1)
        material(self, text='SECRET draft 密码', status='draft')
        revoked = material(self, text='SECRET revoked 密码')
        revoked.material.revoked_at = revoked.created_at
        revoked.material.save(update_fields=['revoked_at'])
        corrupted = material(self, text='SECRET corrupt 密码')
        MaterialChunk.objects.filter(revision=corrupted).update(chunk_hash='0' * 64)
        with patch('learning_knowledge.services.rank_candidates', wraps=rank_candidates) as ranker, \
                patch('requests.get', side_effect=AssertionError('No network')), \
                patch('requests.post', side_effect=AssertionError('No network')), \
                patch('legal_kb.services.embedding_service.EmbeddingService.embed_many', side_effect=AssertionError('No embedding')):
            response = search(self.scope, query='密码')
        self.assertEqual([item.text for item in ranker.call_args.args[0]], ['口令使用规则'])
        self.assertEqual([row['material_id'] for row in response['results']], [str(allowed.material.material_id)])
        self.assertEqual(response['mode'], 'lexical')
        self.assertNotIn('SECRET', str(response))

    def test_cache_contains_only_ids_and_opaque_query_digest_and_reauthorizes(self):
        revision = material(self, text='口令管理')
        with patch('learning_knowledge.services.cache.set') as save:
            search(self.scope, query='密码 PRIVATE-QUERY')
        key, values, ttl = save.call_args.args
        self.assertNotIn('PRIVATE-QUERY', key)
        self.assertTrue(all(type(value) is int for value in values))
        self.assertEqual(ttl, 300)
        # Even a poisoned cache cannot grant access to an unapproved revision.
        secret = material(self, 'teacher_answer', text='SECRET')
        with patch('learning_knowledge.services.cache.get', return_value=[secret.chunks.get().pk, revision.chunks.get().pk]):
            results = search(self.scope, query='密码')['results']
        self.assertEqual(len(results), 1)
        CourseGrant.objects.filter(user=self.student).update(active=False)
        with self.assertRaises(NotFound):
            search(self.scope, query='密码')

    def test_retrieval_log_persists_only_allowlisted_metadata(self):
        import time
        from legal_kb.models import LegalRetrievalLog
        from legal_kb.services.retrieval_service import LegalRetrievalService

        rows = [{'id': 42, 'source_type': 'document', 'title': 'PRIVATE-TITLE', 'text': 'PRIVATE-BODY'}]
        returned = LegalRetrievalService()._record_results(
            query='PRIVATE-QUERY', top_k=5,
            filters={'source_type': ['document'], 'raw': 'PRIVATE-FILTER'},
            results=rows, started=time.perf_counter(), user=self.student,
        )
        log = LegalRetrievalLog.objects.get()
        self.assertEqual(returned, rows)
        self.assertEqual(log.filters, {'source_type': ['document']})
        self.assertEqual(log.results, [{'id': 42, 'source_type': 'document'}])
        self.assertNotIn('PRIVATE', str((log.query, log.filters, log.results)))

    def test_invalid_scope_never_reaches_ranker(self):
        material(self)
        scopes = [None, {}, Scope(self.other, self.attempt.attempt_id),
                  Scope(self.student, self.attempt.attempt_id, purpose='hint_delivery')]
        with patch('learning_knowledge.services.rank_candidates', side_effect=AssertionError('No ranking')):
            for scope in scopes:
                with self.subTest(scope=scope), self.assertRaises(NotFound):
                    search(scope, query='授权')

    @override_settings(KNOWLEDGE_RAG_SAFE_SOURCE_TYPES=['teacher_authored', 'challenge', 'article'])
    def test_legacy_facade_scope_guards_and_allowlist_ceiling(self):
        material(self, text='口令管理')
        service = SafeKnowledgeRetrievalService()
        self.assertEqual(service.safe_source_types, ('article',))
        # Config cannot promote teacher_authored or challenge sources.
        self.assertEqual(service.retrieve(query='密码', user=self.student, task_context=self.scope), [])
        with patch('learning_knowledge.services.search', side_effect=AssertionError('No search')):
            for context, user in ((None, self.student), (self.scope, self.other),
                                  (Scope(self.student, self.attempt.attempt_id, 'hint_delivery'), self.student)):
                self.assertEqual(service.retrieve(query='密码', user=user, task_context=context), [])
        CourseGrant.objects.filter(user=self.student).update(active=False)
        self.assertEqual(service.retrieve(query='密码', user=self.student, task_context=self.scope), [])

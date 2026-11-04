from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.test import APIClient

from learning_knowledge.models import Material, MaterialChunk, ReviewAction
from learning_knowledge.policy import authorize, digest
from learning_knowledge.review import _candidate_spans, inspection, new_revision, parse_candidate, register, transition
from learning_knowledge.services import chunk_text, read_evidence, search
from .helpers import setup_case


def metadata(text='原创教学草案。\n\n只在授权范围核查。'):
    return dict(title='教学依据', publisher='测试编审', source_version='test-1',
                source_date=date(2026, 10, 29), verified_at=date(2026, 10, 29),
                license_id='internal-review-only', attribution_text='Synthetic test author',
                reuse_scope='内部待审，不对外授权', applicability='仅合成任务', source_snapshot=text)


class ReviewTests(TestCase):
    def setUp(self):
        setup_case(self)
        self.revision = register(actor=self.teacher, catalog=self.task.catalog,
                                 material_class='lesson', tasks=[self.task], metadata=metadata())
        parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)

    def act(self, action, actor=None, revision=None, key=None):
        revision = revision or self.revision
        return transition(actor=actor or self.teacher, material_id=revision.material.material_id,
                          expected_revision=revision.revision, action=action,
                          idempotency_key=key or f'{action}-{revision.revision}', reason='合成测试审阅')

    def publish(self, revision=None):
        self.act('submit', revision=revision)
        self.act('approve', actor=self.admin, revision=revision)
        return self.act('publish', revision=revision)

    def test_t3_01_independent_review_and_live_reviewer_duty(self):
        self.assertIsNone(authorize(self.revision.pk, self.scope))
        self.act('submit')
        with self.assertRaises(ValidationError):
            self.act('approve')
        self.act('approve', self.admin)
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(ValidationError):
            self.act('publish')
        self.admin.is_active = True
        self.admin.save()
        self.act('publish')
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))

    def test_revision_author_cannot_review_own_replacement(self):
        replacement = new_revision(actor=self.admin, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('替换草案'))
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.act('submit', self.admin, replacement)
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin, replacement)

    def test_action_idempotency_conflict_and_stale_revision(self):
        self.act('submit')
        self.act('submit')
        self.assertEqual(ReviewAction.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin, key='submit-1')
        new_revision(actor=self.teacher, material=self.revision.material,
                     tasks=[self.task], metadata=metadata('新草案'))
        with self.assertRaises(ValidationError):
            self.act('approve', self.admin)

    def test_source_and_chunk_integrity_required_for_publish(self):
        self.act('submit')
        self.act('approve', self.admin)
        MaterialChunk.objects.filter(revision=self.revision).update(chunk_hash='0' * 64)
        with self.assertRaises(NotFound):
            self.act('publish')
        self.assertIsNone(authorize(self.revision.pk, self.scope))

    def test_t3_08_old_worker_cannot_replace_new_candidate(self):
        old_chunks = list(self.revision.chunks.values_list('pk', flat=True))
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('新草案'))
        with self.assertRaises(ValidationError):
            parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.assertEqual(list(self.revision.chunks.values_list('pk', flat=True)), old_chunks)

    def test_t3_08_failed_candidate_swap_preserves_published_revision(self):
        self.publish()
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('新草案'))
        with patch('learning_knowledge.review.MaterialChunk.objects.bulk_create', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))
        self.assertFalse(replacement.chunks.exists())

    def test_t3_16_replacement_and_withdrawal_preserve_audit_not_old_access(self):
        self.publish()
        evidence = search(self.scope)['results'][0]
        replacement = new_revision(actor=self.teacher, material=self.revision.material,
                                   tasks=[self.task], metadata=metadata('替换依据'))
        parse_candidate(revision_id=replacement.pk, token=replacement.ingestion_token)
        self.publish(replacement)
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.review_status, 'superseded')
        self.assertTrue(self.revision.chunks.exists())
        with self.assertRaises(NotFound):
            read_evidence(evidence['evidence_id'], self.student)
        self.assertEqual({c['material_revision'] for c in search(self.scope)['results']}, {2})
        self.act('withdraw', revision=replacement)
        self.assertEqual(search(self.scope)['results'], [])
        self.assertTrue(ReviewAction.objects.filter(revision=self.revision).exists())

    def test_management_preview_never_authorizes_student(self):
        with self.assertRaises(NotFound):
            inspection(self.revision, self.student)
        preview = inspection(self.revision, self.teacher)
        self.assertEqual(len(preview['chunks']), 1)  # Adjacent tiny paragraphs share one source span.
        self.assertEqual(preview['chunks'][0]['text'], self.revision.source_snapshot)
        self.assertEqual(preview['affected_task_count'], 1)
        self.assertEqual(search(self.scope)['results'], [])
        client = APIClient()
        client.force_authenticate(self.student)
        response = client.get(f'/api/teaching-knowledge/materials/{self.revision.material.material_id}/chunks/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_http_review_state_and_bounded_actions(self):
        client = APIClient()
        url = f'/api/teaching-knowledge/materials/{self.revision.material.material_id}/'
        for action, actor in [('submit', self.teacher), ('approve', self.admin), ('publish', self.teacher)]:
            client.force_authenticate(actor)
            response = client.post(url + action + '/', {
                'expected_revision': 1, 'idempotency_key': action, 'reason': '本地合成审阅',
            }, format='json')
            self.assertEqual(response.status_code, 200, response.data)
        client.force_authenticate(self.student)
        response = client.post(url + 'withdraw/', {
            'expected_revision': 1, 'idempotency_key': 'withdraw', 'reason': 'not allowed',
        }, format='json')
        self.assertEqual(response.status_code, 404)
        client.force_authenticate(self.teacher)
        response = client.post(url + 'withdraw/', {
            'expected_revision': 1, 'idempotency_key': 'x' * 65, 'reason': 'test',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(authorize(self.revision.pk, self.scope))

    def test_pending_candidate_license_cannot_be_published(self):
        self.revision.license_id = 'LicenseRef-Project-Internal-Pending'
        self.revision.save(update_fields=['license_id'])
        self.act('submit')
        self.act('approve', self.admin)
        with self.assertRaisesRegex(ValidationError, 'Candidate reuse permission is pending'):
            self.act('publish')
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.parse_status, 'completed')
        self.assertEqual(self.revision.review_status, 'approved')
        self.assertFalse(ReviewAction.objects.filter(revision=self.revision, action='publish').exists())
        self.assertIsNone(authorize(self.revision.pk, self.scope))

    def test_missing_provenance_registration_is_atomic(self):
        incomplete = metadata()
        del incomplete['license_id']
        with self.assertRaises(ValidationError):
            register(actor=self.teacher, catalog=self.task.catalog, material_class='lesson',
                     tasks=[self.task], metadata=incomplete)
        self.assertEqual(Material.objects.count(), 1)

    def test_refined_spans_keep_hashes_inspection_and_published_evidence(self):
        text = '## 扫描范围\r\n\r\n' + '仅在授权范围内核查服务，并保存可复核的教学证据。' * 110
        revision = new_revision(actor=self.teacher, material=self.revision.material,
                                tasks=[self.task], metadata=metadata(text))
        parsed = parse_candidate(revision_id=revision.pk, token=revision.ingestion_token)
        chunks = list(parsed.chunks.all())
        self.assertGreater(len(chunks), 2)
        self.assertEqual(parsed.parser_version, 'm3-paragraph-2')
        self.assertEqual(parsed.source_hash, digest(text))
        self.assertEqual(parsed.review_status, 'draft')
        self.assertEqual(parsed.ingestion_token, revision.ingestion_token)
        self.assertEqual([c.index for c in chunks], list(range(len(chunks))))
        self.assertEqual(chunks[0].locator, {'paragraph': 1})
        self.assertTrue(all(c.locator == {'paragraph': 2} for c in chunks[1:]))
        self.assertEqual(''.join(chunk_text(c, parsed) for c in chunks), text)
        for chunk in chunks:
            self.assertEqual(chunk.heading_path, [revision.title, '扫描范围'])
            self.assertEqual(chunk.chunk_hash, digest(text[chunk.start:chunk.end]))
        preview = inspection(parsed, self.teacher)
        self.assertEqual([c['text'] for c in preview['chunks']], [chunk_text(c, parsed) for c in chunks])
        self.assertEqual(search(self.scope)['results'], [])
        self.publish(revision)
        results = search(self.scope)['results']
        self.assertEqual({item['chunk_ref'] for item in results}, {str(c.pk) for c in chunks})
        for result in results:
            self.assertEqual(read_evidence(result['evidence_id'], self.student)['locator'], result['locator'])
        self.act('withdraw', revision=revision)
        with self.assertRaises(NotFound):
            read_evidence(results[0]['evidence_id'], self.student)

    def test_completed_parse_is_idempotent_and_reviewed_snapshot_is_not_reparsed(self):
        before = list(self.revision.chunks.values())
        # Completed v1 candidates are not silently re-chunked during a retry.
        self.revision.parser_version = 'm3-paragraph-1'
        self.revision.save(update_fields=['parser_version'])
        parsed = parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)
        self.assertEqual(parsed.parser_version, 'm3-paragraph-1')
        self.assertEqual(list(parsed.chunks.values()), before)
        self.act('submit')
        with self.assertRaisesRegex(ValidationError, 'Reviewed snapshots cannot be replaced'):
            parse_candidate(revision_id=self.revision.pk, token=self.revision.ingestion_token)
        self.assertEqual(list(self.revision.chunks.values()), before)

    def test_empty_candidate_and_missing_token_leave_pending_revision_unchanged(self):
        for text, token in [(' \r\n\t\r\n ', 'use_revision_token'), ('可检查的候选正文。', None)]:
            with self.subTest(text=text):
                revision = new_revision(actor=self.teacher, material=self.revision.material,
                                        tasks=[self.task], metadata=metadata(text))
                if token == 'use_revision_token':
                    token = revision.ingestion_token
                with self.assertRaises(ValidationError):
                    parse_candidate(revision_id=revision.pk, token=token)
                revision.refresh_from_db()
                self.assertEqual(revision.parse_status, 'pending')
                self.assertFalse(revision.chunks.exists())


class CandidateSpanTests(SimpleTestCase):
    def spans(self, text):
        spans = _candidate_spans(text)
        previous_end = 0
        for start, end, paragraph, path in spans:
            self.assertGreaterEqual(start, previous_end)
            self.assertGreater(end, start)
            self.assertLessEqual(end, len(text))
            self.assertGreater(paragraph, 0)
            self.assertEqual(text[previous_end:start].strip(), '')
            previous_end = end
        self.assertEqual(text[previous_end:].strip(), '')
        return spans

    def test_ordinary_paragraph_offsets_and_locators_remain_compatible(self):
        first = '检查授权范围并保留证据。' * 5
        second = '先确认目标地址属于教学环境。' * 5
        text = first + '\n\n' + second
        self.assertEqual(self.spans(text), [
            (0, len(first), 1, ()), (len(first) + 2, len(text), 2, ()),
        ])

    def test_long_chinese_paragraph_splits_at_sentences_without_overlap(self):
        text = '先确认扫描目标属于授权范围，再核查扫描结果。' * 130
        spans = self.spans(text)
        self.assertGreater(len(spans), 3)
        self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans), text)
        for start, end, paragraph, path in spans:
            self.assertLessEqual(end - start, 839)
            self.assertEqual(text[end - 1], '。')
            self.assertEqual(paragraph, 1)
            self.assertEqual(path, ())

    def test_split_locators_use_source_paragraph_not_chunk_ordinal(self):
        first = '前置授权说明。' * 10
        middle = '扫描前需确认目标主机和端口属于授权范围。' * 100
        last = '最后保存复核证据。' * 10
        text = '\n\n'.join((first, middle, last))
        spans = self.spans(text)
        self.assertEqual(spans[0][2], 1)
        self.assertEqual(spans[-1][2], 3)
        self.assertGreater(len(spans[1:-1]), 1)
        self.assertEqual({span[2] for span in spans[1:-1]}, {2})

    def test_short_heading_joins_next_paragraph_and_persists_until_next_heading(self):
        body = '扫描之前先确认课程授权的主机和端口范围。' * 4
        text = '\n\n'.join(('扫描范围', body, body, '证据记录', body))
        spans = self.spans(text)
        self.assertEqual([span[3] for span in spans], [('扫描范围',), ('扫描范围',), ('证据记录',)])
        self.assertEqual([span[2] for span in spans], [1, 3, 4])
        self.assertEqual(text[spans[0][0]:spans[0][1]], '扫描范围\n\n' + body)
        self.assertEqual(text[spans[-1][0]:spans[-1][1]], '证据记录\n\n' + body)

    def test_markdown_heading_levels_and_single_newline_keep_raw_source(self):
        body = '每次练习先核查授权，完成后保留操作证据。' * 4
        text = '# Nmap\n## 主机发现\n' + body + '\n\n### 输出核查\n' + body + '\n\n## 端口扫描\n' + body
        spans = self.spans(text)
        self.assertEqual([span[3] for span in spans], [
            ('Nmap', '主机发现'), ('Nmap', '主机发现', '输出核查'), ('Nmap', '端口扫描'),
        ])
        self.assertTrue(text[spans[0][0]:spans[0][1]].startswith('# Nmap\n## 主机发现\n'))
        self.assertEqual([span[2] for span in spans], [1, 2, 3])

    def test_markdown_closing_hashes_do_not_strip_hashes_from_the_heading_name(self):
        body = '在授权范围内分析程序并复核每个输入的边界。' * 4
        for heading in ('## C#', '## C# ##'):
            with self.subTest(heading=heading):
                text = heading + '\n\n' + body
                self.assertEqual(self.spans(text), [(0, len(text), 1, ('C#',))])

    def test_heading_plus_long_body_tracks_each_original_paragraph(self):
        body = '对授权目标收集最小必要信息，避免无关探测。' * 100
        text = '扫描范围\n\n' + body
        spans = self.spans(text)
        self.assertGreater(len(spans), 2)
        self.assertEqual(spans[0][2], 1)
        self.assertEqual({span[2] for span in spans[1:]}, {2})
        self.assertEqual({span[3] for span in spans}, {('扫描范围',)})
        self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans), text)

    def test_crlf_and_whitespace_only_blank_lines_preserve_exact_offsets(self):
        body = '核查主机授权并保存原始扫描记录。' * 4
        text = ' \r\n\t## 扫描范围\r\n \t\r\n  ' + body + '  \r\n\t\r\n' + body + '\r\n'
        spans = self.spans(text)
        self.assertEqual(len(spans), 2)
        self.assertEqual(spans[0][0], text.index('##'))
        self.assertEqual(spans[0][2:], (1, ('扫描范围',)))
        self.assertEqual(spans[1][2:], (3, ('扫描范围',)))
        self.assertIn('\r\n \t\r\n  ', text[spans[0][0]:spans[0][1]])
        self.assertTrue(text[spans[0][0]:spans[0][1]].endswith('  '))

    def test_tiny_paragraphs_merge_with_previous_or_next_without_reordering(self):
        body = '检查每次操作的授权范围并保留可复核证据。' * 4
        for paragraphs in [('备注。', body), (body, '备注。'), (body, '备注。', body), ('甲。', '乙。', '丙。')]:
            with self.subTest(paragraphs=paragraphs):
                text = '\n\n'.join(paragraphs)
                spans = self.spans(text)
                self.assertEqual(spans[0][2], 1)
                self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans).replace('\n', ''), text.replace('\n', ''))
                self.assertTrue(all(end - start >= 40 for start, end, _, _ in spans) or len(spans) == 1)
        text = '独立的一句。'
        self.assertEqual(self.spans(text), [(0, len(text), 1, ())])

    def test_long_neighbor_does_not_split_a_merged_tiny_paragraph_back_out(self):
        text = '备注。\n\n' + '核' * 1000 + '。'
        spans = self.spans(text)
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(end - start >= 40 for start, end, _, _ in spans))
        self.assertTrue(text[spans[0][0]:spans[0][1]].startswith('备注。\n\n核'))
        self.assertEqual([span[2] for span in spans], [1, 2])
        self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans), text)

    def test_short_sentences_are_not_headings(self):
        body = '在独立教学环境中执行练习并保存完整的证据。' * 3
        for sentence in ('备注。', '继续！', '继续？', 'Note.', 'Next!', 'Why?', '说明；', 'Note;', '“注意。”', '"Note."'):
            with self.subTest(sentence=sentence):
                text = sentence + '\n\n' + body
                self.assertEqual(self.spans(text), [(0, len(text), 1, ())])

    def test_long_unpunctuated_line_is_not_a_heading(self):
        first = '仅用于合成测试的长说明' * 5
        text = first + '\n\n' + '扫描后保存授权证据。' * 5
        spans = self.spans(text)
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(span[3] == () for span in spans))

    def test_tiny_paragraphs_do_not_cross_new_section_boundaries(self):
        text = '前言。\n\n## 授权\n\n核查。\n\n## 授权\n\n记录。'
        spans = self.spans(text)
        self.assertEqual([text[start:end] for start, end, _, _ in spans], ['前言。', '## 授权\n\n核查。', '## 授权\n\n记录。'])
        self.assertEqual([span[2] for span in spans], [1, 2, 4])
        self.assertEqual([span[3] for span in spans], [(), ('授权',), ('授权',)])

    def test_orphan_heading_and_heading_only_document_are_not_dropped(self):
        body = '保存原始记录并确认复核人员具有访问权限。' * 3
        text = body + '\n\n附录'
        self.assertEqual(self.spans(text), [(0, len(text), 1, ())])
        self.assertEqual(self.spans('## 独立标题'), [(0, len('## 独立标题'), 1, ())])
        text = '# 根标题\n\n## 子标题'
        self.assertEqual(self.spans(text), [(0, len(text), 1, ('根标题',))])

    def test_long_sentence_falls_back_to_comma_then_hard_cut(self):
        text = ('核' * 99 + '，') * 20 + '记录。'
        spans = self.spans(text)
        self.assertEqual([end - start for start, end, _, _ in spans], [800, 800, 403])
        self.assertTrue(all(text[end - 1] == '，' for _, end, _, _ in spans[:-1]))
        text = '证' * 1601
        spans = self.spans(text)
        self.assertEqual([end - start for start, end, _, _ in spans], [800, 801])
        self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans), text)

    def test_sentence_quotes_and_english_periods_stay_with_their_sentence(self):
        for sentence, ending in [
            ('讲义指出：“扫描前必须确认授权主机与端口范围。”', '。”'),
            ('Check the authorized host using TLS 1.3 before every classroom scan. ', '.'),
        ]:
            with self.subTest(sentence=sentence):
                text = sentence * 100
                spans = self.spans(text)
                self.assertGreater(len(spans), 2)
                self.assertTrue(all(text[start:end].rstrip().endswith(ending) for start, end, _, _ in spans))
                self.assertEqual(''.join(text[start:end] for start, end, _, _ in spans), text)

    def test_size_threshold_and_tiny_split_tail_tolerance(self):
        text = '证' * 799 + '。'
        self.assertEqual(self.spans(text), [(0, 800, 1, ())])
        text += '后续核查。'
        self.assertEqual(self.spans(text), [(0, len(text), 1, ())])
        text = '证' * 799 + '。' + '据' * 39 + '。'
        self.assertEqual(self.spans(text), [(0, 800, 1, ()), (800, 840, 1, ())])

    def test_empty_and_whitespace_only_content_has_no_spans(self):
        for text in ('', ' ', '\r\n\t\n  \r\n'):
            with self.subTest(text=text):
                self.assertEqual(self.spans(text), [])

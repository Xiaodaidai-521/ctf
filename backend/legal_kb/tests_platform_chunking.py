"""Offline platform indexing checks for teaching windows and embedding context."""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings

from ai_assistant.models import ChallengeKnowledgePack
from articles.models import Article
from challenges.models import Category, Challenge
from learning_knowledge.models import Material
from learning_map.models import CatalogVersion
from learning_paths.models import KnowledgeConcept
from resources.models import Resource

from .models import LegalKnowledgeEmbedding
from .services.chunking_service import ChunkingService, TextChunk
from .services.embedding_service import EmbeddingService, EmbeddingUnavailableError
from .services.hashing import sha256_text
from .services.platform_indexing_service import PlatformContentIndexingService


class PlatformEmbeddingContextTests(SimpleTestCase):
    def setUp(self):
        self.chunk = TextChunk(
            clause_key='chunk-1', title='Chunk 1', text='仅有正文，不含上下文头。', order=1,
        )

    def test_missing_heading_does_not_invent_context_from_synthetic_title_or_category(self):
        text = PlatformContentIndexingService._embedding_text(
            '网络探测', self.chunk, {'category_name': 'Web', 'concept_type': 'tool'},
        )
        self.assertEqual(text, '标题：网络探测\n\n' + self.chunk.text)

    def test_absent_title_and_headings_leave_embedding_input_unchanged(self):
        self.assertEqual(
            PlatformContentIndexingService._embedding_text('', self.chunk, {}),
            self.chunk.text,
        )

    def test_existing_chunk_chapter_is_used_without_modifying_body(self):
        chunk = TextChunk(
            clause_key='chunk-2', title='Chunk 2', text=self.chunk.text,
            order=2, chapter='第一章 网络基础',
        )
        self.assertEqual(
            PlatformContentIndexingService._embedding_text('课程', chunk, {}),
            '标题：课程\n章节：第一章 网络基础\n\n' + self.chunk.text,
        )
        self.assertEqual(chunk.text, self.chunk.text)

    def test_heading_path_accepts_strings_and_only_textual_path_components(self):
        for path, expected in [
            (' 端口扫描 ', '端口扫描'),
            ([' 网络基础 ', '', None, 3, {'secret': 'not-a-heading'}, '端口扫描'], '网络基础 > 端口扫描'),
            (('网络基础', '端口扫描'), '网络基础 > 端口扫描'),
        ]:
            with self.subTest(path=path):
                self.assertEqual(
                    PlatformContentIndexingService._embedding_text(
                        '课程', self.chunk, {'heading_path': path},
                    ),
                    f'标题：课程\n章节路径：{expected}\n\n' + self.chunk.text,
                )

    def test_invalid_or_empty_heading_metadata_is_not_stringified(self):
        for path in (None, {}, {'secret': 'not-a-heading'}, 1, [], [' ', None]):
            with self.subTest(path=path):
                self.assertEqual(
                    PlatformContentIndexingService._embedding_text(
                        '课程', self.chunk, {'heading_path': path, 'chapter': {'secret': 'not-a-chapter'}},
                    ),
                    '标题：课程\n\n' + self.chunk.text,
                )


@override_settings(EMBEDDING_PROVIDER='local')
class PlatformTeachingChunkingTests(TestCase):
    """Real database fixtures explicitly opt into deterministic local vectors."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_user(
            username='platform-chunk-admin', role='admin', is_staff=True,
        )
        # 3,000 characters, regular sentence boundaries and a non-tiny final
        # window for every source's existing (unchanged) text renderer.
        body = ('网' * 49 + '。') * 60
        category = Category.objects.create(name='platform-chunk-fixture')
        cls.challenge = Challenge.objects.create(
            title='题目标题哨兵', description=body, category=category,
            difficulty='easy', score=10, flag='fixture-flag', is_active=True,
        )
        cls.pack = ChallengeKnowledgePack.objects.create(
            challenge=cls.challenge, context_text=body,
        )
        cls.article = Article.objects.create(
            title='文章标题哨兵', summary='课程摘要', content=body,
            author=cls.admin, status='approved',
        )
        cls.resource = Resource.objects.create(
            title='资源标题哨兵', description=body, resource_type='document',
            category='网络基础', uploader=cls.admin, status='approved',
        )
        cls.concept = KnowledgeConcept.objects.create(
            name='概念标题哨兵', slug='platform-chunk-concept', description=body,
            concept_type='tool', difficulty_level=2, cwe_id='CWE-200',
        )

    def setUp(self):
        self.embedding_service = EmbeddingService()
        self.indexer = PlatformContentIndexingService(self.embedding_service)

    def sources(self):
        return [
            ('index_challenges', 'challenge', self.challenge, self.challenge.title),
            ('index_challenge_knowledge_packs', 'challenge', self.pack, self.challenge.title),
            ('index_articles', 'article', self.article, self.article.title),
            ('index_resources', 'resource', self.resource, self.resource.title),
            ('index_knowledge_concepts', 'knowledge_concept', self.concept, self.concept.name),
        ]

    def rows_for(self, source_type, item):
        return LegalKnowledgeEmbedding.objects.filter(
            source_type=source_type, content_type=ContentType.objects.get_for_model(item),
            object_id=item.pk,
        ).order_by('chunk_index')

    def test_all_platform_source_entrypoints_use_teaching_size_and_overlap(self):
        self.assertEqual(ChunkingService.TEACHING_MAX_CHARS, 800)
        self.assertEqual(ChunkingService.TEACHING_OVERLAP, 100)
        split = ChunkingService.split_plain_text
        for method, source_type, item, _title in self.sources():
            with self.subTest(method=method):
                with patch.object(ChunkingService, 'split_plain_text', wraps=split) as splitter:
                    result = getattr(self.indexer, method)(actor=self.admin)
                splitter.assert_called_once()
                self.assertEqual(splitter.call_args.kwargs, {'max_chars': 800, 'overlap': 100})
                expected_chunks = split(splitter.call_args.args[0], max_chars=800, overlap=100)
                rows = list(self.rows_for(source_type, item))
                self.assertEqual(result.indexed_objects, 1)
                self.assertEqual(result.embedded_chunks, len(expected_chunks))
                self.assertGreater(len(rows), 1)
                self.assertEqual([row.text for row in rows], [chunk.text for chunk in expected_chunks])
                self.assertTrue(all(120 <= len(row.text) <= 800 for row in rows[:-1]))
                self.assertLessEqual(len(rows[-1].text), 800 + ChunkingService.tail_tolerance(800))
                self.assertGreaterEqual(len(rows[-1].text), 120)
                for left, right in zip(rows, rows[1:]):
                    self.assertEqual(left.text[-100:], right.text[:100])

    def test_short_content_and_tail_absorption_keep_original_source_body(self):
        for length in (50, 850, 919, 920):
            with self.subTest(length=length):
                self.article.summary = ''
                self.article.content = '文' * (length - len(self.article.title) - 2)
                self.article.save(update_fields=['summary', 'content'])
                source_text = f'{self.article.title}\n\n{self.article.content}'
                self.assertEqual(len(source_text), length)
                self.indexer.index_articles(actor=self.admin)
                rows = list(self.rows_for('article', self.article))
                if length <= 800 + ChunkingService.tail_tolerance(800):
                    self.assertEqual([row.text for row in rows], [source_text])
                else:
                    self.assertEqual([len(row.text) for row in rows], [800, 220])
                    self.assertEqual(rows[0].text + rows[1].text[100:], source_text)

    def test_each_chunk_embeds_title_but_stores_original_body_hash_and_versioned_vector(self):
        for method, source_type, item, title in self.sources():
            with self.subTest(method=method):
                with patch.object(
                    self.embedding_service, 'embed_text', wraps=self.embedding_service.embed_text,
                ) as embed:
                    getattr(self.indexer, method)(actor=self.admin)
                rows = list(self.rows_for(source_type, item))
                self.assertEqual(len(rows), embed.call_count)
                # Existing source renderers already contain the title once in
                # the first chunk. The new context must not pollute later ones.
                self.assertNotIn(title, rows[-1].text)
                for row, call in zip(rows, embed.call_args_list):
                    vector_input = call.args[0]
                    self.assertEqual(vector_input, f'标题：{title}\n\n{row.text}')
                    self.assertNotIn('标题：', row.text)
                    self.assertEqual(row.title, title)
                    self.assertEqual(row.text_hash, sha256_text(row.text))
                    self.assertNotEqual(row.text_hash, sha256_text(vector_input))
                    expected = self.embedding_service.storage_fields(
                        self.embedding_service.embed_local_text(vector_input),
                    )
                    for key, value in expected.items():
                        self.assertEqual(getattr(row, key), value)
                    self.assertTrue(self.embedding_service.matches_index(row))
                    self.assertEqual(row.metadata['chunking_version'], ChunkingService.VERSION)
                    self.assertEqual(row.metadata['vector_model'], self.embedding_service.model)
                    self.assertNotIn('heading_path', row.metadata)
                    self.assertNotIn('chapter', row.metadata)

    def test_existing_pack_heading_metadata_is_used_but_unrelated_metadata_is_not_sent(self):
        self.pack.metadata = {
            'chapter': '第二章 实验验证',
            'heading_path': ['端口扫描', '服务识别'],
            'unrelated': 'DO-NOT-EMBED-ARBITRARY-METADATA',
        }
        self.pack.save(update_fields=['metadata'])
        with patch.object(
            self.embedding_service, 'embed_text', wraps=self.embedding_service.embed_text,
        ) as embed:
            self.indexer.index_challenge_knowledge_packs(actor=self.admin)
        rows = list(self.rows_for('challenge', self.pack))
        self.assertEqual(len(rows), embed.call_count)
        for row, call in zip(rows, embed.call_args_list):
            self.assertEqual(
                call.args[0],
                f'标题：{self.challenge.title}\n章节：第二章 实验验证\n'
                f'章节路径：端口扫描 > 服务识别\n\n{row.text}',
            )
            self.assertNotIn('DO-NOT-EMBED', call.args[0])
            self.assertNotIn('第二章 实验验证', row.text)
            self.assertNotIn('端口扫描', row.text)
            self.assertEqual(row.text_hash, sha256_text(row.text))
            self.assertEqual(row.metadata['chapter'], self.pack.metadata['chapter'])
            self.assertEqual(row.metadata['heading_path'], self.pack.metadata['heading_path'])
            self.assertEqual(row.metadata['kind'], 'knowledge_pack')
            self.assertNotIn('unrelated', row.metadata)

    def test_chunk_specific_metadata_heading_takes_precedence_over_source_metadata(self):
        self.pack.metadata = {'heading_path': ['来源路径'], 'chapter': '来源章节'}
        self.pack.save(update_fields=['metadata'])
        with patch.object(
            self.embedding_service, 'embed_text', wraps=self.embedding_service.embed_text,
        ) as embed:
            self.indexer._index_queryset(
                source_type='challenge', queryset=ChallengeKnowledgePack.objects.filter(pk=self.pack.pk),
                actor=self.admin, title_getter=lambda item: item.challenge.title,
                text_getter=lambda item: '保持原样的正文。',
                metadata_getter=lambda item, chunk: {
                    'heading_path': ['本块路径'], 'chapter': '本块章节', 'chunk_key': chunk.clause_key,
                },
            )
        embed.assert_called_once_with(
            f'标题：{self.challenge.title}\n章节：本块章节\n章节路径：本块路径\n\n保持原样的正文。',
        )
        row = self.rows_for('challenge', self.pack).get()
        self.assertEqual(row.text, '保持原样的正文。')
        self.assertEqual(row.metadata['heading_path'], ['本块路径'])

    def test_missing_provider_fails_loudly_and_preserves_existing_index(self):
        self.indexer.index_articles(actor=self.admin)
        original = list(self.rows_for('article', self.article).values())
        with self.settings(EMBEDDING_PROVIDER='', EMBEDDING_API_KEY=''):
            unavailable = EmbeddingService()
            with patch.object(unavailable, '_local_embed_text') as local:
                with self.assertLogs('legal_kb.services.embedding_service', level='ERROR'):
                    with self.assertRaises(EmbeddingUnavailableError):
                        PlatformContentIndexingService(unavailable).index_articles(actor=self.admin)
        local.assert_not_called()
        self.assertEqual(list(self.rows_for('article', self.article).values()), original)

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='fixture-key', EMBEDDING_DIMENSION=3)
    def test_remote_error_never_falls_back_and_rolls_back_replacement(self):
        # Method-level overrides start after setUp: construct the remote client
        # here, while the shared fixture remains explicitly local.
        service = EmbeddingService()
        indexer = PlatformContentIndexingService(service)
        self.indexer.index_articles(actor=self.admin)
        original = list(self.rows_for('article', self.article).values())
        with patch.object(
            service, '_remote_embed_many', side_effect=RuntimeError('PRIVATE-PROVIDER-DETAIL'),
        ):
            with patch.object(service, '_local_embed_text') as local:
                with self.assertLogs('legal_kb.services.embedding_service', level='ERROR') as logs:
                    with self.assertRaises(EmbeddingUnavailableError) as error:
                        indexer.index_articles(actor=self.admin)
        local.assert_not_called()
        self.assertNotIn('PRIVATE-PROVIDER-DETAIL', str(error.exception) + '\n'.join(logs.output))
        self.assertEqual(list(self.rows_for('article', self.article).values()), original)

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='fixture-key', EMBEDDING_DIMENSION=3)
    def test_remote_authorization_precedes_body_title_and_metadata_rendering(self):
        service = EmbeddingService()
        indexer = PlatformContentIndexingService(service)
        student = get_user_model().objects.create_user(username='platform-chunk-student', role='student')
        for actor in (None, student):
            with self.subTest(actor=actor):
                text, title, metadata = Mock(), Mock(), Mock()
                with patch.object(service, '_remote_embed_many') as remote:
                    with self.assertRaises(ValueError):
                        indexer._index_queryset(
                            source_type='article', queryset=Article.objects.all(), actor=actor,
                            title_getter=title, text_getter=text, metadata_getter=metadata,
                        )
                text.assert_not_called()
                title.assert_not_called()
                metadata.assert_not_called()
                remote.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

    @override_settings(EMBEDDING_PROVIDER='dashscope', EMBEDDING_API_KEY='fixture-key', EMBEDDING_DIMENSION=3)
    def test_registered_sources_and_both_challenge_entrypoints_are_excluded_before_context(self):
        service = EmbeddingService()
        indexer = PlatformContentIndexingService(service)
        catalog = CatalogVersion.objects.create(version='platform-chunk-catalog', label='fixture')
        for _method, source_type, item, _title in self.sources():
            if source_type != 'challenge':
                Material.objects.create(
                    catalog=catalog, owner=self.admin, material_class='lesson',
                    source_type=source_type, source_object_id=item.pk,
                )
        with patch.object(indexer, '_embedding_text') as context:
            with patch.object(indexer, '_build_challenge_text') as challenge_body:
                with patch.object(indexer, '_build_challenge_pack_text') as pack_body:
                    with patch.object(service, '_remote_embed_many') as remote:
                        results = indexer.index_all(actor=self.admin)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(result.indexed_objects == result.embedded_chunks == 0 for result in results))
        context.assert_not_called()
        challenge_body.assert_not_called()
        pack_body.assert_not_called()
        remote.assert_not_called()
        self.assertFalse(LegalKnowledgeEmbedding.objects.exists())

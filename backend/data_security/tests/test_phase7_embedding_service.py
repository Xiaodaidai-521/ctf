"""Provider-handle routing with no database, real credential, or network request."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from ai_providers import ProviderHandle
from data_security.contracts import BASELINE_LIMITS, EmbeddingResult, Outlet, ProtectionContext
from data_security.tests.fixtures import examples
from legal_kb.services.embedding_service import EmbeddingService

MODEL = 'doubao-embedding-vision-251215'


class VisionEmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(EMBEDDING_PROVIDER='volcano', EMBEDDING_MODEL=MODEL,
                                       EMBEDDING_DIMENSION=1024, EMBEDDING_BATCH_SIZE=10)
        self.handle = Mock()
        self.handle.embed.return_value = SimpleNamespace(vectors=((0.25,) * 1024,))
        settings = patch('legal_kb.services.embedding_service.settings', self.settings)
        manager = patch('legal_kb.services.embedding_service.get_manager')
        settings.start()
        self.addCleanup(settings.stop)
        manager.start().return_value.get_provider.return_value = self.handle
        self.addCleanup(manager.stop)

    def test_vision_texts_each_form_one_multimodal_input_not_a_fused_batch(self):
        service = EmbeddingService()
        vectors = service.embed_many(['first text', 'second text'])
        self.assertEqual(len(vectors), 2)
        self.assertTrue(all(len(vector) == 1024 for vector in vectors))
        self.assertEqual(self.handle.embed.call_args_list, [
            call([{'type': 'text', 'text': 'first text'}], model=MODEL, dimensions=1024),
            call([{'type': 'text', 'text': 'second text'}], model=MODEL, dimensions=1024)])
        self.assertEqual(service.vector_space, 'volcano/' + MODEL + '/1024/raw-v1')

    def test_query_and_corpus_texts_use_identical_declared_space(self):
        service = EmbeddingService()
        self.assertEqual(service.embed_text('same text'), service.embed_many(['same text'])[0])
        self.assertEqual(self.handle.embed.call_args_list[0], self.handle.embed.call_args_list[1])

    def test_ark_alias_defaults_to_native_1024_vision_model(self):
        self.settings.EMBEDDING_PROVIDER = 'ark'
        self.settings.EMBEDDING_MODEL = 'local-hash-v1'
        self.settings.EMBEDDING_DIMENSION = 128
        service = EmbeddingService()
        self.assertEqual((service.provider, service.model, service.dimension), ('volcano', MODEL, 1024))

    def test_wrong_configured_dimension_is_not_silently_projected(self):
        self.settings.EMBEDDING_DIMENSION = 2048
        with self.assertRaisesRegex(RuntimeError, '^EMBEDDING_DIMENSION_REQUIRES_APPROVAL$'):
            EmbeddingService()
        self.handle.embed.assert_not_called()

    def test_wrong_remote_cardinality_and_dimension_are_rejected(self):
        for vectors in ((), ((0.25,) * 2048,), ((0.25,) * 1024, (0.25,) * 1024)):
            with self.subTest(count=len(vectors)):
                self.handle.embed.return_value = SimpleNamespace(vectors=vectors)
                with self.assertRaisesRegex(ValueError, '^EMBEDDING_SHAPE_INVALID$'):
                    EmbeddingService().embed_text('a text')

    def test_remote_failure_does_not_become_a_local_hash_vector(self):
        self.handle.embed.side_effect = RuntimeError('PROVIDER_UNAVAILABLE')
        with patch.object(EmbeddingService, '_local_embed_text') as local:
            with self.assertRaisesRegex(RuntimeError, '^PROVIDER_UNAVAILABLE$'):
                EmbeddingService().embed_text('a text')
            local.assert_not_called()

    def test_text_provider_keeps_original_batch_shape(self):
        self.settings.EMBEDDING_PROVIDER = 'qwen'
        self.settings.EMBEDDING_MODEL = 'text-embedding-v3'
        self.handle.embed.return_value = SimpleNamespace(vectors=((0.25,) * 1024,) * 2)
        vectors = EmbeddingService().embed_many(['first', 'second'])
        self.assertEqual(len(vectors), 2)
        self.handle.embed.assert_called_once_with(['first', 'second'], model='text-embedding-v3')

    def test_local_vectors_remain_explicitly_deterministic(self):
        self.settings.EMBEDDING_PROVIDER = ''
        self.settings.EMBEDDING_MODEL = 'local-hash-v1'
        self.settings.EMBEDDING_DIMENSION = 128
        service = EmbeddingService()
        self.assertEqual(service.vector_space, 'local/local-hash-v1/128/raw-v1')
        self.assertEqual(service.retrieval_mode, 'deterministic')
        self.assertEqual(len(service.embed_text('same text')), 128)
        self.assertEqual(service.embed_text('same text'), service.embed_text('same text'))
        self.handle.embed.assert_not_called()

    def test_provider_handle_carries_dimensions_in_the_existing_port(self):
        port, context = Mock(), examples()[ProtectionContext]
        result = EmbeddingResult(schema_version=EmbeddingResult.SCHEMA,
            vectors=((0.25,) * 1024,), endpoint_ref='volcano', model_ref=MODEL, trace_id='trace/phase7')
        port.embed.return_value = result
        context_factory = Mock(return_value=context)
        handle = ProviderHandle(name='volcano', model=MODEL, port=port, context_factory=context_factory,
            binding='fixture-binding', limits=BASELINE_LIMITS, sanitize_response=lambda value: value,
            run_sync=None)
        self.assertIs(handle.embed([{'type': 'text', 'text': 'query'}], model=MODEL, dimensions=1024), result)
        request, actual_context, binding = port.embed.call_args.args
        self.assertEqual(request.content.tree.to_value(), {
            'input': [{'type': 'text', 'text': 'query'}], 'dimensions': 1024})
        context_factory.assert_called_once_with(Outlet.EMBEDDING)
        self.assertIs(actual_context, context)
        self.assertEqual(binding, 'fixture-binding')

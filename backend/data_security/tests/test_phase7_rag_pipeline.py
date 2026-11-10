"""Port-only RAG ordering probes; no database, provider, or startup binding."""
import unittest
from unittest.mock import Mock
from uuid import UUID

from rag_ingestion.interfaces import Chunk, ParsedDocument
from rag_ingestion.pipeline import EmptyDocumentError, IngestionPipeline, UnsupportedFormatError


class RagPipelineTests(unittest.TestCase):
    def setUp(self):
        self.steps = []
        self.parser = Mock(name='parser')
        self.parser.name = 'fixture-parser'
        self.parser.parse.side_effect = self.parse
        self.chunker, self.embedder, self.repository = Mock(), Mock(), Mock()
        self.chunker.split.side_effect = self.split
        self.embedder.embed.side_effect = self.embed
        self.repository.replace.side_effect = self.store
        self.token = UUID('00000000-0000-4000-8000-000000000007')

    def parse(self, data, **kwargs):
        self.steps.append('parse')
        self.assertEqual(kwargs['filename'], 'private@example.invalid.md')
        return ParsedDocument(text='  Body private@example.invalid\r\n',
                              metadata={'author': 'private@example.invalid'})

    def protect(self, value, **context):
        self.steps.append('protect')
        self.assertNotIn('\r', value['text'])
        self.assertEqual(context['object_ref'], 'rag/document-7')
        self.assertEqual(context['object_version'], str(self.token))
        self.assertEqual(context['outlet'], 'rag')
        self.assertEqual(value['metadata']['filename'], 'private@example.invalid.md')
        self.assertEqual(value['metadata']['author'], 'private@example.invalid')
        self.assertEqual(value['metadata']['title'], 'private@example.invalid title')
        self.assertEqual(value['metadata']['notes'], {'owner': 'private@example.invalid'})
        return {'text': 'Body [REDACTED]', 'metadata': {
            'source_type': 'document', 'document_id': 7, 'filename': '[REDACTED].md',
            'title': '[REDACTED] title', 'author': '[REDACTED]',
            'notes': {'owner': '[REDACTED]'}, 'parser': 'fixture-parser',
        }}

    def split(self, text, **kwargs):
        self.steps.append('chunk')
        self.assertEqual(text, 'Body [REDACTED]')
        return [Chunk(text=text, order=1)]

    def embed(self, chunks):
        self.steps.append('embed')
        self.assertEqual(chunks[0].text, 'Body [REDACTED]')
        return ['embedded-fixture']

    def store(self, **kwargs):
        self.steps.append('store')
        self.assertNotIn('private@example.invalid', str(kwargs))
        self.assertEqual(kwargs['ingestion_token'], self.token)
        return 1

    def pipeline(self, **overrides):
        ports = dict(parser_selector=lambda filename, mime: self.parser,
                     chunker=self.chunker, embedder=self.embedder,
                     repository=self.repository, protect=self.protect)
        ports.update(overrides)
        return IngestionPipeline(**ports)

    def run_pipeline(self, pipeline):
        return pipeline.run(data=b'input bytes', filename='private@example.invalid.md',
                            title='private@example.invalid title', document_id=7,
                            base_metadata={'notes': {'owner': 'private@example.invalid'}},
                            ingestion_token=self.token)

    def test_protects_cleaned_body_and_metadata_before_chunk_embed_store(self):
        result = self.run_pipeline(self.pipeline())
        self.assertEqual(self.steps, ['parse', 'protect', 'chunk', 'embed', 'store'])
        self.assertEqual((result.chunk_count, result.embedded_count), (1, 1))
        self.assertNotIn('private@example.invalid', str(result.metadata))

    def test_protection_failure_never_chunks_embeds_or_stores(self):
        protect = Mock(side_effect=RuntimeError('RAG_PROTECTION_FAILED'))
        with self.assertRaisesRegex(RuntimeError, '^RAG_PROTECTION_FAILED$'):
            self.run_pipeline(self.pipeline(protect=protect))
        protect.assert_called_once()
        self.chunker.split.assert_not_called()
        self.embedder.embed.assert_not_called()
        self.repository.replace.assert_not_called()

    def test_custom_embedder_and_repository_need_no_default_implementation(self):
        embedder, repository = Mock(), Mock()
        embedder.embed.return_value = ['replacement-vector']
        repository.replace.return_value = 3
        result = self.run_pipeline(self.pipeline(embedder=embedder, repository=repository))
        self.assertEqual(result.embedded_count, 3)
        self.assertEqual(repository.replace.call_args.kwargs['embedded'], ['replacement-vector'])
        self.embedder.embed.assert_not_called()
        self.repository.replace.assert_not_called()

    def test_unsupported_parser_does_not_enter_protection_or_output(self):
        protect = Mock()
        with self.assertRaises(UnsupportedFormatError):
            self.run_pipeline(self.pipeline(parser_selector=lambda filename, mime: None, protect=protect))
        protect.assert_not_called()
        self.embedder.embed.assert_not_called()
        self.repository.replace.assert_not_called()

    def test_empty_text_does_not_publish(self):
        self.parser.parse.side_effect = None
        self.parser.parse.return_value = ParsedDocument(text=' \n ')
        with self.assertRaises(EmptyDocumentError):
            self.run_pipeline(self.pipeline())
        self.embedder.embed.assert_not_called()
        self.repository.replace.assert_not_called()

    def test_orchestrator_requires_explicit_ports(self):
        with self.assertRaises(TypeError):
            IngestionPipeline()

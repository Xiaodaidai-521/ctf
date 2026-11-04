"""Explicit offline integration-test profile; never use for serving the app.

Legacy ingestion fixtures outside the RAG change scope require a deterministic
embedding. Select with --settings=legal_kb.test_settings; production defaults
remain fail-loud, and missing-provider tests override this opt-in explicitly.
"""
from ctf_backend.settings import *  # noqa: F403

EMBEDDING_PROVIDER = 'local'
EMBEDDING_MODEL = 'local-hash-v1'
EMBEDDING_DIMENSION = 128
EMBEDDING_API_KEY = ''
EMBEDDING_BASE_URL = ''

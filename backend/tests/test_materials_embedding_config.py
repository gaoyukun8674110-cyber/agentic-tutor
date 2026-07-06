import unittest
from unittest.mock import patch

from app.config import settings
from app.services.materials import HashEmbeddingProvider, MaterialService, default_embedding_provider


class WrongDimensionProvider:
    mode = "test"

    def embed_batch(self, texts):
        return [[1.0, 0.0, 0.0] for _text in texts]


class MaterialsEmbeddingConfigTests(unittest.TestCase):
    def setUp(self):
        self.previous_embedding_key = getattr(settings, "RAG_EMBEDDING_API_KEY", None)
        self.previous_embedding_base_url = getattr(settings, "RAG_EMBEDDING_BASE_URL", None)
        self.previous_embedding_model = settings.RAG_EMBEDDING_MODEL
        self.previous_embedding_mode = getattr(settings, "RAG_EMBEDDING_MODE", None)
        self.previous_openai_key = settings.OPENAI_API_KEY
        self.previous_openai_base_url = settings.OPENAI_BASE_URL
        self.previous_vector_dim = getattr(settings, "RAG_VECTOR_DIM", None)

    def tearDown(self):
        if "RAG_EMBEDDING_API_KEY" in settings.__class__.model_fields:
            settings.RAG_EMBEDDING_API_KEY = self.previous_embedding_key
        if "RAG_EMBEDDING_BASE_URL" in settings.__class__.model_fields:
            settings.RAG_EMBEDDING_BASE_URL = self.previous_embedding_base_url
        settings.RAG_EMBEDDING_MODEL = self.previous_embedding_model
        if "RAG_EMBEDDING_MODE" in settings.__class__.model_fields:
            settings.RAG_EMBEDDING_MODE = self.previous_embedding_mode
        settings.OPENAI_API_KEY = self.previous_openai_key
        settings.OPENAI_BASE_URL = self.previous_openai_base_url
        if "RAG_VECTOR_DIM" in settings.__class__.model_fields:
            settings.RAG_VECTOR_DIM = self.previous_vector_dim

    def test_default_embedding_provider_uses_dedicated_rag_openai_settings(self):
        self.assertIn("RAG_EMBEDDING_API_KEY", settings.__class__.model_fields)
        self.assertIn("RAG_EMBEDDING_BASE_URL", settings.__class__.model_fields)
        settings.RAG_EMBEDDING_MODE = "openai"
        settings.RAG_EMBEDDING_API_KEY = "embedding-key"
        settings.RAG_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
        settings.RAG_EMBEDDING_MODEL = "text-embedding-3-small"
        settings.OPENAI_API_KEY = "chat-key"
        settings.OPENAI_BASE_URL = "https://sssaicode.com/api/v1"

        with patch("app.services.materials.OpenAIEmbeddingProvider") as provider_class:
            default_embedding_provider()

        provider_class.assert_called_once_with(
            api_key="embedding-key",
            base_url="https://api.openai.com/v1",
            model="text-embedding-3-small",
        )

    def test_default_embedding_provider_fails_fast_without_embedding_key(self):
        self.assertIn("RAG_EMBEDDING_API_KEY", settings.__class__.model_fields)
        settings.RAG_EMBEDDING_MODE = "openai"
        settings.RAG_EMBEDDING_API_KEY = None
        settings.OPENAI_API_KEY = "chat-key"
        settings.OPENAI_BASE_URL = "https://sssaicode.com/api/v1"

        with self.assertRaisesRegex(RuntimeError, "RAG_EMBEDDING_API_KEY"):
            default_embedding_provider()

    def test_default_embedding_provider_uses_hash_mode_without_api_key(self):
        self.assertIn("RAG_EMBEDDING_MODE", settings.__class__.model_fields)
        settings.RAG_EMBEDDING_MODE = "hash"
        settings.RAG_EMBEDDING_API_KEY = None

        provider = default_embedding_provider()

        self.assertIsInstance(provider, HashEmbeddingProvider)

    def test_hash_embedding_provider_defaults_to_configured_vector_dimension(self):
        self.assertIn("RAG_VECTOR_DIM", settings.__class__.model_fields)
        settings.RAG_VECTOR_DIM = 64

        provider = HashEmbeddingProvider()

        self.assertEqual(provider.dimensions, 64)
        self.assertEqual(len(provider.embed("posterior probability")), 64)

    def test_material_service_rejects_embeddings_with_wrong_dimension(self):
        self.assertIn("RAG_VECTOR_DIM", settings.__class__.model_fields)
        settings.RAG_VECTOR_DIM = 64
        service = MaterialService(db=None, embedding_provider=WrongDimensionProvider())

        with self.assertRaisesRegex(ValueError, "Embedding dimension mismatch"):
            service._embed_texts(["posterior probability"])


if __name__ == "__main__":
    unittest.main()

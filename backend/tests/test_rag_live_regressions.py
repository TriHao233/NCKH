import unittest
from unittest.mock import MagicMock, patch

from modules.rag.chromadb_engine import _huggingface_model_name
from modules.rag.search import get_evaluation_evidence


class RagLiveRegressionTests(unittest.TestCase):
    def test_evaluation_uses_active_model_scoped_collection(self):
        collection = MagicMock()
        collection.query.return_value = {
            "documents": [[]], "metadatas": [[]], "distances": [[]],
        }
        with (
            patch("modules.rag.search._active_vector_snapshot", return_value=("set-1", "vector-1", "chunks_scoped")),
            patch("modules.rag.search.get_collection", return_value=collection) as get_collection,
            patch("modules.rag.search.get_rag_db"),
        ):
            result = get_evaluation_evidence("document-1", "stack queue", "chunks")

        get_collection.assert_called_once_with("chunks_scoped")
        self.assertEqual(result["collection_name"], "chunks_scoped")
        self.assertEqual(result["results"], [])

    def test_short_embedding_alias_resolves_to_public_repository(self):
        with patch("modules.rag.chromadb_engine.settings.embedding_model_name", "all-MiniLM-L6-v2"):
            self.assertEqual(_huggingface_model_name(), "sentence-transformers/all-MiniLM-L6-v2")


if __name__ == "__main__":
    unittest.main()

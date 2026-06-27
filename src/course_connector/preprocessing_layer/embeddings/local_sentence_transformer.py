"""Optional local sentence-transformers embedding provider."""

from __future__ import annotations

from course_connector.preprocessing_layer.config import EmbeddingsConfig, PreprocessingConfigurationError
from course_connector.preprocessing_layer.embeddings.base import EmbeddingProvider


class LocalSentenceTransformerEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by sentence-transformers, imported lazily."""

    def __init__(self, config: EmbeddingsConfig) -> None:
        self.config = config
        self._model = self._load_model()

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=False, show_progress_bar=False)
        return [[float(value) for value in vector] for vector in vectors]

    def _load_model(self) -> object:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise PreprocessingConfigurationError(
                "Local embedding retrieval requires optional dependency `sentence-transformers`. "
                "Install with `pip install -e .[local-embeddings]` or use retrieval mode `keyword`."
            ) from exc

        try:
            return SentenceTransformer(self.config.model, local_files_only=self.config.local_files_only)
        except TypeError:
            return SentenceTransformer(self.config.model)
        except Exception as exc:
            raise PreprocessingConfigurationError(
                "Local embedding model is not available. Use retrieval mode `keyword`, install/cache the model, "
                "or set `local_files_only: false` intentionally."
            ) from exc

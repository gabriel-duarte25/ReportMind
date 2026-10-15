"""Local multilingual embeddings, isolated from indexing and search logic."""

import math
from functools import lru_cache
from pathlib import Path
from threading import Lock

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource, PoolingType

from app.core.config import get_settings


class EmbeddingService:
    def __init__(self, model_name: str, dimension: int, cache_path: Path):
        self.model_name = model_name
        self.dimension = dimension
        self.cache_path = cache_path
        self._model: TextEmbedding | None = None
        self._load_lock = Lock()

    def _load_model(self) -> TextEmbedding:
        with self._load_lock:
            if self._model is None:
                if self.model_name == "intfloat/multilingual-e5-small":
                    if self.dimension != 384:
                        raise ValueError("Multilingual E5 small requires 384 dimensions")
                    if not any(item["model"] == self.model_name for item in TextEmbedding.list_supported_models()):
                        TextEmbedding.add_custom_model(
                            model=self.model_name,
                            pooling=PoolingType.MEAN,
                            normalization=True,
                            sources=ModelSource(hf=self.model_name),
                            dim=384,
                            model_file="onnx/model.onnx",
                        )
                self.cache_path.mkdir(parents=True, exist_ok=True)
                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.cache_path),
                    threads=2,
                )
            return self._model

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = [vector.tolist() for vector in self._load_model().embed(texts, batch_size=16)]
        if len(vectors) != len(texts) or any(
            len(vector) != self.dimension or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("Embedding model returned invalid vectors")
        return vectors

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        prefix = "passage: " if "e5" in self.model_name.lower() else ""
        return self._vectors([prefix + text for text in texts])

    def embed_query(self, query: str) -> list[float]:
        prefix = "query: " if "e5" in self.model_name.lower() else ""
        return self._vectors([prefix + query])[0]


@lru_cache
def get_embedding_service() -> EmbeddingService:
    settings = get_settings()
    return EmbeddingService(settings.embedding_model, settings.embedding_dimension, settings.embedding_cache_path)

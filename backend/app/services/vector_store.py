"""Qdrant adapter; MySQL remains the source for document and chunk text."""

from functools import lru_cache

from qdrant_client import QdrantClient, models

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class VectorStoreError(Exception):
    pass


class VectorStore:
    def __init__(self, url: str, collection: str, dimension: int):
        self.collection = collection
        self.dimension = dimension
        self.client = QdrantClient(url=url, timeout=15, check_compatibility=False)

    @staticmethod
    def _document_filter(document_ids: list[int]) -> models.Filter:
        return models.Filter(must=[
            models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))
        ])

    def ensure_collection(self) -> None:
        try:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=models.VectorParams(size=self.dimension, distance=models.Distance.COSINE),
                )
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name="document_id",
                    field_schema=models.PayloadSchemaType.INTEGER,
                    wait=True,
                )
            config = self.client.get_collection(self.collection).config.params.vectors
            if not isinstance(config, models.VectorParams) or config.size != self.dimension or config.distance != models.Distance.COSINE:
                raise VectorStoreError("Qdrant collection has an incompatible vector configuration")
        except VectorStoreError:
            raise
        except Exception as exc:
            raise VectorStoreError("Qdrant is unavailable") from exc

    def replace_document(self, document: Document, chunks: list[DocumentChunk], vectors: list[list[float]]) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")
        self.ensure_collection()
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=models.FilterSelector(filter=self._document_filter([document.id])),
                wait=True,
            )
            for offset in range(0, len(chunks), 64):
                points = [
                    models.PointStruct(
                        id=chunk.id,
                        vector=vector,
                        payload={
                            "chunk_id": chunk.id,
                            "document_id": document.id,
                            "document_name": document.original_filename,
                            "page_start": chunk.page_start,
                            "page_end": chunk.page_end,
                            "section": chunk.section,
                            "chunk_index": chunk.chunk_index,
                        },
                    )
                    for chunk, vector in zip(chunks[offset:offset + 64], vectors[offset:offset + 64], strict=True)
                ]
                self.client.upsert(collection_name=self.collection, points=points, wait=True)
            return self.client.count(
                collection_name=self.collection,
                count_filter=self._document_filter([document.id]),
                exact=True,
            ).count
        except Exception as exc:
            raise VectorStoreError("Could not store document vectors in Qdrant") from exc

    def delete_document(self, document_id: int) -> None:
        try:
            if self.client.collection_exists(self.collection):
                self.client.delete(
                    collection_name=self.collection,
                    points_selector=models.FilterSelector(filter=self._document_filter([document_id])),
                    wait=True,
                )
        except Exception as exc:
            raise VectorStoreError("Could not delete document vectors from Qdrant") from exc

    def search(self, vector: list[float], document_ids: list[int], limit: int):
        try:
            if not self.client.collection_exists(self.collection):
                return []
            return self.client.query_points(
                collection_name=self.collection,
                query=vector,
                query_filter=self._document_filter(document_ids),
                with_payload=True,
                limit=limit,
            ).points
        except Exception as exc:
            raise VectorStoreError("Could not search Qdrant") from exc


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(settings.qdrant_url, settings.qdrant_collection, settings.embedding_dimension)

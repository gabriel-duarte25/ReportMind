"""Vector and hybrid retrieval with Reciprocal Rank Fusion."""

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.bm25 import bm25_search
from app.services.embeddings import EmbeddingService
from app.services.search import semantic_search
from app.services.vector_store import VectorStore


def retrieve_chunks(
    query: str,
    document_ids: list[int],
    limit: int,
    db: Session,
    embeddings: EmbeddingService,
    vectors: VectorStore,
    settings: Settings,
) -> list[dict]:
    pool_size = min(max(settings.rag_vector_pool_size, limit), 100)
    vector_results = semantic_search(query, pool_size, document_ids, db, embeddings, vectors)
    eligible_vectors = [result for result in vector_results if result["score"] >= settings.rag_min_score]

    if settings.rag_retrieval_mode == "vector":
        return eligible_vectors[:limit]

    lexical_pool_size = min(max(settings.rag_bm25_pool_size, limit), 100)
    lexical_results = bm25_search(query, document_ids, lexical_pool_size, db)
    fused: dict[int, dict] = {}

    for rank, result in enumerate(eligible_vectors, start=1):
        fused[result["chunk_id"]] = {
            **result,
            "vector_score": result["score"],
            "vector_rank": rank,
            "bm25_rank": None,
            "rrf_score": 1 / (settings.rag_rrf_k + rank),
        }

    for rank, result in enumerate(lexical_results, start=1):
        existing = fused.get(result["chunk_id"])
        contribution = 1 / (settings.rag_rrf_k + rank)
        if existing is None:
            fused[result["chunk_id"]] = {
                **result,
                "vector_score": None,
                "vector_rank": None,
                "bm25_rank": rank,
                "rrf_score": contribution,
            }
        else:
            existing["bm25_rank"] = rank
            existing["bm25_score"] = result["bm25_score"]
            existing["rrf_score"] += contribution

    maximum_rrf_score = 2 / (settings.rag_rrf_k + 1)
    results = list(fused.values())
    for result in results:
        # Public `score` remains within 0..1, while raw component scores stay internal.
        result["score"] = min(result["rrf_score"] / maximum_rrf_score, 1.0)
    results.sort(
        key=lambda item: (
            -item["rrf_score"],
            -(item.get("vector_score") or 0),
            -item.get("bm25_score", 0),
            item["chunk_id"],
        )
    )
    return results[:limit]

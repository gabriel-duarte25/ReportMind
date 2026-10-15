"""Small in-process BM25 implementation over selected MySQL chunks."""

import math
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


TOKEN_PATTERN = re.compile(r"(?u)\b[\w]+(?:[./:-][\w]+)*\b")
TOKEN_SEPARATOR = re.compile(r"[./:-]")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "with",
    "a", "ao", "aos", "as", "como", "da", "das", "de", "do", "dos", "e", "em", "entre",
    "é", "foi", "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "qual", "quais",
    "que", "quem", "se", "um", "uma",
}


def tokenize(text: str) -> list[str]:
    """Keep exact compound identifiers and their individual components."""
    tokens: list[str] = []
    for match in TOKEN_PATTERN.finditer(text.casefold()):
        token = match.group(0)
        if token not in STOPWORDS:
            tokens.append(token)
        parts = [part for part in TOKEN_SEPARATOR.split(token) if part]
        if len(parts) > 1:
            tokens.extend(part for part in parts if part not in STOPWORDS)
    return tokens


def bm25_search(query: str, document_ids: list[int], limit: int, db: Session) -> list[dict]:
    if not document_ids or limit <= 0:
        return []

    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.document_id.in_(document_ids))
        .order_by(DocumentChunk.id)
    ).all()
    if not rows:
        return []

    query_terms = set(tokenize(query))
    if not query_terms:
        return []

    tokenized = [tokenize(chunk.text) for chunk, _document in rows]
    frequencies = [Counter(tokens) for tokens in tokenized]
    document_count = len(rows)
    average_length = sum(len(tokens) for tokens in tokenized) / document_count
    document_frequency = {
        term: sum(1 for frequency in frequencies if term in frequency)
        for term in query_terms
    }
    k1 = 1.5
    b = 0.75
    results: list[dict] = []

    for (chunk, document), terms, frequency in zip(rows, tokenized, frequencies):
        score = 0.0
        length_normalization = k1 * (1 - b + b * len(terms) / max(average_length, 1))
        for term in query_terms:
            term_frequency = frequency.get(term, 0)
            if not term_frequency:
                continue
            occurrences = document_frequency[term]
            inverse_frequency = math.log(1 + (document_count - occurrences + 0.5) / (occurrences + 0.5))
            score += inverse_frequency * (term_frequency * (k1 + 1)) / (term_frequency + length_normalization)
        if score <= 0:
            continue
        results.append({
            "score": score,
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_name": document.original_filename,
            "text": chunk.text,
            "section": chunk.section,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "bm25_score": score,
        })

    results.sort(key=lambda item: (-item["bm25_score"], item["chunk_id"]))
    return results[:limit]

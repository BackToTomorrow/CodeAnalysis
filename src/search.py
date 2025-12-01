from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .embedding import embed_texts
from .storage import ensure_db, fts_search
from .vector_store import vector_search


@dataclass
class SearchResult:
    id: str
    score: float
    mode: str  # "hybrid" | "fts" | "vector"


def hybrid_search(query: str, k: int = 20, alpha: float = 0.5) -> List[SearchResult]:
    """Combine FTS and vector similarity, similar in spirit to Continue's hybrid index."""
    conn = ensure_db()

    # Text side
    fts_results = fts_search(conn, query, limit=k * 2)
    fts_scores = {cid: -rank for cid, rank in fts_results}  # lower rank = better

    # Vector side
    [q_vec] = embed_texts([query])
    vec_results = vector_search(conn, q_vec, limit=k * 2)
    vec_scores = {cid: score for cid, score in vec_results}

    # Combine
    all_ids = set(fts_scores) | set(vec_scores)
    combined: List[SearchResult] = []
    for cid in all_ids:
        t = fts_scores.get(cid, 0.0)
        v = vec_scores.get(cid, 0.0)
        score = alpha * v + (1 - alpha) * t
        combined.append(SearchResult(id=cid, score=score, mode="hybrid"))

    combined.sort(key=lambda r: r.score, reverse=True)
    return combined[:k]


def semantic_search(query: str, k: int = 20) -> List[SearchResult]:
    conn = ensure_db()
    [q_vec] = embed_texts([query])
    vec_results = vector_search(conn, q_vec, limit=k)
    return [SearchResult(id=cid, score=score, mode="vector") for cid, score in vec_results]


def text_search(query: str, k: int = 20) -> List[SearchResult]:
    conn = ensure_db()
    fts_results = fts_search(conn, query, limit=k)
    return [SearchResult(id=cid, score=-rank, mode="fts") for cid, rank in fts_results]



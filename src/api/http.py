from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI
from pydantic import BaseModel

from ..core.indexing import index_project, reindex_paths, sync_index
from ..search.hybrid import SearchResult, hybrid_search, semantic_search, text_search
from ..infra.sqlite_store import ensure_db, get_progress, get_chunks_by_ids
from ..search.prompting import build_context_prompt


class IndexRequest(BaseModel):
    root: str


class IncrementalIndexRequest(BaseModel):
    paths: List[str]


class SearchRequest(BaseModel):
    query: str
    k: int = 20
    alpha: float = 0.5  # for hybrid search


class SearchResponseItem(BaseModel):
    id: str
    score: float
    mode: str


class HybridContextRequest(BaseModel):
    query: str
    results: List[SearchResponseItem]
    prompt_template: str | None = None


class HybridContextResponse(BaseModel):
    prompt: str
    used_ids: List[str]


app = FastAPI(title="C# Code Analysis & Hybrid Search")


@app.post("/index")
def index_endpoint(req: IndexRequest) -> dict:
    root = Path(req.root)
    index_project(root)
    return {"status": "ok", "indexed_root": str(root)}


@app.post("/index/sync")
def index_sync_endpoint(req: IndexRequest) -> dict:
    """Smart indexing: full or incremental as needed, resumable."""
    root = Path(req.root)
    result = sync_index(root)
    return result


@app.post("/index/incremental")
def incremental_index_endpoint(req: IncrementalIndexRequest) -> dict:
    path_objs = [Path(p) for p in req.paths]
    reindex_paths(path_objs)
    return {"status": "ok", "updated_paths": [str(p) for p in path_objs]}


@app.get("/index/status")
def index_status_endpoint() -> dict:
    """Return last known indexing progress for UI polling."""
    conn = ensure_db()
    prog = get_progress(conn)
    if prog is None:
        return {"state": "idle"}
    return prog


@app.post("/search/hybrid", response_model=List[SearchResponseItem])
def hybrid_endpoint(req: SearchRequest) -> List[SearchResponseItem]:
    results: List[SearchResult] = hybrid_search(req.query, k=req.k, alpha=req.alpha)
    return [SearchResponseItem(**r.__dict__) for r in results]


@app.post("/search/semantic", response_model=List[SearchResponseItem])
def semantic_endpoint(req: SearchRequest) -> List[SearchResponseItem]:
    results: List[SearchResult] = semantic_search(req.query, k=req.k)
    return [SearchResponseItem(**r.__dict__) for r in results]


@app.post("/search/text", response_model=List[SearchResponseItem])
def text_endpoint(req: SearchRequest) -> List[SearchResponseItem]:
    results: List[SearchResult] = text_search(req.query, k=req.k)
    return [SearchResponseItem(**r.__dict__) for r in results]


@app.post("/search/hybrid/context", response_model=HybridContextResponse)
def hybrid_context_endpoint(req: HybridContextRequest) -> HybridContextResponse:
    """Take hybrid search results and build a high-quality context prompt for a chat model."""
    # Preserve the order and ids from the hybrid search response
    ids = [r.id for r in req.results]

    conn = ensure_db()
    chunks = get_chunks_by_ids(conn, ids)

    prompt = build_context_prompt(
        query=req.query,
        chunks=chunks,
        template=req.prompt_template,
    )
    return HybridContextResponse(prompt=prompt, used_ids=ids)




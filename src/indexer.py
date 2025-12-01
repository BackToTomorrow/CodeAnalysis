from __future__ import annotations

from pathlib import Path
from typing import Iterable, List
import os

from .ast_csharp import CSharpAstParser
from .config import CSHARP_EXTENSIONS
from .embedding import embed_texts
from .index_schema import CodeChunk
from .storage import (
    ensure_db,
    upsert_chunks,
    read_file_index_state,
    upsert_file_state,
    delete_files,
    init_progress,
    increment_progress,
    finish_progress,
    upsert_symbol_relations,
)
from .vector_store import upsert_embeddings as upsert_vectors, delete_by_file_paths


def discover_csharp_files(root: Path) -> List[Path]:
    return [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in CSHARP_EXTENSIONS
    ]


def index_project(root: Path) -> None:
    """Force a full reindex of all C# files under root."""
    parser = CSharpAstParser()
    files = discover_csharp_files(root)
    all_chunks: List[CodeChunk] = []
    for f in files:
        all_chunks.extend(parser.parse_file(f))

    conn = ensure_db()
    upsert_chunks(conn, all_chunks)
    upsert_symbol_relations(conn, all_chunks)

    texts = [c.content for c in all_chunks]
    embeddings = embed_texts(texts)
    upsert_vectors(all_chunks, embeddings)

    # Update file state so that subsequent runs can be incremental
    for f in files:
        st = f.stat()
        upsert_file_state(conn, str(f), st.st_mtime, st.st_size)


def reindex_paths(paths: Iterable[Path]) -> None:
    """Explicitly reindex the given files/directories."""
    parser = CSharpAstParser()
    all_chunks: List[CodeChunk] = []
    files: List[Path] = []
    for p in paths:
        if p.is_dir():
            for f in discover_csharp_files(p):
                all_chunks.extend(parser.parse_file(f))
                files.append(f)
        elif p.is_file() and p.suffix.lower() in CSHARP_EXTENSIONS:
            all_chunks.extend(parser.parse_file(p))
            files.append(p)

    if not all_chunks:
        return

    conn = ensure_db()
    upsert_chunks(conn, all_chunks)
    upsert_symbol_relations(conn, all_chunks)
    texts = [c.content for c in all_chunks]
    embeddings = embed_texts(texts)
    upsert_vectors(all_chunks, embeddings)

    for f in files:
        st = f.stat()
        upsert_file_state(conn, str(f), st.st_mtime, st.st_size)


def sync_index(root: Path) -> dict:
    """Smart index: decide between full and incremental, track progress, and be resumable.

    - If files have never been indexed, this behaves like a full index.
    - Otherwise it only reindexes new/changed files and cleans up deleted ones.
    - Safe to call repeatedly; it will continue where it left off.
    """
    conn = ensure_db()
    existing_state = read_file_index_state(conn)

    all_fs_files = discover_csharp_files(root)
    all_fs_set = {str(p) for p in all_fs_files}

    # Files to index: new or modified
    to_index: List[Path] = []
    for f in all_fs_files:
        key = str(f)
        st = f.stat()
        mtime_size = (st.st_mtime, st.st_size)
        if key not in existing_state or existing_state[key] != mtime_size:
            to_index.append(f)

    # Files to delete: in DB but no longer on disk under this root
    to_delete = [fp for fp in existing_state.keys() if fp not in all_fs_set]

    if to_delete:
        delete_files(conn, to_delete)
        delete_by_file_paths(to_delete)

    total = len(to_index)
    if total == 0:
        return {
            "status": "up_to_date",
            "root": str(root),
            "total_files": len(all_fs_files),
            "updated_files": 0,
            "deleted_files": len(to_delete),
        }

    init_progress(conn, str(root), total_files=total)

    parser = CSharpAstParser()
    updated_count = 0

    for f in to_index:
        chunks = parser.parse_file(f)
        upsert_chunks(conn, chunks)
        upsert_symbol_relations(conn, chunks)
        texts = [c.content for c in chunks]
        embeddings = embed_texts(texts)
        upsert_vectors(chunks, embeddings)

        st = f.stat()
        upsert_file_state(conn, str(f), st.st_mtime, st.st_size)

        increment_progress(conn, 1)
        updated_count += 1

    finish_progress(conn)

    return {
        "status": "indexed",
        "root": str(root),
        "total_files": len(all_fs_files),
        "updated_files": updated_count,
        "deleted_files": len(to_delete),
    }



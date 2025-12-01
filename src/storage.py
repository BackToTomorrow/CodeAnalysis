from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import sqlite3
import time

from .config import INDEX_DB_PATH
from .index_schema import CodeChunk


def ensure_db() -> sqlite3.Connection:
    INDEX_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INDEX_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    # Main chunk table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            language TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT
        );
        """
    )

    # FTS5 virtual table for full-text search
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
        USING fts5(
            id UNINDEXED,
            content,
            file_path UNINDEXED,
            tokenize = "unicode61"
        );
        """
    )

    # Simple embedding store: id -> vector (JSON array)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            vector_json TEXT NOT NULL
        );
        """
    )

    # Track per-file indexing state (for incremental decisions)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_index_state (
            file_path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            size INTEGER NOT NULL,
            last_indexed_at REAL NOT NULL
        );
        """
    )

    # Track current indexing progress (single row, id always 1)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS index_progress (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL,
            root TEXT,
            total_files INTEGER NOT NULL,
            processed_files INTEGER NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL
        );
        """
    )

    # Symbol relationships table (for calls, inheritance, etc.)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS symbol_relations (
            from_symbol_id TEXT NOT NULL,
            to_symbol_id TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            file_path TEXT NOT NULL,
            PRIMARY KEY (from_symbol_id, to_symbol_id, relation_type)
        );
        """
    )

    return conn


def upsert_chunks(conn: sqlite3.Connection, chunks: Iterable[CodeChunk]) -> None:
    chunk_rows = []
    fts_rows = []
    for c in chunks:
        metadata = {
            "symbols": [s.__dict__ for s in (c.symbols or [])],
            "extra": c.extra or {},
        }
        chunk_rows.append(
            (
                c.id,
                str(c.file_path),
                c.start_line,
                c.end_line,
                c.language,
                c.content,
                json.dumps(metadata, ensure_ascii=False),
            )
        )
        fts_rows.append((c.id, c.content, str(c.file_path)))

    with conn:
        conn.executemany(
            """
            INSERT INTO chunks (id, file_path, start_line, end_line, language, content, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                file_path=excluded.file_path,
                start_line=excluded.start_line,
                end_line=excluded.end_line,
                language=excluded.language,
                content=excluded.content,
                metadata_json=excluded.metadata_json;
            """,
            chunk_rows,
        )
        conn.execute("DELETE FROM chunks_fts;")
        conn.executemany(
            "INSERT INTO chunks_fts (id, content, file_path) VALUES (?, ?, ?);",
            fts_rows,
        )


def upsert_embeddings(
    conn: sqlite3.Connection, rows: Iterable[Tuple[str, List[float]]]
) -> None:
    db_rows = []
    for chunk_id, vec in rows:
        db_rows.append((chunk_id, json.dumps(vec)))
    with conn:
        conn.executemany(
            """
            INSERT INTO embeddings (id, vector_json)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET
                vector_json=excluded.vector_json;
            """,
            db_rows,
        )


def fts_search(
    conn: sqlite3.Connection, query: str, limit: int = 20
) -> List[Tuple[str, float]]:
    cur = conn.execute(
        """
        SELECT id, rank
        FROM chunks_fts
        WHERE chunks_fts MATCH ?
        ORDER BY rank
        LIMIT ?;
        """,
        (query, limit),
    )
    return [(row[0], float(row[1])) for row in cur.fetchall()]


def vector_search(
    conn: sqlite3.Connection, query_vec: List[float], limit: int = 20
) -> List[Tuple[str, float]]:
    # Simple brute-force cosine similarity in Python for clarity
    cur = conn.execute("SELECT id, vector_json FROM embeddings;")
    rows = cur.fetchall()
    if not rows:
        return []

    q = np.asarray(query_vec, dtype="float32")
    ids: List[str] = []
    vecs: List[np.ndarray] = []
    for cid, vjson in rows:
        ids.append(cid)
        vecs.append(np.asarray(json.loads(vjson), dtype="float32"))

    mat = np.stack(vecs, axis=0)
    # Normalize
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
    q /= np.linalg.norm(q) + 1e-8
    sims = mat @ q
    order = np.argsort(-sims)[:limit]
    return [(ids[i], float(sims[i])) for i in order]


# ---------- file state & progress helpers ----------


def read_file_index_state(conn: sqlite3.Connection) -> Dict[str, Tuple[float, int]]:
    """Return {file_path: (mtime, size)} for all tracked files."""
    cur = conn.execute("SELECT file_path, mtime, size FROM file_index_state;")
    return {row[0]: (float(row[1]), int(row[2])) for row in cur.fetchall()}


def upsert_file_state(
    conn: sqlite3.Connection, file_path: str, mtime: float, size: int
) -> None:
    now = time.time()
    with conn:
        conn.execute(
            """
            INSERT INTO file_index_state (file_path, mtime, size, last_indexed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                mtime=excluded.mtime,
                size=excluded.size,
                last_indexed_at=excluded.last_indexed_at;
            """,
            (file_path, mtime, size, now),
        )


def delete_files(conn: sqlite3.Connection, file_paths: Iterable[str]) -> None:
    fps = list(file_paths)
    if not fps:
        return
    with conn:
        # Remove chunks and FTS rows
        q_marks = ",".join("?" for _ in fps)
        conn.execute(
            f"DELETE FROM chunks WHERE file_path IN ({q_marks});",
            fps,
        )
        conn.execute(
            f"DELETE FROM chunks_fts WHERE file_path IN ({q_marks});",
            fps,
        )
        conn.execute(
            f"DELETE FROM file_index_state WHERE file_path IN ({q_marks});",
            fps,
        )
        conn.execute(
            f"DELETE FROM symbol_relations WHERE file_path IN ({q_marks});",
            fps,
        )


def init_progress(conn: sqlite3.Connection, root: str, total_files: int) -> None:
    now = time.time()
    with conn:
        conn.execute(
            """
            INSERT INTO index_progress (id, state, root, total_files, processed_files, started_at, finished_at)
            VALUES (1, ?, ?, ?, 0, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                state=excluded.state,
                root=excluded.root,
                total_files=excluded.total_files,
                processed_files=0,
                started_at=excluded.started_at,
                finished_at=NULL;
            """,
            ("running", root, total_files, now),
        )


def increment_progress(conn: sqlite3.Connection, delta: int = 1) -> None:
    with conn:
        conn.execute(
            """
            UPDATE index_progress
            SET processed_files = processed_files + ?
            WHERE id = 1;
            """,
            (delta,),
        )


def finish_progress(conn: sqlite3.Connection) -> None:
    now = time.time()
    with conn:
        conn.execute(
            """
            UPDATE index_progress
            SET state = 'idle',
                finished_at = ?
            WHERE id = 1;
            """,
            (now,),
        )


def get_progress(conn: sqlite3.Connection):
    cur = conn.execute(
        """
        SELECT state, root, total_files, processed_files, started_at, finished_at
        FROM index_progress
        WHERE id = 1;
        """
    )
    row = cur.fetchone()
    if row is None:
        return None
    keys = ["state", "root", "total_files", "processed_files", "started_at", "finished_at"]
    return dict(zip(keys, row))


def get_chunks_by_ids(
    conn: sqlite3.Connection, ids: Iterable[str]
) -> List[Dict[str, object]]:
    """Fetch chunk rows for the given ids, preserving input order where possible."""
    id_list = list(ids)
    if not id_list:
        return []

    placeholders = ",".join("?" for _ in id_list)
    cur = conn.execute(
        f"""
        SELECT id, file_path, start_line, end_line, language, content, metadata_json
        FROM chunks
        WHERE id IN ({placeholders});
        """,
        id_list,
    )
    rows = cur.fetchall()
    by_id = {}
    for r in rows:
        meta = json.loads(r[6]) if r[6] else {}
        by_id[r[0]] = {
            "id": r[0],
            "file_path": r[1],
            "start_line": int(r[2]),
            "end_line": int(r[3]),
            "language": r[4],
            "content": r[5],
            "metadata": meta,
        }

    ordered: List[Dict[str, object]] = []
    for cid in id_list:
        if cid in by_id:
            ordered.append(by_id[cid])
    return ordered


def upsert_symbol_relations(conn: sqlite3.Connection, chunks: Iterable[CodeChunk]) -> None:
    """Persist symbol relations derived from chunks into the symbol_relations table.

    Strategy: for each file_path present in the chunks, delete existing relations
    and insert the fresh set from chunk.extra["relations"].
    """
    chunk_list = list(chunks)
    if not chunk_list:
        return

    # Collect rows and file paths we touch
    file_paths: List[str] = []
    rows: List[Tuple[str, str, str, str]] = []

    for c in chunk_list:
        fp = str(c.file_path)
        if fp not in file_paths:
            file_paths.append(fp)
        extra = c.extra or {}
        rels = extra.get("relations") or []
        for r in rels:
            # r could be dataclass dict or already a mapping
            from_id = r.get("from_symbol_id")
            to_id = r.get("to_symbol_id")
            rel_type = r.get("relation_type")
            if not from_id or not to_id or not rel_type:
                continue
            rows.append((from_id, to_id, rel_type, fp))

    if not file_paths:
        return

    q_marks = ",".join("?" for _ in file_paths)
    with conn:
        # Remove old relations for these files
        conn.execute(
            f"DELETE FROM symbol_relations WHERE file_path IN ({q_marks});",
            file_paths,
        )
        if rows:
            conn.executemany(
                """
                INSERT OR REPLACE INTO symbol_relations (
                    from_symbol_id,
                    to_symbol_id,
                    relation_type,
                    file_path
                ) VALUES (?, ?, ?, ?);
                """,
                rows,
            )


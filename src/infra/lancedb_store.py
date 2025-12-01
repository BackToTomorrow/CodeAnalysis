from __future__ import annotations

from typing import Iterable, List, Tuple

import lancedb
import pyarrow as pa

from .config import LANCEDB_DIR
from ..core.models import CodeChunk


TABLE_NAME = "code_vectors"


def _connect_db():
    LANCEDB_DIR.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(LANCEDB_DIR))


def _ensure_table():
    db = _connect_db()
    if TABLE_NAME in db.table_names():
        return db.open_table(TABLE_NAME)

    # Minimal schema: id, file_path, vector
    schema = pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("file_path", pa.string()),
            pa.field("vector", pa.list_(pa.float32())),
        ]
    )
    return db.create_table(TABLE_NAME, data=[], schema=schema)


def upsert_embeddings(chunks: Iterable[CodeChunk], vectors: Iterable[List[float]]) -> None:
    """Upsert vectors for the given chunks into LanceDB.

    Strategy: delete existing rows with those ids, then add fresh ones.
    """
    table = _ensure_table()
    chunk_list = list(chunks)
    vec_list = list(vectors)
    if not chunk_list or not vec_list:
        return

    if len(chunk_list) != len(vec_list):
        raise ValueError("chunks and vectors must have same length")

    ids = [c.id for c in chunk_list]
    # Delete existing rows for these ids (if any)
    # LanceDB uses a SQL-like predicate string.
    # For many ids we build an IN (...) clause.
    id_list = ",".join("'" + i.replace("'", "''") + "'" for i in ids)
    predicate = f"id IN ({id_list})"
    table.delete(where=predicate)

    rows = []
    for c, v in zip(chunk_list, vec_list):
        rows.append(
            {
                "id": c.id,
                "file_path": str(c.file_path),
                "vector": [float(x) for x in v],
            }
        )
    table.add(rows)


def delete_by_file_paths(file_paths: Iterable[str]) -> None:
    """Remove all vectors for the given file paths.

    Useful when files are deleted from the C# project.
    """
    table = _ensure_table()
    fps = list(file_paths)
    if not fps:
        return
    fp_list = ",".join("'" + p.replace("'", "''") + "'" for p in fps)
    predicate = f"file_path IN ({fp_list})"
    table.delete(where=predicate)


def vector_search(query_vec: List[float], limit: int = 20) -> List[Tuple[str, float]]:
    """Return (chunk_id, similarity_score) using LanceDB search.

    LanceDB returns a distance; we convert to a similarity in (0, 1].
    """
    table = _ensure_table()
    if table.count_rows() == 0:
        return []

    df = table.search(query_vec).limit(limit).to_pandas()
    # LanceDB exposes distance as "_distance" column
    results: List[Tuple[str, float]] = []
    for _, row in df.iterrows():
        dist = float(row["_distance"])
        score = 1.0 / (1.0 + dist)
        results.append((row["id"], score))
    return results




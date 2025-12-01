from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List

import numpy as np
import requests

from .config import EMBEDDING_API_BASE_URL, EMBEDDING_MODEL_NAME


@lru_cache(maxsize=1)
def _embedding_endpoint() -> str:
    base = EMBEDDING_API_BASE_URL.rstrip("/")
    return f"{base}/embeddings"


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    text_list = list(texts)
    if not text_list:
        return []

    url = _embedding_endpoint()
    # llama.cpp server uses an OpenAI-compatible embeddings API:
    # POST /v1/embeddings with JSON { "model": "...", "input": ["text1", "text2", ...] }
    payload = {
        "model": EMBEDDING_MODEL_NAME,
        "input": text_list,
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    # OpenAI / llama.cpp format: { "data": [ { "embedding": [...] }, ... ] }
    vectors = [item["embedding"] for item in data.get("data", [])]

    arr = np.asarray(vectors, dtype="float32")
    # Normalize to unit length like before
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-8
    arr = arr / norms
    return arr.tolist()


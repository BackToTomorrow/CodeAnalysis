from __future__ import annotations

from functools import lru_cache
from typing import Iterable, List, Dict, Any, Optional

import numpy as np
import requests

from .config import (
    EMBEDDING_API_BASE_URL,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_PROVIDER,
    EMBEDDING_API_KEY,
    EMBEDDING_TIMEOUT,
)


class _OpenAICompatibleEmbeddingClient:
    """Embedding client for any OpenAI-compatible HTTP API.

    This works with:
    - llama.cpp server exposing `/v1/embeddings`
    - Ollama in OpenAI-compatible mode
    - OpenAI / Azure OpenAI style endpoints
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str],
        timeout: int,
    ) -> None:
        self._endpoint = base_url.rstrip("/") + "/embeddings"
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        payload: Dict[str, Any] = {
            "model": self._model,
            "input": texts,
        }

        resp = requests.post(
            self._endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        # Expected format: { "data": [ { "embedding": [...] }, ... ] }
        vectors = [item["embedding"] for item in data.get("data", [])]

        arr = np.asarray(vectors, dtype="float32")
        # Normalize to unit length like before
        norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-8
        arr = arr / norms
        return arr.tolist()


@lru_cache(maxsize=1)
def _get_client() -> _OpenAICompatibleEmbeddingClient:
    """Return a singleton embedding client based on configuration.

    Currently all supported providers (llama.cpp, Ollama, OpenAI-like) use
    the same OpenAI-compatible HTTP shape, so we reuse the same client class
    and rely on config for base URL / model / auth.
    """
    provider = (EMBEDDING_PROVIDER or "llama_cpp").lower()

    # In the future we could branch on provider for provider-specific logic,
    # but today they are all OpenAI-compatible.
    _ = provider  # keep linters happy until we add branching logic

    return _OpenAICompatibleEmbeddingClient(
        base_url=EMBEDDING_API_BASE_URL,
        model=EMBEDDING_MODEL_NAME,
        api_key=EMBEDDING_API_KEY,
        timeout=EMBEDDING_TIMEOUT,
    )


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    """Embed a batch of texts using the configured embedding provider.

    The rest of the codebase should call this function and not depend on
    any provider-specific behavior.
    """
    client = _get_client()
    return client.embed(list(texts))


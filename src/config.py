from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

# Where to persist the SQLite + FTS index
INDEX_DB_PATH = BASE_DIR / "index" / "code_index.db"

# Where to store LanceDB tables (vector index)
LANCEDB_DIR = BASE_DIR / "index" / "lancedb"

# Embedding service configuration
#
# The embedding client talks to an OpenAI-compatible embeddings endpoint so it can
# work with:
# - llama.cpp server (`/v1/embeddings`)
# - local Ollama in OpenAI-compatible mode
# - hosted OpenAI-like services (OpenAI, Azure OpenAI, etc.)
#
# Provider is informational (used for defaults / documentation) – all of them use
# the same OpenAI-compatible HTTP shape.
#
# Valid values: "llama_cpp", "ollama", "openai_compat"
EMBEDDING_PROVIDER = "llama_cpp"

# Base URL of the OpenAI-compatible API (including `/v1`).
# Examples:
# - llama.cpp: "http://127.0.0.1:8080/v1"
# - Ollama (OpenAI-compatible): "http://127.0.0.1:11434/v1"
# - OpenAI: "https://api.openai.com/v1"
EMBEDDING_API_BASE_URL = "http://127.0.0.1:8080/v1"

# Embedding model name
# Examples:
# - llama.cpp: "embed-model"
# - Ollama: "nomic-embed-text" (or any embeddings model you pulled)
# - OpenAI: "text-embedding-3-small"
EMBEDDING_MODEL_NAME = "embed-model"

# Optional API key / token for providers that require auth (e.g. OpenAI).
# For llama.cpp or a local Ollama without auth enabled, you can leave this empty.
EMBEDDING_API_KEY: str | None = None

# HTTP timeout for embedding requests (seconds)
EMBEDDING_TIMEOUT = 60

# File extensions to treat as C# source
CSHARP_EXTENSIONS = [".cs"]



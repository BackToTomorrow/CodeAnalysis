from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

# Where to persist the SQLite + FTS index
INDEX_DB_PATH = BASE_DIR / "index" / "code_index.db"

# Where to store LanceDB tables (vector index)
LANCEDB_DIR = BASE_DIR / "index" / "lancedb"

# Remote embedding service hosted by llama.cpp (OpenAI-compatible API)
# Adjust these to match your server configuration.
EMBEDDING_API_BASE_URL = "http://127.0.0.1:8080/v1"
EMBEDDING_MODEL_NAME = "embed-model"

# File extensions to treat as C# source
CSHARP_EXTENSIONS = [".cs"]



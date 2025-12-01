## C# Code Analysis & Hybrid Search (Python)

This project is a minimal, extensible solution for analysing C# projects from Python using:

- **AST parsing** via `tree_sitter` (C# grammar) to extract symbols and structure.
- **Hybrid search** combining **vector similarity** (LanceDB + external embeddings) and **full‑text search** (SQLite FTS5).
- A small **HTTP API** (FastAPI + Uvicorn), inspired by indexers like the *Continue* extension.

### 1. Install

```bash
cd CodeBaseAnalyse
python -m venv .venv
.venv\Scripts\activate  # PowerShell
pip install -r requirements.txt
```

### 2. Configure embedding service

This solution expects an **embedding model service** hosted by `llama.cpp` (OpenAI‑compatible API):

- Default base URL: `http://127.0.0.1:8080/v1`
- Default model name: `embed-model`

You can change these in `src/config.py`:

```python
EMBEDDING_API_BASE_URL = "http://127.0.0.1:8080/v1"
EMBEDDING_MODEL_NAME = "embed-model"
```

Then start your `llama.cpp` server separately (example):

```bash
./server -m /path/to/your-embed-model.gguf --port 8080
```

### 3. Run the API server

```bash
python main.py
```

Server runs on `http://127.0.0.1:8000`.

### 4. Index a C# project (smart full/incremental)

Send a POST request:

```bash
curl -X POST http://127.0.0.1:8000/index/sync ^
  -H "Content-Type: application/json" ^
  -d "{\\"root\\": \\"C:\\\\path\\\\to\\\\your\\\\csharp-solution\\"}"
```

This will:

- Walk all `*.cs` files under the given root.
- Parse them with tree-sitter C#.
- Extract basic symbols (classes, methods, etc.).
- Store chunks + metadata in SQLite with FTS.
- Call your `llama.cpp` embedding service to generate embeddings.
- Store vectors in LanceDB for fast vector search.
- Track per‑file state so subsequent runs only reindex changed files (incremental).

You can check indexing progress:

```bash
curl http://127.0.0.1:8000/index/status
```

### 5. Query the index

- **Hybrid search**:

```bash
curl -X POST http://127.0.0.1:8000/search/hybrid ^
  -H "Content-Type: application/json" ^
  -d "{\\"query\\": \\"http client retry logic\\", \\"k\\": 10, \\"alpha\\": 0.6}"
```

- **Semantic only**:

```bash
curl -X POST http://127.0.0.1:8000/search/semantic ^
  -H "Content-Type: application/json" ^
  -d "{\\"query\\": \\"how we validate JWT tokens\\", \\"k\\": 10}"
```

- **Text/FTS only**:

```bash
curl -X POST http://127.0.0.1:8000/search/text ^
  -H "Content-Type: application/json" ^
  -d "{\\"query\\": \\"ILogger AND Startup\\", \\"k\\": 10}"
```

### 6. How it maps to a “Continue”-style indexer

- **AST layer (`src/ast_csharp.py`)**:
  - Uses tree-sitter C#.
  - Extracts `class`, `struct`, `interface`, `enum`, `method`, `property` symbols.
  - Attaches them to file‑level `CodeChunk`s (you can refine this to symbol‑level chunks).

- **Storage layer (`src/storage.py` + `src/vector_store.py`)**:
  - `chunks` table stores code, line ranges, language, metadata (symbols etc.).
  - `chunks_fts` is an SQLite FTS5 virtual table for full‑text search.
  - `code_vectors` LanceDB table stores vectors for semantic search.

- **Indexer (`src/indexer.py`)**:
  - Walks all `*.cs` files.
  - Parses AST and builds `CodeChunk`s.
  - Upserts chunks into SQLite + FTS.
  - Calls the external embed service and stores vectors in LanceDB.
  - Keeps per‑file index state and exposes a smart `/index/sync` endpoint (full vs incremental).

- **Search (`src/search.py`)**:
  - `text_search` uses FTS only.
  - `semantic_search` uses LanceDB vector similarity only.
  - `hybrid_search` linearly combines both (parameter `alpha`).

- **Context builder (`src/prompting.py` + `/search/hybrid/context`)**:
  - Takes hybrid search results and builds a high‑quality prompt string
    (code snippets + instructions + original question) that you can send
    directly to a chat model.

### 7. Built‑in C# test project (for debugging)

For quick local testing, this repo includes a small C# console app under `test_csharp_project`.

- **Target framework**: `net8.0`
- **Entry point**: `test_csharp_project/Program.cs`
- Contains a mix of **classes**, **enums**, **interfaces**, **services**, and **method calls** so
  you can easily inspect symbol extraction and relations from `src/ast_csharp.py`.

To index this built‑in test project, you can point the `root` to the folder in this repo. For example,
if your workspace is located at `C:\Users\you\Desktop\Project\CodeAnalysis`:

```bash
curl -X POST http://127.0.0.1:8000/index/sync ^
  -H "Content-Type: application/json" ^
  -d "{\\"root\\": \\"C:\\\\Users\\\\you\\\\Desktop\\\\Project\\\\CodeAnalysis\\\\test_csharp_project\\"}"
```

You can then experiment with the search endpoints against this small, known codebase.

### 8. Next steps / customization

- Split large files into **semantic chunks** (per method or fixed line window).
- Store **symbol relationships** (e.g. calls, inheritance) in an extra table for richer queries.
- Add endpoints to:
  - Fetch chunk content + symbol metadata by `id`.
  - Index **incremental changes** from your editor.
- Tune the `hybrid_search` `alpha` parameter to balance semantic vs keyword matches.
- Customize the context prompt in `src/prompting.py` to match your preferred system prompt.
- Add authentication / multi‑repo support around the existing HTTP API.



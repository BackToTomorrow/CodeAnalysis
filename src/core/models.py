from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class SymbolInfo:
    id: str
    file_path: Path
    symbol_name: str
    symbol_kind: str  # e.g. class, method, property
    start_line: int
    end_line: int
    signature: Optional[str]
    docstring: Optional[str]


@dataclass
class CodeChunk:
    id: str
    file_path: Path
    start_line: int
    end_line: int
    content: str
    language: str = "csharp"
    symbols: List[SymbolInfo] | None = None
    extra: Dict[str, Any] | None = None


@dataclass
class SymbolRelation:
    """Lightweight representation of relationships between symbols."""

    from_symbol_id: str
    to_symbol_id: str
    relation_type: str  # e.g. "calls", "inherits"



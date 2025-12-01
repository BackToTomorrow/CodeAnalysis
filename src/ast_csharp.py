from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Dict

from tree_sitter import Parser
from tree_sitter_languages import get_language

from .index_schema import CodeChunk, SymbolInfo, SymbolRelation


class CSharpAstParser:
    """Thin wrapper around tree-sitter-c-sharp to extract symbols, relationships, and chunks."""

    def __init__(self) -> None:
        language = get_language("c_sharp")
        self._parser = Parser(language)

    def parse_file(self, path: Path) -> List[CodeChunk]:
        source_bytes = path.read_bytes()
        tree = self._parser.parse(source_bytes)
        root = tree.root_node

        symbols: List[SymbolInfo] = []

        for node in root.children:
            symbols.extend(self._extract_symbols(path, node, source_bytes))

        # Build simple symbol index for this file
        symbols_by_key: Dict[tuple, SymbolInfo] = {}
        for s in symbols:
            key = (s.symbol_kind, s.symbol_name, s.start_line)
            symbols_by_key[key] = s

        relations: List[SymbolRelation] = self._extract_relations(
            path, root, source_bytes, symbols_by_key
        )

        # For now, create a single big chunk per file, tagged with symbol + relation metadata
        text = source_bytes.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        chunk = CodeChunk(
            id=f"file:{path}",
            file_path=path,
            start_line=1,
            end_line=len(lines),
            content=text,
            language="csharp",
            symbols=symbols,
            extra={
                "symbol_dicts": [asdict(s) for s in symbols],
                "relations": [asdict(r) for r in relations],
            },
        )
        return [chunk]

    # ---- internals -----------------------------------------------------

    def _extract_symbols(
        self, path: Path, node, source_bytes: bytes
    ) -> Iterable[SymbolInfo]:
        # tree-sitter-c-sharp node types for top-level symbols
        interesting_types = {
            "class_declaration": "class",
            "struct_declaration": "struct",
            "interface_declaration": "interface",
            "enum_declaration": "enum",
            "method_declaration": "method",
            "property_declaration": "property",
        }

        results: List[SymbolInfo] = []
        stack = [node]
        while stack:
            n = stack.pop()
            kind = interesting_types.get(n.type)
            if kind:
                name_node = self._find_child_of_type(n, "identifier")
                name = (
                    source_bytes[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8", errors="ignore"
                    )
                    if name_node is not None
                    else "<anonymous>"
                )

                signature = self._node_source(n, source_bytes).splitlines()[0].strip()

                results.append(
                    SymbolInfo(
                        id=f"{path}:{n.start_point[0]+1}:{name}",
                        file_path=path,
                        symbol_name=name,
                        symbol_kind=kind,
                        start_line=n.start_point[0] + 1,
                        end_line=n.end_point[0] + 1,
                        signature=signature,
                        docstring=None,
                    )
                )

            stack.extend(n.children)

        return results

    def _extract_relations(
        self,
        path: Path,
        root,
        source_bytes: bytes,
        symbols_by_key: Dict[tuple, SymbolInfo],
    ) -> List[SymbolRelation]:
        """Derive basic relationships (inheritance, calls) between symbols in a single file."""
        relations: List[SymbolRelation] = []

        def find_symbol(kind: str, name: str, start_line: int) -> SymbolInfo | None:
            return symbols_by_key.get((kind, name, start_line))

        stack = [root]
        while stack:
            n = stack.pop()

            # Inheritance: class/struct/interface base list
            if n.type in {"class_declaration", "struct_declaration", "interface_declaration"}:
                name_node = self._find_child_of_type(n, "identifier")
                if name_node is not None:
                    name = source_bytes[name_node.start_byte : name_node.end_byte].decode(
                        "utf-8", errors="ignore"
                    )
                    kind = {
                        "class_declaration": "class",
                        "struct_declaration": "struct",
                        "interface_declaration": "interface",
                    }[n.type]
                    from_sym = find_symbol(kind, name, n.start_point[0] + 1)
                    if from_sym is not None:
                        # Look for base_list identifiers (base types / interfaces)
                        for child in n.children:
                            if child.type == "base_list":
                                for id_node in self._find_all_of_type(child, "identifier"):
                                    base_name = source_bytes[
                                        id_node.start_byte : id_node.end_byte
                                    ].decode("utf-8", errors="ignore")
                                    # We don't know exact kind of base; try common kinds
                                    for base_kind in ("class", "interface", "struct"):
                                        base_sym = find_symbol(
                                            base_kind, base_name, id_node.start_point[0] + 1
                                        )
                                        if base_sym is not None:
                                            relations.append(
                                                SymbolRelation(
                                                    from_symbol_id=from_sym.id,
                                                    to_symbol_id=base_sym.id,
                                                    relation_type="inherits",
                                                )
                                            )
                                            break

            # Call graph: method_declaration -> invocation_expression
            if n.type == "method_declaration":
                name_node = self._find_child_of_type(n, "identifier")
                if name_node is not None:
                    method_name = source_bytes[
                        name_node.start_byte : name_node.end_byte
                    ].decode("utf-8", errors="ignore")
                    from_sym = find_symbol("method", method_name, n.start_point[0] + 1)
                else:
                    from_sym = None

                if from_sym is not None:
                    for inv in self._find_all_of_type(n, "invocation_expression"):
                        id_node = self._find_child_of_type(inv, "identifier")
                        if id_node is None:
                            continue
                        callee_name = source_bytes[
                            id_node.start_byte : id_node.end_byte
                        ].decode("utf-8", errors="ignore")
                        # Try to resolve callee within same file
                        callee_sym = None
                        for candidate_kind in ("method", "function"):
                            sym = find_symbol(
                                candidate_kind, callee_name, id_node.start_point[0] + 1
                            )
                            if sym is not None:
                                callee_sym = sym
                                break
                        if callee_sym is not None:
                            relations.append(
                                SymbolRelation(
                                    from_symbol_id=from_sym.id,
                                    to_symbol_id=callee_sym.id,
                                    relation_type="calls",
                                )
                            )

            stack.extend(n.children)

        return relations

    @staticmethod
    def _find_child_of_type(node, type_name: str):
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    @staticmethod
    def _find_all_of_type(node, type_name: str):
        stack = [node]
        out = []
        while stack:
            n = stack.pop()
            if n.type == type_name:
                out.append(n)
            stack.extend(n.children)
        return out

    @staticmethod
    def _node_source(node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="ignore"
        )


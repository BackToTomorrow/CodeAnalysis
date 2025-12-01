from __future__ import annotations

from typing import Iterable, Dict, List


DEFAULT_CONTEXT_PROMPT_TEMPLATE = """You are an AI assistant helping a developer understand and work with a large C# codebase.

You are given a user question and a set of relevant code snippets from the repository.

<INSTRUCTIONS>
- Use ONLY the information in the provided code snippets as your primary source of truth.
- If the answer is not clearly present in the snippets, say you don't know based on the given context.
- When you reference code, mention the file path and line numbers.
- Prefer precise, practical explanations over vague descriptions.
- If useful, explain how the shown code fits into the larger architecture (based on the context you see).
</INSTRUCTIONS>

<CODE_CONTEXT>
{contexts}
</CODE_CONTEXT>

<USER_QUESTION>
{query}
</USER_QUESTION>

Now provide a clear, concise, and helpful answer for the user, grounded in the code context above.
"""


def _symbol_name_from_id(sym_id: str) -> str:
    # Our symbol ids are roughly "path:startLine:name"; last segment is the name.
    return sym_id.rsplit(":", 1)[-1]


def format_code_context(chunks: Iterable[Dict[str, object]]) -> str:
    parts: List[str] = []
    for idx, ch in enumerate(chunks, start=1):
        file_path = ch["file_path"]
        start_line = ch["start_line"]
        end_line = ch["end_line"]
        language = ch.get("language") or "csharp"
        content = ch["content"]

        metadata = ch.get("metadata") or {}
        extra = metadata.get("extra") or {}
        relations = extra.get("relations") or []

        rel_lines: List[str] = []
        for rel in relations:
            rtype = rel.get("relation_type") or rel.get("type")
            from_id = rel.get("from_symbol_id") or rel.get("from_id")
            to_id = rel.get("to_symbol_id") or rel.get("to_id")
            if not rtype or not from_id or not to_id:
                continue
            from_name = _symbol_name_from_id(str(from_id))
            to_name = _symbol_name_from_id(str(to_id))
            if rtype == "inherits":
                rel_lines.append(f"- inherits: {from_name} -> {to_name}")
            elif rtype == "calls":
                rel_lines.append(f"- calls: {from_name} -> {to_name}")
            else:
                rel_lines.append(f"- {rtype}: {from_name} -> {to_name}")

        rel_block = ""
        if rel_lines:
            rel_block = "Relationships in this snippet:\n" + "\n".join(rel_lines) + "\n\n"

        # We don't enforce language in the fence, but "csharp" helps editors.
        snippet = (
            f"=== Snippet {idx} ===\n"
            f"File: {file_path} (lines {start_line}-{end_line})\n"
            f"{rel_block}"
            f"```{language}\n"
            f"{content}\n"
            f"```\n"
        )
        parts.append(snippet)
    return "\n".join(parts)


def build_context_prompt(
    query: str,
    chunks: Iterable[Dict[str, object]],
    template: str | None = None,
) -> str:
    """Build a high-quality prompt to be sent to a chat model.

    - query: the original user question
    - chunks: code chunks fetched from storage for relevant search hits
    - template: optional override; must contain {query} and {contexts}
    """
    tmpl = template or DEFAULT_CONTEXT_PROMPT_TEMPLATE
    contexts = format_code_context(chunks)
    return tmpl.format(query=query, contexts=contexts)




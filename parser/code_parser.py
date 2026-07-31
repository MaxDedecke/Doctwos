from typing import Dict, List


class CodeParser:
    """
    Generic line-based text chunker used for all file types (code, documents,
    markdown). Historically dispatched to per-language AST parsers via
    `languages/`, but that layer never actually extracted anything in
    production (PARSER_REGISTRY was always empty, extract_references() always
    returned []) — see docs/TECH_DEBT_CLEANUP_PLAN.md §1. Only chunking, which
    was always language-agnostic, survives.
    """

    def __init__(self, language_name: str):
        self.language_name = language_name

    def chunk_file(self, content: str, chunk_size: int = 1000, overlap_size: int = 150) -> List[Dict]:
        """
        Splits the file content into logical text chunks of a given maximum character size,
        with an overlap of characters to preserve context across boundaries.

        Args:
            content: The raw text content of the file.
            chunk_size: Target size in characters for each chunk.
            overlap_size: Target size in characters for chunk overlap.

        Returns:
            A list of dictionaries containing:
                - 'content': The string content of the chunk.
                - 'start_line': The 1-based start line of the chunk in the original file.
                - 'end_line': The 1-based end line of the chunk in the original file.
        """
        if not content.strip():
            return []

        lines = content.splitlines()
        chunks = []
        n = len(lines)
        i = 0

        while i < n:
            current_chunk_lines = []
            current_len = 0
            start_line = i + 1

            j = i
            while j < n:
                line = lines[j]
                if current_len > 0 and current_len + len(line) > chunk_size:
                    break
                current_chunk_lines.append(line)
                current_len += len(line) + 1  # Include newline length approximation
                j += 1

            end_line = j
            chunks.append({
                "content": "\n".join(current_chunk_lines),
                "start_line": start_line,
                "end_line": end_line
            })

            if j == n:
                break

            # Compute overlap to find next starting index
            overlap_len = 0
            next_start = j
            while next_start > i:
                line_len = len(lines[next_start - 1]) + 1
                if overlap_len + line_len > overlap_size:
                    break
                overlap_len += line_len
                next_start -= 1

            # Prevent infinite loops if progress is blocked
            if next_start == i:
                i = j
            else:
                i = next_start

        return chunks

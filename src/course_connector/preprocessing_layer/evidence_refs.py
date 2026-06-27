"""Evidence locator helpers for human review."""

from __future__ import annotations

from typing import Any


def coarse_file_locator() -> dict[str, Any]:
    """Locator for a whole file when a precise range is not available."""
    return {"kind": "coarse_file"}


def object_path_locator(path: str) -> dict[str, Any]:
    """Locator for structured data paths such as modules[0]."""
    return {"kind": "object_path", "object_path": path}


def row_locator(row_index: int) -> dict[str, Any]:
    """Locator for CSV rows, using one-based data row index."""
    return {"kind": "row_index", "row_index": row_index}


def line_range_locator(line_start: int, line_end: int) -> dict[str, Any]:
    """Locator for text line ranges, using one-based line numbers."""
    return {"kind": "line_range", "line_start": line_start, "line_end": line_end}


def evidence_ref(chunk: dict[str, Any]) -> dict[str, Any]:
    """Build a compact evidence reference from a chunk."""
    return {
        "chunk_id": chunk["chunk_id"],
        "source_role": chunk["source_role"],
        "source_path": chunk["source_path"],
        "source_type": chunk["source_type"],
        "locator": chunk["locator"],
    }

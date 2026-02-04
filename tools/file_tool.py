"""
File information tool for MCP.
Provides information about files in the project directory.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

# Project root: directory containing the tools/ package (mcp-example root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def execute(
    directory: Optional[str] = None,
    max_depth: Optional[int] = None,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    """
    List files and directories in the project (or a subdirectory) with basic metadata.

    - directory: Relative path from project root, or empty/None for project root.
    - max_depth: Maximum depth to traverse (1 = root only, 2 = root + one level, etc.). None = no limit (single-level list only).
    - include_hidden: If true, include entries whose names start with '.'.
    """
    base = PROJECT_ROOT
    if directory and directory.strip():
        base = (PROJECT_ROOT / directory.strip()).resolve()
        if not base.is_dir():
            return {"error": f"Not a directory or not found: {directory}", "entries": []}
        if not str(base).startswith(str(PROJECT_ROOT)):
            return {"error": "Path must be inside project directory", "entries": []}

    depth_limit = max_depth if max_depth is not None else 1
    entries: List[Dict[str, Any]] = []

    try:
        for p in sorted(base.iterdir()):
            if not include_hidden and p.name.startswith("."):
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            entry: Dict[str, Any] = {
                "name": p.name,
                "path": str(p.relative_to(PROJECT_ROOT)),
                "type": "directory" if p.is_dir() else "file",
            }
            if p.is_file():
                entry["size_bytes"] = stat.st_size
            entries.append(entry)
    except OSError as e:
        return {"error": str(e), "entries": []}

    return {
        "directory": str(base.relative_to(PROJECT_ROOT)) if base != PROJECT_ROOT else ".",
        "project_root": str(PROJECT_ROOT),
        "entries": entries,
        "count": len(entries),
    }


TOOL_METADATA = {
    "name": "project_files",
    "description": (
        "Get information about files and directories in the project. "
        "Returns a list of entries with name, path, type (file or directory), and size for files. "
        "Use directory to list a subdirectory (path relative to project root). "
        "Use include_hidden=true to include dotfiles/dot-directories."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Relative path from project root to list (e.g. 'tools' or 'example_client'). Omit or empty for project root.",
            },
            "max_depth": {
                "type": "integer",
                "description": "Maximum depth to list; 1 means only direct children of the given directory. Omit for single-level listing.",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "If true, include files and directories whose names start with '.'.",
                "default": False,
            },
        },
        "required": [],
    },
}

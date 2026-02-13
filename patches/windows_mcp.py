"""
LLM-adaptive patch descriptions for windows-mcp.

Instead of static diffs, this module describes WHAT needs to change and WHY.
Claude Code reads current windows-mcp source and generates version-appropriate patches.

This file is the "patch intent" — the actual patching is done by Claude Code itself
when HealthCheck detects patches are missing.
"""

import os
from pathlib import Path

# windows-mcp install location — configurable via environment variable,
# defaults to standard Claude Extensions path for any user
WINDOWS_MCP_PATH = Path(
    os.environ.get(
        "WINDOWS_MCP_PATH",
        os.path.expandvars(
            r"%APPDATA%\Claude\Claude Extensions\ant.dir.cursortouch.windows-mcp"
        ),
    )
)

# Each patch describes intent, not implementation
PATCH_INTENTS = [
    {
        "id": "dpi_awareness",
        "description": "Make Click-Tool and Move-Tool DPI-aware",
        "intent": """
            The Click-Tool and Move-Tool in windows-mcp accept coordinates but don't account
            for Windows DPI scaling. On systems with scaling > 100%, the coordinates passed
            by the LLM (which come from State-Tool in physical space) are correct, but any
            coordinates derived from Win32 API calls (GetWindowRect, etc.) are in logical space
            and need conversion.

            The fix: Add an optional 'coordinate_system' parameter to Click-Tool and Move-Tool
            that accepts 'physical' (default, no conversion) or 'logical' (multiply by scale factor).
            The scale factor should be read from precision-desktop's calibration.json.
        """,
        "priority": "medium",
        "phase": 2,
    },
    {
        "id": "find_and_click",
        "description": "Add text-target support to Click-Tool",
        "intent": """
            Add an optional 'element_name' parameter to Click-Tool. When provided (instead of
            coordinates), use Windows UI Automation to find the element by name and click its
            center. This enables Click-Tool to work without coordinate estimation.

            Implementation: Call precision-desktop's find_element module via subprocess or
            import, get center_x/center_y (already physical), then click there.
        """,
        "priority": "high",
        "phase": 2,
    },
]


def get_patch_status() -> list[dict]:
    """
    Check which patches are applied by reading current windows-mcp source.
    Returns list of patches with their current status.
    """
    main_py = WINDOWS_MCP_PATH / "main.py"
    if not main_py.exists():
        return [{"id": p["id"], "status": "cannot_check", "reason": "main.py not found"}
                for p in PATCH_INTENTS]

    source = main_py.read_text(encoding="utf-8")
    results = []

    for patch in PATCH_INTENTS:
        if patch["id"] == "dpi_awareness":
            applied = "coordinate_system" in source
        elif patch["id"] == "find_and_click":
            applied = "element_name" in source
        else:
            applied = False

        results.append({
            "id": patch["id"],
            "description": patch["description"],
            "status": "applied" if applied else "not_applied",
            "phase": patch["phase"],
            "priority": patch["priority"],
        })

    return results


def get_patch_prompt(patch_id: str) -> str | None:
    """
    Get the prompt that Claude Code should use to apply a specific patch.
    Returns None if patch_id is unknown.
    """
    for patch in PATCH_INTENTS:
        if patch["id"] == patch_id:
            main_py = WINDOWS_MCP_PATH / "main.py"
            return (
                f"Read the file at {main_py} and modify it to implement this change:\n\n"
                f"**{patch['description']}**\n\n"
                f"{patch['intent'].strip()}\n\n"
                f"Make minimal changes. Preserve all existing functionality. "
                f"Add the new parameter as optional with backward-compatible defaults."
            )
    return None

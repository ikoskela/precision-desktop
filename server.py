#!/usr/bin/env python3
"""
precision-desktop MCP Server

Companion MCP for windows-mcp providing:
- DPI coordinate calibration (user-assisted with MPos)
- UI Automation element finding (FindElement)
- Environment health checks
- Coordinate conversion between physical/logical systems
"""

import asyncio
import json
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import calibration
import find_element
import health_check
from patches import windows_mcp as patches

server = Server("precision-desktop")


# ─── Tool Definitions ───────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="calibrate",
            description=(
                "Calibrate DPI coordinate systems. Provide 2+ points with both "
                "physical (Click-Tool/Move-Tool) and logical (Cursor.Position/GetWindowRect) "
                "coordinates. Use MPos or similar tool to read coordinates at known landmarks. "
                "Landmarks: Start button (bottom-left), Date/time (bottom-right), "
                "Minimize button (upper-right)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "physical_x": {"type": "integer", "description": "X in physical coords (Click-Tool space)"},
                                "physical_y": {"type": "integer", "description": "Y in physical coords (Click-Tool space)"},
                                "logical_x": {"type": "integer", "description": "X in logical coords (Cursor.Position space)"},
                                "logical_y": {"type": "integer", "description": "Y in logical coords (Cursor.Position space)"},
                                "label": {"type": "string", "description": "Landmark name (e.g. 'start_button', 'datetime')"},
                            },
                            "required": ["physical_x", "physical_y", "logical_x", "logical_y"],
                        },
                        "minItems": 2,
                        "description": "Calibration points with both coordinate systems",
                    },
                },
                "required": ["points"],
            },
        ),
        Tool(
            name="calibrate_verify",
            description=(
                "Mark calibration as verified after Move-Tool confirmation. "
                "Call this after using Move-Tool to go to a known landmark and "
                "confirming the cursor landed correctly."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean", "description": "Did the cursor land on the expected landmark?"},
                    "notes": {"type": "string", "description": "Optional verification notes"},
                },
                "required": ["success"],
            },
        ),
        Tool(
            name="get_calibration",
            description="Get current calibration state (scale factors, verification status).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="convert_coordinates",
            description=(
                "Convert coordinates between physical and logical systems. "
                "Physical = Click-Tool/Move-Tool/State-Tool space. "
                "Logical = GetWindowRect/Cursor.Position/.NET space."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "from_system": {
                        "type": "string",
                        "enum": ["physical", "logical"],
                        "description": "Source coordinate system",
                    },
                    "to_system": {
                        "type": "string",
                        "enum": ["physical", "logical"],
                        "description": "Target coordinate system",
                    },
                },
                "required": ["x", "y", "from_system", "to_system"],
            },
        ),
        Tool(
            name="find_ui_element",
            description=(
                "Find a UI element by name using Windows UI Automation. "
                "Returns physical coordinates ready for Click-Tool/Move-Tool. "
                "Works where State-Tool cannot see (Chrome extension popups, "
                "overlay dialogs, native app controls)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "element_name": {"type": "string", "description": "Name of the UI element to find (exact match)"},
                    "window_title": {"type": "string", "description": "Window title to scope search (substring match)"},
                    "window_handle": {"type": "integer", "description": "Window handle (hwnd) — takes priority over title"},
                },
                "required": ["element_name"],
            },
        ),
        Tool(
            name="find_all_ui_elements",
            description=(
                "Find ALL UI elements matching a name. Returns list of physical coordinates. "
                "Useful when multiple elements share the same name (e.g. multiple 'Close' buttons)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "element_name": {"type": "string", "description": "Name to search for"},
                    "window_title": {"type": "string", "description": "Window title to scope search"},
                    "window_handle": {"type": "integer", "description": "Window handle (hwnd)"},
                },
                "required": ["element_name"],
            },
        ),
        Tool(
            name="list_ui_elements",
            description=(
                "List all named interactive elements in a window (buttons, text fields, etc.). "
                "Useful for discovering what's available before targeting a specific element."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "window_title": {"type": "string", "description": "Window title to scope search (substring match)"},
                    "window_handle": {"type": "integer", "description": "Window handle (hwnd)"},
                },
            },
        ),
        Tool(
            name="find_window",
            description="Find a window handle by title substring. Returns the hwnd for use with other tools.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title substring to search for"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="health_check",
            description=(
                "Run environment health checks: calibration freshness, "
                "UI Automation availability, windows-mcp status. "
                "Run at session start to ensure everything is working."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="patch_status",
            description=(
                "Check which windows-mcp patches are applied. "
                "Returns list of patch intents and whether they're currently active. "
                "If patches are missing, use Claude Code to apply them adaptively."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ─── Tool Handlers ───────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "calibrate":
            points = arguments["points"]
            state = calibration.compute_calibration(points)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": "calibrated",
                    "scale_x": state["scale_x"],
                    "scale_y": state["scale_y"],
                    "offset_x": state["offset_x"],
                    "offset_y": state["offset_y"],
                    "consistent": state["consistent"],
                    "spread_x": state.get("spread_x"),
                    "spread_y": state.get("spread_y"),
                    "points_used": len(points),
                    "next_step": (
                        "Calibration computed. To verify: use Move-Tool to go to a known "
                        "landmark (e.g. minimize button of a window), confirm the cursor "
                        "landed correctly, then call 'calibrate_verify' with the result."
                    ),
                }, indent=2),
            )]

        elif name == "calibrate_verify":
            success = arguments["success"]
            notes = arguments.get("notes", "")
            state = calibration.mark_verified(success, notes)
            status = "verified" if success else "failed"
            return [TextContent(
                type="text",
                text=json.dumps({
                    "status": status,
                    "message": f"Calibration {status}." + (f" Notes: {notes}" if notes else ""),
                    "scale_x": state["scale_x"],
                    "scale_y": state["scale_y"],
                }, indent=2),
            )]

        elif name == "get_calibration":
            state = calibration.load_state()
            return [TextContent(type="text", text=json.dumps(state, indent=2))]

        elif name == "convert_coordinates":
            x, y = arguments["x"], arguments["y"]
            from_sys = arguments["from_system"]
            to_sys = arguments["to_system"]

            if from_sys == to_sys:
                result = {"x": x, "y": y, "note": "Same system, no conversion needed"}
            elif from_sys == "physical" and to_sys == "logical":
                lx, ly = calibration.physical_to_logical(x, y)
                result = {"physical_x": x, "physical_y": y, "logical_x": lx, "logical_y": ly}
            else:
                px, py = calibration.logical_to_physical(x, y)
                result = {"logical_x": x, "logical_y": y, "physical_x": px, "physical_y": py}

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "find_ui_element":
            element_name = arguments["element_name"]
            window_title = arguments.get("window_title")
            window_handle = arguments.get("window_handle")

            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: find_element.find_element_by_name(
                    element_name, window_title, window_handle
                ),
            )

            if result:
                result["note"] = "Coordinates are PHYSICAL — use directly with Click-Tool/Move-Tool"
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "found": False,
                        "element_name": element_name,
                        "window_title": window_title,
                        "suggestion": "Try list_ui_elements to see what's available in this window.",
                    }, indent=2),
                )]

        elif name == "find_all_ui_elements":
            element_name = arguments["element_name"]
            window_title = arguments.get("window_title")
            window_handle = arguments.get("window_handle")

            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: find_element.find_elements_by_name(
                    element_name, window_title, window_handle
                ),
            )

            return [TextContent(
                type="text",
                text=json.dumps({
                    "count": len(results),
                    "elements": results,
                    "note": "All coordinates are PHYSICAL" if results else "No elements found",
                }, indent=2),
            )]

        elif name == "list_ui_elements":
            window_title = arguments.get("window_title")
            window_handle = arguments.get("window_handle")

            results = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: find_element.list_window_elements(
                    window_title, window_handle
                ),
            )

            return [TextContent(
                type="text",
                text=json.dumps({
                    "count": len(results),
                    "elements": results,
                    "note": "All coordinates are PHYSICAL" if results else "No interactive elements found",
                }, indent=2),
            )]

        elif name == "find_window":
            title = arguments["title"]
            hwnd = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: find_element.find_window_handle(title),
            )

            if hwnd:
                return [TextContent(
                    type="text",
                    text=json.dumps({"found": True, "hwnd": hwnd, "title_searched": title}, indent=2),
                )]
            else:
                return [TextContent(
                    type="text",
                    text=json.dumps({"found": False, "title_searched": title}, indent=2),
                )]

        elif name == "health_check":
            checks = await asyncio.get_event_loop().run_in_executor(
                None, health_check.run_all_checks
            )
            return [TextContent(type="text", text=json.dumps(checks, indent=2))]

        elif name == "patch_status":
            status = await asyncio.get_event_loop().run_in_executor(
                None, patches.get_patch_status
            )
            return [TextContent(type="text", text=json.dumps(status, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


# ─── Main ────────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())

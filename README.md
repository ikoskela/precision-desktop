# precision-desktop

mcp-name: io.github.ikoskela/precision-desktop

**A companion MCP server that fixes DPI coordinate scaling for Windows desktop automation.**

Windows DPI scaling silently breaks every MCP tool that clicks, types, or hovers on the desktop. `precision-desktop` detects and corrects the coordinate mismatch so your AI agent's clicks actually land where they should.

## The Problem

Windows has **two coordinate systems** and doesn't tell you which one you're using.

When Windows DPI scaling is set above 100% (which it is on most modern laptops and monitors), different Windows APIs return coordinates in different systems:

| Coordinate System | Used By | Example: Point at 50% across a 4K display |
|---|---|---|
| **Physical** (pixels) | Mouse events, `SetCursorPos`, UI Automation* | `1920, 1080` |
| **Logical** (DPI-scaled) | `GetWindowRect`, `Cursor.Position`, `.NET`, **screenshots** | `1097, 617` (at 175% scaling) |

\* *UI Automation returns physical on DPI-aware processes, logical on others — yet another inconsistency.*

**The ratio between them is your DPI scale factor** (e.g., 1.25x, 1.5x, 1.75x, 2.0x).

The problem isn't just "some APIs return logical." It's that **different APIs return different coordinate systems with no indication of which one you're getting.** There's no flag, no header, no type annotation — just numbers that look identical but mean completely different things.

### Three ways this breaks AI agents

**1. API mismatch** — Click tools accept physical coordinates, but common Windows APIs return logical:

```
What the AI wants to click: [Button at physical (1920, 1080)]
What GetWindowRect says:    [Button at logical  (1097, 617)]
Where the click lands:                          (1097, 617) in physical space
                                                 ^^^^^^^^^ WRONG - completely different spot
```

**2. Screenshot mismatch** — Screen captures are taken at logical resolution, but click tools expect physical coordinates. On a 3840x2400 display at 175% scaling, screenshots are 2194x1371 pixels. When a vision model (GPT-4o, Claude, CogAgent) looks at a screenshot and estimates "the button is at pixel (500, 300)," that's a logical coordinate. Clicking there in physical space misses by hundreds of pixels:

```
Vision model sees:    [Button at (500, 300) in screenshot]
Screenshot space:     Logical (2194x1371)
Click-Tool expects:   Physical (3840x2400)
Correct click:        (875, 525)  ← needs 1.75x conversion
```

**3. Mixed sources within the same tool** — Even a single tool can return both systems. For example, windows-mcp's State-Tool reports element coordinates in physical space (correct for clicking), but its screenshots are captured at logical resolution. An agent combining both — reading element positions from the accessibility tree *and* estimating positions from screenshots — will silently mix coordinate systems.

### This isn't an edge case

- **~1 billion** active Windows devices worldwide
- **~30-50%** have DPI scaling above 100% — that's **300-500 million machines**
- Windows **auto-enables** scaling >100% on most modern laptops (13-16" screens at 1080p+ get 125-150% by default)
- **47%** of PC users now run resolutions above 1080p ([Steam Hardware Survey](https://store.steampowered.com/hwsurvey)) — 21% at 1440p, 5% at 2560x1600, 4.2% at 4K — and climbing
- The MCP ecosystem has **5,800+ servers** and **97M+ monthly SDK downloads** — every Windows desktop automation server will hit this

If you've ever watched an AI agent click confidently at exactly the wrong spot, DPI scaling is probably why.

## The Solution

`precision-desktop` is a companion MCP server that sits alongside your desktop automation MCP (like `windows-mcp`) and provides:

1. **Calibration** — Measure the actual DPI scale factor on this specific machine using known screen landmarks
2. **Coordinate conversion** — Convert between physical and logical systems on demand
3. **UI element finding** — Locate elements by name via Windows UI Automation, returning physical coordinates ready for clicking
4. **Health checks** — Detect stale calibration, verify UI Automation availability, check companion MCP status
5. **Patch awareness** — Track which DPI-aware patches have been applied to the companion MCP

## Tools

| Tool | Description |
|---|---|
| `calibrate` | Compute DPI scale factors from 2+ reference points with known physical and logical coordinates |
| `calibrate_verify` | Mark calibration as verified after confirming a test click landed correctly |
| `get_calibration` | Read current calibration state (scale factors, verification status, age) |
| `convert_coordinates` | Convert a coordinate pair between physical and logical systems |
| `find_ui_element` | Find a single UI element by name using Windows UI Automation. Returns physical coordinates |
| `find_all_ui_elements` | Find all UI elements matching a name. Returns list with physical coordinates |
| `list_ui_elements` | List all named interactive elements (buttons, text fields, etc.) in a window |
| `find_window` | Find a window handle (hwnd) by title substring |
| `health_check` | Run environment checks: calibration freshness, UI Automation, companion MCP status |
| `patch_status` | Check which DPI-aware patches are applied to the companion MCP |

## Quick Start

### 1. Install

Clone this repo and install dependencies:

```bash
git clone https://github.com/ikoskela/precision-desktop.git
cd precision-desktop
pip install -e .
```

### 2. Configure MCP

Add to your Claude Code MCP configuration (`.mcp.json` or settings):

```json
{
  "mcpServers": {
    "precision-desktop": {
      "command": "python",
      "args": ["C:/path/to/precision-desktop/server.py"]
    }
  }
}
```

Or if using Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "precision-desktop": {
      "command": "python",
      "args": ["C:\\path\\to\\precision-desktop\\server.py"]
    }
  }
}
```

### 3. Calibrate

The AI agent calibrates itself on first use. The flow:

1. **Agent calls `health_check`** — discovers calibration is missing
2. **Agent gathers reference points** — uses a coordinate reading tool (like [MPos](https://sourceforge.net/projects/mpos/)) or Move-Tool + Cursor.Position to get both physical and logical coordinates at 2+ known screen landmarks
3. **Agent calls `calibrate`** with the reference points — computes scale factors
4. **Agent verifies** — moves cursor to a known element, confirms it landed correctly, calls `calibrate_verify`

Calibration persists in `state/calibration.json` and only needs to be redone if DPI settings change or the display configuration changes.

## Calibration Guide

### What you need

Two coordinate readings for the same point:
- **Physical coordinates** — from Move-Tool, Click-Tool, or State-Tool (these operate in physical space)
- **Logical coordinates** — from `[System.Windows.Forms.Cursor]::Position` in PowerShell, or `GetWindowRect` API calls

### Good calibration landmarks

- **Start button** (bottom-left of taskbar) — easy to locate precisely
- **Date/time** (bottom-right of taskbar) — anchors the opposite corner
- **Minimize button** of any maximized window — well-defined clickable target

### Example calibration call

```json
{
  "points": [
    {
      "physical_x": 38,
      "physical_y": 2365,
      "logical_x": 21,
      "logical_y": 1351,
      "label": "start_button"
    },
    {
      "physical_x": 3691,
      "physical_y": 2332,
      "logical_x": 2109,
      "logical_y": 1332,
      "label": "datetime"
    }
  ]
}
```

This computes a scale factor (here, ~1.75x) and persists it for future coordinate conversions.

### Verification

After calibration, the agent should:
1. Use `convert_coordinates` to convert a known logical position to physical
2. Use Move-Tool to move the cursor there
3. Confirm the cursor is on the expected target
4. Call `calibrate_verify` with `success: true`

## UI Element Finding

Beyond coordinate conversion, `precision-desktop` can locate elements directly by name using Windows UI Automation — no coordinates needed.

```
Agent: find_ui_element(element_name="Save", window_title="Notepad")
→ { "name": "Save", "center_x": 450, "center_y": 32, "control_type": "button", ... }
   (coordinates are physical, ready for Click-Tool)
```

This works for:
- Native Windows application controls (buttons, text fields, menus)
- Chrome extension popups and dialogs
- Overlay windows that State-Tool may not see
- Any UI element exposed via Windows UI Automation

### Scoped search

You can scope searches to a specific window to avoid finding elements in the wrong application:

```
find_ui_element(element_name="Submit", window_title="My App")
find_ui_element(element_name="Close", window_handle=12345)
```

### Discovery

Don't know the element name? Use `list_ui_elements` to see what's available:

```
list_ui_elements(window_title="Settings")
→ [{ "name": "General", "control_type": "tab item", ... },
   { "name": "Apply", "control_type": "button", ... }, ...]
```

## Integration with windows-mcp

`precision-desktop` is designed to work alongside [windows-mcp](https://github.com/anthropics/windows-mcp) (or any MCP that provides desktop click/type/scroll tools).

### The patching concept

Rather than forking windows-mcp, `precision-desktop` describes **patch intents** — what should change in the companion MCP and why. The AI agent reads these intents and applies version-appropriate patches itself.

Current patch intents:
- **`dpi_awareness`** — Add an optional `coordinate_system` parameter to Click-Tool and Move-Tool that auto-converts logical coordinates to physical
- **`find_and_click`** — Add an optional `element_name` parameter to Click-Tool that finds and clicks an element by name (no coordinates needed)

Use `patch_status` to check which patches are applied.

### Environment variable

If windows-mcp is installed in a non-standard location, set the `WINDOWS_MCP_PATH` environment variable:

```
WINDOWS_MCP_PATH=C:\path\to\windows-mcp
```

By default, it looks in the standard Claude Extensions directory (`%APPDATA%\Claude\Claude Extensions\ant.dir.cursortouch.windows-mcp`).

## Architecture

```
precision-desktop/
├── server.py              # MCP server entry point — tool definitions and routing
├── calibration.py         # DPI calibration: compute, persist, convert coordinates
├── find_element.py        # Windows UI Automation: find elements, list elements, find windows
├── health_check.py        # Environment checks: calibration, UI Automation, companion MCP
├── patches/
│   └── windows_mcp.py     # LLM-adaptive patch intents for windows-mcp
├── state/
│   └── calibration.json   # Persisted calibration data (user-specific, gitignored)
└── pyproject.toml
```

### How calibration works

1. User (or AI agent) provides 2+ points with both physical and logical coordinates
2. `calibration.py` computes the median scale factor for X and Y axes independently
3. Checks consistency — if points disagree by more than 2%, flags as inconsistent
4. Computes offset (typically 0 for standard DPI scaling, non-zero for multi-monitor setups)
5. Persists to `state/calibration.json`
6. Subsequent `convert_coordinates` calls use the persisted factors

### How UI Automation finding works

1. `find_element.py` runs PowerShell scripts that load `UIAutomationClient` and `UIAutomationTypes` assemblies
2. Searches the UI Automation tree for elements matching the requested name
3. Returns bounding rectangles in the coordinate system that UI Automation reports (which is physical on DPI-aware processes)
4. Results include center coordinates ready for direct use with Click-Tool/Move-Tool

## Requirements

- **Windows 10/11** (uses Windows UI Automation)
- **Python 3.10+**
- **PowerShell** (ships with Windows)
- **[mcp](https://pypi.org/project/mcp/) >= 1.0.0** (MCP SDK)
- **[MPos](https://sourceforge.net/projects/mpos/)** or similar coordinate reader (for calibration) — any tool that shows the cursor's screen position in both physical and logical coordinates. MPos is lightweight and portable (no install needed)

## License

[MIT](LICENSE)

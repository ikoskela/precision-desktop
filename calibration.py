"""
Calibration module for precision-desktop MCP.

Computes the linear scale factor between two coordinate systems:
  - Physical (what Click-Tool / Move-Tool / State-Tool use)
  - Logical  (what GetWindowRect / Cursor.Position / .NET report)

Relationship: Physical = Logical * scale + offset
Typical Windows DPI scaling: 1.0, 1.25, 1.5, 1.75, 2.0
"""

import json
import statistics
from pathlib import Path
from datetime import datetime, timezone

STATE_FILE = Path(__file__).parent / "state" / "calibration.json"

# Well-known landmark hints for the calibration flow
LANDMARKS = {
    "start_button": {
        "description": "Windows Start button (bottom-left corner of taskbar)",
        "region": "bottom-left",
    },
    "datetime": {
        "description": "Date/time display (bottom-right corner of taskbar)",
        "region": "bottom-right",
    },
    "minimize": {
        "description": "Minimize button of any open window (upper-right area, leftmost of min/max/close)",
        "region": "upper-right",
    },
}


def load_state() -> dict:
    """Load persisted calibration state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "calibrated": False,
        "scale_x": None,
        "scale_y": None,
        "offset_x": 0,
        "offset_y": 0,
        "points": [],
        "calibrated_at": None,
        "verified": False,
    }


def save_state(state: dict) -> None:
    """Persist calibration state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def compute_calibration(points: list[dict]) -> dict:
    """
    Given 2+ calibration points, compute scale and offset.

    Each point: {
        "physical_x": int, "physical_y": int,
        "logical_x": int,  "logical_y": int,
        "label": str (optional)
    }

    Returns updated state dict.
    """
    if len(points) < 2:
        raise ValueError("Need at least 2 calibration points")

    scales_x = []
    scales_y = []

    for p in points:
        if p["logical_x"] != 0:
            scales_x.append(p["physical_x"] / p["logical_x"])
        if p["logical_y"] != 0:
            scales_y.append(p["physical_y"] / p["logical_y"])

    if not scales_x or not scales_y:
        raise ValueError("Cannot compute scale — logical coordinates contain zeros")

    scale_x = statistics.median(scales_x)
    scale_y = statistics.median(scales_y)

    # Check consistency — if points disagree by more than 2%, warn
    spread_x = (max(scales_x) - min(scales_x)) / scale_x if scale_x else 0
    spread_y = (max(scales_y) - min(scales_y)) / scale_y if scale_y else 0
    consistent = spread_x < 0.02 and spread_y < 0.02

    # For standard DPI scaling, offset should be 0.
    # We compute it from the median residual just in case.
    offsets_x = [p["physical_x"] - p["logical_x"] * scale_x for p in points if p["logical_x"] != 0]
    offsets_y = [p["physical_y"] - p["logical_y"] * scale_y for p in points if p["logical_y"] != 0]
    offset_x = round(statistics.median(offsets_x)) if offsets_x else 0
    offset_y = round(statistics.median(offsets_y)) if offsets_y else 0

    state = {
        "calibrated": True,
        "scale_x": round(scale_x, 6),
        "scale_y": round(scale_y, 6),
        "offset_x": offset_x,
        "offset_y": offset_y,
        "points": points,
        "calibrated_at": datetime.now(timezone.utc).isoformat(),
        "verified": False,
        "consistent": consistent,
        "spread_x": round(spread_x, 4),
        "spread_y": round(spread_y, 4),
    }
    save_state(state)
    return state


def mark_verified(success: bool, notes: str = "") -> dict:
    """Mark the current calibration as verified (or failed)."""
    state = load_state()
    state["verified"] = success
    state["verification_notes"] = notes
    state["verified_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return state


def physical_to_logical(phys_x: int, phys_y: int) -> tuple[int, int]:
    """Convert physical coordinates to logical."""
    state = load_state()
    if not state["calibrated"]:
        raise RuntimeError("Not calibrated — run the 'calibrate' tool first")
    lx = round((phys_x - state["offset_x"]) / state["scale_x"])
    ly = round((phys_y - state["offset_y"]) / state["scale_y"])
    return lx, ly


def logical_to_physical(log_x: int, log_y: int) -> tuple[int, int]:
    """Convert logical coordinates to physical."""
    state = load_state()
    if not state["calibrated"]:
        raise RuntimeError("Not calibrated — run the 'calibrate' tool first")
    px = round(log_x * state["scale_x"] + state["offset_x"])
    py = round(log_y * state["scale_y"] + state["offset_y"])
    return px, py

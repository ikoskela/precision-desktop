"""
Health check module for precision-desktop MCP.

Checks:
1. Is calibration current and verified?
2. Is windows-mcp installed and accessible?
3. Are required PowerShell assemblies available?
4. Is windows-mcp patched (future: LLM-adaptive patching)?
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from calibration import load_state as load_calibration

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


def _run_ps(script: str, timeout: int = 10) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def check_calibration() -> dict:
    """Check calibration freshness and validity."""
    state = load_calibration()

    if not state.get("calibrated"):
        return {
            "status": "missing",
            "message": "No calibration data. Run 'calibrate' tool.",
            "action_needed": True,
        }

    cal_time = state.get("calibrated_at")
    if cal_time:
        cal_dt = datetime.fromisoformat(cal_time)
        age = datetime.now(timezone.utc) - cal_dt
        stale = age > timedelta(days=7)
    else:
        stale = True

    verified = state.get("verified", False)
    consistent = state.get("consistent", True)

    if stale:
        return {
            "status": "stale",
            "message": f"Calibration is {age.days} days old. Consider re-calibrating.",
            "scale_x": state.get("scale_x"),
            "scale_y": state.get("scale_y"),
            "action_needed": True,
        }

    if not verified:
        return {
            "status": "unverified",
            "message": "Calibration computed but not verified. Run verification step.",
            "scale_x": state.get("scale_x"),
            "scale_y": state.get("scale_y"),
            "action_needed": True,
        }

    if not consistent:
        return {
            "status": "inconsistent",
            "message": f"Calibration points disagree (spread: x={state.get('spread_x')}, y={state.get('spread_y')}). Re-calibrate with better points.",
            "scale_x": state.get("scale_x"),
            "scale_y": state.get("scale_y"),
            "action_needed": True,
        }

    return {
        "status": "ok",
        "message": f"Calibration valid. Scale: {state['scale_x']}x / {state['scale_y']}y",
        "scale_x": state["scale_x"],
        "scale_y": state["scale_y"],
        "action_needed": False,
    }


def check_ui_automation() -> dict:
    """Check that PowerShell UI Automation assemblies are loadable."""
    try:
        output = _run_ps(
            'Add-Type -AssemblyName UIAutomationClient; '
            'Add-Type -AssemblyName UIAutomationTypes; '
            'Write-Output "OK"'
        )
        if "OK" in output:
            return {"status": "ok", "message": "UI Automation assemblies available"}
        return {"status": "error", "message": f"Unexpected output: {output}"}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "PowerShell timed out loading UI Automation"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def check_windows_mcp() -> dict:
    """Check windows-mcp installation status."""
    if not WINDOWS_MCP_PATH.exists():
        return {
            "status": "missing",
            "message": "windows-mcp not found at expected path",
            "path": str(WINDOWS_MCP_PATH),
        }

    main_py = WINDOWS_MCP_PATH / "main.py"
    manifest = WINDOWS_MCP_PATH / "manifest.json"

    if not main_py.exists():
        return {
            "status": "error",
            "message": "windows-mcp directory exists but main.py missing",
            "path": str(WINDOWS_MCP_PATH),
        }

    version = "unknown"
    if manifest.exists():
        try:
            mf = json.loads(manifest.read_text(encoding="utf-8"))
            version = mf.get("version", "unknown")
        except Exception:
            pass

    return {
        "status": "ok",
        "message": f"windows-mcp v{version} found",
        "path": str(WINDOWS_MCP_PATH),
        "version": version,
        "main_py_size": main_py.stat().st_size,
    }


def run_all_checks() -> dict:
    """Run all health checks and return combined report."""
    checks = {
        "calibration": check_calibration(),
        "ui_automation": check_ui_automation(),
        "windows_mcp": check_windows_mcp(),
    }

    any_action = any(c.get("action_needed") for c in checks.values())
    any_error = any(c.get("status") == "error" for c in checks.values())

    checks["overall"] = {
        "status": "error" if any_error else ("action_needed" if any_action else "ok"),
        "message": "All checks passed" if not any_error and not any_action
        else "Some checks need attention",
    }

    return checks

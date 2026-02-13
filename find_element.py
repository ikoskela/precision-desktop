"""
UI Automation element finder for precision-desktop MCP.

Uses PowerShell + System.Windows.Automation to locate UI elements
by name, automation ID, or class name within a window.

Returns physical coordinates (ready for Click-Tool / Move-Tool).
"""

import subprocess
import re
import json


def _run_ps(script: str, timeout: int = 10) -> str:
    """Run a PowerShell script and return stdout."""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0 and result.stderr.strip():
        raise RuntimeError(f"PowerShell error: {result.stderr.strip()}")
    return result.stdout.strip()


def find_window_handle(title_substring: str) -> int | None:
    """Find a window handle by title substring."""
    script = f'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty,
    "{title_substring}",
    [System.Windows.Automation.PropertyConditionFlags]::IgnoreCase)
$windows = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Children, $condition)
if ($windows.Count -gt 0) {{
    $hwnd = $windows[0].Current.NativeWindowHandle
    Write-Output $hwnd
}} else {{
    # Fallback: partial match via substring
    $all = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Children,
        [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($w in $all) {{
        if ($w.Current.Name -like "*{title_substring}*") {{
            Write-Output $w.Current.NativeWindowHandle
            break
        }}
    }}
}}
'''
    output = _run_ps(script)
    if output and output.strip().isdigit():
        return int(output.strip())
    return None


def find_element_by_name(
    element_name: str,
    window_title: str | None = None,
    window_handle: int | None = None,
) -> dict | None:
    """
    Find a UI element by its Name property.

    Args:
        element_name: The Name property to search for (exact match).
        window_title: Window title substring to scope the search.
        window_handle: Specific window handle (takes priority over title).

    Returns:
        Dict with keys: name, x, y, width, height, center_x, center_y,
        control_type, automation_id. Coordinates are PHYSICAL.
        Returns None if not found.
    """
    if window_handle:
        root_expr = f"[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{window_handle})"
    elif window_title:
        # Find window first, then search within it
        root_expr = f'''$(
            $root = [System.Windows.Automation.AutomationElement]::RootElement
            $wCond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                "{window_title}",
                [System.Windows.Automation.PropertyConditionFlags]::IgnoreCase)
            $wins = $root.FindAll(
                [System.Windows.Automation.TreeScope]::Children, $wCond)
            if ($wins.Count -eq 0) {{
                # Partial match fallback
                $all = $root.FindAll(
                    [System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition)
                $found = $null
                foreach ($w in $all) {{
                    if ($w.Current.Name -like "*{window_title}*") {{
                        $found = $w; break
                    }}
                }}
                $found
            }} else {{
                $wins[0]
            }}
        )'''
    else:
        root_expr = "[System.Windows.Automation.AutomationElement]::RootElement"

    # Escape double quotes in element name for PowerShell
    safe_name = element_name.replace('"', '`"')

    script = f'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$searchRoot = {root_expr}
if ($null -eq $searchRoot) {{
    Write-Output "WINDOW_NOT_FOUND"
    exit
}}
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "{safe_name}")
$element = $searchRoot.FindFirst(
    [System.Windows.Automation.TreeScope]::Descendants, $condition)
if ($null -ne $element) {{
    $rect = $element.Current.BoundingRectangle
    $cx = [int]($rect.Left + $rect.Width / 2)
    $cy = [int]($rect.Top + $rect.Height / 2)
    $result = @{{
        name = $element.Current.Name
        x = [int]$rect.Left
        y = [int]$rect.Top
        width = [int]$rect.Width
        height = [int]$rect.Height
        center_x = $cx
        center_y = $cy
        control_type = $element.Current.LocalizedControlType
        automation_id = $element.Current.AutomationId
    }}
    $result | ConvertTo-Json -Compress
}} else {{
    Write-Output "NOT_FOUND"
}}
'''
    output = _run_ps(script, timeout=15)

    if not output or output == "NOT_FOUND":
        return None
    if output == "WINDOW_NOT_FOUND":
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def find_elements_by_name(
    element_name: str,
    window_title: str | None = None,
    window_handle: int | None = None,
) -> list[dict]:
    """
    Find ALL UI elements matching a Name property.
    Same args as find_element_by_name but returns a list.
    """
    if window_handle:
        root_expr = f"[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{window_handle})"
    elif window_title:
        root_expr = f'''$(
            $root = [System.Windows.Automation.AutomationElement]::RootElement
            $wCond = New-Object System.Windows.Automation.PropertyCondition(
                [System.Windows.Automation.AutomationElement]::NameProperty,
                "{window_title}",
                [System.Windows.Automation.PropertyConditionFlags]::IgnoreCase)
            $wins = $root.FindAll(
                [System.Windows.Automation.TreeScope]::Children, $wCond)
            if ($wins.Count -eq 0) {{
                $all = $root.FindAll(
                    [System.Windows.Automation.TreeScope]::Children,
                    [System.Windows.Automation.Condition]::TrueCondition)
                $found = $null
                foreach ($w in $all) {{
                    if ($w.Current.Name -like "*{window_title}*") {{
                        $found = $w; break
                    }}
                }}
                $found
            }} else {{
                $wins[0]
            }}
        )'''
    else:
        root_expr = "[System.Windows.Automation.AutomationElement]::RootElement"

    safe_name = element_name.replace('"', '`"')

    script = f'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$searchRoot = {root_expr}
if ($null -eq $searchRoot) {{
    Write-Output "[]"
    exit
}}
$condition = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, "{safe_name}")
$elements = $searchRoot.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants, $condition)
$results = @()
foreach ($element in $elements) {{
    $rect = $element.Current.BoundingRectangle
    $cx = [int]($rect.Left + $rect.Width / 2)
    $cy = [int]($rect.Top + $rect.Height / 2)
    $results += @{{
        name = $element.Current.Name
        x = [int]$rect.Left
        y = [int]$rect.Top
        width = [int]$rect.Width
        height = [int]$rect.Height
        center_x = $cx
        center_y = $cy
        control_type = $element.Current.LocalizedControlType
        automation_id = $element.Current.AutomationId
    }}
}}
$results | ConvertTo-Json -Compress
'''
    output = _run_ps(script, timeout=15)

    if not output or output == "[]":
        return []

    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    except json.JSONDecodeError:
        return []


def list_window_elements(
    window_title: str | None = None,
    window_handle: int | None = None,
    max_depth: int = 3,
) -> list[dict]:
    """
    List all named interactive elements in a window (buttons, text fields, etc.).
    Useful for discovering what's available before targeting a specific element.
    """
    if window_handle:
        root_expr = f"[System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]{window_handle})"
    elif window_title:
        root_expr = f'''$(
            $root = [System.Windows.Automation.AutomationElement]::RootElement
            $all = $root.FindAll(
                [System.Windows.Automation.TreeScope]::Children,
                [System.Windows.Automation.Condition]::TrueCondition)
            $found = $null
            foreach ($w in $all) {{
                if ($w.Current.Name -like "*{window_title}*") {{
                    $found = $w; break
                }}
            }}
            $found
        )'''
    else:
        root_expr = "[System.Windows.Automation.AutomationElement]::RootElement"

    script = f'''
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$searchRoot = {root_expr}
if ($null -eq $searchRoot) {{
    Write-Output "[]"
    exit
}}
$elements = $searchRoot.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
$results = @()
$interactive = @("button", "edit", "text", "hyperlink", "menu item", "tab item",
                 "list item", "check box", "radio button", "combo box", "slider")
$count = 0
foreach ($element in $elements) {{
    $ct = $element.Current.LocalizedControlType
    $name = $element.Current.Name
    if ($name -and ($interactive -contains $ct)) {{
        $rect = $element.Current.BoundingRectangle
        if ($rect.Width -gt 0 -and $rect.Height -gt 0) {{
            $results += @{{
                name = $name
                control_type = $ct
                center_x = [int]($rect.Left + $rect.Width / 2)
                center_y = [int]($rect.Top + $rect.Height / 2)
                automation_id = $element.Current.AutomationId
            }}
            $count++
            if ($count -ge 100) {{ break }}
        }}
    }}
}}
$results | ConvertTo-Json -Compress
'''
    output = _run_ps(script, timeout=20)

    if not output or output == "[]":
        return []

    try:
        parsed = json.loads(output)
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    except json.JSONDecodeError:
        return []

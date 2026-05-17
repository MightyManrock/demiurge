"""
UI-layer constants: sentinels, option lists, well-known directories,
and grid layouts referenced by Textual widgets and screens.
"""
from __future__ import annotations
from pathlib import Path

# Sentinel returned by modal/picker dismissals when the user pressed Back.
# A nested action flow can detect this and re-show the previous step.
BACK = "__back__"

# (key, label, latitude_value) tuples for the Proxius directive latitude picker.
_LATITUDE_OPTS = [
    ("strict", "Strict", 0.0),
    ("guided", "Guided", 0.5),
    ("lax",    "Lax",    1.0),
]

# Action keys whose handlers are not yet implemented; the action browser greys
# them out so the player knows the option is reserved for future content.
_STUB_ACTIONS: frozenset[str] = frozenset({
    "read_divine_traces",
    "negotiate_herald",
    "obstruct_herald",
    "petition_luminary_herald",
    "investigate_underreal",
})

# Canonical 4×4 grid order for the domain picker (row-major).
_DOMAIN_GRID_ORDER: list[str] = [
    "domain:truth",    "domain:light",    "domain:void",      "domain:change",
    "domain:order",    "domain:fire",     "domain:decay",     "domain:conflict",
    "domain:memory",   "domain:growth",   "domain:community", "domain:silence",
    "domain:mastery",  "domain:water",    "domain:sacrifice", "domain:secrecy",
]

# Project-root directories used by save/load/log flows.
# Anchored to the parent of the `ui/` package so they resolve correctly
# regardless of the CWD the app is launched from.
_PROJECT_ROOT  = Path(__file__).resolve().parent.parent
_SAVES_DIR     = _PROJECT_ROOT / "saves"
_SCENARIOS_DIR = _PROJECT_ROOT / "scenarios"
_LOGS_DIR      = _PROJECT_ROOT / "logs"

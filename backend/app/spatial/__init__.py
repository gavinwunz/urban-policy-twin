"""Spatial traffic-assignment layer (SPEC §7.7).

Models geography explicitly: a peak-hour static traffic assignment (MSA
user-equilibrium with a BPR volume-delay function) over the Auckland road
grid, driven by the same deterministic agent-based mode-choice demand as
``/simulate``. Produces congested link flows, cordon inflow, network vehicle-
hours, gravity job accessibility and a per-zone road-CO₂ dispersion proxy —
each as World A vs World B. Deterministic, no LLM (SPEC §34).
"""

from .assignment import AssignmentResult, assign
from .model import build_spatial_report
from .network import Arc, Network
from .params import DEFAULT_SPATIAL_PARAMS, SpatialParams
from .schema import (
    AccessibilityReport,
    ArcLoad,
    NetworkState,
    PollutionReport,
    SpatialReport,
    ZoneChange,
)

__all__ = [
    "assign",
    "AssignmentResult",
    "build_spatial_report",
    "Network",
    "Arc",
    "SpatialParams",
    "DEFAULT_SPATIAL_PARAMS",
    "SpatialReport",
    "NetworkState",
    "ArcLoad",
    "ZoneChange",
    "AccessibilityReport",
    "PollutionReport",
]

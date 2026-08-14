"""Pydantic schemas for the SDG alignment layer (SPEC §23).

Every SDG result exposes the exact fields SPEC §23 mandates —
``indicator / proxy``, ``baseline``, ``scenario``, ``change``, ``data source``,
``confidence`` — plus the provenance ``tag`` the rest of the app uses. There is
no composite score: SPEC §23 forbids arbitrary "SDG scores", so the report only
maps outcomes to indicators and counts improvements.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import Checkpoint, MetricTag


class SdgIndicator(BaseModel):
    """One measurable indicator / transparent proxy mapped to an SDG target."""

    id: str = Field(description="Stable key, e.g. 'sdg11.sustainable_mode_share'.")
    sdg_target: str = Field(description="SDG target reference, e.g. '11.2'.")
    indicator: str = Field(description="Human-readable indicator / proxy name.")
    proxy_for: str = Field(
        description="What real-world concept this measurable number stands in for."
    )
    unit: str
    baseline: float = Field(description="World-A value at the horizon (no intervention).")
    scenario: float = Field(description="World-B value at the horizon (with policy).")
    change: float = Field(description="scenario − baseline.")
    change_pct: float | None = Field(
        default=None, description="Change as % of baseline (None when baseline ≈ 0)."
    )
    better_when: str = Field(description="'higher' or 'lower' — direction of improvement.")
    improved: bool = Field(description="True when the change moves toward the SDG target.")
    data_source: str = Field(description="Which model / dataset produced these numbers.")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in the change (falls with horizon)."
    )
    confidence_label: str = Field(description="'high' | 'medium' | 'low'.")
    tag: MetricTag = Field(description="Observed/Estimated/Simulated/Generated.")
    note: str = Field(default="", description="Caveats / interpretation for this indicator.")


class SdgGoal(BaseModel):
    """One SDG grouping the indicators mapped to it."""

    goal: int = Field(description="SDG number, e.g. 11.")
    title: str
    tier: str = Field(description="'core' or 'secondary' GOV SIM alignment (SPEC §23).")
    indicators: list[SdgIndicator] = Field(default_factory=list)
    improved_count: int = 0
    worsened_count: int = 0
    unchanged_count: int = 0
    summary: str = Field(default="", description="One-line verdict for the goal.")


class SdgReport(BaseModel):
    """Full SDG alignment mapping for a policy run (SPEC §23)."""

    provenance: MetricTag = Field(MetricTag.simulated)
    note: str = Field(
        default=(
            "SDG alignment maps deterministic simulation + cohort-opinion outcomes "
            "onto UN SDG targets via measurable indicators / transparent proxies. "
            "No composite 'SDG score' is produced (SPEC §23); each indicator carries "
            "its own baseline/scenario/change/source/confidence. No LLM touches any "
            "number (SPEC §34)."
        )
    )
    policy_id: str
    horizon: Checkpoint = Field(description="Horizon the indicators are quoted at.")
    goals: list[SdgGoal] = Field(default_factory=list)
    total_improved: int = 0
    total_worsened: int = 0
    total_unchanged: int = 0
    headline: str = Field(
        default="", description="Count-based summary — never an arbitrary SDG score."
    )

"""Pydantic schemas for the model registry (SPEC §33).

The registry is the machine-readable answer to "what models produced this
forecast, on what assumptions, and how do we stop an LLM inventing numbers?".
Every card is a transparency artifact, not a simulation output, so nothing here
carries a Simulated tag — it describes *how* Simulated numbers are made.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import MetricTag


class AssumptionRecord(BaseModel):
    """One documented, auditable input assumption feeding a model."""

    name: str = Field(description="Stable key, e.g. 'car_co2_kg_per_km'.")
    label: str = Field(description="Human-readable description.")
    value: object = Field(description="The live value read from the code (any JSON type).")
    unit: str = Field(default="", description="Unit of the value, if any.")
    source: str = Field(description="Where this assumption comes from / its rationale.")
    tag: MetricTag = Field(
        description="Provenance of the assumption itself (usually Estimated/Observed)."
    )


class ModelCard(BaseModel):
    """A self-describing entry for one model / forecast layer (SPEC §7/§33)."""

    id: str = Field(description="Stable key, e.g. 'agent_based_mode_choice'.")
    name: str
    spec_sections: list[str] = Field(
        default_factory=list, description="SPEC sections this model implements."
    )
    layer: str = Field(
        description="Which hybrid-forecast family (SPEC §7) or analysis stage this is."
    )
    method: str = Field(description="One-paragraph description of how it computes.")
    determinism: str = Field(
        description="'deterministic' | 'stochastic (seeded)' — reproducibility class."
    )
    produces_numbers: bool = Field(
        description="Whether this model emits core numeric effects."
    )
    llm_touches_numbers: bool = Field(
        default=False,
        description="MUST be False for any numeric model (SPEC §34 guardrail).",
    )
    llm_role: str = Field(
        default="none",
        description="What (if anything) an LLM does here — prose only, never numbers.",
    )
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    output_tag: MetricTag = Field(
        description="Provenance tag applied to this model's numeric outputs."
    )
    code: str = Field(description="Python module path implementing the model.")
    assumptions: list[AssumptionRecord] = Field(default_factory=list)


class DataSourceCard(BaseModel):
    """One data source the models read (SPEC §4/§33)."""

    id: str
    name: str
    kind: str = Field(description="'synthetic' | 'legacy' | 'live' | 'assumption-set'.")
    description: str
    tag: MetricTag
    used_by: list[str] = Field(
        default_factory=list, description="Model ids that consume this source."
    )


class GuardrailCheck(BaseModel):
    """One SPEC §34 anti-'AI-astrology' guardrail and how GOV SIM enforces it."""

    id: str
    rule: str = Field(description="The guardrail as stated in SPEC §34.")
    enforced_by: str = Field(description="Concretely how the codebase enforces it.")
    holds: bool = Field(description="Whether the current build satisfies the rule.")


class ModelRegistry(BaseModel):
    """The full transparency manifest for the forecast engine (SPEC §33)."""

    provenance: MetricTag = Field(
        MetricTag.observed,
        description="The registry describes the code, so it is Observed about itself.",
    )
    note: str = Field(
        default=(
            "Model registry: a self-describing catalogue of every forecast layer, "
            "its documented assumptions (read live from the code so values cannot "
            "drift), the data sources it reads, and the SPEC §34 guardrails that "
            "keep LLMs out of the numeric path. Transparency artifact, not a "
            "simulation output."
        )
    )
    app_version: str
    generated_from: str = Field(
        default="live parameter introspection",
        description="How the assumption values were obtained (not hand-copied).",
    )
    models: list[ModelCard] = Field(default_factory=list)
    data_sources: list[DataSourceCard] = Field(default_factory=list)
    guardrails: list[GuardrailCheck] = Field(default_factory=list)
    assumption_index: list[AssumptionRecord] = Field(
        default_factory=list,
        description="Flat, de-duplicated list of every documented numeric assumption.",
    )
    counts: dict = Field(
        default_factory=dict,
        description="Summary counts (models, deterministic, numeric, assumptions).",
    )

"""Pydantic schemas for the Data Fabric layer (SPEC §4).

Every dataset the engine reads is described with the full SPEC §4 metadata
record. The fabric is a transparency artifact *about the data* (Observed), so
its provenance tag describes the catalogue, not a forecast.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import MetricTag


class VariableCard(BaseModel):
    """One measured/derived variable inside a dataset (SPEC §4 ``variables``)."""

    name: str = Field(description="Field key as it appears in the file.")
    dtype: str = Field(description="Inferred storage type: number / integer / string / boolean.")
    unit: str = Field(default="", description="Physical/economic unit, if any.")
    description: str = Field(default="", description="What the variable means.")
    missing_pct: float = Field(
        description="Share of records where this field is absent/null (0–100)."
    )


class TransformationStep(BaseModel):
    """One entry in a dataset's ``transformation_history`` (SPEC §4)."""

    step: str = Field(description="What was done, e.g. 'destination-constrained gravity fit'.")
    by: str = Field(description="Code/module that performed it.")
    tag: MetricTag = Field(description="Provenance of the step's output.")


class DatasetCard(BaseModel):
    """The full SPEC §4 dataset provenance record, built live from the file."""

    id: str
    title: str
    publisher: str
    source_url: str = Field(description="Where the bytes (or the generator) live.")
    retrieved_at: str | None = Field(
        default=None,
        description="ISO time of retrieval; null for deterministically generated data.",
    )
    geographic_scope: str
    spatial_resolution: str = ""
    time_start: str | None = None
    time_end: str | None = None
    frequency: str = Field(default="", description="Cadence of observations, if a time series.")
    units: str = ""
    variables: list[VariableCard] = Field(default_factory=list)
    license: str = ""
    missingness: float = Field(
        description="Overall share of missing cells across declared variables (0–100)."
    )
    revision: str = Field(
        description="Content-addressed version: short sha256 of the actual file bytes."
    )
    confidence: str = Field(description="How much weight the record can bear + why.")
    transformation_history: list[TransformationStep] = Field(default_factory=list)
    # Operational extras beyond the raw §4 schema, still auditable:
    format: str = Field(description="On-disk serialisation, e.g. 'GeoJSON'.")
    record_count: int = Field(description="Number of features/records/rows.")
    kind: str = Field(description="'synthetic' | 'legacy' | 'live' | 'assumption-set'.")
    tag: MetricTag = Field(description="Provenance tag for the dataset's values.")
    real_world_analogues: list[str] = Field(
        default_factory=list,
        description="Real datasets this synthetic file is schema-compatible with (not sources).",
    )


class FormatSupport(BaseModel):
    """One of SPEC §4's supported ingestion formats + its wiring status."""

    format: str
    status: str = Field(
        description="'native' (read in the demo) | 'adapter-ready' (schema fits, no live feed) "
        "| 'declared' (part of the §4 contract, not exercised here)."
    )
    note: str = ""


class HarmonisationStep(BaseModel):
    """One SPEC §4 harmonisation pipeline stage + whether it actually runs."""

    step: str
    implemented: bool = Field(description="Whether this build performs the step on real data.")
    where: str = Field(description="Code path / mechanism, or why it is N/A.")
    note: str = ""


class DataFabric(BaseModel):
    """Top-level Data Fabric manifest (SPEC §4)."""

    provenance: MetricTag = Field(
        MetricTag.observed,
        description="The fabric describes the data on disk, so it is Observed about itself.",
    )
    note: str = Field(
        default=(
            "Data Fabric: the dataset ingestion & provenance layer (SPEC §4). Every "
            "dataset carries the full §4 metadata record, built live from the file "
            "bytes so it cannot drift from what the engine actually reads. Auckland is "
            "a synthetic city — no real administrative record is ingested — so "
            "datasets are tagged Simulated/Synthetic and real-world sources are listed "
            "as the schemas the data is shaped like, never claimed as live feeds."
        )
    )
    app_version: str
    generated_from: str = Field(
        default="live file introspection (counts, missingness and content hashes read on disk)",
    )
    lineage_contract: str = Field(
        default="input data → transformation → model → assumptions → result",
        description="SPEC §4: no model output exists without a traceable path back to source.",
    )
    datasets: list[DatasetCard] = Field(default_factory=list)
    format_support: list[FormatSupport] = Field(default_factory=list)
    harmonisation: list[HarmonisationStep] = Field(default_factory=list)
    counts: dict = Field(default_factory=dict)

"""Model registry / transparency manifest (SPEC §33).

A self-describing catalogue of every model layer GOV SIM uses to turn a policy into
numbers, the documented assumptions that parameterise each one, the data sources
they read, and the SPEC §34 anti-"AI-astrology" guardrails and how each is
enforced. It is assembled by *introspecting the live parameter objects* (so the
published values cannot drift from the code that runs), is fully deterministic,
and no LLM touches any of it (SPEC §34).
"""

from .model import build_registry
from .schema import (
    AssumptionRecord,
    DataSourceCard,
    GuardrailCheck,
    ModelCard,
    ModelRegistry,
)

__all__ = [
    "build_registry",
    "ModelRegistry",
    "ModelCard",
    "AssumptionRecord",
    "DataSourceCard",
    "GuardrailCheck",
]

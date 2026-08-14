"""Build the per-run reproducibility manifest (SPEC §32).

The ``run_id`` is a SHA-256 **content address** over the exact inputs that
determine a run — policy DSL, shocks, seed, dataset fingerprints, code version
and the live parameter set — with the wall-clock timestamp deliberately
excluded. Identical inputs therefore always produce the same ``run_id``: that is
what makes "REPRODUCE RUN" meaningful rather than decorative.

To prove (not merely assert) reproducibility, the deterministic simulation core
is executed twice and its canonical output digest compared; ``reproducible`` is
only True when the two digests match. Everything is deterministic and LLM-free
(SPEC §32/§34).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..baseline.model import compute_baseline
from ..baseline.schema import MetricTag
from ..baseline.timeseries import build_timeseries
from ..config import settings
from ..policy.dsl import PolicyDSL
from ..registry.model import build_registry
from ..simulation.compare import build_delta
from ..simulation.model import compute_world_b
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .schema import DatasetVersion, ModelVersion, ReproManifest

# repo_root/backend/app/reproduce/manifest.py -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_DIR = _REPO_ROOT / "data" / "city"

# Datasets that pin the world state a run reads (SPEC §4/§32).
_DATASET_FILES = [
    ("city_grid", "Auckland policy analysis grid", "manifest.json", "generate_city.py"),
    ("population", "Auckland synthetic population", "population.json", "generate_population.py"),
]


def _canonical(obj: object) -> str:
    """Stable JSON: sorted keys, no incidental whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _code_version() -> str:
    """Git commit of the running code, or a documented fallback (SPEC §32).

    Never raises: reproducibility metadata must not break the app when git is
    unavailable (e.g. a source tarball deploy).
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        sha = out.stdout.strip()
        if out.returncode == 0 and sha:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(_REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            suffix = "+dirty" if dirty.stdout.strip() else ""
            return f"git:{sha}{suffix}"
    except (OSError, subprocess.SubprocessError):
        pass
    return f"v{settings.version} (git commit unavailable)"


@lru_cache(maxsize=1)
def _dataset_versions() -> tuple[DatasetVersion, ...]:
    """Pin each input dataset by content hash (cached; files are static at runtime)."""
    out: list[DatasetVersion] = []
    for ds_id, name, filename, generator in _DATASET_FILES:
        path = _DATA_DIR / filename
        if not path.exists():
            # Record the gap honestly rather than silently dropping the dataset.
            out.append(
                DatasetVersion(
                    id=ds_id,
                    name=name,
                    generated_by=f"data/{generator}",
                    path=f"data/city/{filename}",
                    content_sha256="MISSING",
                    summary={"error": "dataset file not found"},
                )
            )
            continue
        raw = path.read_bytes()
        content_hash = hashlib.sha256(raw).hexdigest()
        seed: object = None
        summary: dict = {}
        try:
            doc = json.loads(raw)
            if isinstance(doc, dict):
                seed = doc.get("seed")
                for key in ("counts", "totals", "summary", "target_agents"):
                    if key in doc:
                        summary[key] = doc[key]
        except json.JSONDecodeError:  # pragma: no cover - defensive
            pass
        out.append(
            DatasetVersion(
                id=ds_id,
                name=name,
                generated_by=f"data/{generator}",
                seed=seed,
                path=f"data/city/{filename}",
                content_sha256=content_hash,
                summary=summary,
            )
        )
    return tuple(out)


def _model_versions() -> list[ModelVersion]:
    """Map the live §33 registry cards onto pinned model-version records."""
    reg = build_registry()
    return [
        ModelVersion(
            id=m.id,
            name=m.name,
            spec_sections=m.spec_sections,
            code=m.code,
            determinism=m.determinism,
            output_tag=m.output_tag,
            llm_touches_numbers=m.llm_touches_numbers,
        )
        for m in reg.models
    ]


def _sim_output_digest(policy: PolicyDSL, shocks: Shocks | None) -> str:
    """Run the deterministic A/B/Δ core and hash its canonical outputs.

    This is exactly the pipeline behind ``POST /simulate`` (World A baseline,
    World B staged-adaptation timeline, Δ = B − A). Floats are rounded before
    hashing so the digest is a clean content address of the result.
    """
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)
    b_full = compute_world_b(policy, params=params, reinvestment=True)
    b_behav = compute_world_b(policy, params=params, reinvestment=False)
    b_ts = build_world_b_timeline(
        policy,
        baseline=base,
        world_b_full=b_full,
        world_b_behaviour=b_behav,
        params=params,
        trend=trend,
    )
    delta = build_delta(base_ts, b_ts)

    payload = {
        "world_a": base.model_dump(mode="json"),
        "world_b": b_full.model_dump(mode="json"),
        "delta": delta.model_dump(mode="json"),
    }
    return _sha256(_canonical(_round_floats(payload)))


def _round_floats(obj: object, ndigits: int = 6) -> object:
    """Recursively round floats so the digest is stable and clean."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def build_manifest(
    policy: PolicyDSL,
    shocks: Shocks | None = None,
    seed: int | None = None,
) -> ReproManifest:
    """Assemble the reproducibility record for a run (SPEC §32).

    Deterministic apart from the ``created_at`` timestamp, which is metadata and
    is excluded from the ``run_id`` content hash.
    """
    datasets = list(_dataset_versions())
    models = _model_versions()
    reg = build_registry()  # reuse the live, de-duplicated assumption index
    code_version = _code_version()
    shocks_dump = shocks.model_dump(mode="json") if shocks else {}

    # The exact components that determine the run (timestamp excluded on purpose).
    fingerprint = {
        "policy": policy.model_dump(mode="json"),
        "shocks": shocks_dump,
        "seed": seed,
        "code_version": code_version,
        "app_version": settings.version,
        "datasets": {d.id: d.content_sha256 for d in datasets},
        "assumptions": {a.name: a.value for a in reg.assumption_index},
    }
    run_id = _sha256(_canonical(fingerprint))

    # Prove reproducibility: identical inputs → identical deterministic outputs.
    digest_a = _sim_output_digest(policy, shocks)
    digest_b = _sim_output_digest(policy, shocks)
    reproducible = digest_a == digest_b

    created_at = datetime.now(timezone.utc).isoformat()

    how_to = (
        "POST this manifest's `policy` (and `shocks`, `seed`) back to /reproduce "
        "on the same `code_version` and dataset content hashes to obtain the "
        f"identical run_id ({run_id[:12]}…) and output_digest. Any change to the "
        "policy, shocks, code or datasets changes the run_id."
    )

    return ReproManifest(
        run_id=run_id,
        reproducible=reproducible,
        output_digest=digest_a,
        created_at=created_at,
        app_version=settings.version,
        code_version=code_version,
        seed=seed,
        policy=policy,
        shocks=shocks_dump,
        datasets=datasets,
        models=models,
        assumptions=reg.assumption_index,
        prompts=[],  # SPEC §34: no LLM prompt enters the numeric path.
        inputs_fingerprint=fingerprint,
        how_to_reproduce=how_to,
    )

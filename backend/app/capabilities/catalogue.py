"""Curated catalogue mapping every served route to its SPEC section + metadata.

This is the *only* place a route's human description / SPEC mapping lives. The
builder (``model.py``) reconciles the paths here against the live app routes, so
adding a route without a card (or leaving a card for a deleted route) is caught
by ``undocumented_routes`` / ``phantom_cards`` and the standing test — the
catalogue can never silently fall behind the real surface.

Framework infrastructure (``/docs``, ``/redoc``, ``/openapi.json``,
``/docs/oauth2-redirect``) is intentionally excluded — it is not part of the
engine's product surface.
"""

from __future__ import annotations

from ..baseline.schema import MetricTag

# Routes FastAPI mounts for its own docs UI — not product endpoints.
INFRA_PATHS: frozenset[str] = frozenset(
    {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
)

# Ordered area metadata: (area, spec_sections, one-line summary).
AREA_META: list[tuple[str, list[str], str]] = [
    (
        "System & transparency",
        ["§4", "§32", "§33", "§34"],
        "Service metadata and the machine-readable 'how do we know these numbers "
        "aren't AI astrology?' answer — model registry, per-run reproducibility "
        "envelope, dataset provenance, overridable assumptions.",
    ),
    (
        "Machine-learning layer",
        ["§33", "§34"],
        "The learned traffic-speed models underneath the projection: nine "
        "classical regressors and an LSTM fitted on the loop-detector speed "
        "corpus, their measured held-out scores, the observed sensor network, "
        "and the MongoDB-backed run ledger. Every response carries its "
        "provenance and runs on the local Auckland network.",
    ),
    (
        "Policy input",
        ["§3"],
        "Turn a natural-language policy into the compiled, auditable Policy DSL.",
    ),
    (
        "Baseline world",
        ["§5", "§28.2"],
        "The browsable World-A digital twin: aggregate baseline metrics and the "
        "demographic / economic / geographic / institutional structure.",
    ),
    (
        "Core simulation & time machine",
        ["§7.5", "§9", "§11", "§21", "§22", "§34.10"],
        "Apply the compiled policy to the deterministic A/B model across the Time "
        "Machine checkpoints, amend it, compare worlds, and re-run under pinned "
        "assumptions.",
    ),
    (
        "Hybrid forecast layers",
        ["§7.1", "§7.2", "§7.3", "§7.4", "§7.6", "§7.7", "§8"],
        "The independent §7 forecast families — historical analogue, time-series, "
        "microsimulation, economic spillover, system dynamics, spatial assignment "
        "— plus the ensemble that pools them.",
    ),
    (
        "Uncertainty, sensitivity & backtesting",
        ["§24", "§25", "§26"],
        "Honest-about-the-future analysis: Monte-Carlo uncertainty fans, "
        "which-assumption-matters attribution, and historical backtesting.",
    ),
    (
        "Explainability",
        ["§26"],
        "Walk any headline metric down its input-data → transform → model → "
        "assumptions → result causal trace (the Evidence Drawer).",
    ),
    (
        "Governance agents",
        ["§11", "§12", "§18"],
        "The Model Parliament debate, the Devil's-Advocate failure-mode register, "
        "and the professional-mandate institutional reviewers.",
    ),
    (
        "Society & media",
        ["§13", "§14", "§15", "§16"],
        "Cohort public reaction, opinion diffusion across a social graph, the "
        "SIMULATED media feed, and the staged press conference.",
    ),
    (
        "Micro drill-downs",
        ["§17"],
        "Click a single household or firm and see its before/after life staged "
        "over the Time Machine — the macro/micro explainability bridge.",
    ),
    (
        "Decision support",
        ["§20", "§22", "§23"],
        "Choose under uncertainty: policy optimiser, robustness/regret ranking, "
        "external-shock stress tests, and SDG alignment.",
    ),
    (
        "Composed answers & export",
        ["§27", "§28", "§29", "§37"],
        "One-call compositions a judge or minister reads directly — the killer-demo "
        "pipeline, the §37 North-Star answer, and the printable Minister's Brief.",
    ),
]

# One card per served route. ``ex`` = keyless GET companion; ``tag`` = provenance
# class of this route's numbers (None = prose-only / mixed / pure metadata).
_S = MetricTag.simulated
_E = MetricTag.estimated
_G = MetricTag.generated
_O = MetricTag.observed

# (path, area, spec_sections, summary, produces_numbers, output_tag, keyless_example)
ENDPOINTS: list[tuple] = [
    # --- System & transparency ---
    ("/", "System & transparency", [], "Service root: name, version, docs/health/capabilities links.", False, _O, None),
    ("/health", "System & transparency", [], "Liveness probe + coarse config (llm_enabled).", False, _O, None),
    ("/capabilities", "System & transparency", ["§27", "§33"], "This manifest: every route mapped to its SPEC section, area and provenance class.", False, _O, None),
    ("/registry", "System & transparency", ["§33"], "Model & assumption registry: every forecast layer, its live assumptions and the §34 guardrails.", False, _O, None),
    ("/reproduce", "System & transparency", ["§32"], "Per-run reproducibility envelope: content-addressed run_id over pinned inputs + datasets.", False, _O, None),
    ("/data-fabric", "System & transparency", ["§4"], "Dataset ingestion & provenance catalogue with harmonisation lineage (built live from the file bytes).", False, _O, None),
    ("/assumptions", "System & transparency", ["§34.10"], "The overridable model-assumption catalogue (read live from the running dataclasses).", False, _O, None),
    # --- Machine-learning layer ---
    ("/ml/models", "Machine-learning layer", ["§33"], "The bake-off leaderboard: nine classical regressors plus the LSTM, with R2/MAE/RMSE measured on the held-out test split.", True, _O, None),
    ("/ml/forecast", "Machine-learning layer", ["§33"], "Forecast the next twelve 5-minute link speeds from an observed 12-step history (LSTM), cross-checked against the winning classical regressor.", True, _S, "/ml/forecast/example"),
    ("/ml/forecast/example", "Machine-learning layer", ["§33"], "Keyless: a demo forecast for an arterial sliding into the AM peak.", False, _S, None),
    ("/ml/anomaly", "Machine-learning layer", ["§33"], "Isolation-forest score for one traffic window — does it look like an incident rather than a peak?", True, _S, None),
    ("/ml/anomaly/profile", "Machine-learning layer", ["§33"], "Keyless: corpus-wide anomaly rate and how it varies by hour of day.", False, _O, None),
    ("/ml/congestion-clock", "Machine-learning layer", ["§33"], "Keyless: fitted speed over the hour x day-of-week grid — the 24x7 congestion surface.", False, _E, None),
    ("/ml/sensors", "Machine-learning layer", ["§4", "§33"], "The real loop-detector network from MongoDB: locations and observed speed profiles.", False, _O, None),
    ("/ml/runs", "Machine-learning layer", ["§32"], "The MongoDB-backed simulation run ledger — what was run, when, and against which policy.", False, _O, None),
    ("/parliament/nz/history", "Governance agents", ["§11"], "Official New Zealand general-election results 2005-2023: party vote shares and seat counts (Observed).", False, _O, None),
    ("/parliament/nz/chamber", "Governance agents", ["§11"], "The House as it currently stands: seats by party after the 2023 election.", False, _O, None),
    ("/parliament/nz/division", "Governance agents", ["§11", "§34"], "Simulate a whipped roll-call division over the real 2023 House, party by party, from stance priors plus the simulated outcome.", True, _S, "/parliament/nz/division/example"),
    ("/parliament/nz/division/example", "Governance agents", ["§11"], "Keyless: a division on the canonical demo charge.", False, _S, None),
    # --- Policy input ---
    ("/policy/compile", "Policy input", ["§3"], "Compile natural-language policy text into the structured Policy DSL (LLM prose or rule fallback).", False, _G, None),
    ("/scenarios", "Policy input", ["§3", "§28"], "The discoverable menu of canonical demo policies: NL prompt + live compiled DSL + ready-to-POST bodies for /simulate and the composed-answer endpoints.", False, _O, None),
    ("/scenarios/{scenario_id}", "Policy input", ["§3", "§28"], "One canonical scenario by id (404 echoes the valid ids).", False, _O, None),
    # --- Baseline world ---
    ("/baseline", "Baseline world", ["§5"], "World-A aggregate baseline: mode split, traffic, CO2, transit + reference time series.", True, _S, None),
    ("/world", "Baseline world", ["§5", "§28.2"], "The composed baseline digital twin across the six §5 layers (population/economy/geography/environment/institutions/society).", False, _S, None),
    # --- Core simulation & time machine ---
    ("/simulate", "Core simulation & time machine", ["§7.5", "§9"], "World A, World B and Δ(B−A) per metric across the Time-Machine checkpoints (Simulated).", True, _S, None),
    ("/simulate/amend", "Core simulation & time machine", ["§11"], "Re-simulate an amended policy (the parliament amendment loop) and compare to the original.", True, _S, None),
    ("/compare", "Core simulation & time machine", ["§21"], "Compare the baseline against one or more caller amendments — never a metric without its baseline.", True, _S, None),
    ("/compare/grand", "Core simulation & time machine", ["§21", "§22"], "The canonical A/B/C/D quartet (baseline / policy / opposition amendment / GOV SIM-optimised).", True, _S, None),
    ("/assumptions/rerun", "Core simulation & time machine", ["§34.10"], "Pin one or more assumptions to chosen values and re-run A/B/Δ (clamped + flagged if out of range).", True, _S, None),
    # --- Hybrid forecast layers ---
    ("/analogues", "Hybrid forecast layers", ["§7.1"], "Historical-analogue causal layer: difference-in-differences over comparable real schemes + transferability.", True, _E, None),
    ("/timeseries", "Hybrid forecast layers", ["§7.2"], "Fitted statistical baseline forecast (trend+seasonality+AR1), then the policy shifts the trajectory.", True, _E, None),
    ("/microsim", "Hybrid forecast layers", ["§7.3"], "Person-level who-gains/who-loses welfare table by income decile, household, neighbourhood, occupation.", True, _S, None),
    ("/economy", "Hybrid forecast layers", ["§7.4"], "Transparent input-output / elasticity spillover: charge transfer, revenue recycling, footfall, logistics.", True, _E, None),
    ("/dynamics", "Hybrid forecast layers", ["§7.6"], "Stocks-and-flows system dynamics closing the recursive feedback loop (charge→mode→revenue→capacity→support).", True, _S, None),
    ("/spatial", "Hybrid forecast layers", ["§7.7"], "Peak-hour static traffic assignment (BPR/MSA) on the real road graph: cordon inflow, accessibility, CO2 dispersion.", True, _S, None),
    ("/ensemble", "Hybrid forecast layers", ["§8"], "Pool the methodologically-independent estimators into a weighted ensemble whose band spans their disagreement.", True, _E, None),
    # --- Uncertainty, sensitivity & backtesting ---
    ("/uncertainty", "Uncertainty, sensitivity & backtesting", ["§24"], "Seeded Monte-Carlo sweep over the documented assumptions → uncertainty fan + most-influential assumption.", True, _S, None),
    ("/sensitivity", "Uncertainty, sensitivity & backtesting", ["§24", "§26"], "Deterministic OAT tornado: which assumption is each metric's answer resting on, across the whole dashboard.", True, _E, None),
    ("/backtest", "Uncertainty, sensitivity & backtesting", ["§25"], "Replay a historical case through the model on pre-implementation state and score against actuals.", True, _S, None),
    # --- Explainability ---
    ("/evidence", "Explainability", ["§26"], "Turn one metric into the input-data → transform → model → assumptions → result causal ladder.", True, _S, None),
    # --- Governance agents ---
    ("/parliament/debate", "Governance agents", ["§11"], "The five-persona Model Parliament debate + stance tally + synthesis (prose Generated, numbers cited).", False, _G, None),
    ("/parliament/ask", "Governance agents", ["§11"], "Ask a single parliament persona a question grounded in the simulated evidence.", False, _G, None),
    ("/parliament/failure-modes", "Governance agents", ["§12"], "The Devil's-Advocate ranked Failure-Mode Register (risk/mechanism/severity/probability/evidence/mitigation).", True, _E, None),
    ("/institutions/review", "Governance agents", ["§18"], "Professional-mandate reviewers (Climate/Implementation/Legal/Auditor) assessing the policy on the same evidence.", False, _G, None),
    # --- Society & media ---
    ("/public", "Society & media", ["§13"], "Cohort public-reaction model: per-income-band Likert support distribution + net support (not one 'public' agent).", True, _S, None),
    ("/diffusion", "Society & media", ["§14"], "Friedkin–Johnsen opinion diffusion over a typed social graph: trajectories, salience, polarisation, coalitions.", True, _S, None),
    ("/media", "Society & media", ["§15"], "The SIMULATED media feed across horizons (labelled banner, fictional outlets; prose Generated).", False, _G, None),
    ("/press-conference", "Society & media", ["§16"], "Staged post-announcement press conference: spokesperson statement + five archetype journalists (Generated).", False, _G, None),
    # --- Micro drill-downs ---
    ("/citizen", "Micro drill-downs", ["§17"], "Single-household drill-down: before/after commute + cost + support staged over the Time Machine, with a Why?.", True, _S, None),
    ("/business", "Micro drill-downs", ["§17"], "Single-firm drill-down: footfall, labour accessibility, deliveries, cost, revenue proxy + adaptation decisions.", True, _E, None),
    # --- Decision support ---
    ("/optimise", "Decision support", ["§22"], "Grid-search candidate interventions under objective+constraints → 4-objective Pareto frontier + labelled picks.", True, _S, None),
    ("/shortlist", "Decision support", ["§21", "§22"], "Rank the caller's OWN 2–8 candidate policies head-to-head: simulate each → caller-weighted composite + Pareto dominance + labelled winner/greenest/most-equitable picks.", True, _S, None),
    ("/robustness", "Decision support", ["§20", "§22"], "Decision-under-uncertainty across candidates × shock states: payoff/regret matrices + maximin/minimax-regret/Laplace picks.", True, _S, None),
    ("/sdg", "Decision support", ["§23"], "Map the sim + audit artifacts onto UN SDG 11/16/13/10 indicators (no arbitrary composite score).", True, _S, None),
    ("/stress-test", "Decision support", ["§20"], "Re-run the policy under named external shocks (recession/fuel/flood/…) → per-metric robust/weakened/reversed verdict.", True, _S, None),
    # --- Composed answers & export ---
    ("/run", "Composed answers & export", ["§28", "§29"], "The one-call killer-demo pipeline: compile→simulate→public→parliament→auto-amendment→media in one consistent envelope.", True, None, None),
    ("/north-star", "Composed answers & export", ["§37"], "The §37 minister's answer as a fixed 15-line narrative, every line embedding the standalone endpoint's own object.", True, None, None),
    ("/brief", "Composed answers & export", ["§27"], "The one-page printable Minister's Brief (Markdown memo) rendered from the North-Star answer.", True, None, None),
    # --- Keyless GET companions (canonical answers with no body) ---
    ("/analogues/cases", "Hybrid forecast layers", ["§7.1"], "The curated historical-analogue case database (illustrative published figures).", False, _O, None),
    ("/backtest/example", "Uncertainty, sensitivity & backtesting", ["§25"], "Keyless: the built-in synthetic 2018 cordon backtest.", False, _S, None),
    ("/brief/example", "Composed answers & export", ["§27"], "Keyless: the Minister's Brief for the canonical §28 demo charge.", False, None, None),
    ("/business/sample", "Micro drill-downs", ["§17"], "Keyless: a policy-independent firm picker spanning sectors.", False, _O, None),
    ("/citizen/sample", "Micro drill-downs", ["§17"], "Keyless: a policy-independent household picker spanning income bands.", False, _O, None),
    ("/compare/example", "Core simulation & time machine", ["§21", "§22"], "Keyless: the A/B/C/D four-world comparison for the demo charge.", False, _S, None),
    ("/evidence/example", "Explainability", ["§26"], "Keyless: the causal trace for peak transit demand (the spec's own worked example).", False, _S, None),
    ("/north-star/example", "Composed answers & export", ["§37"], "Keyless: the §37 North-Star answer for the demo charge.", False, None, None),
    ("/run/example", "Composed answers & export", ["§28", "§29"], "Keyless: the full killer-demo pipeline for the demo charge, no body.", False, None, None),
    ("/robustness/objectives", "Decision support", ["§20", "§22"], "Keyless: the selectable robustness objectives + shock-state keys.", False, _O, None),
    ("/shortlist/example", "Decision support", ["§21", "§22"], "Keyless: rank three contrasting demo policies (charge→buses vs charge→general-fund vs pedestrianise).", False, _S, None),
    ("/stress-test/catalogue", "Decision support", ["§20"], "Keyless: the named external-shock scenario catalogue with documented knobs.", False, _O, None),
]

# Wire each POST endpoint to its keyless GET companion (kept next to the data so
# the two lists can't disagree).
_KEYLESS_COMPANION: dict[str, str] = {
    "/backtest": "/backtest/example",
    "/brief": "/brief/example",
    "/business": "/business/sample",
    "/citizen": "/citizen/sample",
    "/compare/grand": "/compare/example",
    "/evidence": "/evidence/example",
    "/north-star": "/north-star/example",
    "/run": "/run/example",
    "/analogues": "/analogues/cases",
    "/robustness": "/robustness/objectives",
    "/shortlist": "/shortlist/example",
    "/stress-test": "/stress-test/catalogue",
}

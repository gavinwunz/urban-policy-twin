/**
 * Tiny typed client for the GOV SIM backend.
 *
 * The base URL comes from `NEXT_PUBLIC_API_BASE_URL` so the same build can point
 * at local dev or a deployed backend. All values returned by the twin are tagged
 * Observed/Estimated/Simulated/Generated per SPEC §34; this module only carries
 * the liveness probe for now.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface Health {
  status: string;
  service: string;
  version: string;
  environment: string;
  llm_enabled: boolean;
}

/** Fetch the backend liveness probe. Throws on network/HTTP error. */
export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${API_BASE_URL}/health`, {
    signal,
    // Always hit the live backend; never serve a stale cached health status.
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  const body = (await res.json()) as Partial<Health>;
  // Guard against a *different* service answering on the same host/port: a bare
  // 200 with the wrong shape must not read as a healthy GOV SIM backend (SPEC §34
  // honesty). Require the fields we actually render.
  if (
    typeof body?.status !== "string" ||
    typeof body?.service !== "string" ||
    typeof body?.version !== "string"
  ) {
    throw new Error(
      "Reachable, but the response isn’t the GOV SIM /health payload — is another service on this port?",
    );
  }
  return body as Health;
}

// ---------------------------------------------------------------------------
// Policy compiler (SPEC §3) — POST /policy/compile
// ---------------------------------------------------------------------------

/**
 * The structured Policy DSL is deliberately typed loosely on the client: the
 * backend (`app/policy/dsl.py`) owns the authoritative schema, and the editable
 * assumptions panel reads/writes fields by dotted path rather than by a fixed
 * shape. Keeping it as a nested record avoids the two schemas drifting.
 */
export type PolicyDSL = Record<string, unknown>;

/**
 * One extracted/inferred field surfaced for human correction. Per SPEC §3 the
 * compiler must "display every extracted assumption … never bury assumptions
 * inside prompts", so each carries where it came from and how sure we are.
 */
export interface Assumption {
  /** Dotted path into the DSL, e.g. `intervention.amount`. */
  field: string;
  /** The value the compiler chose (scalar, array, or nested object). */
  value: unknown;
  /** `stated` (verbatim), `inferred` (derived), or `default` (not in text). */
  source: "stated" | "inferred" | "default" | string;
  /** 0..1 confidence. */
  confidence: number;
  /** Short human-readable justification. */
  rationale: string;
}

export interface CompileResponse {
  policy: PolicyDSL;
  assumptions: Assumption[];
  /** `"llm"` or `"rule_based"`. */
  method: string;
  /** Always `"Generated"` — the DSL is machine-produced (SPEC §34). */
  provenance: string;
  warnings: string[];
}

export interface CompileRequest {
  text: string;
  jurisdiction?: string;
}

/** Compile natural-language policy text into a Policy DSL. Throws on error. */
export async function compilePolicy(
  req: CompileRequest,
  signal?: AbortSignal,
): Promise<CompileResponse> {
  const res = await fetch(`${API_BASE_URL}/policy/compile`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as CompileResponse;
}

// ---------------------------------------------------------------------------
// Baseline (World A) — GET /baseline (SPEC §5/§9)
// ---------------------------------------------------------------------------

/** Provenance class for a single number (SPEC §8). */
export type MetricTag = "Observed" | "Estimated" | "Simulated" | "Generated";

export interface Checkpoint {
  label: string;
  t_months: number;
  t_years: number;
}

/** A metric's central value + uncertainty band at one checkpoint (SPEC §8/§9). */
export interface MetricPoint {
  t_months: number;
  value: number;
  low: number;
  high: number;
}

export interface MetricSeries {
  key: string;
  label: string;
  unit: string;
  tag: MetricTag;
  method: string;
  assumptions: string[];
  points: MetricPoint[];
}

export interface BaselineTimeSeries {
  provenance: MetricTag;
  note: string;
  checkpoints: Checkpoint[];
  series: MetricSeries[];
  trend: Record<string, unknown>;
}

export interface ModeShare {
  car: number;
  public_transit: number;
  walk: number;
  car_pct: number;
  public_transit_pct: number;
  walk_pct: number;
}

export interface BaselineSnapshot {
  world: string;
  provenance: MetricTag;
  note: string;
  population_agents: number;
  commuters: number;
  mode_share: ModeShare;
  traffic: Record<string, number>;
  emissions: Record<string, number>;
  transit: Record<string, number>;
  metrics: Array<{
    key: string;
    label: string;
    value: number;
    unit: string;
    tag: MetricTag;
    method: string;
    assumptions: string[];
  }>;
  params: Record<string, unknown>;
}

export interface BaselineResponse {
  world: string;
  provenance: MetricTag;
  snapshot: BaselineSnapshot;
  timeseries: BaselineTimeSeries;
}

/** Fetch the World-A baseline snapshot + time series. Throws on error. */
export async function getBaseline(
  signal?: AbortSignal,
): Promise<BaselineResponse> {
  const res = await fetch(`${API_BASE_URL}/baseline`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as BaselineResponse;
}

// ---------------------------------------------------------------------------
// Simulation (World B) — POST /simulate (SPEC §5/§7.7/§21)
// ---------------------------------------------------------------------------

/** One metric's Δ(B−A) point at a checkpoint, with a combined band. */
export interface DeltaPoint {
  t_months: number;
  world_a: number;
  world_b: number;
  delta: number;
  delta_pct: number | null;
  low: number;
  high: number;
}

export interface DeltaSeries {
  key: string;
  label: string;
  unit: string;
  tag: MetricTag;
  method: string;
  points: DeltaPoint[];
}

export interface DeltaTimeSeries {
  provenance: MetricTag;
  note: string;
  checkpoints: Checkpoint[];
  series: DeltaSeries[];
}

export interface LedgerEvent {
  id: string;
  type: string;
  scenario_month: number;
  scenario_year: number;
  timestamp: string | null;
  description: string;
  cause: string[];
  affected_agents: number;
  confidence: number;
  downstream: string[];
  severity: string;
  evidence: Record<string, unknown>;
  provenance: MetricTag;
}

export interface EventLedger {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  events: LedgerEvent[];
  thresholds: Record<string, unknown>;
}

export interface SimulateResponse {
  provenance: MetricTag;
  policy_id: string;
  note: string;
  world_a: { snapshot: BaselineSnapshot; timeseries: BaselineTimeSeries };
  world_b: { snapshot: Record<string, unknown>; timeseries: BaselineTimeSeries };
  delta: DeltaTimeSeries;
  event_ledger: EventLedger;
  shocks_applied: Record<string, unknown>;
  seed: number | null;
}

/** Run the deterministic policy simulation for a compiled DSL. Throws on error. */
export async function simulate(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<SimulateResponse> {
  const res = await fetch(`${API_BASE_URL}/simulate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as SimulateResponse;
}

// ---------------------------------------------------------------------------
// Model Parliament — POST /parliament/debate + /parliament/failure-modes
// ---------------------------------------------------------------------------

export type Stance = "support" | "oppose" | "conditional" | "challenge";

export interface EvidenceCitation {
  kind: string;
  ref: string;
  detail: string;
  tag: MetricTag;
}

export interface Argument {
  persona: string;
  role: string;
  stance: Stance;
  headline: string;
  points: string[];
  speech: string;
  citations: EvidenceCitation[];
  confidence: number;
}

export interface DebateResponse {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  motion: string;
  method: string;
  arguments: Argument[];
  tally: Record<string, number>;
  summary: string;
}

/** Convene the Model Parliament to debate a compiled policy. Throws on error. */
export async function runDebate(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<DebateResponse> {
  const res = await fetch(`${API_BASE_URL}/parliament/debate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as DebateResponse;
}

/** The five Parliament personas `POST /parliament/ask` will address. */
export const PERSONAS = [
  "Government",
  "Opposition",
  "Equity Advocate",
  "Economist",
  "Devil's Advocate",
] as const;
export type PersonaName = (typeof PERSONAS)[number];

export interface AskResponse {
  provenance: MetricTag;
  persona: string;
  role: string;
  stance: Stance;
  question: string;
  answer: string;
  method: string;
  citations: EvidenceCitation[];
}

/** Ask one persona a direct follow-up question, grounded in their own evidence. */
export async function askPersona(
  policy: PolicyDSL,
  persona: PersonaName,
  question: string,
  signal?: AbortSignal,
): Promise<AskResponse> {
  const res = await fetch(`${API_BASE_URL}/parliament/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, persona, question }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as AskResponse;
}

export type Severity = "low" | "medium" | "high" | "critical";

export interface FailureMode {
  id: string;
  risk: string;
  mechanism: string;
  severity: Severity;
  probability: number;
  risk_score: number;
  evidence: EvidenceCitation[];
  mitigation: string;
  affected_agents: number;
}

export interface FailureModeRegister {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  failure_modes: FailureMode[];
}

/** Devil's Advocate → ranked Failure Mode Register for a policy. Throws on error. */
export async function runFailureModes(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<FailureModeRegister> {
  const res = await fetch(`${API_BASE_URL}/parliament/failure-modes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as FailureModeRegister;
}

// ---------------------------------------------------------------------------
// Public reaction — POST /public (SPEC §13)
// ---------------------------------------------------------------------------

/** Support distribution over the six SPEC §13 buckets (fractions sum to ~1). */
export interface OpinionDistribution {
  strong_support: number;
  support: number;
  neutral: number;
  oppose: number;
  strong_oppose: number;
  uncertain: number;
  /** (strong_support + support) − (oppose + strong_oppose), in [-1, 1]. */
  net_support: number;
}

export interface CohortOpinion {
  key: string;
  income_band: string;
  /** `"inbound"` (commutes into CBD) or `"local"`. */
  geography: string;
  travel_mode: string;
  size: number;
  mean_material_impact: number;
  mean_fairness: number;
  mean_support: number;
  distribution: OpinionDistribution;
}

export interface PublicOpinion {
  /** Always `"Simulated"` — deterministic structural model, no poll (SPEC §34). */
  provenance: MetricTag;
  note: string;
  policy_id: string;
  population: number;
  overall: OpinionDistribution;
  cohorts: CohortOpinion[];
  params: Record<string, unknown>;
}

/** Gauge the deterministic cohort public reaction to a policy. Throws on error. */
export async function runPublicOpinion(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<PublicOpinion> {
  const res = await fetch(`${API_BASE_URL}/public`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as PublicOpinion;
}

// ---------------------------------------------------------------------------
// Evidence drawer — POST /evidence (SPEC §26)
// ---------------------------------------------------------------------------

/** One behavioural lever the policy applies to the mode-choice model (SPEC §7.5). */
export interface BehaviouralRule {
  name: string;
  label: string;
  parameter: string;
  value: number;
  unit: string;
  plausible_range: number[];
  sensitivity: string;
  source: string;
}

/** One node on the causal trace (input-data → … → result). */
export interface TraceStep {
  stage: "input-data" | "transform" | "model" | "assumption" | "result" | string;
  label: string;
  detail: string;
  tag: MetricTag;
  value: number | null;
  unit: string;
  refs: string[];
}

export interface TraceAssumption {
  name: string;
  value: number | string;
  unit: string;
  detail: string;
  tag: MetricTag;
}

export interface HistoricalAnalogue {
  scheme: string;
  city: string;
  year: number;
  mechanism: string;
  relevance: string;
  tag: MetricTag;
  note: string;
}

export interface TraceConfidence {
  value: number;
  band_half_width: number;
  band_rel_pct: number | null;
  horizon_months: number;
  note: string;
}

export interface TraceResult {
  world_a: number;
  world_b: number;
  delta: number;
  delta_pct: number | null;
  low: number;
  high: number;
}

export interface ProvenanceTrace {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  metric_key: string;
  metric_label: string;
  unit: string;
  tag: MetricTag;
  horizon: Checkpoint;
  available_horizons_months: number[];
  result: TraceResult;
  confidence: TraceConfidence;
  ascii_trace: string;
  chain: TraceStep[];
  rules: BehaviouralRule[];
  assumptions: TraceAssumption[];
  historical_analogues: HistoricalAnalogue[];
  citations: string[];
}

/** Fetch the causal provenance trace for one metric under a policy. Throws on error. */
export async function runEvidence(
  policy: PolicyDSL,
  metricKey: string,
  horizonMonths?: number,
  signal?: AbortSignal,
): Promise<ProvenanceTrace> {
  const res = await fetch(`${API_BASE_URL}/evidence`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      policy,
      metric_key: metricKey,
      horizon_months: horizonMonths ?? null,
    }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail && typeof body.detail === "object") {
        const d = body.detail as { error?: string };
        if (d.error) detail = d.error;
      }
    } catch {
      // keep generic message
    }
    throw new Error(detail);
  }
  return (await res.json()) as ProvenanceTrace;
}

/**
 * Trace the canonical §26 metric (peak transit demand — *"why does public
 * transport demand rise?"*) for the §28 demo congestion charge with no request
 * body (`GET /evidence/example`). A body-less GET so a judge landing cold — with
 * no compiled policy in the store — can still open the Evidence Drawer and walk
 * the whole causal ladder with one keyless click. It compiles the demo policy and
 * runs the *identical* `run_evidence` service `POST /evidence` uses, so this
 * surface can never disagree with the POST endpoint; every number is copied from
 * the deterministic simulation with no LLM on the numeric path (SPEC §26/§34).
 * Throws on network/HTTP error so the drawer shows an honest waiting/error state
 * instead of inventing a trace.
 */
export async function getEvidenceExample(
  signal?: AbortSignal,
): Promise<ProvenanceTrace> {
  const res = await fetch(`${API_BASE_URL}/evidence/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail && typeof body.detail === "object") {
        const d = body.detail as { error?: string };
        if (d.error) detail = d.error;
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as ProvenanceTrace;
}

// ---------------------------------------------------------------------------
// Simulated media — POST /media (SPEC §15)
// ---------------------------------------------------------------------------

export type MediaArchetype =
  | "public_broadcaster"
  | "business_press"
  | "local_news"
  | "tabloid"
  | "environmental"
  | "industry";

export type MediaSentiment = "positive" | "critical" | "mixed" | string;

export interface Headline {
  archetype: MediaArchetype;
  /** Fictional generic outlet name — never a real outlet. */
  outlet_label: string;
  headline: string;
  standfirst: string;
  angle: string;
  sentiment: MediaSentiment;
  /** Event ids / metric keys the story is built on. */
  cited_refs: string[];
  /** Mandatory SIMULATED banner (SPEC §15). */
  label: string;
  /** Always `"Generated"`. */
  provenance: MetricTag;
}

export interface MediaScenario {
  /** Horizon label, e.g. "Month 5". */
  label: string;
  scenario_month: number;
  headlines: Headline[];
}

export interface MediaResponse {
  /** `"Generated"` — media prose is generated; cited figures are Simulated. */
  provenance: MetricTag;
  disclaimer: string;
  note: string;
  policy_id: string;
  /** `"llm"` or `"template"`. */
  method: string;
  scenarios: MediaScenario[];
}

/** Generate clearly-labelled SIMULATED media coverage for a policy. Throws on error. */
export async function runMedia(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<MediaResponse> {
  const res = await fetch(`${API_BASE_URL}/media`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as MediaResponse;
}

// ---------------------------------------------------------------------------
// SDG alignment — POST /sdg (SPEC §23)
// ---------------------------------------------------------------------------

/** One measurable indicator / transparent proxy mapped to an SDG target. */
export interface SdgIndicator {
  id: string;
  sdg_target: string;
  indicator: string;
  proxy_for: string;
  unit: string;
  baseline: number;
  scenario: number;
  change: number;
  change_pct: number | null;
  /** `"higher"` or `"lower"` — direction of improvement. */
  better_when: string;
  improved: boolean;
  data_source: string;
  confidence: number;
  /** `"high" | "medium" | "low"`. */
  confidence_label: string;
  tag: MetricTag;
  note: string;
}

export interface SdgGoal {
  goal: number;
  title: string;
  /** `"core"` or `"secondary"` GOV SIM alignment (SPEC §23). */
  tier: string;
  indicators: SdgIndicator[];
  improved_count: number;
  worsened_count: number;
  unchanged_count: number;
  summary: string;
}

export interface SdgReport {
  /** Always `"Simulated"` — deterministic sim mapped onto SDG targets (SPEC §34). */
  provenance: MetricTag;
  note: string;
  policy_id: string;
  horizon: Checkpoint;
  goals: SdgGoal[];
  total_improved: number;
  total_worsened: number;
  total_unchanged: number;
  /** Count-based summary — never an arbitrary SDG score (SPEC §23). */
  headline: string;
}

/** Map a compiled policy onto UN SDG targets. Throws on error. */
export async function runSdg(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<SdgReport> {
  const res = await fetch(`${API_BASE_URL}/sdg`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as SdgReport;
}

// ---------------------------------------------------------------------------
// Opinion diffusion — POST /diffusion (SPEC §14)
// ---------------------------------------------------------------------------

export interface DiffusionNode {
  id: string;
  type: string;
  label: string;
  size: number;
  susceptibility: number;
  initial_opinion: number;
  final_opinion: number;
  opinion_prior_source: string;
}

export interface DiffusionEdge {
  source: string;
  target: string;
  weight: number;
  kind: string;
}

export interface OpinionTrajectory {
  node_id: string;
  opinions: number[];
}

export interface Coalition {
  /** `"support" | "oppose" | "contested"`. */
  stance: string;
  members: string[];
  citizen_share: number;
  mean_opinion: number;
}

export interface InfoShock {
  round: number;
  node: string;
  delta: number;
  label: string;
}

export interface DiffusionResult {
  /** Always `"Simulated"` — deterministic Friedkin–Johnsen diffusion (SPEC §34). */
  provenance: MetricTag;
  note: string;
  policy_id: string;
  rounds: number;
  nodes: DiffusionNode[];
  edges: DiffusionEdge[];
  trajectories: OpinionTrajectory[];
  /** Issue salience per round (0–1). */
  salience: number[];
  /** Opinion polarisation per round (0–1). */
  polarisation: number[];
  coalitions: Coalition[];
  initial_net_support: number;
  final_net_support: number;
  dominant_narrative: string;
  shocks_applied: InfoShock[];
  assumptions: Record<string, unknown>;
}

/** Run the opinion-diffusion process for a policy. Throws on error. */
export async function runDiffusion(
  policy: PolicyDSL,
  rounds?: number,
  signal?: AbortSignal,
): Promise<DiffusionResult> {
  const res = await fetch(`${API_BASE_URL}/diffusion`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rounds != null ? { policy, rounds } : { policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as DiffusionResult;
}

// ---------------------------------------------------------------------------
// Backtesting — GET /backtest/example + POST /backtest (SPEC §25)
// ---------------------------------------------------------------------------

export interface ActualObservation {
  metric_key: string;
  t_months: number;
  value: number;
  low: number | null;
  high: number | null;
}

export interface HistoricalCase {
  id: string;
  name: string;
  description: string;
  policy: PolicyDSL;
  implementation_date: string | null;
  horizon_months: number;
  observations: ActualObservation[];
  events: Array<{ type: string; t_months: number }>;
  /** `Observed` for real cases; the built-in demo is `Simulated` (synthetic). */
  actuals_provenance: MetricTag;
  actuals_note: string;
}

export interface MetricScore {
  metric_key: string;
  t_months: number;
  forecast: number;
  forecast_low: number | null;
  forecast_high: number | null;
  actual: number;
  baseline: number;
  error: number;
  abs_error: number;
  pct_error: number | null;
  direction_correct: boolean;
  within_interval: boolean;
}

export interface EventTimingScore {
  type: string;
  predicted_month: number | null;
  actual_month: number | null;
  timing_error_months: number | null;
  matched: boolean;
}

export interface Scorecard {
  provenance: MetricTag;
  note: string;
  case_id: string;
  case_name: string;
  /** Provenance of the ACTUALS being scored against (SPEC §25/§34). */
  actuals_provenance: MetricTag;
  actuals_note: string;
  n_observations: number;
  mae: number;
  rmse: number;
  mape_pct: number | null;
  direction_accuracy_pct: number;
  interval_coverage_pct: number;
  mean_event_timing_error_months: number | null;
  metric_scores: MetricScore[];
  event_scores: EventTimingScore[];
  geographic_accuracy: string | null;
  summary: string;
}

/** Fetch the built-in synthetic benchmark case (its actuals are Simulated). */
export async function getBacktestExample(
  signal?: AbortSignal,
): Promise<HistoricalCase> {
  const res = await fetch(`${API_BASE_URL}/backtest/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as HistoricalCase;
}

/** Replay a case (or the built-in benchmark if omitted) → scorecard. Throws on error. */
export async function runBacktest(
  historicalCase?: HistoricalCase,
  signal?: AbortSignal,
): Promise<Scorecard> {
  const res = await fetch(`${API_BASE_URL}/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(historicalCase ? { case: historicalCase } : {}),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as Scorecard;
}

// ---------------------------------------------------------------------------
// Ensemble forecast (SPEC §8) — POST /ensemble
// ---------------------------------------------------------------------------

/** One independent estimator's view of the flagship metric (a SPEC §7 layer). */
export interface MethodEstimate {
  method_id: string;
  name: string;
  spec_layer: string;
  approach: string;
  central_pct: number;
  low_pct: number;
  high_pct: number;
  weight: number;
  applicable: boolean;
  tag: MetricTag;
  assumptions: string[];
  note: string;
}

/** The pooled ensemble estimate for one metric with a disagreement signal. */
export interface EnsembleMetric {
  metric_key: string;
  label: string;
  unit: string;
  horizon: Checkpoint;
  methods: MethodEstimate[];
  ensemble_central_pct: number;
  ensemble_low_pct: number;
  ensemble_high_pct: number;
  method_spread_pct: number;
  /** 'low' | 'moderate' | 'high' agreement label. */
  disagreement: string;
  tag: MetricTag;
  interpretation: string;
}

export interface EnsembleForecast {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  horizon: Checkpoint;
  metrics: EnsembleMetric[];
  method_weights: Record<string, number>;
}

/**
 * Run the multi-method ensemble forecast for a compiled policy (SPEC §8). The
 * band each metric carries spans method *disagreement*, not a single run's noise.
 * Throws on network/HTTP error.
 */
export async function runEnsemble(
  policy: PolicyDSL,
  horizonMonths = 24,
  signal?: AbortSignal,
): Promise<EnsembleForecast> {
  const res = await fetch(`${API_BASE_URL}/ensemble`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, horizon_months: horizonMonths }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as EnsembleForecast;
}

// ---------------------------------------------------------------------------
// Press conference (SPEC §16) — POST /press-conference
// ---------------------------------------------------------------------------

/** One journalist's pointed, evidence-anchored question. */
export interface PressQuestion {
  archetype: string;
  outlet_label: string;
  reporter: string;
  question: string;
  angle: string;
  /** 'friendly' | 'neutral' | 'hostile'. */
  hostility: string;
  cited_refs: string[];
}

/** The spokesperson's grounded response to one question. */
export interface PressAnswer {
  /** 'defends' | 'acknowledges' | 'rebuts' | 'commits'. */
  stance: string;
  answer: string;
  cited_refs: string[];
}

export interface PressExchange {
  question: PressQuestion;
  answer: PressAnswer;
}

export interface PressConference {
  provenance: MetricTag;
  disclaimer: string;
  note: string;
  policy_id: string;
  /** 'llm' or 'template'. */
  method: string;
  horizon: Checkpoint;
  spokesperson: string;
  opening_statement: string;
  opening_refs: string[];
  exchanges: PressExchange[];
  public_mood: string;
}

/**
 * Stage a simulated press conference for a compiled policy (SPEC §16): a
 * spokesperson opening plus five archetype journalist exchanges, each grounded in
 * a specific Δ metric or event. The whole thing is fictional (SIMULATED) — prose
 * is Generated over Simulated figures; no LLM produces a number. Throws on error.
 */
export async function runPressConference(
  policy: PolicyDSL,
  horizonMonths = 5,
  signal?: AbortSignal,
): Promise<PressConference> {
  const res = await fetch(`${API_BASE_URL}/press-conference`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, horizon_months: horizonMonths }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as PressConference;
}

// ---------------------------------------------------------------------------
// Policy optimiser (SPEC §22) — POST /optimise
// ---------------------------------------------------------------------------

export interface CandidateConfig {
  intervention_type: string;
  charge_amount: number | null;
  public_transport_share: number;
  exempt_low_income: boolean;
  pedestrianised: boolean;
}

export interface CandidateMetrics {
  emissions_reduction_pct: number;
  traffic_reduction_pct: number;
  transit_gain_pct: number;
  avg_commute_increase_pct: number;
  low_income_burden_pct: number;
  net_support: number;
  /** Illustrative scheme cost — an Estimated proxy, NOT a simulated figure. */
  est_cost: number;
}

export interface OptimiserCandidate {
  policy_id: string;
  label: string;
  description: string[];
  config: CandidateConfig;
  metrics: CandidateMetrics;
  feasible: boolean;
  violated_constraints: string[];
  pareto: boolean;
}

export interface OptimiserRecommendations {
  cheapest: string | null;
  most_equitable: string | null;
  largest_emissions_reduction: string | null;
  best_balanced: string | null;
}

export interface OptimiserResult {
  provenance: MetricTag;
  note: string;
  objective: Record<string, unknown>;
  constraints: Record<string, unknown>;
  horizon: Checkpoint;
  n_candidates: number;
  n_feasible: number;
  constraints_satisfiable: boolean;
  pareto_front: OptimiserCandidate[];
  recommendations: OptimiserRecommendations;
  candidates: OptimiserCandidate[];
  cost_model: Record<string, unknown>;
  objective_axes: string[];
}

/**
 * Search the candidate policy grid for a given objective + constraints and return
 * the feasible Pareto frontier plus representative picks (SPEC §22). Outcome
 * metrics are Simulated; the budget cost proxy is an Estimated documented
 * constant. Policy-independent — runs without a compiled policy. Throws on error.
 */
export async function runOptimise(
  objective: Record<string, unknown> = {},
  constraints: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<OptimiserResult> {
  const res = await fetch(`${API_BASE_URL}/optimise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ objective, constraints }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as OptimiserResult;
}

// ---------------------------------------------------------------------------
// Uncertainty fan (SPEC §24) — POST /uncertainty
// ---------------------------------------------------------------------------

/** A central estimate's [low, high] band at one confidence level. */
export interface Interval {
  level: number;
  low: number;
  high: number;
}

/** The fan at one Time-Machine checkpoint: median + nested intervals. */
export interface HorizonBand {
  t_months: number;
  t_years: number;
  median: number;
  intervals: Interval[];
}

/** One assumption's influence on the metric (one-at-a-time swing). */
export interface SensitivityEntry {
  rank: number;
  name: string;
  label: string;
  unit: string;
  low_value: number;
  high_value: number;
  delta_at_low: number;
  delta_at_high: number;
  swing: number;
  swing_pct_of_median: number | null;
  /** 'up' | 'down' | 'flat'. */
  direction: string;
}

/** One behavioural-regime run in the model-disagreement ensemble. */
export interface EnsembleVariant {
  name: string;
  label: string;
  delta: number;
  description: string;
}

export interface ModelDisagreement {
  variants: EnsembleVariant[];
  spread: number;
  note: string;
}

export interface UncertaintyResult {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  metric_key: string;
  metric_label: string;
  unit: string;
  horizon: Checkpoint;
  point_estimate: number;
  median: number;
  mean: number;
  intervals: Interval[];
  samples: number;
  seed: number;
  fan: HorizonBand[];
  influential_assumptions: SensitivityEntry[];
  model_disagreement: ModelDisagreement;
  swept_assumptions: string[];
}

/**
 * Thrown when the requested metric key isn't in the simulation's delta series.
 * Carries the backend's list of valid keys so the UI can offer them (SPEC §24).
 */
export class MetricNotFoundError extends Error {
  available: string[];
  constructor(message: string, available: string[]) {
    super(message);
    this.name = "MetricNotFoundError";
    this.available = available;
  }
}

/**
 * Monte-Carlo uncertainty fan for one metric of a compiled policy (SPEC §24):
 * median + 50/80/95% intervals per horizon, a ranked sensitivity list, and a
 * behavioural-regime disagreement ensemble. Every number is a re-run of the
 * deterministic model with perturbed assumptions — no LLM on the numeric path.
 * Throws `MetricNotFoundError` (with valid keys) on an unknown metric.
 */
export async function runUncertainty(
  policy: PolicyDSL,
  metricKey: string,
  signal?: AbortSignal,
): Promise<UncertaintyResult> {
  const res = await fetch(`${API_BASE_URL}/uncertainty`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, metric_key: metricKey }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 404) {
      try {
        const body = (await res.json()) as {
          detail?: { error?: string; available_metric_keys?: string[] };
        };
        const d = body.detail;
        if (d && Array.isArray(d.available_metric_keys)) {
          throw new MetricNotFoundError(
            d.error ?? `Unknown metric key ${metricKey}`,
            d.available_metric_keys,
          );
        }
      } catch (e) {
        if (e instanceof MetricNotFoundError) throw e;
        // fall through to generic error below
      }
    }
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as UncertaintyResult;
}

// ---------------------------------------------------------------------------
// Global sensitivity tornado (SPEC §24/§26) — POST /sensitivity
// ---------------------------------------------------------------------------

/**
 * How far one metric's policy effect Δ(B−A) moves when one assumption is swept
 * from its documented low edge to its documented high edge (others held at
 * default) — one bar of a tornado chart.
 */
export interface AssumptionSwing {
  name: string;
  label: string;
  unit: string;
  low_value: number;
  high_value: number;
  delta_at_low: number;
  delta_at_high: number;
  /** Signed high−low change in the metric's Δ. */
  swing: number;
  /** |swing| — the bar length for ranking. */
  abs_swing: number;
  /** |swing| as % of the default-assumption Δ (null when that Δ ≈ 0). */
  pct_of_default: number | null;
  /** This assumption's 0–1 share of THIS metric's total sensitivity. */
  influence_share: number;
  /** 'up' | 'down' | 'flat'. */
  direction: string;
}

/** One headline metric's tornado: its default effect + every assumption swing. */
export interface MetricTornado {
  key: string;
  label: string;
  unit: string;
  tag: MetricTag;
  default_delta: number;
  total_abs_swing: number;
  most_influential: string | null;
  bars: AssumptionSwing[];
}

/** One assumption's aggregate leverage across the whole dashboard. */
export interface AssumptionDriver {
  name: string;
  label: string;
  unit: string;
  /** Mean influence_share across all metrics (0–1). */
  global_score: number;
  max_pct_of_default: number | null;
  top_metric: string | null;
  /** False when this assumption is flat on every metric for this policy. */
  matters: boolean;
  note: string;
}

/** Global one-at-a-time sensitivity tornado across all headline metrics. */
export interface SensitivityResult {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  horizon: Checkpoint;
  swept_assumptions: string[];
  drivers: AssumptionDriver[];
  tornados: MetricTornado[];
  headline: string;
  not_modelled: string[];
}

/**
 * Cross-metric one-at-a-time sensitivity tornado for a compiled policy
 * (`POST /sensitivity`, SPEC §24/§26). Where `/uncertainty` gives a Monte-Carlo
 * fan for a *single* metric, this ranks which assumptions the whole dashboard's
 * answer rests on. Every value is a re-run of the deterministic model at
 * documented assumption edges — no LLM on the numeric path (SPEC §34). Throws on
 * network/HTTP error so the panel can show an honest waiting/error state.
 */
export async function runSensitivity(
  policy: PolicyDSL,
  horizonMonths?: number | null,
  metricKeys?: string[] | null,
  signal?: AbortSignal,
): Promise<SensitivityResult> {
  const res = await fetch(`${API_BASE_URL}/sensitivity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      policy,
      ...(horizonMonths != null ? { horizon_months: horizonMonths } : {}),
      ...(metricKeys && metricKeys.length > 0 ? { metric_keys: metricKeys } : {}),
    }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as SensitivityResult;
}

// ---------------------------------------------------------------------------
// Counterfactual comparison (SPEC §21) — POST /compare
// ---------------------------------------------------------------------------

/** One world's value for one metric at the headline horizon. */
export interface ComparisonCell {
  world_id: string;
  value: number;
  delta_vs_baseline: number;
  delta_pct: number | null;
}

/** One metric across all worlds at the headline horizon. */
export interface ComparisonRow {
  key: string;
  label: string;
  unit: string;
  tag: MetricTag;
  /** World-A value — never omitted (SPEC §21). */
  baseline_value: number;
  cells: ComparisonCell[];
}

/** One intervention world (B, C, D…) — meta only; snapshots typed loosely. */
export interface CounterfactualWorld {
  id: string;
  /** 'intervention' | 'amendment'. */
  role: string;
  label: string;
  policy_id: string;
  changes: string[];
}

export interface CounterfactualComparison {
  provenance: MetricTag;
  note: string;
  base_policy_id: string;
  horizon: Checkpoint;
  worlds: CounterfactualWorld[];
  headline_table: ComparisonRow[];
  /**
   * How the C/D worlds were derived — present only on the grand A/B/C/D
   * comparison (`POST /compare/grand`); `null`/absent on a plain `/compare`.
   */
  derivation?: GrandDerivation | null;
}

/** Optimiser candidate config underlying World D (from the §22 optimiser). */
export interface OptimiserCandidateConfig {
  intervention_type: string;
  charge_amount: number | null;
  public_transport_share: number;
  exempt_low_income: boolean;
  pedestrianised: boolean;
}

/** World C audit record: how the opposition amendment was derived (SPEC §21). */
export interface GrandWorldC {
  role: string;
  /** 'caller' (supplied) or a deterministic-default source label. */
  source: string;
  proposed: boolean;
  amendment: Amendment | null;
  rationale: string;
}

/** World D audit record: the §22 optimiser's best-balanced pick (SPEC §21/§22). */
export interface GrandWorldD {
  role: string;
  objective: Record<string, number>;
  constraints: Record<string, number>;
  constraints_satisfiable: boolean;
  /** Which recommendation slot supplied World D (e.g. 'best_balanced'). */
  selection: string;
  chosen_policy_id: string | null;
  config: OptimiserCandidateConfig | null;
  feasible: boolean | null;
  n_candidates: number;
  n_feasible: number;
}

/** The `derivation` audit block returned only by `POST /compare/grand`. */
export interface GrandDerivation {
  world_c?: GrandWorldC;
  world_d?: GrandWorldD;
}

/** Request body for `POST /compare/grand`. */
export interface GrandCompareRequest {
  policy: PolicyDSL;
  amendment?: Amendment | null;
  objective?: Record<string, number>;
  constraints?: Record<string, number>;
  horizon_months?: number | null;
}

/**
 * Compare World A (baseline) vs World B (intervention) vs one world per amendment
 * (C, D…) in a single deterministic payload (SPEC §21). The baseline is always
 * present. Returns the headline table (baseline + every world + Δ per metric at
 * one horizon) plus per-world metadata. Throws on network/HTTP error.
 */
export async function runCompare(
  policy: PolicyDSL,
  amendments: Amendment[] = [],
  signal?: AbortSignal,
): Promise<CounterfactualComparison> {
  const res = await fetch(`${API_BASE_URL}/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, amendments }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as CounterfactualComparison;
}

/**
 * Grand counterfactual (SPEC §21/§22): the canonical four-way comparison —
 * World A (baseline) vs B (the compiled policy) vs C (opposition amendment,
 * auto-derived when none is supplied) vs D (the GOV SIM-optimised best-balanced
 * pick). Same deterministic payload as `/compare` plus a `derivation` audit
 * block explaining how C/D were composed. The baseline is always present; every
 * number is Simulated, no LLM on the numeric path (SPEC §34). Throws on error.
 */
export async function runGrandCompare(
  req: GrandCompareRequest,
  signal?: AbortSignal,
): Promise<CounterfactualComparison> {
  const res = await fetch(`${API_BASE_URL}/compare/grand`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as CounterfactualComparison;
}

/**
 * Compose the SPEC §21 four-world grand comparison (A baseline / B policy /
 * C opposition amendment / D GOV SIM-optimised) for the canonical §28 demo
 * congestion charge (`GET /compare/example`). A body-less GET so a judge landing
 * on the Grand-counterfactual tab cold can read the whole quartet with no
 * compiled policy in the store. It runs the *identical* `compare_grand` service
 * `POST /compare/grand` uses, so it can never disagree with the POST surface;
 * every number stays Simulated with no LLM on the numeric path (SPEC §21/§34).
 * Throws on network/HTTP error so the panel shows an honest waiting/error state
 * instead of inventing a comparison.
 */
export async function getCompareExample(
  signal?: AbortSignal,
): Promise<CounterfactualComparison> {
  const res = await fetch(`${API_BASE_URL}/compare/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as CounterfactualComparison;
}

// ---------------------------------------------------------------------------
// Institutional review panel (SPEC §18) — POST /institutions/review
// ---------------------------------------------------------------------------

/** An institutional agent's professional verdict on one dimension. */
export type Verdict = "clear" | "conditional" | "concern" | "block";

/** One specific, evidence-anchored observation within a review. */
export interface InstitutionalFinding {
  dimension: string;
  detail: string;
  /** 'info' | 'watch' | 'risk' | 'blocker'. */
  severity: string;
}

/** One institutional agent's structured assessment (SPEC §18). */
export interface InstitutionalReview {
  agent: string;
  mandate: string;
  spec_ref: string;
  verdict: Verdict;
  summary: string;
  findings: InstitutionalFinding[];
  recommendation: string;
  citations: EvidenceCitation[];
  confidence: number;
}

export interface InstitutionsResponse {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  reviews: InstitutionalReview[];
  overall_verdict: Verdict;
  verdict_tally: Record<string, number>;
  summary: string;
}

/**
 * Run the institutional review panel for a compiled policy (SPEC §18): Climate,
 * Implementation, Legal/Constitutional and Auditor agents each assess the policy
 * against a professional mandate, grounded in the deterministic simulation. The
 * prose is Generated; every cited number is Simulated. Throws on error.
 */
export async function runInstitutions(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<InstitutionsResponse> {
  const res = await fetch(`${API_BASE_URL}/institutions/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as InstitutionsResponse;
}

// ---------------------------------------------------------------------------
// Model registry / transparency manifest (SPEC §33) — GET /registry
// ---------------------------------------------------------------------------

/** One documented, auditable input assumption feeding a model. */
export interface AssumptionRecord {
  name: string;
  label: string;
  value: unknown;
  unit: string;
  source: string;
  tag: MetricTag;
}

/** A self-describing entry for one model / forecast layer (SPEC §7/§33). */
export interface ModelCard {
  id: string;
  name: string;
  spec_sections: string[];
  layer: string;
  method: string;
  /** 'deterministic' | 'stochastic (seeded)'. */
  determinism: string;
  produces_numbers: boolean;
  /** MUST be false for any numeric model (SPEC §34 guardrail). */
  llm_touches_numbers: boolean;
  llm_role: string;
  inputs: string[];
  outputs: string[];
  output_tag: MetricTag;
  code: string;
  assumptions: AssumptionRecord[];
}

/** One data source the models read (SPEC §4/§33). */
export interface DataSourceCard {
  id: string;
  name: string;
  /** 'synthetic' | 'legacy' | 'live' | 'assumption-set'. */
  kind: string;
  description: string;
  tag: MetricTag;
  used_by: string[];
}

/** One SPEC §34 anti-'AI-astrology' guardrail and how GOV SIM enforces it. */
export interface GuardrailCheck {
  id: string;
  rule: string;
  enforced_by: string;
  holds: boolean;
}

export interface ModelRegistry {
  provenance: MetricTag;
  note: string;
  app_version: string;
  generated_from: string;
  models: ModelCard[];
  data_sources: DataSourceCard[];
  guardrails: GuardrailCheck[];
  assumption_index: AssumptionRecord[];
  counts: Record<string, number>;
}

/**
 * Fetch the transparency manifest (SPEC §33): every forecast layer, its live
 * assumptions, data sources, and the SPEC §34 guardrail checklist. Deterministic,
 * no LLM. Throws on network/HTTP error.
 */
export async function getRegistry(signal?: AbortSignal): Promise<ModelRegistry> {
  const res = await fetch(`${API_BASE_URL}/registry`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as ModelRegistry;
}

// ---------------------------------------------------------------------------
// Amendment loop — a structured DSL mutation re-run through /simulate (SPEC §12)
// ---------------------------------------------------------------------------

export interface Amendment {
  label: string;
  exempt_low_income?: boolean;
  exempt_residents?: boolean;
  set_charge_amount?: number | null;
  charge_multiplier?: number | null;
  set_public_transport_share?: number | null;
}

/**
 * Apply an amendment to a compiled DSL client-side, mirroring the backend's
 * `apply_amendment` (backend/app/simulation/amendment.py). The amended DSL is
 * then re-run through `POST /simulate` — the killer interaction (SPEC §29): the
 * change is a transparent structured edit, all numbers still come from the model.
 */
export function applyAmendment(policy: PolicyDSL, a: Amendment): PolicyDSL {
  const amended = JSON.parse(JSON.stringify(policy)) as Record<string, unknown>;
  const id = String((policy as Record<string, unknown>).id ?? "policy");
  amended.id = `${id}__${a.label.replace(/ /g, "_")}`;

  const exemptions = Array.isArray(amended.exemptions)
    ? [...(amended.exemptions as string[])]
    : [];
  if (a.exempt_low_income && !exemptions.some((e) => e.toLowerCase().includes("income"))) {
    exemptions.push("low-income");
  }
  if (a.exempt_residents && !exemptions.some((e) => e.toLowerCase().includes("resident"))) {
    exemptions.push("residents");
  }
  amended.exemptions = exemptions;

  const intervention = (amended.intervention as Record<string, unknown>) ?? {};
  if (a.set_charge_amount != null) {
    intervention.amount = a.set_charge_amount;
  }
  if (a.charge_multiplier != null && typeof intervention.amount === "number") {
    intervention.amount = Math.round(intervention.amount * a.charge_multiplier * 1e4) / 1e4;
  }
  amended.intervention = intervention;

  if (a.set_public_transport_share != null) {
    const pt = a.set_public_transport_share;
    amended.revenue_allocation = {
      public_transport: pt,
      general_fund: Math.round((1 - pt) * 1e4) / 1e4,
    };
  }
  return amended as PolicyDSL;
}

/**
 * Server-authoritative amendment comparison — `POST /simulate/amend` (SPEC §12).
 * Where `applyAmendment` + `simulate` re-runs the amended World B to drive the
 * shared map/dashboard, this endpoint re-simulates BOTH the original and amended
 * policies over the same baseline and returns the isolated **Δ(amended − original)**
 * — the amendment's own marginal effect, which the World-B snapshot alone can't
 * show. Both worlds and the delta are Simulated; no LLM touches any number (§34).
 */
export interface AmendmentComparison {
  original_policy_id: string;
  amended_policy_id: string;
  amendment: Amendment;
  changes: string[];
  original_world_b: Record<string, unknown>;
  amended_world_b: Record<string, unknown>;
  original_vs_baseline: DeltaTimeSeries;
  amended_vs_baseline: DeltaTimeSeries;
  /** Δ(amended − original): the effect of the amendment itself. */
  amendment_delta: DeltaTimeSeries;
}

/**
 * Ask the backend for the isolated effect of a structured amendment vs the
 * original policy (`POST /simulate/amend`). Throws on network/HTTP error so the
 * panel can show an honest waiting/error state instead of inventing a figure (§34).
 */
export async function amendPolicy(
  policy: PolicyDSL,
  amendment: Amendment,
  signal?: AbortSignal,
): Promise<AmendmentComparison> {
  const res = await fetch(`${API_BASE_URL}/simulate/amend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, amendment }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as AmendmentComparison;
}

// ---------------------------------------------------------------------------
// Economic spillover (SPEC §7.4) — POST /economy
// ---------------------------------------------------------------------------

/**
 * One transparent economic transmission channel (input-output / elasticity). The
 * physical driver (`physical_value`) is Simulated by the mode-choice model; the
 * monetary translation (`annual_impact` + band) is Estimated (SPEC §8/§34).
 */
export interface EconomicChannel {
  id: string;
  name: string;
  mechanism: string;
  direction: string; // 'positive' | 'negative' | 'ambiguous'
  physical_basis: string;
  physical_value: number | null;
  annual_impact: number;
  annual_impact_low: number;
  annual_impact_high: number;
  unit: string;
  confidence: number;
  confidence_label: string;
  tag: MetricTag;
  assumptions: string[];
  note: string;
}

/**
 * How one sector is exposed to the policy — a direction + qualitative magnitude,
 * deliberately NOT a fabricated hard jobs/GDP number (SPEC §34).
 */
export interface SectorExposure {
  sector: string;
  direction: string; // 'positive' | 'negative' | 'ambiguous'
  magnitude: string; // 'low' | 'moderate' | 'high'
  mechanism: string;
  annual_impact_estimate: number | null;
  tag: MetricTag;
}

/** Local-economy spillover report for one policy run (SPEC §7.4). */
export interface EconomicSpilloverReport {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  horizon: Checkpoint;
  channels: EconomicChannel[];
  sector_exposure: SectorExposure[];
  net_annual_impact: number;
  net_annual_impact_low: number;
  net_annual_impact_high: number;
  net_confidence: number;
  unit: string;
  not_modelled: string[];
  assumptions: Record<string, unknown>;
  headline: string;
}

/**
 * Estimate a policy's local economic spillover via `POST /economy`. Builds ahead
 * of / alongside the backend against the documented contract; throws on
 * network/HTTP error so the panel can show an honest waiting/error state rather
 * than inventing a figure (SPEC §34).
 */
export async function runEconomy(
  policy: PolicyDSL,
  horizonMonths?: number,
  signal?: AbortSignal,
): Promise<EconomicSpilloverReport> {
  const res = await fetch(`${API_BASE_URL}/economy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, horizon_months: horizonMonths ?? null }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as EconomicSpilloverReport;
}

// ---------------------------------------------------------------------------
// System Dynamics / recursive feedback loop (SPEC §7.6/§19) — POST /dynamics
// ---------------------------------------------------------------------------

/** One checkpoint of the coupled stock trajectories (SPEC §19). */
export interface StockPoint {
  t_months: number;
  t_years: number;
  charge: number;
  support: number;
  transit_demand: number;
  transit_capacity: number;
  crowding: number;
  cumulative_reinvestment: number;
  annual_revenue: number;
  confidence: number;
}

/** A discrete second-order event the recursive loop produced (SPEC §10/§19). */
export interface FeedbackEvent {
  t_months: number;
  type: string; // amendment | capacity_exceeded | crowding_relieved | support_recovered
  label: string;
  cause_chain: string[];
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  confidence: number;
}

/** Closed-loop (political response ON) vs open-loop (OFF) end-state contrast. */
export interface FeedbackContrast {
  metric: string;
  closed_loop: number;
  open_loop: number;
  delta: number;
  interpretation: string;
}

/** Full recursive stock-flow feedback simulation for a policy (SPEC §7.6/§19). */
export interface SystemDynamicsResult {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  political_response_enabled: boolean;
  loop_description: string[];
  trajectory: StockPoint[];
  feedback_events: FeedbackEvent[];
  contrast: FeedbackContrast[];
  final_state: StockPoint;
  amendments_triggered: number;
  anchors: Record<string, unknown>;
  params: Record<string, unknown>;
  not_modelled: string[];
}

/**
 * Run the recursive stocks-and-flows feedback simulation via `POST /dynamics`.
 * Builds ahead of / alongside the backend against the documented contract; throws
 * on network/HTTP error so the panel can show an honest waiting/error state rather
 * than inventing a trajectory (SPEC §34).
 */
export async function runDynamics(
  policy: PolicyDSL,
  politicalResponse: boolean,
  signal?: AbortSignal,
): Promise<SystemDynamicsResult> {
  const res = await fetch(`${API_BASE_URL}/dynamics`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy, political_response: politicalResponse }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as SystemDynamicsResult;
}

// ---------------------------------------------------------------------------
// Distributional microsimulation (SPEC §7.3) — POST /microsim
// ---------------------------------------------------------------------------

/** Distributional impact for one population subgroup (SPEC §7.3). */
export interface GroupImpact {
  group: string;
  agents: number;
  /** Mean per-trip generalized-cost change (min-equiv). +worse / −better. */
  mean_gc_change_min: number;
  /** Mean daily welfare change in money-equivalent (Estimated). +loss. */
  mean_money_equiv_daily: number;
  mean_charge_paid_daily: number;
  /** Mean annual charge as % of annual income (0 for non-payers). */
  mean_burden_pct_income: number;
  pct_worse_off: number;
  pct_better_off: number;
  pct_switched_mode: number;
}

/**
 * Whether the policy's own stated equity constraint holds against the modelled
 * numbers (SPEC §7.3/§34). A policy may declare
 * `constraints.max_low_income_burden_increase_pct` — a cap the minister sets on
 * how much the charge may raise the lowest-income decile's cost burden. The
 * engine now *tests* that cap against the same deterministic microsim burden it
 * reports, rather than merely asserting it in debate: a constraint you never
 * check is theatre. `null` when the policy states no such cap.
 */
export interface ConstraintCheck {
  /** The DSL constraint being checked. */
  name: string;
  /** Stated maximum low-income burden increase (% of income). */
  cap_pct: number;
  /**
   * Modelled World-B out-of-pocket charge burden on the lowest-income decile as
   * % of income. Baseline burden is zero (no charge), so this IS the increase
   * the cap governs.
   */
  modelled_low_income_burden_pct: number;
  /** Whether the modelled increase is within the stated cap. */
  satisfied: boolean;
  /** Cap − modelled: positive = headroom, negative = overshoot (pp). */
  margin_pct: number;
  /** Plain-language reading of the check. */
  note: string;
  provenance: MetricTag;
}

/** Display verdict for a {@link ConstraintCheck}. */
export interface ConstraintVerdict {
  /** `pass` = within cap with real burden; `fail` = overshoots; `moot` = no modelled burden. */
  status: "pass" | "fail" | "moot";
  /** Short badge label. */
  label: string;
  /** Colour class shared with the microsim styles. */
  cls: "good" | "warn";
}

/**
 * Map a {@link ConstraintCheck} to a display verdict (pure; unit-tested). Honesty
 * matters here (SPEC §34): a policy that keeps the low-income decile at zero
 * modelled burden satisfies its cap only *vacuously*, so we mark that `moot`
 * rather than dressing it up as an actively-met promise. A real overshoot is a
 * hard `fail` — the app never softens a policy breaking its own stated equity
 * constraint. The 0.005% floor matches the two-decimal burden shown on screen.
 */
export function constraintVerdict(c: ConstraintCheck): ConstraintVerdict {
  if (c.modelled_low_income_burden_pct <= 0.005) {
    return { status: "moot", label: "No low-income burden", cls: "good" };
  }
  return c.satisfied
    ? { status: "pass", label: "Constraint met", cls: "good" }
    : { status: "fail", label: "Constraint violated", cls: "warn" };
}

/** Full person-level distributional microsimulation report (SPEC §7.3). */
export interface MicrosimReport {
  policy_id: string;
  provenance: MetricTag;
  note: string;
  commuters: number;
  winners: number;
  losers: number;
  unaffected: number;
  mean_gc_change_min: number;
  payers: number;
  mean_payer_burden_pct: number;
  /** Lowest-decile ÷ highest-decile mean burden. >1 = regressive. */
  regressivity_ratio: number;
  regressivity_note: string;
  /**
   * Compliance of the policy's stated equity constraint against the modelled
   * outcome (SPEC §34). `null` when the policy states no low-income burden cap.
   */
  constraint_check: ConstraintCheck | null;
  by_income_decile: GroupImpact[];
  by_household_type: GroupImpact[];
  by_geography: GroupImpact[];
  by_occupation: GroupImpact[];
  worst_hit: string;
  biggest_winner: string;
  params: Record<string, unknown>;
  not_modelled: string[];
}

/**
 * Run the distributional microsimulation via `POST /microsim`. Builds ahead of /
 * alongside the backend against the documented contract; throws on network/HTTP
 * error so the panel can show an honest waiting/error state rather than inventing
 * a distribution (SPEC §34).
 */
export async function runMicrosim(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<MicrosimReport> {
  const res = await fetch(`${API_BASE_URL}/microsim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as MicrosimReport;
}

// ---------------------------------------------------------------------------
// Spatial traffic-assignment (SPEC §7.7) — POST /spatial
// ---------------------------------------------------------------------------

/** Aggregate network performance for one world (peak hour). */
export interface NetworkState {
  world: string; // 'A' baseline or 'B' policy
  total_vehicle_hours: number;
  mean_vc: number;
  max_vc: number;
  congested_arcs: number;
  overcapacity_arcs: number;
  mean_speed_kmh: number;
  cordon_inflow_veh_per_hr: number;
  total_vehicle_km: number;
}

/** Per-arc load in both worlds (notable/cordon/bottleneck arcs). */
export interface ArcLoad {
  arc_id: string;
  from_zone: string;
  to_zone: string;
  road_class: string;
  crosses_cordon: boolean;
  capacity_veh_per_hr: number;
  flow_a: number;
  flow_b: number;
  vc_a: number;
  vc_b: number;
  speed_a_kmh: number;
  speed_b_kmh: number;
  delta_flow: number;
}

/** A per-zone value in both worlds (accessibility or pollution). */
export interface ZoneChange {
  zone_id: string;
  is_cbd: boolean;
  value_a: number;
  value_b: number;
  delta: number;
  delta_pct: number;
}

/** Gravity job-accessibility by congested car network (SPEC §7.7). */
export interface AccessibilityReport {
  metric: string;
  tag: MetricTag;
  mean_a: number;
  mean_b: number;
  mean_delta_pct: number;
  top_gainers: ZoneChange[];
  top_losers: ZoneChange[];
}

/** Road-CO₂ dispersion proxy by zone (SPEC §7.7). */
export interface PollutionReport {
  metric: string;
  tag: MetricTag;
  cbd_a: number;
  cbd_b: number;
  cbd_delta_pct: number;
  network_total_a: number;
  network_total_b: number;
  biggest_drops: ZoneChange[];
  biggest_rises: ZoneChange[];
  displacement_note: string;
}

/** Full spatial traffic-assignment report (SPEC §7.7). */
export interface SpatialReport {
  policy_id: string;
  provenance: MetricTag;
  note: string;
  peak_hour_car_trips_a: number;
  peak_hour_car_trips_b: number;
  world_a: NetworkState;
  world_b: NetworkState;
  cordon_inflow_delta_pct: number;
  vehicle_hours_delta_pct: number;
  notable_arcs: ArcLoad[];
  bottlenecks_a: ArcLoad[];
  bottlenecks_b: ArcLoad[];
  accessibility: AccessibilityReport;
  pollution: PollutionReport;
  params: Record<string, unknown>;
  not_modelled: string[];
}

/**
 * Run the peak-hour spatial traffic assignment via `POST /spatial`. Builds ahead
 * of / alongside the backend against the documented contract; throws on
 * network/HTTP error so the panel can show an honest waiting/error state rather
 * than inventing link flows (SPEC §34).
 */
export async function runSpatial(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<SpatialReport> {
  const res = await fetch(`${API_BASE_URL}/spatial`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as SpatialReport;
}

// ---------------------------------------------------------------------------
// Run reproducibility manifest (SPEC §32) — POST /reproduce
// ---------------------------------------------------------------------------

/** One pinned input dataset, content-addressed by file bytes (SPEC §4/§32). */
export interface DatasetVersion {
  id: string;
  name: string;
  provenance: MetricTag;
  /** 'synthetic' | 'legacy' | 'live'. */
  kind: string;
  generated_by: string;
  seed: unknown;
  path: string;
  /** SHA-256 of the file bytes — changes if the world state changes. */
  content_sha256: string;
  summary: Record<string, unknown>;
}

/** One model/forecast layer that participated, pinned to its code (SPEC §33). */
export interface ModelVersion {
  id: string;
  name: string;
  spec_sections: string[];
  code: string;
  /** 'deterministic' | 'stochastic (seeded)'. */
  determinism: string;
  output_tag: MetricTag;
  /** MUST be false for numeric models (SPEC §34). */
  llm_touches_numbers: boolean;
}

/**
 * The complete reproducibility record for one run (SPEC §32). The `run_id` is a
 * SHA-256 content address of the reproducing inputs (timestamp excluded), so
 * identical inputs always yield the same key — that is the REPRODUCE RUN
 * affordance. `reproducible` is proven, not asserted: the deterministic core is
 * run twice and its `output_digest` compared. The manifest is Observed about the
 * run; no LLM enters the numeric path (`prompts` is always empty, SPEC §34).
 */
export interface ReproManifest {
  provenance: MetricTag;
  note: string;
  run_id: string;
  reproducible: boolean;
  output_digest: string;
  created_at: string;
  app_version: string;
  code_version: string;
  seed: number | null;
  policy: PolicyDSL;
  shocks: Record<string, unknown>;
  datasets: DatasetVersion[];
  models: ModelVersion[];
  assumptions: AssumptionRecord[];
  /** LLM prompts on the numeric path — always empty (SPEC §34). */
  prompts: Array<Record<string, unknown>>;
  inputs_fingerprint: Record<string, unknown>;
  how_to_reproduce: string;
}

/**
 * Fetch the content-addressed reproducibility manifest for a compiled policy via
 * `POST /reproduce` (SPEC §32): dataset + model versions, live assumptions, seed,
 * code version, and a self-verified output digest proving the deterministic core
 * reproduces byte-for-byte. Deterministic, no LLM. Throws on network/HTTP error
 * so the panel can show an honest waiting/error state rather than a fake key.
 */
export async function runReproduce(
  policy: PolicyDSL,
  seed?: number | null,
  signal?: AbortSignal,
): Promise<ReproManifest> {
  const res = await fetch(`${API_BASE_URL}/reproduce`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(seed != null ? { policy, seed } : { policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as ReproManifest;
}

// ---------------------------------------------------------------------------
// Stress-testing environment (SPEC §20) — POST /stress-test, GET /stress-test/catalogue
// ---------------------------------------------------------------------------

/**
 * One named exogenous shock as listed by `GET /stress-test/catalogue`: the
 * human-meaningful scenario, the transparent numeric knobs it maps onto, its
 * model fidelity and a plain-language caveat. Magnitudes are Estimated scenario
 * assumptions, never observed (SPEC §20/§34).
 */
export interface ShockCard {
  key: string;
  label: string;
  /** macro | energy | climate | demographic | technology */
  category: string;
  description: string;
  /** The exact `Shocks` knobs applied to BOTH worlds (auditable). */
  overrides: Record<string, unknown>;
  rationale: string;
  /** modelled | partial | proxy — how faithfully the MVP core represents it. */
  fidelity: string;
  caveat: string;
  provenance: string;
}

export interface ShockCatalogue {
  provenance: string;
  note: string;
  scenarios: ShockCard[];
}

/**
 * How one headline metric's policy benefit Δ(B−A) holds up under one shock. A
 * shock is applied to both worlds, so the delta still isolates the policy;
 * comparing the shocked delta to the no-shock baseline delta tells us whether the
 * benefit survives (SPEC §20/§21).
 */
export interface MetricStress {
  key: string;
  label: string;
  unit: string;
  /** 'decrease' | 'increase' — direction of a *good* policy effect. */
  intended_direction: string;
  delta_baseline: number;
  delta_baseline_pct: number | null;
  delta_shocked: number;
  delta_shocked_pct: number | null;
  /** % of the no-shock benefit retained (100 = unchanged, <0 = reversed). */
  retained_pct: number | null;
  /** robust | strengthened | weakened | neutralised | reversed | n/a */
  verdict: string;
  note: string;
}

/** The policy re-run under one named scenario (or the no-shock baseline). */
export interface ScenarioResult {
  key: string;
  label: string;
  category: string;
  /** modelled | partial | proxy */
  fidelity: string;
  /** high | medium | low, from fidelity × horizon. */
  confidence: string;
  caveat: string;
  overrides: Record<string, unknown>;
  metrics: MetricStress[];
  /** holds | degrades | fails | reference */
  verdict: string;
  summary: string;
}

/** Roll-up: which shocks the policy withstands and which break it. */
export interface StressRobustness {
  robust_to: string[];
  degrades_under: string[];
  fails_under: string[];
  headline: string;
}

/** Full `POST /stress-test` payload (SPEC §20). */
export interface StressReport {
  provenance: MetricTag;
  policy_id: string;
  note: string;
  horizon_months: number;
  horizon_label: string;
  baseline: ScenarioResult;
  scenarios: ScenarioResult[];
  robustness: StressRobustness;
}

/**
 * List the named shock toggles with their transparent overrides + fidelity
 * caveats via `GET /stress-test/catalogue` (SPEC §20). Throws on network/HTTP
 * error so the panel shows an honest waiting/error state.
 */
export async function fetchStressCatalogue(
  signal?: AbortSignal,
): Promise<ShockCatalogue> {
  const res = await fetch(`${API_BASE_URL}/stress-test/catalogue`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as ShockCatalogue;
}

/**
 * Stress-test a compiled policy across the SPEC §20 named shocks via
 * `POST /stress-test`: re-runs the deterministic A/B/Δ core once per shock and
 * reports where the policy's benefit holds, degrades or fails. Shocks are
 * applied to both worlds so Δ(B−A) keeps isolating the policy; no randomness, no
 * LLM. Throws on network/HTTP error so the panel can show an honest waiting/error
 * state rather than inventing a robustness claim (SPEC §20/§34).
 */
export async function runStressTest(
  policy: PolicyDSL,
  scenarios?: string[] | null,
  horizonMonths?: number | null,
  signal?: AbortSignal,
): Promise<StressReport> {
  const body: Record<string, unknown> = { policy };
  if (scenarios && scenarios.length > 0) body.scenarios = scenarios;
  if (horizonMonths != null) body.horizon_months = horizonMonths;
  const res = await fetch(`${API_BASE_URL}/stress-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const errBody = (await res.json()) as { detail?: unknown };
      if (typeof errBody.detail === "string") {
        detail = errBody.detail;
      } else if (
        errBody.detail &&
        typeof errBody.detail === "object" &&
        "error" in errBody.detail &&
        typeof (errBody.detail as { error?: unknown }).error === "string"
      ) {
        detail = (errBody.detail as { error: string }).error;
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as StressReport;
}

// ---------------------------------------------------------------------------
// Decision under uncertainty (SPEC §20/§21/§22) — POST /robustness,
// GET /robustness/objectives. One level up from the stress test: given SEVERAL
// candidate policies and a set of possible futures, which candidate should a
// minister actually pick — the headline winner, or the one least bad when the
// world turns out otherwise? Pure composition of the deterministic stress core;
// every payoff is a Simulated Δ(B−A), no LLM (SPEC §22/§34).
// ---------------------------------------------------------------------------

/** One candidate's outcome in one state of the world (baseline or a shock). */
export interface RobustnessStateResult {
  state_key: string;
  state_label: string;
  category: string;
  /** Policy benefit on the objective (signed so higher = better). Simulated Δ(B−A). */
  payoff: number;
  payoff_pct: number | null;
  /** Best candidate's payoff here − this candidate's (≥0; 0 = best for this state). */
  regret: number;
  /** This candidate's benefit here as % of its own no-shock benefit. */
  retained_pct: number | null;
  /** high | medium | low (widens with the horizon). */
  confidence: string;
}

/** A candidate policy scored across every state of the world. */
export interface RobustnessCandidateScore {
  policy_id: string;
  label: string;
  states: RobustnessStateResult[];
  /** Baseline (no-shock) payoff — the "headline" number. */
  nominal_payoff: number;
  /** Minimum payoff across states (maximin input). */
  worst_case_payoff: number;
  best_case_payoff: number;
  /** Mean payoff across states (Laplace / equal-weight). */
  mean_payoff: number;
  /** Largest regret across states (minimax-regret / Savage input; lower is better). */
  max_regret: number;
  /** Fraction (0..1) of shock states where it retains ≥75% of its no-shock benefit. */
  robustness_score: number;
  holds_under: string[];
  fails_under: string[];
}

/** The candidate each decision criterion selects. */
export interface RobustnessDecisionPicks {
  /** Highest baseline payoff — the headline winner. */
  nominal_best: string | null;
  /** Highest worst-case payoff — best if you assume the worst state. */
  maximin: string | null;
  /** Lowest max-regret (Savage) — least "I wish I'd chosen otherwise". */
  minimax_regret: string | null;
  /** Highest robustness score (holds under most shocks). */
  most_robust: string | null;
  /** Highest mean payoff (equal-weight over states). */
  laplace: string | null;
}

/** Full `POST /robustness` payload (SPEC §20/§21/§22). */
export interface RobustnessReport {
  provenance: MetricTag;
  objective_key: string;
  objective_label: string;
  /** decrease | increase — the direction of a *good* effect. */
  objective_direction: string;
  horizon_months: number;
  horizon_label: string;
  /** State keys evaluated (baseline first). */
  states: string[];
  candidates: RobustnessCandidateScore[];
  picks: RobustnessDecisionPicks;
  /** One-line decision insight: does robustness change the choice? */
  headline: string;
  method: string;
}

/** `GET /robustness/objectives` — valid objective metric keys + the default. */
export interface RobustnessObjectives {
  provenance: MetricTag;
  note: string;
  objectives: string[];
  default: string;
}

/**
 * List the objective metric keys a robustness decision can be framed around via
 * `GET /robustness/objectives`. Throws on network/HTTP error so the panel shows
 * an honest waiting/error state instead of guessing objectives.
 */
export async function fetchRobustnessObjectives(
  signal?: AbortSignal,
): Promise<RobustnessObjectives> {
  const res = await fetch(`${API_BASE_URL}/robustness/objectives`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as RobustnessObjectives;
}

/**
 * Rank candidate policies under uncertainty via `POST /robustness`: scores each
 * candidate under the transparent baseline plus the SPEC §20 named shocks, builds
 * the regret matrix, and reports which candidate each decision criterion picks
 * (nominal / maximin / minimax-regret / Laplace) plus the stress-test robustness
 * rate. Every payoff is a deterministic Δ(B−A); no randomness, no LLM (SPEC §22).
 * Throws on network/HTTP error so the panel can show an honest waiting/error
 * state rather than inventing a decision (SPEC §34).
 */
export async function runRobustness(
  candidates: PolicyDSL[],
  opts?: {
    scenarios?: string[] | null;
    objective?: string | null;
    horizonMonths?: number | null;
  },
  signal?: AbortSignal,
): Promise<RobustnessReport> {
  const body: Record<string, unknown> = { candidates };
  if (opts?.scenarios && opts.scenarios.length > 0) body.scenarios = opts.scenarios;
  if (opts?.objective) body.objective = opts.objective;
  if (opts?.horizonMonths != null) body.horizon_months = opts.horizonMonths;
  const res = await fetch(`${API_BASE_URL}/robustness`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const errBody = (await res.json()) as { detail?: unknown };
      if (typeof errBody.detail === "string") {
        detail = errBody.detail;
      } else if (
        errBody.detail &&
        typeof errBody.detail === "object" &&
        "error" in errBody.detail &&
        typeof (errBody.detail as { error?: unknown }).error === "string"
      ) {
        detail = (errBody.detail as { error: string }).error;
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as RobustnessReport;
}

// ---------------------------------------------------------------------------
// Historical Analogue / Causal Layer (SPEC §7.1) — POST /analogues, GET /analogues/cases
// ---------------------------------------------------------------------------

/**
 * One real-world congestion-pricing / access-restriction scheme in the analogue
 * base (London, Stockholm, Singapore, Milan, Gothenburg, Oslo, Ghent, Madrid).
 * Its reported outcome is Observed (a real, published effect) but flagged
 * illustrative/approximate — a reference figure, not a live data source (§7.1).
 */
export interface HistoricalCase {
  id: string;
  name: string;
  city: string;
  country: string;
  year: number;
  intervention_family: string;
  scheme: string;
  treated_change_pct: number;
  control_change_pct: number;
  charge_per_day_ref: number | null;
  reinvested_in_transit: boolean;
  design: string;
  identification_strength: number;
  parallel_trend_note: string;
  context_similarity: number;
  mode_shift_note: string;
  source_note: string;
  tag: MetricTag;
}

/** One case's difference-in-differences effect and its transfer weight to the input policy. */
export interface CaseEstimate {
  case_id: string;
  name: string;
  year: number;
  applicable: boolean;
  /** treated_change − control_change (%), the trend-stripped effect. */
  did_effect_pct: number;
  identification_strength: number;
  transferability_score: number;
  /** identification_strength × transferability_score. */
  analogue_quality: number;
  /** Normalised weight this case carries in the pool. */
  pool_weight: number;
  /** The auditable components that built the transferability score. */
  transfer_factors: Record<string, number | boolean>;
  note: string;
  tag: MetricTag;
}

/** Cross-check of the analogue estimate against the agent-based model (SPEC §8 honesty). */
export interface StructuralComparison {
  /** The agent-based World-B model's own flagship cordon Δ% (Simulated). */
  structural_effect_pct: number;
  /** This layer's pooled analogue estimate (Estimated). */
  analogue_effect_pct: number;
  /** structural − analogue (percentage points). */
  gap_pct_points: number;
  /** 'consistent' | 'moderate gap' | 'large gap'. */
  agreement: string;
  interpretation: string;
  tag: MetricTag;
}

/** Full `POST /analogues` payload — the Historical Analogue / Causal Layer (SPEC §7.1). */
export interface AnalogueEstimate {
  /** Per-case outcomes are Observed; the transferred estimate is Estimated. */
  provenance: MetricTag;
  note: string;
  policy_id: string;
  intervention_family: string;
  horizon_label: string;
  metric_key: string;
  metric_label: string;
  /** Transfer-weighted central estimate of the % change (negative = fall). */
  estimated_effect_pct: number;
  ci_low_pct: number;
  ci_high_pct: number;
  /** 'strong' | 'moderate' | 'weak' overall analogue quality. */
  analogue_quality: string;
  transferability_score: number;
  cases: CaseEstimate[];
  identification_diagnostics: string[];
  structural_comparison: StructuralComparison | null;
  not_modelled: string[];
}

/**
 * Estimate the flagship cordon effect from comparable real-world schemes via
 * `POST /analogues` (SPEC §7.1): a difference-in-differences read per scheme
 * (treated change − background trend) transferred to this policy by an auditable
 * similarity score, pooled into a central estimate + confidence interval, with an
 * optional cross-check against the agent-based model (SPEC §8). Historical
 * outcomes are Observed but illustrative; the transfer is Estimated. No LLM
 * touches any number. Throws on network/HTTP error so the panel can show an
 * honest waiting/error state rather than inventing a figure (SPEC §7.1/§34).
 */
export async function runAnalogues(
  policy: PolicyDSL,
  horizonMonths?: number | null,
  includeStructuralComparison?: boolean,
  signal?: AbortSignal,
): Promise<AnalogueEstimate> {
  const body: Record<string, unknown> = { policy };
  if (horizonMonths != null) body.horizon_months = horizonMonths;
  if (includeStructuralComparison != null)
    body.include_structural_comparison = includeStructuralComparison;
  const res = await fetch(`${API_BASE_URL}/analogues`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const errBody = (await res.json()) as { detail?: unknown };
      if (typeof errBody.detail === "string") detail = errBody.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as AnalogueEstimate;
}

/**
 * The raw curated database of real-world schemes behind the analogue layer via
 * `GET /analogues/cases` (illustrative, Observed). Throws on network/HTTP error.
 */
export async function fetchAnalogueCases(
  signal?: AbortSignal,
): Promise<HistoricalCase[]> {
  const res = await fetch(`${API_BASE_URL}/analogues/cases`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as HistoricalCase[];
}

// ---------------------------------------------------------------------------
// Time-series forecast (SPEC §7.2) — POST /timeseries
// ---------------------------------------------------------------------------

/** A forecast value with 80% / 95% prediction intervals at one horizon. */
export interface ForecastPoint {
  t_months: number;
  value: number;
  low80: number;
  high80: number;
  low95: number;
  high95: number;
}

/** The fitted structural-model parameters — the model made auditable (SPEC §8). */
export interface FitDiagnostics {
  level: number;
  slope_per_month: number;
  seasonal_amplitude: number;
  ar1_phi: number;
  residual_sigma: number;
  in_sample_mape_pct: number;
  /** Out-of-sample MAPE on a held-out tail; null when the series is too short. */
  holdout_mape_pct: number | null;
  method: string;
}

/** World-A (baseline) and World-B (policy) forecasts for one metric. */
export interface MetricForecast {
  key: string;
  label: string;
  unit: string;
  is_share: boolean;
  /** Synthetic monthly history is Simulated (not real observations). */
  history_tag: MetricTag;
  history: number[];
  fit: FitDiagnostics;
  /** Statistical baseline extrapolation is Estimated. */
  world_a_tag: MetricTag;
  world_a: ForecastPoint[];
  /** Baseline forecast shifted by the deterministic ABM policy Δ — Simulated. */
  world_b_tag: MetricTag;
  world_b: ForecastPoint[];
  /** The ABM Δ(B−A)% applied at each checkpoint (Simulated). */
  policy_shift_pct: number[];
}

/** Full §7.2 payload: World A fitted & forecast first, then the policy alters it. */
export interface TimeSeriesForecast {
  provenance: MetricTag;
  policy_id: string;
  note: string;
  checkpoints: Checkpoint[];
  metrics: MetricForecast[];
  assumptions: Record<string, number | string | boolean>;
  not_modelled: string[];
}

/**
 * Structural time-series forecast for a compiled policy (SPEC §7.2): World A is
 * fitted first (local-linear-trend + seasonal + AR(1)) over a seeded synthetic
 * history anchored to the ABM baseline, then the deterministic ABM policy Δ(B−A)
 * alters that trajectory to give World B. Synthetic history is Simulated, the
 * statistical baseline Estimated, the policy shift Simulated — no LLM on the
 * numeric path (SPEC §7.2/§8/§34). Throws on network/HTTP error.
 */
export async function runTimeseries(
  policy: PolicyDSL,
  signal?: AbortSignal,
): Promise<TimeSeriesForecast> {
  const res = await fetch(`${API_BASE_URL}/timeseries`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ policy }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const errBody = (await res.json()) as { detail?: unknown };
      if (typeof errBody.detail === "string") detail = errBody.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as TimeSeriesForecast;
}

// ---------------------------------------------------------------------------
// Data Fabric (SPEC §4) — GET /data-fabric
// ---------------------------------------------------------------------------

/** One measured/derived variable inside a dataset (SPEC §4 `variables`). */
export interface VariableCard {
  name: string;
  dtype: string;
  unit: string;
  description: string;
  /** Share of records where this field is absent/null (0–100). */
  missing_pct: number;
}

/** One entry in a dataset's `transformation_history` (SPEC §4). */
export interface TransformationStep {
  step: string;
  by: string;
  tag: MetricTag;
}

/** The full SPEC §4 dataset provenance record, built live from the file. */
export interface DatasetCard {
  id: string;
  title: string;
  publisher: string;
  source_url: string;
  /** ISO retrieval time; null for deterministically generated data. */
  retrieved_at: string | null;
  geographic_scope: string;
  spatial_resolution: string;
  time_start: string | null;
  time_end: string | null;
  frequency: string;
  units: string;
  variables: VariableCard[];
  license: string;
  /** Overall share of missing cells across declared variables (0–100). */
  missingness: number;
  /** Content-addressed version: short sha256 of the actual file bytes. */
  revision: string;
  confidence: string;
  transformation_history: TransformationStep[];
  format: string;
  record_count: number;
  /** 'synthetic' | 'legacy' | 'live' | 'assumption-set'. */
  kind: string;
  tag: MetricTag;
  /** Real datasets this synthetic file is schema-compatible with (not sources). */
  real_world_analogues: string[];
}

/** One of SPEC §4's supported ingestion formats + its wiring status. */
export interface FormatSupport {
  format: string;
  /** 'native' | 'adapter-ready' | 'declared'. */
  status: string;
  note: string;
}

/** One SPEC §4 harmonisation pipeline stage + whether it actually runs. */
export interface HarmonisationStep {
  step: string;
  implemented: boolean;
  where: string;
  note: string;
}

/** Full `GET /data-fabric` payload — the dataset ingestion & provenance layer (SPEC §4). */
export interface DataFabric {
  /** The fabric describes the data on disk, so it is Observed about itself. */
  provenance: MetricTag;
  note: string;
  app_version: string;
  generated_from: string;
  lineage_contract: string;
  datasets: DatasetCard[];
  format_support: FormatSupport[];
  harmonisation: HarmonisationStep[];
  counts: Record<string, number>;
}

/**
 * Fetch the Data Fabric manifest via `GET /data-fabric` (SPEC §4): the catalogue
 * of every dataset the engine reads, each carrying the full §4 provenance record
 * (record counts, variable lists, missingness and a content-hash revision all
 * computed live on disk), plus the supported-format contract and the
 * harmonisation-pipeline lineage. It is the dataset-level answer to "where did
 * every number ultimately come from?" — Observed about the data itself, no LLM.
 * Throws on network/HTTP error so the panel can show an honest waiting/error
 * state rather than inventing a catalogue (SPEC §4/§34).
 */
export async function getDataFabric(signal?: AbortSignal): Promise<DataFabric> {
  const res = await fetch(`${API_BASE_URL}/data-fabric`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as DataFabric;
}

// ---------------------------------------------------------------------------
// Scenario orchestrator — POST /run (SPEC §28/§29 — the killer demo)
// ---------------------------------------------------------------------------

/**
 * One beat of the §29 killer-demo storyline, pointing at a response section so a
 * judge can follow the narrative straight into the evidence.
 */
export interface NarrativeBeat {
  /** Approximate demo timecode, e.g. "0–10s". */
  timecode: string;
  /** What happens, e.g. "Compile policy". */
  stage: string;
  /** Which response field carries the evidence. */
  section: string;
  /** One-line narration grounded in this run. */
  description: string;
}

/**
 * A single composed-dashboard tile: the policy effect on one metric at the
 * chosen horizon. Numbers are Simulated — read verbatim from the same
 * deterministic simulation the standalone `/simulate` endpoint returns.
 */
export interface RunHeadlineMetric {
  key: string;
  label: string;
  unit: string;
  world_a: number;
  world_b: number;
  delta: number;
  delta_pct: number | null;
  /** "down" / "up" / "flat" vs baseline (sign only, not good/bad). */
  direction: string;
  /** [low, high] Δ uncertainty band at the horizon. */
  band: number[];
  tag: MetricTag;
}

/** The parliament's amendment (auto-derived or caller-supplied) + its effect. */
export interface RunProposedAmendment {
  proposed: boolean;
  /** "caller", "auto:equity", "auto:reinvestment", or "none". */
  source: string;
  rationale: string;
  amendment: Amendment | null;
  /** Δ(amended − original) across checkpoints (SPEC §12/§21). */
  comparison: AmendmentComparison | null;
}

/**
 * The full §29 demo narrative in one mutually-consistent payload. Every numeric
 * section reuses an existing deterministic layer reading the *same* compiled
 * policy and the *same* simulation, so the dashboard, parliament, amendment and
 * media can never disagree. Numbers Simulated; debate/media prose Generated; no
 * LLM touches any figure (SPEC §34).
 */
export interface RunResponse {
  provenance: string;
  note: string;
  policy_id: string;
  horizon_months: number;
  horizon_label: string;
  /** Compiler output when natural-language `text` was supplied (SPEC §3). */
  compiled: CompileResponse | null;
  narrative: NarrativeBeat[];
  headline: RunHeadlineMetric[];
  /** Overall net public support (support − oppose), in [-1, 1], from /public. */
  net_support: number;
  simulation: SimulateResponse;
  public: PublicOpinion;
  parliament: DebateResponse;
  amendment: RunProposedAmendment;
  media: MediaResponse;
}

/** Input to `POST /run`: supply *either* `policy` (compiled) or `text` (to compile). */
export interface RunRequest {
  text?: string;
  policy?: PolicyDSL;
  jurisdiction?: string;
  /** Horizon the headline dashboard reports (nearest checkpoint). Defaults to Year 2. */
  horizon_months?: number;
  amendment?: Amendment;
  seed?: number;
}

/**
 * Run the whole §29 killer-demo pipeline in a single call (`POST /run`): compile
 * → simulate → public reaction → parliament → amendment re-simulation → media,
 * returned as one mutually-consistent payload. Introduces no new numeric model —
 * every section reads the same compiled policy and the same simulation. Throws on
 * network/HTTP error so the panel can show an honest waiting/error state instead
 * of inventing a narrative (SPEC §28/§29/§34).
 */
export async function runScenario(
  req: RunRequest,
  signal?: AbortSignal,
): Promise<RunResponse> {
  const res = await fetch(`${API_BASE_URL}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as RunResponse;
}

/**
 * Orchestrate the canonical §28 demo congestion charge end-to-end
 * (`GET /run/example`). A body-less GET so a judge can pull the whole §29
 * killer-demo narrative with no compiled policy in the store — the same
 * deterministic pipeline `POST /run` composes, run on the demo policy.
 * Introduces no new number and throws on network/HTTP error so the panel shows
 * an honest waiting/error state instead of inventing a narrative
 * (SPEC §28/§29/§34).
 */
export async function getRunExample(
  signal?: AbortSignal,
): Promise<RunResponse> {
  const res = await fetch(`${API_BASE_URL}/run/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as RunResponse;
}

// ---------------------------------------------------------------------------
// Change-assumptions-and-rerun (SPEC §34.10) — GET /assumptions,
// POST /assumptions/rerun
// ---------------------------------------------------------------------------

/**
 * One overridable model assumption a user can pin and re-run. These are the
 * *same* knobs the §24 uncertainty engine sweeps (single source of truth), read
 * live from the running dataclasses so the published range can't drift from the
 * code. Input assumptions are Estimated — never observed data (SPEC §34).
 */
export interface AssumptionCard {
  /** Stable override key — send this in `overrides`. */
  name: string;
  /** Human-readable name (matches the §24 sensitivity list). */
  label: string;
  /** Which model the field lives on: `"base"` or `"sim"`. */
  target: string;
  /** Dataclass field the override sets. */
  field: string;
  /** Unit of the value where meaningful. */
  unit: string;
  /** Live default read from the running dataclass. */
  default: number;
  /** Lower edge of the documented plausible range. */
  low: number;
  /** Upper edge of the documented plausible range. */
  high: number;
  /** Always `"Estimated"` — these are input assumptions, not observed data. */
  provenance: string;
}

/** The catalogue returned by `GET /assumptions`. */
export interface AssumptionCatalogue {
  note: string;
  count: number;
  assumptions: AssumptionCard[];
}

/** One override, echoed with what the backend actually applied (clamped). */
export interface AppliedOverride {
  name: string;
  label: string;
  unit: string;
  default: number;
  low: number;
  high: number;
  /** The value the caller asked for. */
  requested: number;
  /** The value actually used (clamped into [low, high]). */
  applied: number;
  /** Whether `requested` was within the plausible range. */
  in_range: boolean;
  /** True when `applied` differs from `requested` (was clamped). */
  clamped: boolean;
  note: string;
}

/** How overriding the assumptions moved one metric's Δ(B−A) at the horizon. */
export interface MetricContrast {
  key: string;
  label: string;
  unit: string;
  /** Δ(B−A) under default assumptions. */
  default_delta: number;
  /** Δ(B−A) under the overridden assumptions. */
  overridden_delta: number;
  /** `overridden_delta − default_delta` — the effect of the change. */
  shift: number;
  /** `shift` as % of |default_delta| (null when the default is ~0). */
  shift_pct_of_default: number | null;
}

/**
 * World A/B/Δ re-run under user-pinned assumptions, contrasted vs the defaults
 * (`POST /assumptions/rerun`). The `delta` is the full replot-ready Δ(B−A)
 * trajectory under the overridden assumptions. Deterministic, no LLM on the
 * numeric path — the re-run is the exact pipeline `/simulate` uses (SPEC §34).
 */
export interface AssumptionRerunResult {
  provenance: MetricTag;
  note: string;
  policy_id: string;
  horizon: Checkpoint;
  overrides: AppliedOverride[];
  contrast: MetricContrast[];
  world_a_snapshot: Record<string, unknown>;
  world_b_snapshot: Record<string, unknown>;
  delta: DeltaTimeSeries;
  shocks_applied: Record<string, unknown>;
}

/**
 * Raised when an override names an assumption not in the catalogue (HTTP 404).
 * Carries the backend's list of overridable names so the UI can steer the user
 * back to a valid knob instead of guessing (SPEC §34).
 */
export class UnknownAssumptionError extends Error {
  overridable: string[];
  constructor(message: string, overridable: string[]) {
    super(message);
    this.name = "UnknownAssumptionError";
    this.overridable = overridable;
  }
}

/**
 * The catalogue of overridable model assumptions (`GET /assumptions`). Live from
 * the code, so the ranges never drift from what actually runs. Throws on
 * network/HTTP error so the panel can show an honest waiting state (SPEC §34).
 */
export async function getAssumptions(
  signal?: AbortSignal,
): Promise<AssumptionCatalogue> {
  const res = await fetch(`${API_BASE_URL}/assumptions`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as AssumptionCatalogue;
}

/**
 * Re-run the deterministic A/B/Δ core with one or more assumptions pinned to a
 * chosen value (`POST /assumptions/rerun`, SPEC §34.10). Returns a per-metric
 * contrast against the default-assumption run so the user sees exactly how much
 * their change moved the headline. No new numeric model, no LLM (SPEC §34).
 * Out-of-range values are clamped by the backend and flagged; unknown names
 * throw `UnknownAssumptionError` (with the valid names).
 */
export async function rerunAssumptions(
  policy: PolicyDSL,
  overrides: Record<string, number>,
  horizonMonths?: number,
  signal?: AbortSignal,
): Promise<AssumptionRerunResult> {
  const res = await fetch(`${API_BASE_URL}/assumptions/rerun`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      policy,
      overrides,
      ...(horizonMonths != null ? { horizon_months: horizonMonths } : {}),
    }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    if (res.status === 404) {
      try {
        const body = (await res.json()) as {
          detail?: { error?: string; overridable_assumptions?: string[] };
        };
        const d = body.detail;
        if (d && Array.isArray(d.overridable_assumptions)) {
          throw new UnknownAssumptionError(
            d.error ?? "Unknown assumption",
            d.overridable_assumptions,
          );
        }
      } catch (e) {
        if (e instanceof UnknownAssumptionError) throw e;
        // fall through to the generic error below
      }
    }
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as AssumptionRerunResult;
}

// ---------------------------------------------------------------------------
// Baseline World Model — GET /world (SPEC §5 / §28.2)
//
// World A's structural composition: the browsable digital twin the demo renders
// (§28.2 "roads, transit, population cohorts, businesses"), organised as the six
// SPEC §5 layers. Not a forecast — pure counts / distributions / baseline-ABM
// aggregates. No LLM produces any number (SPEC §34); gaps are surfaced in each
// layer's `not_modelled` list rather than fabricated.
// ---------------------------------------------------------------------------

/** A named categorical breakdown (label → count) with matching percentages. */
export interface WorldDistribution {
  counts: Record<string, number>;
  pct: Record<string, number>;
}

/** SPEC §5 Population layer — who lives and commutes in World A. */
export interface WorldPopulationLayer {
  provenance: MetricTag;
  total_agents: number;
  commuters: number;
  cbd_commuters: number;
  age_years: Record<string, number>; // min / max / mean
  age_bands: WorldDistribution;
  household_size: WorldDistribution;
  income_monthly: Record<string, number>; // min / median / mean
  income_bands: WorldDistribution;
  income_deciles: number[];
  occupations: WorldDistribution;
  mobility: Record<string, number>; // car_access_pct / transit_access_pct / both_pct
  commute: Record<string, number>; // mean_distance_km / cbd_commuter_pct
  behavioural_priors: Record<string, number>;
  not_modelled: string[];
}

/** SPEC §5 Economy layer — sectors, jobs and wages in World A. */
export interface WorldEconomyLayer {
  provenance: MetricTag;
  total_jobs_city: number;
  cbd_jobs: number;
  cbd_job_share_pct: number;
  sectors: WorldDistribution;
  wages_monthly_by_band: Record<string, number>;
  note: string;
  not_modelled: string[];
}

/** SPEC §5 Geography layer — the physical city (§28.2 render targets). */
export interface WorldGeographyLayer {
  provenance: MetricTag;
  zones: number;
  cbd_zones: number;
  land_use: WorldDistribution;
  roads: Record<string, number>;
  road_classes: WorldDistribution;
  buildings: Record<string, number>;
  building_types: WorldDistribution;
  business_locations: Record<string, number>;
  transit: Record<string, number>;
  not_modelled: string[];
}

/** SPEC §5 Environment layer — baseline emissions & land/water state. */
export interface WorldEnvironmentLayer {
  provenance: MetricTag;
  commuter_co2: Record<string, number>; // daily_tonnes / annual_tonnes / kg_per_km
  land_use: WorldDistribution;
  green_space_zones: number;
  water_present: boolean;
  not_modelled: string[];
}

/** SPEC §5 Institutions layer — the governance agents that are *modelled*. */
export interface WorldInstitutionsLayer {
  provenance: MetricTag;
  note: string;
  parliament_agents: string[];
  institutional_agents: string[];
  not_modelled: string[];
}

/** One modelled society actor with its documented opinion prior. */
export interface WorldSocietyActor {
  id: string;
  kind: string;
  label: string;
  prior: number; // opinion prior in [-1, 1] (Estimated)
  rationale: string;
}

/** SPEC §5 Society layer — opinion, media and civic actors (as modelled). */
export interface WorldSocietyLayer {
  provenance: MetricTag;
  note: string;
  opinion_priors_by_income_band: Record<string, number>;
  media_environment: string[];
  civic_actors: WorldSocietyActor[];
  not_modelled: string[];
}

/** The composed Baseline World Model (SPEC §5 / §28.2). */
export interface WorldModel {
  world: string; // 'A' = baseline, no intervention
  provenance: MetricTag;
  note: string;
  layer_selection: string;
  layers_returned: string[];
  population?: WorldPopulationLayer | null;
  economy?: WorldEconomyLayer | null;
  geography?: WorldGeographyLayer | null;
  environment?: WorldEnvironmentLayer | null;
  institutions?: WorldInstitutionsLayer | null;
  society?: WorldSocietyLayer | null;
}

/**
 * Fetch the composed Baseline World Model (World A) across all six SPEC §5
 * layers. Policy-independent and deterministic — it describes the synthetic
 * city as it is, not a forecast. Throws on network/HTTP error.
 */
export async function getWorld(signal?: AbortSignal): Promise<WorldModel> {
  const res = await fetch(`${API_BASE_URL}/world`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as WorldModel;
}

// ---------------------------------------------------------------------------
// North-Star answer (SPEC §37) — POST /north-star
// ---------------------------------------------------------------------------
//
// The minister's "What happens if we implement this?" answered as the fixed §37
// narrative: baseline → analogues → mechanisms → median outcome → uncertainty →
// winners → losers → failure modes → opposition's strongest argument → opinion
// evolution → media narratives → three risk-reducing amendments → each
// amendment's effect → the best-fit configuration → every assumption & piece of
// evidence. It computes NO new number — each section embeds the *same*
// deterministic layer output the standalone endpoints return, so the answer can
// never disagree with the tabs behind it. Numbers Simulated/Estimated; debate &
// media prose Generated; transparency artifacts Observed; no LLM touches a figure
// (SPEC §34).

/** One line of the fixed §37 answer: a synthesis read from the numbers + what backs it. */
export interface NorthStarSection {
  /** Position in the fixed §37 narrative (1..15). */
  order: number;
  /** The §37 line this section answers. */
  question: string;
  /** One-sentence synthesis read straight from the numbers (no LLM). */
  lead: string;
  /** Response field that carries the full evidence. */
  backs: string;
  /** Provenance of this section's substance. */
  tag: MetricTag;
}

/** A risk-reducing amendment (§37 line 12) + its re-simulated isolated effect (line 13). */
export interface NorthStarProposedAmendment {
  label: string;
  /** The risk this amendment is meant to reduce. */
  targets_risk: string;
  rationale: string;
  /** Δ(amended − original) from the same deterministic sim path (SPEC §12). */
  comparison: AmendmentComparison;
}

/**
 * The complete §37 minister's answer for a single policy. Every backing field is
 * the *same* object the standalone endpoint returns (so the answer can never
 * disagree with the deep tabs); `sections` is the ordered narrative over them.
 */
export interface NorthStarAnswer {
  provenance: string;
  note: string;
  policy_id: string;
  /** The minister's question this answers. */
  question: string;
  horizon_months: number;
  horizon_label: string;
  /** Present when the policy was compiled from NL text. */
  compiled: CompileResponse | null;
  sections: NorthStarSection[];
  // ---- Backing evidence (identical to the standalone endpoints) ----
  baseline: BaselineSnapshot;
  analogues: AnalogueEstimate;
  mechanisms: EventLedger;
  median_outcome: RunHeadlineMetric[];
  delta: DeltaTimeSeries;
  uncertainty: UncertaintyResult;
  winners: MicrosimReport;
  failure_modes: FailureModeRegister;
  opposition_argument: Argument | null;
  debate: DebateResponse;
  opinion_evolution: DiffusionResult;
  media: MediaResponse;
  amendments: NorthStarProposedAmendment[];
  best_configuration: OptimiserResult;
  /** §37.15 — every assumption + guardrail behind the conclusions. */
  evidence: Record<string, unknown>;
}

/** Input to `POST /north-star`: supply *either* `policy` (compiled) or `text` (to compile). */
export interface NorthStarRequest {
  text?: string;
  policy?: PolicyDSL;
  jurisdiction?: string;
  /** The minister's question (echoed; the §37 narrative is fixed). */
  question?: string;
  /** Headline horizon; snapped to the nearest checkpoint. Defaults to Year 2. */
  horizon_months?: number;
  /** Optimiser objective for §37.14, e.g. { reduce_transport_emissions_pct: 20 }. */
  objective?: Record<string, number>;
  /** Optimiser constraints for §37.14, e.g. { max_low_income_burden_increase_pct: 2 }. */
  constraints?: Record<string, number>;
  seed?: number;
}

/**
 * Compose the full SPEC §37 North-Star answer in one call (`POST /north-star`).
 * Introduces no new numeric model — every section reuses an existing
 * deterministic layer reading the same compiled policy and the same simulation.
 * Throws on network/HTTP error so the panel can show an honest waiting/error
 * state instead of inventing a narrative (SPEC §37/§34).
 */
export async function runNorthStar(
  req: NorthStarRequest,
  signal?: AbortSignal,
): Promise<NorthStarAnswer> {
  const res = await fetch(`${API_BASE_URL}/north-star`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as NorthStarAnswer;
}

/**
 * Compose the SPEC §37 North-Star answer for the canonical §28 demo congestion
 * charge (`GET /north-star/example`). A body-less GET so a judge can read the
 * whole fixed narrative with no compiled policy in the store — identical inputs
 * to `GET /brief/example`, which delegates to this layer. Introduces no new
 * number and throws on network/HTTP error so the panel shows an honest
 * waiting/error state instead of inventing a narrative (SPEC §37/§34).
 */
export async function getNorthStarExample(
  signal?: AbortSignal,
): Promise<NorthStarAnswer> {
  const res = await fetch(`${API_BASE_URL}/north-star/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as NorthStarAnswer;
}

// --------------------------------------------------------------------------- #
// Citizen View — follow a single household (SPEC §17 / §31)
// --------------------------------------------------------------------------- #

/** The static profile of one synthetic household (SPEC §17). */
export interface CitizenProfile {
  agent_id: string;
  age: number;
  household_size: number;
  income_monthly: number;
  income_annual: number;
  income_band: string;
  occupation: string;
  home_zone: string;
  home_in_central_district: boolean;
  work_zone: string;
  commutes_into_cbd: boolean;
  commute_distance_km: number;
  car_access: boolean;
  public_transit_access: boolean;
  provenance: string;
}

/** This citizen's experience at one Time-Machine checkpoint (SPEC §17). */
export interface CitizenSnapshot {
  label: string;
  t_months: number;
  mode: string;
  commute_minutes_one_way: number;
  commute_minutes_low: number;
  commute_minutes_high: number;
  monthly_transport_cost: number;
  monthly_transport_cost_low: number;
  monthly_transport_cost_high: number;
  charge_paid_monthly: number;
  policy_support: number;
  stance: string;
}

/** SPEC §31 core Agent-State record at one horizon `t`. */
export interface AgentState {
  agent_id: string;
  t: number;
  location: string;
  income: number;
  commute_minutes: number;
  monthly_transport_cost: number;
  policy_support: number;
  provenance: string;
}

/** Full Citizen View for one household under a policy (SPEC §17/§31). */
export interface CitizenView {
  policy_id: string;
  selector: string;
  profile: CitizenProfile;
  before_policy: CitizenSnapshot;
  trajectory: CitizenSnapshot[];
  agent_states: AgentState[];
  headline: string;
  explanation: string[];
  provenance: string;
  not_modelled: string[];
  params: Record<string, unknown>;
}

/** A lightweight, policy-independent household card for a UI picker (SPEC §17). */
export interface CitizenSample {
  agent_id: string;
  label: string;
  income_band: string;
  occupation: string;
  home_zone: string;
  commutes_into_cbd: boolean;
  baseline_mode: string;
  provenance: string;
}

/** The archetype selectors `POST /citizen` accepts when no `agent_id` is given. */
export const CITIZEN_SELECTORS = [
  "representative",
  "most_burdened",
  "biggest_loser",
  "biggest_winner",
  "median",
] as const;
export type CitizenSelector = (typeof CITIZEN_SELECTORS)[number];

/**
 * A diverse, policy-independent set of households for a "click a household"
 * picker (`GET /citizen/sample`, SPEC §17). Throws on network/HTTP error so the
 * panel can show an honest waiting/error state.
 */
export async function getCitizenSample(
  limit = 6,
  signal?: AbortSignal,
): Promise<CitizenSample[]> {
  const res = await fetch(`${API_BASE_URL}/citizen/sample?limit=${limit}`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as CitizenSample[];
}

/**
 * Follow one household through the Time Machine under a compiled policy
 * (`POST /citizen`, SPEC §17/§31). Either an explicit `agentId` or a `select`
 * archetype is used. Every number reuses the same deterministic mode-choice
 * model as `/simulate` and the per-agent opinion model as `/public` — no LLM on
 * the numeric path (SPEC §34). Throws on network/HTTP error so the panel can
 * show an honest waiting/error state.
 */
export async function runCitizen(
  policy: PolicyDSL,
  opts: { agentId?: string | null; select?: CitizenSelector } = {},
  signal?: AbortSignal,
): Promise<CitizenView> {
  const res = await fetch(`${API_BASE_URL}/citizen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      policy,
      ...(opts.agentId ? { agent_id: opts.agentId } : {}),
      select: opts.select ?? "representative",
    }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as CitizenView;
}

// --------------------------------------------------------------------------- #
// Business View — follow a single firm (SPEC §17 Business View)
// --------------------------------------------------------------------------- #

/** The static profile of one synthetic firm (SPEC §17). */
export interface FirmProfile {
  firm_id: string;
  sector: string;
  building_kind: string;
  zone_id: string;
  in_central_district: boolean;
  floors: number;
  floor_area_sqm: number;
  estimated_jobs: number;
  provenance: string;
}

/** This firm's operating picture at one Time-Machine checkpoint (SPEC §17). */
export interface FirmSnapshot {
  label: string;
  t_months: number;
  daily_footfall: number;
  daily_footfall_low: number;
  daily_footfall_high: number;
  labour_accessibility_index: number;
  daily_deliveries: number;
  annual_cost_added: number;
  annual_cost_added_low: number;
  annual_cost_added_high: number;
  revenue_proxy_annual: number;
  revenue_proxy_annual_low: number;
  revenue_proxy_annual_high: number;
  net_revenue_proxy_change_pct: number;
}

/** Full Business View for one firm under a policy (SPEC §17 Business View). */
export interface BusinessView {
  policy_id: string;
  selector: string;
  profile: FirmProfile;
  before_policy: FirmSnapshot;
  trajectory: FirmSnapshot[];
  adaptation_decisions: string[];
  headline: string;
  explanation: string[];
  provenance: string;
  not_modelled: string[];
  params: Record<string, unknown>;
}

/** A lightweight, policy-independent firm card for a UI picker (SPEC §17). */
export interface FirmSample {
  firm_id: string;
  label: string;
  sector: string;
  zone_id: string;
  in_central_district: boolean;
  estimated_jobs: number;
  provenance: string;
}

/** The archetype selectors `POST /business` accepts when no `firm_id` is given. */
export const BUSINESS_SELECTORS = [
  "representative",
  "most_exposed",
  "biggest_footfall_loss",
  "pedestrian_winner",
  "largest",
] as const;
export type BusinessSelector = (typeof BUSINESS_SELECTORS)[number];

/**
 * A diverse, policy-independent set of firms for a "click a firm" picker
 * (`GET /business/sample`, SPEC §17). Throws on network/HTTP error so the panel
 * can show an honest waiting/error state.
 */
export async function getBusinessSample(
  limit = 6,
  signal?: AbortSignal,
): Promise<FirmSample[]> {
  const res = await fetch(`${API_BASE_URL}/business/sample?limit=${limit}`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as FirmSample[];
}

/**
 * Follow one firm through the Time Machine under a compiled policy
 * (`POST /business`, SPEC §17 Business View). Either an explicit `firmId` or a
 * `select` archetype is used. Labour accessibility reuses the same deterministic
 * mode-choice model as `/simulate`; footfall / deliveries / cost / revenue reuse
 * the same economic coefficients as `/economy` — no LLM on the numeric path
 * (SPEC §34). Throws on network/HTTP error so the panel can show an honest
 * waiting/error state.
 */
export async function runBusiness(
  policy: PolicyDSL,
  opts: { firmId?: string | null; select?: BusinessSelector } = {},
  signal?: AbortSignal,
): Promise<BusinessView> {
  const res = await fetch(`${API_BASE_URL}/business`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      policy,
      ...(opts.firmId ? { firm_id: opts.firmId } : {}),
      select: opts.select ?? "representative",
    }),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as BusinessView;
}

// --------------------------------------------------------------------------- #
// Minister's Brief export (SPEC §27/§28.11/§37) — POST /brief
// --------------------------------------------------------------------------- #
//
// The brief is a *rendering* of the North-Star answer, not a model. It reuses the
// exact §37 request, then lays the composed answer out as a single, self-contained
// Markdown memo a minister could read or print — the one-page document behind the
// dashboard. It computes NO new number: every figure is the same object the
// standalone endpoints return, so the brief can never disagree with the tabs
// behind it (SPEC §34). Provenance tags travel with the text, generated media
// stays labelled SIMULATED, and a reproducibility footer closes the memo (§32).

/** One row of the provenance key printed at the top of the memo (SPEC §34). */
export interface TagLegendEntry {
  tag: string;
  meaning: string;
}

/**
 * Input to `POST /brief`: the same contract as `POST /north-star` plus two
 * presentation-only switches. Supply *either* `policy` (compiled) or `text`.
 */
export interface BriefRequest extends NorthStarRequest {
  /** Embed the full structured NorthStarAnswer alongside the Markdown. */
  include_answer?: boolean;
  /** Include the SIMULATED media-narratives section in the memo. */
  include_media?: boolean;
}

/** A rendered Minister's Brief: the Markdown memo + its structured backing. */
export interface BriefResponse {
  note: string;
  policy_id: string;
  title: string;
  question: string;
  horizon_months: number;
  horizon_label: string;
  /** The endpoint whose output this document renders (always `/north-star`). */
  generated_from: string;
  /** Provenance key printed at the top of the memo. */
  tag_legend: TagLegendEntry[];
  /** Length of the rendered Markdown, in words. */
  word_count: number;
  /** The self-contained Markdown memo. */
  markdown: string;
  /** Full structured North-Star answer (present when include_answer=true). */
  answer: NorthStarAnswer | null;
}

/**
 * Render the Minister's Brief for a single policy (`POST /brief`). Introduces no
 * new numeric model — the memo is a layout over the §37 North-Star answer, whose
 * every section reuses an existing deterministic layer. Throws on network/HTTP
 * error so the panel can show an honest waiting/error state instead of inventing
 * a memo (SPEC §37/§34).
 */
export async function runBrief(
  req: BriefRequest,
  signal?: AbortSignal,
): Promise<BriefResponse> {
  const res = await fetch(`${API_BASE_URL}/brief`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as BriefResponse;
}

/**
 * Render the canonical §28 demo congestion-charge brief (`GET /brief/example`).
 * A body-less GET so a judge can see the finished artifact with no compiled
 * policy in the store — the same deterministic North-Star answer, rendered for
 * the demo policy. Introduces no new number and throws on network/HTTP error so
 * the panel can show an honest waiting/error state instead of a minted memo
 * (SPEC §37/§34).
 */
export async function getBriefExample(
  signal?: AbortSignal,
): Promise<BriefResponse> {
  const res = await fetch(`${API_BASE_URL}/brief/example`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `Backend returned HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new Error(detail);
  }
  return (await res.json()) as BriefResponse;
}

// ---------------------------------------------------------------------------
// Capability manifest — the machine-readable "front door" (SPEC §27/§33/§34)
// GET /capabilities: every HTTP route mapped to its SPEC section, area, and
// provenance class, reconciled live against the running app so it cannot drift.
// ---------------------------------------------------------------------------

/** A self-describing entry for one HTTP route in the manifest. */
export interface EndpointCard {
  path: string;
  methods: string[];
  area: string;
  spec_sections: string[];
  summary: string;
  needs_body: boolean;
  /** Companion GET returning a canonical result with no body, if any. */
  keyless_example: string | null;
  produces_numbers: boolean;
  /** Provenance class of this route's numbers (null = prose/metadata only). */
  output_tag: MetricTag | null;
}

/** A functional area grouping several endpoints. */
export interface CapabilityGroup {
  area: string;
  spec_sections: string[];
  summary: string;
  endpoints: EndpointCard[];
}

/** The full self-describing catalogue of the engine's HTTP surface. */
export interface CapabilityManifest {
  provenance: MetricTag;
  note: string;
  app_version: string;
  generated_from: string;
  groups: CapabilityGroup[];
  keyless_examples: string[];
  /** Live routes with no catalogue card — MUST be empty. */
  undocumented_routes: string[];
  /** Catalogue cards for routes that no longer exist — MUST be empty. */
  phantom_cards: string[];
  counts: Record<string, number>;
}

/**
 * Fetch the capability manifest (SPEC §27/§33): every HTTP route the engine
 * serves, mapped to its SPEC section, functional area, provenance class and
 * keyless-example companion, reconciled live against the running app's routes
 * so it cannot drift. Observed about the service — no LLM, no simulation. Throws
 * on network/HTTP error so the panel shows an honest waiting/error state
 * instead of inventing a surface (SPEC §34).
 */
export async function getCapabilities(
  signal?: AbortSignal,
): Promise<CapabilityManifest> {
  const res = await fetch(`${API_BASE_URL}/capabilities`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as CapabilityManifest;
}

// ---------------------------------------------------------------------------
// Scenario presets — the discoverable menu of canonical demo policies
// (SPEC §3/§27/§28). GET /scenarios returns a curated library of ready-to-run
// policies; each card carries its natural-language prompt, the *real* compiler
// output (DSL + reviewable assumptions), and two ready-to-POST bodies. No
// numeric model runs here — the catalogue is Observed about itself and each
// card's `compiled.provenance` is Generated (structuring, not simulation).
// ---------------------------------------------------------------------------

/** One ready-to-run canonical policy scenario. */
export interface ScenarioCard {
  /** Stable key, e.g. `congestion_charge_cbd`. */
  id: string;
  title: string;
  summary: string;
  /**
   * Intervention family, derived live from the compiled DSL
   * (`road_pricing` / `pedestrianisation` / `low_emission_zone` /
   * `parking_levy` / `transit_investment` / `other`) so it can never drift
   * from the compiler.
   */
  family: string;
  spec_sections: string[];
  /** The natural-language policy prompt a user would type. */
  text: string;
  /** Optimiser objective for the composed-answer endpoints (may be empty). */
  objective: Record<string, unknown>;
  /** Optimiser constraints for the composed-answer endpoints (may be empty). */
  constraints: Record<string, unknown>;
  /** The real compiler output for `text` — provenance Generated (SPEC §34). */
  compiled: CompileResponse;
  /** Ready-to-POST body for `/simulate`: `{ policy: <compiled DSL> }`. */
  simulate_body: { policy: PolicyDSL };
  /** Ready-to-POST body for `/run`, `/north-star`, `/brief`. */
  answer_body: {
    text: string;
    objective: Record<string, unknown>;
    constraints: Record<string, unknown>;
  };
}

/** The full curated menu of canonical demo policies. */
export interface ScenarioLibrary {
  /** Observed — the catalogue lists curated inputs (SPEC §34). */
  provenance: MetricTag;
  note: string;
  count: number;
  /** Distinct intervention families represented, sorted. */
  families: string[];
  scenarios: ScenarioCard[];
}

/**
 * Fetch the scenario-presets catalogue (SPEC §3/§27/§28): the discoverable menu
 * of ready-to-run canonical policies. Throws on network/HTTP error so the panel
 * shows an honest waiting/error state rather than inventing a menu (SPEC §34).
 */
export async function getScenarios(
  signal?: AbortSignal,
): Promise<ScenarioLibrary> {
  const res = await fetch(`${API_BASE_URL}/scenarios`, {
    signal,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend returned HTTP ${res.status}`);
  }
  return (await res.json()) as ScenarioLibrary;
}

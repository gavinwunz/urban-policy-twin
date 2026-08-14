/**
 * Client for the machine-learning surface (`/ml/*`).
 *
 * Kept out of `lib/api.ts` deliberately — that file is the simulation engine's
 * contract, and this one is the model layer underneath it. They fail
 * independently: the ML endpoints return 503 until `python -m app.ml.train` has
 * run, and the dashboard has to say so rather than pretend.
 */

import { API_BASE_URL } from "./api";

export interface MlProvenance {
  trained_on: string;
  trained_on_full: string;
  source_url: string;
  applied_to: string;
  transfer_note: string;
  tag: string;
}

export interface ModelRow {
  name: string;
  r2: number;
  mae_mph: number;
  rmse_mph: number;
  mape_pct: number;
  fit_seconds: number;
  train_rows: number;
  best: boolean;
}

export interface HorizonRow {
  horizon_min: number;
  rmse: number;
  mae: number;
  r2: number;
}

export interface SequenceMetrics {
  model: string;
  overall: { rmse: number; mae: number; r2: number };
  by_horizon: HorizonRow[];
  training_history?: Array<{ epoch: number; train_loss: number; val_loss: number }>;
  architecture?: {
    type: string;
    hidden_size: number;
    layers: number;
    dropout: number;
    params: number;
  };
}

export interface Leaderboard {
  trained: boolean;
  horizon_minutes: number;
  target: string;
  models: ModelRow[];
  sequence: SequenceMetrics;
  dataset: {
    name: string;
    source: string;
    description: string;
    units: string;
    sensors: number;
    train_rows_sampled: number;
    test_rows_sampled: number;
    history_steps: number;
    horizon_steps: number;
    step_minutes: number;
    window_start: string;
    window_end: string;
  };
  features: string[];
  generated_at: string;
  provenance: MlProvenance;
  registry_source: string;
}

export interface CongestionClock {
  trained: boolean;
  hours: number[];
  days: string[];
  fitted: number[][];
  observed: Array<Array<number | null>>;
  speed_min: number;
  speed_max: number;
  provenance: MlProvenance;
}

export interface ForecastResult {
  trained: boolean;
  history: number[];
  forecast: Array<{ horizon_min: number; speed_mph: number; speed_kmh: number }>;
  cross_check: { model: string; horizon_min: number; speed_mph: number } | null;
  model: string;
  scenario?: string;
  provenance: MlProvenance;
}

export interface SensorRow {
  sensor_id: number;
  node_id: number;
  lat: number;
  lon: number;
  mean_speed_mph: number;
  std_speed_mph: number;
  p05_speed_mph: number;
  p95_speed_mph: number;
  observations: number;
  hourly_profile_mph: Array<number | null>;
}

export interface AnomalyProfile {
  trained: boolean;
  contamination: number;
  n_scored: number;
  n_anomalies: number;
  anomaly_rate: number;
  rate_by_hour: number[];
  provenance: MlProvenance;
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { signal });
  if (!res.ok) {
    // 503 is the "not trained yet" case and deserves a readable message.
    if (res.status === 503) {
      throw new Error(
        "Models not trained yet — run `python -m app.ml.train` in backend/",
      );
    }
    throw new Error(`${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const getLeaderboard = (s?: AbortSignal) =>
  get<Leaderboard>("/ml/models", s);

export const getCongestionClock = (s?: AbortSignal) =>
  get<CongestionClock>("/ml/congestion-clock", s);

export const getExampleForecast = (s?: AbortSignal) =>
  get<ForecastResult>("/ml/forecast/example", s);

export const getAnomalyProfile = (s?: AbortSignal) =>
  get<AnomalyProfile>("/ml/anomaly/profile", s);

export const getSensors = (s?: AbortSignal) =>
  get<{ count: number; source: string; sensors: SensorRow[]; provenance: MlProvenance }>(
    "/ml/sensors?limit=250",
    s,
  );

export async function postForecast(
  history: number[],
  hour: number,
  dow: number,
  signal?: AbortSignal,
): Promise<ForecastResult> {
  const res = await fetch(`${API_BASE_URL}/ml/forecast`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ history_mph: history, hour, day_of_week: dow }),
    signal,
  });
  if (!res.ok) throw new Error(`forecast failed: HTTP ${res.status}`);
  return (await res.json()) as ForecastResult;
}

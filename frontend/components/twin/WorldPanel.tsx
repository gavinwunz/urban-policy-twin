"use client";

/**
 * World tab (SPEC §5 / §28.2): the browsable Baseline World Model — World A's
 * structural composition, the digital twin the demo renders ("roads, transit,
 * population cohorts, businesses"). `GET /world` returns the six SPEC §5 layers
 * (Population, Economy, Geography, Environment, Institutions, Society), each a
 * bundle of counts / distributions / baseline-ABM aggregates.
 *
 * This tab is policy-independent (it describes the world *before* any
 * intervention) and loads on mount. It is **not a forecast**: every number is a
 * count read from the synthetic city dataset or the deterministic baseline model
 * — no LLM produces any figure (SPEC §34). The Auckland grid is a modelled zone system, so the
 * structural counts are tagged Simulated; the Institutions layer is an Observed
 * description of how governance agents are modelled and the Society layer's
 * opinion priors are Estimated assumptions — each layer carries its own
 * provenance chip. Gaps are surfaced in each layer's `not_modelled` list rather
 * than invented. If the backend is down we say so instead of minting a city.
 */

import { useEffect, useState } from "react";

import { getWorld } from "../../lib/api";
import type {
  WorldModel,
  WorldDistribution,
  WorldPopulationLayer,
  WorldEconomyLayer,
  WorldGeographyLayer,
  WorldEnvironmentLayer,
  WorldInstitutionsLayer,
  WorldSocietyLayer,
} from "../../lib/api";

type Status = "idle" | "loading" | "ready" | "error";

function fmt(n: number): string {
  if (!Number.isFinite(n)) return "—";
  if (Number.isInteger(n)) return n.toLocaleString();
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

/** A metric provenance chip (`.tag.observed/.estimated/.simulated/.generated`). */
function Tag({ p }: { p: string }) {
  return <span className={`tag ${p.toLowerCase()}`}>{p}</span>;
}

/** One label → value stat. */
function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="world-stat">
      <span className="world-stat-val">{value}</span>
      <span className="world-stat-label">{label}</span>
      {sub && <span className="world-stat-sub">{sub}</span>}
    </div>
  );
}

/** A named categorical distribution as horizontal share bars (largest first). */
function DistBars({
  dist,
  title,
  keepOrder,
}: {
  dist: WorldDistribution;
  title: string;
  keepOrder?: boolean;
}) {
  const entries = Object.keys(dist.counts).map((k) => ({
    key: k,
    count: dist.counts[k] ?? 0,
    pct: dist.pct[k] ?? 0,
  }));
  if (!keepOrder) entries.sort((a, b) => b.count - a.count);
  const max = entries.reduce((m, e) => Math.max(m, e.pct), 0) || 1;
  return (
    <div className="world-dist">
      <span className="world-dist-title">{title}</span>
      <div className="world-dist-rows">
        {entries.map((e) => (
          <div className="world-dist-row" key={e.key}>
            <span className="world-dist-key" title={e.key}>
              {e.key.replace(/_/g, " ")}
            </span>
            <span className="world-dist-track" aria-hidden>
              <span
                className="world-dist-fill"
                style={{ width: `${Math.max(2, (e.pct / max) * 100)}%` }}
              />
            </span>
            <span className="world-dist-pct">{e.pct.toFixed(1)}%</span>
            <span className="world-dist-count">{e.count.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Collapsible honest "what we don't model" list for a layer. */
function NotModelled({ items }: { items: string[] }) {
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  return (
    <div className={`world-nm${open ? " open" : ""}`}>
      <button
        type="button"
        className="world-nm-head"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span> not modelled · {items.length}
      </button>
      {open && (
        <ul className="world-nm-list">
          {items.map((it, i) => (
            <li key={i}>{it}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A layer card shell: title, provenance chip, optional note, body, gaps. */
function LayerCard({
  name,
  provenance,
  note,
  children,
  notModelled,
}: {
  name: string;
  provenance: string;
  note?: string;
  children: React.ReactNode;
  notModelled: string[];
}) {
  return (
    <section className="world-layer">
      <header className="world-layer-head">
        <h3>{name}</h3>
        <Tag p={provenance} />
      </header>
      {note && <p className="world-layer-note">{note}</p>}
      {children}
      <NotModelled items={notModelled} />
    </section>
  );
}

function PopulationCard({ p }: { p: WorldPopulationLayer }) {
  return (
    <LayerCard name="Population" provenance={p.provenance} notModelled={p.not_modelled}>
      <div className="world-stats">
        <Stat label="commuter agents" value={fmt(p.total_agents)} />
        <Stat
          label="commute into CBD"
          value={fmt(p.cbd_commuters)}
          sub={`${(p.commute.cbd_commuter_pct ?? 0).toFixed(1)}% of agents`}
        />
        <Stat
          label="median income /mo"
          value={fmt(p.income_monthly.median ?? 0)}
          sub={`mean ${fmt(p.income_monthly.mean ?? 0)}`}
        />
        <Stat
          label="mean age"
          value={`${(p.age_years.mean ?? 0).toFixed(1)}y`}
          sub={`${fmt(p.age_years.min ?? 0)}–${fmt(p.age_years.max ?? 0)}`}
        />
        <Stat label="car access" value={`${(p.mobility.car_access_pct ?? 0).toFixed(1)}%`} />
        <Stat
          label="transit access"
          value={`${(p.mobility.transit_access_pct ?? 0).toFixed(1)}%`}
          sub={`${(p.mobility.both_pct ?? 0).toFixed(1)}% both`}
        />
        <Stat
          label="mean commute"
          value={`${(p.commute.mean_distance_km ?? 0).toFixed(2)} km`}
        />
      </div>
      <div className="world-dist-grid">
        <DistBars dist={p.income_bands} title="Income bands" keepOrder />
        <DistBars dist={p.age_bands} title="Age bands" keepOrder />
        <DistBars dist={p.household_size} title="Household size" keepOrder />
        <DistBars dist={p.occupations} title="Occupations" />
      </div>
      <div className="world-priors">
        <span className="world-priors-label">
          Behavioural priors <Tag p="Estimated" /> (population mean)
        </span>
        <div className="world-priors-row">
          {Object.entries(p.behavioural_priors).map(([k, v]) => (
            <span key={k} className="world-prior">
              <b>{v.toFixed(3)}</b> {k.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      </div>
    </LayerCard>
  );
}

function EconomyCard({ e }: { e: WorldEconomyLayer }) {
  return (
    <LayerCard
      name="Economy"
      provenance={e.provenance}
      note={e.note}
      notModelled={e.not_modelled}
    >
      <div className="world-stats">
        <Stat label="jobs (city)" value={fmt(e.total_jobs_city)} />
        <Stat
          label="CBD jobs"
          value={fmt(e.cbd_jobs)}
          sub={`${e.cbd_job_share_pct.toFixed(1)}% of jobs`}
        />
      </div>
      <div className="world-dist-grid">
        <DistBars dist={e.sectors} title="Employment by sector" />
        <div className="world-wages">
          <span className="world-dist-title">Mean wage by income band /mo</span>
          <div className="world-dist-rows">
            {Object.entries(e.wages_monthly_by_band).map(([band, wage]) => (
              <div className="world-dist-row" key={band}>
                <span className="world-dist-key">{band}</span>
                <span className="world-dist-track" aria-hidden>
                  <span
                    className="world-dist-fill"
                    style={{
                      width: `${
                        (wage /
                          Math.max(1, ...Object.values(e.wages_monthly_by_band))) *
                        100
                      }%`,
                    }}
                  />
                </span>
                <span className="world-dist-pct">{fmt(wage)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </LayerCard>
  );
}

function GeographyCard({ g }: { g: WorldGeographyLayer }) {
  return (
    <LayerCard name="Geography" provenance={g.provenance} notModelled={g.not_modelled}>
      <div className="world-stats">
        <Stat label="zones" value={fmt(g.zones)} sub={`${fmt(g.cbd_zones)} in CBD`} />
        <Stat
          label="road links"
          value={fmt(g.roads.links ?? 0)}
          sub={`${fmt(g.roads.total_km ?? 0)} km`}
        />
        <Stat
          label="cordon-crossing links"
          value={fmt(g.roads.cordon_crossing_links ?? 0)}
        />
        <Stat
          label="network capacity"
          value={`${fmt(g.roads.total_capacity_veh_per_hr ?? 0)}`}
          sub="veh/hr"
        />
        <Stat
          label="buildings"
          value={fmt(g.buildings.count ?? 0)}
          sub={`mean ${(g.buildings.mean_height_m ?? 0).toFixed(1)} m`}
        />
        <Stat
          label="commercial/mixed zones"
          value={fmt(g.business_locations.commercial_or_mixed_zones ?? 0)}
        />
        <Stat
          label="transit access"
          value={`${(g.transit.population_access_pct ?? 0).toFixed(1)}%`}
          sub="of population"
        />
      </div>
      <div className="world-dist-grid">
        <DistBars dist={g.land_use} title="Zone land use" />
        <DistBars dist={g.road_classes} title="Road classes" />
        <DistBars dist={g.building_types} title="Building types" />
      </div>
    </LayerCard>
  );
}

function EnvironmentCard({ e }: { e: WorldEnvironmentLayer }) {
  return (
    <LayerCard name="Environment" provenance={e.provenance} notModelled={e.not_modelled}>
      <div className="world-stats">
        <Stat
          label="commuter CO₂ /day"
          value={`${fmt(e.commuter_co2.daily_tonnes ?? 0)} t`}
        />
        <Stat
          label="commuter CO₂ /yr"
          value={`${fmt(e.commuter_co2.annual_tonnes ?? 0)} t`}
        />
        <Stat
          label="CO₂ intensity"
          value={`${(e.commuter_co2.kg_per_km ?? 0).toFixed(3)}`}
          sub="kg/km"
        />
        <Stat label="green-space zones" value={fmt(e.green_space_zones)} />
        <Stat label="water/flood layer" value={e.water_present ? "present" : "absent"} />
      </div>
      <div className="world-dist-grid">
        <DistBars dist={e.land_use} title="Land use (incl. green space)" />
      </div>
    </LayerCard>
  );
}

function InstitutionsCard({ i }: { i: WorldInstitutionsLayer }) {
  return (
    <LayerCard
      name="Institutions"
      provenance={i.provenance}
      note={i.note}
      notModelled={i.not_modelled}
    >
      <div className="world-agents">
        <div className="world-agent-group">
          <span className="world-dist-title">Model Parliament (SPEC §11)</span>
          <div className="world-chips">
            {i.parliament_agents.map((a) => (
              <span key={a} className="world-chip">
                {a}
              </span>
            ))}
          </div>
        </div>
        <div className="world-agent-group">
          <span className="world-dist-title">
            Institutional reviewers (SPEC §18)
          </span>
          <div className="world-chips">
            {i.institutional_agents.map((a) => (
              <span key={a} className="world-chip">
                {a}
              </span>
            ))}
          </div>
        </div>
      </div>
    </LayerCard>
  );
}

function SocietyCard({ s }: { s: WorldSocietyLayer }) {
  return (
    <LayerCard
      name="Society"
      provenance={s.provenance}
      note={s.note}
      notModelled={s.not_modelled}
    >
      <div className="world-dist-grid">
        <div className="world-priors-bands">
          <span className="world-dist-title">
            Opinion prior by income band <span className="world-hint">−1 … +1</span>
          </span>
          <div className="world-dist-rows">
            {Object.entries(s.opinion_priors_by_income_band).map(([band, prior]) => (
              <div className="world-prior-row" key={band}>
                <span className="world-dist-key">{band}</span>
                <span className="world-prior-track" aria-hidden>
                  <span className="world-prior-axis" />
                  <span
                    className={`world-prior-mark ${prior >= 0 ? "pos" : "neg"}`}
                    style={{ left: `${((prior + 1) / 2) * 100}%` }}
                  />
                </span>
                <span className={`world-prior-val ${prior >= 0 ? "pos" : "neg"}`}>
                  {prior >= 0 ? "+" : ""}
                  {prior.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="world-agent-group">
          <span className="world-dist-title">Media environment (SPEC §15)</span>
          <div className="world-chips">
            {s.media_environment.map((m) => (
              <span key={m} className="world-chip">
                {m}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="world-actors">
        <span className="world-dist-title">Civic actors (SPEC §14)</span>
        <div className="world-actor-rows">
          {s.civic_actors.map((a) => (
            <div className="world-actor" key={a.id}>
              <div className="world-actor-top">
                <span className="world-actor-label">{a.label}</span>
                <span className="world-actor-kind">{a.kind.replace(/_/g, " ")}</span>
                <span className={`world-actor-prior ${a.prior >= 0 ? "pos" : "neg"}`}>
                  {a.prior >= 0 ? "+" : ""}
                  {a.prior.toFixed(2)}
                </span>
              </div>
              <p className="world-actor-rationale">{a.rationale}</p>
            </div>
          ))}
        </div>
      </div>
    </LayerCard>
  );
}

export default function WorldPanel() {
  const [world, setWorld] = useState<WorldModel | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);

  function load(signal?: AbortSignal) {
    setStatus("loading");
    setError(null);
    getWorld(signal)
      .then((w) => {
        setWorld(w);
        setStatus("ready");
      })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        setError(e instanceof Error ? e.message : "World model unavailable");
        setStatus("error");
      });
  }

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, []);

  return (
    <section className="card world">
      <div className="dashboard-head">
        <h2>World A · baseline digital twin</h2>
        <span className="dashboard-sub">
          The browsable six-layer world before any policy (SPEC §5 / §28.2)
        </span>
      </div>

      {status === "loading" && !world && (
        <p className="hint">Composing the World-A model from the backend…</p>
      )}

      {status === "error" && (
        <div className="waiting">
          <span className="tag muted">Backend unavailable</span>
          <p>
            Couldn&rsquo;t load the World Model: {error}. Nothing here is invented —
            reconnect the backend to read the live composition (every count is read
            from the synthetic city dataset or the baseline model, no LLM).
          </p>
          <button type="button" className="btn" onClick={() => load()}>
            Retry
          </button>
        </div>
      )}

      {world && (
        <div className="world-body">
          <div className="world-topline">
            <span className="world-worldchip">World {world.world}</span>
            <Tag p={world.provenance} />
            <span className="world-layers">
              {world.layers_returned.length} layers
            </span>
          </div>
          <p className="hint world-note">{world.note}</p>
          <details className="world-selection">
            <summary>How the layer set is chosen (SPEC §5)</summary>
            <p>{world.layer_selection}</p>
          </details>

          <div className="world-layers-grid">
            {world.population && <PopulationCard p={world.population} />}
            {world.economy && <EconomyCard e={world.economy} />}
            {world.geography && <GeographyCard g={world.geography} />}
            {world.environment && <EnvironmentCard e={world.environment} />}
            {world.institutions && <InstitutionsCard i={world.institutions} />}
            {world.society && <SocietyCard s={world.society} />}
          </div>

          <p className="world-foot">
            Structural snapshot, not a forecast — counts read from the synthetic
            Auckland dataset and the deterministic baseline model; no LLM produced
            any number (SPEC §34). Policy effects live in the Run, Compare and
            per-domain tabs.
          </p>
        </div>
      )}
    </section>
  );
}

/**
 * Guided-demo plumbing (SPEC §29, the 60-second flow).
 *
 * The lower deck lives behind an ARIA tab bar (PanelTabs), so a step that
 * targets an analysis panel first asks PanelTabs to switch to it (`tab`),
 * then spotlights the shared `[data-tour="tabs"]` anchor. Steps carry only
 * *guidance* prose — the tour never renders or invents a metric, it just
 * walks a judge through the real UI.
 */

/** Analysis-tab keys the tour (or a feature card) can request — mirrors PanelTabs' TabKey. */
export type DemoTab =
  | "northstar"
  | "brief"
  | "run"
  | "world"
  | "citizen"
  | "business"
  | "parliament"
  | "public"
  | "press"
  | "presser"
  | "redteam"
  | "compare"
  | "grand"
  | "sdg"
  | "diffusion"
  | "ensemble"
  | "uncertainty"
  | "sensitivity"
  | "optimiser"
  | "economy"
  | "dynamics"
  | "microsim"
  | "spatial"
  | "stress"
  | "robustness"
  | "analogue"
  | "timeseries"
  | "institutions"
  | "backtest"
  | "registry"
  | "reproduce"
  | "datafabric"
  | "assumptions";

type TabListener = (tab: DemoTab) => void;

const tabListeners = new Set<TabListener>();

/** Subscribe to demo tab-switch requests; returns an unsubscribe fn. */
export function subscribeDemoTab(fn: TabListener): () => void {
  tabListeners.add(fn);
  return () => tabListeners.delete(fn);
}

/** Ask any mounted PanelTabs to switch to `tab`. No-op if none is listening. */
export function requestDemoTab(tab: DemoTab): void {
  tabListeners.forEach((fn) => fn(tab));
}

type VoidListener = () => void;

const openAdvancedListeners = new Set<VoidListener>();

/** Subscribe to "open the full twin" requests; returns an unsubscribe fn. */
export function subscribeOpenAdvanced(fn: VoidListener): () => void {
  openAdvancedListeners.add(fn);
  return () => openAdvancedListeners.delete(fn);
}

/** Ask the Advanced disclosure to expand. No-op if none is listening. */
export function requestOpenAdvanced(): void {
  openAdvancedListeners.forEach((fn) => fn());
}

export interface TourStep {
  /** CSS selector of the element to spotlight. */
  selector: string;
  /** Analysis tab to switch to before spotlighting, if any. */
  tab?: DemoTab;
  title: string;
  body: string;
}

/**
 * The demo narrative. Mirrors SPEC §29: draft → compile → simulate two worlds →
 * scrub time → read tagged outcomes → adversarial debate → red-team → the whole
 * pipeline composed in one consistent call (§28/§29) → the transparency manifest
 * that answers "how do we know this isn't AI astrology" → the content-addressed
 * reproducibility receipt (§32) that lets a judge re-run to the identical digest →
 * and the §37 North-Star: every layer fused into the single ordered answer to the
 * one question that started it, "What happens if we implement this?".
 */
export const TOUR_STEPS: TourStep[] = [
  {
    selector: '[data-tour="compiler"]',
    title: "1 · Draft a policy in plain language",
    body:
      "Type a policy as prose. The compiler extracts a structured rulebook and " +
      "lists every assumption it made — each one editable, so nothing is buried " +
      "in a prompt. A demo policy is pre-loaded; hit “Compile policy”.",
  },
  {
    selector: '[data-tour="map"]',
    title: "2 · The city, in 3D",
    body:
      "Auckland is the world the policy acts on — zones, roads and the " +
      "CBD cordon. This is a world input, tagged Synthetic; it is not a result. " +
      "Toggle the Traffic / Transit / Support overlays to see the map light up.",
  },
  {
    selector: '[data-tour="timeline"]',
    title: "3 · Run the counterfactual, then scrub time",
    body:
      "Press “Run counterfactual” to simulate World B against the World-A " +
      "baseline, then drag the Time Machine from T0 out to 10 years. Everything " +
      "above updates to the checkpoint you land on.",
  },
  {
    selector: '[data-tour="outcomes"]',
    title: "4 · Read the outcomes — every number tagged",
    body:
      "Traffic, CO₂, transit, equity burden and support each show a value, the Δ " +
      "vs baseline and a visible uncertainty band that widens over time. Tags " +
      "(Observed / Estimated / Simulated / Generated) never let a guess read as " +
      "fact. Click any tile for its evidence trace.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "parliament",
    title: "5 · Send it to Parliament",
    body:
      "Five adversarial agents — Government, Opposition, Equity, Economist and a " +
      "Devil’s Advocate — debate the compiled policy with citations. Apply an " +
      "amendment and re-simulate: the map and outcomes above update from the " +
      "amended world. That round-trip is the whole point. Ask any of them a " +
      "direct follow-up question in \"Ask a persona\" below the debate.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "redteam",
    title: "6 · Red-team it",
    body:
      "The Devil’s Advocate’s Failure Mode Register lists how the policy could " +
      "backfire — displacement, evasion, equity shocks — ranked by severity, so " +
      "the weaknesses are on the table, not hidden.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "run",
    title: "7 · The whole pipeline in one call",
    body:
      "Run composes the entire demo — compile → simulate two worlds → public → " +
      "parliament → amendment re-simulation → press — into a single call, all " +
      "reading the same simulation. The outcomes dashboard, the debate tally, the " +
      "amendment Δ and the SIMULATED press snapshot can’t disagree, because there " +
      "is exactly one run behind them. Numbers Simulated, prose Generated, no LLM " +
      "on the numeric path.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "registry",
    title: "8 · “Is this AI astrology?” — the receipts",
    body:
      "The Registry is the transparency manifest: model cards, data sources, the " +
      "live assumption index and the SPEC §34 guardrail checklist with pass/fail. " +
      "LLMs structure language and write prose — they never generate the core " +
      "numbers. That is what makes the twin trustworthy.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "reproduce",
    title: "9 · Reproduce it — the content-addressed receipt",
    body:
      "Reproduce hands back the run’s manifest: a content-addressed run id, the " +
      "output digest, the pinned code, data and seeds behind it, and a " +
      "proven-reproducible badge the backend earns by running twice and diffing " +
      "the digests. Same inputs, same numbers, every time — determinism you can " +
      "check, not take on trust.",
  },
  {
    selector: '[data-tour="tabs"]',
    tab: "northstar",
    title: "10 · North-Star — the whole thing, as one answer",
    body:
      "This is where it all lands: a minister asks “What happens if we implement " +
      "this?” and North-Star answers with the fixed §37 narrative — baseline, " +
      "analogues, mechanisms, the median outcome, uncertainty, who wins, who " +
      "loses, where it fails, the opposition’s strongest argument, how opinion " +
      "shifts, the media, three risk-reducing amendments and their effects, the " +
      "best-fit configuration, and every assumption. Nothing new is computed — " +
      "each line embeds the same layer you just saw, so the answer can’t disagree " +
      "with the tabs behind it. One question, the whole answer.",
  },
];

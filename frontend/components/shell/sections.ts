/**
 * The section map: what used to be a 35-tab bar, grouped into six stages of one
 * continuous page.
 *
 * The old UI made every panel a click. That is wrong for an instrument someone
 * is meant to read top to bottom during a briefing — you cannot compare a
 * sensitivity sweep against the parliamentary reaction if only one of them can
 * be on screen. So every panel is mounted and visible; this file only decides
 * the order and the grouping, and the scroll-spy nav reads it to build itself.
 *
 * Grouping rule: a section answers one question a minister would actually ask.
 * Each carries a category label so the rail can be scanned by kind rather than
 * only by order.
 */

export interface SectionDef {
  /** Anchor id — also the scroll-spy target. */
  id: string;
  /** Nav label. Short: this sits in a narrow rail. */
  label: string;
  /** Kind of work this section does — shown as a grouping in the rail. */
  category: "Input" | "Projection" | "Evidence" | "Politics" | "Assurance";
  /** The question this section answers, shown under the section heading. */
  question: string;
  /** Longer framing for the section header. */
  blurb: string;
}

export const SECTIONS: SectionDef[] = [
  {
    id: "run",
    label: "Run",
    category: "Input",
    question: "How does it actually work?",
    blurb:
      "State a policy and watch the whole pipeline execute — datasets fetched, " +
      "models loaded, prediction generated, simulation run, House divided, " +
      "press filed. Every stage is a real call with measured timings.",
  },
  {
    id: "simulation",
    label: "Simulation",
    category: "Projection",
    question: "What does this policy do to the city?",
    blurb:
      "The projection over real Auckland geometry: traffic, emissions, mode " +
      "split and public realm across a ten-year horizon.",
  },
  {
    id: "model",
    label: "Model & data",
    category: "Evidence",
    question: "Why should anyone believe the numbers?",
    blurb:
      "The machine-learning layer underneath the projection — the corpus it " +
      "was fitted on, how it scores against held-out data, and where it fails.",
  },
  {
    id: "parliament",
    label: "Parliament",
    category: "Politics",
    question: "Does it survive the House?",
    blurb:
      "A division over the real 2023 New Zealand Parliament, the argument that " +
      "produced it, and eighteen years of election results underneath.",
  },
  {
    id: "reactions",
    label: "Public & press",
    category: "Politics",
    question: "Who fights this, and with what argument?",
    blurb:
      "The public, business and the newsroom react — plus a referendum, and a " +
      "red team hunting for the failure nobody costed.",
  },
  {
    id: "stress",
    label: "Stress test",
    category: "Assurance",
    question: "Where does it break?",
    blurb:
      "Alternatives ranked head to head, then the policy pushed until it " +
      "fails: sensitivity sweeps, uncertainty bands, shocks and robustness.",
  },
  {
    id: "evidence",
    label: "Audit",
    category: "Assurance",
    question: "Can this be audited?",
    blurb:
      "Every assumption, every dataset, and a reproducibility receipt — the " +
      "part that makes a projection admissible rather than merely persuasive.",
  },
];

# GOV SIM — final pitch deck outline

15 slides. One idea per slide. Image slots marked `[IMG]` with the exact asset to fetch.

---

## 01 — Policy is tested on real people

**Open on one headline, full bleed, nothing else:**

# The Dutch government resigned. 26,000 families were already ruined.

Hold for two seconds. Then the rest fade in behind it, small, overlapping, like a wall of newsprint:

| Netherlands, 2013–2019 | Algorithm flags 26,000 families for benefit fraud. Wrongly. Repayments of €20,000–60,000. Over 1,600 children removed into care. Entire cabinet resigns, 2021. |
|---|---|
| Sri Lanka, 2021 | Overnight ban on fertiliser imports. Rice yields fall over 30%, tea exports lose ~$425m, grocery prices rise up to 90%. Reversed in seven months. Contributed to the collapse of a presidency. |
| Australia, 2015–2020 | Robodebt. Promised $4.7bn in savings. 500,000+ people pursued for unlawful debts. $1.8bn class action settlement. Only 5 in 10,000 debts were ever formally challenged. |
| India, 2016 | 86% of currency voided overnight. Employment and output fall ~2pp in the quarter. Informal economy — half of GDP — hit hardest. |
| United Kingdom, 2013– | Universal Credit staged rollout. +2.8pp mental-health problems on becoming unemployed (+5.2pp lone parents). ~35,000 burglaries and ~25,000 vehicle crimes attributable. |

**Bottom line, one sentence:**

> Five continents. Five decades of policy technique. The same method: enact it, then find out.

`[IMG]` optional — faded newspaper-column texture behind the wall. No photographs of victims.

---

## 02 — The data that decides your life is not allowed in the room

**Why it happens, reason one.**

**On screen:** a building outline. Inside it, a stack of dataset icons. Outside it, a consultant with an empty folder. One red line between them.

Every country's most decision-relevant data is legally immobile:

- National infrastructure topology and load
- Citizen-level tax, benefit and health administrative records
- Security and border systems
- Utility, grid and telecom operational data
- Commercially confidential enterprise filings

Classified, privacy-protected, or sovereign. **It cannot be exported to an external advisor.**

So the analysis is produced by someone modelling *around the hole* — with published aggregates, national averages, and inference.

> The consultant is not failing. The consultant is **barred**.

---

## 03 — The loop

**Why it happens, reason two.**

**On screen:** a closed circle, six arcs, each labelled with its wait. Cost sits in the centre.

```
brief  →  procure  →  scope  →  collect  →  single-domain report  →  review
  ↑                                                                     │
  └─────────────────────  re-brief  ←──────────────────────────────────┘
```

**6–18 months per revolution.**

| Global consulting spend | ~US$85bn/yr |
|---|---|
| UK central government alone | £1.36bn (2022–23) |
| Officials who rate the work valuable | 86% |
| Revolutions a government can afford | **One.** |

Three consequences, one line each:

- One report per question, because a second costs another year and another million
- Four reports, four disciplines, zero interaction modelled — the second-order effect lives in the gap between them
- A national elasticity applied to one specific street network

> You cannot iterate at £1.36 billion a cycle. So nobody iterates. The first draft ships.

---

## 04 — The evidence exists. It isn't being used.

**On screen:** split. Left half grey — what governments do. Right half bright — what the technology can already do.

**Left — nobody checks afterwards:**

- **14 of 32** countries have any system for ex-post review of legislation
- Fewer than **15%** of EU member states share evaluation results at all
- So the failure is never fed back. The next policy starts from the same place.

**Right — prediction is a solved-enough problem:**

- **GraphCast** beat the world's best operational weather system on **90% of 1,380 targets** — 10-day global forecast in under a minute, on one machine
- Machine learning now outperforms decades of physics-based simulation in the single hardest forecasting domain there is

**Across the bottom, one line:**

> Weather gets a supercomputer and a neural network. Policy gets a press conference.
> Decisions that bind millions are still made on narrative, anecdote and instinct — not because better tools don't exist, but because nobody has pointed them at government.

---

## 05 — Everyone else simulates first

**On screen:** the table fills the slide. Small type. Let the density do the work.

| Industry | What it simulates before committing |
|---|---|
| Aviation | Full-motion flight simulators; certification hours flown virtually |
| Aerospace | Mission profiles, re-entry, orbital insertion |
| Automotive | Crash, crumple, thermal — thousands of virtual impacts per physical one |
| Semiconductors | Full logic and timing simulation before tape-out |
| Software | Staging, CI, canary release, load and chaos testing |
| Finance | Backtesting, Monte Carlo, regulatory stress tests |
| Pharmaceuticals | In-silico trials, model-informed drug development |
| Surgery | Patient-specific rehearsal on imaging-derived models |
| Nuclear | Reactor physics and containment simulation |
| Power grid | Load flow, contingency, cascade failure |
| Weather | Numerical and now learned global models |
| Epidemiology | Outbreak and intervention modelling |
| Defence | Wargaming and force-on-force simulation |
| Maritime | Hull, seakeeping, bridge simulators |
| Rail | Signalling and timetable simulation |
| Logistics | Network, warehouse and fleet simulation |
| Motorsport | CFD and lap simulation under regulated compute budgets |
| Construction | Structural, seismic, thermal FEA |
| Mining | Ore body, blast and ventilation modelling |
| Agriculture | Yield, irrigation and climate response models |
| Insurance | Catastrophe models pricing entire national risk pools |
| Telecoms | RF propagation and network capacity planning |
| Robotics | Sim-to-real training in physics engines |
| Architecture | Daylight, airflow, occupancy, energy |

**Then one word, large, alone at the bottom:**

# Government.

> The sector that spends the most and rehearses the least.

`[IMG]` full-motion flight simulator cockpit — Wikimedia Commons or a manufacturer press kit (CAE, Textron).

---

## 06 — This is not a local problem

**On screen:** world map, no country highlighted. Dots on every continent from slide 01.

First principles, three lines:

1. A policy is an irreversible intervention in a complex adaptive system
2. Every government makes them with partial data, one discipline at a time, and no rehearsal
3. Every government has the data required — it just cannot leave the building

**Then the SDG logos, four of them, large:**

`[IMG]` official UN SDG icons — un.org/sustainabledevelopment/news/communications-material

| **11** | Sustainable Cities and Communities |
|---|---|
| **16** | Peace, Justice and Strong Institutions |
| **10** | Reduced Inequalities |
| **13** | Climate Action |

> An international failure mode. A local blast radius. Same fix, any jurisdiction.

---

## 07 — GOV SIM

**On screen:** the loop, animated once, end to end. Then the timer.

```
policy  →  compiled to DSL  →  baseline twin  →  simulation  →  time machine
                                                                     │
   press  ←  re-simulation  ←  amendment  ←  parliament  ←───────────┘
```

Write a policy in plain English. Watch ten years happen.

- Eight real stages. No queue, no callback, no procurement.
- Every run hashed and reproducible.
- The political reaction is **inside** the model, not a paragraph at the end of a report.

**Big, bottom right:**

# 6–18 months → ~10 seconds

---

## 08 — The stack

**On screen:** four horizontal bands, arrows flowing upward. Logos on the left of each band.

```
┌─────────────────────────────────────────────────────────┐
│  INTERFACE   Next.js 14 · TypeScript · deck.gl 9        │
│              MapLibre · extruded footprints              │
│              10-year projection computed in-browser      │
└───────────────────────▲─────────────────────────────────┘
┌───────────────────────┴─────────────────────────────────┐
│  ENGINE      Python 3.11 · FastAPI · 65 endpoints        │
│              ~40 modules: compiler · baseline · synthetic │
│              population · microsim · spatial · economy ·  │
│              dynamics · time-series · analogues ·         │
│              ensemble · uncertainty · stress · opinion ·  │
│              parliament · media · SDG · optimiser ·       │
│              backtest · evidence · registry               │
└───────────────────────▲─────────────────────────────────┘
┌───────────────────────┴─────────────────────────────────┐
│  MODELS      scikit-learn · PyTorch · CPU                │
│              LSTM 2×64, 12 horizons  → R² 0.904 @ +5min  │
│              Gradient Boosting        → R² 0.732 @ +30min │
│              Isolation Forest         → incident anomalies│
│              RF response surface      → hour × weekday    │
└───────────────────────▲─────────────────────────────────┘
┌───────────────────────┴─────────────────────────────────┐
│  CONTEXT     MongoDB, local, read and written            │
│              sensor_readings · ml_models · runs · policies│
│              LLM runs inside the perimeter, reads Mongo   │
│              directly. Nothing crosses the border.        │
└─────────────────────────────────────────────────────────┘
```

**Live international sources — same pipeline, any country:**

`[IMG]` logo row — OpenStreetMap · Overpass API · GTFS · World Bank Open Data · OECD.Stat · UN Data · Copernicus / Sentinel · NASA Earthdata · Global Human Settlement Layer · national open-data portals

- **OpenStreetMap via Overpass, live** — road network, buildings, land use, coastline, anywhere on Earth
- **GTFS** — public transit feeds, published by ~10,000 agencies worldwide
- **World Bank / OECD / UN** — economic and demographic baselines for every member state
- **Copernicus & NASA** — emissions, land surface, flood and heat exposure
- **National census OD schemas** — home-zone → work-zone flows by mode
- **Historical election returns** — any jurisdiction that publishes them

**Footer, in bold:**

> LLMs parse policy, argue, red-team and write the press. **They never produce a number.**

`[IMG]` deck.gl 3D extruded-building screenshot — deck.gl official gallery (deck.gl/examples)

---

## 09 — Context is the speed-up

**On screen:** two columns, side by side, same question asked of both.

*"What happens if we congestion-charge the city centre?"*

| | Conventional | AI-native |
|---|---|---|
| Datasets held together | 1 per report | all of them, one store |
| Disciplines in the answer | 1 | 7 engines, simultaneously |
| Sensitive data included | no — barred | yes — never leaves |
| Time to first answer | 6–18 months | ~10 seconds |
| Cost per additional scenario | another contract | zero |
| Scenarios a government can afford | 1 | unlimited |
| Political outcome modelled | no | yes |

**Underneath:**

- Cross-industry benchmark: unifying context before committing cuts development time by up to **50%** (McKinsey, on digital twins) and prototype cost by **40%**
- The gain has never come from better experts. It comes from putting the whole system in one place and running it before committing.

> A government that can run a thousand scenarios does not need to be right the first time.

*(Note: the two columns are a derived comparison — conventional timings from NAO/consulting data, AI-native from measured GOV SIM run times. Not a single published study.)*

---

## 10 — See it on the ground

**On screen:** the live map. Let it move.

`[IMG]` GOV SIM screenshot — 3D extruded city, impact heat layer

- Real street network, real building footprints, real coastline
- Architectural and land-use change rendered spatially
- Climate exposure overlays — flood, heat, emissions concentration
- Infrastructure bottlenecks appear as **places**, not rows
- Drag the timeline: implementation → 10 years

> Every number on this map is attached to a coordinate.

---

## 11 — What it can actually predict

**On screen:** the seven engines, firing in sequence over the same geometry.

Traffic · emissions · transit load · household budgets by decile · business footfall · land use · public opinion

- **Spatial assignment** on the real network
- **Microsimulation** — who gains, who loses, which decile, which street
- **Economic spillover · system dynamics · time-series baseline**
- **Historical analogues** — London, Stockholm, Singapore, Milan, Gothenburg, Oslo, Ghent, Madrid — each scored for transferability to *this* geography
- **Monte Carlo bands** that visibly widen with the horizon

`[IMG]` LSTM accuracy decay curve, R² 0.904 → 0.61

> The decay curve is plotted, not hidden. That is the honest limit of the forecast.

---

## 12 — It has to survive the chamber

**On screen:** the chamber, two divisions side by side, seats coloured by party.

| Mild distributional impact | **carries 99–14** |
|---|---|
| Low-income burden past the stated constraint | **fails 38–52** |

- Real seat composition, real party priors from published election returns
- Opposition files an amendment
- One click re-simulates the amended policy end to end

> Same intervention. One constraint moved. Opposite political outcome.
> The version that passes is never the version that was modelled — unless you model the version that passes.

---

## 13 — And the public, and the press

**On screen:** simulated front pages across the editorial spectrum, watermarked SIMULATED.

- Heterogeneous cohorts, not an average voter — by income, geography, mode of travel, age
- Opinion diffusion across a social network, not a single poll number
- Predicted coverage from left, centre and right desks
- Consensus and backlash forecast against historical voting behaviour in that jurisdiction

**Red team, underneath:**

Loopholes · displacement · perverse incentives · enforcement gaps · capacity bottlenecks · political collapse
Stressed under: recession · fuel shock · flood · heatwave · population surge

**One sentence, large:**

> **Performs well under baseline. Fails under recession.**

That sentence is the product.

---

## 14 — Limits, and what we measure

**On screen:** two blocks.

**What it is not:**

1. Scenarios under stated assumptions — not forecasts
2. LLMs never produce a quantitative result
3. Uncertainty widens with the horizon, visibly
4. Every output tagged Observed / Estimated / Simulated / Generated
5. Every number traces back: data → transformation → model → assumption
6. `REPRODUCE RUN` regenerates any result exactly
7. Backtest scores shown, including the bad ones

**What it moves — measured, not scored:**

| **SDG 11** | transport access, land use, resilience |
|---|---|
| **SDG 16** | evidence-informed, auditable, reproducible decisions |
| **SDG 10** | burden by decile and zone, surfaced before enactment |
| **SDG 13** | emissions per scenario |

Baseline · scenario · change · source · confidence. No composite index — a composite index is a marketing number.

> Decision support. Not an oracle.

---

## 15 — Close

**On screen:** black. One line at a time.

> Twenty-four industries rehearse before they commit.
>
> Government is the last one that doesn't.
>
> The data exists. The models exist. The compute fits in a building.
>
> **What's been missing is a place to put it all at once.**

**Then, full width:**

# Stop governing on instinct.

> Every disaster on the first slide was discoverable in simulation.
> None of them were simulated.
>
> **GOV SIM. Run the policy before you run the country.**

---

## Works Cited

Chodorow-Reich, Gabriel, et al. *Cash and the Economy: Evidence from India's Demonetization*. Working Paper 25370, National Bureau of Economic Research, Dec. 2018, nber.org/digest/feb19/indias-demonetization-reduced-employment-and-economic-activity.

European Court of Auditors. *Ex-post Review of EU Legislation: A Well-Established System, but Incomplete*. Special Report 16/2018, Publications Office of the European Union, 2018, op.europa.eu/webpub/eca/special-reports/better-regulation-16-2018/en/.

Holmes, Catherine. *Report of the Royal Commission into the Robodebt Scheme*. Commonwealth of Australia, July 2023, pmc.gov.au/sites/default/files/resource/download/gov-response-royal-commission-robodebt-scheme.pdf.

Lam, Remi, et al. "Learning Skillful Medium-Range Global Weather Forecasting." *Science*, vol. 382, no. 6677, Dec. 2023, doi:10.1126/science.adi2336.

Lahiri, Amartya. "The Great Indian Demonetization." *Journal of Economic Perspectives*, vol. 34, no. 1, Winter 2020, pp. 55–74, aeaweb.org/articles?id=10.1257/jep.34.1.55.

National Audit Office. *Government's Use of External Consultants*. NAO, nao.org.uk/insights/governments-use-of-external-consultants/.

Organisation for Economic Co-operation and Development. "Ex-post Evaluation." *Government at a Glance 2025*, OECD Publishing, 2025, oecd.org/en/publications/2025/06/government-at-a-glance-2025_70e14c6c/full-report/ex-post-evaluation_5fd27bda.html.

Parlementaire Ondervragingscommissie Kinderopvangtoeslag. *Ongekend Onrecht*. Tweede Kamer der Staten-Generaal, Dec. 2020.

"Sri Lanka's Organic Farming Experiment Went Catastrophically Wrong." *Foreign Policy*, 5 Mar. 2022, foreignpolicy.com/2022/03/05/sri-lanka-organic-farming-crisis/.

"What Sri Lanka's Ban of Chemical Fertilizers in 2021 Can Teach the World." *International Water Management Institute*, 17 Oct. 2025, iwmi.org/blogs/challenges-and-opportunities-for-an-agro-ecological-transformation/.

"What Is Digital-Twin Technology?" *McKinsey & Company*, 26 Aug. 2024, mckinsey.com/featured-insights/mckinsey-explainers/what-is-digital-twin-technology.

Wickham, Sophie, et al. "Universal Credit and Mental Health." *Journal of Health Economics*, Elsevier, sciencedirect.com/science/article/pii/S0167629624000857.

"Universal Credit, Financial Insecurity and Crime." *Journal of Law, Economics, and Organization*, vol. 40, no. 1, 2024, pp. 129–, academic.oup.com/jleo/article-abstract/40/1/129/6637737.
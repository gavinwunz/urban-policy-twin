import PolicyCompiler from "./PolicyCompiler";
import SimulationSection from "../components/city/SimulationSection";
import Newsroom from "../components/media/Newsroom";
import Referendum from "../components/media/Referendum";
import ModelSection from "../components/model/ModelSection";
import ParliamentSection from "../components/parliament/ParliamentSection";
import PipelineRun from "../components/pipeline/PipelineRun";
import Hero from "../components/shell/Hero";
import Masthead from "../components/shell/Masthead";
import SectionNav from "../components/shell/SectionNav";
import { Block, Grid, Section } from "../components/shell/Section";
import { TwinProvider } from "../components/twin/TwinStore";

import AnaloguePanel from "../components/twin/AnaloguePanel";
import AssumptionsPanel from "../components/twin/AssumptionsPanel";
import BacktestPanel from "../components/twin/BacktestPanel";
import BriefPanel from "../components/twin/BriefPanel";
import BusinessPanel from "../components/twin/BusinessPanel";
import CitizenPanel from "../components/twin/CitizenPanel";
import ComparePanel from "../components/twin/ComparePanel";
import DataFabricPanel from "../components/twin/DataFabricPanel";
import DiffusionPanel from "../components/twin/DiffusionPanel";
import DynamicsPanel from "../components/twin/DynamicsPanel";
import EconomyPanel from "../components/twin/EconomyPanel";
import EnsemblePanel from "../components/twin/EnsemblePanel";
import FailureModesPanel from "../components/twin/FailureModesPanel";
import GrandComparePanel from "../components/twin/GrandComparePanel";
import InstitutionsPanel from "../components/twin/InstitutionsPanel";
import MicrosimPanel from "../components/twin/MicrosimPanel";
import NorthStarPanel from "../components/twin/NorthStarPanel";
import OptimiserPanel from "../components/twin/OptimiserPanel";
import PressConferencePanel from "../components/twin/PressConferencePanel";
import PublicReactionPanel from "../components/twin/PublicReactionPanel";
import RegistryPanel from "../components/twin/RegistryPanel";
import ReproducePanel from "../components/twin/ReproducePanel";
import RobustnessPanel from "../components/twin/RobustnessPanel";
import RunPanel from "../components/twin/RunPanel";
import ScenariosPanel from "../components/twin/ScenariosPanel";
import SdgPanel from "../components/twin/SdgPanel";
import SensitivityPanel from "../components/twin/SensitivityPanel";
import SpatialPanel from "../components/twin/SpatialPanel";
import StressPanel from "../components/twin/StressPanel";
import TimeseriesPanel from "../components/twin/TimeseriesPanel";
import UncertaintyPanel from "../components/twin/UncertaintyPanel";
import WorldPanel from "../components/twin/WorldPanel";

/**
 * One page, seven sections, nothing behind a tab.
 *
 * The previous build put 35 analysis panels behind a tab bar inside a collapsed
 * "Advanced" disclosure — three clicks from the landing state to any given
 * number, and no way to read two of them together. Every panel below is mounted
 * and visible; the sticky rail on the left groups them by the kind of work they
 * do and moves you through them.
 *
 * Order is the order a briefing actually takes: run the thing, look at what it
 * did to the city, interrogate the model, then take it to the House, the
 * public and the press, then try to break it, then prove it can be audited.
 */
export default function Home() {
  return (
    <>
      <Masthead />
      <SectionNav />

      <main className="dash">
        <Hero />

        <TwinProvider>
          {/* 01 — the pipeline, executing */}
          <Section id="run">
            <Grid>
              <Block
                title="Run the simulation"
                hint="Eight dependent stages across the compiler, the model registry, an LSTM, the agent-based engine, an opinion model, the House and the newsroom."
                span={2}
              >
                <PipelineRun />
              </Block>
              <Block
                title="Policy compiler"
                hint="The structured Policy DSL behind the run — every extracted parameter, editable before you simulate."
                span={2}
              >
                <PolicyCompiler />
              </Block>
            </Grid>
          </Section>

          {/* 02 — what it does to the city */}
          <Section id="simulation">
            <SimulationSection />
            <Grid>
              <Block
                title="Engine run"
                hint="The full agent-based simulation with uncertainty bands, checkpoint by checkpoint."
                span={2}
              >
                <RunPanel />
              </Block>
              <Block title="World state" hint="Zones, land use and travel demand the policy acts on.">
                <WorldPanel />
              </Block>
              <Block title="Spatial incidence" hint="Which parts of the network absorb the change.">
                <SpatialPanel />
              </Block>
              <Block title="Time series" hint="Every tracked indicator over the ten-year horizon.">
                <TimeseriesPanel />
              </Block>
              <Block title="System dynamics" hint="Feedback loops and second-order effects.">
                <DynamicsPanel />
              </Block>
              <Block title="Economy" hint="Revenue, costs and distributional impact.">
                <EconomyPanel />
              </Block>
              <Block title="Microsimulation" hint="Household-level incidence against the stated equity constraint.">
                <MicrosimPanel />
              </Block>
            </Grid>
          </Section>

          {/* 03 — the model underneath */}
          <Section id="model">
            <ModelSection />
            <Grid>
              <Block title="Backtest" hint="The model run against history, where the answer is already known.">
                <BacktestPanel />
              </Block>
              <Block title="Ensemble" hint="Many model configurations, disagreeing usefully.">
                <EnsemblePanel />
              </Block>
              <Block title="Real-world analogues" hint="Cities that already tried this, and what happened.">
                <AnaloguePanel />
              </Block>
              <Block title="Diffusion" hint="How adoption spreads through the population over time.">
                <DiffusionPanel />
              </Block>
            </Grid>
          </Section>

          {/* 04 — the House */}
          <Section id="parliament">
            <ParliamentSection />
          </Section>

          {/* 05 — public and press */}
          <Section id="reactions">
            <Grid>
              <Block
                title="The front page"
                hint="How this lands in the press, at each Time-Machine checkpoint. Simulated archetypes, never real mastheads."
                span={2}
              >
                <Newsroom />
              </Block>
              <Block
                title="Citizens-initiated referendum"
                hint="Would it survive a public vote? Computed from the cohort opinion model, with turnout weighting."
              >
                <Referendum />
              </Block>
              <Block title="Public reaction" hint="Modelled opinion by segment, with the drivers behind it.">
                <PublicReactionPanel />
              </Block>
              <Block title="Business response" hint="How firms inside the cordon expect to be affected.">
                <BusinessPanel />
              </Block>
              <Block title="One household" hint="The policy from a single citizen's point of view.">
                <CitizenPanel />
              </Block>
              <Block title="Institutional review" hint="What the statutory bodies would say.">
                <InstitutionsPanel />
              </Block>
              <Block title="Press conference" hint="The questions a minister would actually be asked.">
                <PressConferencePanel />
              </Block>
              <Block title="Red team" hint="The failure nobody costed — adversarial, on purpose." span={2}>
                <FailureModesPanel />
              </Block>
            </Grid>
          </Section>

          {/* 06 — where it breaks */}
          <Section id="stress">
            <Grid>
              <Block title="Scenario library" hint="Canonical policies to compare against.">
                <ScenariosPanel />
              </Block>
              <Block title="Head to head" hint="This policy against its nearest alternative.">
                <ComparePanel />
              </Block>
              <Block title="Four worlds" hint="A/B/C/D — do nothing, this, the alternative, and both." span={2}>
                <GrandComparePanel />
              </Block>
              <Block title="Sensitivity" hint="Which assumption the answer actually hinges on.">
                <SensitivityPanel />
              </Block>
              <Block title="Uncertainty" hint="The bands around every headline number.">
                <UncertaintyPanel />
              </Block>
              <Block title="Stress tests" hint="Shocks applied until something gives.">
                <StressPanel />
              </Block>
              <Block title="Robustness" hint="Ranked by how well it survives being wrong.">
                <RobustnessPanel />
              </Block>
              <Block title="Optimiser" hint="The parameter set that best meets the stated objective.">
                <OptimiserPanel />
              </Block>
              <Block title="Sustainable development goals" hint="Alignment against the SDG framework.">
                <SdgPanel />
              </Block>
            </Grid>
          </Section>

          {/* 07 — the audit trail */}
          <Section id="evidence">
            <Grid>
              <Block title="The answer" hint="One fused response to 'what happens if we do this?'" span={2}>
                <NorthStarPanel />
              </Block>
              <Block title="Ministerial brief" hint="The whole thing, as a document a minister would be handed." span={2}>
                <BriefPanel />
              </Block>
              <Block title="Assumptions" hint="Every knob, its value, and what happens if it is wrong.">
                <AssumptionsPanel />
              </Block>
              <Block title="Data fabric" hint="Every dataset, its licence and its provenance tag.">
                <DataFabricPanel />
              </Block>
              <Block title="Reproducibility receipt" hint="Enough to re-run this exact result later.">
                <ReproducePanel />
              </Block>
              <Block title="Model registry" hint="What is deployed, and when it was last fitted.">
                <RegistryPanel />
              </Block>
            </Grid>
          </Section>
        </TwinProvider>

        <footer className="dash-footer">
          <p>
            <strong>GOV SIM</strong> — policy simulation environment. Projections
            are <span className="tag simulated">Simulated</span> and never
            presented as fact. Auckland city geometry scraped from OpenStreetMap
            under the Open Database Licence; basemap tiles © CARTO. Traffic
            model fitted on a 207-sensor loop-detector speed corpus. Election
            results from the New Zealand Electoral Commission.
          </p>
        </footer>
      </main>
    </>
  );
}

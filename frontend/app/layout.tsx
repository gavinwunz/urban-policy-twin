import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
// Loaded second on purpose: the dashboard layer overrides the older page
// styles it replaces (hero, section rhythm, map frame).
import "./dashboard.css";

// Type system (SPEC-adjacent to the palette below, see globals.css):
// Fraunces carries the hero and section headings — a display serif with real
// weight, used sparingly. IBM Plex Sans is the body face. IBM Plex Mono marks
// anything measured: provenance tags, the title block, tabular data — a
// typographic cue that a value was drawn from the model, not typed by hand.
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "GOV SIM — Policy Simulation Environment",
  description:
    "GOV SIM lets governments test, stress-test, debate, amend and explore " +
    "policies before they are deployed in the real world — based on local " +
    "datasets and ML prediction models. Every metric is tagged " +
    "Observed / Estimated / Simulated / Generated.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}

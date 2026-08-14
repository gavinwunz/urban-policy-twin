/**
 * Custom 404 (Next.js App Router).
 *
 * Completes the error-surface coverage alongside `error.tsx` / `global-error.tsx`:
 * a bad URL should land on a themed, honest page with a way back to the twin, not
 * Next's bare default 404 (off-brand mid-demo). Static and self-contained; renders
 * inside the root layout so `globals.css` theme tokens apply. No data, no metrics.
 */

import Link from "next/link";

export default function NotFound() {
  return (
    <main>
      <p className="eyebrow">GOV SIM — Policy Digital Twin</p>
      <h1>Page not found</h1>
      <p className="lede">
        There’s nothing at this address. The digital twin lives on the main
        screen — head back and pick up where you left off.
      </p>
      <div className="error-actions">
        <Link href="/" className="btn primary">
          Back to the twin
        </Link>
      </div>
    </main>
  );
}

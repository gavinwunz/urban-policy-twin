"use client";

/**
 * Route-segment error boundary (Next.js App Router).
 *
 * Individual panels already handle their own fetch idle/loading/error states,
 * but a *render* throw — an unexpected backend payload shape, a deck.gl /
 * MapLibre runtime error, a null deref deep in a chart — is not caught by those
 * and would otherwise blank the whole app to Next's default crash page. In a
 * live demo that reads as "the product broke". This boundary keeps the failure
 * contained and honest: a clear message, the error digest for debugging, and a
 * one-click recovery — never a fabricated metric (SPEC §34).
 *
 * This file renders inside the root layout, so `globals.css` theme tokens and
 * utility classes are available. Root-layout failures are handled separately by
 * `app/global-error.tsx`.
 */

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface to the browser console for anyone inspecting a broken demo.
    // eslint-disable-next-line no-console
    console.error("GOV SIM UI render error:", error);
  }, [error]);

  return (
    <main>
      <p className="eyebrow">GOV SIM — Policy Digital Twin</p>
      <h1>Something in the interface crashed</h1>
      <p className="lede">
        A part of the twin failed to render. Nothing here is a real result — no
        numbers were produced or estimated. Recover the view and try again; if it
        keeps happening, the backend may be returning an unexpected shape.
      </p>

      <div className="card error-boundary">
        <h2>What happened</h2>
        <p className="error-text">
          {error.message || "An unexpected client-side error occurred."}
        </p>
        {error.digest && (
          <p className="hint">
            Error digest: <code>{error.digest}</code>
          </p>
        )}
        <div className="error-actions">
          <button type="button" className="btn primary" onClick={() => reset()}>
            Try again
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => window.location.reload()}
          >
            Reload the app
          </button>
        </div>
      </div>
    </main>
  );
}

"use client";

/**
 * Root-layout error boundary (Next.js App Router).
 *
 * `app/error.tsx` cannot catch a throw in the root layout itself, because it
 * renders *inside* that layout. `global-error` replaces the entire document, so
 * it must render its own <html>/<body> and cannot rely on the layout's imported
 * `globals.css`. Styles are therefore inlined and kept minimal but on-brand.
 *
 * Same honesty contract as the segment boundary: a clear failure state and a
 * recovery action, never a fabricated metric (SPEC §34).
 */

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          background: "#0b1020",
          color: "#e7ecf5",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
          lineHeight: 1.5,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
        }}
      >
        <div style={{ maxWidth: "40rem", width: "100%" }}>
          <p
            style={{
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              fontSize: "0.75rem",
              color: "#93a0bd",
              margin: "0 0 0.5rem",
            }}
          >
            GOV SIM — Policy Digital Twin
          </p>
          <h1 style={{ fontSize: "2rem", lineHeight: 1.15, margin: "0 0 1rem" }}>
            The app failed to start
          </h1>
          <p style={{ color: "#93a0bd", margin: "0 0 1.5rem" }}>
            A fatal error occurred before the interface could load. No results
            were produced — nothing shown here is a real number. Reload to try
            again.
          </p>
          <div
            style={{
              background: "#141c30",
              border: "1px solid #263149",
              borderRadius: "12px",
              padding: "1.25rem 1.5rem",
            }}
          >
            <p style={{ color: "#ff6b6b", margin: "0 0 0.75rem" }}>
              {error.message || "An unexpected fatal error occurred."}
            </p>
            {error.digest && (
              <p
                style={{
                  color: "#93a0bd",
                  fontSize: "0.85rem",
                  margin: "0 0 1rem",
                }}
              >
                Error digest: <code>{error.digest}</code>
              </p>
            )}
            <button
              type="button"
              onClick={() => reset()}
              style={{
                background: "#4f8cff",
                border: "1px solid #4f8cff",
                borderRadius: "8px",
                padding: "0.5rem 0.9rem",
                fontSize: "0.9rem",
                color: "#06122b",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Reload the app
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}

import { useReport } from "../hooks/ReportContext";
import { dismissed } from "../lib/report";
import { pct } from "../lib/format";

export function Dismissed() {
  const { report } = useReport();
  if (!report) return null;

  const items = dismissed(report);

  return (
    <>
      <p className="statusline">
        Examined &mdash; <span className="em">not regressions</span>
      </p>
      <p className="section-title">
        We examined {items.length} suspicious pattern{items.length !== 1 ? "s" : ""} and cleared them.
        Precision is a designed outcome.
      </p>

      <div className="strip">
        {items.map((f) => (
          <details key={f.id}>
            <summary>
              {f.plain_summary}
              <span className="muted small" style={{ marginLeft: 10 }}>
                {f.tenant} &middot; day {f.window.from_day}&ndash;{f.window.to_day}
              </span>
            </summary>
            <div className="reason">
              {f.not_a_regression_because && (
                <div className="line"><strong>Why not a regression:</strong> {f.not_a_regression_because}</div>
              )}
              {f.evidence.length > 0 && (
                <div className="line" style={{ marginTop: 6 }}>
                  <strong>Evidence:</strong>
                  <ul style={{ margin: "4px 0 0 18px", padding: 0 }}>
                    {f.evidence.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}
              {f.observed != null && f.expected != null && (
                <div className="line" style={{ marginTop: 6 }}>
                  {f.metric}: {pct(f.expected)} &rarr; {pct(f.observed)}
                </div>
              )}
            </div>
          </details>
        ))}
      </div>

      {items.length === 0 && (
        <p className="muted" style={{ padding: 40, textAlign: "center" }}>
          No patterns were examined and dismissed.
        </p>
      )}
    </>
  );
}

import { useState } from "react";
import { useReport } from "../hooks/ReportContext";
import { dismissed } from "../lib/report";
import { IncidentsTable } from "../components/IncidentsTable";
import { FindingSidePanel } from "../components/FindingSidePanel";
import type { Finding } from "../api/types";

export function Dismissed() {
  const { report } = useReport();
  const [selected, setSelected] = useState<Finding | null>(null);
  if (!report) return null;

  const items = dismissed(report);

  return (
    <div className="page-container page-container-wide">
      <div className="page-header">
        <h1>Lookalikes</h1>
        <p>
          {items.length} pattern{items.length !== 1 ? "s" : ""} looked like regressions and weren&rsquo;t.
          Here&rsquo;s why each one was cleared.
        </p>
      </div>

      {items.length > 0 ? (
        <IncidentsTable
          findings={items}
          report={report}
          visibleColumns={["title", "context"]}
          onSelect={setSelected}
        />
      ) : (
        <p className="muted" style={{ padding: 40, textAlign: "center" }}>
          No patterns were examined and dismissed.
        </p>
      )}

      <FindingSidePanel report={report} finding={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

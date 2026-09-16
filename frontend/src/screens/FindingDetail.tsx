import { useParams, useNavigate } from "react-router-dom";
import { useReport } from "../hooks/ReportContext";
import { FindingDetailBody } from "../components/FindingDetailBody";

export function FindingDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { report } = useReport();
  if (!report || !id) return null;

  const finding = report.findings.find((f) => f.id === id);
  if (!finding) return <p className="error">Finding not found.</p>;

  return (
    <div className="page-container finding-page">
      <button className="back" onClick={() => nav("/")}>&larr; Back to Incidents</button>
      <FindingDetailBody report={report} finding={finding} />
    </div>
  );
}

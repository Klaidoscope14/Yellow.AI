import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "tools", "nexus-loop-kit", "pipeline.py")
KIT_PATH = os.path.join(ROOT, "kit")
REPORT_PATH = os.environ.get(
    "NEXUS_REPORT_PATH",
    os.path.join(ROOT, "loop-report.json"),
)
APPROVALS_PATH = os.path.join(ROOT, ".approvals.json")

LAST_REPORT = {}
REPORT_LOCK = threading.Lock()


def load_approvals() -> dict:
    try:
        with open(APPROVALS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_approvals(approvals: dict) -> None:
    temporary_path = APPROVALS_PATH + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(approvals, handle, indent=2)
    os.replace(temporary_path, APPROVALS_PATH)


def apply_saved_approvals(report: dict) -> dict:
    approvals = load_approvals()
    for prescription in report.get("prescriptions", []):
        approval = approvals.get(prescription.get("id"))
        if approval:
            prescription["approval"] = approval
    return report


def persist_report_approval(prescription_id: str, approval: dict) -> None:
    if not os.path.exists(REPORT_PATH):
        return
    with open(REPORT_PATH, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    for prescription in report.get("prescriptions", []):
        if prescription.get("id") == prescription_id:
            prescription["approval"] = approval
            break
    temporary_path = REPORT_PATH + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    os.replace(temporary_path, REPORT_PATH)


def bootstrap_report() -> None:
    global LAST_REPORT
    try:
        if os.path.exists(REPORT_PATH):
            with open(REPORT_PATH, "r", encoding="utf-8") as handle:
                raw_report = json.load(handle)
        else:
            raw_report = run_agent_pipeline("generalized-final-loop", KIT_PATH, "http://127.0.0.1:8719")
        LAST_REPORT = apply_saved_approvals(to_service_model(raw_report))
    except Exception as exc:  # pragma: no cover
        LAST_REPORT = {"status": "error", "message": str(exc)}


def to_service_model(raw_report: dict) -> dict:
    report = dict(raw_report)
    for field in ("metrics", "standard", "findings", "diagnoses", "prescriptions", "verifications", "gaps"):
        report.setdefault(field, [])

    report["findings"] = [
        {
            **finding,
            "plain_summary": finding.get("plain_summary")
            or (finding.get("impact") or {}).get("derivation", "Detected anomaly"),
        }
        for finding in report["findings"]
    ]

    self_assessment = report.get("self_assessment") or {}
    report.update({
        "run_id": f"run_{report.get('team', 'demo')}_{len(report['findings'])}",
        "status": "ok",
        "summary": {
            "findings": len(report["findings"]),
            "prescriptions": len(report["prescriptions"]),
            "verified": len(report["verifications"]),
            "self_assessment_cycles": self_assessment.get("cycles", 0),
            "team": report.get("team"),
        },
    })
    return report


def run_agent_pipeline(team: str, kit: str, replay_url: str | None = None) -> dict:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as temp_file:
        out_path = temp_file.name

    cmd = [
        sys.executable,
        PIPELINE,
        "--kit",
        kit,
        "--team",
        team,
        "--out",
        out_path,
    ]
    if replay_url:
        cmd.extend(["--replay-url", replay_url])
    cmd.append("--score")

    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"pipeline failed with return code {result.returncode}")

    with open(out_path, "r", encoding="utf-8") as handle:
        raw_report = json.load(handle)

    os.unlink(out_path)
    return raw_report


class ServiceHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_json({"status": "ok"})
        elif parsed.path == "/report":
            self.send_json(LAST_REPORT)
        else:
            self.send_error(404, "Not found")

    def handle_approval(self, payload: dict) -> None:
        prescription_id = payload.get("prescription_id")
        verdict = payload.get("verdict")
        reason = str(payload.get("reason") or "").strip()
        if not prescription_id or verdict not in {"accepted", "rejected", "deferred"}:
            self.send_json({"status": "error", "message": "invalid approval payload"}, status=400)
            return
        if not reason:
            self.send_json({"status": "error", "message": "reason is required"}, status=400)
            return

        with REPORT_LOCK:
            prescription = next(
                (item for item in LAST_REPORT.get("prescriptions", [])
                 if item.get("id") == prescription_id),
                None,
            )
            if prescription is None:
                self.send_json({"status": "error", "message": "prescription not found"}, status=404)
                return

            approval = {
                "verdict": verdict,
                "decided_by": payload.get("decided_by") or "operator",
                "reason": reason,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            approvals = load_approvals()
            approvals[prescription_id] = approval
            save_approvals(approvals)
            persist_report_approval(prescription_id, approval)
            prescription["approval"] = approval

        self.send_json({"prescription_id": prescription_id, "approval": approval})

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_json({"status": "error", "message": "invalid json"}, status=400)
            return

        if parsed.path == "/approvals":
            self.handle_approval(payload)
            return
        if parsed.path != "/run":
            self.send_error(404, "Not found")
            return

        team = payload.get("team") or "generalized-final-loop"
        kit = payload.get("kit") or KIT_PATH
        replay_url = payload.get("replay_url")

        try:
            raw_report = run_agent_pipeline(team, kit, replay_url)
            public_report = to_service_model(raw_report)
            global LAST_REPORT
            LAST_REPORT = apply_saved_approvals(public_report)
            self.send_json(LAST_REPORT)
        except Exception as exc:  # pragma: no cover
            self.send_json({"status": "error", "message": str(exc)}, status=500)

    def send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    bootstrap_report()
    server = ThreadingHTTPServer(("127.0.0.1", 8081), ServiceHandler)
    print("service listening on http://127.0.0.1:8081")
    server.serve_forever()

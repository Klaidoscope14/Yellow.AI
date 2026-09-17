const SERVICE_URL = "http://127.0.0.1:8081";

const statusBox = document.getElementById("statusBox");
const scoreBox = document.getElementById("scoreBox");
const summaryOutput = document.getElementById("summaryOutput");
const standardsList = document.getElementById("standardsList");
const findingsList = document.getElementById("findingsList");
const verificationList = document.getElementById("verificationList");
const runBtn = document.getElementById("runBtn");

async function callRun() {
  statusBox.textContent = "Running...";
  runBtn.disabled = true;

  try {
    const response = await fetch(`${SERVICE_URL}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        team: "generalized-final-loop",
        kit: "C:/Users/Samsung/Desktop/nexus-loop-day1/nexus-loop-day1/kit",
        replay_url: "http://127.0.0.1:8719",
      }),
    });

    const data = await response.json();
    if (!response.ok || data.status === "error") {
      throw new Error(data.message || "Run failed");
    }

    renderReport(data);
    statusBox.textContent = "Completed successfully";
  } catch (error) {
    statusBox.textContent = `Error: ${error.message}`;
  } finally {
    runBtn.disabled = false;
  }
}

function renderReport(report) {
  scoreBox.textContent = `Score: ${report.score ?? "--"}`;
  summaryOutput.textContent = JSON.stringify(report.summary, null, 2);

  standardsList.innerHTML =
    (report.standards || [])
      .map(
        (item) => `
    <li>
      <strong>${item.metric}</strong> · ${item.cohort}<br>
      best: ${item.best} · median: ${item.median} · deficit: ${item.deficit}
    </li>
  `,
      )
      .join("") || "<li>No standards returned</li>";

  findingsList.innerHTML =
    (report.findings || [])
      .map(
        (item) => `
    <li>
      <strong>${item.id}</strong> [${item.severity}]<br>
      ${item.summary}
    </li>
  `,
      )
      .join("") || "<li>No findings</li>";

  verificationList.innerHTML =
    (report.verifications || [])
      .map(
        (item) => `
    <li>
      ${item.prescription_id} · ${item.verdict} · ${item.metric}<br>
      golden_set_pass: ${item.golden_set_pass}
    </li>
  `,
      )
      .join("") || "<li>No verification data</li>";
}

runBtn.addEventListener("click", callRun);

fetch(`${SERVICE_URL}/health`)
  .then((r) => r.json())
  .then((data) => {
    statusBox.textContent =
      data.status === "ok" ? "Service connected" : "Service unavailable";
  })
  .catch(() => {
    statusBox.textContent = "Service unavailable";
  });

import subprocess
import time
import sys
import os
import urllib.request
import json

root = os.path.dirname(os.path.abspath(__file__))

# Clean up any orphaned ports before starting
ports = [8719, 8802, 8801, 5173]
try:
    import psutil
    print("Killing existing processes on ports 8719, 8802, 8801, 5173...")
    for conn in psutil.net_connections():
        if conn.laddr.port in ports and conn.pid:
            try:
                psutil.Process(conn.pid).terminate()
            except:
                pass
except ImportError:
    pass

env = os.environ.copy()
env["NEXUS_DATA_DIR"] = os.path.join(root, "Nexus-Loop", "kit", "corpus")
env["NEXUS_CATALOG_PATH"] = os.path.join(root, "Nexus-Loop", "kit", "catalog.json")
env["NEXUS_LABELS_PATH"] = os.path.join(root, "Nexus-Loop", "kit", "labels", "rubric_scores.jsonl")

print("[1/4] Starting Replay Service (Port 8719)...")
p1 = subprocess.Popen([sys.executable, "replay/serve.py", "--kit", "../../kit", "--ground-truth", "../../../flaggingLogic/pipeline/ground_truth.json", "--port", "8719"], 
                      cwd=os.path.join(root, "Nexus-Loop", "tools", "nexus-loop-kit"))
time.sleep(2)

print("[2/4] Starting AI/ML Service (Port 8802)...")
p2 = subprocess.Popen([sys.executable, "run_aiml.py"], cwd=os.path.join(root, "Nexus-Loop"))
time.sleep(3)

print("[3/4] Starting Backend Server (Port 8801)...")
p3 = subprocess.Popen([sys.executable, "run_backend.py"], cwd=os.path.join(root, "flaggingLogic"), env=env)
time.sleep(4)

print("Calling backend to generate report and trigger Replay service...")
try:
    req = urllib.request.Request("http://127.0.0.1:8801/report")
    with urllib.request.urlopen(req, timeout=60) as response:
        report_data = json.loads(response.read().decode())
        out_path = os.path.join(root, "flaggingLogic", "output", "loop-report.json")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report_data, f, indent=2)
        print(f"Report generated successfully to {out_path}!")
except Exception as e:
    print(f"Failed to generate report automatically: {e}")

print("[4/4] Starting Frontend (Port 5173)...")
# use shell=True for npm to work properly on windows
p4 = subprocess.Popen("npm run dev", shell=True, cwd=os.path.join(root, "frontend"))

print("\nAll services are running! Press Ctrl+C to shut everything down.")
try:
    p4.wait()
except KeyboardInterrupt:
    print("\nShutting down all services...")
    p1.kill()
    p2.kill()
    p3.kill()
    p4.kill()

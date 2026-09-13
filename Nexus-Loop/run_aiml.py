"""Run the AI/ML API.  python run_aiml.py  (default port 8802)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # make `service` importable

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("NEXUS_AIML_PORT", "8802"))
    host = os.environ.get("NEXUS_AIML_HOST", "127.0.0.1")
    uvicorn.run("service.app:app", host=host, port=port, reload=False)

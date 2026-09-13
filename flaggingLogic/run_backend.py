"""Run the backend API.  python run_backend.py  (default port 8801)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # make `service` importable

import uvicorn  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("NEXUS_BACKEND_PORT", "8801"))
    host = os.environ.get("NEXUS_BACKEND_HOST", "127.0.0.1")
    uvicorn.run("service.app:app", host=host, port=port, reload=False)

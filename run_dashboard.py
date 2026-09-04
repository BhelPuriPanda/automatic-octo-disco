"""
SupplyChainIQ - Phase 6 Runner Script: Web Dashboard Server
Launches the FastAPI backend & Interactive Web Dashboard application.
Access in browser: http://localhost:8000
Interactive Swagger API Docs: http://localhost:8000/docs
"""

import uvicorn
import webbrowser
import threading
import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))


def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    print("=" * 75)
    print("       SUPPLYCHAINIQ: INTERACTIVE SUPPLY CHAIN & INVENTORY PLATFORM    ")
    print("=" * 75)
    print(">>> Web Dashboard: http://localhost:8000")
    print(">>> Swagger API Docs: http://localhost:8000/docs")
    print(">>> Press CTRL+C to stop the server.")
    print("=" * 75)

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, log_level="info")

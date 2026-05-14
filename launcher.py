"""Launcher script to open the app in browser automatically."""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

def start_app():
    """Start Flask server and open in browser."""
    script_dir = Path(__file__).parent
    app_script = script_dir / "src" / "hibs_predictor" / "main.py"
    
    print("🟤💛 hibs-bet — starting advanced betting app")
    print("=" * 50)
    
    # Start Flask app in subprocess
    print("Starting server...")
    server_process = subprocess.Popen(
        [sys.executable, str(app_script), "web"],
        cwd=str(script_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server to start
    time.sleep(3)
    
    # Open in browser
    url = "http://127.0.0.1:5000"
    print(f"Opening {url} in your browser...")
    webbrowser.open(url)
    
    print("\n✓ App launched! Opening dashboard...")
    print("Press Ctrl+C to stop the server\n")
    
    try:
        server_process.wait()
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        server_process.terminate()
        server_process.wait()
        sys.exit(0)

if __name__ == "__main__":
    start_app()

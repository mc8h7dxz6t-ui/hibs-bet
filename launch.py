#!/usr/bin/env python3
"""HibsBetting One-Click Launcher - Double-click to launch!"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

def main():
    """Launch HibsBetting with browser auto-open."""
    script_dir = Path(__file__).parent

    print("🟤💛 HibsBetting — Advanced Betting Intelligence")
    print("═══════════════════════════════════════════════════")
    print()

    # Check for .env file
    env_file = script_dir / ".env"
    if not env_file.exists():
        print("❌ No .env file found!")
        print("Please create .env file with your API keys:")
        print("1. Copy .env.example to .env")
        print("2. Edit .env with your actual API keys")
        print()
        input("Press Enter to exit...")
        return

    # Activate virtual environment
    venv_path = script_dir / ".venv" / "bin" / "activate"
    if venv_path.exists():
        print("🔧 Activating virtual environment...")
        # We'll use subprocess to run the command with activated venv
        cmd = f"source {venv_path} && python src/hibs_predictor/web.py"
    else:
        print("⚠️  Virtual environment not found, using system Python...")
        cmd = "python src/hibs_predictor/web.py"

    print("🚀 Starting Flask server...")

    # Start Flask in subprocess
    process = subprocess.Popen(
        cmd,
        shell=True,
        cwd=str(script_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to start
    print("⏳ Waiting for server to start...")
    time.sleep(4)

    # Check if server is running
    try:
        import requests
        response = requests.get("http://127.0.0.1:5000", timeout=5)
        if response.status_code == 200:
            print("✅ Server started successfully!")
        else:
            print("⚠️  Server responded but with status:", response.status_code)
    except:
        print("❌ Server failed to start. Check console for errors.")

    # Open browser
    url = "http://127.0.0.1:5000"
    print(f"🌐 Opening {url} in your browser...")
    webbrowser.open(url)

    print()
    print("🎯 Dashboard loaded with next 48h fixtures!")
    print("📊 Features: ML predictions, odds, BTTS, form data")
    print()
    print("Press Ctrl+C in terminal to stop the server")
    print()

    try:
        process.wait()
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except:
            process.kill()

if __name__ == "__main__":
    main()
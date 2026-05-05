#!/usr/bin/env python3
"""hibs.bet — One-Click Launcher"""

import os
import sys
import time
import webbrowser
import subprocess
from pathlib import Path

BANNER = """
┌────────────────────────────────────────────────────┐
│                                                    │
│   ██╗  ██╗██╗██████╗ ███████╗  .bet          │
│   ██║  ██║██║██╔══██╗██╔════╝               │
│   ███████║██║██████╔╝███████╗               │
│   ██╔══██║██║██╔══██╗╚════██║               │
│   ██║  ██║██║██████╔╝███████║               │
│   ╚═╝  ╚═╝╚═╝╚═────╝ ╚══════╝               │
│                                                    │
│   Edinburgh Betting Intelligence                   │
│   Scottish · English · European · International   │
└────────────────────────────────────────────────────┘
"""

def main():
    script_dir = Path(__file__).parent
    print(BANNER)
    env_file = script_dir / ".env"
    if not env_file.exists():
        print("\u274c  No .env file found! Copy .env.example to .env and add your API keys.")
        input("Press Enter to exit...")
        return
    with open(env_file) as f:
        if "your_" in f.read():
            print("\u26a0\ufe0f   .env has placeholder values. App will run with limited data.\n")
    venv_pip = script_dir / ".venv" / "bin" / "pip"
    req = script_dir / "requirements.txt"
    if venv_pip.exists() and req.exists():
        print("\U0001f4e6  Checking dependencies...")
        subprocess.run([str(venv_pip), "install", "-q", "-r", str(req)], check=False)
    venv_python = script_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable
    web_script = script_dir / "src" / "hibs_predictor" / "web.py"
    print("\U0001f680  Starting hibs.bet...")
    process = subprocess.Popen(
        [python_cmd, str(web_script)],
        cwd=str(script_dir),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url = "http://127.0.0.1:5000"
    print(f"\u23f3  Waiting for server at {url}...")
    for _ in range(30):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            pass
    print(f"\u2705  Ready \u2014 opening {url}")
    webbrowser.open(url)
    print("\n   Press Ctrl+C to stop\n")
    try:
        for line in process.stdout:
            print("   ", line, end="")
    except KeyboardInterrupt:
        print("\n\U0001f6d1  Shutting down...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
    print("\U0001f44b  Goodbye!")

if __name__ == "__main__":
    main()

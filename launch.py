#!/usr/bin/env python3
"""hibs.bet — One-Click Launcher. Run: python3 launch.py"""

import os, sys, time, webbrowser, subprocess
from pathlib import Path

def main():
    root = Path(__file__).parent
    print("\n╔" + "═"*44 + "╗")
    print("║  ██╗  ██╗██╗██████╗ ███████╗  .bet        ║")
    print("║  ██║  ██║██║██╔══██╗██╔════╝             ║")
    print("║  ███████║██║██████╔╝███████╗             ║")
    print("║  ██╔══██║██║██╔══██╗╚════██║             ║")
    print("║  ██║  ██║██║██████╔╝███████║             ║")
    print("║  Edinburgh Betting Intelligence          ║")
    print("╚" + "═"*44 + "╝\n")

    # Check .env
    env = root / ".env"
    if not env.exists():
        print("❌  .env not found. Copy .env.example and add your API keys.")
        input("Press Enter to exit...")
        return
    with open(env) as f:
        content = f.read()
    if "your_" in content:
        print("⚠\ufe0f   Some API keys are still placeholders — limited data may show.\n")

    # Kill anything on port 5000
    try:
        result = subprocess.run(["lsof","-ti",":5000"], capture_output=True, text=True)
        pids = result.stdout.strip()
        if pids:
            for pid in pids.split():
                subprocess.run(["kill","-9",pid], capture_output=True)
            print("🔄  Cleared port 5000")
            time.sleep(0.5)
    except Exception:
        pass

    # Clear stale cache
    cache_dir = root / ".cache"
    if cache_dir.exists():
        cleared = 0
        for f in cache_dir.glob("*.json"):
            try:
                f.unlink()
                cleared += 1
            except Exception:
                pass
        if cleared:
            print(f"🗑\ufe0f   Cleared {cleared} cached files for fresh data")

    # Install deps
    venv_pip = root / ".venv" / "bin" / "pip"
    if venv_pip.exists():
        print("📦  Checking dependencies...")
        subprocess.run([str(venv_pip),"install","-q","-r",str(root/"requirements.txt")], check=False)

    python = str(root/".venv"/"bin"/"python") if (root/".venv"/"bin"/"python").exists() else sys.executable
    script = root / "src" / "hibs_predictor" / "web.py"

    print("🚀  Starting hibs.bet...")
    proc = subprocess.Popen([python, str(script)], cwd=str(root),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    url = "http://127.0.0.1:5000"
    print(f"⏳  Loading data from APIs (first load may take 30-60s)...")
    for _ in range(60):
        time.sleep(0.5)
        try:
            import urllib.request
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            pass

    print(f"✅  Ready — opening {url}")
    webbrowser.open(url)
    print("\n   ℹ\ufe0f  Tap any fixture card to expand full analysis")
    print("   Press Ctrl+C to stop\n")

    try:
        for line in proc.stdout:
            if any(x in line for x in ["ERROR","Exception","Traceback","Running on"]):
                print("  ", line, end="")
    except KeyboardInterrupt:
        print("\n🛑  Stopping hibs.bet...")
        proc.terminate()
        try: proc.wait(timeout=5)
        except: proc.kill()
    print("👋  Goodbye!")

if __name__ == "__main__":
    main()

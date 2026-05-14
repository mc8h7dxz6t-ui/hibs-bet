#!/bin/bash
# Double-click this file in Finder to launch hibs-bet via Streamlit.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
  osascript -e 'display dialog "hibs-bet cannot start without a .env file in the project root. Copy .env.example and fill in your API keys." buttons {"OK"} default button "OK"'
  exit 1
fi

PYTHON=${PYTHON:-python3}
if [ -f ".venv/bin/activate" ]; then
  source ".venv/bin/activate"
  PYTHON=${PYTHON:-python}
fi

if ! command -v streamlit >/dev/null 2>&1; then
  echo "Installing Streamlit..."
  pip install streamlit
fi

streamlit run launch/streamlit_app.py --server.port=8501

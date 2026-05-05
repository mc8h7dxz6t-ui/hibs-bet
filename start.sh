#!/bin/bash
# HibsBetting One-Click Launcher

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=${PYTHON:-python3}

echo "🟤💛 HibsBetting — Advanced Betting Intelligence"
echo "═══════════════════════════════════════════════════"
echo ""

# Check if .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "❌ No .env file found!"
    echo "Please create .env file with your API keys:"
    echo "cp .env.example .env"
    echo "Then edit .env with your API keys"
    echo ""
    exit 1
fi

# Activate virtual environment
if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    echo "🔧 Activating virtual environment..."
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "⚠️  Virtual environment not found. Using system Python."
fi

echo "📦 Checking dependencies..."
python -c "import flask, pandas, sklearn, requests, dotenv" 2>/dev/null || {
    echo "Installing requirements..."
    pip install -q -r requirements.txt
}

echo ""
echo "🚀 Starting Flask server..."

echo "📱 Opening browser to fixtures dashboard..."

echo ""

python src/hibs_predictor/web.py &
FLASK_PID=$!

sleep 3

if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:5000"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:5000"
elif command -v start >/dev/null 2>&1; then
    start "http://127.0.0.1:5000"
else
    echo "Please open: http://127.0.0.1:5000"
fi

echo "✅ App launched successfully!"
echo "🌐 Dashboard: http://127.0.0.1:5000"
echo "🎯 Acca Builder: http://127.0.0.1:5000/acca"
echo ""
echo "Press Ctrl+C to stop the server"

wait $FLASK_PID

# hibs-bet quick start

## 🚀 One-Click Launch (Recommended)

**Double-click `Run-hibs-streamlit.command`** in this folder to start the app instantly.

For the Flask web dashboard instead, double-click **`Run-hibs-bet.command`** or **`HibsBet.command`** in this folder (same script). If port 5000 or 5002 is busy, the launcher picks the next free port (5000 → 5001 → 5002 → …) and opens the correct URL.

Desktop shortcut: **`~/Desktop/HibsBet.command`** runs the same launcher (no longer hard-coded to 5002).

**Logs:** `logs/hibs-bet.log` (rotating, 5×5MB) plus prediction audit DB at `data/prediction_audit.sqlite` when `HIBS_PREDICTION_LOG_ENABLED=1` (on by default in the launcher).
- Check for your `.env` file
- Activate the virtual environment
- Install Streamlit if needed
- Open the dashboard at `http://localhost:8501`

## 📋 Manual Setup (If Needed)

If the one-click launcher doesn't work:

### 1. Setup Environment
```bash
# Copy the example config
cp .env.example .env

# Edit .env and add your API keys:
# API_SPORTS_FOOTBALL_KEY=your_key_here
# FOOTBALL_DATA_ORG_KEY=your_key_here
# SPORTSMONK_KEY=your_key_here
```

### 2. Install Dependencies
```bash
# Activate virtual environment
source .venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 3. Run the App

**Option A: Streamlit (Recommended)**
```bash
streamlit run launch/streamlit_app.py
```
Opens at `http://localhost:8501`

**Option B: Flask**
```bash
python src/hibs_predictor/web.py
```
Opens at `http://127.0.0.1:5000`

## 🔑 API Keys Required

Get free API keys from:
- [API-Sports Football](https://api-sports.io/)
- [Football-Data.org](https://www.football-data.org/)
- [SportsMonk](https://sportsmonk.com/)

## 🐛 Troubleshooting

**"No .env file found"**
- Copy `.env.example` to `.env`
- Add your API keys to `.env`

**"Virtual environment not found"**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**App doesn't start**
- Check your API keys are valid
- Try running: `python -c "import requests; print('Network OK')"`

## 📱 What You'll See

- **UK leagues first**: Scotland, Premier League, Europa League
- **Compact fixture list**: KO time, teams, odds, predictions
- **Expandable details**: Last 6 results, BTTS chance, xG, best bets
- **Real-time data**: Refreshes every 10 minutes

## 🎯 Features

- ML-powered match predictions
- Live bookmaker odds comparison
- BTTS probability analysis
- Expected goals (xG) calculations
- Value betting opportunities
- Form analysis from recent matches

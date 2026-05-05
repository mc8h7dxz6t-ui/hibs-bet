# HibsBetting Quick Start

## 🚀 One-Click Launch (Recommended)

**Double-click `RunHibsStreamlit.command`** in this folder to start the app instantly.

That's it! The launcher will:
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

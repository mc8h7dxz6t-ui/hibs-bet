# 🟤💛 HibsBetting Quick Start

## One-Command Launch

### macOS / Linux

```bash
bash start.sh
```

### Windows

```bash
start.bat
```

This will:
1. Check for dependencies (install if needed)
2. Prompt for API keys on first run
3. Launch the web dashboard at http://127.0.0.1:5000

## What You'll See

### Dashboard Features

- **Next 48 Hours** — Upcoming fixtures across UK and European leagues
- **Team Form** — Last 10 games (W/D/L) for home and away teams
- **BTTS Stats** — Both Teams To Score percentage from last 10 matches
- **Recent Results** — Expandable dropdown showing last 5 match results for each team
- **League Info** — Color-coded by league (Scottish Premiership, EPL, Europa League, etc.)

### Dropdown Menu

Click any fixture card to expand and see:
- Win/Draw/Loss counts
- BTTS occurrences
- Recent match scores and dates
- Side-by-side team comparison

## Manual Commands

```bash
# One-time API key setup
python3 src/hibs_predictor/main.py setup

# Launch web dashboard
python3 src/hibs_predictor/main.py web

# Train ML model
python3 src/hibs_predictor/main.py train

# Predict a fixture
python3 src/hibs_predictor/main.py predict \
  --home "Hibernian" \
  --away "Celtic" \
  --odds-home 2.20 \
  --odds-draw 3.40 \
  --odds-away 3.00 \
  --league "Scottish Premiership"
```

## Free API Keys

Get yours from:

1. **API-Sports Football** (recommended)
   - https://www.api-football.com
   - Free tier: 300 requests/day, excellent coverage
   
2. **Football-Data.org**
   - https://www.football-data.org
   - Free tier: 100 requests/month, high-quality data
   
3. **SportsMonk**
   - https://www.sportmonks.com
   - Free tier: 150 requests/hour

## Architecture

```
HibsBetting/
├── src/hibs_predictor/
│   ├── __init__.py
│   ├── api_clients.py       # API integrations with caching
│   ├── config.py             # League IDs and rate limit config
│   ├── cache.py              # Local JSON caching (4-hour TTL)
│   ├── rate_limiter.py       # Tracks API calls per service
│   ├── features.py           # Feature engineering (form, odds, etc.)
│   ├── model.py              # ML model training/prediction
│   ├── main.py               # CLI interface
│   └──                 # Flask dashboard app
├── templates/
│   ├── base.html             # Base layout
│   ├── dashboard.html        # Main dashboard
│   └── setup.html            # API key entry
├── start.sh                  # macOS/Linux launcher
├── start.bat                 # Windows launcher
├── requirements.txt          # Python dependencies
├── .env.example              # API key template
└── README.md
```

## Rate Limiting & Caching

- **Caching:** All API responses cached locally for 4 hours
- **Rate Limits:** Tracked per service, resets hourly
- **Free-Tier Safe:** Built-in checks prevent exceeding limits
- **Fallback:** Uses sample data if APIs unavailable

## Notes

- This is a learning project, not financial advice
- Always use predictions responsibly
- Edinburgh-themed project for Hibernian FC supporters
- All data from public free APIs

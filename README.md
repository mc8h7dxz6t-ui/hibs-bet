# hibs-bet

An advanced bet predictor for UK and European football leagues with Edinburgh/Hibernian theme. Features sophisticated ensemble ML models, multi-API data integration, and professional-grade value betting detection.

## What's Included

### 🧠 **Advanced Betting Engine**
- **Ensemble Models**: Random Forest + Gradient Boosting for predictions
- **23 Advanced Features**: Team strength, form, xG, home/away factors
- **Value Bet Detection**: Identifies profitable bets using Kelly Criterion
- **Odds Analysis**: Aggregates bookmaker odds and calculates ROI

### 📊 **Multi-API Integration**
- **API-Sports Football**: Fixtures, odds, team stats, xG (300 req/day)
- **Football-Data.org**: Premium league data (100 req/month)
- **SportsMonk**: Historical data and statistics (150 req/hour)
- **Odds API**: Live odds from 50+ bookmakers (500 req/day)
- **Stats API**: Advanced analytics and xG metrics (150 req/hour)

### 🌐 **Web Dashboard**
- **Next 48 Hours**: Auto-filtered fixtures with predictions
- **Team Strength Metrics**: Attack/Defence/Form ratings
- **Value Bets**: Highlighted with expected ROI%
- **Expected Goals**: xG analysis for each matchup
- **BTTS Probability**: Both Teams To Score prediction

### ⚙️ **Smart Architecture**
- **Intelligent Caching**: 1-12 hour TTL by data type
- **Rate Limiting**: Respects all free-tier API limits
- **One-Time Setup**: Interactive API key configuration
- **Fallback Mode**: Uses sample data if APIs unavailable

## Project folder

**Work here:** `~/Applications` (also `~/hibs-betting-app` → same folder). See `PROJECT_LOCATIONS.md`.

## Quick Start

### 1. Install & Setup

```bash
cd ~/Applications
python3 -m pip install -r requirements.txt
python3 src/hibs_predictor/main.py setup
```

### 2. Add Your API Keys

Get free keys from:
- [API-Sports](https://www.api-football.com)
- [Football-Data.org](https://www.football-data.org)
- [SportsMonk](https://www.sportmonks.com)
- [Odds API](https://the-odds-api.com)
- [Stats API](https://www.api-football.com)

Or manually edit `.env`:
```env
API_SPORTS_FOOTBALL_KEY=your_key
FOOTBALL_DATA_ORG_KEY=your_key
SPORTSMONK_KEY=your_key
ODDS_API_KEY=your_key
STATS_API_KEY=your_key
```

### 3. Launch Dashboard

```bash
bash start.sh              # macOS/Linux
start.bat                  # Windows
```

Visit: **http://127.0.0.1:5000**

## Dashboard Features

### Predictions
- Home/Draw/Away win probabilities
- Model confidence score (0-100%)
- Predicted match outcome

### Value Betting
- **Best Bet**: Highest ROI opportunity
- **Expected ROI %**: (Model Prob - Bookmaker Prob) / Bookmaker Prob
- **Kelly Criterion**: Optimal bet sizing for bankroll
- **All Available Bets**: Complete value analysis

### Match Analytics
- Team form percentages (last 10 games)
- Team strength ratings
- Expected Goals (xG): Home vs Away
- Both Teams To Score (BTTS) probability
- Bookmaker odds comparison

## Commands

```bash
# Web dashboard with predictions
python3 src/hibs_predictor/main.py web

# Re-configure API keys
python3 src/hibs_predictor/main.py setup

# Train ML model
python3 src/hibs_predictor/main.py train

# Predict single fixture
python3 src/hibs_predictor/main.py predict \
  --home "Hibernian" \
  --away "Celtic" \
  --odds-home 2.20 \
  --odds-draw 3.40 \
  --odds-away 3.00 \
  --league "Scottish Premiership"
```

## Betting Engine Breakdown

### Team Strength Calculation
```
Strength = (Attack 40% + Defence 20% + Form 30% + Venue 10%)
```

### Value Bet Formula
```
Value = Model Probability - Bookmaker Implied Probability
ROI = (Value / Implied Probability) × 100%
```

### Kelly Criterion Sizing
```
Bet Size = (Win Prob × Odds - 1) / (Odds - 1) × 25%
```
(Limited to 10% of bankroll for risk management)

## Supported Leagues

- 🏴󠁧󠁢󠁥󠁮󠁧󠁿 **UK**: Premier League, Championship, Scottish Premiership
- 🇪🇸 **Europe**: La Liga, Serie A, Bundesliga, Ligue 1
- 🏆 **International**: UEFA Europa League

## Architecture

```
hibs-bet/
├── src/hibs_predictor/
│   ├── betting_engine.py       # ML models + value detection
│   ├── data_aggregator.py      # Multi-API data enrichment
│   ├── api_clients.py          # Enhanced API integrations
│   ├── features.py             # Feature engineering
│   ├── model.py                # Training utilities
│   ├── cache.py                # Smart caching (TTL)
│   ├── rate_limiter.py         # API rate tracking
│   ├── config.py               # League & API config
│   ├── main.py                 # CLI interface
│   └── web.py                  # Flask dashboard
├── templates/                  # HTML templates
├── start.sh / start.bat       # One-click launchers
└── BETTING_ENGINE.md          # Detailed documentation
```

## Data quality (DQ) and 90% target

Each fixture gets a **0–100% data quality** score from weighted inputs (team IDs, last-10 form, season stats, table position, xG source, 1X2 odds, side markets, supplemental context, injuries). Block weights are defined in `src/hibs_predictor/data_quality.py` (xG is 18 points max; 1X2 book prices 19).

**Realistic ceilings (typical full 7-day window, with APIs configured):**

| League tier | Typical ≥90% | Typical ≥85% | Main blockers below 90% |
|-------------|--------------|--------------|-------------------------|
| EPL / top-5 with Understat | 55–70% | 75–85% | Missing side markets, cup rounds without fixture xG |
| Scottish Prem / Championship (FBref schedule) | 45–60% | 65–80% | Proxy xG until schedule match; sparse injuries |
| UEFA cups / lower tiers | 15–35% | 40–55% | No team IDs, no league table, goals-only xG |
| Friendlies / unmapped teams | &lt;10% | &lt;20% | No IDs, no odds, no standings |

**Raise coverage toward 90%:**

```env
HIBS_TARGET_DQ_PCT=90          # second-pass deep enrich until 90% or 2 retries (75–89% band)
HIBS_DEEP_ENRICH=1             # same target when TARGET unset (defaults to 90)
HIBS_MAX_DATA=1                # full API + StatsBomb light scrapers
HIBS_ENRICH_PRIORITY_TODAY=1   # fetch leagues with a kickoff today first (API budget)
```

Measure before/after: `python3 scripts/measure_dq_7d.py` (reports ≥78%, ≥85%, ≥90%, avg, and weak blocks on 78–89% rows).

Dashboard: use the **90%+ data only** chip to filter to the high-trust pool without hiding other leagues.

## Performance Notes

- **Accuracy**: Baseline ~55% on outcome prediction
- **Value Bets**: Identified when ROI > 3%
- **Confidence**: Model outputs 0-100% prediction confidence
- **Caching**: Reduces API calls by ~80-90%
- **Rate Limits**: Safe operation within all free tiers

## Free-Tier Safety

✓ All APIs use free tiers (no payment required)  
✓ Smart caching prevents redundant calls  
✓ Rate limiter tracks usage per service  
✓ Auto-resets hourly/daily by provider  
✓ Fallback to sample data if limits hit  

## Risk Disclaimer

- This is an analytical tool for learning and research
- Betting always carries financial risk
- Past performance ≠ future results
- Use predictions responsibly
- Start with small stakes
- Validate model before betting real money

## Betting Tips

✅ Only bet on **value bets** (positive expected value)  
✅ Use **Kelly Criterion** for optimal sizing  
✅ Track all predictions for validation  
✅ Compare odds across bookmakers  
✅ Long-term data matters for accuracy  

## Fixture cache (v22)

On-disk fixture cache keys use **v22** (see `_FIXTURE_CACHE_VERSION` in `web.py`). After upgrading, clear fixture caches (dashboard **Refresh**, `POST /api/cache/clear`, or delete `fixtures_*` / `all_fixtures_*` / `enriched_fixture_*` under `HIBS_CACHE_DIR`, default `.cache`) so BTTS/Win columns, deep-enrich fields, and dual value-finder data load; older cache files may omit these fields.

## Production deploy (hibs-bet.co.uk)

Server path: `/opt/hibs-bet` (see `deploy/hibs-bet.service`). Full checklist: [deploy/README.md](deploy/README.md).

```bash
# On the server (after git pull or rsync)
cd /opt/hibs-bet
git pull   # or your deploy sync
.venv/bin/pip install -r requirements.txt   # if requirements changed

# Secrets: copy from .env.example — never commit .env
# Recommended prod flags (in /opt/hibs-bet/.env):
#   HIBS_PREDICTION_LOG_ENABLED=1
#   HIBS_MAX_DATA=1
#   HIBS_CACHE_DIR=/opt/hibs-bet/.cache

# Clear stale fixture cache after code/cache-version upgrades (v22)
rm -f .cache/fixtures_* .cache/all_fixtures_* .cache/enriched_fixture_* 2>/dev/null || true
# Or use dashboard Refresh / POST /api/cache/clear

sudo cp deploy/hibs-bet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart hibs-bet
sudo systemctl status hibs-bet
```

Gunicorn listens on **0.0.0.0:8000**; put nginx/Caddy in front for HTTPS on **hibs-bet.co.uk**.

## Documentation

- [Advanced Betting Engine](BETTING_ENGINE.md) — Detailed feature breakdown
- [Enhancements](ENHANCEMENTS.md) — Architecture overview
- [Quick Start](QUICKSTART.md) — Fast reference guide

## Get Started Now

```bash
bash start.sh
```

The interactive setup will guide you through adding API keys and launch the dashboard.

---

**🟤💛 hibs-bet — Advanced Football Betting Intelligence for Edinburgh**

*Built with ❤️ for Hibernian FC supporters and analytical bettors*


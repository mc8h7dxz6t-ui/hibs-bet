# 🟤💛 HibsBetting — Enhancements Summary

## What's New

### 1. **Real League & Endpoint Mapping** ✓
- UK Leagues: EPL, Championship, Scottish Premiership
- European: La Liga, Serie A, Bundesliga, Ligue 1
- International: Europa League
- Each league mapped to correct free-tier API IDs for Football-Data.org, API-Sports, SportsMonk

**Files:** `src/hibs_predictor/config.py`

### 2. **Smart Caching System** ✓
- Local JSON caching with 4-hour TTL
- Automatically caches all API responses
- Reduces redundant API calls and respects free-tier limits
- Cache files stored in `.cache/` directory

**Files:** `src/hibs_predictor/cache.py`

### 3. **Rate Limiting Tracker** ✓
- Monitors API calls per service (hourly reset)
- Tracks usage against free-tier limits:
  - Football-Data.org: 100/hour
  - API-Sports: 150/hour
  - SportsMonk: 150/hour
- Blocks requests if limits exceeded

**Files:** `src/hibs_predictor/rate_limiter.py`

### 4. **Enhanced API Clients** ✓
- Integrated caching & rate limiting into base client
- Football-Data.org: `fetch_team_matches()`, `parse_form_from_matches()`
- API-Sports: `fetch_fixtures_by_league()`, `fetch_team_last_matches()`
- SportsMonk: `fetch_team_matches()`
- All methods return form, goals, BTTS data

**Files:** `src/hibs_predictor/api_clients.py`

### 5. **Flask Web Dashboard** ✓
**Features:**
- Next 48 hours of upcoming fixtures (auto-filtered)
- Team form display (last 10 games: W/D/L)
- BTTS percentage from recent matches
- Expandable dropdown menus per fixture
- Recent match results (last 5) for each team
- League color-coding and fixture timestamps
- Responsive grid layout

**Files:** `src/hibs_predictor/web.py`, `templates/dashboard.html`

### 6. **Setup & Initialization** ✓
- Interactive `setup` command for first-time API key entry
- Prompts user for Football-Data.org, API-Sports, SportsMonk keys
- Saves to `.env` automatically
- Fallback to setup screen if `.env` missing

**Files:** `src/hibs_predictor/main.py` (run_setup function)

### 7. **One-Click Launch Scripts** ✓
- `start.sh` — macOS/Linux launcher
- `start.bat` — Windows launcher
- Auto-dependency check and install
- Auto-runs setup on first launch
- Directly opens dashboard

## Usage Flow

### First Time

```bash
bash start.sh              # macOS/Linux
start.bat                  # Windows
```

→ Prompts for API keys → Installs deps → Launches dashboard at http://127.0.0.1:5000

### Subsequent Launches

```bash
bash start.sh              # Dashboard opens instantly
```

### Manual Commands

```bash
python3 src/hibs_predictor/main.py setup          # Re-setup API keys
python3 src/hibs_predictor/main.py web            # Launch dashboard
python3 src/hibs_predictor/main.py train          # Train ML model
python3 src/hibs_predictor/main.py predict ...    # Predict single match
```

## Technical Architecture

### API Client Layer (with caching & rate limiting)
```
api_clients.py
  ├── FootballDataOrgClient    → EPL, Championship, SPL, Europa League
  ├── ApiSportsFootballClient  → 39+ leagues, live odds
  └── SportsMonkClient         → Alternative league coverage
  
  All use:
  ├── Cache (4hr TTL, JSON storage)
  └── RateLimiter (hourly tracking)
```

### Feature Pipeline
```
features.py
  ├── build_feature_matrix()        → Odds, form, league factor
  └── normalize_strength()          → Team stats normalization
```

### ML Model
```
model.py
  ├── RandomForestClassifier (150 estimators)
  ├── StandardScaler normalization
  └── 18% test split for validation
```

### Web Layer
```
web.py (Flask)
  ├── / (dashboard view)
  ├── /api/fixtures (JSON endpoint)
  └── /api/team-form/<id> (team stats)

templates/
  ├── base.html       (layout + Hibs branding)
  ├── dashboard.html  (fixture grid + forms)
  └── setup.html      (API key entry)
```

## Data Flow: Dashboard Loading

1. User opens http://127.0.0.1:5000
2. Flask loads `.env` for API keys
3. Checks cache for "next_48h_fixtures"
4. If expired, fetches from API-Sports for each league
5. Filters fixtures within 48-hour window
6. For each fixture, fetches last 10 team matches
7. Parses W/D/L, BTTS, recent results
8. Renders dashboard with dropdown menus
9. User clicks dropdown → displays form data

## Free-Tier Safety

✓ Caches all responses (max 100 API calls/day)
✓ Rate limiter prevents over-requests
✓ Respects all free-tier hourly limits
✓ Falls back to sample data if APIs unavailable
✓ ~2-3 API calls per dashboard refresh

## File Manifest

| File | Purpose |
|------|---------|
| `src/hibs_predictor/config.py` | League IDs, rate limits |
| `src/hibs_predictor/cache.py` | JSON caching with TTL |
| `src/hibs_predictor/rate_limiter.py` | API call tracking |
| `src/hibs_predictor/api_clients.py` | Enhanced API clients |
| `src/hibs_predictor/web.py` | Flask app + routes |
| `src/hibs_predictor/main.py` | CLI (setup, web, train, predict) |
| `templates/base.html` | HTML base + Hibs styling |
| `templates/dashboard.html` | Fixture grid + forms |
| `templates/setup.html` | API key entry screen |
| `start.sh` | macOS/Linux launcher |
| `start.bat` | Windows launcher |
| `QUICKSTART.md` | Quick reference |

## Next Steps (Optional)

- Add player-level stats integration
- Implement live odds scraping
- Add bet slip calculator
- Persist historical predictions
- Mobile-responsive improvements
- Automated daily email reports

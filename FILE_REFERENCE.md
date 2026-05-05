# HibsBetting — Complete File Reference

## 📁 Directory Structure with Descriptions

```
HibsBetting/
│
├─ 📄 README_FEATURES.md ...................... Feature overview & installation guide
├─ 📄 README.md (existing) ................... Quick start reference
├─ 📄 ACCA_BUILDER_GUIDE.md .................. Step-by-step user guide (betting)
├─ 📄 TECHNICAL_DOCS.md ...................... Deep architecture & API details
├─ 📄 IMPLEMENTATION_CHECKLIST.md ............ Complete feature checklist
├─ 📄 SETUP_SUMMARY.py ....................... Display system overview
│
├─ src/hibs_predictor/
│  │
│  ├─ __init__.py ............................ Package initialization
│  │
│  ├─ api_clients.py (~900 lines) ............ 5 API integrations
│  │  ├─ BaseApiClient ...................... Base class with caching
│  │  ├─ ApiSportsFootballClient ............ Premier API for fixtures
│  │  ├─ FootballDataOrgClient .............. Premium EU football data
│  │  ├─ SportsMonkClient ................... Historical match data
│  │  ├─ OddsApiClient ...................... Live bookmaker odds
│  │  └─ StatsApiClient ..................... Advanced xG metrics
│  │
│  ├─ betting_engine.py (~600 lines) ........ ML prediction engine
│  │  ├─ TeamStrengthCalculator ............ Attack/defense metrics
│  │  ├─ OddsAnalyzer ....................... Probability & Kelly Criterion
│  │  └─ BettingEngine ....................... Ensemble ML + predictions
│  │
│  ├─ data_aggregator.py (~400 lines) ....... Multi-API enrichment
│  │  └─ DataAggregator ..................... Combines all API data
│  │
│  ├─ cache.py (~200 lines) .................. TTL-based caching
│  │  └─ Cache .............................. JSON file storage with expiration
│  │
│  ├─ rate_limiter.py (~250 lines) .......... API rate limiting
│  │  └─ RateLimiter ........................ Per-service hourly tracking
│  │
│  ├─ config.py (~150 lines) ................ Configuration system
│  │  ├─ LEAGUES ............................ 8 league definitions
│  │  ├─ HIBS_LEAGUE_FOCUS ................. Priority leagues
│  │  └─ MAX_REQUESTS_PER_HOUR ............. Rate limit per service
│  │
│  └─ web.py (~350 lines) ................... Flask web application
│     ├─ fetch_next_48h_fixtures() ......... Get predictions for next 48h
│     ├─ index() ............................ GET / dashboard route
│     ├─ acca_builder() ..................... GET /acca builder interface
│     ├─ api_fixtures() ..................... GET /api/fixtures endpoint
│     ├─ api_prediction() ................... GET /api/prediction/<id> endpoint
│     ├─ place_bet() ........................ POST /api/place-bet endpoint
│     └─ _generate_affiliate_url() ......... William Hill/Ladbrokes URLs
│
├─ templates/
│  │
│  ├─ base.html (~450 lines) ............... Master layout template
│  │  ├─ Header with navigation ............ Dashboard / Acca Builder links
│  │  ├─ Betting panel structure .......... Left sidebar for acca
│  │  ├─ Fixtures grid ..................... Fixture card layout
│  │  ├─ JavaScript functions .............. addToAcca(), updateAccaOdds()
│  │  └─ Styling ........................... Hibs branding, gradients, animations
│  │
│  ├─ dashboard.html (~350 lines) ......... Predictions display page
│  │  ├─ Fixture cards ..................... Prediction badges, confidence
│  │  ├─ Value bet highlighting ........... +3% ROI opportunities
│  │  ├─ Match statistics ................. Form, strength, xG
│  │  ├─ Expandable details ............... Full analysis breakdown
│  │  └─ Navigation header ................ Links to both pages
│  │
│  └─ acca_builder.html (~400 lines) ...... Acca builder interface
│     ├─ Left panel ........................ Acca selection + calculations
│     ├─ Right panel ....................... Quick fixture list
│     ├─ Quick-add buttons ................. Click odds to add
│     ├─ JavaScript ........................ Selection management
│     ├─ Affiliate links ................... William Hill & Ladbrokes
│     └─ Mobile responsive layout ......... Touch-friendly design
│
├─ static/
│  │
│  ├─ hibs_badge.svg (~200 lines) ......... Hibernian FC badge
│  │  ├─ Circular design ................... Outer ring #1a472a
│  │  ├─ Brown/yellow stripes ............ Authentic Hibs colors
│  │  ├─ Yellow H monogram ................ Center crest
│  │  ├─ "HIBERNIAN EST 1875" text ....... Curved around top
│  │  └─ Gold circle border ............... Decorative ring
│  │
│  └─ edinburgh_bg.svg (~300 lines) ....... Edinburgh skyline background
│     ├─ Edinburgh Castle ................. Simplified tower geometry
│     ├─ Arthur's Seat ................... Green hill (opacity 0.6)
│     ├─ Building skyline ................. Left, center, right with varying heights
│     ├─ Window lights .................... Yellow lights on buildings
│     ├─ Sky gradient ..................... #87CEEB to #E0F6FF
│     ├─ Yellow sun ....................... #FFD700 (opacity 0.8)
│     ├─ Green ground ..................... #2d5a1f
│     └─ Text overlay ..................... "HIBSBETTING — EDINBURGH"
│
├─ .cache/ (Auto-created)
│  ├─ next_48h_fixtures_EPL.json ......... Cached fixtures
│  ├─ next_48h_fixtures_SCOTLAND.json .... Cached fixtures
│  ├─ next_48h_fixtures_EUROPA_LEAGUE.json Cached fixtures
│  ├─ team_stats_<id>.json ............... Cached team data
│  ├─ odds_<id>.json ..................... Cached odds
│  └─ prediction_<id>.json ............... Cached predictions
│
├─ launcher.py (~80 lines) ................ Auto-launch script
│  ├─ Starts Flask server in subprocess .. Runs on 127.0.0.1:5000
│  ├─ Waits 3 seconds ....................... For server startup
│  ├─ Opens browser automatically ......... Uses webbrowser module
│  └─ Graceful shutdown ................... Handles Ctrl+C
│
├─ test_app.py (~200 lines) ............... Test suite (6 tests)
│  ├─ test_imports() ...................... Verify all modules load
│  ├─ test_config() ....................... Check configuration
│  ├─ test_cache() ........................ Validate caching
│  ├─ test_rate_limiter() ................ Test rate limiting
│  ├─ test_flask_routes() ................ Verify Flask routes
│  └─ test_templates() .................... Check template syntax
│
├─ requirements.txt ....................... Python dependencies
│  ├─ pandas>=2.0 ......................... Data manipulation
│  ├─ scikit-learn>=1.4 ................... ML models
│  ├─ requests>=2.31 ...................... HTTP library
│  ├─ python-dotenv>=1.0 .................. Environment config
│  ├─ joblib>=1.4 ......................... Model serialization
│  ├─ flask>=3.0 .......................... Web framework
│  └─ numpy>=1.24 ......................... Numerical computations
│
├─ .env.example ............................ API key template
│  ├─ FOOTBALL_DATA_ORG_KEY ............... Football-Data.org
│  ├─ SPORTSMONK_KEY ...................... SportsMonk
│  ├─ API_SPORTS_FOOTBALL_KEY ............ API-Sports
│  ├─ ODDS_API_KEY ........................ Odds API
│  └─ STATS_API_KEY ....................... Stats API
│
├─ .gitignore ............................ Git ignore patterns
│  ├─ .env ................................ Never commit secrets
│  ├─ .cache/ ............................. Cache files
│  ├─ .rate_limit_state.json ............. Rate limit state
│  ├─ __pycache__/ ........................ Python cache
│  └─ *.pyc ............................... Compiled Python
│
└─ .rate_limit_state.json (Auto-created) ... Rate limit tracking
   ├─ api_sports ........................... Count and reset time
   ├─ football_data_org ................... Count and reset time
   ├─ sportsmonk .......................... Count and reset time
   ├─ odds_api ............................. Count and reset time
   └─ stats_api ........................... Count and reset time

```

## 📚 Documentation Files

### README_FEATURES.md (~600 lines)
**Purpose**: Complete feature overview for users
- What you get (features overview)
- Installation instructions
- Configuration guide
- Running the app
- Usage examples
- API endpoints documentation
- Betting engine architecture
- Performance metrics
- Troubleshooting

### ACCA_BUILDER_GUIDE.md (~400 lines)
**Purpose**: Step-by-step user guide for betting
- Getting started
- Dashboard interface explanation
- How to build accas (5-step guide)
- Strategy tips (value betting, confidence management)
- Mobile compatibility
- API endpoints for developers
- Troubleshooting common issues
- Responsible gambling

### TECHNICAL_DOCS.md (~900 lines)
**Purpose**: Deep technical architecture documentation
- System architecture overview
- Data flow diagrams
- API integration details (all 5 APIs)
- Betting engine ML pipeline (23-feature vector)
- Model ensemble explanation (RF 60% + GB 40%)
- Confidence calibration details
- Value bet detection math
- Caching system strategy
- Rate limiting mechanism
- Prediction accuracy metrics
- Frontend JavaScript functions
- Deployment considerations

### IMPLEMENTATION_CHECKLIST.md (~300 lines)
**Purpose**: Complete feature checklist for verification
- 10 development phases (all ✓)
- Technical requirements verification
- Performance metrics
- Security checklist
- Deployment readiness
- User experience items
- Feature completeness matrix
- Quality assurance items
- Current status: PRODUCTION READY

## 🚀 Key Entry Points

### For Users
1. **Read First**: README_FEATURES.md or SETUP_SUMMARY.py
2. **Quick Start**: `python3 launcher.py`
3. **Learn Betting**: ACCA_BUILDER_GUIDE.md
4. **Troubleshoot**: TECHNICAL_DOCS.md "Troubleshooting" section

### For Developers
1. **Architecture**: TECHNICAL_DOCS.md (system overview)
2. **Code Entry**: src/hibs_predictor/web.py (Flask app)
3. **ML Engine**: src/hibs_predictor/betting_engine.py
4. **Data Source**: src/hibs_predictor/data_aggregator.py
5. **APIs**: src/hibs_predictor/api_clients.py

### For Deployment
1. **Checklist**: IMPLEMENTATION_CHECKLIST.md
2. **Dependencies**: requirements.txt
3. **Configuration**: .env.example → .env
4. **Startup**: launcher.py or `python3 -m hibs_predictor.web`

## 📊 Code Statistics

| Component | Lines | Status |
|-----------|-------|--------|
| api_clients.py | ~900 | ✅ Complete |
| betting_engine.py | ~600 | ✅ Complete |
| data_aggregator.py | ~400 | ✅ Complete |
| rate_limiter.py | ~250 | ✅ Complete |
| cache.py | ~200 | ✅ Complete |
| web.py | ~350 | ✅ Complete |
| config.py | ~150 | ✅ Complete |
| base.html | ~450 | ✅ Complete |
| dashboard.html | ~350 | ✅ Complete |
| acca_builder.html | ~400 | ✅ Complete |
| **TOTAL** | **~4,650** | **✅ COMPLETE** |

## 📖 Documentation Statistics

| Document | Lines | Audience |
|----------|-------|----------|
| README_FEATURES.md | ~600 | Users & Developers |
| ACCA_BUILDER_GUIDE.md | ~400 | End Users |
| TECHNICAL_DOCS.md | ~900 | Developers & Architects |
| IMPLEMENTATION_CHECKLIST.md | ~300 | Project Managers |
| SETUP_SUMMARY.py | ~400 | Quick Reference |
| **TOTAL DOCS** | **~2,600** | **Comprehensive** |

## 🎯 Quick Reference

### To Start App
```bash
python3 launcher.py
```

### To Test
```bash
python3 test_app.py
```

### To Run Flask Directly
```bash
python3 -m hibs_predictor.web
```

### To Check Syntax
```bash
python3 -m py_compile src/hibs_predictor/*.py
```

### To View Available Routes
```bash
python3 -c "from hibs_predictor.web import app; print([str(r) for r in app.url_map.iter_rules()])"
```

---

## ✅ All Files Present & Ready

- ✅ Core Python modules (7 files)
- ✅ HTML templates (3 files)
- ✅ SVG graphics (2 files)
- ✅ Configuration files (3 files)
- ✅ Documentation (5 major files + inline comments)
- ✅ Test suite (1 file)
- ✅ Launcher script (1 file)
- ✅ Hidden files (.env.example, .gitignore)

**Status**: 🚀 **PRODUCTION READY**

---

*Last Updated: January 2025 | HibsBetting v1.0*

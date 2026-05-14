# Advanced Betting Engine — Full API Integration

## Overview

Your hibs-bet predictor now includes a **professional-grade betting engine** that integrates data from **5 premium APIs** to provide sophisticated match predictions with value betting analysis.

## APIs Integrated

| API | Free Tier | Key Features |
|-----|-----------|--------------|
| **API-Sports Football** | 300 req/day | Fixtures, odds, team stats, xG, live data |
| **Football-Data.org** | 100 req/month | Premier League data, detailed standings |
| **SportsMonk** | 150 req/hour | Historical matches, team statistics |
| **Odds API** | 500 req/day | Live odds from multiple bookmakers |
| **Stats API** | 150 req/hour | Advanced statistics, expected goals |

## Betting Engine Features

### 1. **Team Strength Calculation**
```
Team Strength = (Attack 40% + Defence 20% + Form 30% + Home/Away 10%)
```
- **Attack Strength**: Goals scored vs expected goals
- **Defence Strength**: Goals conceded vs expected goals against
- **Form Strength**: Last 10 games W/D/L + xG differential
- **Home/Away Factor**: Performance multiplier by venue

### 2. **Advanced Feature Engineering (23 features)**
- Attack/Defence/Form metrics for both teams
- Odds from all bookmakers (implied probability)
- Expected Goals (xG) from stats APIs
- Team strength differentials
- League strength factors
- Home/away performance factors

### 3. **Ensemble Predictions**
- **Random Forest Classifier**: 200 trees, 60% weight
- **Gradient Boosting Classifier**: 150 trees, 40% weight
- Outputs: Home Win % | Draw % | Away Win %

### 4. **Value Bet Detection**
Identifies bets where:
```
Model Probability > Bookmaker Implied Probability + 3% Margin
```

For each value bet calculates:
- **Expected ROI %**: (Model Prob - Implied Prob) / Implied Prob × 100
- **Kelly Criterion**: Optimal bet sizing for bankroll growth
- **Confidence Score**: Model's prediction confidence (0-100%)

### 5. **Odds Analysis**
- Aggregates odds from multiple bookmakers
- Converts decimal odds to implied probabilities
- Identifies best odds for each outcome
- Detects market inefficiencies

### 6. **Expected Goals (xG)**
- Fetches actual xG from match data
- Calculates BTTS (Both Teams To Score) probability
- Provides goal-based match analysis

## Setup Your API Keys

### Step 1: Add Keys to `.env`

```bash
cp .env.example .env
```

Then add your keys:

```env
API_SPORTS_FOOTBALL_KEY=your_key_here
FOOTBALL_DATA_ORG_KEY=your_key_here
SPORTSMONK_KEY=your_key_here
ODDS_API_KEY=your_key_here
STATS_API_KEY=your_key_here
```

### Step 2: Get Free API Keys

1. **API-Sports Football** (Recommended)
   - https://www.api-football.com/register
   - 300 requests/day
   - Instant activation
   - Coverage: 50+ leagues

2. **Football-Data.org**
   - https://www.football-data.org/client/register
   - 100 requests/month
   - Email approval required
   - Coverage: Premium leagues only

3. **SportsMonk**
   - https://www.sportmonks.com/plans/free
   - 150 requests/hour
   - Instant activation
   - Coverage: 40+ leagues

4. **Odds API**
   - https://the-odds-api.com/
   - 500 requests/day
   - Instant activation
   - Coverage: 50+ sportsbooks

5. **Stats API**
   - https://www.api-football.com (alternate endpoint)
   - 150 requests/hour
   - Advanced statistics
   - Coverage: European leagues

## Running the Advanced Engine

### Launch Dashboard with Predictions

```bash
python3 src/hibs_predictor/main.py web
```

Visit: **http://127.0.0.1:5000**

### Dashboard Display

For each fixture, you'll see:

#### **Predictions**
- Home Win Probability
- Draw Probability
- Away Win Probability
- Model Confidence Score (0-100%)
- Predicted Match Outcome

#### **Odds & Value Bets**
- Bookmaker odds (Home/Draw/Away)
- Current market implied probabilities
- **Value Bets**: Outcomes where model > market with ROI%
- **Best Bet**: Highest ROI opportunity
- **Kelly Bet Size**: Recommended bet as % of bankroll

#### **Match Stats**
- Team form percentages
- Team strength ratings
- Expected Goals (xG): Home vs Away
- Both Teams To Score (BTTS) probability

#### **All Available Bets**
- Complete value bet analysis for every outcome
- Model probability vs implied probability
- Expected ROI for each bet
- Kelly Criterion sizing

## Betting Engine Code Structure

```
src/hibs_predictor/
├── betting_engine.py          # ML models, value detection
│   ├── TeamStrengthCalculator # Attack/Defence/Form metrics
│   ├── OddsAnalyzer          # Odds & probability analysis
│   └── BettingEngine         # Ensemble predictions
├── data_aggregator.py        # Multi-API data enrichment
│   └── DataAggregator        # Fetches & enriches fixtures
├── api_clients.py            # Enhanced API clients
│   ├── OddsApiClient         # Live bookmaker odds
│   └── StatsApiClient        # Advanced xG metrics
└── config.py                 # League strength factors
```

## Advanced Examples

### Get Enriched Fixture Data

```python
from hibs_predictor.data_aggregator import DataAggregator

aggregator = DataAggregator()
fixture = {
    "fixture": {"id": 123},
    "teams": {"home": {"id": 1}, "away": {"id": 2}}
}
enriched = aggregator.enrich_fixture(fixture, league_code="EPL")
```

### Generate Predictions with Value Bets

```python
from hibs_predictor.betting_engine import BettingEngine

engine = BettingEngine(aggregator.get_all_clients())
prediction = engine.predict_with_confidence(enriched)

print(f"Predicted: {prediction['predicted_outcome']}")
print(f"Confidence: {prediction['confidence']:.1%}")
print(f"Best Bet: {prediction['best_bet']} (ROI: +{prediction['best_bet_roi']:.1f}%)")
```

### Identify Value Bets Manually

```python
from hibs_predictor.betting_engine import OddsAnalyzer

model_probs = {"home": 0.45, "draw": 0.30, "away": 0.25}
bookmaker_odds = {"home": 2.00, "draw": 3.50, "away": 4.00}

value_bets = OddsAnalyzer.identify_value_bets(
    model_probs, 
    bookmaker_odds, 
    margin=0.05
)

for outcome, bet in value_bets.items():
    print(f"{outcome}: ROI +{bet['roi_percent']:.1f}%")
```

## Rate Limits & Caching

| Service | Limit | Reset | Cached |
|---------|-------|-------|--------|
| API-Sports | 150/hr | Hourly | 1-2 hrs |
| Football-Data | 100/hr | Hourly | 4-12 hrs |
| SportsMonk | 150/hr | Hourly | 4 hrs |
| Odds API | 500/day | Daily | 2 hrs |
| Stats API | 150/hr | Hourly | 6 hrs |

All responses are cached locally to minimize API calls. Caching TTL:
- **Fixtures**: 1-2 hours
- **Team Stats**: 6-12 hours
- **Odds**: 2 hours
- **xG Data**: 6 hours

## Betting Tips

### ✅ Best Practices
1. Only bet on **value bets** (ROI > 3%)
2. Use **Kelly Criterion** sizing for optimal growth
3. Track predictions vs results to validate model
4. Compare across multiple bookmakers for best odds
5. Combine multiple predictions for confidence

### ⚠️ Risk Management
- Never bet more than Kelly Criterion recommends
- Start with small stakes while validating
- Expected ROI requires long-term sample size
- Short-term variance is normal
- Betting always carries risk — use responsibly

## Model Performance Metrics

The ensemble model is evaluated on:
- Accuracy: % of correct outcome predictions
- ROI: Average return on value bets
- Precision: % of value bets that hit
- Calibration: Match between model confidence and actual results

## Troubleshooting

### API Keys Not Working?
- Check `.env` file format (no quotes needed)
- Verify keys are activated on provider websites
- Check rate limit status in `.rate_limit_state.json`

### No Value Bets Found?
- Bookmaker odds are fairly priced
- Model confidence is low (< 60%)
- Increase margin threshold (default 3%)

### Slow Dashboard Loading?
- Check internet connection
- Wait for API rate limits to reset
- Clear cache: `rm -rf .cache/`

### Import Errors?
- Reinstall dependencies: `pip install -r requirements.txt`
- Verify Python 3.8+: `python3 --version`

## Next Steps

1. Add your API keys to `.env`
2. Run: `python3 src/hibs_predictor/main.py web`
3. View predictions and value bets
4. Start tracking results for validation
5. Optimize betting strategy based on performance

## Support

For API documentation:
- [API-Sports Football](https://www.api-football.com/documentation)
- [Football-Data.org](https://www.football-data.org/client/documentation)
- [SportsMonk](https://www.sportmonks.com/docs)
- [Odds API](https://the-odds-api.com/api-documentation)

Remember: This is an analytical tool for learning. Betting always carries risk.

---

**🟤💛 hibs-bet — Edinburgh-Inspired Advanced Betting Intelligence**

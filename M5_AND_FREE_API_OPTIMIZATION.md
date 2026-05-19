# HibsBetting M5 & Free API Optimization Guide

## macOS App Bundles Setup

### Using the New .app Bundles

The project now includes native macOS app bundles that are optimized for Apple Silicon and free API usage:

**HibsBetting.app** (Flask)
- Location: `launch/HibsBetting.app`
- Double-click to run from Finder
- Main dashboard interface on port 5000

**HibsBetting-Streamlit.app** (Streamlit)
- Location: `launch/HibsBetting-Streamlit.app`
- Lightweight alternative interface on port 8501

### First Time Setup

1. Copy `.env.example` to `.env` in the project root
2. Add your API keys (see Free Tier APIs section below)
3. Ensure virtual environment is set up: `.venv/`
4. Double-click either app to launch

## Apple Silicon (M5/M4/M3) Optimizations

### Automatic Optimization
The `m5_optimization.py` module automatically:
- Detects Apple Silicon architecture
- Uses native arm64 libraries (NumPy, Pandas, scikit-learn)
- Optimizes thread counts for efficiency
- Configures BLAS libraries

### Manual Environment Setup (if needed)
```bash
export OPENBLAS_NUM_THREADS=7  # For M5 (8-core)
export MKL_NUM_THREADS=7
export VECLIB_MAXIMUM_THREADS=7
```

### Performance Tips
- **CPU**: M5 has plenty of performance; optimization focuses on efficiency
- **Memory**: 8GB+ recommended for full feature set
- **Threads**: Automatically limited to CPU count - 1 for battery efficiency
- **Caching**: Aggressive caching reduces API calls and improves responsiveness

## Free API Tier Optimization

### Free Tier Limits

| API | Limit | Strategy |
|-----|-------|----------|
| football-data.org | 100/day | Core league data |
| api-sports | 150/day | Alternative fixtures/stats |
| sportsmonk | 150/day | Backup data source |
| Odds API | 500/month | ~17/day, for odds only |
| Stats API | 150/day | Historical data |

### Smart Caching Strategy

The system automatically implements:

1. **Fixture Caching** (12 hours)
   - Fixtures rarely change within a day
   - Reuse for all prediction requests

2. **Team Stats Caching** (4 hours)
   - Stats update after matches complete
   - Balanced freshness vs API calls

3. **Odds Caching** (1 hour)
   - Odds change frequently
   - More aggressive refresh

4. **Predictions Caching** (12 hours)
   - Once calculated, predictions valid for ~12 hours
   - Only recalculate when new match data available

### League Priority Strategy

Focus on these leagues to minimize API calls:

1. **Scottish Premiership** (Primary - Hibernian's league)
2. **English Premier League** (High interest, widely available)
3. **UEFA Europa League** (Hibernian's European competition)

### Rate Limit Monitoring

Check current API usage:
```python
from src.hibs_predictor.rate_limiter import RateLimiter

limiter = RateLimiter()
limiter.print_usage_report()
```

Output shows:
- Current/daily limit per service
- Visual usage bar
- Warnings when approaching limits
- Time until reset

### Recommended Usage Patterns

#### Morning Update (7-8 AM)
- Fetch latest fixtures for upcoming weekend
- Update team form/stats
- Cache predictions for next 12 hours

#### Match Day
- Don't refresh predictions (use cached versions)
- Only update odds if creating ACCA bets

#### Weekly Optimization
- Track API usage trends
- Plan prefetching schedule
- Focus on upcoming matches

## Configuration

### Environment Variables (.env)

```bash
# API Keys (get free tier keys)
FOOTBALL_DATA_ORG_API_KEY=your_key
API_SPORTS_API_KEY=your_key
SPORTSMONK_API_KEY=your_key
ODDS_API_KEY=your_key

# Flask Settings
FLASK_ENV=development
FLASK_DEBUG=1

# Prediction Settings
MODEL_CONFIDENCE_THRESHOLD=0.65
MIN_HISTORICAL_MATCHES=10
```

### Streamlit Config

Cache location: `~/.streamlit/config.toml`

Recommended settings for M5:
```toml
[client]
showErrorDetails = true

[logger]
level = "info"

[server]
port = 8501
headless = false
```

## Troubleshooting

### App Won't Launch

1. **Check logs:**
   ```bash
   cat hibs_flask.log      # Flask errors
   cat hibs_streamlit.log  # Streamlit errors
   ```

2. **Verify .env file:**
   ```bash
   ls -la .env
   # Should show file with size > 0
   ```

3. **Test from terminal:**
   ```bash
   source .venv/bin/activate
   python src/hibs_predictor/web.py
   ```

### Rate Limit Errors

1. **Check usage:**
   ```python
   python -c "from src.hibs_predictor.rate_limiter import RateLimiter; RateLimiter().print_usage_report()"
   ```

2. **Common causes:**
   - Multiple instances running (both apps)
   - Rapid refreshes in browser
   - Historical data fetching

3. **Solutions:**
   - Close other app instances
   - Wait for rate limit reset (typically 1 hour)
   - Check `.rate_limit_state.json` for state

### Port Already in Use

If port 5000 or 8501 is taken:

**For Flask (port 5000):**
```bash
lsof -i :5000  # Find what's using it
kill -9 <PID>  # Kill the process
```

**For Streamlit (port 8501):**
```bash
lsof -i :8501
kill -9 <PID>
```

## Performance Benchmarks (M5)

Expected performance on MacBook Air M5:

- **Startup time:** 3-5 seconds (Flask), 8-12 seconds (Streamlit)
- **Prediction generation:** 200-500ms
- **Dashboard load:** <1 second (cached)
- **API response:** 100-300ms + cache time
- **Memory usage:** ~400-600MB baseline

## Best Practices

1. **Keep app running** - Don't restart frequently (hits API limits)
2. **Use caching** - Let system cache data intelligently
3. **Monitor logs** - Check for API errors regularly
4. **Plan updates** - Schedule fetches outside peak hours
5. **Batch operations** - Group API calls together
6. **Cache before sharing** - Pre-calculate predictions for ACCAs

## Free Tier API Registration

Get free tier keys from:

1. **football-data.org**
   - https://www.football-data.org/register
   - 100 calls/day

2. **api-sports**
   - https://rapidapi.com/api-sports/api/api-football
   - 150 calls/day

3. **SportsMonk**
   - https://www.sportsmonk.io
   - 150 calls/day

4. **Odds-API**
   - https://the-odds-api.com
   - 500 calls/month

5. **Stats API**
   - https://www.stats-api.com
   - 150 calls/day

---

**Last Updated:** May 2026
**Optimized for:** macOS 11.0+, Apple Silicon (M1-M5), Free API Tiers

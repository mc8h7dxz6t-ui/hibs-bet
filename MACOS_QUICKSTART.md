# HibsBetting macOS Quick Start Guide

## 🚀 First Time Setup (5 minutes)

### 1. Get Your API Keys (2 minutes)

Sign up for free tier APIs:

```bash
# Open these links and sign up:
- https://www.football-data.org/register (100 calls/day)
- https://rapidapi.com/api-sports/api/api-football (150 calls/day)
- https://www.sportsmonk.io (150 calls/day)
- https://the-odds-api.com (500 calls/month)
```

### 2. Configure Your Project (2 minutes)

```bash
# From project root, copy the example env file
cp .env.example .env

# Edit .env with your API keys (open in your editor)
nano .env  # or use your preferred editor
```

Your `.env` should have:
```
FOOTBALL_DATA_ORG_API_KEY=your_key_here
API_SPORTS_API_KEY=your_key_here
SPORTSMONK_API_KEY=your_key_here
ODDS_API_KEY=your_key_here
```

### 3. Set Up Virtual Environment (1 minute)

```bash
cd /Users/philipmacleod/HibsBetting
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 🎮 Running the Apps

### Option 1: Double-Click in Finder (Easiest)

1. Open Finder
2. Navigate to: `HibsBetting/launch/`
3. Double-click one of these:

**For Flask Dashboard:**
- `RunHibsBetting.command` → Opens web dashboard at http://127.0.0.1:5000

**For Streamlit Interface:**
- `RunHibsStreamlit.command` → Opens Streamlit app at http://127.0.0.1:8501

**Note:** If double-clicking shows a permission error, use Option 2 below.

### Option 2: Terminal Commands (Alternative)

If Finder blocks the `.command` files due to macOS Gatekeeper:

```bash
# For Flask Dashboard
cd /Users/philipmacleod/HibsBetting
./launch/RunHibsBetting.command

# For Streamlit Interface
cd /Users/philipmacleod/HibsBetting
./launch/RunHibsStreamlit.command
```

### Option 3: Native App Bundles

Double-click these app bundles (may also be blocked by Gatekeeper):

- `HibsBetting.app` → Flask dashboard
- `HibsBetting-Streamlit.app` → Streamlit interface
   - **HibsBetting.app** - Main dashboard (Flask)
   - **HibsBetting-Streamlit.app** - Alternative interface

The app will:
- ✅ Start the server
- ✅ Check for .env file
- ✅ Open your browser automatically
- ✅ Show info dialog when ready

### Option 2: Terminal (If Finder double-click doesn't work)

**Flask Dashboard:**
```bash
open /Users/philipmacleod/HibsBetting/launch/HibsBetting.app
```

**Streamlit Interface:**
```bash
open /Users/philipmacleod/HibsBetting/launch/HibsBetting-Streamlit.app
```

### Option 3: Terminal (For Development)

```bash
cd /Users/philipmacleod/HibsBetting
source .venv/bin/activate

# Flask (port 5000)
python src/hibs_predictor/web.py

# Or Streamlit (port 8501)
streamlit run launch/streamlit_app.py
```

## 📊 Accessing the App

Once running, open your browser:

- **Flask**: http://127.0.0.1:5000
- **Streamlit**: http://127.0.0.1:8501

## 🎯 What You Can Do

### Dashboard Features
- 📈 Real-time predictions for upcoming matches
- 🔍 Fixture analysis for Scottish Premiership, EPL, Europa League
- 💰 ACCA builder for multi-bet combinations
- 📊 Historical form and statistics

### Free API Usage
- ✅ Automatic caching (4-12 hours depending on data type)
- ✅ Rate limit tracking with warnings
- ✅ Optimized for free tier limits
- ✅ Smart prefetching to maximize usage

## 🛑 Stopping the App

1. **From Finder:** Close the app window
2. **From Terminal:** Press `Ctrl+C`
3. **From Browser:** Just close the tab (server continues running in background)

## 🐛 Troubleshooting

### "Cannot execute because you do not have appropriate access privileges"

The old .command files might be cached by Gatekeeper. Use the new .app bundles instead:
```bash
open /Users/philipmacleod/HibsBetting/launch/HibsBetting.app
```

### Port Already in Use

Close the other app using the port:
```bash
# For port 5000 (Flask)
lsof -i :5000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# For port 8501 (Streamlit)  
lsof -i :8501 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### "API Key missing" Error

Check that:
1. `.env` file exists in project root
2. It has the correct API keys filled in
3. No trailing spaces in keys

```bash
cat .env  # Verify content
```

### Rate Limit Errors

Check your API usage:
```bash
cd /Users/philipmacleod/HibsBetting
source .venv/bin/activate
python -c "from src.hibs_predictor.rate_limiter import RateLimiter; RateLimiter().print_usage_report()"
```

Wait for the next hour for daily limit reset, or next month for monthly limits.

### App Won't Start - Check Logs

```bash
# Check Flask errors
cat /Users/philipmacleod/HibsBetting/hibs_flask.log

# Check Streamlit errors
cat /Users/philipmacleod/HibsBetting/hibs_streamlit.log

# Or check the last 50 lines
tail -50 hibs_flask.log
tail -50 hibs_streamlit.log
```

## 📚 Documentation

For more detailed information:

- **M5 & Free API Optimization**: See `M5_AND_FREE_API_OPTIMIZATION.md`
- **Implementation Details**: See `TECHNICAL_DOCS.md`
- **ACCA Builder**: See `ACCA_BUILDER_GUIDE.md`
- **Betting Engine**: See `BETTING_ENGINE.md`

## 🔧 Configuration

All settings are automatic for M5/free API usage. If you need to customize:

1. **Cache settings** - Edit `src/hibs_predictor/cache.py`
2. **Rate limits** - Edit `src/hibs_predictor/rate_limiter.py`
3. **League focus** - Edit `src/hibs_predictor/config.py`

## 📱 M5 MacBook Air Specific Notes

The app is optimized for:
- ✅ Apple Silicon (M5, M4, M3, M2, M1)
- ✅ Efficient CPU usage (limits threads to CPU count - 1)
- ✅ Native arm64 Python libraries
- ✅ Minimal battery drain
- ✅ Fast startup (3-5 seconds Flask, 8-12 seconds Streamlit)

**Expected Performance:**
- Startup: 3-5 seconds
- Predictions: 200-500ms
- Memory: ~400-600MB
- CPU: Low even under load

## ⚡ Pro Tips

1. **Keep it running** - Don't restart frequently to avoid hitting API limits
2. **Morning refresh** - Update predictions early morning for weekend matches
3. **Check logs** - Monitor `hibs_*.log` files for API issues
4. **Plan ahead** - Batch your API calls, don't refresh constantly
5. **Use Finder** - Double-click .app is the smoothest experience on macOS

## 🆘 Need Help?

1. Check the log files (see Troubleshooting)
2. Verify API keys are correct and have quota remaining
3. Ensure virtual environment is activated
4. Try running from terminal for detailed error messages
5. Restart the app fresh

---

**System Requirements:**
- macOS 11.0 or later
- Apple Silicon or Intel processor
- 4GB RAM (8GB recommended)
- Python 3.8+ (via virtual environment)

**Last Updated:** May 2026
**Compatible with:** M5, M4, M3, M2, M1, Intel Macs

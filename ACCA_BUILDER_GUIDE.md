# hibs-bet Acca Builder — Quick Start Guide

## 🚀 Getting Started

### 1. Start the Application
```bash
python3 launcher.py
```
The app will automatically open in your browser at `http://127.0.0.1:5000`

### 2. Navigate to Acca Builder
Click the **"💰 Acca Builder"** button in the header, or go directly to:
```
http://127.0.0.1:5000/acca
```

## 📊 Dashboard Interface

### Left Panel: Your Acca
This is where your selections appear in real-time.

**Stats**:
- **Selections**: Count of added bets
- **Total Odds**: Running total of multiplied odds

**Your Bets List**:
- Shows each selection with outcome and odds
- Click "✕" to remove a selection

**Stake Input**:
- Enter the amount you want to bet (£)
- Returns automatically calculate as you type

**Potential Returns**:
- Displayed in large red text
- Formula: Stake × Total Odds

**Action Buttons**:
- **Place Acca**: Review summary and open betting site
- **William Hill**: Direct link to William Hill
- **Ladbrokes**: Direct link to Ladbrokes

### Right Panel: Next 48 Hours Fixtures

Shows all upcoming matches across your focus leagues.

**For Each Match**:
- **Teams & League**: Home vs Away, league name
- **Prediction Indicator**: Best bet type and confidence %
- **Three Odds Buttons**: Click to add outcome to acca
  - Left button: Home team win
  - Center button: Draw
  - Right button: Away team win

## 💡 How to Build an Acca

### Step 1: Browse Fixtures
Scroll through the list of next 48-hour matches. Look for:
- ✨ Strong predictions (high confidence %)
- 💎 Value bet indicators (model found +3% ROI)

### Step 2: Add Selections
Click any odds button to add that selection:
```
Manchester City vs Liverpool
    [2.10]  [3.50]  [3.25]
     Win    Draw    Win
```
Clicking 2.10 adds "Manchester City Win @ 2.10" to your acca.

### Step 3: Watch Odds Update
Each time you add or remove a selection:
- **Total Odds** multiply together
- **Potential Returns** recalculate instantly
- **Selection Count** updates

Example:
```
Selection 1: Man City Win @ 2.10
Selection 2: Draw @ 3.50
Selection 3: Liverpool Win @ 3.25
─────────────────────────────
Total Odds: 2.10 × 3.50 × 3.25 = 23.86
Stake: £10.00
Returns: £238.60
```

### Step 4: Enter Your Stake
Type the amount you want to bet in the "Stake (£)" field.

**Watch**:
- Potential returns update instantly
- Formula updates based on new stake

### Step 5: Place Your Acca
Click the **"🎯 Place Acca"** button:
1. Review your acca summary
2. Check selections, odds, stake, returns
3. Click OK to open your chosen betting site
4. Complete bet placement on William Hill or Ladbrokes

## 🎯 Strategy Tips

### Value Betting
- Look for 💎 **VALUE BET** indicators
- These are model-identified opportunities with +3%+ ROI
- Combine multiple value bets for higher returns

### Confidence Management
- **80%+ Confidence**: Likely predictions
- **50-70% Confidence**: Mixed prospects
- **<50% Confidence**: Speculative bets

### Acca Building
- **Safer**: 2-3 selections from high-confidence matches
- **Aggressive**: 4-5 selections mixing various outcomes
- **Kelly Criterion**: App suggests optimal bet sizing (shown in details)

### Expected Goals (xG)
In the details section, check:
- **xG Differential**: How much attacking quality each team created
- **BTTS Probability**: Chance both teams score

## 📱 Mobile Compatibility

The acca builder works on mobile devices:
- Responsive design adapts to screen size
- Touch-friendly buttons and inputs
- Fixture list scrolls smoothly

## ⚙️ API Endpoints

Developers can use the API directly:

### Place Bet Programmatically
```bash
curl -X POST http://127.0.0.1:5000/api/place-bet \
  -H "Content-Type: application/json" \
  -d '{
    "selections": [
      {"fixture_id": 123, "outcome": "home", "odds": 2.10},
      {"fixture_id": 456, "outcome": "draw", "odds": 3.50}
    ],
    "stake": 10.00,
    "affiliate": "william_hill"
  }'
```

Response:
```json
{
  "status": "success",
  "bet_id": "BET_20250115120304",
  "total_odds": 7.35,
  "potential_returns": 73.50,
  "affiliate_url": "https://www.williamhill.com/?ref=hibs-bet&...",
  "timestamp": "2025-01-15T12:03:04.123456"
}
```

## 🔍 Troubleshooting

### No Fixtures Showing
**Problem**: Right panel is empty
- **Solution**: Wait 30 seconds for APIs to load
- **Check**: Ensure `.env` has valid API keys
- **Verify**: Run `python3 test_app.py` to diagnose

### Odds Not Updating
**Problem**: Potential returns don't change when you type stake
- **Solution**: Refresh the page (Cmd+R on Mac)
- **Clear**: Restart Flask app

### Betting Links Not Working
**Problem**: Clicking William Hill/Ladbrokes buttons doesn't work
- **Solution**: Make sure pop-ups aren't blocked
- **Try**: Open link manually at `williamhill.com` or `ladbrokes.com`

### JavaScript Errors
**Problem**: Buttons don't respond to clicks
- **Check**: Browser console (Cmd+Option+J on Mac)
- **Verify**: JavaScript isn't disabled
- **Clear**: Browser cache

## 📞 Support

For technical issues:
1. Check console errors (F12)
2. Run diagnostic: `python3 test_app.py`
3. Verify API keys in `.env`
4. Check network in browser DevTools

## ⚠️ Responsible Gambling

**Remember**:
- Betting carries risk
- Never bet more than you can afford
- Set strict budgets
- Seek help if needed

Visit [BeGambleAware.org](https://www.begambleaware.org) for support.

---

**Happy betting! 🟤💛**

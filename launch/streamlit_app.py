#!/usr/bin/env python3
"""Streamlit interface for hibs-bet with minimal desktop launch input."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")
sys.path.insert(0, str(REPO_ROOT / "src"))

from hibs_predictor.config import HIBS_LEAGUE_FOCUS, LEAGUES
from hibs_predictor.web import fetch_next_48h_fixtures

st.set_page_config(
    page_title="hibs-bet streamlit",
    page_icon="⚽",
    layout="wide",
)

st.title("hibs-bet streamlit dashboard")
st.markdown(
    "Compact football market intelligence for UK and European fixtures — "
    "double-click the desktop launcher to start with zero extra input."
)

with st.sidebar:
    st.header("Launcher")
    st.write("Choose leagues, then review the latest predictions and odds.")
    selected_leagues = st.multiselect(
        "Select leagues",
        options=list(LEAGUES.keys()),
        default=HIBS_LEAGUE_FOCUS,
    )
    st.info(
        "If this is the first run, make sure `.env` exists in the project root with your API keys. "
        "The desktop launcher will start this Streamlit app automatically."
    )
    if st.button("Refresh data"):
        st.experimental_rerun()

if not selected_leagues:
    st.warning("Select at least one league from the sidebar to load fixtures.")
    st.stop()

@st.cache_data(ttl=600)
def load_fixtures(leagues):
    fixtures = []
    for league_code in leagues:
        try:
            fixtures.extend(fetch_next_48h_fixtures(league_code))
        except Exception as error:
            st.error(f"Error loading fixtures for {league_code}: {error}")
    return fixtures

fixtures = load_fixtures(selected_leagues)

if not fixtures:
    st.warning("No fixtures available yet. Check your API keys and try again.")
    st.stop()

st.subheader(f"{len(fixtures)} fixtures loaded")

for league_code in selected_leagues:
    league_fixtures = [f for f in fixtures if f.get("league") == league_code]
    if not league_fixtures:
        continue

    st.markdown(f"### {LEAGUES.get(league_code, {}).get('name', league_code)} ({len(league_fixtures)} fixtures)")

    for fixture in league_fixtures:
        prediction = fixture.get("prediction") or {}
        home = fixture.get("home", "Unknown")
        away = fixture.get("away", "Unknown")
        ko = fixture.get("ko", fixture.get("date", "TBD"))
        pred_outcome = prediction.get("predicted_outcome", "TBD").upper()
        btts = prediction.get("btts_probability")
        confidence = prediction.get("confidence")
        best_bet = prediction.get("best_bet")
        odds = prediction.get("bookmaker_odds") or {}

        header = f"{ko} · {home} vs {away} · {pred_outcome}"
        with st.expander(header, expanded=False):
            cols = st.columns([2, 2, 1, 1, 1])
            cols[0].markdown(f"**Match**\n{home} vs {away}")
            cols[1].markdown(
                f"**Odds**\nHome {odds.get('home', 'N/A')} · Draw {odds.get('draw', 'N/A')} · Away {odds.get('away', 'N/A')}"
            )
            cols[2].metric("BTTS", f"{btts * 100:.0f}%" if btts is not None else "N/A")
            cols[3].metric("Confidence", f"{confidence * 100:.0f}%" if confidence is not None else "N/A")
            cols[4].markdown(f"**Best bet**\n{best_bet.upper() if best_bet else 'N/A'}")

            st.markdown("---")
            st.markdown(
                f"**Last 6 Home:** {fixture.get('home_last', 'No data')}  \n"
                f"**Last 6 Away:** {fixture.get('away_last', 'No data')}"
            )
            btts_text = f"{btts * 100:.0f}%" if btts is not None else "N/A"
            st.markdown(
                f"**Expected xG**: {prediction.get('expected_goals_home', 'N/A')} - {prediction.get('expected_goals_away', 'N/A')}  \n"
                f"**BTTS chance**: {btts_text}"
            )

            if best_bet:
                bet_data = prediction.get("value_bets", {}).get(best_bet, {})
                st.markdown(
                    f"**Bet edge**: {bet_data.get('value', 0) * 100:.1f}%  \n"
                    f"**Odds**: {bet_data.get('odds', 'N/A')}  \n"
                    f"**Expected ROI**: {bet_data.get('roi_percent', 0):.1f}%"
                )

st.markdown("---")
st.caption("Double-click the desktop launcher in the launch folder to run this app with minimal input.")

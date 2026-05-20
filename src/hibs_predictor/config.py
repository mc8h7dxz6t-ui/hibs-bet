"""Configuration for supported leagues and API endpoint mappings."""

LEAGUES = {
    # Scottish
    "SCOTLAND": {
        "name": "Scottish Premiership",
        "country": "Scotland",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "football_data_org_id": None,
        "api_sports_id": 179,
        "sportsmonk_id": 501,
        "strength_factor": 0.75,
    },
    "SCOTLAND_CHAMP": {
        "name": "Scottish Championship",
        "country": "Scotland",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "football_data_org_id": None,
        "api_sports_id": 180,
        "sportsmonk_id": None,
        "strength_factor": 0.65,
    },
    "SCOTLAND_L1": {
        "name": "Scottish League One",
        "country": "Scotland",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "football_data_org_id": None,
        "api_sports_id": 181,
        "sportsmonk_id": None,
        "strength_factor": 0.55,
    },
    "SCOTLAND_L2": {
        "name": "Scottish League Two",
        "country": "Scotland",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "football_data_org_id": None,
        "api_sports_id": 182,
        "sportsmonk_id": None,
        "strength_factor": 0.50,
    },
    "SCOTTISH_CUP": {
        "name": "Scottish Cup",
        "country": "Scotland",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "football_data_org_id": None,
        "api_sports_id": 528,
        "sportsmonk_id": None,
        "strength_factor": 0.75,
    },
    # English
    "EPL": {
        "name": "Premier League",
        "country": "England",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "football_data_org_id": "PL",
        "api_sports_id": 39,
        "sportsmonk_id": 2,
        "strength_factor": 1.0,
    },
    "CHAMPIONSHIP": {
        "name": "Championship",
        "country": "England",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "football_data_org_id": "ELC",
        "api_sports_id": 40,
        "sportsmonk_id": 3,
        "strength_factor": 0.85,
    },
    "LEAGUE_ONE": {
        "name": "League One",
        "country": "England",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "football_data_org_id": "EL1",
        "api_sports_id": 41,
        "sportsmonk_id": None,
        "strength_factor": 0.72,
    },
    "LEAGUE_TWO": {
        "name": "League Two",
        "country": "England",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "football_data_org_id": "EL2",
        "api_sports_id": 42,
        "sportsmonk_id": None,
        "strength_factor": 0.65,
    },
    "FA_CUP": {
        "name": "FA Cup",
        "country": "England",
        "region": "UK",
        "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "football_data_org_id": "FAC",
        "api_sports_id": 45,
        "sportsmonk_id": None,
        "strength_factor": 0.90,
    },
    # European
    "UCL": {
        "name": "Champions League",
        "country": "International",
        "region": "European",
        "flag": "🏆",
        "football_data_org_id": "CL",
        "api_sports_id": 2,
        "sportsmonk_id": 2,
        "strength_factor": 1.0,
    },
    "EUROPA_LEAGUE": {
        "name": "Europa League",
        "country": "International",
        "region": "European",
        "flag": "🏆",
        "football_data_org_id": "EL",
        "api_sports_id": 3,
        "sportsmonk_id": 180,
        "strength_factor": 0.90,
    },
    "UECL": {
        "name": "Conference League",
        "country": "International",
        "region": "European",
        "flag": "🏆",
        "football_data_org_id": "UECL",
        "api_sports_id": 848,
        "sportsmonk_id": None,
        "strength_factor": 0.80,
    },
    "LA_LIGA": {
        "name": "La Liga",
        "country": "Spain",
        "region": "European",
        "flag": "🇪🇸",
        "football_data_org_id": "PD",
        "api_sports_id": 140,
        "sportsmonk_id": 564,
        "strength_factor": 1.0,
    },
    "SERIE_A": {
        "name": "Serie A",
        "country": "Italy",
        "region": "European",
        "flag": "🇮🇹",
        "football_data_org_id": "SA",
        "api_sports_id": 135,
        "sportsmonk_id": 384,
        "strength_factor": 0.95,
    },
    "BUNDESLIGA": {
        "name": "Bundesliga",
        "country": "Germany",
        "region": "European",
        "flag": "🇩🇪",
        "football_data_org_id": "BL1",
        "api_sports_id": 78,
        "sportsmonk_id": 364,
        "strength_factor": 1.0,
    },
    "LIGUE_1": {
        "name": "Ligue 1",
        "country": "France",
        "region": "European",
        "flag": "🇫🇷",
        "football_data_org_id": "FL1",
        "api_sports_id": 61,
        "sportsmonk_id": 10,
        "strength_factor": 0.90,
    },
    "EREDIVISIE": {
        "name": "Eredivisie",
        "country": "Netherlands",
        "region": "European",
        "flag": "🇳🇱",
        "football_data_org_id": "DED",
        "api_sports_id": 88,
        "sportsmonk_id": None,
        "strength_factor": 0.85,
    },
    "PRIMEIRA": {
        "name": "Primeira Liga",
        "country": "Portugal",
        "region": "European",
        "flag": "🇵🇹",
        "football_data_org_id": "PPL",
        "api_sports_id": 94,
        "sportsmonk_id": None,
        "strength_factor": 0.85,
    },
    "BELGIUM_FIRST": {
        "name": "Belgium Pro League",
        "country": "Belgium",
        "region": "European",
        "flag": "🇧🇪",
        "football_data_org_id": None,
        "api_sports_id": 144,
        "sportsmonk_id": None,
        "strength_factor": 0.82,
    },
    "DENMARK_SL": {
        "name": "Denmark Superliga",
        "country": "Denmark",
        "region": "European",
        "flag": "🇩🇰",
        "football_data_org_id": None,
        "api_sports_id": 119,
        "sportsmonk_id": None,
        "strength_factor": 0.78,
    },
    "GREECE_SL": {
        "name": "Greece Super League",
        "country": "Greece",
        "region": "European",
        "flag": "🇬🇷",
        "football_data_org_id": None,
        "api_sports_id": 197,
        "sportsmonk_id": None,
        "strength_factor": 0.76,
    },
    "AUSTRIA_BL": {
        "name": "Austria Bundesliga",
        "country": "Austria",
        "region": "European",
        "flag": "🇦🇹",
        "football_data_org_id": None,
        "api_sports_id": 218,
        "sportsmonk_id": None,
        "strength_factor": 0.78,
    },
    "NORWAY_ELITESERIEN": {
        "name": "Eliteserien",
        "country": "Norway",
        "region": "European",
        "flag": "🇳🇴",
        "football_data_org_id": None,
        "api_sports_id": 103,
        "sportsmonk_id": None,
        "strength_factor": 0.72,
    },
    "FINLAND_VEIKKAUSLIIGA": {
        "name": "Veikkausliiga",
        "country": "Finland",
        "region": "European",
        "flag": "🇫🇮",
        "football_data_org_id": None,
        "api_sports_id": 244,
        "sportsmonk_id": None,
        "strength_factor": 0.68,
    },
    # International
    "WORLD_CUP": {
        "name": "FIFA World Cup",
        "country": "International",
        "region": "International",
        "flag": "🌍",
        "football_data_org_id": "WC",
        "api_sports_id": 1,
        "sportsmonk_id": None,
        "strength_factor": 1.0,
    },
    "EUROS": {
        "name": "UEFA Euros",
        "country": "International",
        "region": "International",
        "flag": "🌍",
        "football_data_org_id": "EC",
        "api_sports_id": 4,
        "sportsmonk_id": None,
        "strength_factor": 1.0,
    },
    "NATIONS_LEAGUE": {
        "name": "Nations League",
        "country": "International",
        "region": "International",
        "flag": "🌍",
        "football_data_org_id": "UNL",
        "api_sports_id": 5,
        "sportsmonk_id": None,
        "strength_factor": 0.95,
    },
}

# All competitions below are fetched for the dashboard window; value detection runs across
# every league with data. Wider coverage + richer per-fixture enrichment improve edge quality.
# Fetch + display order: SPL → EPL → lower Scotland → lower England → European leagues →
# World Cup / internationals → Champions League / Europa / Conference.
ALL_LEAGUE_CODES = [
    "SCOTLAND",
    "EPL",
    "SCOTLAND_CHAMP",
    "SCOTLAND_L1",
    "SCOTLAND_L2",
    "SCOTTISH_CUP",
    "CHAMPIONSHIP",
    "LEAGUE_ONE",
    "LEAGUE_TWO",
    "FA_CUP",
    "LA_LIGA",
    "SERIE_A",
    "BUNDESLIGA",
    "LIGUE_1",
    "EREDIVISIE",
    "PRIMEIRA",
    "BELGIUM_FIRST",
    "DENMARK_SL",
    "GREECE_SL",
    "AUSTRIA_BL",
    "NORWAY_ELITESERIEN",
    "FINLAND_VEIKKAUSLIIGA",
    "WORLD_CUP",
    "EUROS",
    "NATIONS_LEAGUE",
    "UCL",
    "EUROPA_LEAGUE",
    "UECL",
]

DASHBOARD_LEAGUE_ORDER = list(ALL_LEAGUE_CODES)

LEAGUE_REGIONS = {
    "🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland": ["SCOTLAND", "SCOTLAND_CHAMP", "SCOTLAND_L1", "SCOTLAND_L2", "SCOTTISH_CUP"],
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 England": ["EPL", "CHAMPIONSHIP", "LEAGUE_ONE", "LEAGUE_TWO", "FA_CUP"],
    "🏆 European": [
        "LA_LIGA", "SERIE_A", "BUNDESLIGA", "LIGUE_1", "EREDIVISIE", "PRIMEIRA",
        "BELGIUM_FIRST", "DENMARK_SL", "GREECE_SL", "AUSTRIA_BL",
        "NORWAY_ELITESERIEN", "FINLAND_VEIKKAUSLIIGA",
        "UCL", "EUROPA_LEAGUE", "UECL",
    ],
    "🌍 International": ["WORLD_CUP", "EUROS", "NATIONS_LEAGUE"],
}

# Dashboard sidebar region chips (UK = Scotland + England only; UEFA cups are European).
_DASHBOARD_REGION_UK = frozenset(
    {
        "SCOTLAND",
        "SCOTLAND_CHAMP",
        "SCOTLAND_L1",
        "SCOTLAND_L2",
        "SCOTTISH_CUP",
        "EPL",
        "CHAMPIONSHIP",
        "LEAGUE_ONE",
        "LEAGUE_TWO",
        "FA_CUP",
    }
)
_DASHBOARD_REGION_EUROPEAN = frozenset(
    {
        "LA_LIGA",
        "SERIE_A",
        "BUNDESLIGA",
        "LIGUE_1",
        "EREDIVISIE",
        "PRIMEIRA",
        "BELGIUM_FIRST",
        "DENMARK_SL",
        "GREECE_SL",
        "AUSTRIA_BL",
        "NORWAY_ELITESERIEN",
        "FINLAND_VEIKKAUSLIIGA",
        "UCL",
        "EUROPA_LEAGUE",
        "UECL",
    }
)
_DASHBOARD_REGION_INTERNATIONAL = frozenset({"WORLD_CUP", "EUROS", "NATIONS_LEAGUE"})

DASHBOARD_FILTER_REGIONS = (
    ("", "All"),
    ("uk", "UK"),
    ("european", "European"),
    ("international", "International"),
)


def league_dashboard_region(league_code: str) -> str:
    """Region slug for dashboard filter chips (UEFA cups → european, not uk)."""
    code = (league_code or "").strip()
    if code in _DASHBOARD_REGION_UK:
        return "uk"
    if code in _DASHBOARD_REGION_EUROPEAN:
        return "european"
    if code in _DASHBOARD_REGION_INTERNATIONAL:
        return "international"
    return "other"

DEFAULT_CACHE_TTL_HOURS = 4

MAX_REQUESTS_PER_HOUR = {
    "football_data_org": 100,
    "api_sports": 150,
    "sportsmonk": 150,
    "odds_api": 500,
    "stats_api": 150,
}

# Default leagues for Streamlit / launcher multiselect
HIBS_LEAGUE_FOCUS = ["SCOTLAND", "EPL", "EUROPA_LEAGUE"]

"""Configuration for supported leagues and API endpoint mappings."""

LEAGUES = {
    "EPL": {
        "name": "English Premier League",
        "country": "England",
        "region": "UK",
        "football_data_org_id": "PL",
        "api_sports_id": 39,
        "sportsmonk_id": 2,
        "strength_factor": 1.0,
    },
    "CHAMPIONSHIP": {
        "name": "English Football League Championship",
        "country": "England",
        "region": "UK",
        "football_data_org_id": "ELC",
        "api_sports_id": 40,
        "sportsmonk_id": 3,
        "strength_factor": 0.9,
    },
    "SCOTLAND": {
        "name": "Scottish Premiership",
        "country": "Scotland",
        "region": "UK",
        "football_data_org_id": "SPL",
        "api_sports_id": 179,
        "sportsmonk_id": 501,
        "strength_factor": 0.75,
    },
    "LA_LIGA": {
        "name": "La Liga",
        "country": "Spain",
        "region": "Europe",
        "football_data_org_id": "PD",
        "api_sports_id": 140,
        "sportsmonk_id": 564,
        "strength_factor": 1.0,
    },
    "SERIE_A": {
        "name": "Serie A",
        "country": "Italy",
        "region": "Europe",
        "football_data_org_id": "SA",
        "api_sports_id": 135,
        "sportsmonk_id": 384,
        "strength_factor": 0.95,
    },
    "BUNDESLIGA": {
        "name": "Bundesliga",
        "country": "Germany",
        "region": "Europe",
        "football_data_org_id": "BL1",
        "api_sports_id": 78,
        "sportsmonk_id": 364,
        "strength_factor": 1.0,
    },
    "LIGUE_1": {
        "name": "Ligue 1",
        "country": "France",
        "region": "Europe",
        "football_data_org_id": "FL1",
        "api_sports_id": 61,
        "sportsmonk_id": 10,
        "strength_factor": 0.95,
    },
    "EUROPA_LEAGUE": {
        "name": "UEFA Europa League",
        "country": "International",
        "region": "Europe",
        "football_data_org_id": "EL",
        "api_sports_id": 684,
        "sportsmonk_id": 180,
        "strength_factor": 0.85,
    },
}

HIBS_LEAGUE_FOCUS = ["EPL", "CHAMPIONSHIP", "LA_LIGA"]

DEFAULT_CACHE_TTL_HOURS = 4

MAX_REQUESTS_PER_HOUR = {
    "football_data_org": 100,
    "api_sports": 150,
    "sportsmonk": 150,
    "odds_api": 500,
    "stats_api": 150,
}

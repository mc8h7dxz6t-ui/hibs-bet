"""FotMob international friendlies fixture discovery."""

from hibs_predictor.scrapers.fotmob_client import (
    _is_national_friendlies_league_name,
    fixtures_for_league,
)


def test_national_friendlies_name_filter():
    assert _is_national_friendlies_league_name("Friendlies") is True
    assert _is_national_friendlies_league_name("International Friendly") is True
    assert _is_national_friendlies_league_name("Club Friendlies") is False
    assert _is_national_friendlies_league_name("Premier League") is False


def test_intl_friendlies_uses_dedicated_fotmob_path(monkeypatch):
    from datetime import date

    calls = []

    def fake_intl(start, end, *, cache=None):
        calls.append((start, end))
        return [{"id": 1, "home": {"name": "A"}, "away": {"name": "B"}}]

    import hibs_predictor.scrapers.fotmob_client as fm

    monkeypatch.setattr(fm, "fixtures_international_friendlies", fake_intl)
    out = fixtures_for_league("INTL_FRIENDLIES", date(2026, 5, 26), date(2026, 5, 28))
    assert len(calls) == 1
    assert len(out) == 1

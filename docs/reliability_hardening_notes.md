# Reliability hardening release notes

Grouped by plan checkpoint. No feature removals, DQ scoring semantics unchanged, all sources remain enabled by default.

## Checkpoint 1 — Core stability

- **Structured resilience logging** (`HIBS_RESILIENCE_LOG`, default on): `log_resilience_event` / `log_slow_path` in `app_logging.py`; `_log_resilience()` in `web.py` for stale bundle fallback.
- **Rate limiter**: `block_reason()` distinguishes `guard_hour` vs `guard_minute`; `diagnostics()` for probes.
- **API clients**: local guard vs provider rate limits; stale cache reuse on guard/HTTP/429 with logged `block_reason`.
- **`fetch_all_fixtures`**: when a refresh returns zero fixtures, reuses last complete on-disk bundle with `cache_stale=True` (no blank dashboard).
- **Dashboard filters**: resets stale region/league and DQ chip filters when they hide all cards on first pass.
- **Acca builder**: uses `allow_stale=True` to avoid blocking loads.
- **Tests**: `tests/test_stability_routes.py`, expanded `test_rate_limiter.py`, `test_api_clients_guard.py`.

**Rollback**: revert `web.py` stale fallback block and `api_clients.py` guard helpers.

## Checkpoint 2 — DQ and source durability

- **Enrichment**: `enrich_fixture` reuses expired disk cache via `peek` when `get` misses (partial provider failure).
- **DQ regression guard**: `test_dq_floor_constants_unchanged_for_regression_guard` pins `_CORE_DQ_FLOOR`, `_INTL_DQ_FLOOR`, `_PREMIUM_DQ_FLOOR`.

**Rollback**: remove `peek` block in `data_aggregator.enrich_fixture`.

## Checkpoint 3 — Players and UI

- **Players dock**: cold-start auto-reload (max 3) when cache is warming.
- **Players page**: safe `or []` on scorer lists.
- **Settings / base**: `normalizeUiMode()` — invalid `uiMode` values fall back to `home`.
- **Sky dock**: fallback links visible when `sky_dock_unavailable_note` is set.

**Rollback**: revert template-only changes.

## Validation checklist

```bash
python3 -m pytest tests/test_stability_routes.py tests/test_cold_start_routes.py \
  tests/test_rate_limiter.py tests/test_api_clients_guard.py tests/test_players_route.py \
  tests/test_data_quality_floor.py -q
```

Manual: cold load `/`, `/players`, `/insights`; `?refresh=1` on dashboard; toggle Hibs Home/Away in Settings; collapse/expand Players dock.

## Deploy note

Production on GitLab `c624a43e` predates this work. Push `main` to GitLab and run CI deploy for hibs.co.uk to pick up these changes.

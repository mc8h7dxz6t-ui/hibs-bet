#!/usr/bin/env bash
# Heavy scrape production profile (2GB VPS). More HTTP, usually does not burn API quotas like fixture/stats calls.
# Run: sudo bash /opt/hibs-bet/deploy/apply-vps-heavy-production.sh
set -euo pipefail
APP="${APP:-/opt/hibs-bet}"
ENV="$APP/.env"
SVC=/etc/systemd/system/hibs-bet.service
MARK="# --- VPS heavy scrape production ---"

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo bash $0"; exit 1; }

cp -a "$ENV" "${ENV}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || touch "$ENV"

sed -i \
  -e "\|^${MARK}|d" \
  -e '/^# --- VPS 1GB production tuning/d' \
  -e '/^# --- Safer full data/d' \
  -e '/^# --- Production (2GB VPS)/d' \
  -e '/^HIBS_FETCH_DAYS=/d' \
  -e '/^HIBS_MAX_DATA=/d' \
  -e '/^HIBS_DASHBOARD_LITE=/d' \
  -e '/^HIBS_ALWAYS_DEEP_SCRAPE=/d' \
  -e '/^HIBS_SKIP_HEAVY_WHEN_API_STRONG=/d' \
  -e '/^HIBS_FBREF_BLOCKED=/d' \
  -e '/^HIBS_ENABLE_HEAVY_SCRAPERS=/d' \
  -e '/^HIBS_FIXTURE_FETCH_WORKERS=/d' \
  -e '/^HIBS_WARM_FIXTURE_CACHE=/d' \
  -e '/^HIBS_ENRICH_API_SEM=/d' \
  "$ENV"

cat >>"$ENV" <<EOF

${MARK}
HIBS_FETCH_DAYS=7
HIBS_MAX_DATA=1
HIBS_DASHBOARD_LITE=0
HIBS_ENABLE_HEAVY_SCRAPERS=1
HIBS_ALWAYS_DEEP_SCRAPE=1
HIBS_SKIP_HEAVY_WHEN_API_STRONG=0
HIBS_FIXTURE_FETCH_WORKERS=4
HIBS_ENRICH_API_SEM=2
HIBS_WARM_FIXTURE_CACHE=1
HIBS_ENABLE_PLAYER_INSIGHT=1
HIBS_USE_INJURY_LAMBDA_ADJUST=1
HIBS_FBREF_BLOCKED=1
# World Cup window (May–Jul 2026): auto-limits fetch to internationals unless overridden.
# HIBS_TOURNAMENT_FOCUS=worldcup
# HIBS_TOURNAMENT_FOCUS=0
EOF
chown www-data:www-data "$ENV"
chmod 640 "$ENV"

sed -i 's/--workers [0-9]\+/--workers 2/' "$SVC"
sed -i 's/--timeout [0-9]\+/--timeout 300/' "$SVC"
grep -q 'Environment=HOME=' "$SVC" || sed -i '/WorkingDirectory=/a Environment=HOME=/opt/hibs-bet' "$SVC"

rm -f "$APP/.cache/all_fixtures_"* "$APP/.cache/fixtures_"* "$APP/.cache/team_stats_"* 2>/dev/null || true
chown -R www-data:www-data "$APP/.cache"

systemctl daemon-reload
systemctl restart hibs-bet
echo "Heavy scrape profile applied. Clear browser cache and Refresh dashboard."

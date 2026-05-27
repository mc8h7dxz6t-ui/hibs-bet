(function () {
    'use strict';

    function bindInsightsAccaSlips(root) {
        (root || document).querySelectorAll('.hibs-insights-acca-slip').forEach(function (btn) {
            if (btn.dataset.hibsAccaBound) return;
            btn.dataset.hibsAccaBound = '1';
            btn.addEventListener('click', function () {
                var card = btn.closest('.acca-rec-card') || btn.closest('.acca-rec-brief');
                if (!card) return;
                var raw = card.getAttribute('data-acca-legs');
                if (!raw) return;
                var legs;
                try {
                    legs = JSON.parse(raw);
                } catch (e) {
                    return;
                }
                if (window.HibsAssistant && typeof HibsAssistant.addAccaLegsToSlip === 'function') {
                    HibsAssistant.addAccaLegsToSlip(legs);
                } else if (window.HibsBetslip && typeof HibsBetslip.addMultipleSelections === 'function') {
                    HibsBetslip.addMultipleSelections(legs);
                }
            });
        });
    }

    function updateInsightsSummaryPills(data) {
        if (!data || !data.summary) return;
        var eligible = document.getElementById('insights-eligible-pill');
        var excluded = document.getElementById('insights-excluded-pill');
        if (eligible) {
            eligible.textContent = String(data.summary.fixtures_eligible || 0) + ' eligible';
        }
        if (excluded) {
            excluded.textContent = String(data.summary.fixtures_excluded || 0) + ' data-gated';
        }
    }

    function applyOddsFormat(root) {
        if (typeof window.applyOddsFormatToRoot === 'function') {
            window.applyOddsFormatToRoot(root);
        } else if (typeof window.hibsApplyOddsFormat === 'function') {
            window.hibsApplyOddsFormat(root);
        }
    }

    function loadDeferredMount(mount) {
        if (!mount || mount.dataset.hibsDeferredLoaded === '1') return;
        var url = mount.getAttribute('data-fetch-url');
        if (!url) return;
        mount.dataset.hibsDeferredLoaded = '1';
        fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                if (data.html) {
                    mount.innerHTML = data.html;
                    mount.setAttribute('aria-busy', 'false');
                    mount.classList.remove('hibs-deferred');
                    bindInsightsAccaSlips(mount);
                    applyOddsFormat(mount);
                }
                if (mount.id === 'insights-deferred-mount') {
                    updateInsightsSummaryPills(data);
                }
                if (mount.id === 'dash-results-mount' && (!data.total || data.total <= 0)) {
                    mount.remove();
                }
            })
            .catch(function () {
                mount.dataset.hibsDeferredLoaded = '0';
                var err = document.createElement('p');
                err.className = 'hibs-deferred-loading';
                err.textContent = 'Could not load this section — try Refresh on the dashboard.';
                mount.innerHTML = '';
                mount.appendChild(err);
                mount.setAttribute('aria-busy', 'false');
            });
    }

    function initDeferredMounts() {
        document.querySelectorAll('.hibs-deferred[data-fetch-url]').forEach(loadDeferredMount);
    }

    document.addEventListener('DOMContentLoaded', initDeferredMounts);

    window.HibsDeferred = {
        loadDeferredMount: loadDeferredMount,
        bindInsightsAccaSlips: bindInsightsAccaSlips,
    };
})();

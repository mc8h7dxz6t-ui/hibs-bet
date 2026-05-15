(function () {
    'use strict';

    var packets = [];
    var recommendations = null;
    var panel, body, fab, closeBtn, fixtureSel;

    function init() {
        loadSnapshot(window.HIBS_ASSISTANT);
        panel = document.getElementById('hibs-assistant-panel');
        body = document.getElementById('hibs-assistant-body');
        fab = document.getElementById('hibs-assistant-fab');
        closeBtn = document.getElementById('hibs-assistant-close');
        fixtureSel = document.getElementById('hibs-assistant-fixture');
        if (!panel || !body || !fab) return;

        populateFixtureSelect();
        fab.addEventListener('click', togglePanel);
        if (closeBtn) closeBtn.addEventListener('click', function () { panel.classList.remove('open'); });
        document.querySelectorAll('.hibs-assistant-quick button').forEach(function (btn) {
            btn.addEventListener('click', function () {
                runPrompt(btn.getAttribute('data-prompt'));
            });
        });
        if (fixtureSel) {
            fixtureSel.addEventListener('change', function () {
                if (fixtureSel.value) runPrompt('analyze');
            });
        }
    }

    function loadSnapshot(raw) {
        if (!raw) return;
        if (raw.packets) {
            packets = raw.packets;
            recommendations = raw.recommendations || null;
        } else if (Array.isArray(raw)) {
            packets = raw;
        }
    }

    function populateFixtureSelect() {
        if (!fixtureSel) return;
        while (fixtureSel.options.length > 1) fixtureSel.remove(1);
        packets.forEach(function (p) {
            var opt = document.createElement('option');
            opt.value = String(p.id != null ? p.id : (p.home + '|' + p.away));
            var ko = p.kickoff_time || '';
            if (!ko && p.date && p.date.indexOf('T') !== -1) ko = p.date.slice(11, 16);
            if (ko) ko = ko + ' ';
            opt.textContent = ko + (p.home || '') + ' v ' + (p.away || '');
            fixtureSel.appendChild(opt);
        });
    }

    function togglePanel() {
        panel.classList.toggle('open');
        if (panel.classList.contains('open') && body && !body.childElementCount) {
            appendBot('Tap <strong>Deep dive all</strong> for a full-window scan, or pick an acca / singles prompt. Only fixtures with strong data coverage are used.');
        }
    }

    function findPacket(id) {
        return packets.find(function (p) {
            var key = String(p.id != null ? p.id : (p.home + '|' + p.away));
            return key === String(id);
        });
    }

    function selectedPacket() {
        if (!fixtureSel || !fixtureSel.value) return null;
        return findPacket(fixtureSel.value);
    }

    function ensureRecommendations(cb) {
        if (recommendations) {
            cb(recommendations);
            return;
        }
        fetch('/api/assistant/snapshot')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                loadSnapshot(data);
                populateFixtureSelect();
                cb(recommendations || { deep_dive_summary: {}, acca_suggestions: [], best_singles: [] });
            })
            .catch(function () {
                cb({ deep_dive_summary: {}, acca_suggestions: [], best_singles: [] });
            });
    }

    function runPrompt(kind) {
        if (kind === 'deep-dive') {
            appendUser('Deep dive all matches');
            ensureRecommendations(function (rec) {
                renderDeepDive(rec);
            });
            return;
        }
        if (kind === 'best-singles') {
            appendUser('Best singles');
            ensureRecommendations(function (rec) {
                renderBestSingles(rec);
            });
            return;
        }
        if (kind === 'btts-acca') {
            appendUser('BTTS acca');
            ensureRecommendations(function (rec) {
                renderAccaByType(rec, 'btts');
            });
            return;
        }
        if (kind === 'goals-acca') {
            appendUser('Goals acca (Over 2.5)');
            ensureRecommendations(function (rec) {
                renderAccaByType(rec, 'over25');
            });
            return;
        }
        if (kind === 'win-acca') {
            appendUser('Win acca');
            ensureRecommendations(function (rec) {
                renderAccaByType(rec, 'win');
            });
            return;
        }
        if (kind === 'value-all') {
            analyzeAllValue();
            return;
        }
        var pkt = selectedPacket();
        if (!pkt) {
            appendBot('Choose a fixture from the dropdown first.');
            return;
        }
        if (kind === 'analyze') {
            appendUser('Analyze ' + pkt.home + ' v ' + pkt.away);
            appendStructuredCard(pkt);
        }
    }

    function renderDeepDive(rec) {
        var sum = rec.deep_dive_summary || {};
        var html = '<div class="hibs-assistant-card">';
        html += '<p class="ac-line"><strong>Deep dive</strong></p>';
        html += '<p class="ac-line">' + esc(sum.summary_line || 'Scan complete.') + '</p>';
        if (sum.excluded_by_reason) {
            html += '<p class="ac-line" style="font-size:0.88em;color:var(--muted);">Excluded: ';
            var parts = [];
            Object.keys(sum.excluded_by_reason).forEach(function (k) {
                parts.push(k.replace(/_/g, ' ') + ' (' + sum.excluded_by_reason[k] + ')');
            });
            html += esc(parts.join('; ') || 'none') + '</p>';
        }
        html += '<p class="ac-line" style="font-size:0.85em;">Bar: ≥' + (sum.min_data_pct || 78) + '% data, form sample ≥' + (sum.min_form_matches || 3) + ' matches per side where possible.</p>';
        html += '</div>';
        appendBot(html);

        var accas = rec.acca_suggestions || [];
        if (accas.length) {
            appendBot('<p class="ac-line"><strong>Acca ideas</strong> (' + accas.length + ' built from eligible fixtures):</p>');
            accas.forEach(function (a) { appendAccaCard(a); });
        } else {
            appendBot('No acca met the 3-leg minimum with book prices — try refreshing or widening the fixture window.');
        }

        var mh = rec.market_highlights || {};
        var mhKeys = Object.keys(mh);
        if (mhKeys.length) {
            appendBot('<p class="ac-line"><strong>Market highlights</strong></p>');
            mhKeys.forEach(function (bucket) {
                var rows = mh[bucket] || [];
                if (!rows.length) return;
                appendBot('<p class="ac-line" style="font-weight:700;margin-top:6px;">' + esc(bucketLabel(bucket)) + '</p>');
                rows.slice(0, 3).forEach(function (leg) {
                    appendLegLine(leg, true);
                });
            });
        }
        if (rec.disclaimer) {
            appendBot('<p class="ac-line" style="font-size:0.82em;color:var(--muted);">' + esc(rec.disclaimer) + '</p>');
        }
    }

    function renderBestSingles(rec) {
        var singles = rec.best_singles || [];
        if (!singles.length) {
            appendBot('No singles cleared the data bar. Use Deep dive all for exclusion reasons.');
            return;
        }
        appendBot(singles.length + ' top single(s) by model + value score:');
        singles.forEach(function (leg) {
            var html = '<div class="hibs-assistant-card">';
            html += '<p class="ac-line"><strong>' + esc(leg.match || (leg.home + ' v ' + leg.away)) + '</strong>';
            if (leg.kickoff_time) html += ' · ' + esc(leg.kickoff_time);
            html += '</p>';
            html += '<p class="ac-line"><strong>Pick:</strong> <span style="color:var(--neon)">' + esc(leg.market_label) + '</span>';
            if (leg.odds) html += ' @ ' + leg.odds;
            if (leg.model_pct != null) html += ' · model ' + leg.model_pct + '%';
            html += '</p>';
            if (leg.is_value && leg.edge_pct != null) {
                html += '<p class="ac-line" style="color:var(--gold);">Value edge +' + leg.edge_pct + '%</p>';
            }
            if (leg.rationale && leg.rationale.length) {
                html += '<ul>';
                leg.rationale.forEach(function (b) { html += '<li>' + esc(b) + '</li>'; });
                html += '</ul>';
            }
            html += '</div>';
            appendBot(html);
        });
    }

    function renderAccaByType(rec, type) {
        var accas = rec.acca_suggestions || [];
        var match = accas.filter(function (a) { return a.type === type; });
        if (!match.length) {
            appendBot('No ' + type + ' acca available — need ≥3 eligible legs with prices. Run Deep dive all for context.');
            return;
        }
        match.forEach(function (a) { appendAccaCard(a); });
    }

    function appendAccaCard(acca) {
        var html = '<div class="hibs-assistant-card hibs-acca-card">';
        html += '<p class="ac-line"><strong>' + esc(acca.title) + '</strong> · ' + acca.leg_count + ' legs</p>';
        if (acca.combined_odds) {
            html += '<p class="ac-line">Combined odds <strong style="color:var(--gold);">' + acca.combined_odds + '</strong>';
            if (acca.joint_confidence_pct != null) {
                html += ' · joint model conf. ~' + acca.joint_confidence_pct + '%';
            }
            html += '</p>';
        }
        html += '<ol class="hibs-acca-legs">';
        (acca.legs || []).forEach(function (leg) {
            html += '<li>' + legHtml(leg) + '</li>';
        });
        html += '</ol>';
        if (acca.rationale && acca.rationale.length) {
            html += '<ul style="margin-top:6px;">';
            acca.rationale.forEach(function (b) { html += '<li style="font-size:0.88em;color:var(--muted);">' + esc(b) + '</li>'; });
            html += '</ul>';
        }
        html += '</div>';
        appendBot(html);
    }

    function appendLegLine(leg, compact) {
        appendBot('<p class="ac-line">' + legHtml(leg) + (compact && leg.model_pct != null ? ' · ' + leg.model_pct + '%' : '') + '</p>');
    }

    function legHtml(leg) {
        var ko = leg.kickoff_time ? esc(leg.kickoff_time) + ' ' : '';
        var s = ko + '<strong>' + esc(leg.home) + '</strong> v <strong>' + esc(leg.away) + '</strong> — ' + esc(leg.market_label);
        if (leg.odds) s += ' @ ' + leg.odds;
        if (leg.is_value) s += ' <span style="color:var(--gold);">VALUE</span>';
        return s;
    }

    function bucketLabel(key) {
        var map = {
            btts_yes: 'BTTS Yes',
            btts_no: 'BTTS No',
            over_15: 'Over 1.5',
            over_25: 'Over 2.5',
            over_35: 'Over 3.5',
            win_combo: 'Win + BTTS combos'
        };
        return map[key] || key;
    }

    function analyzeAllValue() {
        appendUser('Value scan');
        var hits = packets.filter(function (p) { return p.has_value_bet; });
        if (!hits.length) {
            appendBot('No value-flagged fixtures in the current snapshot.');
            return;
        }
        appendBot(hits.length + ' value fixture(s) (data-gated model vs book):');
        hits.slice(0, 10).forEach(function (p) {
            appendStructuredCard(p, true);
        });
        if (hits.length > 10) {
            appendBot('… and ' + (hits.length - 10) + ' more.');
        }
    }

    function appendUser(text) {
        var el = document.createElement('div');
        el.className = 'hibs-assistant-msg user';
        el.textContent = text;
        body.appendChild(el);
        body.scrollTop = body.scrollHeight;
    }

    function appendBot(html) {
        var el = document.createElement('div');
        el.className = 'hibs-assistant-msg bot';
        if (typeof html === 'string' && html.indexOf('<') !== -1) {
            el.innerHTML = html;
        } else {
            el.textContent = html;
        }
        body.appendChild(el);
        body.scrollTop = body.scrollHeight;
    }

    function appendStructuredCard(pkt, compact) {
        var si = pkt.structured_insight || {};
        var html = '<div class="hibs-assistant-card">';
        var ko = pkt.kickoff_time || '';
        html += '<p class="ac-line"><strong>Match:</strong> ' + esc(si.match || (pkt.home + ' vs ' + pkt.away));
        if (ko) html += ' · ' + esc(ko);
        html += '</p>';
        html += '<p class="ac-line"><strong>Pick:</strong> <span style="color:var(--neon)">' + esc(si.pick || '—') + '</span></p>';
        if (si.mode === 'odds_only') {
            html += '<p class="ac-line" style="color:#fde68a;">Insufficient data for model acca legs — prices only.</p>';
        }
        if (si.rationale && si.rationale.length && !compact) {
            html += '<ul>';
            si.rationale.forEach(function (b) { html += '<li>' + esc(b) + '</li>'; });
            html += '</ul>';
        }
        if (si.confidence_pct != null) {
            html += '<p class="ac-line"><strong>Confidence:</strong> ' + si.confidence_pct + '%</p>';
        }
        if (si.predicted_scoreline) {
            html += '<p class="ac-line"><strong>Scoreline:</strong> ' + esc(si.predicted_scoreline) + '</p>';
        }
        if (pkt.data_quality_pct != null) {
            html += '<p class="ac-line" style="font-size:0.88em;">Data ' + pkt.data_quality_pct + '%</p>';
        }
        if (pkt.has_value_bet && pkt.value_bets_display && pkt.value_bets_display[0]) {
            var v = pkt.value_bets_display[0];
            html += '<p class="ac-line" style="color:var(--gold);">Value: ' + esc(v.market_label) + ' @ ' + v.odds;
            if (v.edge_pct != null) html += ' · +' + v.edge_pct + '% edge';
            html += '</p>';
        }
        if (si.disclaimer && !compact) {
            html += '<p class="ac-line" style="font-size:0.85em;color:var(--muted);">' + esc(si.disclaimer) + '</p>';
        }
        html += '</div>';
        appendBot(html);
    }

    function esc(s) {
        var d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    function refreshFromApi() {
        fetch('/api/assistant/snapshot')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                loadSnapshot(data);
                populateFixtureSelect();
            })
            .catch(function () { /* keep embedded snapshot */ });
    }

    document.addEventListener('DOMContentLoaded', function () {
        init();
        if (!packets.length) refreshFromApi();
    });
})();

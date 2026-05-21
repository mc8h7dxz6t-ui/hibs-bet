(function () {
    'use strict';

    var packets = [];
    var recommendations = null;
    var panel, body, fab, closeBtn, fixtureContext, form, inputEl, sendBtn;
    var busy = false;

    function init() {
        loadSnapshot(window.HIBS_ASSISTANT);
        panel = document.getElementById('hibs-assistant-panel');
        body = document.getElementById('hibs-assistant-body');
        fab = document.getElementById('hibs-assistant-fab');
        closeBtn = document.getElementById('hibs-assistant-close');
        fixtureContext = document.getElementById('hibs-assistant-fixture');
        form = document.getElementById('hibs-assistant-form');
        inputEl = document.getElementById('hibs-assistant-input');
        sendBtn = document.getElementById('hibs-assistant-send');
        if (!panel || !body || !fab) return;

        fab.addEventListener('click', togglePanel);
        if (closeBtn) closeBtn.addEventListener('click', function () { panel.classList.remove('open'); });
        if (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                submitQuestion();
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

    function togglePanel() {
        panel.classList.toggle('open');
        if (panel.classList.contains('open') && body && !body.childElementCount) {
            appendBot(welcomeHtml());
        }
    }

    function welcomeHtml() {
        return '<div class="hibs-assistant-card"><p class="ac-line">I can build accas from today\'s card — want 2–5 legs, safer or bigger price?</p><p class="ac-line" style="font-size:0.88em;color:var(--muted);">Try <em>best acca</em>, <em>acca tips</em>, <em>suggest legs</em>, <em>BTTS acca</em>, or name a fixture for a single-game read.</p></div>';
    }

    function setBusy(on) {
        busy = on;
        if (sendBtn) sendBtn.disabled = on;
        if (inputEl) inputEl.disabled = on;
    }

    function submitQuestion() {
        if (busy || !inputEl) return;
        var q = (inputEl.value || '').trim();
        if (!q) return;
        inputEl.value = '';
        appendUser(q);
        setBusy(true);
        var fid = fixtureContext && fixtureContext.value ? fixtureContext.value : null;
        var payload = { question: q, fixture_id: fid };
        if (window.HIBS_ACCA_LEGS && window.HIBS_ACCA_LEGS.length) {
            payload.legs = window.HIBS_ACCA_LEGS;
        }
        fetch('/api/assistant/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    appendBot(esc(data.error));
                    return;
                }
                renderReply(data);
            })
            .catch(function () {
                appendBot('Could not reach the assistant API. Check the server is running and refresh the dashboard.');
            })
            .finally(function () { setBusy(false); });
    }

    function renderReply(data) {
        var blocks = data.blocks || [];
        if (!blocks.length) {
            appendBot('No response blocks — try rephrasing or type <em>help</em>.');
            return;
        }
        blocks.forEach(function (block) {
            renderBlock(block);
        });
        if (data.disclaimer) {
            appendBot('<p class="ac-line" style="font-size:0.82em;color:var(--muted);margin-top:8px;">' + esc(data.disclaimer) + '</p>');
        }
    }

    function renderBlock(block) {
        var t = block.type;
        if (t === 'text') {
            var html = '<div class="hibs-assistant-card">';
            (block.lines || []).forEach(function (line) {
                if (!line) return;
                html += '<p class="ac-line">' + formatLine(line) + '</p>';
            });
            html += '</div>';
            appendBot(html);
            return;
        }
        if (t === 'summary') {
            var s = block.data || {};
            var h = '<div class="hibs-assistant-card"><p class="ac-line"><strong>Card scan</strong></p>';
            h += '<p class="ac-line">' + esc(s.summary_line || '') + '</p>';
            if (s.excluded_by_reason) {
                var parts = [];
                Object.keys(s.excluded_by_reason).forEach(function (k) {
                    parts.push(k.replace(/_/g, ' ') + ' (' + s.excluded_by_reason[k] + ')');
                });
                h += '<p class="ac-line" style="font-size:0.88em;color:var(--muted);">Excluded: ' + esc(parts.join('; ')) + '</p>';
            }
            h += '</div>';
            appendBot(h);
            return;
        }
        if (t === 'singles') {
            appendBot('<p class="ac-line"><strong>Best singles</strong></p>');
            (block.items || []).forEach(function (leg) {
                appendBot(singleCardHtml(leg));
            });
            return;
        }
        if (t === 'suggest_legs') {
            appendBot('<p class="ac-line"><strong>Leg options</strong> — add any to your slip</p>');
            (block.items || []).forEach(function (leg) {
                appendBot(suggestLegCardHtml(leg));
            });
            return;
        }
        if (t === 'accas') {
            (block.items || []).forEach(function (a) { appendBot(accaCardHtml(a)); });
            return;
        }
        if (t === 'builders') {
            var builders = block.items || [];
            if (builders.length) appendBot('<p class="ac-line"><strong>Pro bet builders</strong></p>');
            builders.forEach(function (b) { appendBot(builderCardHtml(b)); });
            return;
        }
        if (t === 'highlights') {
            appendBot('<p class="ac-line"><strong>Market highlights</strong></p>');
            var mh = block.data || {};
            Object.keys(mh).forEach(function (bucket) {
                var rows = mh[bucket] || [];
                if (!rows.length) return;
                appendBot('<p class="ac-line" style="font-weight:700;margin-top:6px;">' + esc(bucketLabel(bucket)) + '</p>');
                rows.slice(0, 3).forEach(function (leg) {
                    appendBot(suggestLegCardHtml(leg));
                });
            });
            return;
        }
        if (t === 'stats') {
            var sh = '<div class="hibs-assistant-card">';
            (block.lines || []).forEach(function (line) {
                sh += '<p class="ac-line">' + formatLine(line) + '</p>';
            });
            sh += '</div>';
            appendBot(sh);
            return;
        }
        if (t === 'fixture') {
            if (block.packet) appendBot(fixtureCardHtml(block.packet, block.compact));
            return;
        }
        if (t === 'fixtures') {
            (block.items || []).forEach(function (p) {
                appendBot(fixtureCardHtml(p, block.compact));
            });
            return;
        }
        if (t === 'acca_review') {
            appendBot(accaReviewHtml(block.data || {}));
        }
    }

    function mapMarketToOutcome(marketKey) {
        var m = { home_win: 'home', away_win: 'away', draw: 'draw' };
        return m[marketKey] || marketKey;
    }

    function legFromPayload(leg) {
        if (!leg) return null;
        var slip = leg.slip || leg;
        if (!slip.fixture_id && !leg.fixture_id) return null;
        return {
            fixture_id: slip.fixture_id || leg.fixture_id,
            home: slip.home || leg.home,
            away: slip.away || leg.away,
            league: slip.league || leg.league_name || leg.league || '',
            market_key: slip.market_key || leg.market_key,
            market_label: slip.market_label || leg.market_label,
            odds: slip.odds != null ? slip.odds : leg.odds
        };
    }

    function addLegToSlip(leg, openDrawer) {
        if (!window.HibsBetslip || typeof HibsBetslip.addSelection !== 'function') {
            alert('Betslip not loaded on this page.');
            return false;
        }
        var p = legFromPayload(leg);
        if (!p || !p.odds || parseFloat(p.odds) <= 1) {
            alert('No book price on this leg.');
            return false;
        }
        HibsBetslip.addSelection({
            fid: String(p.fixture_id),
            home: p.home,
            away: p.away,
            league: p.league,
            outcome: mapMarketToOutcome(p.market_key),
            odds: parseFloat(p.odds),
            label: p.market_label
        });
        if (openDrawer !== false) {
            HibsBetslip.openDrawer();
        }
        syncAccaLegsFromBetslip();
        return true;
    }

    function addAccaLegsToSlip(legs) {
        var added = 0;
        (legs || []).forEach(function (leg) {
            if (addLegToSlip(leg, false)) added += 1;
        });
        if (added && window.HibsBetslip) {
            HibsBetslip.openDrawer();
        }
        return added;
    }

    function syncAccaLegsFromBetslip() {
        if (!window.HibsBetslip || typeof HibsBetslip.loadSlip !== 'function') return;
        var slip = HibsBetslip.loadSlip();
        var outcomeLabels = { home: 'Home Win', draw: 'Draw', away: 'Away Win' };
        window.HIBS_ACCA_LEGS = Object.keys(slip).map(function (fid) {
            var s = slip[fid];
            return {
                fixture_id: fid,
                home: s.home,
                away: s.away,
                market_key: s.outcome,
                market_label: s.label || outcomeLabels[s.outcome] || s.outcome,
                odds: s.odds
            };
        });
    }

    function dqBadgeClass(pct) {
        if (pct == null) return '';
        if (pct >= 90) return 'ok';
        if (pct >= 78) return 'mid';
        return 'low';
    }

    function accaReviewHtml(data) {
        var legs = data.legs || [];
        var html = '<div class="hibs-assistant-card hibs-acca-review">';
        if (data.summary) {
            html += '<p class="ac-line"><strong>Acca review</strong> — ' + esc(data.summary) + '</p>';
        }
        legs.forEach(function (leg, i) {
            var dq = leg.data_quality_pct;
            var badge = dq != null
                ? '<span class="fr-dq fr-dq-compact ' + dqBadgeClass(dq) + '">' + dq + '%</span> '
                : '';
            var verdictColor = leg.verdict === 'strong' ? 'var(--green)'
                : (leg.verdict === 'caution' || leg.thin_data) ? '#fde68a' : 'var(--muted)';
            html += '<div class="acca-review-leg" style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(148,163,184,0.15);">';
            html += '<p class="ac-line"><strong>Leg ' + (i + 1) + ':</strong> ' + badge + esc(leg.match || '') + ' — <span style="color:var(--neon);">' + esc(leg.market_label || '') + '</span></p>';
            if (leg.model_pct != null) {
                html += '<p class="ac-line" style="font-size:0.86em;">Model ' + leg.model_pct + '%';
                if (leg.implied_pct != null) html += ' vs implied ' + leg.implied_pct + '%';
                if (leg.edge_pct != null) html += ' · edge ' + (leg.edge_pct >= 0 ? '+' : '') + leg.edge_pct + '%';
                html += '</p>';
            }
            if (leg.xg_snippet) {
                html += '<p class="ac-line" style="font-size:0.84em;color:var(--muted);">' + esc(leg.xg_snippet) + '</p>';
            }
            if (leg.form_snippet) {
                html += '<p class="ac-line" style="font-size:0.84em;color:var(--muted);">' + esc(leg.form_snippet) + '</p>';
            }
            if (leg.data_sources) {
                html += '<p class="ac-line" style="font-size:0.82em;color:var(--muted);">Sources: ' + esc(leg.data_sources) + '</p>';
            }
            html += '<p class="ac-line" style="font-size:0.88em;">' + esc(leg.paragraph || '') + '</p>';
            if (leg.thin_data || (leg.flags && leg.flags.length)) {
                html += '<p class="ac-line" style="font-size:0.86em;color:' + verdictColor + ';">Thin data — caution</p>';
            }
            html += '</div>';
        });
        html += '</div>';
        return html;
    }

    function formatLine(line) {
        var s = esc(line);
        return s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    }

    function oddsHtml(odds) {
        var dec = parseFloat(odds);
        if (!isFinite(dec)) return esc(odds);
        var txt = window.HibsOdds && typeof HibsOdds.formatOdds === 'function'
            ? HibsOdds.formatOdds(dec)
            : dec.toFixed(2);
        return '<span data-odds-dec="' + dec + '">' + txt + '</span>';
    }

    function legPayloadAttr(leg) {
        try {
            return encodeURIComponent(JSON.stringify(legFromPayload(leg) || leg));
        } catch (e) {
            return '';
        }
    }

    function parseLegPayload(raw) {
        if (!raw) return null;
        try {
            return JSON.parse(decodeURIComponent(raw));
        } catch (e) {
            try {
                return JSON.parse(raw);
            } catch (e2) {
                return null;
            }
        }
    }

    function addToSlipButtonHtml(leg) {
        return '<button type="button" class="hibs-assistant-send hibs-leg-slip" data-leg="' + legPayloadAttr(leg) + '">Add to slip</button>';
    }

    function suggestLegCardHtml(leg) {
        var h = '<div class="hibs-assistant-card hibs-leg-card">';
        h += '<p class="ac-line">' + legHtml(leg) + '</p>';
        if (leg.rationale) {
            h += '<p class="ac-line" style="font-size:0.86em;color:var(--muted);">' + esc(leg.rationale) + '</p>';
        }
        if (leg.data_quality_pct != null) {
            h += '<p class="ac-line" style="font-size:0.84em;">Data <span class="fr-dq fr-dq-compact ' + dqBadgeClass(leg.data_quality_pct) + '">' + leg.data_quality_pct + '%</span></p>';
        }
        h += '<p class="ac-line" style="margin-top:6px;">' + addToSlipButtonHtml(leg) + '</p>';
        h += '</div>';
        return h;
    }

    function singleCardHtml(leg) {
        var h = '<div class="hibs-assistant-card">';
        h += '<p class="ac-line"><strong>' + esc(leg.match || (leg.home + ' v ' + leg.away)) + '</strong>';
        if (leg.kickoff_time) h += ' · ' + esc(leg.kickoff_time);
        h += '</p><p class="ac-line"><strong>Pick:</strong> <span style="color:var(--neon)">' + esc(leg.market_label) + '</span>';
        if (leg.odds) h += ' @ ' + oddsHtml(leg.odds);
        if (leg.model_pct != null) h += ' · model ' + leg.model_pct + '%';
        h += '</p>';
        if (leg.is_value && leg.edge_pct != null) {
            h += '<p class="ac-line" style="color:var(--gold);">Value +' + leg.edge_pct + '% edge</p>';
        }
        if (leg.pick_detail) {
            h += '<p class="ac-line" style="font-size:0.88em;">' + formatLine(leg.pick_detail) + '</p>';
        }
        if (leg.rationale && leg.rationale.length) {
            h += '<ul>';
            leg.rationale.forEach(function (b) { h += '<li>' + esc(b) + '</li>'; });
            h += '</ul>';
        }
        h += '<p class="ac-line" style="margin-top:6px;">' + addToSlipButtonHtml(leg) + '</p>';
        h += '</div>';
        return h;
    }

    function accaCardHtml(acca) {
        var legsAttr = encodeURIComponent(JSON.stringify((acca.legs || []).map(legFromPayload)));
        var html = '<div class="hibs-assistant-card hibs-acca-card" data-acca-legs="' + legsAttr + '">';
        html += '<p class="ac-line"><strong>' + esc(acca.title) + '</strong> · ' + acca.leg_count + ' legs</p>';
        if (acca.combined_odds) {
            html += '<p class="ac-line">Combined <strong style="color:var(--gold);">' + oddsHtml(acca.combined_odds) + '</strong>';
            if (acca.joint_confidence_pct != null) {
                html += ' · joint conf. ~' + acca.joint_confidence_pct + '%';
            }
            html += '</p>';
        }
        html += '<ol class="hibs-acca-legs">';
        (acca.legs || []).forEach(function (leg) {
            html += '<li class="hibs-acca-leg-row">' + legHtml(leg);
            html += ' ' + addToSlipButtonHtml(leg);
            html += '</li>';
        });
        html += '</ol>';
        if (acca.rationale && acca.rationale.length) {
            html += '<p class="ac-line" style="font-size:0.88em;color:var(--muted);margin-top:6px;">';
            html += acca.rationale.slice(0, 2).map(function (b) { return esc(b); }).join(' ');
            html += '</p>';
        }
        html += '<p class="ac-line" style="margin-top:8px;"><button type="button" class="hibs-assistant-send hibs-acca-slip" data-acca-slip="1">Add all legs to slip</button></p>';
        html += '</div>';
        return html;
    }

    function builderCardHtml(builder) {
        var html = '<div class="hibs-assistant-card hibs-builder-card">';
        html += '<p class="ac-line"><strong>' + esc(builder.title || 'Bet builder') + '</strong>';
        if (builder.match) html += ' · ' + esc(builder.match);
        if (builder.kickoff_time) html += ' · ' + esc(builder.kickoff_time);
        html += '</p>';
        html += '<ol class="hibs-acca-legs">';
        (builder.legs || []).forEach(function (leg) {
            html += '<li>' + legHtml(leg) + '</li>';
        });
        html += '</ol>';
        if (builder.estimated_independent_odds) {
            html += '<p class="ac-line" style="font-size:0.86em;color:var(--muted);">Component odds multiply to ~' + oddsHtml(builder.estimated_independent_odds) + ' (correlated — get a book quote).</p>';
        }
        if (builder.joint_confidence_pct != null) {
            html += '<p class="ac-line">Model builder confidence: <strong>' + builder.joint_confidence_pct + '%</strong></p>';
        }
        if (builder.rationale && builder.rationale.length) {
            html += '<p class="ac-line" style="font-size:0.88em;color:var(--muted);">' + esc(builder.rationale[0]) + '</p>';
        }
        if (builder.disclaimer) {
            html += '<p class="ac-line" style="font-size:0.78em;color:var(--muted);">' + esc(builder.disclaimer) + '</p>';
        }
        html += '</div>';
        return html;
    }

    function fixtureCardHtml(pkt, compact) {
        var si = pkt.structured_insight || {};
        var html = '<div class="hibs-assistant-card">';
        var ko = pkt.kickoff_time || '';
        html += '<p class="ac-line"><strong>Match:</strong> ' + esc(si.match || (pkt.home + ' vs ' + pkt.away));
        if (ko) html += ' · ' + esc(ko);
        html += '</p>';
        html += '<p class="ac-line"><strong>Pick:</strong> <span style="color:var(--neon)">' + esc(si.pick || '—') + '</span></p>';
        if (si.mode === 'odds_only') {
            html += '<p class="ac-line" style="color:#fde68a;">Thin data — odds only, not used in accas.</p>';
        }
        if (si.rationale && si.rationale.length && !compact) {
            html += '<ul>';
            si.rationale.forEach(function (b) { html += '<li>' + esc(b) + '</li>'; });
            html += '</ul>';
        }
        if (si.confidence_pct != null) {
            html += '<p class="ac-line"><strong>Confidence:</strong> ' + si.confidence_pct + '%</p>';
        }
        if (pkt.data_quality_pct != null) {
            html += '<p class="ac-line" style="font-size:0.88em;">Data <span class="fr-dq fr-dq-compact ' + dqBadgeClass(pkt.data_quality_pct) + '">' + pkt.data_quality_pct + '%</span></p>';
        }
        if (pkt.xg_source) {
            html += '<p class="ac-line" style="font-size:0.84em;color:var(--muted);">xG source: ' + esc(pkt.xg_source) + '</p>';
        }
        if (si.rationale_metrics && si.rationale_metrics.length && !compact) {
            html += '<ul style="font-size:0.86em;">';
            si.rationale_metrics.slice(0, 4).forEach(function (m) {
                html += '<li><strong>' + esc(m.label) + ':</strong> ' + esc(m.value) + (m.note ? ' — ' + esc(m.note) : '') + '</li>';
            });
            html += '</ul>';
        }
        if (pkt.has_value_bet && pkt.value_bets_display && pkt.value_bets_display[0]) {
            var v = pkt.value_bets_display[0];
            html += '<p class="ac-line" style="color:var(--gold);">Value: ' + esc(v.market_label) + ' @ ' + oddsHtml(v.odds);
            if (v.edge_pct != null) html += ' · +' + v.edge_pct + '%';
            html += '</p>';
        }
        html += '</div>';
        return html;
    }

    function legHtml(leg) {
        var ko = leg.kickoff_time ? esc(leg.kickoff_time) + ' ' : '';
        var s = ko + '<strong>' + esc(leg.home) + '</strong> v <strong>' + esc(leg.away) + '</strong> — ' + esc(leg.market_label);
        if (leg.odds) s += ' @ ' + oddsHtml(leg.odds);
        if (leg.model_pct != null) s += ' (' + leg.model_pct + '%)';
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
        wireSlipButtons(el);
        body.scrollTop = body.scrollHeight;
    }

    function wireSlipButtons(root) {
        if (!root) return;
        root.querySelectorAll('.hibs-leg-slip').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var leg = parseLegPayload(btn.getAttribute('data-leg'));
                if (leg) addLegToSlip(leg, true);
            });
        });
        root.querySelectorAll('[data-acca-slip]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var card = btn.closest('.hibs-acca-card');
                if (!card) return;
                var legs = parseLegPayload(card.getAttribute('data-acca-legs'));
                if (legs && legs.length) addAccaLegsToSlip(legs);
            });
        });
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
            })
            .catch(function () { /* keep embedded snapshot */ });
    }

    document.addEventListener('DOMContentLoaded', function () {
        init();
        if (!packets.length) refreshFromApi();
        document.addEventListener('hibs-betslip-change', syncAccaLegsFromBetslip);
        syncAccaLegsFromBetslip();
    });

    window.HibsAssistant = {
        addLegToSlip: addLegToSlip,
        addAccaLegsToSlip: addAccaLegsToSlip,
        syncAccaLegsFromBetslip: syncAccaLegsFromBetslip
    };
})();

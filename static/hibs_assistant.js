(function () {
    'use strict';

    var packets = [];
    var recommendations = null;
    var panel, body, fab, closeBtn, fixtureSel, form, inputEl, sendBtn;
    var busy = false;

    function init() {
        loadSnapshot(window.HIBS_ASSISTANT);
        panel = document.getElementById('hibs-assistant-panel');
        body = document.getElementById('hibs-assistant-body');
        fab = document.getElementById('hibs-assistant-fab');
        closeBtn = document.getElementById('hibs-assistant-close');
        fixtureSel = document.getElementById('hibs-assistant-fixture');
        form = document.getElementById('hibs-assistant-form');
        inputEl = document.getElementById('hibs-assistant-input');
        sendBtn = document.getElementById('hibs-assistant-send');
        if (!panel || !body || !fab) return;

        populateFixtureSelect();
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
            appendBot(welcomeHtml());
        }
    }

    function welcomeHtml() {
        return '<div class="hibs-assistant-card"><p class="ac-line">Ask anything about fixtures, stats, value, or accas. I only use matches with <strong>strong data coverage</strong>.</p><p class="ac-line" style="font-size:0.88em;color:var(--muted);">Try: <em>best bets</em>, <em>mixed acca</em>, <em>BTTS acca</em>, <em>stats for Hibs v Hearts</em>, <em>deep dive all</em>.</p></div>';
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
        var fid = fixtureSel && fixtureSel.value ? fixtureSel.value : null;
        fetch('/api/assistant/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: q, fixture_id: fid })
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
            var html = '<div class="hibs-assistant-card"><ul>';
            (block.lines || []).forEach(function (line) {
                html += '<li>' + formatLine(line) + '</li>';
            });
            html += '</ul></div>';
            appendBot(html);
            return;
        }
        if (t === 'summary') {
            var s = block.data || {};
            var h = '<div class="hibs-assistant-card"><p class="ac-line"><strong>Deep dive</strong></p>';
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
        if (t === 'accas') {
            (block.items || []).forEach(function (a) { appendBot(accaCardHtml(a)); });
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
                    appendBot('<p class="ac-line">' + legHtml(leg) + '</p>');
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
        }
    }

    function formatLine(line) {
        var s = esc(line);
        return s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    }

    function singleCardHtml(leg) {
        var h = '<div class="hibs-assistant-card">';
        h += '<p class="ac-line"><strong>' + esc(leg.match || (leg.home + ' v ' + leg.away)) + '</strong>';
        if (leg.kickoff_time) h += ' · ' + esc(leg.kickoff_time);
        h += '</p><p class="ac-line"><strong>Pick:</strong> <span style="color:var(--neon)">' + esc(leg.market_label) + '</span>';
        if (leg.odds) h += ' @ ' + leg.odds;
        if (leg.model_pct != null) h += ' · model ' + leg.model_pct + '%';
        h += '</p>';
        if (leg.is_value && leg.edge_pct != null) {
            h += '<p class="ac-line" style="color:var(--gold);">Value +' + leg.edge_pct + '% edge</p>';
        }
        if (leg.rationale && leg.rationale.length) {
            h += '<ul>';
            leg.rationale.forEach(function (b) { h += '<li>' + esc(b) + '</li>'; });
            h += '</ul>';
        }
        h += '</div>';
        return h;
    }

    function accaCardHtml(acca) {
        var html = '<div class="hibs-assistant-card hibs-acca-card">';
        html += '<p class="ac-line"><strong>' + esc(acca.title) + '</strong> · ' + acca.leg_count + ' legs</p>';
        if (acca.combined_odds) {
            html += '<p class="ac-line">Combined <strong style="color:var(--gold);">' + acca.combined_odds + '</strong>';
            if (acca.joint_confidence_pct != null) {
                html += ' · joint conf. ~' + acca.joint_confidence_pct + '%';
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
            acca.rationale.forEach(function (b) {
                html += '<li style="font-size:0.88em;color:var(--muted);">' + esc(b) + '</li>';
            });
            html += '</ul>';
        }
        html += '<p class="ac-line" style="margin-top:8px;"><button type="button" class="hibs-assistant-send hibs-acca-slip" data-acca-slip="1">Add legs to betslip</button></p>';
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
            html += '<p class="ac-line" style="font-size:0.88em;">Data ' + pkt.data_quality_pct + '%</p>';
        }
        if (pkt.has_value_bet && pkt.value_bets_display && pkt.value_bets_display[0]) {
            var v = pkt.value_bets_display[0];
            html += '<p class="ac-line" style="color:var(--gold);">Value: ' + esc(v.market_label) + ' @ ' + v.odds;
            if (v.edge_pct != null) html += ' · +' + v.edge_pct + '%';
            html += '</p>';
        }
        html += '</div>';
        return html;
    }

    function legHtml(leg) {
        var ko = leg.kickoff_time ? esc(leg.kickoff_time) + ' ' : '';
        var s = ko + '<strong>' + esc(leg.home) + '</strong> v <strong>' + esc(leg.away) + '</strong> — ' + esc(leg.market_label);
        if (leg.odds) s += ' @ ' + leg.odds;
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
        wireAccaSlipButtons(el);
        body.scrollTop = body.scrollHeight;
    }

    function wireAccaSlipButtons(root) {
        if (!root || !window.HibsBetslip) return;
        root.querySelectorAll('[data-acca-slip]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var card = btn.closest('.hibs-acca-card');
                if (!card) return;
                /* legs parsed from DOM is fragile — user can use pick menus on dashboard */
                HibsBetslip.openDrawer();
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
                populateFixtureSelect();
            })
            .catch(function () { /* keep embedded snapshot */ });
    }

    document.addEventListener('DOMContentLoaded', function () {
        init();
        if (!packets.length) refreshFromApi();
    });
})();

/**
 * Shared betslip (localStorage) + slide-out drawer. Used on dashboard and Acca Builder.
 */
(function (global) {
  const STORAGE_KEY = "hibs_betslip_v1";

  function loadSlip() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (e) {
      return {};
    }
  }

  function saveSlip(slip) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(slip));
    } catch (e) {
      /* ignore quota */
    }
    global.dispatchEvent(new CustomEvent("hibs-betslip-change", { detail: { slip } }));
  }

  function addSelection(entry) {
    const slip = loadSlip();
    const fid = String(entry.fid || entry.id || "");
    if (!fid) return;
    slip[fid] = {
      home: entry.home || "?",
      away: entry.away || "?",
      league: entry.league || "",
      outcome: entry.outcome || "home",
      odds: parseFloat(entry.odds) || 1.01,
      label: entry.label || entry.outcome || "",
    };
    saveSlip(slip);
    renderDrawer();
  }

  function removeSelection(fid) {
    const slip = loadSlip();
    delete slip[String(fid)];
    saveSlip(slip);
    renderDrawer();
  }

  function clearSlip() {
    saveSlip({});
    renderDrawer();
  }

  function countSelections() {
    return Object.keys(loadSlip()).length;
  }

  function formatOdds(odds) {
    if (global.HibsOdds && typeof global.HibsOdds.formatOdds === "function") {
      return global.HibsOdds.formatOdds(odds);
    }
    return (Number(odds) || 0).toFixed(2);
  }

  function renderDrawer() {
    const body = document.getElementById("betslip-drawer-body");
    const empty = document.getElementById("betslip-drawer-empty");
    const countEl = document.getElementById("betslip-drawer-count");
    const oddsEl = document.getElementById("betslip-drawer-odds");
    const fabBadge = document.getElementById("betslip-fab-count");
    if (!body) return;

    const slip = loadSlip();
    const keys = Object.keys(slip);
    if (countEl) countEl.textContent = String(keys.length);
    if (fabBadge) {
      fabBadge.textContent = String(keys.length);
      fabBadge.style.display = keys.length ? "inline-flex" : "none";
    }
    body.querySelectorAll(".betslip-leg").forEach((n) => n.remove());
    if (empty) empty.style.display = keys.length ? "none" : "block";

    let totalOdds = 1;
    keys.forEach((fid) => {
      const s = slip[fid];
      totalOdds *= s.odds || 1;
      const ol =
        s.outcome === "home" ? s.home : s.outcome === "away" ? s.away : "Draw";
      const row = document.createElement("div");
      row.className = "betslip-leg";
      row.innerHTML =
        '<button type="button" class="betslip-leg-rm" data-fid="' +
        fid +
        '" aria-label="Remove">✕</button>' +
        '<div class="betslip-leg-meta">' +
        (s.league ? escapeHtml(s.league) + " · " : "") +
        escapeHtml(s.home) +
        " v " +
        escapeHtml(s.away) +
        "</div>" +
        '<div class="betslip-leg-row"><span class="betslip-leg-pick">' +
        escapeHtml(s.label || ol) +
        '</span><span class="betslip-leg-odds" data-odds-dec="' +
        (s.odds || 0) +
        '">' +
        formatOdds(s.odds || 0) +
        "</span></div>";
      body.appendChild(row);
    });
    body.querySelectorAll(".betslip-leg-rm").forEach((btn) => {
      btn.addEventListener("click", function () {
        removeSelection(btn.getAttribute("data-fid"));
      });
    });
    if (oddsEl) oddsEl.textContent = keys.length ? formatOdds(totalOdds) : "—";

    const stakeIn = document.getElementById("betslip-drawer-stake");
    if (stakeIn) recalcDrawerReturns(stakeIn.value);
  }

  function recalcDrawerReturns(stakeVal) {
    const slip = loadSlip();
    const keys = Object.keys(slip);
    const stake = parseFloat(stakeVal) || 0;
    const retEl = document.getElementById("betslip-drawer-return");
    if (!retEl) return;
    if (!keys.length) {
      retEl.textContent = "£—";
      return;
    }
    const totalOdds = keys.reduce((a, k) => a * (slip[k].odds || 1), 1);
    retEl.textContent = "£" + (stake * totalOdds).toFixed(2);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function openDrawer() {
    const el = document.getElementById("betslip-drawer");
    const backdrop = document.getElementById("betslip-backdrop");
    if (el) {
      el.classList.add("open");
      el.setAttribute("aria-hidden", "false");
    }
    if (backdrop) backdrop.classList.add("open");
    renderDrawer();
  }

  function closeDrawer() {
    const el = document.getElementById("betslip-drawer");
    const backdrop = document.getElementById("betslip-backdrop");
    if (el) {
      el.classList.remove("open");
      el.setAttribute("aria-hidden", "true");
    }
    if (backdrop) backdrop.classList.remove("open");
  }

  function wireDrawerUi() {
    const fab = document.getElementById("betslip-fab");
    const closeBtn = document.getElementById("betslip-drawer-close");
    const backdrop = document.getElementById("betslip-backdrop");
    const stakeIn = document.getElementById("betslip-drawer-stake");
    if (fab) fab.addEventListener("click", openDrawer);
    if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
    if (backdrop) backdrop.addEventListener("click", closeDrawer);
    if (stakeIn) stakeIn.addEventListener("input", function () {
      recalcDrawerReturns(stakeIn.value);
    });
    document.querySelectorAll("[data-betslip-open]").forEach((btn) => {
      btn.addEventListener("click", openDrawer);
    });
    renderDrawer();
  }

  global.HibsBetslip = {
    loadSlip,
    saveSlip,
    addSelection,
    removeSelection,
    clearSlip,
    countSelections,
    renderDrawer,
    openDrawer,
    closeDrawer,
    wireDrawerUi,
    STORAGE_KEY,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wireDrawerUi);
  } else {
    wireDrawerUi();
  }
  document.addEventListener("hibs-odds-format-change", renderDrawer);
})(window);

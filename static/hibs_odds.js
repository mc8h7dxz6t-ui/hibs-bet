(function (global) {
  "use strict";

  var STORAGE_KEY = "hibs_odds_format_v1";
  var currentFormat = "dec";

  function normaliseFormat(format) {
    return format === "frac" ? "frac" : "dec";
  }

  function readPreference() {
    try {
      return normaliseFormat(global.localStorage.getItem(STORAGE_KEY));
    } catch (e) {
      return "dec";
    }
  }

  function savePreference(format) {
    try {
      global.localStorage.setItem(STORAGE_KEY, normaliseFormat(format));
    } catch (e) {
      /* localStorage may be unavailable in private contexts */
    }
  }

  function gcd(a, b) {
    a = Math.abs(a);
    b = Math.abs(b);
    while (b) {
      var t = b;
      b = a % b;
      a = t;
    }
    return a || 1;
  }

  function decimalToFraction(decimal) {
    var profit = Number(decimal) - 1;
    if (!isFinite(profit) || profit <= 0) return "";

    var bestNum = 1;
    var bestDen = 1;
    var bestErr = Infinity;
    for (var den = 1; den <= 100; den += 1) {
      var num = Math.round(profit * den);
      if (num <= 0) continue;
      var err = Math.abs(profit - num / den);
      if (err < bestErr) {
        bestNum = num;
        bestDen = den;
        bestErr = err;
      }
      if (err < 0.0001) break;
    }

    var div = gcd(bestNum, bestDen);
    return bestNum / div + "/" + bestDen / div;
  }

  function formatOdds(decimal, format) {
    var dec = Number(decimal);
    if (!isFinite(dec) || dec <= 0) return "";
    return normaliseFormat(format || currentFormat) === "frac"
      ? decimalToFraction(dec)
      : dec.toFixed(2);
  }

  function renderOddsNode(node, format) {
    var formatted = formatOdds(node.getAttribute("data-odds-dec"), format);
    if (!formatted) return;

    var template = node.getAttribute("data-odds-template");
    if (template) {
      node.textContent = template.replace(/\{odds\}/g, formatted);
      return;
    }

    node.textContent =
      (node.getAttribute("data-odds-prefix") || "") +
      formatted +
      (node.getAttribute("data-odds-suffix") || "");
  }

  function syncToggleButtons(format) {
    document.querySelectorAll(".odds-toggle .ot[data-odds]").forEach(function (btn) {
      var active = normaliseFormat(btn.getAttribute("data-odds")) === format;
      btn.classList.toggle("ot-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function applyFormat(format, options) {
    currentFormat = normaliseFormat(format);
    if (!options || options.persist !== false) savePreference(currentFormat);
    document.documentElement.setAttribute("data-odds-format", currentFormat);
    syncToggleButtons(currentFormat);
    document.querySelectorAll("[data-odds-dec]").forEach(function (node) {
      renderOddsNode(node, currentFormat);
    });
    document.dispatchEvent(
      new CustomEvent("hibs-odds-format-change", { detail: { format: currentFormat } })
    );
  }

  function bindToggles(root) {
    (root || document).querySelectorAll(".odds-toggle .ot[data-odds]").forEach(function (btn) {
      if (btn.getAttribute("data-odds-bound") === "1") return;
      btn.setAttribute("data-odds-bound", "1");
      btn.addEventListener("click", function () {
        applyFormat(btn.getAttribute("data-odds"));
      });
    });
    syncToggleButtons(currentFormat);
  }

  function refresh(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-odds-dec]").forEach(function (node) {
      renderOddsNode(node, currentFormat);
    });
    bindToggles(scope);
  }

  function observeDynamicOdds() {
    if (!global.MutationObserver || !document.body) return;
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        mutation.addedNodes.forEach(function (node) {
          if (!node.querySelectorAll) return;
          if (node.matches && node.matches("[data-odds-dec]")) {
            renderOddsNode(node, currentFormat);
          }
          refresh(node);
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function init() {
    currentFormat = readPreference();
    bindToggles(document);
    applyFormat(currentFormat, { persist: false });
    observeDynamicOdds();
  }

  global.HibsOdds = {
    STORAGE_KEY: STORAGE_KEY,
    applyFormat: applyFormat,
    bindToggles: bindToggles,
    formatOdds: formatOdds,
    refresh: refresh,
    readPreference: readPreference,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})(window);

/**
 * Onion Link Rewriter — bridges .onion links to work in regular browsers.
 *
 * Strategy (in preference order):
 *   1. Local Tor proxy at /api/onion-proxy?url=...  (if user has Tor running)
 *   2. Tor2web gateway (onion.ly) — clearnet gateway, no Tor install needed
 *   3. Raw .onion link (for users already in Tor Browser)
 *
 * The active mode is stored in localStorage and can be changed via the
 * onion settings dropdown that appears on Deep Web result pages.
 */
(function () {
  "use strict";

  // Only activate on onion search pages
  const resultsContainer = document.querySelector('[data-type="onion"]');
  if (!resultsContainer) return;

  // ---------------------------------------------------------------------------
  // Config
  // ---------------------------------------------------------------------------
  const GATEWAY_SUFFIX = ".onion.ly";          // Tor2web clearnet gateway
  const LOCAL_PROXY    = "/api/onion-proxy?url="; // Flask proxy route

  const MODES = {
    gateway:  { label: "Tor2web Gateway", desc: "Open via onion.ly (no Tor needed)" },
    proxy:    { label: "Local Tor Proxy",  desc: "Route through local Tor (port 9050)" },
    raw:      { label: "Raw .onion",       desc: "Direct link (requires Tor Browser)" },
  };

  let activeMode = localStorage.getItem("onion-mode") || "raw";

  // ---------------------------------------------------------------------------
  // Rewrite a single .onion URL based on current mode
  // ---------------------------------------------------------------------------
  function rewriteUrl(originalUrl) {
    if (!originalUrl || !originalUrl.includes(".onion")) return originalUrl;

    try {
      const u = new URL(originalUrl);
      if (!u.hostname.endsWith(".onion")) return originalUrl;

      switch (activeMode) {
        case "gateway": {
          // http://abc123.onion/path  =>  https://abc123.onion.ly/path
          const gwHost = u.hostname + GATEWAY_SUFFIX.replace(".onion", "");
          return `https://${gwHost}${u.pathname}${u.search}${u.hash}`;
        }
        case "proxy":
          return LOCAL_PROXY + encodeURIComponent(originalUrl);
        case "raw":
        default:
          return originalUrl;
      }
    } catch {
      return originalUrl;
    }
  }

  // ---------------------------------------------------------------------------
  // Rewrite all .onion links currently on the page
  // ---------------------------------------------------------------------------
  function rewriteAllLinks() {
    const links = resultsContainer.querySelectorAll("a[href]");
    let count = 0;

    links.forEach(link => {
      // Store original href on first pass
      if (!link.dataset.onionOriginal && link.href.includes(".onion")) {
        link.dataset.onionOriginal = link.href;
      }

      const original = link.dataset.onionOriginal;
      if (!original) return;

      link.href = rewriteUrl(original);
      link.rel = "noopener noreferrer";
      count++;
    });

    // Also rewrite the <cite> display URLs — show original .onion for clarity
    // (no rewrite needed, they're just text)

    updateModeIndicator();
    if (count) console.log(`[onion-rewriter] Rewrote ${count} links (mode: ${activeMode})`);
  }

  // ---------------------------------------------------------------------------
  // Mode selector UI — injected into the onion warning banner
  // ---------------------------------------------------------------------------
  function injectModeSelector() {
    const banner = document.querySelector(".onion-warning");
    if (!banner || banner.querySelector(".onion-mode-select")) return;

    const wrapper = document.createElement("span");
    wrapper.className = "onion-mode-wrapper";
    wrapper.innerHTML = `
      <select class="onion-mode-select" aria-label="Link open mode">
        ${Object.entries(MODES).map(([k, v]) =>
          `<option value="${k}" ${k === activeMode ? "selected" : ""}>${v.label}</option>`
        ).join("")}
      </select>
    `;

    banner.appendChild(wrapper);

    wrapper.querySelector("select").addEventListener("change", e => {
      activeMode = e.target.value;
      localStorage.setItem("onion-mode", activeMode);
      rewriteAllLinks();
    });
  }

  // ---------------------------------------------------------------------------
  // Mode indicator badge on each result
  // ---------------------------------------------------------------------------
  function updateModeIndicator() {
    const badge = MODES[activeMode];
    const existing = document.querySelectorAll(".onion-mode-tag");

    if (activeMode === "raw") {
      existing.forEach(el => el.remove());
      return;
    }

    const label = activeMode === "gateway" ? "via gateway" : "via proxy";

    // Update existing tags instead of destroy/recreate
    existing.forEach(el => {
      if (el.textContent !== label) {
        el.textContent = label;
        el.title = badge.desc;
      }
    });

    // Add tags to new headers that don't have one yet
    document.querySelectorAll(".onion-result-header").forEach(header => {
      if (!header.querySelector(".onion-mode-tag")) {
        const tag = document.createElement("span");
        tag.className = "onion-mode-tag";
        tag.textContent = label;
        tag.title = badge.desc;
        header.appendChild(tag);
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Observe for dynamically loaded results (infinite scroll)
  // ---------------------------------------------------------------------------
  let rewriteTimer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(rewriteTimer);
    rewriteTimer = setTimeout(rewriteAllLinks, 100);
  });
  observer.observe(resultsContainer, { childList: true, subtree: true });

  // ---------------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------------
  injectModeSelector();
  rewriteAllLinks();

})();

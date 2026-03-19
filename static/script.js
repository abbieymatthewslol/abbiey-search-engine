// Sync paid access token from localStorage to cookie so server can validate it
// across restarts without requiring re-payment.
(function syncAccessCookie() {
  try {
    const token = localStorage.getItem("abbiey_access_token");
    if (token && token.length === 32) {
      document.cookie = "abbiey_token=" + token + ";path=/;max-age=" + (365 * 24 * 3600) + ";SameSite=Lax";
    }
  } catch (e) {}
})();

document.addEventListener("DOMContentLoaded", () => {
  const html = document.documentElement;

  // ===== Search loading indicator =====
  const searchForm = document.getElementById("search-form");
  const searchBtn = document.querySelector(".search-btn");
  if (searchForm && searchBtn) {
    searchForm.addEventListener("submit", () => {
      const q = document.getElementById("search-input");
      if (!q || !q.value.trim()) return;
      searchBtn.classList.add("loading");
      searchBtn.innerHTML = '<span class="btn-spinner"></span> Searching';
      const bar = document.createElement("div");
      bar.className = "search-loading-bar";
      document.body.appendChild(bar);
    });
  }

  // ===== Theme toggle =====
  const toggle = document.getElementById("theme-toggle");
  const saved = localStorage.getItem("theme");
  if (saved) html.setAttribute("data-theme", saved);

  if (toggle) toggle.addEventListener("click", () => {
    const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
  });

  // ===== Custom accent color =====
  const savedAccent = localStorage.getItem("accent-color");
  if (savedAccent) applyAccentColor(savedAccent);

  function applyAccentColor(color) {
    html.style.setProperty("--accent", color);
    // Generate a darker variant
    const dim = adjustBrightness(color, -30);
    html.style.setProperty("--accent-dim", dim);
    localStorage.setItem("accent-color", color);
    // Mark active swatch
    document.querySelectorAll(".color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === color);
    });
  }

  function adjustBrightness(hex, amount) {
    hex = hex.replace("#", "");
    const r = Math.max(0, Math.min(255, parseInt(hex.slice(0, 2), 16) + amount));
    const g = Math.max(0, Math.min(255, parseInt(hex.slice(2, 4), 16) + amount));
    const b = Math.max(0, Math.min(255, parseInt(hex.slice(4, 6), 16) + amount));
    return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
  }

  // Theme settings popover
  // ===== Settings Modal =====
  const _S = {
    theme:         { key: "theme",                 def: "dark"   },
    accent:        { key: "accent-color",          def: "#6ee7b7"},
    density:       { key: "density",               def: "default"},
    fontSize:      { key: "abbiey_font_size",      def: "medium" },
    fontFamily:    { key: "abbiey_font_family",    def: "system" },
    safesearch:    { key: "abbiey_safesearch",     def: "off"    },
    newTab:        { key: "abbiey_new_tab",        def: "true"   },
    defaultTab:    { key: "abbiey_default_tab",    def: "text"   },
    aiSummary:     { key: "abbiey_ai_summary",     def: "true"   },
    autocomplete:  { key: "abbiey_autocomplete",   def: "true"   },
    persistRegion: { key: "abbiey_region_persist", def: "false"  },
    history:       { key: "abbiey_history",        def: "true"   },
    showCards:     { key: "abbiey_show_cards",     def: "true"   },
    showFavicons:  { key: "abbiey_show_favicons",  def: "true"   },
    showDates:     { key: "abbiey_show_dates",     def: "true"   },
  };
  function gs(name) { return localStorage.getItem(_S[name].key) ?? _S[name].def; }
  function ss(name, val) { localStorage.setItem(_S[name].key, val); }

  // Apply all settings on load
  function applyAllSettings() {
    // Font size — change html font-size so rem units scale
    const fsMap = { small: "13.5px", medium: "", large: "17.5px", xl: "20px" };
    const fs = gs("fontSize");
    html.style.fontSize = fsMap[fs] || "";
    html.setAttribute("data-font-size", fs);

    // Font family
    const ffMap = {
      system: "",
      serif:  "Georgia, 'Times New Roman', serif",
      mono:   "'SF Mono', 'Fira Code', Consolas, monospace",
    };
    html.setAttribute("data-font-family", gs("fontFamily"));
    document.body.style.fontFamily = ffMap[gs("fontFamily")] || "";

    // Safe search hidden input
    const ssInput = document.getElementById("safesearch-input");
    if (ssInput) ssInput.value = gs("safesearch");

    // Default tab (only set on homepage, not when already on a search tab)
    if (!window.__searchType) {
      const typeInput = document.getElementById("search-type-input");
      if (typeInput) typeInput.value = gs("defaultTab");
    }

    // Open in new tab
    if (gs("newTab") === "false") {
      document.querySelectorAll("a.result-title[target='_blank']").forEach(a => a.removeAttribute("target"));
    }

    // AI summary
    const aiCard = document.getElementById("ai-summary-card");
    if (aiCard && gs("aiSummary") === "false") aiCard.style.display = "none";

    // Answer cards
    if (gs("showCards") === "false") {
      [".calculator-card",".color-card",".unit-convert-card",".knowledge-panel",
       ".weather-card",".dictionary-card",".qr-card"].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => { el.style.display = "none"; });
      });
    }

    // Favicons
    if (gs("showFavicons") === "false") {
      const st = document.createElement("style");
      st.id = "hide-favicons-style";
      st.textContent = ".result-favicon{display:none!important}";
      document.head.appendChild(st);
    }

    // Result dates
    if (gs("showDates") === "false") {
      const st = document.createElement("style");
      st.id = "hide-dates-style";
      st.textContent = ".result-date{display:none!important}";
      document.head.appendChild(st);
    }

    // Persist region: restore saved region on page load
    if (gs("persistRegion") === "true") {
      const savedReg = localStorage.getItem("abbiey_region");
      const rInput = document.getElementById("region-input");
      const rSelect = document.getElementById("region-select");
      if (savedReg && rInput && !rInput.value) {
        rInput.value = savedReg;
        if (rSelect) rSelect.value = savedReg;
      }
    }
  }

  applyAllSettings();

  // ===== Density toggle (header quick-toggle) =====
  const densityBtn = document.getElementById("density-toggle");
  const densityLevels = ["compact", "default", "comfortable"];
  const savedDensity = gs("density");
  html.setAttribute("data-density", savedDensity);

  if (densityBtn) {
    densityBtn.addEventListener("click", () => {
      const current = html.getAttribute("data-density") || "default";
      const idx = densityLevels.indexOf(current);
      const next = densityLevels[(idx + 1) % densityLevels.length];
      html.setAttribute("data-density", next);
      ss("density", next);
      densityBtn.title = `Density: ${next}`;
      // keep settings modal in sync if open
      syncBtnGroup("density-group", next);
    });
    densityBtn.title = `Density: ${savedDensity}`;
  }

  // ===== Open / close settings modal =====
  const settingsBtn = document.getElementById("theme-settings-btn");
  const settingsOverlay = document.getElementById("settings-overlay");
  const settingsClose = document.getElementById("settings-close");

  function openSettings() {
    settingsOverlay.removeAttribute("hidden");
    syncSettingsUI();
  }
  function closeSettings() {
    if (!settingsOverlay || settingsOverlay.hasAttribute("hidden")) return;
    settingsOverlay.classList.add("closing");
    setTimeout(() => {
      settingsOverlay.setAttribute("hidden", "");
      settingsOverlay.classList.remove("closing");
    }, 140);
  }

  if (settingsBtn) settingsBtn.addEventListener("click", (e) => { e.stopPropagation(); openSettings(); });
  if (settingsClose) settingsClose.addEventListener("click", closeSettings);
  if (settingsOverlay) {
    settingsOverlay.addEventListener("click", (e) => { if (e.target === settingsOverlay) closeSettings(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !settingsOverlay.hasAttribute("hidden")) closeSettings(); });
  }

  // ===== Header overflow dropdown =====
  const overflowBtn = document.getElementById("header-overflow-btn");
  const overflowMenu = document.getElementById("header-overflow-menu");
  if (overflowBtn && overflowMenu) {
    overflowBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (overflowMenu.hasAttribute("hidden")) {
        overflowMenu.removeAttribute("hidden");
      } else {
        overflowMenu.setAttribute("hidden", "");
      }
    });
    document.addEventListener("click", (e) => {
      if (!overflowMenu.hasAttribute("hidden") && !overflowMenu.contains(e.target) && e.target !== overflowBtn) {
        overflowMenu.setAttribute("hidden", "");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") overflowMenu.setAttribute("hidden", "");
    });
  }

  // ===== Sync UI to current values =====
  function syncBtnGroup(id, activeVal) {
    const g = document.getElementById(id);
    if (!g) return;
    g.querySelectorAll(".settings-seg-btn").forEach(b => b.classList.toggle("active", b.dataset.val === activeVal));
  }
  function syncToggle(id, checked) {
    const el = document.getElementById(id);
    if (el) el.checked = checked;
  }
  function syncSettingsUI() {
    syncBtnGroup("theme-btn-group",    gs("theme"));
    syncBtnGroup("density-group",      gs("density"));
    syncBtnGroup("font-size-group",    gs("fontSize"));
    syncBtnGroup("font-family-group",  gs("fontFamily"));
    syncBtnGroup("safesearch-group",   gs("safesearch"));
    syncBtnGroup("default-tab-group",  gs("defaultTab"));
    syncBtnGroup("newtab-group",       gs("newTab"));
    syncToggle("ai-summary-toggle",    gs("aiSummary")     === "true");
    syncToggle("autocomplete-toggle",  gs("autocomplete")  === "true");
    syncToggle("persist-region-toggle",gs("persistRegion") === "true");
    syncToggle("history-toggle",       gs("history")       === "true");
    syncToggle("cards-toggle",         gs("showCards")     === "true");
    syncToggle("favicons-toggle",      gs("showFavicons")  === "true");
    syncToggle("dates-toggle",         gs("showDates")     === "true");
    const cc = document.getElementById("custom-color");
    if (cc) cc.value = gs("accent");
    // mark active swatch
    document.querySelectorAll(".color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === gs("accent"));
    });
  }

  // ===== Wire segmented button groups =====
  function wireBtnGroup(groupId, settingName, onChange) {
    const g = document.getElementById(groupId);
    if (!g) return;
    g.querySelectorAll(".settings-seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        ss(settingName, btn.dataset.val);
        syncBtnGroup(groupId, btn.dataset.val);
        if (onChange) onChange(btn.dataset.val);
      });
    });
  }
  function wireToggle(id, settingName, onChange) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      ss(settingName, el.checked ? "true" : "false");
      if (onChange) onChange(el.checked);
    });
  }

  wireBtnGroup("theme-btn-group", "theme", (val) => {
    html.setAttribute("data-theme", val);
    localStorage.setItem("theme", val);
  });
  wireBtnGroup("density-group", "density", (val) => {
    html.setAttribute("data-density", val);
    ss("density", val);
    densityBtn && (densityBtn.title = `Density: ${val}`);
  });
  wireBtnGroup("font-size-group", "fontSize", (val) => {
    const m = { small: "13.5px", medium: "", large: "17.5px", xl: "20px" };
    html.style.fontSize = m[val] || "";
    html.setAttribute("data-font-size", val);
  });
  wireBtnGroup("font-family-group", "fontFamily", (val) => {
    const m = { system: "", serif: "Georgia,'Times New Roman',serif", mono: "'SF Mono','Fira Code',Consolas,monospace" };
    document.body.style.fontFamily = m[val] || "";
    html.setAttribute("data-font-family", val);
  });
  wireBtnGroup("safesearch-group", "safesearch", (val) => {
    const inp = document.getElementById("safesearch-input");
    if (inp) inp.value = val;
  });
  wireBtnGroup("default-tab-group", "defaultTab", null);
  wireBtnGroup("newtab-group", "newTab", (val) => {
    document.querySelectorAll("a.result-title").forEach(a => {
      if (val === "true") a.setAttribute("target", "_blank");
      else a.removeAttribute("target");
    });
  });

  wireToggle("ai-summary-toggle", "aiSummary", (checked) => {
    const c = document.getElementById("ai-summary-card");
    if (c) c.style.display = checked ? "" : "none";
  });
  wireToggle("autocomplete-toggle", "autocomplete", null);
  wireToggle("persist-region-toggle", "persistRegion", null);
  wireToggle("history-toggle", "history", null);
  wireToggle("cards-toggle", "showCards", (checked) => {
    [".calculator-card",".color-card",".unit-convert-card",".knowledge-panel",
     ".weather-card",".dictionary-card",".qr-card"].forEach(sel => {
      document.querySelectorAll(sel).forEach(el => { el.style.display = checked ? "" : "none"; });
    });
  });
  wireToggle("favicons-toggle", "showFavicons", (checked) => {
    let st = document.getElementById("hide-favicons-style");
    if (!checked) {
      if (!st) { st = document.createElement("style"); st.id = "hide-favicons-style"; document.head.appendChild(st); }
      st.textContent = ".result-favicon{display:none!important}";
    } else if (st) { st.textContent = ""; }
  });
  wireToggle("dates-toggle", "showDates", (checked) => {
    let st = document.getElementById("hide-dates-style");
    if (!checked) {
      if (!st) { st = document.createElement("style"); st.id = "hide-dates-style"; document.head.appendChild(st); }
      st.textContent = ".result-date{display:none!important}";
    } else if (st) { st.textContent = ""; }
  });

  // ===== Accent color (in settings modal) =====
  document.querySelectorAll(".color-swatch").forEach(swatch => {
    swatch.addEventListener("click", () => {
      applyAccentColor(swatch.dataset.color);
      ss("accent", swatch.dataset.color);
      document.querySelectorAll(".color-swatch").forEach(s => s.classList.toggle("active", s.dataset.color === swatch.dataset.color));
      const cc = document.getElementById("custom-color");
      if (cc) cc.value = swatch.dataset.color;
    });
  });
  const customColorInput = document.getElementById("custom-color");
  if (customColorInput) {
    if (savedAccent) customColorInput.value = savedAccent;
    customColorInput.addEventListener("input", () => {
      applyAccentColor(customColorInput.value);
      ss("accent", customColorInput.value);
    });
  }

  // ===== Clear buttons =====
  const clearHistBtn = document.getElementById("clear-history-btn");
  if (clearHistBtn) {
    clearHistBtn.addEventListener("click", () => {
      localStorage.removeItem("abbiey_search_history");
      clearHistBtn.textContent = "Cleared!";
      setTimeout(() => { clearHistBtn.textContent = "Clear"; }, 1500);
    });
  }
  const clearAllBtn = document.getElementById("clear-all-btn");
  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", () => {
      if (!confirm("Reset all data? This clears history, bookmarks and all settings.")) return;
      localStorage.clear();
      location.reload();
    });
  }

  // ===== Region selector =====
  const regionSelect = document.getElementById("region-select");
  const regionInput = document.getElementById("region-input");
  if (regionSelect && regionInput) {
    regionSelect.addEventListener("change", () => {
      regionInput.value = regionSelect.value;
      const langInput = document.getElementById("lang-input");
      if (langInput) {
        const parts = regionSelect.value.split("-");
        langInput.value = parts.length > 1 ? parts[1] : "";
      }
      // Persist if enabled
      if (gs("persistRegion") === "true") {
        localStorage.setItem("abbiey_region", regionSelect.value);
      }
      // Auto-submit if there's already a query
      const q = document.getElementById("search-input");
      if (q && q.value.trim()) {
        document.getElementById("search-form").submit();
      }
    });
  }

  // ===== Privacy badge popover =====
  const privacyBadge = document.getElementById("privacy-badge");
  const privacyPopover = document.getElementById("privacy-popover");
  const privacyPopoverClose = document.getElementById("privacy-popover-close");
  if (privacyBadge && privacyPopover) {
    let privacyStatsFetched = false;
    privacyBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      if (privacyPopover.classList.contains("open")) {
        privacyPopover.classList.add("closing");
        setTimeout(() => { privacyPopover.classList.remove("open", "closing"); }, 150);
      } else {
        privacyPopover.classList.add("open");
        if (!privacyStatsFetched && privacyPopover.classList.contains("open")) {
          privacyStatsFetched = true;
          fetch("/api/privacy-stats")
            .then(r => r.json())
            .then(data => {
              const t = document.getElementById("pstat-trackers");
              const p = document.getElementById("pstat-personal");
              const s = document.getElementById("pstat-shared");
              if (t) t.textContent = data.trackers ?? 0;
              if (p) p.textContent = data.personal_data ?? 0;
              if (s) s.textContent = data.third_party_shared ?? 0;
            })
            .catch(() => { /* keep default 0s on error */ });
        }
      }
    });
    if (privacyPopoverClose) {
      privacyPopoverClose.addEventListener("click", () => {
        privacyPopover.classList.add("closing");
        setTimeout(() => { privacyPopover.classList.remove("open", "closing"); }, 150);
      });
    }
  }

  // ===== AI Summary async fetch (text tab, page 1 only) =====
  const aiCard = document.getElementById("ai-summary-card");
  const aiBody = document.getElementById("ai-summary-body");
  const aiSources = document.getElementById("ai-summary-sources");
  if (aiCard && aiBody && window.__searchQuery && window.__searchType === "text") {
    fetch(`/api/ai-summary?q=${encodeURIComponent(window.__searchQuery)}`)
      .then(r => r.json())
      .then(data => {
        if (data.error === "rate_limited") {
          aiBody.innerHTML = `<div class="ai-summary-text ai-unavailable">AI summary temporarily unavailable &mdash; too many requests. Results shown below.</div>`;
          return;
        }
        if (data.error) { aiCard.classList.add("ai-hidden"); return; }
        // Render summary with clickable citations
        let summary = esc(data.summary);
        // Make [1], [2] etc into clickable links
        summary = summary.replace(/\[(\d+)\]/g, (match, num) => {
          const idx = parseInt(num) - 1;
          if (data.sources && data.sources[idx]) {
            const url = data.sources[idx].url;
            // Only allow http/https URLs
            if (url && /^https?:\/\//i.test(url)) {
              return `<a class="ai-citation" href="${esc(url)}" target="_blank" rel="noopener">${num}</a>`;
            }
          }
          return match;
        });
        aiBody.innerHTML = `<div class="ai-summary-text">${summary}</div>`;
        // Render source pills
        if (data.sources && data.sources.length) {
          aiSources.innerHTML = data.sources
            .filter(s => s.url && /^https?:\/\//i.test(s.url))
            .map((s, i) =>
              `<a class="ai-source-pill" href="${esc(s.url)}" target="_blank" rel="noopener">[${i+1}] ${esc(s.title).slice(0, 40)}</a>`
            ).join("");
        }
      })
      .catch(() => { aiCard.classList.add("ai-hidden"); });
  }

  // ===== Bang command suggestions =====
  const searchInput = document.getElementById("search-input");
  const acDropdown = document.getElementById("ac-dropdown");
  if (searchInput && acDropdown) {
    const bangList = [
      {bang: "!w",    label: "Wikipedia",    desc: "Search Wikipedia"},
      {bang: "!wiki", label: "Wikipedia",    desc: "Search Wikipedia"},
      {bang: "!yt",   label: "YouTube",      desc: "Search YouTube"},
      {bang: "!gh",   label: "GitHub",       desc: "Search GitHub"},
      {bang: "!so",   label: "StackOverflow",desc: "Search StackOverflow"},
      {bang: "!r",    label: "Reddit",       desc: "Search Reddit"},
      {bang: "!a",    label: "Amazon",       desc: "Search Amazon"},
      {bang: "!g",    label: "Google",       desc: "Search Google"},
      {bang: "!tw",   label: "X / Twitter",  desc: "Search X"},
      {bang: "!npm",  label: "npm",          desc: "Search npm"},
      {bang: "!pypi", label: "PyPI",         desc: "Search PyPI"},
      {bang: "!mdn",  label: "MDN",          desc: "Search MDN"},
      {bang: "!maps", label: "Maps",         desc: "Search OpenStreetMap"},
      {bang: "!ddg",  label: "DuckDuckGo",   desc: "Search DuckDuckGo"},
      {bang: "!sp",   label: "Spotify",      desc: "Search Spotify"},
      {bang: "!img",  label: "Google Images",desc: "Search Google Images"},
      {bang: "!hn",   label: "Hacker News",  desc: "Search Hacker News"},
      {bang: "!wb",   label: "Wayback Machine", desc: "Search Internet Archive"},
      {bang: "!x",    label: "X / Twitter",  desc: "Search X"},
    ];
    searchInput.addEventListener("input", () => {
      const val = searchInput.value;
      if (val.startsWith("!") && !val.includes(" ")) {
        const query = val.toLowerCase();
        const matches = bangList.filter(b => b.bang.startsWith(query));
        if (matches.length && val.length > 0) {
          acDropdown.innerHTML = matches.map((b, i) =>
            `<div class="ac-item" data-idx="${i}"><span class="ac-item-icon">\u{26A1}</span><span class="ac-item-text">${esc(b.bang)} <span style="color:var(--text-dim);font-size:.8em">${esc(b.desc)}</span></span></div>`
          ).join("");
          acDropdown.classList.add("open");
          // Override click to insert bang + space
          acDropdown.querySelectorAll(".ac-item").forEach((item, idx) => {
            item.addEventListener("mousedown", (e) => {
              e.preventDefault();
              searchInput.value = matches[idx].bang + " ";
              acDropdown.classList.remove("open");
              searchInput.focus();
            });
          });
        }
      }
    });
  }

  // ===== Operator chip removal =====
  const chipContainer = document.getElementById("operator-chips");
  if (chipContainer) {
    chipContainer.addEventListener("click", (e) => {
      const removeBtn = e.target.closest(".chip-remove");
      if (!removeBtn) return;
      const chip = removeBtn.closest(".operator-chip");
      const op = chip.dataset.op;
      const val = chip.dataset.val;
      const searchInput = document.getElementById("search-input");
      if (searchInput) {
        const regex = new RegExp(`\\b${op}:${val.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*`, "gi");
        searchInput.value = searchInput.value.replace(regex, "").trim();
      }
      chip.remove();
      const form = document.getElementById("search-form");
      if (form) form.submit();
    });
  }

  // ===== Autocomplete + History =====
  const input = document.getElementById("search-input");
  const dropdown = document.getElementById("ac-dropdown");
  const form = document.getElementById("search-form");

  if (input && dropdown && form) {
    let acTimer = null;
    let acSeq = 0;
    let activeIdx = -1;

    const HISTORY_KEY = "abbiey_search_history";
    const MAX_HISTORY = 20;

    function getHistory() {
      try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
      catch { return []; }
    }
    function saveHistory(items) {
      try { localStorage.setItem(HISTORY_KEY, JSON.stringify(items)); }
      catch {}
    }
    function addHistory(term) {
      if (gs("history") === "false") return;
      const t = term.trim();
      if (!t) return;
      let items = getHistory().filter(i => i !== t);
      items.unshift(t);
      if (items.length > MAX_HISTORY) items = items.slice(0, MAX_HISTORY);
      saveHistory(items);
    }
    function removeHistory(term) { saveHistory(getHistory().filter(i => i !== term)); }
    function clearHistory() { try { localStorage.removeItem(HISTORY_KEY); } catch {} }

    form.addEventListener("submit", () => { addHistory(input.value); });

    function showDropdown() { dropdown.classList.add("open"); }
    function hideDropdown() { dropdown.classList.remove("open"); activeIdx = -1; }

    function renderSuggestions(items) {
      if (!items.length) { hideDropdown(); return; }
      dropdown.innerHTML = items.map((text, i) =>
        `<div class="ac-item" data-idx="${i}"><span class="ac-item-icon">\u{1F50D}</span><span class="ac-item-text">${esc(text)}</span></div>`
      ).join("");
      activeIdx = -1;
      showDropdown();
    }

    function renderHistory() {
      const items = getHistory();
      if (!items.length) { hideDropdown(); return; }
      let h = `<div class="ac-header"><span class="ac-header-label">Recent searches</span><button class="ac-clear-btn" id="ac-clear-all" type="button">Clear all</button></div>`;
      h += items.map((text, i) =>
        `<div class="ac-item" data-idx="${i}" data-history="1"><span class="ac-item-icon">\u{1F550}</span><span class="ac-item-text">${esc(text)}</span><button class="ac-delete-btn" data-del-idx="${i}" type="button" title="Remove">&times;</button></div>`
      ).join("");
      dropdown.innerHTML = h;
      activeIdx = -1;
      showDropdown();
      const clearBtn = document.getElementById("ac-clear-all");
      if (clearBtn) clearBtn.addEventListener("click", (e) => { e.stopPropagation(); clearHistory(); hideDropdown(); });
    }

    function getItems() { return dropdown.querySelectorAll(".ac-item"); }
    function setActive(idx) {
      const items = getItems();
      items.forEach(el => el.classList.remove("active"));
      if (idx >= 0 && idx < items.length) { items[idx].classList.add("active"); items[idx].scrollIntoView({ block: "nearest" }); }
      activeIdx = idx;
    }
    function selectItem(text) { input.value = text; hideDropdown(); addHistory(text); form.submit(); }

    let acController = null;
    function fetchSuggestions(q) {
      const seq = ++acSeq;
      if (acController) acController.abort();
      acController = new AbortController();
      fetch(`/api/suggestions?q=${encodeURIComponent(q)}`, { signal: acController.signal })
        .then(r => r.json())
        .then(data => { if (seq !== acSeq) return; if (Array.isArray(data)) renderSuggestions(data); else hideDropdown(); })
        .catch(() => {});
    }

    input.addEventListener("input", () => {
      clearTimeout(acTimer);
      const val = input.value.trim();
      if (!val) { renderHistory(); return; }
      if (gs("autocomplete") === "false") { hideDropdown(); return; }
      // Don't interfere with bang command suggestions
      if (val.startsWith("!") && !val.includes(" ")) return;
      hideDropdown();
      acTimer = setTimeout(() => fetchSuggestions(val), 120);
    });
    input.addEventListener("focus", () => { if (!input.value.trim()) renderHistory(); });
    input.addEventListener("keydown", (e) => {
      const items = getItems();
      if (!dropdown.classList.contains("open") || !items.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(activeIdx < items.length - 1 ? activeIdx + 1 : 0); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(activeIdx > 0 ? activeIdx - 1 : items.length - 1); }
      else if (e.key === "Enter" && activeIdx >= 0) { e.preventDefault(); selectItem(items[activeIdx].querySelector(".ac-item-text").textContent); }
      else if (e.key === "Escape") hideDropdown();
    });
    dropdown.addEventListener("mousedown", (e) => {
      const delBtn = e.target.closest(".ac-delete-btn");
      if (delBtn) { e.preventDefault(); e.stopPropagation(); const idx = parseInt(delBtn.getAttribute("data-del-idx")); const items = getHistory(); if (idx >= 0 && idx < items.length) removeHistory(items[idx]); renderHistory(); return; }
      const item = e.target.closest(".ac-item");
      if (item) { e.preventDefault(); selectItem(item.querySelector(".ac-item-text").textContent); }
    });
  }

  // ===== Quick Filters Bar =====
  const filterBar = document.getElementById("filter-bar");
  if (filterBar) {
    const filterForm = document.getElementById("search-form");
    const filterInput = document.getElementById("search-input");

    function removeOperator(query, op) {
      return query.replace(new RegExp(`\\b${op}:\\S+\\s*`, "gi"), "").trim();
    }

    function applyFilter() {
      if (filterForm) filterForm.submit();
    }

    // Time filter
    const timeSelect = document.getElementById("filter-time");
    const dfInput = document.getElementById("df-input");
    if (timeSelect && dfInput) {
      // Pre-select from current df value
      if (dfInput.value) timeSelect.value = dfInput.value;

      timeSelect.addEventListener("change", () => {
        dfInput.value = timeSelect.value;
        applyFilter();
      });
    }

    // File type pills
    const pillContainer = document.getElementById("filter-pills");
    if (pillContainer) {
      pillContainer.addEventListener("click", (e) => {
        const pill = e.target.closest(".filter-pill");
        if (!pill) return;
        const ft = pill.dataset.ft;
        let q = filterInput.value;
        const regex = new RegExp(`\\bfiletype:${ft}\\s*`, "gi");
        if (pill.classList.contains("active")) {
          q = q.replace(regex, "").trim();
          pill.classList.remove("active");
        } else {
          q = `${q} filetype:${ft}`.trim();
          pill.classList.add("active");
        }
        filterInput.value = q;
        applyFilter();
      });
    }

    // Site filter
    const siteInput = document.getElementById("filter-site");
    if (siteInput) {
      function applySiteFilter() {
        let q = filterInput.value;
        q = removeOperator(q, "site");
        const site = siteInput.value.trim();
        if (site) {
          q = `${q} site:${site}`.trim();
        }
        filterInput.value = q;
        applyFilter();
      }
      siteInput.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applySiteFilter(); } });
      siteInput.addEventListener("blur", () => {
        // Only apply if value changed
        const currentQ = filterInput.value;
        const currentSite = (currentQ.match(/\bsite:(\S+)/i) || [])[1] || "";
        if (siteInput.value.trim() !== currentSite) applySiteFilter();
      });
    }
  }

  // ===== Infinite scroll (IntersectionObserver) =====
  const sentinel = document.getElementById("scroll-sentinel");
  if (sentinel) {
  let loading = false;
  let hasMore = sentinel.dataset.hasMore === "true";
  const container = document.getElementById("results");
  const type = sentinel.dataset.type;
  const query = sentinel.dataset.query;

  function showSkeletons(count) {
    const frag = document.createDocumentFragment();
    for (let i = 0; i < count; i++) {
      const div = document.createElement("div");
      if (type === "images") {
        div.className = "skeleton-image-card";
        div.setAttribute("data-skeleton", "");
        div.innerHTML = `<div class="skeleton-image-thumb"></div><div class="skeleton-image-info"><div class="skeleton-title"></div></div>`;
      } else {
        div.className = "skeleton-result";
        div.setAttribute("data-skeleton", "");
        div.innerHTML = `<div class="skeleton-title"></div><div class="skeleton-url"></div><div class="skeleton-body"></div><div class="skeleton-body"></div>`;
      }
      frag.appendChild(div);
    }
    container.appendChild(frag);
  }
  function removeSkeletons() { container.querySelectorAll("[data-skeleton]").forEach(el => el.remove()); }

  function loadMore() {
    if (loading || !hasMore) return;
    loading = true;
    const loadMoreBtn = document.querySelector(".load-more-btn");
    if (loadMoreBtn) loadMoreBtn.classList.add("loading");
    const page = parseInt(sentinel.dataset.page) + 1;
    sentinel.querySelector(".scroll-loader").classList.remove("hidden");
    showSkeletons(5);

    const regionVal = document.getElementById("region-input")?.value || "";
    const langVal = document.getElementById("lang-input")?.value || "";
    const dfVal = document.getElementById("df-input")?.value || "";
    let scrollUrl = `/search?q=${encodeURIComponent(query)}&page=${page}&type=${type}`;
    if (regionVal) scrollUrl += `&region=${encodeURIComponent(regionVal)}`;
    if (langVal) scrollUrl += `&lang=${encodeURIComponent(langVal)}`;
    if (dfVal) scrollUrl += `&df=${encodeURIComponent(dfVal)}`;
    fetch(scrollUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(r => r.json())
      .then(data => {
        removeSkeletons();
        const frag = document.createDocumentFragment();
        data.results.forEach((r, idx) => {
          const delay = Math.min(idx * 15, 200);
          const el = document.createElement(type === "images" ? "div" : "article");
          el.style.animationDelay = `${delay}ms`;
          el.dataset.url = r.url || "";

          if (type === "images") {
            el.className = "image-card";
            el.dataset.full = r.image || r.thumbnail;
            el.dataset.title = r.title;
            el.dataset.source = r.source || "";
            el.innerHTML = `<img src="${esc(r.thumbnail || r.image)}" alt="${esc(r.title)}" loading="lazy"><div class="image-card-info"><span class="image-title">${esc(r.title)}</span>${r.source ? `<span class="image-source">${esc(r.source)}</span>` : ""}</div>`;
          } else if (type === "videos") {
            el.className = "result video-result";
            el.innerHTML = `${r.thumbnail ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="video-thumb"><img src="${esc(r.thumbnail)}" alt="${esc(r.title)}" loading="lazy">${r.duration ? `<span class="duration">${esc(r.duration)}</span>` : ""}</a>` : ""}<div class="result-text"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${faviconImg(r.url)}<cite class="result-url">${esc(r.publisher || "")}</cite><p class="result-snippet">${esc(r.description || "")}</p></div>`;
          } else if (type === "onion") {
            el.className = "result onion-result";
            const isOnion = r.onion || (r.url && /\.onion(\/|$)/i.test(r.url));
            el.innerHTML = `<div class="onion-result-header"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${isOnion ? '<span class="onion-badge">.onion</span>' : ""}</div><cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p>`;
          } else if (type === "code") {
            el.className = "result code-result";
            el.innerHTML = `<div class="code-result-header"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${r.language ? `<span class="code-lang-badge">${esc(r.language)}</span>` : ""}<span class="code-source-badge">${esc(r.source || "")}</span></div>${faviconImg(r.url)}<cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p><div class="code-meta">${r.stars ? `<span class="code-stat">&#9733; ${esc(r.stars)}</span>` : ""}${r.forks ? `<span class="code-stat">&#9906; ${esc(r.forks)}</span>` : ""}</div>`;
          } else {
            el.className = "result";
            el.innerHTML = `<button class="bookmark-btn" data-url="${esc(r.url)}" data-title="${esc(r.title)}" data-snippet="${esc(r.body || "")}" aria-label="Save result" title="Save"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg></button><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${faviconImg(r.url)}<cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p>${r.date ? `<time class="result-date">${esc(r.date)}</time>` : ""}`;
          }
          frag.appendChild(el);
        });
        container.appendChild(frag);
        initBookmarkBtns(container);
        sentinel.dataset.page = page;
        if (data.has_more) { hasMore = true; sentinel.querySelector(".scroll-loader").classList.add("hidden"); }
        else { hasMore = false; sentinel.remove(); observer.disconnect(); }
        loading = false;
        const loadMoreBtnDone = document.querySelector(".load-more-btn");
        if (loadMoreBtnDone) loadMoreBtnDone.classList.remove("loading");
      })
      .catch(() => { removeSkeletons(); sentinel.querySelector(".scroll-loader").classList.add("hidden"); loading = false; const loadMoreBtnErr = document.querySelector(".load-more-btn"); if (loadMoreBtnErr) loadMoreBtnErr.classList.remove("loading"); });
  }

  const observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && !loading && hasMore) loadMore();
  }, { rootMargin: "0px 0px 600px 0px" });
  observer.observe(sentinel);
  }

  // ===== Image lightbox =====
  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightbox-img");
  const lightboxTitle = document.getElementById("lightbox-title");
  const lightboxSource = document.getElementById("lightbox-source");
  const lightboxClose = document.getElementById("lightbox-close");

  let openLightbox = null;
  if (lightbox) {
    lightbox.removeAttribute("hidden");
    openLightbox = function(card) {
      lightboxImg.src = card.dataset.full;
      lightboxImg.alt = card.dataset.title;
      lightboxTitle.textContent = card.dataset.title;
      lightboxSource.href = card.dataset.url;
      requestAnimationFrame(() => { lightbox.classList.add("active"); document.body.style.overflow = "hidden"; });
    };
    function closeLightbox() {
      lightbox.classList.remove("active");
      document.body.style.overflow = "";
      setTimeout(() => { if (!lightbox.classList.contains("active")) lightboxImg.src = ""; }, 250);
    }
    lightboxClose.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", (e) => { if (e.target === lightbox) closeLightbox(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && lightbox.classList.contains("active")) closeLightbox(); });
    document.addEventListener("mouseover", (e) => { const card = e.target.closest(".image-card"); if (card && !card._preloaded) { card._preloaded = true; new Image().src = card.dataset.full; } }, { passive: true });
  }

  // ===== Consolidated click-outside handler (single delegated listener) =====
  document.addEventListener("click", (e) => {
    const target = e.target;

    // Privacy popover close
    if (privacyPopover && privacyPopover.classList.contains("open") && !privacyPopover.classList.contains("closing")) {
      if (!target.closest(".privacy-popover") && !target.closest("#privacy-badge")) {
        privacyPopover.classList.add("closing");
        setTimeout(() => { privacyPopover.classList.remove("open", "closing"); }, 150);
      }
    }

    // Autocomplete close
    if (dropdown && dropdown.classList.contains("open")) {
      if (!target.closest(".search-box-wrapper")) {
        dropdown.classList.remove("open");
      }
    }

    // Color copy button (CSS-based state, no innerHTML mutation)
    const copyBtn = target.closest(".color-copy-btn");
    if (copyBtn && copyBtn.dataset.copy) {
      navigator.clipboard.writeText(copyBtn.dataset.copy).then(() => {
        copyBtn.classList.add("copied");
        setTimeout(() => copyBtn.classList.remove("copied"), 1500);
      }).catch(() => {});
      return;
    }

    // Dictionary audio
    const audioBtn = target.closest(".dictionary-audio-btn");
    if (audioBtn && audioBtn.dataset.audio) {
      e.preventDefault();
      new Audio(audioBtn.dataset.audio).play().catch(() => {});
      return;
    }

    // Image lightbox open
    if (openLightbox) {
      const imageCard = target.closest(".image-card");
      if (imageCard) {
        e.preventDefault();
        openLightbox(imageCard);
        return;
      }
    }
  });

  // ===== Result Preview Panel =====
  const previewPanel = document.getElementById("preview-panel");
  const previewBody = document.getElementById("preview-body");
  const previewEmpty = document.getElementById("preview-empty");
  const previewContent = document.getElementById("preview-content");
  const previewLoading = document.getElementById("preview-loading");
  const previewClose = document.getElementById("preview-close");

  let previewOpen = false;
  let previewCache = {};
  let activeResultIdx = -1;

  // Cache preview element references once
  const _previewImg = document.getElementById("preview-image");
  const _previewTitle = document.getElementById("preview-title");
  const _previewSite = document.getElementById("preview-site");
  const _previewDesc = document.getElementById("preview-desc");
  const _previewExcerpt = document.getElementById("preview-excerpt");
  const _previewLink = document.getElementById("preview-link");

  if (previewPanel) {
    previewClose.addEventListener("click", () => {
      previewPanel.classList.remove("open");
      previewOpen = false;
      clearResultHighlight();
    });

    // Cached result elements — invalidated on DOM changes
    let _cachedResults = null;
    const resultsEl = document.getElementById("results");

    function getResultElements() {
      if (!_cachedResults) {
        _cachedResults = resultsEl.querySelectorAll(":scope > .result");
      }
      return _cachedResults;
    }

    // Invalidate cache when infinite scroll adds results
    const resultObserver = new MutationObserver(() => { _cachedResults = null; });
    resultObserver.observe(resultsEl, { childList: true });

    function clearResultHighlight() {
      const prev = resultsEl.querySelector(".result.result-focused");
      if (prev) prev.classList.remove("result-focused");
    }

    function highlightResult(idx) {
      const results = getResultElements();
      clearResultHighlight();
      if (idx >= 0 && idx < results.length) {
        results[idx].classList.add("result-focused");
        results[idx].scrollIntoView({ block: "nearest", behavior: "instant" });
        const url = results[idx].dataset.url;
        if (url) loadPreview(url);
      }
    }

    function loadPreview(url) {
      if (!url || !url.startsWith("http")) return;

      // Show panel if not open
      if (!previewOpen) {
        previewPanel.classList.add("open");
        previewOpen = true;
      }

      // Check cache
      if (previewCache[url]) {
        renderPreview(previewCache[url]);
        return;
      }

      // Show loading — batched in rAF
      requestAnimationFrame(() => {
        previewEmpty.style.display = "none";
        previewContent.style.display = "none";
        previewLoading.style.display = "flex";
      });

      fetch(`/api/preview?url=${encodeURIComponent(url)}`)
        .then(r => r.json())
        .then(data => {
          if (data.error) {
            requestAnimationFrame(() => {
              previewLoading.style.display = "none";
              previewContent.style.display = "block";
              _previewTitle.textContent = "Preview unavailable";
              _previewDesc.textContent = "Could not load page preview.";
              _previewExcerpt.textContent = "";
              _previewSite.textContent = "";
              _previewImg.style.display = "none";
              _previewLink.href = url;
            });
            return;
          }
          previewCache[url] = data;
          renderPreview(data);
        })
        .catch(() => {
          requestAnimationFrame(() => {
            previewLoading.style.display = "none";
            previewEmpty.style.display = "block";
          });
        });
    }

    function renderPreview(data) {
      const hasImage = !!data.image;
      const siteName = data.site_name || (() => { try { return new URL(data.url).hostname; } catch { return ""; } })();

      requestAnimationFrame(() => {
        previewLoading.style.display = "none";
        previewEmpty.style.display = "none";
        previewContent.style.display = "block";

        if (hasImage) { _previewImg.src = data.image; _previewImg.style.display = "block"; }
        else { _previewImg.style.display = "none"; _previewImg.src = ""; }

        _previewTitle.textContent = data.title || "";
        _previewSite.textContent = siteName;
        _previewDesc.textContent = data.description || "";
        _previewExcerpt.textContent = data.excerpt || "";
        _previewLink.href = data.url;
      });
    }

    // Hover to preview
    let hoverTimer = null;
    document.addEventListener("mouseover", (e) => {
      const result = e.target.closest("#results > .result");
      if (!result || !result.dataset.url) return;
      clearTimeout(hoverTimer);
      hoverTimer = setTimeout(() => loadPreview(result.dataset.url), 300);
    }, { passive: true });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest("#results > .result")) clearTimeout(hoverTimer);
    }, { passive: true });

    // Keyboard navigation: j/k for results, o to open (inside previewPanel scope)
    document.addEventListener("keydown", (e) => {
      const tag = document.activeElement.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      if (e.key === "/" ) {
        e.preventDefault();
        document.getElementById("search-input").focus();
        return;
      }

      const results = getResultElements();
      if (!results.length) return;

      if (e.key === "j") {
        e.preventDefault();
        activeResultIdx = Math.min(activeResultIdx + 1, results.length - 1);
        highlightResult(activeResultIdx);
      } else if (e.key === "k") {
        e.preventDefault();
        activeResultIdx = Math.max(activeResultIdx - 1, 0);
        highlightResult(activeResultIdx);
      } else if (e.key === "o" && activeResultIdx >= 0) {
        e.preventDefault();
        const url = results[activeResultIdx].dataset.url;
        if (url) window.open(url, "_blank");
      } else if (e.key === "Escape" && previewOpen) {
        previewPanel.classList.remove("open");
        previewOpen = false;
        clearResultHighlight();
        activeResultIdx = -1;
      }
    });
  }

  // ===== "/" shortcut to focus search (works on all pages) =====
  if (!previewPanel) {
    document.addEventListener("keydown", (e) => {
      const tag = document.activeElement.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "/") {
        e.preventDefault();
        document.getElementById("search-input").focus();
      }
    });
  }

  // ===== AI Research Chat =====
  const chatPanel = document.getElementById("chat-panel");
  const chatFab = document.getElementById("chat-fab");
  const chatToggle = document.getElementById("chat-toggle");
  const chatNew = document.getElementById("chat-new");
  const chatInput = document.getElementById("chat-input");
  const chatSend = document.getElementById("chat-send");
  const chatMessages = document.getElementById("chat-messages");
  const chatWelcome = document.getElementById("chat-welcome");
  const chatBody = document.getElementById("chat-body");

  if (chatPanel && chatFab) {
    let chatHistory = [];
    const searchQuery = window.__searchQuery || "";
    let chatOpen = false;

    function toggleChat() {
      chatOpen = !chatOpen;
      chatPanel.classList.toggle("open", chatOpen);
      chatFab.classList.toggle("hidden", chatOpen);
      if (chatOpen && chatInput) chatInput.focus();
    }

    chatFab.addEventListener("click", toggleChat);
    chatToggle.addEventListener("click", toggleChat);
    chatNew.addEventListener("click", () => { chatHistory = []; chatMessages.innerHTML = ""; chatWelcome.style.display = ""; });

    function sendMessage() {
      const msg = chatInput.value.trim();
      if (!msg) return;
      chatWelcome.style.display = "none";
      appendMessage("user", msg);
      chatInput.value = "";
      chatInput.disabled = true;
      chatSend.disabled = true;
      const typingId = appendTyping();

      fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery, message: msg, history: chatHistory }),
      })
        .then(r => r.json())
        .then(data => {
          removeMessage(typingId);
          if (data.error) appendMessage("assistant", `Error: ${data.error}`);
          else { appendMessage("assistant", data.response); chatHistory.push({ role: "user", content: msg }); chatHistory.push({ role: "assistant", content: data.response }); }
        })
        .catch(() => { removeMessage(typingId); appendMessage("assistant", "Connection error. Please try again."); })
        .finally(() => { chatInput.disabled = false; chatSend.disabled = false; chatInput.focus(); });
    }

    if (chatSend) chatSend.addEventListener("click", sendMessage);
    if (chatInput) chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

    let msgCounter = 0;
    function appendTyping() {
      const id = `msg-${msgCounter++}`;
      const div = document.createElement("div");
      div.className = "chat-msg chat-msg-assistant typing";
      div.id = id;
      div.innerHTML = `<div class="chat-msg-content">Researching <span class="typing-dots"><span></span><span></span><span></span></span></div>`;
      chatMessages.appendChild(div);
      chatBody.scrollTop = chatBody.scrollHeight;
      return id;
    }
    function appendMessage(role, content) {
      const id = `msg-${msgCounter++}`;
      const div = document.createElement("div");
      div.className = `chat-msg chat-msg-${role}`;
      div.id = id;
      let formatted = esc(content)
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        .replace(/(?<!="|">)(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
        .replace(/\n/g, "<br>");
      div.innerHTML = `<div class="chat-msg-content">${formatted}</div>`;
      chatMessages.appendChild(div);
      chatBody.scrollTop = chatBody.scrollHeight;
      return id;
    }
    function removeMessage(id) { const el = document.getElementById(id); if (el) el.remove(); }
  }

  // ===== Onion Link Verification =====
  if (window.__searchType === "onion") {
    const onionResults = document.querySelectorAll(".onion-result");
    if (onionResults.length) {
      const ONION_VERIFIED_KEY = "onion_verified";
      const ONION_TTL = 10 * 60 * 1000; // 10 minutes, matches server cache
      const now = Date.now();

      // Load cached statuses, filtering expired entries
      let verified = {};
      try {
        const raw = JSON.parse(localStorage.getItem(ONION_VERIFIED_KEY)) || {};
        for (const [k, v] of Object.entries(raw)) {
          if (v && v.ts && now - v.ts < ONION_TTL) verified[k] = v.status;
        }
      } catch {}

      // Helper: reorder onion results within their container without disrupting non-result siblings
      const container = document.getElementById("results");
      function reorderOnionResults() {
        if (!container) return;
        const firstOnion = onionResults[0];
        if (!firstOnion) return;
        const sorted = [...onionResults].sort((a, b) => {
          const aLive = a.classList.contains("onion-live") ? 0 : a.classList.contains("onion-down") ? 2 : 1;
          const bLive = b.classList.contains("onion-live") ? 0 : b.classList.contains("onion-down") ? 2 : 1;
          return aLive - bLive;
        });
        // Insert before the first non-onion-result sibling after all onion results
        const ref = container.querySelector(":scope > :not(.onion-result):not(.result)");
        sorted.forEach(el => container.insertBefore(el, ref));
      }

      // Add badges — only check actual .onion URLs, skip clearnet DDG fallback results
      const urls = [];
      onionResults.forEach(el => {
        const url = el.dataset.url || "";
        const header = el.querySelector(".onion-result-header");
        if (!header) return;
        // Only verify actual .onion links
        const isOnion = /\.onion(\/|$)/i.test(url);
        if (!isOnion) return;
        const badge = document.createElement("span");
        badge.className = "onion-status checking";
        if (verified[url]) {
          badge.textContent = verified[url] === "live" ? "Live" : "Down";
          badge.className = "onion-status " + verified[url];
          if (verified[url] === "down") el.classList.add("onion-down");
          else el.classList.add("onion-live");
        } else {
          badge.textContent = "Checking\u2026";
        }
        header.appendChild(badge);
        urls.push(url);
      });

      reorderOnionResults();

      // Fire off verification request — skip if all URLs already cached
      const uncachedUrls = urls.filter(u => !verified[u]);
      if (uncachedUrls.length) {
        fetch("/api/onion-check", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ urls: uncachedUrls }),
        })
          .then(r => r.json())
          .then(data => {
            if (!data.results) return;
            const res = data.results;

            // Update badges and classes
            let hasResults = false;
            onionResults.forEach(el => {
              const url = el.dataset.url;
              const status = res[url];
              if (!status || status === "unknown") {
                // Tor not available — remove checking badge
                const badge = el.querySelector(".onion-status.checking");
                if (badge) badge.remove();
                return;
              }
              hasResults = true;
              const badge = el.querySelector(".onion-status");
              if (badge) {
                badge.textContent = status === "live" ? "Live" : "Down";
                badge.className = "onion-status " + status;
              }
              el.classList.remove("onion-live", "onion-down");
              el.classList.add(status === "live" ? "onion-live" : "onion-down");
              verified[url] = status;
            });

            if (hasResults) reorderOnionResults();

            // Persist to localStorage with timestamps (merge with existing)
            try {
              const ts = Date.now();
              const merged = {};
              // Keep existing non-expired entries
              const existing = JSON.parse(localStorage.getItem(ONION_VERIFIED_KEY)) || {};
              for (const [k, v] of Object.entries(existing)) {
                if (v && v.ts && ts - v.ts < ONION_TTL) merged[k] = v;
              }
              // Add/update current results
              for (const [k, v] of Object.entries(verified)) {
                merged[k] = { status: v, ts };
              }
              localStorage.setItem(ONION_VERIFIED_KEY, JSON.stringify(merged));
            } catch {}
          })
          .catch(() => {
            // On error, remove "Checking..." badges
            onionResults.forEach(el => {
              const badge = el.querySelector(".onion-status.checking");
              if (badge) badge.remove();
            });
          });
      }
    }
  }

  // ===== Bookmarking =====
  const BOOKMARKS_KEY = "abbiey_bookmarks";

  function getBookmarks() {
    try { return JSON.parse(localStorage.getItem(BOOKMARKS_KEY)) || []; }
    catch { return []; }
  }
  function saveBookmarks(items) {
    try { localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(items)); } catch {}
  }
  function isBookmarked(url) {
    return getBookmarks().some(b => b.url === url);
  }
  function addBookmark(url, title, snippet) {
    const items = getBookmarks().filter(b => b.url !== url);
    items.unshift({ url, title, snippet, saved: Date.now() });
    saveBookmarks(items);
  }
  function removeBookmark(url) {
    saveBookmarks(getBookmarks().filter(b => b.url !== url));
  }
  function updateBookmarkBadge() {
    const badge = document.getElementById("bookmark-count-badge");
    if (!badge) return;
    const count = getBookmarks().length;
    badge.textContent = count > 0 ? count : "";
    badge.style.display = count > 0 ? "inline-flex" : "none";
  }
  function initBookmarkBtns(scope) {
    (scope || document).querySelectorAll(".bookmark-btn:not([data-bm-init])").forEach(btn => {
      btn.setAttribute("data-bm-init", "1");
      const url = btn.dataset.url;
      if (isBookmarked(url)) btn.classList.add("bookmarked");
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (isBookmarked(url)) {
          removeBookmark(url);
          btn.classList.remove("bookmarked");
        } else {
          addBookmark(url, btn.dataset.title, btn.dataset.snippet);
          btn.classList.add("bookmarked");
        }
        updateBookmarkBadge();
      });
    });
  }

  initBookmarkBtns();
  updateBookmarkBadge();

  // Render saved tab
  if (window.__searchType === "saved") {
    const savedContainer = document.getElementById("saved-results-container");
    if (savedContainer) {
      const bookmarks = getBookmarks();
      if (!bookmarks.length) {
        savedContainer.innerHTML = '<p class="no-results">No saved results yet. Click the bookmark icon on any result to save it.</p>';
      } else {
        savedContainer.innerHTML = bookmarks.map(b => `
          <article class="result saved-result">
            <button class="bookmark-remove-btn" data-url="${esc(b.url)}" aria-label="Remove bookmark" title="Remove">&#10005;</button>
            <a href="${esc(b.url)}" target="_blank" rel="noopener" class="result-title">${esc(b.title)}</a>
            <cite class="result-url">${esc(b.url)}</cite>
            <p class="result-snippet">${esc(b.snippet || "")}</p>
          </article>
        `).join("");
        savedContainer.querySelectorAll(".bookmark-remove-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            removeBookmark(btn.dataset.url);
            btn.closest(".saved-result").remove();
            updateBookmarkBadge();
            if (!getBookmarks().length) {
              savedContainer.innerHTML = '<p class="no-results">No saved results.</p>';
            }
          });
        });
      }
    }
  }

  // ===== Related Searches =====
  const relatedContainer = document.getElementById("related-searches");
  const searchQuery = window.__searchQuery;
  if (relatedContainer && searchQuery) {
    fetch(`/api/related?q=${encodeURIComponent(searchQuery)}`)
      .then(r => r.json())
      .then(items => {
        if (!Array.isArray(items) || !items.length) return;
        let h = `<div class="related-header">Related searches</div><div class="related-pills">`;
        h += items.map(t => `<a href="/search?q=${encodeURIComponent(t)}&type=${window.__searchType || 'text'}" class="related-pill">${esc(t)}</a>`).join("");
        h += `</div>`;
        relatedContainer.innerHTML = h;
      })
      .catch(() => {});
  }

  // ===== Trending Searches =====
  (function initTrending() {
    function renderTrending(container, items, compact) {
      if (!items.length) return;
      const pills = items.map((t, i) =>
        `<a class="trending-pill" href="/search?q=${encodeURIComponent(t.query)}&type=text" style="animation-delay:${i * 0.04}s">
          ${esc(t.query)}${!compact ? `<span class="trending-count">${t.count}</span>` : ""}
        </a>`
      ).join("");
      container.innerHTML =
        `<div class="trending-header">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
          Trending now
        </div>
        <div class="trending-pills">${pills}</div>`;
      container.style.display = "";
    }

    // Homepage trending
    const homeEl = document.getElementById("trending-home");
    // Results page trending (shown after related searches)
    const resultsEl = document.getElementById("trending-searches");

    if (homeEl || resultsEl) {
      fetch("/api/trends")
        .then(r => r.json())
        .then(items => {
          if (!Array.isArray(items) || !items.length) return;
          if (homeEl) renderTrending(homeEl, items.slice(0, 8), false);
          if (resultsEl) renderTrending(resultsEl, items.slice(0, 6), true);
        })
        .catch(() => {});
    }
  })();

  // ===== Feature 1: Voice Search =====
  (function initVoiceSearch() {
    const voiceBtn = document.getElementById("voice-btn");
    if (!voiceBtn) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      voiceBtn.style.display = "none";
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = navigator.language || "en-US";

    const micIcon  = voiceBtn.querySelector(".voice-icon-mic");
    const stopIcon = voiceBtn.querySelector(".voice-icon-stop");
    const input    = document.getElementById("search-input");
    let listening  = false;

    function startListening() {
      listening = true;
      voiceBtn.classList.add("listening");
      micIcon.style.display  = "none";
      stopIcon.style.display = "";
      voiceBtn.setAttribute("aria-label", "Stop listening");
      recognition.start();
    }

    function stopListening() {
      listening = false;
      voiceBtn.classList.remove("listening");
      micIcon.style.display  = "";
      stopIcon.style.display = "none";
      voiceBtn.setAttribute("aria-label", "Voice search");
      recognition.stop();
    }

    voiceBtn.addEventListener("click", () => {
      if (listening) stopListening();
      else startListening();
    });

    recognition.addEventListener("result", (e) => {
      const transcript = Array.from(e.results)
        .map(r => r[0].transcript)
        .join("");
      input.value = transcript;
      // Auto-submit on final result
      if (e.results[e.results.length - 1].isFinal) {
        stopListening();
        if (transcript.trim()) document.getElementById("search-form").submit();
      }
    });

    recognition.addEventListener("end",   () => { if (listening) stopListening(); });
    recognition.addEventListener("error", () => stopListening());
  })();

  // ===== Feature 2: In-Results Filter =====
  (function initResultsFilter() {
    const filterInput = document.getElementById("results-filter-input");
    const filterCount = document.getElementById("results-filter-count");
    const filterClear = document.getElementById("results-filter-clear");
    if (!filterInput) return;

    const container = document.getElementById("results");
    if (!container) return;

    function getResults() {
      return Array.from(container.querySelectorAll(".result:not(.result-compact)"));
    }

    function highlight(el, term) {
      // Highlight in title and snippet only
      [".result-title", ".result-snippet"].forEach(sel => {
        const node = el.querySelector(sel);
        if (!node) return;
        // Strip old highlights first
        node.innerHTML = node.innerHTML.replace(/<mark class="result-filter-highlight">([^<]*)<\/mark>/gi, "$1");
        if (!term) return;
        const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        node.innerHTML = node.innerHTML.replace(
          new RegExp(`(${escaped})`, "gi"),
          '<mark class="result-filter-highlight">$1</mark>'
        );
      });
    }

    function applyFilter(term) {
      const results = getResults();
      const q = term.trim().toLowerCase();
      let visible = 0;

      results.forEach(r => {
        const text = (r.textContent || "").toLowerCase();
        const match = !q || text.includes(q);
        r.classList.toggle("filter-hidden", !match);
        if (match) {
          visible++;
          highlight(r, q ? term.trim() : "");
        }
      });

      if (q) {
        filterCount.textContent = `${visible} of ${results.length}`;
        filterClear.style.display = "";
      } else {
        filterCount.textContent = "";
        filterClear.style.display = "none";
      }
    }

    filterInput.addEventListener("input", () => applyFilter(filterInput.value));
    filterClear.addEventListener("click", () => {
      filterInput.value = "";
      applyFilter("");
      filterInput.focus();
    });
  })();

  // ===== Feature 3: View Mode Switcher =====
  (function initViewMode() {
    const switcher  = document.getElementById("view-mode-switcher");
    const container = document.getElementById("results");
    if (!switcher || !container) return;

    const STORAGE_KEY = "abbiey_view_mode";
    const saved = localStorage.getItem(STORAGE_KEY) || "list";

    function setView(mode) {
      // Update container attribute
      container.removeAttribute("data-view");
      if (mode !== "list") container.setAttribute("data-view", mode);

      // Sync buttons
      switcher.querySelectorAll(".view-mode-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.view === mode);
      });

      localStorage.setItem(STORAGE_KEY, mode);
    }

    // Apply saved mode on load
    setView(saved);

    switcher.addEventListener("click", (e) => {
      const btn = e.target.closest(".view-mode-btn");
      if (btn) setView(btn.dataset.view);
    });
  })();

  // ===== Ripple micro-interaction on primary buttons =====
  document.querySelectorAll(".search-btn, .error-home-btn").forEach(btn => {
    btn.addEventListener("pointerdown", function(e) {
      const rect = this.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height) * 2;
      const wave = document.createElement("span");
      wave.className = "ripple-wave";
      wave.style.cssText = `width:${size}px;height:${size}px;left:${e.clientX - rect.left - size / 2}px;top:${e.clientY - rect.top - size / 2}px`;
      this.appendChild(wave);
      wave.addEventListener("animationend", () => wave.remove(), { once: true });
    });
  });

  // ===== Tab sliding indicator =====
  (function initTabIndicator() {
    const tabsEl = document.querySelector(".search-tabs");
    if (!tabsEl) return;

    const indicator = document.createElement("div");
    indicator.className = "tab-indicator";
    tabsEl.appendChild(indicator);

    function moveIndicator() {
      const active = tabsEl.querySelector(".tab.active");
      if (!active) { indicator.style.width = "0"; return; }
      const tRect = active.getBoundingClientRect();
      const cRect = tabsEl.getBoundingClientRect();
      indicator.style.left  = (tRect.left - cRect.left) + "px";
      indicator.style.width = tRect.width + "px";
    }

    // Initial position (no transition on first paint)
    indicator.style.transition = "none";
    requestAnimationFrame(() => {
      moveIndicator();
      requestAnimationFrame(() => { indicator.style.transition = ""; });
    });

    window.addEventListener("resize", moveIndicator, { passive: true });
  })();
});

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}

function faviconImg(url) {
  try {
    const host = new URL(url).hostname;
    return `<img class="result-favicon" src="https://icons.duckduckgo.com/ip3/${esc(host)}/favicon.ico" onerror="this.style.display='none'" alt="" loading="lazy">`;
  } catch { return ""; }
}



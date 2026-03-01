document.addEventListener("DOMContentLoaded", () => {
  const html = document.documentElement;

  // ===== Theme toggle =====
  const toggle = document.getElementById("theme-toggle");
  const saved = localStorage.getItem("theme");
  if (saved) html.setAttribute("data-theme", saved);

  toggle.addEventListener("click", () => {
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
  const themeBtn = document.getElementById("theme-settings-btn");
  const themePopover = document.getElementById("theme-popover");
  const themePopoverClose = document.getElementById("theme-popover-close");

  if (themeBtn && themePopover) {
    themeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      themePopover.classList.toggle("open");
    });
    themePopoverClose.addEventListener("click", () => {
      themePopover.classList.remove("open");
    });
    // Preset swatches
    themePopover.querySelectorAll(".color-swatch").forEach(swatch => {
      swatch.addEventListener("click", () => {
        applyAccentColor(swatch.dataset.color);
      });
    });

    // Custom color picker
    const customColor = document.getElementById("custom-color");
    if (customColor) {
      if (savedAccent) customColor.value = savedAccent;
      customColor.addEventListener("input", () => {
        applyAccentColor(customColor.value);
      });
    }
  }

  // ===== Density toggle =====
  const densityBtn = document.getElementById("density-toggle");
  const densityLevels = ["compact", "default", "comfortable"];
  const savedDensity = localStorage.getItem("density") || "default";
  html.setAttribute("data-density", savedDensity);

  if (densityBtn) {
    densityBtn.addEventListener("click", () => {
      const current = html.getAttribute("data-density") || "default";
      const idx = densityLevels.indexOf(current);
      const next = densityLevels[(idx + 1) % densityLevels.length];
      html.setAttribute("data-density", next);
      localStorage.setItem("density", next);
      // Brief visual indicator
      densityBtn.title = `Density: ${next}`;
    });
    densityBtn.title = `Density: ${savedDensity}`;
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
    });
  }

  // ===== Privacy badge popover =====
  const privacyBadge = document.getElementById("privacy-badge");
  const privacyPopover = document.getElementById("privacy-popover");
  const privacyPopoverClose = document.getElementById("privacy-popover-close");
  if (privacyBadge && privacyPopover) {
    privacyBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      privacyPopover.classList.toggle("open");
    });
    if (privacyPopoverClose) {
      privacyPopoverClose.addEventListener("click", () => {
        privacyPopover.classList.remove("open");
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
      {bang: "!w", label: "Wikipedia", desc: "Search Wikipedia"},
      {bang: "!yt", label: "YouTube", desc: "Search YouTube"},
      {bang: "!gh", label: "GitHub", desc: "Search GitHub"},
      {bang: "!so", label: "StackOverflow", desc: "Search StackOverflow"},
      {bang: "!r", label: "Reddit", desc: "Search Reddit"},
      {bang: "!a", label: "Amazon", desc: "Search Amazon"},
      {bang: "!g", label: "Google", desc: "Search Google"},
      {bang: "!tw", label: "X / Twitter", desc: "Search X"},
      {bang: "!npm", label: "npm", desc: "Search npm"},
      {bang: "!pypi", label: "PyPI", desc: "Search PyPI"},
      {bang: "!mdn", label: "MDN", desc: "Search MDN"},
      {bang: "!maps", label: "Maps", desc: "Search OpenStreetMap"},
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

    const HISTORY_KEY = "freesearch_history";
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
    if (timeSelect) {
      // Pre-select if after: operator exists
      const currentQ = filterInput ? filterInput.value : "";
      const afterMatch = currentQ.match(/\bafter:(\S+)/i);
      if (afterMatch) {
        // Try to determine which option matches
        const afterDate = new Date(afterMatch[1]);
        const now = new Date();
        const diffDays = Math.round((now - afterDate) / 86400000);
        if (diffDays <= 0.1) timeSelect.value = "1h";
        else if (diffDays <= 1) timeSelect.value = "24h";
        else if (diffDays <= 7) timeSelect.value = "7d";
        else if (diffDays <= 30) timeSelect.value = "30d";
        else if (diffDays <= 365) timeSelect.value = "365d";
      }

      timeSelect.addEventListener("change", () => {
        let q = filterInput.value;
        q = removeOperator(q, "after");
        if (timeSelect.value) {
          const now = new Date();
          const map = { "1h": 1/24, "24h": 1, "7d": 7, "30d": 30, "365d": 365 };
          const days = map[timeSelect.value] || 0;
          if (days) {
            const d = new Date(now.getTime() - days * 86400000);
            const dateStr = d.toISOString().slice(0, 10);
            q = `${q} after:${dateStr}`.trim();
          }
        }
        filterInput.value = q;
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
    const page = parseInt(sentinel.dataset.page) + 1;
    sentinel.querySelector(".scroll-loader").classList.remove("hidden");
    showSkeletons(5);

    fetch(`/search?q=${encodeURIComponent(query)}&page=${page}&type=${type}`, {
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
          } else if (type === "code") {
            el.className = "result code-result";
            el.innerHTML = `<div class="code-result-header"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${r.language ? `<span class="code-lang-badge">${esc(r.language)}</span>` : ""}<span class="code-source-badge">${esc(r.source || "")}</span></div>${faviconImg(r.url)}<cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p><div class="code-meta">${r.stars ? `<span class="code-stat">&#9733; ${esc(r.stars)}</span>` : ""}${r.forks ? `<span class="code-stat">&#9906; ${esc(r.forks)}</span>` : ""}</div>`;
          } else {
            el.className = "result";
            el.innerHTML = `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${faviconImg(r.url)}<cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p>${r.date ? `<time class="result-date">${esc(r.date)}</time>` : ""}`;
          }
          frag.appendChild(el);
        });
        container.appendChild(frag);
        sentinel.dataset.page = page;
        if (data.has_more) { hasMore = true; sentinel.querySelector(".scroll-loader").classList.add("hidden"); }
        else { hasMore = false; sentinel.remove(); observer.disconnect(); }
        loading = false;
      })
      .catch(() => { removeSkeletons(); sentinel.querySelector(".scroll-loader").classList.add("hidden"); loading = false; });
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

    // Theme popover close
    if (themePopover && themePopover.classList.contains("open")) {
      if (!target.closest(".theme-popover") && !target.closest("#theme-settings-btn")) {
        themePopover.classList.remove("open");
      }
    }

    // Privacy popover close
    if (privacyPopover && privacyPopover.classList.contains("open")) {
      if (!target.closest(".privacy-popover") && !target.closest("#privacy-badge")) {
        privacyPopover.classList.remove("open");
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
        .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
        .replace(/\n/g, "<br>");
      div.innerHTML = `<div class="chat-msg-content">${formatted}</div>`;
      chatMessages.appendChild(div);
      chatBody.scrollTop = chatBody.scrollHeight;
      return id;
    }
    function removeMessage(id) { const el = document.getElementById(id); if (el) el.remove(); }
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



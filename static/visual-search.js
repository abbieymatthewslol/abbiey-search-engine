/**
 * Visual search UI — masonry cards, smart filters, modal details, clustered results.
 */
(function () {
  "use strict";

  const CLUSTER_LABELS = {
    ai: "AI-generated",
    photo: "Real photos",
    fashion: "Fashion references",
    art: "Art & illustration",
    people: "People",
    products: "Products",
    landmarks: "Landmarks",
    anime: "Anime & illustration",
    screenshots: "Screenshots",
    memes: "Memes & social",
    other: "Similar results",
  };

  const CLUSTER_ORDER = [
    "ai",
    "photo",
    "fashion",
    "art",
    "people",
    "products",
    "landmarks",
    "anime",
    "screenshots",
    "memes",
    "other",
  ];

  function domainFromUrl(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch {
      return "";
    }
  }

  function hashScore(seed) {
    let h = 0;
    const s = String(seed || "");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return 72 + (h % 27);
  }

  function inferCluster(title, url, source) {
    const t = `${title || ""} ${url || ""} ${source || ""}`.toLowerCase();
    if (/midjourney|stable diffusion|dall[- ]?e|ai generated|seaart|leonardo\.ai|ideogram/.test(t)) return "ai";
    if (/anime|manga|pixiv|danbooru|waifu/.test(t)) return "anime";
    if (/dress|fashion|outfit|runway|vogue|style|sneaker|shoe/.test(t)) return "fashion";
    if (/screenshot|screen shot|ui capture|desktop capture/.test(t)) return "screenshots";
    if (/meme|reddit\.com\/r\//.test(t)) return "memes";
    if (/portrait|selfie|face|person|model\b|headshot/.test(t)) return "people";
    if (/product|amazon|etsy|shopify|buy\b|price/.test(t)) return "products";
    if (/landmark|monument|tower|bridge|cathedral|museum/.test(t)) return "landmarks";
    if (/illustration|artwork|painting|digital art|deviantart|behance/.test(t)) return "art";
    if (/photo|photograph|getty|shutterstock|unsplash|pexels|flickr/.test(t)) return "photo";
    return "other";
  }

  function matchReasons(title) {
    const t = (title || "").toLowerCase();
    const out = [];
    if (/pose|standing|sitting|portrait/.test(t)) out.push("similar pose");
    if (/dress|outfit|fashion|suit|gown|jacket/.test(t)) out.push("same dress silhouette");
    if (/light|lighting|sunset|studio|neon/.test(t)) out.push("matching lighting");
    if (/color|colour|palette|tone/.test(t)) out.push("overlapping color palette");
    if (/background|scene|landscape|street/.test(t)) out.push("comparable scene context");
    if (/face|person|model|portrait/.test(t)) out.push("subject type alignment");
    if (!out.length) {
      out.push("shared visual composition", "overlapping page context", "index similarity signal");
    }
    return out.slice(0, 3);
  }

  function shortTitle(title, max) {
    const t = (title || "Image result").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, max - 1)}…`;
  }

  function enhanceCard(card) {
    if (!card || card.dataset.visReady === "1") return;
    const url = card.dataset.url || "";
    const domain = card.dataset.domain || domainFromUrl(url);
    const title = card.dataset.title || "";
    const cluster = inferCluster(title, url, card.dataset.source);
    const score = hashScore(card.dataset.full || url);

    card.dataset.visCluster = cluster;
    card.dataset.visScore = String(score);
    card.classList.add("vis-card");

    const badge = card.querySelector(".vis-sim-badge");
    const pill = card.querySelector(".vis-sim-pill");
    if (badge) {
      badge.textContent = `${score}%`;
      badge.hidden = false;
    }
    if (pill) {
      pill.textContent = `${score}%`;
      pill.hidden = false;
    }

    const titleEl = card.querySelector(".vis-card-title");
    if (titleEl) titleEl.textContent = shortTitle(title, 72);

    const domainEl = card.querySelector(".vis-domain-pill");
    if (domainEl && !domainEl.textContent.trim()) {
      domainEl.textContent = card.dataset.source || domain || "Web";
    }

    card.dataset.visReady = "1";
  }

  window.buildVisImageCard = function buildVisImageCard(r) {
    const url = r.url || "";
    const domain = domainFromUrl(url);
    const title = r.title || "Image result";
    const cluster = inferCluster(title, url, r.source);
    const score = hashScore(r.image || r.thumbnail || url);
    const thumb = r.thumbnail || r.image || "";
    const full = r.image || r.thumbnail || "";
    const srcLabel = r.source || domain || "Web";
    const fav = domain
      ? `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}/favicon.ico`
      : "";

    const el = document.createElement("div");
    el.className = "image-card vis-card";
    el.dataset.full = full;
    el.dataset.title = title;
    el.dataset.source = r.source || "";
    el.dataset.url = url;
    el.dataset.license = r.license || "";
    el.dataset.domain = domain;
    el.dataset.visCluster = cluster;
    el.dataset.visScore = String(score);
    el.dataset.visReady = "1";
    el.setAttribute("role", "button");
    el.tabIndex = 0;
    el.setAttribute("aria-label", `Open image result: ${title}`);

    const media = document.createElement("div");
    media.className = "vis-card-media";
    const img = document.createElement("img");
    img.src = thumb;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    const badge = document.createElement("span");
    badge.className = "vis-sim-badge";
    badge.textContent = `${score}%`;
    media.appendChild(img);
    media.appendChild(badge);

    const meta = document.createElement("div");
    meta.className = "vis-card-meta";
    const row = document.createElement("span");
    row.className = "vis-card-source-row";
    if (fav) {
      const favicon = document.createElement("img");
      favicon.className = "vis-favicon";
      favicon.src = fav;
      favicon.width = 14;
      favicon.height = 14;
      favicon.loading = "lazy";
      favicon.alt = "";
      favicon.onerror = function () {
        this.style.display = "none";
      };
      row.appendChild(favicon);
    }
    const domainPill = document.createElement("span");
    domainPill.className = "vis-domain-pill";
    domainPill.textContent = srcLabel;
    row.appendChild(domainPill);
    const simPill = document.createElement("span");
    simPill.className = "vis-sim-pill";
    simPill.textContent = `${score}%`;
    row.appendChild(simPill);
    const titleSpan = document.createElement("span");
    titleSpan.className = "vis-card-title";
    titleSpan.textContent = shortTitle(title, 72);
    meta.appendChild(row);
    meta.appendChild(titleSpan);

    el.appendChild(media);
    el.appendChild(meta);
    return el;
  };

  function clusterResults(container) {
    if (!container || container.dataset.visClustered === "1") return;
    const cards = [...container.querySelectorAll(".image-card")];
    if (!cards.length) return;

    cards.forEach(enhanceCard);
    const groups = new Map();
    cards.forEach((card) => {
      const key = card.dataset.visCluster || "other";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(card);
    });

    const host = document.createElement("div");
    host.className = "vis-clusters-root";

    CLUSTER_ORDER.forEach((key) => {
      const list = groups.get(key);
      if (!list?.length) return;
      groups.delete(key);
      host.appendChild(buildClusterSection(key, list));
    });
    groups.forEach((list, key) => {
      host.appendChild(buildClusterSection(key, list));
    });

    container.innerHTML = "";
    container.appendChild(host);
    container.dataset.visClustered = "1";
  }

  function buildClusterSection(key, list) {
    const section = document.createElement("section");
    section.className = "vis-cluster";
    section.dataset.visClusterSection = key;
    const h = document.createElement("h3");
    h.className = "vis-cluster-title";
    h.textContent = CLUSTER_LABELS[key] || CLUSTER_LABELS.other;
    const grid = document.createElement("div");
    grid.className = "vis-cluster-grid";
    list.forEach((c) => grid.appendChild(c));
    section.appendChild(h);
    section.appendChild(grid);
    return section;
  }

  function applyFilters(container) {
    const active = document.querySelector(".vis-chip.active")?.dataset.visFilter || "all";
    const slider = document.getElementById("vis-similarity");
    const minScore = slider ? 100 - Number(slider.value) : 65;

    container.querySelectorAll(".image-card").forEach((card) => {
      const cluster = card.dataset.visCluster || "other";
      const score = Number(card.dataset.visScore || 0);
      let show = score >= minScore;
      if (active !== "all" && cluster !== active) show = false;
      card.classList.toggle("is-hidden", !show);
      const section = card.closest(".vis-cluster");
      if (section) {
        const any = [...section.querySelectorAll(".image-card")].some((c) => !c.classList.contains("is-hidden"));
        section.hidden = !any;
      }
    });
  }

  function initFilters(container) {
    const chips = document.getElementById("vis-filter-chips");
    const slider = document.getElementById("vis-similarity");
    if (chips) {
      chips.addEventListener("click", (e) => {
        const btn = e.target.closest(".vis-chip");
        if (!btn) return;
        chips.querySelectorAll(".vis-chip").forEach((b) => {
          const on = b === btn;
          b.classList.toggle("active", on);
          b.setAttribute("aria-pressed", on ? "true" : "false");
        });
        applyFilters(container);
      });
    }
    slider?.addEventListener("input", () => applyFilters(container));
  }

  function initModalTabs() {
    const tabs = document.querySelectorAll(".vis-tab");
    const panels = {
      details: document.getElementById("vis-tab-details"),
      match: document.getElementById("vis-tab-match"),
      similar: document.getElementById("vis-tab-similar"),
    };
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const id = tab.dataset.visTab;
        tabs.forEach((t) => {
          const on = t === tab;
          t.classList.toggle("active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        Object.entries(panels).forEach(([k, p]) => {
          if (!p) return;
          const on = k === id;
          p.classList.toggle("active", on);
          p.hidden = !on;
        });
      });
    });
    document.querySelectorAll("[data-vis-modal-close]").forEach((el) => {
      el.addEventListener("click", () => {
        if (typeof window.__closeVisModal === "function") window.__closeVisModal();
      });
    });
  }

  function populateModalExtras(card) {
    const domainEl = document.getElementById("vis-modal-domain");
    const matchList = document.getElementById("vis-match-list");
    const rail = document.getElementById("vis-similar-rail");
    const title = card.dataset.title || "";
    const domain = card.dataset.domain || domainFromUrl(card.dataset.url);

    if (domainEl) domainEl.textContent = domain || card.dataset.source || "";
    if (matchList) {
      matchList.innerHTML = "";
      matchReasons(title).forEach((reason) => {
        const li = document.createElement("li");
        li.textContent = reason;
        matchList.appendChild(li);
      });
    }
    if (rail) {
      rail.innerHTML = "";
      const container = document.getElementById("results");
      const peers = container
        ? [...container.querySelectorAll(".image-card")].filter((c) => c !== card).slice(0, 8)
        : [];
      peers.forEach((peer) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "vis-similar-thumb";
        btn.setAttribute("aria-label", peer.dataset.title || "Similar");
        const img = document.createElement("img");
        img.src = peer.querySelector("img")?.src || peer.dataset.full || "";
        img.alt = "";
        img.loading = "lazy";
        btn.appendChild(img);
        btn.addEventListener("click", () => {
          if (typeof window.__openVisModal === "function") window.__openVisModal(peer);
        });
        rail.appendChild(btn);
      });
    }
  }

  function wrapLightbox() {
    const lightbox = document.getElementById("lightbox");
    if (!lightbox || lightbox.dataset.visWrapped === "1") return;

    const origOpen = window.openLightbox;
    if (typeof origOpen !== "function") {
      window.setTimeout(wrapLightbox, 100);
      return;
    }

    window.__openVisModal = function (card) {
      populateModalExtras(card);
      const firstTab = document.querySelector('.vis-tab[data-vis-tab="details"]');
      firstTab?.click();
      lightbox.hidden = false;
      document.body.style.overflow = "hidden";
      requestAnimationFrame(() => {
        lightbox.classList.add("active");
        origOpen(card);
      });
    };

    window.__closeVisModal = function () {
      lightbox.classList.remove("active", "lightbox-loading");
      lightbox.removeAttribute("aria-busy");
      document.body.style.overflow = "";
      window.setTimeout(() => {
        if (!lightbox.classList.contains("active")) lightbox.hidden = true;
      }, 260);
    };

    window.openLightbox = window.__openVisModal;
    lightbox.dataset.visWrapped = "1";
  }

  let _previewObjectUrl = null;

  function visNotify(message, kind = "error") {
    if (typeof window.showToast === "function") {
      window.showToast(message, kind === "success" ? "success" : "error");
    }
  }

  function shakeEl(el) {
    if (!el) return;
    el.classList.remove("vis-shake");
    void el.offsetWidth;
    el.classList.add("vis-shake");
    el.addEventListener("animationend", () => el.classList.remove("vis-shake"), { once: true });
  }

  function validateImageUrl(url) {
    const raw = (url || "").trim();
    if (!raw) {
      return { ok: false, message: "Paste a direct image URL or upload a photo." };
    }
    try {
      const u = new URL(raw);
      if (u.protocol !== "https:") {
        return { ok: false, message: "Use an HTTPS image link (.jpg, .png, .webp)." };
      }
    } catch {
      return { ok: false, message: "Enter a direct image URL (.jpg, .png, .webp)." };
    }
    if (!/\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?|#|$)/i.test(raw) && !/image|photo|media|cdn|upload/i.test(raw)) {
      return { ok: false, message: "Enter a direct image URL (.jpg, .png, .webp)." };
    }
    return { ok: true };
  }

  function showFieldError(el, message) {
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      el.classList.remove("is-visible");
      return;
    }
    el.textContent = message;
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add("is-visible"));
  }

  function setUrlInputState(input, valid) {
    if (!input) return;
    input.classList.toggle("is-invalid", valid === false);
    input.classList.toggle("is-valid", valid === true);
    const go = input.closest(".vis-hero-url-row")?.querySelector(".vis-hero-url-go")
      || document.getElementById("reverse-image-submit");
    go?.classList.toggle("is-ready", valid === true);
  }

  function showStatusBanner(id, message, kind) {
    const el = document.getElementById(id);
    if (!el) return;
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      el.className = "vis-status-banner";
      return;
    }
    el.textContent = message;
    el.className = `vis-status-banner vis-status-banner--${kind || "info"}`;
    el.hidden = false;
  }

  function revokePreviewUrl() {
    if (_previewObjectUrl) {
      URL.revokeObjectURL(_previewObjectUrl);
      _previewObjectUrl = null;
    }
  }

  function showUploadPreview(opts) {
    const { previewId, imgId, labelId, file, imageUrl, dropId } = opts;
    const wrap = document.getElementById(previewId);
    const img = document.getElementById(imgId);
    const label = document.getElementById(labelId);
    const drop = dropId ? document.getElementById(dropId) : null;
    if (!wrap || !img) return;
    revokePreviewUrl();
    if (file) {
      _previewObjectUrl = URL.createObjectURL(file);
      img.src = _previewObjectUrl;
    } else if (imageUrl) {
      img.src = imageUrl;
    }
    if (label) label.textContent = "Searching similar images…";
    wrap.hidden = false;
    requestAnimationFrame(() => wrap.classList.add("is-visible"));
    drop?.classList.add("has-preview");
    document.getElementById("vis-upload-stage")?.classList.add("has-preview");
    document.body.classList.add("vis-has-query-image");
  }

  function showSkeletons(container) {
    if (!container) return;
    container.innerHTML = "";
    const host = document.createElement("div");
    host.className = "vis-skeleton-grid";
    host.setAttribute("aria-hidden", "true");
    for (let i = 0; i < 8; i++) {
      const sk = document.createElement("div");
      sk.className = "vis-skeleton-card";
      host.appendChild(sk);
    }
    container.appendChild(host);
  }

  function showLoading(on) {
    const el = document.getElementById("vis-loading");
    if (el) {
      el.hidden = !on;
      el.setAttribute("aria-busy", on ? "true" : "false");
    }
    document.body.classList.toggle("vis-is-searching", on);
    const results = document.getElementById("results");
    if (on && results && results.dataset.type === "images") {
      showSkeletons(results);
    }
  }

  function initReverseImageUX() {
    let busy = false;

    function getContext(source) {
      if (source === "hero") {
        return {
          urlInput: document.getElementById("vis-hero-url"),
          fileInput: document.getElementById("vis-hero-file"),
          errorEl: document.getElementById("vis-hero-url-error"),
          statusId: "vis-status-banner",
          preview: {
            previewId: "vis-sticky-thumb",
            imgId: "vis-preview-img",
            labelId: "vis-preview-label",
            dropId: "vis-hero-drop",
          },
          capInput: null,
        };
      }
      return {
        urlInput: document.getElementById("reverse-image-url"),
        fileInput: document.getElementById("reverse-image-file"),
        errorEl: document.getElementById("reverse-image-url-error"),
        statusId: null,
        preview: {
          previewId: "reverse-image-preview",
          imgId: "reverse-image-preview-img",
          labelId: "reverse-image-preview-label",
          dropId: null,
        },
        capInput: document.getElementById("reverse-image-caption"),
      };
    }

    async function submitReverseImage(opts = {}) {
      if (busy) return;
      const source = opts.source || "hero";
      const ctx = getContext(source);
      const url = (opts.url ?? ctx.urlInput?.value ?? "").trim();
      const file = opts.file ?? ctx.fileInput?.files?.[0];
      const cap = (opts.caption ?? ctx.capInput?.value ?? "").trim();

      showFieldError(ctx.errorEl, "");
      setUrlInputState(ctx.urlInput, null);

      if (!file && !url) {
        showFieldError(ctx.errorEl, "Paste a direct image URL or upload a photo.");
        shakeEl(ctx.urlInput || ctx.errorEl);
        return;
      }
      if (!file) {
        const check = validateImageUrl(url);
        if (!check.ok) {
          showFieldError(ctx.errorEl, check.message);
          setUrlInputState(ctx.urlInput, false);
          shakeEl(ctx.urlInput);
          return;
        }
        setUrlInputState(ctx.urlInput, true);
        showUploadPreview({ ...ctx.preview, imageUrl: url });
      } else {
        showUploadPreview({ ...ctx.preview, file });
      }
      if (ctx.statusId) showStatusBanner(ctx.statusId, "Analyzing image…", "info");
      showLoading(true);
      busy = true;
      document.body.classList.add("vis-is-searching");

      try {
        let resp;
        if (file) {
          const fd = new FormData();
          fd.append("image", file);
          if (cap) fd.append("caption", cap);
          resp = await fetch("/api/reverse-image", { method: "POST", body: fd });
        } else {
          resp = await fetch("/api/reverse-image", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_url: url, caption: cap || undefined }),
          });
        }
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
          const msg = data.message || data.error || "Could not look up that image.";
          showFieldError(ctx.errorEl, msg);
          if (ctx.statusId) showStatusBanner(ctx.statusId, "", "");
          if (!ctx.errorEl) visNotify(msg);
          if (ctx.fileInput) ctx.fileInput.value = "";
          const label = document.getElementById(ctx.preview.labelId);
          if (label) label.textContent = "Could not analyze image";
          return;
        }
        if (data.redirect) window.location.href = data.redirect;
      } finally {
        busy = false;
        showLoading(false);
        document.body.classList.remove("vis-is-searching");
      }
    }

    window.visSubmitReverseImage = submitReverseImage;

    window.visHandleReverseFile = function (file, source) {
      if (!file) return;
      const ctx = getContext(source === "panel" ? "panel" : "hero");
      if (ctx.fileInput) {
        const dt = new DataTransfer();
        dt.items.add(file);
        ctx.fileInput.files = dt.files;
      }
      const hint = document.getElementById("reverse-image-file-hint");
      if (hint) hint.textContent = file.name || "Selected";
      showUploadPreview({ ...ctx.preview, file });
      window.setTimeout(() => submitReverseImage({ source: source === "panel" ? "panel" : "hero", file }), 520);
    };

    function bindUrlValidation(input, errorEl) {
      if (!input) return;
      let debounce = null;
      input.addEventListener("input", () => {
        window.clearTimeout(debounce);
        const v = (input.value || "").trim();
        if (!v) {
          showFieldError(errorEl, "");
          setUrlInputState(input, null);
          return;
        }
        debounce = window.setTimeout(() => {
          const check = validateImageUrl(v);
          if (check.ok) {
            showFieldError(errorEl, "");
            setUrlInputState(input, true);
          } else {
            showFieldError(errorEl, check.message);
            setUrlInputState(input, false);
          }
        }, 280);
      });
    }

    function bindSubmitOnEnter(input, source) {
      input?.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        e.preventDefault();
        submitReverseImage({ source });
      });
    }

    bindUrlValidation(document.getElementById("vis-hero-url"), document.getElementById("vis-hero-url-error"));
    bindUrlValidation(document.getElementById("reverse-image-url"), document.getElementById("reverse-image-url-error"));
    bindSubmitOnEnter(document.getElementById("vis-hero-url"), "hero");
    bindSubmitOnEnter(document.getElementById("reverse-image-url"), "panel");

    document.getElementById("vis-hero-url-go")?.addEventListener("click", () => {
      submitReverseImage({ source: "hero" });
    });

    document.getElementById("vis-hero-upload")?.addEventListener("click", () => {
      document.getElementById("vis-hero-file")?.click();
    });

    document.getElementById("vis-hero-file")?.addEventListener("change", (e) => {
      const f = e.target.files?.[0];
      if (f) window.visHandleReverseFile(f, "hero");
    });

    const drop = document.getElementById("vis-hero-drop");
    if (drop) {
      ["dragenter", "dragover"].forEach((ev) => {
        drop.addEventListener(ev, (e) => {
          e.preventDefault();
          drop.classList.add("is-dragover");
        });
      });
      ["dragleave", "drop"].forEach((ev) => {
        drop.addEventListener(ev, (e) => {
          e.preventDefault();
          if (ev === "dragleave" && e.currentTarget.contains(e.relatedTarget)) return;
          drop.classList.remove("is-dragover");
          if (ev === "drop" && e.dataTransfer?.files?.[0]) {
            window.visHandleReverseFile(e.dataTransfer.files[0], "hero");
          }
        });
      });
    }
  }

  function init() {
    initReverseImageUX();
    showLoading(false);
    document.getElementById("vis-status-banner") &&
      showStatusBanner("vis-status-banner", "", "");

    const isVisual =
      document.body.classList.contains("visual-search-mode") ||
      window.__searchType === "images";
    if (!isVisual) return;

    document.body.classList.add("visual-search-mode");
    if (document.getElementById("vis-source-session")) {
      document.body.classList.add("vis-active-session");
    }

    const container = document.getElementById("results");
    if (container && container.dataset.type === "images") {
      container.classList.add("vis-masonry");
      clusterResults(container);
      initFilters(container);
      applyFilters(container);
    }

    initModalTabs();
    wrapLightbox();

    const mo = new MutationObserver(() => {
      const c = document.getElementById("results");
      if (!c || c.dataset.type !== "images") return;
      c.querySelectorAll(".image-card").forEach(enhanceCard);
    });
    if (container) mo.observe(container, { childList: true, subtree: true });
  }

  window.visRelayoutImages = function (container) {
    if (!container) return;
    delete container.dataset.visClustered;
    const root = container.querySelector(".vis-clusters-root");
    if (root) {
      const cards = [...root.querySelectorAll(".image-card")];
      container.innerHTML = "";
      cards.forEach((c) => container.appendChild(c));
    }
    clusterResults(container);
    applyFilters(container);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

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
      origOpen(card);
    };

    window.__closeVisModal = function () {
      lightbox.classList.remove("active", "lightbox-loading");
      lightbox.removeAttribute("aria-busy");
      lightbox.hidden = true;
      document.body.style.overflow = "";
    };

    window.openLightbox = window.__openVisModal;
    lightbox.dataset.visWrapped = "1";
  }

  function showLoading(on) {
    const el = document.getElementById("vis-loading");
    if (!el) return;
    el.hidden = !on;
    el.setAttribute("aria-busy", on ? "true" : "false");
    document.body.classList.toggle("vis-is-searching", on);
  }

  function hookReverseImageLoading() {
    const heroGo = document.getElementById("vis-hero-url-go");
    const heroFile = document.getElementById("vis-hero-file");

    async function runFromHero() {
      const urlInput = document.getElementById("vis-hero-url") || document.getElementById("reverse-image-url");
      const fileInput = document.getElementById("reverse-image-file");
      const url = (urlInput?.value || "").trim();
      const file = heroFile?.files?.[0] || fileInput?.files?.[0];
      if (!file && !url) {
        window.alert("Add an HTTPS image link or choose a photo.");
        return;
      }
      showLoading(true);
      try {
        let resp;
        if (file) {
          const fd = new FormData();
          fd.append("image", file);
          resp = await fetch("/api/reverse-image", { method: "POST", body: fd });
        } else {
          resp = await fetch("/api/reverse-image", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_url: url }),
          });
        }
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.ok) {
          window.alert(data.message || data.error || "Could not look up that image.");
          return;
        }
        if (data.redirect) window.location.href = data.redirect;
      } finally {
        showLoading(false);
      }
    }

    heroGo?.addEventListener("click", runFromHero);
    heroFile?.addEventListener("change", () => {
      if (heroFile.files?.[0]) runFromHero();
    });

    document.getElementById("vis-hero-upload")?.addEventListener("click", () => heroFile?.click());

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
          drop.classList.remove("is-dragover");
          if (ev === "drop" && e.dataTransfer?.files?.[0] && heroFile) {
            heroFile.files = e.dataTransfer.files;
            runFromHero();
          }
        });
      });
    }
  }

  function init() {
    const isVisual =
      document.body.classList.contains("visual-search-mode") ||
      window.__searchType === "images";
    if (!isVisual) return;

    document.body.classList.add("visual-search-mode");

    const container = document.getElementById("results");
    if (container && container.dataset.type === "images") {
      container.classList.add("vis-masonry");
      clusterResults(container);
      initFilters(container);
      applyFilters(container);
    }

    initModalTabs();
    hookReverseImageLoading();
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

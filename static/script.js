/**
 * script.js â€” main client bundle (single file for simple deploy/caching).
 * Logical regions (grep for "// ====="):
 *   Post-checkout search unlock sync, loading bars, theme, settings modal, filters, infinite scroll,
 *   lightbox, preview panel + layout gutter, "/" shortcut, chat, onion verify,
 *   bookmarks, related/trending, voice, result reorder prefs (drag), scroll indexing ring,
 *   unfiltered leaderboard, in-results filter, view mode, ripple, tabs.
 */
document.addEventListener("DOMContentLoaded", () => {
  const html = document.documentElement;
  const PHONE_PLACEHOLDER_BY_COUNTRY = Object.freeze({
    AU: "+61 412 345 678",
    BR: "+55 11 91234-5678",
    CA: "+1 416 555 0123",
    DE: "+49 1512 3456789",
    ES: "+34 612 34 56 78",
    FR: "+33 6 12 34 56 78",
    GB: "+44 7700 900123",
    IE: "+353 85 123 4567",
    IN: "+91 98765 43210",
    IT: "+39 312 345 6789",
    JP: "+81 90-1234-5678",
    MX: "+52 55 1234 5678",
    NL: "+31 6 12345678",
    NZ: "+64 21 123 4567",
    SG: "+65 9123 4567",
    US: "+1 555 123 4567",
    ZA: "+27 71 123 4567",
  });
  const SEARCH_REGION_BY_COUNTRY = Object.freeze({
    AU: "au-en",
    BR: "br-pt",
    CA: "ca-en",
    DE: "de-de",
    ES: "es-es",
    FR: "fr-fr",
    GB: "uk-en",
    IE: "uk-en",
    IN: "in-en",
    IT: "it-it",
    JP: "jp-jp",
    NZ: "au-en",
    US: "us-en",
  });
  const TIMEZONE_COUNTRY_BY_EXACT = Object.freeze({
    "Europe/Dublin": "IE",
    "Europe/London": "GB",
    "Pacific/Auckland": "NZ",
  });
  const TIMEZONE_COUNTRY_BY_PREFIX = Object.freeze({
    "Africa/Johannesburg": "ZA",
    "America/Chicago": "US",
    "America/Denver": "US",
    "America/Edmonton": "CA",
    "America/Halifax": "CA",
    "America/Los_Angeles": "US",
    "America/Mexico_City": "MX",
    "America/New_York": "US",
    "America/Phoenix": "US",
    "America/Sao_Paulo": "BR",
    "America/Toronto": "CA",
    "America/Vancouver": "CA",
    "America/Winnipeg": "CA",
    "Asia/Kolkata": "IN",
    "Asia/Singapore": "SG",
    "Asia/Tokyo": "JP",
    "Australia/": "AU",
    "Europe/Amsterdam": "NL",
    "Europe/Berlin": "DE",
    "Europe/Madrid": "ES",
    "Europe/Paris": "FR",
    "Europe/Rome": "IT",
    "Pacific/Honolulu": "US",
  });
  const TERMS_CONSENT_KEY = "abbiey_terms_accepted";
  const LOCATION_CONSENT_KEY = "abbiey_location_consent";
  const LOCATION_CONSENT_VALUES = Object.freeze({
    granted: "granted",
    denied: "denied",
  });
  const CLIENT_PREF_MAX_AGE = 31536000;
  let geoRequestInFlight = false;

  /** Line-art search glass: tilted lens, NW highlight arc, rounded handle (suggestions + recent + inline reuse). */
  const ICON_SEARCH_GLASS_SVG =
    '<svg class="icon-search-glass" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<g transform="rotate(38 12 11.5)" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="11" r="5.5" stroke-width="1.65"/>' +
    '<path d="M9.05 9.4A3.15 3.15 0 0 1 10.95 7.72" stroke-width="1.35"/>' +
    '<line x1="16.2" y1="15.05" x2="20.95" y2="20.4" stroke-width="2.2"/>' +
    "</g></svg>";
  const CLOSE_ICON_SVG =
    '<svg class="close-icon" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">' +
    '<path d="M5 5L15 15" stroke="currentColor" stroke-width="1.85" stroke-linecap="round"/>' +
    '<path d="M15 5L5 15" stroke="currentColor" stroke-width="1.85" stroke-linecap="round"/>' +
    "</svg>";
  const reducedMotionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;

  function bodyDatasetValue(name) {
    const body = document.body;
    if (!body || !body.dataset) return "";
    const value = body.dataset[name];
    return typeof value === "string" ? value.trim() : "";
  }

  function normalizeCountryCode(raw) {
    const value = String(raw || "").replace(/[^a-z]/gi, "").toUpperCase();
    if (value.length === 2 && value !== "XX" && value !== "ZZ") return value;
    return "";
  }

  function countryCodeFromLocaleTag(localeTag) {
    const normalized = String(localeTag || "").trim().replace(/_/g, "-");
    if (!normalized) return "";
    const parts = normalized.split("-").filter(Boolean);
    if (parts.length < 2) return "";
    return normalizeCountryCode(parts[parts.length - 1]);
  }

  function countryCodeFromTimeZone(timeZone) {
    const zone = String(timeZone || "").trim();
    if (!zone) return "";
    if (TIMEZONE_COUNTRY_BY_EXACT[zone]) return TIMEZONE_COUNTRY_BY_EXACT[zone];
    const prefixes = Object.keys(TIMEZONE_COUNTRY_BY_PREFIX);
    for (let i = 0; i < prefixes.length; i += 1) {
      if (zone === prefixes[i] || zone.startsWith(prefixes[i])) {
        return TIMEZONE_COUNTRY_BY_PREFIX[prefixes[i]];
      }
    }
    return "";
  }

  function detectUserCountryCode() {
    const serverCountry = normalizeCountryCode(bodyDatasetValue("detectedCountry"));
    if (serverCountry) return serverCountry;
    const languages = Array.isArray(navigator.languages) && navigator.languages.length
      ? navigator.languages
      : [navigator.language || ""];
    for (let i = 0; i < languages.length; i += 1) {
      const localeCountry = countryCodeFromLocaleTag(languages[i]);
      if (localeCountry) return localeCountry;
    }
    try {
      const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
      const timeZoneCountry = countryCodeFromTimeZone(timeZone);
      if (timeZoneCountry) return timeZoneCountry;
    } catch (_) {
      /* ignore */
    }
    return "";
  }

  function detectSearchRegion() {
    const serverRegion = bodyDatasetValue("detectedSearchRegion").toLowerCase();
    if (serverRegion) return serverRegion;
    const country = detectUserCountryCode();
    return SEARCH_REGION_BY_COUNTRY[country] || "";
  }

  function searchLangForRegion(region) {
    const value = String(region || "").trim().toLowerCase();
    if (!value) return "";
    const parts = value.split("-");
    return parts.length > 1 ? parts[1] : "";
  }

  function buildSearchHref(query, overrides) {
    const params = new URLSearchParams();
    const q = String(query || "").trim();
    const opts = overrides || {};
    const typeInput = document.getElementById("search-type-input");
    const regionInput = document.getElementById("region-input");
    const langInput = document.getElementById("lang-input");
    const dfInput = document.getElementById("df-input");
    const safeInput = document.getElementById("safesearch-input");
    const cleanwebInput = document.getElementById("cleanweb-input");
    const openKnowledgeCheck = document.getElementById("open-knowledge-check");
    const onionModeInput = document.getElementById("onion-mode-input");
    const sentinel = document.getElementById("results-sentinel");
    const type = String(opts.type || (typeInput && typeInput.value) || window.__searchType || "text").trim() || "text";
    if (!q) return "/search";
    params.set("q", q);
    if (type !== "text") params.set("type", type);
    if (regionInput && regionInput.value.trim()) params.set("region", regionInput.value.trim());
    if (langInput && langInput.value.trim()) params.set("lang", langInput.value.trim());
    if (dfInput && dfInput.value.trim()) params.set("df", dfInput.value.trim());
    if (safeInput && safeInput.value.trim() && safeInput.value.trim() !== "off") {
      params.set("safesearch", safeInput.value.trim());
    }
    if (cleanwebInput && cleanwebInput.value === "1") params.set("cleanweb", "1");
    if (openKnowledgeCheck && openKnowledgeCheck.checked) params.set("open_knowledge", "1");
    if (type === "onion" && onionModeInput && onionModeInput.value.trim()) {
      params.set("onion_mode", onionModeInput.value.trim());
    }
    if (type === "mybot" && sentinel && sentinel.dataset.botId) {
      params.set("bot_id", sentinel.dataset.botId);
    }
    return `/search?${params.toString()}`;
  }

  function readClientCookie(name) {
    try {
      const cookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith(`${name}=`));
      return cookie ? decodeURIComponent(cookie.slice(name.length + 1)) : "";
    } catch (_) {
      return "";
    }
  }

  function writeClientCookie(name, value, maxAgeSeconds) {
    try {
      const secure = window.location.protocol === "https:";
      document.cookie =
        `${name}=${encodeURIComponent(String(value || ""))}; path=/; max-age=${maxAgeSeconds}; samesite=lax` +
        (secure ? "; secure" : "");
    } catch (_) {
      /* ignore */
    }
  }

  function clearClientCookie(name) {
    try {
      const secure = window.location.protocol === "https:";
      document.cookie = `${name}=; path=/; max-age=0; samesite=lax` + (secure ? "; secure" : "");
    } catch (_) {
      /* ignore */
    }
  }

  function isTorSearchMode(mode) {
    return String(mode || "").trim().toLowerCase() === "onion";
  }

  function searchTypeFromHref(href) {
    try {
      const url = new URL(href, window.location.origin);
      if (!url.pathname.startsWith("/search")) return "";
      return String(url.searchParams.get("type") || "text").trim().toLowerCase();
    } catch (_) {
      return "";
    }
  }

  function initTorAgreementGate() {
    const overlay = document.getElementById("tor-agreement-overlay");
    const checkbox = document.getElementById("tor-agreement-check");
    const typeInput = document.getElementById("search-type-input");
    const form = document.getElementById("search-form");
    let approved = false;
    let pendingAction = null;

    function hideBanner() {
      if (!overlay) return;
      overlay.hidden = true;
      document.body.classList.remove("tor-agreement-active");
    }

    function showBanner(action) {
      if (!overlay || !checkbox) {
        approved = true;
        if (typeof action === "function") action();
        return;
      }
      pendingAction = typeof action === "function" ? action : null;
      overlay.hidden = false;
      document.body.classList.add("tor-agreement-active");
      checkbox.checked = false;
      window.setTimeout(() => checkbox.focus(), 0);
    }

    function ensureAgreement(action) {
      if (approved) {
        if (typeof action === "function") action();
        return true;
      }
      showBanner(action);
      return false;
    }

    if (checkbox) {
      checkbox.addEventListener("change", () => {
        if (!checkbox.checked) return;
        approved = true;
        hideBanner();
        const action = pendingAction;
        pendingAction = null;
        if (typeof action === "function") action();
      });
    }

    if (form && typeInput) {
      form.addEventListener(
        "submit",
        (e) => {
          if (!isTorSearchMode(typeInput.value) || approved) return;
          e.preventDefault();
          e.stopImmediatePropagation();
          showBanner(() => {
            if (typeof form.requestSubmit === "function") form.requestSubmit();
            else form.submit();
          });
        },
        true
      );
    }

    window.setTimeout(() => {
      if (typeInput && isTorSearchMode(typeInput.value) && !approved) {
        showBanner();
      }
    }, 0);

    return {
      ensureAgreement,
      isApproved: () => approved,
    };
  }

  const torAgreementGate = initTorAgreementGate();

  function readClientPref(key) {
    try {
      const localValue = localStorage.getItem(key);
      if (localValue != null) return String(localValue);
    } catch (_) {
      /* ignore */
    }
    return readClientCookie(key);
  }

  function writeClientPref(key, value) {
    const normalized = String(value || "");
    try {
      localStorage.setItem(key, normalized);
    } catch (_) {
      /* ignore */
    }
    writeClientCookie(key, normalized, CLIENT_PREF_MAX_AGE);
  }

  function clearClientPref(key) {
    try {
      localStorage.removeItem(key);
    } catch (_) {
      /* ignore */
    }
    clearClientCookie(key);
  }

  function getTermsAccepted() {
    return readClientPref(TERMS_CONSENT_KEY) === "1";
  }

  function setTermsAccepted(accepted) {
    if (accepted) {
      writeClientPref(TERMS_CONSENT_KEY, "1");
    } else {
      clearClientPref(TERMS_CONSENT_KEY);
    }
  }

  function normalizeLocationConsent(value) {
    const normalized = String(value || "").trim().toLowerCase();
    if (normalized === LOCATION_CONSENT_VALUES.granted || normalized === LOCATION_CONSENT_VALUES.denied) {
      return normalized;
    }
    return "";
  }

  function getLocationConsent() {
    return normalizeLocationConsent(readClientPref(LOCATION_CONSENT_KEY));
  }

  function clearStoredGeoCoordinates() {
    try {
      sessionStorage.removeItem("abbiey_geo");
    } catch (_) {
      /* ignore */
    }
    const latInput = document.getElementById("geo-lat-input");
    const lonInput = document.getElementById("geo-lon-input");
    if (latInput) latInput.value = "";
    if (lonInput) lonInput.value = "";
  }

  function setLocationConsent(value) {
    const normalized = normalizeLocationConsent(value);
    if (!normalized) {
      clearClientPref(LOCATION_CONSENT_KEY);
      clearStoredGeoCoordinates();
      return;
    }
    writeClientPref(LOCATION_CONSENT_KEY, normalized);
    if (normalized !== LOCATION_CONSENT_VALUES.granted) {
      clearStoredGeoCoordinates();
    }
  }

  function pageUsesPreciseLocation() {
    return !!document.getElementById("geo-lat-input") || !!document.getElementById("geo-lon-input");
  }

  function storePreciseLocation(lat, lon) {
    try {
      sessionStorage.setItem(
        "abbiey_geo",
        JSON.stringify({
          lat,
          lon,
          t: Date.now(),
        }),
      );
    } catch (_) {
      /* ignore */
    }
    const latInput = document.getElementById("geo-lat-input");
    const lonInput = document.getElementById("geo-lon-input");
    if (latInput) latInput.value = String(lat);
    if (lonInput) lonInput.value = String(lon);
  }

  function requestPreciseLocation() {
    if (!navigator.geolocation || !pageUsesPreciseLocation() || geoRequestInFlight) {
      return Promise.resolve(false);
    }
    geoRequestInFlight = true;
    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          geoRequestInFlight = false;
          storePreciseLocation(pos.coords.latitude, pos.coords.longitude);
          resolve(true);
        },
        () => {
          geoRequestInFlight = false;
          clearStoredGeoCoordinates();
          resolve(false);
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
      );
    });
  }

  function localizePhonePlaceholders() {
    const country = detectUserCountryCode() || "US";
    const placeholder = PHONE_PLACEHOLDER_BY_COUNTRY[country] || PHONE_PLACEHOLDER_BY_COUNTRY.US;
    document.querySelectorAll("[data-phone-placeholder-localize]").forEach((input) => {
      if (!(input instanceof HTMLInputElement)) return;
      input.placeholder = placeholder;
      if (country) input.dataset.phoneCountry = country;
    });
  }

  localizePhonePlaceholders();
  window.__abbieyConsent = {
    getTermsAccepted,
    setTermsAccepted,
    getLocationConsent,
    setLocationConsent,
    clearStoredGeoCoordinates,
    requestPreciseLocation,
  };

  /** Append &lat=&lon= for local ranking when browser or prior search shared coordinates. */
  function geoQuerySuffix() {
    const la = document.getElementById("geo-lat-input");
    const lo = document.getElementById("geo-lon-input");
    let lat = la && la.value.trim();
    let lon = lo && lo.value.trim();
    if (!lat || !lon) {
      try {
        const g = JSON.parse(sessionStorage.getItem("abbiey_geo") || "{}");
        if (typeof g.lat === "number" && typeof g.lon === "number") {
          lat = String(g.lat);
          lon = String(g.lon);
        }
      } catch (_) {
        /* ignore */
      }
    }
    if (lat && lon) return `&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`;
    return "";
  }

  /** Region, language, Original web â€” keep AI APIs aligned with the current SERP. */
  function searchContextQuerySuffix() {
    let s = geoQuerySuffix();
    const reg = document.getElementById("region-input");
    const lng = document.getElementById("lang-input");
    const cw = document.getElementById("cleanweb-input");
    if (reg && reg.value.trim()) s += `&region=${encodeURIComponent(reg.value.trim())}`;
    if (lng && lng.value.trim()) s += `&lang=${encodeURIComponent(lng.value.trim())}`;
    if (cw && cw.value === "1") s += "&cleanweb=1";
    return s;
  }

  /** Server should send stable copy; this trims and blocks obvious junk from ever showing in the UI. */
  function userFacingPreviewError(msg) {
    const s = msg != null ? String(msg).trim() : "";
    if (!s || s.length > 400 || /traceback|exception|error:/i.test(s)) {
      return "We couldn't load a preview for this page.";
    }
    return s;
  }
  function userFacingChatError(msg) {
    const s = msg != null ? String(msg).trim() : "";
    if (!s || s.length > 400 || /traceback|exception|^error:/i.test(s)) {
      return "The research assistant is temporarily unavailable. Please try again.";
    }
    return s;
  }
  function userFacingApiError(msg, fallback) {
    const s = msg != null ? String(msg).trim() : "";
    if (!s || s.length > 240 || /traceback|exception|^error:/i.test(s)) {
      return fallback;
    }
    return s;
  }
  function showToast(message, kind = "success") {
    if (!message) return;
    const toast = document.createElement("div");
    toast.className = `toast ${kind}`;
    toast.textContent = String(message);
    document.body.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3200);
  }
  window.showToast = showToast;
  async function fetchJson(url, options = {}) {
    const opts = {
      credentials: "same-origin",
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    };
    const resp = await fetch(url, opts);
    let data = null;
    try {
      const text = await resp.text();
      data = text ? JSON.parse(text) : null;
    } catch (_) {
      data = null;
    }
    if (resp.status === 429) {
      showToast("You're sending requests too quickly. Please wait a moment and try again.");
    }
    return { ok: resp.ok, status: resp.status, data, response: resp };
  }
  function motionDelay(ms) {
    return reducedMotionQuery && reducedMotionQuery.matches ? 0 : ms;
  }
  function afterMotion(ms, cb) {
    window.setTimeout(cb, motionDelay(ms));
  }
  function rememberFocus(fallback = null) {
    const active = document.activeElement;
    if (active instanceof HTMLElement) return active;
    if (fallback instanceof HTMLElement) return fallback;
    return null;
  }
  function restoreFocus(target) {
    if (!(target instanceof HTMLElement)) return;
    try {
      target.focus({ preventScroll: true });
    } catch (_) {
      target.focus();
    }
  }

  if (getLocationConsent() === LOCATION_CONSENT_VALUES.granted) {
    requestPreciseLocation();
  }

  // Search paywall (quota / $7 / 24h) removed; keep Stripe return handling so post-checkout unlock still syncs.
  (async function initSearchUnlockFromReturn() {
    const ACCESS_URLS = {
      status: "/api/search-access",
      claim: "/api/search-access/claim",
    };
    const UNLOCK_COOKIE = "abbiey_search_unlocked";
    const UNLOCK_COOKIE_MAX_AGE = 315360000;
    let hasServerUnlock = window.__currentUserHasPaidAccess === true;

    function hasUnlockCookie() {
      try {
        return document.cookie.split(";").some((c) => {
          const t = c.trim();
          const i = t.indexOf("=");
          if (i === -1) return false;
          const name = t.slice(0, i).trim();
          const val = t.slice(i + 1).trim();
          return name === UNLOCK_COOKIE && val === "1";
        });
      } catch (_) {
        return false;
      }
    }

    function setPaidUnlockPersistence() {
      try {
        localStorage.setItem("abbiey_unlocked", "1");
      } catch (_) {}
      try {
        const secure = window.location.protocol === "https:";
        document.cookie =
          UNLOCK_COOKIE +
          "=1; path=/; max-age=" +
          UNLOCK_COOKIE_MAX_AGE +
          "; samesite=lax" +
          (secure ? "; secure" : "");
      } catch (_) {}
    }
    function applyLocalUnlock() {
      hasServerUnlock = true;
      setPaidUnlockPersistence();
    }
    async function refreshServerUnlock() {
      try {
        const result = await fetchJson(ACCESS_URLS.status);
        if (result.ok && result.data && result.data.unlocked) {
          applyLocalUnlock();
          return true;
        }
      } catch (_) {}
      return false;
    }
    async function claimReturnedUnlock() {
      var checkoutToken = "";
      try {
        checkoutToken = localStorage.getItem("abbiey_checkout_token") || "";
      } catch (_) {}
      try {
        const result = await fetchJson(ACCESS_URLS.claim, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ checkout_token: checkoutToken }),
        });
        if (result.ok && result.data && result.data.unlocked) {
          try {
            localStorage.removeItem("abbiey_checkout_token");
          } catch (_) {}
          applyLocalUnlock();
          return true;
        }
        showToast(
          userFacingApiError(result.data && result.data.message, "We couldn't sync your unlock yet. Try again from your account or email recovery."),
          "error"
        );
      } catch (_) {
        showToast("We couldn't sync your unlock yet.", "error");
      }
      return false;
    }
    if (localStorage.getItem("abbiey_unlocked") === "1" || hasUnlockCookie()) {
      try {
        localStorage.setItem("abbiey_unlocked", "1");
      } catch (_) {}
      hasServerUnlock = true;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get("unlocked") === "1" || params.get("paid") === "1") {
      var restored = await claimReturnedUnlock();
      if (!restored) {
        restored = await refreshServerUnlock();
      }
      if (!restored) {
        applyLocalUnlock();
      }
      params.delete("unlocked");
      params.delete("paid");
      const qs = params.toString();
      const nu = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
      window.history.replaceState({}, "", nu);
    } else {
      await refreshServerUnlock();
    }
    if (hasServerUnlock && typeof window !== "undefined") {
      window.__currentUserHasPaidAccess = true;
    }
  })();

  // ===== After Stripe (API keys): remember return to developer dashboard =====
  (function initApiCheckoutReturnCapture() {
    document.querySelectorAll("a.dev-stripe-btn").forEach((a) => {
      a.addEventListener(
        "click",
        () => {
          try {
            localStorage.setItem(
              "abbiey_checkout_return",
              JSON.stringify({ kind: "developer" })
            );
          } catch (_) {}
        },
        true
      );
    });
  })();

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

  // ===== Top loading progress bar =====
  (function initProgressBar() {
    const bar = document.createElement('div');
    bar.id = 'nprogress-bar';
    bar.style.cssText = 'width:0%;opacity:0';
    document.body.prepend(bar);

    function start() {
      bar.style.transition = 'none';
      bar.style.width = '0%';
      bar.style.opacity = '1';
      requestAnimationFrame(() => {
        bar.style.transition = 'width 8s cubic-bezier(.1,1,.1,1)';
        bar.style.width = '85%';
      });
    }
    function finish() {
      bar.style.transition = 'width .2s ease, opacity .3s .2s ease';
      bar.style.width = '100%';
      bar.style.opacity = '0';
    }

    const form = document.getElementById('search-form');
    if (form) form.addEventListener('submit', start);
    window.addEventListener('pageshow', finish);
  })();

  // ===== Theme toggle =====
  const toggle = document.getElementById("theme-toggle");
  const isSignedInUi = () => !!document.querySelector(".user-avatar-chip");
  function promptCustomizationAccountRequired() {
    showToast("Create an account to customize and save settings.", "error");
  }
  const saved = localStorage.getItem("theme");
  if (saved) html.setAttribute("data-theme", saved);

  if (toggle) toggle.addEventListener("click", () => {
    if (!isSignedInUi()) {
      promptCustomizationAccountRequired();
      return;
    }
    const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    try { ss("theme", next); } catch (_) {}
    const om = document.getElementById("header-overflow-menu");
    if (om) om.setAttribute("hidden", "");
  });

  // ===== Custom accent color =====
  const savedAccent = localStorage.getItem("accent-color");
  if (savedAccent) applyAccentColor(savedAccent, { persist: false });

  function applyAccentColor(color, { persist = true } = {}) {
    html.style.setProperty("--accent", color);
    // Generate a darker variant
    const dim = adjustBrightness(color, -30);
    html.style.setProperty("--accent-dim", dim);
    if (persist) {
      localStorage.setItem("accent-color", color);
      try { ss("accent", color); } catch (_) {}
    }
    // Mark active swatch
    document.querySelectorAll(".color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === color);
    });
  }

  // ===== Custom search-bar colour =====
  // Independent from --accent so users can theme the search pill without
  // dragging every other accent-tinted element along. Empty string = reset.
  const SEARCH_ACCENT_KEY = "abbiey_search_accent";
  const savedSearchAccent = localStorage.getItem(SEARCH_ACCENT_KEY) || "";
  applySearchAccent(savedSearchAccent);

  const SEARCH_INPUT_COLOR_KEY = "abbiey_search_input_color";
  const SEARCH_SURFACE_COLOR_KEY = "abbiey_search_surface_color";
  const savedSearchInputColor = localStorage.getItem(SEARCH_INPUT_COLOR_KEY) || "";
  const savedSearchSurfaceColor = localStorage.getItem(SEARCH_SURFACE_COLOR_KEY) || "";
  applySearchInputColor(savedSearchInputColor);
  applySearchSurfaceColor(savedSearchSurfaceColor);

  function applySearchAccent(color) {
    const vars = [
      "--search-accent-border",
      "--search-accent-border-hover",
      "--search-accent-focus",
      "--search-accent-ring",
      "--search-accent-focus-icon",
    ];
    if (!color) {
      vars.forEach(v => html.style.removeProperty(v));
      localStorage.removeItem(SEARCH_ACCENT_KEY);
    } else {
      // Idle border: 45% of picked colour blended onto transparent.
      html.style.setProperty("--search-accent-border", _mix(color, 0.45));
      html.style.setProperty("--search-accent-border-hover", _mix(color, 0.75));
      html.style.setProperty("--search-accent-focus", color);
      html.style.setProperty("--search-accent-ring", _mix(color, 0.22));
      html.style.setProperty("--search-accent-focus-icon", _mix(color, 1.0, true));
      localStorage.setItem(SEARCH_ACCENT_KEY, color);
    }
    document.querySelectorAll(".search-color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === color);
    });
  }

  function applySearchInputColor(color) {
    const c = String(color || "").trim();
    if (!c) {
      html.style.removeProperty("--search-input-color");
      localStorage.removeItem(SEARCH_INPUT_COLOR_KEY);
      return;
    }
    html.style.setProperty("--search-input-color", c);
    localStorage.setItem(SEARCH_INPUT_COLOR_KEY, c);
  }

  function applySearchSurfaceColor(color) {
    const c = String(color || "").trim();
    if (!c) {
      html.style.removeProperty("--search-surface");
      html.style.removeProperty("--search-surface-focus");
      localStorage.removeItem(SEARCH_SURFACE_COLOR_KEY);
      return;
    }
    html.style.setProperty("--search-surface", c);
    html.style.setProperty("--search-surface-focus", c);
    localStorage.setItem(SEARCH_SURFACE_COLOR_KEY, c);
  }

  function _mix(hex, alpha, brighten) {
    const h = String(hex || "").replace("#", "");
    if (h.length !== 6) return hex;
    let r = parseInt(h.slice(0, 2), 16);
    let g = parseInt(h.slice(2, 4), 16);
    let b = parseInt(h.slice(4, 6), 16);
    if (brighten) {
      r = Math.min(255, Math.round(r + (255 - r) * 0.35));
      g = Math.min(255, Math.round(g + (255 - g) * 0.35));
      b = Math.min(255, Math.round(b + (255 - b) * 0.35));
      return `rgb(${r}, ${g}, ${b})`;
    }
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function adjustBrightness(hex, amount) {
    hex = hex.replace("#", "");
    const r = Math.max(0, Math.min(255, parseInt(hex.slice(0, 2), 16) + amount));
    const g = Math.max(0, Math.min(255, parseInt(hex.slice(2, 4), 16) + amount));
    const b = Math.max(0, Math.min(255, parseInt(hex.slice(4, 6), 16) + amount));
    return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
  }

  // Wrap URL paths in a span so CSS can hide just the path, leaving the domain visible
  function applyDomainUrlStyle() {
    document.querySelectorAll("cite.result-url").forEach(el => {
      if (el.dataset.urlProcessed) return;
      el.dataset.urlProcessed = "1";
      const raw = el.textContent.trim();
      try {
        const u = new URL(raw.startsWith("http") ? raw : "https://" + raw);
        const domain = u.protocol + "//" + u.host;
        const path   = u.pathname + u.search + u.hash;
        if (path && path !== "/") {
          el.innerHTML = "";
          el.appendChild(document.createTextNode(domain));
          const pathSpan = document.createElement("span");
          pathSpan.className = "result-url-path";
          pathSpan.textContent = path;
          el.appendChild(pathSpan);
        }
      } catch {}
    });
  }

  // Theme settings popover
  // ===== Settings Modal =====
  const _S = {
    theme:         { key: "theme",                 def: "dark"    },
    accent:        { key: "accent-color",          def: "#e7e5e4" },
    searchAccent:  { key: "abbiey_search_accent",  def: ""        },
    searchInputColor:   { key: "abbiey_search_input_color",   def: "" },
    searchSurfaceColor: { key: "abbiey_search_surface_color", def: "" },
    density:       { key: "density",               def: "default" },
    fontSize:      { key: "abbiey_font_size",      def: "medium"  },
    fontFamily:    { key: "abbiey_font_family",    def: "system"  },
    safesearch:    { key: "abbiey_safesearch",     def: "off"     },
    newTab:        { key: "abbiey_new_tab",        def: "true"    },
    defaultTab:    { key: "abbiey_default_tab",    def: "text"    },
    aiSummary:     { key: "abbiey_ai_summary",     def: "true"    },
    autocomplete:  { key: "abbiey_autocomplete",   def: "true"    },
    persistRegion: { key: "abbiey_region_persist", def: "false"   },
    history:       { key: "abbiey_history",        def: "false"   },
    incognito:     { key: "abbiey_incognito",      def: "false"   },
    showCards:     { key: "abbiey_show_cards",     def: "true"    },
    showFavicons:  { key: "abbiey_show_favicons",  def: "true"    },
    showDates:     { key: "abbiey_show_dates",     def: "true"    },
    // New customisation settings
    radius:        { key: "abbiey_radius",         def: "default" },
    motion:        { key: "abbiey_motion",         def: "full"    },
    width:         { key: "abbiey_width",          def: "default" },
    urlStyle:      { key: "abbiey_url_style",      def: "full"    },
    snippetStyle:  { key: "abbiey_snippet_style",  def: "full"    },
    searchBar:     { key: "abbiey_searchbar",      def: "default" },
    hoverPreview:  { key: "abbiey_hover_preview",  def: "true"    },
  };
  const _ACCOUNT_CUSTOM_SETTINGS = new Set([
    "theme", "accent", "searchAccent", "searchInputColor", "searchSurfaceColor",
    "density", "fontSize", "fontFamily", "radius", "motion", "width",
    "urlStyle", "snippetStyle", "searchBar",
  ]);
  let _accountSettingsHydrating = false;
  let _accountSettingsSaveTimer = 0;
  function _isAccountLockedSetting(name) {
    return _ACCOUNT_CUSTOM_SETTINGS.has(name);
  }
  function gs(name) {
    if (_isAccountLockedSetting(name) && !isSignedInUi()) return _S[name].def;
    return localStorage.getItem(_S[name].key) ?? _S[name].def;
  }
  function _queueSaveAccountCustomizationSettings() {
    if (!isSignedInUi() || _accountSettingsHydrating) return;
    if (_accountSettingsSaveTimer) window.clearTimeout(_accountSettingsSaveTimer);
    _accountSettingsSaveTimer = window.setTimeout(async () => {
      const settings = {};
      _ACCOUNT_CUSTOM_SETTINGS.forEach((name) => {
        settings[name] = localStorage.getItem(_S[name].key) ?? _S[name].def;
      });
      await fetchJson("/api/user/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings }),
      });
    }, 300);
  }
  function ss(name, val) {
    if (_isAccountLockedSetting(name) && !isSignedInUi()) {
      promptCustomizationAccountRequired();
      return false;
    }
    localStorage.setItem(_S[name].key, val);
    if (_isAccountLockedSetting(name)) _queueSaveAccountCustomizationSettings();
    return true;
  }

  async function loadAccountCustomizationSettings() {
    if (!isSignedInUi()) return;
    const resp = await fetchJson("/api/user/settings");
    if (!resp.ok || !resp.data || typeof resp.data.settings !== "object") return;
    _accountSettingsHydrating = true;
    try {
      const incoming = resp.data.settings;
      _ACCOUNT_CUSTOM_SETTINGS.forEach((name) => {
        const raw = incoming[name];
        if (typeof raw !== "string") return;
        localStorage.setItem(_S[name].key, raw);
      });
    } finally {
      _accountSettingsHydrating = false;
    }
    applyAllSettings();
    syncSettingsUI();
  }
  function clearStoredSearchHistory(includeServer = false) {
    try { sessionStorage.removeItem("abbiey_search_history"); } catch {}
    try { localStorage.removeItem("abbiey_search_history"); } catch {}
    if (includeServer && document.querySelector(".user-avatar-chip")) {
      fetch("/api/user/history", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ clear_all: true }),
      }).catch(() => {});
    }
  }

  // Apply all settings on load
  function applyAllSettings() {
    html.setAttribute("data-theme", gs("theme"));
    applyAccentColor(gs("accent"), { persist: false });

    // Font size â€” change html font-size so rem units scale
    const fsMap = { small: "13.5px", medium: "", large: "17.5px", xl: "20px" };
    const fs = gs("fontSize");
    html.style.fontSize = fsMap[fs] || "";
    html.setAttribute("data-font-size", fs);

    // Font family
    const ffMap = {
      system: "",
      serif:  "Georgia, 'Times New Roman', serif",
      mono:   "ui-monospace, Consolas, monospace",
    };
    html.setAttribute("data-font", gs("fontFamily"));
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

    // AI summary + answer layer
    const aiCard = document.getElementById("ai-summary-card");
    if (aiCard && gs("aiSummary") === "false") aiCard.style.display = "none";
    const answerLayerCard = document.getElementById("answer-layer-card");
    if (answerLayerCard && gs("aiSummary") === "false") answerLayerCard.style.display = "none";

    // Answer cards
    if (gs("showCards") === "false") {
      [".calculator-card",".color-card",".unit-convert-card",".knowledge-panel",
       ".weather-card",".dictionary-card",".qr-card",".knowledge-graph-root"].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => { el.style.display = "none"; });
      });
    } else {
      document.querySelectorAll(".knowledge-graph-root").forEach(el => { el.style.display = ""; });
    }

    const _incBadge = document.getElementById("incognito-badge");
    if (_incBadge) _incBadge.hidden = gs("incognito") !== "true";

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
    } else {
      const detectedRegion = detectSearchRegion();
      const detectedLang = searchLangForRegion(detectedRegion);
      const rInput = document.getElementById("region-input");
      const rSelect = document.getElementById("region-select");
      const langInput = document.getElementById("lang-input");
      if (detectedRegion && rInput && !rInput.value) {
        rInput.value = detectedRegion;
      }
      if (detectedRegion && rSelect && !rSelect.value) {
        rSelect.value = detectedRegion;
      }
      if (detectedLang && langInput && !langInput.value) {
        langInput.value = detectedLang;
      }
    }

    const _LP = {
      previewW: "abbiey_preview_panel_w",
      previewDocked: "abbiey_preview_docked",
      chatW: "abbiey_chat_w",
      chatH: "abbiey_chat_h",
    };
    const _pw = localStorage.getItem(_LP.previewW);
    if (_pw) {
      const n = parseInt(_pw, 10);
      if (!Number.isNaN(n) && n >= 240 && n <= 560) {
        html.style.setProperty("--preview-panel-width", `${n}px`);
      }
    }
    const _cw = localStorage.getItem(_LP.chatW);
    if (_cw) {
      const n = parseInt(_cw, 10);
      if (!Number.isNaN(n) && n >= 280 && n <= 520) {
        html.style.setProperty("--chat-panel-width", `${n}px`);
      }
    }
    const _ch = localStorage.getItem(_LP.chatH);
    const _chatEl = document.getElementById("chat-panel");
    if (_ch && _chatEl) {
      const n = parseInt(_ch, 10);
      if (!Number.isNaN(n) && n >= 220 && n <= 720) {
        html.style.setProperty("--chat-panel-height", `${n}px`);
        _chatEl.classList.add("chat-user-sized");
      }
    }
    const _appL = document.querySelector(".app-layout");
    if (localStorage.getItem(_LP.previewDocked) === "1" && _appL) {
      _appL.classList.add("preview-docked-hidden");
      const _prt = document.getElementById("preview-restore-tab");
      if (_prt) _prt.hidden = false;
    }

    if (sessionStorage.getItem("abbiey_ai_summary_session_hide") === "1") {
      const _aic = document.getElementById("ai-summary-card");
      if (_aic && gs("aiSummary") === "true") {
        _aic.style.display = "none";
        const _air = document.getElementById("ai-summary-restore-wrap");
        if (_air) _air.hidden = false;
      }
    }
    if (sessionStorage.getItem("abbiey_answer_layer_session_hide") === "1") {
      const _alc = document.getElementById("answer-layer-card");
      if (_alc && gs("aiSummary") === "true") {
        _alc.style.display = "none";
        const _alr = document.getElementById("answer-layer-restore-wrap");
        if (_alr) _alr.hidden = false;
      }
    }

    // Corner radius
    const _radius = gs("radius");
    if (_radius !== "default") html.setAttribute("data-radius", _radius);

    // Animation speed
    const _motion = gs("motion");
    if (_motion !== "full") html.setAttribute("data-motion", _motion);

    // Results width
    const _width = gs("width");
    if (_width !== "default") html.setAttribute("data-width", _width);

    // URL display
    const _urlStyle = gs("urlStyle");
    if (_urlStyle !== "full") {
      html.setAttribute("data-url-style", _urlStyle);
      if (_urlStyle === "domain") applyDomainUrlStyle();
    }

    // Snippet style
    const _snippetStyle = gs("snippetStyle");
    if (_snippetStyle !== "full") html.setAttribute("data-snippet-style", _snippetStyle);

    // Search bar style
    const _searchBar = gs("searchBar");
    if (_searchBar !== "default") html.setAttribute("data-searchbar", _searchBar);

    // Search bar colours
    applySearchAccent(gs("searchAccent"));
    applySearchInputColor(gs("searchInputColor"));
    applySearchSurfaceColor(gs("searchSurfaceColor"));
  }

  applyAllSettings();
  loadAccountCustomizationSettings();

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
      const om = document.getElementById("header-overflow-menu");
      if (om) om.setAttribute("hidden", "");
    });
    densityBtn.title = `Density: ${savedDensity}`;
  }

  // ===== Open / close settings modal =====
  const settingsBtn = document.getElementById("theme-settings-btn");
  const settingsOverlay = document.getElementById("settings-overlay");
  const settingsClose = document.getElementById("settings-close");
  let settingsReturnFocus = null;

  function applyCustomizationLockUi() {
    if (isSignedInUi()) return;
    const section = document.querySelector(".settings-section-account-custom");
    if (!section) return;
    section.classList.add("settings-locked");
    section.querySelectorAll("button, input, select, textarea").forEach((el) => {
      if (el.closest(".settings-account-cta")) return;
      el.disabled = true;
      el.setAttribute("aria-disabled", "true");
    });
  }
  applyCustomizationLockUi();

  function openSettings(trigger = settingsBtn) {
    settingsReturnFocus = rememberFocus(trigger);
    document.body.style.overflow = "hidden";
    settingsOverlay.removeAttribute("hidden");
    syncSettingsUI();
    afterMotion(0, () => restoreFocus(settingsClose));
  }
  function closeSettings({ restore = true } = {}) {
    if (!settingsOverlay || settingsOverlay.hasAttribute("hidden")) return;
    settingsOverlay.classList.add("closing");
    afterMotion(140, () => {
      settingsOverlay.setAttribute("hidden", "");
      settingsOverlay.classList.remove("closing");
      document.body.style.overflow = "";
      if (restore) restoreFocus(settingsReturnFocus);
      settingsReturnFocus = null;
    });
  }

  if (settingsBtn) settingsBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!isSignedInUi()) {
      promptCustomizationAccountRequired();
    }
    openSettings(e.currentTarget);
  });
  if (settingsClose) settingsClose.addEventListener("click", closeSettings);
  if (settingsOverlay) {
    settingsOverlay.addEventListener("click", (e) => { if (e.target === settingsOverlay) closeSettings(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !settingsOverlay.hasAttribute("hidden")) closeSettings(); });
  }

  // ===== Header overflow dropdown (search page + base layout) =====
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

    // Make entire rows clickable (for Settings, Theme, Density, etc.)
    const overflowRows = overflowMenu.querySelectorAll(".overflow-menu-row");
    overflowRows.forEach(row => {
      // Add pointer cursor so it feels clickable
      row.style.cursor = "pointer";
      row.addEventListener("click", (e) => {
        // If they actually clicked the interactive element inside, don't double trigger
        const interactive = row.querySelector("button, select, input, a");
        if (!interactive || e.target === interactive || interactive.contains(e.target)) return;

        // For selects, focus or showPicker if available
        if (interactive.tagName === "SELECT") {
          try {
            if (typeof interactive.showPicker === "function") {
              interactive.showPicker();
            } else {
              interactive.focus();
            }
          } catch (err) {
            interactive.focus();
          }
        }
        // For buttons/anchors, mock click
        else if (typeof interactive.click === "function") {
          interactive.click();
        }
      });
    });
  }

  // ===== Tab More dropdown =====
  (function initTabMore() {
    const btn = document.getElementById("tab-more-btn");
    const menu = document.getElementById("tab-more-menu");
    if (!btn || !menu) return;
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const isOpen = !menu.hasAttribute("hidden");
      if (isOpen) {
        menu.setAttribute("hidden", "");
        btn.setAttribute("aria-expanded", "false");
      } else {
        menu.removeAttribute("hidden");
        btn.setAttribute("aria-expanded", "true");
      }
    });
    document.addEventListener("click", (e) => {
      if (menu.hasAttribute("hidden")) return;
      if (btn.contains(e.target) || menu.contains(e.target)) return;
      menu.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", "false");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { menu.setAttribute("hidden", ""); btn.setAttribute("aria-expanded", "false"); }
    });

    fetch("/api/user/search-bots", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d || !Array.isArray(d.bots) || !d.bots.length) return;
        const qEl = document.getElementById("search-input") || document.querySelector('input[name="q"]');
        const q = (qEl && qEl.value) ? qEl.value.trim() : "";
        const sub = document.createElement("div");
        sub.className = "tab-more-mybot-sub";
        sub.setAttribute("role", "group");
        sub.setAttribute("aria-label", "Your custom search bots");
        const cap = document.createElement("span");
        cap.className = "tab-more-subcap";
        cap.textContent = "Your bots";
        sub.appendChild(cap);
        d.bots.forEach((b) => {
          const a = document.createElement("a");
          a.className = "tab-more-item tab-more-mybot-item";
          const p = new URLSearchParams();
          p.set("type", "mybot");
          p.set("bot_id", String(b.id));
          if (q) p.set("q", q);
          a.href = `/search?${p.toString()}`;
          a.textContent = b.name || `Bot ${b.id}`;
          sub.appendChild(a);
        });
        menu.appendChild(sub);
      })
      .catch(() => {});
  })();

  // ===== Filters toggle =====
  (function initFilterMore() {
    const btn = document.getElementById("filter-more-btn");
    const extras = document.getElementById("filter-extras");
    if (!btn || !extras) return;
    btn.addEventListener("click", () => {
      const open = extras.hasAttribute("hidden");
      extras[open ? "removeAttribute" : "setAttribute"]("hidden", "");
      btn.setAttribute("aria-expanded", String(open));
      if (open) {
        const firstInput = extras.querySelector("input, button");
        if (firstInput) firstInput.focus();
      }
    });
  })();

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
    syncBtnGroup("radius-group",       gs("radius"));
    syncBtnGroup("motion-group",       gs("motion"));
    syncBtnGroup("width-group",        gs("width"));
    syncBtnGroup("url-style-group",    gs("urlStyle"));
    syncBtnGroup("snippet-style-group",gs("snippetStyle"));
    syncBtnGroup("searchbar-group",    gs("searchBar"));
    syncToggle("ai-summary-toggle",    gs("aiSummary")     === "true");
    syncToggle("autocomplete-toggle",  gs("autocomplete")  === "true");
    syncToggle("persist-region-toggle",gs("persistRegion") === "true");
    syncToggle("location-consent-toggle", getLocationConsent() === LOCATION_CONSENT_VALUES.granted);
    syncToggle("history-toggle",       gs("history")       === "true");
    syncToggle("incognito-toggle",     gs("incognito")     === "true");
    syncToggle("cards-toggle",         gs("showCards")     === "true");
    syncToggle("favicons-toggle",      gs("showFavicons")  === "true");
    syncToggle("dates-toggle",         gs("showDates")     === "true");
    syncToggle("hover-preview-toggle", gs("hoverPreview")  === "true");
    const regionSelectModal = document.getElementById("region-select-modal");
    const regionInput = document.getElementById("region-input");
    if (regionSelectModal && regionInput) {
      regionSelectModal.value = regionInput.value || "";
    }
    const cc = document.getElementById("custom-color");
    if (cc) cc.value = gs("accent");
    const sic = document.getElementById("search-input-color");
    if (sic) sic.value = gs("searchInputColor") || "#111827";
    const ssc = document.getElementById("search-surface-color");
    if (ssc) ssc.value = gs("searchSurfaceColor") || "#ffffff";
    // mark active swatch
    document.querySelectorAll(".color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === gs("accent"));
    });
    document.querySelectorAll(".search-color-swatch").forEach(s => {
      s.classList.toggle("active", s.dataset.color === gs("searchAccent"));
    });
  }

  // ===== Wire segmented button groups =====
  function wireBtnGroup(groupId, settingName, onChange) {
    const g = document.getElementById(groupId);
    if (!g) return;
    g.querySelectorAll(".settings-seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        if (!ss(settingName, btn.dataset.val)) return;
        syncBtnGroup(groupId, btn.dataset.val);
        if (onChange) onChange(btn.dataset.val);
      });
    });
  }
  function wireToggle(id, settingName, onChange) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      if (!ss(settingName, el.checked ? "true" : "false")) {
        el.checked = gs(settingName) === "true";
        return;
      }
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
    const m = { system: "", serif: "Georgia,'Times New Roman',serif", mono: "ui-monospace,Consolas,monospace" };
    document.body.style.fontFamily = m[val] || "";
    html.setAttribute("data-font", val);
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
  wireBtnGroup("radius-group", "radius", (val) => {
    html.setAttribute("data-radius", val);
  });
  wireBtnGroup("motion-group", "motion", (val) => {
    html.setAttribute("data-motion", val);
  });
  wireBtnGroup("width-group", "width", (val) => {
    html.setAttribute("data-width", val);
  });
  wireBtnGroup("url-style-group", "urlStyle", (val) => {
    html.setAttribute("data-url-style", val);
    if (val === "domain") applyDomainUrlStyle();
  });
  wireBtnGroup("snippet-style-group", "snippetStyle", (val) => {
    html.setAttribute("data-snippet-style", val);
  });
  wireBtnGroup("searchbar-group", "searchBar", (val) => {
    html.setAttribute("data-searchbar", val);
  });

  wireToggle("ai-summary-toggle", "aiSummary", (checked) => {
    const c = document.getElementById("ai-summary-card");
    if (c) c.style.display = checked ? "" : "none";
    const w = document.getElementById("ai-summary-restore-wrap");
    if (w) w.hidden = true;
    const alc = document.getElementById("answer-layer-card");
    if (alc) alc.style.display = checked ? "" : "none";
    const alw = document.getElementById("answer-layer-restore-wrap");
    if (alw) alw.hidden = true;
    if (checked) {
      sessionStorage.removeItem("abbiey_ai_summary_session_hide");
      sessionStorage.removeItem("abbiey_answer_layer_session_hide");
    }
  });
  wireToggle("autocomplete-toggle", "autocomplete", null);
  wireToggle("persist-region-toggle", "persistRegion", null);
  const locationConsentToggle = document.getElementById("location-consent-toggle");
  if (locationConsentToggle) {
    locationConsentToggle.addEventListener("change", async () => {
      if (locationConsentToggle.checked) {
        setLocationConsent(LOCATION_CONSENT_VALUES.granted);
        const granted = await requestPreciseLocation();
        if (!granted && pageUsesPreciseLocation()) {
          setLocationConsent(LOCATION_CONSENT_VALUES.denied);
          showToast("Location access was not granted. Nearby results will keep using your region setting.", "error");
        }
      } else {
        setLocationConsent(LOCATION_CONSENT_VALUES.denied);
      }
      syncToggle("location-consent-toggle", getLocationConsent() === LOCATION_CONSENT_VALUES.granted);
    });
  }
  wireToggle("history-toggle", "history", (checked) => {
    if (!checked) {
      clearStoredSearchHistory(true);
      document.getElementById("history-panel")?.setAttribute("hidden", "");
    }
  });
  wireToggle("incognito-toggle", "incognito", (checked) => {
    const badge = document.getElementById("incognito-badge");
    if (badge) badge.hidden = !checked;
    if (checked) clearStoredSearchHistory(false);
  });
  wireToggle("cards-toggle", "showCards", (checked) => {
    [".calculator-card",".color-card",".unit-convert-card",".knowledge-panel",
     ".weather-card",".dictionary-card",".qr-card",".knowledge-graph-root"].forEach(sel => {
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
  wireToggle("hover-preview-toggle", "hoverPreview", null);
  if (gs("history") !== "true") clearStoredSearchHistory();

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

  // ===== Search-bar colour (in settings modal) =====
  document.querySelectorAll(".search-color-swatch").forEach(swatch => {
    swatch.addEventListener("click", () => {
      const c = swatch.dataset.color || "";
      applySearchAccent(c);
      ss("searchAccent", c);
      const sc = document.getElementById("search-custom-color");
      if (sc && c) sc.value = c;
    });
  });
  const searchCustomColor = document.getElementById("search-custom-color");
  if (searchCustomColor) {
    if (gs("searchAccent")) searchCustomColor.value = gs("searchAccent");
    searchCustomColor.addEventListener("input", () => {
      applySearchAccent(searchCustomColor.value);
      ss("searchAccent", searchCustomColor.value);
    });
  }
  const searchInputColor = document.getElementById("search-input-color");
  if (searchInputColor) {
    if (gs("searchInputColor")) searchInputColor.value = gs("searchInputColor");
    searchInputColor.addEventListener("input", () => {
      applySearchInputColor(searchInputColor.value);
      ss("searchInputColor", searchInputColor.value);
    });
  }
  const searchSurfaceColor = document.getElementById("search-surface-color");
  if (searchSurfaceColor) {
    if (gs("searchSurfaceColor")) searchSurfaceColor.value = gs("searchSurfaceColor");
    searchSurfaceColor.addEventListener("input", () => {
      applySearchSurfaceColor(searchSurfaceColor.value);
      ss("searchSurfaceColor", searchSurfaceColor.value);
    });
  }

  // ===== History panel (Settings â†’ Privacy) =====
  (function () {
    const HISTORY_KEY_PANEL = "abbiey_search_history";
    const CLOCK_SVG = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;

    function panelGetHistory() {
      if (gs("history") !== "true" || gs("incognito") === "true") return [];
      try { localStorage.removeItem(HISTORY_KEY_PANEL); } catch {}
      try { return JSON.parse(sessionStorage.getItem(HISTORY_KEY_PANEL)) || []; } catch { return []; }
    }
    function isLoggedInUi() {
      return !!document.querySelector(".user-avatar-chip");
    }
    /** Server-first order, then local-only queries (logged-in); else localStorage only. */
    async function panelHistoryQueries() {
      if (gs("history") !== "true" || gs("incognito") === "true") return [];
      const local = panelGetHistory();
      if (!isLoggedInUi()) return local;
      try {
        const result = await fetchJson("/api/user/history");
        if (!result.ok || !result.data || !Array.isArray(result.data.history)) return local;
        const fromServer = result.data.history.map(h => (h && h.query ? String(h.query).trim() : "")).filter(Boolean);
        const seen = new Set(fromServer);
        const merged = [...fromServer];
        for (const q of local) {
          if (q && !seen.has(q)) {
            seen.add(q);
            merged.push(q);
          }
        }
        return merged.slice(0, 50);
      } catch {
        return local;
      }
    }
    function panelRemove(term) {
      const items = panelGetHistory().filter(i => i !== term);
      try { sessionStorage.setItem(HISTORY_KEY_PANEL, JSON.stringify(items)); } catch {}
      if (isLoggedInUi()) {
        fetch("/api/user/history", {
          method: "DELETE", headers: { "Content-Type": "application/json" },
          credentials: "same-origin", body: JSON.stringify({ query: term }),
        }).catch(() => {});
      }
    }
    function panelClearAll() {
      clearStoredSearchHistory(true);
    }

    async function renderPanel() {
      const list = document.getElementById("history-panel-list");
      if (!list) return;
      list.innerHTML = `<div class="history-panel-empty">Loadingâ€¦</div>`;
      const items = await panelHistoryQueries();
      if (!items.length) {
        list.innerHTML = gs("incognito") === "true"
          ? `<div class="history-panel-empty">Incognito is on â€” new searches are not saved. Turn it off in Settings to build history again.</div>`
          : `<div class="history-panel-empty">No recent searches</div>`;
        return;
      }
      list.innerHTML = items.map((text, i) =>
        `<div class="history-panel-item" data-idx="${i}">` +
        `<span class="history-panel-item-icon">${CLOCK_SVG}</span>` +
        `<span class="history-panel-item-text" data-term="${esc(text)}">${esc(text)}</span>` +
        `<button class="history-panel-item-del" data-del="${esc(text)}" title="Remove" aria-label="Remove ${esc(text)}" type="button">${CLOSE_ICON_SVG}</button>` +
        `</div>`
      ).join("");

      list.querySelectorAll(".history-panel-item-text").forEach(el => {
        el.addEventListener("click", () => {
          const q = el.getAttribute("data-term");
          const searchInput = document.getElementById("search-input") || document.querySelector("input[name='q']");
          if (searchInput) { searchInput.value = q; }
          document.querySelector(".settings-overlay")?.classList.remove("open");
          const sf = document.getElementById("main-search-form") || document.querySelector("form[action*='search']");
          if (sf) sf.submit();
        });
      });
      list.querySelectorAll(".history-panel-item-del").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          panelRemove(btn.getAttribute("data-del"));
          void renderPanel();
        });
      });
    }

    const viewHistBtn = document.getElementById("view-history-btn");
    const histPanel = document.getElementById("history-panel");
    const histPanelClose = document.getElementById("history-panel-close");
    let historyReturnFocus = null;

    function closeHistoryPanel({ restore = true } = {}) {
      if (!histPanel) return;
      histPanel.hidden = true;
      if (viewHistBtn) viewHistBtn.textContent = "View";
      if (restore) restoreFocus(historyReturnFocus || viewHistBtn);
      historyReturnFocus = null;
    }

    if (viewHistBtn && histPanel) {
      viewHistBtn.addEventListener("click", () => {
        const isHidden = histPanel.hidden;
        if (!isHidden) { closeHistoryPanel({ restore: false }); return; }
        historyReturnFocus = rememberFocus(viewHistBtn);
        histPanel.hidden = false;
        viewHistBtn.textContent = "Hide";
        void renderPanel();
        afterMotion(0, () => restoreFocus(histPanelClose));
      });
    }
    if (histPanelClose && histPanel) {
      histPanelClose.addEventListener("click", () => closeHistoryPanel());
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && histPanel && !histPanel.hidden) {
        closeHistoryPanel();
      }
    });

    // ===== Clear buttons =====
    const clearHistBtn = document.getElementById("clear-history-btn");
    if (clearHistBtn) {
      clearHistBtn.addEventListener("click", () => {
        panelClearAll();
        closeHistoryPanel({ restore: false });
        clearHistBtn.textContent = "Cleared!";
        afterMotion(1500, () => { clearHistBtn.textContent = "Clear all"; });
      });
    }
  }());

  const exportBookmarksBtn = document.getElementById("export-bookmarks-btn");
  if (exportBookmarksBtn) {
    exportBookmarksBtn.addEventListener("click", () => {
      const items = getBookmarks();
      if (!items.length) { showToast("No bookmarks to export.", "error"); return; }
      const json = JSON.stringify(items, null, 2);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `abbiey-bookmarks-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
      showToast(`Exported ${items.length} bookmark${items.length !== 1 ? "s" : ""}.`);
    });
  }

  const importBookmarksInput = document.getElementById("import-bookmarks-input");
  if (importBookmarksInput) {
    importBookmarksInput.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const parsed = JSON.parse(ev.target.result);
          if (!Array.isArray(parsed)) { showToast("Invalid bookmark file.", "error"); return; }
          const valid = parsed.filter(b => b && typeof b.url === "string" && b.url.startsWith("http"));
          if (!valid.length) { showToast("No valid bookmarks found in file.", "error"); return; }
          const current = getBookmarks();
          const merged = mergeBookmarks(current, valid);
          saveBookmarks(merged);
          updateBookmarkBadge();
          const added = merged.length - current.length;
          showToast(added > 0 ? `Imported ${added} bookmark${added !== 1 ? "s" : ""}.` : "All bookmarks already saved.");
        } catch {
          showToast("Could not parse bookmark file.", "error");
        }
        importBookmarksInput.value = "";
      };
      reader.readAsText(file);
    });
  }
  const clearAllBtn = document.getElementById("clear-all-btn");
  if (clearAllBtn) {
    clearAllBtn.addEventListener("click", () => {
      if (
        !confirm(
          "Reset all data? This clears history, bookmarks and settings. Your one-time search unlock (if you purchased it) stays active on this browser."
        )
      )
        return;
      const paidSearchUnlock = localStorage.getItem("abbiey_unlocked");
      localStorage.clear();
      if (paidSearchUnlock === "1") {
        try {
          localStorage.setItem("abbiey_unlocked", "1");
        } catch (_) {}
      }
      clearClientCookie("abbiey_welcome_seen");
      clearClientPref(TERMS_CONSENT_KEY);
      clearClientPref(LOCATION_CONSENT_KEY);
      clearStoredGeoCoordinates();
      location.reload();
    });
  }

  const resetLayoutBtn = document.getElementById("reset-layout-btn");
  if (resetLayoutBtn) {
    resetLayoutBtn.addEventListener("click", () => {
      ["abbiey_preview_panel_w", "abbiey_preview_docked", "abbiey_chat_w", "abbiey_chat_h"].forEach((k) => {
        localStorage.removeItem(k);
      });
      html.style.removeProperty("--preview-panel-width");
      html.style.removeProperty("--chat-panel-width");
      html.style.removeProperty("--chat-panel-height");
      document.querySelector(".app-layout")?.classList.remove("preview-docked-hidden");
      const pr = document.getElementById("preview-restore-tab");
      if (pr) pr.hidden = true;
      document.getElementById("chat-panel")?.classList.remove("chat-user-sized");
      const g = document.getElementById("layout-gutter-preview");
      if (g) g.setAttribute("aria-valuenow", "340");
      resetLayoutBtn.textContent = "Reset!";
      setTimeout(() => { resetLayoutBtn.textContent = "Reset sizes & preview column"; }, 1500);
    });
  }

  // ===== Region selector =====
  const regionSelect = document.getElementById("region-select");
  const regionInput = document.getElementById("region-input");
  function applyRegion(val) {
    if (regionInput) regionInput.value = val;
    if (regionSelect) regionSelect.value = val;
    const langInput = document.getElementById("lang-input");
    if (langInput) {
      const parts = val.split("-");
      langInput.value = parts.length > 1 ? parts[1] : "";
    }
    if (gs("persistRegion") === "true") {
      localStorage.setItem("abbiey_region", val);
    }
  }
  if (regionSelect && regionInput) {
    regionSelect.addEventListener("change", () => {
      applyRegion(regionSelect.value);
      const om = document.getElementById("header-overflow-menu");
      if (om) om.setAttribute("hidden", "");
      const q = document.getElementById("search-input");
      if (q && q.value.trim()) document.getElementById("search-form").submit();
    });
  }
  // Sync settings modal region select
  const regionSelectModal = document.getElementById("region-select-modal");
  if (regionSelectModal) {
    if (regionInput) regionSelectModal.value = regionInput.value || "";
    regionSelectModal.addEventListener("change", () => {
      applyRegion(regionSelectModal.value);
      const q = document.getElementById("search-input");
      if (q && q.value.trim()) document.getElementById("search-form").submit();
    });
  }

  // ===== Header positioning popover =====
  const privacyBadge = document.getElementById("privacy-badge");
  const privacyPopover = document.getElementById("privacy-popover");
  const privacyPopoverClose = document.getElementById("privacy-popover-close");
  let hidePrivacyPopoverFn = null;
  if (privacyBadge && privacyPopover) {
    let privacyPopoverReturnFocus = null;
    const hidePrivacyPopover = ({ restore = true } = {}) => {
      privacyBadge.setAttribute("aria-expanded", "false");
      privacyPopover.classList.add("closing");
      afterMotion(150, () => {
        privacyPopover.classList.remove("open", "closing");
        if (restore) restoreFocus(privacyPopoverReturnFocus || privacyBadge);
        privacyPopoverReturnFocus = null;
      });
    };
    hidePrivacyPopoverFn = hidePrivacyPopover;
    privacyBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      const overflowMenu = document.getElementById("header-overflow-menu");
      if (overflowMenu && !overflowMenu.hasAttribute("hidden")) {
        overflowMenu.setAttribute("hidden", "");
      }
      if (privacyPopover.classList.contains("open")) {
        hidePrivacyPopover({ restore: false });
      } else {
        privacyPopoverReturnFocus = rememberFocus(e.currentTarget);
        privacyBadge.setAttribute("aria-expanded", "true");
        privacyPopover.classList.add("open");
        afterMotion(0, () => restoreFocus(privacyPopoverClose));
      }
    });
    if (privacyPopoverClose) {
      privacyPopoverClose.addEventListener("click", hidePrivacyPopover);
    }
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && privacyPopover.classList.contains("open")) {
        hidePrivacyPopover();
      }
    });
  }

  // ===== Answer layer + AI Summary async fetch (text tab, page 1 only) =====
  const aiCard = document.getElementById("ai-summary-card");
  const aiBody = document.getElementById("ai-summary-body");
  const aiSources = document.getElementById("ai-summary-sources");
  const layerCard = document.getElementById("answer-layer-card");
  const layerBody = document.getElementById("answer-layer-body");
  const layerSources = document.getElementById("answer-layer-sources");
  const layerRestoreWrap = document.getElementById("answer-layer-restore-wrap");
  const layerRestoreBtn = document.getElementById("answer-layer-restore-tab");

  function formatSynthesisParagraphs(text) {
    const raw = (text || "").trim();
    if (!raw) return "";
    return raw
      .split(/\n\n+/)
      .map((p) => p.trim())
      .filter(Boolean)
      .map((p) => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  function sourceRefLink(sources, idx1) {
    const s = sources && sources[idx1 - 1];
    if (!s || !s.url || !/^https?:\/\//i.test(s.url)) {
      return `<span class="answer-layer-src-num">[${idx1}]</span>`;
    }
    return `<a class="answer-layer-src-num ai-citation" href="${esc(s.url)}" target="_blank" rel="noopener">[${idx1}]</a>`;
  }

  function sourceIndicesHtml(sources, indices) {
    if (!indices || !indices.length) return "";
    return indices.map((i) => sourceRefLink(sources, i)).join(" ");
  }

  function renderAnswerLayer(data) {
    if (!layerBody || !layerSources) return;
    const src = data.sources || [];
    const headline = (data.headline || "").trim();
    const headHtml = headline ? `<h3 class="answer-layer-headline">${esc(headline)}</h3>` : "";
    const synthHtml = formatSynthesisParagraphs(data.synthesis || "");
    let claimsHtml = "";
    (data.claims || []).forEach((c) => {
      let cnum = Number(c.confidence);
      if (!Number.isFinite(cnum)) cnum = 0.65;
      const pct = Math.round(Math.max(0, Math.min(1, cnum)) * 100);
      const w = Math.max(0, Math.min(100, pct));
      const idxs = c.source_indices || [];
      claimsHtml +=
        `<div class="answer-layer-claim">` +
        `<div class="answer-layer-claim-row">` +
        `<span class="answer-layer-claim-text">${esc(c.statement || "")}</span>` +
        `<span class="answer-layer-confidence-num">${w}%</span></div>` +
        `<div class="answer-layer-confidence-track" role="presentation"><span class="answer-layer-confidence-fill" style="width:${w}%"></span></div>` +
        (idxs.length ? `<div class="answer-layer-mini-src">Sources ${sourceIndicesHtml(src, idxs)}</div>` : "") +
        `</div>`;
    });
    let contraHtml = "";
    (data.contradictions || []).forEach((z) => {
      contraHtml +=
        `<div class="answer-layer-contra">` +
        `<div class="answer-layer-contra-title">${esc(z.summary || "Sources disagree on this point.")}</div>` +
        `<div class="answer-layer-contra-grid">` +
        `<div><span class="answer-layer-contra-tag">View A</span><p>${esc(z.position_a || "")}</p>` +
        `<div class="answer-layer-mini-src">${sourceIndicesHtml(src, z.sources_a || [])}</div></div>` +
        `<div><span class="answer-layer-contra-tag">View B</span><p>${esc(z.position_b || "")}</p>` +
        `<div class="answer-layer-mini-src">${sourceIndicesHtml(src, z.sources_b || [])}</div></div>` +
        `</div></div>`;
    });
    const steps = data.reasoning_steps || [];
    let whyHtml = "";
    if (steps.length) {
      const lis = steps
        .map((r) => {
          const step = esc((r.step || "").trim());
          const links = sourceIndicesHtml(src, r.source_indices || []);
          return `<li><span class="answer-layer-step-text">${step}</span>${
            links ? ` <span class="answer-layer-step-srcs">${links}</span>` : ""
          }</li>`;
        })
        .join("");
      whyHtml = `<details class="answer-layer-why"><summary class="answer-layer-why-summary">Why this answer</summary><ol class="answer-layer-why-list">${lis}</ol></details>`;
    }
    layerBody.innerHTML =
      `<div class="answer-layer-inner">${headHtml}<div class="answer-layer-synthesis">${synthHtml}</div>` +
      (claimsHtml
        ? `<section class="answer-layer-section" aria-label="Claims"><h4 class="answer-layer-section-title">Claims &amp; confidence</h4>${claimsHtml}</section>`
        : "") +
      (contraHtml
        ? `<section class="answer-layer-section" aria-label="Contradictions"><h4 class="answer-layer-section-title">Where sources disagree</h4>${contraHtml}</section>`
        : "") +
      `${whyHtml}</div>`;
    layerSources.hidden = false;
    layerSources.innerHTML = src
      .filter((s) => s.url && /^https?:\/\//i.test(s.url))
      .map((s, i) => {
        const t = (s.title || displayNetloc(s.url) || "").slice(0, 44);
        return `<a class="ai-source-pill" href="${esc(s.url)}" target="_blank" rel="noopener">[${i + 1}] ${esc(t)}</a>`;
      })
      .join("");
  }

  function applyAiSummaryPayload(data, ok) {
    if (!aiCard || !aiBody || !aiSources) return;
    if (!data) {
      throw new Error("No summary payload");
    }
    if (data.enabled === false) {
      aiCard.classList.add("ai-hidden");
      return;
    }
    if (!ok || data.error) {
      const msg = userFacingApiError(
        data.message || data.error,
        "Summary temporarily unavailable. Results are shown below."
      );
      aiBody.innerHTML = `<div class="ai-summary-text ai-unavailable">${esc(msg)}</div>`;
      aiSources.innerHTML = "";
      return;
    }
    const lbl = document.getElementById("ai-summary-label");
    if (lbl && data.answer_mode === "single") {
      lbl.textContent = "Answer";
      aiCard.classList.add("answer-single");
      aiCard.setAttribute("data-answer-mode", "single");
    } else if (lbl && data.answer_mode === "standard") {
      lbl.textContent = "Summary";
      aiCard.classList.remove("answer-single");
      aiCard.setAttribute("data-answer-mode", "standard");
    }
    let summary = esc(data.summary);
    summary = summary.replace(/\[(\d+)\]/g, (match, num) => {
      const idx = parseInt(num, 10) - 1;
      if (data.sources && data.sources[idx]) {
        const url = data.sources[idx].url;
        if (url && /^https?:\/\//i.test(url)) {
          return `<a class="ai-citation" href="${esc(url)}" target="_blank" rel="noopener">${num}</a>`;
        }
      }
      return match;
    });
    aiBody.innerHTML = `<div class="ai-summary-text">${summary}</div>`;
    if (data.sources && data.sources.length) {
      aiSources.innerHTML = data.sources
        .filter((s) => s.url && /^https?:\/\//i.test(s.url))
        .map((s, i) =>
          `<a class="ai-source-pill" href="${esc(s.url)}" target="_blank" rel="noopener">[${i + 1}] ${esc(s.title).slice(0, 40)}</a>`
        )
        .join("");
    }
  }

  function fetchAiSummaryOnly() {
    if (!aiCard || !aiBody || !aiSources || !window.__searchQuery || window.__searchType !== "text") return Promise.resolve();
    if (window.__queryUi && window.__queryUi.show_ai_summary === false) {
      aiCard.classList.add("ai-hidden");
      return Promise.resolve();
    }
    const aiQ = `/api/ai-summary?q=${encodeURIComponent(window.__searchQuery)}${searchContextQuerySuffix()}`;
    return fetchJson(aiQ)
      .then(({ ok, data }) => {
        applyAiSummaryPayload(data, ok);
      })
      .catch(() => {
        aiBody.innerHTML =
          '<div class="ai-summary-text ai-unavailable">Summary temporarily unavailable. Results are shown below.</div>';
        aiSources.innerHTML = "";
      });
  }

  if (aiCard && aiBody && window.__searchQuery && window.__searchType === "text") {
    if (window.__queryUi && window.__queryUi.show_ai_summary === false) {
      aiCard.classList.add("ai-hidden");
      if (layerCard) layerCard.classList.add("ai-hidden");
    } else if (window.__showAnswerLayer && layerCard && layerBody && layerSources) {
      const layerHidden = sessionStorage.getItem("abbiey_answer_layer_session_hide") === "1";
      if (layerHidden) {
        fetchAiSummaryOnly();
      } else {
        const layerQ = `/api/answer-layer?q=${encodeURIComponent(window.__searchQuery)}${searchContextQuerySuffix()}`;
        fetchJson(layerQ)
          .then(({ ok, data }) => {
            if (!data) {
              throw new Error("No answer-layer payload");
            }
            if (data.enabled === false) {
              layerCard.classList.add("ai-hidden");
              return fetchAiSummaryOnly();
            }
            if (data.layer === true && data.enabled === true) {
              renderAnswerLayer(data);
              aiCard.style.display = "none";
              return;
            }
            layerCard.classList.add("ai-hidden");
            return fetchAiSummaryOnly();
          })
          .catch(() => {
            layerCard.classList.add("ai-hidden");
            return fetchAiSummaryOnly();
          });
      }
    } else {
      fetchAiSummaryOnly();
    }
  }

  const aiDismiss = document.getElementById("ai-summary-dismiss");
  const aiRestoreWrap = document.getElementById("ai-summary-restore-wrap");
  const aiRestoreBtn = document.getElementById("ai-summary-restore-tab");
  if (aiDismiss && aiCard && aiRestoreWrap && aiRestoreBtn) {
    aiDismiss.addEventListener("click", () => {
      sessionStorage.setItem("abbiey_ai_summary_session_hide", "1");
      aiCard.style.display = "none";
      aiRestoreWrap.hidden = false;
    });
    aiRestoreBtn.addEventListener("click", () => {
      sessionStorage.removeItem("abbiey_ai_summary_session_hide");
      aiCard.style.display = "";
      aiRestoreWrap.hidden = true;
    });
  }

  const layerDismiss = document.getElementById("answer-layer-dismiss");
  if (layerDismiss && layerCard && layerRestoreWrap) {
    layerDismiss.addEventListener("click", () => {
      sessionStorage.setItem("abbiey_answer_layer_session_hide", "1");
      layerCard.style.display = "none";
      layerRestoreWrap.hidden = false;
      if (aiCard) {
        aiCard.style.display = "";
        fetchAiSummaryOnly();
      }
    });
  }
  if (layerRestoreBtn && layerCard && layerRestoreWrap && aiCard) {
    layerRestoreBtn.addEventListener("click", () => {
      sessionStorage.removeItem("abbiey_answer_layer_session_hide");
      layerCard.style.display = "";
      layerRestoreWrap.hidden = true;
      aiCard.style.display = "none";
    });
  }

  // ===== Stable placeholder copy =====
  const rotatingInput = document.querySelector("[data-placeholder-rotate]");
  if (rotatingInput && !rotatingInput.value) {
    rotatingInput.setAttribute(
      "placeholder",
      "Try: site:example.com \u00b7 8.8.8.8 \u00b7 user@domain \u00b7 BTC address \u00b7 .onion index\u2026"
    );
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
      if (gs("history") !== "true" || gs("incognito") === "true") return [];
      try { localStorage.removeItem(HISTORY_KEY); } catch {}
      try { return JSON.parse(sessionStorage.getItem(HISTORY_KEY)) || []; }
      catch { return []; }
    }
    function saveHistory(items) {
      if (gs("history") !== "true" || gs("incognito") === "true") { clearStoredSearchHistory(); return; }
      try { sessionStorage.setItem(HISTORY_KEY, JSON.stringify(items)); }
      catch {}
    }
    function addHistory(term) {
      if (gs("history") === "false" || gs("incognito") === "true") return;
      const t = term.trim();
      if (!t) return;
      let items = getHistory().filter(i => i !== t);
      items.unshift(t);
      if (items.length > MAX_HISTORY) items = items.slice(0, MAX_HISTORY);
      saveHistory(items);
    }
    function removeHistory(term) { saveHistory(getHistory().filter(i => i !== term)); }
    function clearHistory() { clearStoredSearchHistory(true); }

    function syncServerUserHistory(q) {
      if (gs("history") !== "true" || gs("incognito") === "true") return;
      if (!document.querySelector(".user-avatar-chip")) return;
      const t = (q || "").trim();
      if (!t) return;
      const typeInput = document.getElementById("search-type-input");
      const st = (typeInput && typeInput.value) ? typeInput.value : "text";
      fetch("/api/user/history", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ query: t, search_type: st }),
      }).catch(() => {});
    }

    form.addEventListener("submit", () => {
      addHistory(input.value);
      syncServerUserHistory(input.value);
    });

    function showDropdown() { dropdown.classList.add("open"); }
    function hideDropdown() { dropdown.classList.remove("open"); activeIdx = -1; }

    function renderSuggestions(items) {
      if (!items.length) { hideDropdown(); return; }
      dropdown.innerHTML = items.map((text, i) =>
        `<div class="ac-item" data-idx="${i}"><span class="ac-item-icon ac-item-icon-search">${ICON_SEARCH_GLASS_SVG}</span><span class="ac-item-text">${esc(text)}</span><button class="ac-dismiss-btn" data-dismiss-idx="${i}" type="button" title="Not relevant" aria-label="Hide suggestion ${esc(text)}">${CLOSE_ICON_SVG}</button></div>`
      ).join("");
      activeIdx = -1;
      showDropdown();
    }

    function renderHistory() {
      const items = getHistory();
      let h = "";
      if (items.length) {
        h += `<div class="ac-header"><span class="ac-header-label">Recent</span><button class="ac-clear-btn" id="ac-clear-all" type="button">Clear</button></div>`;
        h += items.slice(0, 5).map((text, i) =>
          `<div class="ac-item" data-idx="${i}" data-history="1"><span class="ac-item-icon ac-item-icon-clock"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></span><span class="ac-item-text">${esc(text)}</span><button class="ac-delete-btn" data-del-idx="${i}" type="button" title="Remove" aria-label="Remove ${esc(text)}">${CLOSE_ICON_SVG}</button></div>`
        ).join("");
      }
      dropdown.innerHTML = h;
      activeIdx = -1;
      showDropdown();
    }

    function getItems() { return dropdown.querySelectorAll(".ac-item"); }
    function setActive(idx) {
      const items = getItems();
      items.forEach(el => el.classList.remove("active"));
      if (idx >= 0 && idx < items.length) { items[idx].classList.add("active"); items[idx].scrollIntoView({ block: "nearest" }); }
      activeIdx = idx;
    }
    function postSuggestionFeedback(payload) {
      fetch("/api/feedback/suggestion", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      }).catch(() => {});
    }
    function selectItem(text, meta) {
      const prefix = meta && meta.prefix ? meta.prefix : input.value.trim();
      input.value = text;
      hideDropdown();
      addHistory(text);
      if (meta && meta.source === "suggestion") {
        postSuggestionFeedback({
          query_prefix: prefix,
          suggestion: text,
          action: "select",
          position: meta.idx || 0,
          rating: 1,
        });
      }
      form.submit();
    }

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
      hideDropdown();
      acTimer = window.setTimeout(() => fetchSuggestions(val), motionDelay(120));
    });
    input.addEventListener("focus", () => { if (!input.value.trim()) renderHistory(); });
    input.addEventListener("keydown", (e) => {
      const items = getItems();
      if (!dropdown.classList.contains("open") || !items.length) return;
      if (e.key === "ArrowDown") { e.preventDefault(); setActive(activeIdx < items.length - 1 ? activeIdx + 1 : 0); }
      else if (e.key === "ArrowUp") { e.preventDefault(); setActive(activeIdx > 0 ? activeIdx - 1 : items.length - 1); }
      else if (e.key === "Enter" && activeIdx >= 0) {
        e.preventDefault();
        const it = items[activeIdx];
        const text = it.querySelector(".ac-item-text").textContent;
        const isHistory = it.getAttribute("data-history") === "1";
        selectItem(text, { idx: activeIdx, source: isHistory ? "history" : "suggestion", prefix: input.value.trim() });
      }
      else if (e.key === "Escape") hideDropdown();
    });
    dropdown.addEventListener("mousedown", (e) => {
      if (e.target.closest(".ac-item, .ac-delete-btn, .ac-clear-btn, .ac-dismiss-btn")) {
        e.preventDefault();
      }
    });
    dropdown.addEventListener("click", (e) => {
      const clearBtn = e.target.closest(".ac-clear-btn");
      if (clearBtn) {
        e.preventDefault();
        e.stopPropagation();
        clearHistory();
        hideDropdown();
        return;
      }
      const delBtn = e.target.closest(".ac-delete-btn");
      if (delBtn) { e.preventDefault(); e.stopPropagation(); const idx = parseInt(delBtn.getAttribute("data-del-idx")); const items = getHistory(); if (idx >= 0 && idx < items.length) removeHistory(items[idx]); renderHistory(); return; }
      const dismissBtn = e.target.closest(".ac-dismiss-btn");
      if (dismissBtn) {
        e.preventDefault();
        e.stopPropagation();
        const item = dismissBtn.closest(".ac-item");
        const idx = parseInt(dismissBtn.getAttribute("data-dismiss-idx") || "0");
        const text = item ? item.querySelector(".ac-item-text").textContent : "";
        if (text) {
          postSuggestionFeedback({
            query_prefix: input.value.trim(),
            suggestion: text,
            action: "dismiss",
            position: idx,
            rating: -1,
          });
        }
        if (item) item.remove();
        if (!getItems().length) hideDropdown();
        return;
      }
      const item = e.target.closest(".ac-item");
      if (item) {
        e.preventDefault();
        const idx = parseInt(item.getAttribute("data-idx") || "0");
        const isHistory = item.getAttribute("data-history") === "1";
        selectItem(item.querySelector(".ac-item-text").textContent, { idx, source: isHistory ? "history" : "suggestion", prefix: input.value.trim() });
      }
    });

    // '/' keyboard shortcut to focus search (when not already in an input)
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== input &&
          !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement.tagName)) {
        e.preventDefault();
        input.focus();
        input.select();
      }
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

    // Original web (anti-template ranking) â€” toggles hidden cleanweb=1
    const cleanwebPill = document.getElementById("cleanweb-pill");
    const cleanwebInput = document.getElementById("cleanweb-input");
    if (cleanwebPill && cleanwebInput && filterForm) {
      cleanwebPill.addEventListener("click", () => {
        const on = cleanwebInput.value === "1";
        cleanwebInput.value = on ? "" : "1";
        cleanwebPill.classList.toggle("active", !on);
        cleanwebPill.setAttribute("aria-pressed", (!on).toString());
        applyFilter();
      });
    }

    // Deep web mode toggles
    const onionScopeBar = document.getElementById("onion-scope-bar");
    const onionModeInput = document.getElementById("onion-mode-input");
    if (onionScopeBar && onionModeInput && filterForm) {
      const modeBtns = onionScopeBar.querySelectorAll(".onion-scope-btn");
      onionScopeBar.addEventListener("click", (e) => {
        const btn = e.target.closest(".onion-scope-btn");
        if (!btn || !onionScopeBar.contains(btn)) return;
        const mode = (btn.dataset.onionMode || "").trim();
        if (!mode || mode === onionModeInput.value) return;
        torAgreementGate.ensureAgreement(() => {
          onionModeInput.value = mode;
          modeBtns.forEach((b) => {
            const active = b === btn;
            b.classList.toggle("active", active);
            b.setAttribute("aria-pressed", active ? "true" : "false");
          });
          applyFilter();
        });
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

  const LS_RESULT_ORDER = "abbiey_result_order_v1";
  function resultOrderKey() {
    const s = document.getElementById("scroll-sentinel");
    const q =
      (s && s.dataset.query) ||
      (typeof window.__searchQuery !== "undefined" ? window.__searchQuery : "") ||
      "";
    const t =
      (s && s.dataset.type) ||
      (typeof window.__searchType !== "undefined" ? window.__searchType : "text") ||
      "text";
    return `${t}|${String(q).trim().toLowerCase()}`;
  }
  function loadResultOrderMap() {
    try {
      const raw = localStorage.getItem(LS_RESULT_ORDER);
      const o = raw ? JSON.parse(raw) : {};
      return o && typeof o === "object" ? o : {};
    } catch (_) {
      return {};
    }
  }
  function saveResultOrderForKey(key, urls) {
    try {
      const m = loadResultOrderMap();
      m[key] = urls;
      localStorage.setItem(LS_RESULT_ORDER, JSON.stringify(m));
    } catch (_) {}
  }
  function applySavedResultOrder(scope) {
    const c = scope || document.getElementById("results");
    if (!c) return;
    const order = loadResultOrderMap()[resultOrderKey()];
    if (!order || !Array.isArray(order) || order.length < 2) return;
    const articles = Array.from(c.querySelectorAll(":scope > article.result[data-url]"));
    if (articles.length < 2) return;
    const byUrl = new Map(articles.map(a => [a.dataset.url, a]));
    const frag = document.createDocumentFragment();
    const seen = new Set();
    order.forEach(u => {
      const el = byUrl.get(u);
      if (el) {
        frag.appendChild(el);
        seen.add(u);
      }
    });
    articles.forEach(a => {
      if (!seen.has(a.dataset.url)) frag.appendChild(a);
    });
    c.appendChild(frag);
  }
  function attachResultDragHandles(scope) {
    const c = scope || document.getElementById("results");
    if (!c) return;
    const st = (typeof window.__searchType !== "undefined" ? window.__searchType : "") || "";
    if (st === "images" || st === "saved") return;
    c.querySelectorAll(":scope > article.result[data-url]").forEach(art => {
      if (art.querySelector(":scope > .result-drag-handle")) return;
      const h = document.createElement("span");
      h.className = "result-drag-handle";
      h.setAttribute("draggable", "true");
      h.setAttribute("role", "button");
      h.setAttribute("tabindex", "0");
      h.setAttribute("aria-label", "Drag to reorder results");
      h.title = "Drag to reorder";
      h.innerHTML = "<span class=\"result-drag-grip\" aria-hidden=\"true\"></span>";
      art.insertBefore(h, art.firstChild);
      const url = art.dataset.url;
      h.addEventListener("dragstart", e => {
        e.dataTransfer.setData("text/plain", url);
        e.dataTransfer.effectAllowed = "move";
        art.classList.add("result-dragging");
      });
      h.addEventListener("dragend", () => art.classList.remove("result-dragging"));
    });
    c.querySelectorAll(":scope > article.result[data-url]").forEach(art => {
      if (art.dataset.dragDropInit === "1") return;
      art.dataset.dragDropInit = "1";
      art.addEventListener("dragover", e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
      });
      art.addEventListener("drop", e => {
        e.preventDefault();
        const fromUrl = e.dataTransfer.getData("text/plain");
        const toUrl = art.dataset.url;
        if (!fromUrl || !toUrl || fromUrl === toUrl) return;
        const parent = art.parentNode;
        if (!parent) return;
        const nodes = Array.from(parent.querySelectorAll(":scope > article.result[data-url]"));
        const fromEl = nodes.find(n => n.dataset.url === fromUrl);
        const toEl = nodes.find(n => n.dataset.url === toUrl);
        if (!fromEl || !toEl) return;
        const rect = toEl.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        if (before) parent.insertBefore(fromEl, toEl);
        else parent.insertBefore(fromEl, toEl.nextSibling);
        const urls = Array.from(parent.querySelectorAll(":scope > article.result[data-url]")).map(
          n => n.dataset.url
        );
        saveResultOrderForKey(resultOrderKey(), urls);
      });
    });
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
    let progTimer = null;
    const progWrap = sentinel.querySelector(".indexing-progress-wrap");
    if (progWrap) {
      progWrap.style.setProperty("--index-progress", "0");
      let progVal = 0;
      progTimer = window.setInterval(() => {
        progVal = Math.min(progVal + (Math.random() * 0.08 + 0.02), 0.92);
        progWrap.style.setProperty("--index-progress", String(progVal));
      }, 110);
    }
    const loadMoreBtn = document.querySelector(".load-more-btn");
    if (loadMoreBtn) loadMoreBtn.classList.add("loading");
    const page = parseInt(sentinel.dataset.page) + 1;
    sentinel.querySelector(".scroll-loader").classList.remove("hidden");
    showSkeletons(5);

    const regionVal = document.getElementById("region-input")?.value || "";
    const langVal = document.getElementById("lang-input")?.value || "";
    const dfVal = document.getElementById("df-input")?.value || "";
    const safeVal = document.getElementById("safesearch-input")?.value || "";
    const openKnowledge = document.getElementById("open-knowledge-check")?.checked;
    let scrollUrl = `/search?q=${encodeURIComponent(query)}&page=${page}&type=${type}`;
    if (type === "mybot" && sentinel.dataset.botId) {
      scrollUrl += `&bot_id=${encodeURIComponent(sentinel.dataset.botId)}`;
    }
    if (regionVal) scrollUrl += `&region=${encodeURIComponent(regionVal)}`;
    if (langVal) scrollUrl += `&lang=${encodeURIComponent(langVal)}`;
    if (dfVal) scrollUrl += `&df=${encodeURIComponent(dfVal)}`;
    if (safeVal && safeVal !== "off") scrollUrl += `&safesearch=${encodeURIComponent(safeVal)}`;
    if (sentinel.dataset.cleanweb === "1") scrollUrl += "&cleanweb=1";
    if (openKnowledge) scrollUrl += "&open_knowledge=1";
    const imgExtra = sentinel.dataset.imgExtra;
    if (type === "images" && imgExtra) scrollUrl += `&${imgExtra}`;
    if (type === "images" && sentinel.dataset.imgRevKey) {
      scrollUrl += `&img_rev_key=${encodeURIComponent(sentinel.dataset.imgRevKey)}`;
    }
    if (type === "onion" && sentinel.dataset.onionMode) {
      scrollUrl += `&onion_mode=${encodeURIComponent(sentinel.dataset.onionMode)}`;
    }
    let geoSuf = geoQuerySuffix();
    if (!geoSuf && sentinel.dataset.lat && sentinel.dataset.lon) {
      geoSuf = `&lat=${encodeURIComponent(sentinel.dataset.lat)}&lon=${encodeURIComponent(sentinel.dataset.lon)}`;
    }
    scrollUrl += geoSuf;
    fetch(scrollUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(r => r.json())
      .then(data => {
        if (progTimer) window.clearInterval(progTimer);
        if (progWrap) {
          progWrap.style.setProperty("--index-progress", "1");
          window.setTimeout(() => progWrap.style.setProperty("--index-progress", "0"), 500);
        }
        removeSkeletons();
        const frag = document.createDocumentFragment();
        data.results.forEach((r, idx) => {
          const delay = Math.min(idx * 15, 200);
          const el = document.createElement(type === "images" ? "div" : "article");
          el.style.animationDelay = `${delay}ms`;
          el.dataset.url = r.url || "";
          if (type !== "images") el.dataset.rank = String(idx);

          if (type === "images" && typeof window.buildVisImageCard === "function") {
            const card = window.buildVisImageCard(r);
            card.style.animationDelay = `${delay}ms`;
            frag.appendChild(card);
            return;
          }
          if (type === "images") {
            el.className = "image-card";
            el.dataset.full = r.image || r.thumbnail;
            el.dataset.title = r.title;
            el.dataset.source = r.source || "";
            el.dataset.license = r.license || "";
            const lic = r.license ? `<span class="image-license" title="License">${esc(r.license)}</span>` : "";
            const desc = r.body ? `<p class="image-result-desc">${esc(r.body)}</p>` : "";
            el.innerHTML = `<img src="${esc(r.thumbnail || r.image)}" alt="${esc(r.title)}" loading="lazy"><div class="image-card-info"><span class="image-title">${esc(r.title)}</span>${r.source ? `<span class="image-source">${esc(r.source)}</span>` : ""}${desc}${lic}</div>`;
          } else if (type === "videos") {
            el.className = "result video-result";
            el.innerHTML = `${r.thumbnail ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="video-thumb"><img src="${esc(r.thumbnail)}" alt="${esc(r.title)}" loading="lazy">${r.duration ? `<span class="duration">${esc(r.duration)}</span>` : ""}</a>` : ""}<div class="result-text"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${faviconImg(r.url)}<cite class="result-url">${esc(r.publisher || "")}</cite><p class="result-snippet">${esc(r.description || "")}</p><div class="result-actions" data-feedback="1"><button type="button" class="result-action-btn feedback-btn" data-rating="up">Helpful</button><button type="button" class="result-action-btn feedback-btn" data-rating="down">Not relevant</button></div></div>`;
          } else if (type === "onion") {
            el.className = "result onion-result";
            const isOnion = r.onion || (r.url && /\.onion(\/|$)/i.test(r.url));
            const sourceLabel = r.source_label ? `<span class="onion-source-badge">${esc(r.source_label)}</span>` : "";
            const accessLabel = r.access === "clearnet"
              ? '<span class="onion-access-badge onion-access-badge-clearnet">Clearnet reference</span>'
              : '<span class="onion-access-badge">Tor</span>';
            el.innerHTML = `<div class="onion-result-header"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${isOnion ? '<span class="onion-badge">.onion</span>' : ""}${sourceLabel}</div><cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p><div class="onion-meta-row">${accessLabel}${r.source ? `<span class="onion-meta-source">${esc(String(r.source).replace(/-/g, " "))}</span>` : ""}</div><div class="result-actions" data-feedback="1"><button type="button" class="result-action-btn feedback-btn" data-rating="up">Helpful</button><button type="button" class="result-action-btn feedback-btn" data-rating="down">Not relevant</button></div>`;
          } else if (type === "code") {
            el.className = "result code-result";
            el.innerHTML = `<div class="code-result-header"><a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a>${r.language ? `<span class="code-lang-badge">${esc(r.language)}</span>` : ""}<span class="code-source-badge">${esc(r.source || "")}</span></div>${faviconImg(r.url)}<cite class="result-url">${esc(r.url)}</cite><p class="result-snippet">${esc(r.body || "")}</p><div class="code-meta">${r.stars ? `<span class="code-stat">&#9733; ${esc(r.stars)}</span>` : ""}${r.forks ? `<span class="code-stat">&#9906; ${esc(r.forks)}</span>` : ""}</div><div class="result-actions" data-feedback="1"><button type="button" class="result-action-btn feedback-btn" data-rating="up">Helpful</button><button type="button" class="result-action-btn feedback-btn" data-rating="down">Not relevant</button></div>`;
          } else {
            el.className = "result";
            el.setAttribute("data-source-type", r.source_type || "");
            el.innerHTML = `<button class="bookmark-btn" data-url="${esc(r.url)}" data-title="${esc(r.title)}" data-snippet="${esc(r.body || "")}" aria-label="Save result" title="Save"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z"/></svg></button>${resultDomainRow(r.url, r.source_type, r.source)}<a href="${esc(r.url)}" target="_blank" rel="noopener" class="result-title">${esc(r.title)}</a><p class="result-snippet">${esc(r.body || "")}</p>${r.date ? `<time class="result-date">${esc(r.date)}</time>` : ""}<div class="result-actions" data-feedback="1"><button type="button" class="result-action-btn feedback-btn" data-rating="up">Helpful</button><button type="button" class="result-action-btn feedback-btn" data-rating="down">Not relevant</button></div>`;
          }
          frag.appendChild(el);
        });
        container.appendChild(frag);
        if (type === "images" && typeof window.visRelayoutImages === "function") {
          window.visRelayoutImages(container);
        }
        initBookmarkBtns(container);
        applySavedResultOrder(container);
        attachResultDragHandles(container);
        sentinel.dataset.page = page;
        if (data.has_more) { hasMore = true; sentinel.querySelector(".scroll-loader").classList.add("hidden"); }
        else { hasMore = false; sentinel.remove(); observer.disconnect(); }
        loading = false;
        const loadMoreBtnDone = document.querySelector(".load-more-btn");
        if (loadMoreBtnDone) loadMoreBtnDone.classList.remove("loading");
      })
      .catch(() => {
        if (progTimer) window.clearInterval(progTimer);
        if (progWrap) progWrap.style.setProperty("--index-progress", "0");
        removeSkeletons();
        sentinel.querySelector(".scroll-loader").classList.add("hidden");
        loading = false;
        const loadMoreBtnErr = document.querySelector(".load-more-btn");
        if (loadMoreBtnErr) loadMoreBtnErr.classList.remove("loading");
      });
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
  const lightboxTools = document.getElementById("lightbox-tools");
  const lightboxClose = document.getElementById("lightbox-close");

  let openLightbox = null;
  let lightboxReturnFocus = null;
  if (lightbox) {
    const lightboxIsVisModal = lightbox.classList.contains("vis-modal");
    if (!lightboxIsVisModal) lightbox.removeAttribute("hidden");
    openLightbox = function(card) {
      lightboxReturnFocus = rememberFocus(card);
      function endLightboxLoad() {
        lightbox.classList.remove("lightbox-loading");
        lightbox.removeAttribute("aria-busy");
        lightboxImg.onload = null;
        lightboxImg.onerror = null;
      }
      lightbox.classList.add("lightbox-loading");
      lightbox.setAttribute("aria-busy", "true");
      lightboxImg.onload = endLightboxLoad;
      lightboxImg.onerror = endLightboxLoad;
      const fullUrl = (card.dataset.full || "").trim();
      lightboxImg.src = fullUrl;
      if (!fullUrl || (lightboxImg.complete && lightboxImg.naturalWidth > 0)) {
        endLightboxLoad();
      }
      lightboxImg.alt = card.dataset.title;
      lightboxTitle.textContent = card.dataset.title;
      lightboxSource.href = card.dataset.url;
      if (lightboxTools) {
        const u = card.dataset.full;
        if (u) {
          lightboxTools.href = "https://imgops.com/" + encodeURIComponent(u);
          lightboxTools.hidden = false;
        } else {
          lightboxTools.hidden = true;
        }
      }
      requestAnimationFrame(() => {
        lightbox.classList.add("active");
        document.body.style.overflow = "hidden";
        restoreFocus(lightboxClose);
      });
    };
    function closeLightbox({ restore = true } = {}) {
      lightbox.classList.remove("lightbox-loading");
      lightbox.removeAttribute("aria-busy");
      lightboxImg.onload = null;
      lightboxImg.onerror = null;
      lightbox.classList.remove("active");
      if (lightboxIsVisModal) lightbox.hidden = true;
      document.body.style.overflow = "";
      afterMotion(250, () => {
        if (!lightbox.classList.contains("active")) lightboxImg.src = "";
      });
      if (restore) restoreFocus(lightboxReturnFocus);
      lightboxReturnFocus = null;
    }
    lightboxClose.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", (e) => { if (e.target === lightbox) closeLightbox(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && lightbox.classList.contains("active")) closeLightbox(); });
    document.addEventListener("keydown", (e) => {
      if ((e.key !== "Enter" && e.key !== " ") || !openLightbox) return;
      const imageCard = e.target.closest ? e.target.closest(".image-card") : null;
      if (!imageCard) return;
      e.preventDefault();
      openLightbox(imageCard);
    });
    document.addEventListener("mouseover", (e) => { const card = e.target.closest(".image-card"); if (card && !card._preloaded) { card._preloaded = true; new Image().src = card.dataset.full; } }, { passive: true });
  }

  // ===== On-demand OSINT (entity card + image lightbox host) =====
  const lightboxOsintBtn = document.getElementById("lightbox-osint-btn");
  const lightboxOsintResults = document.getElementById("lightbox-osint-results");
  const osintPanel = document.getElementById("osint-panel");
  const osintToggle = document.getElementById("osint-toggle");
  const osintBody = document.getElementById("osint-body");
  const osintFacts = document.getElementById("osint-facts");
  const osintStatus = document.getElementById("osint-status");

  function renderOsintFactsList(ul, facts, disclaimer) {
    if (!ul) return;
    ul.innerHTML = "";
    if (!facts || !facts.length) {
      const li = document.createElement("li");
      li.textContent = "No public records returned (or lookup failed).";
      ul.appendChild(li);
    } else {
      for (const f of facts) {
        const li = document.createElement("li");
        const lb = document.createElement("span");
        lb.className = "osint-fact-label";
        lb.textContent = f.label || f.type || "Fact";
        const val = document.createElement("span");
        val.className = "osint-fact-value";
        val.textContent = f.value != null ? String(f.value) : "";
        const src = document.createElement("span");
        src.className = "osint-fact-src";
        src.append(document.createTextNode(f.source ? String(f.source) : ""));
        if (f.evidence_url) {
          src.append(document.createTextNode(" "));
          const a = document.createElement("a");
          a.href = f.evidence_url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = "Evidence";
          src.appendChild(a);
        }
        li.appendChild(lb);
        li.appendChild(val);
        li.appendChild(src);
        ul.appendChild(li);
      }
    }
    if (disclaimer && ul.parentElement) {
      let disc = ul.parentElement.querySelector(".osint-disclaimer");
      if (!disc) {
        disc = document.createElement("p");
        disc.className = "osint-disclaimer";
        ul.parentElement.appendChild(disc);
      }
      disc.textContent = String(disclaimer);
    }
  }

  let osintEntityLoaded = false;
  if (window.__osintEnabled && osintToggle && osintPanel && osintBody && osintFacts && osintStatus) {
    osintToggle.addEventListener("click", async () => {
      const expanded = osintToggle.getAttribute("aria-expanded") === "true";
      if (expanded) {
        osintToggle.setAttribute("aria-expanded", "false");
        osintBody.hidden = true;
        return;
      }
      osintToggle.setAttribute("aria-expanded", "true");
      osintBody.hidden = false;
      if (osintEntityLoaded) return;
      osintEntityLoaded = true;
      osintStatus.textContent = "Loading public signalsâ€¦";
      const body = {
        entity_type: osintPanel.dataset.osintType,
        value: osintPanel.dataset.osintValue,
      };
      const { ok, data } = await fetchJson("/api/osint/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!ok || !data || data.ok === false) {
        osintStatus.textContent = userFacingApiError(
          data && data.error,
          "Could not load public signals for this entity.",
        );
        renderOsintFactsList(osintFacts, [], data && data.disclaimer);
        return;
      }
      osintStatus.textContent = data.modules && data.modules.length
        ? `Sources used: ${data.modules.join(", ")}`
        : "";
      renderOsintFactsList(osintFacts, data.facts || [], data.disclaimer);
    });
  }

  if (window.__osintEnabled && lightboxOsintBtn && lightboxOsintResults && openLightbox) {
    const _origOpen = openLightbox;
    openLightbox = function(card) {
      _origOpen(card);
      let host = "";
      try {
        const u = new URL(card.dataset.url || "", window.location.origin);
        host = (u.hostname || "").toLowerCase();
      } catch (_) {
        host = "";
      }
      const looksHost = /^[a-z0-9][a-z0-9.-]*\.[a-z]{2,63}$/i.test(host) && !host.startsWith("data:");
      if (looksHost) {
        lightboxOsintBtn.hidden = false;
        lightboxOsintBtn.dataset.osintHost = host;
      } else {
        lightboxOsintBtn.hidden = true;
        lightboxOsintBtn.dataset.osintHost = "";
      }
      lightboxOsintResults.hidden = true;
      lightboxOsintResults.innerHTML = "";
    };
    lightboxOsintBtn.addEventListener("click", async () => {
      const host = lightboxOsintBtn.dataset.osintHost;
      if (!host) return;
      lightboxOsintResults.hidden = false;
      lightboxOsintResults.innerHTML = "<p class=\"osint-fact-line\">Loadingâ€¦</p>";
      const { ok, data } = await fetchJson("/api/osint/enrich", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ entity_type: "domain", value: host }),
      });
      if (!ok || !data || data.ok === false) {
        lightboxOsintResults.innerHTML = `<p class="osint-fact-line">${esc(userFacingApiError(data && data.error, "Could not load signals for this host."))}</p>`;
        return;
      }
      const parts = (data.facts || []).map((f) => {
        const line = `<div class="osint-fact-line"><strong>${esc(f.label || f.type)}</strong> â€” ${esc(f.value != null ? String(f.value) : "")}</div><div class="osint-fact-meta">${esc(f.source || "")}</div>`;
        return line;
      });
      parts.push(`<div class="osint-fact-meta" style="margin-top:.5rem">${esc(data.disclaimer || "")}</div>`);
      lightboxOsintResults.innerHTML = parts.join("") || "<p class=\"osint-fact-line\">No records.</p>";
    });
  }

  // ===== Consolidated click-outside handler (single delegated listener) =====
  document.addEventListener("click", (e) => {
    const target = e.target;

    // Privacy popover close
    if (privacyPopover && privacyPopover.classList.contains("open") && !privacyPopover.classList.contains("closing")) {
      if (!target.closest(".privacy-popover") && !target.closest("#privacy-badge")) {
        hidePrivacyPopoverFn?.({ restore: false });
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
        afterMotion(1500, () => copyBtn.classList.remove("copied"));
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
  let previewFocusFromKeyboard = false;

  // Cache preview element references once
  const _previewImg = document.getElementById("preview-image");
  const _previewTitle = document.getElementById("preview-title");
  const _previewSite = document.getElementById("preview-site");
  const _previewDesc = document.getElementById("preview-desc");
  const _previewExcerpt = document.getElementById("preview-excerpt");
  const _previewSnapshot = document.getElementById("preview-snapshot");
  const _previewLink = document.getElementById("preview-link");

  if (previewPanel && previewClose) {
    const layoutRoot = document.querySelector(".app-layout");
    const gutter = document.getElementById("layout-gutter-preview");
    const previewDockBtn = document.getElementById("preview-dock-btn");
    const previewRestoreTab = document.getElementById("preview-restore-tab");
    const LP_PREVIEW_W = "abbiey_preview_panel_w";
    const LP_PREVIEW_DOCKED = "abbiey_preview_docked";
    let scheduleKbFocusPending = false;

    function schedulePreviewFocusFromKeyboard() {
      if (!scheduleKbFocusPending) return;
      scheduleKbFocusPending = false;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          (previewDockBtn || previewClose)?.focus?.();
        });
      });
    }

    function undockPreviewIfNeeded() {
      if (!layoutRoot || !layoutRoot.classList.contains("preview-docked-hidden")) return;
      layoutRoot.classList.remove("preview-docked-hidden");
      localStorage.removeItem(LP_PREVIEW_DOCKED);
      if (previewRestoreTab) previewRestoreTab.hidden = true;
    }

    previewClose.addEventListener("click", () => {
      previewPanel.classList.remove("open");
      previewOpen = false;
      clearResultHighlight();
      ss("hoverPreview", "false");
      syncToggle("hover-preview-toggle", false);
    });

    if (previewDockBtn && layoutRoot) {
      previewDockBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        layoutRoot.classList.add("preview-docked-hidden");
        localStorage.setItem(LP_PREVIEW_DOCKED, "1");
        previewPanel.classList.remove("open");
        previewOpen = false;
        clearResultHighlight();
        activeResultIdx = -1;
        if (previewRestoreTab) previewRestoreTab.hidden = false;
      });
    }
    if (previewRestoreTab && layoutRoot) {
      previewRestoreTab.addEventListener("click", () => {
        layoutRoot.classList.remove("preview-docked-hidden");
        localStorage.removeItem(LP_PREVIEW_DOCKED);
        previewRestoreTab.hidden = true;
      });
    }

    function clampPreviewWidth(px) {
      const minW = 240;
      const maxW = Math.min(560, Math.max(minW, window.innerWidth - 400));
      return Math.round(Math.max(minW, Math.min(maxW, px)));
    }

    function persistPreviewWidth(w) {
      html.style.setProperty("--preview-panel-width", `${w}px`);
      localStorage.setItem(LP_PREVIEW_W, String(w));
    }

    if (gutter) {
      let dragPrev = false;
      let gutterPtrId = null;
      function onMove(clientX) {
        const w = clampPreviewWidth(window.innerWidth - clientX);
        persistPreviewWidth(w);
        gutter.setAttribute("aria-valuenow", String(w));
      }
      function endGutterDrag(e) {
        if (!dragPrev || (e && e.pointerId !== gutterPtrId)) return;
        dragPrev = false;
        gutterPtrId = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        try {
          gutter.releasePointerCapture(e.pointerId);
        } catch (_) { /* noop */ }
      }
      gutter.addEventListener("pointerdown", (e) => {
        if (window.innerWidth <= 1100 || e.button !== 0) return;
        dragPrev = true;
        gutterPtrId = e.pointerId;
        e.preventDefault();
        gutter.setPointerCapture(e.pointerId);
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        onMove(e.clientX);
      });
      gutter.addEventListener("pointermove", (e) => {
        if (!dragPrev || e.pointerId !== gutterPtrId) return;
        onMove(e.clientX);
      });
      gutter.addEventListener("pointerup", endGutterDrag);
      gutter.addEventListener("pointercancel", endGutterDrag);
      gutter.addEventListener("keydown", (e) => {
        if (window.innerWidth <= 1100) return;
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        const cur = parseInt(
          getComputedStyle(html).getPropertyValue("--preview-panel-width").trim() || "340",
          10,
        ) || 340;
        const next = clampPreviewWidth(cur + (e.key === "ArrowRight" ? 12 : -12));
        persistPreviewWidth(next);
        gutter.setAttribute("aria-valuenow", String(next));
      });
      gutter.addEventListener("dblclick", () => {
        if (window.innerWidth <= 1100) return;
        html.style.removeProperty("--preview-panel-width");
        localStorage.removeItem(LP_PREVIEW_W);
        gutter.setAttribute("aria-valuenow", "340");
      });
    }

    // Cached result elements â€” invalidated on DOM changes
    let _cachedResults = null;
    const resultsEl = document.getElementById("results");

    const PREVIEW_CARD_SEL = [
      ".entity-results-section article.result[data-url]",
      "#results .result[data-url]",
      "#results .image-card[data-url]",
    ].join(", ");

    function getResultElements() {
      if (!_cachedResults) {
        const list = [];
        document.querySelectorAll(PREVIEW_CARD_SEL).forEach((el) => list.push(el));
        _cachedResults = list;
      }
      return _cachedResults;
    }

    // Invalidate when results tree changes (infinite scroll, saved tab fill-in, etc.)
    const resultObserver = new MutationObserver(() => { _cachedResults = null; });
    if (resultsEl) resultObserver.observe(resultsEl, { childList: true, subtree: true });

    function normalizePreviewUrl(raw) {
      if (!raw || typeof raw !== "string") return "";
      const u = raw.trim();
      if (u.startsWith("//")) return `https:${u}`;
      if (u.startsWith("http://") || u.startsWith("https://")) return u;
      return "";
    }

    function clearResultHighlight() {
      if (!resultsEl) return;
      const prev = resultsEl.querySelector(".result-focused");
      if (prev) prev.classList.remove("result-focused");
    }

    function highlightResult(idx) {
      if (!resultsEl) return;
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
      const u = normalizePreviewUrl(url);
      if (!u) return;

      scheduleKbFocusPending = previewFocusFromKeyboard;
      previewFocusFromKeyboard = false;

      undockPreviewIfNeeded();

      // Show panel if not open
      if (!previewOpen) {
        previewPanel.classList.add("open");
        previewOpen = true;
      }

      // Check cache (key by normalized URL)
      if (previewCache[u]) {
        renderPreview(previewCache[u]);
        return;
      }

      // Show loading â€” batched in rAF
      requestAnimationFrame(() => {
        previewEmpty.style.display = "none";
        previewContent.style.display = "none";
        previewLoading.style.display = "flex";
      });

      fetch(`/api/preview?url=${encodeURIComponent(u)}`)
        .then(r => r.json())
        .then(data => {
          if (data.error) {
            requestAnimationFrame(() => {
              previewLoading.style.display = "none";
              previewContent.style.display = "block";
              _previewTitle.textContent = "Preview unavailable";
              _previewDesc.textContent = userFacingPreviewError(data.error);
              _previewExcerpt.textContent = "";
              _previewSite.textContent = "";
              _previewImg.style.display = "none";
              if (_previewSnapshot) {
                _previewSnapshot.removeAttribute("srcdoc");
                _previewSnapshot.style.display = "none";
              }
              _previewLink.href = u;
              schedulePreviewFocusFromKeyboard();
            });
            return;
          }
          previewCache[u] = data;
          renderPreview(data);
        })
        .catch(() => {
          requestAnimationFrame(() => {
            previewLoading.style.display = "none";
            previewEmpty.style.display = "block";
            schedulePreviewFocusFromKeyboard();
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

        if (_previewSnapshot) {
          if (data.snapshot_html) {
            _previewSnapshot.srcdoc = data.snapshot_html;
            _previewSnapshot.style.display = "block";
          } else {
            _previewSnapshot.removeAttribute("srcdoc");
            _previewSnapshot.style.display = "none";
          }
        }

        _previewTitle.textContent = data.title || "";
        _previewSite.textContent = siteName;
        _previewDesc.textContent = data.description || "";
        _previewExcerpt.textContent = data.excerpt || "";
        _previewLink.href = data.url;
        schedulePreviewFocusFromKeyboard();
      });
    }

    // Hover to preview (all result cards with data-url: main grid, saved, entity sections)
    let hoverTimer = null;
    document.addEventListener("mouseover", (e) => {
      if (gs("hoverPreview") !== "true") return;
      const result = e.target.closest(PREVIEW_CARD_SEL);
      if (!result || !result.dataset.url) return;
      previewFocusFromKeyboard = false;
      clearTimeout(hoverTimer);
      hoverTimer = window.setTimeout(() => loadPreview(result.dataset.url), motionDelay(300));
    }, { passive: true });
    document.addEventListener("mouseout", (e) => {
      if (e.target.closest(PREVIEW_CARD_SEL)) clearTimeout(hoverTimer);
    }, { passive: true });

    // Tap on card body on touch / coarse-pointer devices â€” hover does not run there
    function onResultCardTapPreview(e) {
      const card = e.target.closest(PREVIEW_CARD_SEL);
      if (!card || !card.dataset.url) return;
      if (e.target.closest("a[href], button, input, textarea, select, label")) return;
      loadPreview(card.dataset.url);
    }
    if (window.matchMedia("(hover: none), (pointer: coarse)").matches) {
      document.addEventListener("click", onResultCardTapPreview);
    }

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
        previewFocusFromKeyboard = true;
        highlightResult(activeResultIdx);
      } else if (e.key === "k") {
        e.preventDefault();
        activeResultIdx = Math.max(activeResultIdx - 1, 0);
        previewFocusFromKeyboard = true;
        highlightResult(activeResultIdx);
      } else if (e.key === "o" && activeResultIdx >= 0) {
        e.preventDefault();
        const u = normalizePreviewUrl(results[activeResultIdx].dataset.url);
        if (u) window.open(u, "_blank");
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
  const chatAttach = document.getElementById("chat-attach");
  const chatImageInput = document.getElementById("chat-image-input");
  const chatImagePreview = document.getElementById("chat-image-preview");
  const chatImagePreviewImg = document.getElementById("chat-image-preview-img");
  const chatImageRemove = document.getElementById("chat-image-remove");
  const chatSaveBtn = document.getElementById("chat-save");
  const chatSavedBtn = document.getElementById("chat-saved");
  const chatSavedMenu = document.getElementById("chat-saved-menu");
  const chatSavedList = document.getElementById("chat-saved-list");

  if (chatPanel && chatFab) {
    let chatHistory = [];
    let chatPendingImage = null;
    let chatActiveLocalId = null;
    let chatServerSaveId = null;
    let chatSavedOpen = false;
    const searchQuery = window.__searchQuery || "";
    const LP_RESEARCH_CHATS = "abbiey_research_chats_v1";
    const CHAT_MAX_IMAGE_BYTES = 4 * 1024 * 1024;
    let chatOpen = false;
    const chatPeek = document.getElementById("chat-peek");
    const LP_CHAT_W = "abbiey_chat_w";
    const LP_CHAT_H = "abbiey_chat_h";

    function toggleChat() {
      chatOpen = !chatOpen;
      chatPanel.classList.toggle("open", chatOpen);
      if (!chatOpen) chatPanel.classList.remove("collapsed");
      chatFab.classList.toggle("hidden", chatOpen);
      if (chatOpen && chatInput) chatInput.focus();
    }

    chatFab.addEventListener("click", toggleChat);
    if (chatToggle) {
      chatToggle.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleChat();
      });
    }
    if (chatPeek) {
      chatPeek.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!chatOpen) return;
        chatPanel.classList.toggle("collapsed");
      });
    }
    if (chatNew) {
      chatNew.addEventListener("click", (e) => {
        e.stopPropagation();
        startNewChat();
      });
    }

    function chatIsLoggedIn() {
      return !!document.querySelector(".user-avatar-chip");
    }

    function readLocalChatStore() {
      try { localStorage.removeItem(LP_RESEARCH_CHATS); } catch {}
      try { return JSON.parse(sessionStorage.getItem(LP_RESEARCH_CHATS) || "{}"); } catch { return {}; }
    }

    function writeLocalChatStore(store) {
      try { sessionStorage.setItem(LP_RESEARCH_CHATS, JSON.stringify(store)); } catch {}
    }

    function localChatsForQuery(q) {
      const store = readLocalChatStore();
      return Array.isArray(store[q]) ? store[q] : [];
    }

    function upsertLocalChat(q, entry) {
      const store = readLocalChatStore();
      const list = Array.isArray(store[q]) ? store[q] : [];
      const idx = list.findIndex(c => c.id === entry.id);
      if (idx >= 0) list[idx] = entry;
      else list.unshift(entry);
      store[q] = list.slice(0, 20);
      writeLocalChatStore(store);
    }

    function removeLocalChat(q, localId) {
      const store = readLocalChatStore();
      const list = (store[q] || []).filter(c => c.id !== localId);
      store[q] = list;
      writeLocalChatStore(store);
    }

    function chatTitleFromHistory(messages) {
      for (const m of messages) {
        if (m.role === "user") {
          const t = (m.content || "").trim();
          if (t) return t.slice(0, 120);
          if (m.image) return `Image Â· ${searchQuery}`.slice(0, 120);
        }
      }
      return searchQuery.slice(0, 120) || "Research chat";
    }

    function clearPendingImage() {
      chatPendingImage = null;
      if (chatImagePreview) chatImagePreview.hidden = true;
      if (chatImagePreviewImg) chatImagePreviewImg.removeAttribute("src");
      if (chatAttach) chatAttach.classList.remove("has-image");
      if (chatImageInput) chatImageInput.value = "";
    }

    function setPendingImage(dataUrl) {
      chatPendingImage = dataUrl;
      if (chatImagePreviewImg) chatImagePreviewImg.src = dataUrl;
      if (chatImagePreview) chatImagePreview.hidden = false;
      if (chatAttach) chatAttach.classList.add("has-image");
    }

    function readImageFile(file) {
      return new Promise((resolve, reject) => {
        if (!file || !file.type || !file.type.startsWith("image/")) {
          reject(new Error("Please choose a JPEG, PNG, WebP, or GIF image."));
          return;
        }
        if (file.size > CHAT_MAX_IMAGE_BYTES) {
          reject(new Error("Image is too large. Please use a file under 4 MB."));
          return;
        }
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ""));
        reader.onerror = () => reject(new Error("Could not read that image."));
        reader.readAsDataURL(file);
      });
    }

    function renderChatHistory() {
      chatMessages.innerHTML = "";
      msgCounter = 0;
      for (const m of chatHistory) {
        appendMessage(m.role, m.content, m.image || null, { skipScroll: true, animate: false });
      }
      scrollChatIfFollowing(true);
    }

    function startNewChat() {
      chatHistory = [];
      chatActiveLocalId = null;
      chatServerSaveId = null;
      chatMessages.innerHTML = "";
      chatWelcome.style.display = "";
      clearPendingImage();
      if (chatSaveBtn) chatSaveBtn.classList.remove("saved");
      closeSavedMenu();
    }

    async function persistChat({ manual = false } = {}) {
      if (!searchQuery || !chatHistory.length) {
        if (manual && chatSaveBtn) {
          const prev = chatSaveBtn.title;
          chatSaveBtn.title = "Nothing to save yet";
          setTimeout(() => { chatSaveBtn.title = prev || "Save this conversation"; }, 1800);
        }
        return;
      }
      const now = Date.now();
      if (!chatActiveLocalId) chatActiveLocalId = `local-${now}-${Math.random().toString(36).slice(2, 8)}`;
      const entry = {
        id: chatActiveLocalId,
        title: chatTitleFromHistory(chatHistory),
        messages: chatHistory.map(m => ({ role: m.role, content: m.content, ...(m.image ? { image: m.image } : {}) })),
        updatedAt: now,
        serverId: chatServerSaveId,
      };
      upsertLocalChat(searchQuery, entry);
      if (chatSaveBtn) chatSaveBtn.classList.add("saved");
      if (!chatIsLoggedIn()) {
        if (manual) flashChatSaved();
        return;
      }
      try {
        const r = await fetch("/api/research-chats", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            id: chatServerSaveId,
            query: searchQuery,
            title: entry.title,
            messages: entry.messages,
          }),
        });
        const data = await r.json();
        if (r.ok && data.id) {
          chatServerSaveId = data.id;
          entry.serverId = data.id;
          upsertLocalChat(searchQuery, entry);
        }
      } catch {}
      if (manual) flashChatSaved();
    }

    function flashChatSaved() {
      if (!chatSaveBtn) return;
      chatSaveBtn.classList.add("saved");
      const prev = chatSaveBtn.title;
      chatSaveBtn.title = "Saved";
      setTimeout(() => { chatSaveBtn.title = prev || "Save this conversation"; }, 1800);
    }

    function closeSavedMenu() {
      chatSavedOpen = false;
      if (chatSavedMenu) chatSavedMenu.hidden = true;
      if (chatSavedBtn) chatSavedBtn.setAttribute("aria-expanded", "false");
    }

    function openSavedMenu() {
      chatSavedOpen = true;
      if (chatSavedMenu) chatSavedMenu.hidden = false;
      if (chatSavedBtn) chatSavedBtn.setAttribute("aria-expanded", "true");
      renderSavedChatsMenu();
    }

    async function renderSavedChatsMenu() {
      if (!chatSavedList) return;
      chatSavedList.innerHTML = `<div class="chat-saved-empty">Loadingâ€¦</div>`;
      const local = localChatsForQuery(searchQuery);
      let server = [];
      if (chatIsLoggedIn()) {
        try {
          const r = await fetch(`/api/research-chats?query=${encodeURIComponent(searchQuery)}`, { credentials: "same-origin" });
          const data = await r.json();
          if (r.ok && Array.isArray(data.chats)) server = data.chats;
        } catch {}
      }
      const merged = [];
      const seen = new Set();
      for (const s of server) {
        const key = `srv-${s.id}`;
        seen.add(key);
        merged.push({
          key,
          id: s.id,
          localId: null,
          title: s.title || searchQuery,
          meta: `${s.message_count || 0} messages Â· account`,
          server: true,
        });
      }
      for (const l of local) {
        const key = l.serverId ? `srv-${l.serverId}` : l.id;
        if (seen.has(key)) continue;
        seen.add(key);
        merged.push({
          key: l.id,
          id: l.serverId || null,
          localId: l.id,
          title: l.title || searchQuery,
          meta: `${(l.messages || []).length} messages Â· this device`,
          server: false,
          messages: l.messages,
        });
      }
      if (!merged.length) {
        chatSavedList.innerHTML = `<div class="chat-saved-empty">No saved chats for this search yet. Your conversation auto-saves after each reply.</div>`;
        return;
      }
      chatSavedList.innerHTML = merged.map(item =>
        `<div class="chat-saved-item" role="menuitem">` +
        `<button type="button" class="chat-saved-item-main" data-load-key="${esc(item.key)}" data-server-id="${item.id || ""}" data-local-id="${esc(item.localId || "")}">` +
        `<span class="chat-saved-item-title">${esc(item.title)}</span>` +
        `<span class="chat-saved-item-meta">${esc(item.meta)}</span>` +
        `</button>` +
        `<button type="button" class="chat-saved-item-del" data-del-key="${esc(item.key)}" data-server-id="${item.id || ""}" data-local-id="${esc(item.localId || "")}" aria-label="Delete saved chat">&#10005;</button>` +
        `</div>`
      ).join("");
    }

    async function loadSavedChat(serverId, localId) {
      closeSavedMenu();
      if (serverId && chatIsLoggedIn()) {
        try {
          const r = await fetch(`/api/research-chats/${serverId}`, { credentials: "same-origin" });
          const data = await r.json();
          if (r.ok && Array.isArray(data.messages)) {
            chatHistory = data.messages;
            chatServerSaveId = data.id;
            chatActiveLocalId = localId || `local-srv-${data.id}`;
            chatWelcome.style.display = "none";
            renderChatHistory();
            if (chatSaveBtn) chatSaveBtn.classList.add("saved");
            return;
          }
        } catch {}
      }
      const local = localChatsForQuery(searchQuery).find(c => c.id === localId);
      if (local && Array.isArray(local.messages)) {
        chatHistory = local.messages;
        chatActiveLocalId = local.id;
        chatServerSaveId = local.serverId || null;
        chatWelcome.style.display = "none";
        renderChatHistory();
        if (chatSaveBtn) chatSaveBtn.classList.add("saved");
      }
    }

    async function deleteSavedChat(serverId, localId) {
      if (localId) removeLocalChat(searchQuery, localId);
      if (serverId && chatIsLoggedIn()) {
        try {
          await fetch(`/api/research-chats/${serverId}`, { method: "DELETE", credentials: "same-origin" });
        } catch {}
      }
      if ((chatServerSaveId && String(chatServerSaveId) === String(serverId)) ||
          (chatActiveLocalId && chatActiveLocalId === localId)) {
        startNewChat();
      }
      renderSavedChatsMenu();
    }

    function restoreLatestLocalChat() {
      const latest = localChatsForQuery(searchQuery)[0];
      if (!latest || !Array.isArray(latest.messages) || !latest.messages.length) return;
      chatHistory = latest.messages;
      chatActiveLocalId = latest.id;
      chatServerSaveId = latest.serverId || null;
      chatWelcome.style.display = "none";
      renderChatHistory();
      if (chatSaveBtn) chatSaveBtn.classList.add("saved");
    }

    const resizeN = document.getElementById("chat-resize-n");
    const resizeW = document.getElementById("chat-resize-w");
    function clampChatW(w) {
      return Math.round(Math.max(280, Math.min(520, w)));
    }
    function clampChatH(h) {
      return Math.round(Math.max(220, Math.min(720, h)));
    }
    let chatDragN = false;
    let chatDragW = false;
    let chatPtrN = null;
    let chatPtrW = null;
    let chatResizeStartY = 0;
    let chatResizeStartH = 0;
    let chatResizeStartX = 0;
    let chatResizeStartW = 0;

    function endChatDragN(e) {
      if (!chatDragN || (e && e.pointerId !== chatPtrN)) return;
      chatDragN = false;
      chatPtrN = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      const h = chatPanel.getBoundingClientRect().height;
      localStorage.setItem(LP_CHAT_H, String(clampChatH(Math.round(h))));
      if (e && resizeN) {
        try {
          resizeN.releasePointerCapture(e.pointerId);
        } catch (_) { /* noop */ }
      }
    }
    function endChatDragW(e) {
      if (!chatDragW || (e && e.pointerId !== chatPtrW)) return;
      chatDragW = false;
      chatPtrW = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      const w = chatPanel.getBoundingClientRect().width;
      localStorage.setItem(LP_CHAT_W, String(clampChatW(Math.round(w))));
      if (e && resizeW) {
        try {
          resizeW.releasePointerCapture(e.pointerId);
        } catch (_) { /* noop */ }
      }
    }

    if (resizeN) {
      resizeN.addEventListener("pointerdown", (e) => {
        if (window.innerWidth <= 768 || !chatPanel.classList.contains("open") || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        chatDragN = true;
        chatPtrN = e.pointerId;
        resizeN.setPointerCapture(e.pointerId);
        chatResizeStartY = e.clientY;
        chatResizeStartH = chatPanel.getBoundingClientRect().height;
        document.body.style.userSelect = "none";
        document.body.style.cursor = "ns-resize";
      });
      resizeN.addEventListener("pointermove", (e) => {
        if (!chatDragN || e.pointerId !== chatPtrN) return;
        const nh = clampChatH(chatResizeStartH + (chatResizeStartY - e.clientY));
        html.style.setProperty("--chat-panel-height", `${nh}px`);
        chatPanel.classList.add("chat-user-sized");
      });
      resizeN.addEventListener("pointerup", endChatDragN);
      resizeN.addEventListener("pointercancel", endChatDragN);
      resizeN.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
        if (!chatPanel.classList.contains("open") || window.innerWidth <= 768) return;
        e.preventDefault();
        const cur = Math.round(chatPanel.getBoundingClientRect().height);
        const nh = clampChatH(cur + (e.key === "ArrowUp" ? 16 : -16));
        html.style.setProperty("--chat-panel-height", `${nh}px`);
        chatPanel.classList.add("chat-user-sized");
        localStorage.setItem(LP_CHAT_H, String(nh));
      });
    }
    if (resizeW) {
      resizeW.addEventListener("pointerdown", (e) => {
        if (window.innerWidth <= 768 || !chatPanel.classList.contains("open") || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        chatDragW = true;
        chatPtrW = e.pointerId;
        resizeW.setPointerCapture(e.pointerId);
        chatResizeStartX = e.clientX;
        chatResizeStartW = chatPanel.getBoundingClientRect().width;
        document.body.style.userSelect = "none";
        document.body.style.cursor = "ew-resize";
      });
      resizeW.addEventListener("pointermove", (e) => {
        if (!chatDragW || e.pointerId !== chatPtrW) return;
        const nw = clampChatW(chatResizeStartW + (chatResizeStartX - e.clientX));
        html.style.setProperty("--chat-panel-width", `${nw}px`);
      });
      resizeW.addEventListener("pointerup", endChatDragW);
      resizeW.addEventListener("pointercancel", endChatDragW);
      resizeW.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        if (!chatPanel.classList.contains("open") || window.innerWidth <= 768) return;
        e.preventDefault();
        const cur = Math.round(chatPanel.getBoundingClientRect().width);
        const nw = clampChatW(cur + (e.key === "ArrowLeft" ? 16 : -16));
        html.style.setProperty("--chat-panel-width", `${nw}px`);
        localStorage.setItem(LP_CHAT_W, String(nw));
      });
    }
    if (resizeN) {
      resizeN.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        chatPanel.classList.remove("chat-user-sized");
        html.style.removeProperty("--chat-panel-height");
        localStorage.removeItem(LP_CHAT_H);
      });
    }
    if (resizeW) {
      resizeW.addEventListener("dblclick", (e) => {
        e.preventDefault();
        e.stopPropagation();
        html.style.removeProperty("--chat-panel-width");
        localStorage.removeItem(LP_CHAT_W);
      });
    }

    const CHAT_SCROLL_THRESHOLD = 72;
    const CHAT_TYPING_MIN_MS = 850;
    const CHAT_TYPING_STAGES = [
      "Reviewing your search results",
      "Cross-checking sources",
      "Composing an answer",
    ];
    let chatFollowBottom = true;
    let typingStageTimer = null;

    function isChatNearBottom() {
      if (!chatBody) return true;
      return chatBody.scrollHeight - chatBody.scrollTop - chatBody.clientHeight <= CHAT_SCROLL_THRESHOLD;
    }

    function scrollChatIfFollowing(force = false) {
      if (!chatBody) return;
      if (force || (chatFollowBottom && isChatNearBottom())) {
        requestAnimationFrame(() => {
          chatBody.scrollTop = chatBody.scrollHeight;
        });
      }
    }

    if (chatBody) {
      chatBody.addEventListener("scroll", () => {
        chatFollowBottom = isChatNearBottom();
      }, { passive: true });
    }

    function sendMessage() {
      const msg = chatInput.value.trim();
      const imageToSend = chatPendingImage;
      if (!msg && !imageToSend) return;
      chatWelcome.style.display = "none";
      appendMessage("user", msg, imageToSend);
      chatInput.value = "";
      clearPendingImage();
      chatInput.disabled = true;
      chatSend.disabled = true;
      if (chatAttach) chatAttach.disabled = true;
      const typingStarted = Date.now();
      const typingId = appendTyping();
      const payload = { query: searchQuery, message: msg, history: chatHistory };
      if (imageToSend) payload.image = imageToSend;

      fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(r => r.json())
        .then(data => {
          const finish = () => {
            removeMessage(typingId);
            if (data.error) appendMessage("assistant", userFacingChatError(data.error));
            else {
              revealAssistantMessage(data.response);
              const userEntry = { role: "user", content: msg };
              if (imageToSend) userEntry.image = imageToSend;
              chatHistory.push(userEntry);
              chatHistory.push({ role: "assistant", content: data.response });
              persistChat();
            }
          };
          const wait = Math.max(0, CHAT_TYPING_MIN_MS - (Date.now() - typingStarted));
          if (wait) setTimeout(finish, wait);
          else finish();
        })
        .catch(() => {
          removeMessage(typingId);
          appendMessage("assistant", "Connection error. Please try again.");
        })
        .finally(() => {
          chatInput.disabled = false;
          chatSend.disabled = false;
          if (chatAttach) chatAttach.disabled = false;
          chatInput.focus();
        });
    }

    if (chatSend) chatSend.addEventListener("click", sendMessage);
    if (chatInput) chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });

    if (chatAttach && chatImageInput) {
      chatAttach.addEventListener("click", () => chatImageInput.click());
      chatImageInput.addEventListener("change", () => {
        const file = chatImageInput.files && chatImageInput.files[0];
        if (!file) return;
        readImageFile(file).then(setPendingImage).catch(err => {
          appendMessage("assistant", err.message || "Could not attach that image.");
        });
      });
    }
    if (chatImageRemove) chatImageRemove.addEventListener("click", clearPendingImage);
    if (chatInput) {
      chatInput.addEventListener("paste", (e) => {
        const items = e.clipboardData && e.clipboardData.items;
        if (!items) return;
        for (const item of items) {
          if (item.type && item.type.startsWith("image/")) {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) readImageFile(file).then(setPendingImage).catch(() => {});
            break;
          }
        }
      });
    }
    if (chatSaveBtn) chatSaveBtn.addEventListener("click", (e) => { e.stopPropagation(); persistChat({ manual: true }); });
    if (chatSavedBtn) {
      chatSavedBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (chatSavedOpen) closeSavedMenu();
        else openSavedMenu();
      });
    }
    if (chatSavedList) {
      chatSavedList.addEventListener("click", (e) => {
        const del = e.target.closest("[data-del-key]");
        if (del) {
          e.stopPropagation();
          deleteSavedChat(del.dataset.serverId || null, del.dataset.localId || null);
          return;
        }
        const load = e.target.closest("[data-load-key]");
        if (load) {
          loadSavedChat(load.dataset.serverId || null, load.dataset.localId || null);
        }
      });
    }
    document.addEventListener("click", (e) => {
      if (!chatSavedOpen) return;
      if (e.target.closest("#chat-saved-menu") || e.target.closest("#chat-saved")) return;
      closeSavedMenu();
    });

    let msgCounter = 0;

    // Formats raw markdown-lite content to safe HTML
    function formatChatContent(raw) {
      return esc(raw)
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/\[(.*?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
        .replace(/(?<!="|">)(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
        .replace(/\n/g, "<br>");
    }

    function appendTyping() {
      const id = `msg-${msgCounter++}`;
      const div = document.createElement("div");
      div.className = "chat-message assistant typing";
      div.id = id;
      div.innerHTML = `<div class="chat-msg-content"><span class="typing-status">${CHAT_TYPING_STAGES[0]}</span><span class="typing-dots"><span></span><span></span><span></span></span></div>`;
      chatMessages.appendChild(div);
      scrollChatIfFollowing(true);
      let stage = 0;
      typingStageTimer = setInterval(() => {
        stage = Math.min(stage + 1, CHAT_TYPING_STAGES.length - 1);
        const status = div.querySelector(".typing-status");
        if (status) status.textContent = CHAT_TYPING_STAGES[stage];
      }, 2400);
      return id;
    }

    function appendMessage(role, content, imageUrl = null, opts = {}) {
      const id = `msg-${msgCounter++}`;
      const div = document.createElement("div");
      div.className = `chat-message ${role}`;
      if (opts.animate === false) div.style.animation = "none";
      div.id = id;
      const innerEl = document.createElement("div");
      innerEl.className = "chat-msg-content";
      if (imageUrl) {
        const img = document.createElement("img");
        img.className = "chat-msg-image";
        img.src = imageUrl;
        img.alt = "Attached image";
        innerEl.appendChild(img);
      }
      if (content) {
        const textWrap = document.createElement("div");
        textWrap.innerHTML = formatChatContent(content);
        innerEl.appendChild(textWrap);
      }
      div.appendChild(innerEl);
      chatMessages.appendChild(div);
      if (!opts.skipScroll) scrollChatIfFollowing(role === "user");
      return id;
    }

    function splitIntoRevealChunks(text) {
      if (!text) return [];
      const paragraphs = text.split(/(\n{2,})/);
      const chunks = [];
      let pendingBreak = "";
      for (const part of paragraphs) {
        if (/^\n{2,}$/.test(part)) {
          pendingBreak = part;
          continue;
        }
        if (!part.trim()) continue;
        const sentences = part.match(/[^.!?â€¦]+[.!?â€¦]+(?:\s+|$)|[^.!?â€¦]+$/g) || [part];
        if (sentences.length <= 1 && part.length < 90) {
          chunks.push(pendingBreak + part);
          pendingBreak = "";
          continue;
        }
        let batch = pendingBreak;
        pendingBreak = "";
        for (const sentence of sentences) {
          batch += sentence;
          if (batch.length >= 72 || /[.!?â€¦]\s*$/.test(batch)) {
            chunks.push(batch);
            batch = "";
          }
        }
        if (batch) chunks.push(batch);
      }
      return chunks.length ? chunks : [text];
    }

    function chunkRevealDelay(chunk) {
      const len = (chunk || "").length;
      return 110 + Math.min(len * 1.4, 180);
    }

    function revealAssistantMessage(rawContent) {
      if (!rawContent || rawContent.length < 100) {
        appendMessage("assistant", rawContent);
        return;
      }
      const chunks = splitIntoRevealChunks(rawContent);
      if (chunks.length <= 1) {
        appendMessage("assistant", rawContent);
        return;
      }

      const id = `msg-${msgCounter++}`;
      const div = document.createElement("div");
      div.className = "chat-message assistant streaming";
      div.id = id;
      const inner = document.createElement("div");
      inner.className = "chat-msg-content";
      div.appendChild(inner);
      chatMessages.appendChild(div);
      scrollChatIfFollowing(true);

      let buf = "";
      let idx = 0;

      function revealNext() {
        if (idx >= chunks.length) {
          inner.innerHTML = formatChatContent(buf);
          div.classList.remove("streaming");
          scrollChatIfFollowing();
          return;
        }
        buf += chunks[idx++];
        inner.innerHTML = formatChatContent(buf) + '<span class="chat-cursor" aria-hidden="true"></span>';
        scrollChatIfFollowing();
        setTimeout(revealNext, chunkRevealDelay(chunks[idx - 1]));
      }

      setTimeout(revealNext, 320);
      return id;
    }

    function removeMessage(id) {
      if (typingStageTimer) {
        clearInterval(typingStageTimer);
        typingStageTimer = null;
      }
      const el = document.getElementById(id);
      if (el) el.remove();
    }

    // Auto-collapse to visible strip on results pages so the assistant is discoverable
    if (searchQuery) {
      chatOpen = true;
      chatPanel.classList.add("open", "collapsed");
      chatFab.classList.add("hidden");
      restoreLatestLocalChat();
    }

    // Header click expands from collapsed state
    const chatHeader = chatPanel.querySelector(".chat-header");
    if (chatHeader) {
      chatHeader.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        if (chatPanel.classList.contains("collapsed")) {
          chatPanel.classList.remove("collapsed");
          if (chatInput) chatInput.focus();
        }
      });
    }

  }  // end if (chatPanel && chatFab)

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

      // Add badges â€” only check actual .onion URLs, skip clearnet DDG fallback results
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

      // Fire off verification request â€” skip if all URLs already cached
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
                // Tor not available â€” remove checking badge
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
  const bookmarkAccountUser = window.__currentUser || null;
  let bookmarkServerIds = new Map();
  let bookmarkSyncPromise = null;

  function bookmarkSavedTs(value) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
    const parsed = Date.parse(value || "");
    return Number.isNaN(parsed) ? 0 : parsed;
  }
  function normalizeBookmarkItem(item) {
    const url = String((item && item.url) || "").trim();
    if (!url) return null;
    return {
      id: item && item.id ? item.id : null,
      url,
      title: String((item && item.title) || "").trim().slice(0, 300) || url,
      snippet: String((item && item.snippet) || "").trim().slice(0, 500),
      saved: bookmarkSavedTs(item && (item.saved ?? item.saved_at)) || Date.now(),
    };
  }
  function dedupeBookmarks(items) {
    const byUrl = new Map();
    (items || []).forEach((raw) => {
      const item = normalizeBookmarkItem(raw);
      if (!item) return;
      const prev = byUrl.get(item.url);
      if (!prev || item.saved >= prev.saved) byUrl.set(item.url, item);
    });
    return Array.from(byUrl.values()).sort((a, b) => (b.saved || 0) - (a.saved || 0));
  }
  function getBookmarks() {
    try { return dedupeBookmarks(JSON.parse(localStorage.getItem(BOOKMARKS_KEY)) || []); }
    catch { return []; }
  }
  function saveBookmarks(items) {
    try { localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(dedupeBookmarks(items))); } catch {}
  }
  function mergeBookmarks(localItems, remoteItems) {
    return dedupeBookmarks([...(localItems || []), ...(remoteItems || [])]);
  }
  function updateBookmarkServerIds(items) {
    bookmarkServerIds = new Map();
    (items || []).forEach((item) => {
      if (item && item.url && item.id != null) {
        bookmarkServerIds.set(item.url, item.id);
      }
    });
  }
  function isBookmarked(url) {
    return getBookmarks().some(b => b.url === url);
  }
  async function syncBookmarksWithServer(options = {}) {
    const silent = options.silent === true;
    if (!bookmarkAccountUser) return getBookmarks();
    if (bookmarkSyncPromise) return bookmarkSyncPromise;
    bookmarkSyncPromise = (async () => {
      const local = getBookmarks();
      const remoteResp = await fetchJson("/api/user/bookmarks");
      if (remoteResp.status === 401) return local;
      if (!remoteResp.ok) {
        throw new Error(userFacingApiError(remoteResp.data && remoteResp.data.error, "Bookmarks couldn't sync right now."));
      }
      const remoteItems = Array.isArray(remoteResp.data && remoteResp.data.bookmarks)
        ? remoteResp.data.bookmarks
        : [];
      updateBookmarkServerIds(remoteItems);
      const merged = mergeBookmarks(local, remoteItems);
      saveBookmarks(merged);
      const syncResp = await fetchJson("/api/user/bookmarks/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bookmarks: merged }),
      });
      if (syncResp.status !== 401 && !syncResp.ok) {
        throw new Error(userFacingApiError(syncResp.data && syncResp.data.error, "Bookmarks couldn't sync right now."));
      }
      if (syncResp.ok && Array.isArray(syncResp.data && syncResp.data.bookmarks)) {
        updateBookmarkServerIds(syncResp.data.bookmarks);
        saveBookmarks(mergeBookmarks(merged, syncResp.data.bookmarks));
      }
      return getBookmarks();
    })()
      .catch((err) => {
        if (!silent) {
          showToast(err && err.message ? err.message : "Bookmarks couldn't sync right now.", "error");
        }
        return getBookmarks();
      })
      .finally(() => {
        bookmarkSyncPromise = null;
        updateBookmarkBadge();
        if (window.__searchType === "saved") renderSavedBookmarks();
        initBookmarkBtns();
      });
    return bookmarkSyncPromise;
  }
  async function persistBookmarkAdd(item) {
    if (!bookmarkAccountUser) return;
    const resp = await fetchJson("/api/user/bookmarks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: item.url, title: item.title, snippet: item.snippet }),
    });
    if (resp.ok && resp.data && resp.data.id != null) {
      bookmarkServerIds.set(item.url, resp.data.id);
      return;
    }
    if (resp.status !== 401) {
      showToast(userFacingApiError(resp.data && resp.data.error, "Bookmark saved locally, but account sync failed."), "error");
    }
  }
  async function persistBookmarkRemove(url) {
    if (!bookmarkAccountUser) return;
    const id = bookmarkServerIds.get(url);
    const target = id != null
      ? `/api/user/bookmarks/${encodeURIComponent(String(id))}`
      : `/api/user/bookmarks?url=${encodeURIComponent(url)}`;
    const resp = await fetchJson(target, { method: "DELETE" });
    if (resp.ok) {
      bookmarkServerIds.delete(url);
      return;
    }
    if (resp.status !== 401) {
      showToast(userFacingApiError(resp.data && resp.data.error, "Bookmark removal synced locally, but account sync failed."), "error");
    }
  }
  function addBookmark(url, title, snippet) {
    const item = normalizeBookmarkItem({ url, title, snippet, saved: Date.now() });
    const items = getBookmarks().filter(b => b.url !== url);
    if (item) items.unshift(item);
    saveBookmarks(items);
    if (item) persistBookmarkAdd(item).catch(() => {});
  }
  function removeBookmark(url) {
    saveBookmarks(getBookmarks().filter(b => b.url !== url));
    persistBookmarkRemove(url).catch(() => {});
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
        if (window.__searchType === "saved") renderSavedBookmarks();
      });
    });
  }
  function renderSavedBookmarks() {
    const savedContainer = document.getElementById("saved-results-container");
    if (!savedContainer) return;
    const bookmarks = getBookmarks();
    if (!bookmarks.length) {
      savedContainer.innerHTML = '<p class="no-results">No saved results yet. Click the bookmark icon on any result to save it.</p>';
      return;
    }
    savedContainer.innerHTML = bookmarks.map(b => `
      <article class="result saved-result" data-url="${esc(b.url)}">
        <button class="bookmark-remove-btn" data-url="${esc(b.url)}" aria-label="Remove bookmark" title="Remove">&#10005;</button>
        <a href="${esc(b.url)}" target="_blank" rel="noopener" class="result-title">${esc(b.title)}</a>
        <cite class="result-url">${esc(b.url)}</cite>
        <p class="result-snippet">${esc(b.snippet || "")}</p>
      </article>
    `).join("");
    savedContainer.querySelectorAll(".bookmark-remove-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        removeBookmark(btn.dataset.url);
        renderSavedBookmarks();
        updateBookmarkBadge();
      });
    });
  }

  initBookmarkBtns();
  applySavedResultOrder();
  attachResultDragHandles();
  updateBookmarkBadge();
  if (window.__searchType === "saved") {
    renderSavedBookmarks();
  }
  if (bookmarkAccountUser) {
    syncBookmarksWithServer({ silent: true }).catch(() => {});
  }

  (function initResultFeedback() {
    const container = document.getElementById("results");
    const q = window.__searchQuery;
    const st = window.__searchType || "text";
    if (!container || !q || st === "images" || st === "saved") return;
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".feedback-btn");
      if (!btn) return;
      const article = btn.closest("[data-url]");
      if (!article) return;
      e.preventDefault();
      e.stopPropagation();
      const url = article.dataset.url || "";
      const title = (article.querySelector(".result-title")?.textContent || "").trim();
      const rank = parseInt(article.dataset.rank || "0", 10) || 0;
      const rating = btn.dataset.rating === "up" ? 1 : -1;
      fetch("/api/feedback/result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          query: q,
          search_type: st,
          url,
          title,
          rank,
          rating,
        }),
      }).catch(() => {});
      const wrap = btn.closest(".result-actions");
      if (wrap) {
        wrap.querySelectorAll(".feedback-btn").forEach(b => { b.disabled = true; });
      }
      btn.textContent = "Thanks";
    });
  })();

  (function initUnfilteredLeaderboard() {
    const ol = document.getElementById("leaderboard-list");
    if (!ol) return;
    fetch("/api/unfiltered/leaderboard")
      .then(r => (r.ok ? r.json() : null))
      .then(data => {
        if (!data || !data.ok || !Array.isArray(data.entries)) {
          ol.innerHTML = "";
          return;
        }
        if (!data.entries.length) {
          ol.innerHTML =
            "<li class=\"leaderboard-empty\">No explorers yet â€” full-access searches (safesearch off) add to this list.</li>";
          return;
        }
        ol.innerHTML = data.entries
          .map(
            e => `<li><span class="lb-rank">${esc(e.rank)}</span><span class="lb-label">${esc(
              e.label
            )}</span><span class="lb-score" title="Score">${Number(e.score).toFixed(1)}</span></li>`
          )
          .join("");
      })
      .catch(() => {});
  })();

  (function pingUnfilteredEngagement() {
    const safe = document.getElementById("safesearch-input");
    const cw = document.getElementById("cleanweb-input");
    if (!safe || !cw || safe.value !== "off" || cw.value === "1") return;
    if (!window.__searchQuery) return;
    let pid = "";
    try {
      pid = localStorage.getItem("abbiey_unfiltered_id") || "";
    } catch (_) {}
    if (!pid) {
      try {
        pid = crypto.randomUUID();
        localStorage.setItem("abbiey_unfiltered_id", pid);
      } catch (_) {
        return;
      }
    }
    const sessKey = "abbiey_uf_ping_" + String(window.__searchQuery || "").slice(0, 160);
    try {
      if (sessionStorage.getItem(sessKey)) return;
      sessionStorage.setItem(sessKey, "1");
    } catch (_) {}
    const intent = (document.querySelector(".app-layout") || {}).dataset?.queryIntent || "";
    let depth = 1;
    if (/research/i.test(String(intent))) depth = 3;
    else if (/deep|intent_deep/i.test(String(intent))) depth = 2;
    else if (/quick|instant/i.test(String(intent))) depth = 0.5;
    fetch("/api/unfiltered/activity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ participant_id: pid, depth, receipts: 0 }),
    }).catch(() => {});
  })();

  // ===== Related Searches =====
  const relatedContainer = document.getElementById("related-searches");
  const searchQuery = window.__searchQuery;
  if (relatedContainer && searchQuery) {
    fetch(`/api/related?q=${encodeURIComponent(searchQuery)}`)
      .then(r => r.json())
      .then(items => {
        if (!Array.isArray(items) || !items.length) return;
        let h = `<div class="related-header">Related searches</div><div class="related-pills">`;
        h += items.map(t => `<a href="${buildSearchHref(t)}" class="related-pill">${esc(t)}</a>`).join("");
        h += `</div>`;
        relatedContainer.innerHTML = h;
      })
      .catch(() => {});
  }

  // ===== Knowledge graph (Wikipedia + Wikidata + categories; client-rendered) =====
  (function initKnowledgeGraph() {
    const root = document.getElementById("knowledge-graph-root");
    const q = window.__searchQuery;
    if (!root || !q || window.__searchType !== "text") return;
    if (gs("showCards") === "false") return;
    fetch(`/api/knowledge-graph?q=${encodeURIComponent(q)}`)
      .then(r => r.json())
      .then(data => {
        if (!data || typeof data !== "object") return;
        const topics = Array.isArray(data.topics) ? data.topics : [];
        const cats = Array.isArray(data.categories) ? data.categories : [];
        const wiki = data.wikipedia;
        const hasPanel = document.querySelector(".knowledge-panel");
        const showWikiMini = !hasPanel && wiki && wiki.extract;
        if (!topics.length && !cats.length && !showWikiMini) return;
        let html = `<article class="knowledge-graph-card" aria-label="Knowledge graph">`;
        html += `<div class="kg-header"><span class="kg-title">Knowledge graph</span><span class="kg-sub">Topics and categories from public knowledge bases â€” not a custom crawl.</span></div>`;
        if (showWikiMini) {
          const ex = String(wiki.extract);
          const short = ex.length > 560 ? `${ex.slice(0, 560)}â€¦` : ex;
          html += `<div class="kg-wiki-mini">`;
          if (wiki.image_url) {
            html += `<img src="${esc(wiki.image_url)}" alt="" class="kg-wiki-thumb" loading="lazy"/>`;
          }
          html += `<div class="kg-wiki-mini-text"><h3 class="kg-wiki-title">${esc(wiki.title)}</h3>`;
          html += `<p class="kg-wiki-extract">${esc(short)}</p>`;
          if (wiki.page_url) {
            html += `<a class="kg-wiki-more" href="${esc(wiki.page_url)}" target="_blank" rel="noopener">Read on Wikipedia â†’</a>`;
          }
          html += `</div></div>`;
        }
        if (topics.length) {
          html += `<div class="kg-block"><span class="kg-block-label">Related topics</span><div class="kg-pills">`;
          topics.forEach(t => {
            html += `<a class="kg-pill" href="${buildSearchHref(t, { type: "text" })}">${esc(t)}</a>`;
          });
          html += `</div></div>`;
        }
        if (cats.length) {
          html += `<div class="kg-block"><span class="kg-block-label">Wikipedia categories</span><div class="kg-pills kg-pills-muted">`;
          cats.forEach(c => {
            html += `<a class="kg-pill" href="/search?q=${encodeURIComponent(c)}&type=text">${esc(c)}</a>`;
          });
          html += `</div></div>`;
        }
        html += `</article>`;
        root.innerHTML = html;
        root.hidden = false;
      })
      .catch(() => {});
  })();

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

    const resultsEl = document.getElementById("trending-searches");
    if (!resultsEl) return;

    fetch("/api/trends")
      .then(r => r.json())
      .then(items => {
        if (!Array.isArray(items) || !items.length) return;
        renderTrending(resultsEl, items.slice(0, 6), true);
      })
      .catch(() => {});
  })();

  // ===== Recent Search History Chips =====
  (function initRecentSearches() {
    const container = document.getElementById("recent-searches-home");
    if (!container) return;
    // Only show if user is logged in (avatar chip present)
    if (!document.querySelector(".user-avatar-chip")) return;
    fetch("/api/user/recent-searches")
      .then(r => r.ok ? r.json() : [])
      .then(items => {
        if (!Array.isArray(items) || !items.length) return;
        const chips = items.map(item =>
          `<button class="recent-search-chip" data-query="${esc(item.query)}" data-type="${esc(item.type || 'text')}">${esc(item.query)}</button>`
        ).join("");
        container.innerHTML =
          `<div class="trending-header">
            ${ICON_SEARCH_GLASS_SVG}
            Recent
          </div>
          <div class="trending-pills">${chips}</div>`;
        container.style.display = "";
        container.querySelectorAll(".recent-search-chip").forEach(chip => {
          chip.addEventListener("click", () => {
            const q = document.querySelector("input[name='q']");
            const typeInput = document.getElementById("type-input") || document.querySelector("input[name='type']");
            const form = document.querySelector(".search-form") || document.querySelector("form[action]");
            if (q) q.value = chip.dataset.query;
            if (typeInput) typeInput.value = chip.dataset.type;
            if (form) form.submit();
          });
        });
      })
      .catch(() => {});
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
    /** Committed finals for this mic session (see result handler). */
    let voiceFinalAccum = "";

    if (!input) return;

    function startListening() {
      listening = true;
      voiceFinalAccum = "";
      voiceBtn.classList.add("listening");
      micIcon.style.display  = "none";
      stopIcon.style.display = "";
      voiceBtn.setAttribute("aria-label", "Stop listening");
      voiceBtn.title = "Stop listening";
      recognition.start();
    }

    function stopListening() {
      listening = false;
      voiceBtn.classList.remove("listening");
      micIcon.style.display  = "";
      stopIcon.style.display = "none";
      voiceBtn.setAttribute("aria-label", "Search by voice");
      voiceBtn.title = "Voice search";
      recognition.stop();
    }

    voiceBtn.addEventListener("click", () => {
      if (listening) stopListening();
      else startListening();
    });

    recognition.addEventListener("result", (e) => {
      // Build transcript like MDN: only new slices (resultIndex), keep finals across
      // events, and recompute interim each fire so refinements do not duplicate text.
      // Joining every result with "" used to glue words ("hello" + "world" â†’ "helloworld").
      let interimTranscript = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        const piece = res[0] ? res[0].transcript : "";
        if (res.isFinal) {
          const needsSpace =
            voiceFinalAccum &&
            piece &&
            !/\s$/.test(voiceFinalAccum) &&
            !/^\s/.test(piece);
          voiceFinalAccum += (needsSpace ? " " : "") + piece;
        } else {
          interimTranscript += piece;
        }
      }
      const transcript = (voiceFinalAccum + interimTranscript).replace(/\s{2,}/g, " ");
      input.value = transcript;
      const last = e.results[e.results.length - 1];
      if (last && last.isFinal) {
        stopListening();
        const form = document.getElementById("search-form");
        if (transcript.trim() && form) form.submit();
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

  // ===== Home: Web / Images / News / Videos before first query =====
  (function initReverseImageSearch() {
    const btn = document.getElementById("reverse-image-btn");
    const panel = document.getElementById("reverse-image-panel");
    const urlEntryBtn = document.getElementById("reverse-image-url-entry");
    const pickBtn = document.getElementById("reverse-image-pick-btn");
    const closeBtn = document.getElementById("reverse-image-close");
    const submitBtn = document.getElementById("reverse-image-submit");
    const urlInput = document.getElementById("reverse-image-url");
    const fileInput = document.getElementById("reverse-image-file");
    const capInput = document.getElementById("reverse-image-caption");
    const fileHint = document.getElementById("reverse-image-file-hint");
    if (!btn || !panel || !fileInput) return;

    let busy = false;

    function isLikelyMobileImagePicker() {
      const ua = navigator.userAgent || "";
      return /Android|iPhone|iPad|iPod|Mobile/i.test(ua);
    }

    async function openPreferredImagePicker(input) {
      if (!input) return;
      input.setAttribute("accept", "image/*");
      try {
        if (!isLikelyMobileImagePicker() && typeof window.showOpenFilePicker === "function") {
          const [handle] = await window.showOpenFilePicker({
            multiple: false,
            excludeAcceptAllOption: true,
            startIn: "pictures",
            types: [
              {
                description: "Images",
                accept: {
                  "image/*": [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg", ".avif", ".heic", ".heif", ".ico", ".tif", ".tiff"],
                },
              },
            ],
          });
          if (!handle) return;
          const file = await handle.getFile();
          const dt = new DataTransfer();
          dt.items.add(file);
          input.files = dt.files;
          input.dispatchEvent(new Event("change", { bubbles: true }));
          return;
        }
      } catch (_err) {
        // Fall through to browser-native file input when the File System Access API is unavailable or cancelled.
      }
      if (typeof input.showPicker === "function") {
        try {
          await input.showPicker();
          return;
        } catch (_err) {
          // Fall through to click() when showPicker is unsupported or blocked.
        }
      }
      input.click();
    }

    window.openPreferredImagePicker = openPreferredImagePicker;

    function openImageFilePicker() {
      fileInput.value = "";
      if (fileHint) fileHint.textContent = "";
      return openPreferredImagePicker(fileInput);
    }

    function setOpen(open) {
      panel.hidden = !open;
      urlEntryBtn?.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        requestAnimationFrame(() => {
          urlInput?.focus();
        });
      }
    }

    function setBusy(on) {
      busy = on;
      btn.setAttribute("aria-busy", on ? "true" : "false");
      submitBtn?.setAttribute("aria-busy", on ? "true" : "false");
    }

    async function runReverseImageSubmit() {
      if (busy) return;
      if (typeof window.visSubmitReverseImage === "function") {
        setBusy(true);
        try {
          await window.visSubmitReverseImage({
            source: "panel",
            url: (urlInput?.value || "").trim(),
            file: fileInput.files?.[0],
            caption: (capInput?.value || "").trim(),
          });
        } finally {
          setBusy(false);
        }
        return;
      }
      const cap = (capInput?.value || "").trim();
      const file = fileInput.files && fileInput.files[0];
      const url = (urlInput?.value || "").trim();
      if (!file && !url) {
        const errEl = document.getElementById("reverse-image-url-error");
        if (errEl) {
          errEl.textContent = "Paste a direct image URL or upload a photo.";
          errEl.hidden = false;
          errEl.classList.add("is-visible");
        } else if (typeof window.showToast === "function") {
          window.showToast("Paste a direct image URL or upload a photo.", "error");
        }
        return;
      }
      if (fileHint) fileHint.textContent = file ? "Searchingâ€¦" : "";
      setBusy(true);
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
          if (typeof window.showToast === "function") {
            window.showToast(data.message || data.error || "Could not look up that image.", "error");
          }
          fileInput.value = "";
          if (fileHint) fileHint.textContent = "";
          return;
        }
        if (data.redirect) window.location.href = data.redirect;
      } finally {
        setBusy(false);
        if (fileHint && fileHint.textContent === "Searchingâ€¦") fileHint.textContent = "";
      }
    }

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (busy) return;
      openImageFilePicker();
    });

    pickBtn?.addEventListener("click", () => {
      if (busy) return;
      openImageFilePicker();
    });

    urlEntryBtn?.addEventListener("click", () => {
      if (busy) return;
      setOpen(panel.hidden);
    });

    closeBtn?.addEventListener("click", () => {
      setOpen(false);
      urlEntryBtn?.focus();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !panel.hidden) {
        setOpen(false);
        urlEntryBtn?.focus();
      }
    });

    fileInput.addEventListener("change", () => {
      const f = fileInput.files && fileInput.files[0];
      if (!f) return;
      if (typeof window.visHandleReverseFile === "function") {
        window.visHandleReverseFile(f, "panel");
        return;
      }
      if (fileHint) fileHint.textContent = f.name || "Selected";
      runReverseImageSubmit();
    });

    submitBtn?.addEventListener("click", () => runReverseImageSubmit());
  })();

  (function initHomeSearchModes() {
    const row = document.querySelector(".home-search-modes-row");
    const typeInput = document.getElementById("search-type-input");
    if (!row || !typeInput) return;

    function syncPressed(activeBtn) {
      row.querySelectorAll(".home-mode-btn").forEach((b) => {
        const on = b === activeBtn;
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
    }

    const initial = (typeInput.value || "text").trim() || "text";
    const match = row.querySelector(`.home-mode-btn[data-search-mode="${initial}"]`);
    if (match) syncPressed(match);

    row.addEventListener("click", (e) => {
      const btn = e.target.closest(".home-mode-btn");
      if (!btn || !row.contains(btn)) return;
      const mode = (btn.dataset.searchMode || "").trim();
      if (!mode) return;
      const activateMode = () => {
        typeInput.value = mode;
        syncPressed(btn);
      };
      if (isTorSearchMode(mode) && !torAgreementGate.isApproved()) {
        torAgreementGate.ensureAgreement(activateMode);
        return;
      }
      activateMode();
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

  // ===== SERP category tabs: href q= matches live search box =====
  (function initSearchTabHrefSync() {
    const tabsRoot = document.querySelector(".search-tabs");
    const searchInput = document.getElementById("search-input");
    if (!tabsRoot || !searchInput) return;

    function patchAnchorHref(a) {
      const raw = a.getAttribute("href");
      if (!raw || raw.startsWith("#")) return;
      try {
        const u = new URL(raw, window.location.origin);
        if (!u.pathname.startsWith("/search")) return;
        const q = searchInput.value.trim();
        if (q) u.searchParams.set("q", q);
        else u.searchParams.delete("q");
        a.setAttribute("href", u.pathname + u.search + u.hash);
      } catch (_) {}
    }

    function syncSearchTabAnchorsFromInput() {
      tabsRoot.querySelectorAll(".search-tabs-scroll a.tab[href]").forEach(patchAnchorHref);
      const menu = document.getElementById("tab-more-menu");
      if (menu) menu.querySelectorAll("a[href^='/search']").forEach(patchAnchorHref);
    }

    function tabNavAnchorFromEventTarget(target) {
      const a = target && target.closest && target.closest("a[href^='/search']");
      if (!a || !tabsRoot.contains(a)) return null;
      const inScroll = a.closest(".search-tabs-scroll");
      const inMenu = document.getElementById("tab-more-menu")?.contains(a);
      if (inScroll && a.classList.contains("tab")) return a;
      if (inMenu && (a.classList.contains("tab-more-item") || a.classList.contains("tab-more-mybot-item"))) return a;
      return null;
    }

    tabsRoot.addEventListener(
      "focusin",
      (e) => {
        if (tabNavAnchorFromEventTarget(e.target)) syncSearchTabAnchorsFromInput();
      },
      true
    );
    tabsRoot.addEventListener(
      "pointerdown",
      (e) => {
        if (tabNavAnchorFromEventTarget(e.target)) syncSearchTabAnchorsFromInput();
      },
      true
    );
    tabsRoot.addEventListener(
      "click",
      (e) => {
        const anchor = tabNavAnchorFromEventTarget(e.target);
        if (!anchor) return;
        if (isTorSearchMode(searchTypeFromHref(anchor.href)) && !torAgreementGate.isApproved()) {
          e.preventDefault();
          torAgreementGate.ensureAgreement(() => {
            window.location.assign(anchor.href);
          });
          return;
        }
        if (!searchInput.value.trim()) {
          e.preventDefault();
          searchInput.focus();
        }
      },
      true
    );

    let tabHrefTimer = null;
    searchInput.addEventListener("input", () => {
      clearTimeout(tabHrefTimer);
      tabHrefTimer = window.setTimeout(() => {
        syncSearchTabAnchorsFromInput();
      }, motionDelay(120));
    });

    syncSearchTabAnchorsFromInput();
  })();

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

/** Match Jinja `url|domain` (urlparse netloc) for display; favicon CDN still uses hostname. */
function displayNetloc(url) {
  try {
    return new URL(url).host || "";
  } catch {
    return "";
  }
}

function faviconImg(url) {
  try {
    const host = new URL(url).hostname;
    return `<img class="result-favicon" src="https://icons.duckduckgo.com/ip3/${esc(host)}/favicon.ico" onerror="this.style.display='none'" alt="" loading="lazy">`;
  } catch { return ""; }
}

/** Matches server-rendered `result-domain-row` in index.html (text/news/etc.). */
function resultDomainRow(url, sourceType, sourceLabel) {
  const host = displayNetloc(url);
  const st = (sourceType && String(sourceType).trim()) || "";
  const stClass = st.replace(/[^\w-]/g, "");
  const badge = st
    ? `<span class="source-type-badge${stClass ? ` source-type-${stClass}` : ""}">${esc(st)}</span>`
    : "";
  const src = sourceLabel ? `<span class="result-source-label">${esc(sourceLabel)}</span>` : "";
  return `<div class="result-domain-row">${faviconImg(url)}<span class="result-domain">${esc(host)}</span>${badge}${src}</div>`;
}

(function () {
  "use strict";

  const root = document.getElementById("dashboard-root");
  if (!root) return;

  const MODE_LABELS = {
    text: "All",
    images: "Images",
    news: "News",
    videos: "Videos",
    people: "People",
    email: "Email",
    business: "Business",
    onion: "Onion / Tor",
    code: "Code",
  };

  const ENTITY_BADGE = {
    email: "@",
    ip: "IP",
    domain: "URL",
    phone: "TEL",
    username: "@",
    person: "ID",
    crypto: "₿",
    mac: "MAC",
    coordinates: "GEO",
    hashtag: "#",
    address: "ADR",
  };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function searchHref(q, type) {
    const params = new URLSearchParams();
    params.set("q", q);
    if (type && type !== "text") params.set("type", type);
    return "/search?" + params.toString();
  }

  function formatMode(type) {
    return MODE_LABELS[type] || type || "All";
  }

  function renderEmpty(el, msg) {
    el.innerHTML = '<p class="dashboard-empty">' + esc(msg) + "</p>";
  }

  function renderList(el, items, renderItem) {
    if (!items || !items.length) {
      renderEmpty(el, "Nothing here yet — start searching.");
      return;
    }
    const ul = document.createElement("ul");
    ul.className = "dashboard-list";
    items.forEach(function (item) {
      const li = document.createElement("li");
      li.className = "dashboard-list-item";
      li.innerHTML = renderItem(item);
      ul.appendChild(li);
    });
    el.innerHTML = "";
    el.appendChild(ul);
  }

  function patchWidget(id, items, renderItem, emptyMsg) {
    const widget = document.getElementById(id);
    if (!widget) return;
    const old = widget.querySelector(".dashboard-empty, ul, .dashboard-widget-body");
    if (old) old.remove();
    const holder = document.createElement("div");
    holder.className = "dashboard-widget-body";
    widget.appendChild(holder);
    if (!items || !items.length) {
      renderEmpty(holder, emptyMsg || "Nothing here yet.");
      return;
    }
    renderList(holder, items, renderItem);
  }

  function loadGuestLocal() {
    const wrap = document.getElementById("dashboard-guest-local");
    const list = document.getElementById("dashboard-local-history");
    if (!wrap || !list) return;
    let queries = [];
    try {
      const raw = localStorage.getItem("abbiey_search_history");
      if (raw) queries = JSON.parse(raw);
    } catch (_) {}
    if (!Array.isArray(queries) || !queries.length) return;
    wrap.hidden = false;
    renderList(
      list,
      queries.slice(0, 6).map(function (q) {
        return { query: String(q).trim(), type: "text" };
      }),
      function (item) {
        return (
          '<a href="' +
          esc(searchHref(item.query, item.type)) +
          '"><span class="dashboard-list-query">' +
          esc(item.query) +
          '</span><span class="dashboard-list-meta">On this device</span></a>'
        );
      }
    );
  }

  function emphasizeWidgets(focusModes) {
    if (!focusModes || !focusModes.length) return;
    const top = focusModes[0].type;
    const map = {
      email: "widget-entities",
      onion: "widget-searches",
      people: "widget-searches",
      images: "widget-bookmarks",
    };
    const id = map[top];
    if (!id) return;
    const widget = document.getElementById(id);
    if (widget) widget.classList.add("dashboard-widget--emphasis");
  }

  function renderDashboard(data) {
    const title = document.getElementById("dashboard-greeting-title");
    const sub = document.getElementById("dashboard-greeting-sub");
    const pct = document.getElementById("dashboard-activity-pct");
    const fill = document.getElementById("dashboard-activity-fill");
    const statsEl = document.getElementById("dashboard-stats");
    const focusEl = document.getElementById("dashboard-focus");

    const name = (data.user && data.user.display_name) || (data.user && data.user.username) || "there";
    if (title) title.textContent = "Welcome back, " + name;
    if (sub) sub.textContent = "Your personalized search environment on a bee kay.";

    const score = data.activity_score || 0;
    if (pct) pct.textContent = score + "%";
    if (fill) fill.style.width = Math.min(100, score) + "%";

    if (statsEl && data.stats) {
      const s = data.stats;
      statsEl.innerHTML =
        '<div class="dashboard-stat"><div class="dashboard-stat-val">' +
        esc(String(s.searches_7d || 0)) +
        '</div><div class="dashboard-stat-label">Searches (7d)</div></div>' +
        '<div class="dashboard-stat"><div class="dashboard-stat-val">' +
        esc(String(s.bookmarks || 0)) +
        '</div><div class="dashboard-stat-label">Bookmarks</div></div>' +
        '<div class="dashboard-stat"><div class="dashboard-stat-val">' +
        esc(String(s.cases || 0)) +
        '</div><div class="dashboard-stat-label">Investigations</div></div>' +
        '<div class="dashboard-stat"><div class="dashboard-stat-val">' +
        esc(String(s.history || 0)) +
        '</div><div class="dashboard-stat-label">Total searches</div></div>';
    }

    if (focusEl && data.focus_modes && data.focus_modes.length) {
      focusEl.hidden = false;
      focusEl.innerHTML = data.focus_modes
        .map(function (m) {
          return (
            '<span class="dashboard-focus-pill">' +
            esc(formatMode(m.type)) +
            " · " +
            esc(String(m.count)) +
            "</span>"
          );
        })
        .join("");
      emphasizeWidgets(data.focus_modes);
    }

    patchWidget(
      "widget-searches",
      data.recent_searches,
      function (item) {
        return (
          '<a href="' +
          esc(searchHref(item.query, item.type)) +
          '"><span class="dashboard-list-query">' +
          esc(item.query) +
          '</span><span class="dashboard-list-meta">' +
          esc(formatMode(item.type)) +
          "</span></a>"
        );
      },
      "No recent searches yet."
    );

    patchWidget(
      "widget-bookmarks",
      data.recent_bookmarks,
      function (item) {
        const btitle = item.title || item.url || "Bookmark";
        const url = item.url || "#";
        return (
          '<a href="' +
          esc(url) +
          '" target="_blank" rel="noopener noreferrer"><span class="dashboard-list-query">' +
          esc(btitle) +
          '</span><span class="dashboard-list-meta">' +
          esc(url) +
          "</span></a>"
        );
      },
      "No bookmarks saved yet."
    );

    patchWidget(
      "widget-cases",
      data.cases,
      function (item) {
        const ctitle = item.title || "Untitled investigation";
        const meta = item.item_count != null ? item.item_count + " items" : "";
        return (
          '<a href="/profile#cases-section"><div class="dashboard-case-card"><p class="dashboard-case-title">' +
          esc(ctitle) +
          '</p><p class="dashboard-case-meta">' +
          esc(meta) +
          "</p></div></a>"
        );
      },
      "No investigations yet."
    );

    patchWidget(
      "widget-entities",
      data.entity_hints,
      function (item) {
        const badge = ENTITY_BADGE[item.type] || item.type.slice(0, 3).toUpperCase();
        return (
          '<a href="' +
          esc(searchHref(item.value, item.type === "email" ? "email" : "text")) +
          '"><div class="dashboard-entity-hint"><span class="dashboard-entity-badge">' +
          esc(badge) +
          '</span><div><div class="dashboard-entity-value">' +
          esc(item.value) +
          '</div><div class="dashboard-entity-type">' +
          esc(item.type) +
          "</div></div></div></a>"
        );
      },
      "Search for emails, IPs, or domains to see entity hints here."
    );
  }

  if (root.dataset.loggedIn !== "true") {
    loadGuestLocal();
    return;
  }

  fetch("/api/user/dashboard", { credentials: "same-origin" })
    .then(function (r) {
      if (!r.ok) throw new Error("load failed");
      return r.json();
    })
    .then(renderDashboard)
    .catch(function () {
      const sub = document.getElementById("dashboard-greeting-sub");
      if (sub) sub.textContent = "Could not load your dashboard. Try refreshing.";
    });
})();

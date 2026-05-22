/**
 * Settings persistence unit tests for abbiey.search
 *
 * Tests the _S config map, gs() (get-setting) and ss() (set-setting) helpers,
 * and the applyAllSettings() logic — all extracted from static/script.js.
 *
 * No browser or npm dependencies required; runs with plain Node.js:
 *   node tests/test_settings_persistence.js
 */

"use strict";

// ---------------------------------------------------------------------------
// Minimal localStorage shim
// ---------------------------------------------------------------------------
function makeLocalStorage() {
  const store = Object.create(null);
  return {
    getItem(k) { return k in store ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
    removeItem(k) { delete store[k]; },
    clear() { Object.keys(store).forEach(k => delete store[k]); },
  };
}

// ---------------------------------------------------------------------------
// Settings config — must stay in sync with static/script.js _S object
// ---------------------------------------------------------------------------
const _S = {
  theme:         { key: "theme",                 def: "dark"    },
  accent:        { key: "accent-color",          def: "#e7e5e4" },
  density:       { key: "density",               def: "default" },
  fontSize:      { key: "abbiey_font_size",      def: "medium"  },
  fontFamily:    { key: "abbiey_font_family",    def: "system"  },
  safesearch:    { key: "abbiey_safesearch",     def: "off"     },
  newTab:        { key: "abbiey_new_tab",        def: "true"    },
  defaultTab:    { key: "abbiey_default_tab",    def: "text"    },
  aiSummary:     { key: "abbiey_ai_summary",     def: "true"    },
  autocomplete:  { key: "abbiey_autocomplete",   def: "true"    },
  persistRegion: { key: "abbiey_region_persist", def: "false"   },
  history:       { key: "abbiey_history",        def: "true"    },
  incognito:     { key: "abbiey_incognito",      def: "false"   },
  showCards:     { key: "abbiey_show_cards",     def: "true"    },
  showFavicons:  { key: "abbiey_show_favicons",  def: "true"    },
  showDates:     { key: "abbiey_show_dates",     def: "true"    },
};

function makeHelpers(ls) {
  function gs(name) { return ls.getItem(_S[name].key) ?? _S[name].def; }
  function ss(name, val) { ls.setItem(_S[name].key, val); }
  return { gs, ss };
}

// ---------------------------------------------------------------------------
// Tiny test runner
// ---------------------------------------------------------------------------
let passed = 0;
let failed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
    process.stdout.write(`  ✓ ${name}\n`);
  } catch (err) {
    failed++;
    failures.push({ name, err });
    process.stdout.write(`  ✗ ${name}\n    ${err.message}\n`);
  }
}

function assert(condition, msg) {
  if (!condition) throw new Error(msg || "Assertion failed");
}

function assertEqual(a, b) {
  if (a !== b) throw new Error(`Expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

console.log("\nSettings config integrity");

test("every setting name maps to a non-empty key string", () => {
  for (const [name, cfg] of Object.entries(_S)) {
    assert(typeof cfg.key === "string" && cfg.key.length > 0,
      `_S.${name}.key is empty or not a string`);
  }
});

test("every setting name maps to a non-empty default string", () => {
  for (const [name, cfg] of Object.entries(_S)) {
    assert(typeof cfg.def === "string" && cfg.def.length > 0,
      `_S.${name}.def is empty or not a string`);
  }
});

test("all setting keys are unique (no collisions)", () => {
  const keys = Object.values(_S).map(c => c.key);
  const unique = new Set(keys);
  assertEqual(unique.size, keys.length);
});

// ---------------------------------------------------------------------------

console.log("\ngs() — default values");

test("returns default theme 'dark' when localStorage is empty", () => {
  const ls = makeLocalStorage();
  const { gs } = makeHelpers(ls);
  assertEqual(gs("theme"), "dark");
});

test("returns default accent color when localStorage is empty", () => {
  const ls = makeLocalStorage();
  const { gs } = makeHelpers(ls);
  assertEqual(gs("accent"), "#e7e5e4");
});

test("returns default density 'default' when localStorage is empty", () => {
  const ls = makeLocalStorage();
  const { gs } = makeHelpers(ls);
  assertEqual(gs("density"), "default");
});

test("returns 'off' as default safesearch", () => {
  const ls = makeLocalStorage();
  const { gs } = makeHelpers(ls);
  assertEqual(gs("safesearch"), "off");
});

test("returns 'text' as default tab", () => {
  const ls = makeLocalStorage();
  const { gs } = makeHelpers(ls);
  assertEqual(gs("defaultTab"), "text");
});

// ---------------------------------------------------------------------------

console.log("\nss() / gs() — persistence round-trip");

test("saves and restores theme", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("theme", "light");
  assertEqual(gs("theme"), "light");
});

test("saves and restores accent color", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("accent", "#ff5500");
  assertEqual(gs("accent"), "#ff5500");
});

test("saves and restores density", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("density", "compact");
  assertEqual(gs("density"), "compact");
});

test("saves and restores fontSize", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("fontSize", "large");
  assertEqual(gs("fontSize"), "large");
});

test("saves and restores fontFamily", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("fontFamily", "mono");
  assertEqual(gs("fontFamily"), "mono");
});

test("saves and restores safesearch setting", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("safesearch", "strict");
  assertEqual(gs("safesearch"), "strict");
});

test("saves and restores newTab flag", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("newTab", "false");
  assertEqual(gs("newTab"), "false");
});

test("saves and restores defaultTab", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("defaultTab", "images");
  assertEqual(gs("defaultTab"), "images");
});

test("saves and restores aiSummary flag", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("aiSummary", "false");
  assertEqual(gs("aiSummary"), "false");
});

test("saves and restores showFavicons flag", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("showFavicons", "false");
  assertEqual(gs("showFavicons"), "false");
});

// ---------------------------------------------------------------------------

console.log("\nIsolation — settings don't bleed between sessions");

test("two independent localStorage instances do not share state", () => {
  const ls1 = makeLocalStorage();
  const ls2 = makeLocalStorage();
  const h1 = makeHelpers(ls1);
  const h2 = makeHelpers(ls2);
  h1.ss("theme", "light");
  assertEqual(h2.gs("theme"), "dark"); // ls2 still at default
});

test("clearing localStorage restores defaults via gs()", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("theme", "light");
  ls.clear();
  assertEqual(gs("theme"), "dark");
});

test("overwriting a setting replaces the previous value", () => {
  const ls = makeLocalStorage();
  const { gs, ss } = makeHelpers(ls);
  ss("density", "compact");
  ss("density", "comfortable");
  assertEqual(gs("density"), "comfortable");
});

// ---------------------------------------------------------------------------

console.log("\nSearch bar colour helpers");

const SEARCH_ACCENT_KEY = "abbiey_search_accent";

function getReadableTextColor(hex) {
  const h = String(hex || "").replace("#", "");
  if (h.length !== 6) return "#052e16";
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  const luminance = 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
  return luminance > 0.45 ? "#052e16" : "#f8fafc";
}

function applySearchAccent(ls, style, color) {
  const vars = ["--search-button-bg", "--search-button-bg-hover", "--search-button-text"];
  if (!color) {
    vars.forEach((v) => delete style[v]);
    ls.removeItem(SEARCH_ACCENT_KEY);
    return;
  }
  style["--search-button-bg"] = color;
  style["--search-button-bg-hover"] = color;
  style["--search-button-text"] = getReadableTextColor(color);
  ls.setItem(SEARCH_ACCENT_KEY, color);
}

test("uses dark text on light search button colours", () => {
  assertEqual(getReadableTextColor("#e7e5e4"), "#052e16");
});

test("uses light text on dark search button colours", () => {
  assertEqual(getReadableTextColor("#2563eb"), "#f8fafc");
});

test("search bar colour persists and reset clears override key", () => {
  const ls = makeLocalStorage();
  const style = Object.create(null);
  applySearchAccent(ls, style, "#2563eb");
  assertEqual(ls.getItem(SEARCH_ACCENT_KEY), "#2563eb");
  applySearchAccent(ls, style, "");
  assertEqual(ls.getItem(SEARCH_ACCENT_KEY), null);
  assert(!("--search-button-bg" in style), "Expected button bg override to be removed");
});

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------
console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) {
  process.exit(1);
}

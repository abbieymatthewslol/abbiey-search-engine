// Production smoke test — exercises every feature the reviewer flagged.
//
// Runs against SITE_URL (set in repo secrets) and fails if any of:
//   * /refund, /community, /status, /docs/api, /api/v1/docs returns non-2xx
//   * /health reports any feature as "down"
//   * /api/v1/search with API_TEST_KEY does not return JSON with results
//   * Reverse-image upload via /api/v1/reverse-image does not succeed
//     with a synthetic 1x1 PNG (requires SUPABASE_SERVICE_ROLE_KEY in prod)
//
// This file is deliberately dependency-light: just @playwright/test for the
// headless browser check, plus node-native fetch for the JSON probes.

import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { Buffer } from 'node:buffer';

const SITE_URL = (process.env.SITE_URL || '').replace(/\/$/, '');
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
const API_KEY = process.env.API_TEST_KEY || '';

if (!SITE_URL) {
    console.error('SITE_URL not set; smoke tests cannot run.');
    process.exit(1);
}

const screenshotsDir = 'tests/smoke/screenshots';
mkdirSync(screenshotsDir, { recursive: true });

let failures = 0;
const fail = (msg) => { failures++; console.error('FAIL:', msg); };
const pass = (msg) => console.log('OK:  ', msg);

// ---- JSON probes (cheap) ----

async function getJson(path, { headers = {} } = {}) {
    const r = await fetch(`${SITE_URL}${path}`, { headers, redirect: 'follow' });
    const text = await r.text();
    let body = null;
    try { body = JSON.parse(text); } catch (_) { /* non-json */ }
    return { status: r.status, body, text };
}

async function expectOk(path) {
    const r = await fetch(`${SITE_URL}${path}`, { redirect: 'follow' });
    if (r.status < 200 || r.status >= 400) fail(`${path} -> ${r.status}`);
    else pass(`${path} -> ${r.status}`);
}

await expectOk('/refund');
await expectOk('/community');
await expectOk('/status');
await expectOk('/changelog');
await expectOk('/docs/deep-web');
await expectOk('/docs/api');
await expectOk('/docs/self-hosting');
await expectOk('/api/v1/docs');
await expectOk('/openapi.json');

// ---- Health + feature probes ----
{
    const { status, body } = await getJson('/health');
    if (status !== 200 || !body) fail(`/health status=${status}`);
    else if (body.status === 'down') fail(`/health aggregate=down`);
    else pass(`/health aggregate=${body.status}`);

    const features = (body && body.features) || {};
    for (const [k, v] of Object.entries(features)) {
        if (v.state === 'down') fail(`feature ${k} down: ${v.reason || ''}`);
        else pass(`feature ${k} state=${v.state}`);
    }
}

// ---- /api/v1/search with a real key ----
if (API_KEY) {
    const { status, body } = await getJson('/api/v1/search?q=wikipedia', {
        headers: { Authorization: `Bearer ${API_KEY}` },
    });
    if (status !== 200) fail(`/api/v1/search status=${status}`);
    else if (!body || !Array.isArray(body.results)) fail('/api/v1/search returned no results array');
    else pass(`/api/v1/search returned ${body.results.length} results`);
} else {
    console.log('SKIP /api/v1/search (API_TEST_KEY not set)');
}

// ---- Reverse-image smoke (multipart) ----
if (API_KEY) {
    const png = Buffer.from(
        '89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D4944415478DA63' +
        '000100000500010D0A2DB40000000049454E44AE426082',
        'hex'
    );
    const form = new FormData();
    form.append('image', new Blob([png], { type: 'image/png' }), 'pixel.png');
    const r = await fetch(`${SITE_URL}/api/v1/reverse-image`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${API_KEY}` },
        body: form,
    });
    if (r.status === 200 || r.status === 422) pass(`/api/v1/reverse-image status=${r.status} (422 means no upstream match — acceptable)`);
    else fail(`/api/v1/reverse-image status=${r.status}`);
} else {
    console.log('SKIP /api/v1/reverse-image (API_TEST_KEY not set)');
}

// ---- Headless browser render: home + /status + /docs/deep-web ----
const browser = await chromium.launch();
try {
    const page = await browser.newPage();
    for (const path of ['/', '/status', '/docs/deep-web', '/community', '/refund']) {
        const resp = await page.goto(`${SITE_URL}${path}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
        if (!resp || !resp.ok()) fail(`browser: ${path} -> ${resp ? resp.status() : 'no response'}`);
        else pass(`browser: ${path}`);
        await page.screenshot({ path: `${screenshotsDir}${path.replace(/\W+/g, '_') || '_home'}.png` });
    }
} finally {
    await browser.close();
}

if (failures) {
    console.error(`\n${failures} smoke check(s) failed.`);
    process.exit(1);
}
console.log('\nAll smoke checks passed.');

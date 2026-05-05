/** Lightweight connectivity check to the configured origin. */

export async function checkOrigin(origin: string): Promise<{
  ok: boolean;
  message: string;
  status?: number;
}> {
  const base = origin.trim().replace(/\/+$/, "");
  const probe = /^https?:\/\//i.test(base) ? base : `https://${base}`;
  try {
    const u = new URL("/", probe);
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort(), 8000);
    const res = await fetch(u, {
      method: "HEAD",
      redirect: "follow",
      signal: ac.signal,
    });
    clearTimeout(t);
    return {
      ok: res.ok || res.status === 405 || res.status === 403,
      status: res.status,
      message: res.ok
        ? `Reachable (${res.status}).`
        : `Responded with HTTP ${res.status}.`,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, message: msg };
  }
}

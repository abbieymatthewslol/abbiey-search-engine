export type Depth = "quick" | "standard" | "deep-research";
export type Evidence = "links-only" | "key-quotes" | "full-excerpts";
export type AnswerStyle = "direct" | "balanced" | "adversarial";
export type SearchMode = "web" | "research";

export type SearchUrlOptions = {
  origin: string;
  query: string;
  depth?: Depth;
  evidence?: Evidence;
  answerStyle?: AnswerStyle;
  mode?: SearchMode;
  /** Append arbitrary params for experiments or future server-side flags. */
  extra?: Record<string, string>;
};

function normalizeOrigin(origin: string): string {
  const trimmed = origin.trim().replace(/\/+$/, "");
  if (!/^https?:\/\//i.test(trimmed)) {
    return `https://${trimmed}`;
  }
  return trimmed;
}

/** Builds the same `/search?q=` URLs the web experience uses. */
export function buildSearchUrl(opts: SearchUrlOptions): string {
  const origin = normalizeOrigin(opts.origin);
  const u = new URL("/search", origin);
  u.searchParams.set("q", opts.query);

  if (opts.depth) u.searchParams.set("depth", opts.depth);
  if (opts.evidence) u.searchParams.set("evidence", opts.evidence);
  if (opts.answerStyle) u.searchParams.set("answerStyle", opts.answerStyle);
  if (opts.mode === "research") u.searchParams.set("mode", "research");

  for (const [k, v] of Object.entries(opts.extra ?? {})) {
    if (v !== undefined && v !== "") u.searchParams.set(k, v);
  }

  return u.toString();
}

/** ImgOps integration referenced from the web UI for reverse lookup / metadata. */
export function buildImgOpsUrl(imageUrl: string): string {
  const trimmed = imageUrl.trim();
  const encoded = encodeURIComponent(trimmed);
  return `https://imgops.com/${encoded}`;
}

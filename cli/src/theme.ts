/** Minimal styling; respects NO_COLOR / non-TTY / CI. */

const colorEnabled =
  process.stdout.isTTY &&
  process.env.NO_COLOR === undefined &&
  process.env.CI !== "true";

function wrap(code: string, s: string): string {
  if (!colorEnabled) return s;
  return `\u001b[${code}m${s}\u001b[0m`;
}

export const theme = {
  bold: (s: string) => wrap("1", s),
  dim: (s: string) => wrap("2", s),
  accent: (s: string) => wrap("36", s),
  warn: (s: string) => wrap("33", s),
  err: (s: string) => wrap("31", s),
};

export function hr(): string {
  const w = typeof process.stdout.columns === "number" ? process.stdout.columns : 56;
  return theme.dim("─".repeat(Math.min(72, Math.max(32, w))));
}

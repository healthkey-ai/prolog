/**
 * A definition-supplied URL the runner may navigate to: absolute `http(s)`
 * only. Anything else (`javascript:`, `data:`, a relative path, garbage) is
 * dropped rather than rendered as a link — the definition is operator data,
 * but it is the one place it reaches an `href`.
 */
export function httpUrl(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  try {
    const url = new URL(raw);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

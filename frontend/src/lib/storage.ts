/** Browser-token resume (RUN-3): the response id is the only thing stored. */
const PREFIX = "prolog:response:";

export function storedResponseId(slug: string): string | null {
  try {
    return localStorage.getItem(PREFIX + slug);
  } catch {
    return null;
  }
}

export function storeResponseId(slug: string, id: string): void {
  try {
    localStorage.setItem(PREFIX + slug, id);
  } catch {
    /* storage unavailable: the survey still works for this session */
  }
}

export function clearResponseId(slug: string): void {
  try {
    localStorage.removeItem(PREFIX + slug);
  } catch {
    /* ignore */
  }
}

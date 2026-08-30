/**
 * Browser-token resume (RUN-3): the response id is the only thing stored.
 * Surveys with `participation.resume: "none"` keep it for the current tab
 * only (sessionStorage), so a later visitor on the same device never sees it.
 */
const PREFIX = "prolog:response:";

function stores(): Storage[] {
  const out: Storage[] = [];
  try {
    out.push(sessionStorage);
  } catch {
    /* unavailable */
  }
  try {
    out.push(localStorage);
  } catch {
    /* unavailable */
  }
  return out;
}

export function storedResponseId(slug: string): string | null {
  for (const store of stores()) {
    try {
      const id = store.getItem(PREFIX + slug);
      if (id) return id;
    } catch {
      /* ignore */
    }
  }
  return null;
}

export function storeResponseId(slug: string, id: string, persistent = true): void {
  clearResponseId(slug);
  try {
    (persistent ? localStorage : sessionStorage).setItem(PREFIX + slug, id);
  } catch {
    /* storage unavailable: the survey still works for this session */
  }
}

export function clearResponseId(slug: string): void {
  for (const store of stores()) {
    try {
      store.removeItem(PREFIX + slug);
    } catch {
      /* ignore */
    }
  }
}

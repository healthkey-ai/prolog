/**
 * What a participant had typed or ticked but not yet saved, kept across an
 * in-app detour — opening the privacy notice from the email step, say — and
 * nowhere else. Memory only: a reload or a closed tab forgets it, and nothing
 * (an address, above all) touches browser storage.
 */
const scratch = new Map<string, unknown>();

export function recall<T>(key: string): T | undefined {
  return scratch.get(key) as T | undefined;
}

export function remember(key: string, value: unknown): void {
  scratch.set(key, value);
}

export function forget(key: string): void {
  scratch.delete(key);
}

/** Everything, for a test's clean slate; the app forgets by key. */
export function forgetAll(): void {
  scratch.clear();
}

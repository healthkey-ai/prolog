/**
 * Leaving the runner for another page of the site (the theme's `exit_url`):
 * a full page load, since that page is not part of the runner. An object, so
 * a test can watch it (jsdom will not let `location.assign` be replaced).
 */
export const browser = {
  leave(url: string): void {
    window.location.assign(url);
  },
};

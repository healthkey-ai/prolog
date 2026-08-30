import { useEffect } from "react";

/**
 * Keep `document.title` on the survey and the step (WCAG 2.4.2): the browser
 * tab, history entries and the screen reader's page announcement identify the
 * instrument and where the participant is. The previous title (the static one
 * from index.html) comes back when the page unmounts; `undefined` leaves the
 * title alone while the definition is still loading.
 */
export function usePageTitle(title: string | undefined): void {
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);
}

import { useTranslation } from "react-i18next";
import { ApiError } from "@/api/client";
import { Button } from "./ui/button";

/** The message for a definition (or response) that could not be loaded, by status. */
export function definitionErrorKey(error: unknown): string {
  const status = error instanceof ApiError ? error.status : 0;
  if (status === 404) return "app.notFound";
  if (status === 410) return "app.closed";
  if (status === 403) return "app.forbidden";
  if (status === 429) return "app.throttled";
  return "app.error";
}

/** Nothing to retry: the survey is gone, closed, or needs a credential. */
export function definitionErrorTerminal(error: unknown): boolean {
  return error instanceof ApiError && [403, 404, 410].includes(error.status);
}

/**
 * The error screen every page shows when the definition cannot be loaded:
 * the status-mapped message, plus a retry for anything transient (network,
 * throttle, outage) so the participant is never left on "Loading…".
 */
export function DefinitionError({ error, onRetry, retrying }: { error: unknown; onRetry?: () => void; retrying?: boolean }) {
  const { t } = useTranslation();
  return (
    <div className="p-8" data-testid="definition-error">
      <p className="text-error" role="alert">
        {t(definitionErrorKey(error))}
      </p>
      {onRetry && !definitionErrorTerminal(error) && (
        <Button variant="surface" size="runner-sm" className="mt-4" onClick={onRetry} disabled={retrying} data-testid="definition-retry">
          {t("app.retry")}
        </Button>
      )}
    </div>
  );
}

import { Alert, AlertDescription } from "./ui/alert";

/** Validation / save errors pinned above the footer so they never scroll out of view. */
export function ErrorBanner({ errors }: { errors: string[] }) {
  return (
    <div className="border-b border-border bg-card">
      <Alert variant="destructive" role="alert" className="mx-auto max-w-[var(--p-content-max)] rounded-none border-0 bg-transparent px-4 py-2 [&>svg]:hidden" data-testid="error-banner">
        <AlertDescription>
          <ul className="text-sm">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </AlertDescription>
      </Alert>
    </div>
  );
}

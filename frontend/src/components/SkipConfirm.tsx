import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Alert, AlertDescription } from "./ui/alert";
import { Button } from "./ui/button";

export function SkipConfirm({ onSkip, onAnswer }: { onSkip: () => void; onAnswer: () => void }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, []);
  return (
    <div ref={ref} role="alertdialog" aria-labelledby="skip-prompt" className="border-b border-border bg-accent">
      <Alert className="mx-auto flex max-w-[var(--p-content-max)] flex-wrap items-center gap-3 rounded-none border-0 bg-transparent px-4 py-3 [&>svg]:hidden">
        <AlertDescription id="skip-prompt" className="flex-1 text-sm text-foreground">
          {t("skip.prompt")}
        </AlertDescription>
        <Button variant="text" size="runner-sm" onClick={onAnswer}>
          {t("skip.answer")}
        </Button>
        <Button variant="surface" size="runner-sm" onClick={onSkip} data-testid="skip-confirm">
          {t("skip.skip")}
        </Button>
      </Alert>
    </div>
  );
}

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./ui/Button";

export function SkipConfirm({ onSkip, onAnswer }: { onSkip: () => void; onAnswer: () => void }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, []);
  return (
    <div ref={ref} role="alertdialog" aria-labelledby="skip-prompt" className="border-b border-line bg-tint">
      <div className="mx-auto flex max-w-[var(--p-content-max)] flex-wrap items-center gap-3 px-4 py-3">
        <p id="skip-prompt" className="flex-1 text-sm">
          {t("skip.prompt")}
        </p>
        <Button variant="text" onClick={onAnswer} className="min-h-[44px]">
          {t("skip.answer")}
        </Button>
        <Button variant="secondary" onClick={onSkip} className="min-h-[44px]" data-testid="skip-confirm">
          {t("skip.skip")}
        </Button>
      </div>
    </div>
  );
}

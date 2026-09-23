import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { EyeIcon, EyeOffIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { inputClass } from "@/components/renderers/types";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
  testId: string;
}

/**
 * A password field that can be read back.
 *
 * Typing a password you cannot see is where most sign-in failures come from —
 * a pasted string with a character missing, a temporary password from a
 * message. The toggle is a button, not a checkbox, and says which state it
 * will move to, so a screen reader announces something useful.
 */
export function PasswordField({ label, value, onChange, autoComplete, testId }: Props) {
  const { t } = useTranslation();
  const id = useId();
  const [shown, setShown] = useState(false);
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={shown ? "text" : "password"}
          autoComplete={autoComplete}
          className={`${inputClass} pr-12`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testId}
        />
        <button
          type="button"
          onClick={() => setShown((s) => !s)}
          aria-label={shown ? t("password.hide") : t("password.show")}
          aria-pressed={shown}
          className="absolute inset-y-0 right-0 flex min-h-[44px] min-w-[44px] items-center justify-center rounded-[var(--p-radius-input)] text-ink-soft outline-none focus-visible:ring-2 focus-visible:ring-ring"
          data-testid={`${testId}-toggle`}
        >
          {shown ? <EyeOffIcon className="size-5" /> : <EyeIcon className="size-5" />}
        </button>
      </div>
    </div>
  );
}

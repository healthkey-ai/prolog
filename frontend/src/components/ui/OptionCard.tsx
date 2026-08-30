import type { InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

interface OptionCardProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  kind: "radio" | "checkbox";
  label: ReactNode;
  children?: ReactNode;
  inert?: boolean;
}

/** Large tappable option (≥52px) wrapping a real input for accessibility. */
export function OptionCard({ kind, label, children, className, checked, inert, disabled, ...input }: OptionCardProps) {
  return (
    <label
      className={cn(
        "block cursor-pointer rounded-[var(--p-radius-card)] border bg-surface p-4 transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
        checked ? "border-2 border-primary bg-tint" : "border-line hover:bg-tint/60",
        (inert || disabled) && "cursor-not-allowed opacity-50",
        className,
      )}
      data-checked={checked || undefined}
    >
      <span className="flex min-h-[20px] items-start gap-3">
        <input
          type={kind}
          className="mt-1 size-5 shrink-0 accent-primary"
          checked={checked}
          disabled={disabled || inert}
          {...input}
        />
        <span className="flex-1 text-[1.05rem] leading-snug">{label}</span>
      </span>
      {children}
    </label>
  );
}

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "text" | "onPrimary";

const styles: Record<Variant, string> = {
  primary: "bg-primary text-on-primary hover:bg-primary-deep border border-transparent",
  secondary: "bg-surface text-primary border border-line hover:bg-tint",
  text: "bg-transparent text-primary hover:bg-tint border border-transparent",
  onPrimary: "bg-surface text-primary border border-transparent hover:bg-tint",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex min-h-[52px] items-center justify-center gap-2 rounded-[var(--p-radius-button)] px-6 font-heading text-base transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
});

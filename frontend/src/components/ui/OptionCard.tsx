import type { ReactNode } from "react";
import { Checkbox } from "./checkbox";
import { Label } from "./label";
import { RadioGroupItem } from "./radio-group";
import { cn } from "@/lib/utils";

interface OptionCardProps {
  kind: "radio" | "checkbox";
  value: string;
  label: ReactNode;
  checked: boolean;
  /** Checkbox only; radios change through their RadioGroup. */
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  inert?: boolean;
  children?: ReactNode;
  className?: string;
  "data-testid"?: string;
}

/** Large tappable option (≥52px) built on the shadcn RadioGroupItem / Checkbox primitives. */
export function OptionCard({ kind, value, label, checked, onCheckedChange, disabled, inert, children, className, ...rest }: OptionCardProps) {
  const id = `opt-${kind}-${value}`;
  const control =
    kind === "radio" ? (
      <RadioGroupItem id={id} value={value} disabled={disabled || inert} className="mt-0.5 size-5 border-border data-[state=checked]:border-primary" data-testid={rest["data-testid"]} />
    ) : (
      <Checkbox id={id} checked={checked} disabled={disabled || inert} onCheckedChange={(c) => onCheckedChange?.(c === true)} className="mt-0.5 size-5 border-border" data-testid={rest["data-testid"]} />
    );
  return (
    <div
      className={cn(
        "rounded-[var(--p-radius-card)] border bg-card p-4 transition-colors has-[[data-state=checked]]:border-2 has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-accent has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-ring/50",
        checked ? "border-2 border-primary bg-accent" : "border-border hover:bg-accent/60",
        (inert || disabled) && "opacity-50",
        className,
      )}
      data-checked={checked || undefined}
    >
      <div className="flex items-start gap-3">
        {control}
        <Label htmlFor={id} className={cn("flex-1 cursor-pointer text-[1.05rem] font-normal leading-snug", (inert || disabled) && "cursor-not-allowed")}>
          {label}
        </Label>
      </div>
      {children}
    </div>
  );
}

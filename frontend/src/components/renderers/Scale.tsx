import { RadioGroup as RadioGroupPrimitive } from "radix-ui";
import type { RendererProps } from "./types";
import type { ScaleValue } from "@/survey/types";
import { cn } from "@/lib/utils";

/** Segmented scale on the shadcn/Radix RadioGroup primitive (arrow-key navigation, one tab stop). */
export function ScaleControl({
  min,
  max,
  value,
  onSelect,
  name,
  minLabel,
  maxLabel,
  pointLabels,
  ariaLabel,
  labelledBy,
}: {
  min: number;
  max: number;
  value: number | undefined;
  onSelect: (v: number) => void;
  name: string;
  minLabel?: string;
  maxLabel?: string;
  pointLabels?: string[];
  ariaLabel?: string;
  /** Id of a visible label element; takes precedence over `ariaLabel`. */
  labelledBy?: string;
}) {
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  return (
    <div>
      <RadioGroupPrimitive.Root
        value={value === undefined ? "" : String(value)}
        onValueChange={(v) => onSelect(Number(v))}
        aria-labelledby={labelledBy}
        aria-label={labelledBy ? undefined : ariaLabel}
        name={name}
        // Every point shares the row and grows to fill it; they wrap only when
        // they genuinely cannot fit at the 44 px minimum target (WCAG 2.2).
        // A grid with computed column widths wrapped a five-point scale on a
        // wide viewport, because sub-pixel rounding cost auto-fit a column.
        className="flex flex-wrap gap-2"
      >
        {points.map((p, i) => (
          <RadioGroupPrimitive.Item
            key={p}
            value={String(p)}
            data-testid={`scale-${name}-${p}`}
            className={cn(
              "flex min-h-[56px] min-w-[44px] flex-1 basis-[44px] flex-col items-center justify-center rounded-[var(--p-radius-input)] border font-heading text-lg outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
              "border-border bg-card hover:bg-accent data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
            )}
          >
            <span>{p}</span>
            {pointLabels?.[i] && <span className="mt-1 px-1 text-center font-body text-[11px] leading-tight opacity-90">{pointLabels[i]}</span>}
          </RadioGroupPrimitive.Item>
        ))}
      </RadioGroupPrimitive.Root>
      {(minLabel || maxLabel) && (
        <div className="mt-2 flex justify-between text-sm text-muted-foreground">
          <span>{minLabel}</span>
          <span className="text-right">{maxLabel}</span>
        </div>
      )}
    </div>
  );
}

export function Scale({ question, value, onChange }: RendererProps<ScaleValue>) {
  const scale = question.config?.scale;
  if (!scale) return null;
  return (
    <ScaleControl
      min={scale.min}
      max={scale.max}
      value={value?.value}
      onSelect={(v) => onChange({ value: v }, { commit: true })}
      name={question.key}
      minLabel={scale.min_label as string | undefined}
      maxLabel={scale.max_label as string | undefined}
      pointLabels={scale.point_labels as string[] | undefined}
      ariaLabel={question.text as string}
    />
  );
}

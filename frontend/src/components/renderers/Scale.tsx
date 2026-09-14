import { RadioGroup as RadioGroupPrimitive } from "radix-ui";
import type { RendererProps } from "./types";
import { NOT_APPLICABLE, type Rating, type ScaleValue } from "@/survey/types";
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
  notApplicable,
  ariaLabel,
  labelledBy,
}: {
  min: number;
  max: number;
  value: Rating | undefined;
  onSelect: (v: Rating) => void;
  name: string;
  minLabel?: string;
  maxLabel?: string;
  pointLabels?: string[];
  /** A non-scored "not applicable" choice after the last point (matrix rows only). */
  notApplicable?: string;
  ariaLabel?: string;
  /** Id of a visible label element; takes precedence over `ariaLabel`. */
  labelledBy?: string;
}) {
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  const itemClass = cn(
    "flex min-h-[56px] min-w-[44px] flex-1 basis-[44px] flex-col items-center justify-center rounded-[var(--p-radius-input)] border font-heading text-lg outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50",
    "border-border bg-card hover:bg-accent data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground",
  );
  return (
    <div>
      <RadioGroupPrimitive.Root
        value={value === undefined ? "" : String(value)}
        onValueChange={(v) => onSelect(v === NOT_APPLICABLE ? NOT_APPLICABLE : Number(v))}
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
          <RadioGroupPrimitive.Item key={p} value={String(p)} data-testid={`scale-${name}-${p}`} className={itemClass}>
            <span>{p}</span>
            {pointLabels?.[i] && <span className="mt-1 px-1 text-center font-body text-[11px] leading-tight opacity-90">{pointLabels[i]}</span>}
          </RadioGroupPrimitive.Item>
        ))}
        {/* One more item in the same group, so it is chosen the way a point is
            and excludes them the way a point does — but it carries no number:
            it is the respondent saying the row does not apply, not a rating. */}
        {notApplicable && (
          <RadioGroupPrimitive.Item value={NOT_APPLICABLE} data-testid={`scale-${name}-na`} className={cn(itemClass, "font-body text-sm")}>
            <span className="px-1 text-center leading-tight">{notApplicable}</span>
          </RadioGroupPrimitive.Item>
        )}
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
      // A single scale question offers no "not applicable": a respondent skips it instead.
      onSelect={(v) => typeof v === "number" && onChange({ value: v }, { commit: true })}
      name={question.key}
      minLabel={scale.min_label as string | undefined}
      maxLabel={scale.max_label as string | undefined}
      pointLabels={scale.point_labels as string[] | undefined}
      ariaLabel={question.text as string}
    />
  );
}

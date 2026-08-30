import type { RendererProps } from "./types";
import type { ScaleValue } from "@/survey/types";
import { cn } from "@/lib/utils";

export function ScaleControl({
  min,
  max,
  value,
  onSelect,
  name,
  minLabel,
  maxLabel,
  pointLabels,
  disabled,
  ariaLabel,
}: {
  min: number;
  max: number;
  value: number | undefined;
  onSelect: (v: number) => void;
  name: string;
  minLabel?: string;
  maxLabel?: string;
  pointLabels?: string[];
  disabled?: boolean;
  ariaLabel?: string;
}) {
  const points = Array.from({ length: max - min + 1 }, (_, i) => min + i);
  return (
    <div>
      <div role="radiogroup" aria-label={ariaLabel} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
        {points.map((p, i) => (
          <label
            key={p}
            data-testid={`scale-${name}-${p}`}
            className={cn(
              "flex min-h-[56px] cursor-pointer flex-col items-center justify-center rounded-[var(--p-radius-input)] border text-lg font-heading transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
              value === p ? "border-primary bg-primary text-on-primary" : "border-line bg-surface hover:bg-tint",
              disabled && "cursor-not-allowed opacity-50",
            )}
          >
            <input type="radio" name={name} value={p} checked={value === p} disabled={disabled} onChange={() => onSelect(p)} className="sr-only" />
            <span>{p}</span>
            {pointLabels?.[i] && <span className="mt-1 px-1 text-center text-[11px] leading-tight font-body opacity-90">{pointLabels[i]}</span>}
          </label>
        ))}
      </div>
      {(minLabel || maxLabel) && (
        <div className="mt-2 flex justify-between text-sm text-ink-soft">
          <span>{minLabel}</span>
          <span className="text-right">{maxLabel}</span>
        </div>
      )}
    </div>
  );
}

export function Scale({ question, value, onChange, disabled }: RendererProps<ScaleValue>) {
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
      disabled={disabled}
      ariaLabel={question.text as string}
    />
  );
}

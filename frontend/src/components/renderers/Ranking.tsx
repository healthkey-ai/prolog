import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/Button";
import { inputClass, type RendererProps } from "./types";
import type { Option, RankingValue } from "@/survey/types";
import { cn } from "@/lib/utils";

/** Ranking with drag **and** ▲▼ buttons, live position announcements, optional items (Q-6). */
export function Ranking({ question, value, onChange, disabled }: RendererProps<RankingValue>) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  const optional = new Set(question.config?.optional_items ?? []);
  const order = value?.order ?? options.filter((o) => !optional.has(o.key)).map((o) => o.key);
  const unranked = options.filter((o) => optional.has(o.key) && !order.includes(o.key));
  const [announce, setAnnounce] = useState("");
  const labelOf = (key: string) => (options.find((o) => o.key === key)?.label as string) ?? key;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  const commit = (next: string[], otherText = value?.other_text) => {
    const hasFree = next.some((k) => options.find((o) => o.key === k)?.free_text);
    onChange({ order: next, ...(hasFree && otherText ? { other_text: otherText } : {}) }, { commit: true });
  };

  const move = (key: string, delta: number) => {
    const from = order.indexOf(key);
    const to = from + delta;
    if (from < 0 || to < 0 || to >= order.length) return;
    const next = arrayMove(order, from, to);
    setAnnounce(t("ranking.position", { label: labelOf(key), position: to + 1, total: next.length }));
    commit(next);
  };

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e;
    if (!over || active.id === over.id) return;
    const from = order.indexOf(String(active.id));
    const to = order.indexOf(String(over.id));
    const next = arrayMove(order, from, to);
    setAnnounce(t("ranking.position", { label: labelOf(String(active.id)), position: to + 1, total: next.length }));
    commit(next);
  };

  return (
    <div>
      <p className="mb-3 text-sm text-ink-soft">{t("ranking.help")}</p>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <ol className="flex flex-col gap-3" data-testid="ranking-list">
            {order.map((key, i) => (
              <SortableItem
                key={key}
                id={key}
                index={i}
                total={order.length}
                option={options.find((o) => o.key === key)!}
                disabled={disabled}
                onUp={() => move(key, -1)}
                onDown={() => move(key, 1)}
                onRemove={optional.has(key) ? () => commit(order.filter((k) => k !== key), undefined) : undefined}
                otherText={value?.other_text}
                onOtherText={(text, done) => (done ? commit(order, text.trim() || undefined) : onChange({ order, other_text: text }))}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      {unranked.length > 0 && (
        <div className="mt-4 rounded-[var(--p-radius-card)] border border-dashed border-line p-4">
          <p className="text-sm text-ink-soft">{t("ranking.optional")}</p>
          {unranked.map((o) => (
            <div key={o.key} className="mt-2 flex items-center justify-between gap-3">
              <span>{o.label as string}</span>
              <Button variant="secondary" className="min-h-[44px] px-4 text-sm" onClick={() => commit([...order, o.key])} disabled={disabled} data-testid={`ranking-include-${o.key}`}>
                {t("ranking.include")}
              </Button>
            </div>
          ))}
        </div>
      )}
      <p className="sr-only" aria-live="polite" data-testid="ranking-announce">
        {announce}
      </p>
    </div>
  );
}

function SortableItem(p: {
  id: string;
  index: number;
  total: number;
  option: Option;
  disabled?: boolean;
  onUp: () => void;
  onDown: () => void;
  onRemove?: () => void;
  otherText?: string;
  onOtherText: (text: string, done: boolean) => void;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: p.id, disabled: p.disabled });
  const label = p.option.label as string;
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("rounded-[var(--p-radius-card)] border border-line bg-surface p-3", isDragging && "shadow-[var(--p-shadow)] opacity-90")}
      data-testid={`ranking-item-${p.id}`}
    >
      <div className="flex items-center gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary font-heading text-sm text-on-primary" aria-hidden>
          {p.index + 1}
        </span>
        <span className="flex-1">
          <span className="sr-only">{p.index + 1}. </span>
          {label}
        </span>
        <button type="button" className="min-h-[44px] min-w-[44px] cursor-grab rounded text-ink-soft hover:bg-tint" aria-label={`${label}: drag`} {...attributes} {...listeners} disabled={p.disabled}>
          ≡
        </button>
        <button type="button" className="min-h-[44px] min-w-[44px] rounded hover:bg-tint disabled:opacity-40" onClick={p.onUp} disabled={p.disabled || p.index === 0} aria-label={t("ranking.moveUp", { label })} data-testid={`ranking-up-${p.id}`}>
          ▲
        </button>
        <button type="button" className="min-h-[44px] min-w-[44px] rounded hover:bg-tint disabled:opacity-40" onClick={p.onDown} disabled={p.disabled || p.index === p.total - 1} aria-label={t("ranking.moveDown", { label })} data-testid={`ranking-down-${p.id}`}>
          ▼
        </button>
        {p.onRemove && (
          <button type="button" className="min-h-[44px] rounded px-2 text-sm text-ink-soft hover:bg-tint" onClick={p.onRemove} aria-label={t("ranking.exclude")} data-testid={`ranking-remove-${p.id}`}>
            ✕
          </button>
        )}
      </div>
      {p.option.free_text && (
        <input
          type="text"
          className={`${inputClass} mt-3`}
          placeholder={t("single.other")}
          aria-label={t("single.other")}
          maxLength={500}
          value={p.otherText ?? ""}
          onChange={(e) => p.onOtherText(e.target.value, false)}
          onBlur={(e) => p.onOtherText(e.target.value, true)}
          data-testid="other-text"
        />
      )}
    </li>
  );
}

import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type Announcements, type DragEndEvent, type UniqueIdentifier } from "@dnd-kit/core";
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDownIcon, ChevronUpIcon, GripVerticalIcon, XIcon } from "lucide-react";
import { Button } from "../ui/button";
import { OtherTextInput } from "./OtherTextInput";
import type { RendererProps } from "./types";
import { defaultOrder } from "@/survey/answers";
import { freeTextKeys, optionLabel, type Option, type RankingValue } from "@/survey/types";
import { cn } from "@/lib/utils";

/** Ranking with drag **and** ▲▼ buttons, live position announcements, optional items (Q-6). */
export function Ranking({ question, value, onChange }: RendererProps<RankingValue>) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  const optional = new Set(question.config?.optional_items ?? []);
  const free = freeTextKeys(question);
  // A stored skip reaches the renderer as the value; the list shows the default
  // order (moving an item still commits it) with a notice so it does not read
  // as an answer.
  const skipped = value !== undefined && "skipped" in value && Boolean(value.skipped);
  const order = (skipped ? undefined : value?.order) ?? defaultOrder(question);
  const otherText = skipped ? undefined : value?.other_text;
  const unranked = options.filter((o) => optional.has(o.key) && !order.includes(o.key));
  const [announce, setAnnounce] = useState("");
  // An untouched required ranking already holds its displayed order as the
  // draft (survey/answers.ts implicitAnswer), so `value` is only undefined for
  // an optional ranking, which stays skippable.
  const labelOf = (key: UniqueIdentifier) => optionLabel(question, String(key)) ?? String(key);
  const positionOf = (key: UniqueIdentifier) => order.indexOf(String(key)) + 1;
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }));

  // dnd-kit's own instructions and live announcements are English; the
  // runner's chrome is localised, so they come from i18next like everything
  // else (the arrow buttons announce through the component's own live region).
  const announcements: Announcements = {
    onDragStart: ({ active }) => t("ranking.dragStart", { label: labelOf(active.id), position: positionOf(active.id), total: order.length }),
    onDragOver: ({ active, over }) =>
      over ? t("ranking.dragOver", { label: labelOf(active.id), position: positionOf(over.id), total: order.length }) : t("ranking.dragOutside", { label: labelOf(active.id) }),
    onDragEnd: ({ active, over }) =>
      over ? t("ranking.position", { label: labelOf(active.id), position: positionOf(over.id), total: order.length }) : t("ranking.dragDropped", { label: labelOf(active.id) }),
    onDragCancel: ({ active }) => t("ranking.dragCancel", { label: labelOf(active.id), position: positionOf(active.id), total: order.length }),
  };

  const commit = (next: string[], text = otherText) => {
    const hasFree = next.some((k) => free.has(k));
    onChange({ order: next, ...(hasFree && text ? { other_text: text } : {}) }, { commit: true });
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
    // The drop is announced by dnd-kit's live region (announcements.onDragEnd).
    commit(arrayMove(order, order.indexOf(String(active.id)), order.indexOf(String(over.id))));
  };

  return (
    <div>
      <p className="mb-3 text-sm text-ink-soft">{t("ranking.help")}</p>
      {skipped && (
        <p className="mb-3 rounded-[var(--p-radius-card)] bg-tint px-3 py-2 text-sm text-ink" role="status" data-testid="ranking-skipped">
          {t("ranking.skipped")}
        </p>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd} accessibility={{ screenReaderInstructions: { draggable: t("ranking.srInstructions") }, announcements }}>
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <ol className="flex flex-col gap-3" data-testid="ranking-list">
            {order.map((key, i) => (
              <SortableItem
                key={key}
                id={key}
                index={i}
                total={order.length}
                option={options.find((o) => o.key === key)!}
                onUp={() => move(key, -1)}
                onDown={() => move(key, 1)}
                // The text goes with the free-text item: `commit` drops it once that item leaves the order.
                onRemove={optional.has(key) ? () => commit(order.filter((k) => k !== key)) : undefined}
                order={order}
                otherText={otherText}
                onChange={onChange}
              />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      {unranked.length > 0 && (
        <div className="mt-4 rounded-[var(--p-radius-card)] border border-dashed border-border p-4">
          <p className="text-sm text-muted-foreground">{t("ranking.optional")}</p>
          {unranked.map((o) => (
            <div key={o.key} className="mt-2 flex items-center justify-between gap-3">
              <span>{o.label as string}</span>
              <Button variant="surface" size="runner-sm" onClick={() => commit([...order, o.key])} data-testid={`ranking-include-${o.key}`}>
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
  onUp: () => void;
  onDown: () => void;
  onRemove?: () => void;
  order: string[];
  otherText?: string;
  onChange: RendererProps<RankingValue>["onChange"];
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: p.id });
  const label = p.option.label as string;
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn("rounded-[var(--p-radius-card)] border border-border bg-card p-3", isDragging && "shadow-[var(--p-shadow)] opacity-90")}
      data-testid={`ranking-item-${p.id}`}
    >
      <div className="flex items-center gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary font-heading text-sm text-primary-foreground" aria-hidden>
          {p.index + 1}
        </span>
        <span className="flex-1">
          <span className="sr-only">{p.index + 1}. </span>
          {label}
        </span>
        <Button variant="text" size="runner-icon" className="cursor-grab text-muted-foreground" aria-label={t("ranking.drag", { label })} {...attributes} {...listeners}>
          <GripVerticalIcon className="size-5" />
        </Button>
        <Button variant="text" size="runner-icon" onClick={p.onUp} disabled={p.index === 0} aria-label={t("ranking.moveUp", { label })} data-testid={`ranking-up-${p.id}`}>
          <ChevronUpIcon className="size-5" />
        </Button>
        <Button variant="text" size="runner-icon" onClick={p.onDown} disabled={p.index === p.total - 1} aria-label={t("ranking.moveDown", { label })} data-testid={`ranking-down-${p.id}`}>
          <ChevronDownIcon className="size-5" />
        </Button>
        {p.onRemove && (
          <Button variant="text" size="runner-icon" className="text-muted-foreground" onClick={p.onRemove} aria-label={t("ranking.exclude")} data-testid={`ranking-remove-${p.id}`}>
            <XIcon className="size-4" />
          </Button>
        )}
      </div>
      {p.option.free_text && <OtherTextInput base={{ order: p.order }} value={p.otherText} onChange={p.onChange} />}
    </li>
  );
}

import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOptionsSource } from "@/api/hooks";
import { inputClass, type RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";
import { cn } from "@/lib/utils";

/** Searchable single-select (combobox) for option sources such as ISO 3166 (Q-3). */
export function Dropdown({ question, value, onChange, language, disabled }: RendererProps<OptionValue>) {
  const { t } = useTranslation();
  const source = question.config?.options_source;
  const remote = useOptionsSource(source, language);
  const options = useMemo(
    () => [...(remote.data?.options ?? []), ...(question.options ?? []).map((o) => ({ key: o.key, label: o.label as string }))],
    [remote.data, question.options],
  );
  const selected = options.find((o) => o.key === value?.option);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase();
    return q ? options.filter((o) => o.label.toLocaleLowerCase().includes(q)) : options;
  }, [options, query]);

  const choose = (key: string) => {
    onChange({ option: key }, { commit: true });
    setQuery("");
    setOpen(false);
  };

  return (
    <div className="relative">
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && filtered[active] ? `${listId}-${filtered[active].key}` : undefined}
        className={inputClass}
        placeholder={t("dropdown.placeholder")}
        disabled={disabled || remote.isLoading}
        value={open ? query : (selected?.label ?? "")}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
            setActive((a) => Math.min(a + 1, filtered.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((a) => Math.max(a - 1, 0));
          } else if (e.key === "Enter" && open && filtered[active]) {
            e.preventDefault();
            choose(filtered[active].key);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
        data-testid="combobox"
      />
      {selected && !open && (
        <button
          type="button"
          onClick={() => onChange(undefined)}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-sm text-ink-soft hover:text-ink"
          aria-label={t("dropdown.clear")}
        >
          ✕
        </button>
      )}
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-[var(--p-radius-input)] border border-line bg-surface shadow-[var(--p-shadow)]"
        >
          {filtered.length === 0 && <li className="px-4 py-3 text-ink-soft">{t("dropdown.noResults")}</li>}
          {filtered.map((o, i) => (
            <li
              key={o.key}
              id={`${listId}-${o.key}`}
              role="option"
              aria-selected={o.key === value?.option}
              className={cn("cursor-pointer px-4 py-3", i === active && "bg-tint", o.key === value?.option && "font-medium text-primary")}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(o.key);
              }}
              onMouseEnter={() => setActive(i)}
              data-testid={`combobox-option-${o.key}`}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

import { CheckIcon, ChevronsUpDownIcon, XIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOptionsSource } from "@/api/hooks";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import type { RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";
import { cn } from "@/lib/utils";

/** Searchable single-select (shadcn Combobox: Popover + Command) for option sources such as ISO 3166 (Q-3). */
export function Dropdown({ question, value, onChange, language, disabled }: RendererProps<OptionValue>) {
  const { t } = useTranslation();
  const source = question.config?.options_source;
  const remote = useOptionsSource(source, language);
  const options = useMemo(
    () => [...(remote.data?.options ?? []), ...(question.options ?? []).map((o) => ({ key: o.key, label: o.label as string }))],
    [remote.data, question.options],
  );
  const selected = options.find((o) => o.key === value?.option);
  const [open, setOpen] = useState(false);

  return (
    <div className="flex items-center gap-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="surface"
            size="runner"
            role="combobox"
            aria-expanded={open}
            aria-label={question.text as string}
            disabled={disabled || remote.isLoading}
            className="w-full justify-between px-4 font-body text-[1.05rem] font-normal"
            data-testid="combobox-trigger"
          >
            <span className={cn("truncate", !selected && "text-muted-foreground")}>{selected?.label ?? t("dropdown.placeholder")}</span>
            <ChevronsUpDownIcon className="size-4 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0" align="start">
          <Command>
            <CommandInput placeholder={t("dropdown.placeholder")} className="h-12 text-base" data-testid="combobox" />
            <CommandList className="max-h-64">
              <CommandEmpty>{t("dropdown.noResults")}</CommandEmpty>
              <CommandGroup>
                {options.map((o) => (
                  <CommandItem
                    key={o.key}
                    value={o.key}
                    keywords={[o.label as string]}
                    onSelect={() => {
                      onChange({ option: o.key }, { commit: true });
                      setOpen(false);
                    }}
                    className="min-h-[44px] text-base"
                    data-testid={`combobox-option-${o.key}`}
                  >
                    <CheckIcon className={cn("size-4", o.key === value?.option ? "opacity-100" : "opacity-0")} />
                    {o.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selected && (
        <Button variant="text" size="runner-icon" onClick={() => onChange(undefined)} aria-label={t("dropdown.clear")} disabled={disabled}>
          <XIcon className="size-4" />
        </Button>
      )}
    </div>
  );
}

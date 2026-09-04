import { CheckIcon, ChevronsUpDownIcon, XIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useOptionsSource } from "@/api/hooks";
import { Button } from "../ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from "../ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import type { RendererProps } from "./types";
import type { OptionValue } from "@/survey/types";
import { orderedSourceOptions, priorityCount } from "@/survey/answers";
import { cn } from "@/lib/utils";

/** Searchable single-select (shadcn Combobox: Popover + Command) for option sources such as ISO 3166 (Q-3). */
export function Dropdown({ question, value, onChange, language }: RendererProps<OptionValue>) {
  const { t } = useTranslation();
  const source = question.config?.options_source;
  const remote = useOptionsSource(source, language);
  // options_source_include restricts the source list (a survey that only covers
  // some countries); inline options are unaffected. The engines enforce the
  // same restriction, so this is presentation, not validation.
  const include = question.config?.options_source_include;
  // options_source_priority orders the source list (the countries a survey
  // expects most of its respondents from, ahead of the rest). Ordering only:
  // everything the source offers stays answerable.
  const priority = question.config?.options_source_priority;
  const { options, pinned } = useMemo(() => {
    const allowed = include && new Set(include);
    const remoteOptions = (remote.data?.options ?? []).filter((o) => !allowed || allowed.has(o.key));
    const ordered = orderedSourceOptions(question.config, remoteOptions);
    return {
      options: [...ordered, ...(question.options ?? []).map((o) => ({ key: o.key, label: o.label as string }))],
      pinned: priorityCount(question.config, ordered),
    };
  }, [remote.data, question.options, question.config, include, priority]);
  const selected = options.find((o) => o.key === value?.option);
  const [open, setOpen] = useState(false);
  const renderOption = (o: { key: string; label: string }) => (
    <CommandItem
      key={o.key}
      value={o.key}
      keywords={[o.label]}
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
  );
  // Without the remote list the participant could only pick the inline
  // options (e.g. "Prefer not to say"), so the control stays closed and says why.
  const failed = Boolean(source) && remote.isError;

  return (
    <div>
      <div className="flex items-center gap-2">
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="surface"
              size="runner"
              role="combobox"
              aria-expanded={open}
              aria-label={question.text as string}
              disabled={remote.isLoading || failed}
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
                {/* Two groups when some options are pinned, so the order does not
                    read as an alphabetical list that has gone wrong. cmdk hides a
                    separator while a search is running, which is when the grouping
                    stops meaning anything. */}
                <CommandGroup>{options.slice(0, pinned).map(renderOption)}</CommandGroup>
                {pinned > 0 && <CommandSeparator />}
                <CommandGroup>{options.slice(pinned).map(renderOption)}</CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
        {/* Clearing is as deliberate as choosing: it commits, so the wizard records the "no answer" where it can. */}
        {selected && (
          <Button variant="text" size="runner-icon" onClick={() => onChange(undefined, { commit: true })} aria-label={t("dropdown.clear")} data-testid="combobox-clear">
            <XIcon className="size-4" />
          </Button>
        )}
      </div>
      {failed && (
        <p className="mt-2 text-sm text-error" role="alert" data-testid="combobox-error">
          {t("dropdown.error")}{" "}
          <Button variant="text" onClick={() => remote.refetch()} disabled={remote.isFetching}>
            {t("dropdown.retry")}
          </Button>
        </p>
      )}
    </div>
  );
}

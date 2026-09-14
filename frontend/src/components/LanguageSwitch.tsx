import { GlobeIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { languageName, languageNameIn } from "@/i18n/languageName";
import { cn } from "@/lib/utils";

/**
 * The one language control, wherever a page puts it: the wizard header and
 * the intro's top row. A ghost pill — transparent, a translucent border, a
 * globe, a chevron that turns when open — so it reads as part of the surface
 * it sits on rather than a form control dropped onto it; `onPrimary` draws it
 * in the on-primary colour for an immersive intro. The menu is the surface
 * card: each language in its own name, its name in the reader's language
 * beneath when that differs, its code on the right, and the chosen one marked.
 * Never a flag — Spanish and Portuguese each span several countries.
 * Renders nothing for a single-language survey.
 */
export function LanguageSwitch({
  languages,
  language,
  onLanguage,
  onPrimary = false,
  className,
}: {
  languages: string[];
  language: string;
  onLanguage: (lang: string) => void;
  /** Drawn for the primary ground (an immersive intro) rather than a light surface. */
  onPrimary?: boolean;
  className?: string;
}) {
  const { t, i18n } = useTranslation();
  if (languages.length < 2) return null;
  return (
    <Select value={language} onValueChange={onLanguage}>
      <SelectTrigger
        id="language-switch"
        aria-label={t("header.language")}
        className={cn(
          "min-h-[44px] gap-2 rounded-full border pr-3 pl-3.5 text-sm font-medium shadow-none transition-[background-color,border-color] data-[size=default]:h-auto",
          "[&>svg:last-child]:opacity-70 [&>svg:last-child]:transition-transform data-[state=open]:[&>svg:last-child]:rotate-180",
          onPrimary
            ? "border-on-primary/35 bg-on-primary/[0.06] text-on-primary hover:border-on-primary/60 hover:bg-on-primary/15 focus-visible:border-on-primary focus-visible:ring-on-primary/50 data-[state=open]:border-on-primary/60 data-[state=open]:bg-on-primary/15 [&_svg]:text-on-primary"
            : "border-border bg-transparent text-foreground hover:bg-accent data-[state=open]:bg-accent [&_svg]:text-foreground",
          className,
        )}
        data-testid="language-switch"
      >
        <GlobeIcon className="size-4" aria-hidden="true" />
        <SelectValue>
          <span className="font-mono text-[12.5px] tracking-[0.06em] sm:hidden">
            {language.toUpperCase()}
          </span>
          <span className="hidden sm:inline">{languageName(language)}</span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent
        align="end"
        position="popper"
        sideOffset={8}
        className="min-w-[200px] rounded-[14px] border-border p-1.5 shadow-[var(--p-shadow),0_12px_32px_rgb(0_0_0/0.22)]"
      >
        {languages.map((l) => {
          const native = languageName(l);
          const inReadersLanguage = languageNameIn(l, i18n.language);
          return (
            <SelectItem
              key={l}
              value={l}
              className="group min-h-[44px] rounded-[9px] py-2 pr-3 pl-3 data-[state=checked]:bg-accent [&>[data-slot=select-item-indicator]]:hidden [&>span:last-child]:w-full"
              data-testid={`language-${l}`}
            >
              <span className="flex w-full items-center justify-between gap-3">
                <span>
                  {native}
                  {inReadersLanguage && inReadersLanguage !== native && (
                    <span className="block text-xs text-muted-foreground">
                      {inReadersLanguage}
                    </span>
                  )}
                </span>
                <span className="font-mono text-[11.5px] tracking-[0.06em] text-muted-foreground group-data-[state=checked]:text-primary">
                  <span className="hidden font-body group-data-[state=checked]:inline">
                    ✓{" "}
                  </span>
                  {l.toUpperCase()}
                </span>
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}

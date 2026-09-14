import { useTranslation } from "react-i18next";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { languageName } from "@/i18n/languageName";
import { cn } from "@/lib/utils";

/**
 * The one language control, wherever a page puts it: the wizard header and
 * the intro's top row. Each language names itself — translating "Spanish"
 * into a language the respondent cannot read is how a picker fails the people
 * who need it. Renders nothing for a single-language survey.
 */
export function LanguageSwitch({ languages, language, onLanguage, className }: { languages: string[]; language: string; onLanguage: (lang: string) => void; className?: string }) {
  const { t } = useTranslation();
  if (languages.length < 2) return null;
  return (
    <Select value={language} onValueChange={onLanguage}>
      <SelectTrigger id="language-switch" aria-label={t("header.language")} className={cn("min-h-[44px] bg-card px-2 text-foreground sm:px-3", className)} data-testid="language-switch">
        <SelectValue>
          <span className="sm:hidden">{language.toUpperCase()}</span>
          <span className="hidden sm:inline">{languageName(language)}</span>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {languages.map((l) => (
          <SelectItem key={l} value={l} className="min-h-[44px]" data-testid={`language-${l}`}>
            {languageName(l)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

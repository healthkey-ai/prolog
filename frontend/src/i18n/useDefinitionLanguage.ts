import { useEffect } from "react";
import i18n from "@/i18n";

/** Keep runner chrome and `<html lang>` in the definition's language. */
export function useDefinitionLanguage(lang: string | undefined): void {
  useEffect(() => {
    if (!lang) return;
    void i18n.changeLanguage(lang);
    document.documentElement.lang = lang;
  }, [lang]);
}

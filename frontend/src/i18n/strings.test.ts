import { describe, expect, it } from "vitest";
import en from "./en.json";
import i18n, { addStrings, resources } from "./index";
import type { AnswerIssueCode } from "@/survey/answers";

/**
 * Every rejection code, as a runtime list. `Record<AnswerIssueCode, true>`
 * makes the typecheck fail when a code is added to (or dropped from) the
 * engine's union without updating this list.
 */
const ISSUE_CODES: Record<AnswerIssueCode, true> = {
  info_no_answer: true,
  value_not_object: true,
  skip_shape: true,
  skip_not_allowed: true,
  not_visible: true,
  other_text_not_string: true,
  other_text_without_free_option: true,
  other_text_too_long: true,
  option_required: true,
  option_unknown: true,
  options_not_list: true,
  options_duplicate: true,
  options_unknown: true,
  min_selections: true,
  max_selections: true,
  exclusive_combined: true,
  value_not_integer: true,
  value_out_of_range: true,
  order_not_list: true,
  order_duplicate: true,
  order_unknown: true,
  order_incomplete: true,
  ratings_not_object: true,
  matrix_no_rows: true,
  rows_unknown: true,
  rows_incomplete: true,
  rating_not_integer: true,
  rating_out_of_range: true,
  text_required: true,
  text_too_long: true,
  number_required: true,
  number_not_finite: true,
  number_not_integer: true,
  number_too_small: true,
  number_too_large: true,
  date_format: true,
  date_invalid: true,
  date_too_early: true,
  date_too_late: true,
  email_via_endpoint: true,
  unsupported_type: true,
};

describe("chrome strings", () => {
  const keys = Object.keys(resources.en.translation);
  for (const lang of Object.keys(resources)) {
    it(`${lang} has every key and the same placeholders`, () => {
      const bundle = resources[lang].translation;
      expect(Object.keys(bundle).sort()).toEqual([...keys].sort());
      for (const key of keys) {
        const placeholders = (s: string) => (s.match(/{{\w+}}/g) ?? []).sort();
        expect(placeholders(bundle[key]), `${lang}.${key}`).toEqual(placeholders(resources.en.translation[key]));
      }
    });
    it(`${lang} has a participant-facing string for every answer rejection code`, () => {
      const bundle = resources[lang].translation;
      expect(bundle["error.generic"]).toBeTruthy();
      for (const code of Object.keys(ISSUE_CODES)) expect(bundle[`error.${code}`], `${lang}.error.${code}`).toBeTruthy();
    });
  }
});

describe("addStrings", () => {
  it("overrides a bundled language and restores it on the next call", () => {
    const original = en["intro.start"];
    addStrings({ "intro.start": { en: "Begin" } });
    expect(i18n.getResource("en", "translation", "intro.start")).toBe("Begin");
    expect(resources.en.translation["intro.start"]).toBe(original); // the bundled original is not merged into
    addStrings({});
    expect(i18n.getResource("en", "translation", "intro.start")).toBe(original);
  });

  it("does not leak a language outside the bundled four into the next theme", () => {
    addStrings({ "intro.start": { de: "Los" } });
    expect(i18n.getResource("de", "translation", "intro.start")).toBe("Los");
    addStrings({ "intro.start": { en: "Begin" } });
    expect(i18n.hasResourceBundle("de", "translation")).toBe(false);
    expect(i18n.t("intro.start", { lng: "de" })).toBe("Begin"); // en fallback
  });
});

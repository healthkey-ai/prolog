import { describe, expect, it } from "vitest";
import { resources } from "./index";

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
  }
});

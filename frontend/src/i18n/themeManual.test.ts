import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import en from "./en.json";

/**
 * The theme manual's §2.7 table mirrors en.json (the override surface a theme
 * author reads). Every key must be listed, and nothing that is not a key: an
 * override of a key the runner never reads is silently ignored.
 */
const MANUAL = path.resolve(import.meta.dirname, "../../../docs/definitions/theme-definition.md");

/** The backticked keys of the §2.7 table; the Validation row lists bare `error.<code>` codes. */
function documentedKeys(markdown: string): string[] {
  const start = markdown.indexOf("### 2.7");
  expect(start).toBeGreaterThan(-1);
  const end = markdown.indexOf("\n---", start);
  const rows = markdown
    .slice(start, end)
    .split("\n")
    .filter((line) => line.startsWith("|"))
    .slice(2); // header and separator
  expect(rows.length).toBeGreaterThan(0);
  const keys: string[] = [];
  for (const row of rows) {
    const area = row.split("|")[1].trim();
    for (const [, token] of row.matchAll(/`([^`]+)`/g)) {
      if (token.startsWith("{{") || token.includes("<")) continue; // a placeholder, or the `error.<code>` pattern
      keys.push(token.includes(".") ? token : area === "Validation" ? `error.${token}` : token);
    }
  }
  return keys;
}

describe("theme manual §2.7", () => {
  const documented = documentedKeys(readFileSync(MANUAL, "utf8"));

  it("lists every chrome string key exactly once, and no key the runner does not read", () => {
    const duplicates = documented.filter((k, i) => documented.indexOf(k) !== i);
    expect(duplicates).toEqual([]);
    expect([...documented].sort()).toEqual(Object.keys(en).sort());
  });

  it("names the placeholders of every key that has them", () => {
    const markdown = readFileSync(MANUAL, "utf8");
    const section = markdown.slice(markdown.indexOf("### 2.7"), markdown.indexOf("\n---", markdown.indexOf("### 2.7")));
    for (const [key, value] of Object.entries(en)) {
      const placeholders = value.match(/{{\w+}}/g) ?? [];
      if (!placeholders.length) continue;
      const short = key.startsWith("error.") ? key.slice("error.".length) : key;
      // The placeholders follow the key in the same row: `key` (`{{a}}`, `{{b}}`)
      const after = section.slice(section.indexOf(`\`${short}\``) + short.length + 2);
      const named = after.match(/^\s*\(((?:`{{\w+}}`(?:,\s*)?)+)\)/)?.[1] ?? "";
      for (const p of placeholders) expect(named, `${key} ${p}`).toContain(`\`${p}\``);
    }
  });
});

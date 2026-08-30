import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/client";
import { definitionErrorKey, definitionErrorTerminal } from "./DefinitionError";

describe("DefinitionError", () => {
  it("maps the status to the same message the intro shows, and retries only what is transient", () => {
    const cases: [unknown, string, boolean][] = [
      [new ApiError(404, {}), "app.notFound", true],
      [new ApiError(410, {}), "app.closed", true],
      [new ApiError(403, {}), "app.forbidden", true],
      [new ApiError(429, {}), "app.throttled", false],
      [new ApiError(502, {}), "app.error", false],
      [new TypeError("Failed to fetch"), "app.error", false],
    ];
    for (const [error, key, terminal] of cases) {
      expect(definitionErrorKey(error), key).toBe(key);
      expect(definitionErrorTerminal(error), key).toBe(terminal);
    }
  });
});

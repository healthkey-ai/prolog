import { describe, expect, it } from "vitest";
import { exitUrl } from "./useTheme";

describe("exitUrl", () => {
  it("keeps a path on this site and an http(s) URL", () => {
    expect(exitUrl("/")).toBe("/");
    expect(exitUrl("/home?x=1#top")).toBe("/home?x=1#top");
    expect(exitUrl("https://example.org/home")).toBe("https://example.org/home");
  });

  it("refuses anything that could leave the site or run script", () => {
    for (const raw of [
      undefined,
      "",
      "//elsewhere.example",
      "/\\elsewhere.example",
      "/\t/elsewhere.example",
      "/\n/elsewhere.example",
      "/\r\\elsewhere.example",
      " /home",
      "javascript:alert(1)",
      "HTTPS://example.org",
      "https:elsewhere.example",
      "home",
    ]) {
      expect(exitUrl(raw), JSON.stringify(raw)).toBeUndefined();
    }
  });
});

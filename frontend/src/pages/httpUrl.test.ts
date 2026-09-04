import { describe, expect, it } from "vitest";
import { httpUrl } from "./httpUrl";

describe("httpUrl", () => {
  it("keeps absolute http(s) URLs", () => {
    expect(httpUrl("https://example.org/privacy")).toBe("https://example.org/privacy");
    expect(httpUrl("http://example.org/p?x=1#top")).toBe("http://example.org/p?x=1#top");
  });
  it("drops every other scheme, relative paths and junk", () => {
    for (const bad of ["javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd", "/privacy", "privacy", "", undefined]) expect(httpUrl(bad), String(bad)).toBeUndefined();
  });
});

import { expect, test } from "@playwright/test";
import { expectAccessible } from "./helpers";

test.describe("theming", () => {
  test("default theme on the neutral example", async ({ page }) => {
    await page.goto("/s/sample-wellbeing");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await expect(page.getByTestId("start")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe("default");
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--p-primary").trim())).toBe("#176b58");
    await expect(page.getByTestId("decor")).toHaveCount(0);
  });

  test("customer theme restyles the runner at runtime", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/s/sample-themed");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await expect(page.getByTestId("start")).toBeVisible();

    // tokens applied
    expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe("e2e-test");
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--p-primary").trim())).toBe("#4a1a7a");
    const font = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
    expect(font).toContain("Georgia");
    const radius = await page.getByTestId("start").evaluate((el) => getComputedStyle(el).borderRadius);
    expect(radius).toBe("999px");

    // immersive intro with decor and the on-primary logo; chrome string override
    const intro = page.locator("[data-immersive]");
    await expect(intro).toBeVisible();
    expect(await intro.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe("rgb(74, 26, 122)");
    await expect(page.getByTestId("decor").locator("img")).toHaveCount(2);
    const logo = page.getByTestId("theme-logo");
    await expect(logo).toBeVisible();
    expect(await logo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    await expect(page.getByTestId("start")).toHaveText("Begin the survey");
    expect(await page.evaluate(() => document.querySelector<HTMLLinkElement>('link[rel="icon"]')?.href)).toContain("/api/run/themes/e2e-test/assets/logo.svg");
    await expectAccessible(page, "themed intro");

    // question screens use the theme too
    await page.getByTestId("start").click();
    await expect(page.getByTestId("question-welcome")).toBeVisible();
    await expect(page.getByTestId("theme-logo")).toBeVisible();
    const next = await page.getByTestId("next").evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(next).toBe("rgb(74, 26, 122)");
    await expectAccessible(page, "themed question");
  });
});

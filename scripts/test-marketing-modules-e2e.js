const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const baseUrl = (process.env.HEYU_BASE_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const executablePath = process.env.HEYU_BROWSER_PATH || "";

async function main() {
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true,
    args: ["--disable-gpu"],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });

  try {
    await page.goto(`${baseUrl}/create/?lang=en`, { waitUntil: "networkidle" });
    assert.equal(
      await page.locator('[name="content_modules"][value="livestream"]').count(),
      0,
      "the new content flow must not expose a livestream module",
    );
    assert.equal(
      await page.locator('.result-tabs [data-tab="live"]').count(),
      0,
      "the new content flow must not expose a livestream tab",
    );
    await page
      .locator('[name="content_modules"][value="calendar"]')
      .uncheck({ force: true });

    const previewResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${baseUrl}/v1/marketing/preview`
        && response.request().method() === "POST",
    );
    await page.locator('[data-demo-case="tomato"]').click();
    assert.equal((await previewResponsePromise).status(), 200);
    await page.locator("#result-state").waitFor({ state: "visible" });

    assert.equal(
      await page.locator('.result-tabs [data-tab="routes"]').isVisible(),
      true,
      "video route tab should remain visible",
    );
    assert.equal(
      await page.locator('.result-tabs [data-tab="calendar"]').isVisible(),
      false,
      "unselected calendar tab should be hidden",
    );

    await page.locator('.result-tabs [data-tab="routes"]').click();
    const firstRoute = page.locator(".route-card").first();
    const originalTitle = (await firstRoute.locator("h3").textContent()).trim();
    const regenerateResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${baseUrl}/v1/marketing/regenerate/preview`
        && response.request().method() === "POST",
    );
    await firstRoute.locator('[data-regenerate-target="video"]').click();
    assert.equal((await regenerateResponsePromise).status(), 200);
    await page.waitForFunction(
      (previousTitle) =>
        document.querySelector(".route-card h3")?.textContent.trim() !== previousTitle,
      originalTitle,
    );
    assert.notEqual(
      (await page.locator(".route-card").first().locator("h3").textContent()).trim(),
      originalTitle,
      "regeneration should visibly replace only the requested video route",
    );
    assert.deepEqual(browserErrors, []);
    console.log("Marketing module selection and regeneration E2E: PASS");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

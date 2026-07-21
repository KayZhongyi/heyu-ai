const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const baseUrl = process.env.HEYU_BASE_URL || "http://127.0.0.1:8765";

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage();
  const browserErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));

  try {
    const bootstrapResponse = await context.request.post(`${baseUrl}/v1/auth/bootstrap`, {
      data: {
        organization_name: "禾语 Demo 验收",
        organization_slug: "heyu-afternoon-demo",
        display_name: "Demo 验收员",
        email: "demo@heyu-ai.example.com",
        password: "HeyuDemo2026!",
      },
    });
    let auth;
    if (bootstrapResponse.status() === 201) {
      auth = await bootstrapResponse.json();
    } else {
      const loginResponse = await context.request.post(`${baseUrl}/v1/auth/login`, {
        data: {
          organization_slug: "heyu-afternoon-demo",
          email: "demo@heyu-ai.example.com",
          password: "HeyuDemo2026!",
        },
      });
      assert.equal(
        loginResponse.status(),
        200,
        `demo authentication failed: bootstrap=${bootstrapResponse.status()} login=${loginResponse.status()}`,
      );
      auth = await loginResponse.json();
    }

    await page.goto(`${baseUrl}/create/?lang=zh-CN`, { waitUntil: "networkidle" });
    await page.evaluate((token) => localStorage.setItem("heyu_token", token), auth.access_token);
    await page.reload({ waitUntil: "networkidle" });

    await page.locator('[data-demo-case="tomato"]').click();
    await page.locator("#result-state").waitFor({ state: "visible", timeout: 30_000 });
    assert.equal(await page.locator("#result-product").textContent(), "当季番茄");
    await assertVisibleText(page, "strategy", ["产品定位", "平台策略", "接下来就这样做"]);
    await assertVisibleText(page, "topics", ["热点融入", "适配分", "来源类型"]);
    await assertVisibleText(page, "routes", ["实用吸睛", "人物故事", "轻松反差"]);
    assert.equal(await page.locator(".route-card").count(), 3);
    await assertVisibleText(page, "prep", ["当前拍摄路线", "开头钩子", "拍摄提示"]);
    assert.equal(await page.locator('[data-tab="live"]').count(), 0);
    await assertVisibleText(page, "calendar", ["让用户认识产品", "补充产品信息", "复盘并再利用"]);

    const saveResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${baseUrl}/v1/marketing-plans`
        && response.request().method() === "POST",
    );
    await page.locator("#save-result").click();
    const saveResponse = await saveResponsePromise;
    assert.equal(saveResponse.status(), 201);
    assert.ok(await page.locator("#open-saved-plan").isVisible());

    await page.locator('.result-tabs [data-tab="routes"]').click();
    const downloadButton = page.locator(
      '.route-card [data-download-route="practical-hook"]',
    );
    await downloadButton.waitFor({ state: "visible" });
    await page.waitForFunction(
      () =>
        !document.querySelector(
          '.route-card [data-download-route="practical-hook"]',
        )?.disabled,
    );
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      downloadButton.click(),
    ]);
    assert.match(download.suggestedFilename(), /\.zip$/i);
    assert.equal(await download.failure(), null);

    assert.deepEqual(browserErrors, []);
    console.log("Heyu tomato demo E2E: PASS");
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

async function assertVisibleText(page, tab, expectedTexts) {
  await page.locator(`.result-tabs [data-tab="${tab}"]`).click();
  const content = page.locator("#result-content");
  for (const expected of expectedTexts) {
    await content.getByText(expected, { exact: false }).first().waitFor();
  }
}

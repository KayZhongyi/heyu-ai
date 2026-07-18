const assert = require("node:assert/strict");
const { chromium } = require("playwright");

const baseUrl = (process.env.HEYU_BASE_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const executablePath = process.env.HEYU_BROWSER_PATH || "";
const unique = Date.now().toString(36);
const password = "HeyuProviderE2E2026!";

async function api(page, path, options = {}) {
  const response = await page.request.fetch(`${baseUrl}${path}`, options);
  assert.ok(response.ok(), `${options.method || "GET"} ${path} failed: ${response.status()} ${await response.text()}`);
  return response.status() === 204 ? null : response.json();
}

async function signInBrowser(page, token, path = "/workspace/providers") {
  await page.goto(`${baseUrl}/workspace/`, { waitUntil: "domcontentloaded" });
  await page.evaluate((value) => localStorage.setItem("heyu_token", value), token);
  await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
}

async function main() {
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true,
    args: ["--disable-gpu"],
  });
  const ownerPage = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  const browserErrors = [];
  ownerPage.on("pageerror", (error) => browserErrors.push(error.message));
  ownerPage.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });

  try {
    const owner = await api(ownerPage, "/v1/auth/bootstrap", {
      method: "POST",
      data: {
        organization_name: `Provider E2E ${unique}`,
        organization_slug: `provider-e2e-${unique}`,
        email: `owner-${unique}@heyu.example`,
        display_name: "Provider owner",
        password,
      },
    });
    const auth = { Authorization: `Bearer ${owner.access_token}` };
    await signInBrowser(ownerPage, owner.access_token);

    await ownerPage.locator('[data-page-panel="providers"]').waitFor({ state: "visible" });
    assert.equal(await ownerPage.locator(".provider-nav").isVisible(), true);
    assert.equal((await ownerPage.locator("#page-title").textContent()).trim(), "模型连接");

    const form = ownerPage.locator("#provider-form");
    await form.locator('[name="name"]').fill("国内测试模型");
    await form.locator('[name="base_url"]').fill("https://api.example.com/v1");
    await form.locator('[name="chat_model"]').fill("demo-chat");
    await form.locator('[name="embedding_model"]').fill("demo-embedding");
    await form.locator('[name="secret_reference"]').fill("HEYU_E2E_PROVIDER_KEY");
    await form.locator('[name="is_fallback"]').check();
    await form.locator('[name="is_primary"]').check();
    assert.equal(await form.locator('[name="is_fallback"]').isChecked(), false, "primary and fallback must be mutually exclusive");

    const createResponse = ownerPage.waitForResponse(
      (response) => response.url() === `${baseUrl}/v1/provider-connections` && response.request().method() === "POST",
    );
    await form.locator('[type="submit"]').click();
    assert.equal((await createResponse).status(), 201);
    await ownerPage.getByText("国内测试模型", { exact: true }).waitFor();
    assert.equal(await ownerPage.locator(".provider-card").count(), 1);
    assert.doesNotMatch(await ownerPage.locator(".provider-card").innerText(), /HeyuProviderE2E2026|temporary-only-secret/);

    await ownerPage.locator("[data-edit-provider]").click();
    await form.locator('[name="chat_model"]').fill("demo-chat-v2");
    const patchResponse = ownerPage.waitForResponse(
      (response) => response.url().includes("/v1/provider-connections/") && response.request().method() === "PATCH",
    );
    await form.locator('[type="submit"]').click();
    assert.equal((await patchResponse).status(), 200);
    await ownerPage.getByText("demo-chat-v2", { exact: true }).waitFor();

    const probeResponse = ownerPage.waitForResponse(
      (response) => response.url().endsWith("/test") && response.request().method() === "POST",
    );
    await ownerPage.locator(".provider-probe button").click();
    assert.equal((await probeResponse).status(), 200);
    await ownerPage.getByText("最近测试失败", { exact: true }).waitFor();

    await ownerPage.locator('[data-locale="zh-HK"]').first().click();
    await ownerPage.waitForFunction(() => document.documentElement.lang === "zh-HK");
    assert.equal((await ownerPage.locator("#page-title").textContent()).trim(), "模型連接");
    assert.equal(await form.locator('[name="name"]').getAttribute("placeholder"), "例如：國內生產模型");

    await ownerPage.locator('[data-locale="en"]').first().click();
    await ownerPage.waitForFunction(() => document.documentElement.lang === "en");
    assert.equal((await ownerPage.locator("#page-title").textContent()).trim(), "Model connections");
    assert.equal(await form.locator('[name="chat_model"]').getAttribute("placeholder"), "Model identifier");

    const invitation = await api(ownerPage, "/v1/invitations", {
      method: "POST",
      headers: auth,
      data: { email: `viewer-${unique}@heyu.example`, role: "viewer", expires_in_hours: 24 },
    });
    const viewer = await api(ownerPage, "/v1/invitations/accept", {
      method: "POST",
      data: {
        token: invitation.token,
        display_name: "Provider viewer",
        password,
      },
    });
    const viewerPage = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await signInBrowser(viewerPage, viewer.access_token);
    await viewerPage.locator('[data-page-panel="overview"]').waitFor({ state: "visible" });
    assert.equal(await viewerPage.locator(".provider-nav").isVisible(), false);
    assert.equal(new URL(viewerPage.url()).pathname, "/workspace/");
    await viewerPage.close();

    ownerPage.once("dialog", (dialog) => dialog.accept());
    const deleteResponse = ownerPage.waitForResponse(
      (response) => response.url().includes("/v1/provider-connections/") && response.request().method() === "DELETE",
    );
    await ownerPage.locator("[data-delete-provider]").click();
    assert.equal((await deleteResponse).status(), 204);
    await ownerPage.waitForFunction(() => document.querySelectorAll(".provider-card").length === 0);

    assert.deepEqual(browserErrors, []);
    console.log("Provider connections E2E: PASS");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

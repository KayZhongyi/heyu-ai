const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = (process.env.HEYU_BASE_URL || "http://127.0.0.1:8765").replace(/\/$/, "");
const outputDir = path.resolve(process.env.HEYU_E2E_OUTPUT || "outputs/browser-e2e");
const executablePath = process.env.HEYU_BROWSER_PATH || "";

const unique = Date.now().toString(36);
const organizationSlug = `e2e-${unique}`;
const ownerEmail = `owner-${unique}@heyu.example`;
const invitedEmail = `creator-${unique}@heyu.example`;
const password = "HeyuE2E2026!";
const businessName = `青禾 Orchard ${unique}`;

fs.mkdirSync(outputDir, { recursive: true });

async function expectNoHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert.ok(
    dimensions.scrollWidth <= dimensions.clientWidth + 1,
    `${label} horizontally overflows: ${JSON.stringify(dimensions)}`,
  );
}

async function screenshot(page, name) {
  await page.screenshot({ path: path.join(outputDir, name), fullPage: true });
}

async function selectLocale(page, locale) {
  await page.locator(`[data-locale="${locale}"]`).first().click();
  await page.waitForFunction((expected) => document.documentElement.lang === expected, locale);
}

async function main() {
  const browser = await chromium.launch({
    ...(executablePath ? { executablePath } : {}),
    headless: true,
    args: ["--disable-gpu"],
  });

  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 960 } });
    await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
    const page = await context.newPage();

    for (const [locale, expected, filename] of [
      ["zh-CN", "进入工作台", "landing-zh-CN.png"],
      ["zh-HK", "進入工作區", "landing-zh-HK.png"],
      ["en", "Open workspace", "landing-en.png"],
    ]) {
      await page.goto(`${baseUrl}/?lang=${locale}`, { waitUntil: "networkidle" });
      await assert.doesNotReject(() => page.getByText(expected, { exact: false }).first().waitFor());
      await expectNoHorizontalOverflow(page, `landing ${locale}`);
      await screenshot(page, filename);
    }

    await page.goto(`${baseUrl}/workspace/?lang=zh-CN`, { waitUntil: "networkidle" });
    const bootstrap = page.locator("#bootstrap-form");
    await bootstrap.locator('[name="organization_name"]').fill("禾语浏览器验收组织");
    await bootstrap.locator('[name="organization_slug"]').fill(organizationSlug);
    await bootstrap.locator('[name="display_name"]').fill("验收负责人");
    await bootstrap.locator('[name="email"]').fill(ownerEmail);
    await bootstrap.locator('[name="password"]').fill(password);
    await bootstrap.locator('button[type="submit"]').click();
    await page.locator("#workspace").waitFor({ state: "visible" });

    await page.locator('[data-page="assets"]').click();
    const brandName = page.locator('#brand-form [name="name"]');
    await brandName.fill(businessName);
    await page.locator('#brand-form [name="story"]').fill("这是业务数据，不应因界面切换而改变。");
    await page.locator('#brand-form [name="voice"]').fill("清晰、可信");

    await selectLocale(page, "en");
    assert.equal(await brandName.inputValue(), businessName, "locale switch changed form input");
    await selectLocale(page, "zh-HK");
    assert.equal(await brandName.inputValue(), businessName, "second locale switch changed form input");
    await page.locator("#brand-save-button").click();
    await page.locator("#asset-list h3", { hasText: businessName }).waitFor();

    for (const [locale, filename] of [
      ["zh-CN", "workspace-zh-CN.png"],
      ["zh-HK", "workspace-zh-HK.png"],
      ["en", "workspace-en.png"],
    ]) {
      await selectLocale(page, locale);
      assert.equal(await page.locator("#asset-list h3", { hasText: businessName }).count(), 1);
      await expectNoHorizontalOverflow(page, `workspace ${locale}`);
      await screenshot(page, filename);
    }

    const ownerToken = await page.evaluate(() => localStorage.getItem("heyu_token"));
    assert.ok(ownerToken, "owner token missing after bootstrap");
    const invitationResponse = await context.request.post(`${baseUrl}/v1/invitations`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: { email: invitedEmail, role: "creator", expires_in_hours: 24 },
    });
    assert.equal(invitationResponse.status(), 201);
    const invitation = await invitationResponse.json();
    assert.ok(invitation.token);

    const inviteContext = await browser.newContext({ viewport: { width: 1050, height: 800 } });
    const invitePage = await inviteContext.newPage();
    await invitePage.goto(`${baseUrl}/workspace/#invite=${encodeURIComponent(invitation.token)}`, {
      waitUntil: "networkidle",
    });
    assert.equal(invitePage.url(), `${baseUrl}/workspace/`, "invitation token remained in address bar");
    await invitePage.locator("#invite-accept-form").waitFor({ state: "visible" });
    await invitePage.getByText(invitedEmail, { exact: false }).waitFor();
    await screenshot(invitePage, "invitation-inspected.png");
    await invitePage.locator('#invite-accept-form [name="display_name"]').fill("内容创作者");
    await invitePage.locator('#invite-accept-form [name="password"]').fill(password);
    await invitePage.locator('#invite-accept-form button[type="submit"]').click();
    await invitePage.locator("#workspace").waitFor({ state: "visible" });

    const repeatedInspect = await inviteContext.request.post(`${baseUrl}/v1/invitations/inspect`, {
      data: { token: invitation.token },
    });
    assert.equal(repeatedInspect.status(), 200);
    assert.equal(repeatedInspect.headers()["cache-control"], "no-store");
    assert.ok((await repeatedInspect.json()).accepted_at, "used invitation was not marked accepted");
    const repeatedAccept = await inviteContext.request.post(`${baseUrl}/v1/invitations/accept`, {
      data: { token: invitation.token, display_name: "重复接受", password },
    });
    assert.ok([400, 404, 409, 410, 422].includes(repeatedAccept.status()));
    assert.equal(repeatedAccept.headers()["cache-control"], "no-store");

    await invitePage.setViewportSize({ width: 700, height: 900 });
    await invitePage.reload({ waitUntil: "networkidle" });
    await invitePage.locator("#workspace").waitFor({ state: "visible" });
    await expectNoHorizontalOverflow(invitePage, "workspace 700px");
    await screenshot(invitePage, "workspace-700px.png");

    await invitePage.setViewportSize({ width: 390, height: 844 });
    await invitePage.reload({ waitUntil: "networkidle" });
    await invitePage.locator("#workspace").waitFor({ state: "visible" });
    await expectNoHorizontalOverflow(invitePage, "workspace 390px");
    await screenshot(invitePage, "workspace-390px.png");
    await inviteContext.close();
    await context.tracing.stop({ path: path.join(outputDir, "trace.zip") });
    await context.close();

    console.log(`Browser E2E passed. Evidence: ${outputDir}`);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

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
const revokedEmail = `revoked-${unique}@heyu.example`;
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

async function openWorkspacePage(page, name) {
  await page.locator(`[data-page="${name}"]`).click();
  await page.locator(`[data-page-panel="${name}"]`).waitFor({ state: "visible" });
}

async function expectHiddenOrAbsent(page, selector, label) {
  const locator = page.locator(selector);
  for (let index = 0; index < await locator.count(); index += 1) {
    assert.equal(
      await locator.nth(index).isVisible(),
      false,
      `${label} remained visible to a viewer`,
    );
  }
}

async function expectReadOnlyNotice(page, locale) {
  const candidates = page.locator(
    [
      "[data-readonly-notice]",
      "[data-read-only-notice]",
      "#readonly-notice",
      "#read-only-notice",
      ".readonly-notice",
      ".read-only-notice",
      "[data-role-notice]",
      "#role-notice",
      ".role-notice",
      '[data-access-mode="readonly"]',
      '[data-access-mode="viewer"]',
    ].join(","),
  );
  let noticeText = "";
  for (let index = 0; index < await candidates.count(); index += 1) {
    const candidate = candidates.nth(index);
    if (await candidate.isVisible()) {
      noticeText = (await candidate.textContent()).trim();
      if (noticeText) break;
    }
  }
  assert.ok(noticeText, `${locale} did not show a visible read-only notice`);
  const localePatterns = {
    "zh-CN": /只读/,
    "zh-HK": /唯讀|只讀/,
    en: /read[\s-]?only|view[\s-]?only/i,
  };
  assert.match(noticeText, localePatterns[locale], `${locale} read-only notice was not localized`);
  return noticeText;
}

async function expectSimpleModeLocale(page, locale, expectedCases, expectedPlatforms) {
  await page.goto(`${baseUrl}/create/?lang=${locale}`, { waitUntil: "networkidle" });
  assert.equal(await page.locator("[data-demo-case]").count(), 3);
  for (const label of expectedCases) {
    await page.getByText(label, { exact: true }).waitFor();
  }
  for (const label of expectedPlatforms) {
    await page.getByText(label, { exact: true }).waitFor();
  }
  const generationLabels = {
    "zh-CN": ["选择生成方式", "规则 Demo", "真实模型", "外部热点源（可选）"],
    "zh-HK": ["選擇生成方式", "規則 Demo", "真實模型", "外部熱點來源（可選）"],
    en: ["Choose how to generate", "Rules demo", "Live model", "External trend feeds (optional)"],
  };
  for (const label of generationLabels[locale]) {
    await page.getByText(label, { exact: true }).waitFor();
  }
  assert.equal(
    await page.locator('[name="generation_mode"][value="rules"]').isChecked(),
    true,
    `${locale} did not default to the rules demo`,
  );
  const visibleText = await page.locator("body").innerText();
  assert.doesNotMatch(
    visibleText,
    /�|(?:Ã.|Â.|â€|ðŸ)|(?:绂捐|鍐滀|闁嬪|鐢熸垚)/,
    `simple mode ${locale} contains mojibake`,
  );
  await expectNoHorizontalOverflow(page, `simple mode ${locale}`);
}

async function generateDemoCase(
  page,
  caseId,
  expectedProduct,
  expectedPlatformValue,
  expectedPlatformName,
  expectedNextActionsLabel,
) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${baseUrl}/v1/marketing/preview` &&
      response.request().method() === "POST",
  );
  await page.locator(`[data-demo-case="${caseId}"]`).click();
  const response = await responsePromise;
  assert.equal(response.status(), 200, `${caseId} preview request failed`);
  await page.locator("#result-state").waitFor({ state: "visible" });
  assert.equal(await page.locator("#provider-meta").getAttribute("data-generation-mode"), "rules");
  assert.equal(await page.locator("#provider-meta").getAttribute("data-degraded"), "false");
  assert.equal((await page.locator("#result-product").textContent()).trim(), expectedProduct);
  assert.equal(
    await page.locator(`[data-demo-case="${caseId}"]`).evaluate((node) =>
      node.classList.contains("active"),
    ),
    true,
    `${caseId} demo button was not marked active`,
  );
  assert.equal(
    await page.locator(`[name="platform"][value="${expectedPlatformValue}"]`).isChecked(),
    true,
    `${caseId} did not select ${expectedPlatformValue}`,
  );
  assert.equal(await page.locator(".result-tabs button").count(), 6);
  const strategyCards = page.locator("#result-content .result-card");
  assert.ok((await strategyCards.count()) >= 2);
  await strategyCards.nth(1).getByText(expectedPlatformName, { exact: false }).waitFor();
  const nextActionsCard = strategyCards.filter({ hasText: expectedNextActionsLabel });
  await nextActionsCard.waitFor();
  const nextActions = nextActionsCard.locator("li");
  assert.ok(
    (await nextActions.count()) >= 3 && (await nextActions.count()) <= 6,
    `${caseId} next actions must contain 3 to 6 items`,
  );
  for (let index = 0; index < await nextActions.count(); index += 1) {
    assert.ok((await nextActions.nth(index).innerText()).trim(), "next action must not be empty");
  }

  await page.locator('[data-tab="topics"]').click();
  assert.ok(await page.locator("#result-content .topic-card").count());
  await page.locator('[data-tab="routes"]').click();
  assert.equal(await page.locator("#result-content .route-card").count(), 3);
  assert.equal(await page.locator("#result-content .route-card.recommended").count(), 1);
  await page.locator('[data-select-route="1"]').click();
  assert.equal(await page.locator("#result-content .route-card.selected").count(), 1);
  await page.locator('[data-tab="prep"]').click();
  assert.ok(await page.locator("#result-content .prep-hero").count());
  await page.locator('[data-tab="live"]').click();
  assert.ok(await page.locator("#result-content .result-card").count());
  await page.locator('[data-tab="calendar"]').click();
  assert.equal(await page.locator("#result-content .day-list > li").count(), 7);
  assert.ok(await page.locator("#result-content [data-save-plan]").count());
  const resultText = await page.locator("#result-state").innerText();
  assert.doesNotMatch(
    resultText,
    /�|(?:Ã.|Â.|â€|ðŸ)|(?:绂捐|鍐滀|闁嬪|鐢熸垚)/,
    `${caseId} result contains mojibake`,
  );
}

async function expectLocalizedClaimError(page, locale, riskyDescription, expectedMessage) {
  await page.goto(`${baseUrl}/create/?lang=${locale}`, { waitUntil: "networkidle" });
  await page.locator('[name="product_name"]').fill(
    locale === "en" ? "Risk check tomatoes" : "宣传检查番茄",
  );
  await page.locator('[name="product_description"]').fill(riskyDescription);

  let dialogMessage = "";
  const dialogHandled = new Promise((resolve) => {
    page.once("dialog", async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.accept();
      resolve();
    });
  });
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url() === `${baseUrl}/v1/marketing/preview` &&
      response.request().method() === "POST",
  );
  await page.locator('#marketing-form [type="submit"]').click();
  const response = await responsePromise;
  assert.equal(response.status(), 422, `${locale} risky claim was not rejected`);
  await dialogHandled;
  assert.equal(dialogMessage, expectedMessage, `${locale} claim error was not localized`);
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
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.addInitScript(() => {
      window.__heyuUnhandledRejections = [];
      window.addEventListener("unhandledrejection", (event) => {
        const reason = event.reason;
        window.__heyuUnhandledRejections.push(
          reason instanceof Error ? reason.message : String(reason),
        );
      });
    });

    for (const [locale, expected, filename] of [
      ["zh-CN", "生成第一份内容方案", "landing-zh-CN.png"],
      ["zh-HK", "產生第一份內容方案", "landing-zh-HK.png"],
      ["en", "Create your first content plan", "landing-en.png"],
    ]) {
      await page.goto(`${baseUrl}/?lang=${locale}`, { waitUntil: "networkidle" });
      await assert.doesNotReject(() => page.getByText(expected, { exact: false }).first().waitFor());
      await expectNoHorizontalOverflow(page, `landing ${locale}`);
      await screenshot(page, filename);
    }

    for (const [locale, cases, platforms, nextActionsLabel] of [
      [
        "zh-CN",
        [
          ["tomato", "番茄", "当季番茄", "douyin", "抖音"],
          ["tea", "高山茶叶", "高山云雾茶", "xiaohongshu", "小红书"],
          ["fruit", "当季水果", "岭南当季水果礼盒", "wechat-channels", "视频号"],
        ],
        ["抖音", "小红书", "视频号", "快手"],
        "接下来就这样做",
      ],
      [
        "zh-HK",
        [
          ["tomato", "番茄", "時令番茄", "douyin", "抖音"],
          ["tea", "高山茶葉", "高山雲霧茶", "xiaohongshu", "小紅書"],
          ["fruit", "時令水果", "嶺南時令水果禮盒", "wechat-channels", "視頻號"],
        ],
        ["抖音", "小紅書", "視頻號", "快手"],
        "接下來就這樣做",
      ],
      [
        "en",
        [
          ["tomato", "Tomatoes", "Seasonal tomatoes", "douyin", "Douyin"],
          ["tea", "High-mountain tea", "High-mountain mist tea", "xiaohongshu", "Xiaohongshu"],
          ["fruit", "Seasonal fruit", "Lingnan seasonal fruit box", "wechat-channels", "WeChat Channels"],
        ],
        ["Douyin", "Xiaohongshu", "WeChat Channels", "Kuaishou"],
        "What to do next",
      ],
    ]) {
      await expectSimpleModeLocale(
        page,
        locale,
        cases.map(([, label]) => label),
        platforms,
      );
      await screenshot(page, `simple-mode-${locale}.png`);
      for (const [caseId, , product, platformValue, platformName] of cases) {
        await generateDemoCase(
          page,
          caseId,
          product,
          platformValue,
          platformName,
          nextActionsLabel,
        );
        await screenshot(
          page,
          locale === "zh-CN"
            ? `simple-mode-${caseId}.png`
            : `simple-mode-${locale}-${caseId}.png`,
        );
      }
    }

    await page.goto(`${baseUrl}/create/?lang=zh-CN`, { waitUntil: "networkidle" });
    await generateDemoCase(
      page,
      "tomato",
      "当季番茄",
      "douyin",
      "抖音",
      "接下来就这样做",
    );
    const productBeforeLocaleSwitch = await page.locator("#result-product").textContent();
    for (const [locale, tabLabel] of [
      ["zh-HK", "創意路線"],
      ["en", "Creative routes"],
      ["zh-CN", "创意路线"],
    ]) {
      await selectLocale(page, locale);
      assert.equal(
        await page.locator("#result-product").textContent(),
        productBeforeLocaleSwitch,
        `locale switch to ${locale} changed the generated product`,
      );
      await page.getByRole("button", { name: tabLabel, exact: true }).waitFor();
    }

    for (const [locale, description, message] of [
      [
        "zh-CN",
        "自然成熟的番茄，可以降血糖，适合每天食用。",
        "输入中包含需要核验的医疗、认证或绝对化宣传，请修改后再生成。",
      ],
      [
        "zh-HK",
        "自然成熟的番茄，可以降血糖，適合每天食用。",
        "輸入中包含需要核實的醫療、認證或絕對化宣傳，請修改後再生成。",
      ],
      [
        "en",
        "Naturally ripened tomatoes that treat cancer and suit everyday meals.",
        "The brief contains a medical, certification or absolute claim that must be verified before generation.",
      ],
    ]) {
      await expectLocalizedClaimError(page, locale, description, message);
    }

    const simpleMobileContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
    });
    const simpleMobilePage = await simpleMobileContext.newPage();
    const simpleMobileErrors = [];
    simpleMobilePage.on("pageerror", (error) => simpleMobileErrors.push(error.message));
    await simpleMobilePage.goto(`${baseUrl}/create/?lang=zh-CN`, {
      waitUntil: "networkidle",
    });
    await generateDemoCase(
      simpleMobilePage,
      "tomato",
      "当季番茄",
      "douyin",
      "抖音",
      "接下来就这样做",
    );
    await expectNoHorizontalOverflow(simpleMobilePage, "simple mode 390px");
    await screenshot(simpleMobilePage, "simple-mode-390px.png");
    assert.deepEqual(simpleMobileErrors, [], `simple mode page errors: ${simpleMobileErrors}`);
    await simpleMobileContext.close();

    const englishMobileContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
    });
    const englishMobilePage = await englishMobileContext.newPage();
    await englishMobilePage.goto(`${baseUrl}/create/?lang=en`, { waitUntil: "networkidle" });
    await generateDemoCase(
      englishMobilePage,
      "fruit",
      "Lingnan seasonal fruit box",
      "wechat-channels",
      "WeChat Channels",
      "What to do next",
    );
    await englishMobilePage.locator('[data-tab="strategy"]').click();
    await expectNoHorizontalOverflow(englishMobilePage, "English fruit strategy 390px");
    await screenshot(englishMobilePage, "simple-mode-en-fruit-strategy-390px.png");
    await englishMobileContext.close();

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

    await selectLocale(page, "en");
    const ownerToken = await page.evaluate(() => localStorage.getItem("heyu_token"));
    assert.ok(ownerToken, "owner token missing after bootstrap");

    await page.goto(`${baseUrl}/create/?lang=en`, { waitUntil: "networkidle" });
    await generateDemoCase(
      page,
      "tomato",
      "Seasonal tomatoes",
      "douyin",
      "Douyin",
      "What to do next",
    );
    let trendRequestPayload;
    await page.route(
      "**/v1/trends/discover",
      async (route) => {
        trendRequestPayload = route.request().postDataJSON();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [
              {
                candidate: {
                  title: "seasonal produce and everyday family meals",
                  source_url: "https://feeds.example.test/agriculture.xml",
                  source_label: "Agriculture feed",
                  captured_at: "2026-07-16T00:00:00Z",
                  published_at: "2026-07-15T00:00:00Z",
                  source_type: "rss",
                  summary: "A traceable RSS item for the browser path.",
                },
                fit: {
                  product: { score: 90, explanation: "Product fit" },
                  selling_points: { score: 88, explanation: "Selling point fit" },
                  audience: { score: 84, explanation: "Audience fit" },
                  platform: { score: 82, explanation: "Platform fit" },
                  timeliness: { score: 86, explanation: "Timely" },
                  filmability: { score: 91, explanation: "Easy to film" },
                },
                fit_score: 87,
                recommendation: "recommended",
                recommendation_reason: "Relevant and practical.",
              },
            ],
            warnings: [],
            used_fallback: false,
            metric_note: "Fit score is not a real-time popularity metric.",
          }),
        });
      },
      { times: 1 },
    );
    await page
      .locator('[name="feed_sources"]')
      .fill("Agriculture feed | https://feeds.example.test/agriculture.xml");
    await page.locator('[name="generation_mode"][value="model"]').check();
    await page.getByText("Live model mode", { exact: true }).waitFor();
    const liveGenerationResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${baseUrl}/v1/marketing/generate` &&
        response.request().method() === "POST",
    );
    await page.locator('#marketing-form [type="submit"]').click();
    const liveGenerationResponse = await liveGenerationResponsePromise;
    assert.equal(liveGenerationResponse.status(), 200, "live model generation request failed");
    assert.ok(trendRequestPayload, "trend discovery request was not captured");
    assert.deepEqual(trendRequestPayload.feed_sources, [
      {
        url: "https://feeds.example.test/agriculture.xml",
        label: "Agriculture feed",
      },
    ]);
    assert.equal(
      liveGenerationResponse.request().headers().authorization,
      `Bearer ${ownerToken}`,
      "live model generation did not use the signed-in team token",
    );
    const liveGeneration = await liveGenerationResponse.json();
    const providerMeta = page.locator("#provider-meta");
    await providerMeta.waitFor();
    assert.equal(await providerMeta.getAttribute("data-generation-mode"), "model");
    assert.equal(
      await providerMeta.getAttribute("data-degraded"),
      String(Boolean(liveGeneration.degraded)),
    );
    assert.match(await providerMeta.innerText(), new RegExp(liveGeneration.provider, "i"));
    const createMarketingPlanResponsePromise = page.waitForResponse(
      (response) =>
        response.url() === `${baseUrl}/v1/marketing-plans` &&
        response.request().method() === "POST",
    );
    await page.locator("#save-result").click();
    const createMarketingPlanResponse = await createMarketingPlanResponsePromise;
    assert.equal(createMarketingPlanResponse.status(), 201, "owner could not save tomato plan");
    const savedMarketingPlan = await createMarketingPlanResponse.json();
    assert.equal(savedMarketingPlan.current_version.version_number, 1);
    assert.match(savedMarketingPlan.product_name, /tomato/i);
    await page.locator("#open-saved-plan").waitFor({ state: "visible" });
    const savedRouteDownloads = page.locator("#route-downloads [data-download-route]");
    assert.equal(await savedRouteDownloads.count(), 3, "saved plan did not expose all route kits");
    let exportAuthorization = "";
    await page.route(
      `**/v1/marketing-plans/${savedMarketingPlan.id}/export?route_id=practical-hook`,
      async (route) => {
        exportAuthorization = route.request().headers().authorization || "";
        await route.fulfill({
          status: 200,
          contentType: "application/zip",
          headers: {
            "Content-Disposition": "attachment; filename=seasonal-tomatoes-practical-hook.zip",
          },
          body: Buffer.from("browser-e2e-publishing-kit"),
        });
      },
      { times: 1 },
    );
    const routeDownloadPromise = page.waitForEvent("download");
    await page
      .locator('#route-downloads [data-download-route="practical-hook"]')
      .click();
    const routeDownload = await routeDownloadPromise;
    assert.equal(
      routeDownload.suggestedFilename(),
      "seasonal-tomatoes-practical-hook.zip",
    );
    assert.equal(
      exportAuthorization,
      `Bearer ${ownerToken}`,
      "publishing kit export did not use the signed-in team token",
    );
    await Promise.all([
      page.waitForURL(
        `${baseUrl}/workspace/plans?plan=${encodeURIComponent(savedMarketingPlan.id)}`,
      ),
      page.locator("#open-saved-plan").click(),
    ]);
    await page.locator("#workspace").waitFor({ state: "visible" });
    await page.locator('[data-page-panel="plans"]').waitFor({ state: "visible" });
    await page.locator("#marketing-plan-detail").waitFor({ state: "visible" });
    await page.locator("#marketing-plan-title", { hasText: /tomato/i }).waitFor();
    assert.equal(
      await page.locator("#marketing-plan-preview .plan-video-card").count(),
      3,
      "saved plan did not render three video concepts",
    );
    assert.equal(
      await page.locator("#marketing-plan-preview .plan-calendar article").count(),
      7,
      "saved plan did not render the seven-day operating plan",
    );

    const updatedPositioning = `E2E tomato positioning ${unique}`;
    await page.locator(".plan-editor-wrap").evaluate((element) => {
      element.open = true;
    });
    const initialPlanContent = JSON.parse(
      await page.locator("#marketing-plan-editor").inputValue(),
    );
    initialPlanContent.product_profile.one_line_value = updatedPositioning;
    await page
      .locator("#marketing-plan-editor")
      .fill(JSON.stringify(initialPlanContent, null, 2));
    await page
      .locator("#marketing-plan-change-summary")
      .fill("Browser E2E positioning update");
    const versionResponsePromise = page.waitForResponse(
      (response) =>
        response.url() ===
          `${baseUrl}/v1/marketing-plans/${savedMarketingPlan.id}/versions` &&
        response.request().method() === "POST",
    );
    await page.locator("#save-marketing-plan-version").click();
    const versionResponse = await versionResponsePromise;
    assert.equal(versionResponse.status(), 201, "owner could not save marketing plan v2");
    const versionedMarketingPlan = await versionResponse.json();
    assert.equal(versionedMarketingPlan.current_version.version_number, 2);
    assert.equal(
      versionedMarketingPlan.current_version.content.product_profile.one_line_value,
      updatedPositioning,
    );
    const marketingPlanVersionButtons = page.locator("#marketing-plan-versions button");
    await marketingPlanVersionButtons.nth(1).waitFor();
    assert.equal(await marketingPlanVersionButtons.count(), 2);

    const versionOneButton = page.locator(
      '#marketing-plan-versions button:has(b:text-is("v1"))',
    );
    const versionTwoButton = page.locator(
      '#marketing-plan-versions button:has(b:text-is("v2"))',
    );
    await versionOneButton.click();
    const versionOneContent = JSON.parse(
      await page.locator("#marketing-plan-editor").inputValue(),
    );
    assert.notEqual(
      versionOneContent.product_profile.one_line_value,
      updatedPositioning,
      "saving v2 overwrote v1",
    );
    await versionTwoButton.click();
    assert.equal(
      JSON.parse(await page.locator("#marketing-plan-editor").inputValue()).product_profile
        .one_line_value,
      updatedPositioning,
      "v2 could not be reopened",
    );

    const copyResponsePromise = page.waitForResponse(
      (response) =>
        response.url() ===
          `${baseUrl}/v1/marketing-plans/${savedMarketingPlan.id}/copy` &&
        response.request().method() === "POST",
    );
    await page.locator("#copy-marketing-plan").click();
    const copyResponse = await copyResponsePromise;
    assert.equal(copyResponse.status(), 201, "owner could not copy marketing plan");
    const copiedMarketingPlan = await copyResponse.json();
    assert.notEqual(copiedMarketingPlan.id, savedMarketingPlan.id);
    assert.equal(copiedMarketingPlan.current_version.version_number, 1);
    await page.waitForURL(
      `${baseUrl}/workspace/plans?plan=${encodeURIComponent(copiedMarketingPlan.id)}`,
    );
    assert.equal(await page.locator("#marketing-plan-version-count").textContent(), "1");

    const localizedPlanHeadings = new Set();
    for (const locale of ["zh-CN", "zh-HK", "en"]) {
      await selectLocale(page, locale);
      const expectedHeading = await page.evaluate(() => HeyuI18n.t("marketingPlans.heading"));
      const heading = page.locator('[data-i18n="marketingPlans.heading"]');
      await heading.waitFor({ state: "visible" });
      assert.equal((await heading.textContent()).trim(), expectedHeading);
      localizedPlanHeadings.add(expectedHeading);
    }
    await screenshot(page, "marketing-plan-owner-v2-copy.png");

    await openWorkspacePage(page, "assets");
    const brandsResponse = await context.request.get(`${baseUrl}/v1/brands`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    assert.equal(brandsResponse.status(), 200);
    const brand = (await brandsResponse.json()).find((item) => item.name === businessName);
    assert.ok(brand, "created brand not returned by API");

    const productName = `Harvest tomato ${unique}`;
    await page.locator('#product-form [name="brand_id"]').selectOption(brand.id);
    await page.locator('#product-form [name="name"]').fill(productName);
    await page.locator('#product-form [name="origin"]').fill("Verified demonstration field");
    await page.locator('#product-form [name="specification"]').fill("500 g");
    await page.locator("#product-save-button").click();
    await page.locator("#asset-list h3", { hasText: productName }).waitFor();

    const productsResponse = await context.request.get(`${baseUrl}/v1/products`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    assert.equal(productsResponse.status(), 200);
    const product = (await productsResponse.json()).find((item) => item.name === productName);
    assert.ok(product, "created product not returned by API");

    const sourceResponse = await context.request.post(`${baseUrl}/v1/knowledge`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: {
        title: "Browser E2E verified fact",
        kind: "product_fact",
        content: "The demonstration product is harvested by hand.",
        citation_label: "Browser E2E fact 1",
        brand_id: brand.id,
        product_id: product.id,
      },
    });
    assert.equal(sourceResponse.status(), 201);
    const source = await sourceResponse.json();
    assert.equal(
      (
        await context.request.post(`${baseUrl}/v1/knowledge/${source.id}/submit`, {
          headers: { Authorization: `Bearer ${ownerToken}` },
        })
      ).status(),
      200,
    );
    assert.equal(
      (
        await context.request.post(`${baseUrl}/v1/knowledge/${source.id}/review`, {
          headers: { Authorization: `Bearer ${ownerToken}` },
          data: { status: "approved", note: "Browser E2E reviewed" },
        })
      ).status(),
      200,
    );
    const projectResponse = await context.request.post(`${baseUrl}/v1/content-projects`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: {
        brand_id: brand.id,
        product_id: product.id,
        title: `Review-gated project ${unique}`,
        content_type: "social_post",
      },
    });
    assert.equal(projectResponse.status(), 201);
    const project = await projectResponse.json();
    const secondProjectResponse = await context.request.post(`${baseUrl}/v1/content-projects`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: {
        brand_id: brand.id,
        product_id: product.id,
        title: `Project switch regression ${unique}`,
        content_type: "title_and_cover",
      },
    });
    assert.equal(secondProjectResponse.status(), 201);
    const secondProject = await secondProjectResponse.json();

    await page.reload({ waitUntil: "networkidle" });
    await page.locator("#workspace").waitFor({ state: "visible" });
    await page.locator('[data-page="studio"]').click();
    await page.locator("#project-select").selectOption(project.id);
    await page.locator("#generate-button").click();
    await page.locator("#toast.error").waitFor({ state: "visible" });
    assert.match(await page.locator("#toast").textContent(), /approved brand and product assets/i);

    await page.locator('[data-page="assets"]').click();
    for (const name of [businessName, productName]) {
      const card = page.locator("#asset-list article", { has: page.getByRole("heading", { name }) });
      await card.locator("[data-submit-asset]").click();
      await card.locator('[data-review-asset][data-status="approved"]').waitFor();
      page.once("dialog", (dialog) => dialog.accept("Browser E2E fact review"));
      await card.locator('[data-review-asset][data-status="approved"]').click();
      await card.locator(".badge.approved").waitFor();
    }

    await page.locator('[data-page="studio"]').click();
    await page.locator("#project-select").selectOption(project.id);
    await page.locator("#generate-button").click();
    await page.locator("#content-toolbar").waitFor({ state: "visible" });
    await page.locator("#edit-version").waitFor({ state: "visible" });
    assert.notEqual(await page.locator("#version-editor").inputValue(), "");

    await page.locator("#project-select").selectOption(secondProject.id);
    await page.locator("#content-toolbar").waitFor({ state: "hidden" });
    await page.locator("#edit-version").waitFor({ state: "hidden" });
    assert.equal(await page.locator("#version-editor").inputValue(), "");
    assert.equal(await page.locator("#generation-output").textContent(), "");
    assert.equal(await page.locator("#generation-provenance").count(), 0);
    await page.locator("#project-select").selectOption(project.id);

    await page.locator('[data-page="assets"]').click();
    const productCard = page.locator("#asset-list article", {
      has: page.getByRole("heading", { name: productName }),
    });
    await productCard.locator("[data-edit-product]").click();
    await page.locator('#product-form [name="origin"]').fill("Changed after approval");
    await page.locator("#product-save-button").click();
    await productCard.locator(".badge.draft").waitFor();

    await page.locator('[data-page="studio"]').click();
    await page.locator("#project-select").selectOption(project.id);
    await page.locator("#generate-button").click();
    await page.locator("#toast.error").waitFor({ state: "visible" });
    assert.match(await page.locator("#toast").textContent(), /pending: product/i);

    assert.equal(
      (
        await context.request.post(`${baseUrl}/v1/products/${product.id}/submit`, {
          headers: { Authorization: `Bearer ${ownerToken}` },
        })
      ).status(),
      200,
    );
    assert.equal(
      (
        await context.request.post(`${baseUrl}/v1/products/${product.id}/review`, {
          headers: { Authorization: `Bearer ${ownerToken}` },
          data: { status: "approved", note: "Approved for failure-path E2E" },
        })
      ).status(),
      200,
    );
    const campaignResponse = await context.request.post(`${baseUrl}/v1/campaign-packages`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: {
        brand_id: brand.id,
        product_id: product.id,
        title: `Verified farmer campaign ${unique}`,
        platform: "Instagram",
        target_audience: "Customers who value transparent sourcing",
        objective: "Support farmers through a verified direct-purchase campaign.",
        tone: "Clear and factual",
        extra_requirements: "Only use approved farmer-support claims.",
        create_default_items: true,
      },
    });
    assert.equal(campaignResponse.status(), 201);
    const campaign = await campaignResponse.json();

    await page.goto(`${baseUrl}/workspace/campaigns?lang=en`, { waitUntil: "networkidle" });
    await page.locator("#workspace").waitFor({ state: "visible" });
    await page.locator('[data-page-panel="campaigns"]').waitFor({ state: "visible" });
    assert.equal(
      new URL(page.url()).pathname,
      "/workspace/campaigns",
      "direct campaign workspace navigation did not preserve the route",
    );
    await page
      .locator("#campaign-list article", { hasText: campaign.title })
      .locator("li", { hasText: "Mobile shooting checklist" })
      .waitFor();

    await page.locator("#campaign-brief-campaign-select").selectOption(campaign.id);
    assert.equal(
      await page.locator("#campaign-brief-campaign-select").inputValue(),
      campaign.id,
      "campaign brief workbench did not select the requested campaign",
    );
    const campaignBriefForm = page.locator("#campaign-brief-form");
    await campaignBriefForm.locator('[name="platform"]').fill("Instagram");
    await campaignBriefForm.locator('[name="locale"]').selectOption("en");
    await campaignBriefForm
      .locator('[name="target_audience"]')
      .fill("Customers who value transparent sourcing");
    await campaignBriefForm
      .locator('[name="audience_need"]')
      .fill("A concise reason to trust the product story.");
    await campaignBriefForm
      .locator('[name="objective"]')
      .fill("Increase consideration for the campaign.");
    await campaignBriefForm
      .locator('[name="core_message"]')
      .fill("Choose a product with a reviewed story.");
    await campaignBriefForm
      .locator('[name="desired_action"]')
      .fill("Read the campaign and consider purchasing.");
    await campaignBriefForm.locator('[name="tone"]').fill("Clear and factual");
    await campaignBriefForm
      .locator('[name="extra_requirements"]')
      .fill("Use only reviewed wording.");
    await campaignBriefForm
      .locator('[name="change_summary"]')
      .fill("Browser E2E evidence-backed revision");
    await page.evaluate(() => render());
    assert.equal(
      await campaignBriefForm.locator('[name="core_message"]').inputValue(),
      "Choose a product with a reviewed story.",
      "an unrelated workspace render reset the in-progress campaign brief form",
    );
    const claimRow = page.locator("#campaign-brief-claims .claim-row").first();
    await claimRow
      .locator('[data-claim-field="claim_text"]')
      .fill("The demonstration product is harvested by hand.");
    await claimRow.locator('[data-claim-field="claim_type"]').selectOption("product_fact");
    await claimRow
      .locator('[data-claim-field="source_type"]')
      .selectOption("knowledge_source");
    await claimRow.locator('[data-claim-field="source_id"]').selectOption(source.id);
    assert.equal(
      await claimRow.locator('[data-claim-field="evidence_key"]').inputValue(),
      "content",
      "knowledge-source claims must map to the source content field",
    );

    const [briefCreateResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url() === `${baseUrl}/v1/campaign-packages/${campaign.id}/brief-revisions` &&
          response.request().method() === "POST",
      ),
      campaignBriefForm.locator('button[type="submit"]').click(),
    ]);
    assert.equal(briefCreateResponse.status(), 201);
    const briefRevision = await briefCreateResponse.json();
    const briefCard = page.locator("#campaign-brief-history article", {
      hasText: "Browser E2E evidence-backed revision",
    });
    await briefCard.waitFor();
    await briefCard.locator(".brief-score strong", { hasText: "1/1" }).waitFor();

    const evidenceMapResponse = await context.request.get(
      `${baseUrl}/v1/campaign-packages/${campaign.id}/brief-revisions/${briefRevision.id}/claim-evidence-map`,
      { headers: { Authorization: `Bearer ${ownerToken}` } },
    );
    assert.equal(evidenceMapResponse.status(), 200);
    const evidenceMap = await evidenceMapResponse.json();
    assert.equal(evidenceMap.complete, true, `brief evidence map blockers: ${evidenceMap.blockers}`);
    assert.equal(evidenceMap.mapped_claims, 1);
    assert.equal(evidenceMap.total_claims, 1);
    assert.deepEqual(evidenceMap.blockers, []);

    const [briefSubmitResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url() ===
            `${baseUrl}/v1/campaign-packages/${campaign.id}/brief-revisions/${briefRevision.id}/submit` &&
          response.request().method() === "POST",
      ),
      briefCard.locator("[data-submit-campaign-brief]").click(),
    ]);
    assert.equal(briefSubmitResponse.status(), 200);
    await briefCard.locator(".badge.pending_review").waitFor();

    page.once("dialog", (dialog) => dialog.accept("Browser E2E brief reviewed"));
    const [briefReviewResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url() ===
            `${baseUrl}/v1/campaign-packages/${campaign.id}/brief-revisions/${briefRevision.id}/review` &&
          response.request().method() === "POST",
      ),
      briefCard.locator(
        `[data-review-campaign-brief="${briefRevision.id}"][data-status="approved"]`,
      ).click(),
    ]);
    assert.equal(briefReviewResponse.status(), 200);
    await briefCard.locator(".badge.approved").first().waitFor();
    await page
      .locator("#campaign-list article", { hasText: campaign.title })
      .locator(".readiness-chip.ready", { hasText: /Brief ready/i })
      .waitFor();
    await page.evaluate((campaignId) => {
      const selected = state.campaigns.find((item) => item.id === campaignId);
      selected.progress.generation_ready = false;
      selected.progress.generation_blockers = ["campaign_claim_evidence_stale"];
      renderCampaigns();
    }, campaign.id);
    const blockedCampaignCard = page.locator("#campaign-list article", {
      hasText: campaign.title,
    });
    await blockedCampaignCard
      .locator(".campaign-generation-blockers", {
        hasText: /Evidence linked to the campaign brief has changed/i,
      })
      .waitFor();
    assert.equal(
      await blockedCampaignCard.locator("[data-generate-campaign-item]").count(),
      0,
      "campaign generation actions remained visible while the backend reported blockers",
    );
    await page.evaluate(() => refresh());
    assert.deepEqual(
      await page.evaluate(() => window.__heyuUnhandledRejections),
      [],
      "campaign brief flow emitted an unhandled promise rejection",
    );

    await page.locator("#farmer-evidence-campaign-select").selectOption(campaign.id);
    const farmerEvidenceForm = page.locator("#farmer-evidence-form");
    await farmerEvidenceForm.locator('[name="party_display_name"]').fill("Browser E2E Cooperative");
    await farmerEvidenceForm.locator('[name="relationship_type"]').selectOption("direct_purchase");
    await farmerEvidenceForm
      .locator('[name="relationship_summary"]')
      .fill("The campaign purchases the listed product directly from the cooperative.");
    await farmerEvidenceForm
      .locator('[name="benefit_mechanism"]')
      .fill("The cooperative receives the agreed purchase price for accepted deliveries.");
    const activeFrom = new Date(Date.now() - 60 * 60 * 1000).toISOString().slice(0, 16);
    const activeUntil = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 16);
    await farmerEvidenceForm.locator('[name="active_from"]').fill(activeFrom);
    await farmerEvidenceForm.locator('[name="active_until"]').fill(activeUntil);
    await farmerEvidenceForm
      .locator('[name="allowed_claims"][value="general_support"]')
      .check();
    await farmerEvidenceForm
      .locator('[name="allowed_claims"][value="direct_sourcing"]')
      .check();
    await farmerEvidenceForm.locator('[name="consent_scope"][value="party_name"]').check();
    await farmerEvidenceForm.locator('[name="consent_scope"][value="relationship"]').check();
    await farmerEvidenceForm
      .locator(`[name="evidence_source_ids"][value="${source.id}"]`)
      .check();
    await farmerEvidenceForm.locator('button[type="submit"]').click();
    const farmerEvidenceCard = page
      .locator("#farmer-evidence-history article", { hasText: "Browser E2E Cooperative" })
      .first();
    await farmerEvidenceCard.waitFor();
    await farmerEvidenceCard.locator("[data-submit-farmer-evidence]").click();
    await farmerEvidenceCard.locator('[data-review-farmer-evidence][data-status="approved"]').waitFor();
    page.once("dialog", (dialog) => dialog.accept("Relationship evidence reviewed"));
    await farmerEvidenceCard
      .locator('[data-review-farmer-evidence][data-status="approved"]')
      .click();
    await farmerEvidenceCard.locator(".badge.approved").first().waitFor();
    await page
      .locator("#campaign-list article", { hasText: campaign.title })
      .locator(".readiness-chip.ready", { hasText: /Farmer evidence ready/i })
      .waitFor();
    await page.goto(`${baseUrl}/workspace/?lang=en`, { waitUntil: "networkidle" });
    await page.locator("#workspace").waitFor({ state: "visible" });

    const traceableProjectResponse = await context.request.post(
      `${baseUrl}/v1/content-projects`,
      {
        headers: { Authorization: `Bearer ${ownerToken}` },
        data: {
          brand_id: brand.id,
          product_id: product.id,
          title: `[E2E traceable generation] ${unique}`,
          content_type: "social_post",
        },
      },
    );
    assert.equal(traceableProjectResponse.status(), 201);
    const traceableProject = await traceableProjectResponse.json();

    await page.reload({ waitUntil: "networkidle" });
    await page.locator("#workspace").waitFor({ state: "visible" });
    await page.locator('[data-page="studio"]').click();
    await page.locator("#project-select").selectOption(traceableProject.id);
    const [generationResponse] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url() ===
            `${baseUrl}/v1/content-projects/${traceableProject.id}/generate` &&
          response.request().method() === "POST",
      ),
      page.locator("#generate-button").click(),
    ]);
    assert.equal(generationResponse.status(), 201);
    const completedHistory = page.locator("#generation-history-list article", {
      hasText: "social_post",
    });
    await completedHistory.waitFor();
    const completedLabel = await page.evaluate(() =>
      HeyuI18n.t("generationStatus.completed"),
    );
    await completedHistory.getByText(completedLabel, { exact: true }).waitFor();

    const generationRunsResponse = await context.request.get(
      `${baseUrl}/v1/content-projects/${traceableProject.id}/generation-runs`,
      { headers: { Authorization: `Bearer ${ownerToken}` } },
    );
    assert.equal(generationRunsResponse.status(), 200);
    const generationRuns = await generationRunsResponse.json();
    assert.equal(generationRuns.length, 1, "project should have exactly one generation run");
    assert.equal(generationRuns[0].status, "succeeded");
    assert.ok(generationRuns[0].sources.length > 0, "generation should retain source provenance");
    assert.ok(
      generationRuns[0].output?.citations?.length > 0,
      "generation should include at least one trusted source citation",
    );

    const generatedVersionsResponse = await context.request.get(
      `${baseUrl}/v1/content-projects/${traceableProject.id}/versions`,
      { headers: { Authorization: `Bearer ${ownerToken}` } },
    );
    assert.equal(generatedVersionsResponse.status(), 200);
    assert.equal((await generatedVersionsResponse.json()).length, 1);

    await page.reload({ waitUntil: "networkidle" });
    await page.locator("#workspace").waitFor({ state: "visible" });
    await page.locator('[data-page="studio"]').click();
    await page.locator("#project-select").selectOption(traceableProject.id);
    for (const locale of ["zh-CN", "zh-HK", "en"]) {
      await selectLocale(page, locale);
      assert.equal(
        await page.locator("#project-select").inputValue(),
        traceableProject.id,
        `locale switch to ${locale} changed the selected generated project`,
      );
      const expected = await page.evaluate(() => ({
        status: HeyuI18n.t("generationStatus.completed"),
      }));
      const localizedGeneration = page.locator("#generation-history-list article", {
        hasText: "social_post",
      });
      await localizedGeneration.waitFor();
      await localizedGeneration.getByText(expected.status, { exact: true }).waitFor();
    }
    assert.deepEqual(
      await page.evaluate(() => window.__heyuUnhandledRejections),
      [],
      "workspace emitted an unhandled promise rejection",
    );
    await screenshot(page, "generation-traceability-persisted.png");

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

    const revocationResponse = await context.request.post(`${baseUrl}/v1/invitations`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: { email: revokedEmail, role: "viewer", expires_in_hours: 24 },
    });
    assert.equal(revocationResponse.status(), 201);
    assert.equal(revocationResponse.headers()["cache-control"], "no-store");
    const revocableInvitation = await revocationResponse.json();
    await openWorkspacePage(page, "members");
    await page.reload({ waitUntil: "networkidle" });
    await openWorkspacePage(page, "members");
    const revocableRow = page.locator("#invitation-list article", { hasText: revokedEmail });
    await revocableRow.waitFor();
    assert.ok(
      !(await page.locator("#invitation-list").innerText()).includes(revocableInvitation.token),
      "invitation list exposed a plaintext token",
    );
    for (const [locale, expectedStatus] of [
      ["zh-CN", "待接受"],
      ["zh-HK", "待接受"],
      ["en", "Pending"],
    ]) {
      await selectLocale(page, locale);
      await revocableRow.getByText(expectedStatus, { exact: true }).waitFor();
    }
    await selectLocale(page, "zh-CN");
    page.once("dialog", (dialog) => dialog.accept());
    await revocableRow.locator("[data-revoke-invitation]").click();
    await revocableRow.getByText("已撤销", { exact: true }).waitFor();
    assert.equal(
      await revocableRow.locator("[data-revoke-invitation]").count(),
      0,
      "revoked invitation still showed a revoke control",
    );
    const revokedInspect = await context.request.post(`${baseUrl}/v1/invitations/inspect`, {
      data: { token: revocableInvitation.token },
    });
    assert.equal(revokedInspect.status(), 200);
    assert.ok((await revokedInspect.json()).revoked_at, "revoked invitation had no revoked_at");
    const revokedAccept = await context.request.post(`${baseUrl}/v1/invitations/accept`, {
      data: {
        token: revocableInvitation.token,
        display_name: "Revoked member",
        password,
      },
    });
    assert.equal(revokedAccept.status(), 410);

    const revokedContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const revokedPage = await revokedContext.newPage();
    await revokedPage.goto(
      `${baseUrl}/workspace/#invite=${encodeURIComponent(revocableInvitation.token)}`,
      { waitUntil: "networkidle" },
    );
    await revokedPage.locator("#invite-accept-form").waitFor({ state: "visible" });
    assert.equal(
      await revokedPage.locator('#invite-accept-form button[type="submit"]').isDisabled(),
      true,
      "revoked invitation remained actionable",
    );
    await expectNoHorizontalOverflow(revokedPage, "revoked invitation 390px");
    await screenshot(revokedPage, "invitation-revoked-390px.png");
    await revokedContext.close();

    const invitationResponse = await context.request.post(`${baseUrl}/v1/invitations`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
      data: { email: invitedEmail, role: "creator", expires_in_hours: 24 },
    });
    assert.equal(invitationResponse.status(), 201);
    const invitation = await invitationResponse.json();
    assert.ok(invitation.token);

    const inviteContext = await browser.newContext({ viewport: { width: 1050, height: 800 } });
    const invitePage = await inviteContext.newPage();
    const invitePageErrors = [];
    invitePage.on("pageerror", (error) => invitePageErrors.push(error.message));
    await invitePage.addInitScript(() => {
      window.__heyuUnhandledRejections = [];
      window.addEventListener("unhandledrejection", (event) => {
        const reason = event.reason;
        window.__heyuUnhandledRejections.push(
          reason instanceof Error ? reason.message : String(reason),
        );
      });
    });
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
    const creatorToken = await invitePage.evaluate(() => localStorage.getItem("heyu_token"));
    assert.ok(creatorToken, "creator token missing after invitation acceptance");

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

    const membersResponse = await context.request.get(`${baseUrl}/v1/members`, {
      headers: { Authorization: `Bearer ${ownerToken}` },
    });
    assert.equal(membersResponse.status(), 200);
    const creatorMembership = (await membersResponse.json()).find(
      (member) => member.email === invitedEmail,
    );
    assert.ok(creatorMembership, "accepted creator was not returned in the member list");
    assert.equal(creatorMembership.role, "creator");

    const demotionResponse = await context.request.patch(
      `${baseUrl}/v1/members/${creatorMembership.membership_id}`,
      {
        headers: { Authorization: `Bearer ${ownerToken}` },
        data: { role: "viewer" },
      },
    );
    assert.equal(demotionResponse.status(), 200);
    assert.equal((await demotionResponse.json()).role, "viewer");

    const staleTokenStatus = await invitePage.evaluate(async () => {
      const token = localStorage.getItem("heyu_token");
      return (
        await fetch("/v1/me", {
          headers: { Authorization: `Bearer ${token}` },
        })
      ).status;
    });
    assert.equal(staleTokenStatus, 401, "creator token remained valid after viewer demotion");

    await invitePage.evaluate(() => localStorage.removeItem("heyu_token"));
    await invitePage.reload({ waitUntil: "networkidle" });
    await invitePage.locator("#auth-view").waitFor({ state: "visible" });
    await invitePage.locator('[data-auth-mode="login"]').click();
    const loginForm = invitePage.locator("#login-form");
    await loginForm.locator('[name="organization_slug"]').fill(organizationSlug);
    await loginForm.locator('[name="email"]').fill(invitedEmail);
    await loginForm.locator('[name="password"]').fill(password);
    await loginForm.locator('button[type="submit"]').click();
    await invitePage.locator("#workspace").waitFor({ state: "visible" });
    await openWorkspacePage(invitePage, "assets");
    await invitePage.locator("#asset-list", { hasText: businessName }).waitFor();

    const viewerToken = await invitePage.evaluate(() => localStorage.getItem("heyu_token"));
    assert.ok(viewerToken, "viewer token missing after signing in again");
    assert.notEqual(viewerToken, creatorToken, "viewer login unexpectedly reused the creator token");
    const viewerResponse = await inviteContext.request.get(`${baseUrl}/v1/me`, {
      headers: { Authorization: `Bearer ${viewerToken}` },
    });
    assert.equal(viewerResponse.status(), 200);
    assert.equal((await viewerResponse.json()).role, "viewer");

    await openWorkspacePage(invitePage, "plans");
    await invitePage
      .locator(
        `[data-open-marketing-plan="${copiedMarketingPlan.id}"], [data-open-marketing-plan="${savedMarketingPlan.id}"]`,
      )
      .first()
      .click();
    await invitePage.locator("#marketing-plan-detail").waitFor({ state: "visible" });
    await invitePage.locator("#marketing-plan-preview", { hasText: /tomato/i }).waitFor();
    await expectHiddenOrAbsent(
      invitePage,
      "#import-marketing-plan",
      "marketing plan import control",
    );
    await expectHiddenOrAbsent(
      invitePage,
      "#save-marketing-plan-version",
      "marketing plan version save control",
    );
    await expectHiddenOrAbsent(
      invitePage,
      "#copy-marketing-plan",
      "marketing plan copy control",
    );
    await expectHiddenOrAbsent(invitePage, ".plan-editor-wrap", "marketing plan editor");

    const viewerPlanResponse = await inviteContext.request.get(
      `${baseUrl}/v1/marketing-plans/${savedMarketingPlan.id}`,
      { headers: { Authorization: `Bearer ${viewerToken}` } },
    );
    assert.equal(viewerPlanResponse.status(), 200, "viewer could not read marketing plan");
    const viewerPlan = await viewerPlanResponse.json();
    const viewerVersionResponse = await inviteContext.request.post(
      `${baseUrl}/v1/marketing-plans/${savedMarketingPlan.id}/versions`,
      {
        headers: { Authorization: `Bearer ${viewerToken}` },
        data: {
          request_payload: viewerPlan.current_version.request_payload,
          content: viewerPlan.current_version.content,
          change_summary: "Viewer must not save",
        },
      },
    );
    assert.equal(viewerVersionResponse.status(), 403, "viewer created a marketing plan version");
    const viewerCopyResponse = await inviteContext.request.post(
      `${baseUrl}/v1/marketing-plans/${savedMarketingPlan.id}/copy`,
      {
        headers: { Authorization: `Bearer ${viewerToken}` },
        data: {},
      },
    );
    assert.equal(viewerCopyResponse.status(), 403, "viewer copied a marketing plan");

    const readOnlyNotices = {};
    for (const [locale, filename] of [
      ["zh-CN", "viewer-readonly-zh-CN.png"],
      ["zh-HK", "viewer-readonly-zh-HK.png"],
      ["en", "viewer-readonly-en.png"],
    ]) {
      await selectLocale(invitePage, locale);
      readOnlyNotices[locale] = await expectReadOnlyNotice(invitePage, locale);
      await screenshot(invitePage, filename);
    }
    assert.ok(
      new Set(Object.values(readOnlyNotices)).size > 1,
      "read-only notice did not change across the three locales",
    );

    await openWorkspacePage(invitePage, "assets");
    await expectHiddenOrAbsent(invitePage, "#brand-form", "brand write form");
    await expectHiddenOrAbsent(invitePage, "#product-form", "product write form");
    await invitePage.locator("#asset-list", { hasText: businessName }).waitFor();
    await invitePage.locator("#asset-list", { hasText: productName }).waitFor();

    await openWorkspacePage(invitePage, "knowledge");
    await expectHiddenOrAbsent(invitePage, "#knowledge-form", "knowledge write form");
    await invitePage.locator("#knowledge-list", { hasText: source.title }).waitFor();

    await openWorkspacePage(invitePage, "studio");
    await expectHiddenOrAbsent(invitePage, "#project-form", "content project write form");
    await expectHiddenOrAbsent(invitePage, "#generate-button", "AI generation control");
    await expectHiddenOrAbsent(invitePage, "#edit-version", "content version editor");
    await expectHiddenOrAbsent(invitePage, "#save-version-button", "content version save control");
    await invitePage.locator("#project-list", { hasText: project.title }).waitFor();
    await invitePage.locator("#project-select").selectOption(project.id);
    await invitePage.locator("#generation-history-list article").first().waitFor();

    await openWorkspacePage(invitePage, "operations");
    await expectHiddenOrAbsent(invitePage, "#publication-form", "publication write form");
    await invitePage.locator("#publication-list").waitFor({ state: "visible" });

    await openWorkspacePage(invitePage, "review");
    await invitePage.locator("#review-list").waitFor({ state: "visible" });
    await expectHiddenOrAbsent(
      invitePage,
      "[data-submit-version], [data-review-version]",
      "content review write control",
    );

    await openWorkspacePage(invitePage, "audit");
    await invitePage.locator("#audit-list article").first().waitFor();
    await expectHiddenOrAbsent(invitePage, ".member-nav", "member management navigation");

    await invitePage.setViewportSize({ width: 700, height: 900 });
    await invitePage.reload({ waitUntil: "networkidle" });
    await invitePage.locator("#workspace").waitFor({ state: "visible" });
    await expectNoHorizontalOverflow(invitePage, "workspace 700px");
    await screenshot(invitePage, "workspace-700px.png");

    await invitePage.setViewportSize({ width: 390, height: 844 });
    await invitePage.goto(
      `${baseUrl}/workspace/plans?plan=${encodeURIComponent(copiedMarketingPlan.id)}&lang=en`,
      { waitUntil: "networkidle" },
    );
    await invitePage.locator("#workspace").waitFor({ state: "visible" });
    await invitePage.locator('[data-page-panel="plans"]').waitFor({ state: "visible" });
    await invitePage.locator("#marketing-plan-detail").waitFor({ state: "visible" });
    await expectNoHorizontalOverflow(invitePage, "marketing plan workspace 390px");
    await screenshot(invitePage, "marketing-plan-viewer-390px.png");
    assert.deepEqual(
      await invitePage.evaluate(() => window.__heyuUnhandledRejections || []),
      [],
      "viewer workspace emitted an unhandled promise rejection",
    );
    assert.deepEqual(
      invitePageErrors,
      [],
      `viewer workspace page errors: ${invitePageErrors.join("\n")}`,
    );
    assert.equal(localizedPlanHeadings.size, 3, "marketing plan heading was not trilingual");
    await inviteContext.close();
    assert.deepEqual(pageErrors, [], `browser page errors: ${pageErrors.join("\n")}`);
    assert.deepEqual(
      await page.evaluate(() => window.__heyuUnhandledRejections || []),
      [],
      "browser unhandled promise rejections",
    );
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

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE_URL = process.env.HEYU_BASE_URL || "http://127.0.0.1:8765";
const outputDirectory = path.resolve(
  process.env.HEYU_VIDEO_OUTPUT || "outputs/promo-video-20260716",
);

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function centerOf(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("Element is not visible");
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

async function moveTo(page, locator) {
  const point = await centerOf(locator);
  await page.mouse.move(point.x, point.y, { steps: 16 });
  await wait(220);
}

async function click(page, locator, pause = 650) {
  await moveTo(page, locator);
  await locator.click();
  await wait(pause);
}

async function typeInto(page, selector, value, delay = 14) {
  const locator = page.locator(selector);
  await moveTo(page, locator);
  await locator.click();
  await locator.fill("");
  await locator.pressSequentially(value, { delay });
  await wait(320);
}

async function showLandingSection(page, selector, pause = 1700) {
  await page.locator(selector).evaluate((element) => {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  await wait(pause);
}

async function showResultTab(page, tab, scrollAmount = 0, pause = 1350) {
  await page.locator(`.result-tabs [data-tab="${tab}"]`).evaluate((element) => {
    element.click();
  });
  await page.evaluate(() => window.scrollTo({ left: 0, top: window.scrollY }));
  const content = page.locator("#result-content");
  await content.evaluate((element) => element.scrollTo({ top: 0, behavior: "auto" }));
  await wait(pause);
  if (scrollAmount > 0) {
    await content.evaluate(
      (element, amount) => element.scrollTo({ top: amount, behavior: "smooth" }),
      scrollAmount,
    );
    await wait(1150);
  }
  const scrollX = await page.evaluate(() => window.scrollX);
  if (scrollX !== 0) {
    await page.evaluate(() => window.scrollTo({ left: 0, top: window.scrollY }));
  }
}

async function main() {
  fs.mkdirSync(outputDirectory, { recursive: true });
  let browser;
  let context;

  try {
    browser = await chromium.launch({ headless: true });
    context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      recordVideo: {
        dir: outputDirectory,
        size: { width: 1440, height: 900 },
      },
      colorScheme: "light",
      locale: "zh-CN",
    });
    const page = await context.newPage();

    await page.addInitScript(() => {
      localStorage.setItem("heyu-locale", "zh-CN");
    });

    await page.goto(`${BASE_URL}/`, { waitUntil: "networkidle" });
    await page.addStyleTag({
      content: `
        html { scroll-behavior: smooth !important; }
        * { caret-color: #18a978 !important; }
        button:focus-visible, a:focus-visible, input:focus-visible,
        textarea:focus-visible, select:focus-visible {
          outline: 3px solid rgba(24, 169, 120, .40) !important;
          outline-offset: 3px !important;
        }
      `,
    });

    // 展示完整首页，而不是只停留在首屏。
    await wait(2200);
    await showLandingSection(page, ".proof-strip", 1500);
    await showLandingSection(page, "#capabilities", 2100);
    await showLandingSection(page, "#workflow", 2100);
    await showLandingSection(page, "#principles", 1900);
    await showLandingSection(page, "footer", 1300);
    await page.evaluate(() => window.scrollTo({ top: 0, left: 0, behavior: "smooth" }));
    await wait(1800);

    await click(page, page.locator(".hero-actions .primary-cta"), 900);
    await page.waitForURL(/\/create\/?(?:\?.*)?$/);
    await page.waitForLoadState("networkidle");
    await wait(1400);

    await page.locator('select[name="persona"]').selectOption("cooperative");
    await wait(350);
    await click(page, page.locator('input[name="goals"][value="build-brand"] + span'), 350);
    await click(page, page.locator('input[name="goals"][value="gain-followers"] + span'), 450);

    await typeInto(page, 'input[name="product_name"]', "盛夏高山黄金百香果");
    await typeInto(page, 'input[name="origin"]', "广东清远");
    await typeInto(
      page,
      'textarea[name="product_description"]',
      "果园里的黄金百香果自然成熟后分批采摘，金黄色果皮醒目，切开后果香明显、汁水充足，酸甜平衡。合作社当天采摘、统一分级，既可以直接挖着吃，也适合加入冰水、气泡水或酸奶，做成盛夏低负担饮品。",
      7,
    );
    await typeInto(
      page,
      'input[name="selling_points"]',
      "自然成熟，金黄果皮，果香浓郁，酸甜多汁，当天采摘，切果和冲饮画面鲜明",
      10,
    );
    await typeInto(
      page,
      'input[name="audience"]',
      "喜欢夏日水果、低负担饮品、家庭鲜食和果园产地内容的年轻消费者",
      10,
    );

    await click(page, page.locator('input[name="platform"][value="douyin"] + span'), 350);
    await page.locator('select[name="tone"]').selectOption("lively");
    await wait(350);
    await typeInto(
      page,
      'input[name="trend"]',
      "抖音盛夏开箱：切开黄金百香果看酸甜爆汁，再冲一杯年轻人喜欢的气泡饮",
      9,
    );

    await click(page, page.locator(".generate-button"), 450);
    await page.locator("#result-state").waitFor({ state: "visible", timeout: 20_000 });
    await wait(2100);

    // 固定工作台视口，只切换内容，避免标签居中造成画面向右迁移。
    await page.locator("#result-panel").evaluate((element) => {
      element.scrollIntoView({ behavior: "smooth", block: "start", inline: "nearest" });
    });
    await page.evaluate(() => window.scrollTo({ left: 0, top: window.scrollY }));
    await wait(1200);

    await showResultTab(page, "strategy", 260, 1200);
    await showResultTab(page, "topics", 280, 1300);
    await showResultTab(page, "routes", 600, 1550);
    await showResultTab(page, "prep", 560, 1450);
    await showResultTab(page, "live", 500, 1400);
    await showResultTab(page, "calendar", 680, 1700);

    await page.locator("#result-content").evaluate((element) =>
      element.scrollTo({ top: 0, behavior: "smooth" }),
    );
    await page.evaluate(() => window.scrollTo({ left: 0, top: window.scrollY }));
    await wait(1400);

    const video = page.video();
    await context.close();
    context = null;
    await browser.close();
    browser = null;

    const rawPath = await video.path();
    const finalPath = path.join(outputDirectory, "heyu-ai-promo-raw.webm");
    if (path.resolve(rawPath) !== path.resolve(finalPath)) {
      if (fs.existsSync(finalPath)) fs.rmSync(finalPath);
      fs.renameSync(rawPath, finalPath);
    }
    console.log(finalPath);
  } finally {
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

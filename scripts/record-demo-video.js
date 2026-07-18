const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE_URL = process.env.HEYU_BASE_URL || "http://127.0.0.1:8765";
const outputDirectory = path.resolve(
  process.env.HEYU_VIDEO_OUTPUT || "outputs/demo-video-20260716",
);

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function centerOf(locator) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error(`Element is not visible: ${locator}`);
  return {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
}

async function moveTo(page, locator) {
  const point = await centerOf(locator);
  await page.mouse.move(point.x, point.y, { steps: 18 });
  await wait(280);
}

async function click(page, locator, pause = 700) {
  await moveTo(page, locator);
  await locator.click();
  await wait(pause);
}

async function typeInto(page, selector, value) {
  const locator = page.locator(selector);
  await moveTo(page, locator);
  await locator.click();
  await locator.fill("");
  await locator.pressSequentially(value, { delay: 24 });
  await wait(420);
}

async function scrollPage(page, y, duration = 900) {
  await page.evaluate(
    ({ top, behavior }) => window.scrollTo({ top, behavior }),
    { top: y, behavior: "smooth" },
  );
  await wait(duration);
}

async function showResultTab(page, tab, scrollAmount = 0, pause = 1450) {
  const locator = page.locator(`.result-tabs [data-tab="${tab}"]`);
  await click(page, locator, 650);
  const content = page.locator("#result-content");
  await content.evaluate((element) => element.scrollTo({ top: 0, behavior: "smooth" }));
  await wait(pause);
  if (scrollAmount > 0) {
    await content.hover();
    await page.mouse.wheel(0, scrollAmount);
    await wait(1200);
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
      * { caret-color: #18a978 !important; }
      button:focus-visible, a:focus-visible, input:focus-visible,
      textarea:focus-visible, select:focus-visible {
        outline: 3px solid rgba(24, 169, 120, .42) !important;
        outline-offset: 3px !important;
      }
    `,
  });
  await wait(2600);

  await scrollPage(page, 150, 950);
  await wait(900);
  await click(page, page.locator(".hero-actions .primary-cta"), 1100);
  await page.waitForURL(/\/create\/?(?:\?.*)?$/);
  await page.waitForLoadState("networkidle");
  await wait(1800);

  await page.locator('select[name="persona"]').selectOption("cooperative");
  await wait(500);
  await click(page, page.locator('input[name="goals"][value="build-brand"] + span'), 500);

  await typeInto(page, 'input[name="product_name"]', "当季树熟番茄");
  await typeInto(page, 'input[name="origin"]', "广东清远");
  await typeInto(
    page,
    'textarea[name="product_description"]',
    "每天清晨采摘自然成熟的番茄，果肉饱满、酸甜多汁。合作社统一分级，当天采摘后及时发出，适合家庭鲜食、沙拉和轻食搭配。",
  );
  await typeInto(
    page,
    'input[name="selling_points"]',
    "自然成熟，酸甜多汁，清晨采摘，合作社统一分级",
  );
  await typeInto(
    page,
    'input[name="audience"]',
    "关注新鲜食材、家庭饮食和轻食搭配的城市消费者",
  );

  await click(page, page.locator('input[name="platform"][value="douyin"] + span'), 450);
  await page.locator('select[name="tone"]').selectOption("lively");
  await wait(450);
  await typeInto(page, 'input[name="trend"]', "夏日轻食、产地直采、当季新鲜");

  const generateButton = page.locator(".generate-button");
  await click(page, generateButton, 500);
  await page.locator("#result-state").waitFor({ state: "visible", timeout: 20_000 });
  await wait(2300);

  await showResultTab(page, "strategy", 300, 1300);
  await showResultTab(page, "topics", 320, 1400);
  await showResultTab(page, "routes", 680, 1700);
  await showResultTab(page, "prep", 650, 1600);
  await showResultTab(page, "live", 580, 1500);
  await showResultTab(page, "calendar", 720, 1900);

  await page.locator("#result-content").evaluate((element) =>
    element.scrollTo({ top: 0, behavior: "smooth" }),
  );
  await wait(1700);

  const video = page.video();
  await context.close();
  context = null;
  await browser.close();
  browser = null;
  const rawPath = await video.path();
  const finalPath = path.join(outputDirectory, "heyu-ai-demo-raw.webm");
  if (path.resolve(rawPath) !== path.resolve(finalPath)) {
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

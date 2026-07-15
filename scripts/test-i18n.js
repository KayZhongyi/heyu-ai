const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const root = path.resolve(__dirname, "..");
const context = { globalThis: {} };
context.globalThis = context;
vm.createContext(context);

for (const locale of ["zh-CN", "zh-HK", "en"]) {
  const file = path.join(root, "apps", "web", "assets", "locales", `${locale}.js`);
  const source = fs.readFileSync(file, "utf8");
  assert.equal(source.includes("\ufffd"), false, `${locale} contains replacement characters`);
  assert.equal(source.includes("????"), false, `${locale} contains damaged placeholder text`);
  vm.runInContext(source, context, { filename: file });
}

const locales = context.HeyuLocales;
assert.deepEqual(Object.keys(locales).sort(), ["en", "zh-CN", "zh-HK"]);

const requiredMessages = [
  "meta.landing.title",
  "meta.workspace.title",
  "content_renderer.draft",
  "content_renderer.citations",
  "farmerEvidence.heading",
  "farmerEvidence.claim.general_support",
  "farmerEvidence.consent.relationship",
  "farmerEvidence.ready",
  "contentFreshness.farmer_evidence_replaced_or_expired",
  "publication.noPublishableVersion",
];
for (const locale of Object.keys(locales)) {
  for (const key of requiredMessages) {
    assert.ok(locales[locale].messages[key], `${locale} is missing ${key}`);
  }
}

for (const locale of ["zh-HK", "en"]) {
  assert.ok(Object.keys(locales[locale].phrases).length >= 265, `${locale} page phrase coverage is incomplete`);
  for (const phrase of [
    "让土地里的认真，",
    "进入工作台",
    "工作空间",
    "经营概览",
    "品牌与农产品",
    "内容资料库",
    "内容创作台",
    "团队与权限",
  ]) {
    assert.ok(locales[locale].phrases[phrase], `${locale} is missing phrase: ${phrase}`);
  }
}

const workspace = fs.readFileSync(path.join(root, "apps", "web", "workspace.html"), "utf8");
for (const id of [
  "asset-list",
  "project-list",
  "knowledge-list",
  "audit-list",
  "publication-list",
  "member-list",
  "generation-preview",
  "generation-output",
  "generation-history-list",
  "farmer-evidence-history",
]) {
  assert.match(
    workspace,
    new RegExp(`id="${id}"[^>]*data-business-data|data-business-data[^>]*id="${id}"`),
    `${id} must be excluded from automatic phrase translation`,
  );
}

const appSource = fs.readFileSync(path.join(root, "apps", "web", "assets", "app.js"), "utf8");
assert.equal(appSource.includes("location.search).get(\"invite\")"), false, "invite token must not use query parameters");
assert.equal(appSource.includes("/workspace/?invite="), false, "invite links must not use query parameters");
assert.ok(appSource.includes("/workspace/#invite="), "invite links must use a URL fragment");
assert.ok(appSource.includes("/v1/invitations/inspect"), "invitation inspection must use the POST endpoint");
assert.ok(
  appSource.includes("/farmer-evidence-snapshots"),
  "workspace must expose the farmer evidence workflow",
);
assert.ok(
  appSource.includes('name="allowed_claims"'),
  "farmer evidence claims must use explicit multi-select controls",
);

console.log("i18n dictionaries: PASS");

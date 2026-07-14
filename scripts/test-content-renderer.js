const assert = require("node:assert/strict");
const { renderContent, safeFilename } = require("../apps/web/assets/content-renderer.js");

const fixtures = [
  {
    format: "short_video_script",
    title_options: ["产地故事"],
    hook: "先看产地。",
    script: "这是一段完整口播。",
    shots: [{ seconds: "0-3", visual: "产品特写", voiceover: "先看产地。" }],
    cta: "欢迎留言。",
  },
  {
    format: "livestream_product_pitch",
    run_of_show: [{ stage: "产品亮相", script: "今天介绍番茄。" }],
    host_notes: ["不得扩展功效。"],
  },
  { format: "comment_reply", reply_options: ["谢谢关注。"] },
  {
    format: "social_post",
    headline: "认真介绍一份番茄",
    body: "正文。",
    cta: "欢迎留言。",
    hashtags: ["#番茄"],
  },
  {
    format: "title_and_cover",
    title_options: ["从产地认识番茄"],
    cover_copy_options: ["先看事实"],
  },
  {
    format: "mobile_shooting_checklist",
    shooting_goal: "用手机竖屏拍清产品事实。",
    before_shooting: [
      { task: "清洁镜头并核对产品", required: true, reason: "保证画面清晰且信息准确" },
    ],
    shots: [
      {
        sequence: 1,
        duration_seconds: 5,
        shot_size: "近景",
        orientation: "vertical",
        subject: "产品与包装",
        action: "稳定拍摄",
        voiceover_or_text: "展示已审核产品名称",
        evidence_required: "已审核产品资料",
        capture_notes: "预留字幕安全区",
      },
    ],
    continuity_checks: ["保持产品和光线位置一致"],
    do_not_capture_or_claim: ["不得虚构认证或功效"],
  },
];

for (const fixture of fixtures) {
  fixture.risk_notes = ["禁止使用：治疗疾病"];
  fixture.citations = [{ source_id: "source-1", label: "产品档案" }];
  const rendered = renderContent(fixture);
  assert.match(rendered, /禾语 AI 内容稿/);
  assert.match(rendered, /风险提示/);
  assert.match(rendered, /产品档案/);
  assert.doesNotMatch(rendered, /\[object Object\]/);
  assert.doesNotMatch(rendered, /^\s*\{/);
}

assert.equal(safeFilename(' 番茄 / "首发" '), "番茄-首发");
assert.equal(safeFilename(""), "heyu-content");
console.log("Content renderer self-test passed.");

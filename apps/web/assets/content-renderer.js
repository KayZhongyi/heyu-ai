(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HeyuContent = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const text = value => String(value ?? "").trim();
  const section = (title, lines) => {
    const values = lines.map(text).filter(Boolean);
    return values.length ? [`【${title}】`, ...values, ""] : [];
  };
  const numbered = values => (values || []).map((value, index) => `${index + 1}. ${text(value)}`);
  const citations = content => (content.citations || []).map(
    item => `${text(item.label) || "未命名来源"}${item.source_id ? `（${item.source_id}）` : ""}`,
  );

  function renderContent(content) {
    if (!content || typeof content !== "object") return "";
    const lines = [];
    const format = content.format || "structured_content";
    lines.push(`禾语 AI 内容稿 · ${format}`, "");

    if (format === "short_video_script") {
      lines.push(...section("标题备选", numbered(content.title_options)));
      lines.push(...section("开场钩子", [content.hook]));
      lines.push(...section("完整口播", [content.script]));
      lines.push(...section("分镜脚本", (content.shots || []).map(
        shot => `${text(shot.seconds)}｜画面：${text(shot.visual)}｜口播：${text(shot.voiceover)}`,
      )));
      lines.push(...section("行动引导", [content.cta]));
    } else if (format.startsWith("livestream_")) {
      lines.push(...section("直播流程", (content.run_of_show || []).map(
        item => `${text(item.stage)}｜${text(item.script)}`,
      )));
      lines.push(...section("主播提示", numbered(content.host_notes)));
    } else if (format === "comment_reply") {
      lines.push(...section("回复备选", numbered(content.reply_options)));
    } else if (format === "title_and_cover") {
      lines.push(...section("标题备选", numbered(content.title_options)));
      lines.push(...section("封面文案备选", numbered(content.cover_copy_options)));
    } else if (format === "social_post") {
      lines.push(...section("标题", [content.headline]));
      lines.push(...section("正文", [content.body]));
      lines.push(...section("行动引导", [content.cta]));
      lines.push(...section("话题标签", [(content.hashtags || []).join(" ")]));
    } else {
      lines.push(...section("结构化内容", [JSON.stringify(content, null, 2)]));
    }

    lines.push(...section("风险提示", numbered(content.risk_notes)));
    lines.push(...section("引用来源", numbered(citations(content))));
    return lines.join("\n").trim() + "\n";
  }

  function safeFilename(value) {
    return (text(value) || "heyu-content")
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^[.-]+|[.-]+$/g, "")
      .slice(0, 80) || "heyu-content";
  }

  return { renderContent, safeFilename };
});

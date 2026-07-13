(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.HeyuContent = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const text = value => String(value ?? "").trim();
  const defaultLabels = {
    draft: "禾语 AI 内容稿", unnamedSource: "未命名来源", titleOptions: "标题备选",
    hook: "开场钩子", script: "完整口播", shots: "分镜脚本", cta: "行动引导",
    livestream: "直播流程", hostNotes: "主播提示", replyOptions: "回复备选",
    coverOptions: "封面文案备选", headline: "标题", body: "正文", hashtags: "话题标签",
    structured: "结构化内容", risks: "风险提示", citations: "引用来源",
  };
  const label = (options, key) => options?.t ? options.t(`content_renderer.${key}`) : defaultLabels[key];
  const section = (title, lines) => {
    const values = lines.map(text).filter(Boolean);
    return values.length ? [`【${title}】`, ...values, ""] : [];
  };
  const numbered = values => (values || []).map((value, index) => `${index + 1}. ${text(value)}`);
  const citations = (content, options) => (content.citations || []).map(
    item => `${text(item.label) || label(options, "unnamedSource")}${item.source_id ? `（${item.source_id}）` : ""}`,
  );

  function renderContent(content, options = {}) {
    if (!content || typeof content !== "object") return "";
    const lines = [];
    const format = content.format || "structured_content";
    lines.push(`${label(options, "draft")} · ${format}`, "");
    if (format === "short_video_script") {
      lines.push(...section(label(options, "titleOptions"), numbered(content.title_options)));
      lines.push(...section(label(options, "hook"), [content.hook]));
      lines.push(...section(label(options, "script"), [content.script]));
      lines.push(...section(label(options, "shots"), (content.shots || []).map(
        shot => `${text(shot.seconds)}｜${text(shot.visual)}｜${text(shot.voiceover)}`,
      )));
      lines.push(...section(label(options, "cta"), [content.cta]));
    } else if (format.startsWith("livestream_")) {
      lines.push(...section(label(options, "livestream"), (content.run_of_show || []).map(
        item => `${text(item.stage)}｜${text(item.script)}`,
      )));
      lines.push(...section(label(options, "hostNotes"), numbered(content.host_notes)));
    } else if (format === "comment_reply") {
      lines.push(...section(label(options, "replyOptions"), numbered(content.reply_options)));
    } else if (format === "title_and_cover") {
      lines.push(...section(label(options, "titleOptions"), numbered(content.title_options)));
      lines.push(...section(label(options, "coverOptions"), numbered(content.cover_copy_options)));
    } else if (format === "social_post") {
      lines.push(...section(label(options, "headline"), [content.headline]));
      lines.push(...section(label(options, "body"), [content.body]));
      lines.push(...section(label(options, "cta"), [content.cta]));
      lines.push(...section(label(options, "hashtags"), [(content.hashtags || []).join(" ")]));
    } else {
      lines.push(...section(label(options, "structured"), [JSON.stringify(content, null, 2)]));
    }
    lines.push(...section(label(options, "risks"), numbered(content.risk_notes)));
    lines.push(...section(label(options, "citations"), numbered(citations(content, options))));
    return lines.join("\n").trim() + "\n";
  }

  function safeFilename(value) {
    return (text(value) || "heyu-content")
      .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
      .replace(/\s+/g, "-").replace(/-+/g, "-").replace(/^[.-]+|[.-]+$/g, "")
      .slice(0, 80) || "heyu-content";
  }
  return { renderContent, safeFilename };
});

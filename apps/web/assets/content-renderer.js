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
    shootingGoal: "拍摄目标", beforeShooting: "开拍前准备", shotTasks: "镜头任务",
    continuityChecks: "连贯性检查", prohibitedCapture: "禁止拍摄或声称",
    required: "必做", optional: "建议", evidenceRequired: "事实依据",
    captureNotes: "拍摄提示", structured: "结构化内容", risks: "风险提示",
    citations: "引用来源", positioning: "产品定位", platformStrategy: "平台策略",
    trendPlan: "热点融入", videoScripts: "短视频脚本", livestreamPlan: "直播话术",
    sevenDayPlan: "七天运营计划", nextActions: "下一步行动",
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
    const isMarketingPlan = content.product_profile && content.strategy
      && Array.isArray(content.videos) && Array.isArray(content.seven_day_plan);
    if (isMarketingPlan) {
      lines.push(`${label(options, "draft")} · marketing_plan`, "");
      lines.push(...section(label(options, "positioning"), [
        content.product_profile.one_line_value,
        content.product_profile.story_angle,
        ...numbered(content.product_profile.core_selling_points),
      ]));
      lines.push(...section(label(options, "platformStrategy"), [
        content.strategy.platform_name,
        content.strategy.content_focus,
        content.strategy.recommended_duration,
        content.strategy.conversion_action,
      ]));
      lines.push(...section(label(options, "trendPlan"), [
        content.trend?.trend_used,
        content.trend?.integration_method,
        content.trend?.caution,
      ]));
      lines.push(...section(label(options, "videoScripts"), content.videos.flatMap((video, index) => [
        `${index + 1}. ${text(video.title)}｜${text(video.angle)}`,
        `${text(video.hook)}\n${text(video.script)}\n${text(video.call_to_action)}`,
      ])));
      lines.push(...section(label(options, "livestreamPlan"), (content.livestream || []).map(
        item => `${text(item.section)}｜${(item.talking_points || []).map(text).join("；")}`,
      )));
      lines.push(...section(label(options, "sevenDayPlan"), content.seven_day_plan.map(
        item => `Day ${item.day}｜${text(item.objective)}｜${text(item.content)}｜${text(item.action)}`,
      )));
      lines.push(...section(label(options, "nextActions"), numbered(content.next_actions)));
      return lines.join("\n").trim() + "\n";
    }
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
    } else if (format === "mobile_shooting_checklist") {
      lines.push(...section(label(options, "shootingGoal"), [content.shooting_goal]));
      lines.push(...section(label(options, "beforeShooting"), (content.before_shooting || []).map(
        item => `${item.required ? label(options, "required") : label(options, "optional")}｜${text(item.task)}｜${text(item.reason)}`,
      )));
      lines.push(...section(label(options, "shotTasks"), (content.shots || []).map(
        shot => [
          `${text(shot.sequence)}｜${text(shot.duration_seconds)}s｜${text(shot.shot_size)}｜${text(shot.subject)}`,
          `${text(shot.action)}｜${text(shot.voiceover_or_text)}`,
          `${label(options, "evidenceRequired")}：${text(shot.evidence_required)}`,
          `${label(options, "captureNotes")}：${text(shot.capture_notes)}`,
        ].join("\n"),
      )));
      lines.push(...section(label(options, "continuityChecks"), numbered(content.continuity_checks)));
      lines.push(...section(label(options, "prohibitedCapture"), numbered(content.do_not_capture_or_claim)));
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

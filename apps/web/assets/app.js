const inviteFragment=new URLSearchParams(location.hash.replace(/^#/,"")).get("invite")||"";
if(inviteFragment)history.replaceState(null,"","/workspace/");
const state={token:localStorage.getItem("heyu_token")||"",actor:null,members:[],invitations:[],brands:[],products:[],knowledge:[],campaigns:[],campaignBriefRevisions:[],campaignBriefMaps:{},campaignSupplySnapshots:[],campaignFarmerEvidenceSnapshots:[],marketingPlans:[],currentMarketingPlan:null,selectedMarketingVersion:null,projects:[],versions:[],generationRuns:[],publications:[],performanceReviews:{},operationImportFile:null,operationImportPreview:null,audit:[],currentVersion:null,inviteToken:inviteFragment};
const t=(key,variables={})=>HeyuI18n.t(key,variables);
const operationMessages={
  "zh-CN":{
    "import.heading":"批量回传运营数据","import.format":"CSV / XLSX","import.intro":"上传平台导出的数据文件，先检查字段匹配、发布记录匹配与逐行错误，再确认写入数据快照。","import.chooseFile":"选择运营数据文件","import.fileHint":"支持 UTF-8 CSV 与 XLSX，最大 20 MB","import.mappingSummary":"高级：自定义字段映射","import.mappingLabel":"字段映射 JSON（可留空自动识别）","import.mappingPlaceholder":"例如：{\"渠道\":\"platform\",\"帖子编号\":\"external_content_id\",\"曝光\":\"views\"}","import.preview":"预览匹配结果","import.previewing":"正在预览…","import.confirm":"确认导入有效匹配行","import.importing":"正在导入…","import.selected":"已选择：{name}","import.summary":"共 {total} 行 · {valid} 行格式有效 · {matched} 行匹配发布 · {invalid} 行有误","import.sheet":"工作表：{name}","import.mapping":"识别字段","import.warnings":"文件提示","import.row":"行","import.publicationMatch":"发布匹配","import.data":"规范化数据","import.errors":"错误","import.matched":"已匹配","import.unmatched":"未匹配","import.duplicate":"重复数据","import.valid":"可导入","import.noErrors":"无","import.moreRows":"仅显示前 {count} 行，请根据汇总确认完整文件。","import.noMatchedRows":"没有可导入的有效匹配行。请检查平台与平台内容 ID / 外部链接。","import.invalidMapping":"字段映射必须是有效的 JSON 对象。","import.completed":"导入完成：写入 {imported} 行，跳过 {duplicates} 行重复数据。","import.previewRequired":"请先预览当前文件。",
    "loop.heading":"发布、复盘与改进","loop.history":"保留历史","loop.intro":"每次数据录入都会形成独立快照。可基于最新快照生成规则复盘，把建议保存为改进简报，再创建关联的下一轮草稿。",
    "review.generate":"生成运营复盘","review.generating":"正在生成复盘…","review.heading":"运营数据复盘","review.method":"方法：{method}","review.signals":"数据信号","review.recommendations":"改进建议","review.limitations":"使用边界","review.noSignals":"当前数据不足以计算比率信号。","review.saveBrief":"保存为改进简报","review.savingBrief":"正在保存建议…","review.savedBrief":"复盘建议已保存为改进简报。","review.needSnapshot":"请先导入或录入至少一条数据快照。","review.generated":"运营复盘已生成。","review.diagnosisTitle":"运营数据复盘建议","review.briefTitle":"下一轮运营改进简报","review.briefObjective":"依据最新运营数据，只调整少量内容变量并保留可追溯版本。",
    "brief.heading":"改进简报","brief.oneClickDraft":"一键创建下一轮草稿","brief.creatingDraft":"正在创建草稿…","brief.draftCreated":"下一轮草稿已创建，可前往“审核与版本”继续编辑和提交。","brief.changeSummary":"依据“{title}”创建下一轮改进草稿","brief.custom":"高级：手工调整草稿 JSON",
  },
  "zh-HK":{
    "import.heading":"批量回傳營運數據","import.format":"CSV / XLSX","import.intro":"上載平台匯出的數據檔案，先檢查欄位配對、發佈記錄配對及逐行錯誤，再確認寫入數據快照。","import.chooseFile":"選擇營運數據檔案","import.fileHint":"支援 UTF-8 CSV 及 XLSX，最大 20 MB","import.mappingSummary":"進階：自訂欄位配對","import.mappingLabel":"欄位配對 JSON（可留空自動識別）","import.mappingPlaceholder":"例如：{\"渠道\":\"platform\",\"帖子編號\":\"external_content_id\",\"曝光\":\"views\"}","import.preview":"預覽配對結果","import.previewing":"正在預覽…","import.confirm":"確認匯入有效配對列","import.importing":"正在匯入…","import.selected":"已選擇：{name}","import.summary":"共 {total} 列 · {valid} 列格式有效 · {matched} 列配對發佈 · {invalid} 列有誤","import.sheet":"工作表：{name}","import.mapping":"識別欄位","import.warnings":"檔案提示","import.row":"列","import.publicationMatch":"發佈配對","import.data":"標準化數據","import.errors":"錯誤","import.matched":"已配對","import.unmatched":"未配對","import.duplicate":"重複數據","import.valid":"可匯入","import.noErrors":"無","import.moreRows":"只顯示首 {count} 列，請按彙總確認完整檔案。","import.noMatchedRows":"沒有可匯入的有效配對列。請檢查平台與平台內容 ID / 外部連結。","import.invalidMapping":"欄位配對必須是有效的 JSON 物件。","import.completed":"匯入完成：寫入 {imported} 列，略過 {duplicates} 列重複數據。","import.previewRequired":"請先預覽目前檔案。",
    "loop.heading":"發佈、復盤與改進","loop.history":"保留歷史","loop.intro":"每次數據輸入都會形成獨立快照。可按最新快照產生規則復盤，把建議儲存為改進簡報，再建立關聯的下一輪草稿。",
    "review.generate":"產生營運復盤","review.generating":"正在產生復盤…","review.heading":"營運數據復盤","review.method":"方法：{method}","review.signals":"數據訊號","review.recommendations":"改進建議","review.limitations":"使用界線","review.noSignals":"目前數據不足以計算比率訊號。","review.saveBrief":"儲存為改進簡報","review.savingBrief":"正在儲存建議…","review.savedBrief":"復盤建議已儲存為改進簡報。","review.needSnapshot":"請先匯入或輸入至少一條數據快照。","review.generated":"營運復盤已產生。","review.diagnosisTitle":"營運數據復盤建議","review.briefTitle":"下一輪營運改進簡報","review.briefObjective":"依據最新營運數據，只調整少量內容變數並保留可追溯版本。",
    "brief.heading":"改進簡報","brief.oneClickDraft":"一鍵建立下一輪草稿","brief.creatingDraft":"正在建立草稿…","brief.draftCreated":"下一輪草稿已建立，可前往「審核與版本」繼續編輯及提交。","brief.changeSummary":"依據「{title}」建立下一輪改進草稿","brief.custom":"進階：手動調整草稿 JSON",
  },
  "en":{
    "import.heading":"Import operation data","import.format":"CSV / XLSX","import.intro":"Upload a platform export, review field mapping, publication matches, and row errors, then confirm the performance snapshots to write.","import.chooseFile":"Choose operation data file","import.fileHint":"UTF-8 CSV and XLSX, up to 20 MB","import.mappingSummary":"Advanced: custom field mapping","import.mappingLabel":"Field mapping JSON (leave blank for automatic detection)","import.mappingPlaceholder":"Example: {\"Channel\":\"platform\",\"Post ID\":\"external_content_id\",\"Impressions\":\"views\"}","import.preview":"Preview matches","import.previewing":"Previewing…","import.confirm":"Import valid matched rows","import.importing":"Importing…","import.selected":"Selected: {name}","import.summary":"{total} rows · {valid} structurally valid · {matched} matched to publications · {invalid} with errors","import.sheet":"Worksheet: {name}","import.mapping":"Detected fields","import.warnings":"File notices","import.row":"Row","import.publicationMatch":"Publication match","import.data":"Normalized data","import.errors":"Errors","import.matched":"Matched","import.unmatched":"Unmatched","import.duplicate":"Duplicate","import.valid":"Ready","import.noErrors":"None","import.moreRows":"Showing the first {count} rows. Use the summary to confirm the complete file.","import.noMatchedRows":"There are no valid matched rows to import. Check the platform and platform content ID / external URL.","import.invalidMapping":"Field mapping must be a valid JSON object.","import.completed":"Import complete: {imported} rows written and {duplicates} duplicates skipped.","import.previewRequired":"Preview the current file first.",
    "loop.heading":"Publish, review, and improve","loop.history":"History retained","loop.intro":"Every data entry creates a separate snapshot. Generate a rule-based review from the latest snapshot, save its recommendations as an improvement brief, and create a linked follow-up draft.",
    "review.generate":"Generate performance review","review.generating":"Generating review…","review.heading":"Performance review","review.method":"Method: {method}","review.signals":"Data signals","review.recommendations":"Recommendations","review.limitations":"Limitations","review.noSignals":"The current data is insufficient for ratio signals.","review.saveBrief":"Save as improvement brief","review.savingBrief":"Saving recommendations…","review.savedBrief":"The review recommendations were saved as an improvement brief.","review.needSnapshot":"Import or enter at least one performance snapshot first.","review.generated":"Performance review generated.","review.diagnosisTitle":"Operation performance review recommendations","review.briefTitle":"Next-round operation improvement brief","review.briefObjective":"Use the latest operation data to change only a small number of content variables while retaining traceable versions.",
    "brief.heading":"Improvement briefs","brief.oneClickDraft":"Create next-round draft","brief.creatingDraft":"Creating draft…","brief.draftCreated":"The next-round draft was created. Continue editing and submit it from Review & versions.","brief.changeSummary":"Created a next-round improvement draft from “{title}”","brief.custom":"Advanced: edit draft JSON manually",
  },
};
const operationText=(key,variables={})=>{
  const locale=operationMessages[HeyuI18n.getLocale()]?HeyuI18n.getLocale():"zh-CN";
  let value=operationMessages[locale][key]||operationMessages["zh-CN"][key]||key;
  return value.replace(/\{(\w+)\}/g,(_,name)=>variables[name]??`{${name}}`);
};
const roleLabel=role=>t(`role.${role}`)===`role.${role}`?role:t(`role.${role}`);
const enumLabel=(prefix,value)=>{const key=`${prefix}.${value}`;const label=t(key);return label===key?value:label};
const contentTypeLabel=value=>enumLabel("contentType",value);
const contentStatusLabel=value=>enumLabel("contentStatus",value);
const generationStatusLabel=value=>enumLabel("generationStatus",value);
const severityLabel=value=>enumLabel("severity",value);
const fieldSeparator=()=>t("punctuation.fieldSeparator");
const roleOptions=(selected="",allowOwner=true)=>["owner","admin","product_manager","creator","reviewer","viewer"].filter(role=>allowOwner||role!=="owner").map(role=>`<option value="${role}"${role===selected?" selected":""}>${roleLabel(role)}</option>`).join("");
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
let sessionInvalidated=false;
const invalidateSession=()=>{
  if(sessionInvalidated)return;
  sessionInvalidated=true;
  localStorage.removeItem("heyu_token");
  state.token="";
  state.actor=null;
  $("#auth-view").hidden=false;
  $("#workspace").hidden=true;
  $("#logout").hidden=true;
  const loginTab=$('[data-auth-mode="login"]');
  $$('[data-auth-mode]').forEach(item=>item.classList.toggle("active",item===loginTab));
  $$('[data-auth-panel]').forEach(panel=>panel.hidden=panel.dataset.authPanel!=="login");
  toast(t("auth.sessionExpired"),true);
};
const apiErrorMessage=(detail,fallback)=>{
  if(typeof detail==="string")return detail;
  if(!detail||typeof detail!=="object")return fallback;
  if(typeof detail.message==="string"&&detail.message)return detail.message;
  const code=detail.code?briefBlockerLabel(String(detail.code).toLowerCase()):"";
  const blockers=Array.isArray(detail.blockers)?detail.blockers.map(briefBlockerLabel):[];
  return [code,...blockers].filter(Boolean).join(fieldSeparator())||fallback;
};
const requestHeaders=options=>{const headers={...(options.headers||{})};if(!(options.body instanceof FormData))headers["Content-Type"]="application/json";if(state.token)headers.Authorization=`Bearer ${state.token}`;return headers};
const api=async(path,options={})=>{const response=await fetch(path,{...options,headers:requestHeaders(options)});if(!response.ok){let message=response.status===429?t("error.tooManyRequests"):t("error.requestFailed",{status:response.status});try{const body=await response.json();if(response.status!==429)message=apiErrorMessage(body.detail,message)}catch{}if(response.status===401&&state.token){invalidateSession();message=t("auth.sessionExpired")}throw new Error(message)}return response.status===204?null:response.json()};
const apiFile=async(path,options={})=>{const response=await fetch(path,{...options,headers:requestHeaders(options)});if(!response.ok){let message=t("error.requestFailed",{status:response.status});try{const body=await response.json();message=apiErrorMessage(body.detail,message)}catch{}if(response.status===401&&state.token)invalidateSession();throw new Error(message)}return response};
const formData=form=>Object.fromEntries(new FormData(form));
const lines=value=>value.split("\n").map(v=>v.trim()).filter(Boolean);
const toast=(message,error=false)=>{const el=$("#toast");el.textContent=message;el.className=`show${error?" error":""}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className="",3000)};
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fileBaseName=name=>name.replace(/\.(txt|md|markdown|csv|pdf|pptx)$/i,"");
const knowledgeMediaType=file=>file.type||({txt:"text/plain",md:"text/markdown",markdown:"text/markdown",csv:"text/csv",pdf:"application/pdf",pptx:"application/vnd.openxmlformats-officedocument.presentationml.presentation"}[file.name.split(".").pop().toLowerCase()]||"text/plain");
const request=async(fn,success)=>{try{await fn();if(success)toast(success)}catch(error){toast(error.message,true)}};
const resultContent=()=>state.currentVersion?.content||null;
const resultText=()=>HeyuContent.renderContent(resultContent(),{t:HeyuI18n.t,locale:HeyuI18n.getLocale()});
const renderGenerationResult=content=>{
  $("#generation-preview").textContent=HeyuContent.renderContent(content,{t:HeyuI18n.t,locale:HeyuI18n.getLocale()});
  $("#generation-output").textContent=JSON.stringify(content,null,2);
  $("#content-toolbar").hidden=false;
  $$("[data-result-mode]").forEach(button=>button.classList.toggle("active",button.dataset.resultMode==="preview"));
  $("#generation-preview").hidden=false;
  $("#generation-output").hidden=true;
};
const resetGenerationWorkspace=()=>{
  state.currentVersion=null;
  $("#version-editor").value="";
  $("#change-summary").value="";
  $("#edit-version").hidden=true;
  $("#generation-preview").textContent="";
  $("#generation-preview").hidden=false;
  $("#generation-output").textContent="";
  $("#generation-output").hidden=true;
  $("#content-toolbar").hidden=true;
  $("#generation-provenance")?.remove();
};
const downloadResult=(content,type)=>{
  const project=state.projects.find(item=>item.id===state.currentVersion?.project_id);
  const basename=HeyuContent.safeFilename(project?.title||"heyu-content");
  const isJson=type==="json";
  const body=isJson?JSON.stringify(content,null,2):HeyuContent.renderContent(content,{t:HeyuI18n.t,locale:HeyuI18n.getLocale()});
  const blob=new Blob([body],{type:isJson?"application/json;charset=utf-8":"text/plain;charset=utf-8"});
  const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=`${basename}.${isJson?"json":"txt"}`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);
};
const downloadCampaignPresentation=async campaign=>{
  const response=await apiFile(`/v1/campaign-packages/${campaign.id}/presentation`);
  const blob=await response.blob();
  const link=document.createElement("a");
  link.href=URL.createObjectURL(blob);
  link.download=`${HeyuContent.safeFilename(campaign.title||"heyu-campaign")}.pptx`;
  link.click();
  setTimeout(()=>URL.revokeObjectURL(link.href),0);
};
const workspacePages=["overview","plans","assets","knowledge","campaigns","studio","operations","review","audit","members"];
const pageFromLocation=()=>{const page=location.pathname.split("/").filter(Boolean)[1]||"overview";return workspacePages.includes(page)?page:"overview"};

function showWorkspace(){
  $("#auth-view").hidden=Boolean(state.token);$("#workspace").hidden=!state.token;$("#logout").hidden=!state.token;
  if(state.token){sessionInvalidated=false;navigate(pageFromLocation(),false);refresh().catch(error=>{if(!sessionInvalidated)toast(error.message,true)})}
}
async function showInvitation(){
  if(!state.inviteToken||state.token)return;
  const tab=$('[data-auth-mode="invite"]');tab.hidden=false;
  $$('[data-auth-mode]').forEach(x=>x.classList.toggle("active",x===tab));
  $$('[data-auth-panel]').forEach(panel=>panel.hidden=panel.dataset.authPanel!=="invite");
  const form=$("#invite-accept-form");form.elements.token.value=state.inviteToken;
  try{
    const invite=await api("/v1/invitations/inspect",{method:"POST",body:JSON.stringify({token:state.inviteToken})});
    const expired=new Date(invite.expires_at)<=new Date();
    const invalid=Boolean(invite.accepted_at||invite.revoked_at||expired);
    $("#invite-summary").textContent=invalid?t("invite.invalid"):t("invite.summary",{organization:invite.organization_name,email:invite.email,role:roleLabel(invite.role)});
    $("#invite-summary").classList.toggle("error",invalid);
    form.querySelector("button").disabled=invalid;
  }catch(error){$("#invite-summary").textContent=error.message;$("#invite-summary").classList.add("error");form.querySelector("button").disabled=true}
}
function navigate(page,push=true){
  if(!workspacePages.includes(page))page="overview";
  $$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.page===page));
  $$(".page").forEach(x=>x.classList.toggle("active",x.dataset.pagePanel===page));
  $("#page-title").textContent=t(`workspace.page.${page}`);
  const path=page==="overview"?"/workspace/":`/workspace/${page}`;
  if(push&&location.pathname!==path)history.pushState({page},"",path);
}
async function refresh(){
  state.actor=await api("/v1/me");
  const canManageMembers=["owner","admin"].includes(state.actor.role);
  [state.brands,state.products,state.knowledge,state.campaigns,state.marketingPlans,state.projects,state.publications,state.audit]=await Promise.all([api("/v1/brands"),api("/v1/products"),api("/v1/knowledge"),api("/v1/campaign-packages"),api("/v1/marketing-plans"),api("/v1/content-projects"),api("/v1/publications"),api("/v1/audit-events")]);
  [state.members,state.invitations]=canManageMembers?await Promise.all([api("/v1/members"),api("/v1/invitations")]):[[],[]];
  $$(".member-nav").forEach(x=>x.hidden=!canManageMembers);
  if(!canManageMembers&&$(".nav.active")?.dataset.page==="members")navigate("overview");
  render();
  const requestedPlan=new URLSearchParams(location.search).get("plan");
  const pendingImport=new URLSearchParams(location.search).get("import")==="1";
  if(pendingImport&&canWriteScope("content")&&pendingMarketingPlan()){
    await importPendingMarketingPlan();
    return;
  }
  const planId=requestedPlan||state.currentMarketingPlan?.id||state.marketingPlans[0]?.id;
  if(planId)await openMarketingPlan(planId,false);
}
const canWriteScope=scope=>{
  const role=state.actor?.role;
  if(scope==="assets")return ["owner","admin","product_manager"].includes(role);
  if(scope==="farmer-evidence")return ["owner","admin","product_manager"].includes(role);
  if(scope==="content")return ["owner","admin","product_manager","creator"].includes(role);
  return false;
};
function renderAccessMode(){
  const readonly=["reviewer","viewer"].includes(state.actor.role);
  const banner=$("#access-mode-banner");
  banner.hidden=!readonly;
  if(readonly){
    const mode=state.actor.role==="reviewer"?"reviewer":"viewer";
    $("#access-mode-title").textContent=t(`access.${mode}.title`);
    $("#access-mode-copy").textContent=t(`access.${mode}.copy`);
    $("#access-mode-role").textContent=roleLabel(state.actor.role);
  }
  $$("[data-write-scope]").forEach(element=>{element.hidden=!canWriteScope(element.dataset.writeScope)});
}
function options(items,placeholder){
  return `<option value="">${placeholder}</option>`+items.map(x=>`<option value="${x.id}">${escapeHtml(x.name||x.title)}</option>`).join("");
}
function renderAssetCard(item,type){
  const isBrand=type==="brands";
  const canSubmit=["owner","admin","product_manager"].includes(state.actor.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor.role);
  const canEdit=["owner","admin","product_manager"].includes(state.actor.role);
  const description=isBrand
    ? item.story||t("asset.brandStoryMissing")
    : `${item.origin||t("asset.originMissing")}${fieldSeparator()}${item.specification||t("asset.specificationMissing")}`;
  const editButton=canEdit?`<button data-edit-${isBrand?"brand":"product"}="${item.id}">${escapeHtml(t(isBrand?"asset.editBrand":"asset.editProduct"))}</button>`:"";
  const submitButton=canSubmit&&item.status==="draft"?`<button class="approve" data-submit-asset="${item.id}" data-asset-type="${type}">${escapeHtml(t("asset.submit"))}</button>`:"";
  const reviewButtons=canReview&&item.status==="pending_review"?`<button class="approve" data-review-asset="${item.id}" data-asset-type="${type}" data-status="approved">${escapeHtml(t("asset.approve"))}</button><button class="reject" data-review-asset="${item.id}" data-asset-type="${type}" data-status="rejected">${escapeHtml(t("asset.reject"))}</button>`:"";
  return `<article><div class="panel-heading"><span class="pill">${escapeHtml(t(isBrand?"asset.brand":"asset.product"))}</span><span class="badge ${item.status}">${escapeHtml(contentStatusLabel(item.status))}</span></div><h3>${escapeHtml(item.name)}</h3><p>${escapeHtml(description)}</p>${item.review_note?`<p class="review-note">${escapeHtml(t("asset.reviewNote",{note:item.review_note}))}</p>`:""}${editButton||submitButton||reviewButtons?`<div class="row-actions">${editButton}${submitButton}${reviewButtons}</div>`:""}</article>`;
}
const pendingMarketingPlan=()=>{
  const raw=sessionStorage.getItem("heyu_pending_marketing_plan");
  if(!raw)return null;
  try{
    const value=JSON.parse(raw);
    return value&&value.title&&value.request_payload&&value.content?value:null;
  }catch{
    sessionStorage.removeItem("heyu_pending_marketing_plan");
    return null;
  }
};
const marketingPlanDate=value=>new Intl.DateTimeFormat(HeyuI18n.getLocale(),{dateStyle:"medium",timeStyle:"short"}).format(new Date(value));
const marketingPlanVersion=()=>state.selectedMarketingVersion||state.currentMarketingPlan?.current_version||null;
const marketingPlanSection=(title,body,wide=false)=>`<section class="plan-preview-section${wide?" wide":""}"><p class="eyebrow">${escapeHtml(title)}</p>${body}</section>`;
const marketingPlanListItems=items=>`<ul>${(items||[]).map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
function marketingPlanPreviewHtml(content){
  if(!content?.product_profile||!content?.strategy||!Array.isArray(content?.videos))return `<pre>${escapeHtml(JSON.stringify(content,null,2))}</pre>`;
  const profile=content.product_profile;
  const strategy=content.strategy;
  const trend=content.trend||{};
  const videos=content.videos.map((video,index)=>`<article class="plan-video-card"><span>${escapeHtml(t("marketingPlans.videoNumber",{number:index+1}))}</span><h4>${escapeHtml(video.title)}</h4><p>${escapeHtml(video.hook)}</p><small>${escapeHtml(video.angle)}${fieldSeparator()}${escapeHtml(video.background_music)}</small><details><summary>${escapeHtml(t("marketingPlans.openScript"))}</summary><p>${escapeHtml(video.script)}</p><ol>${(video.shots||[]).map(shot=>`<li><b>${escapeHtml(shot.seconds)}</b><span>${escapeHtml(shot.visual)}</span><small>${escapeHtml(shot.voiceover)}</small></li>`).join("")}</ol><strong>${escapeHtml(video.call_to_action)}</strong></details></article>`).join("");
  const livestream=(content.livestream||[]).map(section=>`<article><h4>${escapeHtml(section.section)}</h4>${marketingPlanListItems(section.talking_points)}</article>`).join("");
  const calendar=(content.seven_day_plan||[]).map(day=>`<article><b>${escapeHtml(t("marketingPlans.day",{day:day.day}))}</b><h4>${escapeHtml(day.objective)}</h4><p>${escapeHtml(day.content)}</p><small>${escapeHtml(day.action)}</small></article>`).join("");
  return `<div class="plan-preview-grid">${marketingPlanSection(t("marketingPlans.positioning"),`<h3>${escapeHtml(profile.one_line_value)}</h3><p>${escapeHtml(profile.story_angle)}</p>${marketingPlanListItems(profile.core_selling_points)}`)}${marketingPlanSection(t("marketingPlans.strategy"),`<h3>${escapeHtml(strategy.platform_name)}</h3><p>${escapeHtml(strategy.content_focus)}</p><dl><div><dt>${escapeHtml(t("marketingPlans.duration"))}</dt><dd>${escapeHtml(strategy.recommended_duration)}</dd></div><div><dt>${escapeHtml(t("marketingPlans.conversion"))}</dt><dd>${escapeHtml(strategy.conversion_action)}</dd></div></dl>`)}${marketingPlanSection(t("marketingPlans.trend"),`<h3>${escapeHtml(trend.trend_used||t("marketingPlans.noTrend"))}</h3><p>${escapeHtml(trend.integration_method||"")}</p><small>${escapeHtml(trend.caution||"")}</small>`,true)}${marketingPlanSection(t("marketingPlans.videos"),`<div class="plan-video-grid">${videos}</div>`,true)}${marketingPlanSection(t("marketingPlans.livestream"),`<div class="plan-live-grid">${livestream}</div>`,true)}${marketingPlanSection(t("marketingPlans.sevenDays"),`<div class="plan-calendar">${calendar}</div>`,true)}${marketingPlanSection(t("marketingPlans.nextActions"),marketingPlanListItems(content.next_actions),true)}</div>`;
}
function renderMarketingPlans(){
  const canEdit=canWriteScope("content");
  const pending=pendingMarketingPlan();
  $("#marketing-plan-count").textContent=HeyuI18n.formatNumber(state.marketingPlans.length);
  $("#marketing-plan-import").hidden=!pending;
  $("#import-marketing-plan").hidden=!canEdit;
  $("#marketing-plan-list").classList.toggle("empty",state.marketingPlans.length===0);
  $("#marketing-plan-list").innerHTML=state.marketingPlans.map(plan=>`<button class="plan-list-item${plan.id===state.currentMarketingPlan?.id?" active":""}" data-open-marketing-plan="${plan.id}"><span><b>${escapeHtml(plan.title)}</b><small>${escapeHtml(plan.product_name)}${fieldSeparator()}${escapeHtml(plan.platform)}</small></span><i>v${escapeHtml(plan.current_version.version_number)}</i></button>`).join("")||`<p>${escapeHtml(t("marketingPlans.empty"))}</p>`;
  const detail=state.currentMarketingPlan;
  $("#marketing-plan-empty").hidden=Boolean(detail);
  $("#marketing-plan-detail").hidden=!detail;
  if(!detail)return;
  const version=marketingPlanVersion();
  $("#marketing-plan-title").textContent=detail.title;
  $("#marketing-plan-meta").innerHTML=`<span>${escapeHtml(detail.product_name)}</span><span>${escapeHtml(detail.platform)}</span><span>${escapeHtml(detail.locale)}</span><span>${escapeHtml(version.provider)} / ${escapeHtml(version.model)}</span>${version.degraded?`<span>${escapeHtml(t("marketingPlans.degraded"))}</span>`:""}`;
  $("#marketing-plan-preview").innerHTML=marketingPlanPreviewHtml(version.content);
  $("#marketing-plan-editor").value=JSON.stringify(version.content,null,2);
  $("#marketing-plan-version-count").textContent=HeyuI18n.formatNumber(detail.versions.length);
  $("#marketing-plan-versions").innerHTML=[...detail.versions].reverse().map(item=>`<button class="${item.id===version.id?"active":""}" data-open-marketing-version="${item.id}"><b>v${escapeHtml(item.version_number)}</b><span>${escapeHtml(item.change_summary||t("marketingPlans.noChangeSummary"))}</span><small>${escapeHtml(marketingPlanDate(item.created_at))}</small></button>`).join("");
  $("#copy-marketing-plan").hidden=!canEdit;
}
async function openMarketingPlan(planId,push=true){
  const detail=await api(`/v1/marketing-plans/${encodeURIComponent(planId)}`);
  state.currentMarketingPlan=detail;
  state.selectedMarketingVersion=detail.current_version;
  if(push)history.pushState({page:"plans",plan:planId},"",`/workspace/plans?plan=${encodeURIComponent(planId)}`);
  renderMarketingPlans();
}
async function importPendingMarketingPlan(){
  const snapshot=pendingMarketingPlan();
  if(!snapshot)throw new Error(t("marketingPlans.noPending"));
  const saved=await api("/v1/marketing-plans",{method:"POST",body:JSON.stringify(snapshot)});
  sessionStorage.removeItem("heyu_pending_marketing_plan");
  state.marketingPlans=await api("/v1/marketing-plans");
  state.currentMarketingPlan=saved;
  state.selectedMarketingVersion=saved.current_version;
  history.replaceState({page:"plans",plan:saved.id},"",`/workspace/plans?plan=${encodeURIComponent(saved.id)}`);
  renderMarketingPlans();
  toast(t("marketingPlans.imported"));
}
function render(){
  renderAccessMode();
  const approvedKnowledge=state.knowledge.filter(x=>x.status==="approved").length;
  const pendingKnowledge=state.knowledge.filter(x=>x.status!=="approved").length;
  $("#brand-count").textContent=state.brands.length;$("#product-count").textContent=state.products.length;
  $("#knowledge-count").textContent=approvedKnowledge;$("#project-count").textContent=state.projects.length;
  renderFocus(approvedKnowledge,pendingKnowledge);
  $$(".brand-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.brands,t("select.brand"));x.value=value});
  $$(".product-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.products,t("select.product"));x.value=value});
  $("#project-select").innerHTML=options(state.projects,t("select.project"));
  const reviewSelect=$("#review-project-select");const reviewValue=reviewSelect.value;reviewSelect.innerHTML=options(state.projects,t("select.project"));reviewSelect.value=reviewValue;
  const publicationProject=$("#publication-project-select");const publicationProjectValue=publicationProject.value;publicationProject.innerHTML=options(state.projects,t("select.project"));publicationProject.value=publicationProjectValue;
  $("#asset-list").innerHTML=[...state.brands.map(item=>renderAssetCard(item,"brands")),...state.products.map(item=>renderAssetCard(item,"products"))].join("")||escapeHtml(t("asset.empty"));
  const canManageProjects=["owner","admin","creator","product_manager"].includes(state.actor.role);
  $("#project-list").innerHTML=state.projects.map(project=>`<article><span class="pill">${escapeHtml(contentTypeLabel(project.content_type))}</span><h3>${escapeHtml(project.title)}</h3><p>${escapeHtml(project.platform||t("content.platformDefault"))} · ${escapeHtml(project.target_audience||t("content.audienceMissing"))}</p>${canManageProjects?`<div class="row-actions"><button data-edit-project="${project.id}">${escapeHtml(t("content.editProject"))}</button></div>`:""}</article>`).join("")||escapeHtml(t("content.projectEmpty"));
  const canSubmitKnowledge=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReviewKnowledge=["owner","admin","reviewer"].includes(state.actor.role);
  $("#knowledge-list").innerHTML=state.knowledge.map(k=>`<article><h3>${escapeHtml(k.title)} <span class="badge">${escapeHtml(t("source.revision",{number:k.revision_number||1}))}</span></h3><p>${escapeHtml(k.content.slice(0,130))}</p><div class="source-meta">${k.source_filename?`<span>${escapeHtml(t("source.file",{filename:k.source_filename}))}</span>`:`<span>${escapeHtml(t("source.manualEntry"))}</span>`}<span>${escapeHtml(k.media_type||"text/plain")}</span>${k.content_sha256?`<span title="${escapeHtml(k.content_sha256)}">SHA-256 ${escapeHtml(k.content_sha256.slice(0,12))}…</span>`:""}${k.citation_label?`<span>${escapeHtml(t("source.citation",{label:k.citation_label}))}</span>`:""}${k.parent_source_id?`<span>${escapeHtml(t("source.derivedFrom",{number:(k.revision_number||1)-1}))}</span>`:""}${k.change_summary?`<span>${escapeHtml(t("source.changeSummary",{summary:k.change_summary}))}</span>`:""}${k.reviewed_by?`<span>${escapeHtml(t("source.reviewer",{reviewer:k.reviewed_by.slice(0,8)}))}</span>`:""}</div>${k.review_note?`<p class="review-note">${escapeHtml(t("source.reviewNote",{note:k.review_note}))}</p>`:""}<span class="badge ${k.status}">${escapeHtml(contentStatusLabel(k.status))}</span>${k.status==="draft"&&canSubmitKnowledge?`<div class="row-actions"><button class="approve" data-submit-source="${k.id}">${escapeHtml(t("source.submit"))}</button></div>`:""}${["approved","rejected"].includes(k.status)&&canSubmitKnowledge?`<div class="row-actions"><button data-revise-source="${k.id}">${escapeHtml(t("source.revise"))}</button></div>`:""}${k.status==="pending_review"&&canReviewKnowledge?`<div class="row-actions"><button class="approve" data-review-source="${k.id}" data-status="approved">${escapeHtml(t("source.approve"))}</button><button class="reject" data-review-source="${k.id}" data-status="rejected">${escapeHtml(t("source.reject"))}</button></div>`:""}</article>`).join("")||escapeHtml(t("source.empty"));
  $("#audit-list").innerHTML=state.audit.map(item=>`<article><h3>${escapeHtml(actionLabel(item.action))}</h3><p>${escapeHtml(item.entity_type)} · ${escapeHtml(item.entity_id)}</p><div class="audit-meta"><span>${escapeHtml(t("audit.actor",{actor:item.actor_id.slice(0,8)}))}</span><span>${escapeHtml(JSON.stringify(item.details))}</span></div></article>`).join("")||escapeHtml(t("audit.empty"));
  renderCampaigns();
  renderOperationCopy();
  renderOperationImportPreview();
  renderPublications();
  renderMembers();
  renderMarketingPlans();
}
const campaignStatusLabel=value=>t(`campaign.status.${value}`);
const campaignGenerationBlockerLabel=code=>{
  const key=`campaign.generationBlocker.${code}`;
  const label=t(key);
  return label===key?code:label;
};
function renderCampaigns(){
  $("#campaign-count").textContent=t("campaign.count",{count:HeyuI18n.formatNumber(state.campaigns.length)});
  const canManage=canWriteScope("content");
  $("#campaign-list").innerHTML=state.campaigns.map(campaign=>{
    const progress=campaign.progress;
    const items=campaign.items.map(item=>{
      const stale=Boolean(item.latest_version_id&&!item.content_current);
      const staleDetail=(item.stale_reasons||[]).map(reason=>t(`contentFreshness.${reason}`)).join(fieldSeparator());
      const status=item.publication_id?t("campaign.item.published"):item.approved_version_id?t("campaign.item.approved"):item.latest_version_id?t("campaign.item.draft"):t("campaign.item.notStarted");
      const generationReady=Boolean(progress.generation_ready);
      const action=canManage&&generationReady&&(!item.latest_version_id||stale)?`<button data-generate-campaign-item="${item.content_project_id}">${escapeHtml(t(stale?"supply.regenerate":"campaign.generate"))}</button>`:"";
      return `<li class="${stale?"supply-stale":""}"><span>${escapeHtml(t(`campaign.slot.${item.slot_key}`))}${stale?`<small>${escapeHtml(staleDetail||t("contentFreshness.content_stale"))}</small>`:""}</span><b>${escapeHtml(status)}</b>${action}</li>`;
    }).join("");
    const readiness=`<div class="campaign-readiness"><span class="readiness-chip ${progress.brief_ready?"ready":""}">${escapeHtml(t(progress.brief_ready?"campaignBrief.ready":"campaignBrief.missing"))}</span><span class="readiness-chip ${progress.supply_ready?"ready":""}">${escapeHtml(t(progress.supply_ready?"farmerEvidence.supplyReady":"farmerEvidence.supplyMissing"))}</span><span class="readiness-chip ${progress.farmer_evidence_ready?"ready":""}">${escapeHtml(t(progress.farmer_evidence_ready?"farmerEvidence.ready":"farmerEvidence.missing"))}</span><button data-open-campaign-brief="${campaign.id}">${escapeHtml(t("campaignBrief.open"))}</button></div>`;
    const generationBlockers=progress.generation_ready||!progress.generation_blockers?.length?"":`<div class="campaign-generation-blockers"><strong>${escapeHtml(t("campaign.generationBlocked"))}</strong><ul>${progress.generation_blockers.map(code=>`<li>${escapeHtml(campaignGenerationBlockerLabel(code))}</li>`).join("")}</ul></div>`;
    return `<article class="campaign-card"><div class="panel-heading"><div><span class="badge ${campaign.status==="completed"?"approved":"pending_review"}">${escapeHtml(campaignStatusLabel(campaign.status))}</span><h3>${escapeHtml(campaign.title)}</h3></div><strong>${progress.required_approved}/${progress.required}</strong></div><p>${escapeHtml(campaign.platform)} · ${escapeHtml(campaign.target_audience)}</p>${readiness}${generationBlockers}<div class="campaign-progress"><i style="width:${progress.required?Math.round(progress.required_approved/progress.required*100):0}%"></i></div><ul>${items}</ul><div class="row-actions"><button data-download-campaign-pptx="${campaign.id}">${escapeHtml(t("campaign.presentation.download"))}</button></div></article>`;
  }).join("")||`<p>${escapeHtml(t("campaign.empty"))}</p>`;
  renderCampaignBriefOptions();
  renderSupplyCampaignOptions();
  renderFarmerEvidenceCampaignOptions();
}
const campaignBriefCampaign=()=>state.campaigns.find(item=>item.id===$("#campaign-brief-campaign-select")?.value);
const briefClaimTypes=["product_fact","brand_story","regional_culture","supply_fact","farmer_impact","other"];
const briefEvidenceTypes=["knowledge_source","supply_snapshot","farmer_evidence_snapshot"];
const briefSupplyKeys=["specification","price_minor","available_quantity","quantity_unit","harvest_status","harvest_date","shipping_regions","ship_within_hours","freight_policy","storage_and_freshness","shortage_policy"];
const briefFarmerKeys=["party_display_name","relationship_type","relationship_summary","benefit_mechanism","allowed_claims","prohibited_claims","consent_scope"];
let activeCampaignBriefFormId=null;
const briefEvidenceSources=(campaign,type)=>{
  if(!campaign)return[];
  if(type==="knowledge_source")return state.knowledge.filter(item=>item.status==="approved"&&(item.product_id===campaign.product_id||item.brand_id===campaign.brand_id)).map(item=>({id:item.id,label:item.title}));
  if(type==="supply_snapshot")return campaign.current_supply_snapshot?[{id:campaign.current_supply_snapshot.id,label:t("campaignBrief.currentSupply")}]:[];
  if(type==="farmer_evidence_snapshot")return campaign.current_farmer_evidence_snapshot?[{id:campaign.current_farmer_evidence_snapshot.id,label:t("campaignBrief.currentFarmerEvidence")}]:[];
  return[];
};
const briefEvidenceKeys=type=>type==="supply_snapshot"?briefSupplyKeys:type==="farmer_evidence_snapshot"?briefFarmerKeys:["content"];
const briefSelectOptions=(items,selected="")=>items.map(item=>`<option value="${escapeHtml(item.id??item)}"${String(item.id??item)===String(selected)?" selected":""}>${escapeHtml(item.label??t(`campaignBrief.evidenceKey.${item}`))}</option>`).join("");
function refreshClaimRow(row){
  const campaign=campaignBriefCampaign();
  const type=row.querySelector('[data-claim-field="source_type"]').value;
  const sourceSelect=row.querySelector('[data-claim-field="source_id"]');
  const keySelect=row.querySelector('[data-claim-field="evidence_key"]');
  const previousSource=sourceSelect.value;
  const previousKey=keySelect.value;
  const sources=briefEvidenceSources(campaign,type);
  sourceSelect.innerHTML=`<option value="">${escapeHtml(t("campaignBrief.selectEvidence"))}</option>${briefSelectOptions(sources,previousSource)}`;
  if(sources.some(item=>item.id===previousSource))sourceSelect.value=previousSource;
  const keys=briefEvidenceKeys(type);
  keySelect.innerHTML=briefSelectOptions(keys,previousKey);
  if(keys.includes(previousKey))keySelect.value=previousKey;
  keySelect.disabled=type==="knowledge_source";
}
function addCampaignBriefClaim(claim={}){
  const ref=claim.evidence_refs?.[0]||{source_type:"knowledge_source",source_id:"",evidence_key:"content"};
  const row=document.createElement("div");
  row.className="claim-row";
  row.innerHTML=`<button class="remove-claim" type="button" data-remove-brief-claim aria-label="${escapeHtml(t("campaignBrief.removeClaim"))}">×</button><div class="claim-row-grid"><label><span>${escapeHtml(t("campaignBrief.claimText"))}</span><textarea data-claim-field="claim_text" required>${escapeHtml(claim.claim_text||"")}</textarea></label><label><span>${escapeHtml(t("campaignBrief.claimType"))}</span><select data-claim-field="claim_type">${briefClaimTypes.map(type=>`<option value="${type}"${type===(claim.claim_type||"product_fact")?" selected":""}>${escapeHtml(t(`campaignBrief.claimType.${type}`))}</option>`).join("")}</select></label></div><div class="claim-row-source"><label><span>${escapeHtml(t("campaignBrief.sourceType"))}</span><select data-claim-field="source_type">${briefEvidenceTypes.map(type=>`<option value="${type}"${type===ref.source_type?" selected":""}>${escapeHtml(t(`campaignBrief.sourceType.${type}`))}</option>`).join("")}</select></label><label><span>${escapeHtml(t("campaignBrief.source"))}</span><select data-claim-field="source_id" required></select></label><label><span>${escapeHtml(t("campaignBrief.evidenceKey"))}</span><select data-claim-field="evidence_key"></select></label></div>`;
  $("#campaign-brief-claims").append(row);
  refreshClaimRow(row);
  row.querySelector('[data-claim-field="source_id"]').value=ref.source_id||"";
  row.querySelector('[data-claim-field="evidence_key"]').value=ref.evidence_key||"";
}
function populateCampaignBriefForm(campaign){
  const form=$("#campaign-brief-form");
  if(!form)return;
  const brief=campaign?.current_brief_revision;
  form.reset();
  form.elements.platform.value=brief?.platform||campaign?.platform||"";
  form.elements.locale.value=brief?.locale||HeyuI18n.getLocale();
  form.elements.target_audience.value=brief?.target_audience||campaign?.target_audience||"";
  form.elements.audience_need.value=brief?.audience_need||"";
  form.elements.objective.value=brief?.objective||campaign?.objective||"";
  form.elements.core_message.value=brief?.core_message||"";
  form.elements.desired_action.value=brief?.desired_action||"";
  form.elements.tone.value=brief?.tone||campaign?.tone||"";
  form.elements.hook_seconds.value=brief?.channel_constraints?.hook_seconds||"";
  form.elements.max_duration_seconds.value=brief?.channel_constraints?.max_duration_seconds||"";
  form.elements.mandatory_messages.value=(brief?.mandatory_messages||[]).join("\n");
  form.elements.prohibited_messages.value=(brief?.prohibited_messages||[]).join("\n");
  form.elements.extra_requirements.value=brief?.extra_requirements||campaign?.extra_requirements||"";
  form.elements.change_summary.value="";
  $("#campaign-brief-claims").innerHTML="";
  (brief?.claim_evidence||[]).forEach(addCampaignBriefClaim);
  if(!brief?.claim_evidence?.length)addCampaignBriefClaim();
}
function renderCampaignBriefOptions(){
  const select=$("#campaign-brief-campaign-select");
  if(!select)return;
  const selected=select.value;
  select.innerHTML=options(state.campaigns,t("campaignBrief.selectCampaign"));
  if(state.campaigns.some(item=>item.id===selected))select.value=selected;
  else if(state.campaigns.length)select.value=state.campaigns[0].id;
  if(select.value!==activeCampaignBriefFormId){
    activeCampaignBriefFormId=select.value||null;
    populateCampaignBriefForm(campaignBriefCampaign());
    loadCampaignBriefRevisions(select.value).catch(error=>toast(error.message,true));
  }
}
const briefBlockerLabel=blocker=>{
  const key=blocker.split(":")[0];
  const label=t(`campaignBrief.blocker.${key}`);
  return label===`campaignBrief.blocker.${key}`?blocker:label;
};
function renderCampaignBriefHistory(){
  const campaign=campaignBriefCampaign();
  const currentId=campaign?.current_brief_revision?.id;
  const canSubmit=["owner","admin","creator","product_manager"].includes(state.actor?.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor?.role);
  $("#campaign-brief-revision-count").textContent=HeyuI18n.formatNumber(state.campaignBriefRevisions.length);
  $("#campaign-brief-history").innerHTML=state.campaignBriefRevisions.map(brief=>{
    const map=state.campaignBriefMaps[brief.id]||{complete:false,mapped_claims:0,total_claims:brief.claim_evidence.length,blockers:[]};
    const current=brief.id===currentId;
    const submit=canSubmit&&brief.status==="draft"?`<button class="approve" data-submit-campaign-brief="${brief.id}" data-campaign="${brief.campaign_package_id}">${escapeHtml(t("campaignBrief.submit"))}</button>`:"";
    const review=canReview&&brief.status==="pending_review"?`<button class="approve" data-review-campaign-brief="${brief.id}" data-campaign="${brief.campaign_package_id}" data-status="approved">${escapeHtml(t("campaignBrief.approve"))}</button><button class="reject" data-review-campaign-brief="${brief.id}" data-campaign="${brief.campaign_package_id}" data-status="rejected">${escapeHtml(t("campaignBrief.reject"))}</button>`:"";
    const blockers=map.blockers.length?`<div class="brief-blockers">${map.blockers.map(item=>escapeHtml(briefBlockerLabel(item))).join("<br>")}</div>`:"";
    const proofs=brief.proof_points.length?`<ul class="brief-proof-list">${brief.proof_points.map(item=>`<li>${escapeHtml(item)}</li>`).join("")}</ul>`:"";
    return `<article class="brief-card ${current?"current":""}"><div class="panel-heading"><div><span class="badge ${brief.status}">${escapeHtml(contentStatusLabel(brief.status))}</span>${current?`<span class="badge approved">${escapeHtml(t("campaignBrief.current"))}</span>`:""}<h3>${escapeHtml(t("campaignBrief.revision",{number:brief.revision_number}))}</h3></div><span class="pill">${escapeHtml(enumLabel("campaignBrief.locale",brief.locale))}</span></div><p>${escapeHtml(brief.core_message)}</p><div class="brief-score"><span>${escapeHtml(t(map.complete?"campaignBrief.evidenceComplete":"campaignBrief.evidenceIncomplete"))}</span><strong>${map.mapped_claims}/${map.total_claims}</strong></div>${blockers}${proofs}${brief.change_summary?`<p class="review-note">${escapeHtml(brief.change_summary)}</p>`:""}${submit||review?`<div class="row-actions">${submit}${review}</div>`:""}</article>`;
  }).join("")||`<p>${escapeHtml(t("campaignBrief.empty"))}</p>`;
}
async function loadCampaignBriefRevisions(campaignId){
  if(!campaignId){state.campaignBriefRevisions=[];state.campaignBriefMaps={};renderCampaignBriefHistory();return}
  const revisions=await api(`/v1/campaign-packages/${campaignId}/brief-revisions`);
  const maps=await Promise.all(revisions.map(brief=>api(`/v1/campaign-packages/${campaignId}/brief-revisions/${brief.id}/claim-evidence-map`)));
  state.campaignBriefRevisions=revisions;
  state.campaignBriefMaps=Object.fromEntries(maps.map(map=>[map.brief_revision_id,map]));
  renderCampaignBriefHistory();
}
const toIso=value=>new Date(value).toISOString();
const formatSupplyMoney=snapshot=>new Intl.NumberFormat(HeyuI18n.getLocale(),{style:"currency",currency:snapshot.currency}).format(Number(snapshot.price_minor||0)/100);
const supplyIsCurrent=(campaign,snapshot)=>campaign?.current_supply_snapshot?.id===snapshot.id;
function renderSupplyCampaignOptions(){
  const select=$("#supply-campaign-select");
  if(!select)return;
  const selected=select.value;
  select.innerHTML=options(state.campaigns,t("supply.selectCampaign"));
  if(state.campaigns.some(item=>item.id===selected))select.value=selected;
  else if(state.campaigns.length)select.value=state.campaigns[0].id;
  renderSupplyEvidence();
  loadSupplySnapshots(select.value).catch(error=>toast(error.message,true));
}
function renderSupplyEvidence(){
  const campaign=state.campaigns.find(item=>item.id===$("#supply-campaign-select")?.value);
  const sources=campaign?state.knowledge.filter(item=>item.status==="approved"&&(item.product_id===campaign.product_id||item.brand_id===campaign.brand_id)):[];
  const target=$("#supply-evidence-list");
  if(!target)return;
  target.innerHTML=sources.map(source=>`<label><input type="checkbox" name="evidence_source_ids" value="${escapeHtml(source.id)}"><span><strong>${escapeHtml(source.title)}</strong><small>${escapeHtml(source.citation_label||t("source.manualEntry"))}</small></span></label>`).join("")||`<p class="form-note">${escapeHtml(t("supply.noEvidence"))}</p>`;
}
async function loadSupplySnapshots(campaignId){
  state.campaignSupplySnapshots=campaignId?await api(`/v1/campaign-packages/${campaignId}/supply-snapshots`):[];
  renderSupplyHistory(campaignId);
}
function renderSupplyHistory(campaignId){
  const campaign=state.campaigns.find(item=>item.id===campaignId);
  const canSubmit=["owner","admin","creator","product_manager"].includes(state.actor?.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor?.role);
  $("#supply-revision-count").textContent=t("supply.revisionCount",{count:HeyuI18n.formatNumber(state.campaignSupplySnapshots.length)});
  $("#supply-history").innerHTML=state.campaignSupplySnapshots.map(snapshot=>{
    const current=supplyIsCurrent(campaign,snapshot);
    const evidence=snapshot.evidence_source_ids.map(id=>{const source=state.knowledge.find(item=>item.id===id);return source?.citation_label||source?.title||id.slice(0,8)}).join(fieldSeparator());
    const actions=snapshot.status==="draft"&&canSubmit
      ? `<div class="row-actions"><button class="approve" data-submit-supply="${snapshot.id}" data-campaign="${campaignId}">${escapeHtml(t("supply.submit"))}</button></div>`
      : snapshot.status==="pending_review"&&canReview
        ? `<div class="row-actions"><button class="approve" data-review-supply="${snapshot.id}" data-campaign="${campaignId}" data-status="approved">${escapeHtml(t("supply.approve"))}</button><button class="reject" data-review-supply="${snapshot.id}" data-campaign="${campaignId}" data-status="rejected">${escapeHtml(t("supply.reject"))}</button></div>`
        : "";
    return `<article class="supply-card ${current?"current":""}"><div class="panel-heading"><div><p class="eyebrow">${escapeHtml(t("supply.revision",{number:snapshot.revision_number}))}</p><h3>${escapeHtml(snapshot.specification)}</h3></div><div><span class="badge ${snapshot.status}">${escapeHtml(contentStatusLabel(snapshot.status))}</span>${current?`<span class="badge approved">${escapeHtml(t("supply.current"))}</span>`:`<span class="badge">${escapeHtml(t("supply.notCurrent"))}</span>`}</div></div><div class="supply-facts"><span><b>${escapeHtml(formatSupplyMoney(snapshot))}</b>${escapeHtml(t("supply.validThrough",{date:HeyuI18n.formatDate(snapshot.price_valid_until)}))}</span><span><b>${escapeHtml(`${snapshot.available_quantity} ${snapshot.quantity_unit}`)}</b>${escapeHtml(t("supply.inventoryAt",{date:HeyuI18n.formatDate(snapshot.inventory_confirmed_at)}))}</span><span><b>${escapeHtml(snapshot.harvest_status)}</b>${escapeHtml(snapshot.harvest_date||t("supply.noHarvestDate"))}</span><span><b>${escapeHtml(t("supply.shippingHours",{hours:snapshot.ship_within_hours}))}</b>${escapeHtml(snapshot.shipping_regions.join(fieldSeparator()))}</span></div><p>${escapeHtml(t("supply.activeWindow",{from:HeyuI18n.formatDate(snapshot.active_from),until:HeyuI18n.formatDate(snapshot.active_until)}))}</p><details><summary>${escapeHtml(t("supply.viewDetails"))}</summary><dl class="supply-details"><dt>${escapeHtml(t("supply.freightPolicy"))}</dt><dd>${escapeHtml(snapshot.freight_policy)}</dd><dt>${escapeHtml(t("supply.storageFreshness"))}</dt><dd>${escapeHtml(snapshot.storage_and_freshness)}</dd><dt>${escapeHtml(t("supply.shortagePolicy"))}</dt><dd>${escapeHtml(snapshot.shortage_policy)}</dd><dt>${escapeHtml(t("supply.evidence"))}</dt><dd>${escapeHtml(evidence)}</dd>${snapshot.order_limit?`<dt>${escapeHtml(t("supply.orderLimit"))}</dt><dd>${escapeHtml(snapshot.order_limit)}</dd>`:""}${snapshot.note?`<dt>${escapeHtml(t("supply.note"))}</dt><dd>${escapeHtml(snapshot.note)}</dd>`:""}</dl></details>${snapshot.review_note?`<p class="review-note">${escapeHtml(t("asset.reviewNote",{note:snapshot.review_note}))}</p>`:""}${actions}</article>`;
  }).join("")||`<p>${escapeHtml(t(campaignId?"supply.empty":"supply.selectCampaign"))}</p>`;
}
const farmerClaimTypes=["general_support","direct_sourcing","sourcing_relationship","economic_benefit","unsold_produce_support","quantified_benefit","personal_story","quotation","image","voice"];
const farmerConsentScopes=["party_name","relationship","benefit_mechanism","personal_story","quotation","image","voice"];
const farmerEvidenceIsCurrent=(campaign,snapshot)=>campaign?.current_farmer_evidence_snapshot?.id===snapshot.id;
const farmerEvidenceLabel=(prefix,value)=>t(`farmerEvidence.${prefix}.${value}`);
function renderFarmerEvidenceCampaignOptions(){
  const select=$("#farmer-evidence-campaign-select");
  if(!select)return;
  const selected=select.value;
  select.innerHTML=options(state.campaigns,t("farmerEvidence.selectCampaign"));
  if(state.campaigns.some(item=>item.id===selected))select.value=selected;
  else if(state.campaigns.length)select.value=state.campaigns[0].id;
  const canCreate=["owner","admin","product_manager"].includes(state.actor?.role);
  $("#farmer-evidence-form").hidden=!canCreate;
  renderFarmerClaimChoices();
  renderFarmerEvidenceSources();
  loadFarmerEvidenceSnapshots(select.value).catch(error=>toast(error.message,true));
}
function renderFarmerClaimChoices(){
  const allowed=$("#farmer-allowed-claims");
  const prohibited=$("#farmer-prohibited-claims");
  const consent=$("#farmer-consent-scope");
  if(allowed)allowed.innerHTML=farmerClaimTypes.map(value=>`<label><input type="checkbox" name="allowed_claims" value="${value}"><span>${escapeHtml(farmerEvidenceLabel("claim",value))}</span></label>`).join("");
  if(prohibited)prohibited.innerHTML=farmerClaimTypes.map(value=>`<label><input type="checkbox" name="prohibited_claims" value="${value}"><span>${escapeHtml(farmerEvidenceLabel("claim",value))}</span></label>`).join("");
  if(consent)consent.innerHTML=farmerConsentScopes.map(value=>`<label><input type="checkbox" name="consent_scope" value="${value}"><span>${escapeHtml(farmerEvidenceLabel("consent",value))}</span></label>`).join("");
}
function renderFarmerEvidenceSources(){
  const campaign=state.campaigns.find(item=>item.id===$("#farmer-evidence-campaign-select")?.value);
  const sources=campaign?state.knowledge.filter(item=>item.status==="approved"&&(item.product_id===campaign.product_id||item.brand_id===campaign.brand_id)):[];
  const target=$("#farmer-evidence-source-list");
  if(!target)return;
  target.innerHTML=sources.map(source=>`<label><input type="checkbox" name="evidence_source_ids" value="${escapeHtml(source.id)}"><span><strong>${escapeHtml(source.title)}</strong><small>${escapeHtml(source.citation_label||t("source.manualEntry"))}</small></span></label>`).join("")||`<p class="form-note">${escapeHtml(t("farmerEvidence.noEvidence"))}</p>`;
}
async function loadFarmerEvidenceSnapshots(campaignId){
  state.campaignFarmerEvidenceSnapshots=campaignId?await api(`/v1/campaign-packages/${campaignId}/farmer-evidence-snapshots`):[];
  renderFarmerEvidenceHistory(campaignId);
}
function renderFarmerEvidenceHistory(campaignId){
  const campaign=state.campaigns.find(item=>item.id===campaignId);
  const canSubmit=["owner","admin","product_manager"].includes(state.actor?.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor?.role);
  $("#farmer-evidence-revision-count").textContent=t("farmerEvidence.revisionCount",{count:HeyuI18n.formatNumber(state.campaignFarmerEvidenceSnapshots.length)});
  $("#farmer-evidence-history").innerHTML=state.campaignFarmerEvidenceSnapshots.map(snapshot=>{
    const current=farmerEvidenceIsCurrent(campaign,snapshot);
    const evidence=snapshot.evidence_source_ids.map(id=>{const source=state.knowledge.find(item=>item.id===id);return source?.citation_label||source?.title||id.slice(0,8)}).join(fieldSeparator());
    const allowed=snapshot.allowed_claims.map(value=>farmerEvidenceLabel("claim",value)).join(fieldSeparator());
    const prohibited=snapshot.prohibited_claims.map(value=>farmerEvidenceLabel("claim",value)).join(fieldSeparator())||t("farmerEvidence.none");
    const consent=snapshot.consent_scope.map(value=>farmerEvidenceLabel("consent",value)).join(fieldSeparator())||t("farmerEvidence.none");
    const actions=snapshot.status==="draft"&&canSubmit
      ? `<div class="row-actions"><button class="approve" data-submit-farmer-evidence="${snapshot.id}" data-campaign="${campaignId}">${escapeHtml(t("farmerEvidence.submit"))}</button></div>`
      : snapshot.status==="pending_review"&&canReview
        ? `<div class="row-actions"><button class="approve" data-review-farmer-evidence="${snapshot.id}" data-campaign="${campaignId}" data-status="approved">${escapeHtml(t("farmerEvidence.approve"))}</button><button class="reject" data-review-farmer-evidence="${snapshot.id}" data-campaign="${campaignId}" data-status="rejected">${escapeHtml(t("farmerEvidence.reject"))}</button></div>`
        : "";
    return `<article class="farmer-evidence-card ${current?"current":""}"><div class="panel-heading"><div><p class="eyebrow">${escapeHtml(t("farmerEvidence.revision",{number:snapshot.revision_number}))}</p><h3>${escapeHtml(snapshot.party_display_name)}</h3></div><div><span class="badge ${snapshot.status}">${escapeHtml(contentStatusLabel(snapshot.status))}</span>${current?`<span class="badge approved">${escapeHtml(t("farmerEvidence.current"))}</span>`:`<span class="badge">${escapeHtml(t("farmerEvidence.notCurrent"))}</span>`}</div></div><div class="farmer-evidence-summary"><span><b>${escapeHtml(farmerEvidenceLabel("relationship",snapshot.relationship_type))}</b>${escapeHtml(snapshot.relationship_summary)}</span><span><b>${escapeHtml(t("farmerEvidence.benefitMechanism"))}</b>${escapeHtml(snapshot.benefit_mechanism)}</span></div><p>${escapeHtml(t("farmerEvidence.activeWindow",{from:HeyuI18n.formatDate(snapshot.active_from),until:HeyuI18n.formatDate(snapshot.active_until)}))}</p><details><summary>${escapeHtml(t("farmerEvidence.viewDetails"))}</summary><dl class="supply-details"><dt>${escapeHtml(t("farmerEvidence.allowedClaims"))}</dt><dd>${escapeHtml(allowed)}</dd><dt>${escapeHtml(t("farmerEvidence.prohibitedClaims"))}</dt><dd>${escapeHtml(prohibited)}</dd><dt>${escapeHtml(t("farmerEvidence.consentScope"))}</dt><dd>${escapeHtml(consent)}</dd><dt>${escapeHtml(t("farmerEvidence.evidence"))}</dt><dd>${escapeHtml(evidence)}</dd>${snapshot.note?`<dt>${escapeHtml(t("farmerEvidence.note"))}</dt><dd>${escapeHtml(snapshot.note)}</dd>`:""}</dl></details>${snapshot.review_note?`<p class="review-note">${escapeHtml(t("asset.reviewNote",{note:snapshot.review_note}))}</p>`:""}${actions}</article>`;
  }).join("")||`<p>${escapeHtml(t(campaignId?"farmerEvidence.empty":"farmerEvidence.selectCampaign"))}</p>`;
}

const actionLabel=action=>{const key=`audit.action.${action}`;const label=t(key);return label===key?action:label};
function renderOperationCopy(){
  $$("[data-operation-copy]").forEach(element=>{element.textContent=operationText(element.dataset.operationCopy)});
  $$("[data-operation-placeholder]").forEach(element=>{element.placeholder=operationText(element.dataset.operationPlaceholder)});
  if(state.operationImportFile)$("#operation-import-file-status").textContent=operationText("import.selected",{name:state.operationImportFile.name});
}
const operationMapping=()=>{
  const raw=$("#operation-field-mapping").value.trim();
  if(!raw)return "";
  let mapping;
  try{mapping=JSON.parse(raw)}catch{throw new Error(operationText("import.invalidMapping"))}
  if(!mapping||Array.isArray(mapping)||typeof mapping!=="object")throw new Error(operationText("import.invalidMapping"));
  return JSON.stringify(mapping);
};
const operationImportFormData=()=>{
  if(!state.operationImportFile)throw new Error(operationText("import.previewRequired"));
  const body=new FormData();
  body.append("file",state.operationImportFile,state.operationImportFile.name);
  const mapping=operationMapping();
  if(mapping)body.append("field_mapping_json",mapping);
  return body;
};
function renderOperationImportPreview(){
  const preview=state.operationImportPreview;
  const target=$("#operation-import-preview");
  const confirm=$("#operation-confirm-button");
  if(!preview){target.hidden=true;target.innerHTML="";confirm.disabled=true;return}
  const shown=preview.rows.slice(0,100);
  const mapping=Object.entries(preview.field_mapping||{}).map(([source,destination])=>`<span><b>${escapeHtml(source)}</b> → ${escapeHtml(destination)}</span>`).join("");
  const warnings=(preview.warnings||[]).map(item=>`<li>${escapeHtml(item)}</li>`).join("");
  const rows=shown.map(row=>{
    const status=row.duplicate?"duplicate":row.errors.length?"invalid":row.publication_id?"matched":"unmatched";
    const statusLabel=operationText(`import.${status==="invalid"?"errors":status}`);
    const errors=row.errors.map(error=>escapeHtml(error.message||error.code)).join("<br>")||escapeHtml(operationText("import.noErrors"));
    return `<tr><td>${escapeHtml(row.row_number)}</td><td><span class="operation-row-status ${status}">${escapeHtml(statusLabel)}</span>${row.publication_id?`<small>${escapeHtml(row.publication_id.slice(0,8))}</small>`:""}</td><td><pre>${escapeHtml(JSON.stringify(row.normalized,null,2))}</pre></td><td>${errors}</td></tr>`;
  }).join("");
  confirm.disabled=preview.matched_rows===0;
  target.hidden=false;
  target.innerHTML=`<div class="operation-preview-summary"><strong>${escapeHtml(operationText("import.summary",{total:HeyuI18n.formatNumber(preview.total_rows),valid:HeyuI18n.formatNumber(preview.valid_rows),matched:HeyuI18n.formatNumber(preview.matched_rows),invalid:HeyuI18n.formatNumber(preview.invalid_rows)}))}</strong>${preview.sheet_name?`<span>${escapeHtml(operationText("import.sheet",{name:preview.sheet_name}))}</span>`:""}</div>${mapping?`<div class="operation-mapping-result"><b>${escapeHtml(operationText("import.mapping"))}</b>${mapping}</div>`:""}${warnings?`<div class="operation-warning"><b>${escapeHtml(operationText("import.warnings"))}</b><ul>${warnings}</ul></div>`:""}${preview.matched_rows===0?`<p class="operation-no-match">${escapeHtml(operationText("import.noMatchedRows"))}</p>`:""}<div class="operation-table-wrap"><table><thead><tr><th>${escapeHtml(operationText("import.row"))}</th><th>${escapeHtml(operationText("import.publicationMatch"))}</th><th>${escapeHtml(operationText("import.data"))}</th><th>${escapeHtml(operationText("import.errors"))}</th></tr></thead><tbody>${rows}</tbody></table></div>${preview.rows.length>shown.length?`<p class="form-note">${escapeHtml(operationText("import.moreRows",{count:HeyuI18n.formatNumber(shown.length)}))}</p>`:""}`;
}
function performanceReviewHtml(publicationId,review){
  if(!review)return "";
  const signals=(review.signals||[]).map(item=>`<li><strong>${escapeHtml(item.metric)}</strong><span>${escapeHtml(HeyuI18n.formatNumber(item.value))}</span><small>${escapeHtml(item.basis||"")}</small></li>`).join("")||`<li>${escapeHtml(operationText("review.noSignals"))}</li>`;
  const recommendations=(review.recommendations||[]).map(item=>`<li><strong>${escapeHtml(item.area)}</strong><span>${escapeHtml(item.action)}</span></li>`).join("");
  const limitations=(review.limitations||[]).map(item=>`<li>${escapeHtml(item)}</li>`).join("");
  const canOperate=canWriteScope("content");
  return `<section class="performance-review"><div class="panel-heading"><div><p class="eyebrow">${escapeHtml(operationText("review.heading"))}</p><h3>${escapeHtml(review.summary)}</h3></div><span class="pill">${escapeHtml(operationText("review.method",{method:review.methodology}))}</span></div><div class="performance-review-grid"><div><h4>${escapeHtml(operationText("review.signals"))}</h4><ul class="review-signals">${signals}</ul></div><div><h4>${escapeHtml(operationText("review.recommendations"))}</h4><ul>${recommendations}</ul></div></div>${limitations?`<details><summary>${escapeHtml(operationText("review.limitations"))}</summary><ul>${limitations}</ul></details>`:""}${canOperate?`<button type="button" data-save-performance-brief="${publicationId}">${escapeHtml(operationText("review.saveBrief"))}</button>`:""}</section>`;
}
function renderPublications(){
  const canOperate=canWriteScope("content");
  $("#publication-list").innerHTML=state.publications.map(item=>`<article class="publication-operation-card"><div class="panel-heading"><div><h3>${escapeHtml(item.platform)}</h3><p>${escapeHtml(HeyuI18n.formatDate(item.published_at))}</p></div><span class="badge approved">${escapeHtml(t("publication.published"))}</span></div>${item.external_url?`<p><a href="${escapeHtml(item.external_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(t("publication.viewExternal"))}</a></p>`:""}${canOperate?`<form class="snapshot-form" data-publication-id="${item.id}"><div class="source-meta"><label>${escapeHtml(t("snapshot.capturedAt"))}<input name="captured_at" type="datetime-local" required></label><label>${escapeHtml(t("metric.views"))}<input name="views" type="number" min="0"></label><label>${escapeHtml(t("metric.likes"))}<input name="likes" type="number" min="0"></label><label>${escapeHtml(t("metric.comments"))}<input name="comments" type="number" min="0"></label><label>${escapeHtml(t("metric.shares"))}<input name="shares" type="number" min="0"></label><label>${escapeHtml(t("metric.saves"))}<input name="saves" type="number" min="0"></label><label>${escapeHtml(t("metric.followersGained"))}<input name="followers_gained" type="number" min="0"></label><label>${escapeHtml(t("metric.orders"))}<input name="orders" type="number" min="0"></label><label>${escapeHtml(t("metric.revenueMinor"))}<input name="revenue_minor" type="number" min="0"></label></div><button>${escapeHtml(t("snapshot.add"))}</button></form>`:""}<div class="snapshot-list" data-snapshot-list="${item.id}"></div>${canOperate?`<div class="row-actions operation-review-action"><button type="button" class="primary" data-generate-performance-review="${item.id}">${escapeHtml(operationText("review.generate"))}</button></div>`:""}<div data-performance-review="${item.id}">${performanceReviewHtml(item.id,state.performanceReviews[item.id])}</div>${canOperate?`<details><summary>${escapeHtml(t("diagnosis.add"))}</summary><form class="diagnosis-form" data-publication-id="${item.id}"><label>${escapeHtml(t("diagnosis.observedAt"))}<input name="observed_at" type="datetime-local" required></label><label>${escapeHtml(t("diagnosis.reportTitle"))}<input name="title" required></label><label>${escapeHtml(t("diagnosis.summary"))}<textarea name="summary" rows="2"></textarea></label><label>${escapeHtml(t("diagnosis.transcriptExcerpt"))}<textarea name="transcript_excerpt" rows="2"></textarea></label><label>${escapeHtml(t("diagnosis.category"))}<input name="category" required></label><label>${escapeHtml(t("diagnosis.severity"))}<select name="severity"><option value="observation">${escapeHtml(severityLabel("observation"))}</option><option value="opportunity">${escapeHtml(severityLabel("opportunity"))}</option><option value="risk">${escapeHtml(severityLabel("risk"))}</option></select></label><label>${escapeHtml(t("diagnosis.evidence"))}<textarea name="evidence" rows="2" required></textarea></label><label>${escapeHtml(t("diagnosis.recommendation"))}<textarea name="recommendation" rows="2"></textarea></label><button>${escapeHtml(t("diagnosis.save"))}</button></form></details>`:""}<div class="diagnosis-list" data-diagnosis-list="${item.id}"></div><div class="brief-list" data-brief-list="${item.id}"></div></article>`).join("")||escapeHtml(t("publication.empty"));
  state.publications.forEach(item=>{loadSnapshots(item.id);loadDiagnoses(item.id);loadImprovementBriefs(item.id)});
}
async function loadDiagnoses(publicationId){
  const diagnoses=await api(`/v1/publications/${publicationId}/video-diagnoses`);
  const target=$(`[data-diagnosis-list="${publicationId}"]`);
  const canOperate=canWriteScope("content");
  if(target)target.innerHTML=diagnoses.map(item=>`<article><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary||t("diagnosis.summaryEmpty"))}</p><div class="source-meta"><span>${escapeHtml(HeyuI18n.formatDate(item.observed_at))}</span><span>${escapeHtml(t("diagnosis.findingCount",{count:HeyuI18n.formatNumber(item.findings.length)}))}</span></div>${item.findings.map(finding=>`<p><span class="badge ${finding.severity==="risk"?"rejected":finding.severity==="opportunity"?"pending_review":"approved"}">${escapeHtml(severityLabel(finding.severity))}</span> <strong>${escapeHtml(finding.category)}</strong>${escapeHtml(fieldSeparator())}${escapeHtml(finding.evidence)}${finding.recommendation?`<br>${escapeHtml(t("diagnosis.recommendation"))}${escapeHtml(fieldSeparator())}${escapeHtml(finding.recommendation)}`:""}</p>`).join("")}${canOperate?`<details><summary>${escapeHtml(t("brief.createFromDiagnosis"))}</summary><form class="brief-form" data-publication-id="${publicationId}" data-diagnosis-id="${item.id}"><label>${escapeHtml(t("brief.title"))}<input name="title" required></label><label>${escapeHtml(t("brief.objective"))}<textarea name="objective" rows="2"></textarea></label><label>${escapeHtml(t("brief.actionCategory"))}<input name="category" required></label><label>${escapeHtml(t("brief.instruction"))}<textarea name="instruction" rows="2" required></textarea></label><label>${escapeHtml(t("brief.evidence"))}<textarea name="evidence" rows="2" required></textarea></label><label>${escapeHtml(t("brief.guardrails"))} (${escapeHtml(t("brief.guardrailsHint"))})<textarea name="guardrails" rows="2"></textarea></label><button>${escapeHtml(t("brief.create"))}</button></form></details>`:""}</article>`).join("")||`<p>${escapeHtml(t("diagnosis.empty"))}</p>`;
}
async function loadImprovementBriefs(publicationId){
  const briefs=await api(`/v1/publications/${publicationId}/improvement-briefs`);
  const target=$(`[data-brief-list="${publicationId}"]`);
  const canOperate=canWriteScope("content");
  if(target)target.innerHTML=briefs.length?`<div class="section-head"><div><p class="eyebrow">IMPROVEMENT LOOP</p><h3>${escapeHtml(operationText("brief.heading"))}</h3></div></div>${briefs.map(item=>`<article><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.objective||t("brief.objectiveMissing"))}</p><div class="source-meta"><span>${escapeHtml(t("brief.actionCount",{count:HeyuI18n.formatNumber(item.actions.length)}))}</span><span>${escapeHtml(t("brief.sourceVersion",{version:item.source_content_version_id.slice(0,8)}))}</span></div>${item.actions.map(action=>`<p><strong>${escapeHtml(action.category)}</strong>${escapeHtml(fieldSeparator())}${escapeHtml(action.instruction)}<br><small>${escapeHtml(t("brief.evidence"))}${escapeHtml(fieldSeparator())}${escapeHtml(action.evidence)}</small></p>`).join("")}${item.guardrails.length?`<p>${escapeHtml(t("brief.guardrails"))}${escapeHtml(fieldSeparator())}${item.guardrails.map(escapeHtml).join(" · ")}</p>`:""}${canOperate?`<div class="row-actions"><button type="button" class="primary" data-create-improvement-draft="${item.id}" data-publication-id="${publicationId}" data-source-version-id="${item.source_content_version_id}" data-brief-title="${escapeHtml(item.title)}">${escapeHtml(operationText("brief.oneClickDraft"))}</button></div><details><summary>${escapeHtml(operationText("brief.custom"))}</summary><form class="improvement-draft-form" data-publication-id="${publicationId}" data-brief-id="${item.id}"><label>${escapeHtml(t("successor.contentJson"))}<textarea name="content" rows="8" required></textarea></label><label>${escapeHtml(t("successor.changeSummary"))}<input name="change_summary" required maxlength="255"></label><p class="form-note">${escapeHtml(t("successor.historyNote"))}</p><button>${escapeHtml(t("successor.create"))}</button></form></details>`:""}</article>`).join("")}`:`<p>${escapeHtml(t("brief.empty"))}</p>`;
}
async function loadSnapshots(publicationId){
  const snapshots=await api(`/v1/publications/${publicationId}/performance-snapshots`);
  const target=$(`[data-snapshot-list="${publicationId}"]`);
  if(target)target.innerHTML=snapshots.map(row=>`<p class="source-meta"><span>${escapeHtml(HeyuI18n.formatDate(row.captured_at))}</span><span>${escapeHtml(t("metric.views"))} ${row.views??"-"}</span><span>${escapeHtml(t("metric.likes"))} ${row.likes??"-"}</span><span>${escapeHtml(t("metric.comments"))} ${row.comments??"-"}</span><span>${escapeHtml(t("metric.shares"))} ${row.shares??"-"}</span><span>${escapeHtml(t("metric.saves"))} ${row.saves??"-"}</span><span>${escapeHtml(t("metric.orders"))} ${row.orders??"-"}</span></p>`).join("")||`<p>${escapeHtml(t("snapshot.empty"))}</p>`;
}
function renderMembers(){
  if(!state.actor)return;
  const allowOwner=state.actor.role==="owner";
  $(".role-select").innerHTML=roleOptions("creator",allowOwner);
  $("#member-count").textContent=t("member.count",{count:HeyuI18n.formatNumber(state.members.length)});
  $("#member-list").innerHTML=state.members.map(member=>`<article class="member-row"><div><h3>${escapeHtml(member.display_name)}${member.user_id===state.actor.user_id?` <span class="badge approved">${escapeHtml(t("member.currentAccount"))}</span>`:""}</h3><p>${escapeHtml(member.email)}</p></div><label>${escapeHtml(t("member.roleLabel"))}<select data-member-role="${member.membership_id}" ${member.user_id===state.actor.user_id&&member.role==="owner"?"disabled":""}>${roleOptions(member.role,allowOwner)}</select></label></article>`).join("")||t("member.empty");
  const now=Date.now();
  $("#invitation-count").textContent=t("invitation.count",{count:HeyuI18n.formatNumber(state.invitations.length)});
  $("#invitation-list").innerHTML=state.invitations.map(invitation=>{
    const expired=new Date(invitation.expires_at).getTime()<=now;
    const status=invitation.accepted_at?"accepted":invitation.revoked_at?"revoked":expired?"expired":"pending";
    return `<article class="invitation-row"><div><h3>${escapeHtml(invitation.email)}</h3><p>${escapeHtml(roleLabel(invitation.role))} · ${escapeHtml(t("invitation.expires",{date:HeyuI18n.formatDate(invitation.expires_at)}))}</p></div><div class="invitation-actions"><span class="badge ${status==="accepted"?"approved":status==="pending"?"pending_review":"rejected"}">${escapeHtml(t(`invitation.status.${status}`))}</span>${status==="pending"?`<button class="reject" data-revoke-invitation="${invitation.id}">${escapeHtml(t("invitation.revoke"))}</button>`:""}</div></article>`;
  }).join("")||t("invitation.empty");
}
function renderFocus(approvedKnowledge,pendingKnowledge){
  let prefix="focus.initial",target="assets",variables={};
  if(state.brands.length&&!state.products.length)prefix="focus.brandReady";
  else if(state.products.length&&!state.knowledge.length){prefix="focus.productReady";target="knowledge"}
  else if(pendingKnowledge){prefix="focus.pendingSources";target="knowledge";variables={count:HeyuI18n.formatNumber(pendingKnowledge)}}
  else if(approvedKnowledge&&!state.projects.length){prefix="focus.sourcesReady";target="studio"}
  else if(state.projects.length){prefix="focus.projects";target="studio";variables={count:HeyuI18n.formatNumber(state.projects.length)}}
  const focus={status:t(`${prefix}.status`,variables),detail:t(`${prefix}.detail`,variables),title:t(`${prefix}.title`,variables),copy:t(`${prefix}.copy`,variables),label:t(`${prefix}.action`,variables),target};
  $("#focus-status").textContent=focus.status;$("#focus-detail").textContent=focus.detail;
  $("#next-action-title").textContent=focus.title;$("#next-action-copy").textContent=focus.copy;
  const button=$("#next-action-button");button.dataset.target=focus.target;button.innerHTML=`${escapeHtml(focus.label)} <b>→</b>`;
}

$("#bootstrap-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const result=await api("/v1/auth/bootstrap",{method:"POST",body:JSON.stringify(data)});state.token=result.access_token;localStorage.setItem("heyu_token",state.token);showWorkspace()},t("toast.workspace.created"))});
$("#login-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const result=await api("/v1/auth/login",{method:"POST",body:JSON.stringify(formData(event.target))});state.token=result.access_token;localStorage.setItem("heyu_token",state.token);showWorkspace()},t("toast.workspace.signedIn"))});
$("#invite-accept-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const result=await api("/v1/invitations/accept",{method:"POST",body:JSON.stringify(formData(event.target))});state.inviteToken="";event.target.elements.token.value="";state.token=result.access_token;localStorage.setItem("heyu_token",state.token);history.replaceState({page:"overview"},"","/workspace/");showWorkspace()},t("toast.invite.accepted"))});
const resetBrandForm=()=>{const form=$("#brand-form");form.reset();$("#brand-form-title").textContent=t("form.brand.new");$("#brand-save-button").textContent=t("asset.saveBrand");$("#brand-edit-cancel").hidden=true};
const resetProductForm=()=>{const form=$("#product-form");form.reset();$("#product-form-title").textContent=t("form.product.new");$("#product-save-button").textContent=t("asset.saveProduct");$("#product-edit-cancel").hidden=true};
$("#brand-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;await api(id?`/v1/brands/${id}`:"/v1/brands",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetBrandForm();await refresh()},t("toast.brand.saved"))});
$("#product-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;data.selling_points=lines(data.selling_points);data.prohibited_claims=lines(data.prohibited_claims);await api(id?`/v1/products/${id}`:"/v1/products",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetProductForm();await refresh()},t("toast.product.saved"))});
$("#campaign-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const data=formData(event.target);
  data.create_default_items=true;
  await api("/v1/campaign-packages",{method:"POST",body:JSON.stringify(data)});
  event.target.reset();await refresh();
},t("campaign.created"))});
$("#campaign-brief-campaign-select").addEventListener("change",event=>{
  activeCampaignBriefFormId=event.target.value||null;
  populateCampaignBriefForm(campaignBriefCampaign());
  request(()=>loadCampaignBriefRevisions(event.target.value));
});
$("#campaign-brief-add-claim").addEventListener("click",()=>addCampaignBriefClaim());
$("#campaign-brief-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const campaignId=$("#campaign-brief-campaign-select").value;
  if(!campaignId)throw new Error(t("campaignBrief.selectCampaign"));
  const data=formData(event.target);
  const claims=[...$("#campaign-brief-claims").querySelectorAll(".claim-row")].map(row=>{
    const value=name=>row.querySelector(`[data-claim-field="${name}"]`).value.trim();
    const sourceType=value("source_type");
    const sourceId=value("source_id");
    if(!sourceId)throw new Error(t("campaignBrief.evidenceRequired"));
    return{claim_text:value("claim_text"),claim_type:value("claim_type"),evidence_refs:[{source_type:sourceType,source_id:sourceId,evidence_key:sourceType==="knowledge_source"?"content":value("evidence_key")}]};
  });
  const channelConstraints={};
  if(data.hook_seconds)channelConstraints.hook_seconds=Number(data.hook_seconds);
  if(data.max_duration_seconds)channelConstraints.max_duration_seconds=Number(data.max_duration_seconds);
  delete data.hook_seconds;delete data.max_duration_seconds;
  data.proof_points=claims.map(item=>item.claim_text);
  data.claim_evidence=claims;
  data.mandatory_messages=lines(data.mandatory_messages);
  data.prohibited_messages=lines(data.prohibited_messages);
  data.channel_constraints=channelConstraints;
  await api(`/v1/campaign-packages/${campaignId}/brief-revisions`,{method:"POST",body:JSON.stringify(data)});
  await refresh();
  $("#campaign-brief-campaign-select").value=campaignId;
  populateCampaignBriefForm(campaignBriefCampaign());
  await loadCampaignBriefRevisions(campaignId);
},t("campaignBrief.saved"))});
$("#supply-campaign-select").addEventListener("change",event=>{renderSupplyEvidence();request(()=>loadSupplySnapshots(event.target.value))});
$("#supply-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const campaignId=$("#supply-campaign-select").value;if(!campaignId)throw new Error(t("supply.selectCampaign"));
  const data=formData(event.target);const amount=Number(data.price_amount);if(!Number.isFinite(amount)||amount<0)throw new Error(t("supply.invalidAmount"));
  delete data.price_amount;data.price_minor=Math.round((amount+Number.EPSILON)*100);data.available_quantity=Number(data.available_quantity);data.ship_within_hours=Number(data.ship_within_hours);data.shipping_regions=lines(data.shipping_regions);data.evidence_source_ids=[...event.target.querySelectorAll('[name="evidence_source_ids"]:checked')].map(item=>item.value);
  if(!data.evidence_source_ids.length)throw new Error(t("supply.evidenceRequired"));["price_valid_until","inventory_confirmed_at","active_from","active_until"].forEach(key=>{data[key]=toIso(data[key])});data.harvest_date=data.harvest_date||null;
  await api(`/v1/campaign-packages/${campaignId}/supply-snapshots`,{method:"POST",body:JSON.stringify(data)});event.target.reset();await refresh();$("#supply-campaign-select").value=campaignId;renderSupplyEvidence();await loadSupplySnapshots(campaignId);
},t("supply.created"))});
$("#farmer-evidence-campaign-select").addEventListener("change",event=>{renderFarmerEvidenceSources();request(()=>loadFarmerEvidenceSnapshots(event.target.value))});
$("#farmer-evidence-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const campaignId=$("#farmer-evidence-campaign-select").value;if(!campaignId)throw new Error(t("farmerEvidence.selectCampaign"));
  const data=formData(event.target);
  data.allowed_claims=[...event.target.querySelectorAll('[name="allowed_claims"]:checked')].map(item=>item.value);
  data.prohibited_claims=[...event.target.querySelectorAll('[name="prohibited_claims"]:checked')].map(item=>item.value);
  data.consent_scope=[...event.target.querySelectorAll('[name="consent_scope"]:checked')].map(item=>item.value);
  data.evidence_source_ids=[...event.target.querySelectorAll('[name="evidence_source_ids"]:checked')].map(item=>item.value);
  if(!data.allowed_claims.length)throw new Error(t("farmerEvidence.allowedRequired"));
  if(data.allowed_claims.some(value=>data.prohibited_claims.includes(value)))throw new Error(t("farmerEvidence.claimConflict"));
  if(!data.evidence_source_ids.length)throw new Error(t("farmerEvidence.evidenceRequired"));
  ["active_from","active_until"].forEach(key=>{data[key]=toIso(data[key])});
  await api(`/v1/campaign-packages/${campaignId}/farmer-evidence-snapshots`,{method:"POST",body:JSON.stringify(data)});
  event.target.reset();await refresh();$("#farmer-evidence-campaign-select").value=campaignId;renderFarmerClaimChoices();renderFarmerEvidenceSources();await loadFarmerEvidenceSnapshots(campaignId);
},t("farmerEvidence.created"))});
$("#brand-edit-cancel").addEventListener("click",resetBrandForm);
$("#product-edit-cancel").addEventListener("click",resetProductForm);
const resetKnowledgeForm=()=>{const form=$("#knowledge-form");form.reset();form.elements.media_type.value="text/plain";$("#knowledge-file-status").textContent=t("sourceImport.idle");$("#knowledge-change-field").hidden=true;$("#knowledge-revision-cancel").hidden=true;$("#knowledge-save-button").textContent=t("source.saveDraft")};
$("#knowledge-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const parentId=data.parent_source_id;delete data.parent_source_id;data.brand_id=data.brand_id||null;data.product_id=data.product_id||null;if(parentId){if(!data.change_summary.trim())throw new Error(t("source.changeSummaryRequired"));await api(`/v1/knowledge/${parentId}/revisions`,{method:"POST",body:JSON.stringify(data)})}else{delete data.change_summary;await api("/v1/knowledge",{method:"POST",body:JSON.stringify(data)})}resetKnowledgeForm();await refresh()},t("toast.source.saved"))});
$("#knowledge-revision-cancel").addEventListener("click",resetKnowledgeForm);
$("#knowledge-file").addEventListener("change",async event=>{
  const file=event.target.files[0];
  const form=$("#knowledge-form");
  const status=$("#knowledge-file-status");
  if(!file){status.textContent=t("sourceImport.idle");return}
  const extension=file.name.split(".").pop().toLowerCase();
  const localTextTypes=["txt","md","markdown","csv"];
  const documentTypes=["pdf","pptx"];
  if(![...localTextTypes,...documentTypes].includes(extension)){event.target.value="";toast(t("sourceImport.unsupportedType"),true);return}
  const sizeLimit=documentTypes.includes(extension)?15*1024*1024:1024*1024;
  if(file.size>sizeLimit){event.target.value="";toast(t(documentTypes.includes(extension)?"sourceImport.documentTooLarge":"sourceImport.fileTooLarge"),true);return}
  status.textContent=t(documentTypes.includes(extension)?"sourceImport.extracting":"sourceImport.reading");
  try{
    let content="";
    let mediaType=knowledgeMediaType(file);
    let sectionCount=0;
    let warnings=[];
    if(localTextTypes.includes(extension)){
      content=await file.text();
    }else{
      const body=new FormData();
      body.append("file",file);
      const preview=await api("/v1/document-imports/preview",{method:"POST",body});
      content=preview.text;
      mediaType=preview.media_type;
      sectionCount=preview.sections.length;
      warnings=preview.warnings||[];
    }
    if(!content.trim())throw new Error(t("sourceImport.emptyFile"));
    if(!form.elements.title.value)form.elements.title.value=fileBaseName(file.name);
    form.elements.content.value=content;
    form.elements.source_filename.value=file.name;
    form.elements.media_type.value=mediaType;
    if(!form.elements.citation_label.value)form.elements.citation_label.value=fileBaseName(file.name);
    status.textContent=documentTypes.includes(extension)
      ?t("sourceImport.extractSuccess",{filename:file.name,count:sectionCount,warnings:warnings.length})
      :t("sourceImport.readSuccess",{filename:file.name,size:(file.size/1024).toFixed(1)});
    if(warnings.length)toast(t("sourceImport.extractWarnings",{count:warnings.length}),true);
  }catch(error){
    event.target.value="";
    status.textContent=t("sourceImport.readFailed");
    toast(error.message||t("sourceImport.unreadable"),true);
  }
});
const resetProjectForm=()=>{const form=$("#project-form");form.reset();form.elements.platform.value=t("form.project.defaultPlatform");form.elements.tone.value=t("form.project.defaultTone");$("#project-form-title").textContent=t("form.project.new");$("#project-save-button").textContent=t("content.saveProject");$("#project-edit-cancel").hidden=true};
$("#project-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;await api(id?`/v1/content-projects/${id}`:"/v1/content-projects",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetProjectForm();await refresh()},t("toast.project.saved"))});
$("#project-edit-cancel").addEventListener("click",resetProjectForm);
$("#member-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);data.expires_in_hours=Number(data.expires_in_hours);const invite=await api("/v1/invitations",{method:"POST",body:JSON.stringify(data)});const link=`${location.origin}/workspace/#invite=${encodeURIComponent(invite.token)}`;$("#invite-link").value=link;$("#invite-result").hidden=false;event.target.reset();state.invitations=await api("/v1/invitations");renderMembers()},t("toast.member.invited"))});
$("#copy-invite-link").addEventListener("click",()=>request(async()=>{await navigator.clipboard.writeText($("#invite-link").value)},t("invite.copied")));
document.addEventListener("click",event=>{const button=event.target.closest("[data-revoke-invitation]");if(!button)return;request(async()=>{if(!confirm(t("invitation.revokeConfirm")))return;await api(`/v1/invitations/${button.dataset.revokeInvitation}/revoke`,{method:"POST"});state.invitations=await api("/v1/invitations");renderMembers()},t("toast.invitation.revoked"))});
$("#generate-button").addEventListener("click",()=>request(async()=>{
  const id=$("#project-select").value;
  if(!id)throw new Error(t("generation.selectProjectFirst"));
  let result;
  try{
    result=await api(`/v1/content-projects/${id}/generate`,{method:"POST"});
  }catch(error){
    await loadGenerationRuns(id);
    throw error;
  }
  state.currentVersion=result.version;
  const content=JSON.stringify(result.version.content,null,2);
  renderGenerationResult(result.version.content);
  $("#version-editor").value=content;
  $("#edit-version").hidden=false;
  let provenance=$("#generation-provenance");
  if(!provenance){
    provenance=document.createElement("div");
    provenance.id="generation-provenance";
    provenance.className="provenance";
    $("#content-toolbar").before(provenance);
  }
  provenance.innerHTML=`<span>${escapeHtml(t("generation.provider"))}: ${escapeHtml(result.provider)}</span><span>${escapeHtml(t("generation.model"))}: ${escapeHtml(result.model)}</span><span>${escapeHtml(t("generation.prompt"))}: ${escapeHtml(result.prompt_name)} v${escapeHtml(result.prompt_version)}</span><span>${escapeHtml(t("generation.sources"))}: ${HeyuI18n.formatNumber(result.source_ids.length)}</span><span>${escapeHtml(t("generation.latency",{milliseconds:HeyuI18n.formatNumber(result.latency_ms)}))}</span>`;
  state.versions=await api(`/v1/content-projects/${id}/versions`);
  state.audit=await api("/v1/audit-events");
  await loadGenerationRuns(id);
  renderReviews(id);
},t("toast.generation.completed")));
$("#save-version-button").addEventListener("click",()=>request(async()=>{if(!state.currentVersion)throw new Error(t("content.generateFirst"));let content;try{content=JSON.parse($("#version-editor").value)}catch{throw new Error(t("content.invalidJson"))}const projectId=state.currentVersion.project_id;const version=await api(`/v1/content-projects/${projectId}/versions`,{method:"POST",body:JSON.stringify({parent_version_id:state.currentVersion.id,content,change_summary:$("#change-summary").value})});state.currentVersion=version;renderGenerationResult(version.content);state.versions=await api(`/v1/content-projects/${projectId}/versions`);renderReviews(projectId)},t("toast.contentVersion.saved")));
$$("[data-result-mode]").forEach(button=>button.addEventListener("click",()=>{$$("[data-result-mode]").forEach(item=>item.classList.toggle("active",item===button));const preview=button.dataset.resultMode==="preview";$("#generation-preview").hidden=!preview;$("#generation-output").hidden=preview}));
$("#copy-content").addEventListener("click",()=>request(async()=>{if(!resultContent())throw new Error(t("content.generateFirst"));await navigator.clipboard.writeText(resultText())},t("content.copied")));
$("#download-content").addEventListener("click",()=>request(async()=>{if(!resultContent())throw new Error(t("content.generateFirst"));downloadResult(resultContent(),"txt")},t("content.downloaded")));
$("#download-json").addEventListener("click",()=>request(async()=>{if(!resultContent())throw new Error(t("content.generateFirst"));downloadResult(resultContent(),"json")},t("content.jsonDownloaded")));
$("#review-project-select").addEventListener("change",event=>request(()=>renderReviews(event.target.value)));
$("#project-select").addEventListener("change",event=>request(async()=>{
  resetGenerationWorkspace();
  await loadGenerationRuns(event.target.value);
}));
$("#publication-project-select").addEventListener("change",event=>request(async()=>{
  const select=$("#publication-version-select");
  if(!event.target.value){select.innerHTML=`<option value="">${escapeHtml(t("publication.selectProjectFirst"))}</option>`;return}
  const versions=await api(`/v1/content-projects/${event.target.value}/versions`);
  const approved=versions.filter(item=>item.status==="approved");
  const publishable=approved.filter(item=>item.publishable);
  select.innerHTML=publishable.length?publishable.map(item=>`<option value="${item.id}">${escapeHtml(t("publication.versionOption",{number:item.version_number,summary:item.change_summary||t("publication.approvedContent")}))}</option>`).join(""):`<option value="">${escapeHtml(t(approved.length?"publication.noPublishableVersion":"publication.noApprovedVersion"))}</option>`;
  const blockers=$("#publication-blockers");
  if(blockers){
    const blocked=approved.filter(item=>!item.publishable);
    blockers.hidden=!blocked.length;
    blockers.innerHTML=blocked.length?`<strong>${escapeHtml(t("publication.blockedHeading"))}</strong><ul>${blocked.map(item=>`<li>${escapeHtml(t("publication.blockedVersion",{number:item.version_number,reasons:(item.publication_blockers||[]).map(reason=>t(`contentFreshness.${reason}`)).join(fieldSeparator())}))}</li>`).join("")}</ul>`:"";
  }
}));
$("#publication-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const data=formData(event.target);
  data.published_at=new Date(data.published_at).toISOString();
  await api("/v1/publications",{method:"POST",body:JSON.stringify(data)});
  event.target.reset();
  await refresh();
},t("toast.publication.saved"))});
$("#operation-import-file").addEventListener("change",event=>{
  state.operationImportFile=event.target.files[0]||null;
  state.operationImportPreview=null;
  renderOperationCopy();
  renderOperationImportPreview();
});
$("#operation-field-mapping").addEventListener("input",()=>{
  state.operationImportPreview=null;
  renderOperationImportPreview();
});
$("#operation-import-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const button=$("#operation-preview-button");
  button.disabled=true;
  button.textContent=operationText("import.previewing");
  try{
    state.operationImportFile=$("#operation-import-file").files[0]||state.operationImportFile;
    state.operationImportPreview=await api("/v1/operation-imports/preview",{method:"POST",body:operationImportFormData()});
    renderOperationImportPreview();
  }finally{
    button.disabled=false;
    button.textContent=operationText("import.preview");
  }
})});
$("#operation-confirm-button").addEventListener("click",()=>request(async()=>{
  if(!state.operationImportPreview)throw new Error(operationText("import.previewRequired"));
  const button=$("#operation-confirm-button");
  button.disabled=true;
  button.textContent=operationText("import.importing");
  try{
    const batch=await api("/v1/operation-imports",{method:"POST",body:operationImportFormData()});
    $("#operation-import-form").reset();
    state.operationImportFile=null;
    state.operationImportPreview=null;
    await refresh();
    toast(operationText("import.completed",{imported:HeyuI18n.formatNumber(batch.imported_rows),duplicates:HeyuI18n.formatNumber(batch.duplicate_rows)}));
  }finally{
    button.textContent=operationText("import.confirm");
    if(state.operationImportPreview)button.disabled=state.operationImportPreview.matched_rows===0;
  }
}));
$$("[data-auth-mode]").forEach(button=>button.addEventListener("click",()=>{$$("[data-auth-mode]").forEach(x=>x.classList.toggle("active",x===button));$$("[data-auth-panel]").forEach(panel=>panel.hidden=panel.dataset.authPanel!==button.dataset.authMode)}));
document.addEventListener("click",event=>{
  const remove=event.target.closest("[data-remove-brief-claim]");
  if(remove){
    const rows=$("#campaign-brief-claims").querySelectorAll(".claim-row");
    if(rows.length===1){toast(t("campaignBrief.claimRequired"),true);return}
    remove.closest(".claim-row").remove();
  }
  const open=event.target.closest("[data-open-campaign-brief]");
  if(open){
    $("#campaign-brief-campaign-select").value=open.dataset.openCampaignBrief;
    activeCampaignBriefFormId=open.dataset.openCampaignBrief;
    populateCampaignBriefForm(campaignBriefCampaign());
    request(()=>loadCampaignBriefRevisions(open.dataset.openCampaignBrief));
    $(".brief-workbench").scrollIntoView({behavior:"smooth",block:"start"});
  }
  const submit=event.target.closest("[data-submit-campaign-brief]");
  if(submit)request(async()=>{await api(`/v1/campaign-packages/${submit.dataset.campaign}/brief-revisions/${submit.dataset.submitCampaignBrief}/submit`,{method:"POST"});await refresh();$("#campaign-brief-campaign-select").value=submit.dataset.campaign;await loadCampaignBriefRevisions(submit.dataset.campaign)},t("campaignBrief.submitted"));
  const review=event.target.closest("[data-review-campaign-brief]");
  if(review){
    const rejected=review.dataset.status==="rejected";
    const note=prompt(t(rejected?"campaignBrief.rejectPrompt":"campaignBrief.reviewPrompt"),"");
    if(note!==null){
      if(rejected&&!note.trim()){toast(t("campaignBrief.rejectionNoteRequired"),true);return}
      request(async()=>{await api(`/v1/campaign-packages/${review.dataset.campaign}/brief-revisions/${review.dataset.reviewCampaignBrief}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status,note})});await refresh();$("#campaign-brief-campaign-select").value=review.dataset.campaign;await loadCampaignBriefRevisions(review.dataset.campaign)},t("campaignBrief.reviewed"));
    }
  }
});
document.addEventListener("change",event=>{
  const sourceType=event.target.closest('[data-claim-field="source_type"]');
  if(sourceType)refreshClaimRow(sourceType.closest(".claim-row"));
});
document.addEventListener("click",event=>{
  const button=event.target.closest("[data-download-campaign-pptx]");
  if(!button)return;
  const campaign=state.campaigns.find(item=>item.id===button.dataset.downloadCampaignPptx);
  if(!campaign)return;
  request(async()=>{
    button.disabled=true;
    button.textContent=t("campaign.presentation.downloading");
    try{
      await downloadCampaignPresentation(campaign);
    }finally{
      button.disabled=false;
      button.textContent=t("campaign.presentation.download");
    }
  },t("campaign.presentation.downloaded"));
});
document.addEventListener("click",event=>{
  const submit=event.target.closest("[data-submit-supply]");
  if(submit)request(async()=>{await api(`/v1/campaign-packages/${submit.dataset.campaign}/supply-snapshots/${submit.dataset.submitSupply}/submit`,{method:"POST"});await refresh();$("#supply-campaign-select").value=submit.dataset.campaign;await loadSupplySnapshots(submit.dataset.campaign)},t("supply.submitted"));
  const review=event.target.closest("[data-review-supply]");
  if(review){const rejected=review.dataset.status==="rejected";const note=prompt(t(rejected?"supply.rejectPrompt":"supply.reviewPrompt"),"");if(note!==null){if(rejected&&!note.trim()){toast(t("supply.rejectionNoteRequired"),true);return}request(async()=>{await api(`/v1/campaign-packages/${review.dataset.campaign}/supply-snapshots/${review.dataset.reviewSupply}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status,note})});await refresh();$("#supply-campaign-select").value=review.dataset.campaign;await loadSupplySnapshots(review.dataset.campaign)},t("supply.reviewed"))}}
  const farmerSubmit=event.target.closest("[data-submit-farmer-evidence]");
  if(farmerSubmit)request(async()=>{await api(`/v1/campaign-packages/${farmerSubmit.dataset.campaign}/farmer-evidence-snapshots/${farmerSubmit.dataset.submitFarmerEvidence}/submit`,{method:"POST"});await refresh();$("#farmer-evidence-campaign-select").value=farmerSubmit.dataset.campaign;await loadFarmerEvidenceSnapshots(farmerSubmit.dataset.campaign)},t("farmerEvidence.submitted"));
  const farmerReview=event.target.closest("[data-review-farmer-evidence]");
  if(farmerReview){const rejected=farmerReview.dataset.status==="rejected";const note=prompt(t(rejected?"farmerEvidence.rejectPrompt":"farmerEvidence.reviewPrompt"),"");if(note!==null){if(rejected&&!note.trim()){toast(t("farmerEvidence.rejectionNoteRequired"),true);return}request(async()=>{await api(`/v1/campaign-packages/${farmerReview.dataset.campaign}/farmer-evidence-snapshots/${farmerReview.dataset.reviewFarmerEvidence}/review`,{method:"POST",body:JSON.stringify({status:farmerReview.dataset.status,note})});await refresh();$("#farmer-evidence-campaign-select").value=farmerReview.dataset.campaign;await loadFarmerEvidenceSnapshots(farmerReview.dataset.campaign)},t("farmerEvidence.reviewed"))}}
});
document.addEventListener("click",event=>{const nav=event.target.closest("[data-page]");if(nav)navigate(nav.dataset.page);const jump=event.target.closest("[data-target]");if(jump)navigate(jump.dataset.target);const campaignGenerate=event.target.closest("[data-generate-campaign-item]");if(campaignGenerate)request(async()=>{await api(`/v1/content-projects/${campaignGenerate.dataset.generateCampaignItem}/generate`,{method:"POST"});await refresh()},t("campaign.generated"));const editProject=event.target.closest("[data-edit-project]");if(editProject){const project=state.projects.find(item=>item.id===editProject.dataset.editProject);const form=$("#project-form");["id","title","brand_id","product_id","content_type","platform","tone","target_audience","objective","extra_requirements"].forEach(name=>form.elements[name].value=project[name]||"");$("#project-form-title").textContent=t("form.project.edit");$("#project-save-button").textContent=t("form.project.saveChanges");$("#project-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editBrand=event.target.closest("[data-edit-brand]");if(editBrand){const brand=state.brands.find(item=>item.id===editBrand.dataset.editBrand);const form=$("#brand-form");["id","name","story","voice"].forEach(name=>form.elements[name].value=brand[name]||"");$("#brand-form-title").textContent=t("form.brand.edit");$("#brand-save-button").textContent=t("form.brand.saveChanges");$("#brand-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editProduct=event.target.closest("[data-edit-product]");if(editProduct){const product=state.products.find(item=>item.id===editProduct.dataset.editProduct);const form=$("#product-form");["id","brand_id","name","origin","specification","price_display","shelf_life","storage_method"].forEach(name=>form.elements[name].value=product[name]||"");form.elements.selling_points.value=(product.selling_points||[]).join("\n");form.elements.prohibited_claims.value=(product.prohibited_claims||[]).join("\n");$("#product-form-title").textContent=t("form.product.edit");$("#product-save-button").textContent=t("form.product.saveChanges");$("#product-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const assetSubmit=event.target.closest("[data-submit-asset]");if(assetSubmit)request(async()=>{await api(`/v1/${assetSubmit.dataset.assetType}/${assetSubmit.dataset.submitAsset}/submit`,{method:"POST"});await refresh()},t("toast.asset.submitted"));const assetReview=event.target.closest("[data-review-asset]");if(assetReview){const note=prompt(t(assetReview.dataset.status==="rejected"?"asset.rejectPrompt":"asset.reviewPrompt"),"");if(note!==null)request(async()=>{await api(`/v1/${assetReview.dataset.assetType}/${assetReview.dataset.reviewAsset}/review`,{method:"POST",body:JSON.stringify({status:assetReview.dataset.status,note})});await refresh()},t("toast.asset.reviewUpdated"))}const revise=event.target.closest("[data-revise-source]");if(revise){const source=state.knowledge.find(item=>item.id===revise.dataset.reviseSource);const form=$("#knowledge-form");["title","kind","content","citation_label","source_filename","media_type","brand_id","product_id"].forEach(name=>{if(form.elements[name])form.elements[name].value=source[name]||""});form.elements.parent_source_id.value=source.id;$("#knowledge-change-field").hidden=false;$("#knowledge-revision-cancel").hidden=false;$("#knowledge-save-button").textContent=t("source.saveRevisionDraft",{number:(source.revision_number||1)+1});form.elements.change_summary.focus();form.scrollIntoView({behavior:"smooth",block:"start"})}const sourceSubmit=event.target.closest("[data-submit-source]");if(sourceSubmit)request(async()=>{await api(`/v1/knowledge/${sourceSubmit.dataset.submitSource}/submit`,{method:"POST"});await refresh()},t("toast.source.submitted"));const review=event.target.closest("[data-review-source]");if(review){const note=prompt(t(review.dataset.status==="rejected"?"source.rejectPrompt":"source.reviewPrompt"),"");if(note!==null)request(async()=>{await api(`/v1/knowledge/${review.dataset.reviewSource}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status,note})});await refresh()},t("toast.source.reviewUpdated"))};const submit=event.target.closest("[data-submit-version]");if(submit)request(async()=>{await api(`/v1/content-projects/${submit.dataset.project}/versions/${submit.dataset.submitVersion}/submit`,{method:"POST"});state.versions=await api(`/v1/content-projects/${submit.dataset.project}/versions`);renderReviews(submit.dataset.project)},t("toast.contentReview.submitted"));const versionReview=event.target.closest("[data-review-version]");if(versionReview){const noteField=document.querySelector(`[data-review-note="${versionReview.dataset.reviewVersion}"]`);const note=(noteField?.value||"").trim();if(versionReview.dataset.status==="rejected"&&!note){toast(t("contentReview.rejectionNoteRequired"),true);noteField?.focus();return}request(async()=>{await api(`/v1/content-projects/${versionReview.dataset.project}/versions/${versionReview.dataset.reviewVersion}/review`,{method:"POST",body:JSON.stringify({status:versionReview.dataset.status,note})});state.versions=await api(`/v1/content-projects/${versionReview.dataset.project}/versions`);renderReviews(versionReview.dataset.project)},t("toast.contentReview.updated"))}});
document.addEventListener("input",event=>{const field=event.target.closest("[data-review-note]");if(field){const counter=document.querySelector(`[data-review-count="${field.dataset.reviewNote}"]`);if(counter)counter.textContent=field.value.length}});
document.addEventListener("change",event=>{const select=event.target.closest("[data-member-role]");if(select)request(async()=>{await api(`/v1/members/${select.dataset.memberRole}`,{method:"PATCH",body:JSON.stringify({role:select.value})});await refresh()},t("toast.member.roleUpdated"))});
document.addEventListener("click",event=>{
  const generate=event.target.closest("[data-generate-performance-review]");
  if(generate)request(async()=>{
    const publicationId=generate.dataset.generatePerformanceReview;
    generate.disabled=true;
    generate.textContent=operationText("review.generating");
    try{
      state.performanceReviews[publicationId]=await api(`/v1/publications/${publicationId}/performance-reviews`,{method:"POST"});
      const target=$(`[data-performance-review="${publicationId}"]`);
      if(target)target.innerHTML=performanceReviewHtml(publicationId,state.performanceReviews[publicationId]);
    }finally{
      generate.disabled=false;
      generate.textContent=operationText("review.generate");
    }
  },operationText("review.generated"));
  const saveBrief=event.target.closest("[data-save-performance-brief]");
  if(saveBrief)request(async()=>{
    const publicationId=saveBrief.dataset.savePerformanceBrief;
    const review=state.performanceReviews[publicationId];
    if(!review)throw new Error(operationText("review.needSnapshot"));
    saveBrief.disabled=true;
    saveBrief.textContent=operationText("review.savingBrief");
    try{
      const findings=review.recommendations.map(item=>({category:item.area,severity:"opportunity",evidence:review.summary,recommendation:item.action}));
      const diagnosis=await api(`/v1/publications/${publicationId}/video-diagnoses`,{method:"POST",body:JSON.stringify({observed_at:new Date().toISOString(),title:operationText("review.diagnosisTitle"),summary:review.summary,transcript_excerpt:"",findings})});
      await api(`/v1/publications/${publicationId}/improvement-briefs`,{method:"POST",body:JSON.stringify({video_diagnosis_id:diagnosis.id,title:operationText("review.briefTitle"),objective:operationText("review.briefObjective"),actions:review.recommendations.map(item=>({category:item.area,instruction:item.action,evidence:review.summary})),guardrails:review.limitations||[]})});
      await Promise.all([loadDiagnoses(publicationId),loadImprovementBriefs(publicationId)]);
      state.audit=await api("/v1/audit-events");
    }finally{
      saveBrief.disabled=false;
      saveBrief.textContent=operationText("review.saveBrief");
    }
  },operationText("review.savedBrief"));
  const createDraft=event.target.closest("[data-create-improvement-draft]");
  if(createDraft)request(async()=>{
    const publication=state.publications.find(item=>item.id===createDraft.dataset.publicationId);
    if(!publication)throw new Error(t("publication.empty"));
    createDraft.disabled=true;
    createDraft.textContent=operationText("brief.creatingDraft");
    try{
      const versions=await api(`/v1/content-projects/${publication.project_id}/versions`);
      const source=versions.find(item=>item.id===createDraft.dataset.sourceVersionId);
      if(!source)throw new Error(t("content.generateFirst"));
      const version=await api(`/v1/publications/${publication.id}/improvement-briefs/${createDraft.dataset.createImprovementDraft}/draft`,{method:"POST",body:JSON.stringify({content:source.content,change_summary:operationText("brief.changeSummary",{title:createDraft.dataset.briefTitle})})});
      state.currentVersion=version;
      state.audit=await api("/v1/audit-events");
    }finally{
      createDraft.disabled=false;
      createDraft.textContent=operationText("brief.oneClickDraft");
    }
  },operationText("brief.draftCreated"));
});
document.addEventListener("submit",event=>{const form=event.target.closest(".snapshot-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  data.captured_at=new Date(data.captured_at).toISOString();
  ["views","likes","comments","shares","saves","followers_gained","orders","revenue_minor"].forEach(key=>{data[key]=data[key]===""?null:Number(data[key])});
  data.currency="CNY";
  await api(`/v1/publications/${form.dataset.publicationId}/performance-snapshots`,{method:"POST",body:JSON.stringify(data)});
  form.reset();
  await loadSnapshots(form.dataset.publicationId);
},t("toast.snapshot.saved"))});
document.addEventListener("submit",event=>{const form=event.target.closest(".diagnosis-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  const payload={observed_at:new Date(data.observed_at).toISOString(),title:data.title,summary:data.summary,transcript_excerpt:data.transcript_excerpt,findings:[{category:data.category,severity:data.severity,evidence:data.evidence,recommendation:data.recommendation}]};
  await api(`/v1/publications/${form.dataset.publicationId}/video-diagnoses`,{method:"POST",body:JSON.stringify(payload)});
  form.reset();
  await loadDiagnoses(form.dataset.publicationId);
},t("toast.diagnosis.saved"))});
document.addEventListener("submit",event=>{const form=event.target.closest(".brief-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  const payload={video_diagnosis_id:form.dataset.diagnosisId,title:data.title,objective:data.objective,actions:[{category:data.category,instruction:data.instruction,evidence:data.evidence}],guardrails:lines(data.guardrails)};
  await api(`/v1/publications/${form.dataset.publicationId}/improvement-briefs`,{method:"POST",body:JSON.stringify(payload)});
  form.reset();
  await loadImprovementBriefs(form.dataset.publicationId);
  state.audit=await api("/v1/audit-events");
},t("toast.brief.saved"))});
document.addEventListener("submit",event=>{const form=event.target.closest(".improvement-draft-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);let content;try{content=JSON.parse(data.content)}catch{throw new Error(t("successor.invalidJson"))}
  const version=await api(`/v1/publications/${form.dataset.publicationId}/improvement-briefs/${form.dataset.briefId}/draft`,{method:"POST",body:JSON.stringify({content,change_summary:data.change_summary})});
  form.reset();
  state.currentVersion=version;
  state.audit=await api("/v1/audit-events");
},t("toast.successor.created"))});
async function renderReviews(selectedId){
  if(!selectedId&&state.projects.length)selectedId=state.projects[0].id;
  if(selectedId)state.versions=await api(`/v1/content-projects/${selectedId}/versions`);
  const canSubmit=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor.role);
  $("#review-list").innerHTML=state.versions.map(v=>{
    const readable=HeyuContent.renderContent(v.content,{t:HeyuI18n.t,locale:HeyuI18n.getLocale()});
    const actions=v.status==="draft"&&canSubmit
      ? `<div class="row-actions"><button class="approve" data-submit-version="${v.id}" data-project="${v.project_id}">${escapeHtml(t("contentReview.submit"))}</button></div>`
      : v.status==="pending_review"&&canReview
        ? `<div class="content-review-form"><label for="review-note-${v.id}">${escapeHtml(t("contentReview.note"))} <span>${escapeHtml(t("contentReview.noteHelp"))}</span></label><textarea id="review-note-${v.id}" data-review-note="${v.id}" maxlength="2000" rows="3" placeholder="${escapeHtml(t("contentReview.notePlaceholder"))}"></textarea><small><span data-review-count="${v.id}">0</span> / 2000</small><div class="row-actions"><button class="approve" data-review-version="${v.id}" data-project="${v.project_id}" data-status="approved">${escapeHtml(t("contentReview.approve"))}</button><button class="reject" data-review-version="${v.id}" data-project="${v.project_id}" data-status="rejected">${escapeHtml(t("contentReview.requestChanges"))}</button></div></div>`
        : "";
    return `<article class="content-review-card"><div class="panel-heading"><div><p class="eyebrow">VERSION ${v.version_number}</p><h3>${escapeHtml(v.change_summary||t("content.aiDraft"))}</h3></div><span class="badge ${v.status}">${escapeHtml(contentStatusLabel(v.status))}</span></div><div class="review-reading-copy">${escapeHtml(readable)}</div><details class="review-structured"><summary>${escapeHtml(t("contentReview.viewJson"))}</summary><pre>${escapeHtml(JSON.stringify(v.content,null,2))}</pre></details>${v.review_note?`<p class="review-note"><strong>${escapeHtml(t("contentReview.note"))}</strong>${escapeHtml(v.review_note)}</p>`:""}${actions}</article>`;
  }).join("")||escapeHtml(t("contentReview.empty"));
}
async function loadGenerationRuns(projectId){
  state.generationRuns=projectId?await api(`/v1/content-projects/${projectId}/generation-runs`):[];
  $("#generation-history-list").innerHTML=state.generationRuns.map(run=>{
    const manifest=run.normalized_input?.context_sources||[];
    const sourceEvidence=run.sources.map(source=>{
      const evidence=manifest.find(item=>item.source_id===source.id);
      const scope=t(`generation.scope.${evidence?.scope||"organization"}`);
      const length=evidence?t("generation.contextLength",{included:HeyuI18n.formatNumber(evidence.included_chars),total:HeyuI18n.formatNumber(evidence.source_chars)}):t("generation.cited");
      return `<li><div><strong>${escapeHtml(source.citation_label||source.title)}</strong><small>${escapeHtml(scope)} · ${escapeHtml(length)}</small></div><span class="context-flag${evidence?.truncated?"":" complete"}">${escapeHtml(t(evidence?.truncated?"generation.truncated":"generation.complete"))}</span></li>`;
    }).join("");
    const failed=run.status==="failed";
    const heading=failed?t("generation.failedRecord"):(run.output.format||t("content.generatedDraft"));
    const errorMessage=failed&&run.output?.error?.message?`<p class="muted">${escapeHtml(run.output.error.message)}</p>`:"";
    return `<article><div class="panel-heading"><div><h3>${escapeHtml(heading)}</h3><p>${escapeHtml(run.provider)} / ${escapeHtml(run.model)} · ${escapeHtml(run.prompt_name)} v${escapeHtml(run.prompt_version)}</p>${errorMessage}</div><span class="badge ${failed?"rejected":"approved"}">${escapeHtml(generationStatusLabel(run.status))}</span></div><div class="provenance"><span>${escapeHtml(t("generation.latency",{milliseconds:HeyuI18n.formatNumber(run.latency_ms)}))}</span><span>${escapeHtml(HeyuI18n.formatDate(run.created_at))}</span><span>${escapeHtml(t("generation.sourceCount",{count:HeyuI18n.formatNumber(run.sources.length)}))}</span></div>${sourceEvidence?`<div class="context-evidence"><div class="context-evidence-head"><strong>${escapeHtml(t("source.usedInGeneration"))}</strong><small>${escapeHtml(run.normalized_input?.context_policy||"legacy")} · ${escapeHtml(t("source.traceable"))}</small></div><ul>${sourceEvidence}</ul></div>`:""}<details><summary>${escapeHtml(t("generation.normalizedInput"))} · ${escapeHtml(t("generation.fullOutput"))}</summary><pre>${escapeHtml(JSON.stringify({input:run.normalized_input,output:run.output},null,2))}</pre></details></article>`;
  }).join("")||escapeHtml(t("generation.historyEmpty"));
}
$("#logout").addEventListener("click",()=>{localStorage.removeItem("heyu_token");state.token="";state.actor=null;location.href="/workspace/"});
$$(".jump").forEach(x=>x.addEventListener("click",()=>navigate(x.dataset.target)));
document.addEventListener("click",event=>{
  const planButton=event.target.closest("[data-open-marketing-plan]");
  if(planButton)request(()=>openMarketingPlan(planButton.dataset.openMarketingPlan));
  const versionButton=event.target.closest("[data-open-marketing-version]");
  if(versionButton&&state.currentMarketingPlan){
    state.selectedMarketingVersion=state.currentMarketingPlan.versions.find(item=>item.id===versionButton.dataset.openMarketingVersion)||state.currentMarketingPlan.current_version;
    renderMarketingPlans();
  }
});
$("#import-marketing-plan").addEventListener("click",()=>request(importPendingMarketingPlan));
$("#save-marketing-plan-version").addEventListener("click",()=>request(async()=>{
  if(!state.currentMarketingPlan)throw new Error(t("marketingPlans.selectFirst"));
  let content;
  try{content=JSON.parse($("#marketing-plan-editor").value)}catch{throw new Error(t("content.invalidJson"))}
  const base=marketingPlanVersion();
  const detail=await api(`/v1/marketing-plans/${state.currentMarketingPlan.id}/versions`,{method:"POST",body:JSON.stringify({request_payload:base.request_payload,content,change_summary:$("#marketing-plan-change-summary").value.trim()})});
  state.currentMarketingPlan=detail;
  state.selectedMarketingVersion=detail.current_version;
  state.marketingPlans=await api("/v1/marketing-plans");
  $("#marketing-plan-change-summary").value="";
  renderMarketingPlans();
},t("marketingPlans.versionSaved")));
$("#copy-marketing-plan").addEventListener("click",()=>request(async()=>{
  if(!state.currentMarketingPlan)throw new Error(t("marketingPlans.selectFirst"));
  const detail=await api(`/v1/marketing-plans/${state.currentMarketingPlan.id}/copy`,{method:"POST",body:JSON.stringify({title:`${state.currentMarketingPlan.title}${t("marketingPlans.copySuffix")}`})});
  state.marketingPlans=await api("/v1/marketing-plans");
  state.currentMarketingPlan=detail;
  state.selectedMarketingVersion=detail.current_version;
  history.pushState({page:"plans",plan:detail.id},"",`/workspace/plans?plan=${encodeURIComponent(detail.id)}`);
  renderMarketingPlans();
},t("marketingPlans.copied")));
window.addEventListener("popstate",()=>{
  navigate(pageFromLocation(),false);
  const planId=new URLSearchParams(location.search).get("plan");
  if(planId&&state.token)request(()=>openMarketingPlan(planId,false));
});
document.addEventListener("heyu:localechange",async()=>{
  const projectId=$("#project-select")?.value;
  navigate(pageFromLocation(),false);
  if(state.actor)render();
  if(projectId)$("#project-select").value=projectId;
  if(state.currentVersion)renderGenerationResult(state.currentVersion.content);
  if(projectId)await loadGenerationRuns(projectId);
});

showWorkspace();
showInvitation();

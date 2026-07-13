const state={token:localStorage.getItem("heyu_token")||"",actor:null,members:[],brands:[],products:[],knowledge:[],projects:[],versions:[],generationRuns:[],publications:[],audit:[],currentVersion:null};
const roleLabels={owner:"所有者",admin:"管理员",product_manager:"产品经理",creator:"内容创作者",reviewer:"审核员",viewer:"只读成员"};
const roleOptions=(selected="",allowOwner=true)=>Object.entries(roleLabels).filter(([role])=>allowOwner||role!=="owner").map(([role,label])=>`<option value="${role}"${role===selected?" selected":""}>${label}</option>`).join("");
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const api=async(path,options={})=>{const headers={"Content-Type":"application/json",...(options.headers||{})};if(state.token)headers.Authorization=`Bearer ${state.token}`;const response=await fetch(path,{...options,headers});if(!response.ok){let message=`请求失败 (${response.status})`;try{const body=await response.json();message=body.detail||message}catch{}throw new Error(message)}return response.status===204?null:response.json()};
const formData=form=>Object.fromEntries(new FormData(form));
const lines=value=>value.split("\n").map(v=>v.trim()).filter(Boolean);
const toast=(message,error=false)=>{const el=$("#toast");el.textContent=message;el.className=`show${error?" error":""}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className="",3000)};
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fileBaseName=name=>name.replace(/\.(txt|md|markdown|csv)$/i,"");
const knowledgeMediaType=file=>file.type||({txt:"text/plain",md:"text/markdown",markdown:"text/markdown",csv:"text/csv"}[file.name.split(".").pop().toLowerCase()]||"text/plain");
const request=async(fn,success)=>{try{await fn();if(success)toast(success)}catch(error){toast(error.message,true)}};
const workspacePages=["overview","assets","knowledge","studio","operations","review","audit","members"];
const pageFromLocation=()=>{const page=location.pathname.split("/").filter(Boolean)[1]||"overview";return workspacePages.includes(page)?page:"overview"};

function showWorkspace(){
  $("#auth-view").hidden=Boolean(state.token);$("#workspace").hidden=!state.token;$("#logout").hidden=!state.token;
  if(state.token){navigate(pageFromLocation(),false);refresh()}
}
function navigate(page,push=true){
  if(!workspacePages.includes(page))page="overview";
  $$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.page===page));
  $$(".page").forEach(x=>x.classList.toggle("active",x.dataset.pagePanel===page));
  const titles={overview:"经营概览",assets:"品牌与农产品",knowledge:"可信知识库",studio:"内容创作台",operations:"发布与运营",review:"审核与版本",audit:"审计记录",members:"团队与权限"};
  $("#page-title").textContent=titles[page];
  const path=page==="overview"?"/workspace/":`/workspace/${page}`;
  if(push&&location.pathname!==path)history.pushState({page},"",path);
}
async function refresh(){
  state.actor=await api("/v1/me");
  const canManageMembers=["owner","admin"].includes(state.actor.role);
  [state.brands,state.products,state.knowledge,state.projects,state.publications,state.audit]=await Promise.all([api("/v1/brands"),api("/v1/products"),api("/v1/knowledge"),api("/v1/content-projects"),api("/v1/publications"),api("/v1/audit-events")]);
  state.members=canManageMembers?await api("/v1/members"):[];
  $$(".member-nav").forEach(x=>x.hidden=!canManageMembers);
  if(!canManageMembers&&$(".nav.active")?.dataset.page==="members")navigate("overview");
  render();
}
function options(items,placeholder){
  return `<option value="">${placeholder}</option>`+items.map(x=>`<option value="${x.id}">${escapeHtml(x.name||x.title)}</option>`).join("");
}
function render(){
  const approvedKnowledge=state.knowledge.filter(x=>x.status==="approved").length;
  const pendingKnowledge=state.knowledge.filter(x=>x.status!=="approved").length;
  $("#brand-count").textContent=state.brands.length;$("#product-count").textContent=state.products.length;
  $("#knowledge-count").textContent=approvedKnowledge;$("#project-count").textContent=state.projects.length;
  renderFocus(approvedKnowledge,pendingKnowledge);
  $$(".brand-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.brands,"请选择品牌");x.value=value});
  $$(".product-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.products,"请选择产品");x.value=value});
  $("#project-select").innerHTML=options(state.projects,"请选择内容任务");
  const reviewSelect=$("#review-project-select");const reviewValue=reviewSelect.value;reviewSelect.innerHTML=options(state.projects,"请选择内容项目");reviewSelect.value=reviewValue;
  const publicationProject=$("#publication-project-select");const publicationProjectValue=publicationProject.value;publicationProject.innerHTML=options(state.projects,"请选择内容项目");publicationProject.value=publicationProjectValue;
  const canManageAssets=["owner","admin","product_manager"].includes(state.actor.role);
  $("#asset-list").innerHTML=[...state.brands.map(b=>`<article><span class="pill">品牌</span><h3>${escapeHtml(b.name)}</h3><p>${escapeHtml(b.story||"尚未填写品牌故事")}</p>${canManageAssets?`<div class="row-actions"><button data-edit-brand="${b.id}">编辑品牌</button></div>`:""}</article>`),...state.products.map(p=>`<article><span class="pill">农产品</span><h3>${escapeHtml(p.name)}</h3><p>${escapeHtml(p.origin||"产地待补充")} · ${escapeHtml(p.specification||"规格待补充")}</p>${canManageAssets?`<div class="row-actions"><button data-edit-product="${p.id}">编辑产品</button></div>`:""}</article>`)].join("")||"暂无品牌与产品";
  const canManageProjects=["owner","admin","creator","product_manager"].includes(state.actor.role);
  $("#project-list").innerHTML=state.projects.map(project=>`<article><span class="pill">${escapeHtml(project.content_type)}</span><h3>${escapeHtml(project.title)}</h3><p>${escapeHtml(project.platform||"通用平台")} · ${escapeHtml(project.target_audience||"受众待补充")}</p>${canManageProjects?`<div class="row-actions"><button data-edit-project="${project.id}">编辑任务</button></div>`:""}</article>`).join("")||"暂无内容任务";
  const canSubmitKnowledge=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReviewKnowledge=["owner","admin","reviewer"].includes(state.actor.role);
  $("#knowledge-list").innerHTML=state.knowledge.map(k=>`<article><h3>${escapeHtml(k.title)} <span class="badge">R${k.revision_number||1}</span></h3><p>${escapeHtml(k.content.slice(0,130))}</p><div class="source-meta">${k.source_filename?`<span>文件 ${escapeHtml(k.source_filename)}</span>`:"<span>手工录入</span>"}<span>${escapeHtml(k.media_type||"text/plain")}</span>${k.content_sha256?`<span title="${escapeHtml(k.content_sha256)}">SHA-256 ${escapeHtml(k.content_sha256.slice(0,12))}…</span>`:""}${k.citation_label?`<span>引用 ${escapeHtml(k.citation_label)}</span>`:""}${k.parent_source_id?`<span>源自 R${(k.revision_number||1)-1}</span>`:""}${k.change_summary?`<span>修订 ${escapeHtml(k.change_summary)}</span>`:""}${k.reviewed_by?`<span>审核人 ${escapeHtml(k.reviewed_by.slice(0,8))}</span>`:""}</div><span class="badge ${k.status}">${k.status}</span>${k.status==="draft"&&canSubmitKnowledge?`<div class="row-actions"><button class="approve" data-submit-source="${k.id}">提交审核</button></div>`:""}${["approved","rejected"].includes(k.status)&&canSubmitKnowledge?`<div class="row-actions"><button data-revise-source="${k.id}">创建修订版</button></div>`:""}${k.status==="pending_review"&&canReviewKnowledge?`<div class="row-actions"><button class="approve" data-review-source="${k.id}" data-status="approved">审核通过</button><button class="reject" data-review-source="${k.id}" data-status="rejected">驳回</button></div>`:""}</article>`).join("")||"暂无知识资料";
  $("#audit-list").innerHTML=state.audit.map(item=>`<article><h3>${escapeHtml(actionLabel(item.action))}</h3><p>${escapeHtml(item.entity_type)} · ${escapeHtml(item.entity_id)}</p><div class="audit-meta"><span>操作者 ${escapeHtml(item.actor_id.slice(0,8))}</span><span>${escapeHtml(JSON.stringify(item.details))}</span></div></article>`).join("")||"暂无审计记录";
  renderPublications();
  renderMembers();
}
const actionLabel=action=>({"membership.created":"创建团队成员","membership.role_changed":"调整成员角色","brand.created":"创建品牌","brand.updated":"更新品牌","product.created":"创建农产品","product.updated":"更新农产品","knowledge.created":"录入知识","knowledge.revised":"创建知识修订版","knowledge.submitted":"知识已提交审核","knowledge.approved":"知识审核通过","knowledge.rejected":"知识被驳回","content_project.created":"创建内容任务","content_project.updated":"更新内容任务","content.generated":"AI 生成内容","content_version.created":"创建内容版本","content_version.submitted":"内容已提交审核","content_version.approved":"内容审核通过","content_version.rejected":"内容被驳回","publication.created":"登记发布内容","performance_snapshot.created":"录入运营数据快照","video_diagnosis.created":"创建视频诊断报告","improvement_brief.created":"创建改进 Brief","improvement_brief.draft_created":"从改进 Brief 创建后继草稿"}[action]||action);
function renderPublications(){
  $("#publication-list").innerHTML=state.publications.map(item=>`<article><div class="panel-heading"><div><h3>${escapeHtml(item.platform)}</h3><p>${escapeHtml(new Date(item.published_at).toLocaleString())}</p></div><span class="badge approved">已发布</span></div>${item.external_url?`<p><a href="${escapeHtml(item.external_url)}" target="_blank" rel="noopener noreferrer">查看外部内容</a></p>`:""}<form class="snapshot-form" data-publication-id="${item.id}"><div class="source-meta"><label>采集时间<input name="captured_at" type="datetime-local" required></label><label>播放<input name="views" type="number" min="0"></label><label>点赞<input name="likes" type="number" min="0"></label><label>评论<input name="comments" type="number" min="0"></label><label>分享<input name="shares" type="number" min="0"></label><label>收藏<input name="saves" type="number" min="0"></label><label>新增粉丝<input name="followers_gained" type="number" min="0"></label><label>订单<input name="orders" type="number" min="0"></label><label>收入（分）<input name="revenue_minor" type="number" min="0"></label></div><button>添加数据快照</button></form><div class="snapshot-list" data-snapshot-list="${item.id}"></div><details><summary>新增结构化视频诊断</summary><form class="diagnosis-form" data-publication-id="${item.id}"><label>观察时间<input name="observed_at" type="datetime-local" required></label><label>诊断标题<input name="title" required></label><label>总结<textarea name="summary" rows="2"></textarea></label><label>转写摘录<textarea name="transcript_excerpt" rows="2"></textarea></label><label>发现类别<input name="category" required placeholder="例如：开场、事实表达、行动引导"></label><label>发现类型<select name="severity"><option value="observation">观察</option><option value="opportunity">优化机会</option><option value="risk">风险</option></select></label><label>证据<textarea name="evidence" rows="2" required></textarea></label><label>建议<textarea name="recommendation" rows="2"></textarea></label><button>保存诊断报告</button></form></details><div class="diagnosis-list" data-diagnosis-list="${item.id}"></div><div class="brief-list" data-brief-list="${item.id}"></div></article>`).join("")||"暂无发布记录";
  state.publications.forEach(item=>{loadSnapshots(item.id);loadDiagnoses(item.id);loadImprovementBriefs(item.id)});
}
async function loadDiagnoses(publicationId){
  const diagnoses=await api(`/v1/publications/${publicationId}/video-diagnoses`);
  const target=$(`[data-diagnosis-list="${publicationId}"]`);
  if(target)target.innerHTML=diagnoses.map(item=>`<article><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary||"无总结")}</p><div class="source-meta"><span>${escapeHtml(new Date(item.observed_at).toLocaleString())}</span><span>${item.findings.length} 条发现</span></div>${item.findings.map(finding=>`<p><span class="badge ${finding.severity==="risk"?"rejected":finding.severity==="opportunity"?"pending_review":"approved"}">${escapeHtml(finding.severity)}</span> <strong>${escapeHtml(finding.category)}</strong>：${escapeHtml(finding.evidence)}${finding.recommendation?`<br>建议：${escapeHtml(finding.recommendation)}`:""}</p>`).join("")}<details><summary>从本次诊断创建改进 Brief</summary><form class="brief-form" data-publication-id="${publicationId}" data-diagnosis-id="${item.id}"><label>Brief 标题<input name="title" required></label><label>改进目标<textarea name="objective" rows="2"></textarea></label><label>行动类别<input name="category" required placeholder="例如：开场、事实表达、行动引导"></label><label>改进指令<textarea name="instruction" rows="2" required></textarea></label><label>依据证据<textarea name="evidence" rows="2" required></textarea></label><label>约束条件（每行一条）<textarea name="guardrails" rows="2" placeholder="不得改变已审核的产品事实&#10;保留原品牌语气"></textarea></label><button>创建改进 Brief</button></form></details></article>`).join("")||"<p>尚无视频诊断</p>";
}
async function loadImprovementBriefs(publicationId){
  const briefs=await api(`/v1/publications/${publicationId}/improvement-briefs`);
  const target=$(`[data-brief-list="${publicationId}"]`);
  if(target)target.innerHTML=briefs.length?`<div class="section-head"><div><p class="eyebrow">IMPROVEMENT LOOP</p><h3>改进 Brief</h3></div></div>${briefs.map(item=>`<article><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.objective||"未填写改进目标")}</p><div class="source-meta"><span>${item.actions.length} 条行动</span><span>源版本 ${escapeHtml(item.source_content_version_id.slice(0,8))}</span></div>${item.actions.map(action=>`<p><strong>${escapeHtml(action.category)}</strong>：${escapeHtml(action.instruction)}<br><small>证据：${escapeHtml(action.evidence)}</small></p>`).join("")}${item.guardrails.length?`<p>约束：${item.guardrails.map(escapeHtml).join(" · ")}</p>`:""}<details><summary>显式创建后继草稿</summary><form class="improvement-draft-form" data-publication-id="${publicationId}" data-brief-id="${item.id}"><label>后继草稿内容（JSON）<textarea name="content" rows="8" required></textarea></label><label>变更说明<input name="change_summary" required maxlength="255"></label><p class="form-note">新草稿将保留来源版本和改进 Brief，不会覆盖已发布版本。</p><button>创建后继草稿</button></form></details></article>`).join("")}`:"<p>尚无改进 Brief</p>";
}
async function loadSnapshots(publicationId){
  const snapshots=await api(`/v1/publications/${publicationId}/performance-snapshots`);
  const target=$(`[data-snapshot-list="${publicationId}"]`);
  if(target)target.innerHTML=snapshots.map(row=>`<p class="source-meta"><span>${escapeHtml(new Date(row.captured_at).toLocaleString())}</span><span>播放 ${row.views??"-"}</span><span>点赞 ${row.likes??"-"}</span><span>评论 ${row.comments??"-"}</span><span>分享 ${row.shares??"-"}</span><span>收藏 ${row.saves??"-"}</span><span>订单 ${row.orders??"-"}</span></p>`).join("")||"<p>尚无数据快照</p>";
}
function renderMembers(){
  if(!state.actor)return;
  const allowOwner=state.actor.role==="owner";
  $(".role-select").innerHTML=roleOptions("creator",allowOwner);
  $("#member-count").textContent=`${state.members.length} 位成员`;
  $("#member-list").innerHTML=state.members.map(member=>`<article class="member-row"><div><h3>${escapeHtml(member.display_name)}${member.user_id===state.actor.user_id?' <span class="badge approved">当前账号</span>':""}</h3><p>${escapeHtml(member.email)}</p></div><label>角色<select data-member-role="${member.membership_id}" ${member.user_id===state.actor.user_id&&member.role==="owner"?"disabled":""}>${roleOptions(member.role,allowOwner)}</select></label></article>`).join("")||"暂无团队成员";
}
function renderFocus(approvedKnowledge,pendingKnowledge){
  let focus={status:"工作空间已就绪",detail:"先完善知识，再开始创作",title:"从最关键的资料开始。",copy:"先建立品牌和产品档案，再录入一条经过审核的事实，AI 才能生成可信内容。",label:"建立第一份档案",target:"assets"};
  if(state.brands.length&&!state.products.length)focus={status:"品牌已建档",detail:"下一步补充农产品事实",title:"让品牌拥有具体的产品。",copy:"补充产地、规格、储存方式、核心卖点与禁止表述，为可信生成建立事实边界。",label:"完善产品档案",target:"assets"};
  else if(state.products.length&&!state.knowledge.length)focus={status:"产品档案已就绪",detail:"知识库仍等待第一条资料",title:"加入第一条可信事实。",copy:"录入产品事实、品牌故事或地域资料。只有审核通过的内容才会进入 AI 上下文。",label:"录入可信资料",target:"knowledge"};
  else if(pendingKnowledge)focus={status:`${pendingKnowledge} 条资料待处理`,detail:"审核后才可用于内容生成",title:"先完成知识审核。",copy:"检查事实内容与引用标签，确认准确后通过审核，避免未经验证的信息进入营销内容。",label:"前往资料审核",target:"knowledge"};
  else if(approvedKnowledge&&!state.projects.length)focus={status:"可信知识已生效",detail:"现在可以创建第一项内容任务",title:"把知识转化为第一条内容。",copy:"选择产品、平台、目标受众和传播目标，生成一份来源可追溯的短视频或直播脚本。",label:"开始内容创作",target:"studio"};
  else if(state.projects.length)focus={status:`${state.projects.length} 个内容项目`,detail:"继续生成或检查待审核版本",title:"继续推进内容定稿。",copy:"打开内容创作台生成新版本，或进入审核页面确认内容是否达到发布标准。",label:"查看内容项目",target:"studio"};
  $("#focus-status").textContent=focus.status;$("#focus-detail").textContent=focus.detail;
  $("#next-action-title").textContent=focus.title;$("#next-action-copy").textContent=focus.copy;
  const button=$("#next-action-button");button.dataset.target=focus.target;button.innerHTML=`${escapeHtml(focus.label)} <b>→</b>`;
}

$("#bootstrap-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const result=await api("/v1/auth/bootstrap",{method:"POST",body:JSON.stringify(data)});state.token=result.access_token;localStorage.setItem("heyu_token",state.token);showWorkspace()},"本地工作空间已创建")});
$("#login-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const result=await api("/v1/auth/login",{method:"POST",body:JSON.stringify(formData(event.target))});state.token=result.access_token;localStorage.setItem("heyu_token",state.token);showWorkspace()},"已登录工作空间")});
const resetBrandForm=()=>{const form=$("#brand-form");form.reset();$("#brand-form-title").textContent="新建品牌";$("#brand-save-button").textContent="保存品牌";$("#brand-edit-cancel").hidden=true};
const resetProductForm=()=>{const form=$("#product-form");form.reset();$("#product-form-title").textContent="新建农产品";$("#product-save-button").textContent="保存产品";$("#product-edit-cancel").hidden=true};
$("#brand-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;await api(id?`/v1/brands/${id}`:"/v1/brands",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetBrandForm();await refresh()},event.target.elements.id.value?"品牌已更新":"品牌已保存")});
$("#product-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;data.selling_points=lines(data.selling_points);data.prohibited_claims=lines(data.prohibited_claims);await api(id?`/v1/products/${id}`:"/v1/products",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetProductForm();await refresh()},event.target.elements.id.value?"农产品已更新":"农产品已保存")});
$("#brand-edit-cancel").addEventListener("click",resetBrandForm);
$("#product-edit-cancel").addEventListener("click",resetProductForm);
const resetKnowledgeForm=()=>{const form=$("#knowledge-form");form.reset();form.elements.media_type.value="text/plain";$("#knowledge-file-status").textContent="也可以直接在下方手工录入";$("#knowledge-change-field").hidden=true;$("#knowledge-revision-cancel").hidden=true;$("#knowledge-save-button").textContent="保存为知识草稿"};
$("#knowledge-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const parentId=data.parent_source_id;delete data.parent_source_id;data.brand_id=data.brand_id||null;data.product_id=data.product_id||null;if(parentId){if(!data.change_summary.trim())throw new Error("请填写修订说明");await api(`/v1/knowledge/${parentId}/revisions`,{method:"POST",body:JSON.stringify(data)})}else{delete data.change_summary;await api("/v1/knowledge",{method:"POST",body:JSON.stringify(data)})}resetKnowledgeForm();await refresh()},event.target.elements.parent_source_id.value?"知识修订版已保存":"知识资料已保存")});
$("#knowledge-revision-cancel").addEventListener("click",resetKnowledgeForm);
$("#knowledge-file").addEventListener("change",async event=>{
  const file=event.target.files[0];
  const form=$("#knowledge-form");
  const status=$("#knowledge-file-status");
  if(!file){status.textContent="也可以直接在下方手工录入";return}
  const extension=file.name.split(".").pop().toLowerCase();
  if(!["txt","md","markdown","csv"].includes(extension)){event.target.value="";toast("仅支持 TXT、Markdown 或 CSV 文本文件",true);return}
  if(file.size>1024*1024){event.target.value="";toast("文本文件不能超过 1 MB",true);return}
  status.textContent="正在读取本地文件…";
  try{
    const content=await file.text();
    if(!content.trim())throw new Error("文件内容为空");
    if(!form.elements.title.value)form.elements.title.value=fileBaseName(file.name);
    form.elements.content.value=content;
    form.elements.source_filename.value=file.name;
    form.elements.media_type.value=knowledgeMediaType(file);
    if(!form.elements.citation_label.value)form.elements.citation_label.value=fileBaseName(file.name);
    status.textContent=`已读取 ${file.name} · ${(file.size/1024).toFixed(1)} KB，可继续编辑`;
  }catch(error){
    event.target.value="";
    status.textContent="文件读取失败，请重新选择";
    toast(error.message||"无法读取该文本文件",true);
  }
});
const resetProjectForm=()=>{const form=$("#project-form");form.reset();form.elements.platform.value="抖音";form.elements.tone.value="真诚、有烟火气";$("#project-form-title").textContent="创建内容任务";$("#project-save-button").textContent="创建任务";$("#project-edit-cancel").hidden=true};
$("#project-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const id=data.id;delete data.id;await api(id?`/v1/content-projects/${id}`:"/v1/content-projects",{method:id?"PUT":"POST",body:JSON.stringify(data)});resetProjectForm();await refresh()},event.target.elements.id.value?"内容任务已更新":"内容任务已创建")});
$("#project-edit-cancel").addEventListener("click",resetProjectForm);
$("#member-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/members",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"团队成员已创建")});
$("#generate-button").addEventListener("click",()=>request(async()=>{const id=$("#project-select").value;if(!id)throw new Error("请先选择内容任务");const result=await api(`/v1/content-projects/${id}/generate`,{method:"POST"});state.currentVersion=result.version;const content=JSON.stringify(result.version.content,null,2);$("#generation-output").textContent=content;$("#version-editor").value=content;$("#edit-version").hidden=false;let provenance=$("#generation-provenance");if(!provenance){provenance=document.createElement("div");provenance.id="generation-provenance";provenance.className="provenance";$("#generation-output").before(provenance)}provenance.innerHTML=`<span>Provider: ${escapeHtml(result.provider)}</span><span>Model: ${escapeHtml(result.model)}</span><span>Prompt: ${escapeHtml(result.prompt_name)} v${escapeHtml(result.prompt_version)}</span><span>Sources: ${result.source_ids.length}</span><span>${result.latency_ms} ms</span>`;state.versions=await api(`/v1/content-projects/${id}/versions`);state.audit=await api("/v1/audit-events");await loadGenerationRuns(id);renderReviews(id)},"内容已生成并进入审核"));
$("#save-version-button").addEventListener("click",()=>request(async()=>{if(!state.currentVersion)throw new Error("请先生成内容");let content;try{content=JSON.parse($("#version-editor").value)}catch{throw new Error("修改内容必须是有效的 JSON 格式")}const projectId=state.currentVersion.project_id;const version=await api(`/v1/content-projects/${projectId}/versions`,{method:"POST",body:JSON.stringify({parent_version_id:state.currentVersion.id,content,change_summary:$("#change-summary").value})});state.currentVersion=version;$("#generation-output").textContent=JSON.stringify(version.content,null,2);state.versions=await api(`/v1/content-projects/${projectId}/versions`);renderReviews(projectId)},"人工修改已保存为新版本"));
$("#review-project-select").addEventListener("change",event=>request(()=>renderReviews(event.target.value)));
$("#project-select").addEventListener("change",event=>request(()=>loadGenerationRuns(event.target.value)));
$("#publication-project-select").addEventListener("change",event=>request(async()=>{
  const select=$("#publication-version-select");
  if(!event.target.value){select.innerHTML='<option value="">请先选择项目</option>';return}
  const versions=await api(`/v1/content-projects/${event.target.value}/versions`);
  const approved=versions.filter(item=>item.status==="approved");
  select.innerHTML=approved.length?approved.map(item=>`<option value="${item.id}">版本 ${item.version_number} · ${escapeHtml(item.change_summary||"已审核内容")}</option>`).join(""):'<option value="">该项目暂无已审核版本</option>';
}));
$("#publication-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const data=formData(event.target);
  data.published_at=new Date(data.published_at).toISOString();
  await api("/v1/publications",{method:"POST",body:JSON.stringify(data)});
  event.target.reset();
  await refresh();
},"发布记录已保存")});
$$("[data-auth-mode]").forEach(button=>button.addEventListener("click",()=>{$$("[data-auth-mode]").forEach(x=>x.classList.toggle("active",x===button));$$("[data-auth-panel]").forEach(panel=>panel.hidden=panel.dataset.authPanel!==button.dataset.authMode)}));
document.addEventListener("click",event=>{const nav=event.target.closest("[data-page]");if(nav)navigate(nav.dataset.page);const jump=event.target.closest("[data-target]");if(jump)navigate(jump.dataset.target);const editProject=event.target.closest("[data-edit-project]");if(editProject){const project=state.projects.find(item=>item.id===editProject.dataset.editProject);const form=$("#project-form");["id","title","brand_id","product_id","content_type","platform","tone","target_audience","objective","extra_requirements"].forEach(name=>form.elements[name].value=project[name]||"");$("#project-form-title").textContent="编辑内容任务";$("#project-save-button").textContent="保存任务修改";$("#project-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editBrand=event.target.closest("[data-edit-brand]");if(editBrand){const brand=state.brands.find(item=>item.id===editBrand.dataset.editBrand);const form=$("#brand-form");["id","name","story","voice"].forEach(name=>form.elements[name].value=brand[name]||"");$("#brand-form-title").textContent="编辑品牌";$("#brand-save-button").textContent="保存品牌修改";$("#brand-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editProduct=event.target.closest("[data-edit-product]");if(editProduct){const product=state.products.find(item=>item.id===editProduct.dataset.editProduct);const form=$("#product-form");["id","brand_id","name","origin","specification","price_display","shelf_life","storage_method"].forEach(name=>form.elements[name].value=product[name]||"");form.elements.selling_points.value=(product.selling_points||[]).join("\n");form.elements.prohibited_claims.value=(product.prohibited_claims||[]).join("\n");$("#product-form-title").textContent="编辑农产品";$("#product-save-button").textContent="保存产品修改";$("#product-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const revise=event.target.closest("[data-revise-source]");if(revise){const source=state.knowledge.find(item=>item.id===revise.dataset.reviseSource);const form=$("#knowledge-form");["title","kind","content","citation_label","source_filename","media_type","brand_id","product_id"].forEach(name=>{if(form.elements[name])form.elements[name].value=source[name]||""});form.elements.parent_source_id.value=source.id;$("#knowledge-change-field").hidden=false;$("#knowledge-revision-cancel").hidden=false;$("#knowledge-save-button").textContent=`保存为 R${(source.revision_number||1)+1} 修订草稿`;form.elements.change_summary.focus();form.scrollIntoView({behavior:"smooth",block:"start"})}const sourceSubmit=event.target.closest("[data-submit-source]");if(sourceSubmit)request(async()=>{await api(`/v1/knowledge/${sourceSubmit.dataset.submitSource}/submit`,{method:"POST"});await refresh()},"知识资料已提交审核");const review=event.target.closest("[data-review-source]");if(review)request(async()=>{await api(`/v1/knowledge/${review.dataset.reviewSource}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status})});await refresh()},"资料审核状态已更新");const submit=event.target.closest("[data-submit-version]");if(submit)request(async()=>{await api(`/v1/content-projects/${submit.dataset.project}/versions/${submit.dataset.submitVersion}/submit`,{method:"POST"});state.versions=await api(`/v1/content-projects/${submit.dataset.project}/versions`);renderReviews(submit.dataset.project)},"内容版本已提交审核");const versionReview=event.target.closest("[data-review-version]");if(versionReview)request(async()=>{await api(`/v1/content-projects/${versionReview.dataset.project}/versions/${versionReview.dataset.reviewVersion}/review`,{method:"POST",body:JSON.stringify({status:versionReview.dataset.status,note:"由禾语工作台审核"})});state.versions=await api(`/v1/content-projects/${versionReview.dataset.project}/versions`);renderReviews(versionReview.dataset.project)},"内容审核状态已更新")});
document.addEventListener("change",event=>{const select=event.target.closest("[data-member-role]");if(select)request(async()=>{await api(`/v1/members/${select.dataset.memberRole}`,{method:"PATCH",body:JSON.stringify({role:select.value})});await refresh()},"成员角色已更新")});
document.addEventListener("submit",event=>{const form=event.target.closest(".snapshot-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  data.captured_at=new Date(data.captured_at).toISOString();
  ["views","likes","comments","shares","saves","followers_gained","orders","revenue_minor"].forEach(key=>{data[key]=data[key]===""?null:Number(data[key])});
  data.currency="CNY";
  await api(`/v1/publications/${form.dataset.publicationId}/performance-snapshots`,{method:"POST",body:JSON.stringify(data)});
  form.reset();
  await loadSnapshots(form.dataset.publicationId);
},"运营数据快照已保存")});
document.addEventListener("submit",event=>{const form=event.target.closest(".diagnosis-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  const payload={observed_at:new Date(data.observed_at).toISOString(),title:data.title,summary:data.summary,transcript_excerpt:data.transcript_excerpt,findings:[{category:data.category,severity:data.severity,evidence:data.evidence,recommendation:data.recommendation}]};
  await api(`/v1/publications/${form.dataset.publicationId}/video-diagnoses`,{method:"POST",body:JSON.stringify(payload)});
  form.reset();
  await loadDiagnoses(form.dataset.publicationId);
},"视频诊断报告已保存")});
document.addEventListener("submit",event=>{const form=event.target.closest(".brief-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);
  const payload={video_diagnosis_id:form.dataset.diagnosisId,title:data.title,objective:data.objective,actions:[{category:data.category,instruction:data.instruction,evidence:data.evidence}],guardrails:lines(data.guardrails)};
  await api(`/v1/publications/${form.dataset.publicationId}/improvement-briefs`,{method:"POST",body:JSON.stringify(payload)});
  form.reset();
  await loadImprovementBriefs(form.dataset.publicationId);
  state.audit=await api("/v1/audit-events");
},"改进 Brief 已创建")});
document.addEventListener("submit",event=>{const form=event.target.closest(".improvement-draft-form");if(!form)return;event.preventDefault();request(async()=>{
  const data=formData(form);let content;try{content=JSON.parse(data.content)}catch{throw new Error("后继草稿内容必须是有效的 JSON 对象")}
  const version=await api(`/v1/publications/${form.dataset.publicationId}/improvement-briefs/${form.dataset.briefId}/draft`,{method:"POST",body:JSON.stringify({content,change_summary:data.change_summary})});
  form.reset();
  state.currentVersion=version;
  state.audit=await api("/v1/audit-events");
},"后继草稿已创建，可前往内容审核页继续处理")});
async function renderReviews(selectedId){
  if(!selectedId&&state.projects.length)selectedId=state.projects[0].id;
  if(selectedId)state.versions=await api(`/v1/content-projects/${selectedId}/versions`);
  const canSubmit=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor.role);
  $("#review-list").innerHTML=state.versions.map(v=>`<article><h3>版本 ${v.version_number} · ${escapeHtml(v.change_summary||"AI 初稿")}</h3><p>${escapeHtml(JSON.stringify(v.content).slice(0,220))}</p><span class="badge ${v.status}">${v.status}</span>${v.status==="draft"&&canSubmit?`<div class="row-actions"><button class="approve" data-submit-version="${v.id}" data-project="${v.project_id}">提交审核</button></div>`:""}${v.status==="pending_review"&&canReview?`<div class="row-actions"><button class="approve" data-review-version="${v.id}" data-project="${v.project_id}" data-status="approved">审核通过</button><button class="reject" data-review-version="${v.id}" data-project="${v.project_id}" data-status="rejected">驳回</button></div>`:""}${v.review_note?`<p class="review-note">审核意见：${escapeHtml(v.review_note)}</p>`:""}</article>`).join("")||"暂无内容版本";
}
async function loadGenerationRuns(projectId){
  state.generationRuns=projectId?await api(`/v1/content-projects/${projectId}/generation-runs`):[];
  $("#generation-history-list").innerHTML=state.generationRuns.map(run=>{
    const manifest=run.normalized_input?.context_sources||[];
    const sourceEvidence=run.sources.map(source=>{
      const evidence=manifest.find(item=>item.source_id===source.id);
      const scope=evidence?.scope==="product"?"产品知识":evidence?.scope==="brand"?"品牌知识":"组织知识";
      const length=evidence?`${evidence.included_chars}/${evidence.source_chars} 字`:"已引用";
      return `<li><div><strong>${escapeHtml(source.citation_label||source.title)}</strong><small>${escapeHtml(scope)} · ${escapeHtml(length)}</small></div>${evidence?.truncated?'<span class="context-flag">已截取</span>':'<span class="context-flag complete">完整</span>'}</li>`;
    }).join("");
    return `<article><div class="panel-heading"><div><h3>${escapeHtml(run.output.format||"生成内容")}</h3><p>${escapeHtml(run.provider)} / ${escapeHtml(run.model)} · ${escapeHtml(run.prompt_name)} v${escapeHtml(run.prompt_version)}</p></div><span class="badge approved">${escapeHtml(run.status)}</span></div><div class="provenance"><span>${run.latency_ms} ms</span><span>${escapeHtml(new Date(run.created_at).toLocaleString())}</span><span>${run.sources.length} 条可信来源</span></div>${sourceEvidence?`<div class="context-evidence"><div class="context-evidence-head"><strong>本次实际使用的知识</strong><small>${escapeHtml(run.normalized_input?.context_policy||"legacy")} · 可追溯</small></div><ul>${sourceEvidence}</ul></div>`:""}<details><summary>查看规范化任务与完整输出</summary><pre>${escapeHtml(JSON.stringify({input:run.normalized_input,output:run.output},null,2))}</pre></details></article>`;
  }).join("")||"该任务尚无生成记录";
}
$("#logout").addEventListener("click",()=>{localStorage.removeItem("heyu_token");state.token="";location.href="/workspace/"});
$$(".jump").forEach(x=>x.addEventListener("click",()=>navigate(x.dataset.target)));
window.addEventListener("popstate",()=>navigate(pageFromLocation(),false));
showWorkspace();

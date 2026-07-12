const state={token:localStorage.getItem("heyu_token")||"",actor:null,members:[],brands:[],products:[],knowledge:[],projects:[],versions:[],generationRuns:[],audit:[],currentVersion:null};
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

function showWorkspace(){
  $("#auth-view").hidden=Boolean(state.token);$("#workspace").hidden=!state.token;$("#logout").hidden=!state.token;
  if(state.token) refresh();
}
function navigate(page){
  $$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.page===page));
  $$(".page").forEach(x=>x.classList.toggle("active",x.dataset.pagePanel===page));
  const titles={overview:"经营概览",assets:"品牌与农产品",knowledge:"可信知识库",studio:"内容创作台",review:"审核与版本",audit:"审计记录",members:"团队与权限"};
  $("#page-title").textContent=titles[page];
}
async function refresh(){
  state.actor=await api("/v1/me");
  const canManageMembers=["owner","admin"].includes(state.actor.role);
  [state.brands,state.products,state.knowledge,state.projects,state.audit]=await Promise.all([api("/v1/brands"),api("/v1/products"),api("/v1/knowledge"),api("/v1/content-projects"),api("/v1/audit-events")]);
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
  $("#asset-list").innerHTML=[...state.brands.map(b=>`<article><span class="pill">品牌</span><h3>${escapeHtml(b.name)}</h3><p>${escapeHtml(b.story||"尚未填写品牌故事")}</p></article>`),...state.products.map(p=>`<article><span class="pill">农产品</span><h3>${escapeHtml(p.name)}</h3><p>${escapeHtml(p.origin||"产地待补充")} · ${escapeHtml(p.specification||"规格待补充")}</p></article>`)].join("")||"暂无品牌与产品";
  const canSubmitKnowledge=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReviewKnowledge=["owner","admin","reviewer"].includes(state.actor.role);
  $("#knowledge-list").innerHTML=state.knowledge.map(k=>`<article><h3>${escapeHtml(k.title)} <span class="badge">R${k.revision_number||1}</span></h3><p>${escapeHtml(k.content.slice(0,130))}</p><div class="source-meta">${k.source_filename?`<span>文件 ${escapeHtml(k.source_filename)}</span>`:"<span>手工录入</span>"}<span>${escapeHtml(k.media_type||"text/plain")}</span>${k.content_sha256?`<span title="${escapeHtml(k.content_sha256)}">SHA-256 ${escapeHtml(k.content_sha256.slice(0,12))}…</span>`:""}${k.citation_label?`<span>引用 ${escapeHtml(k.citation_label)}</span>`:""}${k.parent_source_id?`<span>源自 R${(k.revision_number||1)-1}</span>`:""}${k.change_summary?`<span>修订 ${escapeHtml(k.change_summary)}</span>`:""}${k.reviewed_by?`<span>审核人 ${escapeHtml(k.reviewed_by.slice(0,8))}</span>`:""}</div><span class="badge ${k.status}">${k.status}</span>${k.status==="draft"&&canSubmitKnowledge?`<div class="row-actions"><button class="approve" data-submit-source="${k.id}">提交审核</button></div>`:""}${["approved","rejected"].includes(k.status)&&canSubmitKnowledge?`<div class="row-actions"><button data-revise-source="${k.id}">创建修订版</button></div>`:""}${k.status==="pending_review"&&canReviewKnowledge?`<div class="row-actions"><button class="approve" data-review-source="${k.id}" data-status="approved">审核通过</button><button class="reject" data-review-source="${k.id}" data-status="rejected">驳回</button></div>`:""}</article>`).join("")||"暂无知识资料";
  $("#audit-list").innerHTML=state.audit.map(item=>`<article><h3>${escapeHtml(actionLabel(item.action))}</h3><p>${escapeHtml(item.entity_type)} · ${escapeHtml(item.entity_id)}</p><div class="audit-meta"><span>操作者 ${escapeHtml(item.actor_id.slice(0,8))}</span><span>${escapeHtml(JSON.stringify(item.details))}</span></div></article>`).join("")||"暂无审计记录";
  renderMembers();
}
const actionLabel=action=>({"membership.created":"创建团队成员","membership.role_changed":"调整成员角色","brand.created":"创建品牌","product.created":"创建农产品","knowledge.created":"录入知识","knowledge.revised":"创建知识修订版","knowledge.submitted":"知识已提交审核","knowledge.approved":"知识审核通过","knowledge.rejected":"知识被驳回","content_project.created":"创建内容任务","content.generated":"AI 生成内容","content_version.created":"创建内容版本","content_version.submitted":"内容已提交审核","content_version.approved":"内容审核通过","content_version.rejected":"内容被驳回"}[action]||action);
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
$("#brand-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/brands",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"品牌已保存")});
$("#product-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);data.selling_points=lines(data.selling_points);data.prohibited_claims=lines(data.prohibited_claims);await api("/v1/products",{method:"POST",body:JSON.stringify(data)});event.target.reset();await refresh()},"产品已保存")});
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
$("#project-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/content-projects",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"内容任务已创建")});
$("#member-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/members",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"团队成员已创建")});
$("#generate-button").addEventListener("click",()=>request(async()=>{const id=$("#project-select").value;if(!id)throw new Error("请先选择内容任务");const result=await api(`/v1/content-projects/${id}/generate`,{method:"POST"});state.currentVersion=result.version;const content=JSON.stringify(result.version.content,null,2);$("#generation-output").textContent=content;$("#version-editor").value=content;$("#edit-version").hidden=false;let provenance=$("#generation-provenance");if(!provenance){provenance=document.createElement("div");provenance.id="generation-provenance";provenance.className="provenance";$("#generation-output").before(provenance)}provenance.innerHTML=`<span>Provider: ${escapeHtml(result.provider)}</span><span>Model: ${escapeHtml(result.model)}</span><span>Prompt: ${escapeHtml(result.prompt_name)} v${escapeHtml(result.prompt_version)}</span><span>Sources: ${result.source_ids.length}</span><span>${result.latency_ms} ms</span>`;state.versions=await api(`/v1/content-projects/${id}/versions`);state.audit=await api("/v1/audit-events");await loadGenerationRuns(id);renderReviews(id)},"内容已生成并进入审核"));
$("#save-version-button").addEventListener("click",()=>request(async()=>{if(!state.currentVersion)throw new Error("请先生成内容");let content;try{content=JSON.parse($("#version-editor").value)}catch{throw new Error("修改内容必须是有效的 JSON 格式")}const projectId=state.currentVersion.project_id;const version=await api(`/v1/content-projects/${projectId}/versions`,{method:"POST",body:JSON.stringify({parent_version_id:state.currentVersion.id,content,change_summary:$("#change-summary").value})});state.currentVersion=version;$("#generation-output").textContent=JSON.stringify(version.content,null,2);state.versions=await api(`/v1/content-projects/${projectId}/versions`);renderReviews(projectId)},"人工修改已保存为新版本"));
$("#review-project-select").addEventListener("change",event=>request(()=>renderReviews(event.target.value)));
$("#project-select").addEventListener("change",event=>request(()=>loadGenerationRuns(event.target.value)));
$$("[data-auth-mode]").forEach(button=>button.addEventListener("click",()=>{$$("[data-auth-mode]").forEach(x=>x.classList.toggle("active",x===button));$$("[data-auth-panel]").forEach(panel=>panel.hidden=panel.dataset.authPanel!==button.dataset.authMode)}));
document.addEventListener("click",event=>{const nav=event.target.closest("[data-page]");if(nav)navigate(nav.dataset.page);const jump=event.target.closest("[data-target]");if(jump)navigate(jump.dataset.target);const revise=event.target.closest("[data-revise-source]");if(revise){const source=state.knowledge.find(item=>item.id===revise.dataset.reviseSource);const form=$("#knowledge-form");["title","kind","content","citation_label","source_filename","media_type","brand_id","product_id"].forEach(name=>{if(form.elements[name])form.elements[name].value=source[name]||""});form.elements.parent_source_id.value=source.id;$("#knowledge-change-field").hidden=false;$("#knowledge-revision-cancel").hidden=false;$("#knowledge-save-button").textContent=`保存为 R${(source.revision_number||1)+1} 修订草稿`;form.elements.change_summary.focus();form.scrollIntoView({behavior:"smooth",block:"start"})}const sourceSubmit=event.target.closest("[data-submit-source]");if(sourceSubmit)request(async()=>{await api(`/v1/knowledge/${sourceSubmit.dataset.submitSource}/submit`,{method:"POST"});await refresh()},"知识资料已提交审核");const review=event.target.closest("[data-review-source]");if(review)request(async()=>{await api(`/v1/knowledge/${review.dataset.reviewSource}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status})});await refresh()},"资料审核状态已更新");const submit=event.target.closest("[data-submit-version]");if(submit)request(async()=>{await api(`/v1/content-projects/${submit.dataset.project}/versions/${submit.dataset.submitVersion}/submit`,{method:"POST"});state.versions=await api(`/v1/content-projects/${submit.dataset.project}/versions`);renderReviews(submit.dataset.project)},"内容版本已提交审核");const versionReview=event.target.closest("[data-review-version]");if(versionReview)request(async()=>{await api(`/v1/content-projects/${versionReview.dataset.project}/versions/${versionReview.dataset.reviewVersion}/review`,{method:"POST",body:JSON.stringify({status:versionReview.dataset.status,note:"由禾语工作台审核"})});state.versions=await api(`/v1/content-projects/${versionReview.dataset.project}/versions`);renderReviews(versionReview.dataset.project)},"内容审核状态已更新")});
document.addEventListener("change",event=>{const select=event.target.closest("[data-member-role]");if(select)request(async()=>{await api(`/v1/members/${select.dataset.memberRole}`,{method:"PATCH",body:JSON.stringify({role:select.value})});await refresh()},"成员角色已更新")});
async function renderReviews(selectedId){
  if(!selectedId&&state.projects.length)selectedId=state.projects[0].id;
  if(selectedId)state.versions=await api(`/v1/content-projects/${selectedId}/versions`);
  const canSubmit=["owner","admin","creator","product_manager"].includes(state.actor.role);
  const canReview=["owner","admin","reviewer"].includes(state.actor.role);
  $("#review-list").innerHTML=state.versions.map(v=>`<article><h3>版本 ${v.version_number} · ${escapeHtml(v.change_summary||"AI 初稿")}</h3><p>${escapeHtml(JSON.stringify(v.content).slice(0,220))}</p><span class="badge ${v.status}">${v.status}</span>${v.status==="draft"&&canSubmit?`<div class="row-actions"><button class="approve" data-submit-version="${v.id}" data-project="${v.project_id}">提交审核</button></div>`:""}${v.status==="pending_review"&&canReview?`<div class="row-actions"><button class="approve" data-review-version="${v.id}" data-project="${v.project_id}" data-status="approved">审核通过</button><button class="reject" data-review-version="${v.id}" data-project="${v.project_id}" data-status="rejected">驳回</button></div>`:""}${v.review_note?`<p class="review-note">审核意见：${escapeHtml(v.review_note)}</p>`:""}</article>`).join("")||"暂无内容版本";
}
async function loadGenerationRuns(projectId){
  state.generationRuns=projectId?await api(`/v1/content-projects/${projectId}/generation-runs`):[];
  $("#generation-history-list").innerHTML=state.generationRuns.map(run=>`<article><div class="panel-heading"><div><h3>${escapeHtml(run.output.format||"生成内容")}</h3><p>${escapeHtml(run.provider)} / ${escapeHtml(run.model)} · ${escapeHtml(run.prompt_name)} v${escapeHtml(run.prompt_version)}</p></div><span class="badge approved">${escapeHtml(run.status)}</span></div><div class="provenance"><span>${run.latency_ms} ms</span><span>${escapeHtml(new Date(run.created_at).toLocaleString())}</span>${run.sources.map(source=>`<span title="${escapeHtml(source.id)}">${escapeHtml(source.citation_label||source.title)}</span>`).join("")}</div><details><summary>查看规范化任务与完整输出</summary><pre>${escapeHtml(JSON.stringify({input:run.normalized_input,output:run.output},null,2))}</pre></details></article>`).join("")||"该任务尚无生成记录";
}
$("#logout").addEventListener("click",()=>{localStorage.removeItem("heyu_token");state.token="";location.reload()});
$$(".jump").forEach(x=>x.addEventListener("click",()=>navigate(x.dataset.target)));
showWorkspace();

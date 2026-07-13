const inviteFragment=new URLSearchParams(location.hash.replace(/^#/,"")).get("invite")||"";
if(inviteFragment)history.replaceState(null,"","/workspace/");
const state={token:localStorage.getItem("heyu_token")||"",actor:null,members:[],invitations:[],brands:[],products:[],knowledge:[],campaigns:[],campaignSupplySnapshots:[],projects:[],versions:[],generationRuns:[],publications:[],audit:[],currentVersion:null,inviteToken:inviteFragment};
const t=(key,variables={})=>HeyuI18n.t(key,variables);
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
const api=async(path,options={})=>{const headers={"Content-Type":"application/json",...(options.headers||{})};if(state.token)headers.Authorization=`Bearer ${state.token}`;const response=await fetch(path,{...options,headers});if(!response.ok){let message=response.status===429?t("error.tooManyRequests"):t("error.requestFailed",{status:response.status});try{const body=await response.json();if(response.status!==429)message=body.detail||message}catch{}if(response.status===401&&state.token){invalidateSession();message=t("auth.sessionExpired")}throw new Error(message)}return response.status===204?null:response.json()};
const formData=form=>Object.fromEntries(new FormData(form));
const lines=value=>value.split("\n").map(v=>v.trim()).filter(Boolean);
const toast=(message,error=false)=>{const el=$("#toast");el.textContent=message;el.className=`show${error?" error":""}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className="",3000)};
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fileBaseName=name=>name.replace(/\.(txt|md|markdown|csv)$/i,"");
const knowledgeMediaType=file=>file.type||({txt:"text/plain",md:"text/markdown",markdown:"text/markdown",csv:"text/csv"}[file.name.split(".").pop().toLowerCase()]||"text/plain");
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
const downloadResult=(content,type)=>{
  const project=state.projects.find(item=>item.id===state.currentVersion?.project_id);
  const basename=HeyuContent.safeFilename(project?.title||"heyu-content");
  const isJson=type==="json";
  const body=isJson?JSON.stringify(content,null,2):HeyuContent.renderContent(content,{t:HeyuI18n.t,locale:HeyuI18n.getLocale()});
  const blob=new Blob([body],{type:isJson?"application/json;charset=utf-8":"text/plain;charset=utf-8"});
  const link=document.createElement("a");link.href=URL.createObjectURL(blob);link.download=`${basename}.${isJson?"json":"txt"}`;link.click();setTimeout(()=>URL.revokeObjectURL(link.href),0);
};
const workspacePages=["overview","assets","knowledge","campaigns","studio","operations","review","audit","members"];
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
  [state.brands,state.products,state.knowledge,state.campaigns,state.projects,state.publications,state.audit]=await Promise.all([api("/v1/brands"),api("/v1/products"),api("/v1/knowledge"),api("/v1/campaign-packages"),api("/v1/content-projects"),api("/v1/publications"),api("/v1/audit-events")]);
  [state.members,state.invitations]=canManageMembers?await Promise.all([api("/v1/members"),api("/v1/invitations")]):[[],[]];
  $$(".member-nav").forEach(x=>x.hidden=!canManageMembers);
  if(!canManageMembers&&$(".nav.active")?.dataset.page==="members")navigate("overview");
  render();
}
const canWriteScope=scope=>{
  const role=state.actor?.role;
  if(scope==="assets")return ["owner","admin","product_manager"].includes(role);
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
  renderPublications();
  renderMembers();
}
const campaignStatusLabel=value=>t(`campaign.status.${value}`);
function renderCampaigns(){
  $("#campaign-count").textContent=t("campaign.count",{count:HeyuI18n.formatNumber(state.campaigns.length)});
  const canManage=canWriteScope("content");
  $("#campaign-list").innerHTML=state.campaigns.map(campaign=>{
    const progress=campaign.progress;
    const items=campaign.items.map(item=>{
      const stale=Boolean(item.latest_version_id&&!item.supply_current);
      const status=item.publication_id?t("campaign.item.published"):item.approved_version_id?t("campaign.item.approved"):item.latest_version_id?t("campaign.item.draft"):t("campaign.item.notStarted");
      const action=canManage&&(!item.latest_version_id||(stale&&campaign.current_supply_snapshot))?`<button data-generate-campaign-item="${item.content_project_id}">${escapeHtml(t(stale?"supply.regenerate":"campaign.generate"))}</button>`:"";
      return `<li class="${stale?"supply-stale":""}"><span>${escapeHtml(t(`campaign.slot.${item.slot_key}`))}${stale?`<small>${escapeHtml(t("supply.contentStale"))}</small>`:""}</span><b>${escapeHtml(status)}</b>${action}</li>`;
    }).join("");
    return `<article class="campaign-card"><div class="panel-heading"><div><span class="badge ${campaign.status==="completed"?"approved":"pending_review"}">${escapeHtml(campaignStatusLabel(campaign.status))}</span><h3>${escapeHtml(campaign.title)}</h3></div><strong>${progress.required_approved}/${progress.required}</strong></div><p>${escapeHtml(campaign.platform)} · ${escapeHtml(campaign.target_audience)}</p><div class="campaign-progress"><i style="width:${progress.required?Math.round(progress.required_approved/progress.required*100):0}%"></i></div><ul>${items}</ul></article>`;
  }).join("")||`<p>${escapeHtml(t("campaign.empty"))}</p>`;
  renderSupplyCampaignOptions();
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

const actionLabel=action=>{const key=`audit.action.${action}`;const label=t(key);return label===key?action:label};
function renderPublications(){
  const canOperate=canWriteScope("content");
  $("#publication-list").innerHTML=state.publications.map(item=>`<article><div class="panel-heading"><div><h3>${escapeHtml(item.platform)}</h3><p>${escapeHtml(HeyuI18n.formatDate(item.published_at))}</p></div><span class="badge approved">${escapeHtml(t("publication.published"))}</span></div>${item.external_url?`<p><a href="${escapeHtml(item.external_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(t("publication.viewExternal"))}</a></p>`:""}${canOperate?`<form class="snapshot-form" data-publication-id="${item.id}"><div class="source-meta"><label>${escapeHtml(t("snapshot.capturedAt"))}<input name="captured_at" type="datetime-local" required></label><label>${escapeHtml(t("metric.views"))}<input name="views" type="number" min="0"></label><label>${escapeHtml(t("metric.likes"))}<input name="likes" type="number" min="0"></label><label>${escapeHtml(t("metric.comments"))}<input name="comments" type="number" min="0"></label><label>${escapeHtml(t("metric.shares"))}<input name="shares" type="number" min="0"></label><label>${escapeHtml(t("metric.saves"))}<input name="saves" type="number" min="0"></label><label>${escapeHtml(t("metric.followersGained"))}<input name="followers_gained" type="number" min="0"></label><label>${escapeHtml(t("metric.orders"))}<input name="orders" type="number" min="0"></label><label>${escapeHtml(t("metric.revenueMinor"))}<input name="revenue_minor" type="number" min="0"></label></div><button>${escapeHtml(t("snapshot.add"))}</button></form>`:""}<div class="snapshot-list" data-snapshot-list="${item.id}"></div>${canOperate?`<details><summary>${escapeHtml(t("diagnosis.add"))}</summary><form class="diagnosis-form" data-publication-id="${item.id}"><label>${escapeHtml(t("diagnosis.observedAt"))}<input name="observed_at" type="datetime-local" required></label><label>${escapeHtml(t("diagnosis.reportTitle"))}<input name="title" required></label><label>${escapeHtml(t("diagnosis.summary"))}<textarea name="summary" rows="2"></textarea></label><label>${escapeHtml(t("diagnosis.transcriptExcerpt"))}<textarea name="transcript_excerpt" rows="2"></textarea></label><label>${escapeHtml(t("diagnosis.category"))}<input name="category" required></label><label>${escapeHtml(t("diagnosis.severity"))}<select name="severity"><option value="observation">${escapeHtml(severityLabel("observation"))}</option><option value="opportunity">${escapeHtml(severityLabel("opportunity"))}</option><option value="risk">${escapeHtml(severityLabel("risk"))}</option></select></label><label>${escapeHtml(t("diagnosis.evidence"))}<textarea name="evidence" rows="2" required></textarea></label><label>${escapeHtml(t("diagnosis.recommendation"))}<textarea name="recommendation" rows="2"></textarea></label><button>${escapeHtml(t("diagnosis.save"))}</button></form></details>`:""}<div class="diagnosis-list" data-diagnosis-list="${item.id}"></div><div class="brief-list" data-brief-list="${item.id}"></div></article>`).join("")||escapeHtml(t("publication.empty"));
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
  if(target)target.innerHTML=briefs.length?`<div class="section-head"><div><p class="eyebrow">IMPROVEMENT LOOP</p><h3>${escapeHtml(t("brief.title"))}</h3></div></div>${briefs.map(item=>`<article><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.objective||t("brief.objectiveMissing"))}</p><div class="source-meta"><span>${escapeHtml(t("brief.actionCount",{count:HeyuI18n.formatNumber(item.actions.length)}))}</span><span>${escapeHtml(t("brief.sourceVersion",{version:item.source_content_version_id.slice(0,8)}))}</span></div>${item.actions.map(action=>`<p><strong>${escapeHtml(action.category)}</strong>${escapeHtml(fieldSeparator())}${escapeHtml(action.instruction)}<br><small>${escapeHtml(t("brief.evidence"))}${escapeHtml(fieldSeparator())}${escapeHtml(action.evidence)}</small></p>`).join("")}${item.guardrails.length?`<p>${escapeHtml(t("brief.guardrails"))}${escapeHtml(fieldSeparator())}${item.guardrails.map(escapeHtml).join(" · ")}</p>`:""}${canOperate?`<details><summary>${escapeHtml(t("successor.createExplicitly"))}</summary><form class="improvement-draft-form" data-publication-id="${publicationId}" data-brief-id="${item.id}"><label>${escapeHtml(t("successor.contentJson"))}<textarea name="content" rows="8" required></textarea></label><label>${escapeHtml(t("successor.changeSummary"))}<input name="change_summary" required maxlength="255"></label><p class="form-note">${escapeHtml(t("successor.historyNote"))}</p><button>${escapeHtml(t("successor.create"))}</button></form></details>`:""}</article>`).join("")}`:`<p>${escapeHtml(t("brief.empty"))}</p>`;
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
$("#supply-campaign-select").addEventListener("change",event=>{renderSupplyEvidence();request(()=>loadSupplySnapshots(event.target.value))});
$("#supply-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const campaignId=$("#supply-campaign-select").value;if(!campaignId)throw new Error(t("supply.selectCampaign"));
  const data=formData(event.target);const amount=Number(data.price_amount);if(!Number.isFinite(amount)||amount<0)throw new Error(t("supply.invalidAmount"));
  delete data.price_amount;data.price_minor=Math.round((amount+Number.EPSILON)*100);data.available_quantity=Number(data.available_quantity);data.ship_within_hours=Number(data.ship_within_hours);data.shipping_regions=lines(data.shipping_regions);data.evidence_source_ids=[...event.target.querySelectorAll('[name="evidence_source_ids"]:checked')].map(item=>item.value);
  if(!data.evidence_source_ids.length)throw new Error(t("supply.evidenceRequired"));["price_valid_until","inventory_confirmed_at","active_from","active_until"].forEach(key=>{data[key]=toIso(data[key])});data.harvest_date=data.harvest_date||null;
  await api(`/v1/campaign-packages/${campaignId}/supply-snapshots`,{method:"POST",body:JSON.stringify(data)});event.target.reset();await refresh();$("#supply-campaign-select").value=campaignId;renderSupplyEvidence();await loadSupplySnapshots(campaignId);
},t("supply.created"))});
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
  if(!["txt","md","markdown","csv"].includes(extension)){event.target.value="";toast(t("sourceImport.unsupportedType"),true);return}
  if(file.size>1024*1024){event.target.value="";toast(t("sourceImport.fileTooLarge"),true);return}
  status.textContent=t("sourceImport.reading");
  try{
    const content=await file.text();
    if(!content.trim())throw new Error(t("sourceImport.emptyFile"));
    if(!form.elements.title.value)form.elements.title.value=fileBaseName(file.name);
    form.elements.content.value=content;
    form.elements.source_filename.value=file.name;
    form.elements.media_type.value=knowledgeMediaType(file);
    if(!form.elements.citation_label.value)form.elements.citation_label.value=fileBaseName(file.name);
    status.textContent=t("sourceImport.readSuccess",{filename:file.name,size:(file.size/1024).toFixed(1)});
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
$("#project-select").addEventListener("change",event=>request(()=>loadGenerationRuns(event.target.value)));
$("#publication-project-select").addEventListener("change",event=>request(async()=>{
  const select=$("#publication-version-select");
  if(!event.target.value){select.innerHTML=`<option value="">${escapeHtml(t("publication.selectProjectFirst"))}</option>`;return}
  const versions=await api(`/v1/content-projects/${event.target.value}/versions`);
  const approved=versions.filter(item=>item.status==="approved");
  select.innerHTML=approved.length?approved.map(item=>`<option value="${item.id}">${escapeHtml(t("publication.versionOption",{number:item.version_number,summary:item.change_summary||t("publication.approvedContent")}))}</option>`).join(""):`<option value="">${escapeHtml(t("publication.noApprovedVersion"))}</option>`;
}));
$("#publication-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{
  const data=formData(event.target);
  data.published_at=new Date(data.published_at).toISOString();
  await api("/v1/publications",{method:"POST",body:JSON.stringify(data)});
  event.target.reset();
  await refresh();
},t("toast.publication.saved"))});
$$("[data-auth-mode]").forEach(button=>button.addEventListener("click",()=>{$$("[data-auth-mode]").forEach(x=>x.classList.toggle("active",x===button));$$("[data-auth-panel]").forEach(panel=>panel.hidden=panel.dataset.authPanel!==button.dataset.authMode)}));
document.addEventListener("click",event=>{
  const submit=event.target.closest("[data-submit-supply]");
  if(submit)request(async()=>{await api(`/v1/campaign-packages/${submit.dataset.campaign}/supply-snapshots/${submit.dataset.submitSupply}/submit`,{method:"POST"});await refresh();$("#supply-campaign-select").value=submit.dataset.campaign;await loadSupplySnapshots(submit.dataset.campaign)},t("supply.submitted"));
  const review=event.target.closest("[data-review-supply]");
  if(review){const rejected=review.dataset.status==="rejected";const note=prompt(t(rejected?"supply.rejectPrompt":"supply.reviewPrompt"),"");if(note!==null){if(rejected&&!note.trim()){toast(t("supply.rejectionNoteRequired"),true);return}request(async()=>{await api(`/v1/campaign-packages/${review.dataset.campaign}/supply-snapshots/${review.dataset.reviewSupply}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status,note})});await refresh();$("#supply-campaign-select").value=review.dataset.campaign;await loadSupplySnapshots(review.dataset.campaign)},t("supply.reviewed"))}}
});
document.addEventListener("click",event=>{const nav=event.target.closest("[data-page]");if(nav)navigate(nav.dataset.page);const jump=event.target.closest("[data-target]");if(jump)navigate(jump.dataset.target);const campaignGenerate=event.target.closest("[data-generate-campaign-item]");if(campaignGenerate)request(async()=>{await api(`/v1/content-projects/${campaignGenerate.dataset.generateCampaignItem}/generate`,{method:"POST"});await refresh()},t("campaign.generated"));const editProject=event.target.closest("[data-edit-project]");if(editProject){const project=state.projects.find(item=>item.id===editProject.dataset.editProject);const form=$("#project-form");["id","title","brand_id","product_id","content_type","platform","tone","target_audience","objective","extra_requirements"].forEach(name=>form.elements[name].value=project[name]||"");$("#project-form-title").textContent=t("form.project.edit");$("#project-save-button").textContent=t("form.project.saveChanges");$("#project-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editBrand=event.target.closest("[data-edit-brand]");if(editBrand){const brand=state.brands.find(item=>item.id===editBrand.dataset.editBrand);const form=$("#brand-form");["id","name","story","voice"].forEach(name=>form.elements[name].value=brand[name]||"");$("#brand-form-title").textContent=t("form.brand.edit");$("#brand-save-button").textContent=t("form.brand.saveChanges");$("#brand-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const editProduct=event.target.closest("[data-edit-product]");if(editProduct){const product=state.products.find(item=>item.id===editProduct.dataset.editProduct);const form=$("#product-form");["id","brand_id","name","origin","specification","price_display","shelf_life","storage_method"].forEach(name=>form.elements[name].value=product[name]||"");form.elements.selling_points.value=(product.selling_points||[]).join("\n");form.elements.prohibited_claims.value=(product.prohibited_claims||[]).join("\n");$("#product-form-title").textContent=t("form.product.edit");$("#product-save-button").textContent=t("form.product.saveChanges");$("#product-edit-cancel").hidden=false;form.scrollIntoView({behavior:"smooth",block:"start"})}const assetSubmit=event.target.closest("[data-submit-asset]");if(assetSubmit)request(async()=>{await api(`/v1/${assetSubmit.dataset.assetType}/${assetSubmit.dataset.submitAsset}/submit`,{method:"POST"});await refresh()},t("toast.asset.submitted"));const assetReview=event.target.closest("[data-review-asset]");if(assetReview){const note=prompt(t(assetReview.dataset.status==="rejected"?"asset.rejectPrompt":"asset.reviewPrompt"),"");if(note!==null)request(async()=>{await api(`/v1/${assetReview.dataset.assetType}/${assetReview.dataset.reviewAsset}/review`,{method:"POST",body:JSON.stringify({status:assetReview.dataset.status,note})});await refresh()},t("toast.asset.reviewUpdated"))}const revise=event.target.closest("[data-revise-source]");if(revise){const source=state.knowledge.find(item=>item.id===revise.dataset.reviseSource);const form=$("#knowledge-form");["title","kind","content","citation_label","source_filename","media_type","brand_id","product_id"].forEach(name=>{if(form.elements[name])form.elements[name].value=source[name]||""});form.elements.parent_source_id.value=source.id;$("#knowledge-change-field").hidden=false;$("#knowledge-revision-cancel").hidden=false;$("#knowledge-save-button").textContent=t("source.saveRevisionDraft",{number:(source.revision_number||1)+1});form.elements.change_summary.focus();form.scrollIntoView({behavior:"smooth",block:"start"})}const sourceSubmit=event.target.closest("[data-submit-source]");if(sourceSubmit)request(async()=>{await api(`/v1/knowledge/${sourceSubmit.dataset.submitSource}/submit`,{method:"POST"});await refresh()},t("toast.source.submitted"));const review=event.target.closest("[data-review-source]");if(review){const note=prompt(t(review.dataset.status==="rejected"?"source.rejectPrompt":"source.reviewPrompt"),"");if(note!==null)request(async()=>{await api(`/v1/knowledge/${review.dataset.reviewSource}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status,note})});await refresh()},t("toast.source.reviewUpdated"))};const submit=event.target.closest("[data-submit-version]");if(submit)request(async()=>{await api(`/v1/content-projects/${submit.dataset.project}/versions/${submit.dataset.submitVersion}/submit`,{method:"POST"});state.versions=await api(`/v1/content-projects/${submit.dataset.project}/versions`);renderReviews(submit.dataset.project)},t("toast.contentReview.submitted"));const versionReview=event.target.closest("[data-review-version]");if(versionReview){const noteField=document.querySelector(`[data-review-note="${versionReview.dataset.reviewVersion}"]`);const note=(noteField?.value||"").trim();if(versionReview.dataset.status==="rejected"&&!note){toast(t("contentReview.rejectionNoteRequired"),true);noteField?.focus();return}request(async()=>{await api(`/v1/content-projects/${versionReview.dataset.project}/versions/${versionReview.dataset.reviewVersion}/review`,{method:"POST",body:JSON.stringify({status:versionReview.dataset.status,note})});state.versions=await api(`/v1/content-projects/${versionReview.dataset.project}/versions`);renderReviews(versionReview.dataset.project)},t("toast.contentReview.updated"))}});
document.addEventListener("input",event=>{const field=event.target.closest("[data-review-note]");if(field){const counter=document.querySelector(`[data-review-count="${field.dataset.reviewNote}"]`);if(counter)counter.textContent=field.value.length}});
document.addEventListener("change",event=>{const select=event.target.closest("[data-member-role]");if(select)request(async()=>{await api(`/v1/members/${select.dataset.memberRole}`,{method:"PATCH",body:JSON.stringify({role:select.value})});await refresh()},t("toast.member.roleUpdated"))});
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
window.addEventListener("popstate",()=>navigate(pageFromLocation(),false));
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

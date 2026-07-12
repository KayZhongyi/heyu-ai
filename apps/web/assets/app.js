const state={token:localStorage.getItem("heyu_token")||"",brands:[],products:[],knowledge:[],projects:[],versions:[]};
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const api=async(path,options={})=>{const headers={"Content-Type":"application/json",...(options.headers||{})};if(state.token)headers.Authorization=`Bearer ${state.token}`;const response=await fetch(path,{...options,headers});if(!response.ok){let message=`请求失败 (${response.status})`;try{const body=await response.json();message=body.detail||message}catch{}throw new Error(message)}return response.status===204?null:response.json()};
const formData=form=>Object.fromEntries(new FormData(form));
const lines=value=>value.split("\n").map(v=>v.trim()).filter(Boolean);
const toast=(message,error=false)=>{const el=$("#toast");el.textContent=message;el.className=`show${error?" error":""}`;clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.className="",3000)};
const escapeHtml=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const request=async(fn,success)=>{try{await fn();if(success)toast(success)}catch(error){toast(error.message,true)}};

function showWorkspace(){
  $("#auth-view").hidden=Boolean(state.token);$("#workspace").hidden=!state.token;$("#logout").hidden=!state.token;
  if(state.token) refresh();
}
function navigate(page){
  $$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.page===page));
  $$(".page").forEach(x=>x.classList.toggle("active",x.dataset.pagePanel===page));
  const titles={overview:"经营概览",assets:"品牌与农产品",knowledge:"可信知识库",studio:"内容创作台",review:"审核与版本"};
  $("#page-title").textContent=titles[page];
}
async function refresh(){
  [state.brands,state.products,state.knowledge,state.projects]=await Promise.all([api("/v1/brands"),api("/v1/products"),api("/v1/knowledge"),api("/v1/content-projects")]);
  render();
}
function options(items,placeholder){
  return `<option value="">${placeholder}</option>`+items.map(x=>`<option value="${x.id}">${escapeHtml(x.name||x.title)}</option>`).join("");
}
function render(){
  $("#brand-count").textContent=state.brands.length;$("#product-count").textContent=state.products.length;
  $("#knowledge-count").textContent=state.knowledge.filter(x=>x.status==="approved").length;$("#project-count").textContent=state.projects.length;
  $$(".brand-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.brands,"请选择品牌");x.value=value});
  $$(".product-select").forEach(x=>{const value=x.value;x.innerHTML=options(state.products,"请选择产品");x.value=value});
  $("#project-select").innerHTML=options(state.projects,"请选择内容任务");
  $("#asset-list").innerHTML=[...state.brands.map(b=>`<article><span class="pill">品牌</span><h3>${escapeHtml(b.name)}</h3><p>${escapeHtml(b.story||"尚未填写品牌故事")}</p></article>`),...state.products.map(p=>`<article><span class="pill">农产品</span><h3>${escapeHtml(p.name)}</h3><p>${escapeHtml(p.origin||"产地待补充")} · ${escapeHtml(p.specification||"规格待补充")}</p></article>`)].join("")||"暂无品牌与产品";
  $("#knowledge-list").innerHTML=state.knowledge.map(k=>`<article><h3>${escapeHtml(k.title)}</h3><p>${escapeHtml(k.content.slice(0,130))}</p><span class="badge ${k.status}">${k.status}</span>${k.status!=="approved"?`<div class="row-actions"><button class="approve" data-review-source="${k.id}" data-status="approved">审核通过</button><button class="reject" data-review-source="${k.id}" data-status="rejected">驳回</button></div>`:""}</article>`).join("")||"暂无知识资料";
}

$("#bootstrap-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);const result=await api("/v1/auth/bootstrap",{method:"POST",body:JSON.stringify(data)});state.token=result.access_token;localStorage.setItem("heyu_token",state.token);showWorkspace()},"本地工作空间已创建")});
$("#brand-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/brands",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"品牌已保存")});
$("#product-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);data.selling_points=lines(data.selling_points);data.prohibited_claims=lines(data.prohibited_claims);await api("/v1/products",{method:"POST",body:JSON.stringify(data)});event.target.reset();await refresh()},"产品已保存")});
$("#knowledge-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{const data=formData(event.target);data.brand_id=data.brand_id||null;data.product_id=data.product_id||null;await api("/v1/knowledge",{method:"POST",body:JSON.stringify(data)});event.target.reset();await refresh()},"知识资料已保存，请进行审核")});
$("#project-form").addEventListener("submit",event=>{event.preventDefault();request(async()=>{await api("/v1/content-projects",{method:"POST",body:JSON.stringify(formData(event.target))});event.target.reset();await refresh()},"内容任务已创建")});
$("#generate-button").addEventListener("click",()=>request(async()=>{const id=$("#project-select").value;if(!id)throw new Error("请先选择内容任务");const result=await api(`/v1/content-projects/${id}/generate`,{method:"POST"});$("#generation-output").textContent=JSON.stringify(result.version.content,null,2);state.versions=await api(`/v1/content-projects/${id}/versions`);renderReviews(id)},"内容已生成并进入审核"));
document.addEventListener("click",event=>{const nav=event.target.closest("[data-page]");if(nav)navigate(nav.dataset.page);const jump=event.target.closest("[data-target]");if(jump)navigate(jump.dataset.target);const review=event.target.closest("[data-review-source]");if(review)request(async()=>{await api(`/v1/knowledge/${review.dataset.reviewSource}/review`,{method:"POST",body:JSON.stringify({status:review.dataset.status})});await refresh()},"资料审核状态已更新");const versionReview=event.target.closest("[data-review-version]");if(versionReview)request(async()=>{await api(`/v1/content-projects/${versionReview.dataset.project}/versions/${versionReview.dataset.reviewVersion}/review`,{method:"POST",body:JSON.stringify({status:versionReview.dataset.status,note:"由禾语工作台审核"})});state.versions=await api(`/v1/content-projects/${versionReview.dataset.project}/versions`);renderReviews(versionReview.dataset.project)},"内容审核状态已更新")});
async function renderReviews(selectedId){
  if(!selectedId&&state.projects.length)selectedId=state.projects[0].id;
  if(selectedId)state.versions=await api(`/v1/content-projects/${selectedId}/versions`);
  $("#review-list").innerHTML=state.versions.map(v=>`<article><h3>版本 ${v.version_number} · ${escapeHtml(v.change_summary||"AI 初稿")}</h3><p>${escapeHtml(JSON.stringify(v.content).slice(0,220))}</p><span class="badge ${v.status}">${v.status}</span>${v.status!=="approved"?`<div class="row-actions"><button class="approve" data-review-version="${v.id}" data-project="${v.project_id}" data-status="approved">审核通过</button><button class="reject" data-review-version="${v.id}" data-project="${v.project_id}" data-status="rejected">驳回</button></div>`:""}</article>`).join("")||"暂无待审核内容";
}
$("#logout").addEventListener("click",()=>{localStorage.removeItem("heyu_token");state.token="";location.reload()});
$$(".jump").forEach(x=>x.addEventListener("click",()=>navigate(x.dataset.target)));
showWorkspace();

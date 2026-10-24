const state={network:null,model:null,pf:null,sc:{max:null,min:null},zones:[],paths:[],relayLibrary:null,currentZone:'Z-R11',currentPath:'PATH-MB0',tccScope:'master',tccMode:'phase',tccView:'mb0',generalFocus:'all',scCase:'max',dataSection:'cables',tccTheme:'etap',tccGrid:false,tccSingleLine:true,lastTCC:null,tccEdits:{},tccLiveZone:null,review:null,reviewCase:'caso1',expertPath:'PATH-MB0',expertStep:0,expertShowAll:false,expertData:null};
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const fmt=(v,d=3)=>v==null||v===''||Number.isNaN(Number(v))?'—':Number(v).toFixed(d);
const pt=(v,d=3)=>v==null||v===''||Number.isNaN(Number(v))?'—':Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const valNum=id=>{const e=$(id);if(!e)return null;const v=e.value.trim();return v===''?null:Number(v)};
const toast=msg=>{const t=$('#toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2600)};
async function api(url,opts={}){const r=await fetch(url,opts);let j={};try{j=await r.json()}catch{}if(!r.ok)throw new Error(j.error||`Erro HTTP ${r.status}`);return j}

const viewMeta={
 dashboard:['Dashboard','Caso: 13,8/6,6kV — visão geral'],data:['Modelo físico','Dados do caso atual — somente leitura'],singleline:['Unifilar','Topologia reduzida usada no Pandapower'],powerflow:['Fluxo de potência','Resultados calculados pelo Pandapower'],shortcircuit:['Curto-circuito','IEC 60909 — MAX e MIN'],protection:['Ajustes 50/51','OC1 editável + correntes calculadas pelo estudo'],tcc:['Coordenogramas','Quatro vistas montadas após fluxo, curto e ajustes'],manual:['Cálculo 51','Seis curvas, TC, múltiplo M e tempo de atuação'],expert:['Módulo especialista','Verificação de coordenação e banda do motor']};
// Navegação móvel: abre um painel lateral sem reduzir o unifilar.
const mobileNavToggle=$('#mobile-nav-toggle');
const mobileNavClose=$('#mobile-nav-close');
const mobileNavBackdrop=$('#mobile-nav-backdrop');
const sidebar=$('#site-sidebar');
function setMobileNavOpen(open){
 const visible=Boolean(open)&&window.innerWidth<=720;
 sidebar?.classList.toggle('mobile-open',visible);
 mobileNavBackdrop?.classList.toggle('is-open',visible);
 mobileNavToggle?.setAttribute('aria-expanded',String(visible));
 mobileNavToggle?.setAttribute('aria-label',visible?'Fechar menu':'Abrir menu');
 document.body.classList.toggle('mobile-nav-open',visible);
}
if(mobileNavToggle)mobileNavToggle.addEventListener('click',()=>setMobileNavOpen(!sidebar?.classList.contains('mobile-open')));
if(mobileNavClose)mobileNavClose.addEventListener('click',()=>setMobileNavOpen(false));
if(mobileNavBackdrop)mobileNavBackdrop.addEventListener('click',()=>setMobileNavOpen(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape')setMobileNavOpen(false)});
let mobileResizeTimer;
window.addEventListener('resize',()=>{
 if(window.innerWidth>720)setMobileNavOpen(false);
 clearTimeout(mobileResizeTimer);
 mobileResizeTimer=setTimeout(()=>{
  if(typeof Plotly==='undefined'||!Plotly.Plots?.resize)return;
  document.querySelectorAll('.view.active .js-plotly-plot').forEach(el=>{
   try{Plotly.Plots.resize(el)}catch(err){console.warn('Redimensionamento do gráfico',err)}
  });
 },180);
});
$$('.nav-btn').forEach(b=>b.onclick=()=>showView(b.dataset.view));
function showView(v){setMobileNavOpen(false);$$('.nav-btn').forEach(x=>x.classList.toggle('active',x.dataset.view===v));$$('.view').forEach(x=>x.classList.toggle('active',x.id===`view-${v}`));$('#page-title').textContent=viewMeta[v][0];$('#page-subtitle').textContent=viewMeta[v][1];if(v==='data')renderDataViewer();if(v==='singleline')renderSingleLine();if(v==='powerflow')loadPF();if(v==='shortcircuit')loadSC(state.scCase);if(v==='protection')loadZones();if(v==='tcc')loadTCC();if(v==='manual')loadManual();if(v==='expert')loadExpert()}
// Curto novo invalida tudo que foi derivado dele: as tabelas de
// fluxo e de curto, os dados do especialista, a verificação em
// cascata e a última folha de coordenograma desenhada. Guardar
// qualquer um deles depois de recalcular deixaria número velho na
// tela ao lado de número novo.
function invalidateDerivedState(){state.pf=null;state.sc={max:null,min:null};state.expertData=null;state.review=null;state.lastTCC=null}
// Redesenha a tela que está aberta agora. Cada tela só se remontava ao ser
// aberta pelo menu, então recalcular o curto com o coordenograma na frente
// deixava o desenho antigo no lugar — era preciso trocar de aba e voltar.
async function reloadActiveView(){
 const v=document.querySelector('.view.active')?.id.replace('view-','');
 if(v==='powerflow')await loadPF();
 else if(v==='shortcircuit')await loadSC(state.scCase);
 else if(v==='protection')await loadZones();
 else if(v==='tcc')await loadTCC();
 else if(v==='manual')await loadManual();
 else if(v==='expert')await loadExpert();
 return v;
}
$('#recalc-btn').onclick=async()=>{const b=$('#recalc-btn');b.disabled=true;b.textContent='Calculando…';toast('Recalculando sistema elétrico…');try{const d=await api('/api/recalculate',{method:'POST'});invalidateDerivedState();await loadSummary();const v=await reloadActiveView();toast(`Sistema recalculado em ${pt(d.elapsed_s,2)} s`+(v==='tcc'?' · coordenograma redesenhado':' · cache pronto'))}catch(e){toast(e.message)}finally{b.disabled=false;b.textContent='Recalcular sistema'}};
$('#print-btn').onclick=()=>window.print();

async function init(){[state.network,state.model]=await Promise.all([api('/api/network'),api('/api/model')]);const [zd,pd,rl,es]=await Promise.all([api('/api/zones'),api('/api/paths'),api('/api/relay-library'),api('/api/equipment-schema')]);state.zones=zd.zones;state.paths=pd.paths;state.relayLibrary=rl;state.equipmentSchema=es;if(!state.zones.find(z=>z.id===state.currentZone))state.currentZone=state.zones[0]?.id;if(!state.paths.find(p=>p.id===state.currentPath))state.currentPath=state.paths[0]?.id;updateModelMetrics();populateZoneSelects();bindConciseTCC();bindDataTabs();renderSingleLine();await loadSummary()}
async function refreshAfterEquipmentChange(){invalidateDerivedState();[state.network,state.model]=await Promise.all([api('/api/network'),api('/api/model')]);state.zones=(await api('/api/zones')).zones;updateModelMetrics();await renderDataViewer();renderSingleLine();await loadSummary();await reloadActiveView()}
function updateModelMetrics(){const n=state.network;if(!n)return;$('#metric-buses').textContent=n.buses.length;$('#metric-gen').textContent=pt(n.generators.reduce((a,g)=>a+Number(g.sn_mva||0),0),2);$('#metric-motors').textContent=n.motors.length;$('#metric-trafo').textContent=n.transformers.length;$('#metric-trafo-sub').textContent=n.transformers.map(t=>`${t.name} ${t.sn_mva} MVA`).join(' · ')}
async function loadSummary(){const s=await api('/api/summary');const ok=s.powerflow_ok&&s.sc_max_ok&&s.sc_min_ok,c=s.cache||{};$('#solver-status').textContent=ok?'Já calculado':(s.powerflow_error?'Motor de cálculo indisponível':'Cálculo parcial');$('#solver-status').className=`pill ${ok?'info':'warn'}`;$('#summary-cards').classList.remove('skeleton');$('#summary-cards').innerHTML=`<div class="summary-row"><span>Energia (fluxo de potência)</span><b class="${s.powerflow_ok?'oktxt':'warntxt'}">${s.powerflow_ok?'calculado':'indisponível'}</b></div><div class="summary-row"><span>Menor tensão do sistema</span><b>${s.min_voltage?`${s.min_voltage.bus} · ${fmt(s.min_voltage.vm_pu,5)} pu`:'—'}</b></div><div class="summary-row"><span>Maior corrente de curto-circuito</span><b>${s.max_sc?`${s.max_sc.bus} · ${fmt(s.max_sc.ka,3)} kA`:'—'}</b></div><div class="summary-row"><span>Cenários calculados</span><b>${s.sc_max_ok?'com motores ✓':'com motores parcial'} · ${s.sc_min_ok?'sem motores ✓':'sem motores parcial'}</b></div><div class="summary-row"><span>Situação do cálculo</span><b>${c.powerflow_cached?'energia ✓':'energia —'} · ${Number(c.shortcircuit_cases_cached||0)}/2 cenários de curto</b></div>${s.powerflow_error?`<div class="notice"><b>Ambiente:</b> ${esc(s.powerflow_error)}</div>`:''}`}

// -------- MODELO FÍSICO --------
const dataCfg={
 cables:{title:'Cabos',sub:'Dados físicos do unifilar. R de fluxo e R a 20 °C do curto ficam separados.',fields:[['name','Cabo'],['from_bus','De'],['to_bus','Para'],['library','Biblioteca'],['size_mm2','mm²'],['length_m','m'],['parallel','Paralelos'],['r1_pf_ohm_per_km','R1 fluxo Ω/km'],['x1_pf_ohm_per_km','X1 Ω/km'],['r0_pf_ohm_per_km','R0 fluxo Ω/km'],['x0_pf_ohm_per_km','X0 Ω/km'],['ampacity_total_a','Ampacidade']]},
 motors:{title:'Motores',sub:'Dados físicos dos motores usados no fluxo/curto e nas referências de partida do TCC.',fields:[['name','Motor'],['bus','Barra'],['kw','kW'],['kva','kVA'],['kv','kV'],['amp','In [A]'],['pf','FP'],['lrc_percent','LRC [%]'],['locked_rotor_current_a','ILR [A]'],['start_time_s','Acel. 100% Vt [s]'],['stall_hot_s','Hot Stall [s]'],['stall_cold_s','Cold Stall [s]'],['asym_locked_rotor_factor','LRC assim.']]},
 generators:{title:'Gerador',sub:'Gerador síncrono do caso reduzido e parâmetros de sequência.',fields:[['name','Gerador'],['bus','Barra'],['p_rated_mw','MW'],['sn_mva','MVA'],['kv','kV'],['pf','FP'],['xdss_pu','Xd” [pu]'],['x_over_r','X/R'],['x0_pu','X0 [pu]'],['x2_pu','X2 [pu]'],['neutral_current_a','Neutro [A]']]},
 transformers:{title:'Transformadores',sub:'T1 usado no fluxo, curto e coordenograma dedicado. Inrush = 8 pu / 1 ciclo conforme dado original.',fields:[['name','Trafo'],['hv_bus','AT'],['lv_bus','BT'],['sn_mva','MVA'],['vn_hv_kv','AT [kV]'],['vn_lv_kv','BT [kV]'],['vk_percent','Z [%]'],['x_over_r','X/R'],['vector_group','Grupo'],['inrush_pu','Inrush [pu]'],['inrush_time_s','t [s]'],['inrush_primary_a','I inrush [A]']]},
 cts:{title:'TCs',sub:'Transformador de corrente como equipamento próprio — cada relé só referencia um TC daqui.',fields:[['name','TC'],['location','Local'],['primary_a','Primário [A]'],['secondary_a','Secundário [A]']]},
 buses:{title:'Barras',sub:'Cinco barras do caso reduzido atual.',fields:[['name','Barra'],['kv','kV'],['role','Função']]},
 switchgear:{title:'Proteções no unifilar',sub:'Identificadores de CB/relé. Ratings reais ainda não foram exportados.',fields:[['breaker','Disjuntor'],['relay','Relé'],['from_bus','De'],['to_bus','Para'],['device','Circuito']]}
};
const EDITABLE_CATEGORIES=new Set(['motors','generators','transformers','cables','cts']);
function bindDataTabs(){$$('.data-tab').forEach(b=>b.onclick=()=>{state.dataSection=b.dataset.section;$$('.data-tab').forEach(x=>x.classList.toggle('active',x===b));renderDataViewer()})}
function readonly(v){if(v==null||v==='')return '<span class="muted">não informado</span>';if(typeof v==='number')return `<span class="readonly-value">${esc(v.toLocaleString('pt-BR',{maximumFractionDigits:6}))}</span>`;return `<span class="readonly-value">${esc(v)}</span>`}
async function renderDataViewer(){
 const cfg=dataCfg[state.dataSection];if(!cfg)return;
 $('#data-editor-title').textContent=cfg.title;$('#data-editor-subtitle').textContent=cfg.sub;
 const rows=state.network[state.dataSection]||state.model[state.dataSection]||[];
 const badge=$('#data-editor-badge');
 if(EDITABLE_CATEGORIES.has(state.dataSection)){
  if(badge){badge.textContent='editável';badge.className='pill warn'}
  const schema=(state.equipmentSchema||{})[state.dataSection]||[];
  let overrides={};
  try{overrides=(await api('/api/equipment-overrides'))[state.dataSection]||{}}catch(e){}
  $('#data-editor').innerHTML=rows.map(r=>equipmentCardHtml(state.dataSection,r,schema,overrides[r.name])).join('')||'<div class="empty-state">Nenhum equipamento nesta categoria.</div>';
  bindEquipmentCards(state.dataSection,schema);
 }else{
  if(badge){badge.textContent='fixo';badge.className='pill'}
  $('#data-editor').innerHTML=`<div class="table-wrap data-table-wrap"><table class="edit-table readonly-table"><thead><tr>${cfg.fields.map(f=>`<th>${f[1]}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cfg.fields.map(f=>`<td>${readonly(r[f[0]])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
 }
}
function equipmentFieldHtml(f,item){
 const val=item[f.key];
 const unit=f.unit?` <small>[${esc(f.unit)}]</small>`:'';
 if(f.type==='bool'){
  const on=val!==false;
  return `<label class="eq-switch">${esc(f.label)}<select data-field="${f.key}"><option value="1" ${on?'selected':''}>Em serviço</option><option value="0" ${on?'':'selected'}>Fora de serviço</option></select></label>`;
 }
 if(f.type==='select'){
  const opts=(f.options||[]).map(o=>`<option value="${esc(o)}" ${o===val?'selected':''}>${esc(o)}</option>`).join('');
  return `<label>${esc(f.label)}${unit}<select data-field="${f.key}">${opts}</select></label>`;
 }
 const step=f.type==='int'?'1':'any';
 return `<label>${esc(f.label)}${unit}<input data-field="${f.key}" type="number" step="${step}" ${'min' in f?`min="${f.min}"`:''} ${'max' in f?`max="${f.max}"`:''} value="${val??''}"></label>`;
}
function equipmentCardHtml(category,item,schema,override){
 const modified=!!override;
 const subtitle=item.bus||[item.from_bus,item.to_bus].filter(Boolean).join(' → ')||[item.hv_bus,item.lv_bus].filter(Boolean).join(' → ')||item.location||'';
 return `<article class="card equipment-card" data-equip="${esc(item.name)}">
   <div class="card-head"><div><h3>${esc(item.name)}</h3><p>${esc(subtitle)}</p></div><span class="pill ${modified?'warn':'info'}">${modified?'editado':'original'}</span></div>
   <div class="protection-form-grid">${schema.map(f=>equipmentFieldHtml(f,item)).join('')}</div>
   <div class="detail-actions">
     <button class="btn primary eq-save" data-category="${category}" data-name="${esc(item.name)}">Salvar e recalcular</button>
     <button class="btn secondary eq-reset" data-category="${category}" data-name="${esc(item.name)}" ${modified?'':'disabled'}>Restaurar</button>
   </div>
 </article>`;
}
function bindEquipmentCards(category,schema){
 $$('.eq-save').forEach(b=>b.onclick=async()=>{
  const card=b.closest('.equipment-card');
  const payload={};
  schema.forEach(f=>{const el=card.querySelector(`[data-field="${f.key}"]`);if(!el)return;payload[f.key]=f.type==='select'?el.value:(f.type==='bool'?el.value==='1':Number(el.value))});
  const resetBtn=card.querySelector('.eq-reset');
  b.disabled=true;if(resetBtn)resetBtn.disabled=true;const orig=b.textContent;b.textContent='Recalculando…';
  try{
   await api(`/api/equipment/${category}/${encodeURIComponent(b.dataset.name)}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   toast('Equipamento atualizado · sistema elétrico recalculado');
   await refreshAfterEquipmentChange();
  }catch(e){toast(e.message);b.disabled=false;if(resetBtn)resetBtn.disabled=false;b.textContent=orig}
 });
 $$('.eq-reset').forEach(b=>{if(b.disabled)return;b.onclick=async()=>{
  b.disabled=true;const orig=b.textContent;b.textContent='Restaurando…';
  try{
   await api(`/api/equipment/${category}/${encodeURIComponent(b.dataset.name)}/reset`,{method:'POST'});
   toast('Valores originais restaurados · sistema recalculado');
   await refreshAfterEquipmentChange();
  }catch(e){toast(e.message);b.disabled=false;b.textContent=orig}
 }});
}

// -------- FLUXO --------
async function loadPF(){if(!state.pf)state.pf=await api('/api/powerflow');const d=state.pf;$('#pf-source').textContent=d.source||'Pandapower';if(!d.ok){$('#pf-chart').innerHTML=`<div class="empty-state"><b>Fluxo não executado neste ambiente.</b><br>${esc(d.error||'')}</div>`;$('#pf-table').innerHTML='';$('#generator-results').innerHTML='<div class="notice">Instale as dependências pelo setup_windows.bat e recalcule.</div>';return}const rows=d.buses;Plotly.react('pf-chart',[{x:rows.map(x=>x.bus),y:rows.map(x=>x.vm_pu),name:'Tensão',type:'scatter',mode:'lines+markers',line:{width:3},marker:{size:8}}],plotLayout('Perfil de tensão','Barra','V [pu]',{yaxis:{range:[Math.min(.94,...rows.map(x=>x.vm_pu))*.995,1.01]}}),plotConfig());$('#pf-table').innerHTML=rows.map(r=>`<tr><td>${r.bus}</td><td>${fmt(r.kv,2)}</td><td>${fmt(r.vm_pu,5)}</td><td>${fmt(r.vm_percent,3)}</td><td>${fmt(r.va_degree,2)}</td></tr>`).join('');$('#generator-results').innerHTML=d.generators.map(g=>`<div class="summary-row"><span>${g.name}</span><b>${fmt(g.p_mw,3)} MW · ${fmt(g.q_mvar,3)} MVAr</b></div>`).join('')}

// -------- CURTO --------
$$('.sc-case').forEach(b=>b.onclick=()=>{state.scCase=b.dataset.case;$$('.sc-case').forEach(x=>x.classList.toggle('active',x===b));loadSC(state.scCase)});$('#sc-fault').onchange=renderSC;
async function getSC(c){if(!state.sc[c])state.sc[c]=await api(`/api/shortcircuit?case=${c}`);return state.sc[c]}
async function loadSC(c){await getSC(c);renderSC()}
function renderSC(){const d=state.sc[state.scCase];if(!d)return;$('#sc-note').textContent=d.note||'';const key=$('#sc-fault').value,field=`${key}_ka`,valid=d.rows.filter(r=>r[field]!=null);if(valid.length)Plotly.react('sc-chart',[{x:valid.map(r=>r.bus),y:valid.map(r=>r[field]),type:'bar',name:'Pandapower'}],plotLayout(`${key.toUpperCase()} — ${state.scCase.toUpperCase()}`,'Barra','Corrente [kA]'),plotConfig());else $('#sc-chart').innerHTML=`<div class="empty-state">Resultado ${key.toUpperCase()} indisponível.${d.errors?.length?'<br>'+esc(d.errors.join(' | ')):''}</div>`;const sorted=[...valid].sort((a,b)=>b[field]-a[field]);$('#sc-kpis').innerHTML=sorted.length?`<div class="summary-row"><span>Maior</span><b>${sorted[0].bus} · ${fmt(sorted[0][field])} kA</b></div><div class="summary-row"><span>Menor</span><b>${sorted.at(-1).bus} · ${fmt(sorted.at(-1)[field])} kA</b></div><div class="summary-row"><span>Cenário</span><b>${state.scCase==='max'?'motores incluídos':'motores excluídos'}</b></div>`:`<div class="notice">Sem dados para este tipo de falta.</div>`;$('#sc-table').innerHTML=d.rows.map(r=>`<tr><td>${r.bus}</td><td>${fmt(r['3f_ka'])}</td><td>${fmt(r.ll_ka)}</td><td>${fmt(r.lg_ka)}</td><td>${fmt(r.llg_ka)}</td></tr>`).join('')}

// -------- PROTEÇÃO / TCC --------
const curveOptions=()=>Object.entries(state.relayLibrary?.curves||{}).map(([k,c])=>`<option value="${k}">${esc(c.label)}</option>`).join('');
function populateZoneSelects(){
 const opts=state.zones.map(z=>`<option value="${z.id}">${z.relay} · ${z.title.replace(z.relay+' · ','')}</option>`).join('');
 $('#manual-zone').innerHTML=opts;$('#manual-zone').value=state.currentZone;
 $('#manual-zone').onchange=e=>{state.currentZone=e.target.value;loadManual()};
}
function bindConciseTCC(){
 $$('#tcc-simple-tabs [data-tcc-view]').forEach(b=>b.onclick=()=>{state.tccView=b.dataset.tccView;$$('#tcc-simple-tabs [data-tcc-view]').forEach(x=>x.classList.toggle('active',x===b));loadTCC()});
 const redraw=()=>{if(state.lastTCC)renderConciseTCC(state.lastTCC,{keepPanel:true})};
 const th=$('#tcc-theme'); if(th)th.onchange=()=>{state.tccTheme=th.value;redraw()};
 const gr=$('#tcc-grid'); if(gr)gr.onchange=()=>{state.tccGrid=gr.checked;redraw()};
 const slb=$('#tcc-singleline'); if(slb)slb.onchange=()=>{state.tccSingleLine=slb.checked;redraw()};
 const png=$('#tcc-png'); if(png)png.onclick=()=>{
  const name=`TCC_${state.tccView}_${new Date().toISOString().slice(0,10)}`;
  // Mesma proporção da folha em tela (quase retrato, como o Star do ETAP);
  // antes o PNG saía 1400x1000 e não batia com o que o usuário via.
  Plotly.downloadImage('tcc-chart',{format:'png',width:1000,height:1080,scale:2,filename:name});
 };
}
function syncTCCScope(){const path=state.tccScope==='path',master=state.tccScope==='master';$('#tcc-path-label').classList.toggle('hidden',!path);$('#tcc-zone-label').classList.toggle('hidden',master);$('#tcc-reference').disabled=state.tccScope==='local'}
async function loadZones(){
 state.zones=(await api('/api/zones')).zones;
 const order=['Z-R1','Z-R10','Z-R12','Z-R11','Z-R3'];
 const zones=[...state.zones].sort((a,b)=>order.indexOf(a.id)-order.indexOf(b.id));
 $('#zone-list').innerHTML=zones.map(z=>`<button class="zone-item ${z.id===state.currentZone?'active':''}" data-zone="${z.id}"><b>${esc(z.relay)}</b><span>${esc(z.title.replace(z.relay+' · ',''))}</span><small>${pt(z.kv,1)} kV · TC ${pt(z.settings.ct_primary_a,0)}/${pt(z.settings.ct_secondary_a,0)}</small></button>`).join('');
 $$('.zone-item').forEach(b=>b.onclick=()=>{state.currentZone=b.dataset.zone;loadZones()});
 renderProtectionEditor();
}
async function renderProtectionEditor(){
 const z=state.zones.find(x=>x.id===state.currentZone);if(!z)return;
 $('#protection-editor').innerHTML='<div class="empty-state">Lendo ajustes e curto-circuito…</div>';
 const d=await api(`/api/protection-context/${z.id}`),s=d.settings,f=d.faults||{},c=d.calculations||{},p=d.physical||{};
 const curves=Object.entries(state.relayLibrary?.curves||{}).map(([k,v])=>`<option value="${k}" ${k===s.phase_curve?'selected':''}>${esc(v.label)}</option>`).join('');
 const op=x=>x&&x.current_a!=null?`${pt(x.current_a,1)} A · ${x.stage?esc(x.stage):'não atua'}${x.time_s!=null?` · ${pt(x.time_s,4)} s`:''}`:'—';
 const setcalc=c.setting||{};
 const calcLine=(label,x)=>x&&x.current_a!=null?`<div class="formula-row"><span>${label}</span><b>I=${pt(x.current_a,1)} A · M=${pt(x.multiple_51,3)} · t51=${x.time_51_s==null?'—':pt(x.time_51_s,4)+' s'} · efetivo=${esc(x.stage||'—')}${x.time_s==null?'':` / ${pt(x.time_s,4)} s`}</b></div>`:'';
 const physical=[];
 if(p.motor)physical.push(`<div><small>Motor</small><b>${esc(p.motor.name)}</b><span>In ${pt(p.motor.amp,2)} A · LRC ${pt(p.motor.locked_rotor_current_a,1)} A</span></div>`);
 if(p.transformer)physical.push(`<div><small>Transformador</small><b>${esc(p.transformer.name)}</b><span>${pt(p.transformer.sn_mva,1)} MVA · ${pt(p.transformer.vn_hv_kv,1)}/${pt(p.transformer.vn_lv_kv,1)} kV</span></div>`);
 if(p.cable)physical.push(`<div><small>Cabo</small><b>${esc(p.cable.name)}</b><span>${p.cable.parallel} × ${pt(p.cable.size_mm2,0)} mm² · ${pt(p.cable.length_m,0)} m${p.cable.thermal_k2s2_ka2s?` · K²S² ${pt(p.cable.thermal_k2s2_ka2s,2)} kA²s`:''}</span></div>`);
 $('#protection-editor').innerHTML=`
 <div class="expert-head"><div><span class="eyebrow">${esc(z.relay)} · ${pt(z.kv,1)} kV</span><h3>${esc(z.title)}</h3><p class="muted">Schneider Electric MiCOM P241 · OC1 atual (dado original)</p></div><span class="pill info">EDITÁVEL</span></div>
 <div class="expert-summary protection-chain-summary">
   <div><small>3F MAX calculado</small><b>${f['3f_max_a']!=null?`${pt(f['3f_max_a']/1000,3)} kA`:'—'}</b><span>${esc(f.fault_bus||'')} · ${esc(f.source_max||'')}${p.cable?.etap_sc_reference?.['3f_ka']?` · ref. original ${pt(p.cable.etap_sc_reference['3f_ka'],3)} kA`:''}</span></div>
   <div><small>Falta fase MIN</small><b>${f.phase_min_a!=null?`${pt(f.phase_min_a/1000,3)} kA`:'—'}</b><span>${esc(f.phase_min_fault||'')} · ${esc(f.source_min||'')}</span></div>
   <div><small>Sensibilidade Imin/Ip</small><b>${c.sensitivity!=null?pt(c.sensitivity,2):'—'}</b><span>calculada com pickup 51P</span></div>
   <div><small>Atuação em 3F MAX</small><b>${op(c.max)}</b><span>curva/50 conforme ajuste salvo</span></div>
 </div>
 <div class="protection-formula-card">
   <div class="formula-row"><span>TC / secundário</span><b>RTC=${pt(setcalc.ct_ratio,3)} · 51=${pt(setcalc.pickup_51_secondary_a,3)} A (${pt(setcalc.pickup_51_multiple_ct,3)}×In) · 50=${pt(setcalc.pickup_50_secondary_a,3)} A (${pt(setcalc.pickup_50_multiple_ct,3)}×In)</b></div>
   <div class="formula-row"><span>Curva 51</span><b>${esc(setcalc.formula||'—')} ${setcalc.constants?`· K=${setcalc.constants.K} · α=${setcalc.constants.alpha}`:''}</b></div>
   ${calcLine('3F MAX',c.max)}
   ${calcLine((f.phase_min_fault||'fase')+' MIN',c.min)}
   ${(setcalc.warnings||[]).map(w=>`<div class="formula-warning">⚠ ${esc(w)}</div>`).join('')}
 </div>
 <div class="protection-form-grid">
   <label>Função de fase<select id="pe-curve">${curves}</select></label>
   <label>TC primário [A] <small>(equipamento — <a href="#" data-editct="${esc(z.ct||'')}">editar TC</a>)</small><input type="number" value="${s.ct_primary_a??''}" disabled></label>
   <label>TC secundário [A] <small>(equipamento — <a href="#" data-editct="${esc(z.ct||'')}">editar TC</a>)</small><input type="number" value="${s.ct_secondary_a??''}" disabled></label>
   ${z.breaker?`<label>Disjuntor ${esc(z.breaker)} — interrupção nominal [kA]<input id="pe-bik" type="number" step="0.1" placeholder="informar do datasheet" value="${s.breaker_interrupt_ka??''}"></label>`:''}
   ${z.breaker?`<label>Disjuntor ${esc(z.breaker)} — tempo de abertura [s]<input id="pe-bopen" type="number" step="0.001" placeholder="informar do datasheet" value="${s.breaker_opening_time_s??''}"></label>`:''}
   <label>51P pickup primário [A]<input id="pe-p51" type="number" step="1" value="${s.phase_stage1_pickup_a??''}"></label>
   <label>TMS / Time Dial<input id="pe-tms" type="number" step="0.025" value="${s.phase_time_setting??''}"></label>
   <label>50P pickup primário [A]<input id="pe-p50" type="number" step="1" value="${s.phase_stage3_pickup_a??''}"></label>
   <label>50P delay [s]<input id="pe-d50" type="number" step="0.01" value="${s.phase_stage3_delay_s??0}"></label>
   ${p.cable?`<label>Ampacidade do cabo [A]<input id="pe-ampacity" type="number" step="1" placeholder="informar se conhecido" value="${s.cable_ampacity_a??''}"></label>`:''}
   ${p.cable?(p.cable.thermal_k2s2_ka2s?`<label>K²S² térmico (fabricante) [kA²s]<input type="number" value="${p.cable.thermal_k2s2_ka2s}" readonly></label>`:`<label>k adiabático [A√s/mm²]<input id="pe-k" type="number" step="1" value="${s.cable_k_adiabatic??''}"></label>`):''}
 </div>
 <div class="detail-actions"><button id="pe-save" class="btn primary">Salvar ajustes</button><button id="pe-reset" class="btn secondary">Restaurar</button><button id="pe-tcc" class="btn secondary">Abrir coordenograma</button></div>
 <div class="expert-section"><div class="card-head"><div><h3>Encadeamento do cálculo</h3><p>O TCC não inventa a corrente de curto.</p></div></div><div class="flow-diagram compact-flow"><span>Modelo físico</span><b>→</b><span>Fluxo</span><b>→</b><span>IEC 60909</span><b>→</b><span>50/51</span><b>→</b><span>TCC</span></div></div>
 ${physical.length?`<div class="expert-summary physical-mini">${physical.join('')}</div>`:''}`;
 $('#pe-save').onclick=async()=>{
   const payload={phase_curve:$('#pe-curve').value,phase_stage1_pickup_a:valNum('#pe-p51'),phase_time_setting:valNum('#pe-tms'),phase_stage3_pickup_a:valNum('#pe-p50'),phase_stage3_delay_s:valNum('#pe-d50')};
   if($('#pe-ampacity'))payload.cable_ampacity_a=valNum('#pe-ampacity'); if($('#pe-k'))payload.cable_k_adiabatic=valNum('#pe-k');
   if($('#pe-bik'))payload.breaker_interrupt_ka=valNum('#pe-bik'); if($('#pe-bopen'))payload.breaker_opening_time_s=valNum('#pe-bopen');
   await saveProtection(z.id,payload); await renderProtectionEditor(); toast('Ajustes salvos · Pandapower não recalculado');
 };
 $('#pe-reset').onclick=async()=>{await api(`/api/protection/${z.id}/reset`,{method:'POST'});state.zones=(await api('/api/zones')).zones;await renderProtectionEditor();toast('Ajustes originais restaurados · cache elétrico preservado')};
 $('#pe-tcc').onclick=()=>{state.tccView=z.id==='Z-R11'?'mb0':z.id==='Z-R3'?'mb6':(z.id==='Z-R10'||z.id==='Z-R12')?'t1':'general';showView('tcc');loadTCC()};
 $$('[data-editct]').forEach(a=>a.onclick=(ev)=>{ev.preventDefault();const ctName=a.dataset.editct;state.dataSection='cts';$$('.data-tab').forEach(x=>x.classList.toggle('active',x.dataset.section==='cts'));showView('data');setTimeout(()=>{const card=document.querySelector(`.equipment-card[data-equip="${CSS.escape(ctName)}"]`);if(card)card.scrollIntoView({behavior:'smooth',block:'center'})},80)});
}
async function saveProtection(zone,payload){const d=await api(`/api/protection/${zone}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});state.zones=(await api('/api/zones')).zones;if(state.network)state.network=await api('/api/network');return d}
// Ajustes que o usuário está digitando no painel ao lado da folha e ainda não
// mandou salvar. Chave = zona; valor = só os campos alterados.
function liveOverrides(){const o={};Object.entries(state.tccEdits||{}).forEach(([z,p])=>{if(p&&Object.keys(p).length)o[z]=p});return o}
// Com ajuste pendente a folha vem do endpoint de prévia; sem nada pendente,
// do endpoint normal. Nos dois casos o desenho sai do mesmo código do servidor.
function fetchTCC(view){
 const o=liveOverrides();
 return Object.keys(o).length
  ? api(`/api/tcc-concise/${view}/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({overrides:o})})
  : api(`/api/tcc-concise/${view}`);
}
async function loadTCC(){
 const view=state.tccView||'mb0';
 $$('#tcc-simple-tabs [data-tcc-view]').forEach(x=>x.classList.toggle('active',x.dataset.tccView===view));
 renderConciseTCC(await fetchTCC(view));
}
function renderConciseTCC(d,opts={}){
 state.lastTCC=d;
 // keepPanel: redesenho vindo da digitação — não remonta os campos, senão o
 // cursor salta do input a cada tecla.
 if(!opts.keepPanel)renderLivePanel(d);
 $('#tcc-zone-id').textContent=d.view==='general'?'SISTEMA':(d.view==='mb0'?'RAMAL M-B-0':(d.view==='mb6'?'RAMAL M-B-6':'TRANSFORMADOR T1'));
 $('#tcc-title').textContent=d.title;
 $('#tcc-subtitle').textContent=d.subtitle;
 $('#tcc-base-pill').textContent=`base ${pt(d.reference_kv,1)} kV`;

 const axis=d.etap_axis||{};
 const xr=d.x_range||[5,1e5], yr=d.y_range||[0.01,1000];
 // A banda vai para o começo da lista: ela é fundo e tem que ser desenhada
 // antes das curvas, senão cobre o traço do relé que é justamente o que se quer
 // olhar dentro dela.
 const all=(d.traces||[]).filter(Boolean);
 const src=[...all.filter(t=>t.kind==='motor_band'),...all.filter(t=>t.kind!=='motor_band')];
 const colors=etapColorMap(src);
 const dark=state.tccTheme==='dark';

 // --- traços -------------------------------------------------------------
 const widths={relay_effective:1.9,motor_thermal_exact:1.9,motor_thermal_hot:1.9,motor_thermal_cold:1.4,
  motor_start:1.9,cable:1.9,transformer_damage:1.9,transformer_damage_exact:1.9,generator_damage:1.9,
  ampacity:2.6,pickup_mark:2.6,fault_max:1.4,fault_min:1.4};
 const traces=src.map(t=>{
  const c=colors[etapDeviceKey(t)];
  if(t.kind==='motor_band')return {x:t.x,y:t.y,name:t.name,type:'scatter',mode:'lines',
   fill:'toself',fillcolor:dark?'rgba(79,209,197,.10)':'rgba(24,120,140,.09)',
   line:{width:0.8,color:dark?'rgba(79,209,197,.35)':'rgba(24,120,140,.30)',dash:'dot'},
   hoverinfo:'skip',showlegend:false};
  // V30: a curva de Hot Start é envoltória estimada a partir do tempo de stall,
  // não a curva exportada do fabricante — vai tracejada, como as demais estimativas.
  const dash=(t.kind==='motor_thermal_cold'||t.kind==='motor_thermal_hot'||t.kind==='transformer_damage'||t.kind==='generator_damage')?'dash':'solid';
  return {x:t.x,y:t.y,name:t.name,type:'scatter',mode:t.mode||'lines',
   line:{width:widths[t.kind]||1.7,color:c,dash,shape:'linear'},
   marker:t.kind==='inrush'?{size:9,symbol:'triangle-up',color:c}:{size:5,color:c},
   visible:t.visible??true,showlegend:false,
   hovertemplate:'I=%{x:,.1f} A<br>t=%{y:.4f} s<extra>'+esc(t.name)+'</extra>'};
 });

 // --- rótulos com seta (no lugar da legenda) ------------------------------
 const leaders=[],marks=[];
 src.forEach(t=>{
  if(t.kind==='motor_band')return;   // fundo, não recebe rótulo com seta
  const c=colors[etapDeviceKey(t)];
  if(t.mark==='top'){
   // O Star desenha a marca de pickup sem texto; só a ampacidade recebe rótulo.
   marks.push({x:t.x[0],y:Math.min(t.y[0],t.y[1]),color:c,place:'top',
    text:t.kind==='pickup_mark'?'':`${t.name}<br>${pt(t.value_a,1)} A`});
  }else if(t.mark==='bottom'){
   marks.push({x:t.x[0],y:Math.max(t.y[0],t.y[1]),text:t.name,color:c,place:'bottom',
    arrowFrom:Math.min(t.y[0],t.y[1]),ka:t.ka});
  }else if(t.kind==='inrush'){
   marks.push({x:t.x[0],y:t.y[0],text:t.name,color:c,place:'point'});
  }else{
   const a=etapAnchor(t,xr,yr);
   if(a)leaders.push({text:t.name,color:c,x:a.x,y:a.y});
  }
 });
 // Em eixo log o Plotly espera log10 nas coordenadas de anotação.
 const L=v=>Math.log10(v);
 // V29: o unifilar saiu do canto reservado dentro do gráfico e virou um painel
 // à parte (renderMiniSingleLine), então o espaço de rótulo à esquerda volta a
 // ser o mesmo dos dois lados — sem "esticar" as curvas pra abrir espaço.
 const reserveLeft=0.05;
 const ann=etapPlaceLabels(leaders,xr,yr,reserveLeft).map(l=>({
  x:L(l.x),y:L(l.y),ax:L(l.ax),ay:L(l.ay),xref:'x',yref:'y',axref:'x',ayref:'y',
  text:l.text,showarrow:true,arrowhead:2,arrowsize:1,arrowwidth:0.9,arrowcolor:dark?'#9fb3c8':'#555',
  standoff:2,startstandoff:2,
  xanchor:l.anchor,yanchor:'middle',align:l.anchor==='left'?'left':'right',
  font:{size:10.5,color:dark?'#e6eef7':ETAP_INK,family:'Arial'},
  bgcolor:dark?'rgba(14,26,41,.82)':'rgba(255,255,255,.82)',borderpad:1}));
 const bottoms=marks.filter(m=>m.place==='bottom'||m.place==='point').sort((a,b)=>a.x-b.x);
 bottoms.forEach((m,i)=>{m.stack=i%3;});
 marks.forEach(m=>{
  if(m.place==='bottom'){
   ann.push({x:L(m.x),y:L(m.y),ax:L(m.x),ay:L(m.arrowFrom),xref:'x',yref:'y',axref:'x',ayref:'y',
    text:'',showarrow:true,arrowhead:3,arrowsize:1.1,arrowwidth:1.2,arrowcolor:m.color});
   // Rótulo à direita da seta, como no Star. Mas seta perto da borda
   // direita (caso da falta total da barra, bem acima da passante)
   // jogaria o texto para fora da folha: ali ele vira à esquerda.
   const naBorda=(L(m.x)-L(xr[0]))/(L(xr[1])-L(xr[0]))>0.62;
   ann.push({x:L(m.x),y:L(m.y),xref:'x',yref:'y',text:m.text+(m.ka?` · ${pt(m.ka,3)} kA`:''),showarrow:false,
    xanchor:naBorda?'right':'left',yanchor:'bottom',xshift:naBorda?-5:5,
    yshift:(m.stack||0)*13,
    font:{size:9.5,color:dark?'#e6eef7':ETAP_INK,family:'Arial'},
    bgcolor:dark?'rgba(14,26,41,.82)':'rgba(255,255,255,.82)',borderpad:1});
  }else if(m.text){
   ann.push({x:L(m.x),y:L(m.y),xref:'x',yref:'y',text:m.text,showarrow:false,
    xanchor:'left',yanchor:m.place==='point'?'bottom':'top',xshift:5,
    yshift:m.place==='point'?(6+(m.stack||0)*13):-4,
    font:{size:9.5,color:dark?'#e6eef7':ETAP_INK,family:'Arial'},
    bgcolor:dark?'rgba(14,26,41,.82)':'rgba(255,255,255,.82)',borderpad:1});
  }
 });

 // --- unifilar: painel separado, ao lado do gráfico (não mais embutido) ----
 // A vista Geral não tem unifilar (junta ramais diferentes); ali o próprio
 // interruptor some, para não ficar um controle que não faz nada.
 const hasSL=!!(d.single_line&&d.single_line.elements&&d.single_line.elements.length);
 const slToggle=$('#tcc-singleline-toggle'); if(slToggle)slToggle.classList.toggle('hidden',!hasSL);
 renderMiniSingleLine(d.single_line,dark);

 // --- eixos: moldura fechada, ticks internos e escala duplicada -----------
 const ink=dark?'#dce9f6':ETAP_INK, frame=dark?'#7f9ab5':ETAP_FRAME;
 const grid=state.tccGrid?{showgrid:true,gridcolor:dark?'#22354a':'#d7d7d7',gridwidth:0.6}:{showgrid:false};
 const baseX={type:'log',range:[Math.log10(xr[0]),Math.log10(xr[1])],
  tickmode:'array',tickvals:axis.x_tick_vals,ticktext:axis.x_tick_text,
  ticks:'inside',ticklen:5,tickwidth:0.8,tickcolor:frame,
  minor:{dtick:'D1',ticks:'inside',ticklen:2.5,tickwidth:0.6,tickcolor:frame,showgrid:false},
  showline:true,linecolor:frame,linewidth:1.1,zeroline:false,
  tickfont:{size:10,color:ink,family:'Arial'},...grid};
 const baseY={type:'log',range:[Math.log10(yr[0]),Math.log10(yr[1])],
  tickmode:'array',tickvals:axis.y_tick_vals,ticktext:axis.y_tick_text,
  ticks:'inside',ticklen:5,tickwidth:0.8,tickcolor:frame,
  minor:{dtick:'D1',ticks:'inside',ticklen:2.5,tickwidth:0.6,tickcolor:frame,showgrid:false},
  showline:true,linecolor:frame,linewidth:1.1,zeroline:false,
  tickfont:{size:10,color:ink,family:'Arial'},...grid};
 const axTitle={text:axis.title||'',font:{size:12,color:ink,family:'Arial'},standoff:8};

 const layout={
  paper_bgcolor:dark?'#0e1a29':ETAP_PAPER,plot_bgcolor:dark?'#0b1520':ETAP_PAPER,
  font:{color:ink,family:'Arial'},showlegend:false,
  margin:{l:64,r:64,t:56,b:56},
  xaxis:{...baseX,side:'bottom',title:axTitle},
  xaxis2:{...baseX,side:'top',overlaying:'x',matches:'x',title:axTitle,anchor:'y'},
  yaxis:{...baseY,side:'left',title:{text:'Seconds',font:{size:12,color:ink,family:'Arial'},standoff:6}},
  yaxis2:{...baseY,side:'right',overlaying:'y',matches:'y',anchor:'x',
   title:{text:'Seconds',font:{size:12,color:ink,family:'Arial'},standoff:6}},
  shapes:[],annotations:ann};
 // Traço invisível só para materializar os eixos espelhados de cima/direita.
 traces.push({x:[xr[0]],y:[yr[0]],xaxis:'x2',yaxis:'y2',type:'scatter',mode:'markers',
  marker:{opacity:0},hoverinfo:'skip',showlegend:false});

 if(traces.length>1)Plotly.react('tcc-chart',traces,layout,plotConfig());
 else $('#tcc-chart').innerHTML='<div class="empty-state">Sem curvas para esta vista.</div>';

 $('#tcc-chart').classList.toggle('etap-sheet',!dark);
 const stamp=$('#tcc-stamp'); if(stamp)stamp.innerHTML=etapSheetBlock(d.sheet,d.title);

 const notes=(d.notes||[]).slice(); const ss=d.study_status||{},ec=d.electrical_cache||{};
 if(ss.powerflow_ok||ss.sc_max_ok||ss.sc_min_ok) notes.unshift(`Cadeia do estudo: Fluxo ${ss.powerflow_ok?'OK':'ERRO'} · Curto MAX ${ss.sc_max_ok?'OK':'ERRO'} · Curto MIN ${ss.sc_min_ok?'OK':'ERRO'}`);
 if(ec.powerflow_cached)notes.unshift('V27+: resultados elétricos reutilizados do cache; o TCC foi reconstruído sem novo runpp/curto global.');
 $('#tcc-concise-summary').innerHTML=notes.length?notes.map(n=>`<div class="tcc-summary-note">${esc(n)}</div>`).join(''):'<div class="tcc-summary-note">TCC montado com ajustes salvos e resultados do estudo elétrico.</div>';
}

// -------- AJUSTE 50/51 AO VIVO, AO LADO DA FOLHA --------
// Só os campos que mexem na curva de fase. O resto (neutro, cabo, disjuntor)
// continua na tela Ajustes 50/51, que é a tela completa.
const LIVE_LABEL={phase_curve:'curva',phase_stage1_pickup_a:'pickup 51',phase_time_setting:'TMS',
 phase_stage3_pickup_a:'pickup 50',phase_stage3_delay_s:'retardo 50'};
let livePreviewTimer=null;
const liveEdits=zid=>state.tccEdits[zid]||{};
function renderLivePanel(d){
 const el=$('#tcc-live'); if(!el)return;
 const zones=d.live_zones||[];
 if(!zones.length){el.innerHTML='';return}
 if(!zones.some(z=>z.id===state.tccLiveZone))state.tccLiveZone=zones[0].id;
 const z=zones.find(x=>x.id===state.tccLiveZone), ed=liveEdits(z.id), saved=z.settings||{};
 const val=k=>ed[k]!==undefined?ed[k]:saved[k];
 const num=(k,label,step)=>`<label class="${ed[k]!==undefined?'edited':''}"><span>${label}</span><input type="number" step="${step}" min="0" data-live="${k}" value="${val(k)??''}"></label>`;
 const zoneSel=zones.length>1
  ?`<label><span>Relé</span><select id="live-zone">${zones.map(x=>`<option value="${x.id}"${x.id===z.id?' selected':''}>${esc(x.relay)} · ${pt(x.kv,1)} kV</option>`).join('')}</select></label>`
  :`<p class="hint" style="margin-bottom:11px"><b>${esc(z.relay)}</b> · ${pt(z.kv,1)} kV</p>`;
 el.innerHTML=`<h4>Ajuste ao vivo</h4>
  <p class="hint">A curva redesenha enquanto você digita. Nada vai para o banco até clicar em salvar.</p>
  ${zoneSel}
  <label class="${ed.phase_curve!==undefined?'edited':''}"><span>Curva 51</span><select data-live="phase_curve">${(d.curve_options||[]).map(c=>`<option value="${c.key}"${val('phase_curve')===c.key?' selected':''}>${esc(c.label)}</option>`).join('')}</select></label>
  <div class="pair">${num('phase_stage1_pickup_a','Pickup 51 (A)','1')}${num('phase_time_setting','TMS','0,001'.replace(',','.'))}</div>
  <div class="pair">${num('phase_stage3_pickup_a','Pickup 50 (A)','1')}${num('phase_stage3_delay_s','Retardo 50 (s)','0.01')}</div>
  <div class="tcc-live-actions"><button class="btn primary" id="live-save" title="Grava no banco tudo que está em prévia">Salvar ajuste</button><button class="btn secondary" id="live-reset" title="Volta ao ajuste salvo, em todos os relés em prévia">Descartar</button></div>
  <div class="tcc-live-status" id="live-status"></div>`;
 const zs=$('#live-zone'); if(zs)zs.onchange=()=>{state.tccLiveZone=zs.value;renderLivePanel(state.lastTCC)};
 $$('#tcc-live [data-live]').forEach(inp=>{
  const ev=inp.tagName==='SELECT'?'change':'input';
  inp.addEventListener(ev,()=>{
   const k=inp.dataset.live, raw=inp.value;
   const edits=state.tccEdits[state.tccLiveZone]||(state.tccEdits[state.tccLiveZone]={});
   // Campo vazio = voltar ao ajuste salvo, em vez de mandar null pro servidor.
   if(raw===''){delete edits[k]}
   else{edits[k]=inp.type==='number'?Number(raw):raw}
   if(!Object.keys(edits).length)delete state.tccEdits[state.tccLiveZone];
   inp.closest('label')?.classList.toggle('edited',raw!==''&&liveEdits(state.tccLiveZone)[k]!==undefined);
   updateLiveStatus();
   clearTimeout(livePreviewTimer);livePreviewTimer=setTimeout(runLivePreview,260);
  });
 });
 const sv=$('#live-save'); if(sv)sv.onclick=saveLiveEdits;
 const rs=$('#live-reset'); if(rs)rs.onclick=discardLiveEdits;
 updateLiveStatus();
}
function setLiveStatus(text,cls){const el=$('#live-status');if(!el)return;el.className='tcc-live-status'+(cls?' '+cls:'');el.textContent=text}
function updateLiveStatus(){
 const ed=liveEdits(state.tccLiveZone), keys=Object.keys(ed);
 const outras=Object.keys(liveOverrides()).filter(z=>z!==state.tccLiveZone);
 if(!keys.length){
  setLiveStatus(outras.length?`Este relé está com o ajuste salvo. Prévia pendente em: ${outras.join(', ')}.`:'Mostrando o ajuste salvo.');
  return;
 }
 setLiveStatus(`Prévia não salva: ${keys.map(k=>LIVE_LABEL[k]||k).join(', ')}.`+(outras.length?` Também pendente em ${outras.join(', ')}.`:''),'dirty');
}
async function runLivePreview(){
 try{renderConciseTCC(await fetchTCC(state.tccView||'mb0'),{keepPanel:true});updateLiveStatus()}
 catch(e){setLiveStatus(e.message,'dirty')}
}
// Salvar e descartar agem sobre TUDO que está em prévia, não só sobre o relé
// que está selecionado no seletor: na vista T1 dá para mexer no Relé11 e no
// Relé12 para coordenar os dois, e sumir com metade do trabalho por causa da
// posição do seletor seria uma pegadinha.
async function saveLiveEdits(){
 const pend=liveOverrides(), zids=Object.keys(pend);
 if(!zids.length){setLiveStatus('Nada alterado.');return}
 const btn=$('#live-save'); if(btn){btn.disabled=true;btn.textContent='Salvando…'}
 try{
  for(const zid of zids){
   await api(`/api/protection/${zid}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pend[zid])});
   delete state.tccEdits[zid];
  }
  state.zones=[];               // a tela Ajustes 50/51 recarrega ao abrir
  await loadTCC();
  setLiveStatus(zids.length>1?`Ajustes salvos: ${zids.join(', ')}.`:'Ajuste salvo.','saved');
  toast(zids.length>1?`${zids.length} relés salvos e coordenograma redesenhado`:`${zids[0]}: ajuste salvo e coordenograma redesenhado`);
 }catch(e){toast(e.message);setLiveStatus(e.message,'dirty')}
 finally{const b=$('#live-save');if(b){b.disabled=false;b.textContent='Salvar ajuste'}}
}
async function discardLiveEdits(){
 if(!Object.keys(liveOverrides()).length)return;
 state.tccEdits={};
 await loadTCC();
 setLiveStatus('Prévia descartada.');
}

// -------- MÓDULO ESPECIALISTA (fase) --------
const EXPERT_FIELD_BY_RULE={'R51-PICKUP':'phase_stage1_pickup_a','R51-TMS':'phase_time_setting','R50-PICKUP':'phase_stage3_pickup_a'};
async function loadExpert(){
 const el=$('#expert-list'); if(!el)return;
 populateExpertPathSelect();
 loadReview();
 el.classList.add('skeleton');
 try{
  if(!state.expertData)state.expertData=await api('/api/expert');
  el.classList.remove('skeleton');
  renderExpertView();
  bindExpertButtons();
 }catch(e){el.classList.remove('skeleton');el.innerHTML=`<div class="notice">${esc(e.message)}</div>`}
}

// -------- VERIFICAÇÃO EM CASCATA (casos 1, 2, 3) --------
// O veredito é do caso inteiro; cada linha mostra a folga e a corrente em que
// ela é mínima, que é o que o engenheiro precisa para agir — não um "ok" seco.
const REVIEW_SCOPE_LABEL={cti:'seletividade',piso:'piso',teto:'teto'};
async function loadReview(){
 const el=$('#review-cases'); if(!el)return;
 el.innerHTML='<div class="review-loading">verificando coordenação…</div>';
 try{
  const d=await api(`/api/coordination-review/${state.expertPath}`);
  state.review=d; renderReview(d);
 }catch(e){el.innerHTML=`<div class="notice">${esc(e.message)}</div>`}
}
function renderReview(d){
 const el=$('#review-cases'); if(!el)return;
 if(!d.cases?.length){el.innerHTML='<div class="notice">Caminho sem casos para verificar.</div>';return}
 if(!d.cases.some(c=>c.id===state.reviewCase))state.reviewCase=d.cases[0].id;
 const c=d.cases.find(x=>x.id===state.reviewCase)||d.cases[0];
 const verdict={approved:['aprovado','ok'],rejected:['reprovado','bad'],pending:['com pendência','warn']};
 const tabs=d.cases.map(x=>{const v=verdict[x.status]||['',''];
  return `<button class="review-tab ${x.id===c.id?'active':''} ${v[1]}" data-case="${x.id}">
   <b>Caso ${x.depth-1}</b><span>${esc(x.title)}</span><em>${v[0]}</em></button>`}).join('');
 const group=k=>c.checks.filter(x=>x.scope===k);
 const line=x=>{
  const folga=x.margin_s==null?'':`<b>${x.margin_s>=0?'+':''}${pt(x.margin_s,3)} s</b>`;
  const onde=x.at_current_a==null?'':`<small>em ${pt(x.at_current_a,0)} A</small>`;
  return `<div class="review-line ${x.status}"><div><b>${esc(x.title)}</b><p>${esc(x.text)}</p></div>
   <div class="review-num">${folga}${onde}</div></div>`;
 };
 const bloco=(titulo,itens,sub)=>itens.length?`<div class="review-block"><h4>${titulo}</h4><p class="review-sub">${sub}</p>${itens.map(line).join('')}</div>`:'';
 el.innerHTML=`<div class="review-tabs">${tabs}</div>
  <article class="card review-card">
   <div class="review-head">
    <div><span class="eyebrow">${esc(d.title)} · base ${pt(d.reference_kv,1)} kV</span>
     <h3>Caso ${c.depth-1} — ${esc(c.title)}</h3>
     <p class="muted">Estágios: ${c.stages.map(s=>esc(s.label)).join(' → ')}</p></div>
    <span class="pill ${c.status==='approved'?'ok':(c.status==='rejected'?'bad':'warn')}">${(verdict[c.status]||[''])[0]}</span>
   </div>
   ${bloco('Seletividade entre estágios',group('cti'),'Relés que abrem o mesmo disjuntor contam como um estágio só.')}
   ${bloco('Piso — partida e inrush',group('piso'),'Vale para todos os relés do caso: nenhum pode desarmar na partida do motor nem na energização do trafo.')}
   ${bloco('Teto — dano do motor',group('teto'),`Cobrado só da proteção principal e da retaguarda imediata.${c.ceiling_exempt?.length?' Isentos neste caso: '+c.ceiling_exempt.map(esc).join(', ')+'.':''}`)}
   <div class="review-notes">${(d.notes||[]).map(n=>`<span>${esc(n)}</span>`).join('')}</div>
  </article>`;
 $$('#review-cases [data-case]').forEach(b=>b.onclick=()=>{state.reviewCase=b.dataset.case;renderReview(state.review)});
}
function populateExpertPathSelect(){
 const sel=$('#expert-path'); if(!sel||sel.dataset.filled)return;
 sel.innerHTML=(state.paths||[]).map(p=>`<option value="${esc(p.id)}">${esc(p.title)}</option>`).join('');
 sel.value=state.expertPath;
 sel.dataset.filled='1';
 sel.onchange=()=>{state.expertPath=sel.value;state.expertStep=0;renderExpertView();loadReview()};
 const allBox=$('#expert-showall');
 if(allBox){allBox.checked=state.expertShowAll;allBox.onchange=()=>{state.expertShowAll=allBox.checked;renderExpertView()}}
}
function renderExpertView(){
 const el=$('#expert-list'), stepperEl=$('#expert-stepper'); if(!el||!state.expertData)return;
 const byZone=Object.fromEntries(state.expertData.zones.map(z=>[z.zone,z]));
 if(state.expertShowAll){
  stepperEl.innerHTML='';
  el.innerHTML=state.expertData.zones.map(expertZoneCard).join('');
  bindExpertButtons();
  return;
 }
 const path=(state.paths||[]).find(p=>p.id===state.expertPath)||state.paths?.[0];
 if(!path){stepperEl.innerHTML='';el.innerHTML='<div class="notice">Nenhum caminho de coordenação encontrado.</div>';return}
 const zoneIds=path.zones;
 state.expertStep=Math.max(0,Math.min(state.expertStep,zoneIds.length-1));
 const crumbs=zoneIds.map((zid,i)=>{
  const z=byZone[zid]; const active=i===state.expertStep;
  return `<button class="expert-crumb ${active?'active':''}" data-step="${i}">${i+1}. ${esc(z?.relay||zid)}</button>`;
 }).join('<span class="expert-crumb-arrow">→</span>');
 stepperEl.innerHTML=`
  <div class="expert-crumbs">${crumbs}</div>
  <div class="expert-step-nav">
   <button id="expert-prev" class="btn secondary" ${state.expertStep===0?'disabled':''}>← Zona anterior (jusante)</button>
   <span class="muted">Passo ${state.expertStep+1} de ${zoneIds.length} — subindo do motor até o gerador</span>
   <button id="expert-next" class="btn primary" ${state.expertStep===zoneIds.length-1?'disabled':''}>Próxima zona (montante) →</button>
  </div>`;
 const currentZone=byZone[zoneIds[state.expertStep]];
 el.innerHTML=currentZone?expertZoneCard(currentZone):'<div class="notice">Sugestão indisponível para esta zona.</div>';
 $('#expert-prev')&&($('#expert-prev').onclick=()=>{state.expertStep--;renderExpertView()});
 $('#expert-next')&&($('#expert-next').onclick=()=>{state.expertStep++;renderExpertView()});
 $$('.expert-crumb').forEach(b=>b.onclick=()=>{state.expertStep=Number(b.dataset.step);renderExpertView()});
 bindExpertButtons();
}
function expertInputsHtml(inputs,unit){
 if(!inputs||!Object.keys(inputs).length)return '';
 const rows=Object.entries(inputs).flatMap(([k,v])=>{
  if(k==='candidatos'&&Array.isArray(v))return v.map(c=>`<li>${esc(c.regra)}: ${pt(c.valor_a,unit==='A'?1:3)}${unit?' '+unit:''}</li>`);
  return [`<li>${esc(k)}: ${typeof v==='number'?pt(v,4):esc(v)}</li>`];
 });
 return `<ul class="expert-inputs">${rows.join('')}</ul>`;
}
function expertRuleHtml(zoneId,r){
 const field=EXPERT_FIELD_BY_RULE[r.id];
 const decimals=r.unit==='A'?1:3;
 const canApply=field&&r.suggested!=null;
 return `<div class="expert-rule">
  <div class="expert-rule-head"><b>${esc(r.title)}</b>${r.clamped?'<span class="pill warn small">limitado à faixa do relé</span>':''}</div>
  <p class="muted">${esc(r.rule)}</p>
  ${expertInputsHtml(r.inputs,r.unit)}
  <div class="expert-rule-values">
   <span>Sugerido: <b>${r.suggested!=null?pt(r.suggested,decimals)+' '+r.unit:'—'}</b></span>
   <span>Atual: <b>${r.current!=null?pt(r.current,decimals)+' '+r.unit:'não definido'}</b></span>
   ${canApply?`<button class="btn secondary small" data-apply-zone="${esc(zoneId)}" data-apply-field="${field}" data-apply-value="${r.suggested}">Aplicar sugestão</button>`:''}
  </div>
 </div>`;
}
function expertZoneCard(z){
 if(z.error)return `<article class="card"><h3>${esc(z.zone)}</h3><p class="muted">${esc(z.error)}</p></article>`;
 return `<article class="card expert-zone-card">
  <div class="card-head"><div><h3>${esc(z.relay)}</h3><p>${esc(z.title)}</p></div><span class="pill info">${esc(z.curve)}</span></div>
  ${z.rules.map(r=>expertRuleHtml(z.zone,r)).join('')}
  ${z.warnings&&z.warnings.length?`<p class="muted small">⚠ ${z.warnings.map(w=>esc(w)).join(' · ')}</p>`:''}
 </article>`;
}
function bindExpertButtons(){
 $$('[data-apply-zone]').forEach(b=>b.onclick=async()=>{
  const zone=b.dataset.applyZone,field=b.dataset.applyField,value=Number(b.dataset.applyValue);
  b.disabled=true;const orig=b.textContent;b.textContent='Aplicando…';
  try{await saveProtection(zone,{[field]:value});toast('Ajuste aplicado · Pandapower não recalculado (só o coordenograma muda)');state.expertData=null;await loadExpert()}
  catch(e){toast(e.message);b.disabled=false;b.textContent=orig}
 });
}
$('#expert-refresh')?.addEventListener('click',()=>{state.expertData=null;loadExpert()});

function currentTickLabel(v){if(v>=1e6)return `${pt(v/1e6,0)} MA`;if(v>=1e3)return `${pt(v/1e3,0)} kA`;return `${pt(v,0)} A`}
function logPowerTicks(min,max){const vals=[];const lo=Math.floor(Math.log10(Math.max(min,1e-12))),hi=Math.ceil(Math.log10(Math.max(max,min*1.01)));for(let p=lo;p<=hi;p++){const v=10**p;if(v>=min*.999&&v<=max*1.001)vals.push(v)}return vals}

// -------- CÁLCULO 51 --------
$('#manual-calc').onclick=loadManual;
async function loadManual(){if(!state.currentZone)return;$('#manual-zone').value=state.currentZone;const current=valNum('#manual-current');const d=await api(`/api/manual51/${state.currentZone}${current==null?'?mode=phase':`?mode=phase&current=${encodeURIComponent(current)}`}`);if(d.error){$('#manual-steps').innerHTML=`<div class="notice">${esc(d.error)}</div>`;return}$('#manual-curve-pill').textContent=d.curve.label;const t=d.time_s==null?'não atua (I ≤ pickup)':`${fmt(d.time_s,4)} s`;$('#manual-steps').innerHTML=`<div class="manual-step"><span>1</span><div><b>Corrente primária</b><p>I = ${fmt(d.current_a,3)} A <small>(${esc(d.current_source)})</small></p></div></div><div class="manual-step"><span>2</span><div><b>TC</b><p>${fmt(d.settings.ct_primary_a,0)}/${fmt(d.settings.ct_secondary_a,0)} A → RTC=${fmt(d.ct_ratio,3)}</p><p>Isec=${fmt(d.current_secondary_a,4)} A</p></div></div><div class="manual-step"><span>3</span><div><b>Pickup 51P</b><p>Ip=${fmt(d.settings.phase_stage1_pickup_a,3)} A → secundário=${fmt(d.pickup_secondary_a,4)} A</p></div></div><div class="manual-step"><span>4</span><div><b>Múltiplo M</b><p>Mprim=${fmt(d.multiple_primary,4)} · Msec=${fmt(d.multiple_secondary,4)}</p></div></div><div class="manual-step"><span>5</span><div><b>${esc(d.curve.label)}</b><code>${esc(d.equation.symbolic)}</code><code>${esc(d.equation.substitution)}</code></div></div><div class="manual-step result"><span>6</span><div><b>Tempo do estágio inverso</b><p>${t}</p></div></div>`;const traces=d.comparison.map(c=>({x:c.x,y:c.y,name:c.label,type:'scatter',mode:'lines',line:{width:c.curve===d.curve.key?4:2,dash:c.curve===d.curve.key?'solid':'dash'}}));if(d.time_s!=null)traces.push({x:[d.current_a],y:[d.time_s],name:'Ponto calculado',type:'scatter',mode:'markers',marker:{size:11}});Plotly.react('manual-compare',traces,plotLayout('','Corrente [A]','Tempo [s]',{xaxis:{type:'log',gridcolor:'#26384d'},yaxis:{type:'log',range:[Math.log10(d.y_range?.[0]||.01),Math.log10(d.y_range?.[1]||1000)],gridcolor:'#26384d'},legend:{orientation:'h',y:-.18},margin:{l:65,r:20,t:10,b:95}}),plotConfig());$('#manual-checks').innerHTML=d.checks.map(a=>`<div class="analysis-line ${a.status}"><b>${esc(a.title)}</b><span>${esc(a.text)}</span></div>`).join('')}

// -------- UNIFILAR --------
// V29: os textos deixam de ser hardcoded e passam a ler state.network, para
// que uma edição de equipamento (Modelo físico) reflita no unifilar sem
// precisar recarregar a página.
const cableSpecLabel=c=>c?`${parseInt(c.parallel||1,10)}-${parseInt(c.phase||3,10)}/C ${Number(c.size_mm2).toLocaleString('pt-BR',{maximumFractionDigits:0})}`:'';
// Símbolo do TC (transformador de corrente): duas alças à esquerda do condutor,
// na altura onde o relé deriva — presente em toda referência ETAP do usuário.
const ctRatioLabel=(relayName)=>{const z=(state.zones||[]).find(z=>z.relay===relayName);const s=z?.settings;return s&&s.ct_primary_a&&s.ct_secondary_a?`${parseInt(s.ct_primary_a,10)}/${parseInt(s.ct_secondary_a,10)}`:''};
const ctLoops=(x,y,relayName)=>{
 if(!relayName)return `<path class="sld-wire" d="M${x} ${y-9} q-7 0 -7 4.5 q0 4.5 7 4.5 q-7 0 -7 4.5 q0 4.5 7 4.5" fill="none"/>`;
 const attrs=` data-type="relay" data-id="${esc(relayName)}"`;
 const hit=`<circle cx="${x-4}" cy="${y}" r="11" fill="transparent" class="sld-click"${attrs}/>`; // área de clique maior que a linha fina
 const loop=`<path class="sld-wire sld-click"${attrs} d="M${x} ${y-9} q-7 0 -7 4.5 q0 4.5 7 4.5 q-7 0 -7 4.5 q0 4.5 7 4.5" fill="none"/>`;
 const ratio=ctRatioLabel(relayName);
 return hit+loop+(ratio?`<text class="sld-value sld-click"${attrs} x="${x-11}" y="${y-11}" text-anchor="end" style="cursor:pointer">${ratio}</text>`:'');
};
// Símbolo do gerador: círculo com o "Y" do enrolamento em estrela, três raios a
// 120° (up-left, up-right, para baixo). É o mesmo desenho que o ETAP usa para a
// máquina síncrona e é o que separa o gerador do motor, que no ETAP é círculo
// liso. Antes os dois eram o mesmo círculo e não dava para distinguir.
function generatorSvg(cx,cy,r,id){
 const p=a=>{const t=a*Math.PI/180;return `${(cx+r*Math.cos(t)).toFixed(1)} ${(cy+r*Math.sin(t)).toFixed(1)}`};
 const spokes=[-150,-30,90].map(a=>`M${cx} ${cy}L${p(a)}`).join('');
 return `<g class="sld-click" data-type="generator" data-id="${esc(id||'')}">`
  +`<circle class="sld-generator" cx="${cx}" cy="${cy}" r="${r}"/>`
  +`<path class="sld-generator-wye" d="${spokes}"/></g>`;
}
// V30: símbolo de cabo. Antes o cabo era só um traço reto, indistinguível de um
// condutor qualquer. O ETAP representa o cabo pela sua impedância — resistência
// em zigue-zague e indutância em bobina, em série —, e é isso que se desenha
// aqui: dois trechos de conexão, o zigue-zague, e a bobina, ajustados ao
// comprimento disponível do ramal.
function cableSymbol(x,y1,y2,cable){
 const nome=cable?.name||'';
 const attrs=` class="sld-cable sld-click" data-type="cable" data-id="${esc(nome)}"`;
 const h=y2-y1;
if(h<24) return `<line${attrs} x1="${x}" y1="${y1}" x2="${x}" y2="${y2}"/>`;
 // Reparte o trecho: conexão, zigue-zague (R), folga, bobina (L), conexão.
 // Símbolo compacto: ocupa o meio do trecho e deixa condutor visível dos dois lados.
 const zig=14, bob=15, folga=3;
 const lead=(h-zig-bob-folga)/2;
 const zy=y1+lead, by=zy+zig+folga;
 // Resistência: seis segmentos alternando de lado.
 const amp=3.4, passo=zig/6;
 let d=`M${x} ${zy}`;
 for(let i=1;i<=6;i++) d+=`L${(i%2?x+amp:x-amp).toFixed(1)} ${(zy+i*passo).toFixed(1)}`;
 d+=`L${x} ${(zy+zig).toFixed(1)}`;
 // Indutância: três voltas para o mesmo lado. O raio horizontal é maior que o
 // vertical para a bobina aparecer sem precisar de mais altura no ramal.
 const dy=bob/3, rx=dy*0.85, ry=dy/2;
 let dl=`M${x} ${by}`;
 for(let i=0;i<3;i++) dl+=`a ${rx.toFixed(2)} ${ry.toFixed(2)} 0 0 1 0 ${dy.toFixed(2)}`;
 return `<g${attrs}>`
  +`<line class="sld-cable" x1="${x}" y1="${y1}" x2="${x}" y2="${zy}"/>`
  +`<path class="sld-cable" d="${d}" fill="none"/>`
  +`<line class="sld-cable" x1="${x}" y1="${(zy+zig).toFixed(1)}" x2="${x}" y2="${by}"/>`
  +`<path class="sld-cable" d="${dl}" fill="none"/>`
  +`<line class="sld-cable" x1="${x}" y1="${(by+bob).toFixed(1)}" x2="${x}" y2="${y2}"/></g>`;
}
function renderSingleLine(){
 if(!state.network)return;
 const byName=(arr,name)=>(arr||[]).find(x=>x.name===name);
 const gens=state.network.generators||[];
 const ge1=gens.find(g=>g.name==='GE1')||gens[0], ge2=gens.find(g=>g.name==='GE2');
 const t1=byName(state.network.transformers,'T1');
 const cable1=byName(state.network.cables,'Cabo1'), cable3=byName(state.network.cables,'Cabo3');
 const cable8=byName(state.network.cables,'Cabo8'), cable2=byName(state.network.cables,'Cabo2');
 const cable4=byName(state.network.cables,'Cabo4'), cable5=byName(state.network.cables,'Cabo5');
 const mb6=byName(state.network.motors,'M-B-6'), mb0=byName(state.network.motors,'M-B-0');
 const mb1=byName(state.network.motors,'M-B-1'), mb2=byName(state.network.motors,'M-B-2');
 const bus1=byName(state.network.buses,'Barra3'), bus2=byName(state.network.buses,'Barra5');
 // V30: dois ramais de geração espelhados sobre a barra principal. Um gerador
 // fora de serviço aparece esmaecido e com o disjuntor aberto — é a leitura
 // visual do efeito que o aluno vai medir no curto-circuito.
 const svg=`<svg viewBox="0 0 1000 720" xmlns="http://www.w3.org/2000/svg"><defs><pattern id="sldGrid" width="18" height="18" patternUnits="userSpaceOnUse"><path d="M18 0H0V18" fill="none" stroke="#f0e2d2" stroke-width="1"/></pattern></defs><rect width="1000" height="720" fill="#fdfdfc"/><rect width="1000" height="720" fill="url(#sldGrid)"/><g>
${generatorFeederSvg(330,ge1,'Barra1','Relé1','DJ1',cable1)}
${ge2?generatorFeederSvg(640,ge2,'Barra2','Relé2','DJ5',cable3):''}
<line class="sld-bus sld-click" data-type="bus" data-id="Barra3" x1="100" y1="220" x2="900" y2="220"/><text class="sld-label" x="35" y="214">Barra3</text><text class="sld-label" x="35" y="232">${pt(bus1?.kv,1)} kV</text>
${transformerSvg(280,220,480,t1,'DJ2','Relé10','Relé12')}
${motorFeederSvg(700,220,400,'DJ3','Relé3','Barra4',cable8,mb6)}
<line class="sld-bus sld-click" data-type="bus" data-id="Barra5" x1="100" y1="480" x2="900" y2="480"/><text class="sld-label" x="35" y="474">Barra5</text><text class="sld-label" x="35" y="492">${pt(bus2?.kv,1)} kV</text>
${mb1?motorFeederSvg(200,480,650,'DJ6','Relé4','Barra7',cable4,mb1):''}
${mb2?motorFeederSvg(450,480,650,'DJ7','Relé5','Barra8',cable5,mb2):''}
${motorFeederSvg(700,480,650,'DJ4','Relé11','Barra6',cable2,mb0)}
</g></svg>`;$('#singleline-svg-wrap').innerHTML=svg;$$('.sld-click').forEach(el=>el.onclick=()=>{$$('.sld-click').forEach(x=>x.classList.remove('sld-selected'));el.classList.add('sld-selected');showElement(el.dataset.type,el.dataset.id)})}
// Ramo de geração: máquina -> barra de terminal -> TC/relé -> disjuntor -> cabo -> barra principal.
// Espelhado para GE1 e GE2; fora de serviço, o traço fica esmaecido e o disjuntor aberto.
function generatorFeederSvg(x,g,busName,relay,cb,cable){
 const on=!g||g.in_service!==false;
 const dim=on?'':' style="opacity:.32"';
 const y0=65, tapY=142, brkY=157, busY=220;
 const label=g?`${pt(g.p_rated_mw,0)} MW`:'';
 const aberto=on?'':`<line class="sld-wire" x1="${x-9}" y1="${brkY+3}" x2="${x+9}" y2="${brkY+11}" stroke="#d01818" stroke-width="2"/>`;
 return `<g${dim}>${generatorSvg(x,y0,24,g?.name)}<text class="sld-label" x="${x+34}" y="${y0-20}">${label}</text><text class="sld-label" x="${x+34}" y="${y0-3}">${esc(g?.name||'')}</text>
<line class="sld-wire" x1="${x}" y1="${y0+24}" x2="${x}" y2="${y0+53}"/><circle class="sld-bus sld-click" data-type="bus" data-id="${busName}" cx="${x}" cy="${y0+53}" r="3.2" fill="#000"/><text class="sld-label" x="${x+10}" y="${y0+57}">${busName}</text>
<line class="sld-wire" x1="${x}" y1="${y0+53}" x2="${x}" y2="${tapY}"/>${ctLoops(x,tapY,relay)}<line class="sld-wire" x1="${x}" y1="${tapY}" x2="${x+30}" y2="${tapY}"/><circle class="sld-relay sld-click" data-type="relay" data-id="${relay}" cx="${x+45}" cy="${tapY}" r="15"/><text x="${x+45}" y="${tapY}" text-anchor="middle" dominant-baseline="central" class="sld-relay-text">R</text><text class="sld-label" x="${x+64}" y="${tapY+4}">${relay}</text>
<line class="sld-wire" x1="${x}" y1="${tapY}" x2="${x}" y2="${brkY}"/><rect class="sld-breaker sld-click" data-type="breaker" data-id="${cb}" x="${x-7}" y="${brkY}" width="14" height="14"/>${aberto}
${cableSymbol(x,brkY+14,busY,cable)}<text class="sld-label" x="${x+15}" y="${brkY+36}">${esc(cable?.name||'')}</text><text class="sld-value" x="${x+15}" y="${brkY+51}">${cableSpecLabel(cable)}</text>
${on?'':`<text class="sld-label" x="${x+34}" y="${y0+14}" style="fill:#d01818">fora de serviço</text>`}</g>`}
// Ramo do T1: disjuntor DJ2 (AT) -> tap do Relé10 -> bobina (duas fileiras de
// arcos, igual ao ETAP) -> tap do Relé12 (sem disjuntor, igual à referência) -> Barra5.
function transformerSvg(x,y1,y2,t,cbHv,relayHv,relayLv){
 const cy=(y1+y2)/2;const name=t?.name||'T1';const mva=t?`${pt(t.sn_mva,1)} MVA`:'';
 const tapHvY=y1+34, brkY=tapHvY+16, topCy=cy-15, botCy=cy+15, tr=19, hvWireEnd=topCy-tr, lvTapY=y2-40;
 return `<line class="sld-wire" x1="${x}" y1="${y1}" x2="${x}" y2="${tapHvY}"/>${ctLoops(x,tapHvY,relayHv)}<line class="sld-wire" x1="${x}" y1="${tapHvY}" x2="${x+30}" y2="${tapHvY}"/><circle class="sld-relay sld-click" data-type="relay" data-id="${relayHv}" cx="${x+45}" cy="${tapHvY}" r="15"/><text x="${x+45}" y="${tapHvY}" text-anchor="middle" dominant-baseline="central" class="sld-relay-text">R</text><text class="sld-label" x="${x+64}" y="${tapHvY+4}">${relayHv}</text>
<line class="sld-wire" x1="${x}" y1="${tapHvY}" x2="${x}" y2="${brkY}"/><rect class="sld-breaker sld-click" data-type="breaker" data-id="${cbHv}" x="${x-7}" y="${brkY}" width="14" height="14"/>
<line class="sld-wire" x1="${x}" y1="${brkY+14}" x2="${x}" y2="${hvWireEnd}"/><g class="sld-click" data-type="transformer" data-id="${name}"><circle class="sld-transformer" cx="${x}" cy="${topCy}" r="${tr}"/><circle class="sld-transformer" cx="${x}" cy="${botCy}" r="${tr}"/></g><text class="sld-label" x="${x+85}" y="${cy-5}">${esc(name)} · ${mva}</text>${t?.vector_group?`<text class="sld-value" x="${x+85}" y="${cy+10}">${esc(t.vector_group)}</text>`:''}
<line class="sld-wire" x1="${x}" y1="${botCy+tr}" x2="${x}" y2="${lvTapY}"/>${ctLoops(x,lvTapY,relayLv)}<line class="sld-wire" x1="${x}" y1="${lvTapY}" x2="${x+30}" y2="${lvTapY}"/><circle class="sld-relay sld-click" data-type="relay" data-id="${relayLv}" cx="${x+45}" cy="${lvTapY}" r="15"/><text x="${x+45}" y="${lvTapY}" text-anchor="middle" dominant-baseline="central" class="sld-relay-text">R</text><text class="sld-label" x="${x+64}" y="${lvTapY+4}">${relayLv}</text>
<line class="sld-wire" x1="${x}" y1="${lvTapY}" x2="${x}" y2="${y2}"/>`}
// Ramo motor: Bus -> tap do relé -> disjuntor -> cabo (nome + especificação) -> nó (Barra4/Barra6/…, só ponto+rótulo) -> motor.
// V30: igual ao ramo de geração, um motor fora de serviço aparece esmaecido e
// com o disjuntor aberto — é a leitura visual do que muda no curto MAX.
function motorFeederSvg(x,y1,y2,cb,relay,busName,cable,motor){
 const on=!motor||motor.in_service!==false;
 const dim=on?'':' style="opacity:.32"';
 const tapY=y1+34, brkY=y1+50, cableTop=brkY+14, junctionY=cableTop+54, motorTop=y2-22;
 const kwLabel=motor?`${pt(motor.kw,0)} kW`:'';
 const aberto=on?'':`<line class="sld-wire" x1="${x-9}" y1="${brkY+3}" x2="${x+9}" y2="${brkY+11}" stroke="#d01818" stroke-width="2"/>`;
 return `<g${dim}><line class="sld-wire" x1="${x}" y1="${y1}" x2="${x}" y2="${tapY}"/>${ctLoops(x,tapY,relay)}<line class="sld-wire" x1="${x}" y1="${tapY}" x2="${x+17}" y2="${tapY}"/><circle class="sld-relay sld-click" data-type="relay" data-id="${relay}" cx="${x+30}" cy="${tapY}" r="13"/><text x="${x+30}" y="${tapY}" text-anchor="middle" dominant-baseline="central" class="sld-relay-text" style="font-size:11px">R</text><text class="sld-label" x="${x+47}" y="${tapY+4}">${relay}</text>
<line class="sld-wire" x1="${x}" y1="${tapY}" x2="${x}" y2="${brkY}"/><rect class="sld-breaker sld-click" data-type="breaker" data-id="${cb}" x="${x-7}" y="${brkY}" width="14" height="14"/>${aberto}
${cableSymbol(x,cableTop,junctionY,cable)}<text class="sld-label" x="${x+15}" y="${cableTop+22}">${esc(cable?.name||'')}</text><text class="sld-value" x="${x+15}" y="${cableTop+37}">${cableSpecLabel(cable)}</text>
<circle class="sld-bus sld-click" data-type="bus" data-id="${busName}" cx="${x}" cy="${junctionY}" r="3.2" fill="#000"/><text class="sld-label" x="${x+9}" y="${junctionY+4}">${busName}</text>
<line class="sld-wire" x1="${x}" y1="${junctionY}" x2="${x}" y2="${motorTop}"/><circle class="sld-motor sld-click" data-type="motor" data-id="${motor?.name||''}" cx="${x}" cy="${y2}" r="22"/><text class="sld-label" x="${x+35}" y="${y2-3}">${esc(motor?.name||'')}</text><text class="sld-label" x="${x+35}" y="${y2+17}">${kwLabel}</text>
${on?'':`<text class="sld-label" x="${x+35}" y="${y2+34}" style="fill:#d01818">fora de serviço</text>`}</g>`}
async function showElement(type,id){const n=state.network;let html=`<span class="eyebrow">${esc(type.toUpperCase())}</span><h3>${esc(id)}</h3>`;if(type==='bus'){const b=n.buses.find(x=>x.name===id);html+=`<div class="detail-kv">${pt(b.kv,2)} kV</div><p class="muted">${esc(b.role||'')}</p><div id="detail-pf" class="detail-grid"><div><small>Tensão (fluxo)</small><b>calculando…</b></div></div><table class="sc-mini-table"><thead><tr><th>Falta</th><th>MAX</th><th>MIN</th></tr></thead><tbody id="detail-sc-body"><tr><td colspan="3">calculando…</td></tr></tbody></table>`;$('#element-detail').innerHTML=html;try{if(!state.pf)state.pf=await api('/api/powerflow');const pfEl=$('#detail-pf');const pfRow=state.pf?.buses?.find(r=>r.bus===id);pfEl.innerHTML=pfRow&&pfRow.vm_pu!=null?`<div><small>Tensão (fluxo)</small><b>${fmt(pfRow.vm_pu,4)} pu</b></div><div><small>Tensão</small><b>${fmt(pfRow.vm_percent,2)}%</b></div><div><small>Ângulo</small><b>${fmt(pfRow.va_degree,2)}°</b></div>`:`<div><small>Tensão (fluxo)</small><b>indisponível</b></div>`}catch(e){const pfEl=$('#detail-pf');if(pfEl)pfEl.innerHTML='<div><small>Tensão (fluxo)</small><b>indisponível</b></div>'}try{const [mx,mn]=await Promise.all([getSC('max'),getSC('min')]);const rmx=mx.rows.find(r=>r.bus===id),rmn=mn.rows.find(r=>r.bus===id);const row=(label,key)=>`<tr><td>${label}</td><td>${rmx&&rmx[key]!=null?fmt(rmx[key])+' kA':'—'}</td><td>${rmn&&rmn[key]!=null?fmt(rmn[key])+' kA':'—'}</td></tr>`;$('#detail-sc-body').innerHTML=row('3F','3f_ka')+row('LL','ll_ka')+row('LG','lg_ka')+row('LLG','llg_ka')}catch(e){toast(e.message)}return}else if(type==='generator'){const g=n.generators.find(x=>x.name===id);html+=`<div class="detail-kv">${g.sn_mva} MVA</div><div class="detail-grid"><div><small>P nominal</small><b>${g.p_rated_mw} MW</b></div><div><small>Xd”</small><b>${g.xdss_pu} pu</b></div><div><small>X0</small><b>${g.x0_pu} pu</b></div><div><small>X2</small><b>${g.x2_pu} pu</b></div></div><div class="detail-actions"><button class="btn primary" data-editequip="generators:${esc(id)}">Editar equipamento</button></div>`}else if(type==='transformer'){const t=n.transformers.find(x=>x.name===id);html+=`<div class="detail-kv">${t.sn_mva} MVA</div><div class="detail-grid"><div><small>Tensão</small><b>${t.vn_hv_kv}/${t.vn_lv_kv} kV</b></div><div><small>Z</small><b>${t.vk_percent}%</b></div><div><small>X/R</small><b>${t.x_over_r}</b></div><div><small>Inrush</small><b>${t.inrush_pu} pu · ${t.inrush_time_s}s</b></div></div><div class="detail-actions"><button class="btn primary" data-editequip="transformers:${esc(id)}">Editar equipamento</button></div>`}else if(type==='motor'){const m=n.motors.find(x=>x.name===id),z=n.zones.find(z=>z.motor===id);html+=`<div class="detail-kv">${m.kw} kW</div><div class="detail-grid"><div><small>In</small><b>${pt(m.amp,2)} A</b></div><div><small>LRC</small><b>${pt(m.locked_rotor_current_a,1)} A</b></div><div><small>Aceleração 100% Vt</small><b>${pt(m.start_time_s,2)} s</b></div><div><small>Hot / Cold Stall</small><b>${pt(m.stall_hot_s,1)} / ${pt(m.stall_cold_s,1)} s</b></div></div><p class="muted">Esses dados físicos entram nas referências do TCC do motor. O ajuste 50/51 permanece separado e editável.</p><div class="detail-actions"><button class="btn primary" data-editequip="motors:${esc(id)}">Editar equipamento</button><button class="btn secondary" data-openzone="${z.id}">Abrir ajustes 50/51</button></div>`}else if(type==='cable'){const c=n.cables.find(x=>x.name===id);html+=`<div class="detail-kv">${c.size_mm2} mm²</div><div class="detail-grid"><div><small>Paralelos</small><b>${c.parallel}</b></div><div><small>Comprimento</small><b>${c.length_m} m</b></div><div><small>R1 fluxo</small><b>${c.r1_pf_ohm_per_km} Ω/km</b></div><div><small>Ampacidade</small><b>${c.ampacity_total_a?pt(c.ampacity_total_a,1)+' A':'não informada'}</b></div><div><small>K²S² (fabricante)</small><b>${c.thermal_k2s2_ka2s?pt(c.thermal_k2s2_ka2s,2)+' kA²s':'—'}</b></div></div><div class="detail-actions"><button class="btn primary" data-editequip="cables:${esc(id)}">Editar equipamento</button></div>`}else if(type==='breaker'){const z=n.zones.find(z=>z.breaker===id);html+=z?`<p class="muted">${esc(z.title)}</p><div id="detail-breaker-duty" class="muted small">verificando capacidade de interrupção…</div><div class="detail-actions"><button class="btn primary" data-openzone="${z.id}">Abrir ajustes 50/51</button></div>`:`<p class="muted">Elemento do unifilar.</p>`;$('#element-detail').innerHTML=html;$$('[data-openzone]').forEach(b=>b.onclick=()=>{state.currentZone=b.dataset.openzone;showView('protection')});if(z){try{const d=await api(`/api/breaker-duty/${z.id}`);const el=$('#detail-breaker-duty');if(!el){}else if(!d.available){el.textContent=d.reason||'Verificação indisponível.'}else{const statusLabel={approved:'✓ atende',rejected:'✗ não atende',pending:'⏳ pendente'}[d.status]||d.status;const statusClass={approved:'oktxt',rejected:'warntxt',pending:''}[d.status]||'';el.innerHTML=`<table class="sc-mini-table"><tbody><tr><td>Falta no ponto (${esc(d.governing_fault||'')})</td><td>${fmt(d.duty_ka,2)} kA</td></tr><tr><td>Exigido pelo projeto (×1,10)</td><td>${fmt(d.design_required_ka,2)} kA</td></tr><tr><td>Classe padrão recomendada</td><td>${fmt(d.recommended_class_ka,1)} kA</td></tr><tr><td>Interrupção nominal informada</td><td>${d.rating_ka!=null?fmt(d.rating_ka,1)+' kA':'não informado'}</td></tr></tbody></table><p class="${statusClass}">${statusLabel} — ${esc(d.reason||'')}</p>`}}catch(e){const el=$('#detail-breaker-duty');if(el)el.textContent='Verificação indisponível (requer Pandapower).'}}return}else{const z=n.zones.find(z=>z.relay===id||z.breaker===id);html+=z?`<p class="muted">${esc(z.title)}</p><div class="detail-actions"><button class="btn primary" data-openzone="${z.id}">Abrir ajustes 50/51</button></div>`:`<p class="muted">Elemento do unifilar.</p>`}$('#element-detail').innerHTML=html;$$('[data-openzone]').forEach(b=>b.onclick=()=>{state.currentZone=b.dataset.openzone;showView('protection')});$$('[data-editequip]').forEach(b=>b.onclick=()=>{const [category,name]=b.dataset.editequip.split(':');state.dataSection=category;$$('.data-tab').forEach(x=>x.classList.toggle('active',x.dataset.section===category));showView('data');setTimeout(()=>{const card=document.querySelector(`.equipment-card[data-equip="${CSS.escape(name)}"]`);if(card)card.scrollIntoView({behavior:'smooth',block:'center'})},80)})}

function plotLayout(title,x,y,extra={}){return Object.assign({title:{text:title,font:{size:14}},paper_bgcolor:'#0e1a29',plot_bgcolor:'#0b1520',font:{color:'#dce9f6',family:'Segoe UI,Arial'},xaxis:{title:x,gridcolor:'#243141',zeroline:false},yaxis:{title:y,gridcolor:'#243141',zeroline:false},margin:{l:58,r:18,t:46,b:70}},extra)}
function plotConfig(){return {responsive:true,displaylogo:false,modeBarButtonsToRemove:['lasso2d','select2d']}}

init().catch(e=>{console.error(e);toast(e.message)});

// ===========================================================================
// FOLHA ETAP STAR — tema, rótulos com seta, unifilar embutido e carimbo.
// A geometria (marcas curtas no topo, setas de falta na base, eixos duplicados,
// moldura com ticks internos e sem grade interna) foi copiada do STAR75 do caso.
// ===========================================================================
const ETAP_INK='#000000', ETAP_FRAME='#000000', ETAP_PAPER='#ffffff';
const ETAP_RELAY_COLORS=['#000080','#800080','#b8860b','#008080','#4b0082','#005f87'];
const ETAP_FIXED={start:'#000000',motor:'#e00000',cable:'#a52a2a',trafo:'#006400',fault:'#000000',other:'#404040'};

function etapDeviceKey(t){
 const n=String(t.name||''), k=String(t.kind||'');
 if(k==='motor_start')return 'start:'+n.replace('-100%','');
 if(k.startsWith('motor_thermal'))return 'motor:'+n.split(' ')[0];
 if(k==='cable'||k==='ampacity')return 'cable:'+n.split(' ')[0];
 if(k==='relay_effective'||k==='pickup_mark')return 'relay:'+(t.relay||n.split(' ')[0]);
 if(k.startsWith('transformer')||k==='inrush')return 'trafo:'+n.split(' ')[0];
 if(k.startsWith('fault'))return 'fault';
 return 'other';
}
function etapColorMap(traces){
 const map={}; let ri=0;
 traces.forEach(t=>{const key=etapDeviceKey(t); if(map[key])return;
  const fam=key.split(':')[0];
  map[key]=fam==='relay'?ETAP_RELAY_COLORS[ri++%ETAP_RELAY_COLORS.length]:(ETAP_FIXED[fam]||ETAP_FIXED.other);});
 return map;
}

// --- posição do rótulo -----------------------------------------------------
// Escolhe um ponto da curva dentro da janela e espalha os textos nas bordas
// esquerda/direita da folha, como o Star faz.
function etapAnchor(t,xr,yr){
 const xs=t.x||[],ys=t.y||[];let best=null;
 const lx=Math.log10(xr[0]),hx=Math.log10(xr[1]),ly=Math.log10(yr[0]),hy=Math.log10(yr[1]);
 for(let i=0;i<xs.length;i++){const x=xs[i],y=ys[i];
  if(!(x>0&&y>0))continue;
  if(x<xr[0]*1.02||x>xr[1]*0.98||y<yr[0]*1.05||y>yr[1]*0.95)continue;
  // Distância normalizada até o centro da folha: dá um ponto de ancoragem
  // dentro da janela, como o Star faz, em vez do fim da polilinha.
  const u=(Math.log10(x)-lx)/(hx-lx)-0.5, v=(Math.log10(y)-ly)/(hy-ly)-0.5;
  const d=u*u+v*v;
  if(!best||d<best.d)best={x,y,d};}
 if(best)return best;
 for(let i=0;i<xs.length;i++)if(xs[i]>0&&ys[i]>0)return {x:xs[i],y:ys[i]};
 return null;
}
function etapPlaceLabels(items,xr,yr,reserveLeftBelow){
 const lx=Math.log10(xr[0]),hx=Math.log10(xr[1]),ly=Math.log10(yr[0]),hy=Math.log10(yr[1]);
 const midx=(lx+hx)/2, out=[];
 const sides={left:[],right:[]};
 items.forEach(it=>{(Math.log10(it.x)<=midx?sides.left:sides.right).push(it)});
 for(const side of['left','right']){
  const list=sides[side].sort((a,b)=>Math.log10(b.y)-Math.log10(a.y));
  const span=hy-ly, minGap=span*0.055;
  // Piso da coluna: à esquerda o unifilar embutido ocupa a parte de baixo.
  const floorFrac=(side==='left'&&reserveLeftBelow)?reserveLeftBelow:0.05;
  let prev=null;
  list.forEach(it=>{
   let ty=Math.log10(it.y);
   if(prev!==null&&prev-ty<minGap)ty=prev-minGap;
   ty=Math.min(hy-span*0.04,Math.max(ly+span*floorFrac,ty));
   prev=ty;
   out.push({text:it.text,color:it.color,x:it.x,y:it.y,
    ax:Math.pow(10,side==='left'?lx+(hx-lx)*0.03:hx-(hx-lx)*0.03),
    ay:Math.pow(10,ty),anchor:side==='left'?'left':'right'});});
 }
 return out;
}

// --- unifilar do trecho selecionado — painel separado, ao lado do gráfico --
// V29: deixou de ser desenhado em coordenadas de papel dentro do Plotly (o
// que sobrepunha as curvas e forçava reservar espaço, esticando o gráfico).
// Agora é um SVG independente, sempre em área própria, igual ao Star original.
// Cor única vermelha (#ff0000), igual ao STAR original.
const MINI_SLD_COLOR='#ff0000';
function renderMiniSingleLine(sl,dark){
 const panel=$('#tcc-singleline-panel'); if(!panel)return;
 panel.classList.toggle('light',!dark);
 if(state.tccSingleLine===false||!sl||!sl.elements||!sl.elements.length){panel.innerHTML='';return}
 const C=MINI_SLD_COLOR, DIM='#c9a3a3';
 const n=sl.elements.length, rowH=62, padTop=30, padBottom=22, X=42, W=160;
 const H=padTop+rowH*n+padBottom;
 const L=(x0,y0,x1,y1,w,clr)=>`<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="${clr||C}" stroke-width="${w||1.3}"/>`;
 const T=(x,y,text,anchor,size,clr)=>`<text x="${x}" y="${y}" fill="${clr||C}" font-size="${size||9.5}" font-family="Arial" text-anchor="${anchor||'start'}">${esc(text)}</text>`;
 // TC (transformador de corrente): duas alças à esquerda do condutor, no tap do relé.
 const ct=(x,y,clr)=>`<path d="M${x} ${y-8} q-6 0 -6 4 q0 4 6 4 q-6 0 -6 4 q0 4 6 4" fill="none" stroke="${clr||C}" stroke-width="1.2"/>`;
 // Bobina do trafo: duas fileiras de arcos, igual ao símbolo do unifilar principal.
 // Fileira de arcos do enrolamento. dir='down' = arcos para baixo (enrolamento
 // de cima), dir='up' = arcos para cima (enrolamento de baixo); as duas
 // fileiras ficam voltadas uma para a outra, como no símbolo do Star.
 const coil=(cx,rowY,dir,clr)=>{const n=4,bw=8,r=bw/2,w=n*bw,sweep=dir==='down'?0:1;
  let d=`M${cx-w/2} ${rowY}`;for(let i=0;i<n;i++)d+=` a${r} ${r} 0 0 ${sweep} ${bw} 0`;
  return `<path d="${d}" fill="none" stroke="${clr||C}" stroke-width="1.2"/>`};
 let body='';
 body+=L(X-16,padTop,X+16,padTop,2.2);
 body+=T(X-16,padTop-9,sl.bus||'','start',9.5);
 let y=padTop;
 sl.elements.forEach((el,i)=>{
  const y1=padTop+rowH*(i+1), mid=(y+y1)/2;
  const clr=el.dim?DIM:C;
  if(el.type==='breaker'){
   const tapY=y+18, brkTop=y+38;
   body+=L(X,y,X,tapY,1.3,clr)+ct(X,tapY,clr)+L(X,tapY,X,brkTop,1.3,clr)+`<rect x="${X-7}" y="${brkTop}" width="14" height="14" fill="none" stroke="${clr}" stroke-width="1.3"/>`+L(X,brkTop+14,X,y1,1.3,clr);
   body+=L(X+7,tapY,X+30,tapY,1.3,clr)+`<circle cx="${X+46}" cy="${tapY}" r="15" fill="none" stroke="${clr}" stroke-width="1.3"/>`+T(X+46,tapY+3.5,'R','middle',9.5,clr);
   body+=T(X+66,tapY+3.5,el.relay||el.label,'start',9.5,clr);
   body+=T(X-12,tapY+3.5,el.label,'end',9.5,clr);
  }else if(el.type==='relay_only'){
   body+=L(X,y,X,mid,1.3,clr)+ct(X,mid,clr)+L(X,mid,X,y1,1.3,clr);
   body+=L(X+7,mid,X+30,mid,1.3,clr)+`<circle cx="${X+46}" cy="${mid}" r="15" fill="none" stroke="${clr}" stroke-width="1.3"/>`+T(X+46,mid+3.5,'R','middle',9.5,clr);
   body+=T(X+66,mid+3.5,el.relay||el.label,'start',9.5,clr);
  }else if(el.type==='cable'){
   const zx=[0,6,-6,6,-6,0], seg=(y1-y)/(zx.length-1);
   for(let k=0;k<zx.length-1;k++)body+=L(X+zx[k],y+seg*k,X+zx[k+1],y+seg*(k+1),1.3,clr);
   body+=T(X+22,mid-4,el.label,'start',9.5,clr);
   if(el.sub)body+=T(X+22,mid+11,el.sub,'start',8.5,clr);
  }else if(el.type==='motor'){
   body+=L(X,y,X,y1-19,1.3,clr)+`<circle cx="${X}" cy="${y1}" r="18" fill="none" stroke="${clr}" stroke-width="1.5"/>`;
   body+=T(X+26,y1-2,el.label,'start',9.5,clr);
   if(el.sub)body+=T(X+26,y1+13,el.sub,'start',8.5,clr);
  }else if(el.type==='transformer'){
   // Antes eram dois círculos de r=15 a 18 px de distância: eles se invadiam e
   // o condutor morria dentro do círculo de cima, o que deixava o símbolo
   // torto. Agora são as duas fileiras de arcos do Star, com o fio de cima
   // terminando na fileira superior e o de baixo saindo da inferior.
   const topY=mid-9, botY=mid+9;
   body+=L(X,y,X,topY,1.3,clr)+coil(X,topY,'down',clr)+coil(X,botY,'up',clr)+L(X,botY,X,y1,1.3,clr);
   body+=T(X+26,mid+3.5,el.label+(el.sub?' · '+el.sub:''),'start',9.5,clr);
  }else{
   body+=L(X,y,X,y1,1.3,clr)+L(X-16,y1,X+16,y1,2.2,clr)+T(X-16,y1+15,el.label,'start',9.5,clr);
  }
  y=y1;
 });
 panel.innerHTML=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;max-height:100%">${body}</svg>`;
}

// --- carimbo do rodapé -----------------------------------------------------
function etapSheetBlock(sheet,title){
 if(!sheet)return '';
 const row=(pairs)=>pairs.map(([k,v])=>`<div class="etap-field"><span>${esc(k)}:</span><b>${esc(v||'')}</b></div>`).join('');
 return `<div class="etap-stamp">
   <div class="etap-stamp-left">${row(sheet.left||[])}</div>
   <div class="etap-stamp-mid"><b>${esc(sheet.sheet||'')}</b><span>${esc(title||'')}</span></div>
   <div class="etap-stamp-right">${row(sheet.right||[])}
     <div class="etap-field wide tool"><b>${esc(sheet.tool||'')}</b></div></div>
 </div>`;
}

// Only controlled demo metadata crosses the browser-storage boundary.
export const storageKey='careward-demo-onboarding-v1';
export const tasks=['Discuss the next steps with the person','Identify the staff member coordinating follow-up','Review outstanding information with the referrer','Explain the onboarding process'];
const ids=['DEMO-001','DEMO-002','DEMO-003','DEMO-004'];
const statuses=['not_started','in_progress','done'];
const labels={not_started:'Not started',in_progress:'In progress',done:'Demo step completed'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function cleanRecord(value){
 if(!value||!ids.includes(value.id)||!Array.isArray(value.tasks)||value.tasks.length!==tasks.length||!value.tasks.every(s=>statuses.includes(s)))throw Error('Invalid demo record');
 if(!Number.isSafeInteger(value.savedAt)||value.savedAt<0||!Array.isArray(value.questions)||value.questions.length>100)throw Error('Invalid saved snapshot');
 const questions=value.questions.map(q=>{if(!['mobility','medication'].includes(q.kind)||!['waiting','needs_review','reviewed'].includes(q.status))throw Error('Invalid question');return {kind:q.kind,status:q.status};});
 return {id:value.id,tasks:[...value.tasks],savedAt:value.savedAt,questions};
}
export function saveRecord(storage,record){const clean=cleanRecord(record);storage.setItem(storageKey+':'+clean.id,JSON.stringify(clean));return clean;}
export function loadRecord(storage,id){const raw=storage.getItem(storageKey+':'+id);if(!raw)return null;const value=cleanRecord(JSON.parse(raw));if(value.id!==id)throw Error('Record mismatch');return value;}
const working=new Map();
const pending=new Map();
function read(id){if(working.has(id))return {record:working.get(id)};try{const record=loadRecord(localStorage,id);if(record)working.set(id,record);return {record};}catch{return {error:'Saved demo data could not be read. You can clear it below and start again.'};}}
export function renderOnboarding(root,referral){
 const {record:saved,error}=read(referral.id);
 const draft=saved||{id:referral.id,tasks:tasks.map(()=> 'not_started'),savedAt:0,questions:[]};
 const questions=referral.questions.map(q=>({kind:q.kind,status:q.reviewed?'reviewed':q.response?'needs_review':'waiting'}));
 root.innerHTML=`<section class="panel"><div class="eyebrow">CONTINUITY OF CARE · DEMO</div><h2>Continue onboarding</h2><p>Keep a checklist for ${esc(referral.id)} while intake work continues. These are proposed coordination steps, not confirmed IHH requirements or an admission decision.</p><p><strong>Current session:</strong> ${questions.filter(q=>q.status!=='reviewed').length} open clarification(s). Reviewed replies do not establish clinical eligibility.</p>${tasks.map((name,i)=>`<label class="field-label" for="onboarding-${i}">${name}</label><select id="onboarding-${i}" data-onboarding-task="${i}">${statuses.map(s=>`<option value="${s}" ${(pending.get(referral.id)||draft.tasks)[i]===s?'selected':''}>${labels[s]}</option>`).join('')}</select>`).join('')}<p class="notice">Save only this invented demo checklist and clarification categories on this browser. No names, PDFs, extracted fields, replies, clinical decisions or uploaded records are saved. This is not a shared client record.</p><button class="button primary" id="onboarding-save">Save demo progress on this device</button> <button class="button" id="onboarding-clear">Clear saved demo progress</button><p id="onboarding-status" role="status">${pending.has(referral.id)?'Unsaved checklist changes. Save demo progress to retain them after refresh.':error|| (draft.savedAt?`Saved on this device: ${esc(new Date(draft.savedAt).toLocaleString())}.`:'Not saved on this device.')}</p><div id="onboarding-snapshot">${draft.savedAt?`<h3>Last saved clarification snapshot</h3><p>${draft.questions.length?draft.questions.map(q=>`${q.kind==='mobility'?'Transfer documentation':'Medication documentation'}: ${q.status.replaceAll('_',' ')}`).join('; '):'No clarification requests at time of save.'}</p><p class="muted">Historical demo snapshot only. The referral queue and evidence are session-only; reopen and verify the original sources before continuing clinical review.</p>`:''}</div></section>`;
 root.querySelectorAll('[data-onboarding-task]').forEach(el=>el.onchange=()=>{pending.set(referral.id,[...root.querySelectorAll('[data-onboarding-task]')].map(el=>el.value));root.querySelector('#onboarding-status').textContent='Unsaved checklist changes. Save demo progress to retain them after refresh.';});
 root.querySelector('#onboarding-save').onclick=()=>{try{const next=saveRecord(localStorage,{id:referral.id,tasks:[...root.querySelectorAll('[data-onboarding-task]')].map(el=>el.value),savedAt:Date.now(),questions});working.set(referral.id,next);pending.delete(referral.id);renderOnboarding(root,referral);}catch{root.querySelector('#onboarding-status').textContent='Could not save. Browser storage may be unavailable or full. Keep this page open; your changes are not retained after refresh.';}};
 root.querySelector('#onboarding-clear').onclick=()=>{if(!confirm('Clear saved demo onboarding progress for '+referral.id+' on this device?'))return;try{localStorage.removeItem(storageKey+':'+referral.id);working.delete(referral.id);pending.delete(referral.id);renderOnboarding(root,referral);}catch{root.querySelector('#onboarding-status').textContent='Could not clear browser storage. Use your browser site-data settings.';}};
}
export function renderClientProgress(root,id){
 const {record,error}=read(id);
 root.innerHTML=`<section class="panel"><h2>Next-step conversations</h2><p>Example ${esc(id)} · ${record?'Saved demo checklist from this device.':'No saved demo checklist yet.'} This is a preview, not your actual care record.</p>${record?`<ul>${tasks.map((task,i)=>`<li>${task} — <strong>${labels[record.tasks[i]]}</strong></li>`).join('')}</ul><p>Last saved ${esc(new Date(record.savedAt).toLocaleString())}.</p>`:''}<p>${error||'Your care team must explain your actual next steps. Completing this checklist does not confirm a place, insurance coverage or an arrival time.'}</p></section>`;
}
export function startTour(role){
 if(document.querySelector('#careward-tour'))return;
 const steps=role==='ihh'?[
 ['Start with the referral inbox','Open a DEMO referral to see clarification requests and intake tasks. Use Review packet for the document workspace.'],
 ['Open the full packet','Choose one de-identified PDF, up to 25 MB, or try the synthetic example. The public site previews PDFs; local backend extraction is a separate capability.'],
 ['Check the source evidence','Review fields beside source pages. Missing, conflicting and removed information stays unresolved until a person checks it. AI suggestions are not final decisions.'],
 ['Confirm a next step','Review findings and record a rationale before confirming an outcome. Request clarification when the packet does not support a decision.'],
 ['Continue onboarding','Return to a DEMO referral in the inbox for Continue onboarding. Explicitly save demo checklist progress on this device. Uploaded records and clinical details are not retained.']
 ]:role==='hospital'?[
 ['Prepare a referral','Use the synthetic example packet to inspect completeness. Missing information stays visible; acknowledge gaps before simulating submission.'],
 ['Answer intake questions','Requests from IHH appear in this preview. Provide a synthetic response or mark information unavailable. Nothing is emailed or sent to IHH.'],
 ['Keep the loop moving','IHH staff still need to review replies. A response does not establish eligibility or placement.']
 ]:[
 ['Understand your referral','A referral is a request for care. This preview does not confirm a place or arrival time.'],
 ['See the next conversations','The saved demo checklist shows coordination progress. Your actual next steps must come from your care team.'],
 ['Ask for help','Use the suggested questions when speaking with staff. This site does not send messages or contact your care team.']
 ];
 const previous=document.activeElement;const dialog=document.createElement('dialog');dialog.id='careward-tour';dialog.className='panel';dialog.setAttribute('aria-labelledby','tour-title');dialog.setAttribute('aria-describedby','tour-body');dialog.style.cssText='max-width:36rem;width:calc(100% - 2rem);max-height:85vh;overflow:auto;margin:auto;color:inherit';document.body.append(dialog);let index=0;
 const close=()=>{dialog.close();dialog.remove();if(previous?.isConnected)previous.focus();};
 const draw=()=>{dialog.innerHTML=`<p class="eyebrow">CAREWARD WALKTHROUGH · ${index+1} OF ${steps.length}</p><h2 id="tour-title" tabindex="-1">${steps[index][0]}</h2><p id="tour-body">${steps[index][1]}</p><p class="muted">This walkthrough leaves your current work in place.</p><div class="view-switch"><button class="button" id="tour-close">Skip / close</button><button class="button" id="tour-back" ${index?'':'disabled'}>Back</button><button class="button primary" id="tour-next">${index===steps.length-1?'Finish':'Next'}</button></div>`;dialog.querySelector('#tour-close').onclick=close;dialog.querySelector('#tour-back').onclick=()=>{index--;draw();};dialog.querySelector('#tour-next').onclick=()=>{if(index===steps.length-1)close();else{index++;draw();}};dialog.querySelector('h2').focus();};
 dialog.addEventListener('cancel',e=>{e.preventDefault();close();});draw();dialog.showModal();dialog.querySelector('h2').focus();
}

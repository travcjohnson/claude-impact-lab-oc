// Browser-session synthetic workflow only. Never used as a server authorization model.
export const intakeSteps=['Duplicate referral check','Another provider already involved','OC court check','290 background check','CRM record handoff','Bed availability'];
export const requests={mobility:'Please provide a therapy note describing whether the person can transfer independently and what assistance is needed.',medication:'Please clarify whether the person can take their medications independently, with supporting documentation if available.'};
export function createReferralFlow(now=Date.now()){
 const record=(id,source,age)=>({id,source,receivedAt:now-age*60000,revision:1,questions:[],steps:Object.fromEntries(intakeSteps.map(s=>[s,'not_checked'])),events:[],exportedRevision:null});
 return {mode:'synthetic-demo',records:[record('DEMO-001','Hospital · synthetic',85),record('DEMO-002','SNF · synthetic',35),record('DEMO-003','Community · synthetic',12)],draft:{prepared:false,submittedId:null,gapsAcknowledged:false,items:[{label:'Referral summary',status:'present'},{label:'Therapy / transfer note',status:'missing'},{label:'Medication self-administration',status:'unknown'},{label:'Screening collection date',status:'redacted'}]}};
}
export function changeRecord(r,type,detail,now=Date.now()){r.revision++;r.exportedRevision=null;r.events.push({type,detail,at:now,revision:r.revision});}
export function stage(r){return r.questions.some(q=>q.response&&!q.reviewed)?'Response needs review':r.questions.some(q=>!q.response)?'Waiting for referrer':'Ready for intake review';}
export function remainingMinutes(r,now=Date.now()){return Math.ceil((r.receivedAt+120*60000-now)/60000);}
export function submitReferral(flow,now=Date.now()){
 if(flow.draft.submittedId)return flow.records.find(r=>r.id===flow.draft.submittedId);
 if(!flow.draft.prepared)throw Error('Select the synthetic packet first.');
 if(!flow.draft.gapsAcknowledged)throw Error('Acknowledge the open information before continuing.');
 const r={id:'DEMO-004',source:'Hospital · synthetic',receivedAt:now,revision:1,questions:[],steps:Object.fromEntries(intakeSteps.map(s=>[s,'not_checked'])),events:[],exportedRevision:null,items:structuredClone(flow.draft.items)};
 flow.records.push(r);flow.draft.submittedId=r.id;changeRecord(r,'simulated_submission','No external delivery',now);return r;
}
export function askQuestion(r,kind,now=Date.now()){
 if(!requests[kind])throw Error('Unknown request.');
 if(r.questions.some(q=>q.kind===kind&&!q.reviewed))throw Error('That request is already open.');
 const q={id:`${r.id}-Q${r.questions.length+1}`,kind,text:requests[kind],response:null,reviewed:false,createdAt:now};r.questions.push(q);changeRecord(r,'clarification_requested',q.id,now);return q;
}
export function answerQuestion(r,id,{text='',attachment=false,unavailable=false},now=Date.now()){
 const q=r.questions.find(q=>q.id===id);if(!q||q.response)throw Error('This request is no longer open.');
 text=text.trim();if(!unavailable&&!attachment&&text.length<12)throw Error('Enter at least 12 characters, attach the synthetic example, or mark the information unavailable.');
 if(text.length>2000)throw Error('Keep the answer under 2,000 characters.');
 q.response={text,attachment:attachment?'synthetic-follow-up-note.txt':null,attachmentText:attachment?'SYNTHETIC FOLLOW-UP: This example does not establish transfer independence or medication ability. Staff must verify the source.':null,unavailable,at:now};q.reviewed=false;changeRecord(r,'referrer_responded',q.id,now);
}
export function reviewResponse(r,id,now=Date.now()){
 const q=r.questions.find(q=>q.id===id);if(!q?.response)throw Error('There is no response to review.');if(q.reviewed)return;
 q.reviewed=true;changeRecord(r,'response_reviewed',q.id,now);
}
export function recordStep(r,name,value){if(!intakeSteps.includes(name)||!['not_checked','recorded','needs_follow_up'].includes(value))throw Error('Invalid checklist state.');r.steps[name]=value;changeRecord(r,'manual_step_recorded',{name,value});}
export function crmHandoff(r,reviewer,attested,fields=[]){
 if(!reviewer.trim()||!attested)throw Error('Enter reviewer initials and confirm you reviewed this handoff.');
 if(r.questions.some(q=>q.response&&!q.reviewed))throw Error('Review new responses before preparing the handoff.');
 r.exportedRevision=r.revision;
 return {mode:'synthetic-demo',referralId:r.id,revision:r.revision,reviewer:reviewer.trim(),sent:false,crmConnected:false,clinicalEligibility:'not established',authorization:'not established',confirmedClinicalFields:structuredClone(fields.filter(f=>f.reviewed&&!f.draft&&f.assessment==='verified')),unresolvedFields:structuredClone(fields.filter(f=>!f.reviewed||f.draft||f.assessment!=='verified')),openQuestions:structuredClone(r.questions),manualSteps:structuredClone(r.steps),events:structuredClone(r.events)};
}

// UI-only synthetic fixture. This is not the BE-03 server contract or an API adapter.
export function createFieldReview(){
 const definitions=[
  ['mobility','Mobility / transfer independence','Referral summary: independent. Therapy note: assistance required.','conflicting',[1,2],'MOB-4'],
  ['self_medication','Self-administers medications','Not documented in example packet','missing',[1],'COG-1'],
  ['covid_result','COVID screening result','Negative result documented','extracted',[3],'INF-2'],
  ['covid_date','COVID collection date','Redacted in example','redacted',[3],'INF-2'],
  ['authorization','Authorization status','Request included; approval not documented','missing',[1],null],
  ['authorized_stay','Length of stay authorized','Not documented in example packet','missing',[1],null]
 ];
 return {mode:'synthetic-demo',revision:1,reviewer:'',selectedPage:1,snapshot:null,fields:definitions.map(([id,label,value,status,pages,findingId])=>({id,label,value,originalValue:value,status,pages,source:pages[0],findingId,reviewed:false,assessment:'unresolved',note:'',reviewer:'',history:[]}))};
}
export function invalidateFields(session,field){session.revision++;session.snapshot=null;field.reviewed=false;}
export function saveField(session,index,{value,note,assessment,reviewer}){
 const f=session.fields[index];value=value.trim();note=note.trim();reviewer=reviewer.trim();
 if(!value)return 'Use an explicit unknown value instead of leaving this field blank.';
 if((value!==f.originalValue||value!==f.value)&&note.length<12)return 'Explain the correction in at least 12 characters.';
 if(value!==f.value&&f.history.length&&note===f.note)return 'Add a new explanation for this correction; the previous note describes an earlier value.';
 if(!reviewer)return 'Enter reviewer initials before confirming a field.';
 if(!['verified','unresolved'].includes(assessment))return 'Choose a review assessment.';
 if(assessment==='verified'&&f.status!=='extracted')return 'This example has unresolved source evidence. Keep it open for clarification.';
 if(value.length>4000||note.length>4000||reviewer.length>80)return 'Shorten the value, note or reviewer label.';
 const before={value:f.value,note:f.note,reviewer:f.reviewer,assessment:f.assessment,reviewed:f.reviewed};
 invalidateFields(session,f);
 Object.assign(f,{value,note,assessment,reviewer,reviewed:true});session.reviewer=reviewer;delete f.draft;
 f.history.push({at:new Date().toISOString(),revision:session.revision,before,after:{value,note,reviewer,assessment}});
 return '';
}
export function confirmFieldSummary(session,attested){
 if(session.fields.some(f=>!f.reviewed))return 'Review every field before preparing the summary. Unresolved items may remain open.';
 if(!session.reviewer.trim())return 'Enter reviewer initials before preparing the summary.';
 if(!attested)return 'Confirm that you checked the source and the unresolved items.';
 session.snapshot={mode:'synthetic-demo',revision:session.revision,confirmedAt:new Date().toISOString(),reviewer:session.reviewer,fields:structuredClone(session.fields),authorization:'Not established',clinicalEligibility:'Not evaluated',sent:false};
 return '';
}
export function summaryText(snapshot){
 const lines=['SYNTHETIC DEMO — NOT FOR CLINICAL USE','Reviewed intake summary',`Revision: ${snapshot.revision}`,`Prepared by: ${snapshot.reviewer}`,`Confirmed: ${snapshot.confirmedAt}`,''];
 for(const [title,fields] of [['CONFIRMED FIELDS',snapshot.fields.filter(f=>f.assessment==='verified')],['OPEN QUESTIONS / UNRESOLVED',snapshot.fields.filter(f=>f.assessment!=='verified')]]){
  lines.push(title);if(!fields.length)lines.push('None.');
  for(const f of fields)lines.push(`${f.label}: ${f.value}`,`Source: synthetic page(s) ${f.pages.join(', ')}; original state: ${f.status}; reviewed by ${f.reviewer}`,f.note?`Review note: ${f.note}`:'','');
 }
 lines.push('Authorization: not established. Clinical eligibility: not evaluated.','Limited example fields only; not the complete IHH form.','Nothing has been sent. Local session only; not an authenticated clinical record.');
 return lines.join('\n');
}

export function clarificationText(snapshot){
 const questions={
  mobility:'Please clarify transfer independence; the example referral summary and therapy note disagree.',
  self_medication:'Please provide documentation of medication self-administration ability.',
  covid_result:'Please clarify the documented screening result.',
  covid_date:'Screening timing cannot be assessed because the example date was removed for privacy. Route to an authorized reviewer; do not reconstruct the redacted date.',
  authorization:'Please confirm whether payer authorization has been approved; a request alone does not establish approval.',
  authorized_stay:'Please clarify the authorized length of stay, if authorization has been approved.'
 };
 const unresolved=snapshot.fields.filter(f=>f.assessment!=='verified');
 return ['SYNTHETIC DEMO — UNSENT CLARIFICATION DRAFT',`Based on confirmed review revision ${snapshot.revision}`,`Prepared by: ${snapshot.reviewer}`,'',...unresolved.flatMap((f,i)=>[`${i+1}. ${questions[f.id]||`Please clarify ${f.label}.`}`,`Example source page(s): ${f.pages.join(', ')}`,f.note?`Reviewer context: ${f.note}`:'','']),unresolved.length?'The review remains open pending clarification.':'No unresolved items in this limited example.','No admission decision or insurance authorization is established.','Review this draft before use. Nothing has been sent.'].join('\n');
}

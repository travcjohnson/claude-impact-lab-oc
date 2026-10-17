export const labels = {meets:'Evidence supports', conflict:'Conflicting evidence', unknown:'Unknown', redacted:'Date redacted', unmet:'Does not meet'};
export const sourcePages = [
 {title:'Referral summary',type:'Referral form',body:[['Mobility','Independent with wheelchair use and transfers.'],['Medications','Medication list attached. Ability to self-administer is not documented.'],['Authorization','Authorization request included. Approval is not documented.']]},
 {title:'Therapy assessment',type:'PT / OT note',body:[['Transfers','Assistance required for transfers. This conflicts with the referral summary.'],['Review note','The sequence of these documents cannot be established from this synthetic example.']]},
 {title:'Infection screening',type:'Screening note',body:[['COVID screening','Negative result documented.'],['Collection date','[REDACTED FOR DEMO]'],['Timing','A date is needed to verify the rule for admission.']]}
];
export function createFindings(){return [
 {id:'MOB-4',title:'Independent wheelchair transfers',section:'Mobility',status:'conflict',summary:'The referral summary and therapy note disagree on transfer assistance.',rule:'Wheelchair dependent patients must be able to transfer independently.',pages:[1,2],reviewed:false,note:''},
 {id:'COG-1',title:'Medication self-administration',section:'Daily care',status:'unknown',summary:'A medication list alone does not establish the ability to self-administer.',rule:'Must be capable of self-administering medications (must confirm that patient can self-administer insulin) and receiving medical education.',pages:[1],reviewed:false,note:''},
 {id:'INF-2',title:'Timing of COVID screening',section:'Infection control',status:'redacted',summary:'The collection date is redacted. Timing cannot be verified.',rule:'Covid swab (rapid swab acceptable) documented negative within 24 hours of recuperative care admission if coming from inpatient admission.',pages:[3],reviewed:false,note:''}
].map(f=>({...f,originalStatus:f.status}));}
export function decisionProblem(findings,decision,reviewer,rationale,attested){
 if(findings.some(f=>!f.reviewed))return 'Review each finding before recording an outcome.';
 if(!reviewer.trim())return 'Enter the reviewer name or initials.';
 if(rationale.trim().length<12)return 'Add a specific rationale (at least 12 characters).';
 if(!attested)return 'Confirm that you reviewed the evidence and limitations.';
 if(decision==='approve')return 'Approval is unavailable: this demo covers only three rules, not the full admission criteria.';
 if(decision==='deny'&&!findings.some(f=>f.status==='unmet'))return 'Denial requires a documented criterion that is not met.';
 if(!['clarification','clinical-review','deny'].includes(decision))return 'Select an outcome.';
 return '';
}
export function validateFile(file){
 if(!file)return 'Select a PDF first.';
 if(!/\.pdf$/i.test(file.name))return 'Choose a PDF document.';
 if(file.size>25*1024*1024)return 'Choose a PDF smaller than 25 MB.';
 if(file.size===0)return 'This file is empty. Choose a valid PDF.';
 return '';
}

export function findingReviewProblem(f,status,note){
 const original=f.originalStatus||f.status;
 if((status!==f.status||status!==original)&&note.trim().length<12)return 'Explain the evidence for this change (at least 12 characters).';
 const allowed=original==='conflict'?['conflict','unknown']:[original];
 if(!allowed.includes(status))return 'The fixed example source cannot support that assessment. Keep uncertainty visible and request clarification.';
 if(status!==f.status&&f.note&&note.trim()===f.note.trim())return 'Add a new explanation for this correction; the previous note describes an earlier assessment.';
 return '';
}

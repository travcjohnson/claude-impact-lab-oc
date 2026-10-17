// Read-only "Evidence and gaps" summary for a draft analysis result (BE-03 draft shape).
// Pure functions, no DOM access, no network, no storage. Not wired into app.js yet.
// It never confirms, approves or denies anything: it only shows what the evidence does and does not say.
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export const FINDING_LABELS={meets:'Evidence supports',unmet:'Does not meet',unknown:'Unknown',conflict:'Conflicting evidence',not_applicable:'Not applicable',clinical_review:'Needs clinical review'};
export const FIELD_LABELS={extracted:'Extracted, unreviewed',missing:'Missing',redacted:'Redacted',conflicting:'Conflicting',unreadable:'Unreadable'};
// Order puts the items a person must look at first.
const FINDING_ORDER=['conflict','unknown','clinical_review','unmet','meets','not_applicable'];
const NO_VALUE=['redacted','missing','unreadable'];

// Returns problems with a single citation. Never repairs or drops a citation.
function citationProblems(e,pageCount){
 const p=[];
 if(!e||!Number.isInteger(e.page)||e.page<1||(pageCount&&e.page>pageCount))p.push('citation points outside the packet');
 else if(e.sourceQuality==='unreadable'&&e.quote)p.push('quote cited from an unreadable page');
 return p;
}

// result: the `result` object of an analysis response. options: {synthetic, pageCount}.
export function summarizeAnalysis(result,{synthetic=false,pageCount=0}={}){
 if(!result||typeof result!=='object'||!Array.isArray(result.formFields)||!Array.isArray(result.findings))
  return {ok:false,error:'The analysis result is missing or malformed. Nothing is shown as a finding; use manual source review.'};
 const fields=result.formFields.map(f=>{
  const problems=[];
  const valid=Boolean(FIELD_LABELS[f?.status]);
  if(!valid)problems.push('unrecognised field status');
  if(valid&&NO_VALUE.includes(f.status)&&f.value!=null)problems.push('value present on a '+f.status+' field; shown as unknown');
  const evidence=Array.isArray(f?.evidence)?f.evidence:[];
  evidence.forEach(e=>problems.push(...citationProblems(e,pageCount)));
  const shownValue=!valid||NO_VALUE.includes(f.status)?null:(f.value??null);
  return {id:String(f?.id??''),status:f?.status,label:valid?FIELD_LABELS[f.status]:'Unrecognised',value:shownValue,evidence,
   alternatives:Array.isArray(f?.alternatives)?f.alternatives:[],unresolved:!valid||f.status!=='extracted',problems};
 });
 const known=new Set(fields.map(f=>f.id));
 const findings=result.findings.map(f=>{
  const problems=[];
  const evidence=Array.isArray(f?.evidence)?f.evidence:[];
  const valid=Boolean(FINDING_LABELS[f?.status]);
  if(!valid)problems.push('unrecognised finding status');
  // A supporting or failing finding with no evidence is not trustworthy: downgrade the display, keep the original.
  const unsupported=['meets','unmet'].includes(f?.status)&&evidence.length===0;
  if(unsupported)problems.push('no cited evidence; treated as unknown');
  if(f?.status==='conflict'&&evidence.length<2)problems.push('conflict cites fewer than two sources');
  (Array.isArray(f?.fieldIds)?f.fieldIds:[]).forEach(id=>{if(!known.has(id))problems.push('references unknown field '+id);});
  evidence.forEach(e=>problems.push(...citationProblems(e,pageCount)));
  const shown=unsupported||!valid?'unknown':f.status;
  return {id:String(f?.id??''),ruleId:String(f?.ruleId??''),originalStatus:f?.status,status:shown,label:FINDING_LABELS[shown],
   evidence,rationale:typeof f?.rationale==='string'?f.rationale:'',fieldIds:Array.isArray(f?.fieldIds)?f.fieldIds:[],problems,
   needsAttention:shown!=='not_applicable'&&(shown!=='meets'||problems.length>0)};
 }).sort((a,b)=>FINDING_ORDER.indexOf(a.status)-FINDING_ORDER.indexOf(b.status));
 const cov=result.criteriaCoverage||{};
 const unresolvedRules=Array.isArray(cov.unresolved)?cov.unresolved.map(String):[];
 const auth=result.authorization?.status;
 return {ok:true,synthetic:Boolean(synthetic),fields,findings,
  coverage:{applicable:Number.isInteger(cov.applicable)?cov.applicable:null,evaluated:Number.isInteger(cov.evaluated)?cov.evaluated:null,unresolvedRules,
   // Informational only: never "complete" while anything is unresolved, whatever the source claims.
   complete:cov.complete===true&&unresolvedRules.length===0&&!findings.some(f=>f.needsAttention)&&!fields.some(f=>f.unresolved)},
  authorization:['unknown','requested','approved','denied'].includes(auth)?auth:'unknown',
  counts:{unresolvedFields:fields.filter(f=>f.unresolved).length,needsAttention:findings.filter(f=>f.needsAttention).length}};
}

const cite=e=>e&&Number.isInteger(e.page)?`<li>Original page ${esc(e.page)}: ${e.quote?`“${esc(e.quote)}”`:'<em>no readable quote (redacted or unreadable)</em>'}</li>`:'';

export function renderAnalysisSummary(model){
 if(!model.ok)return `<section class="panel" aria-labelledby="as-h"><h2 id="as-h">Evidence and gaps</h2><p role="alert">${esc(model.error)}</p></section>`;
 const banner=model.synthetic?'<div class="notice"><strong>SYNTHETIC fixture.</strong> Invented example. Not extracted from any packet.</div>':'<div class="notice"><strong>Machine-generated and unreviewed.</strong> Check every item against the original page.</div>';
 const c=model.coverage;
 const cov=`<p>${c.evaluated??'?'} of ${c.applicable??'?'} applicable rules have an evaluation. ${c.unresolvedRules.length?`Unresolved rules: ${c.unresolvedRules.map(esc).join(', ')}.`:'No unresolved rules were listed.'} ${c.complete?'':'Coverage is not complete.'}</p>`;
 const note=p=>p.length?`<p role="note">Check: ${p.map(esc).join('; ')}.</p>`:'';
 const fl=model.findings.map(f=>`<li data-finding="${esc(f.id)}" data-status="${esc(f.status)}"><strong>${esc(f.ruleId)}</strong> — ${esc(f.label)}${f.originalStatus!==f.status?` <em>(source said “${esc(f.originalStatus)}”)</em>`:''}<p>${esc(f.rationale)}</p>${f.evidence.length?`<ul>${f.evidence.map(cite).join('')}</ul>`:'<p><em>No evidence cited.</em></p>'}${note(f.problems)}</li>`).join('');
 const fd=model.fields.map(f=>`<li data-field="${esc(f.id)}" data-status="${esc(f.status)}"><strong>${esc(f.id)}</strong> — ${esc(f.label)}: ${f.value===null?'<em>unknown</em>':esc(f.value)}${f.alternatives.length?`<p>Other reading${f.alternatives.length>1?'s':''}: ${f.alternatives.map(a=>esc(a?.value)).join('; ')}</p>`:''}${f.evidence.length?`<ul>${f.evidence.map(cite).join('')}</ul>`:''}${note(f.problems)}</li>`).join('');
 return `<section class="panel" aria-labelledby="as-h"><h2 id="as-h">Evidence and gaps</h2>${banner}<p role="status">${model.counts.needsAttention} finding(s) and ${model.counts.unresolvedFields} field(s) need a person to look. Authorization: ${esc(model.authorization)} (separate from eligibility). This view does not approve, deny or confirm anything.</p>${cov}<h3>Findings</h3><ul>${fl||'<li>None.</li>'}</ul><h3>Fields</h3><ul>${fd||'<li>None.</li>'}</ul></section>`;
}

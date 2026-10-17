import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {summarizeAnalysis,renderAnalysisSummary,FINDING_LABELS,FIELD_LABELS} from '../analysis-summary.js';
// Synthetic fixture checked into the repo; contains no packet or patient data.
const fx=JSON.parse(readFileSync(new URL('../../backend/fixtures/synthetic-analysis-result.json',import.meta.url),'utf8'));
const opts={synthetic:true,pageCount:fx.request.pages.length};
const model=()=>summarizeAnalysis(structuredClone(fx.result),opts);

test('fixture: conflicting, redacted, missing and unreadable states are preserved, not resolved',()=>{
 const m=model();assert.equal(m.ok,true);
 const by=Object.fromEntries(m.fields.map(f=>[f.id,f]));
 assert.equal(by.transfer_ability.status,'conflicting');assert.equal(by.transfer_ability.alternatives.length,1);
 for(const id of ['covid_swab_date','self_medication','page_3_content']){assert.equal(by[id].value,null);assert.equal(by[id].unresolved,true);}
 assert.equal(by.covid_swab_date.status,'redacted');assert.equal(by.self_medication.status,'missing');assert.equal(by.page_3_content.status,'unreadable');
 assert.equal(m.counts.unresolvedFields,4);
});
test('fixture: conflicts and unknowns sort first; coverage never complete',()=>{
 const m=model();assert.equal(m.findings[0].status,'conflict');
 assert.deepEqual(m.coverage.unresolvedRules,['ADL-1','ADL-2','INF-1']);assert.equal(m.coverage.complete,false);
 assert.equal(m.authorization,'unknown');
});
test('a redacted field never shows a value even if the source supplies one',()=>{
 const r=structuredClone(fx.result);r.formFields[1].value='2026-01-01';
 const f=summarizeAnalysis(r,opts).fields[1];assert.equal(f.value,null);assert.match(f.problems.join(),/shown as unknown/);
});
test('meets/unmet without evidence is displayed as unknown, original status kept',()=>{
 const r=structuredClone(fx.result);r.findings[2].status='meets';r.findings[2].evidence=[];
 const f=summarizeAnalysis(r,opts).findings.find(x=>x.id==='f3');
 assert.equal(f.status,'unknown');assert.equal(f.originalStatus,'meets');assert.equal(f.needsAttention,true);
});
test('unrecognised statuses and out-of-range citations are flagged, not trusted',()=>{
 const r=structuredClone(fx.result);r.findings[0].status='approved';r.findings[0].evidence[0].page=99;
 const f=summarizeAnalysis(r,opts).findings.find(x=>x.id==='f1');
 assert.equal(f.status,'unknown');assert.match(f.problems.join(),/unrecognised/);assert.match(f.problems.join(),/outside the packet/);
 const r2=structuredClone(fx.result);r2.formFields[0].status='verified';
 const g=summarizeAnalysis(r2,opts).fields[0];assert.equal(g.unresolved,true);assert.equal(g.value,null);
});
test('source-claimed coverage.complete is ignored while anything is unresolved',()=>{
 const r=structuredClone(fx.result);r.criteriaCoverage.complete=true;assert.equal(summarizeAnalysis(r,opts).coverage.complete,false);
 r.criteriaCoverage.unresolved=[];assert.equal(summarizeAnalysis(r,opts).coverage.complete,false);
});
test('malformed result yields an error, not partial findings',()=>{
 for(const bad of [null,{},{formFields:[]},{formFields:{},findings:[]}])assert.equal(summarizeAnalysis(bad).ok,false);
 assert.match(renderAnalysisSummary(summarizeAnalysis(null)),/manual source review/);
});
test('render labels synthetic data, escapes content and offers no actions',()=>{
 const r=structuredClone(fx.result);r.findings[0].rationale='<img src=x onerror=alert(1)>';
 const html=renderAnalysisSummary(summarizeAnalysis(r,opts));
 assert.match(html,/SYNTHETIC fixture/);assert.ok(!html.includes('<img'));assert.match(html,/&lt;img/);
 assert.match(html,/does not approve, deny or confirm/);assert.ok(!/<button|<input|<form/.test(html));
 assert.match(html,/Redacted/);assert.match(html,/no readable quote/);
 assert.match(renderAnalysisSummary(summarizeAnalysis(structuredClone(fx.result),{pageCount:3})),/Machine-generated and unreviewed/);
});
test('labels match the fixture statusMapping',()=>{
 assert.deepEqual(FINDING_LABELS,fx._meta.statusMapping.findings);assert.deepEqual(FIELD_LABELS,fx._meta.statusMapping.fields);
});

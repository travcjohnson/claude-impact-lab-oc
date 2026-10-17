import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createFindings,decisionProblem,validateFile} from '../model.js';
import {readFileSync} from 'node:fs';
const reviewed=()=>createFindings().map(f=>({...f,reviewed:true}));
test('unreviewed evidence blocks confirmation',()=>assert.match(decisionProblem(createFindings(),'clarification','AB','Please clarify transfers.',true),/Review each/));
test('unknown or redacted evidence can be reviewed without becoming eligible',()=>{const f=reviewed();assert.equal(decisionProblem(f,'clarification','AB','Please clarify transfers.',true),'');assert.equal(f[2].status,'redacted');assert.match(decisionProblem(f,'approve','AB','Everything reviewed.',true),/Approval is unavailable/);});
test('denial requires an unmet criterion',()=>{const f=reviewed();assert.match(decisionProblem(f,'deny','AB','Evidence reviewed.',true),/requires/);f[0].status='unmet';assert.equal(decisionProblem(f,'deny','AB','Source confirms assisted transfers.',true),'');});
test('identity rationale and attestation required',()=>{assert.match(decisionProblem(reviewed(),'clarification','','Please clarify transfers.',true),/reviewer/);assert.match(decisionProblem(reviewed(),'clarification','AB','',true),/rationale/);assert.match(decisionProblem(reviewed(),'clarification','AB','Please clarify transfers.',false),/Confirm/);});
test('reject invalid and oversized selections',()=>{assert.ok(validateFile({name:'x.html',size:100}));assert.ok(validateFile({name:'x.pdf',size:0}));assert.ok(validateFile({name:'x.pdf',size:26*1024*1024}));assert.equal(validateFile({name:'x.pdf',size:100}),'');});
test('fixture criterion IDs and wording match repository source',()=>{const source=JSON.parse(readFileSync(new URL('../../challenges/1-referral-intake/criteria/admission-criteria.json',import.meta.url)));for(const f of createFindings()){const r=source.rules.find(r=>r.id===f.id);assert.ok(r, f.id);assert.equal(f.rule.replace(/\.$/,''),r.text.replace(/\.$/,''));}});

// Fixed synthetic sources cannot support a definitive failure or success.
test('synthetic assessment changes preserve source uncertainty and fresh reasons', async()=>{
 const {findingReviewProblem}=await import('../model.js');const findings=createFindings();
 for(const f of findings){assert.match(findingReviewProblem(f,'unmet','A long but unsupported claim.'),/cannot support/);assert.match(findingReviewProblem(f,'meets','A long but unsupported claim.'),/cannot support/);}
 const f=findings[0];assert.equal(findingReviewProblem(f,'unknown','The conflicting notes cannot establish independence.'),'');
 f.status='unknown';f.note='The conflicting notes cannot establish independence.';
 assert.match(findingReviewProblem(f,'unknown',''),/Explain/);assert.match(findingReviewProblem(f,'conflict',f.note),/new explanation/);
});

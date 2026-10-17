import test from 'node:test';
import assert from 'node:assert/strict';
import {createFieldReview,saveField,invalidateFields,confirmFieldSummary,summaryText,clarificationText} from '../field-review-model.js';
const review=(s,i,changes={})=>saveField(s,i,{value:s.fields[i].value,note:'',assessment:'unresolved',reviewer:'QA',...changes});
test('review does not turn missing, conflicting or redacted evidence into a fact',()=>{
 const s=createFieldReview();for(const i of [0,1,3,4,5]){assert.match(review(s,i,{assessment:'verified'}),/unresolved/);assert.equal(s.fields[i].reviewed,false);assert.equal(review(s,i),'');assert.equal(s.fields[i].assessment,'unresolved');}
});
test('correction retains original and versioned history and requires explanation',()=>{
 const s=createFieldReview(),original=s.fields[0].value;
 assert.match(review(s,0,{value:'Changed'}),/correction/);
 assert.match(review(s,0,{reviewer:''}),/initials/);
 assert.equal(review(s,0,{value:'Clarification remains necessary',note:'Source documents disagree on assistance.'}),'');
 assert.equal(s.fields[0].originalValue,original);assert.equal(s.fields[0].history[0].before.value,original);assert.equal(s.fields[0].history[0].after.reviewer,'QA');
});
test('summary requires complete review and attestation; exports keep open questions separate',()=>{
 const s=createFieldReview();assert.match(confirmFieldSummary(s,true),/every field/);
 s.fields.forEach((_,i)=>assert.equal(review(s,i,{assessment:i===2?'verified':'unresolved'}),''));
 assert.match(confirmFieldSummary(s,false),/Confirm/);assert.equal(confirmFieldSummary(s,true),'');
 const text=summaryText(s.snapshot);assert.match(text,/CONFIRMED FIELDS\nCOVID screening result/);assert.match(text,/OPEN QUESTIONS \/ UNRESOLVED\nMobility/);assert.match(text,/Authorization: not established/);
 const old=s.snapshot;invalidateFields(s,s.fields[2]);assert.equal(s.snapshot,null);assert.equal(s.fields[2].reviewed,false);assert.equal(old.fields[2].reviewed,true);
 assert.match(confirmFieldSummary(s,true),/every field/);
});

test('clarification includes only unresolved items and preserves redaction limits',()=>{
 const s=createFieldReview();s.fields.forEach((_,i)=>review(s,i,{assessment:i===2?'verified':'unresolved'}));confirmFieldSummary(s,true);
 const draft=clarificationText(s.snapshot);assert.match(draft,/UNSENT CLARIFICATION/);assert.match(draft,/do not reconstruct the redacted date/);assert.match(draft,/Example source page\(s\): 1, 2/);assert.doesNotMatch(draft,/Please clarify the documented screening result/);
});

test('each subsequent field correction needs its own note',()=>{
 const s=createFieldReview();assert.equal(review(s,0,{value:'First correction',note:'First correction evidence note.'}),'');
 assert.match(review(s,0,{value:'Second correction',note:'First correction evidence note.'}),/new explanation/);
 assert.match(review(s,0,{value:s.fields[0].originalValue,note:''}),/correction/);
});

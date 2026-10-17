import test from 'node:test';
import assert from 'node:assert/strict';
import {createReferralFlow,submitReferral,askQuestion,answerQuestion,reviewResponse,stage,crmHandoff,remainingMinutes,recordStep,intakeSteps} from '../referral-flow-model.js';
test('submission keeps gaps and redactions, has one receipt and uses a provisional clock',()=>{
 const flow=createReferralFlow(10000000);assert.throws(()=>submitReferral(flow),/packet/);flow.draft.prepared=true;assert.throws(()=>submitReferral(flow),/Acknowledge/);flow.draft.gapsAcknowledged=true;const r=submitReferral(flow,10000000);assert.equal(r.items[3].status,'redacted');assert.equal(remainingMinutes(r,10000000),120);assert.equal(remainingMinutes(r,10000000+121*60000),-1);assert.equal(submitReferral(flow),r);assert.equal(flow.records.length,4);
});
test('response requires human review and never establishes clinical eligibility',()=>{
 const r=createReferralFlow().records[0];const q=askQuestion(r,'mobility');assert.equal(stage(r),'Waiting for referrer');assert.throws(()=>askQuestion(r,'mobility'),/already open/);assert.throws(()=>answerQuestion(r,q.id,{text:'short'}),/12/);answerQuestion(r,q.id,{unavailable:true});assert.equal(stage(r),'Response needs review');assert.throws(()=>crmHandoff(r,'QA',true),/Review new/);reviewResponse(r,q.id);const exportData=crmHandoff(r,'QA',true);assert.equal(exportData.clinicalEligibility,'not established');assert.equal(exportData.confirmedClinicalFields.length,0);assert.equal(exportData.openQuestions[0].response.unavailable,true);assert.equal(exportData.sent,false);assert.throws(()=>answerQuestion(r,q.id,{text:'overwrite response'}),/no longer open/);recordStep(r,intakeSteps[0],'needs_follow_up');assert.equal(r.exportedRevision,null);
});
test('referrals and responses remain isolated and attachment is an explicit fixture',()=>{
 const flow=createReferralFlow();const a=flow.records[0],b=flow.records[1];const q=askQuestion(a,'medication');assert.throws(()=>answerQuestion(b,q.id,{attachment:true}),/no longer open/);answerQuestion(a,q.id,{attachment:true});assert.match(q.response.attachmentText,/SYNTHETIC/);assert.equal(b.questions.length,0);assert.equal(q.reviewed,false);
});
test('CRM handoff separates confirmed source fields from unresolved or edited ones',()=>{
 const r=createReferralFlow().records[0];const fields=[{id:'verified',reviewed:true,assessment:'verified'},{id:'edited',reviewed:true,assessment:'verified',draft:{value:'unsaved'}},{id:'unknown',reviewed:true,assessment:'unresolved'}];const data=crmHandoff(r,'QA',true,fields);assert.deepEqual(data.confirmedClinicalFields.map(f=>f.id),['verified']);assert.deepEqual(data.unresolvedFields.map(f=>f.id),['edited','unknown']);
});
test('new responses take priority even when another clarification is outstanding',()=>{
 const r=createReferralFlow().records[0];const q=askQuestion(r,'mobility');askQuestion(r,'medication');answerQuestion(r,q.id,{unavailable:true});assert.equal(stage(r),'Response needs review');reviewResponse(r,q.id);assert.equal(stage(r),'Waiting for referrer');
});

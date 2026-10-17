import test from 'node:test';
import assert from 'node:assert/strict';
import {validateTextRecord,validateTextDraft,supportsFieldReview} from '../backend-client.js';
const fixture=()=>({schemaVersion:'0.1',referralId:'synthetic',version:1,document:{documentId:'synthetic',pageCount:2},pages:[{page:1,state:'ready',text:'Example one'},{page:2,state:'ocr_failed',text:''}],reviews:{},job:{},analysis:{status:'not_connected'},formFields:[],findings:[]});
test('packet adapter preserves original page gaps and rejects another packet or unknown analysis state',()=>{
 assert.equal(validateTextRecord(fixture(),'synthetic').pages[1].page,2);
 assert.throws(()=>validateTextRecord(fixture(),'other'),/unsupported/);
 const renumbered=fixture();renumbered.pages[1].page=1;assert.throws(()=>validateTextRecord(renumbered,'synthetic'),/page/);
 for(const status of ['not_connected','unavailable','failed','waiting_for_text','queued','checking','needs_review']){const record=fixture();record.analysis.status=status;record.formFields=[{id:'unreviewed'}];assert.equal(validateTextRecord(record,'synthetic'),record);}
 const bad=fixture();bad.analysis.status='approved';assert.throws(()=>validateTextRecord(bad,'synthetic'),/analysis/);
});
test('server draft must match confirmed revision and be unsent',()=>{
 assert.equal(validateTextDraft({version:2,text:'Unsent',sent:false},2).version,2);
 assert.throws(()=>validateTextDraft({version:1,text:'Old',sent:false},2),/match/);
 assert.throws(()=>validateTextDraft({version:2,text:'Sent',sent:true},2),/match/);
});

test('field adapter rejects malformed fields and cross-document citations',()=>{
 const r=fixture();r.formFields=[{id:'f',status:'extracted',value:'example',review:{reviewed:false},evidence:[{documentId:'synthetic',page:1,quote:'Example one'}],alternatives:[]}];
 assert.equal(supportsFieldReview(r),true);r.formFields[0].evidence[0].documentId='other';assert.equal(supportsFieldReview(r),false);r.formFields=[{id:'new'}];assert.equal(supportsFieldReview(r),false);
});

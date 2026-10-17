import test from 'node:test';
import assert from 'node:assert/strict';
import {saveRecord,loadRecord,storageKey} from '../onboarding.js';
const record={id:'DEMO-001',tasks:['done','not_started','in_progress','not_started'],savedAt:123,questions:[{kind:'mobility',status:'waiting',text:'private reply'}],patientName:'private',pdf:'private',fields:['private']};
test('demo retention whitelists metadata and isolates referral records',()=>{
 const data=new Map();const storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
 saveRecord(storage,record);assert.equal([...data.values()].join('').includes('private'),false);assert.equal(loadRecord(storage,'DEMO-001').tasks[0],'done');assert.equal(loadRecord(storage,'DEMO-002'),null);
 data.set(storageKey+':DEMO-002',JSON.stringify(record));assert.throws(()=>loadRecord(storage,'DEMO-002'),/mismatch/);
});
test('invalid and real record identifiers fail closed; storage errors are surfaced',()=>{
 const storage={setItem:()=>{throw Error('Quota exceeded');}};
 assert.throws(()=>saveRecord(storage,{...record,id:'real-referral'}),/Invalid/);
 assert.throws(()=>saveRecord(storage,{...record,tasks:['eligible']}),/Invalid/);
 assert.throws(()=>saveRecord(storage,record),/Quota/);
 assert.throws(()=>loadRecord({getItem:()=>'{broken'},'DEMO-001'));
});

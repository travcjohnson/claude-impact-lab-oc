// Synthetic API responses only; no model or patient data.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 for(const terminal of ['needs_review','unavailable','failed']){
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const record={schemaVersion:'0.1',referralId:'synthetic',version:1,document:{documentId:'synthetic',pageCount:1},pages:[{page:1,state:'ready',text:'SYNTHETIC source text',imageUrl:null}],reviews:{},job:{state:'text_ready'},analysis:{status:'checking'},formFields:[],findings:[],outcome:null};
  await page.route('**/api/**',async route=>{
   const req=route.request(),path=new URL(req.url()).pathname;let body=record;
   if(path==='/api/referrals'&&req.method()==='POST')body={referralId:'synthetic'};
   else if(path.startsWith('/api/jobs/'))body={state:'text_ready'};
   else if(path.endsWith('/review')){const data=req.postDataJSON();assert.equal(data.version,record.version);record.reviews['1']=data;record.version++;}
   else if(path.endsWith('/outcome')){assert.equal(req.postDataJSON().version,record.version);record.outcome=req.postDataJSON();record.version++;}
   else if(path.endsWith('/draft'))body={version:record.version,sent:false,text:'SYNTHETIC unsent draft'};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('http://127.0.0.1:8000/');await page.click('#nav-intake');
  await page.locator('#file-input').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF- synthetic')});
  await page.locator('#extract-local').click();await page.locator('#local-note').waitFor();
  await page.locator('#local-reviewer').fill('QA');await page.locator('#local-note').fill('Synthetic source note retained.');await page.locator('#local-rationale').fill('Synthetic rationale retained.');await page.locator('#local-attested').check();
  assert.equal(await page.locator('#local-outcome button').isDisabled(),true);
  record.analysis={status:terminal,synthetic:true};if(terminal==='needs_review'){record.version++;record.formFields=[];}
  await page.waitForFunction(()=>!document.querySelector('#local-analysis').textContent.includes('Analysis is running'));
  assert.equal(await page.locator('#local-note').inputValue(),'Synthetic source note retained.');assert.equal(await page.locator('#local-rationale').inputValue(),'Synthetic rationale retained.');assert.equal(await page.locator('#local-attested').isChecked(),false);
  assert.equal(await page.getByText('DO NOT RENDER AS VERIFIED',{exact:true}).count(),0);
  await page.locator('#local-review button').click();await page.getByText('Page review saved. Any earlier confirmation and draft are now invalidated.').waitFor();
  await page.locator('#local-attested').check();await page.locator('#local-outcome button').click();await page.locator('#local-export').waitFor();assert.deepEqual(errors,[]);
  await page.close();
 }
 await browser.close();console.log('PASS analysis pending → completed/unavailable/failed: manual review retained, stale attestation reset, current-version confirmation.');
})().catch(e=>{console.error(e);process.exit(1)});

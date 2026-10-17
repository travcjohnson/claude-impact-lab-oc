const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const record={schemaVersion:'0.1',referralId:'synthetic',version:1,document:{documentId:'synthetic',pageCount:2},pages:[1,2].map(page=>({page,state:'ready',text:'SYNTHETIC source page '+page,imageUrl:null})),reviews:{},job:{state:'text_ready',partial:false},analysis:{status:'not_connected'},formFields:[],findings:[],outcome:null};
 let writes=0,outcomes=0;
 await page.route('**/api/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;let body,status=200;
  if(path==='/api/referrals'&&req.method()==='POST')body={referralId:'synthetic',jobId:'synthetic'};
  else if(path.startsWith('/api/jobs/'))body={state:'text_ready'};
  else if(path.endsWith('/review')){writes++;const data=req.postDataJSON();if(writes===1){status=503;body={detail:'Temporary test failure'};}else if(writes===2){record.version++;record.reviews['1']={note:'Another reviewer saved this note.',reviewer:'OTHER'};status=409;body={detail:'Review changed'};}else{assert.equal(data.version,record.version);record.version++;record.reviews[String(data.page)]=data;record.outcome=null;body=record;}}
  else if(path.endsWith('/outcome')){outcomes++;record.version++;record.outcome=req.postDataJSON();body=record;}
  else if(path.endsWith('/draft'))body={version:record.version,sent:false,text:'UNSENT SYNTHETIC confirmed draft'};
  else if(path.endsWith('/search'))body={matches:[{page:2,snippet:'SYNTHETIC hit'}],truncated:false};
  else body=record;
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto('http://127.0.0.1:8000/');await page.click('#nav-intake');await page.locator('#file-input').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF- synthetic test only')});await page.locator('#extract-local').click();await page.locator('#local-note').waitFor();
 await page.locator('#local-reviewer').fill('QA');await page.locator('#local-note').fill('My unsaved synthetic page one note.');await page.locator('#local-rationale').fill('A synthetic clarification rationale to preserve.');
 page.once('dialog',d=>d.dismiss());await page.locator('#nav-guide').click();await page.locator('#local-note').waitFor();assert.match(await page.locator('#local-rationale').inputValue(),/preserve/);await page.locator('#local-page').selectOption('2');await page.locator('#local-page').selectOption('1');assert.match(await page.locator('#local-note').inputValue(),/My unsaved/);assert.match(await page.locator('#local-rationale').inputValue(),/preserve/);
 await page.locator('#local-review button').click();await page.getByText('Temporary test failure').waitFor();assert.match(await page.locator('#local-note').inputValue(),/My unsaved/);
 await page.locator('#local-review button').click();await page.locator('#local-reload').waitFor();assert.equal(await page.locator('#local-review button').isDisabled(),true);
 await page.locator('#local-reload').click();await page.getByText('Another reviewer saved this note.').waitFor({state:'attached'});assert.match(await page.locator('#local-note').inputValue(),/My unsaved/);assert.match(await page.locator('#local-rationale').inputValue(),/preserve/);
 await page.locator('#local-review button').click();await page.getByText('Page review saved. Any earlier confirmation and draft are now invalidated.').waitFor();await page.locator('#local-attested').check();await page.locator('#local-outcome button').dblclick();await page.locator('#local-export').waitFor();assert.equal(outcomes,1);
 await page.locator('#local-draft').fill('An edited unsent synthetic draft.');await page.locator('#local-page').selectOption('2');assert.equal(await page.locator('#local-draft').inputValue(),'An edited unsent synthetic draft.');
 const download=page.waitForEvent('download');await page.locator('#local-export').click();await (await download).saveAs('/tmp/recovery-review.json');const result=JSON.parse(require('fs').readFileSync('/tmp/recovery-review.json','utf8'));assert.equal(result.draftEdited,true);assert.match(result.serverDraft,/confirmed/);
 record.version++;let downloads=0;page.on('download',()=>downloads++);await page.locator('#local-export').click();await page.locator('#local-reload').waitFor();assert.equal(await page.locator('#local-export').count(),0);assert.equal(downloads,0);
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS synthetic API recovery: notes/rationale/draft retained, 503 retry, 409 reload/compare, duplicate guard, verified export, stale export blocked.');
})().catch(e=>{console.error(e);process.exit(1)});

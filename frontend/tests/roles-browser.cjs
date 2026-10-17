const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/');await page.click('#nav-intake');await page.locator('#demo').click();
 await page.locator('#workspace-role').selectOption('client');
 assert.equal(await page.locator('#nav-guide').isVisible(),false);assert.equal(await page.locator('a[href="./team/"]').count(),0);
 assert.match(await page.locator('h1').textContent(),/Your referral/);assert.equal(await page.locator('#file-input').count(),0);assert.equal(await page.locator('#fields-view').count(),0);
 await page.locator('#client-questions').click();assert.match(await page.locator('#client-question').textContent(),/referral stands/);
 await page.locator('#workspace-role').selectOption('hospital');assert.equal(await page.locator('#hospital-submit').isDisabled(),true);await page.locator('#hospital-prepare').click();await page.locator('#gaps-ack').check();await page.locator('#hospital-submit').click();assert.match(await page.locator('#hospital-status').textContent(),/Nothing was sent/);
 await page.locator('#workspace-role').selectOption('ihh');await page.locator('#fields-view').waitFor();
 for(const role of ['client','hospital','ihh']){await page.setViewportSize({width:390,height:844});await page.locator('#workspace-role').selectOption(role);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);}
 // Leaving local review respects the existing unsaved-work guard.
 await page.reload();await page.click('#nav-intake');await page.locator('#file-input').setInputFiles({name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF- synthetic')});
 await page.route('**/api/**',route=>{const path=new URL(route.request().url()).pathname;const record={schemaVersion:'0.1',referralId:'synthetic',version:1,document:{documentId:'synthetic',pageCount:1},pages:[{page:1,state:'ready',text:'Synthetic'}],reviews:{},job:{state:'text_ready'},analysis:{status:'not_connected'},formFields:[],findings:[]};return route.fulfill({contentType:'application/json',body:JSON.stringify(path.endsWith('/referrals')?{referralId:'synthetic'}:path.includes('/jobs/')?{state:'text_ready'}:record)});});
 await page.locator('#extract-local').click();await page.locator('#local-note').fill('Keep my unsaved note.');page.once('dialog',d=>d.dismiss());await page.locator('#workspace-role').selectOption('client');assert.equal(await page.locator('#workspace-role').inputValue(),'ihh');assert.equal(await page.locator('#local-note').inputValue(),'Keep my unsaved note.');
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS distinct role views, synthetic hospital handoff, client questions, staff state retained, mobile and unsaved-work guard.');
})().catch(e=>{console.error(e);process.exit(1)});

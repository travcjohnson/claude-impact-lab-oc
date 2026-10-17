const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));let mode='queued';
 await page.route('**/api/referrals',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({referralId:'synthetic',jobId:'synthetic'})}));
 await page.route('**/api/jobs/*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(mode==='queued'?{state:'extracting',completedPages:1,totalPages:3}:{state:'failed',error:'Synthetic OCR process failure'})}));
 const upload=async()=>{await page.goto('http://127.0.0.1:8000/');await page.click('#nav-intake');await page.locator('#file-input').setInputFiles({name:'synthetic.pdf',mimeType:'text/html',buffer:Buffer.from('%PDF-<script>parent.previewExecuted=true</script>')});const frame=page.locator('iframe');assert.equal(await frame.getAttribute('sandbox'),'');assert.equal(await page.evaluate(async()=>{const r=await fetch(document.querySelector('iframe').src);return(await r.blob()).type;}),'application/pdf');assert.equal(await page.evaluate(()=>Boolean(window.previewExecuted)),false);await page.locator('#extract-local').click();};
 await upload();await page.getByText('Processing your packet').waitFor();await page.locator('#nav-guide').click();await page.getByRole('heading',{name:'Built around the review.'}).waitFor();await page.locator('#nav-intake').click();await page.getByRole('heading',{name:'Your packet is ready to view.'}).waitFor();
 mode='failed';await page.locator('#extract-local').click();await page.getByText('Synthetic OCR process failure').waitFor();assert.equal(await page.locator('#local-outcome').count(),0);await page.locator('#local-back').click();await page.getByRole('heading',{name:'Your packet is ready to view.'}).waitFor();
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS: typed/sandboxed preview, leave processing safely, reopen failed job, error without fabricated review.');
})().catch(e=>{console.error(e);process.exit(1)});

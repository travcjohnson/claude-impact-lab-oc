const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(process.env.FRONTEND_URL||'http://127.0.0.1:4176/');await page.click('#nav-intake');
 await page.locator('#demo').click();await page.locator('#fields-view').click();
 await page.locator('#field-reviewer').fill('QA');
 await page.locator('#next-field').click();assert.equal(await page.locator('#field-0').evaluate(el=>el===document.activeElement),true);
 await page.locator('[data-jump="3"]').click();assert.equal(await page.locator('#field-3').evaluate(el=>el===document.activeElement),true);
 await page.locator('[data-field="0"] [data-source-page="2"]').click();await page.getByRole('heading',{name:'Therapy assessment'}).waitFor();
 await page.locator('#return-to-field').click();assert.equal(await page.locator('#field-0').evaluate(el=>el===document.activeElement),true);
 assert.equal(await page.locator('#prepare-field-summary').isDisabled(),true);
 await page.locator('#field-0').fill('Conflicting transfer documentation; request clarification.');
 await page.locator('[data-field="0"] button[type=submit]').click();await page.getByText('Explain the correction in at least 12 characters.').waitFor();
 await page.locator('#note-0').fill('Both original pages disagree about transfer independence.');
 // Saving another card must not discard this unsaved correction.
 await page.locator('[data-field="1"] button[type=submit]').click();
 assert.equal(await page.locator('#field-0').inputValue(),'Conflicting transfer documentation; request clarification.');
 await page.locator('[data-field="0"] button[type=submit]').click();
 for(let i=2;i<6;i++){if(i===2)await page.locator('#assessment-2').selectOption('verified');await page.locator(`[data-field="${i}"] button[type=submit]`).click();}
 assert.equal(await page.locator('#prepare-field-summary').isEnabled(),true);
 await page.locator('#prepare-field-summary').click();await page.getByText('Confirm that you checked the source and the unresolved items.').waitFor();
 await page.locator('#field-attestation').check();await page.locator('#prepare-field-summary').click();
 const summary=await page.locator('#field-summary-preview').inputValue();assert.match(summary,/CONFIRMED FIELDS\nCOVID screening result/);assert.match(summary,/OPEN QUESTIONS/);
 const download=page.waitForEvent('download');await page.locator('#download-field-json').click();const file=await download;await file.saveAs('/tmp/intake-fields-review.json');
 const record=JSON.parse(require('fs').readFileSync('/tmp/intake-fields-review.json','utf8'));assert.equal(record.mode,'synthetic-demo');assert.equal(record.fields[0].originalValue,'Referral summary: independent. Therapy note: assistance required.');assert.equal(record.fields[0].assessment,'unresolved');assert.equal(record.fields[0].history.length,1);
 await page.locator('.clarification-preview summary').click();const clarificationDownload=page.waitForEvent('download');await page.locator('#download-field-clarification').click();await (await clarificationDownload).saveAs('/tmp/intake-clarification.txt');const clarification=require('fs').readFileSync('/tmp/intake-clarification.txt','utf8');assert.match(clarification,/do not reconstruct/);assert.doesNotMatch(clarification,/Please clarify the documented screening result/);
 await page.screenshot({path:'/tmp/intake-fields-desktop.png',fullPage:true});
 await page.locator('#field-2').fill('Edited after confirmation');await page.locator('[data-jump="2"]').waitFor();assert.equal(await page.locator('#download-field-clarification').count(),0);assert.equal(await page.locator('#download-field-json').count(),0);assert.equal(await page.locator('#prepare-field-summary').isDisabled(),true);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/intake-fields-mobile.png',fullPage:true});
 await page.locator('#back-to-findings').click();await page.locator('#fields-view').click();assert.equal(await page.locator('#field-2').inputValue(),'Edited after confirmation');assert.equal(await page.locator('#download-field-json').count(),0);
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS: evidence navigation, corrections, draft retention, uncertainty, review/export gates, original/history, stale invalidation, mobile, no JS errors.');
})().catch(e=>{console.error(e);process.exit(1)});

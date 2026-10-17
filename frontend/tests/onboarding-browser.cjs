const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox']});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:4176/');
 await page.click('#take-tour');await page.locator('#tour-next').click();assert.match(await page.locator('#tour-title').textContent(),/packet/);await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>document.activeElement.id),'take-tour');
 await page.click('[data-referral="DEMO-001"]');await page.selectOption('#onboarding-0','done');
 // Draft survives referral navigation, but does not leak into another referral.
 await page.click('#flow-back');await page.click('[data-referral="DEMO-002"]');assert.equal(await page.inputValue('#onboarding-0'),'not_started');
 await page.click('#flow-back');await page.click('[data-referral="DEMO-001"]');assert.equal(await page.inputValue('#onboarding-0'),'done');
 await page.click('#ask-referrer button');await page.click('#onboarding-save');await page.reload();await page.click('[data-referral="DEMO-001"]');assert.equal(await page.inputValue('#onboarding-0'),'done');assert.match(await page.locator('#onboarding-snapshot').textContent(),/Transfer documentation: waiting/);
 await page.selectOption('#workspace-role','client');assert.match(await page.locator('main').textContent(),/Demo step completed/);assert.equal(await page.locator('#onboarding-save').count(),0);
 await page.click('#take-tour');assert.match(await page.locator('#tour-title').textContent(),/Understand/);await page.click('#tour-close');
 await page.selectOption('#workspace-role','ihh');page.once('dialog',d=>d.accept());await page.click('#onboarding-clear');assert.equal(await page.inputValue('#onboarding-0'),'not_started');
 await page.evaluate(()=>localStorage.setItem('careward-demo-onboarding-v1:DEMO-001','{broken'));await page.reload();await page.click('[data-referral="DEMO-001"]');assert.match(await page.locator('#onboarding-status').textContent(),/could not be read/);
 await page.evaluate(()=>Storage.prototype.setItem=function(){throw Error('Blocked')});await page.click('#onboarding-save');assert.match(await page.locator('#onboarding-status').textContent(),/Could not save/);
 await page.setViewportSize({width:390,height:844});await page.click('#take-tour');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await page.screenshot({path:'/tmp/careward-tour.png'});
 assert.deepEqual(errors,[]);await browser.close();console.log('PASS onboarding retention, isolation, storage failures, draft continuity and role tours.');
})().catch(e=>{console.error(e);process.exit(1)});

import {mkdir,readFile,writeFile,copyFile,rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const frontend=fileURLToPath(new URL('../',import.meta.url));
const root=path.resolve(frontend,'..'),out=path.join(frontend,'dist');
await rm(out,{recursive:true,force:true});await mkdir(path.join(out,'reference'),{recursive:true});
for(const f of ['index.html','styles.css','model.js','backend-client.js','referral-flow.js','referral-flow-model.js','onboarding.js','field-review-model.js','field-review.js'])await copyFile(path.join(frontend,f),path.join(out,f));
let app=await readFile(path.join(frontend,'app.js'),'utf8');
app=app.replaceAll('../challenges/1-referral-intake/criteria/admission-criteria.md','./reference/admission-criteria.md').replaceAll('../docs/frontend-research-and-handoff.md','./reference/frontend-research-and-handoff.md');
await writeFile(path.join(out,'app.js'),app);
await copyFile(path.join(root,'challenges/1-referral-intake/criteria/admission-criteria.md'),path.join(out,'reference/admission-criteria.md'));
await copyFile(path.join(root,'docs/frontend-research-and-handoff.md'),path.join(out,'reference/frontend-research-and-handoff.md'));
await writeFile(path.join(out,'.nojekyll'),'');
console.log('Built static frontend only in frontend/dist (no PDFs, ZIPs, OCR, or case data).');


await mkdir(path.join(out,'assets'),{recursive:true});
for(const f of ['source-sans-3-latin.woff2','source-sans-3-LICENSE.txt'])await copyFile(path.join(frontend,'assets',f),path.join(out,'assets',f));

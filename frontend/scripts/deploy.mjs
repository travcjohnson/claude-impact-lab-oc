import {execFileSync} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const frontend=fileURLToPath(new URL('../',import.meta.url));
const root=path.resolve(frontend,'..'),dist=path.join(frontend,'dist');
execFileSync(process.execPath,[path.join(frontend,'scripts/build.mjs')],{stdio:'inherit'});
const temp=await mkdtemp(path.join(tmpdir(),'intake-pages-'));
const base={cwd:root,encoding:'utf8'};
function git(args,env){return execFileSync('git',args,{...base,env:env||process.env}).trim();}
try{
 const ref='refs/heads/gh-pages';
 const exists=git(['ls-remote','--heads','origin','gh-pages']);
 let parent;
 if(exists){git(['fetch','origin','gh-pages']);parent=git(['rev-parse','FETCH_HEAD']);}
 const env={...process.env,GIT_INDEX_FILE:path.join(temp,'index'),GIT_WORK_TREE:dist};
 git(['read-tree','--empty'],env);
 git(['--work-tree',dist,'-C',dist,'add','--all'],{...env,GIT_DIR:path.join(root,'.git')});
 const tree=git(['write-tree'],env);
 const args=['commit-tree',tree,...(parent?['-p',parent]:[]),'-m','Deploy referral intake frontend'];
 const commit=git(args);
 execFileSync('git',['push','origin',`${commit}:${ref}`],{...base,stdio:'inherit'});
 console.log('Published frontend files to gh-pages. GitHub Pages must be configured to serve that branch.');
}finally{await rm(temp,{recursive:true,force:true});}

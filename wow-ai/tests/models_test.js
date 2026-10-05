'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),os=require('os');
const M=require('../bridge/models'),P=require('../bridge/protocol'),A=require('../bridge/agents');
const r=id=>M.row({id,name:'Name '+id,variants:['low','high'],efforts:['low','high']});
test('Kilo verbose catalog parses real pretty metadata and drops non-tool models',()=>{
 const text='kilo/orc\n'+JSON.stringify({name:'Orc',capabilities:{toolcall:true},isFree:true,cost:{input:0,output:0},variants:{low:{},high:{}}},null,2)+'\nkilo/no-tools\n'+JSON.stringify({capabilities:{toolcall:false}},null,2);
 const rows=M.parseModels('kilo',text);assert.equal(rows.length,1);assert.equal(rows[0].id,'kilo/orc');assert.deepEqual(rows[0].variants,['low','high']);assert.equal(rows[0].free,true);assert.equal(rows[0].priced,true);
 assert.equal(M.parseModels('agy','gemini-new\tGemini New\nrandom banner\n').length,1);
});
test('IDs cannot become flags or wire controls',()=>{
 for(const id of ['--auto','a;b','two words','x\nfoo','x|y',''])assert.equal(M.validId(id),false);
 for(const id of ['kilo/~vendor/new-model:free','claude-new[1m]','gpt-new'])assert.equal(M.validId(id),true);
 assert.throws(()=>M.parseOptions('{bad'));assert.throws(()=>M.parseOptions({model:'--auto'}));
});
test('catalog cache coalesces concurrent discovery, paginates, searches and refreshes',async()=>{
 let calls=0;const items=Array.from({length:23},(_,i)=>({...r('m'+String(i).padStart(2,'0')),free:i%2===0}));
 const c=new M.ModelCatalog({config:{agents:{kilo:{model:'m00',researchOnly:true}}},defaultAgent:'kilo',loader:async()=>{calls++;return items;}});
 await Promise.all([c.request({chat:'one',id:1,text:'{}'}),c.request({chat:'two',id:2,text:'{}'})]);assert.equal(calls,1);assert.equal(c.wire()[0].items.length,10);assert.equal(c.wire()[0].pages,3);
 await c.request({chat:'one',id:3,text:JSON.stringify({page:3,selected:'m02'})});assert.equal(c.wire()[0].items.length,3);assert.equal(c.wire()[0].selected.id,'m02');
 await c.request({chat:'one',id:4,text:JSON.stringify({query:'m02'})});assert.equal(c.wire()[0].total,1);
 await c.request({chat:'one',id:5,text:JSON.stringify({free:true,refresh:true})});assert.equal(calls,2);assert.equal(c.wire()[0].total,12);
});
test('late results from a previous agent cannot replace the current view',async()=>{
 let finish;const c=new M.ModelCatalog({config:{},defaultAgent:'kilo',loader:id=>id==='kilo'?new Promise(r=>finish=r):Promise.resolve([r('new')])});
 const old=c.request({chat:'one',id:1,text:'{}'});await c.request({chat:'one',id:2,text:'{"agent":"agy"}'});finish([r('old')]);await old;assert.equal(c.wire()[0].agent,'agy');assert.equal(c.wire()[0].items[0].id,'new');
});
test('discovery failure remains a control error, with configured fallback metadata',async()=>{
 const c=new M.ModelCatalog({config:{agents:{grok:{model:'my-model'}}},defaultAgent:'grok',loader:async()=>{throw Error('No discovery');}});await c.request({chat:'one',id:1,text:'{}'});assert.equal(c.wire()[0].status,'error');assert.equal(c.wire()[0].default_model,'my-model');assert.equal(c.wire()[0].can_restrict,false);
});
test('per-chat model, variant and effort arguments leave global config intact',()=>{
 const base={model:'old',permissionMode:'default',variant:'old'},entry={items:[r('new')]};
 const kilo=M.applyOptions(base,'kilo',{model:'new',variant:'high'},entry);assert.equal(kilo.model,'new');assert.equal(base.model,'old');assert.ok(A.AGENTS.kilo.args({cfg:kilo,cwd:'.'}).includes('high'));
 const codex=M.applyOptions(base,'codex',{model:'new',effort:'low',restrict:true},entry);assert.equal(codex.permissionMode,'default');assert.ok(A.AGENTS.codex.args({cfg:codex,cwd:'.'}).includes('model_reasoning_effort="low"'));
 const claude=M.applyOptions(base,'claude',{model:'new',effort:'high',restrict:true},entry);assert.equal(claude.permissionMode,'plan');assert.ok(A.AGENTS.claude.args({cfg:claude}).includes('--effort'));
 assert.throws(()=>M.applyOptions(base,'kilo',{model:'new',variant:'unsupported'},entry));assert.throws(()=>M.applyOptions(base,'grok',{restrict:true},entry));
 assert.equal(M.applyOptions({...base,researchOnly:true},'kilo',{}).researchOnly,true);
 assert.deepEqual(M.applyOptions({...base,extraArgs:['--model','old','--other']},'kilo',{model:'new'},entry).extraArgs,['--other']);
 assert.throws(()=>M.applyOptions({...base,extraArgs:['--auto']},'kilo',{restrict:true},entry));
});
test('both transports preserve per-chat settings and catalog requests',()=>{
 const opts=JSON.stringify({model:'kilo/new',variant:'low',restrict:true}),hex=Buffer.from(opts).toString('hex');
 const job=P.jobsFromStrip(1,['s','c','1','','agent=kilo;opts='+hex,'Name','hello'].join('\x1f'))[0];assert.equal(job.options,opts);
 assert.equal(P.jobsFromStrip(2,['s','c','2','','models','Name','{}'].join('\x1f'))[0].models,true);
 const sv=P.parseOutbox(`WoWAIDB={ ["outbox"]={ ["id"]=2,["models"]=true,["options"]="${hex}",["text"]="7b7d" } }`);assert.equal(sv.models,true);assert.equal(sv.options,opts);
 const lua=P.luaTable('Data',[],{catalogs:[{chat:'c',agent:'kilo',items:[r('new')],selected:r('new'),status:'ready'}],controlAcks:[{session:'s',id:1}],speech:{profile:'goblin',phase:'Loading voice model',neuralAvailable:true}});
 assert.ok(lua.includes('model_catalogs ='));assert.ok(lua.includes('control_acks ='));assert.ok(lua.includes('profile = "goblin"'));assert.ok(lua.includes('phase = "Loading voice model"'));
});
test('real bridge catalog control does not launch an agent or write a transcript',()=>{
 const {spawnSync,execFileSync}=require('child_process'),root=fs.mkdtempSync(path.join(os.tmpdir(),'goblin-model-bridge-')),bridge=path.join(__dirname,'../bridge');
 for(const f of ['bridge.js','models.js','protocol.js','agents.js','research.js','evidence.js','publisher.js','activity.js','instance-lock.js','kilo-policy.js','speech.js','speak.ps1','install-slots.js'])fs.copyFileSync(path.join(bridge,f),path.join(root,f));
 const fake=path.join(root,'fake-model-cli.js');fs.writeFileSync(fake,`if(process.argv.includes('models')){ console.log('new-model\\tNew model'); }else{require('fs').writeFileSync(${JSON.stringify(path.join(root,'AGENT-RAN'))},'bad');}`);
 const cfg={agent:'agy',agents:{agy:{path:fake,model:'old'}},defaultCwd:root,addonDir:path.join(root,'addons'),inboxFile:path.join(root,'addons/WoWAI/Inbox.lua'),savedVariablesFile:path.join(root,'save.lua'),capture:{enabled:false},slots:2,actMax:2,presenceMax:2};
 fs.mkdirSync(path.dirname(cfg.inboxFile),{recursive:true});fs.writeFileSync(path.join(path.dirname(cfg.inboxFile),'WoWAI.toc'),'## Interface: 16001');fs.writeFileSync(path.join(root,'config.json'),JSON.stringify(cfg));fs.writeFileSync(cfg.savedVariablesFile,'WoWAIDB={ ["outbox"]={ ["id"]=1,["chat"]="c",["session"]="s",["models"]=true,["text"]="7b7d" } }');
 execFileSync(process.execPath,[path.join(root,'install-slots.js')]);const before=fs.readFileSync(path.join(root,'config.json'),'utf8');
 const child=spawnSync(process.execPath,[path.join(root,'bridge.js'),'--once'],{cwd:root,encoding:'utf8',timeout:10000});assert.equal(child.status,0,child.stderr+child.stdout);
 assert.ok(fs.readFileSync(cfg.inboxFile,'utf8').includes('New model'));assert.equal(fs.existsSync(path.join(root,'AGENT-RAN')),false);assert.equal(fs.existsSync(path.join(root,'transcripts.json')),false);assert.equal(fs.readFileSync(path.join(root,'config.json'),'utf8'),before);
});

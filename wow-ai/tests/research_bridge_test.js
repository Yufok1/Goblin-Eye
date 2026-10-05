'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const {spawnSync,execFileSync}=require('child_process');
test('bridge preserves a long answer and full tool result through a real subprocess and fake addon slots',()=>{
 fs.mkdirSync(path.join(__dirname,'tmp'),{recursive:true});
 const root=fs.mkdtempSync(path.join(__dirname,'tmp','research-'));
 const bridge=path.join(__dirname,'..','bridge');
 for(const name of ['bridge.js','models.js','protocol.js','agents.js','research.js','evidence.js','publisher.js','activity.js','instance-lock.js','kilo-policy.js','speech.js','speak.ps1','install-slots.js'])fs.copyFileSync(path.join(bridge,name),path.join(root,name));
 const cfg=JSON.parse(fs.readFileSync(path.join(bridge,'config.example.json'),'utf8'));
 cfg.addonDir=path.join(root,'addons');cfg.inboxFile=path.join(cfg.addonDir,'WoWAI','Inbox.lua');cfg.savedVariablesFile=path.join(root,'save.lua');cfg.defaultCwd=root;
 cfg.agent='codex';cfg.capture.enabled=false;cfg.slots=3;cfg.actMax=3;cfg.presenceMax=3;cfg.primerFile='';
 const fake=path.join(root,'fake-agent.js');cfg.agents={codex:{path:fake,permissionMode:'default'}};
 const answer='🌿 é 中文 Readable herb research.\n'.repeat(300)+'ANSWER COMPLETE END\nhttps://example.org/evidence';
 const result='Drop-source result.\n'.repeat(1000)+'RESULT COMPLETE END';
 const events=[{type:'thread.started',thread_id:'fake-session'},
  {type:'item.started',item:{type:'mcp_tool_call',id:'tool',server:'goblin_eye',tool:'get_item_market_context',arguments:{item_id:4306}}},
  {type:'item.completed',item:{type:'mcp_tool_call',id:'tool',server:'goblin_eye',tool:'get_item_market_context',status:'completed',result:{content:[{type:'text',text:result}]}}},
  {type:'item.completed',item:{type:'agent_message',id:'final',text:answer+'\n\nTL;DR:\nChecked the evidence.'}},{type:'turn.completed'}];
 fs.writeFileSync(fake,'process.stdin.resume(); process.stdin.on("end",()=>{ const bytes=Buffer.from('+JSON.stringify(events.map(e=>JSON.stringify(e)).join('\n')+'\n')+'); const split=bytes.indexOf(Buffer.from("🌿"))+2; process.stdout.write(bytes.subarray(0,split)); setTimeout(()=>process.stdout.write(bytes.subarray(split)),10); });');
 fs.mkdirSync(path.dirname(cfg.inboxFile),{recursive:true});fs.writeFileSync(path.join(path.dirname(cfg.inboxFile),'WoWAI.toc'),'## Interface: 16001\n');
 fs.writeFileSync(path.join(root,'config.json'),JSON.stringify(cfg));
 const hex=s=>Buffer.from(s).toString('hex');
 fs.writeFileSync(cfg.savedVariablesFile,`WoWAIDB = { ["outbox"] = { ["id"] = 1, ["chat"] = "c1", ["session"] = "game", ["text"] = "${hex('Check herbs')}", ["cwd"] = "${hex(root)}", ["agent"] = "codex" } }`);
 execFileSync(process.execPath,[path.join(root,'install-slots.js')],{cwd:root});
 const child=spawnSync(process.execPath,[path.join(root,'bridge.js'),'--once'],{cwd:root,encoding:'utf8',timeout:20000});
 assert.equal(child.status,0,child.stderr+'\n'+child.stdout);
 const transcripts=JSON.parse(fs.readFileSync(path.join(root,'transcripts.json'),'utf8'));
 const reply=transcripts.chats.c1.messages.at(-1);
 assert.equal(reply.text,answer+'\n\nTL;DR:\nChecked the evidence.');assert.equal(reply.research.total,1);
 const archive=JSON.parse(fs.readFileSync(reply.research.archive,'utf8'));
 assert.ok(archive.calls[0].result.includes('RESULT COMPLETE END'));
 assert.ok(reply.research.calls[0].result.includes('Showing 12000'));
 for(let i=1;i<=3;i++){
  const slot=fs.readFileSync(path.join(cfg.addonDir,'WoWAI_S00'+i,'Inbox.lua'),'utf8');
  assert.ok(slot.includes('ANSWER COMPLETE END'));assert.ok(slot.includes('get_item_market_context'));assert.ok(slot.includes('https://example.org/evidence'));
 }
});

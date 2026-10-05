'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path');
const {spawn,spawnSync,execFileSync}=require('child_process');
const P=require('../bridge/protocol');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(check,label){
 const deadline=Date.now()+12000;
 while(Date.now()<deadline){const value=check();if(value)return value;await pause(40);}
 throw new Error('Timed out: '+label);
}
function read(file,fallback){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{return fallback;}}
function fixture(t,parallel=1,delay=60000){
 const base=path.join(__dirname,'tmp');fs.mkdirSync(base,{recursive:true});
 const root=fs.mkdtempSync(path.join(base,'lifecycle-')),bridge=path.join(__dirname,'..','bridge');
 for(const name of fs.readdirSync(bridge))if(/\.(js|ps1)$/.test(name))fs.copyFileSync(path.join(bridge,name),path.join(root,name));
 const cfg=JSON.parse(fs.readFileSync(path.join(bridge,'config.example.json'),'utf8'));
 cfg.addonDir=path.join(root,'addons');cfg.inboxFile=path.join(cfg.addonDir,'WoWAI','Inbox.lua');cfg.savedVariablesFile=path.join(root,'save.lua');
 cfg.defaultCwd=root;cfg.agent='codex';cfg.capture.enabled=false;cfg.slots=3;cfg.actMax=3;cfg.presenceMax=3;cfg.primerFile='';cfg.pollMs=50;cfg.maxParallel=parallel;
 const fake=path.join(root,'fake-agent.js');cfg.agents={codex:{path:fake,permissionMode:'default'}};
 fs.writeFileSync(fake,`const fs=require('fs'),path=require('path'),{spawn}=require('child_process');
 process.stdin.resume();process.stdin.on('end',()=>{
 fs.appendFileSync(path.join(__dirname,'starts.txt'),'start\\n');
 fs.appendFileSync(path.join(__dirname,'pids.txt'),process.pid+'\\n');
 process.stdout.write(JSON.stringify({type:'thread.started',thread_id:'fake-session'})+'\\n');
 const sub=spawn(process.execPath,['-e',"setInterval(()=>require('fs').appendFileSync(process.argv[1],'tick'+String.fromCharCode(10)),100)",path.join(__dirname,'ticks.txt')],{windowsHide:true,stdio:'ignore'});
 fs.writeFileSync(path.join(__dirname,'descendant.txt'),String(sub.pid));
 setTimeout(()=>{sub.kill();process.stdout.write(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'DONE\\nTL;DR:\\nDone.'}})+'\\n'+JSON.stringify({type:'turn.completed'})+'\\n');},${delay});
 });`);
 fs.mkdirSync(path.dirname(cfg.inboxFile),{recursive:true});fs.writeFileSync(path.join(path.dirname(cfg.inboxFile),'WoWAI.toc'),'## Interface: 16001\n');
 fs.writeFileSync(path.join(root,'config.json'),JSON.stringify(cfg));fs.writeFileSync(cfg.savedVariablesFile,'WoWAIDB = {}');
 execFileSync(process.execPath,[path.join(root,'install-slots.js')],{cwd:root,windowsHide:true});
 const children=[];
 function kill(child){if(child.exitCode!==null||child.signalCode!==null)return;
  if(process.platform==='win32')spawnSync('taskkill',['/pid',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  else {
   try{process.kill(-child.pid,'SIGKILL');}catch{child.kill('SIGKILL');}
   // Agent runs have their own process groups. A simulated PC power cut stops
   // both the bridge and these explicitly recorded test-only groups.
   try{for(const id of fs.readFileSync(path.join(root,'pids.txt'),'utf8').trim().split('\n')){try{process.kill(-Number(id),'SIGKILL');}catch{}}}catch{}
  }
 }
 t.after(()=>{for(const child of children)kill(child);});
 const state=()=>read(path.join(root,'state.json'),{});
 const starts=()=>{try{return fs.readFileSync(path.join(root,'starts.txt'),'utf8').trim().split('\n').length;}catch{return 0;}};
 const inbox=()=>{try{return fs.readFileSync(cfg.inboxFile,'utf8');}catch{return '';}};
 const send=(id,chat,text='',cancel)=>{
  const hex=s=>Buffer.from(s).toString('hex');
  fs.writeFileSync(cfg.savedVariablesFile,`WoWAIDB = { ["outbox"] = { ["id"] = ${id}, ["session"] = "game", ["chat"] = "${chat}", ["text"] = "${hex(text)}", ["cwd"] = "${hex(root)}", ["agent"] = "codex"${cancel===undefined?'':`, ["cancel"] = ${cancel}`} } }`);
 };
 async function start(){
  const presence=state().presence;
  const child=spawn(process.execPath,[path.join(root,'bridge.js')],{cwd:root,windowsHide:true,detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});children.push(child);
  let errors='';child.stderr.on('data',d=>{errors+=d;});child.stdout.resume();
  await until(()=>state().presence!==undefined&&state().presence!==presence,'bridge startup '+errors);return child;
 }
 return {root,cfg,state,starts,inbox,send,start,kill};
}

test('normal startup refuses an old SavedVariables prompt but accepts a fresh user request',async t=>{
 const f=fixture(t);f.send(10,'c1','old instruction');await f.start();
 assert.equal(f.starts(),0);assert.ok(f.inbox().includes('status = "stopped"'));
 assert.ok(f.state().handled.game[10]);
 f.send(11,'c1','new instruction');await until(()=>f.starts()===1,'fresh prompt launches');
 f.send(12,'c1','',11);await until(()=>f.inbox().includes('Stopped by you'),'cancel cleanup');
});

test('a power-cut restart never reruns an accepted request or duplicates its transcript',async t=>{
 const f=fixture(t);const first=await f.start();f.send(1,'c1','interrupted');
 await until(()=>f.starts()===1&&Object.keys(f.state().pending||{}).length===1,'durable accepted request');
 f.kill(first);await until(()=>first.exitCode!==null||first.signalCode!==null,'bridge exited');
 await f.start();await pause(250);
 assert.equal(f.starts(),1);assert.deepEqual(f.state().pending,{});
 assert.ok(f.inbox().includes('status = "stopped"'));
 const messages=read(path.join(f.root,'transcripts.json'),{}).chats.c1.messages;
 assert.equal(messages.filter(m=>m.role==='user').length,1);
 assert.ok(messages.at(-1).text.includes('was not resumed'));
});

test('Stop kills the agent tree, suppresses stale replay, cancels queued work and permits a new turn',async t=>{
 const f=fixture(t);await f.start();f.send(1,'c1','running');
 await until(()=>f.starts()===1&&fs.existsSync(path.join(f.root,'ticks.txt')),'agent and descendant run');
 f.send(2,'c2','queued');await until(()=>Object.keys(f.state().pending||{}).length===2,'second chat queues');
 f.send(3,'c2','',2);await until(()=>f.inbox().includes('Stopped by you'),'queued cancellation');
 assert.equal(f.starts(),1,'queued request must never launch');
 f.send(4,'c1','',1);await until(()=>Object.keys(f.state().pending||{}).length===0,'running cancellation completes');
 const ticks=fs.readFileSync(path.join(f.root,'ticks.txt'),'utf8');await pause(350);
 assert.equal(fs.readFileSync(path.join(f.root,'ticks.txt'),'utf8'),ticks,'agent descendant must also stop');
 f.send(1,'c1','stale replay');await pause(250);assert.equal(f.starts(),1);
 f.send(5,'c1','new question');await until(()=>f.starts()===2,'new turn launches');
 f.send(6,'c1','',5);await until(()=>Object.keys(f.state().pending||{}).length===0,'new turn cancels');
 assert.equal(read(path.join(f.root,'transcripts.json'),{}).chats.c1.messages.filter(m=>m.role==='assistant').length,0,'cancelled agents cannot publish late answers');
});

test('cancellation transport and tombstones are scoped to the originating chat and session',()=>{
 assert.equal(P.parseFlags('cancel=8').cancel,8);
 assert.equal(P.parseFlags('cancel=-1').cancel,undefined);
 const parsed=P.parseOutbox('WoWAIDB = {["outbox"] = {["id"] = 9,["session"] = "game",["chat"] = "c1",["cancel"] = 8,["text"] = ""}}');
 assert.equal(parsed.cancel,8);
 const state={lastId:0,handled:{},cancelledThrough:{'game:c1':8}};
 assert.equal(P.alreadyHandled(state,{session:'game',chat:'c1',id:8}),true);
 assert.equal(P.alreadyHandled(state,{session:'game',chat:'c2',id:8}),false);
 assert.equal(P.alreadyHandled(state,{session:'other',chat:'c1',id:8}),false);
 assert.equal(P.alreadyHandled(state,{session:'game',chat:'c1',id:10}),false);
});

test('stopping one chat leaves a different running chat free to finish',async t=>{
 const f=fixture(t,2,4000);await f.start();f.send(1,'c1','first');await until(()=>f.starts()===1,'first chat launches');
 f.send(2,'c2','second');await until(()=>f.starts()===2,'second chat launches');
 f.send(3,'c1','',1);await until(()=>!f.state().pending['game:c1:1'],'first chat stops');
 await until(()=>read(path.join(f.root,'transcripts.json'),{}).chats?.c2?.messages.some(m=>m.role==='assistant'),'other chat finishes');
 const chats=read(path.join(f.root,'transcripts.json'),{}).chats;
 assert.equal(chats.c1.messages.filter(m=>m.role==='assistant').length,0);
 assert.equal(chats.c2.messages.filter(m=>m.role==='assistant').length,1);
});

test('a persisted Stop control gets a fresh acknowledgement after bridge restart',async t=>{
 const f=fixture(t);const child=await f.start();f.send(1,'c1','work');await until(()=>f.starts()===1,'agent launches');
 f.send(2,'c1','',1);await until(()=>Object.keys(f.state().pending||{}).length===0,'agent stops');
 f.kill(child);await until(()=>child.exitCode!==null||child.signalCode!==null,'bridge exits');
 const saved=f.state();saved.sessions['chat:c1']='newer-completed-session';fs.writeFileSync(path.join(f.root,'state.json'),JSON.stringify(saved));
 await f.start();
 assert.ok(f.inbox().includes('control_acks = { { session = "game", id = 2 } }'));
 assert.equal(f.starts(),1);assert.equal(f.state().cancelledThrough['game:c1'],1);
 assert.equal(f.state().sessions['chat:c1'],'newer-completed-session','an old repeated Stop must not reset a newer session');
});

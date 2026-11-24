'use strict';
// Run the real bridge turn functions in a VM. Every process, game transport,
// network, file write and provider is mocked: no bridge or CLI is launched.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {EventEmitter}=require('node:events');
const C=require('../bridge/continuity'),P=require('../bridge/protocol');
const A=require('../bridge/agents'),Models=require('../bridge/models');
const Research=require('../bridge/research');
const source=fs.readFileSync(path.join(__dirname,'../bridge/bridge.js'),'utf8');
const noteSource=source.slice(source.indexOf('function noteMessage('),source.indexOf('// First message from an addon session'));
const turnSource=source.slice(source.indexOf('function runJob(job)'),source.indexOf('// Input loops'));
const task={active_request:'Investigate the recipe learning plan',constraints:['Use saved evidence only'],
  completed:['Verified profession coverage'],next_step:'Check pattern acquisition sources',status:'active'};
function history(){
  const chat={id:'one',messages:[]};
  C.remember(chat,{role:'user',text:'Investigate the recipe learning plan. Use saved evidence only.',id:10,session:'before-reload',t:10});
  C.remember(chat,{role:'assistant',text:'Verified profession coverage. Next check pattern acquisition sources.',id:10,session:'before-reload',t:11},task);
  return {chats:{one:chat,two:{id:'two',messages:[{role:'user',text:'PRIVATE OTHER CHAT',id:1,t:1}]}},tokens:{}};
}
function fixture(t,{agent='codex',resumed=true,state,transcripts,model=''}={}){
  const identity=JSON.stringify([agent,model,'','','default',false]);
  const savedState=state||{sessions:resumed?{'chat:one':'old-provider-session'}:{},
    sessionCwd:{'chat:one':'D:\\fixture'},sessionAgent:{'chat:one':agent},
    sessionSettings:{'chat:one':identity},handled:{},pending:{},lastId:0};
  const children=[],files=new Map(),published=[],logs=[],persisted={};
  const gameMethods={calls:0};
  const noop=()=>{};
  const fakeFs={existsSync:()=>true,mkdirSync:noop,rmSync:noop,
    writeFileSync:(file,text)=>files.set(file,String(text)),unlinkSync:file=>files.delete(file),
    openSync:()=>{throw Error('No diagnostics fixture');},closeSync:noop};
  const cfg={gameContext:true,agents:{[agent]:{permissionMode:'default',model}}};
  const makeChild=(file,args,options)=>{
    const child=new EventEmitter();child.file=file;child.args=args;child.options=options;
    child.stdin=new EventEmitter();child.stdin.end=text=>{child.input=String(text);};
    child.stdout=new EventEmitter();child.stderr=new EventEmitter();
    child.stdout.setEncoding=noop;child.stderr.setEncoding=noop;
    child.kill=()=>{child.killed=true;};
    child.close=code=>{if(!child.closed){child.closed=true;child.emit('close',code);}};
    children.push(child);return child;
  };
  const context={fs:fakeFs,path,P,Models,Research,Continuity:C,
    A:{...A,validateProject:cwd=>require('../bridge/runtime-storage').validateRoot(cwd),resolveCommand:()=>({file:'fixture-cli',args:[],found:true})},
    cfg,DEFAULT_AGENT:agent,TMP_DIR:'D:\\fixture\\tmp',HERE:'D:\\fixture',MAP_DIR:'D:\\fixture\\maps',
    state:JSON.parse(JSON.stringify(savedState)),transcripts:JSON.parse(JSON.stringify(transcripts||history())),
    forgotten:new Set(),running:new Map(),catalog:{cache:new Map()},exitWhenIdle:false,
    process:{platform:process.platform,env:{},exit:()=>assert.fail('No process exit permitted')},
    require:name=>{assert.equal(name,'./background-process');return {spawnBackground:makeChild};},
    log:(...text)=>logs.push(text.join(' ')),signal:noop,resetBeats:noop,beat:noop,
    ...require('../bridge/activity'),
    killTree:child=>{child.killed=true;child.killCalls=(child.killCalls||0)+1;},
    resolveCwd:cwd=>cwd||'D:\\fixture',sameFolder:P.sameFolder,chatKey:P.chatKey,sessKey:P.sessKey,
    primer:()=>'',maybeOfferRestore:noop,allowRules:()=>[],mapFileFor:()=> 'fixture-map',
    publish:async(key,value)=>{published.push({key,...value});return {written:1,failures:[],elapsedMs:0};},
    takeMapCommands:(job,text)=>({text,note:''}),speech:{completed:async()=>{}},drainQueue:noop,
    markHandled:job=>P.markHandled(context.state,job),
    saveState:()=>{persisted.state=JSON.parse(JSON.stringify(context.state));},
    saveTranscripts:()=>{persisted.transcripts=JSON.parse(JSON.stringify(context.transcripts));},
    randomUUID:()=> 'fixture-speech-key',setTimeout,clearTimeout,setInterval,clearInterval,
  };
  vm.createContext(context);vm.runInContext(noteSource+'\n'+turnSource,context);
  function run(overrides={}){
    const job={id:414,chat:'one',session:'after-reload',text:'Reloaded; resume the task.',cwd:'D:\\fixture',via:'fixture',...overrides};
    context.runJob(job);return job;
  }
  t.after(()=>{
    for(const {job} of context.running.values())job.cancelled=true;
    for(const child of children)child.close(1);
  });
  return {context,children,files,published,logs,persisted,run,gameMethods};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('system-drive chat folders are rejected before any agent is started', {skip:process.platform!=='win32'}, t=>{
  const f=fixture(t);f.run({cwd:'C:\\workspace'});
  assert.equal(f.children.length,0);
  assert.equal(f.published.at(-1).status,'error');
  assert.match(f.published.at(-1).text,/system drive|C:/);
});
function reply(child,text='Evidence checked.',session='new-provider-session'){
  child.stdout.emit('data',[
    {type:'thread.started',thread_id:session},
    {type:'item.completed',item:{type:'agent_message',text}},
    {type:'turn.completed'},
  ].map(v=>JSON.stringify(v)).join('\n')+'\n');
  child.close(0);
}

test('real bridge turn supplies saved context to every adapter on an already resumed session',async t=>{
  for(const agent of A.agentIds()){
    const f=fixture(t,{agent});f.run();
    assert.equal(f.children.length,1);
    const child=f.children[0];
    const delivered=agent==='agy'?child.args.find(s=>s.startsWith('-p=')):
      agent==='grok'?[...f.files.values()].find(s=>s.includes('[Current user message]')):child.input;
    assert.match(delivered,/Investigate the recipe learning plan/,agent);
    assert.match(delivered,/Check pattern acquisition sources/,agent);
    assert.match(delivered,/Reloaded; resume the task/,agent);
    assert.ok(!delivered.includes('PRIVATE OTHER CHAT'),agent);
    assert.ok(child.args.includes('old-provider-session'),agent);
    child.close(1);await flush();
  }
});

test('model, folder, agent and explicit session changes retain chat context on a fresh client session',async t=>{
  for(const change of ['model','folder','agent','newSession']){
    const f=fixture(t);
    if(change==='model')f.context.cfg.agents.codex.model='new-model';
    if(change==='folder')f.context.state.sessionCwd['chat:one']='D:\\old-folder';
    if(change==='agent')f.context.state.sessionAgent['chat:one']='kilo';
    f.run(change==='newSession'?{newSession:true}:{});
    assert.ok(!f.children[0].args.includes('old-provider-session'),change);
    assert.match(f.children[0].input,/Investigate the recipe learning plan/,change);
    f.children[0].close(1);await flush();
  }
});

test('reply checkpoint is hidden, persisted and supplied after a full bridge restart or Stop',async t=>{
  const f=fixture(t);f.run();
  reply(f.children[0],'Evidence checked.\n```goblin-continuity\n'+JSON.stringify(task)+'\n```\nTL;DR:\nReady for the next step.');
  await flush();
  const chat=f.persisted.transcripts.chats.one;
  assert.equal(chat.checkpoint.task.next_step,task.next_step);
  assert.ok(!chat.messages.at(-1).text.includes('goblin-continuity'));
  assert.ok(!f.published.at(-1).text.includes('goblin-continuity'));
  const resumed=fixture(t,{state:f.persisted.state,transcripts:f.persisted.transcripts});
  resumed.run({id:1,session:'next-game-reload',text:'Continue after the restart.'});
  assert.ok(resumed.children[0].args.includes('new-provider-session'));
  assert.match(resumed.children[0].input,/Check pattern acquisition sources/);
  resumed.children[0].close(1);await flush();
  const afterStop=JSON.parse(JSON.stringify(f.persisted));
  delete afterStop.state.sessions['chat:one'];
  C.remember(afterStop.transcripts.chats.one,{role:'system',status:'stopped',text:'Stopped by you.',id:415,session:'after-reload',t:20});
  const stopped=fixture(t,{state:afterStop.state,transcripts:afterStop.transcripts});
  assert.equal(stopped.children.length,0,'loading state never executes a pending task');
  stopped.run({id:416,text:'Resume now.'});
  assert.match(stopped.children[0].input,/Stopped by you/);
  assert.match(stopped.children[0].input,/Check pattern acquisition sources/);
  assert.ok(!stopped.children[0].args.includes('new-provider-session'));
});

test('unavailable session automatically retries once with context and one stored user message',async t=>{
  const f=fixture(t),job=f.run();
  f.children[0].stderr.emit('data','Session old-provider-session not found');
  f.children[0].close(1);
  assert.equal(f.children.length,2);
  assert.ok(!f.children[1].args.includes('old-provider-session'));
  assert.match(f.children[1].input,/Investigate the recipe learning plan/);
  assert.match(f.children[1].input,/Reloaded; resume the task/);
  assert.equal(f.children[1].input.split('Reloaded; resume the task.').length-1,1,'recovery must not duplicate the current request in its handoff');
  assert.equal(f.context.transcripts.chats.one.messages.filter(m=>m.role==='user'&&m.id===job.id).length,1);
  reply(f.children[1]);await flush();
  assert.equal(f.context.state.sessions['chat:one'],'new-provider-session');
  assert.match(f.logs.join('\n'),/restoring this chat's context/);
});

test('missing-session recovery never loops or replays a turn that produced activity',async t=>{
  const loop=fixture(t);loop.run();
  for(let i=0;i<2;i++){
    loop.children[i].stderr.emit('data','Session old-provider-session not found');
    loop.children[i].close(1);
  }
  await flush();assert.equal(loop.children.length,2);
  const active=fixture(t);active.run();
  active.children[0].stdout.emit('data',JSON.stringify({type:'item.started',item:{type:'mcp_tool_call',id:'t',server:'goblin_eye',tool:'get_source_health',arguments:{}}})+'\n');
  active.children[0].stderr.emit('data','Session old-provider-session not found');
  active.children[0].close(1);await flush();
  assert.equal(active.children.length,1,'a tool-started turn must never be retried automatically');
  const plain=fixture(t,{agent:'hermes'});plain.run();
  plain.children[0].stdout.emit('data','Started checking the requested sources.');
  plain.children[0].stderr.emit('data','Session old-provider-session not found');
  plain.children[0].close(1);await flush();
  assert.equal(plain.children.length,1,'plain-text work must not be replayed');
});
test('a completed turn is delivered without waiting for inherited stdout to close',async t=>{
  const f=fixture(t);const job=f.run();const child=f.children[0];
  const report='First paragraph.\n\n1. First step.\n2. Second step.\n\n```goblin-continuity '+JSON.stringify(task)+' ```\nTL;DR:\nStart with the first step.';
  child.stdout.emit('data',[
    {type:'thread.started',thread_id:'fresh-session'},
    {type:'item.completed',item:{type:'agent_message',text:report}},
    {type:'turn.completed'},
  ].map(JSON.stringify).join('\n')+'\n');
  await flush();
  assert.equal(child.closed,undefined,'inherited pipes remain open in this regression case');
  assert.equal(job.finished,true);assert.equal(child.killCalls,1);
  assert.equal(f.published.at(-1).status,'done');
  assert.match(f.published.at(-1).text,/First paragraph\.\n\n1\. First step\.\n2\. Second step\./);
  assert.equal(f.published.at(-1).summary,'Start with the first step.');
  for(const record of f.published)assert.doesNotMatch(record.text,/goblin-continuity|active_request|next_step/);
  assert.equal(f.persisted.transcripts.chats.one.checkpoint.task.next_step,task.next_step);
  const count=f.published.length;
  child.stdout.emit('data',JSON.stringify({type:'turn.failed',error:{message:'late failure'}})+'\n');
  child.emit('error',Error('late pipe error'));child.close(1);await flush();
  assert.equal(f.published.length,count,'late process events cannot replace the delivered result');
  assert.equal(f.context.transcripts.chats.one.messages.filter(m=>m.role==='assistant').length,2,'the prior answer and exactly one new answer');
});
test('working records report real parsed activity independently of sound heartbeats',async t=>{
  const f=fixture(t);f.run();const child=f.children[0];
  child.stdout.emit('data',JSON.stringify({type:'item.started',item:{id:'tool',type:'mcp_tool_call',server:'goblin_eye',tool:'list_characters',arguments:{}}})+'\n');
  const record=f.published.at(-1);
  assert.ok(record.activity.events>0);
  assert.equal(record.activity.beats,0,'mocked/unsupported sound probes do not invent beats');
  assert.ok(record.activity.last_event_ago_ms>=0);
  child.close(1);await flush();
});

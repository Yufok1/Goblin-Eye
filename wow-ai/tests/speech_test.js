'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {EventEmitter}=require('events');
const {spawnSync,execFileSync}=require('child_process');
const {SpeechManager,spokenText,findReply}=require('../bridge/speech');
const P=require('../bridge/protocol');
function fixture() {
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'goblin-voice-')), calls=[];
 const spawnProcess=(file,args,opts)=>{const child=new EventEmitter();child.stderr=new EventEmitter();child.stderr.setEncoding=()=>{};child.stdout=new EventEmitter();child.stdout.setEncoding=()=>{};child.stdin=new EventEmitter();child.stdin.end=(data,encoding)=>{child.data=JSON.parse(data);child.encoding=encoding;};child.stdin.write=(data,encoding)=>{child.data=JSON.parse(data);child.encoding=encoding;};child.kill=()=>{child.killed=true;};calls.push({file,args,opts,child});return child;};
 return {directory,calls,speech:new SpeechManager({directory,spawnProcess,platform:'win32'})};
}
test('in-game Stop cancels Desktop playback and the next Play starts a new helper',()=>{
 const {speech,calls}=fixture();speech.say('First reply');const first=calls[0].child;
 speech.control('stop');assert.ok(first.killed);assert.equal(speech.info().busy,false);
 speech.say('Second reply');assert.equal(calls.length,2);assert.equal(calls[1].child.data.text,'Second reply');
 first.emit('close',0);assert.equal(speech.info().busy,true);speech.stop();assert.ok(calls[1].child.killed);
});
test('older replies resolve by unique saved ID while duplicate IDs never select a different reply',()=>{
 const first={role:'assistant',id:7,text:'Old reply'},second={role:'assistant',id:8,text:'New reply',speech_key:'unique'};
 const messages=[{role:'user',id:7,text:'Question'},first,second];
 assert.equal(findReply(messages,'id:7'),first);assert.equal(findReply(messages,'unique'),second);assert.equal(findReply(messages,''),second);
 assert.equal(findReply([...messages,{role:'assistant',id:7,text:'ID repeated after reset'}],'id:7'),undefined);assert.equal(findReply(messages,'missing'),undefined);
});
test('speech is opt-in, summary by default, and settings survive restart',()=>{
 const {speech,calls,directory}=fixture();speech.completed('Private reply');assert.equal(calls.length,0);
 assert.equal(speech.info().mode,'summary');speech.configure('on');speech.configure('volume','50');speech.configure('rate','-2');
 const reload=new SpeechManager({directory,platform:'win32'});assert.equal(reload.info().enabled,true);assert.equal(reload.info().volume,50);assert.equal(reload.info().rate,-2);assert.equal(calls.length,0,'restoring settings does not read historical replies');
 assert.throws(()=>speech.configure('volume','101'));assert.equal(speech.info().volume,50);
});
test('summary chooses TL;DR while manual full preserves the complete prose',()=>{
 const {speech,calls}=fixture();const reply='Detailed answer with herbs.\n\nTL;DR:\nFarm Bruiseweed.';
 speech.configure('on');speech.completed(reply);assert.equal(calls[0].child.data.text,'Farm Bruiseweed.');
 speech.say(reply,'full');assert.ok(calls[0].child.killed);assert.ok(calls[1].child.data.text.includes('Detailed answer'));
 speech.stop();assert.ok(calls[1].child.killed);assert.equal(speech.info().busy,false);
});
test('reply and voice name are literal stdin data, never shell arguments or SSML',()=>{
 const {speech,calls}=fixture();speech.configure('name','Voice $(bad);');speech.say('<speak>🌿 é 中文 $(bad);</speak>','full');
 const call=calls[0];assert.equal(call.file,'powershell.exe');assert.equal(call.opts.shell,undefined);assert.equal(call.opts.windowsHide,true);
 assert.ok(!call.args.join(' ').includes('bad'));assert.equal(call.child.encoding,'utf8');assert.equal(call.child.data.voice,'Voice $(bad);');assert.ok(call.child.data.text.includes('é 中文'));assert.ok(!call.child.data.text.includes('🌿'));
 const ps=fs.readFileSync(path.join(__dirname,'../bridge/speak.ps1'),'utf8');assert.ok(ps.includes('SpeakAsync([string]$speechRequest.text)'));assert.ok(!ps.includes('SpeakSsml('));
});
test('speech cleans formatting, skips code and URLs, and uses a bounded opening fallback',()=>{
 assert.equal(spokenText('**Herbs** [source](https://example.org/a)\n```lua\n/run unsafe\n```','full'),'Herbs source\n Code block omitted.');
 assert.ok(spokenText('x'.repeat(2000)).length<900);assert.ok(spokenText('x'.repeat(2000)).includes('Short preview'));
});

test('report speech removes texture codes and table separators but retains item names and quotes',()=>{
 const text=spokenText('🌿 Herbs\n| Item | Price |\n| --- | ---: |\n| Bruiseweed | 12 silver |\n|TInterface/icon:16|t','full');
 assert.ok(text.includes('Bruiseweed, 12 silver'));assert.ok(!text.includes('---'));assert.ok(!text.includes('Interface/icon'));assert.ok(!text.includes('🌿'));
});

test('controls look up a transcript reply; missing replies and helper failures remain audio errors',()=>{
 const {speech,calls}=fixture();let lookupKey='';speech.control('listen','key',key=>{lookupKey=key;return {text:'Detail\nTL;DR: Listen summary'};});assert.equal(lookupKey,'key');assert.equal(calls[0].child.data.text,'Listen summary');
 calls[0].child.stderr.emit('data','No sound device');calls[0].child.emit('close',1);assert.ok(speech.info().error.includes('No sound device'));assert.equal(speech.info().busy,false);
 speech.control('listenfull','missing',()=>null);assert.ok(speech.info().error.includes('no longer exists'));assert.equal(calls.length,1);
 speech.control('unknown','',()=>{throw Error('must not look up');});assert.ok(speech.info().error.includes('Unsupported'));
});
test('off stops current speech and ignored completion callbacks cannot stop a newer reply',()=>{
 const {speech,calls}=fixture();speech.say('First');speech.say('Second');calls[0].child.emit('close',0);assert.equal(speech.info().busy,true);speech.configure('off');assert.equal(speech.info().busy,false);assert.ok(calls[1].child.killed);
});
test('voice control flag is recognized in pixel and reload transports and reply keys survive serialization',()=>{
 const jobs=P.jobsFromStrip(7,['session','chat','7','','voice=stop','Name',''].join('\x1f'));assert.equal(jobs[0].voice,'stop');
 const job=P.parseOutbox('WoWAIDB={ ["outbox"]={ ["id"]=7, ["voice"]="volume", ["text"]="3730", ["chat"]="chat" } }');assert.equal(job.voice,'volume');assert.equal(job.text,'70');
 const lua=P.luaTable('Data',[{speech_key:'unique',status:'done',text:'Reply'}],{speech:{enabled:false,mode:'summary'},restore:{chats:[{messages:[{speech_key:'restored',role:'assistant'}]}]}});assert.ok(lua.includes('speech_key = "unique"'));assert.ok(lua.includes('speech_key = "restored"'));assert.ok(lua.includes('enabled = false'));
});
test('real bridge voice controls persist preferences and never invoke the agent',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'goblin-voice-bridge-'));const bridge=path.join(__dirname,'../bridge');
 for(const f of ['bridge.js','models.js','protocol.js','agents.js','research.js','evidence.js','publisher.js','activity.js','instance-lock.js','kilo-policy.js','speech.js','speak.ps1','install-slots.js'])fs.copyFileSync(path.join(bridge,f),path.join(root,f));
 const cfg=JSON.parse(fs.readFileSync(path.join(bridge,'config.example.json'),'utf8'));cfg.addonDir=path.join(root,'addons');cfg.inboxFile=path.join(cfg.addonDir,'WoWAI','Inbox.lua');cfg.savedVariablesFile=path.join(root,'save.lua');cfg.defaultCwd=root;cfg.agent='codex';cfg.capture.enabled=false;cfg.slots=2;cfg.primerFile='';cfg.agents={codex:{path:'must-not-be-launched.exe',permissionMode:'default'}};
 fs.mkdirSync(path.dirname(cfg.inboxFile),{recursive:true});fs.writeFileSync(path.join(path.dirname(cfg.inboxFile),'WoWAI.toc'),'## Interface: 16001');fs.writeFileSync(path.join(root,'config.json'),JSON.stringify(cfg));
 execFileSync(process.execPath,[path.join(root,'install-slots.js')],{cwd:root});
 for(const [id,voice] of [[1,'on'],[2,'off'],[3,'bogus']]) {
  fs.writeFileSync(cfg.savedVariablesFile,`WoWAIDB={ ["outbox"]={ ["id"]=${id}, ["session"]="s", ["chat"]="c", ["voice"]="${voice}" } }`);
  const child=spawnSync(process.execPath,[path.join(root,'bridge.js'),'--once'],{cwd:root,encoding:'utf8',timeout:10000});assert.equal(child.status,0,child.stderr);assert.ok(!child.stdout.includes('spawn failed'));
  const inbox=fs.readFileSync(cfg.inboxFile,'utf8');assert.ok(inbox.includes('speech = {'));assert.ok(inbox.includes(voice==='on'?'enabled = true':'enabled = false'));
 }
 assert.equal(fs.existsSync(path.join(root,'transcripts.json')),false,'audio controls do not create chat history');
});

test('removed character preferences migrate to Desktop and cannot load private assets',()=>{
 const {directory,calls}=fixture();
 fs.writeFileSync(path.join(directory,'speech-settings.json'),JSON.stringify({enabled:true,profile:'goblin',volume:55,rate:1}));
 fs.writeFileSync(path.join(directory,'neural-voice.json'),JSON.stringify({python:'must-not-launch.exe',assets:'private'}));
 const reload=new SpeechManager({directory,platform:'win32'});
 assert.equal(reload.info().profile,'desktop');assert.equal(reload.info().enabled,true);assert.equal(reload.info().volume,55);
 for(const name of ['orc','goblin','lich'])assert.throws(()=>reload.configure('character',name),/Unsupported/);
 assert.equal(reload.neural,undefined);assert.equal(calls.length,0);
});

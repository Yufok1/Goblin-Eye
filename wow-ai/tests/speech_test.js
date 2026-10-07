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
test('repeated neural Play for the same text does not restart slow generation',()=>{
 const {speech,calls}=fixture();speech.neural={python:'python.exe',assets:'private-assets'};speech.settings.profile='goblin';speech.say('Same reply');const child=calls[0].child;speech.say('Same reply');assert.equal(calls.length,1);assert.equal(child.killed,undefined);assert.equal(speech.info().profile,'goblin');assert.equal(speech.info().phase,'Generating voice');speech.stop();
});

test('in-game Stop cancels the reply and keeps the loaded model for the next Play',()=>{
 const {speech,calls}=fixture();speech.neural={python:'python.exe',assets:'assets'};speech.settings.profile='goblin';speech.say('First reply');const worker=calls[0].child,id=worker.data.id;
 worker.stdout.emit('data','@voice {"loaded":true}\n');speech.control('stop');assert.equal(worker.killed,undefined);assert.deepEqual(worker.data,{cancel:id});assert.equal(speech.worker,worker);assert.equal(speech.info().busy,false);
 speech.say('Second reply');assert.equal(calls.length,1);assert.equal(worker.data.text,'Second reply');worker.stdout.emit('data','@voice '+JSON.stringify({id,cancelled:true})+'\n');assert.equal(speech.info().busy,true);speech.stop();assert.ok(worker.killed);
});
test('character preview uses the Desktop audio helper without loading a neural worker',()=>{
 const {speech,calls,directory}=fixture();speech.neural={assets:directory};fs.mkdirSync(path.join(directory,'auditions'));fs.writeFileSync(path.join(directory,'auditions/orc.wav'),'fixture');speech.settings.profile='orc';
 speech.control('preview','',()=>{throw Error('Preview does not read transcripts');});assert.equal(calls.length,1);assert.equal(calls[0].file,'powershell.exe');assert.equal(calls[0].child.data.audioFile,path.join(directory,'auditions/orc.wav'));assert.equal(speech.worker,null);assert.equal(speech.info().phase,'Playing test clip');calls[0].child.emit('close',0);assert.equal(speech.info().busy,false);
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
test('neural profiles require installed assets and remain opt-in; Desktop stays available',()=>{
 const {speech,calls}=fixture();assert.throws(()=>speech.configure('character','orc'),/not installed/);speech.neural={python:'private-python',assets:'private-assets'};
 for(const theme of ['orc','goblin']){speech.configure('character',theme);assert.equal(speech.info().profile,theme);assert.equal(speech.info().enabled,false);}
 assert.equal(speech.info().rate,0);speech.configure('character','desktop');assert.equal(speech.info().profile,'desktop');assert.throws(()=>speech.configure('character','thrall-clone'));assert.equal(calls.length,0);
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

test('Nano prewarms one worker and generation progress cannot hide concurrent report playback',()=>{
 const {speech,calls}=fixture();speech.neural={python:'private-python',assets:'assets',engine:'nano',device:'hybrid',threads:2};speech.settings.profile='goblin';speech.warm();
 assert.equal(calls.length,1);assert.equal(calls[0].child.data.warm,true);assert.ok(calls[0].args.includes('nano'));assert.ok(calls[0].args.includes('hybrid'));assert.equal(speech.info().busy,false);assert.equal(speech.info().warming,true);
 const child=calls[0].child;child.stdout.emit('data','@voice {"warmed":true,"phase":"Voice ready"}\n');assert.equal(speech.info().ready,true);assert.equal(speech.info().warming,false);
 speech.say('A real report');assert.equal(calls.length,1);const id=child.data.id;
 child.stdout.emit('data','@voice '+JSON.stringify({id,playing:1,total:2,phase:'Playing 1/2'})+'\n');
 child.stdout.emit('data','@voice '+JSON.stringify({id,generating:2,total:2,phase:'Generating 2/2'})+'\n');assert.equal(speech.info().phase,'Playing 1/2');
 child.stdout.emit('data','@voice '+JSON.stringify({id,done:true,phase:'Idle'})+'\n');assert.equal(speech.info().busy,false);assert.equal(speech.worker,child);speech.stop();
});

test('idle character changes preserve the warm GPU worker and pass private runtime paths literally',()=>{
 const {speech,calls}=fixture();speech.neural={python:'private-python',assets:'assets',engine:'nano',device:'cuda-fp16',packages:'C:/private deps',torchPackage:'D:/private torch',prewarm:true};speech.settings.profile='goblin';speech.warm();
 const child=calls[0].child;child.stdout.emit('data','@voice {"warmed":true,"phase":"Voice ready"}\n');
 speech.configure('character','orc');assert.equal(calls.length,1);assert.equal(child.killed,undefined);assert.equal(child.data.profile,'orc');assert.ok(calls[0].args.includes('cuda-fp16'));assert.ok(calls[0].args.includes('C:/private deps'));assert.ok(calls[0].args.includes('D:/private torch'));assert.equal(calls[0].opts.shell,undefined);speech.stop();
});
test('neural speech uses one cached worker, literal stdin, correct reply IDs, phase updates and cancellation',()=>{
 const {speech,calls}=fixture();speech.neural={python:'private-python.exe',assets:'private-assets'};speech.configure('character','orc');speech.say('First reply');
 const child=calls[0].child,id=child.data.id;assert.equal(calls[0].file,'private-python.exe');assert.ok(calls[0].args.includes('-I'));assert.ok(!calls[0].args.join(' ').includes('First reply'));assert.equal(child.data.profile,'orc');
 child.stdout.emit('data','Library noise\n@voice {"id":"'+id+'","phase":"Playing"}\n');assert.equal(speech.info().phase,'Playing');
 child.stdout.emit('data','@voice '+JSON.stringify({id,done:true,phase:'Idle'})+'\n');assert.equal(speech.info().busy,false);
 speech.say('Second reply');assert.equal(calls.length,1,'model stays loaded between replies');assert.equal(child.data.text,'Second reply');assert.equal(speech.info().busy,true);
 child.stdout.emit('data','@voice '+JSON.stringify({id,done:true,phase:'Idle'})+'\n');assert.equal(speech.info().busy,true,'stale completion cannot stop a newer request');
 speech.stop();assert.equal(speech.info().busy,false);assert.ok(child.killed);assert.equal(speech.worker,null);
 speech.say('Restart');assert.equal(calls.length,2);calls[1].child.stdout.emit('data','@voice {"error":"Model error"}\n');assert.equal(speech.info().error,'Model error');assert.ok(calls[1].child.killed);
 assert.throws(()=>speech.say('x'.repeat(16001),'full'),/16,000/);
});
test('controls look up a transcript reply; missing replies and helper failures remain audio errors',()=>{
 const {speech,calls}=fixture();let lookupKey='';speech.control('listen','key',key=>{lookupKey=key;return {text:'Detail\nTL;DR: Listen summary'};});assert.equal(lookupKey,'key');assert.equal(calls[0].child.data.text,'Listen summary');
 calls[0].child.stderr.emit('data','No sound device');calls[0].child.emit('close',1);assert.ok(speech.info().error.includes('No sound device'));assert.equal(speech.info().busy,false);
 speech.control('listenfull','missing',()=>null);assert.ok(speech.info().error.includes('no longer exists'));assert.equal(calls.length,1);
 speech.control('unknown','',()=>{throw Error('must not look up');});assert.ok(speech.info().error.includes('Unknown'));
});
test('off stops current speech and ignored completion callbacks cannot stop a newer reply',()=>{
 const {speech,calls}=fixture();speech.say('First');speech.say('Second');calls[0].child.emit('close',0);assert.equal(speech.info().busy,true);speech.configure('off');assert.equal(speech.info().busy,false);assert.ok(calls[1].child.killed);
});
test('voice control flag is recognized in pixel and reload transports and reply keys survive serialization',()=>{
 const jobs=P.jobsFromStrip(7,['session','chat','7','','voice=stop','Name',''].join('\x1f'));assert.equal(jobs[0].voice,'stop');
 const job=P.parseOutbox('WoWAIDB={ ["outbox"]={ ["id"]=7, ["voice"]="volume", ["text"]="3730", ["chat"]="chat" } }');assert.equal(job.voice,'volume');assert.equal(job.text,'70');
 const lua=P.luaTable('Data',[{speech_key:'unique',status:'done',text:'Reply'}],{speech:{enabled:false,mode:'summary'},restore:{chats:[{messages:[{speech_key:'restored',role:'assistant'}]}]}});assert.ok(lua.includes('speech_key = "unique"'));assert.ok(lua.includes('speech_key = "restored"'));assert.ok(lua.includes('enabled = false'));
});

test('full and summary neural replies use adaptive buffering',()=>{const {speech,calls}=fixture();speech.neural={python:'python.exe',assets:'assets'};speech.settings.profile='goblin';speech.say('A full report','full');assert.equal(calls[0].child.data.playback,'adaptive');speech.say('TL;DR: short','summary');assert.equal(calls[0].child.data.playback,'adaptive');speech.stop();});

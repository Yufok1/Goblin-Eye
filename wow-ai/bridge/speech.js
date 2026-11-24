'use strict';
// Optional desktop audio only. Reply text travels on stdin, never a shell command.
const fs = require('fs'), path = require('path');
const {spawn} = require('child_process');
const {randomUUID}=require('crypto');
const {splitSummary} = require('./protocol');
const Storage = require('./runtime-storage');
const DEFAULTS = {enabled:false, mode:'summary', volume:70, rate:0, voice:'',profile:'desktop'};
// Neural character profiles use local references; Desktop uses Windows speech.
const PRESETS = {orc:{profile:'orc',rate:0},goblin:{profile:'goblin',rate:0},desktop:{profile:'desktop',rate:0}};
function settings(value={}) {
 return {enabled:value.enabled === true, mode:value.mode === 'full' ? 'full' : 'summary',
  volume:Number.isInteger(value.volume) && value.volume >= 0 && value.volume <= 100 ? value.volume : 70,
  rate:Number.isInteger(value.rate) && value.rate >= -10 && value.rate <= 10 ? value.rate : 0,
  voice:typeof value.voice === 'string' && value.voice.length <= 120 ? value.voice : '',
  profile:['orc','goblin'].includes(value.profile)?value.profile:'desktop'};
}
function spokenText(text, mode='summary') {
 text=String(text||'');
 if(mode !== 'full') {
  const summary=splitSummary(text).summary;
  const first=text.trim().split(/\n\s*\n/)[0] || '';
  text=summary || first.slice(0,800)+(first.length>800 ? ' … Short preview. Use Listen full for the rest.' : '');
 }
 return text.replace(/```[\s\S]*?```/g,' Code block omitted. ')
  .replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g,'$1')
  .replace(/https?:\/\/\S+/g,' link in chat ')
  .replace(/\|c[0-9a-fA-F]{8}|\|r/g,'').replace(/\|H[^|]*\|h([^|]*)\|h/g,'$1')
  .replace(/\|T[^|]*\|t/g,'').replace(/\p{Extended_Pictographic}/gu,'')
  .replace(/^\s*\|?[\s:|-]*-{3,}[\s:|-]*\|?\s*$/gm,'')
  .replace(/^\s*\|(.+)\|\s*$/gm,(_,row)=>row.split('|').map(s=>s.trim()).filter(Boolean).join(', '))
  .replace(/(?:^|\n)\s*(?:#+|[-*])\s+/g,'\n').replace(/[*_`]/g,'').trim();
}
function findReply(messages, key) {
 const replies=(messages || []).filter(m=>m.role==='assistant');
 if(!key)return replies.at(-1);
 const legacy=String(key).match(/^id:(\d+)$/);
 const matches=replies.filter(m=>legacy ? Number(m.id)===Number(legacy[1]) : m.speech_key===key);
 // Old IDs may repeat after a client data reset. Never speak a different reply.
 return matches.length===1 ? matches[0] : undefined;
}
class SpeechManager {
 constructor({directory, spawnProcess=spawn, platform=process.platform, log=()=>{}, onChange=()=>{}}) {
  this.directory=directory; this.file=path.join(directory,'speech-settings.json');
  this.spawn=spawnProcess; this.platform=platform; this.log=log; this.onChange=onChange;
  try {this.settings=settings(JSON.parse(fs.readFileSync(this.file,'utf8')));} catch {this.settings={...DEFAULTS};}
  this.active=null; this.error='';
  this.worker=null;this.phase='Idle';this.requestId='';this.idleTimer=null;this.startedAt=0;this.spokenKey='';
  try {this.neural=JSON.parse(fs.readFileSync(path.join(directory,'neural-voice.json'),'utf8'));} catch {this.neural=null;}
 }
 info() {return {...this.settings, available:this.platform==='win32', neuralAvailable:!!this.neural, busy:!!this.active, warming:!!this.warming, ready:!!this.ready, engine:this.neural?.engine||'chatterbox',phase:this.phase,elapsed:this.active&&this.startedAt?Math.floor((Date.now()-this.startedAt)/1000):0,error:this.error};}
 changed() {this.onChange(this.info());}
 configure(op,value) {
  const next={...this.settings};
  if(op==='on'||op==='off')next.enabled=op==='on';
  else if(op==='summary'||op==='full')next.mode=op;
  else if(op==='volume'||op==='rate') {
   if(!/^-?\d+$/.test(String(value)))throw Error('Use a whole number.');
   const n=Number(value), min=op==='rate'?-10:0,max=op==='rate'?10:100;
   if(n<min||n>max)throw Error(`${op} must be ${min} to ${max}.`);
   next[op]=n;
  } else if(op==='character') {
   const preset=PRESETS[String(value).toLowerCase()];if(!preset)throw Error('Choose orc, goblin, or desktop.');
   if(preset.profile!=='desktop'&&!this.neural)throw Error('Neural character voices are not installed.');
   Object.assign(next,preset);
  } else if(op==='name') {
   if(typeof value!=='string'||value.length>120||/[\x00-\x1f]/.test(value))throw Error('Invalid Windows voice name.');
   next.voice=value==='default'?'':value;next.profile='desktop';
  } else throw Error('Unknown voice setting.');
  const tmp=this.file+'.tmp'; fs.writeFileSync(tmp,JSON.stringify(next,null,2)); fs.renameSync(tmp,this.file);
  const switched=next.profile!==this.settings.profile;
  this.settings=next; this.error=''; if(op==='off'||(switched&&next.profile==='desktop'))this.stop(); else if(switched&&this.active)this.cancel();else this.changed();
  if(op==='character'&&this.neural?.prewarm===true&&next.profile!=='desktop')this.warm();
 }
 stop() {clearTimeout(this.idleTimer);const child=this.active,worker=this.worker;if(child)this.log('voice:',`cancelled ${this.settings.profile} (${this.phase})`);this.active=null;this.worker=null;this.ready=false;this.warming=false;this.warmQueued=false;this.playingChunk=0;this.requestId='';this.phase='Idle';this.spokenKey='';this.startedAt=0;if(child)child.kill();if(worker&&worker!==child)worker.kill();this.changed();}
 cancel() {
  const child=this.active,id=this.requestId;
  if(child)this.log('voice:',`cancelled reply; retaining warm ${this.settings.profile} model`);
  this.active=null;this.requestId='';this.spokenKey='';this.playingChunk=0;this.startedAt=0;
  if(child&&child!==this.worker)child.kill();
  if(id&&this.worker)this.worker.stdin.write(JSON.stringify({cancel:id})+'\n','utf8');
  this.phase=this.warming?'Preparing character voice':'Idle';if(this.worker)this.armVoiceIdle();this.changed();
 }
 armVoiceIdle() {clearTimeout(this.idleTimer);this.idleTimer=setTimeout(()=>this.stop(),600000);this.idleTimer.unref?.();}
 ensureWorker() {
  if(!this.worker) {
   const workerEnv=Storage.environment();
   const args=['-I','-X','utf8','-X','pycache_prefix='+workerEnv.PYTHONPYCACHEPREFIX,path.join(this.directory,'neural-worker.py'),'--assets',this.neural.assets,'--parent',String(process.pid)];if(this.neural.quantize===true)args.push('--quantize');
   if(this.neural.engine==='nano')args.push('--engine','nano');
   if(this.neural.device==='hybrid')args.push('--device','hybrid');
   if(this.neural.device==='cuda-fp16')args.push('--device','cuda-fp16');
   if(this.neural.device==='cuda-hybrid')args.push('--device','cuda-hybrid');
   if(typeof this.neural.packages==='string')args.push('--packages',this.neural.packages);
   if(typeof this.neural.torchPackage==='string')args.push('--torch-package',this.neural.torchPackage);
   if(Number.isInteger(this.neural.threads)&&this.neural.threads>=1&&this.neural.threads<=8)args.push('--threads',String(this.neural.threads));
   Storage.validateRoot(path.resolve(this.neural.assets));
   if(fs.existsSync(this.neural.assets))Storage.validateRoot(fs.realpathSync(this.neural.assets));
   const child=this.spawn(this.neural.python,args,{env:workerEnv,windowsHide:true,stdio:['pipe','pipe','pipe']});
   this.worker=child;this.warming=true;let buffer='',diagnostic='';
   const fail=err=>{if(this.worker!==child)return;this.stop();this.error=String(err).slice(0,300);this.log('voice:',this.error);this.changed();};
   child.stdout.setEncoding('utf8');child.stdout.on('data',s=>{buffer+=s;let n;while((n=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,n);buffer=buffer.slice(n+1);if(!line.startsWith('@voice '))continue;let event;try{event=JSON.parse(line.slice(7));}catch{continue;}
    if(event.id&&event.id!==this.requestId)continue;if(event.error){fail(event.error);return;}
    if(event.rendered)this.log('voice:',`chunk ${event.rendered}/${event.total}; ${event.cached?'cached':JSON.stringify(event.metrics)}`);
    if(event.playing&&event.gap_seconds!==undefined)this.log('voice:',`audio gap ${event.gap_seconds}s`);
    if(event.done&&event.metrics)this.log('voice:','diagnostic '+JSON.stringify(event.metrics));
    if(event.engine)this.log('voice:',`${event.phase}; ${event.engine}/${event.device}`);
    if(event.loaded&&!this.warmQueued){this.ready=true;this.warming=false;}
    if(event.warmed){this.warmQueued=false;this.warming=false;this.ready=true;if(!this.active){this.phase='Voice ready';this.armVoiceIdle();}}
    else if(this.active===child||!this.active){
     if(event.playing){this.playingChunk=event.playing;this.phase=event.phase;this.log('voice:',`playing ${event.playing}/${event.total} after ${Math.round((Date.now()-this.startedAt)/1000)}s`);}
     else if(event.played){this.playingChunk=0;this.phase='Preparing next chunk';}
     else if(event.phase&&!this.playingChunk)this.phase=event.phase;
    }
    if(event.done){this.active=null;this.warming=false;this.ready=true;this.playingChunk=0;this.phase='Idle';this.log('voice:','reply playback complete');this.armVoiceIdle();}
    this.changed();
   }if(buffer.length>16000)buffer='';});
   child.stderr.setEncoding('utf8');child.stderr.on('data',s=>{diagnostic=(diagnostic+s).slice(-2000);});
   child.on('error',err=>fail(err.message));child.on('close',code=>fail(diagnostic.trim()||`Neural speech worker exited (${code}).`));child.stdin.on('error',err=>fail(err.message));
  }
  return this.worker;
 }
 warm() {
  if(this.platform!=='win32'||!this.neural||this.settings.profile==='desktop'||this.active)return;
  clearTimeout(this.idleTimer);this.phase='Preparing character voice';this.warming=true;this.warmQueued=true;
  this.ensureWorker().stdin.write(JSON.stringify({warm:true,profile:this.settings.profile})+'\n','utf8');this.changed();
 }
 neuralSay(spoken,mode='summary') {
  if(!this.neural)throw Error('Neural character voices are not installed.');
  if(spoken.length>16000)throw Error('Neural full reply exceeds 16,000 characters; use the summary.');
  clearTimeout(this.idleTimer);this.requestId=randomUUID();this.ensureWorker();this.playingChunk=0;
  this.active=this.worker;this.phase='Generating voice';this.changed();
  this.worker.stdin.write(JSON.stringify({id:this.requestId,profile:this.settings.profile,text:spoken,volume:this.settings.volume,playback:'adaptive'})+'\n','utf8');
 }
 say(text,mode=this.settings.mode) {
  if(this.platform!=='win32')throw Error('Local speech currently requires Windows.');
  const spoken=spokenText(text,mode); if(!spoken)throw Error('This reply has no readable text.');
  if(spoken.length>200000)throw Error('Reply exceeds the speech size limit; use the summary.');
  const key=this.settings.profile+'\n'+spoken;
  if(this.active && this.settings.profile!=='desktop' && this.spokenKey===key){this.changed();return;}
  if(this.settings.profile==='desktop')this.stop();else if(this.active)this.cancel();this.error='';
  this.spokenKey=key;this.startedAt=Date.now();
  this.log('voice:',`start ${this.settings.profile}; ${mode}; ${spoken.length} characters`);
  if(this.settings.profile!=='desktop'){this.neuralSay(spoken,mode);return;}
  const child=this.spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(this.directory,'speak.ps1'),'-ParentId',String(process.pid)],{env:Storage.environment(),windowsHide:true,stdio:['pipe','ignore','pipe']});
  this.active=child; this.changed(); let diagnostic='';
  child.stderr?.setEncoding('utf8'); child.stderr?.on('data',s=>{diagnostic=(diagnostic+s).slice(-2000);});
  const fail=err=>{if(this.active!==child)return;this.active=null;child.kill();this.error=String(err).slice(0,300);this.log('voice:',this.error);this.changed();};
  child.on('error',err=>fail(err.message));
  child.on('close',code=>{if(this.active!==child)return;if(code!==0){fail(diagnostic.trim()||`Speech helper exited (${code}).`);return;}this.active=null;this.changed();});
  child.stdin.on('error',err=>fail(err.message));
  child.stdin.end(JSON.stringify({...this.settings,text:spoken}),'utf8');
 }
 completed(text) {if(this.settings.enabled)this.say(text);}
 preview() {
  if(this.platform!=='win32')throw Error('Local speech currently requires Windows.');
  if(this.settings.profile==='desktop'){this.say('Goblin Eye speech test.','full');return;}
  if(!this.neural)throw Error('Neural character voices are not installed.');
  const audioFile=path.join(this.neural.assets,this.neural.engine==='nano'?'auditions-nano':'auditions',this.settings.profile+'.wav');
  if(!fs.existsSync(audioFile))throw Error('The selected voice test clip is missing.');
  if(this.active)this.cancel();clearTimeout(this.idleTimer);this.error='';this.phase='Playing test clip';this.startedAt=Date.now();
  const child=this.spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(this.directory,'speak.ps1'),'-ParentId',String(process.pid)],{env:Storage.environment(),windowsHide:true,stdio:['pipe','ignore','pipe']});
  this.active=child;this.changed();let diagnostic='';
  child.stderr.setEncoding('utf8');child.stderr.on('data',s=>diagnostic=(diagnostic+s).slice(-2000));
  const done=err=>{if(this.active!==child)return;this.active=null;this.phase='Idle';if(err){child.kill();this.error=String(err).slice(0,300);this.log('voice:',this.error);}if(this.worker){this.idleTimer=setTimeout(()=>this.stop(),600000);this.idleTimer.unref?.();}this.changed();};
  child.on('error',e=>done(e.message));child.on('close',code=>done(code===0?'':diagnostic.trim()||'Test voice playback failed.'));child.stdin.on('error',e=>done(e.message));
  child.stdin.end(JSON.stringify({audioFile,volume:this.settings.volume,rate:0}),'utf8');
 }
 control(op,value,findReply) {
  try {
   this.log('voice:',`control ${op}; ${this.settings.profile}`);
   if(op==='stop')this.cancel();
   else if(op==='preview')this.preview();
   else if(op==='listen'||op==='listenfull') {
    const reply=findReply(value);if(!reply)throw Error('Reply no longer exists in the local transcript.');
    this.say(reply.text,op==='listenfull'?'full':'summary');
   } else if(op==='status')this.changed();
   else this.configure(op,value);
  } catch(err) {this.error=err.message;this.log('voice:',this.error);this.changed();}
 }
}
module.exports={SpeechManager,settings,spokenText,PRESETS,findReply};

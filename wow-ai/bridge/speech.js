'use strict';
// Optional Windows speech. Reply text travels as literal stdin data, never code.
const fs = require('fs'), path = require('path');
const {spawn} = require('child_process');
const {splitSummary} = require('./protocol');
const DEFAULTS = {enabled:false, mode:'summary', volume:70, rate:0, voice:'', profile:'desktop'};
function settings(value={}) {
 return {enabled:value.enabled === true, mode:value.mode === 'full' ? 'full' : 'summary',
  volume:Number.isInteger(value.volume) && value.volume >= 0 && value.volume <= 100 ? value.volume : 70,
  rate:Number.isInteger(value.rate) && value.rate >= -10 && value.rate <= 10 ? value.rate : 0,
  voice:typeof value.voice === 'string' && value.voice.length <= 120 ? value.voice : '',
  // Old character preferences migrate to Desktop without loading their assets.
  profile:'desktop'};
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
 return matches.length===1 ? matches[0] : undefined;
}
class SpeechManager {
 constructor({directory, spawnProcess=spawn, platform=process.platform, log=()=>{}, onChange=()=>{}}) {
  this.directory=directory; this.file=path.join(directory,'speech-settings.json');
  this.spawn=spawnProcess; this.platform=platform; this.log=log; this.onChange=onChange;
  try {this.settings=settings(JSON.parse(fs.readFileSync(this.file,'utf8')));} catch {this.settings={...DEFAULTS};}
  this.active=null; this.error=''; this.phase='Idle'; this.startedAt=0;
 }
 info() {return {...this.settings, available:this.platform==='win32', busy:!!this.active, warming:false,
  phase:this.phase, elapsed:this.active&&this.startedAt?Math.floor((Date.now()-this.startedAt)/1000):0, error:this.error};}
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
  } else if(op==='name') {
   if(typeof value!=='string'||value.length>120||/[\x00-\x1f]/.test(value))throw Error('Invalid Windows voice name.');
   next.voice=value==='default'?'':value;
  } else if(op==='character'&&value==='desktop')next.profile='desktop'; // Legacy Desktop button.
  else throw Error('Unsupported voice option. Choose an installed Windows voice.');
  const tmp=this.file+'.tmp'; fs.writeFileSync(tmp,JSON.stringify(next,null,2)); fs.renameSync(tmp,this.file);
  this.settings=next; this.error=''; if(op==='off')this.stop(); else this.changed();
 }
 stop() {
  const child=this.active; this.active=null; this.phase='Idle'; this.startedAt=0;
  if(child)child.kill(); this.changed();
 }
 say(text,mode=this.settings.mode) {
  if(this.platform!=='win32')throw Error('Local speech currently requires Windows.');
  const spoken=spokenText(text,mode); if(!spoken)throw Error('This reply has no readable text.');
  if(spoken.length>200000)throw Error('Reply exceeds the speech size limit; use the summary.');
  this.stop(); this.error=''; this.startedAt=Date.now(); this.phase='Playing';
  this.log('voice:',`start desktop; ${mode}; ${spoken.length} characters`);
  const child=this.spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(this.directory,'speak.ps1'),'-ParentId',String(process.pid)],{windowsHide:true,stdio:['pipe','ignore','pipe']});
  this.active=child; this.changed(); let diagnostic='';
  child.stderr?.setEncoding('utf8'); child.stderr?.on('data',s=>{diagnostic=(diagnostic+s).slice(-2000);});
  const done=err=>{
   if(this.active!==child)return;
   this.active=null;this.phase='Idle';this.startedAt=0;
   if(err){child.kill();this.error=String(err).slice(0,300);this.log('voice:',this.error);}
   this.changed();
  };
  child.on('error',err=>done(err.message));
  child.on('close',code=>done(code===0?'':diagnostic.trim()||`Speech helper exited (${code}).`));
  child.stdin.on('error',err=>done(err.message));
  child.stdin.end(JSON.stringify({...this.settings,text:spoken}),'utf8');
 }
 completed(text) {if(this.settings.enabled)this.say(text);}
 preview() {this.say('Goblin Eye speech test.','full');}
 control(op,value,lookup) {
  try {
   if(op==='stop')this.stop();
   else if(op==='preview')this.preview();
   else if(op==='listen'||op==='listenfull') {
    const reply=lookup(value);if(!reply)throw Error('Reply no longer exists in the local transcript.');
    this.say(reply.text,op==='listenfull'?'full':'summary');
   } else if(op==='status')this.changed();
   else this.configure(op,value);
  } catch(err) {this.error=err.message;this.log('voice:',this.error);this.changed();}
 }
}
module.exports={SpeechManager,settings,spokenText,findReply};

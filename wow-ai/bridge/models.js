'use strict';
// Discovery commands only: no prompts, shell, login changes or config writes.
const {spawn}=require('child_process');
const A=require('./agents');
const TTL=5*60*1000, PAGE_SIZE=10;
const validId=s=>typeof s==='string' && s.length>0 && s.length<=256 && !/^[\s-]|[\x00-\x20\x7f;|]/.test(s);
const clean=(s,n=240)=>String(s||'').replace(/[\x00-\x1f\x7f|]/g,' ').slice(0,n);
function row(m){
 if(!validId(m.id))return null;
 return {id:m.id,name:clean(m.name||m.id,140),description:clean(m.description),variants:(m.variants||[]).filter(validId).slice(0,16),efforts:(m.efforts||[]).filter(validId).slice(0,16),free:m.free===true,priced:Number.isFinite(m.input)&&Number.isFinite(m.output),input:Number(m.input)||0,output:Number(m.output)||0};
}
function kiloModels(text){
 const out=[];let id='',block='',depth=0;
 for(const line of text.replace(/\x1b\[[0-9;]*m/g,'').split(/\r?\n/)){
  if(!depth && validId(line.trim()) && line.includes('/')){id=line.trim();continue;}
  if(!depth && line.trim()!=='{')continue;
  block+=line+'\n';depth+=(line.match(/^\s*\{$|:\s*\{$/g)||[]).length;
  // CLI pretty JSON can contain nested arrays/objects on one line. Use a JSON
  // parse attempt at each closing root candidate rather than count braces in strings.
  if(line.trim()==='}' && line[0]==='}'){
   try{const m=JSON.parse(block);if(m.capabilities?.toolcall!==false && !['deprecated','retired'].includes(m.status))out.push(row({id,name:m.name,description:m.options?.description,variants:Object.keys(m.variants||{}),free:m.isFree===true,input:m.cost?.input,output:m.cost?.output}));}catch{}
   depth=0;block='';
  }
 }
 return out.filter(Boolean);
}
function parseModels(id,text){
 if(id==='kilo')return kiloModels(text);
 if(id==='agy')return text.split(/\r?\n/).map(line=>{const [value,name]=line.split('\t');return name?row({id:value,name}):null;}).filter(Boolean);
 return [];
}
function discover(id,cfg,{refresh=false,spawnFn=spawn,cwd=process.cwd(),timeout=25000}={}){
 const cmd=A.resolveCommand(id,cfg);
 if(!cmd.found)return Promise.reject(Error(`${A.displayName(id)} is not installed.`));
 if(!['kilo','agy','codex','claude'].includes(id))return Promise.reject(Error('This CLI has no supported model-discovery interface. Use its configured model.'));
 return new Promise((resolve,reject)=>{
  const args=id==='kilo'?['models','--verbose',...(refresh?['--refresh']:[])]:id==='agy'?['models']:id==='codex'?['app-server']:['-p','--input-format','stream-json','--output-format','stream-json','--verbose'];
  const env={...process.env};delete env.CLAUDECODE;
  const child=spawnFn(cmd.file,[...cmd.args,...args],{cwd,env,windowsHide:true,stdio:['pipe','pipe','pipe']});
  let text='',buffer='',size=0,settled=false,rows=[],cursor=null,pages=0;
  const timer=setTimeout(()=>done(Error('Model discovery timed out. Refresh to retry.')),timeout);
  function done(err,result){if(settled)return;settled=true;clearTimeout(timer);child.kill();err?reject(err):resolve(result);}
  function send(ev){child.stdin.write(JSON.stringify(ev)+'\n');}
  child.on('error',()=>done(Error('Could not start model discovery.')));
  child.stdin.on('error',()=>{});
  child.stderr.on('data',()=>{}); // Never put credentials, paths or raw diagnostics in the game.
  child.stdout.setEncoding('utf8');child.stdout.on('data',s=>{
   size+=Buffer.byteLength(s);if(size>8*1024*1024)return done(Error('Model catalog exceeds the discovery size limit.'));
   if(id==='kilo'||id==='agy'){text+=s;return;}
   buffer+=s;let n;
   while((n=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,n);buffer=buffer.slice(n+1);let ev;try{ev=JSON.parse(line);}catch{continue;}
    if(id==='claude' && ev.type==='control_response' && ev.response?.request_id==='wow-models'){
     if(ev.response.subtype!=='success')return done(Error('Claude could not supply its model list.'));
     return done(null,(ev.response.response?.models||[]).map(m=>row({id:m.value,name:m.displayName,description:m.description,efforts:m.supportedEffortLevels})).filter(Boolean));
    }
    if(id==='codex' && ev.id===1){if(ev.error)return done(Error('Codex model discovery initialization failed.'));send({method:'initialized',params:{}});send({id:2,method:'model/list',params:{includeHidden:false}});}
    if(id==='codex' && ev.id===2){
     if(ev.error)return done(Error('Codex could not supply its model list.'));
     rows.push(...(ev.result?.data||[]).filter(m=>!m.hidden).map(m=>row({id:m.model||m.id,name:m.displayName,description:m.description,efforts:(m.supportedReasoningEfforts||[]).map(e=>e.reasoningEffort)})).filter(Boolean));
     if(ev.result?.nextCursor){if(++pages>30||cursor===ev.result.nextCursor)return done(Error('Codex model pagination did not complete.'));cursor=ev.result.nextCursor;send({id:2,method:'model/list',params:{includeHidden:false,cursor}});}else done(null,rows);
    }
   }
  });
  child.on('close',code=>{if(settled)return;if(code!==0)return done(Error(`${A.displayName(id)} model discovery failed. Check its login in a terminal.`));const result=parseModels(id,text);result.length?done(null,result):done(Error('The CLI returned no usable models.'));});
  if(id==='codex')send({id:1,method:'initialize',params:{clientInfo:{name:'wow_ai_models',version:'1.0'},capabilities:{experimentalApi:true}}});
  else if(id==='claude')send({type:'control_request',request_id:'wow-models',request:{subtype:'initialize'}});
  else child.stdin.end();
 });
}
class ModelCatalog {
 constructor({config,defaultAgent,onChange=()=>{},loader=discover,now=Date.now,cwd}={}){Object.assign(this,{config,defaultAgent,onChange,loader,now,cwd});this.cache=new Map();this.pending=new Map();this.views=new Map();this.sequence=new Map();}
 async request(job){
  let req;try{req=JSON.parse(job.text||'{}');}catch{req={};}
  const id=A.normalizeAgent(req.agent||job.agent||this.defaultAgent), chat=String(job.chat||''), seq=(this.sequence.get(chat)||0)+1;this.sequence.set(chat,seq);
  if(!id){this.views.set(chat,{chat,agent:'',status:'error',error:'Unknown agent.',items:[]});this.onChange();return;}
  const acfg=A.agentConfig(this.config,id), query=clean(req.query,100).trim().toLowerCase(), free=req.free===true;
  const base={chat,agent:id,request_id:job.id,query,free,default_model:clean(acfg.model,256),default_variant:clean(acfg.variant,80),default_effort:clean(acfg.effort,80),permission:clean(acfg.permissionMode||'default'),research_only:acfg.researchOnly===true,can_restrict:['kilo','codex','claude','agy'].includes(id),page_size:PAGE_SIZE};
  this.views.set(chat,{...base,status:'loading',items:[]});this.onChange();
  try{
   let entry=this.cache.get(id);
   if(!entry || req.refresh===true || this.now()-entry.time>TTL){
    if(!this.pending.has(id))this.pending.set(id,this.loader(id,acfg,{refresh:req.refresh===true,cwd:this.cwd}).then(items=>{const unique=[...new Map(items.filter(Boolean).map(m=>[m.id,m])).values()];if(!unique.length)throw Error('No models were returned.');const result={time:this.now(),items:unique};this.cache.set(id,result);return result;}).finally(()=>this.pending.delete(id)));
    entry=await this.pending.get(id);
   }
   if(this.sequence.get(chat)!==seq)return;
   const filtered=entry.items.filter(m=>(!free||m.free)&&(!query||(m.id+' '+m.name+' '+m.description).toLowerCase().includes(query))).sort((a,b)=>Number(b.free)-Number(a.free)||a.name.localeCompare(b.name));
   const pages=Math.max(1,Math.ceil(filtered.length/PAGE_SIZE)),page=Math.min(pages,Math.max(1,Math.floor(Number(req.page)||1)));
   const selected=entry.items.find(m=>m.id===req.selected);
   this.views.set(chat,{...base,status:'ready',fetched_at:Math.floor(entry.time/1000),total:filtered.length,catalog_total:entry.items.length,page,pages,items:filtered.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE),selected});
  }catch(e){if(this.sequence.get(chat)!==seq)return;this.views.set(chat,{...base,status:'error',error:clean(e.message),items:[]});}
  this.onChange();
 }
 wire(){return [...this.views.values()].slice(-16);}
 close(){this.views.clear();}
}
function parseOptions(raw){
 if(raw===undefined||raw==='')return {};
 let opts;try{opts=typeof raw==='string'?JSON.parse(raw):raw;}catch{throw Error('Invalid chat settings.');}
 if(!opts||typeof opts!=='object'||Array.isArray(opts))throw Error('Invalid chat settings.');
 const out={};for(const k of ['model','variant','effort']){if(opts[k]!==undefined && opts[k]!==''){if(!validId(opts[k]))throw Error(`Invalid ${k} selection.`);out[k]=opts[k];}}
 if(opts.restrict===true)out.restrict=true;
 return out;
}
function applyOptions(base,id,raw,entry){
 const opts=parseOptions(raw),cfg={...base};
 const extras=Array.isArray(cfg.extraArgs)?cfg.extraArgs:[];
 if(opts.restrict && extras.some(s=>/^(?:--(?:dangerously[^=]*|always-approve|auto|yolo|permission[^=]*|sandbox|mode|agent)|-a)(?:=|$)/.test(String(s)) || /^(?:sandbox_mode|permissions\.|approval_policy)\s*=/.test(String(s))))throw Error('Research mode conflicts with extra CLI permission flags. Review those outside the game.');
 cfg.extraArgs=extras.filter((s,i)=>{
  const flags=[...(opts.model?['-m','--model']:[]),...(opts.variant?['--variant']:[]),...(opts.effort?['--effort']:[])];
  if(flags.includes(String(extras[i-1]))||flags.some(f=>String(s)===f||String(s).startsWith(f+'=')))return false;
  if((opts.model||opts.effort) && String(extras[i-1])==='-c' && /^(model|model_reasoning_effort)=/.test(String(s)))return false;
  if((opts.model||opts.effort) && s==='-c' && /^(model|model_reasoning_effort)=/.test(String(extras[i+1])))return false;
  return true;
 });
 if(opts.model)cfg.model=opts.model;
 const selected=entry?.items?.find(m=>m.id===cfg.model);
 if(opts.effort){if(!['codex','claude'].includes(id)||(selected&&!selected.efforts.includes(opts.effort)))throw Error('Refresh models and select a supported reasoning effort.');cfg.effort=opts.effort;}
 else if(opts.model && !selected?.efforts.includes(cfg.effort))delete cfg.effort;
 if(opts.variant){if(id!=='kilo'||(selected&&!selected.variants.includes(opts.variant)))throw Error('Refresh models and select a supported Kilo variant.');cfg.variant=opts.variant;}
 else if(opts.model && !selected?.variants.includes(cfg.variant))delete cfg.variant;
 if(opts.restrict){
  if(id==='kilo'){cfg.permissionMode='default';cfg.researchOnly=true;}
  else if(id==='codex')cfg.permissionMode='default';
  else if(id==='claude'){cfg.permissionMode='plan';cfg.allowedTools=[];cfg.deniedTools=[...new Set([...(cfg.deniedTools||[]),'Edit','Write','Bash','PowerShell','NotebookEdit'])];}
  else if(id==='agy')cfg.permissionMode='default';
  else throw Error('This agent does not expose a supported research-only mode.');
 }
 return cfg;
}
module.exports={ModelCatalog,discover,parseModels,parseOptions,applyOptions,validId,row,TTL,PAGE_SIZE};

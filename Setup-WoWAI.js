#!/usr/bin/env node
'use strict';
// Local setup only. Never logs in, changes global agent config or controls WoW.
const fs=require('fs'),path=require('path'),{spawnSync}=require('child_process');
const readline=require('readline/promises');
const A=require('./wow-ai/bridge/agents');
const ROOT=__dirname;
function options(argv) {
 const out={};
 for(let i=0;i<argv.length;i++) {
  const key=argv[i].replace(/^--/,'');
  if(!['wow','account','agent','yes','help'].includes(key)||!argv[i].startsWith('--'))throw Error('Unknown option: '+argv[i]);
  if(['yes','help'].includes(key))out[key]=true;
  else {if(!argv[i+1]||argv[i+1].startsWith('--'))throw Error('Missing value for --'+key);out[key]=argv[++i];}
 }
 return out;
}
function isClient(dir) {
 try{return fs.statSync(path.join(dir,'Interface')).isDirectory()&&fs.readdirSync(dir).some(n=>/^Wow.*\.exe$/i.test(n));}catch{return false;}
}
function clients() {
 const roots=[process.env['ProgramFiles(x86)'],process.env.ProgramFiles,'C:/Games','D:','E:','D:/Games','E:/Games'].filter(Boolean);
 return [...new Set(roots.flatMap(r=>['_classic_beta_','_forever_'].map(f=>path.resolve(r+(r.endsWith(':')?'/':''),'World of Warcraft',f))).filter(isClient))];
}
function accounts(client) {
 const base=path.join(client,'WTF','Account');
 try{return fs.readdirSync(base,{withFileTypes:true}).filter(d=>d.isDirectory()&&d.name!=='SavedVariables').map(d=>d.name).sort();}catch{return [];}
}
function atomic(file,data) {
 fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=file+'.tmp';fs.writeFileSync(tmp,data);fs.renameSync(tmp,file);
}
function json(file,data){atomic(file,JSON.stringify(data,null,2)+'\n');}
function mcpConfigs(root) {
 const python=path.join(root,'python','python.exe');
 const args=['-m','goblin_eye','--config',path.join(root,'config.json'),'--database',path.join(root,'data','goblin-eye.db'),'mcp'];
 const env={PYTHONPATH:path.join(root,'src')};
 return {
  '.mcp.json':JSON.stringify({mcpServers:{goblin_eye:{command:python,args,env}}},null,2)+'\n',
  'kilo.json':JSON.stringify({mcp:{'goblin-eye':{type:'local',command:[python,...args],environment:env,enabled:true,timeout:30000}}},null,2)+'\n',
  '.codex/config.toml':'# Generated local read-only Goblin Eye MCP connection.\n[mcp_servers.goblin_eye]\ncommand = '+JSON.stringify(python)+'\nargs = '+JSON.stringify(args)+'\n\n[mcp_servers.goblin_eye.env]\nPYTHONPATH = '+JSON.stringify(env.PYTHONPATH)+'\n',
  '.claude/settings.local.json':JSON.stringify({enabledMcpjsonServers:['goblin_eye']},null,2)+'\n'
 };
}
function install(root,client,account,agent) {
 if(!isClient(client))throw Error('Select the client folder containing Wow*.exe and Interface (for example _classic_beta_).');
 if(!accounts(client).includes(account))throw Error('Select an existing account folder. Log into WoW once if none exists.');
 if(!A.normalizeAgent(agent))throw Error('Unknown agent: '+agent);
 const bridge=path.join(root,'wow-ai','bridge'),configFile=path.join(bridge,'config.json');
 const old=fs.existsSync(configFile)?JSON.parse(fs.readFileSync(configFile,'utf8')):null;
 const cfg=old||JSON.parse(fs.readFileSync(path.join(bridge,'config.example.json'),'utf8'));
 if(old&&fs.existsSync(path.join(bridge,'bridge.lock')))throw Error('Stop the chat bridge before running setup again.');
 const project=path.join(root,'Goblin-Eye-Chat');
 if(old?.defaultCwd&&old.defaultCwd!==project)cfg.cwdAliases={...(cfg.cwdAliases||{}),[old.defaultCwd]:project};
 cfg.defaultCwd=project;cfg.addonDir=path.join(client,'Interface','AddOns');
 cfg.inboxFile=path.join(cfg.addonDir,'WoWAI','Inbox.lua');
 cfg.savedVariablesFile=path.join(client,'WTF','Account',account,'SavedVariables','WoWAI.lua');
 cfg.capture.processName=fs.readdirSync(client).find(n=>/^Wow.*\.exe$/i.test(n)).replace(/\.exe$/i,'');
 cfg.agent=agent;cfg.primerFile='../Goblin-Eye-Chat/AGENTS.md';
 // Existing user preferences remain local; new installs use conservative modes.
 const example=JSON.parse(fs.readFileSync(path.join(bridge,'config.example.json'),'utf8'));
 for(const [id,block] of Object.entries(example.agents))cfg.agents[id]??=block;
 const backup=path.join(root,'wow-ai','backups','setup-'+Date.now());
 function backupFile(file,relative) {
  if(fs.existsSync(file)){const dest=path.join(backup,relative);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.copyFileSync(file,dest);}
 }
 backupFile(configFile,'config.json');
 const addon=path.join(cfg.addonDir,'WoWAI');fs.mkdirSync(addon,{recursive:true});
 for(const file of fs.readdirSync(path.join(root,'wow-ai','addon','WoWAI'))) {
  const target=path.join(addon,file);
  if(file==='Inbox.lua'&&fs.existsSync(target))continue;
  backupFile(target,'addon/'+file);fs.copyFileSync(path.join(root,'wow-ai','addon','WoWAI',file),target);
 }
 for(const [name,content] of Object.entries(mcpConfigs(root))) {
  const target=path.join(project,name);backupFile(target,'chat/'+name);atomic(target,content);
 }
 json(configFile,cfg);
 const slots=spawnSync(process.execPath,[path.join(bridge,'install-slots.js')],{encoding:'utf8',windowsHide:true});
 if(slots.status!==0)throw Error('Slot setup failed: '+slots.stderr);
 return {client,account,agent,project,configFile,slots:slots.stdout.trim()};
}
async function main(argv) {
 const opt=options(argv);
 if(opt.help){console.log('Setup-WoWAI.cmd [--wow "<client folder>"] [--account "<folder name>"] [--agent kilo|codex|claude|grok|agy|hermes] [--yes]\nRun interactively to select your client, account and agent. No npm install is needed.');return;}
 if(process.platform!=='win32')throw Error('The packaged setup supports Windows.');
 const [major,minor]=process.versions.node.split('.').map(Number);
 if(major<22||(major===22&&minor<2))throw Error('Install Node.js 22.2 or newer for optional in-game chat.');
 let ui;const ask=async(q,fallback='')=>{if(opt.yes)return fallback;ui??=readline.createInterface({input:process.stdin,output:process.stdout});return (await ui.question(q)).trim()||fallback;};
 try {
  let client=opt.wow;
  if(!client){const found=clients();if(found.length===1)client=await ask('WoW client folder ['+found[0]+']: ',found[0]);else client=await ask('WoW client folder (contains Wow*.exe and Interface): ');}
  if(!client||!isClient(client))throw Error('WoW folder was not found. Run setup with --wow "<client folder>".');client=path.resolve(client);
  const names=accounts(client);console.log('Account folders: '+names.join(', '));
  const account=opt.account||await ask('Account folder'+(names.length===1?' ['+names[0]+']':'')+': ',names.length===1?names[0]:'');
  if(!names.includes(account))throw Error('Choose an account explicitly with --account when several exist.');
  const available=['kilo','codex','claude','grok','agy','hermes'].filter(id=>A.resolveCommand(id,{}).found);
  console.log('Installed agent CLIs: '+(available.join(', ')||'none detected; install and log into one before chatting.'));
  const agent=opt.agent||await ask('Default agent ['+(available[0]||'codex')+']: ',available[0]||'codex');
  const initialize=spawnSync('powershell.exe',['-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',path.join(ROOT,'Run-Goblin-Eye.ps1'),'-InitializeOnly'],{encoding:'utf8',windowsHide:true});
  if(initialize.status!==0)throw Error('Goblin Eye initialization failed: '+initialize.stdout+initialize.stderr);
  const result=install(ROOT,client,account,agent);console.log(result.slots);
  console.log('Ready. Log into your agent CLI once from '+result.project+'. Restart WoW, enable WoW AI and its reply slots, then run Start-Goblin-Eye-Chat.cmd and /wow-ai. Keep Start-Goblin-Eye.cmd running to import new saves.');
 }finally{ui?.close();}
}
module.exports={options,isClient,accounts,mcpConfigs,install,main};
if(require.main===module)main(process.argv.slice(2)).catch(e=>{console.error('Setup failed: '+e.message);process.exitCode=1;});

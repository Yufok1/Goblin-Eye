'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),os=require('os'),path=require('path');
const {install,mcpConfigs,options}=require('../../Setup-WoWAI');
function fixture() {
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'Goblin Eye Setup With Spaces '));
 const src=path.resolve(__dirname,'../..');
 for(const name of ['bridge/config.example.json','bridge/install-slots.js','bridge/protocol.js']) {
  const dest=path.join(root,'wow-ai',name);fs.mkdirSync(path.dirname(dest),{recursive:true});fs.copyFileSync(path.join(src,'wow-ai',name),dest);
 }
 fs.cpSync(path.join(src,'wow-ai/addon/WoWAI'),path.join(root,'wow-ai/addon/WoWAI'),{recursive:true});
 const cfgFile=path.join(root,'wow-ai/bridge/config.example.json');const cfg=JSON.parse(fs.readFileSync(cfgFile));cfg.slots=2;cfg.actMax=2;cfg.presenceMax=2;fs.writeFileSync(cfgFile,JSON.stringify(cfg));
 const client=path.join(root,'Fake Client');fs.mkdirSync(path.join(client,'Interface'),{recursive:true});fs.writeFileSync(path.join(client,'WowB.exe'),'fixture');fs.mkdirSync(path.join(client,'WTF/Account/ACCOUNT'),{recursive:true});
 return {root,client};
}
test('setup installs into an explicitly selected mock client and creates read-only MCP connections',()=>{
 const {root,client}=fixture();const out=install(root,client,'ACCOUNT','kilo');
 const cfg=JSON.parse(fs.readFileSync(out.configFile));assert.equal(cfg.defaultCwd,path.join(root,'Goblin-Eye-Chat'));assert.equal(cfg.agent,'kilo');
 assert.ok(fs.existsSync(path.join(client,'Interface/AddOns/WoWAI_S002/Inbox.lua')));
 const mcp=JSON.parse(fs.readFileSync(path.join(out.project,'.mcp.json'))).mcpServers.goblin_eye;
 assert.equal(mcp.args.at(-1),'mcp');assert.ok(mcp.args.includes(path.join(root,'config.json')));
 const kilo=JSON.parse(fs.readFileSync(path.join(out.project,'kilo.json')));assert.equal(kilo.mcp['goblin-eye'].command[0],mcp.command);
 assert.equal(cfg.agents.codex.permissionMode,'default');assert.equal(cfg.agents.kilo.researchOnly,true);
});
test('rerunning setup preserves user settings and Inbox and repairs moved package paths',()=>{
 const {root,client}=fixture();const out=install(root,client,'ACCOUNT','codex');
 const cfg=JSON.parse(fs.readFileSync(out.configFile));cfg.defaultCwd='old-chat-folder';cfg.agents.codex.model='chosen-model';fs.writeFileSync(out.configFile,JSON.stringify(cfg));
 const inbox=path.join(client,'Interface/AddOns/WoWAI/Inbox.lua');fs.writeFileSync(inbox,'private live Inbox');
 fs.writeFileSync(path.join(out.project,'kilo.json'),'old local config');install(root,client,'ACCOUNT','codex');
 const updated=JSON.parse(fs.readFileSync(out.configFile));assert.equal(updated.agents.codex.model,'chosen-model');assert.equal(updated.cwdAliases['old-chat-folder'],out.project);assert.equal(fs.readFileSync(inbox,'utf8'),'private live Inbox');
 assert.ok(fs.existsSync(path.join(root,'wow-ai/backups')));
 fs.writeFileSync(path.join(root,'wow-ai/bridge/bridge.lock'),'owned');assert.throws(()=>install(root,client,'ACCOUNT','codex'),/Stop the chat bridge/);
});
test('setup refuses ambiguous/wrong accounts, bad arguments and unknown agents',()=>{
 const {root,client}=fixture();assert.throws(()=>install(root,client,'OTHER','codex'),/existing account/);
 assert.throws(()=>install(root,client,'ACCOUNT','unknown'),/Unknown agent/);
 assert.throws(()=>options(['--account']),/Missing/);assert.throws(()=>options(['--secret']),/Unknown/);
 const toml=mcpConfigs(root)['.codex/config.toml'];assert.ok(toml.includes('[mcp_servers.goblin_eye]'));assert.ok(!toml.includes('companion-mcp'));
});

'use strict';
const fs=require('fs'),path=require('path'),fengari=require('fengari');
const {lua,lauxlib,lualib,to_luastring,to_jsstring}=fengari;
function measure(file) {
 const L=lauxlib.luaL_newstate();lualib.luaL_openlibs(L);
 const run=code=>{if(lauxlib.luaL_dostring(L,to_luastring(code))!==lua.LUA_OK)throw new Error(to_jsstring(lua.lua_tostring(L,-1)));};
 run(fs.readFileSync(path.join(__dirname,'wow_stub.lua'),'utf8'));
 for(const f of ['Codec.lua','Inbox.lua'])run(fs.readFileSync(path.join(__dirname,'../addon/WoWAI',f),'utf8'));
 run(fs.readFileSync(file,'utf8'));
 run('STUB.FireEvent("ADDON_LOADED","WoWAI"); STUB.FireEvent("PLAYER_LOGIN"); local c=WoWAIDB.chats[1]; c.history={}; for i=1,200 do c.history[i]={role="assistant",text="Saved herb research "..i,t=i} end; c.pendingId=1; c.progress="checking"; WoWAI.Render(); STUB.measurements=0; for i=1,20 do c.progress="progress update "..i; WoWAI.Render() end; RESULT=STUB.measurements');
 lua.lua_getglobal(L,to_luastring('RESULT'));const measurements=lua.lua_tonumber(L,-1);lua.lua_close(L);
 return {historyMessages:200,progressUpdates:20,textMeasurements:measurements};
}
const baseline=measure(path.join(__dirname,'../baseline/research-preview1/WoWAI.lua'));
const optimized=measure(path.join(__dirname,'../addon/WoWAI/WoWAI.lua'));
const result={baseline,optimized,reductionPercent:100*(1-optimized.textMeasurements/baseline.textMeasurements),scope:'Synthetic Lua API-work measurement using Fengari and the WoW stub; not in-game FPS or model/MCP speed.'};
fs.writeFileSync(path.join(__dirname,'../layout-benchmark.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));

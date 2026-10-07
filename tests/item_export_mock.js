// Run with an already-installed Fengari: FENGARI_PATH=/path/to/fengari node this-file [saved-output]
// No dependency installation is performed.
const fs = require('fs');
const path = require('path');
const {lua, lauxlib, lualib, to_luastring, to_jsstring} = require(process.env.FENGARI_PATH || 'fengari');
const helper = fs.readFileSync(path.join(__dirname, '../integrations/alts-forever/GoblinEyeExport.lua'), 'utf8');
const fixture = `
local ns = {db = {v=2,chars={}}, char={name="Fixture",class="WARLOCK",level=26,faction="Horde",gear={}}}
ns.db.chars.Fixture=ns.char
local events, timers = {}, {}
ns.On=function(event,fn) events[event]=fn end
local complete=true
ns.ScanGear=function(c) return not complete end
local scanned=0
ns.ScanContainers=function() scanned=scanned+1 end
ns.ItemScore=function() return 123 end
local combat=false
InCombatLockdown=function() return combat end
time=function() return 1791371090 end
local clock=0
GetTime=function() return clock end
GetBuildInfo=function() return "1.60.1", "70170" end
GetLocale=function() return "enUS" end
C_Timer={After=function(_,fn) timers[#timers+1]=fn end}
local function flush()
  local count=0
  while #timers>0 do
    local fn=table.remove(timers,1); fn(); count=count+1
    assert(count<1000,"unbounded polling")
  end
end
local function link(id,bonus) return "|cnIQ2:|Hitem:"..id..":254:::::::26:::::1:"..bonus.."|h[Fixture]|h|r" end
local one,two,three,four=link(6617,12729),link(6617,12730),link(10288,12729),link(9820,12729)
local secretValue={secret=true}
issecretvalue=function(v) return v==secretValue end
local cached={[6617]=true,[10288]=false,[9820]=true}
local calls=0
C_Item={
 IsItemDataCachedByID=function(id) return cached[id] end,
 GetItemStats=function(l)
   calls=calls+1
   return {ITEM_MOD_INTELLECT_SHORT=l==two and 11 or 7, ITEM_MOD_STAMINA_SHORT=secretValue}
 end
}
C_Container={GetContainerNumSlots=function(bag) return bag==0 and 2 or 0 end,
 GetContainerItemLink=function(_,slot) return slot==1 and two or three end}
GameTooltip={IsForbidden=function() return false end,GetItem=function() return "Fixture",one end}
ItemRefTooltip={IsForbidden=function() return false end,GetItem=function() return "Fixture",four end}
Enum={TooltipDataType={Item=1}}
local tooltipHook
TooltipDataProcessor={AddTooltipPostCall=function(_,fn) tooltipHook=fn end}
local function loadAddon(...)
`;
const checks = `
end
loadAddon("AltsForever",ns)
events.PLAYER_LOGIN()
ns.char.gear[7]=one
assert(ns.ScanGear(ns.char)==false)
ns.ScanContainers({0},{},{})
assert(scanned==1 and ns.ItemScore(one,"caster")==123)
flush()
local key=one:match("|H(item:[^|]*)|h")
local key2=two:match("|H(item:[^|]*)|h")
local key3=three:match("|H(item:[^|]*)|h")
local key4=four:match("|H(item:[^|]*)|h")
assert(ns.db.goblinEye.items[key].stats.ITEM_MOD_INTELLECT_SHORT==7)
assert(ns.db.goblinEye.items[key2].stats.ITEM_MOD_INTELLECT_SHORT==11,"unequipped suffix must be independent")
assert(ns.db.goblinEye.items[key].stats.ITEM_MOD_STAMINA_SHORT==nil,"secret values must not be persisted")
assert(ns.db.goblinEye.items[key3]==nil,"unloaded item must not become empty stats")
assert(ns.char.goblinEyeGear.slots[13]==false)
cached[10288]=true
events.GET_ITEM_INFO_RECEIVED(); flush()
assert(ns.db.goblinEye.items[key3],"cached unequipped item retry")
tooltipHook(GameTooltip,{lines={{leftText="+7 Intellect"},{leftText=secretValue,rightText="Requires Level 24"}}})
assert(#ns.db.goblinEye.items[key].tooltip==2)
local oldCalls=calls
tooltipHook(GameTooltip,{lines={{leftText="repeat"}}})
assert(calls==oldCalls,"tooltip refresh cooldown")
combat=true
tooltipHook(ItemRefTooltip,{lines={{leftText="blocked"}}})
assert(ns.db.goblinEye.items[key4]==nil)
combat=false; clock=3
tooltipHook(ItemRefTooltip,{lines={{leftText="Observed preview item"}}})
assert(ns.db.goblinEye.items[key4],"ordinary tooltip may record unequipped preview")
complete=false; ns.char.goblinEyeGear=nil
assert(ns.ScanGear(ns.char)==true and ns.char.goblinEyeGear==nil,"incomplete scan cannot establish empty slots")
local function serialize(v)
 if type(v)=="table" then
  local out={}; for k,x in pairs(v) do out[#out+1]="["..serialize(k).."]="..serialize(x) end
  return "{"..table.concat(out,",").."}"
 elseif type(v)=="string" then return string.format("%q",v)
 else return tostring(v) end
end
RESULT="AltsForeverDB="..serialize(ns.db)
`;
const L=lauxlib.luaL_newstate(); lualib.luaL_openlibs(L);
if(lauxlib.luaL_loadstring(L,to_luastring(fixture+helper+checks))!==lua.LUA_OK || lua.lua_pcall(L,0,0,0)!==lua.LUA_OK){
  throw new Error(to_jsstring(lua.lua_tostring(L,-1)));
}
lua.lua_getglobal(L,to_luastring('RESULT'));
const result=to_jsstring(lua.lua_tostring(L,-1));
if(process.argv[2]) fs.writeFileSync(process.argv[2],result);
console.log('Alts export Lua checks passed: cached/unequipped variants, secret guards, tooltip debounce, combat guard, retries, incomplete slots.');

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
ns.On=function(event,fn)
 local previous=events[event]
 events[event]=previous and function(...) previous(...); fn(...) end or fn
end
local complete=true
ns.ScanGear=function(c) return not complete, true end
local scanned=0
local retainedLinks={}
ns.ScanContainers=function(_,_,_,links)
 scanned=scanned+1
 if links then assert(links==retainedLinks); links.kept=true end
end
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
local requests={}
C_Item={
 IsItemDataCachedByID=function(id) return cached[id] end,
 RequestLoadItemDataByID=function(id) requests[id]=(requests[id] or 0)+1 end,
 GetItemInfo=function() return "Observed Item",nil,2,29,24,"Armor","Cloth",1,"INVTYPE_CHEST" end,
 GetItemStats=function(l)
   calls=calls+1
   return {ITEM_MOD_INTELLECT_SHORT=l==two and 11 or 7, ITEM_MOD_STAMINA_SHORT=secretValue}
 end
}
local tooltipCalls, delayedTooltip=0,true
C_TooltipInfo={GetHyperlink=function(l)
 tooltipCalls=tooltipCalls+1
 if l==two and delayedTooltip then delayedTooltip=false; return nil end
 return {lines={{leftText="Observed automatic item details"}}}
end}
C_Container={GetContainerNumSlots=function(bag) return bag==0 and 2 or 0 end,
 GetContainerItemLink=function(_,slot) return slot==1 and two or three end}
GameTooltip={IsForbidden=function() return false end,GetItem=function() return "Fixture",one end}
ItemRefTooltip={IsForbidden=function() return false end,GetItem=function() return "Fixture",four end}
Enum={TooltipDataType={Item=1}}
UnitHealthMax=function() return 900 end
UnitPowerMax=function() return 1200 end
UnitStat=function(_,i) return i*10,i*10+5 end
UnitArmor=function() return 120,140 end
GetSpellBonusDamage=function(school) return school==6 and 43 or 9 end
GetSpellCritChance=function() return 3.5 end
GetSpellHitModifier=function() return 1 end
GetManaRegen=function() return 5,1 end
UnitRace=function() return "Orc","Orc" end
GetRealmName=function() return "Fixture Realm" end
C_QuestLog={GetAllCompletedQuestIDs=function() return {843,846,849} end}
local questRows={{isHeader=true,title="Zone"}, {isHeader=false,questID=1001,title="Partial quest",level=8},
 {isHeader=false,questID=1002,title="Turn in",level=9}}
C_QuestLog.GetNumQuestLogEntries=function() return #questRows,2 end
C_QuestLog.GetInfo=function(index) return questRows[index] end
C_QuestLog.ReadyForTurnIn=function(id) return id==1002 end
C_QuestLog.GetQuestObjectives=function(id)
 if id==1002 then return {} end
 return {{text="Collect things: 2/5",type="item",numFulfilled=2,numRequired=5,finished=false}}
end
local mapX=0.42
C_Map={GetBestMapForUnit=function() return 123 end,
 GetPlayerMapPosition=function() return {GetXY=function() return mapX,0.63 end} end}
GetZoneText=function() return "Fixture zone" end
GetSubZoneText=function() return "Fixture landmark" end
C_Traits={GetConfigsByType=function() return {100} end,
 GetConfigInfo=function() return {treeIDs={200}} end,
 GetTreeNodes=function() return {301,302} end,
 GetNodeInfo=function(_,id) return {currentRank=id==301 and 3 or 0,activeEntry={entryID=400}} end,
 GetEntryInfo=function() return {definitionID=500} end,
 GetDefinitionInfo=function() return {spellID=600} end}
C_Spell={GetSpellInfo=function() return {name="Observed Talent"} end}
C_UnitAuras={GetAuraDataByIndex=function(_,i) if i==1 then return {spellId=700,name="Observed Buff",applications=1} end end}
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
assert(#ns.db.goblinEye.items[key].tooltip==1,"equipped tooltip must capture without hovering")
assert(ns.db.goblinEye.items[key].metadata.required_level==24,"client metadata must be captured generically")
assert(#ns.db.goblinEye.items[key2].tooltip==1,"delayed tooltip must retry without hover or cache event")
assert(requests[10288]==1,"uncached item data must be requested once")
assert(ns.db.goblinEye.items[key].stats.ITEM_MOD_STAMINA_SHORT==nil,"secret values must not be persisted")
assert(ns.db.goblinEye.items[key3]==nil,"unloaded item must not become empty stats")
assert(ns.char.goblinEyeGear.slots[13]==false)
cached[10288]=true
events.GET_ITEM_INFO_RECEIVED(); flush()
assert(ns.db.goblinEye.items[key3],"cached unequipped item retry")
clock=3
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
-- Automatic work paused during lockdown must resume without hover/equipment input.
local five=link(5003,1)
cached[5003]=true
combat=true; ns.char.gear[2]=five; ns.ScanGear(ns.char); flush()
local key5=five:match("|H(item:[^|]*)|h")
assert(ns.db.goblinEye.items[key5]==nil)
combat=false; complete=true; events.PLAYER_REGEN_ENABLED(); flush()
assert(ns.db.goblinEye.items[key5].stats.ITEM_MOD_INTELLECT_SHORT==7)
assert(#ns.db.goblinEye.items[key5].tooltip==1,"deferred automatic tooltip resumes")
-- Unavailable tooltip service must stop its timed retries, preserving numeric data.
local six=link(5001,1)
cached[5001]=true
C_TooltipInfo.GetHyperlink=function() return nil end
ns.char.gear[11]=six; ns.ScanGear(ns.char); flush()
local key6=six:match("|H(item:[^|]*)|h")
assert(ns.db.goblinEye.items[key6].stats.ITEM_MOD_INTELLECT_SHORT==7)
assert(#ns.db.goblinEye.items[key6].tooltip==0 and #timers==0,"failed tooltip retry must be bounded")
events.PLAYER_ENTERING_WORLD(); flush()
assert(ns.char.goblinEyeCharacter.stats.shadow_damage==43)
assert(ns.char.goblinEyeCharacter.stats.intellect==45)
assert(ns.char.goblinEyeCharacter.talents.nodes[1].spellID==600)
assert(ns.char.goblinEyeCharacter.buffs.records[1].spellID==700)
assert(ns.char.goblinEyeQuests.completed[849]==true)
assert(select(2,ns.ScanGear(ns.char))==true,"preserve Alts 1.7 changed return flag")
ns.ScanContainers({}, {}, {}, retainedLinks)
assert(retainedLinks.kept,"preserve Alts 1.8 retained variant links argument")
assert(ns.char.goblinEyeQuestLog.status=="recorded")
assert(#ns.char.goblinEyeQuestLog.entries==2,"headers excluded")
assert(ns.char.goblinEyeQuestLog.entries[1].objectives.records[1].numFulfilled==2)
assert(ns.char.goblinEyeQuestLog.entries[1].readyForTurnIn==false)
assert(ns.char.goblinEyeQuestLog.entries[2].readyForTurnIn==true)
assert(ns.char.goblinEyeLocation.x==0.42)
mapX=0.75; events.QUEST_LOG_UPDATE(); flush()
assert(ns.char.goblinEyeLocation.x==0.42,"quest events must not track movement")
events.PLAYER_LOGOUT()
assert(ns.char.goblinEyeLocation.x==0.75,"save refreshes the starting point")
local oldLog=ns.char.goblinEyeQuestLog
combat=true; events.PLAYER_LOGOUT()
assert(ns.char.goblinEyeQuestLog==oldLog,"lockdown retains earlier capture and timestamp")
combat=false
C_QuestLog.ReadyForTurnIn=function() return secretValue end
C_QuestLog.GetQuestObjectives=function() return nil end
events.QUEST_LOG_UPDATE(); flush()
assert(ns.char.goblinEyeQuestLog.status=="partial")
assert(ns.char.goblinEyeQuestLog.entries[1].readyForTurnIn==nil,"secret readiness is unknown")
assert(ns.char.goblinEyeQuestLog.entries[1].objectives.status=="not_recorded")
C_QuestLog.GetNumQuestLogEntries=function() return 0,0 end
events.QUEST_REMOVED(); flush()
assert(ns.char.goblinEyeQuestLog.status=="recorded" and #ns.char.goblinEyeQuestLog.entries==0,"removed quests replace the log")
C_QuestLog.GetNumQuestLogEntries=nil
events.QUEST_LOG_UPDATE(); flush()
assert(ns.char.goblinEyeQuestLog.status=="not_recorded","unsupported API is not an empty log")
C_Map.GetPlayerMapPosition=function() return nil end
events.PLAYER_LOGOUT()
assert(ns.char.goblinEyeLocation.x==nil and ns.char.goblinEyeLocation.status=="partial","unavailable coordinates stay unknown")
local before=ns.char.goblinEyeCharacter
combat=true; events.UNIT_STATS("player"); events.QUEST_LOG_UPDATE(); flush()
assert(ns.char.goblinEyeCharacter==before,"never capture character-sheet telemetry in combat")
combat=false
GetSpellHitModifier=function() return secretValue end
events.UNIT_STATS("target"); flush()
assert(ns.char.goblinEyeCharacter==before,"ignore other units")
events.UNIT_STATS("player"); flush()
assert(ns.char.goblinEyeCharacter.stats.spell_hit_modifier_percent==nil,"secret character stats stay unknown")
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
console.log('Alts export Lua checks passed: automatic gear/bag tooltips, bounded warmup, cache requests, deferred capture, variants, secret guards, debounce, incomplete slots.');

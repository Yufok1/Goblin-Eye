-- Goblin Eye's optional observation export, loaded by the existing Alts Forever.
-- No gameplay inputs, combat tracking, chat transport, or invented suffix values.
local _, ns = ...
if ns.disabled then return end
local secret = issecretvalue or function() return false end
local function Plain(v) if not secret(v) then return v end end
local function Call(fn, ...)
    if type(fn) ~= "function" then return end
    local ok, a, b, c, d = pcall(fn, ...)
    if ok then return Plain(a), Plain(b), Plain(c), Plain(d) end
end
local function Number(v)
    v = Plain(v)
    if type(v) == "number" and v == v and math.abs(v) <= 100000000 then return v end
end
local function Text(v)
    v = Plain(v)
    if type(v) == "string" and #v <= 200 then return v end
end
local pending, waiting, seen, tooltipAt, scheduled = {}, {}, {}, {}, false
local requested, attempts, retryScheduled = {}, {}, false
local MAX_ITEMS = 1000
local MAX_ATTEMPTS = 4

local function Key(link)
    link = Plain(link)
    if type(link) ~= "string" or #link > 2048 then return end
    return link:match("|H(item:%d+:[^|]*)|h")
end

local function Lines(data)
    local out, bytes = {}, 0
    if secret(data) or type(data) ~= "table" or secret(data.lines) or type(data.lines) ~= "table" then return out end
    for _, line in ipairs(data.lines) do
        if not secret(line) and type(line) == "table" then
        for _, field in ipairs({"leftText", "rightText"}) do
            local text = Plain(line[field])
            if type(text) == "string" and text ~= "" and #out < 40 then
                text = text:sub(1, 400)
                -- Never persist an incomplete UTF-8 code point at the byte bound.
                local start = #text
                while start > 0 and text:byte(start) >= 128 and text:byte(start) < 192 do start = start - 1 end
                local lead = start > 0 and text:byte(start) or 0
                local width = lead >= 240 and 4 or lead >= 224 and 3 or lead >= 192 and 2 or 1
                if #text - start + 1 < width then text = text:sub(1, start - 1) end
                if bytes + #text <= 8000 then
                    out[#out + 1] = text
                    bytes = bytes + #text
                end
            end
        end
        end
    end
    return out
end

local function Capture(link, data)
    if InCombatLockdown and InCombatLockdown() then return false end
    local key = Key(link)
    if not key or not ns.db then return false end
    local id = tonumber(key:match("^item:(%d+):"))
    if C_Item and C_Item.IsItemDataCachedByID then
        local ok, cached = pcall(C_Item.IsItemDataCachedByID, id)
        if not ok or secret(cached) then return false end
        if not cached then
            if not requested[id] and C_Item.RequestLoadItemDataByID then
                requested[id] = true
                pcall(C_Item.RequestLoadItemDataByID, id)
            end
            return false
        end
        requested[id] = nil -- bound request bookkeeping to data still loading
    end
    local clock = GetTime and GetTime() or time()
    if data and tooltipAt[key] and clock - tooltipAt[key] < 2 then return true end
    local build = GetBuildInfo and select(2, GetBuildInfo()) or "unknown"
    if secret(build) then return false end
    build = tostring(build)
    local locale = GetLocale and GetLocale() or "unknown"
    if secret(locale) then return false end
    if seen[key] and not data then return true end
    local fn = C_Item and C_Item.GetItemStats
    if not fn then return false end
    local ok, raw = pcall(fn, link)
    if not ok or secret(raw) or type(raw) ~= "table" then return false end
    local stats = {}
    for k, v in pairs(raw) do
        if not secret(k) and not secret(v) and type(k) == "string" and type(v) == "number"
            and k:match("^[A-Z][A-Z0-9_]*$") and #k <= 100 and v == v and math.abs(v) <= 100000000 then
            stats[k] = v
        end
    end
    ns.db.goblinEye = ns.db.goblinEye or {version = 1, items = {}}
    local export = ns.db.goblinEye
    if export.version ~= 1 or type(export.items) ~= "table" then return false end
    local count, oldestKey, oldestAt = 0, nil, nil
    if not export.items[key] then
        for k, row in pairs(export.items) do
            count = count + 1
            local at = row.capturedAt or 0
            if not oldestAt or at < oldestAt then oldestKey, oldestAt = k, at end
        end
        if count >= MAX_ITEMS and oldestKey then
            export.items[oldestKey] = nil
            seen[oldestKey], tooltipAt[oldestKey], attempts[oldestKey] = nil, nil, nil
        end
    end
    local previous = export.items[key]
    -- Read ordinary item tooltip data directly. No visible tooltip, mouse hover,
    -- game input or WoWAI transport is needed for equipped/bag item details.
    local automaticTooltip = not data and C_TooltipInfo and C_TooltipInfo.GetHyperlink
    if automaticTooltip then
        local tooltipOK, tooltipData = pcall(C_TooltipInfo.GetHyperlink, link)
        if tooltipOK and not secret(tooltipData) then data = tooltipData end
    end
    local tooltip = Lines(data)
    if #tooltip == 0 and previous and previous.build == build then tooltip = previous.tooltip or {} end
    local metadata = {}
    local infoAPI = C_Item and C_Item.GetItemInfo or GetItemInfo
    if infoAPI then
        local infoOK, name, _, quality, level, required, _, _, _, equip = pcall(infoAPI, link)
        if infoOK then metadata = {name=Text(name),quality_id=Number(quality),item_level=Number(level),
            required_level=Number(required),equip_location=Text(equip)} end
    end
    export.items[key] = {link = link, itemId = tonumber(key:match("^item:(%d+):")),
        capturedAt = time(), build = build, locale = locale, stats = stats, tooltip = tooltip, metadata=metadata}
    local complete = not automaticTooltip or #tooltip > 0
    seen[key] = complete or nil
    if data then tooltipAt[key] = clock end
    return complete
end

local Queue
local function RetryLater()
    if retryScheduled or not C_Timer or not C_Timer.After then return end
    for key in pairs(waiting) do
        if (attempts[key] or 0) < MAX_ATTEMPTS then
            retryScheduled = true
            C_Timer.After(1, function()
                retryScheduled = false
                for retryKey, link in pairs(waiting) do
                    if (attempts[retryKey] or 0) < MAX_ATTEMPTS then Queue(link) end
                end
            end)
            return
        end
    end
end

local function Drain()
    scheduled = false
    if InCombatLockdown and InCombatLockdown() then return end
    local processed = 0
    for key, link in pairs(pending) do
        attempts[key] = (attempts[key] or 0) + 1
        if not Capture(link) then waiting[key] = link end
        pending[key] = nil
        processed = processed + 1
        if processed == 4 then break end
    end
    if next(pending) and C_Timer and C_Timer.After then
        scheduled = true
        C_Timer.After(0.05, Drain)
    end
    RetryLater() -- bounded cache/tooltip warmup; never poll indefinitely
end

Queue = function(link)
    local key = Key(link)
    if not key or seen[key] then return end
    -- Bound transient queues as well as the persisted observations.
    local count = 0
    for _ in pairs(pending) do count = count + 1 end
    for _ in pairs(waiting) do count = count + 1 end
    if count >= MAX_ITEMS and not pending[key] and not waiting[key] then return end
    waiting[key] = nil
    pending[key] = link
    if not scheduled and C_Timer and C_Timer.After then
        scheduled = true
        C_Timer.After(0.05, Drain)
    end
end

-- Extend the data addon's own observation points; do not replace its scanners.
local originalGear = ns.ScanGear
ns.ScanGear = function(c)
    local incomplete, changed = originalGear(c)
    for _, link in pairs(c.gear or {}) do Queue(link) end
    if not incomplete and not (InCombatLockdown and InCombatLockdown()) then
        local slots = {}
        for slot = 1, 19 do slots[slot] = (c.gear or {})[slot] or false end
        c.goblinEyeGear = {capturedAt = time(), slots = slots}
    end
    return incomplete, changed
end

local originalContainers = ns.ScanContainers
ns.ScanContainers = function(bags, out, layout, links)
    originalContainers(bags, out, layout, links)
    local api = C_Container
    if not api or not api.GetContainerItemLink or not api.GetContainerNumSlots then return end
    if InCombatLockdown and InCombatLockdown() then return end
    for _, bag in ipairs(bags) do
        local size = Plain(api.GetContainerNumSlots(bag))
        if type(size) == "number" then
            for slot = 1, size do Queue(Plain(api.GetContainerItemLink(bag, slot))) end
        end
    end
end

local originalScore = ns.ItemScore
if originalScore then
    ns.ItemScore = function(link, role)
        local result = originalScore(link, role)
        Queue(link)
        return result
    end
end

local function OnItem(tip, data)
    if (tip ~= GameTooltip and tip ~= ItemRefTooltip) or tip:IsForbidden() then return end
    if InCombatLockdown and InCombatLockdown() then return end
    local _, link = tip:GetItem()
    if Key(link) then Capture(link, data) end
end
ns.On("PLAYER_LOGIN", function()
    if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall and Enum and Enum.TooltipDataType then
        TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, OnItem)
    elseif GameTooltip and GameTooltip.HookScript then
        GameTooltip:HookScript("OnTooltipSetItem", OnItem)
        if ItemRefTooltip then ItemRefTooltip:HookScript("OnTooltipSetItem", OnItem) end
    end
end)
-- Resume only deferred observation work after lockdown; no combat data is saved.
ns.On("PLAYER_REGEN_ENABLED", function()
    if ns.char then ns.ScanGear(ns.char) end
    for _, link in pairs(pending) do Queue(link) end
    for _, link in pairs(waiting) do Queue(link) end
end)
ns.On("GET_ITEM_INFO_RECEIVED", function(itemID, success)
    if success == false then return end
    for key, link in pairs(waiting) do
        if not itemID or tonumber(key:match("^item:(%d+):")) == itemID then Queue(link) end
    end
end)

-- Out-of-combat character-sheet snapshots, not combat/health/movement telemetry.
local function Talents()
    local T = C_Traits
    local kind = Enum and Enum.TraitConfigType and Enum.TraitConfigType.CamelotCombat or 4
    local configs = T and Call(T.GetConfigsByType, kind)
    if type(configs) ~= "table" or not Number(configs[1]) then return {status="not_recorded", nodes={}} end
    local config = configs[1]
    local info = Call(T.GetConfigInfo, config)
    local trees = type(info) == "table" and Plain(info.treeIDs)
    if type(trees) ~= "table" or #trees == 0 then return {status="not_recorded", nodes={}} end
    local out, complete = {}, true
    for _, tree in ipairs(trees) do
        local ids = Number(tree) and Call(T.GetTreeNodes, tree)
        if type(ids) ~= "table" then complete = false else
            for _, id in ipairs(ids) do
                local node = Number(id) and Call(T.GetNodeInfo, config, id)
                local rank = type(node) == "table" and Number(node.currentRank)
                if not rank then complete = false elseif rank > 0 then
                    if #out >= 128 then complete = false; break end
                    local active = Plain(node.activeEntry)
                    local entryID = type(active) == "table" and Number(active.entryID)
                    local entries = Plain(node.entryIDs)
                    if not entryID and type(entries) == "table" and #entries == 1 then entryID = Number(entries[1]) end
                    local entry = entryID and Call(T.GetEntryInfo, config, entryID)
                    local definitionID = type(entry) == "table" and Number(entry.definitionID)
                    local definition = definitionID and Call(T.GetDefinitionInfo, definitionID)
                    local spellID = type(definition) == "table" and Number(definition.spellID)
                    local spell = spellID and C_Spell and Call(C_Spell.GetSpellInfo, spellID)
                    out[#out+1] = {nodeID=id, treeID=tree, rank=rank, entryID=entryID,
                        spellID=spellID, name=type(spell)=="table" and Text(spell.name) or nil}
                end
            end
        end
    end
    return {status=complete and "recorded" or "partial", configID=config, nodes=out}
end
local function Character()
    if not ns.char or (InCombatLockdown and InCombatLockdown()) then return end
    local stats = {}
    stats.max_health = Number(Call(UnitHealthMax, "player"))
    stats.max_mana = Number(Call(UnitPowerMax, "player", 0))
    for i, key in ipairs({"strength", "agility", "stamina", "intellect", "spirit"}) do
        local _, effective = Call(UnitStat, "player", i)
        stats[key] = Number(effective)
    end
    local _, armor = Call(UnitArmor, "player")
    stats.armor = Number(armor)
    for school, key in ipairs({"physical", "holy", "fire", "nature", "frost", "shadow", "arcane"}) do
        if school > 1 then
            stats[key.."_damage"] = Number(Call(GetSpellBonusDamage, school))
            stats[key.."_crit_percent"] = Number(Call(GetSpellCritChance, school))
        end
    end
    stats.healing_power = Number(Call(GetSpellBonusHealing))
    stats.spell_hit_modifier_percent = Number(Call(GetSpellHitModifier))
    stats.spell_hit_rating_bonus_percent = Number(CR_HIT_SPELL and Call(GetCombatRatingBonus, CR_HIT_SPELL))
    stats.spell_penetration = Number(Call(GetSpellPenetration))
    local idle, casting = Call(GetManaRegen)
    stats.mana_regen_per_second = Number(idle)
    stats.mana_regen_casting_per_second = Number(casting)
    local buffs, auraStatus = {}, "not_recorded"
    local A = C_UnitAuras
    local restricted = C_Secrets and Call(C_Secrets.ShouldAurasBeSecret)
    if A and A.GetAuraDataByIndex and restricted ~= true then
        auraStatus = "recorded"
        for index=1,41 do
            local ok, aura = pcall(A.GetAuraDataByIndex, "player", index, "HELPFUL")
            if not ok or secret(aura) then auraStatus="partial"; break end
            if not aura then break end
            if type(aura) ~= "table" then auraStatus="partial"; break end
            if index > 40 then auraStatus="partial"; break end
            local id = Number(aura.spellId)
            if id then buffs[#buffs+1] = {spellID=id, name=Text(aura.name), applications=Number(aura.applications)}
            else auraStatus="partial" end
        end
    end
    local _, race = Call(UnitRace, "player")
    local _, build = Call(GetBuildInfo)
    ns.char.goblinEyeCharacter = {version=1, capturedAt=time(), build=Text(build),
        locale=Text(Call(GetLocale)), race=Text(race), realm=Text(Call(GetRealmName)), stats=stats,
        talents=Talents(), buffs={status=auraStatus, records=buffs}}
end
local function Quests()
    if not ns.char or (InCombatLockdown and InCombatLockdown()) then return end
    local ids = C_QuestLog and Call(C_QuestLog.GetAllCompletedQuestIDs)
    if type(ids) ~= "table" then return end
    local completed, count = {}, 0
    for _, id in ipairs(ids) do
        id = Number(id)
        if not id or id <= 0 or id % 1 ~= 0 then return end
        if not completed[id] then count=count+1; completed[id]=true end
        if count > 100000 then return end
    end
    ns.char.goblinEyeQuests = {version=1, capturedAt=time(), completed=completed}
end
local function Bool(v)
    v = Plain(v)
    if type(v) == "boolean" then return v end
end
local function Count(v, maximum)
    v = Number(v)
    if v and v >= 0 and v % 1 == 0 and v <= maximum then return v end
end
-- Read only the accepted log. Never expand headers, select quests, or infer
-- turn-in readiness from objective counts. Missing/secret APIs stay unknown.
local function ActiveQuests()
    if not ns.char or (InCombatLockdown and InCombatLockdown()) then return end
    local Q = C_QuestLog
    local entries, total = Call(Q and Q.GetNumQuestLogEntries)
    entries, total = Count(entries, 500), Count(total, 100)
    local _, build = Call(GetBuildInfo)
    local capture = {version=1, capturedAt=time(), build=Text(build), locale=Text(Call(GetLocale)),
        status="not_recorded", entries={}, reportedQuestCount=total}
    if entries and Q and type(Q.GetInfo) == "function" then
        capture.status = "recorded"
        local seen = {}
        for index=1,entries do
            local info = Call(Q.GetInfo, index)
            if type(info) ~= "table" then capture.status="partial" else
                local header = Bool(info.isHeader)
                local id = Count(info.questID, 99999999)
                if header == nil then capture.status="partial"
                elseif not header then
                    if not id or id == 0 or seen[id] or #capture.entries >= 100 then capture.status="partial" else
                        seen[id] = true
                        local row = {questID=id, title=Text(info.title), level=Count(info.level,1000),
                            readyForTurnIn=Bool(Call(Q.ReadyForTurnIn,id)),
                            complete=Bool(Call(Q.IsComplete,id)), failed=Bool(Call(Q.IsFailed,id)),
                            objectives={status="not_recorded",records={}}}
                        local objectives = Call(Q.GetQuestObjectives,id)
                        if type(objectives)=="table" then
                            row.objectives.status="recorded"
                            for i, objective in ipairs(objectives) do
                                if i>20 then row.objectives.status="partial"; break end
                                objective=Plain(objective)
                                if type(objective)~="table" then row.objectives.status="partial" else
                                    local item={index=i, text=Text(objective.text), type=Text(objective.type),
                                        numFulfilled=Count(objective.numFulfilled,100000000),
                                        numRequired=Count(objective.numRequired,100000000), finished=Bool(objective.finished)}
                                    if not item.text or item.finished==nil then row.objectives.status="partial" end
                                    row.objectives.records[#row.objectives.records+1]=item
                                end
                            end
                        end
                        if not row.title or row.readyForTurnIn==nil or row.objectives.status~="recorded" then capture.status="partial" end
                        capture.entries[#capture.entries+1]=row
                    end
                end
            end
        end
        if total == nil or total ~= #capture.entries then capture.status="partial" end
    end
    ns.char.goblinEyeQuestLog=capture
end
-- A starting-point observation on login/save only; no movement events or timer.
local function Location()
    if not ns.char or (InCombatLockdown and InCombatLockdown()) then return end
    local M = C_Map
    local map = Count(Call(M and M.GetBestMapForUnit,"player"),99999999)
    if map == 0 then map=nil end
    local position = map and Call(M and M.GetPlayerMapPosition,map,"player")
    local x,y
    if type(position)=="table" then x,y=Call(Plain(position.GetXY),position) end
    x,y=Number(x),Number(y)
    if not x or not y or x<0 or x>1 or y<0 or y>1 then x,y=nil,nil end
    local _,build=Call(GetBuildInfo)
    local zone,subzone=Text(Call(GetZoneText)),Text(Call(GetSubZoneText))
    ns.char.goblinEyeLocation={version=1,capturedAt=time(),build=Text(build),
        status=x and "recorded" or (map or zone) and "partial" or "not_recorded",
        uiMapID=map,x=x,y=y,zone=zone,subZone=subzone}
end
local sheetQueued, questsQueued = false, false
local function SheetSoon(unit)
    if unit and unit ~= "player" then return end
    if sheetQueued or not C_Timer or not C_Timer.After then return end
    sheetQueued = true
    C_Timer.After(1, function() sheetQueued=false; Character() end)
end
local function QuestsSoon()
    if questsQueued or not C_Timer or not C_Timer.After then return end
    questsQueued = true
    C_Timer.After(1, function() questsQueued=false; Quests(); ActiveQuests() end)
end
ns.On("PLAYER_ENTERING_WORLD", function() SheetSoon(); QuestsSoon(); Location() end)
-- Synchronous capture before SavedVariables flush, including /reload.
ns.On("PLAYER_LOGOUT", function() Quests(); ActiveQuests(); Location() end)
ns.On("PLAYER_EQUIPMENT_CHANGED", function() SheetSoon() end)
ns.On("PLAYER_LEVEL_UP", function() SheetSoon() end)
ns.On("TRAIT_CONFIG_UPDATED", function() SheetSoon() end)
ns.On("UNIT_STATS", SheetSoon)
ns.On("UNIT_AURA", SheetSoon)
ns.On("SPELL_POWER_CHANGED", function() SheetSoon() end)
ns.On("QUEST_TURNED_IN", QuestsSoon)
ns.On("QUEST_ACCEPTED", QuestsSoon)
ns.On("QUEST_REMOVED", QuestsSoon)
ns.On("QUEST_LOG_UPDATE", QuestsSoon)
ns.On("PLAYER_REGEN_ENABLED", function() SheetSoon(); QuestsSoon() end)

-- Per-chat controls. Catalog data is text only, never executable Lua or commands.
local AI = WoWAI
if AI.ChatSettingsLoaded then return end
AI.ChatSettingsLoaded = true
local window
local BG = {bgFile="Interface\\Tooltips\\UI-Tooltip-Background",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=true,tileSize=16,edgeSize=12,insets={left=4,right=4,top=4,bottom=4}}
local function Safe(s) return (tostring(s or ""):gsub("|", "¦")) end
local function Button(parent,label,x,y,w,fn)
 local b=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate");b:SetSize(w,22);b:SetPoint("TOPLEFT",x,-y);b:SetText(label);b:SetScript("OnClick",fn);return b
end
local function Text(parent,x,y,w,font)
 local t=parent:CreateFontString(nil,"OVERLAY",font or "GameFontHighlightSmall");t:SetPoint("TOPLEFT",x,-y);t:SetWidth(w);t:SetJustifyH("LEFT");t:SetWordWrap(true);return t
end
local function Request(page,refresh)
 if not window then return end
 local c=AI.ChatSettingsContext(window.chat);if not c then return end
 window.waitFor=AI.RequestModels(c.id,window.search:GetText(),page or 1,refresh,window.free)
 AI.RefreshChatSettings()
end
function AI.RefreshChatSettings()
 local f=window;if not f or not f:IsShown() then return end
 local c,s,v,agents,agent=AI.ChatSettingsContext(f.chat)
 if not c then f:Hide();return end
 local loading=f.waitFor and (not v or (v.request_id or 0)<f.waitFor or v.status=="loading")
 f.title:SetText(Safe("Settings - " .. c.name))
 f.current:SetText(Safe("Next message: " .. agent .. " | " .. ((c.model or "")~="" and c.model or "configured default")))
 f.defaults:SetText(Safe("Configured model: " .. (v and v.default_model~="" and v.default_model or "agent default") .. " | permissions: " .. (v and v.permission or "waiting for bridge")))
 for i,b in ipairs(f.agents) do
  local id=agents[i];b:SetShown(id~=nil);b.agent=id;b:SetText(Safe(id or ""));b:SetEnabled(id~=agent)
 end
 f.freeButton:SetEnabled(agent=="kilo");f.freeButton:SetText(f.free and "Free only: ON" or "Free only: OFF")
 f.status:SetText(Safe(loading and "Fetching models from the agent CLI..." or (v and v.status=="ready" and (v.total .. " matches / " .. v.catalog_total .. " models. Refreshed " .. date("%H:%M:%S",v.fetched_at) .. ".") or (v and v.error or "Connect the bridge to fetch its current model list."))))
 local ready=v and v.status=="ready" and not loading
 for i,b in ipairs(f.rows) do
  local m=ready and v.items[i] or nil;b.model=m;b:SetShown(m~=nil)
  if m then
   local pricing=m.free and "FREE" or (m.priced and string.format("$%.4g / $%.4g per 1M input/output tokens",m.input,m.output) or "Price not reported")
   b:SetText(Safe((c.model==m.id and "> " or "") .. m.name .. "\n" .. m.id .. "  |  " .. pricing))
  end
 end
 f.previous:SetEnabled(ready and v.page>1 or false);f.next:SetEnabled(ready and v.page<v.pages or false)
 f.page:SetText(ready and ("Page " .. v.page .. " / " .. v.pages) or "")
 local selected
 if f.selected and f.selected.id==c.model then selected=f.selected end
 if not selected and v then selected=v.selected end
 if not selected and ready then for _,m in ipairs(v.items) do if m.id==(c.model or v.default_model) then selected=m end end end
 local choices=selected and (agent=="kilo" and selected.variants or selected.efforts) or {}
 local key=agent=="kilo" and "variant" or "effort"
 f.reason:SetText(Safe((agent=="kilo" and "Reasoning variant: " or "Reasoning effort: ") .. (c[key] or "configured default")))
 for i,b in ipairs(f.reasonButtons) do
  local value=i==1 and "" or choices[i-1];b:SetShown(value~=nil);b.value=value;b.key=key
  b:SetText(Safe(value=="" and "Default" or value));b:SetEnabled((c[key] or "")~=value)
 end
 f.restrict:SetEnabled(v and v.can_restrict or false)
 f.restrict:SetText(c.restrict and "Research mode: ON" or "Use configured permissions")
 f.context:SetText(s.context and "Character context: ON" or "Character context: OFF")
 f.echo:SetText("Chat echo: " .. tostring(s.echo));f.font:SetText("Text size: " .. tostring(s.fontSize))
end
function AI.ShowChatSettings(id)
 local c=AI.ChatSettingsContext(id);if not c then return end
 if not window then
  local f=CreateFrame("Frame","WoWAIChatSettings",UIParent,"BackdropTemplate");f:SetSize(660,700);f:SetPoint("CENTER");f:SetFrameStrata("FULLSCREEN_DIALOG");f:SetClampedToScreen(true)
  f:SetBackdrop(BG);f:SetBackdropColor(0.025,0.035,0.04,0.98);f:EnableMouse(true);f:SetMovable(true);f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart",function(self)self:StartMoving()end);f:SetScript("OnDragStop",function(self)self:StopMovingOrSizing()end)
  tinsert(UISpecialFrames,"WoWAIChatSettings")
  local close=CreateFrame("Button",nil,f,"UIPanelCloseButton");close:SetPoint("TOPRIGHT",-3,-3)
  f.title=Text(f,16,14,600,"GameFontNormalLarge")
  f.current=Text(f,16,44,628);f.defaults=Text(f,16,62,628)
  f.agents={}
  for i=1,6 do f.agents[i]=Button(f,"",16+(i-1)*105,89,99,function(b)
   local chat=AI.ChatSettingsContext(f.chat);if chat then AI.SetAgent(b.agent,chat);f.selected=nil;f.free=false;f.search:SetText("");Request(1) end
  end) end
  f.search=CreateFrame("EditBox",nil,f,"InputBoxTemplate");f.search:SetSize(272,22);f.search:SetPoint("TOPLEFT",24,-120);f.search:SetAutoFocus(false);f.search:SetMaxLetters(100)
  f.search:SetScript("OnEnterPressed",function(self)self:ClearFocus();Request(1)end);f.search:SetScript("OnEscapePressed",function(self)self:ClearFocus()end)
  Button(f,"Search",305,120,72,function()f.search:ClearFocus();Request(1)end)
  Button(f,"Refresh list",382,120,108,function()Request(1,true)end)
  f.freeButton=Button(f,"Free only: OFF",496,120,147,function()f.free=not f.free;Request(1)end)
  f.status=Text(f,16,151,625)
  f.rows={}
  for i=1,10 do
   local b=Button(f,"",16,177+(i-1)*31,627,function(self)
    local chat=AI.ChatSettingsContext(f.chat);if not chat or not self.model then return end
    chat.model=self.model.id;chat.variant,chat.effort=nil,nil;f.selected=self.model;AI.RefreshChatSettings()
   end);b:SetHeight(29);b:GetFontString():SetFontObject("GameFontHighlightSmall");b:GetFontString():SetJustifyH("LEFT");f.rows[i]=b
   b:SetScript("OnEnter",function(self)if self.model then GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText(Safe(self.model.name));GameTooltip:AddLine(Safe(self.model.description),0.8,0.8,0.8,true);GameTooltip:AddLine("Catalog availability does not guarantee account access or remaining quota.",0.8,0.8,0.8,true);GameTooltip:Show()end end)
   b:SetScript("OnLeave",function()GameTooltip:Hide()end)
  end
  f.previous=Button(f,"Previous",16,495,87,function()local _,_,v=AI.ChatSettingsContext(f.chat);Request((v and v.page or 1)-1)end)
  f.next=Button(f,"Next",110,495,87,function()local _,_,v=AI.ChatSettingsContext(f.chat);Request((v and v.page or 1)+1)end)
  f.page=Text(f,210,500,170)
  Button(f,"Default model",382,495,126,function()local chat=AI.ChatSettingsContext(f.chat);if chat then chat.model,chat.variant,chat.effort=nil,nil,nil;f.selected=nil;Request(1)end end)
  Button(f,"Default agent",515,495,128,function()local chat=AI.ChatSettingsContext(f.chat);if chat then AI.SetAgent("default",chat);f.selected=nil;f.free=false;Request(1)end end)
  f.reason=Text(f,16,527,620)
  f.reasonButtons={}
  for i=1,8 do f.reasonButtons[i]=Button(f,"",16+(i-1)*79,546,73,function(b)local chat=AI.ChatSettingsContext(f.chat);if chat then chat[b.key]=b.value~="" and b.value or nil;AI.RefreshChatSettings()end end)end
  f.restrict=Button(f,"",16,578,241,function()local chat=AI.ChatSettingsContext(f.chat);if chat then chat.restrict=not chat.restrict;AI.RefreshChatSettings()end end)
  f.context=Button(f,"",264,578,220,function()local _,s=AI.ChatSettingsContext(f.chat);s.context=not s.context;AI.RefreshChatSettings()end)
  Button(f,"Voice settings",491,578,152,function()AI.ShowVoiceSettings()end)
  f.echo=Button(f,"",16,608,190,function()local _,s=AI.ChatSettingsContext(f.chat);local order={summary="full",full="off",off="summary"};s.echo=order[s.echo] or "summary";AI.RefreshChatSettings()end)
  Button(f,"A-",215,608,45,function()local _,s=AI.ChatSettingsContext(f.chat);s.fontSize=math.max(11,s.fontSize-1);AI.Render();AI.RefreshChatSettings()end)
  Button(f,"A+",266,608,45,function()local _,s=AI.ChatSettingsContext(f.chat);s.fontSize=math.min(22,s.fontSize+1);AI.Render();AI.RefreshChatSettings()end)
  f.font=Text(f,320,614,140)
  Text(f,16,643,625):SetText("Model and reasoning choices apply to this chat's next message. Changing them starts a fresh agent session; visible history stays. Character context, echo, text size and voice settings apply across chats. Research mode only tightens configured permissions.")
  window=f
 end
 window.chat=c.id;window.selected=nil;window.free=false;window.search:SetText("");window:Show();Request(1)
end

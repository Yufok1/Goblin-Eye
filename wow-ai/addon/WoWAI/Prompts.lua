-- Local prompt browser. Browsing and drafting never send transport requests.
local AI=WoWAI
if AI.PromptLibraryLoaded then return end
AI.PromptLibraryLoaded=true
local window
local BG={bgFile="Interface\\Tooltips\\UI-Tooltip-Background",edgeFile="Interface\\Tooltips\\UI-Tooltip-Border",tile=true,tileSize=16,edgeSize=12,insets={left=4,right=4,top=4,bottom=4}}
local function Text(parent,x,y,w,font)
 local t=parent:CreateFontString(nil,"OVERLAY",font or "GameFontHighlightSmall")
 t:SetPoint("TOPLEFT",x,-y);t:SetWidth(w);t:SetJustifyH("LEFT");t:SetWordWrap(true);return t
end
local function Button(parent,label,x,y,w,fn)
 local b=CreateFrame("Button",nil,parent,"UIPanelButtonTemplate");b:SetSize(w,24);b:SetPoint("TOPLEFT",x,-y);b:SetText(label);b:SetScript("OnClick",fn)
 if AI.SkinButton then AI.SkinButton(b) end;return b
end
function AI.FilterPrompts(query,category)
 local result={};query=string.lower(query or "")
 for _,p in ipairs(AI.PromptLibrary or {}) do
  if (not category or p.category==category) and (query=="" or string.find(string.lower(p.title.." "..p.summary.." "..p.text),query,1,true)) then result[#result+1]=p end
 end
 return result
end
local function Select(p)
 local f=window;f.selected=p
 f.previewTitle:SetText(p and p.title or "Choose a prompt")
 f.body:SetText(p and p.text or "Select a title on the left to read the complete prompt here.")
 f.content:SetHeight(math.max(1,f.body:GetStringHeight()+16));f.scroll:SetVerticalScroll(0)
 f.use:SetEnabled(p~=nil)
 f.hint:SetText(p and "Ready to send as-is. Uses your conversation and saved context." or "Browse locally. Nothing is sent until you click Send in chat.")
end
local function Refresh()
 local f=window;local matches=AI.FilterPrompts(f.search:GetText(),f.category)
 local pages=math.max(1,math.ceil(#matches/6));f.page=math.max(1,math.min(f.page or 1,pages))
 for i,b in ipairs(f.rows) do
  local p=matches[(f.page-1)*6+i];b.prompt=p;b:SetShown(p~=nil)
  if p then b.label:SetText(p.title);b.summary:SetText(p.summary) end
 end
 f.count:SetText(#matches.." prompts - page "..f.page.." / "..pages)
 for _,b in ipairs(f.categories) do b:SetEnabled(b.category~=f.category) end
 f.previous:SetEnabled(f.page>1);f.next:SetEnabled(f.page<pages)
 local found=false;for _,p in ipairs(matches) do if p==f.selected then found=true end end
 if not found then Select(nil) end
end
function AI.ShowPromptLibrary()
 if not window then
  local f=CreateFrame("Frame","WoWAIPromptLibrary",UIParent,"BackdropTemplate");window=f
  f:SetSize(760,606);f:SetPoint("TOPLEFT",WoWAIFrame,"TOPRIGHT",8,0);f:SetClampedToScreen(true);f:SetFrameStrata("FULLSCREEN_DIALOG")
  if UIParent:GetWidth()<780 or UIParent:GetHeight()<626 then f:SetScale(math.min(1,UIParent:GetWidth()/780,UIParent:GetHeight()/626)) end
  f:SetBackdrop(BG);f:SetBackdropColor(0.035,0.025,0.05,0.99);f:EnableMouse(true);f:SetMovable(true);f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart",function(self)self:StartMoving()end);f:SetScript("OnDragStop",function(self)self:StopMovingOrSizing()end)
  tinsert(UISpecialFrames,"WoWAIPromptLibrary")
  local close=CreateFrame("Button",nil,f,"UIPanelCloseButton");close:SetPoint("TOPRIGHT",-3,-3);close:SetScript("OnClick",function()f:Hide()end)
  Text(f,16,14,680,"GameFontNormalLarge"):SetText("Goblin Eye - Prompt library")
  Text(f,16,43,720):SetText("Choose a research idea, read it, then add it to your current chat draft. Drag this window to reposition.")
  f.search=CreateFrame("EditBox","WoWAIPromptSearch",f,"InputBoxTemplate");f.search:SetSize(242,24);f.search:SetPoint("TOPLEFT",24,-70);f.search:SetAutoFocus(false);f.search:SetMaxLetters(100)
  f.search:SetScript("OnTextChanged",function()f.page=1;Refresh()end)
  f.search:SetScript("OnEscapePressed",function(self)self:ClearFocus()end)
  f.search:SetScript("OnEnterPressed",function(self)self:ClearFocus()end)
  Text(f,282,76,420):SetText("Search titles, summaries and full prompt contents")
  f.categories={}
  local labels={"All"};for _,name in ipairs(AI.PromptCategories) do labels[#labels+1]=name end
  for i,name in ipairs(labels) do
   local b=Button(f,name,16+(i-1)*104,103,100,function(self)f.category=self.category;f.page=1;Refresh()end)
   b.category=i>1 and name or nil;f.categories[i]=b
  end
  f.rows={}
  for i=1,6 do
   local b=Button(f,"",16,144+(i-1)*61,250,function(self)Select(self.prompt)end);b:SetHeight(57)
   b.label=Text(b,8,6,234,"GameFontNormalSmall");b.summary=Text(b,8,25,234);f.rows[i]=b
  end
  f.previous=Button(f,"Previous",16,517,118,function()f.page=f.page-1;Refresh()end)
  f.next=Button(f,"Next",144,517,122,function()f.page=f.page+1;Refresh()end)
  f.count=Text(f,16,556,250)
  f.previewTitle=Text(f,284,145,440,"GameFontNormalLarge")
  f.scroll=CreateFrame("ScrollFrame",nil,f,"UIPanelScrollFrameTemplate");f.scroll:SetPoint("TOPLEFT",284,-181);f.scroll:SetSize(430,322)
  f.content=CreateFrame("Frame",nil,f.scroll);f.content:SetSize(430,1);f.scroll:SetScrollChild(f.content)
  f.body=Text(f.content,0,0,422);f.body:SetFontObject("GameFontHighlightSmall")
  f.use=Button(f,"Add to chat draft",284,517,190,function()
   if f.selected then AI.InsertPromptDraft(f.selected.text);f:Hide() end
  end)
  f.hint=Text(f,284,554,440)
  f:SetScript("OnHide",function()f.search:ClearFocus()end)
  Select(nil)
 end
 window:Show();Refresh()
end

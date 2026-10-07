-- Original Goblin Eye / warlock presentation. No transport or gameplay hooks.
local AI = WoWAI
local unpack = unpack or table.unpack
if AI.GoblinThemeLoaded then return end
AI.GoblinThemeLoaded = true
local EYE = "Interface\\AddOns\\WoWAI\\Media\\GoblinEye.tga"
local BG = { bgFile="Interface\\Buttons\\WHITE8X8", edgeFile="Interface\\Tooltips\\UI-Tooltip-Border", tile=true, tileSize=16, edgeSize=12, insets={left=3,right=3,top=3,bottom=3} }
local currentUI
local tones = {
 neutral={bg={0.09,0.065,0.13,0.98},edge={0.43,0.30,0.57,1},text={0.88,0.83,0.95}},
 fel={bg={0.10,0.20,0.09,1},edge={0.48,0.69,0.24,1},text={0.79,1,0.49}},
 danger={bg={0.19,0.07,0.105,1},edge={0.55,0.25,0.32,1},text={0.97,0.65,0.68}},
}
local function PaintButton(button,hover)
 local style=tones[button.goblinTone] or tones.neutral
 button.goblinSkin:SetBackdropColor(unpack(style.bg))
 local edge=hover and {0.72,0.86,0.48,1} or style.edge
 button.goblinSkin:SetBackdropBorderColor(unpack(edge))
 local label=button:GetFontString()
 if label then
  if button:IsEnabled() then label:SetTextColor(unpack(style.text)) else label:SetTextColor(0.46,0.43,0.5) end
 end
end
function AI.SkinButton(button,tone)
 if not button then return end
 button.goblinTone=tone or button.goblinTone or "neutral"
 if not button.goblinSkin then
  -- Template chrome is replaced visually; native click/disabled behavior stays.
  for _,key in ipairs({"Left","Middle","Right"}) do
   local region=button[key]
   if (type(region)=="table" or type(region)=="userdata") and region.Hide then region:Hide() end
  end
  button:SetNormalTexture("");button:SetPushedTexture("");button:SetDisabledTexture("");button:SetHighlightTexture("")
  local skin=CreateFrame("Frame",nil,button,"BackdropTemplate")
  skin:SetAllPoints();skin:SetBackdrop(BG);skin:EnableMouse(false)
  skin:SetFrameLevel(math.max(0,(button:GetFrameLevel() or 2)-1))
  button.goblinSkin=skin
  button:HookScript("OnEnter",function(self) PaintButton(self,true) end)
  button:HookScript("OnLeave",function(self) PaintButton(self,false) end)
  button:SetNormalFontObject(GameFontHighlightSmall);button:SetHighlightFontObject(GameFontHighlightSmall)
  button:SetDisabledFontObject(GameFontDisableSmall)
 end
 PaintButton(button,false)
end
local function Texture(parent,layer,path,w,h,point,relative,relativePoint,x,y,alpha)
 local texture=parent:CreateTexture(nil,layer)
 if texture:SetTexture(path)==false then texture:SetTexture("Interface\\Icons\\Spell_Shadow_EyeOfKilrogg") end
 texture:SetSize(w,h);texture:SetPoint(point,relative,relativePoint,x,y)
 if alpha then texture:SetAlpha(alpha) end
 return texture
end
local function Line(parent,point,x,y,width,height,r,g,b,a)
 local texture=parent:CreateTexture(nil,"BORDER")
 texture:SetPoint(point,parent,point,x,y);texture:SetSize(width,height);texture:SetColorTexture(r,g,b,a or 1)
 return texture
end
local function Pulse(texture)
 local ok,group=pcall(function()
  local g=texture:CreateAnimationGroup()
  local rise=g:CreateAnimation("Alpha");rise:SetFromAlpha(0.14);rise:SetToAlpha(0.48);rise:SetDuration(1.1);rise:SetOrder(1)
  local fall=g:CreateAnimation("Alpha");fall:SetFromAlpha(0.48);fall:SetToAlpha(0.14);fall:SetDuration(1.1);fall:SetOrder(2)
  g:SetLooping("REPEAT");return g
 end)
 return ok and group or nil
end
local function Counts()
 local unread,working=0,0
 for _,chat in ipairs((WoWAIDB and WoWAIDB.chats) or {}) do
  unread=unread+(chat.unread or 0);if chat.pendingId then working=working+1 end
 end
 return unread,working
end
local function UpdateEye()
 if not currentUI then return end
 local ui=currentUI;local unread,working=Counts()
 ui.miniBadge:SetText(unread>0 and tostring(unread) or (working>0 and "..." or ""))
 ui.miniBadge:SetTextColor(unread>0 and 0.82 or 0.85,unread>0 and 1 or 0.7,unread>0 and 0.48 or 1)
 ui.eyeBadge:SetShown(unread>0 or working>0)
 if ui.eyePulse then
  if ui.mini:IsShown() and (unread>0 or working>0) then
   if not ui.eyePulse:IsPlaying() then ui.eyePulse:Play() end
  else ui.eyePulse:Stop();ui.eyeGlow:SetAlpha(0.14) end
 end
end
function AI.ThemeBubble(bubble)
 if bubble.goblinStyled then return end
 bubble.goblinStyled=true
 local top=Line(bubble,"TOPLEFT",4,0,20,1,0.52,0.37,0.65,0.8)
 top:SetPoint("TOPRIGHT",bubble,"TOPRIGHT",-4,0)
 bubble.who:SetShadowOffset(1,-1);bubble.body:SetShadowOffset(1,-1)
 AI.SkinButton(bubble.allow)
end
function AI.ThemeEvidence(frame,amber)
 frame:SetBackdropColor(0.055,0.043,0.083,0.98)
 frame:SetBackdropBorderColor(amber and 0.72 or 0.38,amber and 0.54 or 0.56,amber and 0.25 or 0.29,1)
 frame.title:SetTextColor(0.79,0.97,0.51)
end
function AI.ApplyGoblinTheme(frame,ui)
 currentUI=ui
 frame:SetBackdropColor(0.025,0.021,0.038,0.985);frame:SetBackdropBorderColor(0.43,0.32,0.49,1)
 local header=frame:CreateTexture(nil,"BACKGROUND");header:SetPoint("TOPLEFT",7,-7);header:SetPoint("TOPRIGHT",-7,-7);header:SetHeight(48);header:SetColorTexture(0.08,0.055,0.11,0.95)
 local rule=Line(frame,"TOPLEFT",14,-56,20,1,0.38,0.52,0.24,0.9);rule:SetPoint("TOPRIGHT",frame,"TOPRIGHT",-14,-56)
 Texture(frame,"ARTWORK",EYE,54,54,"TOPLEFT",frame,"TOPLEFT",13,-4)
 local brand=frame:CreateFontString(nil,"OVERLAY","GameFontNormalLarge")
 brand:SetPoint("TOPLEFT",frame,"TOPLEFT",76,-13);brand:SetText("GOBLIN EYE");brand:SetTextColor(0.78,0.97,0.45);brand:SetShadowOffset(1,-1)
 ui.brand=brand
 ui.title:ClearAllPoints();ui.title:SetPoint("LEFT",brand,"RIGHT",14,0);ui.title:SetPoint("RIGHT",frame,"RIGHT",-160,0)
 ui.title:SetJustifyH("LEFT");ui.title:SetWordWrap(false);ui.title:SetFontObject(GameFontHighlightSmall);ui.title:SetTextColor(0.76,0.69,0.87)
 ui.status:ClearAllPoints();ui.status:SetPoint("TOPLEFT",frame,"TOPLEFT",76,-35);ui.status:SetPoint("RIGHT",frame,"RIGHT",-42,0)
 ui.status:SetTextColor(0.76,0.8,0.71)
 local dot=ui.dot:GetParent();dot:ClearAllPoints();dot:SetSize(12,12);dot:SetPoint("TOPRIGHT",frame,"TOPRIGHT",-44,-17)
 ui.panel:ClearAllPoints();ui.panel:SetPoint("TOPLEFT",frame,"TOPLEFT",14,-64);ui.panel:SetPoint("BOTTOMLEFT",frame,"BOTTOMLEFT",14,50)
 ui.panel:SetBackdropColor(0.055,0.037,0.078,0.97);ui.panel:SetBackdropBorderColor(0.36,0.26,0.45,1)
 Texture(ui.panel,"BACKGROUND",EYE,142,142,"BOTTOM",ui.panel,"BOTTOM",0,8,0.045)
 for _,button in ipairs(ui.chatButtons) do button.selected:SetColorTexture(0.31,0.51,0.17,0.38) end
 ui.inputBg:SetBackdropColor(0.04,0.055,0.034,0.98);ui.inputBg:SetBackdropBorderColor(0.39,0.53,0.27,1)
 ui.input:SetTextColor(0.91,0.95,0.87)
 ui.input:HookScript("OnEditFocusGained",function() ui.inputBg:SetBackdropBorderColor(0.72,0.9,0.36,1) end)
 ui.input:HookScript("OnEditFocusLost",function() ui.inputBg:SetBackdropBorderColor(0.39,0.53,0.27,1) end)
 AI.SkinButton(ui.send,"fel");AI.SkinButton(ui.connect,"fel");AI.SkinButton(ui.stop,"danger")
 ui.cwd:SetTextColor(0.58,0.54,0.65)
 -- Compact, draggable eye instead of the old 250-pixel bar. Existing drag,
 -- click-to-open, saved position and Quit handlers remain in control.
 local mini=ui.mini;mini:SetSize(76,76);mini:SetBackdropColor(0,0,0,0);mini:SetBackdropBorderColor(0,0,0,0)
 ui.eyeGlow=Texture(mini,"BACKGROUND",EYE,74,74,"CENTER",mini,"CENTER",0,0,0.14);ui.eyeGlow:SetBlendMode("ADD")
 ui.eyeIcon=Texture(mini,"ARTWORK",EYE,66,66,"CENTER",mini,"CENTER",0,0)
 ui.miniLabel:Hide()
 local miniDot=ui.miniDot:GetParent();miniDot:ClearAllPoints();miniDot:SetSize(12,12);miniDot:SetPoint("BOTTOMRIGHT",mini,"BOTTOMRIGHT",-8,7)
 local badge=CreateFrame("Frame",nil,mini,"BackdropTemplate");badge:SetSize(24,20);badge:SetPoint("TOPLEFT",mini,"TOPLEFT",0,-4)
 badge:SetBackdrop(BG);badge:SetBackdropColor(0.06,0.08,0.025,0.96);badge:SetBackdropBorderColor(0.55,0.7,0.29,1)
 ui.eyeBadge=badge
 ui.miniBadge:SetParent(badge);ui.miniBadge:ClearAllPoints();ui.miniBadge:SetPoint("CENTER",badge,"CENTER",0,0);ui.miniBadge:SetWidth(20);ui.miniBadge:SetJustifyH("CENTER")
 ui.miniClose:ClearAllPoints();ui.miniClose:SetPoint("TOPRIGHT",mini,"TOPRIGHT",2,2);ui.miniClose:SetSize(20,20);ui.miniClose:SetAlpha(0.4)
 ui.miniClose:HookScript("OnEnter",function(self) self:SetAlpha(1) end);ui.miniClose:HookScript("OnLeave",function(self) self:SetAlpha(0.4) end)
 ui.eyePulse=Pulse(ui.eyeGlow)
 mini:HookScript("OnShow",UpdateEye);mini:HookScript("OnHide",UpdateEye)
 mini:HookScript("OnEnter",function(self)
  local unread,working=Counts()
  GameTooltip:SetOwner(self,"ANCHOR_RIGHT");GameTooltip:SetText("Goblin Eye")
  GameTooltip:AddLine("Click to open your grimoire. Drag to move the eye.",0.79,0.95,0.54,true)
  if working>0 then GameTooltip:AddLine(working.." chat(s) working",0.84,0.71,1) end
  if unread>0 then GameTooltip:AddLine(unread.." unread replies",0.79,1,0.45) end
  GameTooltip:Show()
 end)
 mini:HookScript("OnLeave",function() GameTooltip:Hide() end)
 UpdateEye()
end
local updateMini=AI.UpdateMini
AI.UpdateMini=function(...) updateMini(...);UpdateEye() end

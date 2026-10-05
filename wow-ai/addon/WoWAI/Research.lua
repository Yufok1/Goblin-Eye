-- Optional Goblin Eye research UI. All external resources are copyable links;
-- tool data is displayed as text, never evaluated as Lua or game commands.
local AI = WoWAI
if AI.GoblinResearchLoaded then return end
AI.GoblinResearchLoaded = true
local BG = { bgFile = "Interface\\ChatFrame\\ChatFrameBackground", edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border", tile = true, tileSize = 16, edgeSize = 12, insets = { left = 3, right = 3, top = 3, bottom = 3 } }
local viewer
local function Safe(s) return (tostring(s or ""):gsub("|", "¦")) end
function AI.ResearchBody(text)
 local safe = Safe(text)
 safe = safe:gsub("%*%*(.-)%*%*", "|cffffd778%1|r")
 safe = safe:gsub("^#+%s*([^\n]+)", "|cffffd778%1|r")
 safe = safe:gsub("\n#+%s*([^\n]+)", "\n|cffffd778%1|r")
 return safe
end
local function Button(parent, text, w, fn)
 local b = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
 b:SetSize(w, 22); b:SetText(text); b:SetScript("OnClick", fn)
 return b
end
local voiceWindow
function AI.RefreshVoiceSettings()
 if not voiceWindow then return end
 local s = AI.SpeechInfo()
 voiceWindow.slower:SetEnabled(true); voiceWindow.faster:SetEnabled(true)
 voiceWindow.playSummary:SetEnabled(not s.busy);voiceWindow.playFull:SetEnabled(not s.busy);voiceWindow.testVoice:SetEnabled(not s.busy)
 local voice = (s.voice or "") ~= "" and s.voice or "Windows default"
 voiceWindow.status:SetText(Safe("Automatic replies: " .. (s.enabled and "ON" or "OFF") .. " | " .. (s.mode or "summary") .. "\nVolume: " .. (s.volume or 70) .. " | " .. (s.phase or "Idle") .. "\nVoice: " .. voice .. "\n" .. (s.error or "")))
end
function AI.ShowVoiceSettings()
 if not voiceWindow then
  local f = CreateFrame("Frame", "WoWAIVoiceSettings", UIParent, "BackdropTemplate")
  f:SetSize(440, 340); f:SetPoint("CENTER"); f:SetFrameStrata("FULLSCREEN_DIALOG"); f:SetClampedToScreen(true)
  f:SetBackdrop(BG); f:SetBackdropColor(0.035, 0.05, 0.06, 0.98); f:EnableMouse(true)
  tinsert(UISpecialFrames, "WoWAIVoiceSettings")
  local x = CreateFrame("Button", nil, f, "UIPanelCloseButton"); x:SetPoint("TOPRIGHT", -3, -3)
  local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge"); title:SetPoint("TOPLEFT", 16, -14); title:SetText("Goblin Eye - local voice")
  f.status = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.status:SetPoint("TOPLEFT", 16, -44); f.status:SetWidth(402); f.status:SetJustifyH("LEFT"); f.status:SetWordWrap(true)
  local function Control(label, op, value, xPos, yPos)
   local b = Button(f, label, 94, function() AI.Voice(op, type(value) == "function" and value() or value) end)
   b:SetPoint("TOPLEFT", xPos, -yPos); return b
  end
  Control("Auto on", "on", "", 16, 135); Control("Auto off", "off", "", 120, 135)
  Control("Summary", "summary", "", 224, 135); Control("Full replies", "full", "", 328, 135)
  Control("Volume -", "volume", function() return math.max(0, (AI.SpeechInfo().volume or 70) - 10) end, 16, 164)
  Control("Volume +", "volume", function() return math.min(100, (AI.SpeechInfo().volume or 70) + 10) end, 120, 164)
  f.slower = Control("Slower", "rate", function() return math.max(-10, (AI.SpeechInfo().rate or 0) - 1) end, 224, 164)
  f.faster = Control("Faster", "rate", function() return math.min(10, (AI.SpeechInfo().rate or 0) + 1) end, 328, 164)
  f.playSummary=Control("Play TL;DR", "listen", "", 16, 193); f.playFull=Control("Play full", "listenfull", "", 120, 193)
  Control("Stop voice", "stop", "", 224, 193); Control("Refresh", "status", "", 328, 193)
  f.testVoice=Control("Test voice", "preview", "", 16, 222)
  local note = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); note:SetPoint("TOPLEFT", 16, -253); note:SetWidth(402); note:SetJustifyH("LEFT")
  note:SetText("Windows speech reads replies locally.\nPlay chooses a saved summary or full reply; Stop cancels playback.\nChoose another installed voice with /wow-ai voice name <name>.")
  voiceWindow = f
 end
 AI.RefreshVoiceSettings(); voiceWindow:Show()
end
-- Byte boundaries must not split a UTF-8 character in the game's strings.
function AI.ResearchPages(text, size)
 text, size = tostring(text or ""), math.max(4, size or 3500)
 local pages, from = {}, 1
 while from <= #text do
  local last = math.min(#text, from + size - 1)
  if last < #text then
   while last >= from and text:byte(last + 1) >= 128 and text:byte(last + 1) < 192 do last = last - 1 end
   local chunk = text:sub(from, last)
   local newline = chunk:match(".*()\n")
   if newline and newline > size / 2 then last = from + newline - 1 end
  end
  pages[#pages + 1] = text:sub(from, last); from = last + 1
 end
 if #pages == 0 then pages[1] = "" end
 return pages
end
function AI.ResearchPreview(text, size)
 local pages = AI.ResearchPages(text, size)
 return pages[1], #pages > 1
end
-- Plain text search: returned positions correspond to the original UTF-8 bytes.
function AI.ResearchFindPage(pages, query, after)
 query = tostring(query or ""):lower()
 if query == "" then return nil end
 local text = table.concat(pages)
 local position = text:lower():find(query, (after or 0) + 1, true)
 if not position and (after or 0) > 0 then position = text:lower():find(query, 1, true) end
 if not position then return nil end
 local offset = 0
 for i, page in ipairs(pages) do
  if position <= offset + #page then return i, position end
  offset = offset + #page
 end
end
function AI.ResearchURLs(text)
 local out, seen = {}, {}
 for url in tostring(text or ""):gmatch("https?://[^%s<>\"|]+") do
  url = url:gsub("[%)%],.;]+$", "")
  local host = url:match("^https?://([^/]+)")
  if host and not host:find("@", 1, true) and (url:match("^https://") or host == "127.0.0.1:8765" or host == "localhost:8765") and not seen[url] then
   out[#out + 1] = { label = host, url = url }; seen[url] = true
  end
  if #out >= 12 then break end
 end
 return out
end
function AI.ResearchFont(fs)
 local font, _, flags = ChatFontNormal:GetFont()
 if font then fs:SetFont(font, (WoWAIDB and WoWAIDB.settings.fontSize) or 14, flags or "") end
end
function AI.ShowResearchDocument(title, text)
 if not viewer then
  local f = CreateFrame("Frame", "WoWAIResearchReader", UIParent, "BackdropTemplate")
  f:SetSize(660, 490); f:SetPoint("CENTER"); f:SetFrameStrata("FULLSCREEN_DIALOG")
  f:SetClampedToScreen(true); f:SetMovable(true); f:EnableMouse(true); f:RegisterForDrag("LeftButton")
  f:SetScript("OnDragStart", f.StartMoving); f:SetScript("OnDragStop", f.StopMovingOrSizing)
  f:SetBackdrop(BG); f:SetBackdropColor(0.035, 0.05, 0.06, 0.98); f:SetBackdropBorderColor(0.5, 0.7, 0.4, 1)
  tinsert(UISpecialFrames, "WoWAIResearchReader")
  local x = CreateFrame("Button", nil, f, "UIPanelCloseButton"); x:SetPoint("TOPRIGHT", -3, -3)
  f.title = f:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge"); f.title:SetPoint("TOPLEFT", 16, -14); f.title:SetWidth(595); f.title:SetJustifyH("LEFT")
  local scroll = CreateFrame("ScrollFrame", nil, f, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 16, -76); scroll:SetPoint("BOTTOMRIGHT", -34, 48)
  local content = CreateFrame("Frame", nil, scroll); content:SetSize(606, 1); scroll:SetScrollChild(content)
  f.body = content:CreateFontString(nil, "OVERLAY", "ChatFontNormal")
  f.body:SetPoint("TOPLEFT"); f.body:SetWidth(606); f.body:SetJustifyH("LEFT"); f.body:SetJustifyV("TOP"); f.body:SetWordWrap(true); f.body:SetNonSpaceWrap(true)
  f.body:SetTextColor(0.93, 0.95, 0.90); f.scroll, f.content = scroll, content
  function f:Refresh()
   self.body:SetText(Safe(self.pages[self.page])); AI.ResearchFont(self.body)
   self.content:SetHeight(math.max(1, self.body:GetStringHeight() or 14))
   self.scroll:SetVerticalScroll(0); self.pageText:SetText(self.page .. " / " .. #self.pages)
   self.prev:SetEnabled(self.page > 1); self.next:SetEnabled(self.page < #self.pages)
  end
  f.prev = Button(f, "Previous", 80, function() f.page = math.max(1, f.page - 1); f:Refresh() end); f.prev:SetPoint("BOTTOMLEFT", 16, 14)
  f.next = Button(f, "Next", 80, function() f.page = math.min(#f.pages, f.page + 1); f:Refresh() end); f.next:SetPoint("LEFT", f.prev, "RIGHT", 6, 0)
  f.pageText = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); f.pageText:SetPoint("LEFT", f.next, "RIGHT", 12, 0)
  local copy = Button(f, "Copy all", 90, function() AI.ShowCopy(f.text) end); copy:SetPoint("BOTTOMRIGHT", -16, 14)
  f.find = CreateFrame("EditBox", nil, f, "InputBoxTemplate")
  f.find:SetSize(245, 22); f.find:SetPoint("TOPLEFT", 22, -42); f.find:SetAutoFocus(false)
  f.find:SetMaxLetters(120); f.find:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  f.findStatus = f:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  f.findStatus:SetPoint("TOPLEFT", 370, -46); f.findStatus:SetWidth(245); f.findStatus:SetJustifyH("LEFT")
  local function FindNext()
   local query = f.find:GetText()
   if query ~= f.lastQuery then f.findPosition = 0 end
   f.lastQuery = query
   local page, position = AI.ResearchFindPage(f.pages, query, f.findPosition)
   if page then
    f.findPosition = position; f.page = page; f:Refresh(); f.findStatus:SetText("Found on page " .. page)
   else f.findStatus:SetText(query == "" and "Enter text to find" or "No match") end
  end
  f.find:SetScript("OnEnterPressed", FindNext)
  local find = Button(f, "Find next", 88, FindNext); find:SetPoint("TOPLEFT", 276, -42)
  viewer = f
 end
 viewer.text = tostring(text or ""); viewer.pages = AI.ResearchPages(viewer.text); viewer.page = 1
 viewer.findPosition, viewer.lastQuery = 0, nil; viewer.find:SetText(""); viewer.findStatus:SetText("Find within this document")
 viewer.title:SetText(Safe(title)); viewer:Show(); viewer:Refresh()
end
local function Tip(b, text)
 b.tip = text
 b:SetScript("OnEnter", function(self) GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetText(Safe(self.tip)); GameTooltip:Show() end)
 b:SetScript("OnLeave", function() GameTooltip:Hide() end)
end
function AI.EvidenceStamp(card, now)
 if card.capture_precision == "date" then return "Daily record: " .. card.captured_at .. " (time unknown)" end
 if (card.captured_epoch or 0) > 0 then
  local age = (now or time()) - card.captured_epoch
  if age < 0 then return "Capture timestamp is in the future" end
  local minutes = math.floor(age / 60)
  if minutes < 1 then return "Scan: under 1m ago" end
  if minutes < 60 then return "Scan: " .. minutes .. "m ago" end
  if minutes < 1440 then return "Scan: " .. math.floor(minutes / 60) .. "h " .. (minutes % 60) .. "m ago" end
  return "Scan: " .. math.floor(minutes / 1440) .. "d " .. math.floor((minutes % 1440) / 60) .. "h ago"
 end
 if card.type == "price" or card.type == "aggregate" or card.type == "coverage" then return "Scan time unknown" end
 return "Source facts; no live scan"
end
function AI.EvidenceDocument(card)
 local lines = { card.title .. " - " .. card.badge, card.headline, "Market: " .. (card.market_key ~= "" and card.market_key or "Not a price quote"), "Source: " .. (card.source_key ~= "" and card.source_key or "See tool results"), AI.EvidenceStamp(card) }
 if card.captured_at and card.captured_at ~= "" then lines[#lines + 1] = "Capture: " .. card.captured_at end
 for _, f in ipairs(card.fields or {}) do lines[#lines + 1] = f.label .. ": " .. f.value end
 for _, note in ipairs(card.notes or {}) do lines[#lines + 1] = "Note: " .. note end
 return table.concat(lines, "\n")
end
function AI.EvidenceDraft(card)
 local text = "Research item ID " .. card.item_id
 if card.market_key and card.market_key:match("^[%w_.%-]+$") then text = text .. " in market " .. card.market_key end
 text = text .. " using current saved evidence. Check asking prices and acquisition requirements."
 if WoWAIInput and WoWAIInput:GetText() == "" then
  WoWAIInput:SetText(text); WoWAIInput:SetFocus()
 else AI.ShowCopy(text) end -- Preserve an existing draft; never send automatically.
end
function AI.DrawEvidence(b, message, offset, width, refresh)
 local research = message.research
 local cards = research and research.cards or {}
 b.evidenceFrames = b.evidenceFrames or {}
 for _, frame in ipairs(b.evidenceFrames) do frame:Hide() end
 if #cards == 0 then if b.evidenceHeader then b.evidenceHeader:Hide() end; return offset end
 if not b.evidenceHeader then b.evidenceHeader = Button(b, "", 260, function() end) end
 local header = b.evidenceHeader
 header:ClearAllPoints(); header:SetPoint("TOPLEFT", b.body, "BOTTOMLEFT", 0, -6 - offset)
 header:SetWidth(math.min(310, width - 24)); header:Show()
 header:SetText((message.evidenceOpen == false and "[+]" or "[-]") .. " Evidence - " .. #cards .. " cards")
 header:SetScript("OnClick", function() message.evidenceOpen = message.evidenceOpen == false; refresh() end)
 offset = offset + 28
 local pageCount = math.ceil(#cards / 3)
 message.evidencePage = math.max(1, math.min(pageCount, message.evidencePage or 1))
 if message.evidenceOpen ~= false then
  message.evidenceDetails = message.evidenceDetails or {}
  for i = (message.evidencePage - 1) * 3 + 1, math.min(message.evidencePage * 3, #cards) do
   local card = cards[i]
   local frame = b.evidenceFrames[i]
   if not frame then
    frame = CreateFrame("Frame", nil, b, "BackdropTemplate"); frame:SetBackdrop(BG)
    frame.title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    frame.title:SetPoint("TOPLEFT", 10, -10); frame.title:SetJustifyH("LEFT"); frame.title:SetWordWrap(true)
    frame.body = frame:CreateFontString(nil, "OVERLAY", "ChatFontNormal")
    frame.body:SetPoint("TOPLEFT", frame.title, "BOTTOMLEFT", 0, -5); frame.body:SetJustifyH("LEFT"); frame.body:SetWordWrap(true); frame.body:SetNonSpaceWrap(true)
    frame.details = Button(frame, "Details", 65, function() end)
    frame.result = Button(frame, "Tool result", 82, function() end)
    frame.copy = Button(frame, "Copy card", 82, function() end)
    frame.item = Button(frame, "Item", 50, function() end)
    frame.ask = Button(frame, "Ask more", 75, function() end)
    b.evidenceFrames[i] = frame
   end
   local narrow = width < 490
   frame.evidenceCard = card
   local amber = card.badge == "Classic baseline" or card.type == "aggregate"
   frame:SetBackdropColor(0.04, 0.065, 0.075, 0.96); frame:SetBackdropBorderColor(amber and 0.65 or 0.28, amber and 0.48 or 0.62, amber and 0.20 or 0.64, 1)
   frame.title:SetWidth(width - 58); frame.title:SetText(Safe(card.title .. "  [" .. card.badge .. "]"))
   local lines = {card.headline, (card.market_key ~= "" and card.market_key .. " | " or "") .. (card.source_key ~= "" and card.source_key or "See tool result"), AI.EvidenceStamp(card)}
   if not message.evidenceDetails[card.key] then
    for _, f in ipairs(card.fields or {}) do
     if f.label == "Listed units" or f.label == "Recorded quantity" or f.label == "Gathering requirement" or f.label == "Region" or f.label == "File import errors" then lines[#lines + 1] = f.label .. ": " .. f.value end
    end
   end
   if message.evidenceDetails[card.key] then
    for _, f in ipairs(card.fields or {}) do lines[#lines + 1] = f.label .. ": " .. f.value end
    for _, note in ipairs(card.notes or {}) do lines[#lines + 1] = "Note: " .. note end
    if card.captured_at ~= "" then lines[#lines + 1] = "Capture: " .. card.captured_at end
   end
   frame.body:SetWidth(width - 58); frame.body:SetText(Safe(table.concat(lines, "\n"))); AI.ResearchFont(frame.body)
   local buttonsY = 10 + math.max(14, frame.title:GetStringHeight()) + 5 + math.max(14, frame.body:GetStringHeight()) + 8
   local function Place(q, x, row) q:ClearAllPoints(); q:SetPoint("TOPLEFT", 10 + x, -buttonsY - row * 26); q:Show() end
   Place(frame.details,0,0); Place(frame.result,70,0); Place(frame.copy,157,0)
   local itemRow = narrow and 1 or 0
   Place(frame.item,narrow and 0 or 244,itemRow); Place(frame.ask,narrow and 55 or 299,itemRow)
   frame.details:SetText(message.evidenceDetails[card.key] and "Less" or "Details")
   frame.details:SetScript("OnClick", function() message.evidenceDetails[card.key] = not message.evidenceDetails[card.key]; refresh() end)
   local call
   for _, c in ipairs(research.calls or {}) do if c.id == card.tool_id then call = c; break end end
   frame.result:SetEnabled(call ~= nil)
   frame.result:SetScript("OnClick", function() if call then AI.ShowResearchDocument(card.title .. " - " .. call.name, call.result ~= "" and call.result or "No result text supplied.") end end)
   frame.copy:SetScript("OnClick", function() AI.ShowCopy(AI.EvidenceDocument(card)) end)
   frame.item:SetShown((card.item_id or 0) > 0); frame.ask:SetShown((card.item_id or 0) > 0)
   frame.item:SetScript("OnClick", function() SetItemRef("item:" .. card.item_id, card.title, "LeftButton") end)
   frame.item:SetScript("OnEnter", function(self) GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetHyperlink("item:" .. card.item_id); GameTooltip:Show() end)
   frame.item:SetScript("OnLeave", function() GameTooltip:Hide() end)
   frame.ask:SetScript("OnClick", function() AI.EvidenceDraft(card) end)
   Tip(frame.ask, "Draft a follow-up question. You edit it and press Send; an existing draft is preserved.")
   local h = buttonsY + 30 + (narrow and card.item_id > 0 and 26 or 0)
   frame:ClearAllPoints(); frame:SetPoint("TOPLEFT", b.body, "BOTTOMLEFT", 8, -6 - offset); frame:SetSize(width - 36,h); frame:Show()
   offset = offset + h + 8
  end
 end
 return offset, pageCount
end
function AI.DrawResearch(b, message, offset, width, refresh)
 local redraw = refresh
 refresh = function() message.researchUiVersion = (message.researchUiVersion or 0) + 1; redraw() end
 local research, resources = message.research, message.resources or AI.ResearchURLs(message.text)
 b.researchButtons, b.researchTexts = b.researchButtons or {}, b.researchTexts or {}
 local bn, tn, y = 0, 0, offset
 local function Btn(label, x, w, fn, tip)
  bn = bn + 1; local q = b.researchButtons[bn]
  if not q then q = Button(b, "", w, function() end); b.researchButtons[bn] = q end
  q:SetEnabled(true) -- A pooled paging button may previously have been disabled.
  q:SetText(label); q:SetWidth(w); q:ClearAllPoints(); q:SetPoint("TOPLEFT", b.body, "BOTTOMLEFT", x, -6 - y)
  q:SetScript("OnClick", fn); Tip(q, tip or label); q:Show(); return q
 end
 local function Text(text)
  tn = tn + 1; local q = b.researchTexts[tn]
  if not q then q = b:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall"); q:SetJustifyH("LEFT"); q:SetJustifyV("TOP"); q:SetWordWrap(true); b.researchTexts[tn] = q end
  q:ClearAllPoints(); q:SetPoint("TOPLEFT", b.body, "BOTTOMLEFT", 8, -6 - y); q:SetWidth(width - 36); q:SetText(Safe(text)); q:Show()
  y = y + math.max(14, q:GetStringHeight() or 14) + 8
 end
 local function Sources(list)
  for i, r in ipairs(list or {}) do
   local source = r
   if type(source.url) == "string" and (source.url:match("^https://") or source.url:match("^http://127%.0%.0%.1:")) then
    Btn("Source " .. i .. " - copy URL", 8, math.min(220, width - 36), function() AI.ShowCopy(source.url) end, (source.label or "Source") .. "\n" .. source.url .. "\nClick to copy the URL for your browser.")
    y = y + 26
   elseif (source.kind == "item" or source.kind == "spell") and tonumber(source.id) and source.id > 0 and source.id == math.floor(source.id) then
    local link = source.kind .. ":" .. source.id
    local button = Btn(source.kind .. ": " .. Safe(source.label or source.id), 8, math.min(250, width - 36), function() SetItemRef(link, source.label or "", "LeftButton") end)
    button:SetScript("OnEnter", function(self) GameTooltip:SetOwner(self, "ANCHOR_RIGHT"); GameTooltip:SetHyperlink(link); GameTooltip:Show() end)
    y = y + 26
   end
  end
 end
 local _, long = AI.ResearchPreview(message.text, 6000)
 if long then Btn("Read full reply", 0, 125, function() AI.ShowResearchDocument("Full reply", message.text) end); y = y + 28 end
 if message.role == "assistant" then
  local speechKey
  if type(message.speech_key) == "string" and message.speech_key:match("^[%w%-]+$") and message.speech_key ~= "" then speechKey = message.speech_key
  elseif type(message.id) == "number" and message.id > 0 and message.id == math.floor(message.id) then speechKey = "id:" .. string.format("%.0f", message.id)
  end
  Btn(speechKey and "Play TL;DR" or "Play latest", 8, 105, function() AI.Voice("listen", speechKey or "") end, speechKey and "Read this saved reply's summary using your selected local voice. If no TL;DR exists, read a short opening preview." or "This reply has no saved identifier. Read the latest saved reply in this chat instead.")
  Btn(speechKey and "Play full" or "Play latest full", 119, 110, function() AI.Voice("listenfull", speechKey or "") end, speechKey and "Read this saved reply's full text. Code blocks and link addresses are skipped." or "Read the latest saved reply in this chat, in full.")
  y = y + 26
  Btn("Stop voice", 8, 105, function() AI.Voice("stop") end)
  Btn("Voice settings", 119, 115, function() AI.ShowVoiceSettings() end)
  y = y + 28
 end
 local pages
 y, pages = AI.DrawEvidence(b, message, y, width, refresh)
 if pages and pages > 1 and message.evidenceOpen ~= false then
  local previous = Btn("< Cards", 8, 75, function() message.evidencePage = math.max(1, message.evidencePage - 1); refresh() end)
  local nextPage = Btn("Cards >", 88, 75, function() message.evidencePage = math.min(pages, message.evidencePage + 1); refresh() end)
  previous:SetEnabled(message.evidencePage > 1); nextPage:SetEnabled(message.evidencePage < pages)
  y = y + 26; Text("Evidence page " .. message.evidencePage .. " / " .. pages)
 end
 if research and (research.cards_omitted or 0) > 0 and message.evidenceOpen ~= false then Text(research.cards_omitted .. " earlier cards omitted; inspect tool results or the archive.") end
 if research and #(research.calls or {}) > 0 then
  Btn((message.researchOpen and "[-]" or "[+]") .. " Research - " .. (research.total or #research.calls) .. " tool calls", 0, math.min(310, width - 24), function() message.researchOpen = not message.researchOpen; refresh() end)
  y = y + 28
  if message.researchOpen then
   message.toolOpen = message.toolOpen or {}
   if research.elapsed_ms then Text("Agent round trip: " .. string.format("%.1fs", research.elapsed_ms / 1000) .. " (includes model and tools)") end
   if (research.omitted or 0) > 0 then Text("Showing the latest 40 calls; " .. research.omitted .. " earlier calls are in the full archive.") end
   for _, call in ipairs(research.calls) do
    local tool = call
    local open = message.toolOpen[tool.id]
    local status = tool.status == "running" and "Working" or tool.status == "error" and "Failed" or "Done"
    local duration = tool.status ~= "running" and tool.timing_known and ("  " .. string.format("%.1fs", (tool.elapsed or 0) / 1000)) or ""
    Btn((open and "[-] " or "[+] ") .. status .. ": " .. tostring(tool.name) .. duration, 8, width - 36, function() message.toolOpen[tool.id] = not message.toolOpen[tool.id]; refresh() end, tostring(tool.name) .. "\n" .. status .. duration .. "\nClick to expand inputs, results and sources.")
    y = y + 26
    if open then
     if tool.summary and tool.summary ~= "" then Text(tool.summary) end
     Btn("Inputs", 16, 80, function() AI.ShowResearchDocument(tool.name .. " - inputs", tool.input ~= "" and tool.input or "No arguments.") end)
     Btn("Result", 102, 80, function() AI.ShowResearchDocument(tool.name .. " - result", tool.result ~= "" and tool.result or "Waiting for a result.") end)
     y = y + 28; Sources(tool.resources)
    end
   end
   if research.archive and research.archive ~= "" then
    Btn("Copy full archive path", 8, 190, function() AI.ShowCopy(research.archive) end, "Full tool inputs and results are saved locally:\n" .. research.archive); y = y + 28
   end
   if research.archive_error and research.archive_error ~= "" then Text(research.archive_error) end
  end
 end
 if #resources > 0 then
  Btn((message.sourcesOpen and "[-]" or "[+]") .. " Sources - " .. #resources, 0, 150, function() message.sourcesOpen = not message.sourcesOpen; refresh() end); y = y + 28
  if message.sourcesOpen then Sources(resources) end
 end
 for i = bn + 1, #b.researchButtons do b.researchButtons[i]:Hide() end
 for i = tn + 1, #b.researchTexts do b.researchTexts[i]:Hide() end
 return y
end

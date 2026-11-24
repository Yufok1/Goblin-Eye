lua_path = r'D:\World of Warcraft\_forever_\WTF\Account\314679015#1\SavedVariables\AltsForever.lua'
with open(lua_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

pattern = '["Hair Do"]'
pos = text.find(pattern)
# find the next character or end of table
next_pos = text.find('["Toasty Steedo"]', pos)
if next_pos == -1:
    next_pos = pos + 10000

print(text[pos:next_pos])

import re

lua_path = r'D:\World of Warcraft\_forever_\WTF\Account\314679015#1\SavedVariables\AltsForever.lua'
with open(lua_path, 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

pattern = '["Hair Do"]'
pos = text.find(pattern)
if pos != -1:
    print(f"Found Hair Do at {pos}")
    print(text[pos:pos+4000])
else:
    print("Hair Do not found")

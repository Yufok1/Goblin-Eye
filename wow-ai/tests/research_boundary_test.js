'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('fs'), path = require('path');
const {lua, lauxlib, lualib, to_luastring} = require('fengari');
test('chat context executes without game APIs and returns empty to clear bridge context', () => {
  for (const file of ['WoWAI.core.lua', 'WoWAI.lua']) {
    const source = fs.readFileSync(path.join(__dirname, '../addon/WoWAI', file), 'utf8');
    const body = source.match(/function WoWAI\.GameContext\(\)[\s\S]*?\nend/)[0];
    const L = lauxlib.luaL_newstate(); lualib.luaL_openlibs(L);
    assert.equal(lauxlib.luaL_dostring(L, to_luastring('WoWAI={}\n'+body+'\nassert(WoWAI.GameContext()=="")')), lua.LUA_OK);
    lua.lua_close(L);
    assert.ok(!source.includes('s.context = rest == "on"'));
  }
});

'use strict';
// Filesystem-only fixtures and mocked spawns. Never start a bridge, vendor CLI,
// speech worker, game client or model probe.
const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('fs'), os = require('os'), path = require('path');
const Storage = require('../bridge/runtime-storage');
const {spawnBackground} = require('../bridge/background-process');
const spec = require('../../runtime-storage.json');
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'goblin-storage-test-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  return {root, storage: path.join(root, 'runtime'), source: path.join(root, 'original')};
}
function put(file, text) {fs.mkdirSync(path.dirname(file), {recursive: true}); fs.writeFileSync(file, text);}
test('all writable homes and tool caches replace inherited system-drive paths without changing the parent', t => {
  const f = fixture(t), base = {GOBLIN_EYE_STORAGE_ROOT: f.storage, USERPROFILE: 'C:\\Users\\Player',
    APPDATA: 'C:\\old-appdata', LOCALAPPDATA: 'C:\\old-local', Temp: 'C:\\old-temp',
    CODEX_HOME: 'C:\\old-codex', HF_HOME: 'C:\\old-models', KILO_CONFIG_CONTENT: 'policy', PATH: 'installed-binaries'};
  const before = JSON.stringify(base), env = Storage.environment(base);
  for (const name of Object.keys(spec.directories)) {
    assert.ok(env[name].startsWith(f.storage + path.sep), name);
    assert.ok(fs.statSync(env[name]).isDirectory(), name);
  }
  assert.equal(env.Temp, undefined, 'case variants cannot select the old C: temporary directory');
  assert.equal(env.KILO_CONFIG_CONTENT, 'policy');
  assert.equal(env.PATH, 'installed-binaries');
  assert.equal(env.GOBLIN_EYE_HOST_USERPROFILE, 'C:\\Users\\Player');
  assert.equal(JSON.stringify(base), before);
});
test('system drive, C:, relative and UNC storage roots fail closed', () => {
  for (const root of ['C:\\Goblin Eye', 'c:/tmp', 'D:relative', 'folder', '\\\\host\\share\\data', 'E:\\data']) {
    assert.throws(() => Storage.validateRoot(root, {platform: 'win32', systemDrive: 'E:'}));
  }
  assert.equal(Storage.validateRoot('D:\\Games\\Goblin Eye', {platform: 'win32', systemDrive: 'C:'}), 'D:\\Games\\Goblin Eye');
});
test('a storage junction is rejected before any files are written through it', t => {
  const f = fixture(t), target = path.join(f.root, 'target'); fs.mkdirSync(target);
  fs.symlinkSync(target, f.storage, process.platform === 'win32' ? 'junction' : 'dir');
  assert.throws(() => Storage.environment({}, {root: f.storage}), /link/);
  assert.deepEqual(fs.readdirSync(target), []);
});
test('one-time import copies only sign-ins/settings and never overwrites a private profile or rereads the shared home', t => {
  const f = fixture(t), source = {USERPROFILE: f.source};
  put(path.join(f.source, '.codex/auth.json'), 'fixture-auth');
  put(path.join(f.source, '.codex/config.toml'), 'fixture-config');
  put(path.join(f.source, '.codex/sessions/old.jsonl'), 'do not copy sessions');
  put(path.join(f.source, '.local/share/kilo/auth.json'), 'fixture-kilo');
  put(path.join(f.source, '.local/share/kilo/kilo.db'), 'do not copy database');
  const env = Storage.environment(source, {root: f.storage});
  put(path.join(env.CODEX_HOME, 'config.toml'), 'private-settings');
  const imported = Storage.importSignIns(env, source, {secure: () => {}});
  assert.ok(imported.some(file => file.endsWith('auth.json')));
  assert.equal(fs.readFileSync(path.join(env.CODEX_HOME, 'auth.json'), 'utf8'), 'fixture-auth');
  assert.equal(fs.readFileSync(path.join(env.CODEX_HOME, 'config.toml'), 'utf8'), 'private-settings');
  assert.equal(fs.existsSync(path.join(env.CODEX_HOME, 'sessions')), false);
  assert.equal(fs.existsSync(path.join(env.XDG_DATA_HOME, 'kilo/kilo.db')), false);
  assert.equal(fs.readFileSync(path.join(f.source, '.codex/auth.json'), 'utf8'), 'fixture-auth');
  assert.deepEqual(Storage.importSignIns(env, {USERPROFILE: 'C:\\nonexistent'}, {secure: () => {}}), []);
});
test('a launcher that already redirected HOME still imports from its preserved original profile', t => {
  const f = fixture(t); put(path.join(f.source, '.grok/auth.json'), 'fixture-grok');
  const source = {HOME: path.join(f.root, 'shadow'), USERPROFILE: path.join(f.root, 'shadow'), GOBLIN_EYE_HOST_USERPROFILE: f.source};
  const env = Storage.environment(source, {root: f.storage});
  Storage.importSignIns(env, source, {secure: () => {}});
  assert.equal(fs.readFileSync(path.join(env.GROK_HOME, 'auth.json'), 'utf8'), 'fixture-grok');
  assert.equal(env.GOBLIN_EYE_HOST_HOME, f.source);
});
test('background wrappers and their descendants receive D: storage while retaining hidden-console isolation', t => {
  const f = fixture(t), calls = [];
  const env = {GOBLIN_EYE_STORAGE_ROOT: f.storage, HF_HOME: 'C:\\old-models'};
  spawnBackground('fixture-cli', ['arg'], {env, stdio: 'pipe'}, (...args) => {calls.push(args); return {};});
  const [file, args, options] = calls[0];
  assert.equal(options.windowsHide, true);
  assert.equal(options.env.TEMP, path.join(f.storage, 'tmp'));
  assert.equal(options.env.HF_HOME, path.join(f.storage, spec.directories.HF_HOME));
  assert.equal(options.stdio, 'pipe');
  if (process.platform === 'win32' && process.env.GOBLIN_EYE_HIDDEN_CONSOLE !== '1') {
    assert.equal(path.basename(file), 'python.exe'); assert.ok(args.some(arg => arg.endsWith('hidden-console.py')));
  }
});
test('moving a provider home drops obsolete session handles but retains saved chat context', () => {
  const state = {sessions: {chat: 'old-handle'}, context: {text: 'saved'}, handled: {one: 1}};
  Storage.resetSessions(state, 'D:\\runtime');
  assert.deepEqual(state.sessions, {}); assert.equal(state.context.text, 'saved'); assert.equal(state.handled.one, 1);
  state.sessions.chat = 'new-handle';
  Storage.resetSessions(state, 'D:\\runtime');
  assert.equal(state.sessions.chat, 'new-handle');
});
test('the launcher applies portable storage before Python and fails without starting the supervisor', () => {
  const {main} = require('../bridge/launch-chat'), env = {TEMP: 'D:\\runtime\\tmp'};
  const order = [];
  main({activate: () => {order.push('storage'); return env;}, spawnSync: (file, args, options) => {
    order.push('export'); assert.equal(options.env, env); assert.equal(options.windowsHide, true); return {status: 0};
  }, start: () => order.push('supervisor')});
  assert.deepEqual(order, ['storage', 'export', 'supervisor']);
  assert.throws(() => main({activate: () => env, spawnSync: () => ({status: 1}), start: () => assert.fail('Bridge cannot start on an exporter error')}));
});
test('manual login uses the same private environment and literal arguments without a shell', () => {
  const {main} = require('../bridge/agent-profile'), env = {CODEX_HOME: 'D:\\runtime\\home\\.codex'};
  const code = main(['codex', 'login'], {activate: () => env,
    agents: {normalizeAgent: id => id, validateProject: () => {}, resolveCommand: () => ({found: true, file: 'installed-cli', args: ['launcher']})},
    spawnSync: (file, args, options) => {
      assert.equal(file, 'installed-cli'); assert.deepEqual(args, ['launcher', 'login']);
      assert.equal(options.env, env); assert.equal(options.shell, undefined); return {status: 0};
    }});
  assert.equal(code, 0);
});
test('credential protection must succeed before any sign-in data can be copied', t => {
  const f = fixture(t), source = {USERPROFILE: f.source};
  put(path.join(f.source, '.codex/auth.json'), 'fixture-auth');
  const env = Storage.environment(source, {root: f.storage});
  assert.throws(() => Storage.importSignIns(env, source, {secure: () => {throw Error('permission failure');}}), /permission failure/);
  assert.equal(fs.existsSync(path.join(env.CODEX_HOME, 'auth.json')), false);
});
test('generated read-only MCP connections direct child storage to the installation drive', t => {
  const f = fixture(t);
  fs.copyFileSync(path.join(__dirname, '../../runtime-storage.json'), path.join(f.root, 'runtime-storage.json'));
  const configs = require('../../Setup-WoWAI').mcpConfigs(f.root);
  const mcp = JSON.parse(configs['.mcp.json']).mcpServers.goblin_eye;
  const kilo = JSON.parse(configs['kilo.json']).mcp['goblin-eye'];
  assert.equal(mcp.env.TEMP, path.join(f.root, 'data/runtime/tmp'));
  assert.equal(mcp.env.CODEX_HOME, path.join(f.root, 'data/runtime/home/.codex'));
  assert.equal(kilo.environment.HF_HOME, mcp.env.HF_HOME);
  assert.ok(!mcp.env.GOBLIN_EYE_HOST_HOME);
  assert.ok(configs['.codex/config.toml'].includes('TEMP = '));
  assert.equal(mcp.args.at(-1), 'mcp');
});

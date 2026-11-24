'use strict';
// Process-local writable homes. Installed executables can still be read from the
// host profile; no junctions, global environment changes or shared-cache deletes.
const fs = require('fs');
const os = require('os');
const path = require('path');
const PACKAGE = [path.resolve(__dirname, '../..'), path.resolve(__dirname, '..'), __dirname]
  .find(dir => fs.existsSync(path.join(dir, 'runtime-storage.json')));
if (!PACKAGE) throw Error('Missing runtime-storage.json; extract the complete Goblin Eye package.');
const HOST_KEYS = ['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'GROK_HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'];
function host(env, key) { return env['GOBLIN_EYE_HOST_' + key] || env[key]; }
function hostHome(env) { return env.GOBLIN_EYE_HOST_HOME || env.GOBLIN_EYE_HOST_USERPROFILE || env.USERPROFILE || env.HOME || os.homedir(); }
function validateRoot(root, {platform = process.platform, systemDrive = process.env.SystemDrive || 'C:'} = {}) {
  if (platform === 'win32') {
    if (!path.win32.isAbsolute(root) || root.startsWith('\\\\') || /^[a-z]:$/i.test(root)) throw Error('Goblin Eye storage requires an absolute local folder outside the system drive.');
    const drive = path.win32.parse(root).root.slice(0, 2).toLowerCase();
    if (drive === 'c:' || drive === systemDrive.toLowerCase()) throw Error('Goblin Eye will not store runtime files on C: or the Windows system drive. Move it to D: or set GOBLIN_EYE_STORAGE_ROOT to a non-system drive.');
  }
  return root;
}
function storageRoot(env = process.env, packageRoot = PACKAGE) {
  const requested = env.GOBLIN_EYE_STORAGE_ROOT || path.join(packageRoot, 'data', 'runtime');
  validateRoot(requested);
  return path.resolve(requested);
}
// Reject existing junctions/symlinks before mkdir or any credential copy. Never
// silently follow a D: path that points back to the system drive.
function directory(dir) {
  const parent = path.dirname(dir);
  if (parent !== dir) directory(parent);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir);
  const stat = fs.lstatSync(dir);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw Error('Goblin Eye storage directory must not be a link: ' + dir);
  validateRoot(fs.realpathSync(dir));
}
function environment(base = process.env, {root = storageRoot(base), packageRoot = PACKAGE, create = true} = {}) {
  validateRoot(root);
  const spec = JSON.parse(fs.readFileSync(path.join(packageRoot, 'runtime-storage.json'), 'utf8'));
  const env = {...base};
  const managed = new Set([...Object.keys(spec.directories), ...Object.keys(spec.values)].map(key => key.toLowerCase()));
  for (const key of Object.keys(env)) if (managed.has(key.toLowerCase())) delete env[key];
  for (const key of HOST_KEYS) if (host(base, key)) env['GOBLIN_EYE_HOST_' + key] = host(base, key);
  env.GOBLIN_EYE_HOST_HOME = hostHome(base);
  env.GOBLIN_EYE_STORAGE_ROOT = root;
  for (const [key, relative] of Object.entries(spec.directories)) {
    const target = path.resolve(root, relative);
    const rel = path.relative(root, target);
    if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) throw Error('Invalid portable storage directory.');
    if (create) directory(target);
    env[key] = target;
  }
  Object.assign(env, spec.values);
  if (process.platform === 'win32') {
    env.HOMEDRIVE = path.parse(env.USERPROFILE).root.slice(0, 2);
    env.HOMEPATH = env.USERPROFILE.slice(2);
  }
  // A fresh D: home must not invoke vendor updates or re-install its executable.
  env.DISABLE_AUTOUPDATER = '1';
  env.GROK_DISABLE_AUTOUPDATER = '1';
  return env;
}
function secureRuntime(env) {
  const marker = path.join(env.GOBLIN_EYE_STORAGE_ROOT, 'private-access-v1');
  if (fs.existsSync(marker)) return;
  if (process.platform === 'win32') {
    const bundled = path.join(PACKAGE, 'python', 'python.exe');
    const python = process.env.GOBLIN_EYE_PYTHON || (fs.existsSync(bundled) ? bundled : 'python');
    const result = require('child_process').spawnSync(python, ['-I', path.join(__dirname, 'storage-permissions.py'), env.GOBLIN_EYE_STORAGE_ROOT], {env, windowsHide: true, stdio: 'pipe'});
    if (result.error || result.status !== 0) throw Error('Could not protect the private runtime folder. Sign-ins were not imported.');
  } else fs.chmodSync(env.GOBLIN_EYE_STORAGE_ROOT, 0o700);
  fs.writeFileSync(marker, '1\n', {flag: 'wx', mode: 0o600});
}
function importSignIns(env, source = process.env, {secure = secureRuntime} = {}) {
  secure(env);
  const marker = path.join(env.GOBLIN_EYE_STORAGE_ROOT, 'profile-import-v1.json');
  if (fs.existsSync(marker)) return [];
  const original = hostHome(source);
  const fromHome = file => path.join(original, file);
  const config = host(source, 'XDG_CONFIG_HOME') || fromHome('.config');
  const data = host(source, 'XDG_DATA_HOME') || fromHome('.local/share');
  const profiles = [
    [host(source, 'CODEX_HOME') || fromHome('.codex'), env.CODEX_HOME, ['auth.json', 'config.toml']],
    [host(source, 'CLAUDE_CONFIG_DIR') || fromHome('.claude'), env.CLAUDE_CONFIG_DIR, ['.credentials.json', 'settings.json']],
    [original, env.HOME, ['.claude.json']],
    [original, env.CLAUDE_CONFIG_DIR, ['.claude.json']],
    [host(source, 'GROK_HOME') || fromHome('.grok'), env.GROK_HOME, ['auth.json', 'config.toml']],
    [path.join(config, 'kilo'), path.join(env.XDG_CONFIG_HOME, 'kilo'), ['config.json', 'mcp_config.json']],
    [path.join(data, 'kilo'), path.join(env.XDG_DATA_HOME, 'kilo'), ['auth.json']],
    [fromHome('.gemini'), path.join(env.HOME, '.gemini'), ['settings.json', 'oauth_creds.json', 'google_accounts.json']],
    [fromHome('.gemini/antigravity-cli'), path.join(env.HOME, '.gemini/antigravity-cli'), ['settings.json', 'jetski_state.pbtxt']],
    [fromHome('.gemini/config'), path.join(env.HOME, '.gemini/config'), ['config.json', 'mcp_config.json']],
    [fromHome('.hermes'), env.HERMES_HOME, ['.env', 'config.yaml', 'auth.json']],
  ];
  const copied = [];
  for (const [src, dest, names] of profiles) for (const name of names) {
    const from = path.join(src, name), to = path.join(dest, name);
    if (from === to || fs.existsSync(to) || !fs.existsSync(from)) continue;
    if (!fs.statSync(from).isFile()) continue;
    directory(path.dirname(to));
    fs.copyFileSync(from, to, fs.constants.COPYFILE_EXCL);
    fs.chmodSync(to, 0o600);
    copied.push(path.relative(env.GOBLIN_EYE_STORAGE_ROOT, to));
  }
  // Only allowlisted sign-in/settings files; never import sessions, model
  // packages, logs, databases, skills, plugins or entire user profiles.
  fs.writeFileSync(marker, JSON.stringify({version: 1, copied}, null, 2) + '\n', {flag: 'wx', mode: 0o600});
  return copied;
}
function activate() {
  const env = environment();
  importSignIns(env);
  Object.assign(process.env, env);
  return env;
}
function resetSessions(state, root = process.env.GOBLIN_EYE_STORAGE_ROOT) {
  if (state.agentStorageRoot === root) return;
  state.sessions = {};
  state.agentStorageRoot = root;
}
module.exports = {host, validateRoot, storageRoot, environment, importSignIns, activate, resetSessions, secureRuntime};

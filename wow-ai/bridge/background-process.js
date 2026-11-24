'use strict';
const fs = require('fs'), path = require('path');
const {spawn} = require('child_process');
const Storage = require('./runtime-storage');
function spawnBackground(file, args, options, spawnFn = spawn) {
  options = {...options, env: Storage.environment(options?.env || process.env)};
  if (process.platform !== 'win32' || process.env.GOBLIN_EYE_HIDDEN_CONSOLE === '1') {
    return spawnFn(file, args, {...options, windowsHide: true});
  }
  const bundled = path.resolve(__dirname, '../../python/python.exe');
  const python = process.env.GOBLIN_EYE_PYTHON || (fs.existsSync(bundled) ? bundled : 'python');
  const child = spawnFn(python, ['-I', path.join(__dirname, 'hidden-console.py'), file, ...args], {
    ...options, windowsHide: true,
  });
  // The wrapper owns a kill-on-close Windows job. Terminating it is sufficient
  // to reap the entire tree and avoids taskkill's desktop/launch races.
  child.goblinBackgroundJob = true;
  return child;
}
module.exports = {spawnBackground};

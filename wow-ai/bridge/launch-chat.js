#!/usr/bin/env node
'use strict';
// Set writable profiles before even the policy exporter starts Python.
function main({activate = require('./runtime-storage').activate, spawnSync = require('child_process').spawnSync, start = () => require('./supervisor')} = {}) {
  const env = activate();
  const path = require('path'), fs = require('fs');
  const bundled = path.resolve(__dirname, '../../python/python.exe');
  const python = fs.existsSync(bundled) ? bundled : 'python';
  const result = spawnSync(python, [path.join(__dirname, 'export-research-tools.py')], {env, stdio: 'inherit', windowsHide: true});
  if (result.error || result.status !== 0) throw Error('Could not generate the read-only research policy. Bridge not started.');
  start();
}
module.exports = {main};
if (require.main === module) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}

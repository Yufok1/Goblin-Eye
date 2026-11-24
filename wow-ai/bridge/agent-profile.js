#!/usr/bin/env node
'use strict';
// User-invoked interactive login/settings use the same private home as chat.
function main(argv, {activate = require('./runtime-storage').activate,
  agents = require('./agents'), spawnSync = require('child_process').spawnSync} = {}) {
  const env = activate(), id = agents.normalizeAgent(argv[0]);
  if (!id) throw Error('Usage: node wow-ai/bridge/agent-profile.js <agent> [CLI arguments]');
  agents.validateProject(process.cwd());
  const command = agents.resolveCommand(id, {});
  if (!command.found) throw Error(agents.displayName(id) + ' is not installed.');
  const result = spawnSync(command.file, [...command.args, ...argv.slice(1)], {env, cwd: process.cwd(), windowsHide: true, stdio: 'inherit'});
  if (result.error) throw result.error;
  return result.status ?? 1;
}
module.exports = {main};
if (require.main === module) {
  try {process.exitCode = main(process.argv.slice(2));}
  catch (error) {console.error(error.message); process.exitCode = 1;}
}

'use strict';
// Preloaded only into Node CLI launchers started by the bridge. Hiding the
// launcher does not hide the native executable it spawns (e.g. Kilo/Codex).
// Preserve the vendor's binary selection, environment, stdio and signal logic.
if (process.platform === 'win32') {
  const cp = require('node:child_process');
  for (const name of ['spawn', 'spawnSync']) {
    const original = cp[name];
    cp[name] = function(command, args, options) {
      if (!Array.isArray(args)) {
        options = args;
        args = [];
      }
      return original.call(this, command, args, { ...options,
        windowsHide: process.env.GOBLIN_EYE_HIDDEN_CONSOLE !== '1' });
    };
  }
  // Codex's npm launcher uses ESM named imports; Kilo uses CommonJS.
  require('node:module').syncBuiltinESMExports();
}

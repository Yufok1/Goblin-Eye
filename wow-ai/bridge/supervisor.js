#!/usr/bin/env node
'use strict';
// Keeps bridge.js running: restarts it 3 s after any exit. Ctrl+C stops both.
// This is also the `wow-ai` command (package.json "bin"): arguments and the
// current folder pass straight through to bridge.js, so `cd proj && wow-ai`
// makes proj the default folder for chats.
const { spawn } = require('child_process');
const path = require('path');

let child = null;
let stopping = false;

function start() {
  child = spawn(process.execPath, [path.join(__dirname, 'bridge.js'), ...process.argv.slice(2)], { stdio: 'inherit' });
  child.on('exit', (code) => {
    child = null;
    if (stopping) return;
    if (code === 2 || code === 0) process.exit(code); // config problem or --help/--once: don't loop
    console.log(`\nbridge exited (${code}); restarting in 3 s`);
    setTimeout(start, 3000);
  });
}

function stop() {
  stopping = true;
  if (child) child.kill();
  process.exit(0);
}

process.on('SIGINT', stop);
process.on('SIGTERM', stop);
start();

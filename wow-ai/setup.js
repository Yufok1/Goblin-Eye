#!/usr/bin/env node
'use strict';
// Use the portable Goblin Eye installer, including local MCP setup.
require('../Setup-WoWAI').main(process.argv.slice(2)).catch(e=>{console.error('Setup failed: '+e.message);process.exitCode=1;});

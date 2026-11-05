'use strict';
// Companion policy is process-local; it never rewrites the user's Kilo config.
const TOOL_NAMES=require('./research-tools.json');
if (!Array.isArray(TOOL_NAMES) || !TOOL_NAMES.length || new Set(TOOL_NAMES).size!==TOOL_NAMES.length || TOOL_NAMES.some(name=>typeof name!=='string' || !/^[a-z][a-z0-9_]*$/.test(name))) throw Error('Invalid generated research tool policy.');
function restrictedEnv(env) {
 let content={};
 if(env.KILO_CONFIG_CONTENT){try{content=JSON.parse(env.KILO_CONFIG_CONTENT);}catch{throw Error('KILO_CONFIG_CONTENT must be valid JSON for companion restrictions.');}}
 const permission={'*':'deny',read:{'*':'allow','.env':'deny','*.env.*':'deny'},glob:'allow',grep:'allow',list:'allow',webfetch:'allow',websearch:'allow',todoread:'allow',todowrite:'allow'};
 for(const name of TOOL_NAMES)permission['goblin-eye_'+name]='allow';
 content.agent={...(content.agent||{}),'goblin-research':{description:'Read-only Goblin Eye companion',mode:'primary',permission}};
 return {...env,KILO_CONFIG_CONTENT:JSON.stringify(content)};
}
module.exports={restrictedEnv,TOOL_NAMES};

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const R = require('../bridge/research');
const A = require('../bridge/agents');
const P = require('../bridge/protocol');
const luaparse = require('luaparse');

test('current and older Codex MCP events retain inputs, result, status and timing', () => {
 let now = 1000;
 const j = new R.Journal(() => now);
 j.feed({type:'item.started', item:{type:'mcp_tool_call',id:'one',server:'goblin_eye',tool:'get_economic_summary',arguments:{market_key:'wow-forever'}}}, 'codex');
 now = 2500;
 const completed = {type:'event_msg',payload:{type:'item_completed',item:{type:'McpToolCall',id:'one',server:'goblin_eye',tool:'get_economic_summary',status:'completed',result:{content:[{type:'text',text:JSON.stringify({market_key:'wow-forever',snapshot_count:6,source_url:'https://example.org/evidence'})}]}}}};
 j.feed(completed,'codex');
 const call=j.wire().calls[0];
 assert.equal(j.full().length,1); assert.equal(call.name,'goblin_eye.get_economic_summary');
 assert.equal(call.status,'completed'); assert.equal(call.elapsed,1500);
 assert.match(call.input,/wow-forever/); assert.match(call.summary,/snapshot count: 6/);
 assert.equal(call.resources[0].url,'https://example.org/evidence');
 const parser=A.codexParser();
 assert.ok(parser.feed(completed).progress.some(p=>p.includes('get_economic_summary')));
});
test('custom calls join their output using call_id, without treating code as instructions', () => {
 const j=new R.Journal();
 j.feed({type:'custom_tool_call',call_id:'a',name:'exec',input:'await tools.mcp__goblin_eye__get_source_health({})'},'codex');
 j.feed({type:'custom_tool_call_output',call_id:'a',output:'source health result'},'codex');
 assert.equal(j.full().length,1); assert.equal(j.full()[0].name,'exec');
 assert.equal(j.full()[0].result,'source health result'); assert.equal(j.full()[0].status,'completed');
 assert.equal(j.feed({type:'item.completed',item:{type:'reasoning',id:'private',text:'never collect'}},'codex'),false);
 assert.ok(!JSON.stringify(j.full()).includes('never collect'));
});
test('large tool results have an explicit preview and complete archived content', () => {
 const j=new R.Journal();
 const text='herb '.repeat(5000)+'COMPLETE END';
 j.feed({type:'item.completed',item:{type:'mcp_tool_call',id:'x',tool:'large',result:text}},'codex');
 assert.ok(j.full()[0].result.endsWith('COMPLETE END'));
 assert.match(j.wire('archive.json').calls[0].result,/Showing 12000 of/);
 assert.equal(j.wire().total,1);
 for(let n=0;n<45;n++) j.feed({type:'item.completed',item:{type:'mcp_tool_call',id:String(n),tool:'query',result:'ok'}},'codex');
 assert.equal(j.wire().calls.length,40); assert.equal(j.wire().omitted,6); assert.equal(j.full().length,46);
});
test('credential fields and unsafe external URL schemes are excluded from displays', () => {
 const text=R.printable({api_key:'SECRET',nested:{password:'SECRET'},message:'Bearer SECRET',valid:'https://example.org/a'});
 assert.ok(!text.includes('SECRET'));
 assert.deepEqual(R.urls('http://outside.test/a https://user:password@example.org/ javascript:evil https://example.org/safe).').map(r=>r.url),['https://example.org/safe']);
 assert.equal(R.urls('http://127.0.0.1:8765/')[0].url,'http://127.0.0.1:8765/');
});
test('source and research fields serialize into valid Lua for replies and restores', () => {
 const r={total:1,calls:[{id:'a',name:'get_source_health',status:'completed',elapsed:100,input:'{}',result:'full "result"\nwith | pipes',summary:'ok',resources:[{label:'source',url:'https://example.org/'}]}]};
 const text=P.luaTable('WoWAI_Inbox',[{chat:'c',id:1,status:'done',text:'x'.repeat(9000)+'THE END',research:r,resources:r.calls[0].resources}],{restore:{token:'t',chats:[{id:'c2',messages:[{role:'assistant',id:1,text:'y'.repeat(9000)+'RESTORE END',research:r}]}]}});
 luaparse.parse(text,{luaVersion:'5.1'});
 assert.ok(text.includes('THE END'));assert.ok(text.includes('RESTORE END'));assert.ok(text.includes('get_source_health'));
 assert.ok(text.includes('https://example.org/'));
 assert.equal(A.snippet('z'.repeat(800)).length,800);
});
test('actual tool duration works without a start event, missing timings stay unknown',()=>{
 const j=new R.Journal();
 j.feed({type:'item.completed',item:{type:'McpToolCall',id:'a',tool:'lookup',duration:{secs:1,nanos:500000000},result:'ok'}},'codex');
 j.feed({type:'item.completed',item:{type:'mcp_tool_call',id:'b',tool:'lookup',result:'ok'}},'codex');
 assert.equal(j.full()[0].elapsed,1500); assert.equal(j.full()[1].elapsed,undefined);
});
test('item and spell source buttons use only explicit IDs returned by tools',()=>{
 const resources=R.resources({content:[{type:'text',text:JSON.stringify({items:[{item_id:4306,name:'Silk Cloth'},{item_id:-1,name:'Invalid'},{spell_id:123,name:'A Spell'}]})}]});
 assert.deepEqual(resources.map(r=>[r.kind,r.id]),[['item',4306],['spell',123]]);
});

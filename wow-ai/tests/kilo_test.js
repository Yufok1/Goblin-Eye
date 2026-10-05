'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('fs'),path=require('path'),A=require('../bridge/agents'),R=require('../bridge/research');
test('Kilo preserves stdin, resume, model, variant, and image arguments',()=>{
 const cfg={model:'provider/free-model',variant:'low',permissionMode:'default'};
 const args=A.AGENTS.kilo.args({cfg,cwd:'C:\\research',resume:'ses_1',images:['a.png','-evil']});
 assert.deepEqual(args,['run','--format','json','--dir','C:\\research','--agent','goblin-research','-m','provider/free-model','--variant','low','-s','ses_1','-f','a.png']);
 assert.equal(A.AGENTS.kilo.input({prompt:'x'.repeat(40000),system:'full',systemShort:'short',resume:'ses_1'}).stdin,A.contextBlock('short')+'x'.repeat(40000));
 for(const permissionMode of ['acceptEdits','bypassPermissions']) {
  assert.ok(A.AGENTS.kilo.args({cfg:{permissionMode},cwd:'.'}).includes('--auto'));
  assert.ok(!A.AGENTS.kilo.args({cfg:{permissionMode,researchOnly:true},cwd:'.'}).includes('--auto'));
 }
 const env=A.AGENTS.kilo.env({PATH:'x',KILO_CONFIG_CONTENT:JSON.stringify({model:'keep',agent:{other:{mode:'primary'}}})},{});
 const c=JSON.parse(env.KILO_CONFIG_CONTENT),p=c.agent['goblin-research'].permission;
 assert.equal(c.model,'keep');assert.ok(c.agent.other);assert.equal(p['*'],'deny');assert.equal(p['goblin-eye_get_source_health'],'allow');assert.equal(p.bash,undefined);assert.equal(p.edit,undefined);
 assert.throws(()=>A.AGENTS.kilo.env({KILO_CONFIG_CONTENT:'bad'},{}),/valid JSON/);
 assert.throws(()=>A.AGENTS.kilo.args({cfg:{permissionMode:'typo'},cwd:'.'}),/permissionMode/);
});
test('Kilo tool rounds do not end the turn; private reasoning and unusable Allow buttons are excluded',()=>{
 const p=A.kiloParser();
 assert.deepEqual(p.feed({type:'reasoning',part:{text:'private'}}).progress,[]);
 assert.equal(p.feed({type:'step_finish',sessionID:'ses_1',part:{reason:'tool-calls'}}).done,undefined);
 p.feed({type:'text',part:{text:'Narration'}});p.feed({type:'text',part:{text:'Answer\nTL;DR: Herbs'}});
 assert.equal(p.feed({type:'step_finish',part:{reason:'stop'}}).done.text,'Answer\nTL;DR: Herbs');
 const refusal=p.feed({type:'tool_use',part:{tool:'bash',state:{status:'denied',input:{command:'echo test'}}}});
 assert.deepEqual(refusal.denied,[]);assert.ok(!refusal.notes.join('').includes('Allow button below'));
 assert.equal(p.feed({type:'error',error:{name:'APIError',data:{message:'Actual failure'}}}).done.text,'Actual failure');
 assert.equal(p.feed({type:'step_finish',part:{reason:'length'}}).done.error,true);
});
test('Kilo cards preserve namespaced MCP output, status, identity, timing and source links',()=>{
 const j=new R.Journal();
 const part={type:'tool',id:'prt_1',callID:'call_1',tool:'goblin-eye_get_item_market_context',state:{status:'completed',input:{item_id:4306},time:{start:100,end:240},output:JSON.stringify({item_id:4306,item_name:'Silk',market_key:'wow-forever',snapshot:{source_key:'ahledger'},totals:{listing_count:4,listed_units:20,min_unit_buyout_copper:500},source_url:'https://example.org/'})}};
 j.feed({type:'tool_use',part},'kilo');
 const c=j.wire().calls[0];assert.equal(c.id,'call_1');assert.equal(c.elapsed,140);assert.equal(c.status,'completed');assert.ok(c.input.includes('4306'));assert.ok(c.resources.some(r=>r.url==='https://example.org/'));assert.ok(j.wire().cards.length>0);
 j.feed({type:'tool_use',part:{...part,state:{...part.state,status:'error',output:undefined,error:'Failed'}}},'kilo');assert.equal(j.full().length,1);assert.equal(j.full()[0].status,'error');
 assert.equal(j.feed({type:'reasoning',part:{text:'private'}},'kilo'),false);
});
test('recorded Kilo 7.8.3 MCP stream finishes only after its answer and retains one call',()=>{
 const events=fs.readFileSync(path.join(__dirname,'fixtures/agents/kilo-health.jsonl'),'utf8').trim().split(/\r?\n/).map(JSON.parse),p=A.kiloParser(),j=new R.Journal();let done;
 for(const e of events){const r=p.feed(e);j.feed(e,'kilo');if(e.type==='step_finish'&&e.part.reason==='tool-calls')assert.equal(r.done,undefined);if(r.done)done=r.done;}
 assert.equal(done.error,false);assert.match(done.text,/KILO_OK/);assert.equal(j.full().length,1);assert.equal(j.full()[0].name,'goblin-eye_get_source_health');assert.equal(j.full()[0].status,'completed');
 const q=A.kiloParser();q.feed({type:'text',part:{id:'p1',messageID:'m',text:'Part one'}});q.feed({type:'text',part:{id:'p2',messageID:'m',text:'Part two'}});q.feed({type:'text',part:{id:'p2',messageID:'m',text:'Part two updated'}});assert.equal(q.feed({type:'step_finish',part:{reason:'stop'}}).done.text,'Part one\nPart two updated');
});

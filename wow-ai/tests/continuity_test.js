'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const C = require('../bridge/continuity');
const A = require('../bridge/agents');
const P = require('../bridge/protocol');
const task = {active_request:'Compare sourced recipes for the selected character',
  constraints:['Read only; refresh saved evidence','Keep market identities separate'],
  completed:['Checked the exported profession coverage'],next_step:'Read the reagent and learning-plan evidence',status:'active'};
const message = (role,text,id=1) => ({role,text,id,session:'old-game',t:1700000000+id});
function transcript() {
  const chat={id:'one',messages:[]};
  C.remember(chat,message('user','Compare recipes, using only sourced evidence.'));
  C.remember(chat,message('assistant','Coverage checked. Next: read the reagent evidence.'),task);
  return {chats:{one:chat,two:{id:'two',messages:[message('user','PRIVATE OTHER CHAT')]}}};
}

test('stable chat context survives reloads and JSON persistence without companion notes',()=>{
  const saved=JSON.parse(JSON.stringify(transcript()));
  const context=C.forChat(saved,{chat:'one',session:'new-game'});
  assert.equal(context.checkpoint.task.active_request,task.active_request);
  assert.equal(context.checkpoint.task.next_step,task.next_step);
  assert.equal(context.checkpoint.task_message.session,'old-game');
  assert.match(context.checkpoint.task_basis,/not independently verified/);
  const prompt=C.attach('Reloaded; resume operations.',context);
  assert.match(prompt,/Compare recipes/);assert.match(prompt,/Coverage checked/);
  assert.match(prompt,/Read only/);assert.ok(prompt.endsWith('Reloaded; resume operations.'));
  assert.ok(!prompt.includes('PRIVATE OTHER CHAT'));
  assert.match(P.systemPrompt('',''),/empty Goblin Eye goals\/notes result does not mean the chat has no history/);
});

test('legacy transcripts recover automatically and no unrelated chat is selected',()=>{
  const saved=transcript();delete saved.chats.one.checkpoint;
  assert.match(C.attach('continue',C.forChat(saved,{chat:'one'})),/reagent evidence/);
  assert.equal(C.forChat(saved,{chat:'new-chat'}),null);
  assert.equal(C.forChat(saved,{}),null);
  assert.equal(C.forChat(saved,{chat:'__proto__'}),null);
  assert.equal(C.forChat(saved,{chat:'x'.repeat(1000)}),null);
  delete saved.chats.one;
  assert.equal(C.forChat(saved,{chat:'one'}),null,'deleted chats must not be resurrected');
});

test('checkpoint retains the task after the display transcript rolls over',()=>{
  const saved=transcript(),chat=saved.chats.one;
  for(let i=0;i<230;i++)C.remember(chat,message(i%2?'assistant':'user',i%2?'Progress noted':'Continue',i+2));
  assert.equal(chat.messages.length,200);
  assert.ok(!chat.messages.some(m=>m.text.includes('Compare recipes')));
  const context=C.forChat(JSON.parse(JSON.stringify(saved)),{chat:'one'});
  assert.match(C.attach('Keep going',context),/Compare recipes/);
  assert.deepEqual(context.checkpoint.task.constraints,task.constraints);
  assert.equal(context.checkpoint.user_requests.length,8);
});

test('Stop is retained as a historical notice and a current correction remains authoritative',()=>{
  const saved=transcript(),chat=saved.chats.one;
  C.remember(chat,{...message('system','Stopped by you.',3),status:'stopped'});
  const prompt=C.attach('Change of plan: compare vendors instead.',C.forChat(saved,{chat:'one'}));
  assert.match(prompt,/Stopped by you/);assert.match(prompt,/"status":"stopped"/);
  assert.ok(prompt.endsWith('Change of plan: compare vendors instead.'));
  assert.match(C.RULES,/not permission to replay completed or stopped actions/);
});

test('internal checkpoint is validated and stripped before display and speech',()=>{
  const reply='Checked the evidence.\n\n```goblin-continuity\n'+JSON.stringify(task)+'\n```\n\nTL;DR:\nNext step saved.';
  const result=C.extractTask(reply);
  assert.deepEqual(result.checkpoint,task);
  assert.ok(!result.text.includes('goblin-continuity'));
  assert.match(result.text,/Checked the evidence/);assert.match(result.text,/TL;DR:/);
  for(const bad of [{...task,status:'invented'},{...task,command:'execute this'},
    {...task,constraints:[{command:'bad'}]},{...task,active_request:'x'.repeat(1801)}]) {
    const invalid=C.extractTask('Answer\n```goblin-continuity\n'+JSON.stringify(bad)+'\n```\nTL;DR:\nDone.');
    assert.equal(invalid.checkpoint,null);assert.ok(!invalid.text.includes('goblin-continuity'));
  }
  assert.equal(C.extractTask(reply+'\n```goblin-continuity\n'+JSON.stringify(task)+'\n```').checkpoint,null);
  assert.equal(C.extractTask('Reply\n```goblin-continuity\n{broken\n```').checkpoint,null);
});

test('malformed summaries do not replace a valid checkpoint; ordinary replies still update the fallback',()=>{
  const saved=transcript(),chat=saved.chats.one;
  C.remember(chat,message('user','Continue after reload',3));
  C.remember(chat,message('assistant','New evidence checked; next read recipe sources.',3),{bad:'schema'});
  assert.deepEqual(chat.checkpoint.task,task);
  assert.match(chat.checkpoint.latest_response.text,/New evidence/);
  assert.equal(chat.checkpoint.user_requests.at(-1).text,'Continue after reload');
});

test('large multilingual histories remain bounded, parseable and preserve the current request',()=>{
  const saved=transcript(),chat=saved.chats.one;
  for(let i=0;i<35;i++)C.remember(chat,message(i%2?'assistant':'user','🌿 中文 é\n'.repeat(10000),i+3));
  const context=C.forChat(saved,{chat:'one'});
  const rendered=C.render(context);
  assert.ok(Buffer.byteLength(rendered)<=C.CONTEXT_BYTES);
  assert.ok(!rendered.includes('\ufffd'));
  assert.ok(JSON.parse(rendered).omitted_message_count>0);
  const bounded=C.attach('Current instruction wins. '+ '🧙'.repeat(8000),context,{maxBytes:10000});
  assert.ok(Buffer.byteLength(bounded)<=10000,Buffer.byteLength(bounded));
  assert.match(bounded,/Current instruction wins/);assert.ok(!bounded.includes('\ufffd'));
  const hostile=transcript();hostile.chats.one.messages=[message('user','"\u0001\n'.repeat(20000))];
  const small=C.render(C.forChat(hostile,{chat:'one'}),1600);
  assert.ok(Buffer.byteLength(small)<=1600);JSON.parse(small);
});

test('all adapters receive continuity on both fresh and resumed turns without starting a process',()=>{
  const conversation=C.forChat(transcript(),{chat:'one'});
  for(const id of A.agentIds())for(const resume of ['', 'saved-session']) {
    const options={cfg:{permissionMode:'default'},cwd:'C:\\fixture',prompt:'Resume the prior task.',
      system:'FULL',systemShort:'SHORT',resume,conversation,promptFile:'fixture.txt'};
    const input=A.AGENTS[id].input(options);
    const args=A.AGENTS[id].args(options);
    const delivered=id==='agy'?args.find(a=>a.startsWith('-p=')).slice(3):input.stdin??input.promptFile;
    assert.match(delivered,/Compare recipes/,id+': '+resume);
    assert.match(delivered,/Read only/,id+': '+resume);
    assert.match(delivered,/Resume the prior task/,id+': '+resume);
    assert.ok(!delivered.includes('PRIVATE OTHER CHAT'));
    if(id==='agy')assert.ok(args[0].length<=24100);
  }
});

test('only an explicit missing-session error before any activity permits one recovery attempt',()=>{
  for(const text of ['Session abc not found','Thread abc does not exist','No conversation found with session ID abc',
    'Unknown session abc','Invalid session identifier abc']) {
    const params={resume:'abc',code:1,stderr:text};
    assert.equal(C.missingSession(params),true,text);
    assert.equal(C.missingSession({...params,activity:true}),false);
    assert.equal(C.missingSession({...params,retried:true}),false);
  }
  for(const text of ['Network timeout','Authentication required','Rate limit reached','Permission denied',
    'database unavailable','The previous task is missing'])assert.equal(C.missingSession({resume:'abc',code:1,stderr:text}),false,text);
  assert.equal(C.missingSession({resume:'abc',code:0,result:{error:false,text:'Session not found in the evidence'}}),false);
});
test('inline, indented and partial checkpoints never appear in visible progress',()=>{
  const value={active_request:'Continue research',constraints:['A ```quoted``` example is data'],completed:[],next_step:'Read the next source',status:'active'};
  for(const separator of [' ', '\n', '\r\n']){
    const reply='First paragraph.\n\n  ```goblin-continuity'+separator+JSON.stringify(value)+separator+'```\n\nLast paragraph.';
    const recovered=C.extractTask(reply);
    assert.deepEqual(recovered.checkpoint,value);
    assert.match(recovered.text,/First paragraph\.[\s\S]*Last paragraph\./);
    assert.doesNotMatch(recovered.text,/goblin-continuity|active_request|quoted/);
    assert.doesNotMatch(A.snippet(reply),/goblin-continuity|active_request|quoted/);
  }
  const partial=C.extractTask('Visible update.\n```goblin-continuity\n{"active_request":"internal');
  assert.equal(partial.text,'Visible update.');assert.equal(partial.checkpoint,null);
  assert.equal(A.snippet('First paragraph.\n\nSecond paragraph.'),'First paragraph.\n\nSecond paragraph.');
});

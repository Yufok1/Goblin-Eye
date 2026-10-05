'use strict';
const test = require('node:test'), assert = require('node:assert/strict');
const {SnapshotWriter} = require('../bridge/publisher');
const {shouldBeat} = require('../bridge/activity');
const R = require('../bridge/research');

test('snapshot publication waits for every file and limits concurrent disk work', async () => {
  let active = 0, peak = 0;
  const completed = [];
  const writer = new SnapshotWriter({concurrency:4, write:async(file, data) => {
    active++; peak = Math.max(peak, active);
    await new Promise(resolve => setTimeout(resolve, 3));
    completed.push([file, data]); active--;
  }});
  const files = Array.from({length:201}, (_,i) => ({file:String(i), data:'final'}));
  const result = await writer.enqueue(files);
  assert.equal(completed.length,201); assert.equal(result.written,201);
  assert.equal(peak,4); assert.deepEqual(result.failures,[]);
});

test('pending progress snapshots collapse to the latest while retaining all completion waiters', async () => {
  let release;
  const gate = new Promise(resolve => release = resolve), written=[];
  const writer = new SnapshotWriter({write:async(file,data) => {if(data==='first') await gate; written.push(data);}});
  const one = writer.enqueue([{file:'1',data:'first'}], 'first context');
  const two = writer.enqueue([{file:'1',data:'obsolete'}], 'obsolete context');
  let finalFinished = false;
  const three = writer.enqueue([{file:'1',data:'final'}], 'final context').then(r=>{finalFinished=true;return r;});
  await Promise.resolve(); assert.equal(finalFinished,false); release();
  const results = await Promise.all([one,two,three]);
  assert.deepEqual(written,['first','final']);
  assert.equal(results[1].batchId,results[2].batchId);
  assert.equal(results[1].context,'final context');
  assert.equal(writer.stats.coalesced,1);
});

test('failed disk writes are reported and do not prevent later snapshots', async () => {
  const writer = new SnapshotWriter({write:async(file) => {if(file==='bad') throw Object.assign(new Error('denied'),{code:'EACCES'});}});
  const result = await writer.enqueue([{file:'bad',data:'x'},{file:'good',data:'x'}]);
  assert.equal(result.written,1); assert.equal(result.failures[0].code,'EACCES');
  assert.equal((await writer.enqueue([{file:'good',data:'y'}])).written,1);
});

test('tool bursts do not exhaust the existing 60 liveness files', () => {
  const job = {}; let beats = 0;
  for(let now=0;now<1800000;now+=100) if(shouldBeat(job,now)) beats++;
  assert.equal(beats,60);
  assert.equal(shouldBeat(job,1799900),false);
});

test('tool previews are reused until evidence or archive identity changes', () => {
  const journal = new R.Journal();
  journal.feed({type:'item.started',item:{type:'mcp_tool_call',id:'a',tool:'lookup',arguments:{id:1}}},'codex');
  const one = journal.wire('a.json');
  assert.equal(journal.wire('a.json'),one);
  journal.feed({type:'item.completed',item:{type:'agent_message',text:'unrelated'}},'codex');
  assert.equal(journal.wire('a.json'),one);
  journal.feed({type:'item.completed',item:{type:'mcp_tool_call',id:'a',tool:'lookup',result:'done'}},'codex');
  assert.notEqual(journal.wire('a.json'),one);
  assert.notEqual(journal.wire('b.json'),journal.wire('a.json'));
});

test('interleaved tool completions identify the actual updated call',()=>{
 const journal=new R.Journal();
 for(const id of ['first','second'])journal.feed({type:'item.started',item:{type:'mcp_tool_call',id,tool:id}},'codex');
 journal.feed({type:'item.completed',item:{type:'mcp_tool_call',id:'first',tool:'first',result:'done'}},'codex');
 assert.equal(journal.lastUpdated.name,'first');assert.equal(journal.lastUpdated.status,'completed');
 assert.equal(journal.full()[1].status,'running');
});

'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path');
const E=require('../bridge/evidence'),R=require('../bridge/research'),P=require('../bridge/protocol');
const luaparse=require('luaparse');
const fixture=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures/evidence.json'),'utf8'));
const call=(id,data)=>({id,name:'goblin_eye.'+id,status:'completed',raw_result:{structuredContent:{result:data}}});
const field=(c,label)=>c.fields.find(f=>f.label===label)?.value;

test('synthetic local depth, identity, aggregate, acquisition and coverage remain distinct evidence cards',()=>{
 const {cards}=E.cardsForCalls(Object.entries(fixture).map(([k,v])=>call(k,v)));
 assert.equal(cards.length,5);
 const depth=cards.find(c=>c.type==='price'),aggregate=cards.find(c=>c.type==='aggregate');
 assert.equal(depth.title,'Bruiseweed');assert.equal(depth.headline,'0g 5s 91c / unit');
 assert.equal(depth.market_key,'wow-forever');assert.equal(depth.source_key,'local-ahledger');
 assert.equal(field(depth,'Listed units'),'2017');
 assert.equal(depth.captured_at,'2026-10-04T14:43:56+00:00');assert.ok(depth.captured_epoch>0);
 assert.equal(aggregate.source_key,'local-auctionator');assert.equal(aggregate.capture_precision,'date');
 assert.equal(aggregate.captured_at,'2026-10-04');assert.equal(aggregate.captured_epoch,0);
 assert.equal(field(aggregate,'Recorded quantity'),'2715');
 assert.equal(cards.find(c=>c.type==='acquisition').badge,'Classic baseline');
 assert.equal(field(cards.find(c=>c.type==='coverage'),'Region'),'unknown');
 for(const c of cards.filter(c=>c.item_id>0))assert.equal(field(c,'Gathering requirement'),'Unknown / not supplied');
});

test('recipe skill and item confidence do not become gathering skill or price confidence',()=>{
 const item=structuredClone(fixture.item);item.skill_required=100;item.profession='Alchemy';
 const depth=structuredClone(fixture.depth);delete depth.snapshot.confidence;
 const cards=E.cardsForCalls([call('item',item),call('depth',depth)]).cards;
 const price=cards.find(c=>c.type==='price');
 assert.equal(field(price,'Source score'),undefined);
 assert.equal(field(cards.find(c=>c.type==='item'),'Gathering requirement'),'Unknown / not supplied');
 depth.gathering_requirement={profession:'Herbalism',skill_required:100,source_key:'explicit-source'};
 assert.equal(field(E.cardsForCalls([call('depth',depth)]).cards[0],'Gathering requirement'),'Herbalism 100');
});

test('community markets are never pooled with local prices or borrowing another markets newer timestamp',()=>{
 const peer=structuredClone(fixture.depth);peer.market_key='forever.normal.alliance.us';peer.snapshot.source_key='ahledger';
 const cards=E.cardsForCalls([call('local',fixture.depth),call('peer',peer),call('health',fixture.health)]).cards;
 assert.equal(cards.filter(c=>c.type==='price').length,2);
 const coverage=cards.find(c=>c.type==='coverage');
 assert.equal(coverage.captured_at,fixture.depth.snapshot.captured_at);
 assert.notEqual(coverage.captured_at,'2026-10-04T16:34:46+00:00');
});

test('capture time never falls back to import time and missing scan does not imply zero stock',()=>{
 const depth=structuredClone(fixture.depth);delete depth.snapshot.captured_at;
 const c=E.cardsForCalls([call('depth',depth)]).cards[0];
 assert.equal(c.capture_precision,'unknown');assert.equal(c.captured_epoch,0);
 const missing=E.cardsForCalls([call('missing',{item_id:2453,market_key:'wow-forever',data_available:false})]).cards[0];
 assert.equal(field(missing,'Listed units'),undefined);assert.ok(missing.notes.some(s=>s.includes('availability is unknown')));
});

test('partial listing rows cannot be mistaken for a market minimum and failed calls produce no evidence',()=>{
 assert.equal(E.cardsForCalls([call('partial',fixture.observations.slice(0,2))]).cards.length,0);
 assert.equal(E.cardsForCalls([{...call('error',fixture.depth),status:'error'}]).cards.length,0);
 assert.equal(E.cardsForCalls([{...call('unrelated',fixture.depth),name:'command'}]).cards.length,0);
});

test('zero buyout is not presented as a free item and invalid gathering requirements remain unknown',()=>{
 const data=structuredClone(fixture.depth);
 data.totals.min_unit_buyout_copper=0;data.totals.money_display.min_unit_buyout_copper='0g 0s 0c';
 data.gathering_requirement={profession:'Herbalism',skill_required:-5};
 const c=E.cardsForCalls([call('depth',data)]).cards[0];
 assert.equal(c.headline,'No buyout quoted');assert.equal(field(c,'Gathering requirement'),'Unknown / not supplied');
});

test('supported text MCP envelopes serialize bounded cards safely through a journal and restore',()=>{
 const j=new R.Journal();
 j.feed({type:'item.completed',item:{type:'mcp_tool_call',id:'price',server:'goblin_eye',tool:'get_market_depth',result:{content:[{type:'text',text:JSON.stringify(fixture.depth)}]}}},'codex');
 const research=j.wire();assert.equal(research.cards.length,1);
 const src=P.luaTable('WoWAI_Inbox',[{chat:'c',id:1,text:'Evidence',status:'done',research}],{restore:{token:'t',chats:[{id:'c',messages:[{role:'assistant',id:1,text:'a',research}]}]}});
 luaparse.parse(src,{luaVersion:'5.1'});assert.ok(src.includes('0g 5s 91c / unit'));assert.ok(src.includes('captured_epoch ='));
 const calls=Array.from({length:35},(_,i)=>call(String(i),{...fixture.depth,item_id:100+i}));
 const result=E.cardsForCalls(calls);assert.ok(result.cards.length<=20);assert.equal(result.cards_omitted,35-result.cards.length);
 assert.ok(result.cards.reduce((n,c)=>n+Buffer.byteLength(JSON.stringify(c)),0)<=E.CARD_BYTE_BUDGET);
});

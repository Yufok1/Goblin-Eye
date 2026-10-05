'use strict';
// Presentation adapters for observed Goblin Eye response shapes. No inferred
// demand, sale value, gathering skill, confidence percentage or market pooling.
const MAX_CARDS = 20;
const CARD_BYTE_BUDGET = 24000;
const text = v => typeof v === 'string' || typeof v === 'number' ? Array.from(String(v)).slice(0,240).join('') : '';
const validId = v => Number.isSafeInteger(v) && v > 0 && v < 2147483648;
function roots(value, depth=0) {
  if (depth>5 || value == null) return [];
  if (typeof value === 'string') { try{return roots(JSON.parse(value),depth+1);}catch{return [];} }
  if (Array.isArray(value)) return value.slice(0,100);
  if (typeof value !== 'object') return [];
  if (value.isError) return [];
  if (value.structuredContent) return roots(value.structuredContent,depth+1);
  if (Object.hasOwn(value,'result') && !value.item_id) return roots(value.result,depth+1);
  if (Array.isArray(value.content)) return value.content.filter(c=>c.type==='text').slice(0,8).flatMap(c=>roots(c.text,depth+1));
  return [value];
}
function fact(card,label,value) {
  const v=text(value);
  if(v && card.fields.length<10) card.fields.push({label,value:v});
}
function note(card,value) {
  const v=text(value);
  if(v && !card.notes.includes(v) && card.notes.length<4)card.notes.push(v);
}
function card(call,type,title,data={}) {
  return {key:call.id+':'+type+':'+(data.item_id||data.market_key||''),type,title:text(title),
    item_id:validId(data.item_id)?data.item_id:0,market_key:text(data.market_key),source_key:text(data.source_key),
    captured_at:'',captured_epoch:0,capture_precision:'unknown',headline:'',badge:'',fields:[],notes:[],tool_id:text(call.id)};
}
function score(c,value) {
  if(Number.isFinite(value)){fact(c,'Source score',value);note(c,'Source score is a policy assessment, not a sale or drop probability.');}
}
function capture(c,value,precision='exact') {
  if(typeof value !== 'string')return;
  if(/^\d{4}-\d{2}-\d{2}$/.test(value)){c.captured_at=value;c.capture_precision='date';return;}
  // Never turn a retrieval/import timestamp into an auction capture time.
  if(/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))){c.captured_at=value;c.captured_epoch=Math.floor(Date.parse(value)/1000);c.capture_precision=precision;}
}
function money(data,key) {
  if(data?.[key] === null || Number.isFinite(data?.[key]) && data[key]<=0)return '';
  return text(data?.money_display?.[key]) || (Number.isFinite(data?.[key]) ? data[key]+' copper' : '');
}
function gathering(c,data) {
  const r=data.gathering_requirement;
  if(r && typeof r==='object' && typeof r.profession==='string' && Number.isSafeInteger(r.skill_required) && r.skill_required>=0) {
    fact(c,'Gathering requirement',r.profession+' '+r.skill_required);
    fact(c,'Requirement source',r.source_key||'not supplied');
  } else fact(c,'Gathering requirement','Unknown / not supplied');
}
function extract(call,data) {
  if(!data || typeof data !== 'object')return null;
  if(validId(data.item_id) && (data.snapshot && data.totals || data.data_available===false && data.market_key)) {
    const s=data.snapshot||{},t=data.totals||{};
    const c=card(call,'price',data.item_name||'Item #'+data.item_id,{...data,source_key:s.source_key});
    c.badge='Listed asks';c.headline=money(t,'min_unit_buyout_copper')||'No buyout quoted';
    if(money(t,'min_unit_buyout_copper'))c.headline+=' / unit';
    capture(c,s.captured_at);fact(c,'Listed units',t.listed_units);fact(c,'Listings',t.listing_count);
    fact(c,'Bid-only listings',t.bid_only_listings);fact(c,'Build',s.game_build);score(c,s.confidence);
    gathering(c,data);fact(c,'Ruleset / faction',[s.ruleset,s.faction].filter(Boolean).join(' / '));fact(c,'Region',s.region||'Unknown');
    if(data.data_available===false)note(c,'No scan supplied; availability is unknown.');
    else if(s.is_complete!==1)note(c,'Scan completeness is not independently verified.');
    note(c,'Asking prices and listed supply do not establish sales or demand.');return c;
  }
  if(validId(data.item_id) && data.observation_type==='aggregated_price') {
    const c=card(call,'aggregate',data.item_name||'Item #'+data.item_id,data);
    c.badge='Saved aggregate';c.headline=money(data,'current_min_unit_copper')||'Price not supplied';
    if(money(data,'current_min_unit_copper'))c.headline+=' / unit';
    capture(c,data.observed_date);fact(c,'Recorded quantity',data.available_quantity);score(c,data.confidence);
    gathering(c,data);note(c,'Daily aggregate; exact scan time is unknown.');
    note(c,'Asking prices do not establish sales or current availability.');return c;
  }
  if(validId(data.item_id) && typeof data.name==='string' && data.identity_selection_policy) {
    const c=card(call,'item',data.name,data);c.badge='Item facts';c.headline=text(data.quality)||'Quality unknown';
    fact(c,'Item level',data.item_level);fact(c,'Required character level',data.required_level);
    gathering(c,data);fact(c,'Retrieved at',data.retrieved_at);fact(c,'Recipes consuming item',data.recipes?.consumes?.total);
    fact(c,'Acquisition associations',data.acquisition?.total);fact(c,'Build',data.game_build||'Unspecified');
    score(c,data.confidence);note(c,'Item facts do not establish local prices or a farming recommendation.');return c;
  }
  if(validId(data.item_id) && Array.isArray(data.records) && data.records.some(r=>r.method && r.entity_type)) {
    const rows=data.records,first=rows[0]||{},ev=data.evidence?.[first.evidence_ref]||{};
    const c=card(call,'acquisition',first.item_name||'Item #'+data.item_id,{...data,source_key:first.source_key||ev.source_key});
    const bases=[...new Set(rows.map(r=>r.evidence_basis).filter(Boolean))];
    c.badge=bases.includes('classic_baseline')?'Classic baseline':'Acquisition evidence';
    c.headline=rows.length+' shown of '+(data.total??'unknown')+' associations';
    fact(c,'Methods',[...new Set(rows.map(r=>r.method))].join(', '));
    fact(c,'Shown source entities',[...new Set(rows.map(r=>r.entity_name).filter(Boolean))].slice(0,4).join(', '));
    gathering(c,data);fact(c,'Retrieved at',ev.retrieved_at||first.retrieved_at);fact(c,'Evidence basis',bases.join(', ')||'Unspecified');
    fact(c,'Next page offset',data.next_offset);score(c,ev.confidence);
    if(data.truncated || data.next_offset!=null)note(c,'Partial page; more source records exist.');
    if(data.complete_loot_table!==true)note(c,'This is not a verified complete loot table.');
    if(bases.includes('classic_baseline'))note(c,'Classic baseline associations are not verified live Forever spawns.');return c;
  }
  if(data.auction_context && Array.isArray(data.sources) && Array.isArray(data.markets)) {
    const profile=data.auction_context,m=data.markets.find(m=>m.market_key===data.market_key)||{};
    const c=card(call,'coverage','Market & source coverage',{market_key:data.market_key});c.badge='Coverage';
    c.headline=data.sources.length+' saved source records';capture(c,m.latest_listing_scan||m.latest_precise_price_capture||m.latest_aggregate_date);
    fact(c,'Ruleset',profile.ruleset||'Unknown');fact(c,'Faction',profile.faction||'Unknown');fact(c,'Region',profile.region||'Unknown');
    fact(c,'Realm',profile.realm||'Unknown');fact(c,'File import errors',data.file_import_error_count);
    const failures=data.sources.filter(s=>s.last_error);fact(c,'Sources reporting errors',failures.length);
    if(profile.region==='unknown'||!profile.region)note(c,'Region is unconfirmed.');
    if(failures.length)note(c,failures.map(s=>s.source_key).join(', '));
    note(c,'Counts describe saved coverage, not a fresh game scan.');return c;
  }
  return null;
}
function cardsForCalls(calls) {
  calls=calls.filter(c=>/goblin[-_]eye/.test(c.name||'') || c.name==='exec' && /mcp__goblin_eye__/.test(c.input||''));
  const identities=new Map(),cards=[],seen=new Set();
  for(const call of calls)if(call.status==='completed')for(const data of roots(call.raw_result))
    if(validId(data?.item_id) && data.identity_selection_policy && typeof data.name==='string')identities.set(data.item_id,data);
  for(const call of calls) {
    if(call.status!=='completed')continue;
    for(const data of roots(call.raw_result)) {
      const c=extract(call,data);if(!c)continue;
      const identity=identities.get(c.item_id);
      if(identity && c.title==='Item #'+c.item_id){c.title=text(identity.name);fact(c,'Name source',identity.source_key||'Unspecified');}
      // Exact provenance identity only; local/public markets and aggregate/depth
      // remain separate. Keep different scans as distinct comparisons.
      const key=[c.type,c.item_id,c.market_key,c.source_key,c.captured_at,data.snapshot?.id,data.snapshot?.game_build].join('|');
      if(seen.has(key))continue;seen.add(key);cards.push(c);
    }
  }
  const selected=[];let bytes=0;
  for(let i=cards.length-1;i>=0 && selected.length<MAX_CARDS;i--) {
    const size=Buffer.byteLength(JSON.stringify(cards[i]));
    if(bytes+size>CARD_BYTE_BUDGET)continue;
    selected.unshift(cards[i]);bytes+=size;
  }
  return {cards:selected,cards_omitted:cards.length-selected.length};
}
module.exports={cardsForCalls,roots,MAX_CARDS,CARD_BYTE_BUDGET};

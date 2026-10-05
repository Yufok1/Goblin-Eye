'use strict';
// Observable tool inputs/results only. Never capture private reasoning or session metadata.
const LIMIT = 12000;
const Evidence = require('./evidence');
const canonical = s => String(s || '').replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();
function redact(value) {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) =>
    [k, /^(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|credential)$/i.test(k) ? '[redacted]' : redact(v)]));
  return typeof value === 'string' ? value.replace(/\bBearer\s+[A-Za-z0-9._~-]+/gi, 'Bearer [redacted]') : value;
}
function printable(value) {
  if (value == null) return '';
  if (typeof value === 'string') {
    try { return JSON.stringify(redact(JSON.parse(value)), null, 2); } catch {}
    return redact(value);
  }
  return JSON.stringify(redact(value), null, 2);
}
function preview(text, limit = LIMIT) {
  const chars = Array.from(String(text || ''));
  return chars.length <= limit ? text : chars.slice(0, limit).join('') +
    `\n\n[Showing ${limit} of ${chars.length} characters. This is a preview; the completed reply provides the full research archive.]`;
}
function resultText(result) {
  if (Array.isArray(result?.content)) {
    const blocks = result.content.filter(c => c.type === 'text').map(c => printable(c.text));
    if (blocks.length) {
      const extra = result.content.length - blocks.length;
      return blocks.join('\n\n') + (extra ? `\n\n[${extra} non-text blocks are retained in the archive.]` : '');
    }
  }
  return printable(result);
}
function normalizeCodexEvent(ev) {
  // Older exec JSONL, current desktop item names, and event wrappers.
  if (ev.type === 'event_msg' && ev.payload) ev = ev.payload;
  const type = canonical(ev.type).replace(/^item_(started|completed|updated)$/, 'item.$1');
  if (!ev.item) return { ...ev, type };
  const item = { ...ev.item, type: canonical(ev.item.type) };
  if (!item.text && Array.isArray(item.content)) item.text = item.content.filter(c => canonical(c.type) === 'text').map(c => c.text || '').join('\n');
  return { ...ev, type, item };
}
function events(ev, agent = 'codex') {
  if (agent === 'kilo' && ev.type === 'tool_use' && ev.part?.type === 'tool') {
    const p=ev.part,s=p.state||{},t=s.time||{};
    const status=['error','denied','rejected'].includes(s.status)?'error':s.status==='completed'?'completed':'running';
    if(!p.callID&&!p.id)return []; // never merge unrelated calls by tool name
    return [{id:String(p.callID||p.id),name:p.tool,status,input:s.input,result:s.output,error:s.error,
      durationMs:Number.isFinite(t.end)&&Number.isFinite(t.start)?Math.max(0,t.end-t.start):undefined}];
  }
  if (agent === 'codex') {
    ev = normalizeCodexEvent(ev);
    let i = ev.item;
    // Response items may expose a custom call directly.
    if (ev.type === 'response_item') i = ev.payload;
    if (!i && /^custom_tool_call/.test(canonical(ev.type))) i = ev;
    if (!i) return [];
    const type = canonical(i.type);
    if (!['mcp_tool_call', 'custom_tool_call', 'custom_tool_call_output', 'command_execution', 'web_search'].includes(type)) return [];
    const done = ev.type === 'item.completed' || type === 'custom_tool_call_output' || ['completed', 'failed'].includes(i.status);
    let name = i.tool || i.name || (type === 'command_execution' ? 'command' : type === 'web_search' ? 'web_search' : 'tool');
    if (i.server) name = i.server + '.' + name;
    const result = i.result ?? i.output ?? i.aggregated_output;
    const failed = i.status === 'failed' || i.error || (result && result.isError) || (i.exit_code != null && i.exit_code !== 0);
    return [{ id: String(i.call_id || i.id || name), name,
      status: failed ? 'error' : done ? 'completed' : 'running',
      input: i.arguments ?? i.input ?? i.command ?? i.query,
      result, error: i.error, duration: i.duration, durationMs: i.duration_ms,
      outputOnly: type === 'custom_tool_call_output' }];
  }
  if (agent === 'claude' && ev.type === 'assistant') return (ev.message?.content || []).filter(b => b.type === 'tool_use').map(b =>
    ({ id: b.id, name: b.name, status: 'running', input: b.input }));
  if (agent === 'claude' && ev.type === 'user') return (ev.message?.content || []).filter(b => b.type === 'tool_result').map(b =>
    ({ id: b.tool_use_id, status: b.is_error ? 'error' : 'completed', result: b.content, outputOnly: true }));
  return [];
}
function urls(value) {
  const found = [], seen = new Set();
  const text = printable(value);
  for (const match of text.matchAll(/https?:\/\/[^\s<>"\\]+/g)) {
    const raw = match[0].replace(/[),.;\]]+$/, '');
    try {
      const u = new URL(raw);
      if (u.username || u.password || u.href.length > 2048 || [...u.searchParams.keys()].some(k => /token|api.?key|password|secret/i.test(k)) || seen.has(u.href)) continue;
      if (u.protocol !== 'https:' && !(u.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(u.hostname))) continue;
      seen.add(u.href); found.push({ label: (u.hostname + (u.pathname !== '/' ? u.pathname : '')).slice(0, 200), url: u.href });
      if (found.length === 12) break;
    } catch {}
  }
  return found;
}
function resources(value) {
  const found = urls(value), seen = new Set();
  let visited = 0;
  const visit = data => {
    if (++visited > 3000 || found.length >= 12 || data == null) return;
    if (typeof data === 'string') { try { visit(JSON.parse(data)); } catch {} return; }
    if (typeof data !== 'object') return;
    for (const kind of ['item', 'spell']) {
      const id = data[kind + '_id'];
      if (Number.isSafeInteger(id) && id > 0 && id < 2147483648 && !seen.has(kind + id)) {
        seen.add(kind + id); found.push({ kind, id, label: String(data[kind + '_name'] || data.name || kind + ' #' + id).slice(0, 200), url: '' });
      }
    }
    for (const v of Object.values(data)) visit(v);
  };
  visit(value);
  return found.slice(0, 12);
}
function resultSummary(result) {
  let data = result?.structuredContent?.result || result?.structuredContent || result;
  if (Array.isArray(result?.content)) {
    const text = result.content.filter(c => c.type === 'text').map(c => c.text).join('\n');
    try { data = JSON.parse(text); } catch { if (text) data = text; }
  }
  if (typeof data === 'string') return data.split('\n').find(s => s.trim())?.slice(0, 220) || 'Text returned';
  if (data && typeof data === 'object') {
    const parts = [];
    for (const k of ['market_key', 'queried_at', 'total_snapshots', 'snapshot_count', 'total_items', 'total_listings', 'count', 'next_offset']) {
      if (data[k] != null && typeof data[k] !== 'object') parts.push(k.replace(/_/g, ' ') + ': ' + data[k]);
    }
    for (const [k, v] of Object.entries(data)) if (Array.isArray(v)) parts.push(k.replace(/_/g, ' ') + ': ' + v.length + ' records');
    return parts.slice(0, 5).join(' | ') || 'Returned fields: ' + Object.keys(data).slice(0, 7).join(', ');
  }
  return result == null ? '' : 'Result returned';
}
class Journal {
  constructor(clock = Date.now) { this.clock = clock; this.calls = new Map(); }
  feed(ev, agent) {
    const updates = events(ev, agent);
    if (updates.length) this.wireCache = null;
    for (const e of updates) {
      const old = this.calls.get(e.id) || { id: e.id, started: this.clock(), startKnown: e.status === 'running' };
      if (!e.outputOnly || !old.name) old.name = e.name || old.name || 'tool';
      old.status = e.status;
      if (e.input !== undefined) old.input = printable(e.input);
      if (e.result !== undefined) { old.raw_result = redact(e.result); old.result = resultText(e.result); old.summary = resultSummary(e.result); old.resources = resources(e.result); }
      if (e.error) old.result = printable(e.error);
      if (e.status !== 'running') {
        const duration = Number.isFinite(e.durationMs) ? e.durationMs :
          e.duration && typeof e.duration === 'object' ? (e.duration.secs || 0) * 1000 + (e.duration.nanos || 0) / 1000000 : undefined;
        old.elapsed = duration ?? (old.startKnown ? Math.max(0, this.clock() - old.started) : undefined);
      }
      this.calls.set(e.id, old);
      this.lastUpdated = old;
    }
    return updates.length > 0;
  }
  wire(archive = '') {
    if (this.wireCache?.archive === archive) return this.wireCache;
    const all = [...this.calls.values()];
    const selected = all.slice(-40);
    // Batch a bounded snapshot for the finite addon slots; complete results stay on disk.
    const resultBudget = Math.min(LIMIT, Math.floor(48000 / Math.max(1, selected.length)));
    this.wireCache = { archive, total: all.length, omitted: Math.max(0, all.length - 40), ...Evidence.cardsForCalls(selected),
      calls: selected.map(({ raw_result, ...c }) => ({ ...c, input: preview(c.input || '', Math.min(3000, resultBudget)), result: preview(c.result || '', resultBudget) })) };
    return this.wireCache;
  }
  full() { return [...this.calls.values()]; }
}
module.exports = { Journal, events, normalizeCodexEvent, printable, urls, resources, preview, resultSummary };

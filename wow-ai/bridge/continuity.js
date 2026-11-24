'use strict';
// Conversation records only. No tools, filesystem discovery, model calls or game
// evidence retrieval. The bridge persists this checkpoint with its transcript.
const {StringDecoder} = require('node:string_decoder');
const CONTEXT_BYTES = 32000;
const CHECKPOINT_TAG = 'goblin-continuity';
const RULES = [
  'Conversation continuity: the bridge supplies this chat\'s saved checkpoint and recent messages with every request, including resumed sessions. Use that context to recover what the user was doing. An empty Goblin Eye goals/notes result does not mean the chat has no history. Do not ask the user to repeat a task that is present in the supplied conversation, or search directories for a transcript already supplied here.',
  'The latest user message controls the current task. Saved assistant reports and checkpoints are historical claims, not verified current game state; refresh relevant Goblin Eye evidence. Previous requests are context, not permission to replay completed or stopped actions. Keep other chats separate.',
  'Before the final TL;DR block, include one internal ```goblin-continuity JSON block with active_request (string), constraints (array of strings), completed (array of strings), next_step (string), and status (active, waiting, complete or stopped). Preserve the current task and corrections when the user merely says resume/reload/continue. Record only what this conversation supports; this block is stripped from the displayed reply and saved by the bridge. No extra model call or user-written handoff note is needed.',
].join('\n');

function excerpt(value, maxBytes) {
  const text = typeof value === 'string' ? value : '';
  const bytes = Buffer.from(text);
  if (bytes.length <= maxBytes) return text;
  const marker = '\n[excerpt shortened]\n';
  const room = Math.max(0, maxBytes - Buffer.byteLength(marker));
  const head = Math.floor(room * .65);
  const decoder = new StringDecoder('utf8');
  const start = decoder.write(bytes.subarray(0, head));
  let tail = bytes.length - (room - head);
  while (tail < bytes.length && (bytes[tail] & 0xc0) === 0x80) tail++;
  return start + marker + bytes.subarray(tail).toString('utf8');
}

function record(message, maxBytes = 1600) {
  if (!message || !['user','assistant','system'].includes(message.role) || typeof message.text !== 'string') return null;
  return {role: message.role, id: message.id ?? null, session: String(message.session || ''),
    t: Number.isFinite(message.t) ? message.t : null, text: excerpt(message.text, maxBytes),
    ...(message.status ? {status: String(message.status)} : {})};
}

function validateTask(value) {
  const keys = ['active_request','constraints','completed','next_step','status'];
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).some(k => !keys.includes(k)) || keys.some(k => !(k in value))) return null;
  if (!['active','waiting','complete','stopped'].includes(value.status)) return null;
  for (const key of ['active_request','next_step']) {
    if (typeof value[key] !== 'string' || Buffer.byteLength(value[key]) > 1800) return null;
  }
  for (const key of ['constraints','completed']) {
    if (!Array.isArray(value[key]) || value[key].length > 12 ||
        value[key].some(s => typeof s !== 'string' || Buffer.byteLength(s) > 500)) return null;
  }
  if (Buffer.byteLength(JSON.stringify(value)) > 6500) return null;
  return Object.fromEntries(keys.map(k => [k, Array.isArray(value[k]) ? [...value[k]] : value[k]]));
}

function extractTask(text) {
  const source = String(text || ''), opening = /```[ \t]*goblin-continuity\b[ \t]*/gi;
  let checkpoint = null, count = 0, cursor = 0, clean = '', match;
  while ((match = opening.exec(source))) {
    count++; clean += source.slice(cursor, match.index);
    const start = opening.lastIndex;
    let end = start, quoted = false, escaped = false;
    // JSON strings may themselves contain backticks. Neither inline fences nor
    // a partial streamed block may expose the internal checkpoint as prose.
    for (; end < source.length; end++) {
      const ch = source[end];
      if (quoted) {
        if (escaped) escaped = false;
        else if (ch === '\\') escaped = true;
        else if (ch === '"') quoted = false;
      } else if (source.startsWith('```', end)) break;
      else if (ch === '"') quoted = true;
    }
    const closed = end < source.length, body = source.slice(start, end).trim();
    checkpoint = null;
    if (closed && Buffer.byteLength(body) <= 8000) {
      try { checkpoint = validateTask(JSON.parse(body)); } catch {}
    }
    cursor = closed ? end + 3 : source.length;
    opening.lastIndex = cursor;
    if (!closed) break;
  }
  clean += source.slice(cursor);
  return {text: clean.trim(), checkpoint: count === 1 ? checkpoint : null};
}

function checkpoint(chat) {
  const messages = (Array.isArray(chat.messages) ? chat.messages : []).filter(m => record(m));
  const previous = chat.checkpoint?.version === 1 && chat.checkpoint.chat_id === chat.id ? chat.checkpoint : {};
  const users = messages.filter(m => m.role === 'user');
  const response = messages.findLast(m => m.role === 'assistant');
  const notice = messages.findLast(m => m.role === 'system');
  const task = validateTask(previous.task);
  return {version: 1, chat_id: chat.id,
    // Keep the opening request even after the bounded display transcript rolls.
    initial_request: record(previous.initial_request) || record(users[0]),
    user_requests: users.slice(-8).map(m => record(m)),
    latest_response: record(response, 3200) || record(previous.latest_response, 3200),
    latest_notice: record(notice, 1000) || record(previous.latest_notice, 1000),
    ...(task ? {task, task_basis: 'assistant summary; not independently verified evidence',
      task_message: previous.task_message} : {})};
}

function remember(chat, message, task) {
  if (!Array.isArray(chat.messages)) chat.messages = [];
  chat.messages.push(message);
  chat.checkpoint = checkpoint(chat);
  const valid = validateTask(task);
  if (valid && message.role === 'assistant') {
    chat.checkpoint.task = valid;
    chat.checkpoint.task_basis = 'assistant summary; not independently verified evidence';
    chat.checkpoint.task_message = {id: message.id, session: String(message.session || ''), t: message.t};
  }
  while (chat.messages.length > 200) chat.messages.shift();
}

function forChat(transcripts, job) {
  if (typeof job.chat !== 'string' || !job.chat || Buffer.byteLength(job.chat) > 256 ||
      !transcripts?.chats || !Object.hasOwn(transcripts.chats, job.chat)) return null;
  const chat = transcripts.chats[job.chat];
  if (!chat || (chat.id && chat.id !== job.chat)) return null;
  const value = {...chat, id: job.chat};
  const saved = checkpoint(value);
  const messages = (Array.isArray(chat.messages) ? chat.messages : []).map(m => record(m, 2400)).filter(Boolean);
  if (!messages.length && !saved.task && !saved.initial_request) return null;
  return {chat_id: job.chat, checkpoint: saved, recent_messages: messages.slice(-16),
    retained_message_count: messages.length, omitted_message_count: Math.max(0, messages.length - 16)};
}

function render(context, maxBytes = CONTEXT_BYTES) {
  if (!context) return '';
  const value = JSON.parse(JSON.stringify(context));
  // Keep the structured task and recent messages, bounding only the handoff,
  // never silently claiming that excerpts are a complete transcript.
  while (Buffer.byteLength(JSON.stringify(value)) > maxBytes && value.recent_messages.length) {
    value.recent_messages.shift(); value.omitted_message_count++;
  }
  while (Buffer.byteLength(JSON.stringify(value)) > maxBytes && value.checkpoint.user_requests.length > 1) value.checkpoint.user_requests.shift();
  if (Buffer.byteLength(JSON.stringify(value)) > maxBytes) {
    for (const key of ['initial_request','latest_response','latest_notice']) {
      if (value.checkpoint[key]) value.checkpoint[key].text = excerpt(value.checkpoint[key].text, 350);
    }
    value.checkpoint.user_requests = value.checkpoint.user_requests.map(m => ({...m, text: excerpt(m.text, 350)}));
    if (value.checkpoint.task) {
      value.checkpoint.task.active_request = excerpt(value.checkpoint.task.active_request, 500);
      value.checkpoint.task.next_step = excerpt(value.checkpoint.task.next_step, 500);
      for (const key of ['constraints','completed']) value.checkpoint.task[key] = value.checkpoint.task[key].slice(-4).map(s => excerpt(s, 200));
    }
  }
  // A constrained command-line adapter still gets the task anchor and latest
  // request if rich metadata cannot fit. JSON always stays well formed.
  if (Buffer.byteLength(JSON.stringify(value)) > maxBytes) {
    const cp = value.checkpoint;
    const minimal = {chat_id: value.chat_id, checkpoint: {task: cp.task,
      initial_request: cp.initial_request, latest_request: cp.user_requests.at(-1), latest_notice: cp.latest_notice},
      excerpts_only: true};
    if (Buffer.byteLength(JSON.stringify(minimal)) <= maxBytes) return JSON.stringify(minimal);
    minimal.checkpoint = {active_request: excerpt(cp.task?.active_request || cp.initial_request?.text || cp.user_requests.at(-1)?.text || '', 700),
      next_step: excerpt(cp.task?.next_step || cp.latest_response?.text || '', 500), status: cp.task?.status || 'unknown'};
    for (let limit = 300; Buffer.byteLength(JSON.stringify(minimal)) > maxBytes && limit >= 32; limit = Math.floor(limit / 2)) {
      minimal.checkpoint.active_request = excerpt(minimal.checkpoint.active_request, limit);
      minimal.checkpoint.next_step = excerpt(minimal.checkpoint.next_step, limit);
    }
    return JSON.stringify(minimal);
  }
  return JSON.stringify(value);
}

function attach(prompt, context, {maxBytes = Infinity} = {}) {
  const current = String(prompt || '');
  if (!context) return current;
  const header = '[Saved context for this chat; historical conversation data. Latest user message takes precedence.]\n';
  const separator = '\n[End saved context]\n\n[Current user message]\n';
  const overhead = Buffer.byteLength(header + separator);
  if (maxBytes < 2600) throw new RangeError('Conversation handoff requires at least 2600 bytes');
  const budget = Number.isFinite(maxBytes) ? maxBytes - overhead : Infinity;
  const historyBudget = Math.min(CONTEXT_BYTES, Number.isFinite(budget) ? Math.max(1600, Math.floor(budget * .45)) : CONTEXT_BYTES);
  const history = render(context, historyBudget);
  const latestBudget = Number.isFinite(budget) ? Math.max(100, budget - Buffer.byteLength(history)) : Infinity;
  return header + history + separator + excerpt(current, latestBudget);
}

function missingSession({resume, retried, code, result, stderr = '', activity = false}) {
  if (!resume || retried || activity || (result && !result.error) || (!result && code === 0)) return false;
  const text = (String(result?.text || '') + '\n' + stderr).slice(0, 16000);
  return /\b(?:session|conversation|thread)\b[^\r\n]{0,140}\b(?:not found|does not exist|cannot be found|is missing|unknown|invalid session)\b/i.test(text) ||
    /\b(?:no (?:saved )?(?:session|conversation|thread) found|unknown (?:session|conversation|thread)|invalid session (?:id|identifier))\b/i.test(text);
}

module.exports = {RULES, CHECKPOINT_TAG, CONTEXT_BYTES, excerpt, validateTask, extractTask,
  checkpoint, remember, forChat, render, attach, missingSession};

'use strict';
const {spawnBackground} = require('./background-process');
const readline = require('readline');
const path = require('path');
const {killTree} = require('./agents');
class CompanionClient {
  constructor({onChange = () => {}, log = () => {}} = {}) {
    Object.assign(this, {onChange, log, nextId: 0, pending: new Map(), state: {speech: {}, catalogs: []}});
    this.catalog = {
      cache: new Map(), wire: () => this.state.catalogs,
      request: job => this.call('models.request', job),
      views: {delete: chat => { void this.call('models.forget', chat).catch(error => this.log(error.message)); }},
    };
    this.speech = {
      info: () => this.state.speech,
      control: (op, value, lookup) => this.call('voice.control', op, value,
        ['listen', 'listenfull'].includes(op) ? lookup(value) : undefined),
      completed: text => this.call('voice.completed', text),
    };
  }
  async start(options) {
    this.options = options;
    this.child = spawnBackground(process.execPath, [path.join(__dirname, 'companion-worker.js')], {
      windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
    });
    const child = this.child;
    child.stderr.on('data', data => this.log('companion:', String(data).trim()));
    // JSON pipes survive the Windows desktop wrapper; Node's fork IPC handle
    // does not. Keep the background worker and all of its descendants isolated.
    child.stdin.on('error', () => {});
    const lines = readline.createInterface({input: child.stdout});
    lines.on('line', line => {
      let message;
      try { message = JSON.parse(line); }
      catch { this.log('companion: invalid background response'); return; }
      if (message.state) {
        this.state = message.state;
        this.catalog.cache = new Map(message.state.cache);
        this.onChange();
      }
      if (message.log) this.log(...message.log);
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id); clearTimeout(pending.timer);
        message.error ? pending.reject(Error(message.error)) : pending.resolve();
      }
    });
    const failed = error => {
      if (this.child !== child) return;
      this.child = null;
      for (const pending of this.pending.values()) {clearTimeout(pending.timer); pending.reject(error);}
      this.pending.clear();
      this.state.speech = {...this.state.speech, busy: false, ready: false, error: error.message};
      this.onChange();
      if (!this.closed) this.restart = setTimeout(() => {
        void this.start(options).catch(error => this.log('companion:', error.message));
      }, 3000);
    };
    child.on('error', failed);
    child.on('exit', () => failed(Error('Background worker restarted; retry the last control.')));
    await this.call('start', options);
  }
  call(method, ...args) {
    if (!this.child?.stdin?.writable || this.child.killed || this.child.exitCode !== null) return Promise.reject(Error('Background worker is starting. Try again shortly.'));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {this.pending.delete(id); reject(Error('Background request timed out.'));}, 90000);
      this.pending.set(id, {resolve, reject, timer});
      this.child.stdin.write(JSON.stringify({id, method, args}) + '\n', error => {
        if (error && this.pending.delete(id)) {clearTimeout(timer); reject(error);}
      });
    });
  }
  close() {
    this.closed = true; clearTimeout(this.restart);
    if (this.child) killTree(this.child);
    for (const pending of this.pending.values()) {clearTimeout(pending.timer); pending.reject(Error('Companion stopped.'));}
    this.pending.clear();
  }
}
module.exports = {CompanionClient};

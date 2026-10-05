'use strict';
const fs = require('fs/promises');
const {performance} = require('perf_hooks');
// Same addon files and delivery semantics, with bounded asynchronous disk work.
// There is only one active snapshot; pending progress snapshots collapse to the latest.
class SnapshotWriter {
  constructor({concurrency = 4, write} = {}) {
    this.concurrency = Math.max(1, Math.min(8, concurrency));
    this.write = write || (async (file, data) => { await fs.writeFile(file + '.tmp', data); await fs.rename(file + '.tmp', file); });
    this.pending = null;
    this.active = false;
    this.stats = {batches:0, writes:0, bytes:0, coalesced:0, failures:0, lastMs:0};
  }
  enqueue(files, context) {
    return new Promise(resolve => {
      if (this.pending) {
        this.pending.files = files;
        this.pending.context = context;
        this.pending.waiters.push(resolve);
        this.stats.coalesced++;
      } else this.pending = {files, context, waiters:[resolve]};
      if (!this.active) this.drain();
    });
  }
  async drain() {
    this.active = true;
    while (this.pending) {
      const batch = this.pending; this.pending = null;
      let next = 0, written = 0;
      const failures = [], start = performance.now();
      const worker = async () => {
        while (next < batch.files.length) {
          const {file, data} = batch.files[next++];
          try { await this.write(file, data); written++; this.stats.writes++; this.stats.bytes += Buffer.byteLength(data); }
          catch (error) { failures.push({file, code:error.code || '', message:error.message}); this.stats.failures++; }
        }
      };
      await Promise.all(Array.from({length:Math.min(this.concurrency, batch.files.length)}, worker));
      this.stats.batches++; this.stats.lastMs = performance.now() - start;
      const result = {written, failures, elapsedMs:this.stats.lastMs, batchId:this.stats.batches, context:batch.context};
      for (const resolve of batch.waiters) resolve(result);
    }
    this.active = false;
  }
}
module.exports = {SnapshotWriter};

'use strict';
// A file beat signals liveness, not the number of tools. Leave enough of the
// existing 60 files for long answers instead of consuming several per call.
function shouldBeat(job, now = Date.now(), interval = 30000) {
  if (job.lastBeatAt != null && now - job.lastBeatAt < interval) return false;
  job.lastBeatAt = now;
  return true;
}
module.exports = {shouldBeat};

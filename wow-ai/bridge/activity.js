'use strict';
// A file beat signals liveness, not the number of tools. Leave enough of the
// existing 60 files for long answers instead of consuming several per call.
function shouldBeat(job, now = Date.now(), interval = 30000) {
  if (job.lastBeatAt != null && now - job.lastBeatAt < interval) return false;
  job.lastBeatAt = now;
  return true;
}
function noteActivity(job, now = Date.now()) {
  job.activityEvents = (job.activityEvents || 0) + 1;
  job.lastActivityAt = now;
}
function activitySnapshot(job, now = Date.now()) {
  return {at_ms: now, events: job.activityEvents || 0, beats: job.beats || 0,
    elapsed_ms: Math.max(0, now - (job.startedAt ?? now)),
    last_event_ago_ms: job.lastActivityAt == null ? -1 : Math.max(0, now - job.lastActivityAt)};
}
module.exports = {shouldBeat, noteActivity, activitySnapshot};

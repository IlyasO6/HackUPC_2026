const assert = require("assert");
const runtime = require("../static/js/job_runtime.js");

function runSequence(initialState, events) {
  return events.reduce((state, event) => runtime.applyStreamEvent(state, event), initialState);
}

const created = runtime.normalizeCreateJobPayload({
  job_id: "job-42",
  status: "QUEUED",
});

assert.strictEqual(created.id, "job-42");
assert.strictEqual(created.job_id, "job-42");
assert.strictEqual(created.status, "queued");
assert.strictEqual(created.stream_url, "/api/jobs/job-42/stream");

const finalState = runSequence(
  {
    status: "queued",
    running: true,
    progress: 0,
    message: "",
    error: null,
  },
  [
    { event: "job_started", message: "Started" },
    { event: "job_progress", percent: 35, message: "Searching" },
    { event: "ping" },
    { event: "job_progress", progress: 80, message: "Refining" },
    { event: "job_completed", message: "Done" },
  ]
);

assert.strictEqual(finalState.status, "completed");
assert.strictEqual(finalState.running, false);
assert.strictEqual(finalState.progress, 100);
assert.strictEqual(finalState.message, "Done");
assert.strictEqual(finalState.error, null);

const failedState = runtime.applyStreamEvent(
  {
    status: "running",
    running: true,
    progress: 40,
    message: "",
    error: null,
  },
  { event: "job_failed", error: "Solver exploded" }
);

assert.strictEqual(failedState.status, "failed");
assert.strictEqual(failedState.running, false);
assert.strictEqual(failedState.progress, 100);
assert.strictEqual(failedState.error, "Solver exploded");
assert.strictEqual(runtime.normalizeStatus("CANCELLED"), "canceled");

console.log("job_runtime.js tests passed");

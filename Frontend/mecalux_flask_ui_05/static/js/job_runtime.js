(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.JobRuntimeHelpers = factory();
})(typeof self !== "undefined" ? self : globalThis, function () {
  function normalizeStatus(status) {
    const value = String(status || "").trim().toLowerCase();
    const mapping = {
      queued: "queued",
      running: "running",
      completed: "completed",
      failed: "failed",
      canceled: "canceled",
      cancelled: "canceled",
      idle: "idle",
    };
    return mapping[value] || (value || "unknown");
  }

  function resolveJobId(payload) {
    return String(payload?.id || payload?.job_id || "");
  }

  function normalizeCreateJobPayload(payload) {
    const id = resolveJobId(payload);
    return {
      id,
      job_id: id,
      status: normalizeStatus(payload?.status),
      progress: Number(payload?.progress || 0),
      stream_url: payload?.stream_url || `/api/jobs/${id}/stream`,
      message: payload?.message || "",
    };
  }

  function applyStreamEvent(state, payload) {
    const next = { ...state };
    const event = String(payload?.event || "").trim().toLowerCase();

    if (event === "ping") {
      return next;
    }

    if (event === "job_started") {
      next.status = "running";
      next.running = true;
      next.progress = Math.max(1, Number(next.progress || 0));
      next.message = payload?.message || "Optimization started.";
      next.error = null;
      return next;
    }

    if (event === "job_progress") {
      next.status = normalizeStatus(payload?.status || "running");
      next.running = true;
      next.progress = Number(payload?.progress ?? payload?.percent ?? next.progress ?? 0);
      next.message = payload?.message || next.message || "";
      next.error = null;
      return next;
    }

    if (event === "job_completed") {
      next.status = "completed";
      next.running = false;
      next.progress = 100;
      next.message = payload?.message || "Optimization completed.";
      next.error = null;
      return next;
    }

    if (event === "job_failed") {
      next.status = "failed";
      next.running = false;
      next.progress = 100;
      next.error = payload?.error || payload?.message || "Optimization failed.";
      next.message = next.error;
      return next;
    }

    if (event === "job_canceled") {
      next.status = "canceled";
      next.running = false;
      next.progress = 100;
      next.message = payload?.message || "Optimization canceled.";
      next.error = null;
      return next;
    }

    if (payload?.status) {
      next.status = normalizeStatus(payload.status);
      next.progress = Number(payload?.progress ?? next.progress ?? 0);
      next.running = ["queued", "running"].includes(next.status);
      next.message = payload?.message || next.message || "";
      if (payload?.error) {
        next.error = payload.error;
      }
    }

    return next;
  }

  return {
    applyStreamEvent,
    normalizeCreateJobPayload,
    normalizeStatus,
    resolveJobId,
  };
});

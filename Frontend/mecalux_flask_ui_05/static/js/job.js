function jobMonitor(projectId, initialLayout) {
  const CANVAS_W = 1000;
  const CANVAS_H = 650;
  const MARGIN = 35;

  return {
    layout: initialLayout || {},
    socket: null,
    jobId: null,
    status: "idle",
    progress: 0,
    running: false,
    logs: [],
    result: null,
    heatmapCells: [],
    heatmapCols: 5,

    get warehouse() {
      return this.layout.warehouse || { width: 10000, height: 6500 };
    },

    get obstacles() {
      return this.layout.obstacles || [];
    },

    get bayTypes() {
      return this.layout.bayTypes || [];
    },

    get resultBays() {
      return this.result?.placed_bays || this.result?.placedBaysDetailed || [];
    },

    get polygon() {
      if (this.warehouse.polygon && this.warehouse.polygon.length >= 3) return this.warehouse.polygon;
      const width = Number(this.warehouse.width || 10000);
      const height = Number(this.warehouse.height || 6500);
      return [
        { x: 0, y: 0 },
        { x: width, y: 0 },
        { x: width, y: height },
        { x: 0, y: height },
      ];
    },

    get bounds() {
      const points = [...this.polygon];
      this.obstacles.forEach((o) => {
        points.push({ x: Number(o.x || 0), y: Number(o.y || 0) });
        points.push({ x: Number(o.x || 0) + Number(o.w || o.width || 0), y: Number(o.y || 0) + Number(o.h || o.depth || 0) });
      });
      this.resultBays.forEach((b) => {
        const size = this.baySize(b);
        points.push({ x: Number(b.x || 0), y: Number(b.y || 0) });
        points.push({ x: Number(b.x || 0) + size.w, y: Number(b.y || 0) + size.h });
      });
      const xs = points.map((p) => Number(p.x || 0));
      const ys = points.map((p) => Number(p.y || 0));
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const width = Math.max(1, maxX - minX);
      const height = Math.max(1, maxY - minY);
      const scale = Math.min((CANVAS_W - 2 * MARGIN) / width, (CANVAS_H - 2 * MARGIN) / height);
      const drawnW = width * scale;
      const drawnH = height * scale;
      return {
        minX, minY, maxX, maxY, width, height, scale,
        offsetX: (CANVAS_W - drawnW) / 2,
        offsetY: (CANVAS_H - drawnH) / 2,
      };
    },

    toScreenX(x) {
      const b = this.bounds;
      return b.offsetX + (Number(x || 0) - b.minX) * b.scale;
    },

    toScreenY(y) {
      const b = this.bounds;
      return b.offsetY + (Number(y || 0) - b.minY) * b.scale;
    },

    warehousePolygonPoints() {
      return this.polygon.map((p) => `${this.toScreenX(p.x)},${this.toScreenY(p.y)}`).join(" ");
    },

    baySize(bay) {
      if (bay.w && bay.h) return { w: Number(bay.w), h: Number(bay.h) };
      const type = this.bayTypes.find((t) => String(t.id) === String(bay.id || bay.bayTypeId));
      let w = Number(type?.width || 1200);
      let h = Number(type?.depth || 800);
      const rot = Number(bay.rotation || 0) % 180;
      if (rot === 90) [w, h] = [h, w];
      return { w, h };
    },

    rectStyle(item) {
      const x = this.toScreenX(item.x);
      const y = this.toScreenY(item.y);
      const w = Number(item.w || item.width || 0) * this.bounds.scale;
      const h = Number(item.h || item.depth || 0) * this.bounds.scale;
      return `left:${x}px; top:${y}px; width:${w}px; height:${h}px;`;
    },

    bayStyle(bay) {
      const size = this.baySize(bay);
      const x = this.toScreenX(bay.x);
      const y = this.toScreenY(bay.y);
      const w = size.w * this.bounds.scale;
      const h = size.h * this.bounds.scale;
      return `left:${x}px; top:${y}px; width:${w}px; height:${h}px;`;
    },

    async runJob() {
      this.running = true;
      this.status = "queued";
      this.progress = 0;
      this.logs = ["Creating mocked optimization job..."];
      this.result = null;
      this.heatmapCells = [];

      const response = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_id: projectId }),
      });

      const job = await response.json();
      this.jobId = job.id;
      this.connectSocket(job.id);
    },

    connectSocket(jobId) {
      this.socket = io();
      this.socket.emit("join_job", { job_id: jobId });

      this.socket.on("job_update", (job) => {
        if (job.id !== jobId) return;
        this.status = job.status;
        this.progress = job.progress;
        this.running = job.status === "running" || job.status === "queued";
      });

      this.socket.on("job_log", (payload) => {
        if (payload.job_id !== jobId) return;
        this.logs.push(payload.message);
      });

      this.socket.on("job_result", (payload) => {
        if (payload.job_id !== jobId) return;
        this.result = payload.result;
        this.heatmapCols = payload.result.heatmap?.[0]?.length || 5;
        this.heatmapCells = (payload.result.heatmap || []).flat();
        this.running = false;
      });
    },

    heatStyle(value) {
      const alpha = Math.max(0.15, value);
      return `background: rgba(59, 130, 246, ${alpha}); box-shadow: inset 0 0 24px rgba(16, 185, 129, ${alpha / 2});`;
    },
  };
}

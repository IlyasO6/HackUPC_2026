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
    result: null,
    editableBays: [],
    selectedBayUid: null,
    selectedBayTypeId: ((initialLayout || {}).bayTypes || [])[0]?.id || null,
    activeTool: "select",
    placementWarning: null,
    viewBounds: null,
    draggingBayUid: null,
    dragOffsetX: 0,
    dragOffsetY: 0,
    pendingDragEvent: null,
    dragFrame: null,

    init() {
      this.viewBounds = this.calculateBounds();
    },

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
      return this.editableBays;
    },

    get selectedBay() {
      return this.resultBays.find((bay) => bay.uid === this.selectedBayUid) || null;
    },

    get selectedFootprintLabel() {
      if (!this.selectedBay) return "";
      const size = this.bayFootprintSize(this.selectedBay);
      return `${Math.round(size.w)} x ${Math.round(size.h)} mm footprint`;
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

    get polygonLimits() {
      const xs = this.polygon.map((p) => Number(p.x || 0));
      const ys = this.polygon.map((p) => Number(p.y || 0));
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys),
      };
    },

    get bounds() {
      return this.viewBounds || this.calculateBounds();
    },

    calculateBounds() {
      const points = [...this.polygon];
      this.obstacles.forEach((obs) => {
        points.push({ x: Number(obs.x || 0), y: Number(obs.y || 0) });
        points.push({
          x: Number(obs.x || 0) + Number(obs.w || obs.width || 0),
          y: Number(obs.y || 0) + Number(obs.h || obs.depth || 0),
        });
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

    layerMetrics() {
      const rect = this.$refs.finalCanvas?.getBoundingClientRect();
      const width = rect?.width || CANVAS_W;
      const height = rect?.height || CANVAS_H;
      const scale = Math.min(width / CANVAS_W, height / CANVAS_H);
      return {
        scale,
        offsetX: (width - CANVAS_W * scale) / 2,
        offsetY: (height - CANVAS_H * scale) / 2,
      };
    },

    canvasLayerStyle() {
      const layer = this.layerMetrics();
      return [
        `width:${CANVAS_W}px`,
        `height:${CANVAS_H}px`,
        `transform:translate3d(${layer.offsetX}px, ${layer.offsetY}px, 0) scale(${layer.scale})`,
      ].join("; ");
    },

    eventToCanvas(event) {
      const rect = this.$refs.finalCanvas.getBoundingClientRect();
      const layer = this.layerMetrics();
      return {
        x: (event.clientX - rect.left - layer.offsetX) / layer.scale,
        y: (event.clientY - rect.top - layer.offsetY) / layer.scale,
      };
    },

    screenX(x, b) {
      return b.offsetX + (Number(x || 0) - b.minX) * b.scale;
    },

    screenY(y, b) {
      return b.offsetY + (Number(y || 0) - b.minY) * b.scale;
    },

    worldX(x, b) {
      return (Number(x || 0) - b.offsetX) / b.scale + b.minX;
    },

    worldY(y, b) {
      return (Number(y || 0) - b.offsetY) / b.scale + b.minY;
    },

    snap(value) {
      const step = 25;
      return Math.round(Number(value || 0) / step) * step;
    },

    warehousePolygonPoints() {
      const b = this.bounds;
      return this.polygon.map((p) => `${this.screenX(p.x, b)},${this.screenY(p.y, b)}`).join(" ");
    },

    bayTypeFor(bay) {
      return this.bayTypes.find((type) => String(type.id) === String(bay.bayTypeId || bay.id));
    },

    baySize(bay) {
      const type = this.bayTypeFor(bay);
      return {
        w: Number(bay.w || bay.width || type?.width || 1200),
        h: Number(bay.h || bay.depth || type?.depth || 800),
      };
    },

    bayGap(bay) {
      if (bay.gap !== undefined && bay.gap !== null) return Math.max(0, Number(bay.gap || 0));
      return Math.max(0, Number(this.bayTypeFor(bay)?.gap || 0));
    },

    bayFootprintSize(bay) {
      const size = this.baySize(bay);
      return { w: size.w, h: size.h + this.bayGap(bay) };
    },

    rectCorners(item) {
      const x = Number(item.x || 0);
      const y = Number(item.y || 0);
      const w = Number(item.w || item.width || 0);
      const h = Number(item.h || item.depth || 0);
      return [
        { x, y },
        { x: x + w, y },
        { x: x + w, y: y + h },
        { x, y: y + h },
      ];
    },

    bayCorners(bay) {
      const { w, h } = this.bayFootprintSize(bay);
      const x = Number(bay.x || 0);
      const y = Number(bay.y || 0);
      const rotation = (((Number(bay.rotation || 0) % 360) + 360) % 360) * Math.PI / 180;
      const cx = x + w / 2;
      const cy = y + h / 2;
      const local = [
        [-w / 2, -h / 2],
        [ w / 2, -h / 2],
        [ w / 2,  h / 2],
        [-w / 2,  h / 2],
      ];
      const cos = Math.cos(rotation);
      const sin = Math.sin(rotation);
      return local.map(([dx, dy]) => ({
        x: cx + dx * cos - dy * sin,
        y: cy + dx * sin + dy * cos,
      }));
    },

    pointOnSegment(p, a, b) {
      const eps = 1e-7;
      const cross = (p.y - a.y) * (b.x - a.x) - (p.x - a.x) * (b.y - a.y);
      if (Math.abs(cross) > eps) return false;
      return p.x >= Math.min(a.x, b.x) - eps && p.x <= Math.max(a.x, b.x) + eps &&
        p.y >= Math.min(a.y, b.y) - eps && p.y <= Math.max(a.y, b.y) + eps;
    },

    polygonEdges(poly) {
      return poly.map((p, i) => [p, poly[(i + 1) % poly.length]]);
    },

    polyBounds(poly) {
      const xs = poly.map((p) => p.x);
      const ys = poly.map((p) => p.y);
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys),
      };
    },

    boundsOverlap(a, b) {
      return a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
    },

    pointInWarehouse(point) {
      const poly = this.polygon;
      for (const [a, b] of this.polygonEdges(poly)) {
        if (this.pointOnSegment(point, a, b)) return true;
      }
      let inside = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const pi = poly[i];
        const pj = poly[j];
        const intersects = ((pi.y > point.y) !== (pj.y > point.y)) &&
          (point.x < (pj.x - pi.x) * (point.y - pi.y) / ((pj.y - pi.y) || 1e-12) + pi.x);
        if (intersects) inside = !inside;
      }
      return inside;
    },

    orientation(a, b, c) {
      const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
      if (Math.abs(value) < 1e-7) return 0;
      return value > 0 ? 1 : 2;
    },

    segmentsProperlyIntersect(a, b, c, d) {
      const o1 = this.orientation(a, b, c);
      const o2 = this.orientation(a, b, d);
      const o3 = this.orientation(c, d, a);
      const o4 = this.orientation(c, d, b);
      return o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0 && o1 !== o2 && o3 !== o4;
    },

    crossesWarehouseBoundary(poly) {
      return this.polygonEdges(poly).some(([a, b]) => {
        return this.polygonEdges(this.polygon).some(([c, d]) => this.segmentsProperlyIntersect(a, b, c, d));
      });
    },

    projection(poly, axis) {
      const values = poly.map((p) => p.x * axis.x + p.y * axis.y);
      return { min: Math.min(...values), max: Math.max(...values) };
    },

    polygonsOverlap(polyA, polyB) {
      const axes = [];
      for (const poly of [polyA, polyB]) {
        for (const [a, b] of this.polygonEdges(poly)) {
          const edge = { x: b.x - a.x, y: b.y - a.y };
          const length = Math.hypot(edge.x, edge.y) || 1;
          axes.push({ x: -edge.y / length, y: edge.x / length });
        }
      }

      for (const axis of axes) {
        const a = this.projection(polyA, axis);
        const b = this.projection(polyB, axis);
        if (a.max <= b.min + 1e-7 || b.max <= a.min + 1e-7) return false;
      }
      return true;
    },

    placementConflict(candidate, ignoreUid = null) {
      const corners = this.bayCorners(candidate);
      const candidateBounds = this.polyBounds(corners);
      if (!corners.every((corner) => this.pointInWarehouse(corner))) {
        return "Furniture must stay inside the warehouse.";
      }
      if (this.crossesWarehouseBoundary(corners)) {
        return "Furniture crosses the warehouse boundary.";
      }

      for (const obstacle of this.obstacles) {
        const obstacleCorners = this.rectCorners(obstacle);
        if (!this.boundsOverlap(candidateBounds, this.polyBounds(obstacleCorners))) continue;
        if (this.polygonsOverlap(corners, obstacleCorners)) {
          return "Collision with an obstacle.";
        }
      }

      for (const bay of this.resultBays) {
        if (bay.uid === ignoreUid) continue;
        const bayCorners = this.bayCorners(bay);
        if (!this.boundsOverlap(candidateBounds, this.polyBounds(bayCorners))) continue;
        if (this.polygonsOverlap(corners, bayCorners)) {
          return "Collision detected: furniture cannot overlap.";
        }
      }

      return null;
    },

    rectStyle(item) {
      const b = this.bounds;
      const x = this.screenX(item.x, b);
      const y = this.screenY(item.y, b);
      const w = Number(item.w || item.width || 0) * b.scale;
      const h = Number(item.h || item.depth || 0) * b.scale;
      return [
        "left:0",
        "top:0",
        `width:${w}px`,
        `height:${h}px`,
        `transform:translate3d(${x}px, ${y}px, 0)`,
      ].join("; ");
    },

    bayStyle(bay) {
      const b = this.bounds;
      const size = this.baySize(bay);
      const footprint = this.bayFootprintSize(bay);
      const x = this.screenX(bay.x, b);
      const y = this.screenY(bay.y, b);
      const w = footprint.w * b.scale;
      const h = footprint.h * b.scale;
      const gapPercent = footprint.h ? this.bayGap(bay) / footprint.h * 100 : 0;
      const rackPercent = Math.max(0, 100 - gapPercent);
      return [
        "left:0",
        "top:0",
        `width:${w}px`,
        `height:${h}px`,
        `--rack-depth:${rackPercent}%`,
        `--gap-depth:${gapPercent}%`,
        `transform:translate3d(${x}px, ${y}px, 0) rotate(${Number(bay.rotation || 0)}deg)`,
        "transform-origin: center center",
      ].join("; ");
    },

    setTool(tool) {
      this.activeTool = tool;
      if (tool === "delete") this.stopBayDrag();
    },

    selectBay(bay) {
      this.selectedBayUid = bay.uid;
      if (bay.bayTypeId !== undefined && bay.bayTypeId !== null) {
        this.selectedBayTypeId = bay.bayTypeId;
      }
    },

    handleBayPointerDown(event, bay) {
      if (this.activeTool === "delete") {
        this.removeBay(bay.uid);
        return;
      }
      this.selectBay(bay);
      if (this.activeTool === "move" || this.activeTool === "select") {
        this.startBayDrag(event, bay);
      }
    },

    startBayDrag(event, bay) {
      this.draggingBayUid = bay.uid;
      const point = this.eventToCanvas(event);
      const b = this.bounds;
      this.dragOffsetX = point.x - this.screenX(bay.x, b);
      this.dragOffsetY = point.y - this.screenY(bay.y, b);
    },

    dragBay(event) {
      if (!this.draggingBayUid) return;
      this.pendingDragEvent = event;
      if (this.dragFrame) return;
      this.dragFrame = requestAnimationFrame(() => {
        this.dragFrame = null;
        this.applyDragBay(this.pendingDragEvent);
      });
    },

    applyDragBay(event) {
      const bay = this.resultBays.find((item) => item.uid === this.draggingBayUid);
      if (!bay || !event) return;

      const point = this.eventToCanvas(event);
      const b = this.bounds;
      const size = this.bayFootprintSize(bay);
      const limits = this.polygonLimits;

      const candidate = {
        ...bay,
        x: Math.max(limits.minX, Math.min(this.snap(this.worldX(point.x - this.dragOffsetX, b)), limits.maxX - size.w)),
        y: Math.max(limits.minY, Math.min(this.snap(this.worldY(point.y - this.dragOffsetY, b)), limits.maxY - size.h)),
      };
      if (candidate.x === bay.x && candidate.y === bay.y) return;
      const conflict = this.placementConflict(candidate, bay.uid);
      if (conflict) {
        this.placementWarning = conflict;
        return;
      }

      bay.x = candidate.x;
      bay.y = candidate.y;
      this.placementWarning = null;
    },

    stopBayDrag() {
      this.draggingBayUid = null;
      this.pendingDragEvent = null;
      if (this.dragFrame) {
        cancelAnimationFrame(this.dragFrame);
        this.dragFrame = null;
      }
    },

    updateSelected(mutator) {
      const bay = this.selectedBay;
      if (!bay) return false;
      const previous = { ...bay };
      mutator(bay);
      const conflict = this.placementConflict(bay, bay.uid);
      if (conflict) {
        Object.assign(bay, previous);
        this.placementWarning = conflict;
        return false;
      }
      this.placementWarning = null;
      return true;
    },

    setSelectedPosition(axis, value) {
      this.updateSelected((bay) => {
        bay[axis] = this.snap(value);
      });
    },

    setSelectedRotation(value) {
      this.updateSelected((bay) => {
        bay.rotation = ((Math.round(Number(value || 0)) % 360) + 360) % 360;
      });
    },

    rotateSelectedBy(delta) {
      const bay = this.selectedBay;
      if (!bay) return;
      this.setSelectedRotation(Number(bay.rotation || 0) + Number(delta || 0));
    },

    nudgeSelected(dx, dy) {
      const bay = this.selectedBay;
      if (!bay) return;
      const step = 25;
      this.updateSelected((item) => {
        item.x = this.snap(Number(bay.x || 0) + dx * step);
        item.y = this.snap(Number(bay.y || 0) + dy * step);
      });
    },

    normalizeBay(rawBay, index) {
      const type = this.bayTypes.find((bay) => String(bay.id) === String(rawBay.bayTypeId || rawBay.id));
      return {
        ...rawBay,
        uid: rawBay.uid || `bay-${Date.now()}-${index}`,
        id: rawBay.id || rawBay.label || rawBay.bayTypeId || `F${index + 1}`,
        bayTypeId: rawBay.bayTypeId || type?.id || rawBay.id || null,
        x: Number(rawBay.x || 0),
        y: Number(rawBay.y || 0),
        w: Number(rawBay.w || rawBay.width || type?.width || 1200),
        h: Number(rawBay.h || rawBay.depth || type?.depth || 800),
        gap: Number(rawBay.gap ?? type?.gap ?? 0),
        rotation: Number(rawBay.rotation || 0),
      };
    },

    firstFreePosition(size) {
      const limits = this.polygonLimits;
      const step = Math.max(100, this.snap(Math.min(size.w, size.h) / 2));
      const endX = limits.maxX - size.w;
      const endY = limits.maxY - size.h;

      for (let y = limits.minY + 100; y <= endY; y += step) {
        for (let x = limits.minX + 100; x <= endX; x += step) {
          const candidate = {
            uid: "candidate",
            x: this.snap(x),
            y: this.snap(y),
            w: size.w,
            h: size.h,
            gap: size.gap || 0,
            rotation: 0,
          };
          if (!this.placementConflict(candidate)) return { x: candidate.x, y: candidate.y };
        }
      }

      return null;
    },

    addShelf() {
      const type = this.bayTypes.find((bay) => String(bay.id) === String(this.selectedBayTypeId)) || this.bayTypes[0];
      if (!type) return;
      const size = {
        w: Number(type.width || 1200),
        h: Number(type.depth || 800),
        gap: Number(type.gap || 0),
      };
      const position = this.firstFreePosition(size);
      if (!position) {
        this.placementWarning = "No free collision-safe space found for this furniture type.";
        return;
      }

      const bay = this.normalizeBay({
        id: `T${type.id}`,
        bayTypeId: type.id,
        x: position.x,
        y: position.y,
        w: size.w,
        h: size.h,
        gap: size.gap,
        rotation: 0,
      }, this.resultBays.length);
      this.editableBays.push(bay);
      this.selectBay(bay);
      this.activeTool = "move";
      this.placementWarning = null;
    },

    removeBay(uid) {
      this.editableBays = this.editableBays.filter((bay) => bay.uid !== uid);
      if (this.selectedBayUid === uid) this.selectedBayUid = this.editableBays[0]?.uid || null;
      this.stopBayDrag();
      this.placementWarning = null;
    },

    removeSelectedBay() {
      if (!this.selectedBay) return;
      this.removeBay(this.selectedBay.uid);
    },

    async runJob() {
      this.running = true;
      this.status = "queued";
      this.progress = 0;
      this.result = null;
      this.editableBays = [];
      this.selectedBayUid = null;
      this.placementWarning = null;

      if (this.socket) {
        this.socket.disconnect();
        this.socket = null;
      }

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

      this.socket.on("job_result", (payload) => {
        if (payload.job_id !== jobId) return;
        this.result = payload.result;
        const placed = payload.result.placed_bays || payload.result.placedBaysDetailed || [];
        this.editableBays = placed.map((bay, index) => this.normalizeBay(bay, index));
        this.selectedBayUid = this.editableBays[0]?.uid || null;
        this.running = false;
      });
    },
  };
}

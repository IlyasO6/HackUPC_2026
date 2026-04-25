function jobMonitor(projectId, initialLayout) {
  const geometry = window.LayoutGeometry;
  const runtime = window.JobRuntimeHelpers || {};
  const appConfig = window.APP_CONFIG || {};
  const CANVAS_W = 1000;
  const CANVAS_H = 650;
  const MARGIN = 35;

  function clone(value) {
    return JSON.parse(JSON.stringify(value || {}));
  }

  return {
    backendMode: appConfig.backendMode || "mock",
    layout: {},
    socket: null,
    eventSource: null,
    jobId: null,
    status: "idle",
    progress: 0,
    running: false,
    result: null,
    resultBays: [],
    selectedBayUid: null,
    activeTool: "select",
    placementWarning: null,
    failureReason: null,
    statusMessage: "",
    evaluationTimer: null,
    evaluationToken: 0,
    draggingBayUid: null,
    dragOffsetX: 0,
    dragOffsetY: 0,
    pendingDragEvent: null,
    dragFrame: null,
    liveMetrics: {
      Q: null,
      coverage: 0,
      totalLoads: 0,
      totalBayArea: 0,
      warehouseArea: 0,
      valid: true,
      issues: [],
      issueCount: 0,
      source: "idle",
    },
    draftBay: {
      label: "",
      width: 1200,
      depth: 800,
      height: 2400,
      gap: 200,
      nLoads: 12,
      price: 900,
    },

    init() {
      this.layout = this.normalizeLayoutState(clone(initialLayout));
      this.seedDraftFromPreset(this.bayTypes[0] || null);
      this.resultBays = (this.layout.shelves || []).map((bay, index) =>
        this.normalizeBay(bay, index)
      );
      this.selectedBayUid = this.resultBays[0]?.uid || null;
      this.refreshAfterEdit("local");
    },

    get isRealMode() {
      return this.backendMode === "real";
    },

    get warehouse() {
      return this.layout.warehouse || { polygon: [] };
    },

    get obstacles() {
      return this.layout.obstacles || [];
    },

    get ceiling() {
      return this.layout.ceiling || [];
    },

    get bayTypes() {
      return this.layout.bayTypes || [];
    },

    get selectedBay() {
      return this.resultBays.find((bay) => bay.uid === this.selectedBayUid) || null;
    },

    get selectedFootprintLabel() {
      if (!this.selectedBay) {
        return "";
      }
      const dims = geometry.itemDimensions(this.selectedBay);
      return `${Math.round(dims.width)} x ${Math.round(dims.depth)} mm body - gap ${Math.round(dims.gap)} mm`;
    },

    get polygon() {
      return geometry.warehousePolygon(this.warehouse);
    },

    get polygonLimits() {
      const xs = this.polygon.map((point) => point.x);
      const ys = this.polygon.map((point) => point.y);
      return {
        minX: Math.min(...xs),
        maxX: Math.max(...xs),
        minY: Math.min(...ys),
        maxY: Math.max(...ys),
      };
    },

    get bounds() {
      const points = [...this.polygon];
      this.obstacles.forEach((obstacle) => {
        geometry.obstaclePolygon(obstacle).forEach((point) => points.push(point));
      });
      this.resultBays.forEach((bay) => {
        geometry.footprintPolygon(bay).forEach((point) => points.push(point));
      });

      const xs = points.map((point) => point.x);
      const ys = points.map((point) => point.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const width = Math.max(1, maxX - minX);
      const height = Math.max(1, maxY - minY);
      const scale = Math.min(
        (CANVAS_W - 2 * MARGIN) / width,
        (CANVAS_H - 2 * MARGIN) / height
      );
      const drawnW = width * scale;
      const drawnH = height * scale;
      return {
        minX,
        minY,
        maxX,
        maxY,
        width,
        height,
        scale,
        offsetX: (CANVAS_W - drawnW) / 2,
        offsetY: (CANVAS_H - drawnH) / 2,
      };
    },

    get statusLabel() {
      return String(this.status || "idle").toUpperCase();
    },

    get backendIssues() {
      return this.liveMetrics.issues || [];
    },

    get qDisplay() {
      if (this.liveMetrics.Q === null || this.liveMetrics.Q === undefined) {
        return "--";
      }
      const value = Number(this.liveMetrics.Q);
      return Number.isFinite(value) ? value.toFixed(4) : "--";
    },

    get coveragePercent() {
      return (Number(this.liveMetrics.coverage || 0) * 100).toFixed(1);
    },

    get validityLabel() {
      return this.liveMetrics.valid ? "Valid" : "Invalid";
    },

    get liveSourceLabel() {
      const source = String(this.liveMetrics.source || "idle");
      const labels = {
        local: "Local check",
        backend: "FastAPI score",
        solver: "Solved layout",
        idle: "Idle",
      };
      return labels[source] || source;
    },

    formatNumber(value, digits = 0) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) {
        return "--";
      }
      return numeric.toFixed(digits);
    },

    normalizeLayoutState(layout) {
      const warehouse = layout.warehouse || {};
      const polygon = geometry.warehousePolygon(warehouse);
      const normalizedBayTypes = (layout.bayTypes || []).map((entry, index) =>
        this.normalizeBayType(entry, index)
      );
      return {
        warehouse: {
          polygon,
          width: geometry.num(
            warehouse.width,
            Math.max(...polygon.map((point) => point.x)) -
              Math.min(...polygon.map((point) => point.x))
          ),
          height: geometry.num(
            warehouse.height,
            Math.max(...polygon.map((point) => point.y)) -
              Math.min(...polygon.map((point) => point.y))
          ),
          source: warehouse.source || "Manual project",
        },
        obstacles: (layout.obstacles || []).map((entry, index) => ({
          id: String(entry.id || `obs-${index + 1}`),
          x: geometry.num(entry.x),
          y: geometry.num(entry.y),
          w: geometry.num(entry.w ?? entry.width),
          h: geometry.num(entry.h ?? entry.depth),
        })),
        ceiling: (layout.ceiling || []).map((entry) => ({
          x: geometry.num(entry.x),
          height: geometry.num(entry.height),
        })),
        bayTypes: this.mergeBayTypes(
          normalizedBayTypes,
          (layout.shelves || []).map((entry, index) =>
            this.normalizeBay(entry, index, normalizedBayTypes)
          )
        ),
        shelves: (layout.shelves || []).map((entry, index) =>
          this.normalizeBay(entry, index, normalizedBayTypes)
        ),
        rawFiles: Array.isArray(layout.rawFiles) ? layout.rawFiles : [],
      };
    },

    normalizeBayType(entry, index) {
      const bayId = String(entry.id || entry.label || `bay-type-${index + 1}`);
      return {
        id: bayId,
        label: String(entry.label || bayId),
        width: geometry.num(entry.width ?? entry.w, 1200),
        depth: geometry.num(entry.depth ?? entry.h, 800),
        height: geometry.num(entry.height, 2400),
        gap: Math.max(0, geometry.num(entry.gap, 0)),
        nLoads: geometry.num(entry.nLoads ?? entry.loads, 0),
        price: geometry.num(entry.price, 0),
      };
    },

    normalizeBay(entry, index, sourceBayTypes) {
      const candidates = sourceBayTypes || this.bayTypes;
      const bayTypeId = String(
        entry.bayTypeId ||
          entry.typeId ||
          entry.backendBayTypeId ||
          entry.id ||
          `custom-${index + 1}`
      );
      const bayType = candidates.find(
        (candidate) => String(candidate.id) === bayTypeId
      ) || {};
      return {
        uid: String(entry.uid || entry.id || `bay-${index + 1}`),
        id: String(entry.label || entry.id || bayType.label || bayTypeId),
        label: String(entry.label || entry.id || bayType.label || bayTypeId),
        bayTypeId,
        backendBayTypeId: entry.backendBayTypeId || null,
        x: geometry.num(entry.x),
        y: geometry.num(entry.y),
        w: geometry.num(entry.w ?? entry.width, bayType.width || 1200),
        h: geometry.num(entry.h ?? entry.depth, bayType.depth || 800),
        height: geometry.num(entry.height, bayType.height || 2400),
        gap: Math.max(0, geometry.num(entry.gap, bayType.gap || 0)),
        nLoads: geometry.num(entry.nLoads, bayType.nLoads || 0),
        price: geometry.num(entry.price, bayType.price || 0),
        rotation: geometry.normalizeAngle(entry.rotation || 0, 30),
        isInvalid: Boolean(entry.isInvalid),
        issues: Array.isArray(entry.issues) ? entry.issues : [],
      };
    },

    mergeBayTypes(bayTypes, bays) {
      const merged = bayTypes.map((entry) => ({ ...entry }));
      const byId = new Map(merged.map((entry) => [String(entry.id), entry]));
      bays.forEach((bay) => {
        if (byId.has(String(bay.bayTypeId))) {
          return;
        }
        const derived = {
          id: String(bay.bayTypeId),
          label: String(bay.label || bay.bayTypeId),
          width: geometry.num(bay.w),
          depth: geometry.num(bay.h),
          height: geometry.num(bay.height),
          gap: geometry.num(bay.gap),
          nLoads: geometry.num(bay.nLoads),
          price: geometry.num(bay.price),
        };
        merged.push(derived);
        byId.set(String(derived.id), derived);
      });
      return merged;
    },

    serializeBays() {
      return this.resultBays.map((bay) => ({
        uid: bay.uid,
        id: bay.id,
        label: bay.label,
        bayTypeId: bay.bayTypeId,
        backendBayTypeId: bay.backendBayTypeId,
        x: bay.x,
        y: bay.y,
        w: bay.w,
        h: bay.h,
        height: bay.height,
        gap: bay.gap,
        nLoads: bay.nLoads,
        price: bay.price,
        rotation: bay.rotation,
      }));
    },

    serializeLayout() {
      return {
        warehouse: this.warehouse,
        obstacles: this.obstacles,
        ceiling: this.ceiling,
        bayTypes: this.bayTypes,
        shelves: this.serializeBays(),
        rawFiles: this.layout.rawFiles || [],
      };
    },

    issueText(issue) {
      return issue?.message || String(issue || "");
    },

    issuesForBay(index, bayId, issues) {
      return (issues || []).filter((issue) => {
        if ((issue.invalid_bay_id || issue.invalidBayId) === bayId) {
          return true;
        }
        const match = /Bay #(\d+)/.exec(this.issueText(issue));
        return match ? Number(match[1]) === index : false;
      });
    },

    localSummary() {
      const issues = [];
      const invalidBayIds = [];
      let totalArea = 0;
      let totalPrice = 0;
      let totalLoads = 0;

      this.resultBays.forEach((bay, index) => {
        const violations = geometry.placementViolations(
          bay,
          this.resultBays,
          this.obstacles,
          this.warehouse,
          bay.uid
        );
        if (violations.length) {
          invalidBayIds.push(bay.uid);
          violations.forEach((message) => {
            issues.push({
              bay_index: index,
              invalid_bay_id: bay.uid,
              message: `Bay #${index}: ${message}`,
            });
          });
        }
        totalArea += geometry.num(bay.w) * geometry.num(bay.h);
        totalPrice += geometry.num(bay.price);
        totalLoads += geometry.num(bay.nLoads);
      });

      const warehouseArea = geometry.polygonArea(this.polygon);
      const coverage = warehouseArea > 0 ? totalArea / warehouseArea : 0;
      let qValue = null;
      if (totalLoads > 0 && warehouseArea > 0) {
        qValue = Number((totalPrice / totalLoads) ** (2 - coverage));
      }

      return {
        Q: qValue,
        coverage,
        total_loads: totalLoads,
        total_bay_area: totalArea,
        warehouse_area: warehouseArea,
        num_bays: this.resultBays.length,
        is_valid: invalidBayIds.length === 0,
        issues,
        invalid_bay_ids: invalidBayIds,
        issue_count: issues.length,
      };
    },

    applyValidationSummary(summary, source = "local") {
      const invalidSet = new Set(summary.invalid_bay_ids || []);
      this.resultBays = this.resultBays.map((bay, index) => ({
        ...bay,
        isInvalid: invalidSet.has(bay.uid),
        issues: this.issuesForBay(index, bay.uid, summary.issues),
      }));
      this.layout.shelves = this.serializeBays();
      this.liveMetrics = {
        Q: summary.Q,
        coverage: summary.coverage || 0,
        totalLoads: summary.total_loads || 0,
        totalBayArea: summary.total_bay_area || 0,
        warehouseArea: summary.warehouse_area || 0,
        valid: Boolean(summary.is_valid),
        issues: summary.issues || [],
        issueCount: summary.issue_count ?? (summary.issues || []).length,
        source,
      };
      this.placementWarning = this.liveMetrics.valid
        ? null
        : this.issueText(this.liveMetrics.issues[0] || "");
    },

    refreshAfterEdit(source = "local") {
      this.applyValidationSummary(this.localSummary(), source);
      if (this.isRealMode) {
        this.queueBackendEvaluation();
      }
    },

    queueBackendEvaluation() {
      clearTimeout(this.evaluationTimer);
      this.evaluationTimer = setTimeout(() => this.evaluateAgainstBackend(), 220);
    },

    async evaluateAgainstBackend() {
      if (!this.isRealMode) {
        return;
      }
      const token = ++this.evaluationToken;
      try {
        const response = await fetch("/api/score", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            layout: this.serializeLayout(),
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Could not score the current layout");
        }
        if (token !== this.evaluationToken) {
          return;
        }
        this.failureReason = null;
        this.applyValidationSummary(payload, "backend");
      } catch (error) {
        if (token !== this.evaluationToken) {
          return;
        }
        this.failureReason = error.message || "Could not score the current layout";
      }
    },

    seedDraftFromPreset(bay) {
      if (!bay) {
        return;
      }
      this.draftBay = {
        label: String(bay.label || bay.id || ""),
        width: geometry.num(bay.width, 1200),
        depth: geometry.num(bay.depth, 800),
        height: geometry.num(bay.height, 2400),
        gap: Math.max(0, geometry.num(bay.gap, 0)),
        nLoads: geometry.num(bay.nLoads, 0),
        price: geometry.num(bay.price, 0),
      };
    },

    applyPreset(bay) {
      this.seedDraftFromPreset(bay);
    },

    bayTypeMatchesDraft(bay) {
      return String(bay.label || bay.id) === String(this.draftBay.label || "");
    },

    nextCustomBayTypeId(baseLabel) {
      const sanitized = String(baseLabel || "custom")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "custom";
      let candidate = sanitized;
      let suffix = 2;
      const existingIds = new Set(this.bayTypes.map((bay) => String(bay.id)));
      while (existingIds.has(candidate)) {
        candidate = `${sanitized}-${suffix}`;
        suffix += 1;
      }
      return candidate;
    },

    ensureDraftBayType() {
      const draft = {
        label: String(this.draftBay.label || "").trim() || "Custom",
        width: Math.max(1, geometry.num(this.draftBay.width, 1200)),
        depth: Math.max(1, geometry.num(this.draftBay.depth, 800)),
        height: Math.max(0, geometry.num(this.draftBay.height, 2400)),
        gap: Math.max(0, geometry.num(this.draftBay.gap, 0)),
        nLoads: Math.max(0, geometry.num(this.draftBay.nLoads, 0)),
        price: Math.max(0, geometry.num(this.draftBay.price, 0)),
      };

      const exactMatch = this.bayTypes.find((bay) =>
        geometry.num(bay.width) === draft.width &&
        geometry.num(bay.depth) === draft.depth &&
        geometry.num(bay.height) === draft.height &&
        geometry.num(bay.gap) === draft.gap &&
        geometry.num(bay.nLoads) === draft.nLoads &&
        geometry.num(bay.price) === draft.price &&
        String(bay.label || bay.id) === draft.label
      );
      if (exactMatch) {
        return exactMatch;
      }

      const bayId = this.nextCustomBayTypeId(draft.label);
      const created = {
        id: bayId,
        label: draft.label,
        width: draft.width,
        depth: draft.depth,
        height: draft.height,
        gap: draft.gap,
        nLoads: draft.nLoads,
        price: draft.price,
      };
      this.layout.bayTypes = [...this.bayTypes, created];
      return created;
    },

    firstFreePosition(template) {
      const limits = this.polygonLimits;
      const step = Math.max(100, this.snap(Math.min(template.w, template.h) / 2));
      for (let y = limits.minY; y <= limits.maxY; y += step) {
        for (let x = limits.minX; x <= limits.maxX; x += step) {
          const candidate = { ...template, x: this.snap(x), y: this.snap(y) };
          const message = geometry.firstViolation(
            candidate,
            this.resultBays,
            this.obstacles,
            this.warehouse,
            candidate.uid
          );
          if (!message) {
            return { x: candidate.x, y: candidate.y };
          }
        }
      }
      return null;
    },

    addShelf() {
      const bayType = this.ensureDraftBayType();
      const prototype = this.normalizeBay(
        {
          uid: `bay-${Date.now()}`,
          id: this.draftBay.label || bayType.label || bayType.id,
          label: this.draftBay.label || bayType.label || bayType.id,
          bayTypeId: String(bayType.id),
          x: 0,
          y: 0,
          w: bayType.width,
          h: bayType.depth,
          height: bayType.height,
          gap: bayType.gap,
          nLoads: bayType.nLoads,
          price: bayType.price,
          rotation: 0,
        },
        this.resultBays.length + 1
      );
      const position = this.firstFreePosition(prototype);
      if (!position) {
        this.placementWarning =
          "No free collision-safe position was found for this bay.";
        return;
      }

      const created = { ...prototype, x: position.x, y: position.y };
      this.resultBays = [...this.resultBays, created];
      this.selectedBayUid = created.uid;
      this.refreshAfterEdit("local");
    },

    removeBay(uid) {
      this.resultBays = this.resultBays.filter((bay) => bay.uid !== uid);
      this.selectedBayUid = this.resultBays[0]?.uid || null;
      this.stopBayDrag();
      this.refreshAfterEdit("local");
    },

    removeSelectedBay() {
      if (!this.selectedBay) {
        return;
      }
      this.removeBay(this.selectedBay.uid);
    },

    setTool(tool) {
      this.activeTool = tool;
      if (tool === "delete") {
        this.stopBayDrag();
      }
    },

    selectBay(bay) {
      this.selectedBayUid = bay.uid;
    },

    screenX(x, bounds) {
      return bounds.offsetX + (geometry.num(x) - bounds.minX) * bounds.scale;
    },

    screenY(y, bounds) {
      return bounds.offsetY + (geometry.num(y) - bounds.minY) * bounds.scale;
    },

    worldX(x, bounds) {
      return (geometry.num(x) - bounds.offsetX) / bounds.scale + bounds.minX;
    },

    worldY(y, bounds) {
      return (geometry.num(y) - bounds.offsetY) / bounds.scale + bounds.minY;
    },

    snap(value) {
      return Math.round(geometry.num(value) / 25) * 25;
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

    warehousePolygonPoints() {
      const bounds = this.bounds;
      return this.polygon
        .map((point) => `${this.screenX(point.x, bounds)},${this.screenY(point.y, bounds)}`)
        .join(" ");
    },

    rectStyle(item) {
      const bounds = this.bounds;
      return [
        `left:${this.screenX(item.x, bounds)}px`,
        `top:${this.screenY(item.y, bounds)}px`,
        `width:${geometry.num(item.w ?? item.width) * bounds.scale}px`,
        `height:${geometry.num(item.h ?? item.depth) * bounds.scale}px`,
      ].join("; ");
    },

    bayStyle(bay) {
      const bounds = this.bounds;
      const dims = geometry.itemDimensions(bay);
      const footprint = geometry.footprintSize(bay);
      return [
        `left:${this.screenX(bay.x, bounds)}px`,
        `top:${this.screenY(bay.y, bounds)}px`,
        `width:${footprint.w * bounds.scale}px`,
        `height:${footprint.h * bounds.scale}px`,
        `--rack-width:${dims.width * bounds.scale}px`,
        `--gap-width:${dims.gap * bounds.scale}px`,
        `transform:rotate(${geometry.normalizeAngle(bay.rotation, 30)}deg)`,
        "transform-origin: top left",
      ].join("; ");
    },

    bayFootprintPreviewStyle(bay) {
      const width = Math.max(1, geometry.num(bay.width));
      const depth = Math.max(1, geometry.num(bay.depth));
      const gap = Math.max(0, geometry.num(bay.gap));
      const scale = Math.min(86 / (width + gap), 44 / depth);
      return [
        `width:${Math.max(22, (width + gap) * scale)}px`,
        `height:${Math.max(10, depth * scale)}px`,
        `--preview-rack-width:${Math.max(12, width * scale)}px`,
        `--preview-gap-width:${Math.max(0, gap * scale)}px`,
      ].join("; ");
    },

    updateBay(bayUid, mutator) {
      const current = this.resultBays.find((bay) => bay.uid === bayUid);
      if (!current) {
        return false;
      }
      const next = { ...current };
      mutator(next);
      next.rotation = geometry.normalizeAngle(next.rotation, 30);
      if (!this.isRealMode) {
        const conflict = geometry.firstViolation(
          next,
          this.resultBays,
          this.obstacles,
          this.warehouse,
          bayUid
        );
        if (conflict) {
          this.placementWarning = conflict;
          return false;
        }
      }

      this.resultBays = this.resultBays.map((bay) =>
        bay.uid === bayUid ? { ...bay, ...next } : bay
      );
      this.selectedBayUid = bayUid;
      this.refreshAfterEdit("local");
      return true;
    },

    setSelectedPosition(axis, value) {
      if (!this.selectedBay) {
        return;
      }
      this.updateBay(this.selectedBay.uid, (bay) => {
        bay[axis] = this.snap(value);
      });
    },

    setSelectedRotation(value) {
      if (!this.selectedBay) {
        return;
      }
      this.updateBay(this.selectedBay.uid, (bay) => {
        bay.rotation = geometry.normalizeAngle(value, 30);
      });
    },

    rotateSelectedBy(delta) {
      if (!this.selectedBay) {
        return;
      }
      this.setSelectedRotation(geometry.num(this.selectedBay.rotation) + geometry.num(delta));
    },

    nudgeSelected(dx, dy) {
      if (!this.selectedBay) {
        return;
      }
      this.updateBay(this.selectedBay.uid, (bay) => {
        bay.x = this.snap(geometry.num(bay.x) + geometry.num(dx) * 25);
        bay.y = this.snap(geometry.num(bay.y) + geometry.num(dy) * 25);
      });
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
      const bounds = this.bounds;
      this.dragOffsetX = point.x - this.screenX(bay.x, bounds);
      this.dragOffsetY = point.y - this.screenY(bay.y, bounds);
    },

    dragBay(event) {
      if (!this.draggingBayUid) {
        return;
      }
      this.pendingDragEvent = event;
      if (this.dragFrame) {
        return;
      }
      this.dragFrame = requestAnimationFrame(() => {
        this.dragFrame = null;
        this.applyDragBay(this.pendingDragEvent);
      });
    },

    applyDragBay(event) {
      const bay = this.resultBays.find((entry) => entry.uid === this.draggingBayUid);
      if (!bay || !event) {
        return;
      }
      const point = this.eventToCanvas(event);
      const bounds = this.bounds;
      const nextX = this.snap(this.worldX(point.x - this.dragOffsetX, bounds));
      const nextY = this.snap(this.worldY(point.y - this.dragOffsetY, bounds));
      this.updateBay(bay.uid, (candidate) => {
        candidate.x = nextX;
        candidate.y = nextY;
      });
    },

    stopBayDrag() {
      this.draggingBayUid = null;
      this.pendingDragEvent = null;
      if (this.dragFrame) {
        cancelAnimationFrame(this.dragFrame);
        this.dragFrame = null;
      }
    },

    async runJob() {
      this.running = true;
      this.status = "queued";
      this.progress = 0;
      this.failureReason = null;
      this.result = null;
      this.statusMessage = "Submitting layout...";
      this.placementWarning = null;

      if (this.socket) {
        this.socket.disconnect();
        this.socket = null;
      }
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }

      try {
        const response = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_id: projectId,
            layout: this.serializeLayout(),
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Could not create the optimization job");
        }
        const job = runtime.normalizeCreateJobPayload
          ? runtime.normalizeCreateJobPayload(payload)
          : payload;
        this.jobId = job.id || job.job_id;
        this.status = runtime.normalizeStatus
          ? runtime.normalizeStatus(job.status)
          : String(job.status || "queued").toLowerCase();
        this.progress = Number(job.progress || 0);
        this.statusMessage = job.message || "Optimization queued.";
        this.running = true;

        if (this.isRealMode) {
          this.connectEventSource(job.stream_url);
        } else {
          this.connectSocket(this.jobId);
        }
      } catch (error) {
        this.running = false;
        this.status = "failed";
        this.failureReason = error.message || "Could not create the optimization job";
        this.statusMessage = this.failureReason;
      }
    },

    connectSocket(jobId) {
      this.socket = io();
      this.socket.emit("join_job", { job_id: jobId });

      this.socket.on("job_update", (payload) => {
        const next = runtime.applyStreamEvent
          ? runtime.applyStreamEvent(this, payload)
          : payload;
        this.status = next.status || this.status;
        this.progress = Number(next.progress || this.progress || 0);
        this.running = Boolean(next.running);
        this.statusMessage = next.message || this.statusMessage;
        this.failureReason = next.error || null;
      });

      this.socket.on("job_result", (payload) => {
        if ((payload.job_id || payload.id) !== jobId) {
          return;
        }
        this.handleCompletedResult(payload.result);
      });
    },

    connectEventSource(streamUrl) {
      this.eventSource = new EventSource(streamUrl);

      this.eventSource.onmessage = async (event) => {
        let payload = null;
        try {
          payload = JSON.parse(event.data);
        } catch (error) {
          return;
        }

        const next = runtime.applyStreamEvent
          ? runtime.applyStreamEvent(this, payload)
          : payload;
        const eventName = String(payload.event || "").trim().toLowerCase();
        this.status = next.status || this.status;
        this.progress = Number(next.progress || this.progress || 0);
        this.running = Boolean(next.running);
        this.failureReason = next.error || null;
        this.statusMessage = next.message || this.statusMessage;
        if (next.message && this.status === "failed") {
          this.placementWarning = next.message;
        }

        if (eventName === "job_completed" && payload.result) {
          this.handleCompletedResult(payload.result);
          this.eventSource.close();
          this.eventSource = null;
        }

        if (eventName === "job_failed" || eventName === "job_canceled") {
          this.running = false;
          this.eventSource.close();
          this.eventSource = null;
        }
      };

      this.eventSource.onerror = async () => {
        if (!this.running || !this.jobId) {
          this.eventSource?.close();
          this.eventSource = null;
          return;
        }
        try {
          const response = await fetch(`/api/jobs/${this.jobId}`);
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.error || "Could not refresh the job status");
          }
          this.status = runtime.normalizeStatus
            ? runtime.normalizeStatus(payload.status)
            : String(payload.status || "").toLowerCase();
          this.progress = Number(payload.progress || 0);
          this.running = ["queued", "running"].includes(this.status);
          this.statusMessage = payload.message || this.statusMessage;
          if (this.status === "completed") {
            const resultResponse = await fetch(`/api/jobs/${this.jobId}/result`);
            const resultPayload = await resultResponse.json();
            if (resultResponse.ok) {
              this.handleCompletedResult(resultPayload);
            }
            this.eventSource?.close();
            this.eventSource = null;
          }
          if (this.status === "failed" || this.status === "canceled") {
            this.failureReason = payload.error || payload.message || this.failureReason;
            this.statusMessage = this.failureReason || this.statusMessage;
            this.eventSource?.close();
            this.eventSource = null;
          }
        } catch (error) {
          this.failureReason = error.message || "The live progress stream disconnected.";
          this.statusMessage = this.failureReason;
          this.running = false;
          this.eventSource?.close();
          this.eventSource = null;
        }
      };
    },

    handleCompletedResult(result) {
      this.result = result;
      const placed = result?.placed_bays || [];
      this.resultBays = placed.map((bay, index) => this.normalizeBay(bay, index));
      this.selectedBayUid = this.resultBays[0]?.uid || null;
      this.status = "completed";
      this.progress = 100;
      this.running = false;
      this.failureReason = null;
      this.statusMessage = "Optimization completed.";
      const local = this.localSummary();
      this.applyValidationSummary(
        {
          ...local,
          Q: result?.Q ?? result?.score ?? local.Q,
          coverage: result?.coverage ?? local.coverage,
        },
        "solver"
      );
    },
  };
}

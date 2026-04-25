function warehouseEditor(initialLayout, projectId) {
  const geometry = window.LayoutGeometry;
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
    saved: false,
    saving: false,
    saveError: null,
    validationIssues: [],

    canvasW: CANVAS_W,
    canvasH: CANVAS_H,
    draggingShelfId: null,
    dragOffsetX: 0,
    dragOffsetY: 0,
    selectedShelfId: null,
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
      this.selectedShelfId = this.shelves[0]?.id || null;
      this.seedDraftFromPreset(this.bayTypes[0] || null);
    },

    get isRealMode() {
      return this.backendMode === "real";
    },

    get warehouse() {
      return this.layout.warehouse || { polygon: [] };
    },

    get shelves() {
      return this.layout.shelves || [];
    },

    get obstacles() {
      return this.layout.obstacles || [];
    },

    get bayTypes() {
      return this.layout.bayTypes || [];
    },

    get ceiling() {
      return this.layout.ceiling || [];
    },

    get selectedShelf() {
      return this.shelves.find((shelf) => shelf.id === this.selectedShelfId) || null;
    },

    get gapSliderMax() {
      const currentGap = this.selectedShelf ? geometry.num(this.selectedShelf.gap) : 0;
      return Math.max(1000, Math.ceil((currentGap + 300) / 100) * 100);
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
      this.shelves.forEach((shelf) => {
        geometry.footprintPolygon(shelf).forEach((point) => points.push(point));
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

    normalizeLayoutState(layout) {
      const warehouse = layout.warehouse || {};
      const polygon = geometry.warehousePolygon(warehouse);
      const normalizedBayTypes = (layout.bayTypes || []).map((entry, index) =>
        this.normalizeBayType(entry, index)
      );
      const normalizedShelves = (layout.shelves || []).map((entry, index) =>
        this.normalizeShelf(entry, index, normalizedBayTypes)
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
        bayTypes: this.mergeBayTypes(normalizedBayTypes, normalizedShelves),
        shelves: normalizedShelves,
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

    normalizeShelf(entry, index, sourceBayTypes) {
      const bayTypeId = String(
        entry.bayTypeId || entry.typeId || entry.id || `custom-${index + 1}`
      );
      const bayType = sourceBayTypes.find(
        (candidate) => String(candidate.id) === bayTypeId
      ) || {};
      return {
        id: String(entry.id || `shelf-${Date.now()}-${index}`),
        uid: String(entry.uid || entry.id || `shelf-${index + 1}`),
        label: String(entry.label || bayType.label || bayTypeId),
        bayTypeId,
        x: geometry.num(entry.x),
        y: geometry.num(entry.y),
        w: geometry.num(entry.w ?? entry.width, bayType.width || 1200),
        h: geometry.num(entry.h ?? entry.depth, bayType.depth || 800),
        height: geometry.num(entry.height, bayType.height || 2400),
        gap: Math.max(0, geometry.num(entry.gap, bayType.gap || 0)),
        nLoads: geometry.num(entry.nLoads, bayType.nLoads || 0),
        price: geometry.num(entry.price, bayType.price || 0),
        rotation: geometry.normalizeAngle(entry.rotation || 0, 30),
      };
    },

    mergeBayTypes(bayTypes, shelves) {
      const merged = bayTypes.map((entry) => ({ ...entry }));
      const byId = new Map(merged.map((entry) => [String(entry.id), entry]));

      shelves.forEach((shelf) => {
        if (byId.has(String(shelf.bayTypeId))) {
          return;
        }
        const derived = {
          id: String(shelf.bayTypeId),
          label: String(shelf.label || shelf.bayTypeId),
          width: geometry.num(shelf.w),
          depth: geometry.num(shelf.h),
          height: geometry.num(shelf.height),
          gap: geometry.num(shelf.gap),
          nLoads: geometry.num(shelf.nLoads),
          price: geometry.num(shelf.price),
        };
        merged.push(derived);
        byId.set(String(derived.id), derived);
      });

      return merged;
    },

    serializeLayout() {
      return {
        warehouse: this.warehouse,
        obstacles: this.obstacles,
        shelves: this.shelves,
        ceiling: this.ceiling,
        bayTypes: this.bayTypes,
        rawFiles: this.layout.rawFiles || [],
      };
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

    warehousePolygonPoints() {
      const bounds = this.bounds;
      return this.polygon
        .map((point) => `${this.screenX(point.x, bounds)},${this.screenY(point.y, bounds)}`)
        .join(" ");
    },

    rectStyle(item) {
      const bounds = this.bounds;
      const x = this.screenX(item.x, bounds);
      const y = this.screenY(item.y, bounds);
      const w = geometry.num(item.w ?? item.width) * bounds.scale;
      const h = geometry.num(item.h ?? item.depth) * bounds.scale;
      return [
        `left:${x}px`,
        `top:${y}px`,
        `width:${w}px`,
        `height:${h}px`,
      ].join("; ");
    },

    shelfStyle(shelf) {
      const bounds = this.bounds;
      const dims = geometry.itemDimensions(shelf);
      const footprint = geometry.footprintSize(shelf);
      return [
        `left:${this.screenX(shelf.x, bounds)}px`,
        `top:${this.screenY(shelf.y, bounds)}px`,
        `width:${footprint.w * bounds.scale}px`,
        `height:${footprint.h * bounds.scale}px`,
        `--rack-width:${dims.width * bounds.scale}px`,
        `--gap-width:${dims.gap * bounds.scale}px`,
        `transform:rotate(${geometry.normalizeAngle(shelf.rotation, 30)}deg)`,
        "transform-origin: top left",
      ].join("; ");
    },

    bayTypePreviewScale(bay) {
      const width = Math.max(1, geometry.num(bay.width));
      const depth = Math.max(1, geometry.num(bay.depth));
      const gap = Math.max(0, geometry.num(bay.gap));
      return Math.min(86 / (width + gap), 44 / depth);
    },

    bayFootprintPreviewStyle(bay) {
      const scale = this.bayTypePreviewScale(bay);
      return [
        `width:${Math.max(22, (geometry.num(bay.width) + geometry.num(bay.gap)) * scale)}px`,
        `height:${Math.max(10, geometry.num(bay.depth) * scale)}px`,
        `--preview-rack-width:${Math.max(12, geometry.num(bay.width) * scale)}px`,
        `--preview-gap-width:${Math.max(0, geometry.num(bay.gap) * scale)}px`,
      ].join("; ");
    },

    bayTypeMatchesDraft(bay) {
      return String(bay.id) === String(this.draftBay.label || "");
    },

    conflictMessageFor(shelf, ignoreId = null) {
      return geometry.firstViolation(
        shelf,
        this.shelves,
        this.obstacles,
        this.warehouse,
        ignoreId || shelf.id
      );
    },

    setPlacementError(message) {
      this.saveError = message || null;
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
      this.saveError = null;
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
          if (!this.conflictMessageFor(candidate, candidate.id)) {
            return { x: candidate.x, y: candidate.y };
          }
        }
      }
      return null;
    },

    addShelf() {
      const bayType = this.ensureDraftBayType();
      const prototype = {
        id: `shelf-${Date.now()}`,
        uid: `shelf-${Date.now()}`,
        label: String(this.draftBay.label || bayType.label || bayType.id),
        bayTypeId: String(bayType.id),
        x: 0,
        y: 0,
        w: geometry.num(bayType.width),
        h: geometry.num(bayType.depth),
        height: geometry.num(bayType.height),
        gap: geometry.num(bayType.gap),
        nLoads: geometry.num(bayType.nLoads),
        price: geometry.num(bayType.price),
        rotation: 0,
      };
      const position = this.firstFreePosition(prototype);
      if (!position) {
        this.setPlacementError(
          "No free valid space found for this bay. Adjust its measurements or clear shelves."
        );
        return;
      }

      const shelf = { ...prototype, x: position.x, y: position.y };
      this.layout.shelves = [...this.shelves, shelf];
      this.selectedShelfId = shelf.id;
      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    removeShelf(id) {
      this.layout.shelves = this.shelves.filter((shelf) => shelf.id !== id);
      if (this.selectedShelfId === id) {
        this.selectedShelfId = this.shelves[0]?.id || null;
      }
      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    clearShelves() {
      this.layout.shelves = [];
      this.selectedShelfId = null;
      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    deleteSelectedShelf() {
      if (!this.selectedShelf) {
        return;
      }
      this.removeShelf(this.selectedShelf.id);
    },

    selectShelf(shelf) {
      this.selectedShelfId = shelf.id;
    },

    startDrag(event, shelf) {
      this.selectShelf(shelf);
      this.draggingShelfId = shelf.id;

      const canvasRect = this.$refs.canvas.getBoundingClientRect();
      const scaleX = CANVAS_W / canvasRect.width;
      const scaleY = CANVAS_H / canvasRect.height;
      const mouseX = (event.clientX - canvasRect.left) * scaleX;
      const mouseY = (event.clientY - canvasRect.top) * scaleY;
      const bounds = this.bounds;
      this.dragOffsetX = mouseX - this.screenX(shelf.x, bounds);
      this.dragOffsetY = mouseY - this.screenY(shelf.y, bounds);
    },

    dragShelf(event) {
      if (!this.draggingShelfId) {
        return;
      }
      const shelf = this.shelves.find((entry) => entry.id === this.draggingShelfId);
      if (!shelf) {
        return;
      }

      const canvasRect = this.$refs.canvas.getBoundingClientRect();
      const scaleX = CANVAS_W / canvasRect.width;
      const scaleY = CANVAS_H / canvasRect.height;
      const mouseX = (event.clientX - canvasRect.left) * scaleX;
      const mouseY = (event.clientY - canvasRect.top) * scaleY;
      const bounds = this.bounds;

      const previous = { x: shelf.x, y: shelf.y };
      shelf.x = this.snap(this.worldX(mouseX - this.dragOffsetX, bounds));
      shelf.y = this.snap(this.worldY(mouseY - this.dragOffsetY, bounds));

      const conflict = this.conflictMessageFor(shelf, shelf.id);
      if (conflict) {
        shelf.x = previous.x;
        shelf.y = previous.y;
        this.setPlacementError(conflict);
        return;
      }

      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    stopDrag() {
      this.draggingShelfId = null;
    },

    setSelectedRotation(value) {
      const shelf = this.selectedShelf;
      if (!shelf) {
        return;
      }
      const previous = shelf.rotation;
      shelf.rotation = geometry.normalizeAngle(value, 30);
      const conflict = this.conflictMessageFor(shelf, shelf.id);
      if (conflict) {
        shelf.rotation = previous;
        this.setPlacementError(conflict);
        return;
      }
      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    setSelectedGap(value) {
      const shelf = this.selectedShelf;
      if (!shelf) {
        return;
      }
      const previous = shelf.gap;
      shelf.gap = Math.max(0, Math.round(geometry.num(value)));
      const conflict = this.conflictMessageFor(shelf, shelf.id);
      if (conflict) {
        shelf.gap = previous;
        this.setPlacementError(conflict);
        return;
      }

      const matchingType = this.bayTypes.find(
        (bay) => String(bay.id) === String(shelf.bayTypeId)
      );
      if (matchingType) {
        matchingType.gap = shelf.gap;
      }
      this.saved = false;
      this.validationIssues = [];
      this.setPlacementError(null);
    },

    async saveLayout() {
      this.saving = true;
      this.saved = false;
      this.setPlacementError(null);
      this.validationIssues = [];

      const layout = this.serializeLayout();

      for (const shelf of layout.shelves) {
        const conflict = this.conflictMessageFor(shelf, shelf.id);
        if (conflict) {
          this.saving = false;
          this.selectedShelfId = shelf.id;
          this.setPlacementError(conflict);
          return;
        }
      }

      if (this.isRealMode) {
        try {
          const validationResponse = await fetch("/api/validate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_id: projectId, layout }),
          });
          const validation = await validationResponse.json();
          if (!validationResponse.ok) {
            throw new Error(validation.error || "Could not validate layout");
          }
          if (!validation.is_valid) {
            this.validationIssues = validation.issues || [];
            const invalidId = validation.invalid_bay_ids?.[0];
            if (invalidId) {
              this.selectedShelfId = invalidId;
            }
            this.setPlacementError(
              validation.issues?.[0]?.message ||
                validation.issues?.[0] ||
                "Layout is invalid."
            );
            this.saving = false;
            return;
          }
        } catch (error) {
          this.saving = false;
          this.setPlacementError(error.message || "Could not validate layout");
          return;
        }
      }

      try {
        const response = await fetch(`/api/layouts/${projectId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(layout),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "Could not save layout");
        }
        this.layout = this.normalizeLayoutState(payload.layout || layout);
        this.saved = true;
      } catch (error) {
        this.setPlacementError(error.message || "Could not save layout");
      } finally {
        this.saving = false;
      }
    },
  };
}

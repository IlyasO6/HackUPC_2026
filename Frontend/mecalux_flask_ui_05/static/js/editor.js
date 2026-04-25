function warehouseEditor(initialLayout, projectId) {
  const CANVAS_W = 1000;
  const CANVAS_H = 650;
  const MARGIN = 35;

  return {
    layout: initialLayout,
    warehouse: initialLayout.warehouse || { width: 10000, height: 6500 },
    shelves: initialLayout.shelves || [],
    obstacles: initialLayout.obstacles || [],
    bayTypes: initialLayout.bayTypes || [],
    ceiling: initialLayout.ceiling || [],
    saved: false,
    saving: false,
    saveError: null,

    canvasW: CANVAS_W,
    canvasH: CANVAS_H,
    draggingShelfId: null,
    dragOffsetX: 0,
    dragOffsetY: 0,
    selectedShelfId: null,
    selectedBayTypeId: (initialLayout.bayTypes && initialLayout.bayTypes[0] && initialLayout.bayTypes[0].id) || null,

    get selectedShelf() {
      return this.shelves.find((shelf) => shelf.id === this.selectedShelfId) || null;
    },

    get selectedBayType() {
      return this.bayTypes.find((bay) => String(bay.id) === String(this.selectedBayTypeId)) || this.bayTypes[0] || null;
    },

<<<<<<< HEAD
=======
    get gapSliderMax() {
      const currentGap = this.selectedShelf ? this.shelfGap(this.selectedShelf) : 0;
      return Math.max(1000, Math.ceil((currentGap + 250) / 100) * 100);
    },

>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
    get polygon() {
      if (this.warehouse.polygon && this.warehouse.polygon.length >= 3) {
        return this.warehouse.polygon;
      }
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
      this.shelves.forEach((s) => {
<<<<<<< HEAD
        const footprint = this.shelfFootprintSize(s);
        points.push({ x: Number(s.x || 0), y: Number(s.y || 0) });
        points.push({ x: Number(s.x || 0) + footprint.w, y: Number(s.y || 0) + footprint.h });
=======
        this.rectCorners(s).forEach((corner) => points.push(corner));
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
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
      const offsetX = (CANVAS_W - drawnW) / 2;
      const offsetY = (CANVAS_H - drawnH) / 2;

      return { minX, maxX, minY, maxY, width, height, scale, offsetX, offsetY };
    },

    toScreenX(x) {
<<<<<<< HEAD
      const b = this.bounds;
      return b.offsetX + (Number(x || 0) - b.minX) * b.scale;
    },

    toScreenY(y) {
      const b = this.bounds;
      return b.offsetY + (Number(y || 0) - b.minY) * b.scale;
    },

    toWorldX(x) {
      const b = this.bounds;
      return (Number(x || 0) - b.offsetX) / b.scale + b.minX;
    },

    toWorldY(y) {
      const b = this.bounds;
=======
      return this.screenX(x, this.bounds);
    },

    toScreenY(y) {
      return this.screenY(y, this.bounds);
    },

    toWorldX(x) {
      return this.worldX(x, this.bounds);
    },

    toWorldY(y) {
      return this.worldY(y, this.bounds);
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
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
      return (Number(y || 0) - b.offsetY) / b.scale + b.minY;
    },

    snap(value) {
      const step = this.bounds.width > 2000 ? 100 : 25;
      return Math.round(value / step) * step;
    },

    warehousePolygonPoints() {
<<<<<<< HEAD
      return this.polygon.map((p) => `${this.toScreenX(p.x)},${this.toScreenY(p.y)}`).join(" ");
    },

    rectStyle(item) {
      const x = this.toScreenX(item.x);
      const y = this.toScreenY(item.y);
      const w = Number(item.w || item.width || 0) * this.bounds.scale;
      const h = Number(item.h || item.depth || 0) * this.bounds.scale;
=======
      const b = this.bounds;
      return this.polygon.map((p) => `${this.screenX(p.x, b)},${this.screenY(p.y, b)}`).join(" ");
    },

    rectStyle(item) {
      const b = this.bounds;
      const x = this.screenX(item.x, b);
      const y = this.screenY(item.y, b);
      const w = Number(item.w || item.width || 0) * b.scale;
      const h = Number(item.h || item.depth || 0) * b.scale;
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
      const rotation = Number(item.rotation || 0);
      const transform = rotation ? ` transform: rotate(${rotation}deg); transform-origin: center center;` : "";
      return `left:${x}px; top:${y}px; width:${w}px; height:${h}px;${transform}`;
    },

    shelfStyle(shelf) {
<<<<<<< HEAD
      const x = this.toScreenX(shelf.x);
      const y = this.toScreenY(shelf.y);
      const footprint = this.shelfFootprintSize(shelf);
      const rackDepth = this.itemSize(shelf).h * this.bounds.scale;
      const gapDepth = this.shelfGap(shelf) * this.bounds.scale;
=======
      const b = this.bounds;
      const x = this.screenX(shelf.x, b);
      const y = this.screenY(shelf.y, b);
      const footprint = this.shelfFootprintSize(shelf);
      const rackDepth = this.itemSize(shelf).h * b.scale;
      const gapDepth = this.shelfGap(shelf) * b.scale;
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
      const rotation = Number(shelf.rotation || 0);
      const transform = rotation ? ` transform: rotate(${rotation}deg); transform-origin: center center;` : "";
      return [
        `left:${x}px`,
        `top:${y}px`,
<<<<<<< HEAD
        `width:${footprint.w * this.bounds.scale}px`,
        `height:${footprint.h * this.bounds.scale}px`,
=======
        `width:${footprint.w * b.scale}px`,
        `height:${footprint.h * b.scale}px`,
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
        `--rack-depth:${rackDepth}px`,
        `--gap-depth:${gapDepth}px`,
        transform,
      ].join("; ");
    },

    unitCost(bay) {
      const price = Number(bay.price || 0);
      const loads = Number(bay.nLoads || bay.loads || 0);
      if (!loads) return "-";
      return (price / loads).toFixed(2);
    },

<<<<<<< HEAD
    bayTypePreviewStyle(bay) {
      const w = Math.max(1, Number(bay.width || 1));
      const h = Math.max(1, Number(bay.depth || bay.height || 1));
      const scale = Math.min(76 / w, 44 / h);
      return `width:${Math.max(10, w * scale)}px; height:${Math.max(8, h * scale)}px;`;
=======
    bayTypePreviewScale(bay) {
      const w = Math.max(1, Number(bay.width || 1));
      const h = Math.max(1, Number(bay.depth || bay.height || 1));
      const footprintH = h + this.bayGap(bay);
      return Math.min(76 / w, 46 / Math.max(1, footprintH));
    },

    bayFootprintPreviewStyle(bay) {
      const w = Math.max(1, Number(bay.width || 1));
      const h = Math.max(1, Number(bay.depth || bay.height || 1));
      const gap = this.bayGap(bay);
      const scale = this.bayTypePreviewScale(bay);
      return [
        `width:${Math.max(16, w * scale)}px`,
        `height:${Math.max(10, (h + gap) * scale)}px`,
        `--preview-rack-depth:${Math.max(6, h * scale)}px`,
        `--preview-gap-depth:${gap * scale}px`,
      ].join("; ");
    },

    bayGapPreviewStyle(bay) {
      return `height:${this.bayGap(bay) * this.bayTypePreviewScale(bay)}px;`;
    },

    bayRackPreviewStyle(bay) {
      const h = Math.max(1, Number(bay.depth || bay.height || 1));
      return `height:${Math.max(6, h * this.bayTypePreviewScale(bay))}px;`;
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
    },


    obstacleLabel(obs) {
      return obs.id || obs.label || "Obstacle";
    },

    itemSize(item) {
      return {
        w: Number(item.w || item.width || 0),
        h: Number(item.h || item.depth || 0),
      };
    },

<<<<<<< HEAD
    shelfGap(shelf) {
      return Math.max(0, Number(shelf.gap || 0));
=======
    bayGap(bay) {
      return Math.max(0, Number(bay.gap || 0));
    },

    shelfGap(shelf) {
      return this.bayGap(shelf);
    },

    gapLabelVisible(shelf) {
      return this.shelfGap(shelf) * this.bounds.scale > 18;
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
    },

    shelfFootprintSize(shelf) {
      const size = this.itemSize(shelf);
      return {
        w: size.w,
        h: size.h + this.shelfGap(shelf),
      };
    },

    rectCorners(item) {
      const { w, h } = this.shelfFootprintSize(item);
      const x = Number(item.x || 0);
      const y = Number(item.y || 0);
      const rotation = (((Number(item.rotation || 0) % 360) + 360) % 360) * Math.PI / 180;
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

    obstacleCorners(obs) {
      return [
        { x: Number(obs.x || 0), y: Number(obs.y || 0) },
        { x: Number(obs.x || 0) + Number(obs.w || obs.width || 0), y: Number(obs.y || 0) },
        { x: Number(obs.x || 0) + Number(obs.w || obs.width || 0), y: Number(obs.y || 0) + Number(obs.h || obs.depth || 0) },
        { x: Number(obs.x || 0), y: Number(obs.y || 0) + Number(obs.h || obs.depth || 0) },
      ];
    },

    polygonEdges(poly) {
      return poly.map((p, i) => [p, poly[(i + 1) % poly.length]]);
    },

    pointOnSegment(p, a, b) {
      const eps = 1e-7;
      const cross = (p.y - a.y) * (b.x - a.x) - (p.x - a.x) * (b.y - a.y);
      if (Math.abs(cross) > eps) return false;
      return p.x >= Math.min(a.x, b.x) - eps && p.x <= Math.max(a.x, b.x) + eps &&
             p.y >= Math.min(a.y, b.y) - eps && p.y <= Math.max(a.y, b.y) + eps;
    },

    pointInWarehouse(p) {
      const poly = this.polygon;
      for (const [a, b] of this.polygonEdges(poly)) {
        if (this.pointOnSegment(p, a, b)) return true;
      }
      let inside = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const pi = poly[i];
        const pj = poly[j];
        const intersects = ((pi.y > p.y) !== (pj.y > p.y)) &&
          (p.x < (pj.x - pi.x) * (p.y - pi.y) / ((pj.y - pi.y) || 1e-12) + pi.x);
        if (intersects) inside = !inside;
      }
      return inside;
    },

    orientation(a, b, c) {
      const v = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
      if (Math.abs(v) < 1e-7) return 0;
      return v > 0 ? 1 : 2;
    },

    segmentsProperlyIntersect(a, b, c, d) {
      const o1 = this.orientation(a, b, c);
      const o2 = this.orientation(a, b, d);
      const o3 = this.orientation(c, d, a);
      const o4 = this.orientation(c, d, b);
      return o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0 && o1 !== o2 && o3 !== o4;
    },

    projection(poly, axis) {
      const values = poly.map((p) => p.x * axis.x + p.y * axis.y);
      return { min: Math.min(...values), max: Math.max(...values) };
    },

    polygonsOverlap(polyA, polyB) {
      const eps = 1e-7;
      const axes = [];
      for (const poly of [polyA, polyB]) {
        for (const [a, b] of this.polygonEdges(poly)) {
          const edge = { x: b.x - a.x, y: b.y - a.y };
          const length = Math.hypot(edge.x, edge.y) || 1;
          axes.push({ x: -edge.y / length, y: edge.x / length });
        }
      }
      for (const axis of axes) {
        const pa = this.projection(polyA, axis);
        const pb = this.projection(polyB, axis);
        if (pa.max <= pb.min + eps || pb.max <= pa.min + eps) return false;
      }
      return true;
    },

    shelfInsideWarehouse(shelf) {
      const corners = this.rectCorners(shelf);
      if (!corners.every((p) => this.pointInWarehouse(p))) return false;
      const shelfEdges = this.polygonEdges(corners);
      const whEdges = this.polygonEdges(this.polygon);
      for (const [a, b] of shelfEdges) {
        for (const [c, d] of whEdges) {
          if (this.segmentsProperlyIntersect(a, b, c, d)) return false;
        }
      }
      return true;
    },

    placementConflict(shelf, ignoreId = null) {
      if (!this.shelfInsideWarehouse(shelf)) return "outside warehouse";
      const shelfPoly = this.rectCorners(shelf);
      for (const obs of this.obstacles) {
        if (this.polygonsOverlap(shelfPoly, this.obstacleCorners(obs))) return `obstacle ${this.obstacleLabel(obs)}`;
      }
      for (const other of this.shelves) {
        if (other.id === ignoreId || other.id === shelf.id) continue;
        if (this.polygonsOverlap(shelfPoly, this.rectCorners(other))) return `shelf ${other.label || other.id}`;
      }
      return null;
    },

    isValidPlacement(shelf, ignoreId = null) {
      return !this.placementConflict(shelf, ignoreId);
    },

    setPlacementError(conflict) {
      if (!conflict) {
        this.saveError = null;
        return;
      }
      this.saveError = `Invalid placement: collision with ${conflict}.`;
    },

    selectBayType(bay) {
      this.selectedBayTypeId = bay.id;
    },

    selectShelf(shelf) {
      this.selectedShelfId = shelf.id;
      if (shelf.bayTypeId !== undefined && shelf.bayTypeId !== null) {
        this.selectedBayTypeId = shelf.bayTypeId;
      }
    },

    setSelectedRotation(value) {
      const shelf = this.selectedShelf;
      if (!shelf) return;
      const previous = Number(shelf.rotation || 0);
      let angle = Number(value || 0);
      angle = ((Math.round(angle) % 360) + 360) % 360;
      shelf.rotation = angle;

      const conflict = this.placementConflict(shelf, shelf.id);
      if (conflict) {
        shelf.rotation = previous;
        this.setPlacementError(conflict);
        return;
      }

      this.saved = false;
      this.saveError = null;
    },

<<<<<<< HEAD
=======
    setSelectedGap(value) {
      const shelf = this.selectedShelf;
      if (!shelf) return;

      const previous = this.shelfGap(shelf);
      const gap = Math.max(0, Math.round(Number(value || 0)));
      shelf.gap = gap;

      const conflict = this.placementConflict(shelf, shelf.id);
      if (conflict) {
        shelf.gap = previous;
        this.setPlacementError(conflict);
        return;
      }

      this.saved = false;
      this.saveError = null;
    },

>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
    defaultShelfSize() {
      const bay = this.selectedBayType;
      if (bay) {
        return {
          w: Number(bay.width || 1200),
          h: Number(bay.depth || 800),
          label: `T${bay.id}`,
          bayTypeId: bay.id,
          height: Number(bay.height || 0),
          gap: Number(bay.gap || 0),
          nLoads: Number(bay.nLoads || 0),
          price: Number(bay.price || 0),
        };
      }
      return {
        w: Math.max(500, Math.round(this.bounds.width * 0.12)),
        h: Math.max(300, Math.round(this.bounds.height * 0.08)),
        label: "S",
        bayTypeId: null,
      };
    },

    addShelf() {
      const next = this.shelves.length + 1;
      const size = this.defaultShelfSize();
      const baseShelf = {
        id: `shelf-${Date.now()}`,
        w: size.w,
        h: size.h,
        rotation: 0,
        label: size.label || String.fromCharCode(64 + ((next - 1) % 26) + 1),
        bayTypeId: size.bayTypeId,
        height: size.height,
        gap: size.gap,
        nLoads: size.nLoads,
        price: size.price,
      };

      const step = Math.max(100, this.snap(Math.min(size.w, size.h) / 2));
      const startX = this.bounds.minX + 100;
      const startY = this.bounds.minY + 100;
      const endX = this.bounds.maxX - size.w;
      const endY = this.bounds.maxY - (size.h + Number(size.gap || 0));

      for (let y = startY; y <= endY; y += step) {
        for (let x = startX; x <= endX; x += step) {
          const candidate = { ...baseShelf, x: this.snap(x), y: this.snap(y) };
          if (this.isValidPlacement(candidate, candidate.id)) {
            this.shelves.push(candidate);
            this.selectedShelfId = candidate.id;
            this.saved = false;
            this.saveError = null;
            return;
          }
        }
      }

      this.saveError = "No free valid space found for this bay type. Try a smaller bay or clear shelves.";
    },

    removeShelf(id) {
      this.shelves = this.shelves.filter((shelf) => shelf.id !== id);
      if (this.selectedShelfId === id) this.selectedShelfId = null;
      this.saved = false;
      this.saveError = null;
    },

    clearShelves() {
      this.shelves = [];
      this.selectedShelfId = null;
      this.saved = false;
      this.saveError = null;
    },

    deleteSelectedShelf() {
      if (!this.selectedShelfId) return;
      this.removeShelf(this.selectedShelfId);
    },

    startDrag(event, shelf) {
      this.selectShelf(shelf);
      this.draggingShelfId = shelf.id;

      const canvasRect = this.$refs.canvas.getBoundingClientRect();
      const scaleX = CANVAS_W / canvasRect.width;
      const scaleY = CANVAS_H / canvasRect.height;
      const mouseX = (event.clientX - canvasRect.left) * scaleX;
      const mouseY = (event.clientY - canvasRect.top) * scaleY;
<<<<<<< HEAD
      this.dragOffsetX = mouseX - this.toScreenX(shelf.x);
      this.dragOffsetY = mouseY - this.toScreenY(shelf.y);
=======
      const b = this.bounds;
      this.dragOffsetX = mouseX - this.screenX(shelf.x, b);
      this.dragOffsetY = mouseY - this.screenY(shelf.y, b);
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421
    },

    dragShelf(event) {
      if (!this.draggingShelfId) return;

      const shelf = this.shelves.find((s) => s.id === this.draggingShelfId);
      if (!shelf) return;

      const canvasRect = this.$refs.canvas.getBoundingClientRect();
      const scaleX = CANVAS_W / canvasRect.width;
      const scaleY = CANVAS_H / canvasRect.height;
      const mouseX = (event.clientX - canvasRect.left) * scaleX;
      const mouseY = (event.clientY - canvasRect.top) * scaleY;

<<<<<<< HEAD
      let newX = this.toWorldX(mouseX - this.dragOffsetX);
      let newY = this.toWorldY(mouseY - this.dragOffsetY);
=======
      const b = this.bounds;
      let newX = this.worldX(mouseX - this.dragOffsetX, b);
      let newY = this.worldY(mouseY - this.dragOffsetY, b);
>>>>>>> f22f6c81c239d38dcba436717fd21d1c308b4421

      const footprint = this.shelfFootprintSize(shelf);
      newX = Math.max(this.bounds.minX, Math.min(newX, this.bounds.maxX - footprint.w));
      newY = Math.max(this.bounds.minY, Math.min(newY, this.bounds.maxY - footprint.h));

      const oldX = shelf.x;
      const oldY = shelf.y;
      shelf.x = this.snap(newX);
      shelf.y = this.snap(newY);

      const conflict = this.placementConflict(shelf, shelf.id);
      if (conflict) {
        shelf.x = oldX;
        shelf.y = oldY;
        this.setPlacementError(conflict);
        return;
      }

      this.saved = false;
      this.saveError = null;
    },

    stopDrag() {
      this.draggingShelfId = null;
    },

    async saveLayout() {
      this.saving = true;
      this.saveError = null;

      for (const shelf of this.shelves) {
        const conflict = this.placementConflict(shelf, shelf.id);
        if (conflict) {
          this.saving = false;
          this.selectedShelfId = shelf.id;
          this.setPlacementError(conflict);
          return;
        }
      }

      const payload = {
        warehouse: this.warehouse,
        obstacles: this.obstacles,
        shelves: this.shelves,
        ceiling: this.ceiling,
        bayTypes: this.bayTypes,
        rawFiles: this.layout.rawFiles || [],
      };

      try {
        const response = await fetch(`/api/layouts/${projectId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error("Could not save layout");
        }

        this.saved = true;
      } catch (error) {
        this.saveError = error.message || "Could not save layout";
      } finally {
        this.saving = false;
      }
    },
  };
}

(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.LayoutGeometry = factory();
})(typeof self !== "undefined" ? self : globalThis, function () {
  function num(value, fallback = 0) {
    if (value === null || value === undefined || value === "") {
      return Number(fallback);
    }
    return Number(value);
  }

  function normalizeAngle(angle, step = 1) {
    const safeStep = Math.max(1, Number(step || 1));
    const snapped = Math.round(num(angle) / safeStep) * safeStep;
    const normalized = ((snapped % 360) + 360) % 360;
    return normalized === 360 ? 0 : normalized;
  }

  function warehousePolygon(warehouse) {
    if (Array.isArray(warehouse)) {
      return warehouse.map((point) => ({ x: num(point.x), y: num(point.y) }));
    }
    const polygon = warehouse?.polygon || [];
    if (polygon.length >= 3) {
      return polygon.map((point) => ({ x: num(point.x), y: num(point.y) }));
    }
    const width = num(warehouse?.width, 10000);
    const height = num(warehouse?.height, 6500);
    return [
      { x: 0, y: 0 },
      { x: width, y: 0 },
      { x: width, y: height },
      { x: 0, y: height },
    ];
  }

  function polygonArea(points) {
    if (!points || points.length < 3) {
      return 0;
    }
    let area = 0;
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      area += current.x * next.y - next.x * current.y;
    }
    return Math.abs(area) / 2;
  }

  function itemDimensions(item) {
    return {
      width: num(item?.w ?? item?.width),
      depth: num(item?.h ?? item?.depth),
      gap: Math.max(0, num(item?.gap)),
    };
  }

  function footprintSize(item) {
    const dims = itemDimensions(item);
    return {
      w: dims.width + dims.gap,
      h: dims.depth,
    };
  }

  function unitVectors(angle) {
    const theta = (normalizeAngle(angle) * Math.PI) / 180;
    return {
      u: { x: Math.cos(theta), y: Math.sin(theta) },
      v: { x: -Math.sin(theta), y: Math.cos(theta) },
    };
  }

  function pointAt(origin, alongU, alongV, vectors) {
    return {
      x: origin.x + alongU * vectors.u.x + alongV * vectors.v.x,
      y: origin.y + alongU * vectors.u.y + alongV * vectors.v.y,
    };
  }

  function bodyPolygon(item) {
    const origin = { x: num(item?.x), y: num(item?.y) };
    const dims = itemDimensions(item);
    const vectors = unitVectors(item?.rotation);
    return [
      pointAt(origin, 0, 0, vectors),
      pointAt(origin, dims.width, 0, vectors),
      pointAt(origin, dims.width, dims.depth, vectors),
      pointAt(origin, 0, dims.depth, vectors),
    ];
  }

  function gapPolygon(item) {
    const origin = { x: num(item?.x), y: num(item?.y) };
    const dims = itemDimensions(item);
    if (dims.gap <= 0) {
      return [];
    }
    const vectors = unitVectors(item?.rotation);
    return [
      pointAt(origin, dims.width, 0, vectors),
      pointAt(origin, dims.width + dims.gap, 0, vectors),
      pointAt(origin, dims.width + dims.gap, dims.depth, vectors),
      pointAt(origin, dims.width, dims.depth, vectors),
    ];
  }

  function footprintPolygon(item) {
    const origin = { x: num(item?.x), y: num(item?.y) };
    const dims = itemDimensions(item);
    const vectors = unitVectors(item?.rotation);
    return [
      pointAt(origin, 0, 0, vectors),
      pointAt(origin, dims.width + dims.gap, 0, vectors),
      pointAt(origin, dims.width + dims.gap, dims.depth, vectors),
      pointAt(origin, 0, dims.depth, vectors),
    ];
  }

  function obstaclePolygon(item) {
    return [
      { x: num(item?.x), y: num(item?.y) },
      { x: num(item?.x) + num(item?.w ?? item?.width), y: num(item?.y) },
      {
        x: num(item?.x) + num(item?.w ?? item?.width),
        y: num(item?.y) + num(item?.h ?? item?.depth),
      },
      { x: num(item?.x), y: num(item?.y) + num(item?.h ?? item?.depth) },
    ];
  }

  function polygonEdges(poly) {
    return poly.map((point, index) => [point, poly[(index + 1) % poly.length]]);
  }

  function pointOnSegment(point, start, end) {
    const eps = 1e-7;
    const cross = (point.y - start.y) * (end.x - start.x) -
      (point.x - start.x) * (end.y - start.y);
    if (Math.abs(cross) > eps) {
      return false;
    }
    return point.x >= Math.min(start.x, end.x) - eps &&
      point.x <= Math.max(start.x, end.x) + eps &&
      point.y >= Math.min(start.y, end.y) - eps &&
      point.y <= Math.max(start.y, end.y) + eps;
  }

  function pointInPolygon(point, polygon) {
    for (const [start, end] of polygonEdges(polygon)) {
      if (pointOnSegment(point, start, end)) {
        return true;
      }
    }
    let inside = false;
    for (let index = 0, other = polygon.length - 1; index < polygon.length;
      other = index, index += 1) {
      const current = polygon[index];
      const prev = polygon[other];
      const intersects = ((current.y > point.y) !== (prev.y > point.y)) &&
        (point.x < ((prev.x - current.x) * (point.y - current.y)) /
          ((prev.y - current.y) || 1e-12) + current.x);
      if (intersects) {
        inside = !inside;
      }
    }
    return inside;
  }

  function orientation(a, b, c) {
    const value = (b.y - a.y) * (c.x - b.x) - (b.x - a.x) * (c.y - b.y);
    if (Math.abs(value) < 1e-7) {
      return 0;
    }
    return value > 0 ? 1 : 2;
  }

  function segmentsProperlyIntersect(a, b, c, d) {
    const o1 = orientation(a, b, c);
    const o2 = orientation(a, b, d);
    const o3 = orientation(c, d, a);
    const o4 = orientation(c, d, b);
    return o1 !== 0 && o2 !== 0 && o3 !== 0 && o4 !== 0 && o1 !== o2 && o3 !== o4;
  }

  function projection(poly, axis) {
    const values = poly.map((point) => point.x * axis.x + point.y * axis.y);
    return { min: Math.min(...values), max: Math.max(...values) };
  }

  function polygonsOverlap(polyA, polyB) {
    const axes = [];
    for (const poly of [polyA, polyB]) {
      for (const [start, end] of polygonEdges(poly)) {
        const edge = { x: end.x - start.x, y: end.y - start.y };
        const length = Math.hypot(edge.x, edge.y) || 1;
        axes.push({ x: -edge.y / length, y: edge.x / length });
      }
    }

    for (const axis of axes) {
      const a = projection(polyA, axis);
      const b = projection(polyB, axis);
      if (a.max <= b.min + 1e-7 || b.max <= a.min + 1e-7) {
        return false;
      }
    }
    return true;
  }

  function polygonBounds(poly) {
    const xs = poly.map((point) => point.x);
    const ys = poly.map((point) => point.y);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }

  function boundsOverlap(a, b) {
    return a.minX < b.maxX && a.maxX > b.minX &&
      a.minY < b.maxY && a.maxY > b.minY;
  }

  function polygonInsideWarehouse(poly, warehouse) {
    const warehousePoly = warehousePolygon(warehouse);
    if (!poly.every((point) => pointInPolygon(point, warehousePoly))) {
      return false;
    }
    for (const [a, b] of polygonEdges(poly)) {
      for (const [c, d] of polygonEdges(warehousePoly)) {
        if (segmentsProperlyIntersect(a, b, c, d)) {
          return false;
        }
      }
    }
    return true;
  }

  function placementViolations(candidate, bays, obstacles, warehouse, ignoreKey) {
    const warehousePoly = warehousePolygon(warehouse);
    const body = bodyPolygon(candidate);
    const gap = gapPolygon(candidate);
    const bodyBounds = polygonBounds(body);
    const gapBounds = gap.length ? polygonBounds(gap) : null;
    const violations = [];

    if (!polygonInsideWarehouse(body, warehousePoly)) {
      violations.push("Furniture body must stay inside the warehouse.");
    }
    if (gap.length && !polygonInsideWarehouse(gap, warehousePoly)) {
      violations.push("Front gap must stay inside the warehouse.");
    }

    for (const obstacle of obstacles || []) {
      const obstaclePoly = obstaclePolygon(obstacle);
      const obstacleBounds = polygonBounds(obstaclePoly);
      if (boundsOverlap(bodyBounds, obstacleBounds) &&
          polygonsOverlap(body, obstaclePoly)) {
        violations.push("Furniture body overlaps an obstacle.");
        break;
      }
      if (gap.length && gapBounds && boundsOverlap(gapBounds, obstacleBounds) &&
          polygonsOverlap(gap, obstaclePoly)) {
        violations.push("Front gap overlaps an obstacle.");
        break;
      }
    }

    const ignoreValue = ignoreKey == null ? null : String(ignoreKey);
    for (const other of bays || []) {
      const otherKey = String(other?.uid ?? other?.id ?? "");
      if (ignoreValue && otherKey === ignoreValue) {
        continue;
      }
      const otherBody = bodyPolygon(other);
      const otherBodyBounds = polygonBounds(otherBody);
      const otherGap = gapPolygon(other);
      const otherGapBounds = otherGap.length ? polygonBounds(otherGap) : null;

      if (boundsOverlap(bodyBounds, otherBodyBounds) &&
          polygonsOverlap(body, otherBody)) {
        violations.push("Furniture bodies cannot overlap.");
        break;
      }
      if (otherGap.length && otherGapBounds &&
          boundsOverlap(bodyBounds, otherGapBounds) &&
          polygonsOverlap(body, otherGap)) {
        violations.push("Furniture body occupies another bay's gap.");
        break;
      }
      if (gap.length && gapBounds &&
          boundsOverlap(gapBounds, otherBodyBounds) &&
          polygonsOverlap(gap, otherBody)) {
        violations.push("Front gap is occupied by another bay body.");
        break;
      }
    }

    return violations;
  }

  function firstViolation(candidate, bays, obstacles, warehouse, ignoreKey) {
    return placementViolations(candidate, bays, obstacles, warehouse, ignoreKey)[0] || null;
  }

  return {
    boundsOverlap,
    bodyPolygon,
    firstViolation,
    footprintPolygon,
    footprintSize,
    gapPolygon,
    itemDimensions,
    normalizeAngle,
    num,
    obstaclePolygon,
    placementViolations,
    pointInPolygon,
    polygonArea,
    polygonBounds,
    polygonsOverlap,
    warehousePolygon,
  };
});

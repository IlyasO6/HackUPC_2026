"""Greedy solver with arbitrary rotation and gap enforcement.

Strategy:
  1. Rank bay types by price/loads efficiency.
  2. Try multiple (bay_type, angle) configs.
  3. For each config, scan candidate positions and place where legal.
  4. Gap-fill with other types.
  5. Return solution with lowest Q score.

Rotation angles: 0 to 180 in configurable steps (default 45 deg).
Gap: enforced on the front face (x=width edge in local frame).
"""

from __future__ import annotations
import math

from models.case_data import CaseData
from models.bay_type import BayType
from models.solution import PlacedBay, Solution
from geometry.obb import convex_polygons_overlap, rotated_rect_inside_polygon
from geometry.spatial import rects_overlap
from scoring.scorer import compute_score
from solver.base import BaseSolver


# Pre-computed obstacle corner lists (avoids re-creating every check)
_ObsCorners = list[list[tuple[float, float]]]


class GreedySolver(BaseSolver):
    """Greedy solver with OBB rotation and gap enforcement."""

    def __init__(self, angle_step: float = 45.0):
        """angle_step: rotation granularity in degrees (default 45)."""
        self.angle_step = angle_step
        self.angles = []
        a = 0.0
        while a < 180.0:
            self.angles.append(a)
            a += angle_step
        # Always include key angles
        for key in [0.0, 45.0, 90.0, 135.0]:
            if key not in self.angles:
                self.angles.append(key)
        self.angles = sorted(set(self.angles))

    def solve(self, case: CaseData) -> Solution:
        obs_corners = _precompute_obstacles(case)
        configs = self._ranked_configs(case)
        best = Solution()
        best_q = float("inf")

        # Try top configs
        for bt, angle in configs[:12]:
            placed, corners_list, gaps_list, aabbs = self._pack_primary(
                case, bt, angle, obs_corners,
            )
            # Gap-fill
            placed, corners_list, gaps_list, aabbs = self._fill_gaps(
                case, placed, corners_list, gaps_list, aabbs, configs, obs_corners,
            )
            sol = Solution(placements=placed)
            q = compute_score(sol, case)
            if q < best_q:
                best_q = q
                best = sol

        return best

    # ── Config ranking ────────────────────────────────────────────

    def _ranked_configs(self, case: CaseData) -> list[tuple[BayType, float]]:
        configs: list[tuple[float, int, BayType, float]] = []
        for bt in case.bay_types:
            ratio = bt.price / bt.n_loads
            for angle in self.angles:
                configs.append((ratio, -bt.area, bt, angle))
        configs.sort(key=lambda c: (c[0], c[1]))
        return [(c[2], c[3]) for c in configs]

    # ── Packing ───────────────────────────────────────────────────

    def _pack_primary(self, case, bt, angle, obs_corners):
        return self._scan_and_place(case, bt, angle, obs_corners, [], [], [], [])

    def _fill_gaps(self, case, placed, corners_list, gaps_list, aabbs, configs, obs_corners):
        for bt, angle in configs:
            placed, corners_list, gaps_list, aabbs = self._scan_and_place(
                case, bt, angle, obs_corners, placed, corners_list, gaps_list, aabbs,
            )
        return placed, corners_list, gaps_list, aabbs

    def _scan_and_place(
        self, case, bt, angle, obs_corners,
        placed, corners_list, gaps_list, aabbs,
    ):
        placed = list(placed)
        corners_list = list(corners_list)
        gaps_list = list(gaps_list)
        aabbs = list(aabbs)

        poly = case.warehouse.vertex_tuples
        bbox = case.warehouse.bounding_box
        min_x, min_y, max_x, max_y = bbox

        # Candidate positions
        xs = self._candidate_x(case, aabbs, bt.width, bt.depth, angle)
        ys = self._candidate_y(case, aabbs, bt.width, bt.depth, angle)

        for y in ys:
            for x in xs:
                p = PlacedBay(bt.id, x, y, angle)
                cs = p.corners(bt.width, bt.depth)
                ab = p.aabb(bt.width, bt.depth)

                # Quick AABB bounds check
                if ab[0] < min_x - 1 or ab[1] < min_y - 1 or ab[2] > max_x + 1 or ab[3] > max_y + 1:
                    continue

                if not self._can_place(cs, ab, bt, p, poly, case, obs_corners,
                                       corners_list, gaps_list, aabbs):
                    continue

                gz = p.gap_zone(bt.width, bt.depth, bt.gap)
                placed.append(p)
                corners_list.append(cs)
                gaps_list.append(gz)
                aabbs.append(ab)

        return placed, corners_list, gaps_list, aabbs

    # ── Candidate positions ───────────────────────────────────────

    def _candidate_x(self, case, aabbs, w, d, angle):
        bbox = case.warehouse.bounding_box
        min_x, _, max_x, _ = bbox
        # Estimate rotated extent
        theta = math.radians(angle)
        ext_x = abs(w * math.cos(theta)) + abs(d * math.sin(theta))
        step = max(int(ext_x), 100)

        xs: set[int] = set()
        for v in case.warehouse.vertices:
            xs.add(v.x)
        for obs in case.obstacles:
            xs.add(obs.x + obs.width)
            xs.add(obs.x - int(ext_x))
        for ab in aabbs:
            xs.add(int(ab[2]))
            xs.add(int(ab[0]) - int(ext_x))

        x = min_x
        while x <= max_x:
            xs.add(x)
            x += step

        return sorted(x for x in xs if min_x - int(ext_x) <= x <= max_x)

    def _candidate_y(self, case, aabbs, w, d, angle):
        bbox = case.warehouse.bounding_box
        _, min_y, _, max_y = bbox
        theta = math.radians(angle)
        ext_y = abs(w * math.sin(theta)) + abs(d * math.cos(theta))
        step = max(int(ext_y), 100)

        ys: set[int] = set()
        for v in case.warehouse.vertices:
            ys.add(v.y)
        for obs in case.obstacles:
            ys.add(obs.y + obs.depth)
            ys.add(obs.y - int(ext_y))
        for ab in aabbs:
            ys.add(int(ab[3]))
            ys.add(int(ab[1]) - int(ext_y))

        y = min_y
        while y <= max_y:
            ys.add(y)
            y += step

        return sorted(y for y in ys if min_y - int(ext_y) <= y <= max_y)

    # ── Placement check ───────────────────────────────────────────

    @staticmethod
    def _can_place(cs, ab, bt, p, poly, case, obs_corners,
                   corners_list, gaps_list, aabbs):

        # 1. Inside warehouse
        if not rotated_rect_inside_polygon(cs, poly):
            return False

        # 2. Ceiling
        x_min, _, x_max, _ = ab
        max_h = case.ceiling.min_height_in_range(int(x_min), int(x_max) + 1)
        if bt.height > max_h:
            return False

        # 3. Obstacles
        for oc in obs_corners:
            if convex_polygons_overlap(cs, oc):
                return False

        # 4. Existing bay bodies (AABB pre-filter + OBB)
        for i, existing_cs in enumerate(corners_list):
            ea = aabbs[i]
            if ab[2] <= ea[0] or ea[2] <= ab[0] or ab[3] <= ea[1] or ea[3] <= ab[1]:
                continue
            if convex_polygons_overlap(cs, existing_cs):
                return False

        # 5. My body vs existing gap zones
        for gz in gaps_list:
            if gz and convex_polygons_overlap(cs, gz):
                return False

        # 6. My gap zone vs existing bodies
        gz_new = p.gap_zone(bt.width, bt.depth, bt.gap)
        if gz_new:
            for i, existing_cs in enumerate(corners_list):
                ea = aabbs[i]
                # Simple broad-phase: skip if clearly far
                if convex_polygons_overlap(gz_new, existing_cs):
                    return False

        return True


def _precompute_obstacles(case: CaseData) -> _ObsCorners:
    result = []
    for obs in case.obstacles:
        result.append([
            (float(obs.x), float(obs.y)),
            (float(obs.x + obs.width), float(obs.y)),
            (float(obs.x + obs.width), float(obs.y + obs.depth)),
            (float(obs.x), float(obs.y + obs.depth)),
        ])
    return result

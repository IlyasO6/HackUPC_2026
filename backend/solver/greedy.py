"""Backward-compatible shim for legacy greedy solver imports."""

from __future__ import annotations

from solver.hybrid import HybridSolver


GreedySolver = HybridSolver

__all__ = ["GreedySolver", "HybridSolver"]

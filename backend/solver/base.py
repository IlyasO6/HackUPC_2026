"""Abstract solver interface — to be implemented in Phase 2."""

from __future__ import annotations
from abc import ABC, abstractmethod

from models.case_data import CaseData
from models.solution import Solution


class BaseSolver(ABC):
    """Base class for all warehouse bay placement solvers.

    Subclasses must implement `solve()` which receives the full case
    data and returns a placement solution.
    """

    @abstractmethod
    def solve(self, case: CaseData) -> Solution:
        """Run the optimization algorithm and return a solution."""
        ...

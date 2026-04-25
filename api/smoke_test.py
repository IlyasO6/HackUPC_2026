#!/usr/bin/env python3
"""Smoke test: all imports."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from bridge import to_case_data
from scorer import calculate_score
from routes import router
print("ALL OK - no import errors")

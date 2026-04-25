#!/usr/bin/env python3
"""Minimal import smoke test for the API package."""

from __future__ import annotations

import os
import sys


sys.path.insert(0, os.path.dirname(__file__))

from bridge import snap_rotation, to_case_data
from layout_session import StatefulLayoutSession
from routes import router


print("bridge ok", snap_rotation(44.0))
print("session class ok", StatefulLayoutSession.__name__)
print("route count", len(router.routes))

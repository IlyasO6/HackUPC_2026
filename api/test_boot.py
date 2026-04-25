"""Test that the FastAPI app boots correctly."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from main import app
print("✓ FastAPI app created")
print("Routes:")
for r in app.routes:
    if hasattr(r, 'methods'):
        print(f"  {list(r.methods)} {r.path}")

"""
Mecalux Warehouse Optimizer API — Main Application

Single FastAPI service serving both the API endpoints and the static frontend.
Run with: uvicorn main:app --reload --port 8000
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routes import router

app = FastAPI(
    title="Mecalux Warehouse Optimizer",
    description="HackUPC 2026 — Optimize bay placement in warehouses",
    version="1.0.0",
)

# CORS — allow frontend to call API if served from different origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hackathon: accept all origins
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)

# Serve static frontend files (index.html, app.js, style.css)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

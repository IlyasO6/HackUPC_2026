"""FastAPI entrypoint serving both API routes and the static frontend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api_config import API_VERSION
from routes import router
from session_store import get_layout_session_store


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start and stop the session-expiration task with the app lifecycle."""

    store = get_layout_session_store()
    await store.start()
    try:
        yield
    finally:
        await store.stop()


app = FastAPI(
    title="Mecalux Warehouse Optimizer",
    description="Interactive warehouse optimization and live editing",
    version=API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount static assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=templates_dir)

import urllib.parse
from fastapi import Request, UploadFile, Form, File
from fastapi.responses import HTMLResponse, RedirectResponse
import uuid
import asyncio
from csv_parser import parse_all
from job_store import create_job
from api_models import Job as JobModel, OptimizationInput
from routes import _run_optimizer

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "error": error, "backend_mode": "real", "backend_url": ""}
    )

@app.post("/upload")
async def upload_files(
    warehouse_csv: UploadFile | None = File(None),
    obstacles_csv: UploadFile | None = File(None),
    ceiling_csv: UploadFile | None = File(None),
    types_of_bays_csv: UploadFile | None = File(None),
    case_zip: UploadFile | None = File(None),
    case_json: UploadFile | None = File(None),
    case_name: str | None = Form(None),
    next: str | None = Form(None),
):
    try:
        # Read UploadFile contents into strings
        async def _read(f: UploadFile | None) -> str:
            if f is None or f.filename == "":
                return ""
            data = await f.read()
            return data.decode("utf-8") if data else ""

        wh_text = await _read(warehouse_csv)
        obs_text = await _read(obstacles_csv)
        ceil_text = await _read(ceiling_csv)
        bays_text = await _read(types_of_bays_csv)

        if not wh_text.strip():
            raise ValueError("warehouse.csv is required")

        input_data: OptimizationInput = parse_all(
            warehouse_csv=wh_text,
            obstacles_csv=obs_text,
            ceiling_csv=ceil_text,
            bay_types_csv=bays_text,
        )

        # Create a job so the SSE stream and status endpoints work
        job = JobModel(input_data=input_data)
        create_job(job)
        job_id = job.id

        asyncio.create_task(_run_optimizer(job_id, input_data))
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)
    except Exception as e:
        return RedirectResponse(f"/?error={urllib.parse.quote(str(e))}", status_code=303)

@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_page(request: Request, job_id: str):
    return templates.TemplateResponse("job.html", {"request": request, "job_id": job_id, "backend_mode": "real", "backend_url": ""})

@app.get("/editor/{session_id}", response_class=HTMLResponse)
async def editor_page(request: Request, session_id: str):
    return templates.TemplateResponse("editor.html", {"request": request, "session_id": session_id, "backend_mode": "real", "backend_url": ""})


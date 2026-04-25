"""FastAPI entrypoint serving both API routes and the static frontend."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

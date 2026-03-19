from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.db import get_engine
from common.logging import get_logger

logger = get_logger("model-router")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting model-router")
    engine = get_engine()
    yield
    await engine.dispose()
    logger.info("Shutdown model-router")


app = FastAPI(title="model-router", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "model-router"}

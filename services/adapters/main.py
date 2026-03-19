from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.db import get_engine
from common.logging import get_logger

logger = get_logger("adapters")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting adapters")
    engine = get_engine()
    yield
    await engine.dispose()
    logger.info("Shutdown adapters")


app = FastAPI(title="adapters", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "adapters"}

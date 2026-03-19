from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.db import get_engine
from common.logging import get_logger

logger = get_logger("audit-service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting audit-service")
    engine = get_engine()
    yield
    await engine.dispose()
    logger.info("Shutdown audit-service")


app = FastAPI(title="audit-service", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "audit-service"}

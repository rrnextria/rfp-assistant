from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from common.db import get_engine
from common.logging import get_logger
from auth import router as auth_router, users_router
from proxy import router as proxy_router

logger = get_logger("api-gateway")
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting api-gateway")
    get_engine()
    yield
    await get_engine().dispose()
    logger.info("Shutdown api-gateway")


app = FastAPI(title="api-gateway", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(auth_router)
app.include_router(users_router)

# Proxy router must be last — its catch-all /{full_path:path} would shadow
# more specific routes if registered earlier.
app.include_router(proxy_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": "api-gateway"}

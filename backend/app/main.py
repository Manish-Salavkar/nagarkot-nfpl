import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import AsyncSessionLocal, apply_migrations, wait_for_db
from app.routes import api_router
from app.seed import seed_sample_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nfpl")


# Startup and shutdown lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    await wait_for_db(max_retries=20, delay_seconds=1.0)
    apply_migrations()
    async with AsyncSessionLocal() as session:
        await seed_sample_data(session)
    yield


app = FastAPI(
    title="NFPL Access Control Service",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# Health check
@app.get("/healthz")
async def health_check():
    return {"status": "ok", "app_env": settings.APP_ENV}

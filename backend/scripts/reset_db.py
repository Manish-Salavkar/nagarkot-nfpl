import asyncio
import logging
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from app.config import settings
from app.database import AsyncSessionLocal, apply_migrations, engine
from app.seed import seed_sample_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nfpl")


# Reset database tables and reseed
async def reset_database():
    if settings.APP_ENV.lower() == "production":
        logger.error("Database reset not allowed in production.")
        sys.exit(1)

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE audit_events, permission_grants, jobs, users, branches, clients CASCADE;"))

    apply_migrations()

    async with AsyncSessionLocal() as session:
        await seed_sample_data(session)

    logger.info("Database reset complete.")


if __name__ == "__main__":
    asyncio.run(reset_database())

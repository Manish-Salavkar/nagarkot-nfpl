import os
import sys
import uuid
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.database import AsyncSessionLocal, apply_migrations, engine, wait_for_db
from app.main import app
from app.models import Branch, Client, User
from app.seed import seed_sample_data


# Prepare test database with initial schema and seed
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    await wait_for_db(max_retries=10, delay_seconds=1.0)
    apply_migrations()
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE audit_events, permission_grants, jobs, users, branches, clients CASCADE;"))
    async with AsyncSessionLocal() as session:
        await seed_sample_data(session)
    yield


# Database session fixture
@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


# Async HTTP test client
@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# Users lookup dictionary
@pytest_asyncio.fixture
async def users_map(db_session):
    stmt = select(User)
    res = await db_session.execute(stmt)
    users = res.scalars().all()
    return {u.username: u for u in users}


# Clients lookup dictionary
@pytest_asyncio.fixture
async def clients_map(db_session):
    stmt = select(Client)
    res = await db_session.execute(stmt)
    clients = res.scalars().all()
    return {c.code: c for c in clients}


# Branches lookup dictionary
@pytest_asyncio.fixture
async def branches_map(db_session):
    stmt = select(Branch)
    res = await db_session.execute(stmt)
    branches = res.scalars().all()
    return {b.code: b for b in branches}

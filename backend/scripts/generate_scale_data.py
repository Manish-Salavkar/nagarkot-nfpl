import argparse
import asyncio
import logging
import random
import sys
import time
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import insert, select, text
from app.database import AsyncSessionLocal, engine
from app.models import (
    Branch,
    Client,
    Direction,
    GrantEffect,
    Job,
    JobStatus,
    Mode,
    PermissionGrant,
    Role,
    User,
    UserType,
    utc_now,
)
from app.seed import seed_sample_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nfpl")


# Generate scale users and jobs in bulk
async def generate_scale_data(
    target_users: int = 500,
    target_jobs: int = 200000,
    batch_size: int = 5000,
    random_seed: int = 42,
):
    rng = random.Random(random_seed)
    start_time = time.time()

    async with AsyncSessionLocal() as session:
        await seed_sample_data(session)

    async with AsyncSessionLocal() as session:
        b_res = await session.execute(select(Branch.id))
        branch_ids = b_res.scalars().all()

        c_res = await session.execute(select(Client.id))
        client_ids = c_res.scalars().all()

        admin_res = await session.execute(select(User).where(User.username == "admin_sarah"))
        admin_user = admin_res.scalars().first()
        admin_id = admin_user.id if admin_user else uuid.uuid4()

        u_res = await session.execute(select(User.id))
        existing_user_ids = u_res.scalars().all()

    current_user_count = len(existing_user_ids)
    needed_users = max(0, target_users - current_user_count)

    user_ids = list(existing_user_ids)
    if needed_users > 0:
        new_users = []
        new_grants = []
        roles_pool = [Role.MAKER, Role.CHECKER, Role.CLIENT_VIEWER, Role.ADMIN]

        for i in range(1, needed_users + 1):
            uid = uuid.uuid4()
            uname = f"scale_user_{current_user_count + i:05d}"
            role = rng.choices(roles_pool, weights=[0.60, 0.30, 0.08, 0.02])[0]
            utype = UserType.CLIENT if role == Role.CLIENT_VIEWER else UserType.STAFF
            cid = rng.choice(client_ids) if utype == UserType.CLIENT else None

            new_users.append({
                "id": uid,
                "username": uname,
                "full_name": f"Scale Staff {current_user_count + i}",
                "user_type": utype,
                "client_id": cid,
                "is_active": True,
                "created_at": utc_now(),
            })
            user_ids.append(uid)

            scope_client = rng.choice(client_ids) if rng.random() > 0.4 else None
            scope_branch = rng.choice(branch_ids) if rng.random() > 0.4 else None
            scope_dir = rng.choice(list(Direction)) if rng.random() > 0.6 else None
            scope_mode = rng.choice(list(Mode)) if rng.random() > 0.6 else None

            new_grants.append({
                "id": uuid.uuid4(),
                "user_id": uid,
                "role": role,
                "client_id": scope_client,
                "branch_id": scope_branch,
                "direction": scope_dir,
                "mode": scope_mode,
                "effect": GrantEffect.ALLOW,
                "granted_by_id": admin_id,
                "created_at": utc_now(),
                "revoked_at": None,
                "revoked_by_id": None,
            })

        async with engine.begin() as conn:
            for chunk_start in range(0, len(new_users), batch_size):
                chunk = new_users[chunk_start:chunk_start + batch_size]
                await conn.execute(insert(User), chunk)

            for chunk_start in range(0, len(new_grants), batch_size):
                chunk = new_grants[chunk_start:chunk_start + batch_size]
                await conn.execute(insert(PermissionGrant), chunk)

    async with AsyncSessionLocal() as session:
        job_count_res = await session.execute(select(text("COUNT(*) FROM jobs")))
        current_jobs_count = job_count_res.scalar() or 0

    needed_jobs = max(0, target_jobs - current_jobs_count)
    directions = list(Direction)
    modes = list(Mode)
    statuses = list(JobStatus)
    status_weights = [0.25, 0.25, 0.25, 0.20, 0.05]

    total_inserted = 0
    now = utc_now()

    while total_inserted < needed_jobs:
        current_batch_len = min(batch_size, needed_jobs - total_inserted)
        batch_jobs = []

        for _ in range(current_batch_len):
            idx = current_jobs_count + total_inserted + len(batch_jobs) + 1
            cid = rng.choice(client_ids)
            bid = rng.choice(branch_ids)
            dir_val = rng.choice(directions)
            mode_val = rng.choice(modes)
            status_val = rng.choices(statuses, weights=status_weights)[0]
            assigned_id = rng.choice(user_ids) if rng.random() > 0.1 else None

            prep_by = rng.choice(user_ids) if status_val in (JobStatus.PREPARED, JobStatus.CHECKED, JobStatus.FILED) else None
            chk_by = rng.choice(user_ids) if status_val in (JobStatus.CHECKED, JobStatus.FILED) else None
            if chk_by and chk_by == prep_by:
                chk_by = admin_id
            fld_by = chk_by if status_val == JobStatus.FILED else None

            batch_jobs.append({
                "id": uuid.uuid4(),
                "job_number": f"SCALE-{idx:08d}",
                "client_id": cid,
                "branch_id": bid,
                "direction": dir_val,
                "mode": mode_val,
                "status": status_val,
                "assigned_user_id": assigned_id,
                "prepared_by_id": prep_by,
                "checked_by_id": chk_by,
                "filed_by_id": fld_by,
                "created_by_id": admin_id,
                "created_at": now,
                "updated_at": now,
            })

        async with engine.begin() as conn:
            await conn.execute(insert(Job), batch_jobs)

        total_inserted += current_batch_len
        logger.info(f"Progress: {total_inserted}/{needed_jobs} jobs inserted ({total_inserted / needed_jobs * 100:.1f}%)")

    elapsed = time.time() - start_time
    logger.info(f"Scale generation complete in {elapsed:.2f}s. Total: {target_users} users, {target_jobs} jobs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NFPL Access Control Scale Dataset Generator")
    parser.add_argument("--users", type=int, default=500, help="Target total users")
    parser.add_argument("--jobs", type=int, default=200000, help="Target total jobs")
    parser.add_argument("--batch-size", type=int, default=10000, help="Batch size")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    asyncio.run(generate_scale_data(
        target_users=args.users,
        target_jobs=args.jobs,
        batch_size=args.batch_size,
        random_seed=args.seed,
    ))

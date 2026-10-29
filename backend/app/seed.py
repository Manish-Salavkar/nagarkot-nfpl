import logging
import random
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Action,
    AuditEvent,
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

logger = logging.getLogger("nfpl")


# Seed initial reference data, users, grants, and jobs
async def seed_sample_data(db: AsyncSession) -> None:
    existing_user = await db.execute(select(User).where(User.username == "admin_sarah"))
    if existing_user.scalars().first():
        return

    branch_data = [
        ("BR-SYD", "Sydney Gateway"),
        ("BR-MEL", "Melbourne Port"),
        ("BR-BNE", "Brisbane Cargo"),
        ("BR-PER", "Perth International"),
        ("BR-ADL", "Adelaide Hub"),
    ]
    branches = {}
    for code, name in branch_data:
        branch = Branch(code=code, name=name, is_active=True)
        db.add(branch)
        branches[code] = branch

    client_data = [
        ("CLI-ACME", "Acme Corporation"),
        ("CLI-GLBL", "Global Logistics Inc"),
        ("CLI-NEXUS", "Nexus Electronics"),
        ("CLI-ZENITH", "Zenith Manufacturing"),
        ("CLI-APEX", "Apex Consumer Goods"),
        ("CLI-PACIFIC", "Pacific Trading Co"),
        ("CLI-HORIZON", "Horizon Retailers"),
        ("CLI-VORTEX", "Vortex Pharma"),
        ("CLI-TITAN", "Titan Machinery"),
        ("CLI-SOLAR", "Solar Energy Systems"),
    ]
    clients = {}
    for code, name in client_data:
        client = Client(code=code, name=name, is_active=True)
        db.add(client)
        clients[code] = client

    await db.flush()

    admin_sarah = User(
        username="admin_sarah",
        full_name="Sarah Jenkins",
        user_type=UserType.STAFF,
        is_active=True,
    )
    db.add(admin_sarah)
    await db.flush()

    users = {"admin_sarah": admin_sarah}
    user_definitions = [
        ("admin_mark", "Mark Stevens", UserType.STAFF, None, True),
        ("maker_checker_alex", "Alex Rivera", UserType.STAFF, None, True),
        ("checker_lucas", "Lucas Thorne", UserType.STAFF, None, True),
        ("maker_emma", "Emma Watson", UserType.STAFF, None, True),
        ("maker_david", "David Kim", UserType.STAFF, None, True),
        ("checker_rachel", "Rachel Green", UserType.STAFF, None, True),
        ("absent_john", "John Doe (On Leave)", UserType.STAFF, None, True),
        ("client_jane", "Jane Miller (ACME)", UserType.CLIENT, clients["CLI-ACME"].id, True),
        ("client_bob", "Bob Taylor (Global)", UserType.CLIENT, clients["CLI-GLBL"].id, True),
        ("service_parser", "Overnight Parser Bot", UserType.SERVICE, None, True),
        ("revoked_oliver", "Oliver Queen", UserType.STAFF, None, True),
        ("denied_sam", "Sam Vance", UserType.STAFF, None, True),
        ("maker_liam", "Liam Neeson", UserType.STAFF, None, True),
        ("checker_sophia", "Sophia Loren", UserType.STAFF, None, True),
        ("maker_noah", "Noah Clark", UserType.STAFF, None, True),
        ("checker_chloe", "Chloe Bennett", UserType.STAFF, None, True),
        ("maker_ryan", "Ryan Gosling", UserType.STAFF, None, True),
        ("inactive_grace", "Grace Hopper", UserType.STAFF, None, False),
        ("viewer_frank", "Frank Castle", UserType.STAFF, None, True),
    ]

    for uname, fname, utype, cid, active in user_definitions:
        u = User(username=uname, full_name=fname, user_type=utype, client_id=cid, is_active=active)
        db.add(u)
        users[uname] = u

    await db.flush()

    grants = [
        PermissionGrant(user_id=users["admin_sarah"].id, role=Role.ADMIN, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["admin_mark"].id, role=Role.ADMIN, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_checker_alex"].id, role=Role.MAKER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_checker_alex"].id, role=Role.CHECKER, client_id=clients["CLI-ACME"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_checker_alex"].id, role=Role.CHECKER, client_id=clients["CLI-GLBL"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(
            user_id=users["checker_lucas"].id,
            role=Role.CHECKER,
            client_id=clients["CLI-ACME"].id,
            branch_id=branches["BR-SYD"].id,
            direction=Direction.IMPORT,
            effect=GrantEffect.ALLOW,
            granted_by_id=users["admin_sarah"].id,
        ),
        PermissionGrant(user_id=users["maker_emma"].id, role=Role.MAKER, branch_id=branches["BR-SYD"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_emma"].id, role=Role.MAKER, branch_id=branches["BR-MEL"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_david"].id, role=Role.MAKER, client_id=clients["CLI-NEXUS"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_david"].id, role=Role.MAKER, client_id=clients["CLI-ZENITH"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_david"].id, role=Role.MAKER, client_id=clients["CLI-APEX"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["checker_rachel"].id, role=Role.CHECKER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["absent_john"].id, role=Role.MAKER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["absent_john"].id, role=Role.CHECKER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["client_jane"].id, role=Role.CLIENT_VIEWER, client_id=clients["CLI-ACME"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["client_bob"].id, role=Role.CLIENT_VIEWER, client_id=clients["CLI-GLBL"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(
            user_id=users["revoked_oliver"].id,
            role=Role.MAKER,
            effect=GrantEffect.ALLOW,
            granted_by_id=users["admin_sarah"].id,
            revoked_at=utc_now(),
            revoked_by_id=users["admin_sarah"].id,
        ),
        PermissionGrant(user_id=users["denied_sam"].id, role=Role.MAKER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["denied_sam"].id, role=Role.MAKER, mode=Mode.AIR, effect=GrantEffect.DENY, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_liam"].id, role=Role.MAKER, mode=Mode.AIR, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["checker_sophia"].id, role=Role.CHECKER, mode=Mode.FCL, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["checker_sophia"].id, role=Role.CHECKER, mode=Mode.LCL, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_noah"].id, role=Role.MAKER, branch_id=branches["BR-BNE"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["checker_chloe"].id, role=Role.CHECKER, branch_id=branches["BR-PER"].id, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["maker_ryan"].id, role=Role.MAKER, direction=Direction.EXPORT, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
        PermissionGrant(user_id=users["viewer_frank"].id, role=Role.CLIENT_VIEWER, effect=GrantEffect.ALLOW, granted_by_id=users["admin_sarah"].id),
    ]

    for g in grants:
        db.add(g)

    await db.flush()

    client_keys = list(clients.keys())
    branch_keys = list(branches.keys())
    directions = list(Direction)
    modes = list(Mode)

    edge_case_jobs = [
        Job(
            job_number="JOB-SELF-001",
            client_id=clients["CLI-ACME"].id,
            branch_id=branches["BR-SYD"].id,
            direction=Direction.IMPORT,
            mode=Mode.FCL,
            status=JobStatus.PREPARED,
            assigned_user_id=users["maker_checker_alex"].id,
            prepared_by_id=users["maker_checker_alex"].id,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-ABSENT-001",
            client_id=clients["CLI-GLBL"].id,
            branch_id=branches["BR-MEL"].id,
            direction=Direction.EXPORT,
            mode=Mode.AIR,
            status=JobStatus.CONFIRMED,
            assigned_user_id=users["absent_john"].id,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-ABSENT-002",
            client_id=clients["CLI-NEXUS"].id,
            branch_id=branches["BR-BNE"].id,
            direction=Direction.IMPORT,
            mode=Mode.LCL,
            status=JobStatus.PREPARED,
            assigned_user_id=users["absent_john"].id,
            prepared_by_id=users["maker_david"].id,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-FILED-001",
            client_id=clients["CLI-ACME"].id,
            branch_id=branches["BR-SYD"].id,
            direction=Direction.IMPORT,
            mode=Mode.AIR,
            status=JobStatus.FILED,
            assigned_user_id=users["maker_checker_alex"].id,
            prepared_by_id=users["maker_emma"].id,
            checked_by_id=users["checker_rachel"].id,
            filed_by_id=users["checker_rachel"].id,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-CANCELLED-001",
            client_id=clients["CLI-ZENITH"].id,
            branch_id=branches["BR-PER"].id,
            direction=Direction.EXPORT,
            mode=Mode.FCL,
            status=JobStatus.CANCELLED,
            assigned_user_id=None,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-LUCAS-ACT-001",
            client_id=clients["CLI-ACME"].id,
            branch_id=branches["BR-SYD"].id,
            direction=Direction.IMPORT,
            mode=Mode.AIR,
            status=JobStatus.PREPARED,
            assigned_user_id=users["checker_lucas"].id,
            prepared_by_id=users["maker_emma"].id,
            created_by_id=users["admin_sarah"].id,
        ),
        Job(
            job_number="JOB-LUCAS-DENY-001",
            client_id=clients["CLI-ACME"].id,
            branch_id=branches["BR-SYD"].id,
            direction=Direction.EXPORT,
            mode=Mode.AIR,
            status=JobStatus.PREPARED,
            assigned_user_id=users["checker_lucas"].id,
            prepared_by_id=users["maker_emma"].id,
            created_by_id=users["admin_sarah"].id,
        ),
    ]

    for j in edge_case_jobs:
        db.add(j)

    rng = random.Random(42)
    statuses = [JobStatus.CONFIRMED, JobStatus.PREPARED, JobStatus.CHECKED, JobStatus.FILED]
    staff_users = [
        users["maker_checker_alex"],
        users["maker_emma"],
        users["maker_david"],
        users["checker_rachel"],
        users["maker_liam"],
        users["checker_sophia"],
        users["maker_noah"],
        users["checker_chloe"],
        users["maker_ryan"],
    ]

    for i in range(1, 221):
        ckey = rng.choice(client_keys)
        bkey = rng.choice(branch_keys)
        direction = rng.choice(directions)
        mode = rng.choice(modes)
        status = rng.choice(statuses)
        assigned = rng.choice(staff_users)

        prep_by = None
        chk_by = None
        fld_by = None

        if status in (JobStatus.PREPARED, JobStatus.CHECKED, JobStatus.FILED):
            prep_by = users["maker_emma"].id
        if status in (JobStatus.CHECKED, JobStatus.FILED):
            chk_by = users["checker_rachel"].id
        if status == JobStatus.FILED:
            fld_by = users["checker_rachel"].id

        job = Job(
            job_number=f"JOB-SAMPLE-{i:04d}",
            client_id=clients[ckey].id,
            branch_id=branches[bkey].id,
            direction=direction,
            mode=mode,
            status=status,
            assigned_user_id=assigned.id,
            prepared_by_id=prep_by,
            checked_by_id=chk_by,
            filed_by_id=fld_by,
            created_by_id=users["admin_sarah"].id,
        )
        db.add(job)

    await db.flush()
    initial_audit = AuditEvent(
        job_id=edge_case_jobs[0].id,
        actor_id=users["maker_checker_alex"].id,
        event_type="WORKFLOW_TRANSITION",
        action=Action.PREPARE.value,
        decision=GrantEffect.ALLOW,
        reason="Initial preparation completed",
        before_data={"status": "CONFIRMED"},
        after_data={"status": "PREPARED"},
    )
    db.add(initial_audit)
    await db.commit()

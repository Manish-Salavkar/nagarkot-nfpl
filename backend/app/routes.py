import math
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import record_audit_event
from app.authorization import AuthorizationService
from app.database import get_db
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
from app.schemas import (
    AuditEventRead,
    AuthorizationCheckRequest,
    AuthorizationCheckResponse,
    BranchRead,
    ClientRead,
    JobActionRequest,
    JobCreate,
    JobRead,
    JobReassignRequest,
    JobUpdate,
    PaginatedResponse,
    PermissionGrantCreate,
    PermissionGrantRead,
    UserRead,
)
from app.workflow import WorkflowService

api_router = APIRouter(prefix="/api")


# Extract user from header or query
async def get_current_actor(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    user_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    target_id_str = x_user_id or (str(user_id) if user_id else None)
    if not target_id_str:
        return None
    try:
        uid = uuid.UUID(target_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format.")
    return await db.get(User, uid)


# Require active user
async def require_actor(
    actor: Optional[User] = Depends(get_current_actor),
) -> User:
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide X-User-Id header.",
        )
    if not actor.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "USER_INACTIVE", "message": f"User {actor.username} is deactivated."},
        )
    return actor


# Helper to attach codes to job response
def enrich_job_read(job: Job) -> JobRead:
    res = JobRead.model_validate(job)
    if job.client:
        res.client_code = job.client.code
        res.client_name = job.client.name
    if job.branch:
        res.branch_code = job.branch.code
        res.branch_name = job.branch.name
    if job.assigned_user:
        res.assigned_username = job.assigned_user.username
    return res


# List users
@api_router.get("/users", response_model=List[UserRead])
async def list_users(
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.full_name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


# List active clients
@api_router.get("/clients", response_model=List[ClientRead])
async def list_clients(
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Client).where(Client.is_active.is_(True)).order_by(Client.code.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


# List active branches
@api_router.get("/branches", response_model=List[BranchRead])
async def list_branches(
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.code.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


# List permission grants
@api_router.get("/permissions", response_model=List[PermissionGrantRead])
async def list_permissions(
    user_id: Optional[uuid.UUID] = Query(None),
    include_revoked: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PermissionGrant)
    if user_id:
        stmt = stmt.where(PermissionGrant.user_id == user_id)
    if not include_revoked:
        stmt = stmt.where(PermissionGrant.revoked_at.is_(None))
    stmt = stmt.order_by(desc(PermissionGrant.created_at))
    res = await db.execute(stmt)
    return res.scalars().all()


# Create permission grant
@api_router.post("/permissions", response_model=PermissionGrantRead, status_code=status.HTTP_201_CREATED)
async def create_permission_grant(
    grant_in: PermissionGrantCreate,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    decision = await AuthorizationService.evaluate(
        db=db,
        user_id=actor.id,
        action=Action.MANAGE_PERMISSIONS,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": decision.code, "message": decision.reason},
        )

    if grant_in.user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ADMIN_SELF_ESCALATION_DISALLOWED",
                "message": "Administrators cannot grant permissions to themselves.",
            },
        )

    target_user = await db.get(User, grant_in.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user does not exist.")

    grant = PermissionGrant(
        user_id=grant_in.user_id,
        role=grant_in.role,
        client_id=grant_in.client_id,
        branch_id=grant_in.branch_id,
        direction=grant_in.direction,
        mode=grant_in.mode,
        effect=grant_in.effect,
        granted_by_id=actor.id,
    )
    db.add(grant)
    await db.flush()

    await record_audit_event(
        db=db,
        event_type="PERMISSION_GRANTED",
        actor_id=actor.id,
        action=Action.MANAGE_PERMISSIONS.value,
        decision=GrantEffect.ALLOW,
        reason=f"Granted role {grant.role.value} to {target_user.username}",
        after_data={
            "grant_id": str(grant.id),
            "target_user_id": str(grant.user_id),
            "role": grant.role.value,
            "effect": grant.effect.value,
            "client_id": str(grant.client_id) if grant.client_id else None,
            "branch_id": str(grant.branch_id) if grant.branch_id else None,
        },
    )
    await db.commit()
    await db.refresh(grant)
    return grant


# Revoke permission grant
@api_router.post("/permissions/{grant_id}/revoke", response_model=PermissionGrantRead)
async def revoke_permission_grant(
    grant_id: uuid.UUID,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    decision = await AuthorizationService.evaluate(
        db=db,
        user_id=actor.id,
        action=Action.MANAGE_PERMISSIONS,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": decision.code, "message": decision.reason},
        )

    grant = await db.get(PermissionGrant, grant_id)
    if not grant:
        raise HTTPException(status_code=404, detail="Permission grant not found.")
    if grant.revoked_at is not None:
        raise HTTPException(status_code=400, detail="Permission grant is already revoked.")

    before_data = {"revoked_at": None, "revoked_by_id": None}
    grant.revoked_at = utc_now()
    grant.revoked_by_id = actor.id
    after_data = {"revoked_at": grant.revoked_at.isoformat(), "revoked_by_id": str(actor.id)}

    await record_audit_event(
        db=db,
        event_type="PERMISSION_REVOKED",
        actor_id=actor.id,
        action=Action.MANAGE_PERMISSIONS.value,
        decision=GrantEffect.ALLOW,
        reason=f"Revoked grant {grant.id}",
        before_data=before_data,
        after_data=after_data,
    )
    await db.commit()
    await db.refresh(grant)
    return grant


# Query jobs with filters and pagination
@api_router.get("/jobs", response_model=PaginatedResponse[JobRead])
async def list_jobs(
    client_id: Optional[uuid.UUID] = Query(None),
    branch_id: Optional[uuid.UUID] = Query(None),
    status_filter: Optional[JobStatus] = Query(None, alias="status"),
    direction: Optional[Direction] = Query(None),
    mode: Optional[Mode] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: Optional[User] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Job)
        .options(
            selectinload(Job.client),
            selectinload(Job.branch),
            selectinload(Job.assigned_user),
        )
    )

    if actor and actor.user_type == UserType.CLIENT:
        stmt = stmt.where(Job.client_id == actor.client_id)
    elif client_id:
        stmt = stmt.where(Job.client_id == client_id)

    if branch_id:
        stmt = stmt.where(Job.branch_id == branch_id)
    if status_filter:
        stmt = stmt.where(Job.status == status_filter)
    if direction:
        stmt = stmt.where(Job.direction == direction)
    if mode:
        stmt = stmt.where(Job.mode == mode)
    if search:
        stmt = stmt.where(Job.job_number.ilike(f"%{search.strip()}%"))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(desc(Job.created_at)).offset((page - 1) * page_size).limit(page_size)
    jobs_res = await db.execute(stmt)
    jobs = jobs_res.scalars().all()

    enriched = [enrich_job_read(j) for j in jobs]
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedResponse(
        items=enriched,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# Create new job
@api_router.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_in: JobCreate,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    if actor.user_type == UserType.SERVICE:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.INGEST,
            client_id=job_in.client_id,
            branch_id=job_in.branch_id,
            direction=job_in.direction,
            mode=job_in.mode,
        )
    else:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.PREPARE,
            client_id=job_in.client_id,
            branch_id=job_in.branch_id,
            direction=job_in.direction,
            mode=job_in.mode,
        )
        if not decision.allowed:
            admin_dec = await AuthorizationService.evaluate(
                db=db, user_id=actor.id, action=Action.VIEW
            )
            if admin_dec.allowed:
                decision = admin_dec

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": decision.code, "message": decision.reason},
        )

    existing = await db.execute(select(Job).where(Job.job_number == job_in.job_number))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Job number already exists.")

    job = Job(
        job_number=job_in.job_number,
        client_id=job_in.client_id,
        branch_id=job_in.branch_id,
        direction=job_in.direction,
        mode=job_in.mode,
        status=JobStatus.CONFIRMED,
        assigned_user_id=job_in.assigned_user_id or actor.id,
        created_by_id=actor.id,
    )
    db.add(job)
    await db.flush()

    await record_audit_event(
        db=db,
        event_type="JOB_CREATED",
        actor_id=actor.id,
        job_id=job.id,
        action="CREATE",
        decision=GrantEffect.ALLOW,
        reason=f"Created job {job.job_number}",
        after_data={
            "job_number": job.job_number,
            "status": job.status.value,
            "client_id": str(job.client_id),
            "branch_id": str(job.branch_id),
        },
    )
    await db.commit()

    stmt = (
        select(Job)
        .options(
            selectinload(Job.client),
            selectinload(Job.branch),
            selectinload(Job.assigned_user),
        )
        .where(Job.id == job.id)
    )
    res = await db.execute(stmt)
    created_job = res.scalar_one()
    return enrich_job_read(created_job)


# Fetch single job
@api_router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    actor: Optional[User] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Job)
        .options(
            selectinload(Job.client),
            selectinload(Job.branch),
            selectinload(Job.assigned_user),
        )
        .where(Job.id == job_id)
    )
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if actor:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.VIEW,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

    return enrich_job_read(job)


# Update basic job fields
@api_router.patch("/jobs/{job_id}", response_model=JobRead)
async def update_job(
    job_id: uuid.UUID,
    update_in: JobUpdate,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Job)
        .options(
            selectinload(Job.client),
            selectinload(Job.branch),
            selectinload(Job.assigned_user),
        )
        .where(Job.id == job_id)
    )
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    decision = await AuthorizationService.evaluate(
        db=db,
        user_id=actor.id,
        action=Action.VIEW,
        job=job,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": decision.code, "message": decision.reason},
        )

    before_data = {
        "direction": job.direction.value,
        "mode": job.mode.value,
        "assigned_user_id": str(job.assigned_user_id) if job.assigned_user_id else None,
    }

    if update_in.direction is not None:
        job.direction = update_in.direction
    if update_in.mode is not None:
        job.mode = update_in.mode
    if update_in.assigned_user_id is not None:
        job.assigned_user_id = update_in.assigned_user_id

    after_data = {
        "direction": job.direction.value,
        "mode": job.mode.value,
        "assigned_user_id": str(job.assigned_user_id) if job.assigned_user_id else None,
    }

    await record_audit_event(
        db=db,
        event_type="JOB_UPDATED",
        actor_id=actor.id,
        job_id=job.id,
        action="UPDATE",
        decision=GrantEffect.ALLOW,
        reason="Updated job attributes",
        before_data=before_data,
        after_data=after_data,
    )
    await db.commit()
    await db.refresh(job)
    return enrich_job_read(job)


# Transition job to PREPARED
@api_router.post("/jobs/{job_id}/prepare", response_model=JobRead)
async def prepare_job(
    job_id: uuid.UUID,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.prepare_job(db=db, job=job, actor=actor)
    return enrich_job_read(updated_job)


# Transition job to CHECKED
@api_router.post("/jobs/{job_id}/check", response_model=JobRead)
async def check_job(
    job_id: uuid.UUID,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.check_job(db=db, job=job, actor=actor)
    return enrich_job_read(updated_job)


# Transition job to FILED
@api_router.post("/jobs/{job_id}/file", response_model=JobRead)
async def file_job(
    job_id: uuid.UUID,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.file_job(db=db, job=job, actor=actor)
    return enrich_job_read(updated_job)


# Cancel a job
@api_router.post("/jobs/{job_id}/cancel", response_model=JobRead)
async def cancel_job(
    job_id: uuid.UUID,
    req: JobActionRequest,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.cancel_job(db=db, job=job, actor=actor, reason=req.reason)
    return enrich_job_read(updated_job)


# Reopen a filed job
@api_router.post("/jobs/{job_id}/reopen", response_model=JobRead)
async def reopen_job(
    job_id: uuid.UUID,
    req: JobActionRequest,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.reopen_job(db=db, job=job, actor=actor, reason=req.reason)
    return enrich_job_read(updated_job)


# Reassign a job
@api_router.post("/jobs/{job_id}/reassign", response_model=JobRead)
async def reassign_job(
    job_id: uuid.UUID,
    req: JobReassignRequest,
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Job).options(selectinload(Job.client), selectinload(Job.branch), selectinload(Job.assigned_user)).where(Job.id == job_id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    updated_job = await WorkflowService.reassign_job(
        db=db,
        job=job,
        actor=actor,
        new_assigned_user_id=req.assigned_user_id,
        reason=req.reason,
    )
    return enrich_job_read(updated_job)


# Evaluate permission check without mutating
@api_router.post("/authorization/check", response_model=AuthorizationCheckResponse)
async def explain_authorization(
    req: AuthorizationCheckRequest,
    db: AsyncSession = Depends(get_db),
):
    job = None
    if req.job_id:
        job = await db.get(Job, req.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

    decision = await AuthorizationService.evaluate(
        db=db,
        user_id=req.user_id,
        action=req.action,
        job=job,
        client_id=req.client_id,
        branch_id=req.branch_id,
        direction=req.direction,
        mode=req.mode,
    )
    return AuthorizationCheckResponse(
        allowed=decision.allowed,
        code=decision.code,
        reason=decision.reason,
        matched_grant_id=decision.matched_grant_id,
        details=decision.details,
    )


# Get actionable work queue for active user
@api_router.get("/me/jobs", response_model=List[JobRead])
async def get_my_actionable_jobs(
    actor: User = Depends(require_actor),
    db: AsyncSession = Depends(get_db),
):
    if not actor.is_active or actor.user_type == UserType.CLIENT:
        return []

    grants_res = await db.execute(
        select(PermissionGrant).where(
            PermissionGrant.user_id == actor.id,
            PermissionGrant.revoked_at.is_(None),
            PermissionGrant.effect == GrantEffect.ALLOW,
        )
    )
    user_roles = {g.role for g in grants_res.scalars().all()}

    candidate_statuses = []
    if Role.MAKER in user_roles:
        candidate_statuses.append(JobStatus.CONFIRMED)
    if Role.CHECKER in user_roles:
        candidate_statuses.append(JobStatus.PREPARED)
        candidate_statuses.append(JobStatus.CHECKED)

    if not candidate_statuses:
        return []

    stmt = (
        select(Job)
        .options(
            selectinload(Job.client),
            selectinload(Job.branch),
            selectinload(Job.assigned_user),
        )
        .where(Job.status.in_(candidate_statuses))
        .order_by(Job.created_at.asc())
        .limit(200)
    )
    jobs_res = await db.execute(stmt)
    candidate_jobs = jobs_res.scalars().all()

    actionable_jobs: List[Job] = []
    for job in candidate_jobs:
        next_action = None
        if job.status == JobStatus.CONFIRMED:
            next_action = Action.PREPARE
        elif job.status == JobStatus.PREPARED:
            next_action = Action.CHECK
        elif job.status == JobStatus.CHECKED:
            next_action = Action.FILE

        if not next_action:
            continue

        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=next_action,
            job=job,
        )
        if decision.allowed:
            actionable_jobs.append(job)

    return [enrich_job_read(j) for j in actionable_jobs]


# Get audit history for a job
@api_router.get("/jobs/{job_id}/history", response_model=List[AuditEventRead])
async def get_job_history(
    job_id: uuid.UUID,
    actor: Optional[User] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if actor:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.VIEW,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

    stmt = (
        select(AuditEvent)
        .options(selectinload(AuditEvent.actor))
        .where(AuditEvent.job_id == job_id)
        .order_by(desc(AuditEvent.created_at))
    )
    res = await db.execute(stmt)
    events = res.scalars().all()

    read_events = []
    for ev in events:
        item = AuditEventRead.model_validate(ev)
        if ev.actor:
            item.actor_username = ev.actor.username
        read_events.append(item)
    return read_events


# List audit events with pagination
@api_router.get("/audit", response_model=PaginatedResponse[AuditEventRead])
async def list_audit_events(
    job_id: Optional[uuid.UUID] = Query(None),
    actor_id: Optional[uuid.UUID] = Query(None),
    event_type: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    actor: Optional[User] = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditEvent).options(selectinload(AuditEvent.actor))

    if job_id:
        stmt = stmt.where(AuditEvent.job_id == job_id)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if start_time:
        stmt = stmt.where(AuditEvent.created_at >= start_time)
    if end_time:
        stmt = stmt.where(AuditEvent.created_at <= end_time)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(desc(AuditEvent.created_at)).offset((page - 1) * page_size).limit(page_size)
    events_res = await db.execute(stmt)
    events = events_res.scalars().all()

    items = []
    for ev in events:
        read_item = AuditEventRead.model_validate(ev)
        if ev.actor:
            read_item.actor_username = ev.actor.username
        items.append(read_item)

    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

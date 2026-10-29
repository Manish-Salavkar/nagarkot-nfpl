import uuid
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import record_audit_event
from app.authorization import AuthorizationService
from app.models import Action, GrantEffect, Job, JobStatus, User


# Workflow state transition engine
class WorkflowService:

    # Transition from CONFIRMED to PREPARED
    @staticmethod
    async def prepare_job(
        db: AsyncSession,
        job: Job,
        actor: User,
    ) -> Job:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.PREPARE,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

        before = {"status": job.status.value, "prepared_by_id": str(job.prepared_by_id) if job.prepared_by_id else None}
        job.status = JobStatus.PREPARED
        job.prepared_by_id = actor.id
        after = {"status": job.status.value, "prepared_by_id": str(job.prepared_by_id)}

        await record_audit_event(
            db=db,
            event_type="WORKFLOW_TRANSITION",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.PREPARE.value,
            decision=GrantEffect.ALLOW,
            reason="Job checklist prepared",
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

    # Transition from PREPARED to CHECKED
    @staticmethod
    async def check_job(
        db: AsyncSession,
        job: Job,
        actor: User,
    ) -> Job:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.CHECK,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

        before = {"status": job.status.value, "checked_by_id": str(job.checked_by_id) if job.checked_by_id else None}
        job.status = JobStatus.CHECKED
        job.checked_by_id = actor.id
        after = {"status": job.status.value, "checked_by_id": str(job.checked_by_id)}

        await record_audit_event(
            db=db,
            event_type="WORKFLOW_TRANSITION",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.CHECK.value,
            decision=GrantEffect.ALLOW,
            reason="Job verification and check completed",
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

    # Transition from CHECKED to FILED
    @staticmethod
    async def file_job(
        db: AsyncSession,
        job: Job,
        actor: User,
    ) -> Job:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.FILE,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

        before = {"status": job.status.value, "filed_by_id": str(job.filed_by_id) if job.filed_by_id else None}
        job.status = JobStatus.FILED
        job.filed_by_id = actor.id
        after = {"status": job.status.value, "filed_by_id": str(job.filed_by_id)}

        await record_audit_event(
            db=db,
            event_type="WORKFLOW_TRANSITION",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.FILE.value,
            decision=GrantEffect.ALLOW,
            reason="Job filed with customs/carrier",
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

    # Cancel a job with required reason
    @staticmethod
    async def cancel_job(
        db: AsyncSession,
        job: Job,
        actor: User,
        reason: Optional[str] = None,
    ) -> Job:
        if job.status == JobStatus.CANCELLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ALREADY_CANCELLED", "message": "Job is already cancelled."},
            )

        if not reason or not reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "REASON_REQUIRED", "message": "A documented reason is required to cancel a job."},
            )

        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.CANCEL,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

        before = {"status": job.status.value}
        job.status = JobStatus.CANCELLED
        after = {"status": job.status.value}

        await record_audit_event(
            db=db,
            event_type="JOB_CANCELLED",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.CANCEL.value,
            decision=GrantEffect.ALLOW,
            reason=reason.strip(),
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

    # Reopen a filed job
    @staticmethod
    async def reopen_job(
        db: AsyncSession,
        job: Job,
        actor: User,
        reason: Optional[str] = None,
    ) -> Job:
        if job.status != JobStatus.FILED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_STATE", "message": "Only FILED jobs can be reopened."},
            )

        if not reason or not reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "REASON_REQUIRED", "message": "A documented reason is required to reopen a filed job."},
            )

        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.REOPEN,
            job=job,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": decision.code, "message": decision.reason},
            )

        before = {"status": job.status.value}
        job.status = JobStatus.PREPARED
        after = {"status": job.status.value}

        await record_audit_event(
            db=db,
            event_type="JOB_REOPENED",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.REOPEN.value,
            decision=GrantEffect.ALLOW,
            reason=reason.strip(),
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

    # Reassign a job to a different user
    @staticmethod
    async def reassign_job(
        db: AsyncSession,
        job: Job,
        actor: User,
        new_assigned_user_id: uuid.UUID,
        reason: Optional[str] = None,
    ) -> Job:
        decision = await AuthorizationService.evaluate(
            db=db,
            user_id=actor.id,
            action=Action.REASSIGN,
            job=job,
        )
        is_assigned_owner = job.assigned_user_id == actor.id
        if not decision.allowed and not is_assigned_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": decision.code if not decision.allowed else "NOT_AUTHORIZED",
                    "message": "Only administrators or the currently assigned owner can reassign this job.",
                },
            )

        target_user = await db.get(User, new_assigned_user_id)
        if not target_user or not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_TARGET_USER", "message": "Assigned target user does not exist or is inactive."},
            )

        before = {"assigned_user_id": str(job.assigned_user_id) if job.assigned_user_id else None}
        job.assigned_user_id = target_user.id
        after = {"assigned_user_id": str(job.assigned_user_id)}

        await record_audit_event(
            db=db,
            event_type="JOB_REASSIGNED",
            actor_id=actor.id,
            job_id=job.id,
            action=Action.REASSIGN.value,
            decision=GrantEffect.ALLOW,
            reason=reason or f"Reassigned to {target_user.username}",
            before_data=before,
            after_data=after,
        )
        await db.commit()
        await db.refresh(job)
        return job

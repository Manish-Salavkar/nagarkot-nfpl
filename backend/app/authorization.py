import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Action,
    Direction,
    GrantEffect,
    Job,
    JobStatus,
    Mode,
    PermissionGrant,
    Role,
    User,
    UserType,
)

ROLE_ACTIONS = {
    Role.MAKER: [Action.VIEW, Action.PREPARE],
    Role.CHECKER: [Action.VIEW, Action.CHECK, Action.FILE],
    Role.CLIENT_VIEWER: [Action.VIEW],
    Role.ADMIN: [
        Action.VIEW,
        Action.CANCEL,
        Action.REOPEN,
        Action.REASSIGN,
        Action.MANAGE_PERMISSIONS,
    ],
}

SERVICE_ALLOWED_ACTIONS = [Action.VIEW, Action.INGEST]


@dataclass
class AuthorizationDecision:
    allowed: bool
    code: str
    reason: str
    matched_grant_id: Optional[uuid.UUID] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "code": self.code,
            "reason": self.reason,
            "matched_grant_id": self.matched_grant_id,
            "details": self.details or {},
        }


# Check if a grant covers the target job dimensions
def matches_scope(
    grant: PermissionGrant,
    client_id: Optional[uuid.UUID],
    branch_id: Optional[uuid.UUID],
    direction: Optional[Direction],
    mode: Optional[Mode],
) -> bool:
    if grant.client_id is not None and client_id is not None and grant.client_id != client_id:
        return False
    if grant.branch_id is not None and branch_id is not None and grant.branch_id != branch_id:
        return False
    if grant.direction is not None and direction is not None and grant.direction != direction:
        return False
    if grant.mode is not None and mode is not None and grant.mode != mode:
        return False
    return True


# Central permission checker
class AuthorizationService:

    # Evaluate whether a user can perform an action on a job
    @staticmethod
    async def evaluate(
        db: AsyncSession,
        user_id: uuid.UUID,
        action: Action,
        job: Optional[Job] = None,
        client_id: Optional[uuid.UUID] = None,
        branch_id: Optional[uuid.UUID] = None,
        direction: Optional[Direction] = None,
        mode: Optional[Mode] = None,
    ) -> AuthorizationDecision:
        user = await db.get(User, user_id)
        if not user:
            return AuthorizationDecision(
                allowed=False,
                code="USER_NOT_FOUND",
                reason=f"User {user_id} does not exist.",
            )
        if not user.is_active:
            return AuthorizationDecision(
                allowed=False,
                code="USER_INACTIVE",
                reason=f"User {user.username} is deactivated.",
            )

        target_client_id = job.client_id if job else client_id
        target_branch_id = job.branch_id if job else branch_id
        target_direction = job.direction if job else direction
        target_mode = job.mode if job else mode

        if user.user_type == UserType.SERVICE:
            if action not in SERVICE_ALLOWED_ACTIONS:
                return AuthorizationDecision(
                    allowed=False,
                    code="SERVICE_ACCOUNT_RESTRICTED",
                    reason=f"Service identity '{user.username}' is restricted to automated ingestion.",
                )
            return AuthorizationDecision(
                allowed=True,
                code="SERVICE_ALLOWED",
                reason=f"Service identity '{user.username}' authorized.",
            )

        if user.user_type == UserType.CLIENT:
            if action != Action.VIEW:
                return AuthorizationDecision(
                    allowed=False,
                    code="CLIENT_ACTION_RESTRICTED",
                    reason="Client-side users only possess view access to their own shipments.",
                )
            if target_client_id and user.client_id != target_client_id:
                return AuthorizationDecision(
                    allowed=False,
                    code="CLIENT_ISOLATION_VIOLATION",
                    reason=f"Client user '{user.username}' cannot access jobs belonging to other clients.",
                )

        if action == Action.MANAGE_PERMISSIONS:
            admin_stmt = select(PermissionGrant).where(
                PermissionGrant.user_id == user.id,
                PermissionGrant.role == Role.ADMIN,
                PermissionGrant.effect == GrantEffect.ALLOW,
                PermissionGrant.revoked_at.is_(None),
            )
            res = await db.execute(admin_stmt)
            admin_grant = res.scalars().first()
            if not admin_grant:
                return AuthorizationDecision(
                    allowed=False,
                    code="ADMIN_REQUIRED",
                    reason=f"User '{user.username}' lacks ADMIN role required to manage permissions.",
                )
            return AuthorizationDecision(
                allowed=True,
                code="ADMIN_ALLOWED",
                reason="Administrator authorized to manage permissions.",
                matched_grant_id=admin_grant.id,
            )

        if job:
            if job.status == JobStatus.CANCELLED and action != Action.VIEW:
                return AuthorizationDecision(
                    allowed=False,
                    code="JOB_CANCELLED",
                    reason=f"Job {job.job_number} is CANCELLED and cannot be modified.",
                )

            if action == Action.PREPARE and job.status != JobStatus.CONFIRMED:
                return AuthorizationDecision(
                    allowed=False,
                    code="INVALID_WORKFLOW_STATE",
                    reason=f"Job {job.job_number} is in status '{job.status.value}', but PREPARE requires 'CONFIRMED'.",
                )

            if action == Action.CHECK and job.status != JobStatus.PREPARED:
                return AuthorizationDecision(
                    allowed=False,
                    code="INVALID_WORKFLOW_STATE",
                    reason=f"Job {job.job_number} is in status '{job.status.value}', but CHECK requires 'PREPARED'.",
                )

            if action == Action.FILE and job.status != JobStatus.CHECKED:
                return AuthorizationDecision(
                    allowed=False,
                    code="INVALID_WORKFLOW_STATE",
                    reason=f"Job {job.job_number} is in status '{job.status.value}', but FILE requires 'CHECKED'.",
                )

            if action == Action.REOPEN and job.status != JobStatus.FILED:
                return AuthorizationDecision(
                    allowed=False,
                    code="INVALID_WORKFLOW_STATE",
                    reason=f"Job {job.job_number} is in status '{job.status.value}', but REOPEN requires 'FILED'.",
                )

            if action == Action.CHECK and job.prepared_by_id == user.id:
                return AuthorizationDecision(
                    allowed=False,
                    code="SELF_APPROVAL_DISALLOWED",
                    reason=f"User '{user.username}' prepared checklist for job {job.job_number} and cannot approve their own work.",
                )

        stmt = (
            select(PermissionGrant)
            .where(
                PermissionGrant.user_id == user.id,
                PermissionGrant.revoked_at.is_(None),
            )
            .order_by(PermissionGrant.created_at.asc())
        )
        res = await db.execute(stmt)
        active_grants = res.scalars().all()

        for grant in active_grants:
            if grant.effect == GrantEffect.DENY:
                allowed_for_role = ROLE_ACTIONS.get(grant.role, [])
                if action in allowed_for_role and matches_scope(
                    grant, target_client_id, target_branch_id, target_direction, target_mode
                ):
                    return AuthorizationDecision(
                        allowed=False,
                        code="EXPLICIT_DENY",
                        reason=f"Explicit DENY grant {grant.id} overrides access for role {grant.role.value}.",
                        matched_grant_id=grant.id,
                    )

        matched_allow_grant = None
        for grant in active_grants:
            if grant.effect == GrantEffect.ALLOW:
                allowed_for_role = ROLE_ACTIONS.get(grant.role, [])
                if action in allowed_for_role and matches_scope(
                    grant, target_client_id, target_branch_id, target_direction, target_mode
                ):
                    matched_allow_grant = grant
                    break

        if not matched_allow_grant:
            return AuthorizationDecision(
                allowed=False,
                code="NO_MATCHING_GRANT",
                reason=f"No active permission grant authorizes action '{action.value}' for user '{user.username}'.",
            )

        return AuthorizationDecision(
            allowed=True,
            code="ALLOWED",
            reason=f"Action '{action.value}' authorized under grant {matched_allow_grant.id}.",
            matched_grant_id=matched_allow_grant.id,
        )

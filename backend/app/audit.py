import uuid
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import AuditEvent, GrantEffect


# Add an audit event to current transaction
async def record_audit_event(
    db: AsyncSession,
    event_type: str,
    actor_id: Optional[uuid.UUID] = None,
    job_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    decision: Optional[GrantEffect] = None,
    reason: Optional[str] = None,
    before_data: Optional[Dict[str, Any]] = None,
    after_data: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    event = AuditEvent(
        job_id=job_id,
        actor_id=actor_id,
        event_type=event_type,
        action=action,
        decision=decision,
        reason=reason,
        before_data=before_data,
        after_data=after_data,
    )
    db.add(event)
    return event

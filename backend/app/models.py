import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Enum as SQLEnum,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserType(str, Enum):
    STAFF = "STAFF"
    CLIENT = "CLIENT"
    SERVICE = "SERVICE"


class Role(str, Enum):
    MAKER = "MAKER"
    CHECKER = "CHECKER"
    ADMIN = "ADMIN"
    CLIENT_VIEWER = "CLIENT_VIEWER"


class Direction(str, Enum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"


class Mode(str, Enum):
    AIR = "AIR"
    FCL = "FCL"
    LCL = "LCL"


class JobStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    PREPARED = "PREPARED"
    CHECKED = "CHECKED"
    FILED = "FILED"
    CANCELLED = "CANCELLED"


class GrantEffect(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class Action(str, Enum):
    VIEW = "VIEW"
    PREPARE = "PREPARE"
    CHECK = "CHECK"
    FILE = "FILE"
    CANCEL = "CANCEL"
    REOPEN = "REOPEN"
    REASSIGN = "REASSIGN"
    MANAGE_PERMISSIONS = "MANAGE_PERMISSIONS"
    INGEST = "INGEST"


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    users: Mapped[List["User"]] = relationship("User", back_populates="client")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="client")


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="branch")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_type: Mapped[UserType] = mapped_column(SQLEnum(UserType, name="user_type_enum"), nullable=False, default=UserType.STAFF)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="users")
    permission_grants: Mapped[List["PermissionGrant"]] = relationship(
        "PermissionGrant",
        foreign_keys="PermissionGrant.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    direction: Mapped[Direction] = mapped_column(SQLEnum(Direction, name="direction_enum"), nullable=False, index=True)
    mode: Mapped[Mode] = mapped_column(SQLEnum(Mode, name="mode_enum"), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus, name="job_status_enum"), nullable=False, default=JobStatus.CONFIRMED, index=True)
    assigned_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    prepared_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    checked_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    filed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    client: Mapped["Client"] = relationship("Client", back_populates="jobs")
    branch: Mapped["Branch"] = relationship("Branch", back_populates="jobs")
    assigned_user: Mapped[Optional["User"]] = relationship("User", foreign_keys=[assigned_user_id])
    prepared_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[prepared_by_id])
    checked_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[checked_by_id])
    filed_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[filed_by_id])
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    audit_events: Mapped[List["AuditEvent"]] = relationship("AuditEvent", back_populates="job", cascade="all, delete-orphan")


class PermissionGrant(Base):
    __tablename__ = "permission_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(SQLEnum(Role, name="role_enum"), nullable=False, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True)
    branch_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True)
    direction: Mapped[Optional[Direction]] = mapped_column(SQLEnum(Direction, name="direction_enum", create_constraint=False), nullable=True)
    mode: Mapped[Optional[Mode]] = mapped_column(SQLEnum(Mode, name="mode_enum", create_constraint=False), nullable=True)
    effect: Mapped[GrantEffect] = mapped_column(SQLEnum(GrantEffect, name="grant_effect_enum"), nullable=False, default=GrantEffect.ALLOW)
    granted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    revoked_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], back_populates="permission_grants")
    client: Mapped[Optional["Client"]] = relationship("Client")
    branch: Mapped[Optional["Branch"]] = relationship("Branch")
    granted_by: Mapped["User"] = relationship("User", foreign_keys=[granted_by_id])
    revoked_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[revoked_by_id])


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision: Mapped[Optional[GrantEffect]] = mapped_column(SQLEnum(GrantEffect, name="grant_effect_enum", create_constraint=False), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    before_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    job: Mapped[Optional["Job"]] = relationship("Job", back_populates="audit_events")
    actor: Mapped[Optional["User"]] = relationship("User", foreign_keys=[actor_id])


# Helpful indices for high-frequency queries
Index("ix_permission_grants_user_active", PermissionGrant.user_id, PermissionGrant.revoked_at)
Index("ix_jobs_client_branch_status", Job.client_id, Job.branch_id, Job.status)
Index("ix_audit_events_job_created", AuditEvent.job_id, AuditEvent.created_at)

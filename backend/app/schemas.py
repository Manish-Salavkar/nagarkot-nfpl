import uuid
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from app.models import (
    Action,
    Direction,
    GrantEffect,
    JobStatus,
    Mode,
    Role,
    UserType,
)

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# Reference Schemas
class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    created_at: datetime


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    full_name: str
    user_type: UserType
    client_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime


# Permission Grants
class PermissionGrantCreate(BaseModel):
    user_id: uuid.UUID
    role: Role
    client_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None
    direction: Optional[Direction] = None
    mode: Optional[Mode] = None
    effect: GrantEffect = GrantEffect.ALLOW


class PermissionGrantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_id: uuid.UUID
    role: Role
    client_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None
    direction: Optional[Direction] = None
    mode: Optional[Mode] = None
    effect: GrantEffect
    granted_by_id: uuid.UUID
    created_at: datetime
    revoked_at: Optional[datetime] = None
    revoked_by_id: Optional[uuid.UUID] = None


# Job Schemas
class JobCreate(BaseModel):
    job_number: str
    client_id: uuid.UUID
    branch_id: uuid.UUID
    direction: Direction
    mode: Mode
    assigned_user_id: Optional[uuid.UUID] = None


class JobUpdate(BaseModel):
    # Note: Status cannot be arbitrarily modified via PATCH as required by specification
    assigned_user_id: Optional[uuid.UUID] = None
    direction: Optional[Direction] = None
    mode: Optional[Mode] = None


class JobActionRequest(BaseModel):
    reason: Optional[str] = None


class JobReassignRequest(BaseModel):
    assigned_user_id: uuid.UUID
    reason: Optional[str] = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_number: str
    client_id: uuid.UUID
    branch_id: uuid.UUID
    direction: Direction
    mode: Mode
    status: JobStatus
    assigned_user_id: Optional[uuid.UUID] = None
    prepared_by_id: Optional[uuid.UUID] = None
    checked_by_id: Optional[uuid.UUID] = None
    filed_by_id: Optional[uuid.UUID] = None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    client_code: Optional[str] = None
    client_name: Optional[str] = None
    branch_code: Optional[str] = None
    branch_name: Optional[str] = None
    assigned_username: Optional[str] = None


# Authorization Check
class AuthorizationCheckRequest(BaseModel):
    user_id: uuid.UUID
    action: Action
    job_id: Optional[uuid.UUID] = None
    client_id: Optional[uuid.UUID] = None
    branch_id: Optional[uuid.UUID] = None
    direction: Optional[Direction] = None
    mode: Optional[Mode] = None


class AuthorizationCheckResponse(BaseModel):
    allowed: bool
    code: str
    reason: str
    matched_grant_id: Optional[uuid.UUID] = None
    details: Optional[Dict[str, Any]] = None


# Audit Event
class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: Optional[uuid.UUID] = None
    actor_id: Optional[uuid.UUID] = None
    event_type: str
    action: Optional[str] = None
    decision: Optional[GrantEffect] = None
    reason: Optional[str] = None
    before_data: Optional[Dict[str, Any]] = None
    after_data: Optional[Dict[str, Any]] = None
    created_at: datetime
    actor_username: Optional[str] = None

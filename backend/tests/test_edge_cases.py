import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from app.models import (
    Direction,
    Job,
    JobStatus,
    Mode,
)


# Test 1: Maker cannot check their own work
@pytest.mark.asyncio
async def test_1_maker_checker_conflict(async_client: AsyncClient, users_map, db_session):
    alex = users_map["maker_checker_alex"]

    stmt = select(Job).where(Job.job_number == "JOB-SELF-001")
    res = await db_session.execute(stmt)
    job = res.scalar_one()

    assert job.status == JobStatus.PREPARED
    assert job.prepared_by_id == alex.id

    resp = await async_client.post(
        f"/api/jobs/{job.id}/check",
        headers={"X-User-Id": str(alex.id)},
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["code"] == "SELF_APPROVAL_DISALLOWED"

    rachel = users_map["checker_rachel"]
    resp2 = await async_client.post(
        f"/api/jobs/{job.id}/check",
        headers={"X-User-Id": str(rachel.id)},
    )
    assert resp2.status_code == 200
    updated_job = resp2.json()
    assert updated_job["status"] == "CHECKED"
    assert updated_job["checked_by_id"] == str(rachel.id)


# Test 2: Admin can reassign absent owner's job
@pytest.mark.asyncio
async def test_2_absent_owner_reassignment(async_client: AsyncClient, users_map, db_session):
    admin = users_map["admin_sarah"]
    alex = users_map["maker_checker_alex"]

    stmt = select(Job).where(Job.job_number == "JOB-ABSENT-001")
    res = await db_session.execute(stmt)
    job = res.scalar_one()
    old_assigned = job.assigned_user_id

    resp = await async_client.post(
        f"/api/jobs/{job.id}/reassign",
        headers={"X-User-Id": str(admin.id)},
        json={"assigned_user_id": str(alex.id), "reason": "Covering for John on leave"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned_user_id"] == str(alex.id)

    audit_resp = await async_client.get(
        f"/api/jobs/{job.id}/history",
        headers={"X-User-Id": str(admin.id)},
    )
    assert audit_resp.status_code == 200
    history = audit_resp.json()
    reassign_events = [e for e in history if e["event_type"] == "JOB_REASSIGNED"]
    assert len(reassign_events) >= 1
    event = reassign_events[0]
    assert event["actor_id"] == str(admin.id)
    assert event["before_data"]["assigned_user_id"] == str(old_assigned)
    assert event["after_data"]["assigned_user_id"] == str(alex.id)


# Test 3: Changed permissions take effect on subsequent requests
@pytest.mark.asyncio
async def test_3_changed_responsibilities(async_client: AsyncClient, users_map, clients_map, branches_map, db_session):
    admin = users_map["admin_sarah"]
    david = users_map["maker_david"]
    glbl = clients_map["CLI-GLBL"]
    mel = branches_map["BR-MEL"]

    create_job_resp = await async_client.post(
        "/api/jobs",
        headers={"X-User-Id": str(admin.id)},
        json={
            "job_number": f"JOB-DYN-{uuid.uuid4().hex[:6]}",
            "client_id": str(glbl.id),
            "branch_id": str(mel.id),
            "direction": "IMPORT",
            "mode": "FCL",
        },
    )
    assert create_job_resp.status_code == 201
    dyn_job = create_job_resp.json()
    job_id = dyn_job["id"]

    resp_init = await async_client.post(
        f"/api/jobs/{job_id}/prepare",
        headers={"X-User-Id": str(david.id)},
    )
    assert resp_init.status_code == 403
    assert resp_init.json()["detail"]["code"] == "NO_MATCHING_GRANT"

    grant_resp = await async_client.post(
        "/api/permissions",
        headers={"X-User-Id": str(admin.id)},
        json={
            "user_id": str(david.id),
            "role": "MAKER",
            "client_id": str(glbl.id),
            "effect": "ALLOW",
        },
    )
    assert grant_resp.status_code == 201
    grant_id = grant_resp.json()["id"]

    resp_after = await async_client.post(
        f"/api/jobs/{job_id}/prepare",
        headers={"X-User-Id": str(david.id)},
    )
    assert resp_after.status_code == 200
    assert resp_after.json()["status"] == "PREPARED"

    revoke_resp = await async_client.post(
        f"/api/permissions/{grant_id}/revoke",
        headers={"X-User-Id": str(admin.id)},
    )
    assert revoke_resp.status_code == 200


# Test 4: Filed job cancellation requires admin and reason
@pytest.mark.asyncio
async def test_4_filed_job_cancellation(async_client: AsyncClient, users_map, db_session):
    admin = users_map["admin_sarah"]
    alex = users_map["maker_checker_alex"]

    stmt = select(Job).where(Job.job_number == "JOB-FILED-001")
    res = await db_session.execute(stmt)
    job = res.scalar_one()
    assert job.status == JobStatus.FILED

    resp_alex = await async_client.post(
        f"/api/jobs/{job.id}/cancel",
        headers={"X-User-Id": str(alex.id)},
        json={"reason": "Customer cancelled goods"},
    )
    assert resp_alex.status_code == 403

    resp_no_reason = await async_client.post(
        f"/api/jobs/{job.id}/cancel",
        headers={"X-User-Id": str(admin.id)},
        json={"reason": ""},
    )
    assert resp_no_reason.status_code == 400
    assert resp_no_reason.json()["detail"]["code"] == "REASON_REQUIRED"

    resp_admin = await async_client.post(
        f"/api/jobs/{job.id}/cancel",
        headers={"X-User-Id": str(admin.id)},
        json={"reason": "Customs clearance retracted by federal authority authorization doc #8892"},
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["status"] == "CANCELLED"


# Test 5: Filed job reopening requires admin and reason
@pytest.mark.asyncio
async def test_5_filed_job_reopening(async_client: AsyncClient, users_map, clients_map, branches_map, db_session):
    admin = users_map["admin_sarah"]
    alex = users_map["maker_checker_alex"]
    acme = clients_map["CLI-ACME"]
    syd = branches_map["BR-SYD"]

    stmt = (
        select(Job)
        .where(Job.status == JobStatus.FILED, Job.job_number != "JOB-FILED-001")
        .limit(1)
    )
    res = await db_session.execute(stmt)
    job = res.scalars().first()

    if not job:
        job = Job(
            job_number=f"JOB-REOPEN-TEST-{uuid.uuid4().hex[:6]}",
            client_id=acme.id,
            branch_id=syd.id,
            direction=Direction.IMPORT,
            mode=Mode.AIR,
            status=JobStatus.FILED,
            created_by_id=admin.id,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

    resp_alex = await async_client.post(
        f"/api/jobs/{job.id}/reopen",
        headers={"X-User-Id": str(alex.id)},
        json={"reason": "Need to amend invoice"},
    )
    assert resp_alex.status_code == 403

    resp_no_reason = await async_client.post(
        f"/api/jobs/{job.id}/reopen",
        headers={"X-User-Id": str(admin.id)},
        json={"reason": "   "},
    )
    assert resp_no_reason.status_code == 400

    resp_admin = await async_client.post(
        f"/api/jobs/{job.id}/reopen",
        headers={"X-User-Id": str(admin.id)},
        json={"reason": "Customs revised tariff codes requiring re-preparation and secondary check"},
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["status"] == "PREPARED"

    audit_resp = await async_client.get(
        f"/api/jobs/{job.id}/history",
        headers={"X-User-Id": str(admin.id)},
    )
    assert audit_resp.status_code == 200
    reopen_events = [e for e in audit_resp.json() if e["event_type"] == "JOB_REOPENED"]
    assert len(reopen_events) >= 1
    assert reopen_events[0]["reason"] == "Customs revised tariff codes requiring re-preparation and secondary check"


# Test 6: Admin cannot self-escalate permissions
@pytest.mark.asyncio
async def test_6_admin_self_escalation_prevented(async_client: AsyncClient, users_map):
    admin = users_map["admin_sarah"]

    resp = await async_client.post(
        "/api/permissions",
        headers={"X-User-Id": str(admin.id)},
        json={
            "user_id": str(admin.id),
            "role": "CHECKER",
            "effect": "ALLOW",
        },
    )
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["code"] == "ADMIN_SELF_ESCALATION_DISALLOWED"


# Test 7: Service account is restricted to ingestion
@pytest.mark.asyncio
async def test_7_overnight_parser_restrictions(async_client: AsyncClient, users_map, clients_map, branches_map):
    parser_bot = users_map["service_parser"]
    acme = clients_map["CLI-ACME"]
    syd = branches_map["BR-SYD"]

    ingest_resp = await async_client.post(
        "/api/jobs",
        headers={"X-User-Id": str(parser_bot.id)},
        json={
            "job_number": f"EDI-{uuid.uuid4().hex[:8]}",
            "client_id": str(acme.id),
            "branch_id": str(syd.id),
            "direction": "IMPORT",
            "mode": "AIR",
        },
    )
    assert ingest_resp.status_code == 201
    job_id = ingest_resp.json()["id"]

    check_resp = await async_client.post(
        f"/api/jobs/{job_id}/check",
        headers={"X-User-Id": str(parser_bot.id)},
    )
    assert check_resp.status_code == 403
    assert check_resp.json()["detail"]["code"] == "SERVICE_ACCOUNT_RESTRICTED"

    file_resp = await async_client.post(
        f"/api/jobs/{job_id}/file",
        headers={"X-User-Id": str(parser_bot.id)},
    )
    assert file_resp.status_code == 403
    assert file_resp.json()["detail"]["code"] == "SERVICE_ACCOUNT_RESTRICTED"

    perm_resp = await async_client.post(
        "/api/permissions",
        headers={"X-User-Id": str(parser_bot.id)},
        json={
            "user_id": str(parser_bot.id),
            "role": "ADMIN",
            "effect": "ALLOW",
        },
    )
    assert perm_resp.status_code == 403
    assert perm_resp.json()["detail"]["code"] == "SERVICE_ACCOUNT_RESTRICTED"


# Test 8: Scope matching across client, branch, direction, and mode
@pytest.mark.asyncio
async def test_8_scope_matching(async_client: AsyncClient, users_map, db_session):
    lucas = users_map["checker_lucas"]

    stmt = select(Job).where(Job.job_number == "JOB-LUCAS-ACT-001")
    res = await db_session.execute(stmt)
    act_job = res.scalar_one()

    chk_resp1 = await async_client.post(
        "/api/authorization/check",
        json={"user_id": str(lucas.id), "action": "CHECK", "job_id": str(act_job.id)},
    )
    assert chk_resp1.status_code == 200
    assert chk_resp1.json()["allowed"] is True

    stmt2 = select(Job).where(Job.job_number == "JOB-LUCAS-DENY-001")
    res2 = await db_session.execute(stmt2)
    deny_job = res2.scalar_one()

    chk_resp2 = await async_client.post(
        "/api/authorization/check",
        json={"user_id": str(lucas.id), "action": "CHECK", "job_id": str(deny_job.id)},
    )
    assert chk_resp2.status_code == 200
    assert chk_resp2.json()["allowed"] is False
    assert chk_resp2.json()["code"] == "NO_MATCHING_GRANT"


# Test 9: Explicit DENY grant overrides positive ALLOW grants
@pytest.mark.asyncio
async def test_9_explicit_deny_overrides_allow(async_client: AsyncClient, users_map, clients_map, branches_map):
    sam = users_map["denied_sam"]
    acme = clients_map["CLI-ACME"]
    syd = branches_map["BR-SYD"]

    resp_fcl = await async_client.post(
        "/api/authorization/check",
        json={
            "user_id": str(sam.id),
            "action": "PREPARE",
            "client_id": str(acme.id),
            "branch_id": str(syd.id),
            "direction": "IMPORT",
            "mode": "FCL",
        },
    )
    assert resp_fcl.status_code == 200
    assert resp_fcl.json()["allowed"] is True

    resp_air = await async_client.post(
        "/api/authorization/check",
        json={
            "user_id": str(sam.id),
            "action": "PREPARE",
            "client_id": str(acme.id),
            "branch_id": str(syd.id),
            "direction": "IMPORT",
            "mode": "AIR",
        },
    )
    assert resp_air.status_code == 200
    data = resp_air.json()
    assert data["allowed"] is False
    assert data["code"] == "EXPLICIT_DENY"


# Test 10: Closed-by-default denial when no grant matches
@pytest.mark.asyncio
async def test_10_no_matching_allow_results_in_denial(async_client: AsyncClient, users_map, clients_map, branches_map):
    frank = users_map["viewer_frank"]
    acme = clients_map["CLI-ACME"]
    syd = branches_map["BR-SYD"]

    resp = await async_client.post(
        "/api/authorization/check",
        json={
            "user_id": str(frank.id),
            "action": "PREPARE",
            "client_id": str(acme.id),
            "branch_id": str(syd.id),
            "direction": "IMPORT",
            "mode": "AIR",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["allowed"] is False
    assert resp.json()["code"] == "NO_MATCHING_GRANT"


# Test 11: Client user cannot access jobs of other clients
@pytest.mark.asyncio
async def test_11_client_user_cannot_access_other_clients(async_client: AsyncClient, users_map, clients_map, branches_map, db_session):
    jane = users_map["client_jane"]
    glbl = clients_map["CLI-GLBL"]

    stmt = select(Job).where(Job.client_id == glbl.id).limit(1)
    res = await db_session.execute(stmt)
    glbl_job = res.scalars().first()

    resp = await async_client.get(
        f"/api/jobs/{glbl_job.id}",
        headers={"X-User-Id": str(jane.id)},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "CLIENT_ISOLATION_VIOLATION"


# Test 12: Work queue returns only actionable jobs for the active user
@pytest.mark.asyncio
async def test_12_work_queue_returns_only_actionable_jobs(async_client: AsyncClient, users_map):
    lucas = users_map["checker_lucas"]

    resp = await async_client.get(
        "/api/me/jobs",
        headers={"X-User-Id": str(lucas.id)},
    )
    assert resp.status_code == 200
    queue = resp.json()

    for item in queue:
        assert item["client_code"] == "CLI-ACME"
        assert item["branch_code"] == "BR-SYD"
        assert item["direction"] == "IMPORT"
        assert item["status"] in ["PREPARED", "CHECKED"]
        assert item.get("prepared_by_id") != str(lucas.id)


# Test 13: Invalid sequential transitions are rejected
@pytest.mark.asyncio
async def test_13_invalid_workflow_transitions_rejected(async_client: AsyncClient, users_map, clients_map, branches_map):
    admin = users_map["admin_sarah"]
    alex = users_map["maker_checker_alex"]
    acme = clients_map["CLI-ACME"]
    syd = branches_map["BR-SYD"]

    create_resp = await async_client.post(
        "/api/jobs",
        headers={"X-User-Id": str(admin.id)},
        json={
            "job_number": f"INVALID-SEQ-{uuid.uuid4().hex[:6]}",
            "client_id": str(acme.id),
            "branch_id": str(syd.id),
            "direction": "IMPORT",
            "mode": "AIR",
        },
    )
    job_id = create_resp.json()["id"]

    check_resp = await async_client.post(
        f"/api/jobs/{job_id}/check",
        headers={"X-User-Id": str(alex.id)},
    )
    assert check_resp.status_code == 403
    assert check_resp.json()["detail"]["code"] == "INVALID_WORKFLOW_STATE"


# Test 14: Audit history records event details
@pytest.mark.asyncio
async def test_14_audit_history_captures_details(async_client: AsyncClient, users_map, db_session):
    admin = users_map["admin_sarah"]

    resp = await async_client.get(
        "/api/audit?page=1&page_size=10",
        headers={"X-User-Id": str(admin.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert len(data["items"]) > 0

    item = data["items"][0]
    assert "event_type" in item
    assert "created_at" in item
    assert item["created_at"] is not None

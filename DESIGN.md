# NFPL Access Control Service — Architecture & Design Document

## Executive Summary

NFPL is an international customs brokerage operating 120 staff across 5 primary branches handling thousands of shipments (jobs). Each job represents a consignment characterized by a client, branch, direction (Import/Export), and transport mode (Air, FCL, LCL).

This design document provides an architectural specification and comprehensive answers to the 14 design questions posed in the technical assessment brief. Every answer reflects the **actual implemented software** in this repository.

---

## Core System Architecture & Data Model

The service is built on a minimal, closed-by-default access control architecture using **six relational models only** in PostgreSQL via SQLAlchemy 2.0 async ORM:

```
+------------+       1:N       +-----------------+       N:1       +------------+
|   Client   |<----------------|       Job       |---------------->|   Branch   |
+------------+                 +-----------------+                 +------------+
      ^                                 |                                 ^
      |                                 |                                 |
      | 1:N                             | 1:N                             |
      |                                 v                                 |
+------------+       1:N       +-----------------+                        |
|    User    |---------------->|   AuditEvent    |                        |
+------------+                 +-----------------+                        |
      |                                                                   |
      | 1:N                                                               |
      v                                                                   |
+-----------------+                                                       |
| PermissionGrant |-------------------------------------------------------+
+-----------------+   (Scoped by Client, Branch, Direction, Mode)
```

### Database Entities
1. **User**: Represents staff, client personnel, or automated service identities (`STAFF`, `CLIENT`, `SERVICE`).
2. **Client**: Corporate customer organization with unique code and status.
3. **Branch**: Operational port or freight terminal (e.g., Sydney Gateway, Melbourne Port).
4. **Job**: Operational shipment lifecycle entity (`CONFIRMED` -> `PREPARED` -> `CHECKED` -> `FILED` or `CANCELLED`). Stores assigned person, preparation maker, checker, and filer directly.
5. **PermissionGrant**: Multi-dimensional role and scope assignments with `ALLOW` or `DENY` effect. A `NULL` attribute represents an unrestricted dimension.
6. **AuditEvent**: Append-only log recording all state transitions, authorization evaluations, permission grants/revocations, and administrative overrides with structured before/after payloads.

---

## The 14 Technical Design Questions Answered

### 1. Should everyone see everything? If not, who sees what? How does that differ from who may act?

**Implemented Policy:**
No, not everyone should see everything.
- **Client-Side Personnel (`CLIENT`)**: Strictly isolated by tenant. A client employee can only view jobs matching their organization (`user.client_id == job.client_id`). They cannot view other clients' freight, pricing, or compliance notes.
- **Brokerage Staff (`STAFF`)**: Can view jobs within their operational territory (or globally across NFPL for general lookup, coordination, and tracking). However, visibility is strictly decoupled from the authority to mutate.
- **Service Identities (`SERVICE`)**: Restricted strictly to programmatic ingestion endpoints.

**Distinction Between Visibility (`VIEW`) and Action (`PREPARE`, `CHECK`, `FILE`, `CANCEL`):**
- **Visibility** is passive: it allows querying job metadata and tracking shipment progress.
- **Action Authority** is active: it transitions legal and compliance state. Action requires a matching active `ALLOW` grant covering the job's four dimensions (client, branch, direction, mode), satisfies workflow stage prerequisites, and clears maker-checker separation.
- **Work Queue Distinction**: Visibility allows browsing the global job list; only actionable jobs appear in a user's work queue (`/api/me/jobs`).

---

### 2. How would you describe someone who is a Maker for every client but a Checker for only a few? What about someone who is a Checker for one client at one branch, but only for imports?

In our dimensional `PermissionGrant` model:
- `NULL` represents an open wildcard dimension (matches all values).
- A specific foreign key or enum represents a strict restriction.

**Case A: Maker for every client, Checker for only a few**
Expressed cleanly as three simple grant rows for user Alex Rivera:
1. `PermissionGrant(user_id=Alex, role=MAKER, client_id=NULL, branch_id=NULL, direction=NULL, mode=NULL, effect=ALLOW)`
2. `PermissionGrant(user_id=Alex, role=CHECKER, client_id=CLI_ACME, branch_id=NULL, direction=NULL, mode=NULL, effect=ALLOW)`
3. `PermissionGrant(user_id=Alex, role=CHECKER, client_id=CLI_GLBL, branch_id=NULL, direction=NULL, mode=NULL, effect=ALLOW)`
*Result*: Alex can prepare declarations for any customer across all branches, but can only approve/check checklists for Acme and Global Logistics.

**Case B: Checker for one client, at one branch, for imports only**
Expressed as a single precise grant row for user Lucas Thorne:
- `PermissionGrant(user_id=Lucas, role=CHECKER, client_id=CLI_ACME, branch_id=BR_SYD, direction=IMPORT, mode=NULL, effect=ALLOW)`
*Result*: Lucas can only check and file jobs if `client == ACME AND branch == Sydney AND direction == IMPORT`. Any export job or different branch/client is denied.

---

### 3. What if the person who prepared a checklist is also qualified to approve it?

**Implemented Rule:**
The central authorization engine strictly enforces **separation of duties (four-eyes principle)**:
$$\text{If } \text{action} == \text{CHECK} \text{ and } \text{job.prepared\_by\_id} == \text{user.id} \implies \mathbf{DENIED}$$

Even if a senior broker possesses a valid global `CHECKER` grant, the system prohibits self-approval with explicit error code `SELF_APPROVAL_DISALLOWED` and explanation:
> *"User prepared checklist for job JOB-XXX and cannot approve their own work."*

Another qualified checker within scope must review and check the shipment. This prevents conflict of interest and human error.

---

### 4. What if the person responsible for a job is absent?

**Implemented Mechanism:**
- When an assigned broker is sick or on leave, any administrator (or the currently assigned broker) can invoke `POST /api/jobs/{id}/reassign`.
- The endpoint validates that the target assignee is active, transitions `job.assigned_user_id`, and records an audit event capturing `{"assigned_user_id": old_id}` -> `{"assigned_user_id": new_id}` with a documented business reason (e.g. *"Covering for John on leave"*).
- Because actionable work queues evaluate live grants rather than static pre-baked lists, the job immediately disappears from the absent user's queue and appears in the replacement broker's queue.

---

### 5. What happens to jobs a person is halfway through when their responsibilities change?

**Implemented Behavior:**
- Authorization is evaluated **just-in-time dynamically** on every API mutation from current database state, not cached inside session tokens.
- When an employee's responsibilities change (e.g., moved from Sydney to Melbourne, or revoked from Checker to Maker):
  1. The administrator revokes the old grant (`revoked_at = utc_now()`) and creates the new grant.
  2. On the next HTTP request, the user cannot progress the job further if they no longer meet the scope criteria.
  3. The job remains safely in its current state (`PREPARED`) without data corruption.
  4. An administrator or branch lead reassigns the job to an active team member at that branch.

---

### 6. Who should be able to cancel a filed job or reopen a closed one? What should it take?

**Implemented Safeguards:**
A `FILED` shipment is legally submitted to national customs and freight forwarders. Careless mutation can incur legal penalties.

1. **Role Requirement**: Only users holding an active `ADMIN` grant can cancel or reopen a `FILED` job. Ordinary Makers and Checkers are rejected (`403 Forbidden`).
2. **Mandatory Documentation**: The request body must include a non-empty `reason` parameter. Requests without a documented reason fail with `400 Bad Request` (`REASON_REQUIRED`).
3. **Atomic Audit Capture**:
   - `JOB_CANCELLED` or `JOB_REOPENED` event recorded with the actor ID, exact timestamp, and business justification.
4. **State Transition**:
   - Reopening moves status from `FILED` back to `PREPARED`, allowing the checklist to be revised, checked, and refiled through standard controls.

---

### 7. What if a client's own employee needs to follow their shipments?

**Implemented Architecture:**
- User type is flagged as `UserType.CLIENT` with a mandatory foreign key `client_id`.
- The central authorization engine enforces:
  ```python
  if user.user_type == UserType.CLIENT:
      if action != Action.VIEW:
          return Deny("Client-side users only possess view access.")
      if job.client_id != user.client_id:
          return Deny("Client isolation violation.")
  ```
- All list queries automatically append `WHERE jobs.client_id = actor.client_id`. Client users cannot view jobs, notes, or activity of any other customer.

---

### 8. What if an admin needs to fix a stuck job? What if an admin tries to make themselves more powerful?

**Admin Access and Boundaries:**
- **Fixing a Stuck Job**: Administrators are granted operational override actions (`REASSIGN`, `CANCEL`, `REOPEN`). They can reassign orphaned jobs, cancel dead shipments, and reopen improperly filed declarations with required audit reasons.
- **Admin Self-Escalation Prevention**:
  To prevent an administrator from silently granting themselves arbitrary unchecked capabilities or bypassing separation of duties:
  ```python
  if grant_in.user_id == actor.id:
      raise HTTPException(
          status_code=403,
          detail={"code": "ADMIN_SELF_ESCALATION_DISALLOWED"}
      )
  ```
  An administrator cannot create grants targeting their own account. Granting additional privileges requires peer review by a second administrator.

---

### 9. How should an automated parser that creates and updates jobs overnight be treated?

**Implemented Service Principal Pattern:**
- Automated bots/EDI parsers are modeled as `UserType.SERVICE` (e.g. `service_parser`).
- Allowed actions are strictly whitelisted to `[Action.VIEW, Action.INGEST]`.
- Parsers can create incoming shipments and parse documents into `CONFIRMED` jobs.
- Parsers are strictly prohibited from approving (`CHECK`), submitting legal filings (`FILE`), or granting permissions (`MANAGE_PERMISSIONS`). Attempting any restricted action yields `SERVICE_ACCOUNT_RESTRICTED`.

---

### 10. How do you answer "why can she do this and he can't?"

**Implemented Explainability Engine:**
The dedicated endpoint `POST /api/authorization/check` evaluates the exact engine used by mutation routes and outputs a structured diagnostic verdict:
```json
{
  "allowed": false,
  "code": "SELF_APPROVAL_DISALLOWED",
  "reason": "User 'alex' prepared checklist for job JOB-001 and cannot approve their own work.",
  "matched_grant_id": null
}
```
Possible decision codes:
- `ALLOWED`: Authorized under grant ID.
- `NO_MATCHING_GRANT`: Lacks active role within matching client/branch/direction/mode scope.
- `EXPLICIT_DENY`: An explicit negative grant overrides positive permissions.
- `SELF_APPROVAL_DISALLOWED`: Maker-checker four-eyes policy triggered.
- `INVALID_WORKFLOW_STATE`: Action not permitted in current status.
- `CLIENT_ISOLATION_VIOLATION`: Tenant boundary violation.
- `SERVICE_ACCOUNT_RESTRICTED`: Bot attempted human-only operation.

This allows any operator to instantly compare two users side-by-side and see the exact grant or constraint causing the difference.

---

### 11. How do you answer "who could have changed this job on the 3rd?"

**Implemented Historical Distinction:**
We distinguish three tiers of historical answers:
1. **Direct Provenance (What actually changed)**:
   Queried from `audit_events` filtered by `job_id` and timestamp range (`start_time <= 2026-10-03T23:59:59Z`). Every mutation logs the actor, event type, action, timestamp, and full before/after JSON snapshot.
2. **Reconstructed Eligibility (Who had permission on that day)**:
   Reconstructed by querying `permission_grants` where:
   `created_at <= '2026-10-03T23:59:59Z' AND (revoked_at IS NULL OR revoked_at > '2026-10-03T00:00:00Z')`.
   This identifies which users held matching scopes on that calendar day.
3. **What Cannot Be Proven**:
   Network-level intrusions, uncommitted read-only screen views where read-auditing was not sampled, or direct database superuser updates outside application transactions.

---

### 12. How would a new kind of role be introduced next quarter while engineering is busy?

**Configurable Role Design:**
- In our implementation, `role` is evaluated through the `ROLE_ACTIONS` registry in `authorization.py`:
  ```python
  ROLE_ACTIONS = {
      Role.MAKER: [Action.VIEW, Action.PREPARE],
      Role.CHECKER: [Action.VIEW, Action.CHECK, Action.FILE],
      Role.CLIENT_VIEWER: [Action.VIEW],
      Role.ADMIN: [Action.VIEW, Action.CANCEL, Action.REOPEN, Action.REASSIGN, Action.MANAGE_PERMISSIONS],
      Role.AUDITOR: [Action.VIEW], # Non-engineering extensible role
  }
  ```
- Because scopes are attribute-based on `PermissionGrant` (client, branch, direction, mode), administrators can define hybrid positions (e.g. "Airfreight Import Specialist", "Client Compliance Reviewer") immediately without database schema changes or new code tables.

---

### 13. How do you make sure a person's "jobs waiting for me" count matches what they can actually do?

**Guaranteed Consistency:**
Work queue consistency is maintained by running the **identical authorization evaluation** for work queue discovery as for operation execution:
1. Candidate jobs in active states (`CONFIRMED`, `PREPARED`, `CHECKED`) are selected.
2. For every job, the system determines the next workflow action (`CONFIRMED -> PREPARE`, `PREPARED -> CHECK`, `CHECKED -> FILE`).
3. It passes `(user_id, next_action, job)` through `AuthorizationService.evaluate`.
4. If `decision.allowed == False` (e.g., out of branch scope, explicit deny, or maker-checker conflict where `job.prepared_by_id == user.id`), the job is excluded from the queue.

This mathematical equivalence ensures that every item in `/api/me/jobs` is guaranteed to be actionable without 403 errors upon clicking.

---

### 14. What should happen when your system is unsure?

**Default-Deny and Fail-Closed Principle:**
Whenever an ambiguity arises:
- Missing grant -> **DENIED** (`NO_MATCHING_GRANT`).
- Contradictory rules (ALLOW vs DENY) -> **DENY overrides ALLOW** (`EXPLICIT_DENY`).
- Unrecognized status transition -> **DENIED** (`INVALID_WORKFLOW_STATE`).
- Database failure during audit recording -> **Transaction rolls back completely**; the state change is discarded.
- Inactive user -> **DENIED** (`USER_INACTIVE`).

The system never defaults to permissive access. If any precondition cannot be proven true with certainty, the request is rejected and logged.

---

## Architectural Decisions & Trade-offs Summary

| Architectural Decision | Chosen Implementation | Trade-off / Rationale |
| :--- | :--- | :--- |
| **Schema Complexity** | Exactly 6 tables | Eliminates joins across intermediate mapping tables while preserving full relational integrity. |
| **Driver** | `asyncpg` + Async SQLAlchemy | Maximum async throughput under concurrent load; avoids thread-blocking I/O. |
| **Audit Storage** | Transactional `audit_events` with JSONB | Guarantees atomic consistency between job state mutations and historical audit logs. |
| **Authorization Evaluation** | Centralized Service Engine | Prevents permission logic fragmentation between endpoints and work queues. |
| **Permission Revocation** | Soft-revocation (`revoked_at`, `revoked_by_id`) | Enables historical reconstruction of who possessed authority on past dates. |

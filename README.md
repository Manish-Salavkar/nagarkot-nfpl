# NFPL Access Control Service

A minimal, robust, and mathematically sound access control service for NFPL customs brokerage. Built with Python 3.12, FastAPI, async SQLAlchemy 2.0 with asyncpg, PostgreSQL, Alembic migrations, React, Vite, and TypeScript.

---

## 1. Quick Start Guide

### Prerequisites
- Python 3.12+
- Node.js & npm
- Local PostgreSQL instance with database `nfpl`

### Configuration
A single `.env` file in the root directory manages all settings:
```env
DATABASE_URL=postgresql+asyncpg://manish:somethingelse@localhost:5432/nfpl
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
VITE_API_BASE_URL=http://localhost:8000
```

### Run Frontend & Backend Together
Run the single root runner script:
```bash
python run.py
```
This automatically starts:
- **Backend API**: `http://localhost:8000` (auto-applies migrations and seeds data on startup)
- **Frontend App**: `http://localhost:8002` (pure React JSX on Vite)

Press `Ctrl+C` to stop both services gracefully.

---

## 2. Sample Data: Plain-Language Access Table

The initial seed populates 5 branches, 10 clients, 20 users, and ~230 jobs across all workflow states and transport modes:

| Username | Name | User Type | Plain Language Access Summary | Deliberate Test Scenario |
| :--- | :--- | :--- | :--- | :--- |
| `admin_sarah` | Sarah Jenkins | STAFF | **ADMIN** globally (all clients, branches, directions, modes). Can manage permissions, reassign jobs, cancel/reopen filed jobs. | Primary system administrator. |
| `admin_mark` | Mark Stevens | STAFF | **ADMIN** globally. | Operations director & secondary admin. |
| `maker_checker_alex` | Alex Rivera | STAFF | **MAKER** for all clients globally; **CHECKER** for only `CLI-ACME` and `CLI-GLBL`. | Hybrid maker everywhere / checker for selected clients. Demonstrates maker-checker conflict on `JOB-SELF-001`. |
| `checker_lucas` | Lucas Thorne | STAFF | **CHECKER** for client `CLI-ACME`, branch `BR-SYD`, and `IMPORT` direction only (all modes). | Narrow checker scope. Actionable on `JOB-LUCAS-ACT-001`; blocked on exports. |
| `maker_emma` | Emma Watson | STAFF | **MAKER** for all clients, restricted to branches `BR-SYD` and `BR-MEL` (both directions, all modes). | Multi-branch maker. |
| `maker_david` | David Kim | STAFF | **MAKER** for clients `CLI-NEXUS`, `CLI-ZENITH`, `CLI-APEX` (all branches, directions, modes). | Multi-client maker. Demonstrates immediate responsibility change test. |
| `checker_rachel` | Rachel Green | STAFF | **CHECKER** globally across all clients, branches, directions, and modes. | Global senior compliance checker. Can approve jobs prepared by Alex. |
| `absent_john` | John Doe | STAFF | **MAKER** and **CHECKER** globally. Has multiple jobs currently assigned. | Absent staff owner on leave. Demonstrates reassignment on `JOB-ABSENT-001`. |
| `client_jane` | Jane Miller | CLIENT | **CLIENT_VIEWER** strictly restricted to client `CLI-ACME`. | Client employee following own shipments. Blocked from viewing other clients' jobs. |
| `client_bob` | Bob Taylor | CLIENT | **CLIENT_VIEWER** strictly restricted to client `CLI-GLBL`. | Client employee tenant isolation. |
| `service_parser` | Overnight Bot | SERVICE | Service identity authorized for automated shipment ingestion (`INGEST` / `VIEW`). | Overnight EDI parser. Blocked from checking, filing, or managing permissions. |
| `revoked_oliver` | Oliver Queen | STAFF | Previous **MAKER** grant has been revoked (`revoked_at` set). | Demonstrates revoked permission behavior. |
| `denied_sam` | Sam Vance | STAFF | **MAKER** globally, but possesses an explicit **DENY** grant for mode `AIR`. | Demonstrates explicit DENY overriding positive ALLOW grants. |
| `maker_liam` | Liam Neeson | STAFF | **MAKER** for mode `AIR` across all clients and branches. | Mode-specific airfreight maker. |
| `checker_sophia` | Sophia Loren | STAFF | **CHECKER** for modes `FCL` and `LCL` (maritime freight). | Mode-specific maritime checker. |
| `maker_noah` | Noah Clark | STAFF | **MAKER** for branch `BR-BNE` (Brisbane Cargo). | Branch-specific maker. |
| `checker_chloe` | Chloe Bennett | STAFF | **CHECKER** for branch `BR-PER` (Perth International). | Branch-specific checker. |
| `maker_ryan` | Ryan Gosling | STAFF | **MAKER** for direction `EXPORT` across all clients and branches. | Direction-specific export maker. |
| `inactive_grace` | Grace Hopper | STAFF | Inactive user account (`is_active = False`). | Demonstrates immediate rejection of deactivated personnel. |
| `viewer_frank` | Frank Castle | STAFF | **CLIENT_VIEWER** across all clients and branches. | Read-only internal auditor. Closed-by-default denial on any mutation. |

---

## 3. Automated Test Suite

Run all automated tests covering all 14 edge cases:

```bash
cd backend
source .venv/bin/activate
pytest -v
```

### Verified Test Cases:
1. `test_1_maker_checker_conflict`: A Maker cannot check their own work (`SELF_APPROVAL_DISALLOWED`).
2. `test_2_absent_owner_reassignment`: An authorized administrator reassigns an absent user's job with audit log tracking.
3. `test_3_changed_responsibilities`: New permission grants take effect dynamically on subsequent requests.
4. `test_4_filed_job_cancellation`: Only administrators can cancel filed jobs, with a documented reason required.
5. `test_5_filed_job_reopening`: Only administrators can reopen filed jobs, with documented reason and audit tracking.
6. `test_6_admin_self_escalation_prevented`: Administrators are prohibited from creating permission grants targeting themselves.
7. `test_7_overnight_parser_restrictions`: Parser can ingest jobs but cannot check, file, or manage access.
8. `test_8_scope_matching`: Multi-dimensional scope matching across client, branch, direction, and mode.
9. `test_9_explicit_deny_overrides_allow`: Explicit DENY overrides positive ALLOW grants.
10. `test_10_no_matching_allow_results_in_denial`: Closed-by-default security model.
11. `test_11_client_user_cannot_access_other_clients`: Tenant isolation prevents cross-client job visibility.
12. `test_12_work_queue_returns_only_actionable_jobs`: Work queue excludes jobs that are merely visible or non-actionable.
13. `test_13_invalid_workflow_transitions_rejected`: Non-sequential workflow operations fail with clear diagnostics.
14. `test_14_audit_history_captures_details`: Immutable audit trail captures actor, event type, timestamp, and before/after state.

---

## 4. Scale Generator (500 Users, 200,000 Jobs)

To generate the full-scale dataset of 500 users and 200,000 jobs:

```bash
cd backend
source .venv/bin/activate
python scripts/generate_scale_data.py --users 500 --jobs 200000 --batch-size 10000 --seed 42
```

- Generates 500 users and 200,000 jobs distributed across clients, branches, directions, modes, and statuses.
- Uses bulk batch insertion chunks to maximize performance and avoid single-row ORM commit overhead.
- Supports deterministic randomness via `--seed 42`.

---

## 5. Development Database Reset & Reseed

To reset the database back to the clean 20-user, ~230-job dataset:

```bash
cd backend
source .venv/bin/activate
python scripts/reset_db.py
```
*Note: This script enforces `APP_ENV != "production"` to prevent accidental data loss in production.*

---

## 6. Five-Minute Demo Walkthrough Script

Follow these steps for a live or recorded demonstration:

### Part 1: Service Overview & Work Queue (1 Minute)
1. Open `http://localhost:8002`.
2. Notice the top identity selector showing **Alex Rivera (`maker_checker_alex`)**.
3. View the **"My Work Queue"** tab: Alex sees jobs in `CONFIRMED` and `PREPARED` states within his active grants.
4. Switch the identity selector to **Lucas Thorne (`checker_lucas`)**:
   - Notice the queue immediately filters: Lucas only sees `PREPARED` import shipments for Acme Corporation at Sydney Gateway.

### Part 2: Maker-Checker Conflict & Self-Approval Block (1 Minute)
1. Switch back to **Alex Rivera**.
2. Go to the **"All Jobs"** tab and search for `JOB-SELF-001`.
3. Click **"View Details"**: Note that status is `PREPARED` and Alex prepared the checklist.
4. Click **"Check & Approve"**:
   - The system displays a red error banner: `[SELF_APPROVAL_DISALLOWED] User 'maker_checker_alex' prepared checklist for job JOB-SELF-001 and cannot approve their own work.`
5. Switch the identity selector to **Rachel Green (`checker_rachel`)** (Senior Compliance Officer).
6. Click **"Check & Approve"**:
   - Success! Status transitions to `CHECKED`.

### Part 3: "Why can she do this and he can't?" (1 Minute)
1. Navigate to the **"Permission Explainer"** tab.
2. Select Person: **Sam Vance (`denied_sam`)**, Action: `PREPARE`, and evaluate with Mode: `AIR`:
   - Decision: **`DENIED [EXPLICIT_DENY]`** with explanation: *"Explicit DENY grant overrides access for role MAKER"*.
3. Change Mode to `FCL`:
   - Decision: **`ALLOWED`** under positive Maker grant.
4. Test with **Overnight Parser Bot (`service_parser`)** for action `CHECK`:
   - Decision: **`DENIED [SERVICE_ACCOUNT_RESTRICTED]`**.

### Part 4: Absent Owner Reassignment & Job Audit Trail (1 Minute)
1. Switch identity to **Sarah Jenkins (`admin_sarah`)**.
2. Go to **"All Jobs"** and locate `JOB-ABSENT-001` (assigned to absent owner John Doe).
3. In the modal, select a new owner (e.g. `maker_checker_alex`), enter reason *"Covering for John on leave"*, and click **"Reassign"**.
4. Scroll down to **"Job Audit History"**:
   - Point out the immutable audit entry recording actor `admin_sarah`, event `JOB_REASSIGNED`, timestamp, and reason.

### Part 5: Cancel / Reopen Filed Shipments & Admin Protection (1 Minute)
1. Locate a `FILED` job (e.g., `JOB-FILED-001`).
2. Demonstrate that attempting to reopen without entering a documented reason is blocked (`400 Bad Request`).
3. Enter documented reason: *"Customs amended tariff code #4412"*, click **"Reopen Job"**:
   - Job reopens to `PREPARED` for checklist correction, and audit history logs the administrative override.
4. Navigate to the **"Permission Grants"** tab:
   - Try granting a role to `admin_sarah` herself: The system blocks it with `ADMIN_SELF_ESCALATION_DISALLOWED`.

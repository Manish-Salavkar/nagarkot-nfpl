import React, { useEffect, useState } from "react";
import { api } from "./api";

// Main access control application
export const App = () => {
  const [users, setUsers] = useState([]);
  const [clients, setClients] = useState([]);
  const [branches, setBranches] = useState([]);

  const [currentUserId, setCurrentUserId] = useState("");
  const currentActor = users.find((u) => u.id === currentUserId);

  const [activeTab, setActiveTab] = useState("queue");
  const [errorMsg, setErrorMsg] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [loading, setLoading] = useState(false);

  const [jobs, setJobs] = useState([]);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobsPage, setJobsPage] = useState(1);
  const [filterClient, setFilterClient] = useState("");
  const [filterBranch, setFilterBranch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterDirection, setFilterDirection] = useState("");
  const [filterMode, setFilterMode] = useState("");
  const [searchJob, setSearchJob] = useState("");

  const [myJobs, setMyJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobHistory, setJobHistory] = useState([]);
  const [actionReason, setActionReason] = useState("");
  const [reassignUserId, setReassignUserId] = useState("");

  const [checkUserId, setCheckUserId] = useState("");
  const [checkJobId, setCheckJobId] = useState("");
  const [checkAction, setCheckAction] = useState("CHECK");
  const [authzResult, setAuthzResult] = useState(null);

  const [permissionsList, setPermissionsList] = useState([]);
  const [newGrantUserId, setNewGrantUserId] = useState("");
  const [newGrantRole, setNewGrantRole] = useState("MAKER");
  const [newGrantClientId, setNewGrantClientId] = useState("");
  const [newGrantBranchId, setNewGrantBranchId] = useState("");
  const [newGrantDirection, setNewGrantDirection] = useState("");
  const [newGrantMode, setNewGrantMode] = useState("");
  const [newGrantEffect, setNewGrantEffect] = useState("ALLOW");

  const [auditEvents, setAuditEvents] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);

  // Load initial dropdown data
  useEffect(() => {
    loadReferenceData();
  }, []);

  // Fetch reference users, clients and branches
  const loadReferenceData = async () => {
    try {
      setLoading(true);
      const [uList, cList, bList] = await Promise.all([
        api.getUsers(),
        api.getClients(),
        api.getBranches(),
      ]);
      setUsers(uList);
      setClients(cList);
      setBranches(bList);
      if (uList.length > 0 && !currentUserId) {
        const defaultUser = uList.find((u) => u.username === "maker_checker_alex") || uList[0];
        setCurrentUserId(defaultUser.id);
        setCheckUserId(defaultUser.id);
      }
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Reload data on tab or user change
  useEffect(() => {
    if (!currentUserId) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    if (activeTab === "queue") {
      loadMyQueue();
    } else if (activeTab === "jobs") {
      loadJobs();
    } else if (activeTab === "permissions") {
      loadPermissions();
    } else if (activeTab === "audit") {
      loadAudit();
    }
  }, [activeTab, currentUserId, jobsPage, filterClient, filterBranch, filterStatus, filterDirection, filterMode, auditPage]);

  // Load actionable queue for current user
  const loadMyQueue = async () => {
    try {
      setLoading(true);
      const data = await api.getMyJobs(currentUserId);
      setMyJobs(data);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load paginated jobs
  const loadJobs = async (pageOverride, searchOverride) => {
    const pageToUse = pageOverride !== undefined ? pageOverride : jobsPage;
    const searchToUse = searchOverride !== undefined ? searchOverride : searchJob;
    try {
      setLoading(true);
      const data = await api.getJobs(
        {
          client_id: filterClient,
          branch_id: filterBranch,
          status: filterStatus,
          direction: filterDirection,
          mode: filterMode,
          search: searchToUse,
          page: pageToUse,
          page_size: 15,
        },
        currentUserId
      );
      setJobs(data.items);
      setJobsTotal(data.total);
      if (pageOverride !== undefined) {
        setJobsPage(pageOverride);
      }
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load permission grants list
  const loadPermissions = async () => {
    try {
      setLoading(true);
      const data = await api.getPermissions();
      setPermissionsList(data);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Load audit trail
  const loadAudit = async () => {
    try {
      setLoading(true);
      const data = await api.getAuditEvents({ page: auditPage, page_size: 20 }, currentUserId);
      setAuditEvents(data.items);
      setAuditTotal(data.total);
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Select job and fetch its audit history
  const handleSelectJob = async (job) => {
    setSelectedJob(job);
    setActionReason("");
    setReassignUserId(job.assigned_user_id || "");
    try {
      const history = await api.getJobHistory(job.id, currentUserId);
      setJobHistory(history);
    } catch (_) {
      setJobHistory([]);
    }
  };

  // Execute workflow action on selected job
  const executeJobAction = async (action) => {
    if (!selectedJob) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      let updated;
      if (action === "prepare") {
        updated = await api.prepareJob(selectedJob.id, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} prepared successfully.`);
      } else if (action === "check") {
        updated = await api.checkJob(selectedJob.id, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} checked & approved.`);
      } else if (action === "file") {
        updated = await api.fileJob(selectedJob.id, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} filed.`);
      } else if (action === "cancel") {
        if (!actionReason.trim()) {
          setErrorMsg("A reason is required to cancel a job.");
          return;
        }
        updated = await api.cancelJob(selectedJob.id, actionReason, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} cancelled.`);
      } else if (action === "reopen") {
        if (!actionReason.trim()) {
          setErrorMsg("A reason is required to reopen a filed job.");
          return;
        }
        updated = await api.reopenJob(selectedJob.id, actionReason, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} reopened.`);
      } else {
        if (!reassignUserId) {
          setErrorMsg("Select a target user to reassign.");
          return;
        }
        updated = await api.reassignJob(selectedJob.id, reassignUserId, actionReason, currentUserId);
        setSuccessMsg(`Job ${updated.job_number} reassigned.`);
      }

      setSelectedJob(updated);
      const history = await api.getJobHistory(updated.id, currentUserId);
      setJobHistory(history);

      if (activeTab === "queue") loadMyQueue();
      if (activeTab === "jobs") loadJobs();
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  // Run authorization check
  const handleCheckAuthz = async (e) => {
    e.preventDefault();
    if (!checkUserId || !checkAction) return;
    setErrorMsg(null);
    try {
      const payload = {
        user_id: checkUserId,
        action: checkAction,
      };
      if (checkJobId) {
        payload.job_id = checkJobId;
      }
      const res = await api.checkAuthorization(payload);
      setAuthzResult(res);
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  // Create new grant
  const handleCreateGrant = async (e) => {
    e.preventDefault();
    if (!newGrantUserId || !newGrantRole) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await api.createPermission(
        {
          user_id: newGrantUserId,
          role: newGrantRole,
          client_id: newGrantClientId || null,
          branch_id: newGrantBranchId || null,
          direction: newGrantDirection || null,
          mode: newGrantMode || null,
          effect: newGrantEffect,
        },
        currentUserId
      );
      setSuccessMsg("Permission grant created successfully.");
      loadPermissions();
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  // Revoke grant
  const handleRevokeGrant = async (grantId) => {
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await api.revokePermission(grantId, currentUserId);
      setSuccessMsg("Permission grant revoked.");
      loadPermissions();
    } catch (err) {
      setErrorMsg(err.message);
    }
  };

  return (
    <div className="app-container">
      <header>
        <div className="brand">
          <h1>NFPL Access Control</h1>
          <p>Customs Brokerage Operations</p>
        </div>

        <div className="user-selector-box">
          <label htmlFor="user-select">Active User:</label>
          <select
            id="user-select"
            value={currentUserId}
            onChange={(e) => {
              setCurrentUserId(e.target.value);
              setSelectedJob(null);
            }}
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({u.username}) — {u.user_type}
                {!u.is_active ? " [INACTIVE]" : ""}
              </option>
            ))}
          </select>
        </div>
      </header>

      <nav className="nav-tabs">
        <button
          className={`nav-tab ${activeTab === "queue" ? "active" : ""}`}
          onClick={() => setActiveTab("queue")}
        >
          My Work Queue {myJobs.length > 0 && `(${myJobs.length})`}
        </button>
        <button
          className={`nav-tab ${activeTab === "jobs" ? "active" : ""}`}
          onClick={() => setActiveTab("jobs")}
        >
          All Jobs
        </button>
        <button
          className={`nav-tab ${activeTab === "check" ? "active" : ""}`}
          onClick={() => setActiveTab("check")}
        >
          Permission Explainer
        </button>
        <button
          className={`nav-tab ${activeTab === "permissions" ? "active" : ""}`}
          onClick={() => setActiveTab("permissions")}
        >
          Permission Grants
        </button>
        <button
          className={`nav-tab ${activeTab === "audit" ? "active" : ""}`}
          onClick={() => setActiveTab("audit")}
        >
          Audit History
        </button>
      </nav>

      {errorMsg && <div className="error-banner">{errorMsg}</div>}
      {successMsg && <div className="success-banner">{successMsg}</div>}

      {/* WORK QUEUE */}
      {activeTab === "queue" && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Jobs Waiting For Me</h2>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                Showing actionable shipments for <strong>{currentActor?.full_name}</strong>.
              </p>
            </div>
            <button onClick={loadMyQueue} className="secondary" disabled={loading}>
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="loading-state">Loading...</div>
          ) : myJobs.length === 0 ? (
            <div className="empty-state">
              No jobs currently waiting for your action.
            </div>
          ) : (
            <div className="table-responsive">
              <table>
                <thead>
                  <tr>
                    <th>Job Number</th>
                    <th>Client</th>
                    <th>Branch</th>
                    <th>Direction</th>
                    <th>Mode</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {myJobs.map((j) => (
                    <tr key={j.id}>
                      <td><strong>{j.job_number}</strong></td>
                      <td>{j.client_code}</td>
                      <td>{j.branch_code}</td>
                      <td>{j.direction}</td>
                      <td>{j.mode}</td>
                      <td><span className={`badge badge-${j.status}`}>{j.status}</span></td>
                      <td>
                        <button className="table-btn" onClick={() => handleSelectJob(j)}>Inspect</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ALL JOBS */}
      {activeTab === "jobs" && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">All Jobs</h2>
            <div className="search-bar">
              <input
                type="text"
                placeholder="Search job number..."
                value={searchJob}
                onChange={(e) => setSearchJob(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadJobs(1)}
              />
              <button onClick={() => loadJobs(1)}>Search</button>
              {searchJob && (
                <button
                  className="secondary"
                  onClick={() => {
                    setSearchJob("");
                    loadJobs(1, "");
                  }}
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          <div className="grid-form filter-grid">
            <div className="form-group">
              <label>Client</label>
              <select value={filterClient} onChange={(e) => { setFilterClient(e.target.value); setJobsPage(1); }}>
                <option value="">All Clients</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.code} - {c.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Branch</label>
              <select value={filterBranch} onChange={(e) => { setFilterBranch(e.target.value); setJobsPage(1); }}>
                <option value="">All Branches</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>{b.code} - {b.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Status</label>
              <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setJobsPage(1); }}>
                <option value="">All Statuses</option>
                <option value="CONFIRMED">CONFIRMED</option>
                <option value="PREPARED">PREPARED</option>
                <option value="CHECKED">CHECKED</option>
                <option value="FILED">FILED</option>
                <option value="CANCELLED">CANCELLED</option>
              </select>
            </div>

            <div className="form-group">
              <label>Direction</label>
              <select value={filterDirection} onChange={(e) => { setFilterDirection(e.target.value); setJobsPage(1); }}>
                <option value="">Both Directions</option>
                <option value="IMPORT">IMPORT</option>
                <option value="EXPORT">EXPORT</option>
              </select>
            </div>

            <div className="form-group">
              <label>Mode</label>
              <select value={filterMode} onChange={(e) => { setFilterMode(e.target.value); setJobsPage(1); }}>
                <option value="">All Modes</option>
                <option value="AIR">AIR</option>
                <option value="FCL">FCL</option>
                <option value="LCL">LCL</option>
              </select>
            </div>
          </div>

          {loading ? (
            <div className="loading-state">Loading...</div>
          ) : (
            <>
              <div className="table-responsive">
                <table>
                  <thead>
                    <tr>
                      <th>Job Number</th>
                      <th>Client</th>
                      <th>Branch</th>
                      <th>Direction / Mode</th>
                      <th>Status</th>
                      <th>Assigned To</th>
                      <th>Prepared By</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => {
                      const preparer = users.find((u) => u.id === j.prepared_by_id);
                      return (
                        <tr key={j.id}>
                          <td><strong>{j.job_number}</strong></td>
                          <td>{j.client_code}</td>
                          <td>{j.branch_code}</td>
                          <td>{j.direction} / {j.mode}</td>
                          <td><span className={`badge badge-${j.status}`}>{j.status}</span></td>
                          <td>{j.assigned_username || "Unassigned"}</td>
                          <td>{preparer ? preparer.username : "-"}</td>
                          <td>
                            <button className="table-btn" onClick={() => handleSelectJob(j)}>View</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="pagination">
                <span className="pagination-info">Total: {jobsTotal} jobs</span>
                <div className="pagination-buttons">
                  <button
                    disabled={jobsPage <= 1}
                    onClick={() => setJobsPage((p) => p - 1)}
                    className="secondary"
                  >
                    Previous
                  </button>
                  <span className="pagination-current">Page {jobsPage}</span>
                  <button
                    disabled={jobsPage * 15 >= jobsTotal}
                    onClick={() => setJobsPage((p) => p + 1)}
                    className="secondary"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {/* PERMISSION EXPLAINER */}
      {activeTab === "check" && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Permission Decision Explainer</h2>
          </div>

          <form onSubmit={handleCheckAuthz} className="grid-form explainer-form">
            <div className="form-group">
              <label>Person to Evaluate</label>
              <select value={checkUserId} onChange={(e) => setCheckUserId(e.target.value)}>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name} ({u.username}) — {u.user_type}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Action</label>
              <select value={checkAction} onChange={(e) => setCheckAction(e.target.value)}>
                <option value="VIEW">VIEW</option>
                <option value="PREPARE">PREPARE</option>
                <option value="CHECK">CHECK</option>
                <option value="FILE">FILE</option>
                <option value="CANCEL">CANCEL</option>
                <option value="REOPEN">REOPEN</option>
                <option value="REASSIGN">REASSIGN</option>
                <option value="MANAGE_PERMISSIONS">MANAGE_PERMISSIONS</option>
                <option value="INGEST">INGEST</option>
              </select>
            </div>

            <div className="form-group">
              <label>Job (Optional)</label>
              <select value={checkJobId} onChange={(e) => setCheckJobId(e.target.value)}>
                <option value="">-- No Specific Job --</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.job_number} ({j.client_code}, {j.status})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group form-action-btn">
              <button type="submit">Evaluate</button>
            </div>
          </form>

          {authzResult && (
            <div className={`result-box ${authzResult.allowed ? "result-allowed" : "result-denied"}`}>
              <div className="result-header">
                <span className={`badge ${authzResult.allowed ? "badge-ALLOW" : "badge-DENY"}`}>
                  {authzResult.allowed ? "ALLOWED" : "DENIED"}
                </span>
                <span className="result-code">Code: {authzResult.code}</span>
              </div>
              <p className="result-reason"><strong>Reason:</strong> {authzResult.reason}</p>
            </div>
          )}
        </section>
      )}

      {/* PERMISSIONS */}
      {activeTab === "permissions" && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Permission Grants</h2>
          </div>

          <form onSubmit={handleCreateGrant} className="grid-form grants-form">
            <div className="form-group">
              <label>Grant To</label>
              <select value={newGrantUserId} onChange={(e) => setNewGrantUserId(e.target.value)}>
                <option value="">-- Select User --</option>
                {users.map((u) => (
                  <option key={u.id} value={u.id}>{u.full_name} ({u.username})</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Role</label>
              <select value={newGrantRole} onChange={(e) => setNewGrantRole(e.target.value)}>
                <option value="MAKER">MAKER</option>
                <option value="CHECKER">CHECKER</option>
                <option value="ADMIN">ADMIN</option>
                <option value="CLIENT_VIEWER">CLIENT_VIEWER</option>
              </select>
            </div>

            <div className="form-group">
              <label>Client</label>
              <select value={newGrantClientId} onChange={(e) => setNewGrantClientId(e.target.value)}>
                <option value="">All Clients</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.code} - {c.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Branch</label>
              <select value={newGrantBranchId} onChange={(e) => setNewGrantBranchId(e.target.value)}>
                <option value="">All Branches</option>
                {branches.map((b) => (
                  <option key={b.id} value={b.id}>{b.code} - {b.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Direction</label>
              <select value={newGrantDirection} onChange={(e) => setNewGrantDirection(e.target.value)}>
                <option value="">Both Directions</option>
                <option value="IMPORT">IMPORT</option>
                <option value="EXPORT">EXPORT</option>
              </select>
            </div>

            <div className="form-group">
              <label>Mode</label>
              <select value={newGrantMode} onChange={(e) => setNewGrantMode(e.target.value)}>
                <option value="">All Modes</option>
                <option value="AIR">AIR</option>
                <option value="FCL">FCL</option>
                <option value="LCL">LCL</option>
              </select>
            </div>

            <div className="form-group">
              <label>Effect</label>
              <select value={newGrantEffect} onChange={(e) => setNewGrantEffect(e.target.value)}>
                <option value="ALLOW">ALLOW</option>
                <option value="DENY">DENY</option>
              </select>
            </div>

            <div className="form-group form-action-btn">
              <button type="submit">Grant Access</button>
            </div>
          </form>

          <div className="table-responsive" style={{ marginTop: "1rem" }}>
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Role</th>
                  <th>Scope</th>
                  <th>Effect</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {permissionsList.map((g) => {
                  const u = users.find((usr) => usr.id === g.user_id);
                  const c = clients.find((cli) => cli.id === g.client_id);
                  const b = branches.find((br) => br.id === g.branch_id);
                  return (
                    <tr key={g.id}>
                      <td><strong>{u?.username || g.user_id}</strong></td>
                      <td>{g.role}</td>
                      <td>
                        {c?.code || "All"} / {b?.code || "All"} / {g.direction || "All"} / {g.mode || "All"}
                      </td>
                      <td><span className={`badge badge-${g.effect}`}>{g.effect}</span></td>
                      <td>{g.revoked_at ? <span className="status-revoked">Revoked</span> : <span className="status-active">Active</span>}</td>
                      <td>
                        {!g.revoked_at && (
                          <button className="danger table-btn" onClick={() => handleRevokeGrant(g.id)}>
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* AUDIT */}
      {activeTab === "audit" && (
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Audit Trail</h2>
            <button onClick={loadAudit} className="secondary">Refresh</button>
          </div>

          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Actor</th>
                  <th>Event</th>
                  <th>Action</th>
                  <th>Decision</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((ev) => (
                  <tr key={ev.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(ev.created_at).toLocaleString()}</td>
                    <td><strong>{ev.actor_username || "System"}</strong></td>
                    <td><code>{ev.event_type}</code></td>
                    <td>{ev.action || "-"}</td>
                    <td>{ev.decision && <span className={`badge badge-${ev.decision}`}>{ev.decision}</span>}</td>
                    <td>{ev.reason || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span className="pagination-info">Total: {auditTotal} events</span>
            <div className="pagination-buttons">
              <button disabled={auditPage <= 1} onClick={() => setAuditPage((p) => p - 1)} className="secondary">
                Previous
              </button>
              <button disabled={auditPage * 20 >= auditTotal} onClick={() => setAuditPage((p) => p + 1)} className="secondary">
                Next
              </button>
            </div>
          </div>
        </section>
      )}

      {/* MODAL */}
      {selectedJob && (
        <div className="modal-backdrop" onClick={() => setSelectedJob(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="panel-header">
              <h2 className="panel-title">Job {selectedJob.job_number}</h2>
              <button className="secondary" onClick={() => setSelectedJob(null)}>Close</button>
            </div>

            <div className="modal-info-grid">
              <div><strong>Client:</strong> {selectedJob.client_code}</div>
              <div><strong>Branch:</strong> {selectedJob.branch_code}</div>
              <div><strong>Direction:</strong> {selectedJob.direction}</div>
              <div><strong>Mode:</strong> {selectedJob.mode}</div>
              <div><strong>Status:</strong> <span className={`badge badge-${selectedJob.status}`}>{selectedJob.status}</span></div>
              <div><strong>Assigned:</strong> {selectedJob.assigned_username || "None"}</div>
              <div>
                <strong>Prepared By:</strong>{" "}
                {selectedJob.prepared_by_id
                  ? (users.find((u) => u.id === selectedJob.prepared_by_id)?.full_name || "Unknown") +
                    ` (${users.find((u) => u.id === selectedJob.prepared_by_id)?.username || selectedJob.prepared_by_id})`
                  : "Not yet prepared"}
              </div>
            </div>

            <div className="modal-action-box">
              <div className="modal-buttons-row">
                {selectedJob.status === "CONFIRMED" && (
                  <button onClick={() => executeJobAction("prepare")}>Prepare</button>
                )}
                {selectedJob.status === "PREPARED" && (
                  <button className="success" onClick={() => executeJobAction("check")}>Check & Approve</button>
                )}
                {selectedJob.status === "CHECKED" && (
                  <button className="success" onClick={() => executeJobAction("file")}>File Job</button>
                )}
                {selectedJob.status === "FILED" && (
                  <button onClick={() => executeJobAction("reopen")} className="secondary">Reopen</button>
                )}
                {selectedJob.status !== "CANCELLED" && (
                  <button onClick={() => executeJobAction("cancel")} className="danger">Cancel</button>
                )}
              </div>

              <div className="form-group" style={{ marginBottom: "0.75rem" }}>
                <label>Reason (for Cancel, Reopen, Reassign):</label>
                <input
                  type="text"
                  placeholder="Enter reason..."
                  value={actionReason}
                  onChange={(e) => setActionReason(e.target.value)}
                />
              </div>

              <div className="reassign-row">
                <div className="form-group" style={{ flex: 1 }}>
                  <label>Reassign To:</label>
                  <select value={reassignUserId} onChange={(e) => setReassignUserId(e.target.value)}>
                    <option value="">-- Select User --</option>
                    {users.map((u) => (
                      <option key={u.id} value={u.id}>{u.full_name} ({u.username})</option>
                    ))}
                  </select>
                </div>
                <button className="secondary" onClick={() => executeJobAction("reassign")}>Reassign</button>
              </div>
            </div>

            <h4 style={{ marginTop: "1.25rem", marginBottom: "0.5rem" }}>Audit History</h4>
            {jobHistory.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>No history yet.</p>
            ) : (
              <div className="table-responsive">
                <table style={{ fontSize: "0.85rem" }}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Actor</th>
                      <th>Event</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobHistory.map((h) => (
                      <tr key={h.id}>
                        <td style={{ whiteSpace: "nowrap" }}>{new Date(h.created_at).toLocaleTimeString()}</td>
                        <td>{h.actor_username || "System"}</td>
                        <td><code>{h.event_type}</code></td>
                        <td>{h.reason || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
export default App;

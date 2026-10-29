const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// Base request helper
async function request(path, options = {}, currentUserId) {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");
  if (currentUserId) {
    headers.set("X-User-Id", currentUserId);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errMessage = `HTTP ${response.status} ${response.statusText}`;
    try {
      const errJson = await response.json();
      if (errJson.detail) {
        if (typeof errJson.detail === "object") {
          errMessage = `${errJson.detail.code ? `[${errJson.detail.code}] ` : ""}${errJson.detail.message || JSON.stringify(errJson.detail)}`;
        } else {
          errMessage = String(errJson.detail);
        }
      }
    } catch (_) {}
    throw new Error(errMessage);
  }

  return response.json();
}

export const api = {
  // Reference data
  getUsers: () => request("/api/users"),
  getClients: () => request("/api/clients"),
  getBranches: () => request("/api/branches"),

  // Jobs
  getJobs: (params, currentUserId) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        query.set(k, String(v));
      }
    });
    return request(`/api/jobs?${query.toString()}`, {}, currentUserId);
  },

  getJob: (jobId, currentUserId) =>
    request(`/api/jobs/${jobId}`, {}, currentUserId),

  getMyJobs: (currentUserId) =>
    request("/api/me/jobs", {}, currentUserId),

  createJob: (payload, currentUserId) =>
    request("/api/jobs", { method: "POST", body: JSON.stringify(payload) }, currentUserId),

  prepareJob: (jobId, currentUserId) =>
    request(`/api/jobs/${jobId}/prepare`, { method: "POST" }, currentUserId),

  checkJob: (jobId, currentUserId) =>
    request(`/api/jobs/${jobId}/check`, { method: "POST" }, currentUserId),

  fileJob: (jobId, currentUserId) =>
    request(`/api/jobs/${jobId}/file`, { method: "POST" }, currentUserId),

  cancelJob: (jobId, reason, currentUserId) =>
    request(`/api/jobs/${jobId}/cancel`, { method: "POST", body: JSON.stringify({ reason }) }, currentUserId),

  reopenJob: (jobId, reason, currentUserId) =>
    request(`/api/jobs/${jobId}/reopen`, { method: "POST", body: JSON.stringify({ reason }) }, currentUserId),

  reassignJob: (jobId, assignedUserId, reason, currentUserId) =>
    request(
      `/api/jobs/${jobId}/reassign`,
      { method: "POST", body: JSON.stringify({ assigned_user_id: assignedUserId, reason }) },
      currentUserId
    ),

  // Authorization explainer
  checkAuthorization: (payload) =>
    request("/api/authorization/check", { method: "POST", body: JSON.stringify(payload) }),

  // Audit history
  getJobHistory: (jobId, currentUserId) =>
    request(`/api/jobs/${jobId}/history`, {}, currentUserId),

  getAuditEvents: (params, currentUserId) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") {
        query.set(k, String(v));
      }
    });
    return request(`/api/audit?${query.toString()}`, {}, currentUserId);
  },

  // Permissions
  getPermissions: (userId) => {
    const q = userId ? `?user_id=${userId}` : "";
    return request(`/api/permissions${q}`);
  },

  createPermission: (payload, currentUserId) =>
    request("/api/permissions", { method: "POST", body: JSON.stringify(payload) }, currentUserId),

  revokePermission: (grantId, currentUserId) =>
    request(`/api/permissions/${grantId}/revoke`, { method: "POST" }, currentUserId),
};

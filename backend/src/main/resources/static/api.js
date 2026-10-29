const API_ROOT = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message, details = {}) {
    super(message || `Yêu cầu thất bại (${status})`);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class ApiClient {
  constructor() {}

  async request(path, options = {}) {
    const { responseType, ...requestOptions } = options;
    const headers = new Headers(requestOptions.headers || {});
    const csrf = document.querySelector('meta[name="_csrf"]')?.content;
    if (csrf && !["GET", "HEAD"].includes(requestOptions.method || "GET"))
      headers.set("X-CSRF-TOKEN", csrf);
    if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const response = await fetch(`${API_ROOT}${path}`, { ...requestOptions, headers, credentials: "same-origin" });
    if (!response.ok) {
      let body = {};
      try { body = await response.json(); } catch { /* response has no JSON body */ }
      const error = body.error || {};
      throw new ApiError(response.status, error.code, error.message, error.details);
    }
    if (response.status === 204) return null;
    if (responseType === "blob") return response.blob();
    const contentType = response.headers.get("Content-Type") || "";
    return contentType.includes("application/json") ? response.json() : response.blob();
  }

  login(username, password) {
    return this.request("/auth/session", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  }

  me() { return this.request("/auth/me"); }
  csrf() { return this.request("/auth/csrf"); }
  logout() { return this.request("/auth/logout", { method: "POST" }); }
  listDocuments() { return this.request("/documents?limit=50"); }
  document(id, options = {}) { return this.request(`/documents/${encodeURIComponent(id)}`, options); }
  revisions(id, options = {}) { return this.request(`/documents/${encodeURIComponent(id)}/revisions`, options); }
  runs(id, options = {}) { return this.request(`/documents/${encodeURIComponent(id)}/runs`, options); }

  async upload(file, type) {
    const form = new FormData();
    form.set("file", file);
    form.set("document_type", type);
    const key = crypto.randomUUID();
    return this.request("/documents", {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: form,
    });
  }

  createJob(documentId) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/jobs`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
    });
  }

  save(documentId, body) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/review`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  }

  approve(documentId, body) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/approve`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  adoptRun(documentId, body) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/adopt-run`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  createExport(documentId, revisionId) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/exports`, {
      method: "POST",
      body: JSON.stringify({ revision_id: revisionId, format: "json" }),
    });
  }

  downloadExport(id) {
    return this.request(`/exports/${encodeURIComponent(id)}/download`, { responseType: "blob" });
  }

  page(documentId, options = {}) {
    return this.request(`/documents/${encodeURIComponent(documentId)}/pages/0`, options);
  }
}

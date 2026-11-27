const API_ROOT = "/api/v1";
const pendingMutations = new Map();

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

  async login(username, password) {
    const result = await this.request("/auth/session", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    pendingMutations.clear();
    return result;
  }

  me() { return this.request("/auth/me"); }
  csrf() { return this.request("/auth/csrf"); }
  async logout() {
    const result = await this.request("/auth/logout", { method: "POST" });
    pendingMutations.clear();
    return result;
  }
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
    return this.reviewMutation(documentId, "review", "PATCH", body);
  }

  approve(documentId, body) {
    return this.reviewMutation(documentId, "approve", "POST", body);
  }

  adoptRun(documentId, body) {
    return this.reviewMutation(documentId, "adopt-run", "POST", body);
  }

  hasPendingSave(documentId, body) {
    const path = `/documents/${encodeURIComponent(documentId)}/review`;
    return pendingMutations.get(path)?.body === JSON.stringify(body);
  }

  async reviewMutation(documentId, operation, method, body) {
    const path = `/documents/${encodeURIComponent(documentId)}/${operation}`;
    const serialized = JSON.stringify(body);
    const previous = pendingMutations.get(path);
    const key = previous?.body === serialized ? previous.key : crypto.randomUUID();
    pendingMutations.set(path, { body: serialized, key });
    let result;
    try {
      result = await this.request(path, {
        method, headers: { "Idempotency-Key": key }, body: serialized,
      });
    } catch (error) {
      // A definite rejection cannot be reconciled by replaying a lost response.
      if (error instanceof ApiError && error.status < 500 &&
          pendingMutations.get(path)?.key === key) pendingMutations.delete(path);
      throw error;
    }
    if (pendingMutations.get(path)?.key === key) pendingMutations.delete(path);
    return result;
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
    const { revisionId, ...requestOptions } = options;
    const revision = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
    return this.request(`/documents/${encodeURIComponent(documentId)}/pages/0${revision}`, requestOptions);
  }
}

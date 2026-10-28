import { ApiClient, ApiError } from "./api.js";
import {
  emptyItem,
  emptyPayload,
  documentStatus,
  statusLabel,
  isActiveJob,
  RECEIPT_FIELDS,
  INVOICE_FIELDS,
  ITEM_FIELDS,
  toBusinessPayload,
} from "./domain.js";

const root = document.querySelector("#app");
const processingMode = document.querySelector('meta[name="vietdoc-mode"]')?.content;
const state = {
  user: null,
  documents: [],
  selectedId: null,
  document: null,
  editorBase: null,
  remoteDocument: null,
  revisions: [],
  runs: [],
  payload: null,
  rowIds: [],
  changedPaths: new Set(),
  changedItemFields: new Map(),
  acknowledged: new Set(),
  reviewed: false,
  reviewReason: "Đã đối chiếu với ảnh nguồn",
  exportRevisionId: "",
  imageUrl: "",
  uploadFile: null,
  uploadType: "receipt",
  username: "",
  password: "",
  busy: false,
  busyAction: "",
  message: null,
};

let listTimer;
let jobTimer;
let sessionGeneration = 0;
let navigationGeneration = 0;
let listGeneration = 0;
let navigationAbort;
const api = () => new ApiClient();
async function refreshCsrf() {
  const result = await api().csrf();
  document.querySelector('meta[name="_csrf"]').content = result.token;
}
const currentView = (session, navigation, id) =>
  session === sessionGeneration && navigation === navigationGeneration &&
  state.selectedId === id && !!state.user;
const remoteChanged = () => !!(state.remoteDocument && state.editorBase &&
  (state.remoteDocument.head_revision_id !== state.editorBase.id ||
   state.remoteDocument.version !== state.editorBase.version));

function setEditorDocument(document) {
  state.document = document;
  state.editorBase = document.head ? {
    id: document.head_revision_id, version: document.version,
    payload: copy(document.head.payload),
  } : null;
  state.remoteDocument = null;
  state.payload = document.head ? copy(document.head.payload) : null;
  state.rowIds = [...(document.head?.row_ids || [])];
  state.changedPaths.clear();
  state.changedItemFields.clear();
  state.acknowledged.clear();
  state.reviewed = false;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
}

function copy(value) { return structuredClone(value); }
function currentPayload() {
  return state.payload || emptyPayload(state.document?.document_type || state.uploadType);
}

function message(text, kind = "info") {
  state.message = { text, kind };
  render();
}

function apiFailure(error) {
  if (error instanceof ApiError && error.status === 401) {
    clearSession();
    state.message = { text: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", kind: "error" };
    render();
    return;
  }
  const text = error instanceof ApiError
    ? `${error.message}${error.code ? ` (${error.code})` : ""}`
    : (error?.message || "Không thể kết nối đến VietDoc.");
  state.message = { text, kind: "error" };
  render();
}

function setBusy(active, action = "") {
  state.busy = active;
  state.busyAction = active ? action : "";
  render();
}

function clearSession() {
  sessionGeneration++;
  navigationGeneration++;
  navigationAbort?.abort();
  state.user = null;
  state.documents = [];
  state.document = null;
  state.editorBase = null;
  state.remoteDocument = null;
  state.payload = null;
  state.revisions = [];
  state.runs = [];
  state.changedPaths.clear();
  state.changedItemFields.clear();
  state.selectedId = null;
  state.busy = false;
  state.busyAction = "";
  stopPolling();
  releaseImage();
}

function stopPolling() {
  clearInterval(listTimer);
  clearInterval(jobTimer);
  listTimer = undefined;
  jobTimer = undefined;
}

function releaseImage() {
  if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
  state.imageUrl = "";
}

async function start() {
  const session = sessionGeneration;
  try {
    const user = await api().me();
    if (session !== sessionGeneration) return;
    state.user = user;
    await refreshDocuments();
    if (session !== sessionGeneration) return;
    render();
    listTimer = setInterval(() => refreshDocuments().catch(error => {
      if (session === sessionGeneration) apiFailure(error);
    }), 5000);
  } catch (error) {
    if (session !== sessionGeneration) return;
    if (error instanceof ApiError && error.status === 401) clearSession();
    render();
  }
}

async function login(event) {
  event.preventDefault();
  if (state.busy) return;
  const session = sessionGeneration;
  setBusy(true, "login");
  try {
    await refreshCsrf();
    if (session !== sessionGeneration) return;
    const result = await api().login(state.username.trim(), state.password);
    if (session !== sessionGeneration) return;
    await refreshCsrf();
    if (session !== sessionGeneration) return;
    state.user = result.user;
    state.password = "";
    state.message = null;
    await refreshDocuments();
    render();
    listTimer = setInterval(() => refreshDocuments().catch(error => {
      if (session === sessionGeneration) apiFailure(error);
    }), 5000);
  } catch (error) { if (session === sessionGeneration) apiFailure(error); }
  finally { if (session === sessionGeneration) { state.busy = false; state.busyAction = ""; render(); } }
}

async function logout() {
  const request = api().logout();
  sessionGeneration++;
  navigationGeneration++;
  navigationAbort?.abort();
  stopPolling();
  state.user = null;
  state.busy = true;
  state.busyAction = "logout";
  render();
  try { await request; } catch { /* Session is already discarded locally. */ }
  try { await refreshCsrf(); } catch { /* Login reports a connection error if refresh fails. */ }
  clearSession();
  state.message = null;
  render();
}

async function refreshDocuments() {
  if (!state.user) return;
  const session = sessionGeneration;
  const sequence = ++listGeneration;
  const page = await api().listDocuments();
  if (session !== sessionGeneration || sequence !== listGeneration || !state.user) return;
  state.documents = page.items || [];
  if (state.selectedId) {
    const updated = state.documents.find((item) => item.id === state.selectedId);
    if (updated && state.editorBase && updated.version > state.editorBase.version)
      state.remoteDocument = updated;
    else if (updated && !state.editorBase && updated.head && state.document) {
      const id = state.selectedId, navigation = navigationGeneration;
      const [detail, revisions, runs] = await Promise.all([
        api().document(id), api().revisions(id), api().runs(id),
      ]);
      if (!currentView(session, navigation, id) || state.editorBase) return;
      setEditorDocument(detail);
      state.revisions = revisions.items || [];
      state.runs = runs.items || [];
    } else if (updated && state.document && updated.id === state.document.id &&
               (!state.editorBase || updated.version === state.editorBase.version))
      state.document.job = updated.job;
  }
  if (state.document && isActiveJob(state.document.job)) startJobPolling();
  else clearInterval(jobTimer);
  render({ passive: true });
}

async function openDocument(id) {
  if (state.busy && state.busyAction !== "open") return;
  if (state.selectedId && state.selectedId !== id &&
      (isDirty() || state.changedPaths.size || state.changedItemFields.size) &&
      !window.confirm("Bạn có thay đổi chưa lưu. Mở chứng từ khác sẽ bỏ các thay đổi này. Tiếp tục?")) return;
  const session = sessionGeneration;
  const navigation = ++navigationGeneration;
  navigationAbort?.abort();
  navigationAbort = new AbortController();
  const signal = navigationAbort.signal;
  setBusy(true, "open");
  try {
    state.selectedId = id;
    state.document = null;
    state.editorBase = null;
    state.remoteDocument = null;
    state.payload = null;
    state.rowIds = [];
    state.revisions = [];
    state.runs = [];
    releaseImage();
    const [document, revisions, runs, image] = await Promise.all([
      api().document(id, { signal }), api().revisions(id, { signal }),
      api().runs(id, { signal }), api().page(id, { signal }),
    ]);
    if (!currentView(session, navigation, id)) return;
    setEditorDocument(document);
    state.reviewReason = "Đã đối chiếu với ảnh nguồn";
    state.exportRevisionId = "";
    state.message = null;
    state.revisions = revisions.items || [];
    state.runs = runs.items || [];
    state.imageUrl = URL.createObjectURL(image);
    render();
    if (isActiveJob(state.document.job)) startJobPolling();
    else clearInterval(jobTimer);
  } catch (error) { if (currentView(session, navigation, id) && error.name !== "AbortError") apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

function startJobPolling() {
  clearInterval(jobTimer);
  if (!state.document?.job?.id) return;
  jobTimer = setInterval(pollJob, 1800);
}

async function pollJob() {
  const job = state.document?.job;
  const id = state.selectedId;
  const session = sessionGeneration, navigation = navigationGeneration;
  if (!job?.id || !isActiveJob(job)) {
    clearInterval(jobTimer);
    return;
  }
  try {
    const updatedJob = await api().request(`/jobs/${encodeURIComponent(job.id)}`);
    if (!currentView(session, navigation, id) || state.document?.job?.id !== job.id) return;
    state.document.job = updatedJob;
    if (!isActiveJob(state.document.job)) {
      const [revisions, runs] = await Promise.all([
        api().revisions(id), api().runs(id),
      ]);
      const changed = await api().document(id);
      if (!currentView(session, navigation, id) || state.document?.job?.id !== job.id) return;
      if (!state.editorBase && changed.head) setEditorDocument(changed);
      else if (state.editorBase && changed.version > state.editorBase.version)
        state.remoteDocument = changed;
      else state.document.job = changed.job;
      state.revisions = revisions.items || [];
      state.runs = runs.items || [];
      clearInterval(jobTimer);
      await refreshDocuments();
      return;
    }
    render({ passive: true });
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
}

async function uploadAndProcess(event) {
  event.preventDefault();
  if (state.busy) return;
  const session = sessionGeneration;
  const file = state.uploadFile;
  if (!file) return message("Chọn ảnh hoặc PDF trước khi tải lên.", "error");
  const extension = file.name.split(".").pop().toLowerCase();
  if (!(["image/jpeg", "image/png", "application/pdf"].includes(file.type) ||
        ["jpg", "jpeg", "png", "pdf"].includes(extension)))
    return message("Chỉ hỗ trợ JPG, PNG hoặc PDF.", "error");
  setBusy(true, "upload");
  try {
    const document = await api().upload(file, state.uploadType);
    if (session !== sessionGeneration) return;
    state.documents = [document, ...state.documents.filter((item) => item.id !== document.id)];
    state.uploadFile = null;
    render();
    const job = await api().createJob(document.id);
    if (session !== sessionGeneration) return;
    state.documents = [{ ...document, job }, ...state.documents.filter(item => item.id !== document.id)];
    state.message = { text: "File đã lưu an toàn. Job đã vào hàng đợi; bạn có thể theo dõi trạng thái ở đây.", kind: "success" };
    state.busy = false;
    state.busyAction = "";
    await openDocument(document.id);
  } catch (error) { if (session === sessionGeneration) apiFailure(error); }
  finally { if (session === sessionGeneration) { state.busy = false; state.busyAction = ""; render(); } }
}

async function rerun() {
  if (!state.document || state.busy || remoteChanged()) return;
  if (hasUnsavedReview())
    return message("Hãy lưu hoặc tải lại thay đổi chưa lưu trước khi chạy xử lý lại.", "error");
  const session = sessionGeneration, navigation = navigationGeneration, id = state.document.id;
  setBusy(true, "rerun");
  try {
    const job = await api().createJob(id);
    if (!currentView(session, navigation, id)) return;
    state.document.job = job;
    state.message = { text: "Job mới đã được xếp hàng. Kết quả sẽ xuất hiện thành candidate riêng, không ghi đè revision hiện tại.", kind: "success" };
    await refreshDocuments();
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

async function saveReview() {
  const document = state.document;
  if (!document?.head || state.busy || remoteChanged() ||
      (!isDirty() && !state.changedPaths.size && !state.changedItemFields.size)) return;
  const session = sessionGeneration, navigation = navigationGeneration;
  const id = document.id;
  const payload = toBusinessPayload(document.document_type, currentPayload());
  const reviewedPaths = [...state.changedPaths];
  for (const [rowId, fields] of state.changedItemFields) {
    const index = state.rowIds.indexOf(rowId);
    if (index >= 0) for (const field of fields) reviewedPaths.push(`/items/${index}/${field}`);
  }
  setBusy(true, "save");
  try {
    const rowIds = [...state.rowIds];
    while (rowIds.length < payload.items.length) rowIds.push(crypto.randomUUID());
    rowIds.length = payload.items.length;
    const updated = await api().save(document.id, {
      base_revision_id: state.editorBase.id,
      expected_document_version: state.editorBase.version,
      payload,
      reason: state.reviewReason.trim() || "Đã chỉnh sửa sau khi đối chiếu ảnh nguồn",
      row_ids: rowIds,
      reviewed_paths: [...new Set(reviewedPaths)],
    });
    if (!currentView(session, navigation, id)) return;
    setEditorDocument(updated);
    state.message = { text: "Đã lưu thành revision mới. Prediction và các revision trước vẫn được giữ nguyên.", kind: "success" };
    const revisions = await api().revisions(document.id);
    if (!currentView(session, navigation, id)) return;
    state.revisions = revisions.items || [];
    await refreshDocuments();
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

async function adoptCandidate(runId) {
  const document = state.document;
  if (!document?.head) return;
  if (state.busy || remoteChanged() || isDirty() || state.changedPaths.size || state.changedItemFields.size)
    return message("Hãy lưu hoặc tải lại thay đổi chưa lưu trước khi áp dụng candidate.", "error");
  const session = sessionGeneration, navigation = navigationGeneration, id = document.id;
  setBusy(true, "adopt");
  try {
    const updated = await api().adoptRun(document.id, {
      run_id: runId,
      base_revision_id: state.editorBase.id,
      expected_document_version: state.editorBase.version,
      reason: "Áp dụng candidate từ lần chạy AI mới",
    });
    if (!currentView(session, navigation, id)) return;
    setEditorDocument(updated);
    state.message = { text: "Candidate được lưu thành revision mới; prediction và bản sửa cũ vẫn còn trong lịch sử.", kind: "success" };
    const revisions = await api().revisions(document.id);
    if (!currentView(session, navigation, id)) return;
    state.revisions = revisions.items || [];
    await refreshDocuments();
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

async function approve() {
  const document = state.document;
  if (!document?.head || state.busy || remoteChanged() || isDirty() ||
      state.changedPaths.size || state.changedItemFields.size) return;
  const session = sessionGeneration, navigation = navigationGeneration, id = document.id;
  setBusy(true, "approve");
  try {
    const updated = await api().approve(document.id, {
      revision_id: document.head.id,
      expected_document_version: state.editorBase.version,
      confirmed_review: true,
      acknowledged_issue_ids: [...state.acknowledged],
      reason: state.reviewReason.trim() || "Đã đối chiếu với ảnh nguồn",
    });
    if (!currentView(session, navigation, id)) return;
    setEditorDocument(updated);
    state.reviewed = false;
    state.message = { text: "Đã duyệt đúng revision đang mở. Có thể xuất JSON từ revision này.", kind: "success" };
    const revisions = await api().revisions(document.id);
    if (!currentView(session, navigation, id)) return;
    state.revisions = revisions.items || [];
    await refreshDocuments();
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

async function exportRevision() {
  const document = state.document;
  if (!document || !state.exportRevisionId || state.busy) return;
  const session = sessionGeneration, navigation = navigationGeneration, id = document.id;
  const selected = state.revisions.find((revision) => revision.id === state.exportRevisionId);
  if (!selected?.approved_at) return message("Chỉ revision đã duyệt mới được xuất.", "error");
  setBusy(true, "export");
  try {
    const artifact = await api().createExport(document.id, selected.id);
    const blob = await api().downloadExport(artifact.id);
    if (!currentView(session, navigation, id)) return;
    const url = URL.createObjectURL(blob);
    const anchor = documentElement("a", { href: url, download: `vietdoc-${selected.id}.json` });
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
    state.message = { text: `Đã xuất JSON của revision ${selected.id}.`, kind: "success" };
  } catch (error) { if (currentView(session, navigation, id)) apiFailure(error); }
  finally { if (currentView(session, navigation, id)) { state.busy = false; state.busyAction = ""; render(); } }
}

function documentElement(tag, attributes) {
  const element = document.createElement(tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function isDirty() {
  if (!state.editorBase || !state.payload) return false;
  return stableStringify(toBusinessPayload(state.document.document_type, state.payload)) !==
    stableStringify(state.editorBase.payload);
}

function hasUnsavedReview() {
  return isDirty() || state.changedPaths.size > 0 || state.changedItemFields.size > 0;
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function updateBoundValue(target) {
  if (target.dataset.scalar) {
    state.payload[target.dataset.scalar] = target.value === "" ? null : target.value;
    state.changedPaths.add(`/${target.dataset.scalar}`);
  } else if (target.dataset.itemField) {
    const index = Number(target.dataset.index);
    state.payload.items[index][target.dataset.itemField] = target.value === "" ? null : target.value;
    const rowId = state.rowIds[index];
    if (!state.changedItemFields.has(rowId)) state.changedItemFields.set(rowId, new Set());
    state.changedItemFields.get(rowId).add(target.dataset.itemField);
  }
  const stateLabel = root.querySelector("[data-save-state]");
  if (stateLabel) stateLabel.textContent = isDirty() ? "Có thay đổi chưa lưu" : "Đã khớp bản đang mở";
  syncDraftControls();
}

function syncDraftControls() {
  const pending = hasUnsavedReview();
  const remote = remoteChanged();
  const saveButton = root.querySelector('[data-action="save"]');
  if (saveButton) saveButton.disabled = !pending || remote || state.busy;
  const approveButton = root.querySelector('[data-action="approve"]');
  if (approveButton && (pending || remote || state.busy)) approveButton.disabled = true;
  const rerunButton = root.querySelector('[data-action="rerun"]');
  if (rerunButton) rerunButton.disabled = pending || remote ||
    isActiveJob(state.document?.job) || state.busy;
  for (const button of root.querySelectorAll("[data-adopt-run]"))
    if (pending || remote || state.busy) button.disabled = true;
}

function render({ passive = false } = {}) {
  if (passive && root.contains(document.activeElement) &&
      document.activeElement?.matches?.("input, textarea, select")) {
    const notice = root.querySelector("[data-remote-notice]");
    if (notice) notice.hidden = !remoteChanged();
    syncDraftControls();
    return;
  }
  const scrollTop = passive ? root.querySelector(".review-scroll")?.scrollTop : undefined;
  if (!state.user) {
    root.innerHTML = renderLogin();
    return;
  }
  root.innerHTML = renderShell();
  if (scrollTop !== undefined) {
    const scroll = root.querySelector(".review-scroll");
    if (scroll) scroll.scrollTop = scrollTop;
  }
  if (state.message) {
    const notice = root.querySelector("[data-message]");
    if (notice) {
      notice.textContent = state.message.text;
      notice.className = `notice ${state.message.kind === "error" ? "error" : state.message.kind === "success" ? "success" : ""}`;
    }
  }
}

function renderLogin() {
  return `<main class="login-page">
    <section class="login-art">
      <div><div class="brand"><span class="brand-mark">V</span><span>VietDoc<small>document review workspace</small></span></div>
        <h1>Đọc chứng từ. Đối chiếu tự tin.</h1>
        <p>Ảnh được lưu riêng tư. Bạn kiểm tra, chỉnh sửa và duyệt dữ liệu trước khi xuất.</p>
      </div>
    </section>
    <section class="login-content"><div class="login-card">
      <div class="eyebrow">Không gian làm việc an toàn</div>
      <h2>Đăng nhập</h2><p>Dùng tài khoản VietDoc được cấp để tiếp tục.</p>
      ${renderModeBadge()}
      <form class="login-form" data-login>
        <div class="field"><label for="username">Tên đăng nhập</label><input id="username" name="username" autocomplete="username" required value="${escapeHtml(state.username)}" /></div>
        <div class="field"><label for="password">Mật khẩu</label><input id="password" name="password" type="password" autocomplete="current-password" required value="${escapeHtml(state.password)}" /></div>
        <button class="btn btn-primary" type="submit" ${state.busy ? "disabled" : ""}>${state.busy ? '<span class="spinner"></span> Đang đăng nhập' : "Đăng nhập"}</button>
      </form>
      ${state.message ? `<div class="notice error" data-message>${escapeHtml(state.message.text)}</div>` : ""}
    </div></section>
  </main>`;
}

function renderShell() {
  const docs = state.documents.map((item) => renderDocumentRow(item)).join("");
  const selected = state.document;
  return `<div class="shell">
    <header class="topbar">
      <div class="brand"><span class="brand-mark">V</span><span>VietDoc<small>document review workspace</small></span></div>
      <div class="userbar"><span class="avatar">${escapeHtml((state.user.username || "U").slice(0, 1).toUpperCase())}</span><span>${escapeHtml(state.user.username)}</span><button class="btn btn-quiet btn-small" data-action="logout">Đăng xuất</button></div>
    </header>
    <main class="page">
      <div class="page-head"><div><div class="eyebrow">VietDoc / Review</div><h1>Chứng từ của bạn</h1><p class="subtitle">Tải lên, đối chiếu dữ liệu và duyệt trước khi xuất.</p>${renderModeBadge()}</div>
        ${selected ? `<button class="btn btn-secondary" data-action="reload">Tải lại</button>` : ""}
      </div>
      ${state.message ? `<div class="notice ${state.message.kind === "error" ? "error" : state.message.kind === "success" ? "success" : ""}" data-message>${escapeHtml(state.message.text)}</div>` : ""}
      <div class="layout">
        <aside>
          ${renderUpload()}
          <section class="panel"><div class="panel-head"><h2>Danh sách chứng từ</h2><span class="pill">${state.documents.length} gần đây</span></div>
            <div class="panel-body"><div class="document-list">${docs || '<div class="empty-state">Chưa có chứng từ. Tải ảnh hoặc PDF lên để bắt đầu.</div>'}</div></div>
          </section>
        </aside>
        <section class="panel workspace">${selected ? renderWorkspace(selected) : renderWelcome()}</section>
      </div>
    </main>
  </div>`;
}

function renderModeBadge() {
  const label = processingMode === "demo" ? "Demo · kết quả giả lập" :
    processingMode === "manual" ? "Manual · không chạy AI" : "Chế độ xử lý chưa xác định";
  return `<span class="pill mode-pill" data-processing-mode>${label}</span>`;
}

function renderUpload() {
  const fileText = state.uploadFile ? escapeHtml(state.uploadFile.name) : "";
  return `<section class="panel upload-card"><div class="panel-head"><h2>Tải chứng từ lên</h2><span class="eyebrow">Bước 1</span></div>
    <div class="panel-body"><form data-upload>
      <div class="dropzone" data-dropzone tabindex="0" role="button" aria-label="Chọn hoặc thả file chứng từ">
        <div class="upload-icon">↑</div><strong>Kéo thả ảnh hoặc PDF vào đây</strong><p>Hỗ trợ JPG, PNG hoặc PDF · tối đa 20 MB</p>
        <label class="browse" for="upload-file">Chọn file</label><input id="upload-file" type="file" accept="image/jpeg,image/png,application/pdf,.jpg,.jpeg,.png,.pdf" hidden />
        ${fileText ? `<div class="file-name">${fileText}</div>` : ""}
      </div>
      <div class="upload-controls"><select name="document_type" aria-label="Loại chứng từ"><option value="receipt" ${state.uploadType === "receipt" ? "selected" : ""}>Receipt / Hóa đơn bán lẻ</option><option value="invoice" ${state.uploadType === "invoice" ? "selected" : ""}>Invoice / Hóa đơn</option></select>
        <button class="btn btn-primary" type="submit" ${state.busy ? "disabled" : ""}>${state.busyAction === "upload" ? '<span class="spinner"></span>' : "Tải & xử lý"}</button></div>
      <p class="upload-note"><span>🔒</span><span>File gốc ở private storage. Metadata, hash và trạng thái job được quản lý trong backend.</span></p>
    </form></div></section>`;
}

function renderDocumentRow(document) {
  const status = documentStatus(document);
  return `<button class="document-row ${document.id === state.selectedId ? "active" : ""}" data-open="${escapeHtml(document.id)}">
    <span class="document-row-top"><span class="document-name">${escapeHtml(document.filename)}</span><span class="pill pill-${status.toLowerCase()}">${escapeHtml(statusLabel(status))}</span></span>
    <span class="document-meta">${document.document_type === "receipt" ? "Receipt" : "Invoice"} · ${formatDate(document.created_at)}${document.job?.state === "FAILED" ? ` · ${escapeHtml(document.job.error_code || "Lỗi")}` : ""}</span>
  </button>`;
}

function renderWelcome() {
  return `<div class="viewer-side"><div class="viewer-toolbar"><strong>Ảnh chứng từ</strong></div><div class="image-stage"><div class="empty-viewer"><div class="upload-icon">▧</div>Chọn chứng từ trong danh sách hoặc tải file mới lên để xem ảnh và dữ liệu trích xuất.</div></div></div>
    <div class="review-side"><div class="review-toolbar"><h2>Đối chiếu dữ liệu</h2></div><div class="empty-state">Ảnh sẽ hiển thị bên trái.<br />Các trường và dòng hàng sẽ xuất hiện ở đây sau khi xử lý.</div></div>`;
}

function renderWorkspace(document) {
  const status = documentStatus(document);
  return `<div class="viewer-side"><div class="viewer-toolbar"><strong>Ảnh chứng từ gốc</strong><span class="pill">Trang 1 / 1</span></div>
      <div class="image-stage">${state.imageUrl ? `<img class="document-image" src="${escapeHtml(state.imageUrl)}" alt="Ảnh chứng từ ${escapeHtml(document.filename)}" />` : '<div class="loading">Đang tải ảnh…</div>'}</div>
    </div><div class="review-side">${renderReview(document, status)}</div>`;
}

function renderReview(document, status) {
  const head = document.head;
  const payload = currentPayload();
  const fields = document.document_type === "receipt" ? RECEIPT_FIELDS : INVOICE_FIELDS;
  const active = isActiveJob(document.job);
  const warnings = (head?.issues || []).filter((issue) => issue.severity === "warning");
  const blockers = (head?.issues || []).filter((issue) => issue.severity === "blocking");
  const allWarningsChecked = warnings.every((issue) => state.acknowledged.has(issue.id));
  const approvedRevisions = state.revisions.filter((revision) => revision.approved_at);
  const candidates = state.runs.filter((run) => run.id !== head?.run_id);
  const selectedExportId = approvedRevisions.some((revision) => revision.id === state.exportRevisionId)
    ? state.exportRevisionId
    : approvedRevisions[0]?.id || "";
  state.exportRevisionId = selectedExportId;

  return `<div class="review-toolbar"><div><div class="eyebrow">${document.document_type === "receipt" ? "Receipt" : "Invoice"}</div><h2>Đối chiếu dữ liệu</h2></div><span class="pill pill-${status.toLowerCase()}">${escapeHtml(statusLabel(status))}</span></div>
    ${active ? renderJobProgress(document.job) : ""}
    ${document.job?.state === "FAILED" ? `<div class="notice error"><strong>${escapeHtml(document.job.error_code || "JOB_FAILED")}</strong><br />${escapeHtml(document.job.error_message || "Không xử lý được file. Bạn có thể chạy lại job.")}</div>` : ""}
    <div class="review-scroll">
      <div class="revision-info"><span>${head ? `Revision ${escapeHtml(head.id.slice(0, 8))} · ${head.state === "APPROVED" ? "Đã duyệt" : "Bản nháp"}` : "Chưa có kết quả để review"}</span><span data-save-state>${isDirty() ? "Có thay đổi chưa lưu" : "Prediction gốc được giữ nguyên"}</span></div>
      <div class="notice error" data-remote-notice ${remoteChanged() ? "" : "hidden"}>Chứng từ đã thay đổi ở phiên khác. Tải lại để đối chiếu revision mới trước khi lưu hoặc duyệt.</div>
      ${head ? `<div class="field-grid">${fields.map(([key, label, kind]) => renderField(key, label, kind, payload[key])).join("")}</div>
        ${renderItems(payload.items || [])}
        ${renderIssues(head.issues || [])}
        ${renderReviewActions(document, warnings, blockers, allWarningsChecked)}
      ` : `<div class="empty-state">${active ? "Đang chờ runner xử lý. Kết quả sẽ tự xuất hiện ở đây." : "Chưa có prediction. Có thể xếp job vào hàng đợi."}${!active ? '<div class="action-row" style="justify-content:center"><button class="btn btn-primary" data-action="rerun" ' + (state.busy ? "disabled" : "") + '>Chạy xử lý</button></div>' : ""}</div>`}
      ${candidates.length ? renderCandidates(candidates) : ""}
      ${renderExport(document, approvedRevisions, selectedExportId)}
    </div>`;
}

function renderField(key, label, kind, value) {
  const inputType = kind === "date" ? "date" : kind === "time" ? "time" : "text";
  const inputMode = kind === "decimal" ? 'inputmode="decimal"' : "";
  const placeholder = kind === "decimal" ? 'placeholder="Ví dụ: 85000"' : 'placeholder="Chưa xác định"';
  return `<div class="field"><label for="field-${key}">${escapeHtml(label)}</label><input id="field-${key}" data-scalar="${key}" type="${inputType}" ${inputMode} ${placeholder} value="${escapeHtml(value ?? "")}" ${state.busy ? "disabled" : ""} /><button type="button" class="btn btn-quiet btn-small" data-review-field="${key}" ${state.busy ? "disabled" : ""}>${state.changedPaths.has(`/${key}`) ? "Đã đánh dấu đối chiếu" : "Đánh dấu đã đối chiếu"}</button></div>`;
}

function renderItems(items) {
  const cards = items.map((item, index) => `<article class="item-card"><div class="item-card-head"><span>Dòng hàng ${index + 1}</span><button type="button" class="btn btn-quiet btn-small" data-remove-item="${index}" aria-label="Xóa dòng hàng ${index + 1}" ${state.busy ? "disabled" : ""}>Xóa</button></div>
      <div class="item-grid">${ITEM_FIELDS.map(([key, label, kind]) => renderItemField(index, key, label, kind, item[key])).join("")}</div></article>`).join("");
  return `<div class="section-heading"><h3>Dòng hàng (${items.length})</h3><button type="button" class="btn btn-secondary btn-small" data-action="add-item" ${items.length >= 30 || state.busy ? "disabled" : ""}>+ Thêm dòng</button></div>
    ${cards || '<div class="empty-state" style="padding:18px">Chưa có dòng hàng. Có thể thêm nếu chứng từ có bảng hàng hóa.</div>'}`;
}

function renderItemField(index, key, label, kind, value) {
  const inputMode = kind === "decimal" ? 'inputmode="decimal"' : "";
  return `<div class="field"><label for="item-${index}-${key}">${escapeHtml(label)}</label><input id="item-${index}-${key}" data-index="${index}" data-item-field="${key}" type="text" ${inputMode} placeholder="Chưa xác định" value="${escapeHtml(value ?? "")}" ${state.busy ? "disabled" : ""} /></div>`;
}

function renderIssues(issues) {
  if (!issues.length) return "";
  return `<div class="section-heading"><h3>Điểm cần đối chiếu (${issues.length})</h3></div>${issues.map((issue) => {
    const severity = issue.severity === "blocking" ? "blocking" : issue.severity === "warning" ? "warning" : "info";
    const checked = state.acknowledged.has(issue.id) ? "checked" : "";
    const content = `<strong>${escapeHtml(issue.code)}</strong>${escapeHtml(issue.message)}`;
    return `<div class="issue issue-${severity}">${issue.severity === "warning"
      ? `<label><input type="checkbox" data-ack="${escapeHtml(issue.id)}" ${checked} ${state.busy ? "disabled" : ""} /><span>${content}</span></label>`
      : content}</div>`;
  }).join("")}`;
}

function renderReviewActions(document, warnings, blockers, allWarningsChecked) {
  const dirty = isDirty();
  const pending = dirty || state.changedPaths.size || state.changedItemFields.size;
  const canApprove = state.reviewed && !pending && !remoteChanged() && !blockers.length && allWarningsChecked && !state.busy;
  const disabledSave = !pending || remoteChanged() || state.busy || !document.head;
  return `<div class="field reason-field"><label for="review-reason">Ghi chú đối chiếu / lý do</label><input id="review-reason" data-reason value="${escapeHtml(state.reviewReason)}" maxlength="1000" ${state.busy ? "disabled" : ""} /></div>
    <label class="approval-check"><input type="checkbox" data-reviewed ${state.reviewed ? "checked" : ""} ${state.busy ? "disabled" : ""} /><span>Tôi đã đối chiếu dữ liệu với ảnh nguồn và xác nhận mức độ đầy đủ của chứng từ.</span></label>
    ${pending ? '<div class="notice">Có thay đổi hoặc xác nhận field chưa lưu. Hãy lưu thành revision mới trước khi duyệt hoặc chạy xử lý lại.</div>' : ""}
    ${blockers.length ? `<div class="notice error">Còn ${blockers.length} điều kiện chặn. Sửa dữ liệu hoặc kiểm tra lại nội dung trên ảnh trước khi duyệt.</div>` : ""}
    ${warnings.length && !allWarningsChecked ? '<div class="notice">Hãy xác nhận từng cảnh báo để tiếp tục duyệt.</div>' : ""}
    <div class="action-row"><button class="btn btn-secondary" data-action="save" ${disabledSave ? "disabled" : ""}>${state.busyAction === "save" ? '<span class="spinner"></span>' : "Lưu bản sửa"}</button>
      <button class="btn btn-primary" data-action="approve" ${canApprove ? "" : "disabled"}>${state.busyAction === "approve" ? '<span class="spinner"></span>' : "Duyệt revision này"}</button>
      <button class="btn btn-secondary" data-action="rerun" ${isActiveJob(document.job) || pending || remoteChanged() || state.busy ? "disabled" : ""}>${state.busyAction === "rerun" ? '<span class="spinner"></span>' : "Chạy xử lý lại"}</button></div>`;
}

function renderJobProgress(job) {
  const labels = { QUEUED: "Đang chờ runner", RUNNING: "Đang xử lý chứng từ", RETRYING: "Đang thử lại" };
  return `<div class="job-progress"><strong><span class="spinner"></span> ${escapeHtml(labels[job.state] || "Đang xử lý")}</strong><p>Job ${escapeHtml(job.id.slice(0, 8))} · Giai đoạn: ${escapeHtml(job.stage || "WAITING")} · Lần chạy ${job.attempts}</p><div class="progress-track"><span></span></div></div>`;
}

function renderCandidates(runs) {
  return `<div class="section-heading"><h3>Kết quả xử lý khác</h3></div>${runs.map((run) => `<div class="revision-info"><span>Run ${escapeHtml(run.id.slice(0, 8))} · ${formatDate(run.created_at)}</span><button class="btn btn-secondary btn-small" data-adopt-run="${escapeHtml(run.id)}" ${state.busy || remoteChanged() || isDirty() || state.changedPaths.size || state.changedItemFields.size || !state.document.head ? "disabled" : ""}>Tạo revision từ candidate</button></div>`).join("")}`;
}

function renderExport(document, approved, selectedId) {
  if (!approved.length) return `<div class="section-heading"><h3>Xuất dữ liệu</h3></div><div class="empty-state" style="padding:12px">Chưa có revision được duyệt. Bản nháp không thể xuất.</div>`;
  return `<div class="section-heading"><h3>Xuất JSON đã duyệt</h3></div><div class="upload-controls"><select data-export-revision aria-label="Revision được duyệt">${approved.map((revision) => `<option value="${escapeHtml(revision.id)}" ${selectedId === revision.id ? "selected" : ""}>${escapeHtml(revision.id.slice(0, 8))} · ${formatDate(revision.approved_at)}</option>`).join("")}</select><button class="btn btn-primary" data-action="export" ${state.busy ? "disabled" : ""}>${state.busyAction === "export" ? '<span class="spinner"></span>' : "Xuất JSON"}</button></div><p class="upload-note">Xuất luôn gắn với revision đã duyệt đang chọn; revision nháp không được gửi.</p>`;
}

function formatDate(value) {
  if (!value) return "";
  try { return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
  catch { return String(value); }
}

root.addEventListener("submit", (event) => {
  if (event.target.matches("[data-login]")) return login(event);
  if (event.target.matches("[data-upload]")) return uploadAndProcess(event);
});

root.addEventListener("input", (event) => {
  const target = event.target;
  if (target.name === "username") state.username = target.value;
  if (target.name === "password") state.password = target.value;
  if (target.matches("[data-scalar], [data-item-field]")) updateBoundValue(target);
  if (target.matches("[data-reason]")) state.reviewReason = target.value;
});

root.addEventListener("change", (event) => {
  const target = event.target;
  if (target.id === "upload-file") {
    state.uploadFile = target.files?.[0] || null;
    state.message = null;
    return render();
  }
  if (target.name === "document_type") { state.uploadType = target.value; return; }
  if (target.matches("[data-scalar], [data-item-field]")) { updateBoundValue(target); return render(); }
  if (target.matches("[data-reason]")) { state.reviewReason = target.value; return; }
  if (target.matches("[data-ack]")) {
    if (target.checked) state.acknowledged.add(target.dataset.ack);
    else state.acknowledged.delete(target.dataset.ack);
    return render();
  }
  if (target.matches("[data-reviewed]")) { state.reviewed = target.checked; return render(); }
  if (target.matches("[data-export-revision]")) { state.exportRevisionId = target.value; }
});

root.addEventListener("click", (event) => {
  const open = event.target.closest("[data-open]");
  if (open) return openDocument(open.dataset.open);
  if (state.busy && event.target.closest("[data-remove-item], [data-adopt-run], [data-review-field]")) return;
  const reviewedField = event.target.closest("[data-review-field]");
  if (reviewedField) {
    state.changedPaths.add(`/${reviewedField.dataset.reviewField}`);
    return render();
  }
  const remove = event.target.closest("[data-remove-item]");
  if (remove) {
    const index = Number(remove.dataset.removeItem);
    state.changedItemFields.delete(state.rowIds[index]);
    state.payload.items.splice(index, 1);
    state.rowIds.splice(index, 1);
    state.changedPaths.add("/items");
    return render();
  }
  const adopt = event.target.closest("[data-adopt-run]");
  if (adopt) return adoptCandidate(adopt.dataset.adoptRun);
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "logout") return logout();
  if (action === "reload") {
    if (state.selectedId && (isDirty() || state.changedPaths.size || state.changedItemFields.size) &&
        !window.confirm("Tải lại sẽ bỏ các thay đổi chưa lưu. Tiếp tục?")) return;
    return openDocument(state.selectedId);
  }
  if (action === "save") return saveReview();
  if (action === "approve") return approve();
  if (action === "rerun") return rerun();
  if (action === "export") return exportRevision();
  if (action === "add-item" && !state.busy && state.payload.items.length < 30) {
    state.payload.items.push(emptyItem());
    state.rowIds.push(crypto.randomUUID());
    state.changedPaths.add("/items");
    render();
  }
});

root.addEventListener("change", (event) => {
  if (event.target.matches("#upload-file")) return;
});

root.addEventListener("dragover", (event) => {
  const dropzone = event.target.closest("[data-dropzone]");
  if (dropzone) { event.preventDefault(); dropzone.classList.add("dragging"); }
});
root.addEventListener("dragleave", (event) => event.target.closest("[data-dropzone]")?.classList.remove("dragging"));
root.addEventListener("drop", (event) => {
  const dropzone = event.target.closest("[data-dropzone]");
  if (!dropzone) return;
  event.preventDefault();
  dropzone.classList.remove("dragging");
  state.uploadFile = event.dataTransfer.files?.[0] || null;
  render();
});
root.addEventListener("click", (event) => {
  if (event.target.closest("[data-dropzone]") && !event.target.closest("label"))
    root.querySelector("#upload-file")?.click();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && state.user) {
    const session = sessionGeneration;
    refreshDocuments().catch(error => {
      if (session === sessionGeneration) apiFailure(error);
    });
  }
});

start();

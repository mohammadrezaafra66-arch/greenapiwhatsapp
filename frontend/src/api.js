import axios from "axios";

// Backend base URL. Override at build time with VITE_API_BASE.
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";

export const http = axios.create({ baseURL: BASE, timeout: 30000 });

// ── Dashboard ──────────────────────────────────────────
export const Dashboard = {
  stats: () => http.get("/dashboard/stats").then((r) => r.data),
  rateLimits: () => http.get("/dashboard/rate-limits").then((r) => r.data),
  updateRateLimits: (schedule) =>
    http.put("/dashboard/rate-limits", schedule).then((r) => r.data),
};

// ── Accounts ───────────────────────────────────────────
export const Accounts = {
  list: () => http.get("/accounts/").then((r) => r.data),
  create: (name, instance_id, api_token) =>
    http
      .post("/accounts/", null, { params: { name, instance_id, api_token } })
      .then((r) => r.data),
  status: (id) => http.get(`/accounts/${id}/status`).then((r) => r.data),
  qr: (id) => http.get(`/accounts/${id}/qr`).then((r) => r.data),
  reboot: (id) => http.post(`/accounts/${id}/reboot`).then((r) => r.data),
  logout: (id) => http.post(`/accounts/${id}/logout`).then((r) => r.data),
  updateAutoReply: (id, payload) =>
    http.put(`/accounts/${id}/auto-reply`, payload).then((r) => r.data),
  queue: (id) => http.get(`/accounts/${id}/queue`).then((r) => r.data),
  clearQueue: (id) => http.delete(`/accounts/${id}/queue`).then((r) => r.data),
  remove: (id) => http.delete(`/accounts/${id}`).then((r) => r.data),
};

// ── Campaigns ──────────────────────────────────────────
export const Campaigns = {
  list: () => http.get("/campaigns/").then((r) => r.data),
  create: (body) => http.post("/campaigns/", body).then((r) => r.data),
  addContacts: (id, contactIds) =>
    http.post(`/campaigns/${id}/contacts`, contactIds).then((r) => r.data),
  start: (id) => http.post(`/campaigns/${id}/start`).then((r) => r.data),
  pause: (id) => http.post(`/campaigns/${id}/pause`).then((r) => r.data),
  resume: (id) => http.post(`/campaigns/${id}/resume`).then((r) => r.data),
  test: (id, phone, message) =>
    http.post(`/campaigns/${id}/test`, { phone, message }).then((r) => r.data),
  progress: (id) => http.get(`/campaigns/${id}/progress`).then((r) => r.data),
  contacts: (id, status) =>
    http.get(`/campaigns/${id}/contacts`, { params: status ? { status } : {} }).then((r) => r.data),
  get: (id) => http.get(`/campaigns/${id}`).then((r) => r.data),
  update: (id, body) => http.put(`/campaigns/${id}`, body).then((r) => r.data),
  toggleActive: (id) => http.post(`/campaigns/${id}/toggle-active`).then((r) => r.data),
  remove: (id) => http.delete(`/campaigns/${id}`).then((r) => r.data),
};

// ── Contacts ───────────────────────────────────────────
export const Contacts = {
  list: (params = {}) => http.get("/contacts/", { params }).then((r) => r.data),
  create: (body) => http.post("/contacts/", body).then((r) => r.data),
  import: (file, source = "excel_import") => {
    const fd = new FormData();
    fd.append("file", file);
    return http
      .post("/contacts/import", fd, { params: { source } })
      .then((r) => r.data);
  },
  checkBulk: (contactIds) =>
    http.post("/contacts/check-bulk", contactIds).then((r) => r.data),
  history: (id, count = 50) =>
    http.get(`/contacts/${id}/history`, { params: { count } }).then((r) => r.data),
  blacklist: (id, reason) =>
    http.post(`/contacts/${id}/blacklist`, null, { params: { reason } }).then((r) => r.data),
  remove: (id) => http.delete(`/contacts/${id}`).then((r) => r.data),
};

// ── Inbox ──────────────────────────────────────────────
export const Inbox = {
  list: (params = {}) => http.get("/inbox/", { params }).then((r) => r.data),
  markRead: (id) => http.post(`/inbox/${id}/read`).then((r) => r.data),
  reply: (message_id, text) =>
    http.post("/inbox/reply", { message_id, text }).then((r) => r.data),
  stats: () => http.get("/inbox/stats").then((r) => r.data),
};

// ── Groups ─────────────────────────────────────────────
export const Groups = {
  list: () => http.get("/groups/").then((r) => r.data),
  create: (body) => http.post("/groups/", body).then((r) => r.data),
  addMembers: (id, phones) =>
    http.post(`/groups/${id}/members`, { phones }).then((r) => r.data),
  removeMember: (id, phone) =>
    http.delete(`/groups/${id}/members/${phone}`).then((r) => r.data),
  send: (id, message) =>
    http.post(`/groups/${id}/send`, { message }).then((r) => r.data),
  info: (id) => http.get(`/groups/${id}/info`).then((r) => r.data),
  sync: (accountId) => http.post(`/groups/sync/${accountId}`).then((r) => r.data),
};

// ── Statuses ───────────────────────────────────────────
export const Statuses = {
  sendText: (text, bg_color, account_ids) =>
    http.post("/statuses/text", { text, bg_color, account_ids }).then((r) => r.data),
  sendImage: (image_url, caption, account_ids) =>
    http.post("/statuses/image", { image_url, caption, account_ids }).then((r) => r.data),
  stats: (messageId) =>
    http.get(`/statuses/${messageId}/stats`).then((r) => r.data),
};

// ── Templates ──────────────────────────────────────────
export const Templates = {
  list: (category) =>
    http.get("/templates/", { params: { category } }).then((r) => r.data),
  create: (body) => http.post("/templates/", body).then((r) => r.data),
  use: (id) => http.post(`/templates/${id}/use`).then((r) => r.data),
  remove: (id) => http.delete(`/templates/${id}`).then((r) => r.data),
};

// ── Keyword Rules ──────────────────────────────────────────
export const KeywordRulesApi = {
  list: () => http.get("/keyword-rules/").then((r) => r.data),
  create: (body) => http.post("/keyword-rules/", body).then((r) => r.data),
  update: (id, body) => http.put(`/keyword-rules/${id}`, body).then((r) => r.data),
  delete: (id) => http.delete(`/keyword-rules/${id}`).then((r) => r.data),
};

// ── Account Schedules ──────────────────────────────────────
export const AccountSchedulesApi = {
  get: (accountId) => http.get(`/account-schedules/${accountId}`).then((r) => r.data),
  createSlot: (body) => http.post("/account-schedules/", body).then((r) => r.data),
  updateSlot: (id, body) => http.put(`/account-schedules/${id}`, body).then((r) => r.data),
  deleteSlot: (id) => http.delete(`/account-schedules/${id}`).then((r) => r.data),
  updateDelay: (accountId, body) => http.put(`/account-schedules/${accountId}/delay`, body).then((r) => r.data),
};

// ── AI (multi-provider) ────────────────────────────────────
export const AiApi = {
  stats: () => http.get("/dashboard/ai-stats").then((r) => r.data),
  providers: () => http.get("/dashboard/ai-providers").then((r) => r.data),
};

// ── Journals ───────────────────────────────────────────────
export const JournalsApi = {
  incoming: (accountId, minutes = 1440) => http.get(`/journals/${accountId}/incoming?minutes=${minutes}`).then((r) => r.data),
  outgoing: (accountId, minutes = 1440) => http.get(`/journals/${accountId}/outgoing?minutes=${minutes}`).then((r) => r.data),
  chats: (accountId) => http.get(`/journals/${accountId}/chats`).then((r) => r.data),
  queueCount: (accountId) => http.get(`/journals/${accountId}/queue-count`).then((r) => r.data),
  clearWebhooks: (accountId) => http.delete(`/journals/${accountId}/webhooks-queue`).then((r) => r.data),
};

// ── Files ──────────────────────────────────────────────────
export const FilesApi = {
  upload: (accountId, formData) => http.post(`/files/upload/${accountId}`, formData, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data),
  list: (accountId) => http.get(`/files/list/${accountId}`).then((r) => r.data),
};

// ── Proxy & blocked contacts ───────────────────────────────
export const ProxyApi = {
  get: (accountId) => http.get(`/accounts/${accountId}/proxy`).then((r) => r.data),
  set: (accountId, body) => http.put(`/accounts/${accountId}/proxy`, body).then((r) => r.data),
  getBlocked: (accountId) => http.get(`/accounts/${accountId}/blocked-contacts`).then((r) => r.data),
};

// ── Contact extras (disappearing / phonebook) ──────────────
export const ContactExtrasApi = {
  setDisappearing: (id, ephemeral) => http.post(`/contacts/${id}/disappearing?ephemeral=${ephemeral}`).then((r) => r.data),
  addToPhonebook: (id) => http.post(`/contacts/${id}/add-to-phonebook`).then((r) => r.data),
  editPhonebook: (id, first_name, last_name = "") =>
    http.put(`/contacts/${id}/phonebook`, null, { params: { first_name, last_name } }).then((r) => r.data),
};

// ── Contact Groups ─────────────────────────────────────────
export const ContactGroupsApi = {
  list: () => http.get("/contact-groups/").then((r) => r.data),
  create: (body) => http.post("/contact-groups/", body).then((r) => r.data),
  update: (id, body) => http.put(`/contact-groups/${id}`, body).then((r) => r.data),
  delete: (id) => http.delete(`/contact-groups/${id}`).then((r) => r.data),
  addMembers: (id, contact_ids) => http.post(`/contact-groups/${id}/members`, { contact_ids }).then((r) => r.data),
  removeMember: (id, contact_id) => http.delete(`/contact-groups/${id}/members/${contact_id}`).then((r) => r.data),
  contacts: (id) => http.get(`/contact-groups/${id}/contacts`).then((r) => r.data),
};

// ── WA Group Collections ───────────────────────────────────
export const WaCollectionsApi = {
  list: () => http.get("/wa-collections/").then((r) => r.data),
  create: (body) => http.post("/wa-collections/", body).then((r) => r.data),
  update: (id, body) => http.put(`/wa-collections/${id}`, body).then((r) => r.data),
  delete: (id) => http.delete(`/wa-collections/${id}`).then((r) => r.data),
  addGroup: (id, body) => http.post(`/wa-collections/${id}/groups`, body).then((r) => r.data),
  removeGroup: (id, chat_id) => http.delete(`/wa-collections/${id}/groups/${encodeURIComponent(chat_id)}`).then((r) => r.data),
  groups: (id) => http.get(`/wa-collections/${id}/groups`).then((r) => r.data),
};

// ── Reporting ──────────────────────────────────────────────
export const ReportingApi = {
  emergencyContacts: () => http.get("/reporting/emergency-contacts").then((r) => r.data),
  addEmergency: (body) => http.post("/reporting/emergency-contacts", body).then((r) => r.data),
  deleteEmergency: (id) => http.delete(`/reporting/emergency-contacts/${id}`).then((r) => r.data),
  subscribers: () => http.get("/reporting/subscribers").then((r) => r.data),
  addSubscriber: (body) => http.post("/reporting/subscribers", body).then((r) => r.data),
  deleteSubscriber: (id) => http.delete(`/reporting/subscribers/${id}`).then((r) => r.data),
  dailyLogs: (date) => http.get(`/reporting/daily-logs${date ? `?date=${date}` : ""}`).then((r) => r.data),
  productMentions: () => http.get("/dashboard/product-mentions/recent").then((r) => r.data),
  clearMentions: () => http.delete("/reporting/product-mentions").then((r) => r.data),
};

// ── Products & Labels ──────────────────────────────────────
export const ProductsApi = {
  list: () => http.get("/reporting/products").then((r) => r.data),
};
export const LabelsApi = {
  list: () => http.get("/reporting/product-labels").then((r) => r.data),
};

// ── Blacklist ──────────────────────────────────────────
export const BlacklistApi = {
  list: () => http.get("/blacklist/").then((r) => r.data),
  add: (phone, reason) =>
    http.post("/blacklist/", null, { params: { phone, reason } }).then((r) => r.data),
  remove: (phone) => http.delete(`/blacklist/${phone}`).then((r) => r.data),
};

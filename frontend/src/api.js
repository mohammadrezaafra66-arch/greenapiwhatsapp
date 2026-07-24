import axios from "axios";

// Backend base URL. Override at build time with VITE_API_BASE.
const BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";

export const http = axios.create({ baseURL: BASE, timeout: 30000 });

// ── Dashboard ──────────────────────────────────────────
export const Dashboard = {
  stats: () => http.get("/dashboard/stats").then((r) => r.data),
  rateLimits: () => http.get("/dashboard/rate-limits").then((r) => r.data),
  deliverability: () => http.get("/dashboard/deliverability").then((r) => r.data),
  systemHealth: () => http.get("/dashboard/health").then((r) => r.data),
  updateRateLimits: (schedule) =>
    http.put("/dashboard/rate-limits", schedule).then((r) => r.data),
  // V8 F36 — pre-send feasibility check. account_ids repeats in the query string.
  validateCampaign: ({ contact_count, account_ids = [], min_delay = 45, max_delay = 110 }) => {
    const p = new URLSearchParams();
    p.append("contact_count", contact_count);
    p.append("min_delay", min_delay);
    p.append("max_delay", max_delay);
    account_ids.forEach((id) => p.append("account_ids", id));
    return http.post(`/dashboard/validate-campaign?${p.toString()}`).then((r) => r.data);
  },
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
  setDefault: (id) => http.post(`/accounts/${id}/set-default`).then((r) => r.data),
  rename: (id, name) => http.put(`/accounts/${id}/rename`, { name }).then((r) => r.data),
  health: (id) => http.get(`/accounts/${id}/health`).then((r) => r.data),
  dailyLimitDetail: (id) => http.get(`/accounts/${id}/daily-limit-detail`).then((r) => r.data),
  updateLimits: (id, body) => http.put(`/accounts/${id}/limits`, body).then((r) => r.data),
  queue: (id) => http.get(`/accounts/${id}/queue`).then((r) => r.data),
  clearQueue: (id) => http.delete(`/accounts/${id}/queue`).then((r) => r.data),
  remove: (id) => http.delete(`/accounts/${id}`).then((r) => r.data),
  // V14 F17 — profile picture
  setProfilePicture: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return http.post(`/accounts/${id}/profile-picture`, fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 }).then((r) => r.data);
  },
  applyProfilePictureAll: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return http.post("/accounts/profile-picture/apply-all", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 }).then((r) => r.data);
  },
  pfpProgress: () => http.get("/accounts/profile-picture/apply-all/progress").then((r) => r.data),
  // V15 Item 26 — managed auto warm-up
  setWarmup: (id, enabled) => http.post(`/accounts/${id}/warmup`, { enabled }).then((r) => r.data),
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
  preview: (body) => http.post("/campaigns/preview", body).then((r) => r.data),
  progress: (id) => http.get(`/campaigns/${id}/progress`).then((r) => r.data),
  contacts: (id, status) =>
    http.get(`/campaigns/${id}/contacts`, { params: status ? { status } : {} }).then((r) => r.data),
  get: (id) => http.get(`/campaigns/${id}`).then((r) => r.data),
  update: (id, body) => http.put(`/campaigns/${id}`, body).then((r) => r.data),
  toggleActive: (id) => http.post(`/campaigns/${id}/toggle-active`).then((r) => r.data),
  retryFailed: (id) => http.post(`/campaigns/${id}/retry-failed`).then((r) => r.data),
  analytics: (id) => http.get(`/campaigns/${id}/analytics`).then((r) => r.data),
  abResults: (id) => http.get(`/campaigns/${id}/ab-results`).then((r) => r.data),
  roi: (id) => http.get(`/campaigns/${id}/roi`).then((r) => r.data),
  setOutcome: (id, ccId, body) => http.put(`/campaigns/${id}/contacts/${ccId}/outcome`, body).then((r) => r.data),
  recall: (id) => http.post(`/campaigns/${id}/recall`).then((r) => r.data),
  recallProgress: (id) => http.get(`/campaigns/${id}/recall-progress`).then((r) => r.data),
  remove: (id) => http.delete(`/campaigns/${id}`).then((r) => r.data),
};

// ── Contacts ───────────────────────────────────────────
export const Contacts = {
  list: (params = {}) => http.get("/contacts/", { params }).then((r) => r.data),
  count: () => http.get("/contacts/count").then((r) => r.data),
  dedupe: () => http.post("/contacts/dedupe").then((r) => r.data),
  exportUrl: (params = {}) => {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""))
    ).toString();
    return `${http.defaults.baseURL}/contacts/export${q ? `?${q}` : ""}`;
  },
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
  info: (phone, refresh = false) =>
    http.get(`/contacts/${phone}/info`, { params: refresh ? { refresh: true } : {} }).then((r) => r.data),
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
  list: (params = {}) => {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""))
    ).toString();
    return http.get(`/groups/${q ? `?${q}` : ""}`).then((r) => r.data);
  },
  refreshMembers: (groupId) => http.post(`/groups/${groupId}/refresh-members`).then((r) => r.data),
  extractMembers: (groupId) => http.post(`/groups/${groupId}/extract-members`, null, { timeout: 60000 }).then((r) => r.data),
  importMembersToContacts: (groupId, phones) =>
    http.post(`/groups/${groupId}/import-members-to-contacts`, { phones }).then((r) => r.data),
  create: (body) => http.post("/groups/", body).then((r) => r.data),
  addMembers: (id, phones) =>
    http.post(`/groups/${id}/members`, { phones }).then((r) => r.data),
  removeMember: (id, phone) =>
    http.delete(`/groups/${id}/members/${phone}`).then((r) => r.data),
  send: (id, message) =>
    http.post(`/groups/${id}/send`, { message }).then((r) => r.data),
  info: (id) => http.get(`/groups/${id}/info`).then((r) => r.data),
  // V14 F22 — full group management
  data: (id) => http.get(`/groups/${id}/data`).then((r) => r.data),
  settings: (id, body) => http.post(`/groups/${id}/settings`, body).then((r) => r.data),
  setPicture: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return http.post(`/groups/${id}/picture`, fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 }).then((r) => r.data);
  },
  updateName: (id, name, accountId) => http.put(`/groups/${id}/name`, null, { params: { name, account_id: accountId } }).then((r) => r.data),
  promote: (greenId, phone, accountId) => http.post(`/groups/${greenId}/admin/${phone}`, null, { params: { account_id: accountId } }).then((r) => r.data),
  demote: (greenId, phone, accountId) => http.delete(`/groups/${greenId}/admin/${phone}`, { params: { account_id: accountId } }).then((r) => r.data),
  leave: (greenId, accountId) => http.post(`/groups/${greenId}/leave`, null, { params: { account_id: accountId } }).then((r) => r.data),
  safeAdd: (id, phones) => http.post(`/groups/${id}/safe-add`, { phones }).then((r) => r.data),
  safeAddProgress: (id) => http.get(`/groups/${id}/safe-add-progress`).then((r) => r.data),
  sync: (accountId) => http.post(`/groups/sync/${accountId}`, null, { timeout: 120000 }).then((r) => r.data),
  extractAll: (accountId, minMembers = 0) =>
    http.post(`/groups/extract-all-members`, null, { params: { account_id: accountId, min_members: minMembers } }).then((r) => r.data),
  extractProgress: (accountId) => http.get(`/groups/extract-all-progress/${accountId}`).then((r) => r.data),
  // V8 F40 — add members to an admin group. group_id is the chatId (…@g.us).
  autoAddMembers: (group_id, account_id, phones) => {
    const p = new URLSearchParams();
    p.append("group_id", group_id);
    p.append("account_id", account_id);
    phones.forEach((ph) => p.append("contact_phones", ph));
    return http.post(`/groups/auto-add-members?${p.toString()}`).then((r) => r.data);
  },
  importExcelToGroup: (group_id, account_id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    const p = new URLSearchParams({ group_id, account_id });
    return http
      .post(`/groups/import-excel-to-group?${p.toString()}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 120000,
      })
      .then((r) => r.data);
  },
};

// ── Statuses ───────────────────────────────────────────
export const Statuses = {
  sendText: (text, bg_color, account_ids, participants) =>
    http.post("/statuses/text", { text, bg_color, account_ids, participants }).then((r) => r.data),
  sendImage: (image_url, caption, account_ids, participants) =>
    http.post("/statuses/image", { image_url, caption, account_ids, participants }).then((r) => r.data),
  sendVoice: (audio_url, account_ids, participants) =>
    http.post("/statuses/voice", { audio_url, account_ids, participants }).then((r) => r.data),
  incoming: (accountId) =>
    http.get("/statuses/incoming", { params: accountId ? { account_id: accountId } : {} }).then((r) => r.data),
  history: (accountId) => http.get(`/statuses/history/${accountId}`).then((r) => r.data),
  scheduled: (accountId) => http.get(`/statuses/scheduled/${accountId}`).then((r) => r.data),
  stats: (messageId) =>
    http.get(`/statuses/${messageId}/stats`).then((r) => r.data),
  // V40 — story product analysis
  analyzeStory: (rowId) => http.post(`/statuses/${rowId}/analyze`).then((r) => r.data),
  analyzeToday: (accountId) =>
    http.post("/statuses/analyze-today", null, { params: accountId ? { account_id: accountId } : {} }).then((r) => r.data),
  analysisList: (accountId) =>
    http.get("/statuses/analysis", { params: accountId ? { account_id: accountId } : {} }).then((r) => r.data),
  mediaUrl: (storyId) => `${http.defaults.baseURL}/statuses/media/${storyId}`,
};

// ── Own-number exclusions (V45 PART 1) ─────────────────────
export const OwnNumbersApi = {
  list: () => http.get("/own-numbers/").then((r) => r.data),
  add: (phone, label) => http.post("/own-numbers/", { phone, label }).then((r) => r.data),
  remove: (id) => http.delete(`/own-numbers/${id}`).then((r) => r.data),
  reseed: () => http.post("/own-numbers/reseed").then((r) => r.data),
};

// ── Active WhatsApp contacts lead list (V45 PART 3) ────────
export const ActiveContactsApi = {
  list: (params = {}) => http.get("/active-contacts/", { params }).then((r) => r.data),
  exportUrl: () => `${http.defaults.baseURL}/active-contacts/export`,
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
  addToPhonebook: (id) => http.post(`/contacts/${id}/add-to-phonebook`, null, { timeout: 65000 }).then((r) => r.data),
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
  availableGroups: (accountId) => http.get(`/wa-collections/available-groups/${accountId}`).then((r) => r.data),
  importAllMembers: (id) =>
    http.post(`/wa-collections/${id}/import-all-members`, null, { timeout: 300000 }).then((r) => r.data),
};

// ── Hour-schedule presets ──────────────────────────────────
export const PresetsApi = {
  list: () => http.get("/account-schedules/presets").then((r) => r.data),
  applyToSlot: (slotId, presetKey) =>
    http.post(`/account-schedules/${slotId}/apply-preset?preset_key=${presetKey}`).then((r) => r.data),
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
  topProducts: (limit = 150, days = 30, source = "", search = "") =>
    http.get(`/reporting/top-products?limit=${limit}&days=${days}${source ? `&source=${source}` : ""}${search ? `&search=${encodeURIComponent(search)}` : ""}`).then((r) => r.data),
  contactTrend: (phone, days = 90) =>
    http.get(`/reporting/contact-trend?phone=${encodeURIComponent(phone)}&days=${days}`).then((r) => r.data),
  bestHours: (days = 30) => http.get(`/reporting/best-hours?days=${days}`).then((r) => r.data),
  spotAlerts: (unreadOnly = false) =>
    http.get(`/reporting/spot-alerts?unread_only=${unreadOnly}`).then((r) => r.data),
  markSpotAlertRead: (id) => http.post(`/reporting/spot-alerts/${id}/read`).then((r) => r.data),
  productSellers: (productName, days = 30, limit = 100) =>
    http
      .get("/reporting/product-sellers", { params: { product_name: productName, days, limit } })
      .then((r) => r.data),
};

// ── Per-account status scheduler (V11.4) ──────────────────
export const StatusScheduleApi = {
  list: (accountId) =>
    http.get("/status-schedules/", { params: accountId ? { account_id: accountId } : {} }).then((r) => r.data),
  create: (body) => http.post("/status-schedules/", body).then((r) => r.data),
  update: (id, body) => http.put(`/status-schedules/${id}`, body).then((r) => r.data),
  delete: (id) => http.delete(`/status-schedules/${id}`).then((r) => r.data),
  toggle: (id) => http.post(`/status-schedules/${id}/toggle`).then((r) => r.data),
};

// ── Group/community/broadcast join links (V11.3) ───────────
export const JoinLinksApi = {
  list: () => http.get("/join-links/").then((r) => r.data),
  add: (name, link, type) =>
    http.post(`/join-links/?name=${encodeURIComponent(name)}&invite_link=${encodeURIComponent(link)}&link_type=${type}`).then((r) => r.data),
  bulk: (links) => http.post("/join-links/bulk", links).then((r) => r.data),
  delete: (id) => http.delete(`/join-links/${id}`).then((r) => r.data),
  joinAll: (accountId) => http.post(`/join-links/join-all/${accountId}`).then((r) => r.data),
  status: () => http.get("/join-links/status").then((r) => r.data),
};

// ── AI Key Pool (V12) ──────────────────────────────────────
export const AIKeysApi = {
  list: () => http.get("/ai-keys/").then((r) => r.data),
  create: (body) => http.post("/ai-keys/", body).then((r) => r.data),
  bulk: (keys) => http.post("/ai-keys/bulk", keys).then((r) => r.data),
  update: (id, body) => http.put(`/ai-keys/${id}`, body).then((r) => r.data),
  delete: (id) => http.delete(`/ai-keys/${id}`).then((r) => r.data),
  // per-key/test-all can be slow (live provider calls) — allow more time
  test: (id) => http.post(`/ai-keys/${id}/test`, null, { timeout: 45000 }).then((r) => r.data),
  testAll: () => http.post("/ai-keys/test-all", null, { timeout: 180000 }).then((r) => r.data),
  poolStatus: () => http.get("/ai-keys/pool-status").then((r) => r.data),
};

// ── Products & Labels ──────────────────────────────────────
export const ProductsApi = {
  list: () => http.get("/reporting/products").then((r) => r.data),
  supabaseStatus: () => http.get("/reporting/supabase-status").then((r) => r.data),
  table: (params = {}) => http.get("/reporting/products-table", { params }).then((r) => r.data),
};
export const LabelsApi = {
  list: () => http.get("/reporting/product-labels").then((r) => r.data),
};

// ── Green API Partner (V14 PART A) ─────────────────────────
export const PartnerApi = {
  status: () => http.get("/partner/status").then((r) => r.data),
  instances: () => http.get("/partner/instances").then((r) => r.data),
  create: (name, delay_ms = 15000) =>
    http.post("/partner/instances", { name, delay_ms }, { timeout: 60000 }).then((r) => r.data),
  remove: (idInstance) => http.delete(`/partner/instances/${idInstance}`).then((r) => r.data),
  sync: () => http.post("/partner/sync", null, { timeout: 60000 }).then((r) => r.data),
  qr: (accountId) => http.get(`/partner/instances/${accountId}/qr`).then((r) => r.data),
  state: (accountId) => http.get(`/partner/instances/${accountId}/state`).then((r) => r.data),
  authCode: (accountId, phone) =>
    http.post(`/partner/instances/${accountId}/auth-code`, { phone }, { timeout: 30000 }).then((r) => r.data),
  capabilities: () => http.get("/partner/capabilities").then((r) => r.data),
};

// ── Messaging (V14 PART B) ─────────────────────────────────
export const MessagesApi = {
  sendContact: (body) => http.post("/messages/contact", body).then((r) => r.data),
  sendLocation: (body) => http.post("/messages/location", body).then((r) => r.data),
  forward: (body) => http.post("/messages/forward", body).then((r) => r.data),
  validateButtons: (buttons) => http.post("/messages/validate-buttons", { buttons }).then((r) => r.data),
  // saved contact cards
  savedContacts: () => http.get("/messages/saved-contacts").then((r) => r.data),
  createSavedContact: (body) => http.post("/messages/saved-contacts", body).then((r) => r.data),
  deleteSavedContact: (id) => http.delete(`/messages/saved-contacts/${id}`).then((r) => r.data),
  // saved locations
  savedLocations: () => http.get("/messages/saved-locations").then((r) => r.data),
  createSavedLocation: (body) => http.post("/messages/saved-locations", body).then((r) => r.data),
  deleteSavedLocation: (id) => http.delete(`/messages/saved-locations/${id}`).then((r) => r.data),
  // button auto-replies
  autoReplies: () => http.get("/messages/button-auto-replies").then((r) => r.data),
  createAutoReply: (body) => http.post("/messages/button-auto-replies", body).then((r) => r.data),
  updateAutoReply: (id, body) => http.put(`/messages/button-auto-replies/${id}`, body).then((r) => r.data),
  deleteAutoReply: (id) => http.delete(`/messages/button-auto-replies/${id}`).then((r) => r.data),
  // stats
  campaignButtonReplies: (id) => http.get(`/messages/campaign/${id}/button-replies`).then((r) => r.data),
  reactions: (chatId) => http.get("/messages/reactions", { params: chatId ? { chat_id: chatId } : {} }).then((r) => r.data),
  // V14 PART C — message control
  edit: (body) => http.post("/messages/edit", body).then((r) => r.data),
  del: (body) => http.post("/messages/delete", body).then((r) => r.data),
  read: (body) => http.post("/messages/read", body).then((r) => r.data),
  readAll: (body) => http.post("/messages/read-all", body).then((r) => r.data),
  // V14 PART D — chat control
  archive: (body) => http.post("/messages/archive", body).then((r) => r.data),
  disappearing: (body) => http.post("/messages/disappearing", body).then((r) => r.data),
};

// ── Capability registry (V14 PART G) ───────────────────────
export const CapabilitiesApi = {
  get: () => http.get("/capabilities/").then((r) => r.data),
};

// ── Safety incidents + protection (V14 F23) ────────────────
export const IncidentsApi = {
  list: (unresolved = false) => http.get("/incidents/", { params: unresolved ? { unresolved: true } : {} }).then((r) => r.data),
  protection: () => http.get("/incidents/protection").then((r) => r.data),
  resolve: (id) => http.post(`/incidents/${id}/resolve`).then((r) => r.data),
  reboot: (accountId) => http.post(`/incidents/account/${accountId}/reboot`).then((r) => r.data),
  resume: (accountId) => http.post(`/incidents/account/${accountId}/resume`).then((r) => r.data),
  reconnect: (accountId) => http.post(`/incidents/account/${accountId}/reconnect`).then((r) => r.data),
};

// ── Call logs (V14 F24) ────────────────────────────────────
export const CallsApi = {
  list: (params = {}) => http.get("/calls/", { params }).then((r) => r.data),
  missedToday: () => http.get("/calls/missed-today").then((r) => r.data),
};

// ── Send queue (V14 F20) ───────────────────────────────────
export const QueueApi = {
  summary: () => http.get("/queue/summary").then((r) => r.data),
  get: (accountId) => http.get(`/queue/${accountId}`).then((r) => r.data),
  clear: (accountId) => http.delete(`/queue/${accountId}`).then((r) => r.data),
};

// ── Warm-up (V16 PART 5) ───────────────────────────────────
export const WarmupApi = {
  dashboard: () => http.get("/warmup/dashboard").then((r) => r.data),
  startAll: () => http.post("/warmup/start-all").then((r) => r.data),
  stopAll: () => http.post("/warmup/stop-all").then((r) => r.data),
  phrases: () => http.get("/warmup/phrases").then((r) => r.data),
  createPhrase: (body) => http.post("/warmup/phrases", body).then((r) => r.data),
  updatePhrase: (id, body) => http.put(`/warmup/phrases/${id}`, body).then((r) => r.data),
  deletePhrase: (id) => http.delete(`/warmup/phrases/${id}`).then((r) => r.data),
  // V17 — mesh warm-up dashboard + controls
  meshDashboard: () => http.get("/warmup/mesh-dashboard").then((r) => r.data),
  enroll: (accountId) => http.post(`/warmup/enroll/${accountId}`, null, { timeout: 60000 }).then((r) => r.data),
  disable: (accountId) => http.post(`/warmup/disable/${accountId}`).then((r) => r.data),
  pause: (accountId) => http.post(`/warmup/pause/${accountId}`).then((r) => r.data),
  resume: (accountId) => http.post(`/warmup/resume/${accountId}`).then((r) => r.data),
  restart: (accountId) => http.post(`/warmup/restart/${accountId}`).then((r) => r.data),
  events: (accountId) => http.get(`/warmup/events/${accountId}`).then((r) => r.data),
  // V23 — actual warm-up message texts sent across the mesh (from warmup_event_log)
  messages: (limit = 30) => http.get("/warmup/messages", { params: { limit } }).then((r) => r.data),
  setWarmPeer: (accountId, is_warm_peer) => http.post(`/warmup/warm-peer/${accountId}`, { is_warm_peer }).then((r) => r.data),
  meshStartAll: () => http.post("/warmup/mesh-start-all", null, { timeout: 120000 }).then((r) => r.data),
  meshStopAll: () => http.post("/warmup/mesh-stop-all").then((r) => r.data),
  breaker: () => http.get("/warmup/breaker").then((r) => r.data),
  resetBreaker: () => http.post("/warmup/breaker/reset").then((r) => r.data),
  // V19 — group-based warm-up (admin groups) + manual link vault
  warmAccounts: () => http.get("/warmup/warm-accounts").then((r) => r.data),
  adminGroups: (accountId, refresh = false) =>
    http.get(`/warmup/admin-groups/${accountId}`, { params: refresh ? { refresh: true } : {}, timeout: 60000 }).then((r) => r.data),
  groupTargets: (accountId) => http.get(`/warmup/group-targets/${accountId}`).then((r) => r.data),
  setGroupTarget: (accountId, body) => http.post(`/warmup/group-targets/${accountId}`, body).then((r) => r.data),
  linkVault: () => http.get("/warmup/link-vault").then((r) => r.data),
  addLink: (body) => http.post("/warmup/link-vault", body).then((r) => r.data),
  updateLink: (id, body) => http.put(`/warmup/link-vault/${id}`, body).then((r) => r.data),
  deleteLink: (id) => http.delete(`/warmup/link-vault/${id}`).then((r) => r.data),
};

// ── Warm-up "human helpers" assist (V25 PART 1) ────────────
export const WarmupHelpersApi = {
  list: (senderInstanceId) =>
    http.get("/warmup-helpers/", { params: senderInstanceId ? { sender_instance_id: senderInstanceId } : {} }).then((r) => r.data),
  create: (body) => http.post("/warmup-helpers/", body).then((r) => r.data),
  update: (id, body) => http.put(`/warmup-helpers/${id}`, body).then((r) => r.data),
  remove: (id) => http.delete(`/warmup-helpers/${id}`).then((r) => r.data),
  toggle: (enabled) => http.post("/warmup-helpers/toggle", { enabled }).then((r) => r.data),
  tasks: (coldInstanceId) =>
    http.get("/warmup-helpers/tasks", { params: coldInstanceId ? { cold_instance_id: coldInstanceId } : {} }).then((r) => r.data),
  // V28/V29 «همکاری تیمی»
  senders: () => http.get("/warmup-helpers/senders").then((r) => r.data),
  dashboard: () => http.get("/warmup-helpers/dashboard").then((r) => r.data),
  senderToggle: (senderInstanceId, enabled) =>
    http.post("/warmup-helpers/sender-toggle", { sender_instance_id: senderInstanceId, enabled }).then((r) => r.data),
  senderConfig: (senderInstanceId) =>
    http.get("/warmup-helpers/sender-config", { params: { sender_instance_id: senderInstanceId } }).then((r) => r.data),
  coldAccounts: (helperId) => http.get(`/warmup-helpers/${helperId}/cold-accounts`).then((r) => r.data),
  assignCold: (helperId, coldInstanceId) =>
    http.post(`/warmup-helpers/${helperId}/cold-accounts`, { cold_instance_id: coldInstanceId }).then((r) => r.data),
  unassignCold: (helperId, coldInstanceId) =>
    http.delete(`/warmup-helpers/${helperId}/cold-accounts/${coldInstanceId}`).then((r) => r.data),
  setCurrentBrief: (senderInstanceId, briefText) =>
    http.post("/warmup-helpers/current-brief", { sender_instance_id: senderInstanceId, brief_text: briefText }).then((r) => r.data),
  getCurrentBrief: (senderInstanceId) =>
    http.get("/warmup-helpers/current-brief", { params: { sender_instance_id: senderInstanceId } }).then((r) => r.data),
  // V39 PART 2/4 — is this account eligible to be a Team Collaboration sender right now?
  senderEligibility: (senderInstanceId) =>
    http.get("/warmup-helpers/sender-eligibility", { params: { sender_instance_id: senderInstanceId } }).then((r) => r.data),
  // V29 PART 8 warmth + PART 9 log
  warmth: () => http.get("/warmup-helpers/warmth").then((r) => r.data),
  log: (params) => http.get("/warmup-helpers/log", { params: params || {} }).then((r) => r.data),
  // V29 PART 7 cold-account team enrollment
  teamEnroll: (coldInstanceId, enabled) =>
    http.post("/warmup-helpers/team-enroll", { cold_instance_id: coldInstanceId, enabled }).then((r) => r.data),
  teamEnrollments: () => http.get("/warmup-helpers/team-enrollments").then((r) => r.data),
  // V29 PART 10 team dashboard + PART 4 alerts + PART 3 thread preview
  teamDashboard: () => http.get("/warmup-helpers/team-dashboard").then((r) => r.data),
  threadAlerts: () => http.get("/warmup-helpers/thread-alerts").then((r) => r.data),
  ackThreadAlert: (id) => http.post(`/warmup-helpers/thread-alerts/${id}/ack`).then((r) => r.data),
  resumeThreadAlert: (id) => http.post(`/warmup-helpers/thread-alerts/${id}/resume`).then((r) => r.data),
  teamLog: (params) => http.get("/warmup-helpers/log", { params: params || {} }).then((r) => r.data),
  generateThreadPreview: (senderInstanceId, coldInstanceId) =>
    http.post("/warmup-helpers/generate-thread-preview", { sender_instance_id: senderInstanceId, cold_instance_id: coldInstanceId }).then((r) => r.data),
};

// ── Onboarding wizard «راه‌اندازی» (V35 PART 4) ────────────
export const OnboardingApi = {
  list: () => http.get("/onboarding").then((r) => r.data),
  get: (id) => http.get(`/onboarding/${id}`).then((r) => r.data),
  create: (body) => http.post("/onboarding", body).then((r) => r.data),
  confirmWhatsapp: (id) => http.post(`/onboarding/${id}/confirm-whatsapp`).then((r) => r.data),
  confirmGreenApi: (id) => http.post(`/onboarding/${id}/confirm-green-api`).then((r) => r.data),
  remove: (id) => http.delete(`/onboarding/${id}`).then((r) => r.data),
};

// ── Advertising links (V16 PART 3) ─────────────────────────
export const AdLinksApi = {
  list: () => http.get("/advertising-links/").then((r) => r.data),
  create: (body) => http.post("/advertising-links/", body).then((r) => r.data),
  update: (id, body) => http.put(`/advertising-links/${id}`, body).then((r) => r.data),
  toggle: (id) => http.post(`/advertising-links/${id}/toggle`).then((r) => r.data),
  remove: (id) => http.delete(`/advertising-links/${id}`).then((r) => r.data),
};

// ── Blacklist ──────────────────────────────────────────
export const BlacklistApi = {
  list: () => http.get("/blacklist/").then((r) => r.data),
  add: (phone, reason) =>
    http.post("/blacklist/", null, { params: { phone, reason } }).then((r) => r.data),
  remove: (phone) => http.delete(`/blacklist/${phone}`).then((r) => r.data),
  optOutLog: () => http.get("/blacklist/opt-out-log").then((r) => r.data),
};

// ── Group monitoring / listener + voice (V26) ──────────────
export const GroupMonitorApi = {
  setListener: (accountId, is_listener) =>
    http.post(`/group-monitor/listener/${accountId}`, { is_listener }).then((r) => r.data),
  listeners: () => http.get("/group-monitor/listeners").then((r) => r.data),
  availableGroups: (accountId) =>
    http.get(`/group-monitor/available-groups/${accountId}`).then((r) => r.data),
  monitored: (listenerInstanceId) =>
    http.get("/group-monitor/monitored", { params: listenerInstanceId ? { listener_instance_id: listenerInstanceId } : {} }).then((r) => r.data),
  upsertMonitored: (body) => http.post("/group-monitor/monitored", body).then((r) => r.data),
  patchMonitored: (id, body) => http.patch(`/group-monitor/monitored/${id}`, body).then((r) => r.data),
  removeMonitored: (id) => http.delete(`/group-monitor/monitored/${id}`).then((r) => r.data),
  keywords: () => http.get("/group-monitor/keywords").then((r) => r.data),
  createKeyword: (body) => http.post("/group-monitor/keywords", body).then((r) => r.data),
  updateKeyword: (id, body) => http.put(`/group-monitor/keywords/${id}`, body).then((r) => r.data),
  removeKeyword: (id) => http.delete(`/group-monitor/keywords/${id}`).then((r) => r.data),
  replies: () => http.get("/group-monitor/replies").then((r) => r.data),
  createReply: (body) => http.post("/group-monitor/replies", body).then((r) => r.data),
  updateReply: (id, body) => http.put(`/group-monitor/replies/${id}`, body).then((r) => r.data),
  removeReply: (id) => http.delete(`/group-monitor/replies/${id}`).then((r) => r.data),
  messages: (params) => http.get("/group-monitor/messages", { params }).then((r) => r.data),
  alerts: (onlyUnread) =>
    http.get("/group-monitor/alerts", { params: onlyUnread ? { only_unread: true } : {} }).then((r) => r.data),
  markAlertRead: (id) => http.post(`/group-monitor/alerts/${id}/read`).then((r) => r.data),
};

// ── Telegram (TG PART 2) ───────────────────────────────────
export const TelegramApi = {
  create: (body) => http.post("/telegram/accounts", body).then((r) => r.data),
  qrNotice: () => http.get("/telegram/qr-notice").then((r) => r.data),
  qr: (id) => http.get(`/telegram/accounts/${id}/qr`).then((r) => r.data),
  authStart: (id, phone) => http.post(`/telegram/accounts/${id}/auth/start`, { phone }).then((r) => r.data),
  authCode: (id, code) => http.post(`/telegram/accounts/${id}/auth/code`, { code }).then((r) => r.data),
  authPassword: (id, password) => http.post(`/telegram/accounts/${id}/auth/password`, { password }).then((r) => r.data),
  state: (id) => http.get(`/telegram/accounts/${id}/state`).then((r) => r.data),
  sendTest: (id, chat_id) => http.post(`/telegram/accounts/${id}/send-test`, { chat_id }).then((r) => r.data),
};

# CLAUDE CODE PATCH — Groups Page Fix (Features 33-34)
# Add to V7 execution or run standalone
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp

## EXECUTION CONTRACT
Run every phase. No confirmation. Fix errors. Rebuild and push at end.

---

## CONTEXT

Current problems:
1. Member count shows blank in Groups page — not being fetched/stored
2. No filtering by type (group vs broadcast list vs community)
3. Groups page only shows @g.us groups, not broadcast lists

Green API chat types:
- @g.us → regular group (full send capability)
- @broadcast → broadcast list (send as individual DMs to members)
- @newsletter → WhatsApp Channel (NOT supported — owner only, skip)
- @c.us → private chat (skip)

---

## PHASE 1 — Backend: Fix group sync to include member count and type

In `backend/app/models/group.py`, add columns to WhatsAppGroup:

```python
    chat_type: Mapped[str] = mapped_column(String(20), default="group")  # group | broadcast | community
    description: Mapped[str | None] = mapped_column(Text)
```

Add to DDL in main.py:
```python
"ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS chat_type varchar(20) DEFAULT 'group'",
"ALTER TABLE whatsapp_groups ADD COLUMN IF NOT EXISTS description text",
```

In `backend/app/api/v1/groups.py`, fix the sync endpoint to:
1. Detect chat type from chatId suffix
2. Fetch member count from getGroupData (for @g.us groups)
3. Store both

```python
@router.post("/sync/{account_id}")
async def sync_groups_from_wa(account_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch all WhatsApp groups/broadcasts and save to DB with member counts."""
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    chats = await client.get_chats()
    
    saved = 0
    updated = 0
    
    for chat in chats:
        chat_id = chat.get("id", "")
        
        # Determine type
        if "@g.us" in chat_id:
            chat_type = "group"
        elif "@broadcast" in chat_id:
            chat_type = "broadcast"
        elif "@newsletter" in chat_id:
            continue  # Skip WhatsApp Channels — can't post
        else:
            continue  # Skip private chats
        
        name = chat.get("name", "") or chat_id
        member_count = chat.get("participantsCount", 0) or 0
        
        # For groups, try to get accurate member count from getGroupData
        if chat_type == "group" and member_count == 0:
            try:
                group_data = await client.get_group_data(chat_id)
                participants = group_data.get("participants", [])
                member_count = len(participants)
                description = group_data.get("description", "")
            except Exception:
                description = ""
        else:
            description = ""
        
        # Upsert
        existing_result = await db.execute(
            select(WhatsAppGroup).where(WhatsAppGroup.green_group_id == chat_id)
        )
        existing = existing_result.scalar_one_or_none()
        
        if existing:
            existing.name = name
            existing.member_count = member_count
            existing.chat_type = chat_type
            existing.description = description
            existing.account_id = uuid.UUID(account_id)
            updated += 1
        else:
            grp = WhatsAppGroup(
                green_group_id=chat_id,
                account_id=uuid.UUID(account_id),
                name=name,
                member_count=member_count,
                chat_type=chat_type,
                description=description
            )
            db.add(grp)
            saved += 1
    
    await db.commit()
    return {"synced_new": saved, "updated": updated, "total_chats": len(chats)}
```

Also fix `GET /groups/` endpoint to return chat_type and member_count:
```python
@router.get("/")
async def list_groups(
    account_id: str | None = None,
    chat_type: str | None = None,  # filter: group | broadcast | all
    min_members: int | None = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(WhatsAppGroup).order_by(WhatsAppGroup.member_count.desc())
    if account_id:
        query = query.where(WhatsAppGroup.account_id == uuid.UUID(account_id))
    if chat_type and chat_type != "all":
        query = query.where(WhatsAppGroup.chat_type == chat_type)
    if min_members is not None:
        query = query.where(WhatsAppGroup.member_count >= min_members)
    
    result = await db.execute(query)
    groups = result.scalars().all()
    return [
        {
            "id": str(g.id),
            "group_chat_id": g.green_group_id,
            "name": g.name,
            "member_count": g.member_count,
            "chat_type": g.chat_type,
            "description": g.description,
            "account_id": str(g.account_id)
        }
        for g in groups
    ]
```

Add new endpoint to refresh member count for a single group:
```python
@router.post("/{group_id}/refresh-members")
async def refresh_group_members(group_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch fresh member count for one group from Green API."""
    grp = await db.get(WhatsAppGroup, uuid.UUID(group_id))
    if not grp:
        raise HTTPException(404, "Group not found")
    
    account = await db.get(Account, grp.account_id)
    if not account:
        raise HTTPException(400, "Account not found")
    
    client = GreenAPIClient(account.instance_id, account.api_token)
    try:
        group_data = await client.get_group_data(grp.green_group_id)
        participants = group_data.get("participants", [])
        grp.member_count = len(participants)
        grp.description = group_data.get("description", grp.description)
        await db.commit()
        return {"member_count": grp.member_count, "name": grp.name}
    except Exception as e:
        raise HTTPException(500, f"Green API error: {e}")
```

---

## PHASE 2 — Frontend: Fix Groups.jsx

Rewrite the Groups page with full feature set:

```jsx
// Groups.jsx — complete rewrite with filters and member count

import { useState, useEffect } from "react";

const CHAT_TYPE_LABELS = {
  group: { label: "گروه معمولی", icon: "👥", color: "text-green-400" },
  broadcast: { label: "لیست انتشار", icon: "📢", color: "text-blue-400" },
};

const MEMBER_FILTERS = [
  { label: "همه", min: 0 },
  { label: "+۱۰ نفر", min: 10 },
  { label: "+۵۰ نفر", min: 50 },
  { label: "+۱۰۰ نفر", min: 100 },
  { label: "+۵۰۰ نفر", min: 500 },
];

export default function Groups() {
  const [groups, setGroups] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");  // all | group | broadcast
  const [minMembers, setMinMembers] = useState(0);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [syncing, setSyncing] = useState(false);

  // Load accounts and groups on mount
  useEffect(() => {
    loadAccounts();
    loadGroups();
  }, []);

  const loadAccounts = async () => {
    const res = await http.get("/accounts/");
    setAccounts(res.data);
    const active = res.data.find(a => a.status === "active");
    if (active) setSelectedAccount(active.id);
  };

  const loadGroups = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (typeFilter !== "all") params.append("chat_type", typeFilter);
      if (minMembers > 0) params.append("min_members", minMembers);
      const res = await http.get(`/groups/?${params}`);
      setGroups(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadGroups(); }, [typeFilter, minMembers]);

  const syncGroups = async () => {
    if (!selectedAccount) return;
    setSyncing(true);
    try {
      const res = await http.post(`/groups/sync/${selectedAccount}`);
      alert(`${res.data.synced_new} گروه جدید + ${res.data.updated} آپدیت شد`);
      await loadGroups();
    } finally {
      setSyncing(false);
    }
  };

  const refreshMembers = async (groupId) => {
    await http.post(`/groups/${groupId}/refresh-members`);
    await loadGroups();
  };

  // Filter by search
  const filtered = groups.filter(g =>
    g.name?.includes(search) ||
    g.group_chat_id?.includes(search)
  );

  return (
    <div className="p-6 rtl">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">گروه‌های واتساپ</h1>
        <div className="flex gap-2">
          <select value={selectedAccount} onChange={e => setSelectedAccount(e.target.value)}
                  className="select-dark text-sm">
            {accounts.filter(a => a.status === "active").map(a => (
              <option key={a.id} value={a.id}>{a.name} ({a.phone})</option>
            ))}
          </select>
          <button onClick={syncGroups} disabled={syncing}
                  className="btn-green">
            {syncing ? "در حال همگام‌سازی..." : "🔄 همگام‌سازی با واتساپ"}
          </button>
        </div>
      </div>

      {/* Info banner */}
      <div className="bg-blue-900/30 border border-blue-700 rounded-lg p-3 mb-4 text-sm text-blue-300">
        💡 برای نمایش گروه‌ها ابتدا "همگام‌سازی با واتساپ" را بزنید.
        گروه‌های معمولی و لیست‌های انتشاری که عضو آن‌ها هستید نمایش داده می‌شوند.
        کانال‌های واتساپ (@newsletter) پشتیبانی نمی‌شوند.
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap gap-3 mb-4">
        {/* Search */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="جستجو بر اساس نام گروه یا شناسه..."
          className="input-dark flex-1 min-w-48"
        />
        
        {/* Type filter */}
        <div className="flex gap-1 bg-gray-800 rounded-lg p-1">
          {[
            { key: "all", label: "همه" },
            { key: "group", label: "👥 گروه" },
            { key: "broadcast", label: "📢 انتشار" },
          ].map(t => (
            <button key={t.key}
              onClick={() => setTypeFilter(t.key)}
              className={`px-3 py-1 rounded text-sm ${typeFilter === t.key ? "bg-green-600 text-white" : "text-gray-400"}`}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Member count filter */}
        <select value={minMembers} onChange={e => setMinMembers(Number(e.target.value))}
                className="select-dark text-sm">
          {MEMBER_FILTERS.map(f => (
            <option key={f.min} value={f.min}>{f.label}</option>
          ))}
        </select>
      </div>

      {/* Stats */}
      <div className="text-sm text-gray-400 mb-3">
        {filtered.length} گروه نمایش داده می‌شود
        {groups.length !== filtered.length && ` (از ${groups.length} کل)`}
      </div>

      {/* Groups list */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">در حال بارگذاری...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          {groups.length === 0
            ? "گروهی پیدا نشد — ابتدا همگام‌سازی کنید"
            : "گروهی با این فیلترها پیدا نشد"}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(group => {
            const typeInfo = CHAT_TYPE_LABELS[group.chat_type] || CHAT_TYPE_LABELS.group;
            return (
              <div key={group.id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                {/* Header */}
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-semibold text-white text-sm leading-tight">
                    {group.name}
                  </h3>
                  <span className={`text-xs ${typeInfo.color} whitespace-nowrap`}>
                    {typeInfo.icon} {typeInfo.label}
                  </span>
                </div>

                {/* Member count — PROMINENT */}
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-2xl font-bold text-green-400">
                    {group.member_count > 0 ? group.member_count.toLocaleString("fa-IR") : "—"}
                  </span>
                  <span className="text-gray-400 text-sm">عضو</span>
                  {group.member_count > 0 && (
                    <button onClick={() => refreshMembers(group.id)}
                            className="text-xs text-gray-500 hover:text-gray-300 mr-auto">
                      🔄
                    </button>
                  )}
                </div>

                {/* Description */}
                {group.description && (
                  <p className="text-gray-400 text-xs mb-2 line-clamp-2">{group.description}</p>
                )}

                {/* Chat ID */}
                <p className="text-gray-600 text-xs font-mono mb-3 truncate">
                  {group.group_chat_id}
                </p>

                {/* Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={() => sendToGroup(group.group_chat_id)}
                    className="btn-green-sm flex-1 text-xs">
                    ارسال پیام
                  </button>
                  <button
                    onClick={() => navigator.clipboard.writeText(group.group_chat_id)}
                    className="btn-outline-sm text-xs px-2"
                    title="کپی شناسه">
                    📋
                  </button>
                  {group.member_count === 0 && (
                    <button
                      onClick={() => refreshMembers(group.id)}
                      className="btn-outline-sm text-xs px-2"
                      title="دریافت تعداد اعضا">
                      👥
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

---

## PHASE 3 — Update api.js

```javascript
export const GroupsApi = {
  list: (params = {}) => {
    const q = new URLSearchParams(params).toString();
    return http.get(`/groups/?${q}`).then(r => r.data);
  },
  sync: (accountId) => http.post(`/groups/sync/${accountId}`).then(r => r.data),
  refreshMembers: (groupId) => http.post(`/groups/${groupId}/refresh-members`).then(r => r.data),
  send: (groupChatId, message, accountId) =>
    http.post(`/groups/${groupChatId}/send`, { message, account_id: accountId }).then(r => r.data),
  info: (groupId) => http.get(`/groups/${groupId}/info`).then(r => r.data),
};
```

---

## PHASE 4 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/api/v1/groups.py app/models/group.py
python -m pytest tests/ -v
cd ..
docker-compose up -d --build backend
sleep 6
curl -s http://localhost:8002/api/v1/groups/
curl -s "http://localhost:8002/api/v1/groups/?chat_type=group&min_members=10"
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
git add -A
git commit -m "fix: Groups page — member count, type filter, broadcast list support

- Sync now detects chat type (@g.us=group, @broadcast=broadcast, skip @newsletter)
- Sync calls getGroupData per group to get accurate member count
- New filter params on GET /groups/: chat_type, min_members
- POST /groups/{id}/refresh-members — fresh member count on demand
- Groups.jsx: member count shown prominently (large number)
- Filter bar: type (all/group/broadcast) + member count dropdown + search
- Info banner explaining channel limitation
- Refresh button per group card"
git push origin main
```
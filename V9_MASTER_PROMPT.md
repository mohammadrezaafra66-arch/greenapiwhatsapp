# CLAUDE CODE PROMPT — V9 Group Extraction & Contacts Scale-up
# Repo: https://github.com/mohammadrezaafra66-arch/greenapiwhatsapp
# Local: C:\Users\AFRA\Desktop\bots\claudegreenapi

## EXECUTION CONTRACT
Run every phase. No confirmation. Fix errors. Rebuild and push at end.

---

## CRITICAL: NO RESTRICTIONS ON EXTRACT-MEMBERS

The extract-members endpoint must work for ALL groups regardless of admin status.
Green API's getGroupData returns participants for any group you're a member of.
NEVER add is_admin gate to extract-members. Only import-excel-to-group (adding members) requires admin.

---

## PHASE 1 — Backend: Remove all limits from contacts

In `backend/app/api/v1/contacts.py`, update GET /contacts/ endpoint:

```python
@router.get("/")
async def list_contacts(
    search: str | None = None,
    has_whatsapp: bool | None = None,
    blacklisted: bool | None = None,
    skip: int = 0,
    limit: int = 1000,  # default 1000, no hard cap
    db: AsyncSession = Depends(get_db)
):
    query = select(Contact)
    if not blacklisted:
        query = query.where(Contact.blacklisted == False)
    if search:
        query = query.where(
            or_(
                Contact.phone.contains(search),
                Contact.first_name.ilike(f"%{search}%"),
                Contact.last_name.ilike(f"%{search}%")
            )
        )
    if has_whatsapp is not None:
        query = query.where(Contact.has_whatsapp == has_whatsapp)
    
    # Count total
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    
    # Apply pagination
    query = query.order_by(Contact.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    contacts = result.scalars().all()
    
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "contacts": [
            {
                "id": str(c.id),
                "phone": c.phone,
                "name": c.full_name,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "has_whatsapp": c.has_whatsapp,
                "province": c.province,
                "city": c.city,
                "source": c.source,
                "blacklisted": c.blacklisted,
                "created_at": str(c.created_at),
            }
            for c in contacts
        ]
    }
```

Also add GET /contacts/count endpoint:
```python
@router.get("/count")
async def count_contacts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(func.count()).where(Contact.blacklisted == False))
    return {"total": result.scalar()}
```

---

## PHASE 2 — Backend: Bulk extract all groups

In `backend/app/api/v1/groups.py`, add bulk extraction endpoint:

```python
@router.post("/extract-all-members")
async def extract_all_groups_members(
    account_id: str,
    min_members: int = 0,  # 0 = all groups
    db: AsyncSession = Depends(get_db)
):
    """
    Extract phone numbers from ALL groups for this account and import to contacts.
    No is_admin restriction — works for any group you're a member of.
    Runs as background task, returns task_id.
    """
    from app.workers.tasks import task_extract_all_groups
    
    account = await db.get(Account, uuid.UUID(account_id))
    if not account:
        raise HTTPException(404, "Account not found")
    
    # Get all groups for this account
    result = await db.execute(
        select(WhatsAppGroup)
        .where(WhatsAppGroup.account_id == uuid.UUID(account_id))
        .where(WhatsAppGroup.member_count >= min_members if min_members > 0 else True)
        .order_by(WhatsAppGroup.member_count.desc())
    )
    groups = result.scalars().all()
    
    group_data = [(str(g.id), g.green_group_id, g.name) for g in groups]
    
    # Launch background task
    task = task_extract_all_groups.delay(str(account.id), account.instance_id, account.api_token, group_data)
    
    return {
        "task_id": task.id,
        "groups_to_process": len(groups),
        "message": f"استخراج {len(groups)} گروه در پس‌زمینه شروع شد"
    }


@router.get("/extract-all-progress/{account_id}")
async def get_extract_progress(account_id: str, db: AsyncSession = Depends(get_db)):
    """Get progress of bulk extraction."""
    import redis
    r = redis.from_url(settings.redis_url)
    progress_key = f"extract_progress:{account_id}"
    data = r.hgetall(progress_key)
    if not data:
        return {"status": "idle", "processed": 0, "total": 0, "added": 0}
    return {
        "status": data.get(b"status", b"idle").decode(),
        "processed": int(data.get(b"processed", 0)),
        "total": int(data.get(b"total", 0)),
        "added": int(data.get(b"added", 0)),
        "skipped": int(data.get(b"skipped", 0)),
        "current_group": data.get(b"current_group", b"").decode(),
    }
```

---

## PHASE 3 — Celery task: bulk extraction

In `backend/app/workers/tasks.py`, add:

```python
@celery_app.task(name="tasks.extract_all_groups")
def task_extract_all_groups(account_id: str, instance_id: str, api_token: str, group_data: list):
    """
    Extract members from all groups and import to contacts.
    group_data: list of (group_db_id, green_group_id, group_name)
    No is_admin restriction.
    """
    import redis
    import asyncio
    from app.services.green_api import GreenAPIClient
    from app.database import AsyncSessionLocal
    from app.models.contact import Contact
    from sqlalchemy import select as sa_select

    r = redis.from_url(settings.redis_url)
    progress_key = f"extract_progress:{account_id}"
    
    # Initialize progress
    r.hset(progress_key, mapping={
        "status": "running",
        "processed": 0,
        "total": len(group_data),
        "added": 0,
        "skipped": 0,
        "current_group": ""
    })
    r.expire(progress_key, 3600)  # 1 hour TTL

    client = GreenAPIClient(instance_id, api_token)
    
    async def _run():
        total_added = 0
        total_skipped = 0
        
        for i, (group_db_id, green_group_id, group_name) in enumerate(group_data):
            r.hset(progress_key, mapping={
                "processed": i,
                "current_group": group_name[:50],
                "added": total_added,
                "skipped": total_skipped,
            })
            
            try:
                group_data_resp = await client.get_group_data(green_group_id)
                participants = group_data_resp.get("participants", [])
                
                async with AsyncSessionLocal() as db:
                    for p in participants:
                        raw_id = str(p.get("id", "")).split("@")[0]
                        phone = Contact.normalize_phone(raw_id)
                        if not phone:
                            total_skipped += 1
                            continue
                        
                        # Check if exists
                        existing = await db.execute(
                            sa_select(Contact).where(Contact.phone == phone)
                        )
                        if existing.scalar_one_or_none():
                            total_skipped += 1
                            continue
                        
                        # Add with source tag including group name
                        source_tag = f"group:{group_name[:50]}"
                        contact = Contact(
                            phone=phone,
                            source=source_tag,
                        )
                        db.add(contact)
                        total_added += 1
                    
                    await db.commit()
                
                # Rate limit: 1 second between groups
                await asyncio.sleep(1)
                
            except Exception as e:
                print(f"[BulkExtract] Group {group_name}: {e}")
                continue
        
        r.hset(progress_key, mapping={
            "status": "completed",
            "processed": len(group_data),
            "added": total_added,
            "skipped": total_skipped,
            "current_group": ""
        })
    
    asyncio.run(_run())
```

---

## PHASE 4 — DB: Add group source column to contacts

In main.py lifespan DDL:
```python
"ALTER TABLE contacts ADD COLUMN IF NOT EXISTS group_source varchar(500)",
```

Update Contact model in `backend/app/models/contact.py`:
```python
    group_source: Mapped[str | None] = mapped_column(String(500))
```

Update the bulk extraction task to save group_source separately from source.

---

## PHASE 5 — Frontend: Contacts.jsx complete rewrite for scale

Rewrite `frontend/src/pages/Contacts.jsx` to handle 50,000+ contacts:

Key changes:
1. **Virtual pagination** — load 1000 at a time via skip/limit
2. **Total count** shown prominently: "۱۲,۳۴۵ مخاطب کل"
3. **"بارگذاری ۱۰۰۰ بیشتر"** button at bottom
4. **Source column** in table — shows which group the contact came from
5. **Search** works on top 1000 loaded records + backend search
6. **No hard limit** — keep loading until all contacts shown

```jsx
export default function Contacts() {
  const [contacts, setContacts] = useState([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [search, setSearch] = useState("");
  const LIMIT = 1000;

  const loadContacts = async (reset = false) => {
    const newSkip = reset ? 0 : skip;
    if (reset) setLoading(true); else setLoadingMore(true);
    
    try {
      const params = { skip: newSkip, limit: LIMIT };
      if (search) params.search = search;
      const res = await http.get("/contacts/", { params });
      
      const data = res.data;
      setTotal(data.total);
      
      if (reset) {
        setContacts(data.contacts);
        setSkip(LIMIT);
      } else {
        setContacts(prev => [...prev, ...data.contacts]);
        setSkip(newSkip + LIMIT);
      }
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => { loadContacts(true); }, []);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => loadContacts(true), 400);
    return () => clearTimeout(t);
  }, [search]);

  const hasMore = contacts.length < total;

  return (
    <div className="p-6 rtl">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h1 className="text-2xl font-bold">مخاطبین</h1>
          <p className="text-sm text-gray-400 mt-1">
            {total.toLocaleString("fa-IR")} مخاطب کل
            {contacts.length < total && ` | ${contacts.length.toLocaleString("fa-IR")} بارگذاری شده`}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={checkWhatsapp} className="btn-outline text-sm">
            بررسی واتساپ ({selectedIds.length})
          </button>
          <button onClick={openImport} className="btn-outline text-sm">ورود از اکسل</button>
          <button onClick={openAdd} className="btn-green text-sm">افزودن دستی</button>
        </div>
      </div>

      {/* Search */}
      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="جستجو بر اساس نام یا شماره..."
        className="input-dark w-full mb-4"
      />

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">در حال بارگذاری...</div>
      ) : (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="py-2 w-8"><input type="checkbox" onChange={toggleAll} /></th>
                <th className="py-2 text-right">نام</th>
                <th className="py-2 text-right">شماره</th>
                <th className="py-2 text-right">استان</th>
                <th className="py-2 text-right">واتساپ</th>
                <th className="py-2 text-right">منبع</th>
                <th className="py-2 text-right">اکشن</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map(contact => (
                <tr key={contact.id} className="border-b border-gray-800 hover:bg-gray-800">
                  <td className="py-2">
                    <input type="checkbox"
                           checked={selectedIds.includes(contact.id)}
                           onChange={() => toggleSelect(contact.id)} />
                  </td>
                  <td className="py-2">{contact.name || "—"}</td>
                  <td className="py-2 font-mono text-sm" dir="ltr">{contact.phone}</td>
                  <td className="py-2 text-gray-400">{contact.province || "—"}</td>
                  <td className="py-2">
                    {contact.has_whatsapp === true ? "✅" :
                     contact.has_whatsapp === false ? "❌" : "⏳"}
                  </td>
                  <td className="py-2 text-gray-500 text-xs truncate max-w-24">
                    {contact.source || "—"}
                  </td>
                  <td className="py-2">
                    <button onClick={() => blacklist(contact.id)}
                            className="text-xs text-red-400 hover:text-red-300">
                      لیست سیاه
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Load more */}
          {hasMore && (
            <div className="text-center mt-6">
              <button onClick={() => loadContacts(false)}
                      disabled={loadingMore}
                      className="btn-outline px-8">
                {loadingMore
                  ? "در حال بارگذاری..."
                  : `بارگذاری ۱۰۰۰ مخاطب بعدی (${(total - contacts.length).toLocaleString("fa-IR")} باقی‌مانده)`}
              </button>
            </div>
          )}
          
          {!hasMore && contacts.length > 0 && (
            <p className="text-center text-gray-500 text-sm mt-4">
              همه {total.toLocaleString("fa-IR")} مخاطب بارگذاری شده
            </p>
          )}
        </>
      )}
    </div>
  );
}
```

---

## PHASE 6 — Frontend: Groups.jsx — add bulk extract button

In `frontend/src/pages/Groups.jsx`, add a prominent "استخراج اعضای کلیه گروه‌ها" button next to sync button:

```jsx
const [extracting, setExtracting] = useState(false);
const [extractProgress, setExtractProgress] = useState(null);

const extractAllGroups = async () => {
  if (!selectedAccount) return;
  setExtracting(true);
  
  try {
    const res = await http.post(`/groups/extract-all-members`, null, {
      params: { account_id: selectedAccount, min_members: 0 }
    });
    
    // Poll progress
    const interval = setInterval(async () => {
      const prog = await http.get(`/groups/extract-all-progress/${selectedAccount}`);
      setExtractProgress(prog.data);
      
      if (prog.data.status === "completed") {
        clearInterval(interval);
        setExtracting(false);
        alert(`استخراج تکمیل شد!\nاضافه شده: ${prog.data.added}\nتکراری: ${prog.data.skipped}`);
      }
    }, 3000);
    
  } catch (e) {
    setExtracting(false);
    alert("خطا در شروع استخراج");
  }
};

// In the header buttons row:
<button onClick={extractAllGroups} disabled={extracting}
        className="btn-amber text-sm">
  {extracting ? `⏳ استخراج... (${extractProgress?.processed}/${extractProgress?.total})` : "📥 استخراج اعضای کلیه گروه‌ها"}
</button>
```

Show live progress bar when extracting:
```jsx
{extractProgress && extractProgress.status === "running" && (
  <div className="bg-amber-900/20 border border-amber-700 rounded-lg p-3 mb-4">
    <div className="flex justify-between text-sm mb-1">
      <span>در حال استخراج: {extractProgress.current_group}</span>
      <span>{extractProgress.processed}/{extractProgress.total} گروه</span>
    </div>
    <div className="w-full bg-gray-700 rounded-full h-2">
      <div className="bg-amber-500 h-2 rounded-full transition-all"
           style={{width: `${(extractProgress.processed/extractProgress.total)*100}%`}} />
    </div>
    <p className="text-xs text-gray-400 mt-1">
      اضافه شده: {extractProgress.added} | تکراری: {extractProgress.skipped}
    </p>
  </div>
)}
```

---

## PHASE 7 — api.js updates

```javascript
export const ContactsApi = {
  list: (params = {}) => http.get("/contacts/", { params }).then(r => r.data),
  count: () => http.get("/contacts/count").then(r => r.data),
  create: (body) => http.post("/contacts/", body).then(r => r.data),
  delete: (id) => http.delete(`/contacts/${id}`).then(r => r.data),
  blacklist: (id) => http.post(`/contacts/${id}/blacklist`).then(r => r.data),
  checkWhatsapp: (ids) => http.post("/contacts/check-bulk", { contact_ids: ids }).then(r => r.data),
  importExcel: (formData) => http.post("/contacts/import", formData, {headers: {'Content-Type': 'multipart/form-data'}}).then(r => r.data),
};

export const GroupExtractApi = {
  extractOne: (groupId) => http.post(`/groups/${groupId}/extract-members`).then(r => r.data),
  importToContacts: (groupId, phones) => http.post(`/groups/${groupId}/import-members-to-contacts`, { phones }).then(r => r.data),
  extractAll: (accountId, minMembers = 0) => http.post(`/groups/extract-all-members`, null, { params: { account_id: accountId, min_members: minMembers } }).then(r => r.data),
  progress: (accountId) => http.get(`/groups/extract-all-progress/${accountId}`).then(r => r.data),
};
```

---

## PHASE 8 — Verify, rebuild, push

```bash
cd C:/Users/AFRA/Desktop/bots/claudegreenapi/backend
python -m py_compile app/main.py app/models/*.py app/api/v1/*.py app/workers/tasks.py
python -m pytest tests/ -v
cd ..
docker-compose up -d --build backend worker beat
sleep 8
curl -s "http://localhost:8002/api/v1/contacts/?limit=5" | python -m json.tool | head -20
curl -s "http://localhost:8002/api/v1/contacts/count"
cd frontend && npm run build && cd ..
docker-compose up -d --build --no-deps frontend
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:3002/
```

```bash
git add -A
git commit -m "feat: V9 — mass group extraction + contacts scale-up

- Contacts API: no hard limit, skip/limit pagination, total count in response
- GET /contacts/count: total contact count
- POST /groups/extract-all-members: bulk extract ALL groups (no is_admin restriction)
- GET /groups/extract-all-progress/{account_id}: live progress via Redis
- Celery task task_extract_all_groups: extracts all groups with 1s rate limit, tracks progress
- contacts.group_source column: tracks which group each contact came from
- Contacts.jsx: virtual pagination, load 1000 at a time, total count displayed
- Groups.jsx: bulk extract button with live progress bar
- No restrictions: extract-members works for any group regardless of admin status"
git push origin main
```
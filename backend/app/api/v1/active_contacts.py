"""V45 PART 3 — read + export API for the «مخاطبین فعال واتساپ» harvested lead list."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.active_contact import ActiveWhatsappContact

router = APIRouter(prefix="/active-contacts", tags=["active-contacts"])

# Persian labels for the harvest source, shown in the UI/export.
SOURCE_LABELS = {
    "status": "استوری",
    "group": "گروه",
    "channel": "کانال",
    "broadcast": "لیست انتشار",
}


def _rows_query(search: str | None):
    q = select(ActiveWhatsappContact).order_by(ActiveWhatsappContact.last_seen_at.desc())
    if search:
        s = search.strip()
        if s:
            q = q.where(ActiveWhatsappContact.phone_display.contains(s)
                        | ActiveWhatsappContact.phone_core.contains(s)
                        | ActiveWhatsappContact.display_name.ilike(f"%{s}%"))
    return q


@router.get("/")
async def list_active_contacts(search: str | None = None, db: AsyncSession = Depends(get_db)):
    from app.utils.shamsi import to_shamsi
    rows = (await db.execute(_rows_query(search))).scalars().all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "phone": r.phone_display or r.phone_core,
                "name": r.display_name,
                "source": r.first_seen_source,
                "source_label": SOURCE_LABELS.get(r.first_seen_source, r.first_seen_source or "—"),
                "first_seen_shamsi": to_shamsi(r.first_seen_at),
                "last_seen_shamsi": to_shamsi(r.last_seen_at),
                "sighting_count": r.sighting_count,
            }
            for r in rows
        ],
    }


@router.get("/export")
async def export_active_contacts(search: str | None = None, db: AsyncSession = Depends(get_db)):
    """CSV export (UTF-8 BOM so Excel renders Persian) — same pattern as the contacts export."""
    import csv, io
    from fastapi.responses import Response
    from app.utils.shamsi import to_shamsi
    rows = (await db.execute(_rows_query(search))).scalars().all()
    buf = io.StringIO()
    buf.write("﻿")  # BOM
    w = csv.writer(buf)
    w.writerow(["row", "phone", "name", "source", "first_seen", "last_seen", "sighting_count"])
    for i, r in enumerate(rows, 1):
        w.writerow([
            i, r.phone_display or r.phone_core, r.display_name or "",
            SOURCE_LABELS.get(r.first_seen_source, r.first_seen_source or ""),
            to_shamsi(r.first_seen_at), to_shamsi(r.last_seen_at), r.sighting_count,
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=active_whatsapp_contacts.csv"},
    )

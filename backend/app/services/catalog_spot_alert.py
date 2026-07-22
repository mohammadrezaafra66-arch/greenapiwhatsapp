"""V40 PART 7 — raise an admin "catalog product spotted outside" alert (price-free, deduped).

Fires when an IN-ASSISTANT (catalog) product is seen being advertised by an OUTSIDE contact — i.e.
someone who is NOT one of our own accounts. Reuses the V26 admin-alert-row mechanism (a
CatalogSpotAlert row, never an auto-message). Deduped to one alert per (contact, product, day).

PRICE-FREE by design: there is no price data in this pass, so this is a sighting alert, not an
undercut alert. See models/catalog_alert.py for the future price-comparison upgrade note.
"""
from __future__ import annotations
import logging
from datetime import datetime

from sqlalchemy import select

from app.models.catalog_alert import CatalogSpotAlert
from app.services.product_reports import phone_core

logger = logging.getLogger("afrakala.catalog_spot_alert")


async def get_our_phone_cores(db) -> set[str]:
    """The national-core phones of OUR OWN accounts — used to exclude our own numbers so we never
    alert on our own warm/team accounts re-advertising a catalog product."""
    from app.models.account import Account
    phones = (await db.execute(select(Account.phone))).scalars().all()
    return {c for c in (phone_core(p or "") for p in phones) if c}


async def maybe_raise_spot_alert(db, *, contact_phone: str, contact_name: str | None,
                                 product_name: str | None, product_id: str | None, source: str,
                                 instance_id: str | None, message_text: str | None,
                                 our_cores: set[str], now: datetime | None = None) -> bool:
    """Raise ONE admin alert when a catalog product is advertised by an outside contact. Returns True
    if a new alert row was added. No-op (returns False) when: not a catalog product (no product_id),
    the advertiser is one of our own accounts, or an alert for this (contact, product, day) already
    exists. Does NOT commit — the caller owns the transaction."""
    if not product_id:                       # only CATALOG / in-assistant products
        return False
    core = phone_core(contact_phone or "")
    if not core or core in our_cores:        # skip our own accounts / unknown senders
        return False
    now = now or datetime.utcnow()
    today = now.date()
    existing = (await db.execute(
        select(CatalogSpotAlert.id).where(
            CatalogSpotAlert.contact_phone == core,
            CatalogSpotAlert.product_name == product_name,
            CatalogSpotAlert.alert_date == today,
        ).limit(1)
    )).first()
    if existing is not None:                 # already alerted for this contact+product today
        return False
    db.add(CatalogSpotAlert(
        contact_phone=core, contact_name=contact_name, product_name=product_name,
        product_id=product_id, source=source, instance_id=instance_id,
        message_text=(message_text or "")[:1000], alert_date=today, created_at=now,
    ))
    logger.info("catalog-spot alert: %s advertised catalog product '%s' via %s",
                core, product_name, source)
    return True

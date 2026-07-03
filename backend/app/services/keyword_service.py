"""
Check an incoming message against all active keyword_rules.
Returns (matched: bool, reply_message: str | None).
Rules are checked in creation order; first match wins.
account_id=None rules apply globally to all accounts.
"""
from sqlalchemy import select
from app.models.keyword_rule import KeywordRule
from app.database import AsyncSessionLocal


async def check_keywords(
    instance_id: str,
    message_text: str,
    is_group: bool,
    account_id: str | None = None,
) -> tuple[bool, str | None, str | None, str | None]:
    """
    Returns (matched, reply_message, rule_id, scope).
    scope: 'pv' only matches non-group, 'group' only group, 'both' always.
    """
    if not message_text:
        return False, None, None, None

    text_lower = message_text.lower().strip()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(KeywordRule)
            .where(KeywordRule.is_active == True)
            .order_by(KeywordRule.created_at)
        )
        rules = result.scalars().all()

    for rule in rules:
        # account filter: None = global, otherwise must match
        if rule.account_id is not None and str(rule.account_id) != account_id:
            continue

        # scope filter
        if rule.scope == "pv" and is_group:
            continue
        if rule.scope == "group" and not is_group:
            continue

        # match
        kw = rule.keyword.lower().strip()
        matched = False
        if rule.match_type == "exact":
            matched = text_lower == kw
        else:  # contains
            matched = kw in text_lower

        if matched:
            return True, rule.reply_message, str(rule.id), rule.scope

    return False, None, None, None


async def increment_use_count(rule_id: str):
    async with AsyncSessionLocal() as db:
        rule = await db.get(KeywordRule, __import__("uuid").UUID(rule_id))
        if rule:
            rule.use_count += 1
            await db.commit()

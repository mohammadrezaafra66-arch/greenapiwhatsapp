"""
HTTP polling fallback for accounts without a reachable webhook.
Reuses the exact same payload-processing logic as the webhook route.
"""
from app.services.green_api import GreenAPIClient
from app.api.v1.webhook import process_webhook


async def poll_account_once(account) -> int:
    """Fetch and process a single pending notification for one account.
    Returns 1 if a notification was processed, 0 if the queue was empty."""
    client = GreenAPIClient(account.instance_id, account.api_token)
    notif = await client.receive_notification()
    if not notif:
        return 0

    receipt_id = notif.get("receiptId")
    body = notif.get("body", {})
    try:
        await process_webhook(account.instance_id, body)
    finally:
        if receipt_id is not None:
            await client.delete_notification(receipt_id)
    return 1

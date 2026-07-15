"""One-shot: re-run the mutual-contact handshake on every mesh edge that is not yet ACTIVE.
With accounts.phone now populated and add_contact using the correct chatId schema, each
_handshake_edge saves both sides and flips the edge to ACTIVE. Does NOT enroll anyone, does
NOT enable warm-up, does NOT touch the send path — only saves contacts (the handshake step).

Run inside the backend container:  python scripts_heal_stuck_edges.py
"""
import asyncio, json
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.account import Account, AccountStatus
from app.models.warmup_mesh import WarmupMeshEdge
from app.services.warmup_mesh_service import _handshake_edge, edge_is_messageable
from app.services.warmup_state import HandshakeState


async def main():
    out = []
    async with AsyncSessionLocal() as db:
        edges = (await db.execute(select(WarmupMeshEdge))).scalars().all()
        accs = {a.instance_id: a for a in (await db.execute(select(Account))).scalars().all()}
        for e in edges:
            if e.handshake_state == HandshakeState.ACTIVE.value:
                out.append({"edge": f"{e.new_instance_id}->{e.peer_instance_id}",
                            "state": e.handshake_state, "action": "already_active"})
                continue
            new_acc = accs.get(e.new_instance_id)
            peer_acc = accs.get(e.peer_instance_id)
            if not new_acc or not peer_acc:
                out.append({"edge": f"{e.new_instance_id}->{e.peer_instance_id}",
                            "action": "missing_account"})
                continue
            # Only act on active instances; a deleted/banned peer can't handshake.
            if new_acc.status != AccountStatus.active or peer_acc.status != AccountStatus.active:
                out.append({"edge": f"{e.new_instance_id}->{e.peer_instance_id}",
                            "action": f"skip_status new={new_acc.status.value} peer={peer_acc.status.value}"})
                continue
            from app.services.green_api import GreenAPIClient
            edge = await _handshake_edge(db, new_acc, peer_acc, lambda i, t: GreenAPIClient(i, t))
            out.append({"edge": f"{e.new_instance_id}->{e.peer_instance_id}",
                        "state": edge.handshake_state,
                        "saved_new": edge.saved_as_contact_new,
                        "saved_peer": edge.saved_as_contact_peer,
                        "messageable": edge_is_messageable(edge)})
        await db.commit()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

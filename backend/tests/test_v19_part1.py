"""V19 PART 1 — read a warm account's admin-owned groups.

Mocks Green API (no Redis, so caching is a no-op). Asserts: only admin/superadmin groups
are returned; non-admin groups are filtered out; the documented empty-array retry works;
non-group contacts are ignored.
"""
import pytest
from app.services import warmup_groups as wg
from app.services.warmup_groups import (
    is_group_contact, participant_is_admin, get_group_contacts_with_retry, list_admin_groups,
)


# ── pure helpers ─────────────────────────────────────────────────────────────
def test_is_group_contact():
    assert is_group_contact({"type": "group", "id": "12036@g.us"}) is True
    assert is_group_contact({"type": "user", "id": "9891@c.us"}) is False
    assert is_group_contact({"type": "group", "id": "9891@c.us"}) is False   # not @g.us
    assert is_group_contact({"id": "x"}) is False


def test_participant_is_admin_matches_own_number():
    parts = [
        {"id": "989120000001@c.us", "isAdmin": False, "isSuperAdmin": False},
        {"id": "989122270261@c.us", "isAdmin": True, "isSuperAdmin": False},
    ]
    assert participant_is_admin(parts, "989122270261") is True
    assert participant_is_admin(parts, "98912 227 0261") is True     # digit-normalized
    assert participant_is_admin(parts, "989120000001") is False       # present but not admin
    assert participant_is_admin(parts, "989120009999") is False       # not in group


def test_participant_superadmin_counts():
    parts = [{"id": "989122270261@c.us", "isSuperAdmin": True}]
    assert participant_is_admin(parts, "989122270261") is True


def test_participant_empty():
    assert participant_is_admin([], "989122270261") is False
    assert participant_is_admin([{"id": "x@c.us", "isAdmin": True}], "") is False


# ── fake Green API client ────────────────────────────────────────────────────
class FakeClient:
    def __init__(self, contacts_sequence, group_data, own="989122270261"):
        # contacts_sequence: list of return values for successive get_group_contacts calls
        self.instance_id = "WARM"
        self._contacts_seq = list(contacts_sequence)
        self._group_data = group_data
        self._own = own
        self.contacts_calls = 0
        self.group_data_calls = []

    async def get_group_contacts(self):
        self.contacts_calls += 1
        return self._contacts_seq.pop(0) if self._contacts_seq else []

    async def get_group_data(self, group_id):
        self.group_data_calls.append(group_id)
        return self._group_data.get(group_id, {})

    async def get_wa_settings(self):
        return {"phone": self._own}


OWN = "989122270261"
G_ADMIN = "120360000001@g.us"
G_MEMBER = "120360000002@g.us"


def _group_data():
    return {
        G_ADMIN: {"subject": "گروه فروش عمده", "size": 250, "participants": [
            {"id": f"{OWN}@c.us", "isAdmin": True},
            {"id": "989120000009@c.us", "isAdmin": False},
        ]},
        G_MEMBER: {"subject": "گروه دیگران", "size": 100, "participants": [
            {"id": f"{OWN}@c.us", "isAdmin": False},          # we're a member, NOT admin
            {"id": "989120000008@c.us", "isSuperAdmin": True},
        ]},
    }


# ── list_admin_groups ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_only_admin_groups_returned():
    contacts = [[{"type": "group", "id": G_ADMIN}, {"type": "group", "id": G_MEMBER},
                 {"type": "user", "id": "9891@c.us"}]]      # a non-group contact too
    client = FakeClient(contacts, _group_data(), own=OWN)
    groups = await list_admin_groups(client, own_number=OWN, use_cache=False)
    ids = [g["group_id"] for g in groups]
    assert ids == [G_ADMIN]                                  # only the admin group
    assert groups[0]["subject"] == "گروه فروش عمده"
    assert groups[0]["size"] == 250 and groups[0]["is_admin"] is True


@pytest.mark.asyncio
async def test_empty_array_retry():
    """First getContacts returns [], retry returns the groups (documented behavior)."""
    contacts_seq = [[], [], [{"type": "group", "id": G_ADMIN}]]
    client = FakeClient(contacts_seq, _group_data(), own=OWN)
    groups = await get_group_contacts_with_retry(client, retries=3)
    assert client.contacts_calls == 3                        # retried through the empties
    assert [g["id"] for g in groups] == [G_ADMIN]


@pytest.mark.asyncio
async def test_empty_after_all_retries_returns_empty():
    client = FakeClient([[], [], []], _group_data(), own=OWN)
    groups = await get_group_contacts_with_retry(client, retries=3)
    assert groups == [] and client.contacts_calls == 3


@pytest.mark.asyncio
async def test_own_number_fetched_when_not_provided():
    contacts = [[{"type": "group", "id": G_ADMIN}]]
    client = FakeClient(contacts, _group_data(), own=OWN)
    groups = await list_admin_groups(client, own_number=None, use_cache=False)  # must fetch via getWaSettings
    assert [g["group_id"] for g in groups] == [G_ADMIN]


@pytest.mark.asyncio
async def test_no_admin_groups_returns_empty():
    contacts = [[{"type": "group", "id": G_MEMBER}]]         # only a non-admin group
    client = FakeClient(contacts, _group_data(), own=OWN)
    groups = await list_admin_groups(client, own_number=OWN, use_cache=False)
    assert groups == []

"""Shared pytest fixtures.

V30 PART 5 — the peer pacer and the new thank-you pacer are process-global in-memory maps. Reset
them around EVERY test so a send/thank-you recorded by one test can never leak into another and
flip an inline decision. This is purely test isolation; production behavior is unchanged.
"""
import pytest

from app.services import peer_pacer


@pytest.fixture(autouse=True)
def _reset_pacers():
    peer_pacer.reset()
    yield
    peer_pacer.reset()

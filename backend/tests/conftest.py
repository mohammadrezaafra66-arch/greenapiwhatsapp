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


@pytest.fixture(autouse=True)
def _hermetic_ai(monkeypatch):
    """V33 — keep unit tests hermetic & deterministic.

    The test database carries a real AI key, so the DEFAULT «همکاری تیمی» content generators
    (thank-you / thread-ask) reached the live API and returned varied text — which made word-level
    assertions (e.g. «ممنون» in the auto thank-you) pass or fail nondeterministically run-to-run, the
    failure floating between whichever completion-path test the RNG landed on. Tests that deliberately
    exercise the AI path inject their OWN ai_fn and are unaffected; forcing the DEFAULT builders to
    return None makes everything else use the deterministic templated fallback. Production is unchanged.
    """
    def _no_ai(*_a, **_k):
        return None
    for target in ("app.services.warmup_thankyou.build_thankyou_ai_fn",
                   "app.services.outreach_message.build_thread_ai_fn"):
        monkeypatch.setattr(target, _no_ai)
    yield


@pytest.fixture(autouse=True)
def _allow_sender_eligibility(monkeypatch):
    """V39 PART 3 — the send-time sender-eligibility guard (`_send_as_sender`) queries the DB via
    `sender_eligibility.sender_send_allowed`. The many pre-existing tick tests use positional
    fake-session queues and lightweight account doubles (no connect anchor), so that extra query
    would desync them / read the double as ineligible and wrongly block the send. Default the check
    to ALLOW here so those orthogonal tests are unaffected; the guard's real blocking behavior is
    proven directly in test_v39_part3 / test_v39_part5, which re-install the real implementation.
    Production is unchanged."""
    async def _ok(*_a, **_k):
        return True, "ok"
    monkeypatch.setattr("app.services.sender_eligibility.sender_send_allowed", _ok)
    yield

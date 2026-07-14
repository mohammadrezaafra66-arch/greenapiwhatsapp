"""V14 PART G — capability registry categorization."""
from app.api.v1.capabilities import _category_of, CATEGORY, CATEGORY_FA


def test_known_methods_categorized():
    assert _category_of("sendInteractiveButtons") == "sending"
    assert _category_of("addGroupParticipant") == "groups"
    assert _category_of("sendVoiceStatus") == "statuses"
    assert _category_of("getInstances") == "partner"
    assert _category_of("lastIncomingCalls") == "calls"


def test_unknown_method_falls_to_other():
    assert _category_of("someBrandNewMethod") == "other"


def test_every_category_has_a_persian_label():
    for cat in list(CATEGORY.keys()) + ["other"]:
        assert cat in CATEGORY_FA and CATEGORY_FA[cat]

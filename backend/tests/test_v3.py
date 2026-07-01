"""Smoke tests for V3 features."""
import pytest
import inspect
from app.services.keyword_service import check_keywords
from app.services.delay_service import get_delay, set_delay
from app.models.keyword_rule import KeywordRule
from app.models.account_send_config import AccountSendConfig
from app.models.account_hour_schedule import AccountHourSchedule


def test_new_models_importable():
    assert KeywordRule.__tablename__ == "keyword_rules"
    assert AccountSendConfig.__tablename__ == "account_send_configs"
    assert AccountHourSchedule.__tablename__ == "account_hour_schedules"


def test_keyword_service_is_async():
    assert inspect.iscoroutinefunction(check_keywords)


def test_delay_service_is_async():
    assert inspect.iscoroutinefunction(get_delay)
    assert inspect.iscoroutinefunction(set_delay)


def test_campaign_model_has_group_fields():
    from app.models.campaign import Campaign
    assert hasattr(Campaign, "campaign_scope")
    assert hasattr(Campaign, "group_ids")

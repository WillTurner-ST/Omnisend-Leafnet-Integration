import pytest
from middleware.models.nocodb import NocoDBCustomerRecord
from middleware.services.contact_sync_service import ContactSyncService
from middleware.services.category_mapper import CategoryMapper


def test_contact_mapper_full_record():
    service = ContactSyncService()

    raw_nocodb_row = {
        "Id": 101,
        "leafnet_customer_id": "20854",
        "key": "leafnet_customer:20854",
        "email": "  Venus.Celeste@Example.Com  ",
        "first_name": "Venus",
        "last_name": "Celeste",
        "phone": "(423) 713-1503",
        "birth_date": "1994-06-15",
        "favorite_location": "red-bank",
        "leafnet_created_at": "2025-11-19 14:24:33",
        "last_visit": "2026-07-05 18:48:17",
        "days_since_last_visit": 50,
        "visit_count": 103,
        "order_count": 103,
        "lifetime_spend": 2868.00,
        "average_order_value": 27.84,
        "average_days_between_visits": 3.5,
        "points": 362.94,
        "favorite_category": "NON-INF BEVS",
        "opt_status": "none",
        "signup_source": "in-store-register",
    }

    record = NocoDBCustomerRecord(**raw_nocodb_row)
    assert record.has_valid_email is True
    assert record.clean_email == "venus.celeste@example.com"
    assert record.resolved_first_name == "Venus"
    assert record.resolved_last_name == "Celeste"
    assert record.float_lifetime_spend == 2868.00
    assert record.float_points == 362.94
    assert record.int_days_since_last_visit == 50
    assert record.float_visit_frequency_days == 3.5

    omnisend_payload = service.build_omnisend_contact(record)

    # Identifiers check
    assert len(omnisend_payload.identifiers) == 2
    email_ident = [i for i in omnisend_payload.identifiers if i.type == "email"][0]
    phone_ident = [i for i in omnisend_payload.identifiers if i.type == "phone"][0]

    assert email_ident.id == "venus.celeste@example.com"
    assert email_ident.channels.email.status == "subscribed"
    assert phone_ident.id == "+14237131503"

    # Tags check (Goal 5)
    assert "retail" in omnisend_payload.tags
    assert "Leafnet" in omnisend_payload.tags
    assert "store:red-bank" in omnisend_payload.tags
    assert "repeat-customer" in omnisend_payload.tags
    assert "vip" in omnisend_payload.tags
    assert "lapsed-45-days" in omnisend_payload.tags
    assert "category:beverages" in omnisend_payload.tags
    assert not any(tag.startswith("loyalty-tier-") for tag in omnisend_payload.tags)
    phone_ident_channels = phone_ident.channels.sms
    assert phone_ident_channels.status == "nonSubscribed"

    # Custom properties check (Goals 1, 4, 5, 6)
    props = omnisend_payload.customProperties
    assert props["leafnet_customer_id"] == "20854"
    assert props["phone"] == "(423) 713-1503"
    assert props["birthday"] == "1994-06-15"
    assert props["birthday_month_day"] == "06-15"
    assert props["signup_anniversary_month_day"] == "11-19"
    assert props["signup_source"] == "in-store-register"
    assert props["home_store"] == "red-bank"
    assert props["lifetime_value"] == 2868.00
    assert props["days_since_last_visit"] == 50
    assert props["visit_frequency_days"] == 3.5
    assert "points_balance" not in props
    assert "next_milestone_points" not in props
    assert props["top_category"] == "NON-INF BEVS"
    assert props["top_category_bucket"] == "beverages"
    assert props["opt_status"] == "none"


def test_category_mapper_buckets_and_recommendations():
    assert CategoryMapper.normalize_bucket("Snapdragon Gummies") == "gummies"
    assert CategoryMapper.normalize_bucket("Canned Drinks") == "beverages"
    assert CategoryMapper.normalize_bucket("Dragon's Cut Bags - 3.5g") == "flower"
    assert CategoryMapper.normalize_bucket("Connoisseur PR") == "pre-rolls"
    assert CategoryMapper.normalize_bucket("Live Resin Cartridges") == "vapes"
    assert CategoryMapper.normalize_bucket("House Concentrates") == "concentrates"

    rec = CategoryMapper.get_recommendations(["Snapdragon Gummies", "Canned Drinks"])
    assert rec["primary_bucket"] == "gummies"
    assert "beverages" in rec["all_buckets"]
    assert rec["recommended_bucket"] == "beverages"
    assert len(rec["suggested_categories"]) > 0


def test_contact_mapper_includes_loyalty_when_enabled(monkeypatch):
    from middleware.config import settings

    monkeypatch.setattr(settings, "loyalty_enabled", True)
    service = ContactSyncService()
    record = NocoDBCustomerRecord(
        leafnet_customer_id="20854",
        email="venus.celeste@example.com",
        first_name="Venus",
        last_name="Celeste",
        points=362.94,
        favorite_category="NON-INF BEVS",
    )
    payload = service.build_omnisend_contact(record)
    assert "loyalty-tier-300" in payload.tags
    assert payload.customProperties["points_balance"] == 362.94
    assert payload.customProperties["next_milestone_points"] == 500.0


def test_contact_mapper_blank_email():
    record = NocoDBCustomerRecord(
        leafnet_customer_id="30361",
        customer_name="Celeste Thompson",
        phone="(423) 331-4829",
        email="",
    )
    assert record.has_valid_email is False
    assert record.clean_email == ""
    assert record.resolved_first_name == "Celeste"
    assert record.resolved_last_name == "Thompson"


def test_contact_mapper_opt_out():
    service = ContactSyncService()
    record = NocoDBCustomerRecord(
        leafnet_customer_id="999",
        first_name="Jane",
        last_name="Doe",
        email="jane.doe@example.com",
        opt_status="unsubscribed",
    )
    payload = service.build_omnisend_contact(record)
    email_ident = [i for i in payload.identifiers if i.type == "email"][0]
    assert email_ident.channels.email.status == "unsubscribed"

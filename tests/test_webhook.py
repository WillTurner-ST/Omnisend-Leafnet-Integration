import pytest
import os
import tempfile
from middleware.models.leafnet import LeafnetOrderWebhookPayload
from middleware.services.webhook_service import WebhookService
from middleware.database.db import Database


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    yield db
    try:
        os.remove(path)
    except OSError:
        pass


def test_order_webhook_payload_parsing():
    raw_payload = {
        "Order Id": "#232450",
        "customer_id": "20854",
        "email": "venus@example.com",
        "phone": "(423) 713-1503",
        "Created": "2026-07-05 18:48:17",
        "Location": "amnicola",
        "Subtotal": "17.49",
        "Discounts": "0",
        "Tax and Fees": "1.62",
        "Total": "19.11",
        "Contents": [
            {
                "item_id": "922",
                "name": "Dragon's Breath Torch",
                "qty": 1,
                "unit_cost": "34.99",
                "account_id": "34",
                "account_name": "Venus Celeste",
                "barcode": "705626136408",
                "macros": [
                    {"type": "Category", "value": "Lighters & Torches"},
                    {"type": "Vendor", "value": "Warehouse"},
                ],
            }
        ],
    }

    order = LeafnetOrderWebhookPayload(**raw_payload)

    assert order.clean_order_id == "232450"
    assert order.float_total == 19.11
    assert order.total_cents == 1911
    assert order.subtotal_cents == 1749
    assert order.tax_cents == 162
    assert order.categories == ["Lighters & Torches"]
    assert order.staff_account_id == "34"
    assert order.staff_account_name == "Venus Celeste"


@pytest.mark.asyncio
async def test_order_webhook_deduplication_and_recommendations(temp_db):
    class MockOmnisend:
        async def create_order(self, order):
            return {"status": "created", "orderID": order.orderID}

        async def trigger_event(self, event):
            return {"status": "triggered", "properties": event.properties}

        async def upsert_contact(self, contact):
            return {"status": "updated"}

    service = WebhookService(omnisend_client=MockOmnisend(), database=temp_db)

    order_payload = LeafnetOrderWebhookPayload(
        order_id="998877",
        customer_id="123",
        email="test@user.com",
        total="45.50",
        created="2026-07-05 12:00:00",
        location="red-bank",
        items=[
            {
                "item_id": "501",
                "name": "Snapdragon NANO Gummies",
                "qty": 1,
                "unit_cost": "45.50",
                "category_name": "Snapdragon Gummies",
                "account_id": "emp_7",
                "account_name": "Harlie Davis",
            }
        ],
    )

    # First call -> success + category recommendation enrichment
    res1 = await service.process_order_completed(order_payload)
    assert res1["status"] == "success"
    assert res1["order_id"] == "998877"
    assert res1["category_buckets"] == ["gummies"]
    assert res1["recommended_category_bucket"] == "beverages"
    assert res1["omnisend_order"]["status"] == "skipped"
    assert res1["omnisend_event"]["status"] == "skipped"

    # Second call with same order_id -> skipped as duplicate
    res2 = await service.process_order_completed(order_payload)
    assert res2["status"] == "skipped"
    assert res2["reason"] == "duplicate_order"


@pytest.mark.asyncio
async def test_order_webhook_resolves_email_and_tracks_employee_attribution(temp_db):
    class MockOmnisend:
        async def create_order(self, order):
            return {"status": "created", "orderID": order.orderID}

        async def trigger_event(self, event):
            return {"status": "triggered"}

        async def upsert_contact(self, contact):
            return {"status": "updated"}

    # Pre-populate customer 777 as a phone-only customer
    temp_db.upsert_phone_only_customer(
        leafnet_customer_id="777",
        customer_name="Existing Phone Member",
        phone="(423) 555-0199",
        favorite_location="red-bank",
        order_count=4,
        lifetime_spend=120.0,
        last_seen_at="2026-06-01 10:00:00",
    )

    service = WebhookService(omnisend_client=MockOmnisend(), database=temp_db)

    # Now customer 777 places an order WITH an email added and cashier Harlie Davis on the sale
    order_payload = LeafnetOrderWebhookPayload(
        order_id="ord_attr_01",
        customer_id="777",
        email="captured@example.com",
        phone="(423) 555-0199",
        total="25.00",
        created="2026-07-05 15:30:00",
        location="red-bank",
        account_id="34",
        account_name="Harlie Davis",
    )

    res = await service.process_order_completed(order_payload)
    assert res["status"] == "success"
    assert res["has_email"] is True

    # Phone-only customer should now be removed from phone_only_customers
    assert temp_db.get_phone_only_customer("777") is None

    # And Harlie Davis should be credited with an 'existing_account_emails' acquisition!
    leaderboard = temp_db.get_employee_email_acquisitions()
    assert len(leaderboard) == 1
    assert leaderboard[0]["employee_name"] == "Harlie Davis"
    assert leaderboard[0]["existing_account_emails"] == 1

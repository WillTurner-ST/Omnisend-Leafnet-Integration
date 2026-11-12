import pytest
from middleware.services.loyalty_service import LoyaltyService


@pytest.mark.asyncio
async def test_loyalty_milestones():
    triggered_events = []

    class MockOmnisend:
        async def trigger_event(self, event):
            triggered_events.append(event)
            return {"status": "success"}

    class MockLeafnet:
        pass

    service = LoyaltyService(leafnet_client=MockLeafnet(), omnisend_client=MockOmnisend())

    # Case 1: Customer crosses 100 points
    res = await service.check_and_trigger_milestones(
        email="shopper@test.com",
        phone="+15053214567",
        points=120.0,
        previous_points=85.0,
    )
    assert len(res) == 1
    assert res[0]["threshold"] == 100.0
    assert res[0]["reward"] == "$5 off"
    assert len(triggered_events) == 1
    assert triggered_events[0].properties["discount_code"] == "REWARD5OFF"

    # Case 2: Customer already had 120 points and moves to 150 (no new threshold crossed)
    triggered_events.clear()
    res2 = await service.check_and_trigger_milestones(
        email="shopper@test.com",
        phone="+15053214567",
        points=150.0,
        previous_points=120.0,
    )
    assert len(res2) == 0
    assert len(triggered_events) == 0

    # Case 3: Customer crosses 200 points
    triggered_events.clear()
    res3 = await service.check_and_trigger_milestones(
        email="shopper@test.com",
        phone="+15053214567",
        points=210.0,
        previous_points=150.0,
    )
    assert len(res3) == 1
    assert res3[0]["threshold"] == 200.0
    assert res3[0]["reward"] == "10% off"
    assert len(triggered_events) == 1
    assert triggered_events[0].properties["discount_code"] == "REWARD10PCT"

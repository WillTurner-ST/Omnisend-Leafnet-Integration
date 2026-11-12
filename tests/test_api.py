import pytest
import uuid
from fastapi.testclient import TestClient
from middleware.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "integrations" in data


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "/docs" in data["documentation"]


def test_phone_only_report_endpoint():
    response = client.get("/api/reports/phone-only")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_staff_email_report_endpoint():
    response = client.get("/api/reports/staff-email-acquisitions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_customer_updated_webhook():
    payload = {
        "customer_id": "20854",
        "old_email": "",
        "new_email": "new.email@example.com",
        "employee_id": "emp_12",
        "employee_name": "Sarah Connor",
        "location": "red-bank",
    }
    response = client.post("/webhooks/leafnet/customer-updated", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["employee_name"] == "Sarah Connor"


def test_order_completed_webhook_endpoint():
    unique_order_id = f"ord_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "order_id": unique_order_id,
        "customer_id": "5555",
        "email": "customer@test.com",
        "total": 35.00,
        "created": "2026-07-05 14:00:00",
        "location": "east-brainerd",
        "items": [
            {
                "item_id": "100",
                "name": "Snapdragon Gummies",
                "qty": 1,
                "unit_cost": 35.00,
                "category_name": "GUMMIES",
            }
        ],
    }
    response = client.post("/webhooks/leafnet/order-completed", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["order_id"] == unique_order_id
    assert data["total_cents"] == 3500

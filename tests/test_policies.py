"""Lab 2 — Unit and integration tests for the policies API."""
import pytest
from app.models import PolicyStatus


def test_issue_health_policy_success(client, ids):
    # 1. Create a quote
    q = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Priya Nair"],
            "product_id": ids["products"]["HEALTH"],
            "sum_insured": 500000,
            "tenure_years": 1,
        },
    ).json()

    # 2. Issue a policy
    r = client.post(
        "/api/policies",
        json={"quote_id": q["id"], "start_date": "2026-01-01"},
    )
    assert r.status_code == 201
    policy = r.json()

    # Verify policy number format: PD-HEALTH-2026-00001
    assert policy["policy_number"].startswith("PD-HEALTH-2026-")
    assert policy["quote_id"] == q["id"]
    assert policy["customer_id"] == ids["customers"]["Priya Nair"]
    assert policy["product_id"] == ids["products"]["HEALTH"]
    assert policy["sum_insured"] == 500000
    assert policy["premium"] == 15000.0
    assert policy["start_date"] == "2026-01-01"
    assert policy["end_date"] == "2026-12-31"
    assert policy["status"] == PolicyStatus.ACTIVE.value


def test_issue_policy_duplicate_quote_conflict(client, ids):
    q = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Priya Nair"],
            "product_id": ids["products"]["HEALTH"],
            "sum_insured": 500000,
            "tenure_years": 1,
        },
    ).json()

    # First issue succeeds
    r1 = client.post("/api/policies", json={"quote_id": q["id"], "start_date": "2026-01-01"})
    assert r1.status_code == 201

    # Second issue returns 409 Conflict
    r2 = client.post("/api/policies", json={"quote_id": q["id"], "start_date": "2026-01-01"})
    assert r2.status_code == 409
    assert "already been converted" in r2.json()["detail"]


def test_issue_policy_unknown_quote_404(client):
    r = client.post("/api/policies", json={"quote_id": 99999, "start_date": "2026-01-01"})
    assert r.status_code == 404
    assert "Quote not found" in r.json()["detail"]


def test_issue_motor_policy_requires_vehicle(client, ids):
    q = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Rohan Das"],
            "product_id": ids["products"]["MOTOR"],
            "sum_insured": 800000,
            "tenure_years": 2,
            "add_ons": "ZERO_DEPRECIATION",
        },
    ).json()

    # Missing vehicle registration -> 422
    r_err = client.post("/api/policies", json={"quote_id": q["id"], "start_date": "2026-01-01"})
    assert r_err.status_code == 422
    assert "vehicle registration number" in r_err.json()["detail"]

    # With vehicle registration (lower-cased input should be stored upper-cased)
    r_ok = client.post(
        "/api/policies",
        json={
            "quote_id": q["id"],
            "start_date": "2026-01-01",
            "vehicle_registration": "ts09ab1234",
        },
    )
    assert r_ok.status_code == 201
    p = r_ok.json()
    assert p["vehicle_registration"] == "TS09AB1234"
    # 2-year tenure: 2026-01-01 + 730 days - 1 day = 2027-12-31
    assert p["end_date"] == "2027-12-31"


def test_policy_status_transition_and_cancelled_is_final(client, ids):
    q = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Priya Nair"],
            "product_id": ids["products"]["HEALTH"],
            "sum_insured": 500000,
            "tenure_years": 1,
        },
    ).json()
    p = client.post("/api/policies", json={"quote_id": q["id"], "start_date": "2026-01-01"}).json()

    # Active -> Lapsed (OK)
    r_lapsed = client.patch(f"/api/policies/{p['id']}/status", json={"status": "Lapsed"})
    assert r_lapsed.status_code == 200
    assert r_lapsed.json()["status"] == "Lapsed"

    # Lapsed -> Cancelled (OK)
    r_cancel = client.patch(f"/api/policies/{p['id']}/status", json={"status": "Cancelled"})
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "Cancelled"

    # Cancelled -> Active (409 Conflict)
    r_reopen = client.patch(f"/api/policies/{p['id']}/status", json={"status": "Active"})
    assert r_reopen.status_code == 409
    assert "Cancelled policies cannot be changed" in r_reopen.json()["detail"]


def test_policy_status_unknown_policy_404(client):
    r = client.patch("/api/policies/99999/status", json={"status": "Cancelled"})
    assert r.status_code == 404

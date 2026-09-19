"""Lab 3 — Unit and integration tests for the Claims API and validation rules."""
import pytest
from app.models import ClaimStatus


def test_file_claim_success(client, health_policy):
    # health_policy is 1-year Active policy with sum insured 500,000 from 2026-01-01 to 2026-12-31
    r = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 50000,
            "description": "Hospitalization expense for treatment",
            "incident_date": "2026-06-15",
        },
    )
    assert r.status_code == 201
    claim = r.json()
    assert claim["policy_id"] == health_policy["id"]
    assert claim["amount"] == 50000
    assert claim["status"] == ClaimStatus.FILED.value


def test_file_claim_auto_rejected_on_cancelled_policy(client, health_policy):
    # Cancel the policy
    client.patch(f"/api/policies/{health_policy['id']}/status", json={"status": "Cancelled"})

    r = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 25000,
            "description": "Routine surgery expense",
            "incident_date": "2026-06-15",
        },
    )
    assert r.status_code == 201
    claim = r.json()
    assert claim["status"] == ClaimStatus.REJECTED.value
    assert "Policy is cancelled" in claim["reason"]


def test_file_claim_fails_on_lapsed_policy(client, health_policy):
    # Set policy to Lapsed
    client.patch(f"/api/policies/{health_policy['id']}/status", json={"status": "Lapsed"})

    r = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 25000,
            "description": "Accident expense",
            "incident_date": "2026-06-15",
        },
    )
    assert r.status_code == 422
    assert "not active" in r.json()["detail"]


def test_file_claim_incident_date_out_of_bounds(client, health_policy):
    # Before policy start date (start is 2026-01-01)
    r_before = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 10000,
            "description": "Prior illness",
            "incident_date": "2025-12-31",
        },
    )
    assert r_before.status_code == 422
    assert "outside the policy period" in r_before.json()["detail"]

    # After policy end date (end is 2026-12-31)
    r_after = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 10000,
            "description": "Post coverage illness",
            "incident_date": "2027-01-01",
        },
    )
    assert r_after.status_code == 422
    assert "outside the policy period" in r_after.json()["detail"]


def test_file_claim_exceeds_remaining_cover(client, health_policy):
    # Sum insured is 500,000; claim 600,000
    r = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 600000,
            "description": "Major surgery",
            "incident_date": "2026-06-15",
        },
    )
    assert r.status_code == 422
    assert "exceeds remaining cover" in r.json()["detail"]


def test_file_motor_claim_requires_vehicle(client, motor_policy):
    # Motor policy without vehicle registration
    r = client.post(
        "/api/claims",
        json={
            "policy_id": motor_policy["id"],
            "amount": 30000,
            "description": "Bumper repair",
            "incident_date": "2026-06-15",
        },
    )
    assert r.status_code == 422
    assert "Vehicle registration is required" in r.json()["detail"]


def test_claim_status_workflow_transitions(client, health_policy):
    # 1. File a claim
    claim = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 50000,
            "description": "Hospitalization expense",
            "incident_date": "2026-06-15",
        },
    ).json()

    # Direct Filed -> Approved should fail (409 Conflict)
    r_bad = client.patch(f"/api/claims/{claim['id']}/status", json={"status": "Approved"})
    assert r_bad.status_code == 409

    # Filed -> Under Review (OK)
    r_review = client.patch(f"/api/claims/{claim['id']}/status", json={"status": "Under Review"})
    assert r_review.status_code == 200
    assert r_review.json()["status"] == ClaimStatus.UNDER_REVIEW.value

    # Under Review -> Approved (OK)
    r_app = client.patch(
        f"/api/claims/{claim['id']}/status",
        json={"status": "Approved", "reason": "All bills verified"},
    )
    assert r_app.status_code == 200
    assert r_app.json()["status"] == ClaimStatus.APPROVED.value
    assert r_app.json()["reason"] == "All bills verified"

    # Approved -> Rejected should fail (409 Conflict, Approved is final)
    r_reopen = client.patch(f"/api/claims/{claim['id']}/status", json={"status": "Rejected"})
    assert r_reopen.status_code == 409

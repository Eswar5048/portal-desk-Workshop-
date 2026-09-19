"""HTML screen tests. The given pages are covered; add one test per scenario as you build it (docs/scenarios.md)."""


def test_given_pages_render(client):
    for path in ["/", "/customers", "/products", "/quotes/new", "/policies", "/claims"]:
        r = client.get(path)
        assert r.status_code == 200, path
        assert "PolicyDesk" in r.text


def test_student_pages_are_placeholders_until_built(client):
    # These pass on the starter and should be REPLACED by real tests once each scenario is done.
    assert "not built yet" in client.get("/customers/1").text     # Scenario 2


def test_claim_review_page_and_workflow(client, health_policy):
    # File a claim
    claim = client.post(
        "/api/claims",
        json={
            "policy_id": health_policy["id"],
            "amount": 45000,
            "description": "Hospitalization bill",
            "incident_date": "2026-06-15",
        },
    ).json()

    # 1. GET /claims/{id} should render and show "Approve" (starts in Under Review)
    r = client.get(f"/claims/{claim['id']}")
    assert r.status_code == 200
    assert "Claim Review" in r.text
    assert "Approve" in r.text

    # 2. Approve with reason
    client.patch(
        f"/api/claims/{claim['id']}/status",
        json={"status": "Approved", "reason": "Hospital discharge summary verified"},
    )

    # 3. Approved claim shows final state note and reason
    r_approved = client.get(f"/claims/{claim['id']}")
    assert r_approved.status_code == 200
    assert "final state" in r_approved.text
    assert "Hospital discharge summary verified" in r_approved.text

    # 4. Unknown claim returns 404
    assert client.get("/claims/99999").status_code == 404


def test_quotes_list_open_and_product_filter(client, ids):
    # Create a HEALTH quote for Priya Nair
    q_health = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Priya Nair"],
            "product_id": ids["products"]["HEALTH"],
            "sum_insured": 500000,
            "tenure_years": 1,
        },
    ).json()

    # Create a MOTOR quote for Rohan Das
    q_motor = client.post(
        "/api/quotes",
        json={
            "customer_id": ids["customers"]["Rohan Das"],
            "product_id": ids["products"]["MOTOR"],
            "sum_insured": 800000,
            "tenure_years": 2,
            "add_ons": "ZERO_DEPRECIATION",
        },
    ).json()

    r = client.get("/quotes")
    assert r.status_code == 200
    assert "2 shown" in r.text

    motor_link = f'href="/quotes/{q_motor["id"]}"'
    health_link = f'href="/quotes/{q_health["id"]}"'

    # Check status=open vs status=converted
    r_open = client.get("/quotes?status=open")
    assert r_open.status_code == 200
    assert motor_link in r_open.text

    r_converted = client.get("/quotes?status=converted")
    assert r_converted.status_code == 200
    assert motor_link not in r_converted.text

    # Check product=MOTOR filter
    r_motor = client.get("/quotes?product=MOTOR")
    assert r_motor.status_code == 200
    assert motor_link in r_motor.text
    assert health_link not in r_motor.text

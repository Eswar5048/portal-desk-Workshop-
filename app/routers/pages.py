"""Server-rendered HTML screens (Jinja2). The JSON API lives under /api/*.

Screens: Dashboard · Get a Quote -> Issue Policy · Policies list/detail · File a Claim / Claim status
"""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, func, select

from app.db import get_session
from app.models import (
    Claim,
    ClaimCreate,
    ClaimStatus,
    ClaimStatusUpdate,
    Customer,
    CustomerCreate,
    Policy,
    PolicyCreate,
    PolicyStatus,
    Product,
    Quote,
    QuoteCreate,
)
from app.routers.claims import file_claim, update_claim_status
from app.routers.policies import issue_policy
from app.routers.quotes import price_quote
from app.services import pricing
from app.services.claims import ALLOWED_TRANSITIONS, remaining_cover  # noqa: F401  (ALLOWED_TRANSITIONS: Scenario 3)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def money(value: float | None) -> str:
    """Indian-style grouping: 12,34,567.00"""
    if value is None:
        return "—"
    whole, frac = f"{value:.2f}".split(".")
    if len(whole) > 3:
        head, last3 = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [last3])
    return f"₹{whole}.{frac}"


templates.env.filters["money"] = money
templates.env.globals["today"] = date.today
templates.env.globals["PolicyStatus"] = PolicyStatus
templates.env.globals["ClaimStatus"] = ClaimStatus


def render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    counts = {
        "customers": session.exec(select(func.count(Customer.id))).one(),
        "quotes": session.exec(select(func.count(Quote.id))).one(),
        "policies": session.exec(select(func.count(Policy.id))).one(),
        "active": session.exec(select(func.count(Policy.id)).where(Policy.status == PolicyStatus.ACTIVE)).one(),
        "claims": session.exec(select(func.count(Claim.id))).one(),
        "open_claims": session.exec(
            select(func.count(Claim.id)).where(col(Claim.status).in_([ClaimStatus.FILED, ClaimStatus.UNDER_REVIEW]))
        ).one(),
    }
    premium_collected = session.exec(
        select(func.coalesce(func.sum(Policy.premium), 0)).where(Policy.status != PolicyStatus.CANCELLED)
    ).one()
    claims_approved = session.exec(
        select(func.coalesce(func.sum(Claim.amount), 0)).where(Claim.status == ClaimStatus.APPROVED)
    ).one()
    by_product = session.exec(
        select(Product.name, func.count(Policy.id))
        .join(Policy, Policy.product_id == Product.id, isouter=True)
        .group_by(Product.id)
        .order_by(Product.id)
    ).all()
    recent_policies = session.exec(select(Policy).order_by(Policy.created_at.desc()).limit(5)).all()
    recent_claims = session.exec(select(Claim).order_by(Claim.created_at.desc()).limit(5)).all()
    return render(
        request,
        "dashboard.html",
        counts=counts,
        premium_collected=premium_collected,
        claims_approved=claims_approved,
        by_product=by_product,
        recent_policies=recent_policies,
        recent_claims=recent_claims,
    )


# --------------------------------------------------------------------------- #
# Products (given)
# --------------------------------------------------------------------------- #
@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request, session: Session = Depends(get_session)):
    products = session.exec(select(Product).order_by(Product.id)).all()
    policy_counts = dict(
        session.exec(select(Policy.product_id, func.count(Policy.id)).group_by(Policy.product_id)).all()
    )
    return render(request, "products.html", products=products, add_ons=pricing.ADD_ONS, policy_counts=policy_counts)


# --------------------------------------------------------------------------- #
# Student scenarios — see docs/scenarios.md. Replace each placeholder with the real page.
# --------------------------------------------------------------------------- #
SCENARIOS = {
    1: ("Quotes list", "/quotes", "quotes.html",
        "Every quote, Open vs Converted, filter by product, 'Issue policy' button for open quotes."),
    2: ("Customer 360", "/customers/{id}", "customer_detail.html",
        "Profile, totals, and every quote / policy / claim for one customer. 'New quote' button pre-selects them."),
    3: ("Claim review", "/claims/{id}", "claim_detail.html",
        "Claim + policy context, remaining cover, and only the allowed next actions with a reason box."),
}


def scenario_placeholder(request: Request, number: int):
    title, route, template, summary = SCENARIOS[number]
    return render(request, "scenario_todo.html", number=number, title=title, route=route,
                  template=template, summary=summary)


@router.get("/quotes", response_class=HTMLResponse)
def quotes_list(
    request: Request,
    status: str | None = None,
    product: str | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(Quote).order_by(Quote.created_at.desc())
    if product:
        stmt = stmt.join(Product).where(Product.code == product)
    quotes = list(session.exec(stmt).all())

    open_count = sum(1 for q in quotes if q.policy is None)

    if status == "open":
        quotes = [q for q in quotes if q.policy is None]
    elif status == "converted":
        quotes = [q for q in quotes if q.policy is not None]

    products = session.exec(select(Product).order_by(Product.id)).all()
    return render(
        request,
        "quotes.html",
        quotes=quotes,
        status=status,
        product=product,
        products=products,
        open_count=open_count,
    )


@router.get("/customers/{customer_id}", response_class=HTMLResponse)
def customer_detail(request: Request, customer_id: int, session: Session = Depends(get_session)):
    """SCENARIO 2 — Customer 360. TODO: session.get(Customer, id) (404 if missing), collect their quotes,
    policies and claims, render customer_detail.html."""
    return scenario_placeholder(request, 2)


@router.get("/claims/{claim_id}", response_class=HTMLResponse)
def claim_detail(request: Request, claim_id: int, session: Session = Depends(get_session)):
    """SCENARIO 3 — Claim review. TODO: session.get(Claim, id) (404 if missing), remaining cover, allowed next
    states from ALLOWED_TRANSITIONS, render claim_detail.html."""
    return scenario_placeholder(request, 3)


# --------------------------------------------------------------------------- #
# Quote -> Policy
# --------------------------------------------------------------------------- #
@router.get("/quotes/new", response_class=HTMLResponse)
def quote_form(request: Request, customer_id: int | None = None, session: Session = Depends(get_session)):
    return render(
        request,
        "quote.html",
        customers=session.exec(select(Customer).order_by(Customer.name)).all(),
        products=session.exec(select(Product)).all(),
        add_ons=pricing.ADD_ONS,
        form={"customer_id": customer_id} if customer_id else {},
    )


@router.post("/quotes/new", response_class=HTMLResponse)
def quote_submit(
    request: Request,
    customer_id: int = Form(...),
    product_id: int = Form(...),
    sum_insured: float = Form(...),
    tenure_years: int = Form(...),
    add_ons: list[str] = Form(default=[]),
    session: Session = Depends(get_session),
):
    payload = QuoteCreate(
        customer_id=customer_id,
        product_id=product_id,
        sum_insured=sum_insured,
        tenure_years=tenure_years,
        add_ons=",".join(add_ons),
    )
    try:
        premium, _, _ = price_quote(payload, session)
    except HTTPException as exc:
        return render(
            request,
            "quote.html",
            customers=session.exec(select(Customer).order_by(Customer.name)).all(),
            products=session.exec(select(Product)).all(),
            add_ons=pricing.ADD_ONS,
            form=payload.model_dump(),
            error=exc.detail,
        )
    quote = Quote(**payload.model_dump(), premium=premium)
    session.add(quote)
    session.commit()
    return RedirectResponse(f"/quotes/{quote.id}", status_code=303)


@router.get("/quotes/{quote_id}", response_class=HTMLResponse)
def quote_detail(request: Request, quote_id: int, session: Session = Depends(get_session)):
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(404, "Quote not found")
    return render(
        request,
        "quote_detail.html",
        quote=quote,
        age=pricing.age_on(quote.customer.date_of_birth),
        add_on_list=pricing.parse_add_ons(quote.add_ons),
        error=request.query_params.get("error"),
    )


@router.post("/quotes/{quote_id}/issue")
def quote_issue(
    quote_id: int,
    start_date: date = Form(...),
    vehicle_registration: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        policy = issue_policy(
            PolicyCreate(quote_id=quote_id, start_date=start_date, vehicle_registration=vehicle_registration),
            session,
        )
    except HTTPException as exc:
        return RedirectResponse(f"/quotes/{quote_id}?error={exc.detail}", status_code=303)
    return RedirectResponse(f"/policies/{policy.id}?flash=Policy+{policy.policy_number}+issued", status_code=303)


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #
@router.get("/policies", response_class=HTMLResponse)
def policies_list(request: Request, status: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Policy).order_by(Policy.created_at.desc())
    if status:
        stmt = stmt.where(Policy.status == status)
    return render(request, "policies.html", policies=session.exec(stmt).all(), status=status)


@router.get("/policies/{policy_id}", response_class=HTMLResponse)
def policy_detail(request: Request, policy_id: int, session: Session = Depends(get_session)):
    policy = session.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    return render(
        request,
        "policy_detail.html",
        policy=policy,
        remaining=remaining_cover(session, policy),
        flash=request.query_params.get("flash"),
        error=request.query_params.get("error"),
    )


@router.post("/policies/{policy_id}/status")
def policy_status(policy_id: int, status: PolicyStatus = Form(...), session: Session = Depends(get_session)):
    policy = session.get(Policy, policy_id)
    if not policy:
        raise HTTPException(404, "Policy not found")
    if policy.status == PolicyStatus.CANCELLED:
        return RedirectResponse(f"/policies/{policy_id}?error=Cancelled+policies+cannot+be+changed", status_code=303)
    policy.status = status
    session.add(policy)
    session.commit()
    return RedirectResponse(f"/policies/{policy_id}?flash=Status+updated", status_code=303)


# --------------------------------------------------------------------------- #
# Claims
# --------------------------------------------------------------------------- #
@router.get("/claims", response_class=HTMLResponse)
def claims_list(request: Request, status: str | None = None, session: Session = Depends(get_session)):
    stmt = select(Claim).order_by(Claim.created_at.desc())
    if status:
        stmt = stmt.where(Claim.status == status)
    return render(request, "claims.html", claims=session.exec(stmt).all(), status=status)


@router.post("/policies/{policy_id}/claims")
def claim_submit(
    policy_id: int,
    amount: float = Form(...),
    description: str = Form(...),
    incident_date: date = Form(...),
    vehicle_registration: str = Form(""),
    session: Session = Depends(get_session),
):
    try:
        claim = file_claim(
            ClaimCreate(
                policy_id=policy_id,
                amount=amount,
                description=description,
                incident_date=incident_date,
                vehicle_registration=vehicle_registration or None,
            ),
            session,
        )
    except HTTPException as exc:
        return RedirectResponse(f"/policies/{policy_id}?error={exc.detail}", status_code=303)
    msg = "Claim+filed" if claim.status == ClaimStatus.FILED else "Claim+auto-rejected:+" + (claim.reason or "")
    return RedirectResponse(f"/policies/{policy_id}?flash={msg}", status_code=303)


@router.post("/claims/{claim_id}/status")
def claim_status(
    claim_id: int,
    status: ClaimStatus = Form(...),
    reason: str = Form(""),
    back: str = Form(""),
    session: Session = Depends(get_session),
):
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(404, "Claim not found")
    back = back if back.startswith("/") else f"/policies/{claim.policy_id}"
    try:
        update_claim_status(claim_id, ClaimStatusUpdate(status=status, reason=reason or None), session)
    except HTTPException as exc:
        return RedirectResponse(f"{back}?error={exc.detail}", status_code=303)
    return RedirectResponse(f"{back}?flash=Claim+marked+{status.value}", status_code=303)


# --------------------------------------------------------------------------- #
# Customers
# --------------------------------------------------------------------------- #
@router.get("/customers", response_class=HTMLResponse)
def customers_list(request: Request, session: Session = Depends(get_session)):
    return render(
        request,
        "customers.html",
        customers=session.exec(select(Customer).order_by(Customer.name)).all(),
        age_on=pricing.age_on,
        error=request.query_params.get("error"),
    )


@router.post("/customers")
def customer_submit(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    date_of_birth: date = Form(...),
    session: Session = Depends(get_session),
):
    try:
        payload = CustomerCreate(name=name, email=email, phone=phone, date_of_birth=date_of_birth)
    except ValueError as exc:
        first = exc.errors()[0] if hasattr(exc, "errors") else {"msg": str(exc)}
        return RedirectResponse(f"/customers?error={first['msg']}", status_code=303)
    if session.exec(select(Customer).where(Customer.email == payload.email)).first():
        return RedirectResponse("/customers?error=Email+already+registered", status_code=303)
    session.add(Customer.model_validate(payload))
    session.commit()
    return RedirectResponse("/customers", status_code=303)

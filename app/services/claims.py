"""Claim validation rules.   *** LAB 3: YOUR CODE HERE ***

A claim is accepted for filing only if:
    1. The policy is Active.
         Cancelled -> raise ClaimValidationError(..., auto_reject=True)  (the claim is SAVED as Rejected)
         Lapsed    -> raise ClaimValidationError(...)                    (the request is refused with 422)
    2. The incident date falls within the policy period (start and end dates inclusive)
    3. amount <= remaining cover  (sum insured - claims already APPROVED on this policy)
    4. Motor claims include a vehicle registration number

Status workflow (given below): Filed -> Under Review -> Approved / Rejected. Approved and Rejected are final.
"""
from datetime import date

from sqlmodel import Session, select

from app.models import Claim, ClaimStatus, Policy, PolicyStatus, ProductCode


class ClaimValidationError(ValueError):
    """Claim breaks a business rule. `auto_reject=True` means store it as Rejected."""

    def __init__(self, message: str, auto_reject: bool = False):
        super().__init__(message)
        self.auto_reject = auto_reject


def approved_total(session: Session, policy_id: int) -> float:
    """Sum of APPROVED claim amounts on a policy. (Given.)"""
    rows = session.exec(
        select(Claim.amount).where(Claim.policy_id == policy_id, Claim.status == ClaimStatus.APPROVED)
    ).all()
    return float(sum(rows))


def remaining_cover(session: Session, policy: Policy) -> float:
    """Sum insured minus approved claims. (Given.)"""
    return policy.sum_insured - approved_total(session, policy.id)


def validate_claim(
    session: Session,
    policy: Policy,
    *,
    amount: float,
    incident_date: date,
    vehicle_registration: str | None,
) -> None:
    """Raise ClaimValidationError if the claim must not be filed. Return None when it is fine."""
    # 1. Policy status
    if policy.status == PolicyStatus.CANCELLED:
        raise ClaimValidationError("Policy is cancelled", auto_reject=True)
    if policy.status != PolicyStatus.ACTIVE:
        raise ClaimValidationError(f"Policy is not active ({policy.status.value})")

    # 2. Incident date within policy period
    if incident_date < policy.start_date or incident_date > policy.end_date:
        raise ClaimValidationError(
            f"Incident date {incident_date} is outside the policy period ({policy.start_date} to {policy.end_date})"
        )

    # 3. Amount within remaining cover
    cover = remaining_cover(session, policy)
    if amount > cover:
        raise ClaimValidationError(
            f"Claim amount (₹{amount:,.0f}) exceeds remaining cover (₹{cover:,.0f})"
        )

    # 4. Motor claims require vehicle registration
    if policy.product.code == ProductCode.MOTOR and not (vehicle_registration or "").strip():
        raise ClaimValidationError("Vehicle registration is required for Motor claims")


ALLOWED_TRANSITIONS: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.FILED: {ClaimStatus.UNDER_REVIEW, ClaimStatus.APPROVED, ClaimStatus.REJECTED},
    ClaimStatus.UNDER_REVIEW: {ClaimStatus.APPROVED, ClaimStatus.REJECTED},
    ClaimStatus.APPROVED: set(),
    ClaimStatus.REJECTED: set(),
}


def can_transition(current: ClaimStatus, new: ClaimStatus) -> bool:
    return new in ALLOWED_TRANSITIONS[current]

"""Lab 1, Part D — Comprehensive unit tests for the pricing module."""
import pytest

from app.models import ProductCode
from app.services.pricing import (
    PricingError,
    add_on_factor,
    age_factor,
    calculate_premium,
    tenure_factor,
)


# --- Age Factor Tests ---

@pytest.mark.parametrize(
    "age,product,expected",
    [
        (0, ProductCode.MOTOR, 1.2),
        (0, ProductCode.HEALTH, 0.8),
        (24, ProductCode.MOTOR, 1.2),
        (24, ProductCode.HEALTH, 0.8),
        (25, ProductCode.MOTOR, 1.0),
        (25, ProductCode.HEALTH, 1.0),
        (45, ProductCode.MOTOR, 1.0),
        (45, ProductCode.HEALTH, 1.0),
        (46, ProductCode.MOTOR, 1.3),
        (46, ProductCode.HEALTH, 1.3),
        (60, ProductCode.MOTOR, 1.3),
        (60, ProductCode.HEALTH, 1.3),
        (61, ProductCode.MOTOR, 1.6),
        (61, ProductCode.HEALTH, 1.6),
    ],
)
def test_age_factor_bands_and_boundaries(age, product, expected):
    assert age_factor(age, product) == pytest.approx(expected)


def test_age_factor_negative_age():
    with pytest.raises(PricingError, match="Age cannot be negative"):
        age_factor(-1, ProductCode.MOTOR)


# --- Tenure Factor Tests ---

@pytest.mark.parametrize(
    "tenure_years,expected",
    [
        (1, 1.0),
        (2, 0.95),
        (3, 0.90),
    ],
)
def test_tenure_factor_valid(tenure_years, expected):
    assert tenure_factor(tenure_years) == pytest.approx(expected)


def test_tenure_factor_invalid():
    with pytest.raises(PricingError) as exc_info:
        tenure_factor(4)
    assert "4" in str(exc_info.value)


# --- Add-on Factor Tests ---

def test_add_on_factor_health_critical_illness():
    assert add_on_factor(ProductCode.HEALTH, ["CRITICAL_ILLNESS"]) == pytest.approx(1.15)


def test_add_on_factor_motor_lowercase():
    assert add_on_factor(ProductCode.MOTOR, ["zero_depreciation"]) == pytest.approx(1.10)


def test_add_on_factor_term_life_raises():
    with pytest.raises(PricingError):
        add_on_factor(ProductCode.TERM_LIFE, ["CRITICAL_ILLNESS"])


def test_add_on_factor_blank_entries_ignored():
    assert add_on_factor(ProductCode.HEALTH, ["", "  ", "CRITICAL_ILLNESS"]) == pytest.approx(1.15)


# --- Calculate Premium Tests ---

def test_calculate_premium_worked_example():
    # 5,00,000 x 0.03 (Health base rate) x 1.0 (age 36) x 1.0 (1 yr) = 15,000
    assert calculate_premium(
        sum_insured=500000,
        base_rate=0.03,
        age=36,
        tenure_years=1,
        product=ProductCode.HEALTH,
    ) == 15000.0


def test_calculate_premium_with_all_factors():
    # 8,00,000 x 0.025 x 1.2 (age 22 Motor) x 0.95 (2 yr) x 1.10 (ZERO_DEPRECIATION) = 25,080.0
    assert calculate_premium(
        sum_insured=800000,
        base_rate=0.025,
        age=22,
        tenure_years=2,
        product=ProductCode.MOTOR,
        add_ons=["ZERO_DEPRECIATION"],
    ) == pytest.approx(25080.0)


def test_calculate_premium_minimum():
    assert calculate_premium(
        sum_insured=10000,
        base_rate=0.004,
        age=30,
        tenure_years=1,
        product=ProductCode.TERM_LIFE,
    ) == 1000.0


def test_calculate_premium_rounding():
    # Test rounding to 2 decimal places
    res = calculate_premium(
        sum_insured=123456,
        base_rate=0.0312,
        age=30,
        tenure_years=1,
        product=ProductCode.HEALTH,
    )
    assert res == round(res, 2)


def test_calculate_premium_zero_or_negative_sum_insured():
    with pytest.raises(PricingError, match="Sum insured must be positive"):
        calculate_premium(
            sum_insured=0,
            base_rate=0.03,
            age=30,
            tenure_years=1,
            product=ProductCode.HEALTH,
        )
    with pytest.raises(PricingError, match="Sum insured must be positive"):
        calculate_premium(
            sum_insured=-1000,
            base_rate=0.03,
            age=30,
            tenure_years=1,
            product=ProductCode.HEALTH,
        )


def test_calculate_premium_min_max_bounds():
    with pytest.raises(PricingError, match="Sum insured must be at least"):
        calculate_premium(
            sum_insured=50000,
            base_rate=0.03,
            age=30,
            tenure_years=1,
            product=ProductCode.HEALTH,
            min_sum_insured=100000,
        )
    with pytest.raises(PricingError, match="Sum insured cannot exceed"):
        calculate_premium(
            sum_insured=2000000,
            base_rate=0.03,
            age=30,
            tenure_years=1,
            product=ProductCode.HEALTH,
            max_sum_insured=1000000,
        )

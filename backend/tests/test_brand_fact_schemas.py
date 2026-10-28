import pytest
from pydantic import ValidationError

from app.schemas.brand_facts import (
    CreateBrandFactRequest,
    StructuredFactValue,
)


def test_legacy_free_text_fact_is_valid():
    request = CreateBrandFactRequest(
        label="Product information",
        fact_text="The product is available in three sizes.",
    )

    assert request.fact_key is None
    assert request.structured_value is None


def test_structured_price_is_valid():
    request = CreateBrandFactRequest(
        label="Product price",
        fact_text="The approved product price is ₹1299.",
        fact_key="product_price",
        structured_value={
            "kind": "currency",
            "value": "1299",
            "unit": "INR",
        },
    )

    assert request.fact_key == "product_price"
    assert request.structured_value.value == "1299"


@pytest.mark.parametrize(
    ("fact_key", "structured_value"),
    [
        (
            "product_price",
            {"kind": "quantity", "value": "1299", "unit": "INR"},
        ),
        (
            "product_price",
            {"kind": "currency", "value": "1299", "unit": "JPY"},
        ),
        (
            "product_weight",
            {"kind": "quantity", "value": "1", "unit": "ml"},
        ),
        (
            "product_capacity",
            {"kind": "quantity", "value": "-5", "unit": "ml"},
        ),
        (
            "product_capacity",
            {"kind": "quantity", "value": "unknown", "unit": "ml"},
        ),
    ],
)
def test_invalid_structured_facts_are_rejected(fact_key, structured_value):
    with pytest.raises(ValidationError):
        CreateBrandFactRequest(
            label="Test fact",
            fact_text="Approved reference.",
            fact_key=fact_key,
            structured_value=structured_value,
        )


def test_fact_key_requires_structured_value():
    with pytest.raises(ValidationError):
        CreateBrandFactRequest(
            label="Product price",
            fact_text="Price is ₹1299.",
            fact_key="product_price",
        )


def test_structured_value_requires_fact_key():
    with pytest.raises(ValidationError):
        CreateBrandFactRequest(
            label="Product price",
            fact_text="Price is ₹1299.",
            structured_value={
                "kind": "currency",
                "value": "1299",
                "unit": "INR",
            },
        )


def test_blank_label_is_rejected():
    with pytest.raises(ValidationError):
        CreateBrandFactRequest(label="  ", fact_text="Some fact.")


def test_non_finite_structured_number_is_rejected():
    with pytest.raises(ValidationError):
        StructuredFactValue(
            kind="currency",
            value="NaN",
            unit="INR",
        )
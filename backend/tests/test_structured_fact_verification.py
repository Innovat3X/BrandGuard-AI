
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.analysis.claim_extraction import extract_structured_claims
from app.analysis.claims import check_claims
from app.analysis.contracts import FindingResult
from app.infrastructure.db.analysis_knowledge_loader import (
    ApprovedFactVersionRecord,
)
from app.services.analysis_knowledge_mappers import map_approved_facts


def make_fact(
    fact_key: str,
    value: str,
    unit: str,
    kind: str,
) -> ApprovedFactVersionRecord:
    return ApprovedFactVersionRecord(
        organization_id=uuid4(),
        fact_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        fact_text=f"Approved {fact_key}: {value} {unit}",
        source_url="https://example.com/product",
        approved_by=uuid4(),
        approved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_from=None,
        expires_at=None,
        fact_key=fact_key,
        structured_value={
            "kind": kind,
            "value": value,
            "unit": unit,
        },
    )


def analyse(content: str, fact: ApprovedFactVersionRecord):
    claims = extract_structured_claims(content)
    approved_facts = map_approved_facts([fact])

    assert approved_facts is not None

    return check_claims(
        claims,
        approved_facts,
        fact_lookup_completed=True,
    )


@pytest.mark.parametrize(
    ("content", "fact_key", "value", "unit", "kind"),
    [
        (
            "The price is ₹1299.",
            "product_price",
            "1299",
            "INR",
            "currency",
        ),
        (
            "Discount 15%.",
            "discount_percentage",
            "15",
            "%",
            "percentage",
        ),
        (
            "Warranty: 2 years.",
            "warranty_duration",
            "2",
            "years",
            "duration",
        ),
        (
            "Battery life: 10 hours.",
            "battery_life_duration",
            "10",
            "hours",
            "duration",
        ),
        (
            "Weight: 1.5 kg.",
            "product_weight",
            "1.5",
            "kg",
            "quantity",
        ),
        (
            "Capacity: 750 ml.",
            "product_capacity",
            "750",
            "ml",
            "quantity",
        ),
    ],
)
def test_matching_approved_facts_produce_no_findings(
    content,
    fact_key,
    value,
    unit,
    kind,
):
    fact = make_fact(fact_key, value, unit, kind)

    findings = analyse(content, fact)

    assert findings == []


def test_equivalent_weight_units_do_not_produce_conflict():
    # The submitted text uses grams; the approved fact uses kilograms.
    fact = make_fact(
        "product_weight",
        "1",
        "kg",
        "quantity",
    )

    findings = analyse("Weight: 1000 g.", fact)

    assert findings == []


def test_equivalent_capacity_units_do_not_produce_conflict():
    # The submitted text uses millilitres; the approved fact uses litres.
    fact = make_fact(
        "product_capacity",
        "1",
        "l",
        "quantity",
    )

    findings = analyse("Capacity: 1000 ml.", fact)

    assert findings == []


def test_conflicting_price_produces_correction_and_source_reference():
    fact = make_fact("product_price", "1299", "INR", "currency")

    findings = analyse("The price is ₹999.", fact)

    assert len(findings) == 1
    finding = findings[0]

    assert finding.result == FindingResult.CONFLICT
    assert finding.source_fact_version_id == fact.version_id
    assert finding.suggested_correction == "The price is ₹1299."
    assert finding.evidence.source_url == fact.source_url
    assert finding.location.matched_text == "₹999"


def test_missing_approved_fact_is_unsupported():
    claims = extract_structured_claims("The price is ₹999.")

    findings = check_claims(
        claims,
        [],
        fact_lookup_completed=True,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.UNSUPPORTED
    assert findings[0].source_fact_version_id is None


def test_incomplete_fact_lookup_is_not_reported_as_unsupported():
    claims = extract_structured_claims("The price is ₹999.")

    findings = check_claims(
        claims,
        [],
        fact_lookup_completed=False,
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.CHECK_UNAVAILABLE


def test_unrecognised_content_does_not_create_claims():
    assert extract_structured_claims(
        "Experience the ultimate product for your everyday needs."
    ) == ()

from enum import Enum
from uuid import UUID

import pytest

from app.services.analysis_persistence_mapper import (
    FindingMappingError,
    map_finding_for_persistence,
    map_findings_for_persistence,
)


RULE_VERSION_ID = UUID(
    "44444444-4444-4444-8444-444444444444"
)
FACT_VERSION_ID = UUID(
    "66666666-6666-4666-8666-666666666666"
)


def make_finding(**overrides):
    """Build a finding using the shared persistence field names."""

    finding = {
        "id": UUID(
            "11111111-1111-4111-8111-111111111111"
        ),
        "category": "terminology",
        "severity": "medium",
        "result": "conflict",
        "explanation": (
            "The submitted terminology conflicts with "
            "an approved brand rule."
        ),
        "evidence": {
            "submitted_text": "cheap",
            "approved_reference": "affordable",
            "source_name": "Approved terminology rule",
            "source_url": None,
        },
        "source_rule_version_id": RULE_VERSION_ID,
        "source_fact_version_id": None,
        "location": {
            "kind": "text_range",
            "start_offset": 17,
            "end_offset": 22,
            "matched_text": "cheap",
        },
        "suggested_correction": "affordable",
        "detection_method": "deterministic",
        "requires_human_review": True,
    }

    finding.update(overrides)
    return finding


def test_maps_finding_to_persistence_contract():
    finding = make_finding()

    mapped = map_finding_for_persistence(finding)

    assert mapped["category"] == "terminology"
    assert mapped["severity"] == "medium"
    assert mapped["result"] == "conflict"
    assert mapped["source_rule_version_id"] == RULE_VERSION_ID
    assert mapped["suggested_correction"] == "affordable"

    assert "id" not in mapped
    assert len(mapped["finding_fingerprint"]) == 64

    assert set(mapped) == {
        "category",
        "severity",
        "result",
        "explanation",
        "evidence",
        "source_rule_version_id",
        "source_fact_version_id",
        "location",
        "suggested_correction",
        "detection_method",
        "requires_human_review",
        "finding_fingerprint",
    }


def test_fingerprint_is_stable_across_different_finding_ids():
    first = make_finding(
        id=UUID("11111111-1111-4111-8111-111111111111")
    )
    second = make_finding(
        id=UUID("22222222-2222-4222-8222-222222222222")
    )

    first_mapped = map_finding_for_persistence(first)
    second_mapped = map_finding_for_persistence(second)

    assert (
        first_mapped["finding_fingerprint"]
        == second_mapped["finding_fingerprint"]
    )


def test_fingerprint_changes_when_rule_version_changes():
    first = map_finding_for_persistence(
        make_finding(
            source_rule_version_id=RULE_VERSION_ID
        )
    )

    second = map_finding_for_persistence(
        make_finding(
            source_rule_version_id=UUID(
                "55555555-5555-4555-8555-555555555555"
            )
        )
    )

    assert (
        first["finding_fingerprint"]
        != second["finding_fingerprint"]
    )


def test_optional_fields_are_present_as_null_when_missing():
    finding = make_finding(
        evidence=None,
        source_rule_version_id=None,
        source_fact_version_id=None,
        location=None,
        suggested_correction=None,
    )

    mapped = map_finding_for_persistence(finding)

    assert mapped["evidence"] is None
    assert mapped["source_rule_version_id"] is None
    assert mapped["source_fact_version_id"] is None
    assert mapped["location"] is None
    assert mapped["suggested_correction"] is None
    assert mapped["finding_fingerprint"]


def test_rejects_unexpected_fields():
    finding = make_finding(internal_database_id="unexpected")

    with pytest.raises(
        FindingMappingError,
        match="outside the persistence contract",
    ):
        map_finding_for_persistence(finding)


def test_rejects_missing_required_fields():
    finding = make_finding()
    del finding["explanation"]

    with pytest.raises(
        FindingMappingError,
        match="missing required persistence fields",
    ):
        map_finding_for_persistence(finding)


def test_rejects_invalid_category():
    finding = make_finding(category="invented_category")

    with pytest.raises(
        FindingMappingError,
        match="Finding field 'category'",
    ):
        map_finding_for_persistence(finding)


def test_rejects_empty_explanation():
    finding = make_finding(explanation="  ")

    with pytest.raises(
        FindingMappingError,
        match="non-empty string",
    ):
        map_finding_for_persistence(finding)


def test_deduplicates_identical_findings():
    first = make_finding(
        id=UUID("11111111-1111-4111-8111-111111111111")
    )
    second = make_finding(
        id=UUID("22222222-2222-4222-8222-222222222222")
    )

    mapped = map_findings_for_persistence([first, second])

    assert len(mapped) == 1


def test_preserves_findings_from_different_fact_versions():
    first = make_finding(
        category="factual_claim",
        source_rule_version_id=None,
        source_fact_version_id=FACT_VERSION_ID,
    )

    second = make_finding(
        category="factual_claim",
        source_rule_version_id=None,
        source_fact_version_id=UUID(
            "77777777-7777-4777-8777-777777777777"
        ),
    )

    mapped = map_findings_for_persistence([first, second])

    assert len(mapped) == 2
    assert (
        mapped[0]["finding_fingerprint"]
        != mapped[1]["finding_fingerprint"]
    )


class FindingCategory(Enum):
    TERMINOLOGY = "terminology"


def test_converts_enum_values_to_strings():
    finding = make_finding(category=FindingCategory.TERMINOLOGY)

    mapped = map_finding_for_persistence(finding)

    assert mapped["category"] == "terminology"
    assert isinstance(mapped["category"], str)
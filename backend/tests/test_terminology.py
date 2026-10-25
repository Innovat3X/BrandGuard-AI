
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.analysis.contracts import FindingResult
from app.analysis.terminology import (
    ApprovedTerminologyRule,
    check_terminology,
    find_term_occurrences,
)


RULE_VERSION_ID = UUID("11111111-1111-4111-8111-111111111111")


def make_rule(
    rule_type: str,
    term: str,
    replacement: str | None = None,
) -> ApprovedTerminologyRule:
    return ApprovedTerminologyRule(
        source_rule_version_id=RULE_VERSION_ID,
        rule_type=rule_type,
        term=term,
        replacement=replacement,
        severity="medium",
        status="approved",
        source_name="Approved terminology rule",
    )


def test_forbidden_term_detects_all_occurrences():
    rule = make_rule("forbidden_term", "cheap", "affordable")

    findings = check_terminology(
        "Our product is CHEAP and cheap.",
        [rule],
    )

    assert len(findings) == 2
    assert all(
        finding.result == FindingResult.CONFLICT
        for finding in findings
    )

    assert findings[0].location.start_offset == 15
    assert findings[0].location.end_offset == 20
    assert findings[0].location.matched_text == "CHEAP"

    assert findings[0].source_rule_version_id == RULE_VERSION_ID
    assert findings[0].suggested_correction == "affordable"


def test_required_term_is_flagged_when_missing():
    rule = make_rule("required_term", "official partner")

    findings = check_terminology(
        "Discover our new service.",
        [rule],
    )

    assert len(findings) == 1
    assert findings[0].result == FindingResult.CONFLICT
    assert findings[0].location is None
    assert findings[0].suggested_correction == "official partner"


def test_preferred_term_suggests_replacement():
    rule = make_rule("preferred_term", "customers", "clients")

    findings = check_terminology(
        "We support our customers.",
        [rule],
    )

    assert len(findings) == 1
    assert findings[0].location.matched_text == "customers"
    assert findings[0].suggested_correction == "clients"


def test_present_required_term_produces_no_finding():
    rule = make_rule("required_term", "official partner")

    findings = check_terminology(
        "We are an official partner.",
        [rule],
    )

    assert findings == []


def test_term_inside_longer_word_is_not_matched():
    assert find_term_occurrences(
        "Our catalog is ready.",
        "cat",
    ) == []


def test_preferred_term_requires_replacement():
    with pytest.raises(ValidationError):
        make_rule("preferred_term", "customers")

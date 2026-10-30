from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.v1.submissions import (
    build_analysis_idempotency_key,
    normalize_requested_checks,
)
from app.schemas.submissions import QueueAnalysisRequest


SUBMISSION_ID = UUID("12345678-1234-5678-1234-567812345678")


def test_normalize_requested_checks_preserves_none():
    assert normalize_requested_checks(None) is None


def test_normalize_requested_checks_fills_missing_checks_with_false():
    result = normalize_requested_checks({"tone": True})

    assert result == {
        "tone": True,
        "messaging": False,
        "terminology": False,
        "factual_claim": False,
    }


def test_normalize_requested_checks_preserves_explicit_selections():
    result = normalize_requested_checks(
        {
            "tone": True,
            "messaging": False,
            "terminology": True,
            "factual_claim": False,
        }
    )

    assert result == {
        "tone": True,
        "messaging": False,
        "terminology": True,
        "factual_claim": False,
    }


def test_equivalent_check_selections_generate_same_idempotency_key():
    partial = normalize_requested_checks({"tone": True})

    complete = normalize_requested_checks(
        {
            "tone": True,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        }
    )

    partial_key = build_analysis_idempotency_key(
        submission_id=SUBMISSION_ID,
        version_number=1,
        requested_checks=partial,
    )

    complete_key = build_analysis_idempotency_key(
        submission_id=SUBMISSION_ID,
        version_number=1,
        requested_checks=complete,
    )

    assert partial_key == complete_key


def test_different_check_selections_generate_different_keys():
    tone_key = build_analysis_idempotency_key(
        submission_id=SUBMISSION_ID,
        version_number=1,
        requested_checks=normalize_requested_checks({"tone": True}),
    )

    messaging_key = build_analysis_idempotency_key(
        submission_id=SUBMISSION_ID,
        version_number=1,
        requested_checks=normalize_requested_checks({"messaging": True}),
    )

    assert tone_key != messaging_key


def test_default_request_keeps_legacy_idempotency_key():
    key = build_analysis_idempotency_key(
        submission_id=SUBMISSION_ID,
        version_number=1,
        requested_checks=None,
    )

    assert key == (
        f"submission:{SUBMISSION_ID}:version:1:analysis:v1"
    )


def test_request_schema_accepts_supported_check_names():
    request = QueueAnalysisRequest(
        requested_checks={"tone": True, "factual_claim": False}
    )

    assert request.requested_checks == {
        "tone": True,
        "factual_claim": False,
    }


def test_request_schema_rejects_unknown_check_names():
    with pytest.raises(ValidationError):
        QueueAnalysisRequest(
            requested_checks={"visual_analysis": True}
        )


@pytest.mark.parametrize(
    "requested_checks",
    [
        {},
        {
            "tone": False,
            "messaging": False,
            "terminology": False,
            "factual_claim": False,
        },
    ],
)
def test_request_schema_rejects_empty_check_selection(
    requested_checks,
):
    with pytest.raises(
        ValidationError,
        match="At least one analysis check must be selected",
    ):
        QueueAnalysisRequest(requested_checks=requested_checks)


def test_request_schema_preserves_default_selection():
    request = QueueAnalysisRequest()
    assert request.requested_checks is None
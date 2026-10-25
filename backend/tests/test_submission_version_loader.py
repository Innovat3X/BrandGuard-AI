"""Tests for the database-backed submission version loader."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.infrastructure.db.submission_version_loader import (
    DatabaseSubmissionVersionLoader,
)


class FakeSession:
    """Minimal session stub for testing loader behavior."""

    def __init__(self, result):
        self.result = result
        self.statement = None

    def scalar(self, statement):
        self.statement = statement
        return self.result


def make_version(
    *,
    organization_id,
    submission_version_id,
    submission_id,
    source_type="text",
    original_text="Original submission text",
    extracted_text=None,
):
    """Create a lightweight stored-version object."""

    return SimpleNamespace(
        organization_id=organization_id,
        id=submission_version_id,
        submission_id=submission_id,
        version_number=1,
        source_type=source_type,
        original_text=original_text,
        extracted_text=extracted_text,
    )


def test_loads_exact_submission_version_within_organization():
    organization_id = uuid4()
    submission_version_id = uuid4()
    submission_id = uuid4()

    version = make_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        submission_id=submission_id,
        original_text="Original text",
        extracted_text="Extracted text",
    )
    session = FakeSession(version)
    loader = DatabaseSubmissionVersionLoader(session)

    result = loader.load_submission_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
    )

    assert result.organization_id == organization_id
    assert result.submission_version_id == submission_version_id
    assert result.submission_id == submission_id
    assert result.version_number == 1
    assert result.content_text == "Extracted text"

    assert session.statement is not None

    compiled = session.statement.compile()
    query_parameters = compiled.params.values()

    assert organization_id in query_parameters
    assert submission_version_id in query_parameters


def test_uses_original_text_when_extracted_text_is_unavailable():
    organization_id = uuid4()
    submission_version_id = uuid4()
    submission_id = uuid4()

    version = make_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        submission_id=submission_id,
        original_text="Original text fallback",
        extracted_text=None,
    )
    loader = DatabaseSubmissionVersionLoader(FakeSession(version))

    result = loader.load_submission_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
    )

    assert result.content_text == "Original text fallback"


def test_raises_lookup_error_when_version_does_not_exist():
    loader = DatabaseSubmissionVersionLoader(FakeSession(None))

    with pytest.raises(
        LookupError,
        match="Submission version not found",
    ):
        loader.load_submission_version(
            organization_id=uuid4(),
            submission_version_id=uuid4(),
        )


def test_rejects_file_submission_until_file_extraction_is_implemented():
    organization_id = uuid4()
    submission_version_id = uuid4()
    submission_id = uuid4()

    version = make_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        submission_id=submission_id,
        source_type="file",
        original_text=None,
    )
    loader = DatabaseSubmissionVersionLoader(FakeSession(version))

    with pytest.raises(
        NotImplementedError,
        match="supports text submissions only",
    ):
        loader.load_submission_version(
            organization_id=organization_id,
            submission_version_id=submission_version_id,
        )


def test_raises_value_error_when_text_content_is_missing():
    organization_id = uuid4()
    submission_version_id = uuid4()
    submission_id = uuid4()

    version = make_version(
        organization_id=organization_id,
        submission_version_id=submission_version_id,
        submission_id=submission_id,
        source_type="text",
        original_text=None,
        extracted_text=None,
    )
    loader = DatabaseSubmissionVersionLoader(FakeSession(version))

    with pytest.raises(
        ValueError,
        match="no available content",
    ):
        loader.load_submission_version(
            organization_id=organization_id,
            submission_version_id=submission_version_id,
        )
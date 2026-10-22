from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.infrastructure.db import Base


EXPECTED_TABLES = {
    "organizations",
    "users",
    "organization_memberships",
    "brand_rules",
    "brand_rule_versions",
    "brand_facts",
    "brand_fact_versions",
    "brand_assets",
    "submissions",
    "submission_versions",
    "analysis_jobs",
    "findings",
    "review_actions",
    "audit_events",
    "notifications",
}


def _unique_constraints(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]

    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_key_constraints(
    table_name: str,
) -> set[tuple[tuple[str, ...], tuple[str, ...]]]:
    table = Base.metadata.tables[table_name]
    constraints = set()

    for constraint in table.constraints:
        if not isinstance(constraint, ForeignKeyConstraint):
            continue

        local_columns = tuple(
            column.name for column in constraint.columns
        )
        referenced_columns = tuple(
            element.target_fullname
            for element in constraint.elements
        )

        constraints.add((local_columns, referenced_columns))

    return constraints


def _check_constraint_sql(table_name: str) -> str:
    table = Base.metadata.tables[table_name]

    return " ".join(
        str(constraint.sqltext).lower()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    )


def test_all_contract_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_membership_is_unique_per_organization_and_user() -> None:
    assert ("organization_id", "user_id") in _unique_constraints(
        "organization_memberships"
    )


def test_brand_rule_versions_have_unique_version_numbers() -> None:
    assert ("rule_id", "version_number") in _unique_constraints(
        "brand_rule_versions"
    )


def test_brand_fact_versions_have_unique_version_numbers() -> None:
    assert ("fact_id", "version_number") in _unique_constraints(
        "brand_fact_versions"
    )


def test_submission_versions_have_unique_version_numbers() -> None:
    assert ("submission_id", "version_number") in _unique_constraints(
        "submission_versions"
    )


def test_analysis_jobs_have_organization_scoped_idempotency() -> None:
    assert ("organization_id", "idempotency_key") in _unique_constraints(
        "analysis_jobs"
    )


def test_findings_prevent_duplicates_within_a_job() -> None:
    assert ("analysis_job_id", "finding_fingerprint") in _unique_constraints(
        "findings"
    )


def test_rule_versions_match_parent_organization() -> None:
    constraints = _foreign_key_constraints("brand_rule_versions")

    assert (
        ("organization_id", "rule_id"),
        ("brand_rules.organization_id", "brand_rules.id"),
    ) in constraints


def test_fact_versions_match_parent_organization() -> None:
    constraints = _foreign_key_constraints("brand_fact_versions")

    assert (
        ("organization_id", "fact_id"),
        ("brand_facts.organization_id", "brand_facts.id"),
    ) in constraints


def test_submission_versions_match_parent_organization() -> None:
    constraints = _foreign_key_constraints("submission_versions")

    assert (
        ("organization_id", "submission_id"),
        ("submissions.organization_id", "submissions.id"),
    ) in constraints


def test_analysis_jobs_match_submission_version_organization() -> None:
    constraints = _foreign_key_constraints("analysis_jobs")

    assert (
        ("organization_id", "submission_version_id"),
        (
            "submission_versions.organization_id",
            "submission_versions.id",
        ),
    ) in constraints


def test_findings_reference_the_exact_version_processed_by_the_job() -> None:
    constraints = _foreign_key_constraints("findings")

    assert (
        (
            "organization_id",
            "analysis_job_id",
            "submission_version_id",
        ),
        (
            "analysis_jobs.organization_id",
            "analysis_jobs.id",
            "analysis_jobs.submission_version_id",
        ),
    ) in constraints


def test_review_actions_reference_a_version_of_the_selected_submission() -> None:
    constraints = _foreign_key_constraints("review_actions")

    assert (
        ("submission_id", "submission_version_id"),
        ("submission_versions.submission_id", "submission_versions.id"),
    ) in constraints


def test_submission_status_values_match_the_contract() -> None:
    sql = _check_constraint_sql("submissions")

    for status in (
        "draft",
        "submitted",
        "processing",
        "under_review",
        "changes_requested",
        "approved",
        "rejected",
        "failed_needs_attention",
    ):
        assert f"'{status}'" in sql


def test_analysis_job_status_values_match_the_contract() -> None:
    sql = _check_constraint_sql("analysis_jobs")

    for status in (
        "queued",
        "processing",
        "completed",
        "partial",
        "failed",
    ):
        assert f"'{status}'" in sql


def test_asset_size_cannot_be_negative() -> None:
    sql = _check_constraint_sql("brand_assets")

    assert "size_bytes >= 0" in sql

# BrandGuard AI — Database Contract v1

## 1. General rules

- Database: PostgreSQL.
- ORM: SQLAlchemy.
- Migrations: Alembic.
- Primary identifiers: UUID.
- Timestamps: timezone-aware UTC.
- Database access must go through the repository/data-access layer.
- The frontend must never connect directly to the database.
- Every organisation-owned record must be tenant-scoped.
- Use foreign keys, unique constraints and indexes where appropriate.
- Never store plaintext passwords.

## 2. Organisations and users

### organizations
- id
- name
- created_at

### users
- id
- full_name
- email
- password_hash
- is_active
- created_at
- updated_at

Email must be normalised and unique.

### memberships
- id
- organization_id
- user_id
- role
- created_at

Role values:
- admin
- creator
- reviewer

Enforce a unique membership for each organization_id + user_id.

## 3. Brand rules and versions

### brand_rules
- id
- organization_id
- title
- created_by
- created_at

### brand_rule_versions
- id
- rule_id
- version_number
- category
- description
- rule_text
- severity
- status
- created_by
- approved_by
- approved_at
- effective_from
- created_at

Rule version status values:
- draft
- approved
- archived

Rule category values must include at least:
- tone
- terminology
- messaging
- other

Severity values:
- info
- low
- medium
- high

Enforce a unique rule_id + version_number combination.
An approved version must not be silently overwritten.
Findings must point to the exact rule version used.

## 4. Approved facts and versions

### brand_facts
- id
- organization_id
- label
- created_by
- created_at

### brand_fact_versions
- id
- fact_id
- version_number
- fact_text
- source_url
- status
- effective_from
- expires_at
- created_by
- approved_by
- approved_at
- created_at

Fact version status values:
- draft
- approved
- archived

Enforce a unique fact_id + version_number combination.
A fact used in an analysis must be traceable to its exact version.

## 5. Brand assets

### brand_assets
- id
- organization_id
- name
- asset_type
- storage_key
- media_type
- size_bytes
- checksum_sha256
- status
- metadata
- created_by
- approved_by
- approved_at
- created_at

Store file bytes in private file storage, not in public frontend
assets. Store only the private storage reference and relevant
metadata in PostgreSQL.

## 6. Submissions and immutable versions

### submissions
- id
- organization_id
- title
- status
- current_version_number
- created_by
- created_at
- updated_at

### submission_versions
- id
- organization_id
- submission_id
- version_number
- source_type
- original_text
- storage_key
- original_filename
- media_type
- sha256
- extracted_text
- created_by
- created_at

source_type values:
- text
- file

Enforce a unique submission_id + version_number combination.
Preserve original content. Do not overwrite an existing version.
A file upload must retain its original privately stored file.
For text submissions, retain the original submitted text.

## 7. Analysis jobs

### analysis_jobs
- id
- organization_id
- submission_version_id
- status
- idempotency_key
- started_at
- completed_at
- error_code
- error_message
- created_at
- updated_at

Status values:
- queued
- processing
- completed
- partial
- failed

Retries must be safe and must not create duplicate findings
for the same logical analysis result.

## 8. Findings

### findings
- id
- organization_id
- analysis_job_id
- submission_version_id
- category
- severity
- result
- explanation
- evidence
- source_rule_version_id
- source_fact_version_id
- location
- suggested_correction
- detection_method
- created_at

JSON fields may use PostgreSQL JSONB when structured data
is required.

A finding must refer to the exact submission version analysed.
Its rule/fact version references may be null when not applicable.

## 9. Review actions and audit

### review_actions
- id
- organization_id
- submission_id
- submission_version_id
- reviewer_id
- action
- comment
- created_at

action values:
- approve
- request_changes
- reject

### audit_events
- id
- organization_id
- actor_user_id
- action
- entity_type
- entity_id
- details
- created_at

Review decisions and changes to authoritative brand information
must be auditable.

## 10. Notifications

### notifications
- id
- organization_id
- user_id
- type
- payload
- read_at
- created_at

Notifications are in-app records for the initial scope.
External email, SMS and chat notifications are excluded.

## 11. Required relationships

- One organization has many users through memberships.
- One organization has many brand rules, facts, assets and submissions.
- One brand rule has many rule versions.
- One brand fact has many fact versions.
- One submission has many immutable submission versions.
- One submission version may have multiple analysis jobs over time.
- One analysis job has many findings.
- A finding belongs to one analysis job and one submission version.
- One submission can have multiple review actions.
- Audit events belong to an organization and identify the
  actor and affected entity where applicable.

## 12. Required integrity and security

- Apply foreign-key and uniqueness constraints.
- Index commonly queried organisation, submission and status fields.
- Scope repository queries to the authenticated organisation.
- Validate that referenced rule/fact versions belong to the same
  organisation as the submission being analysed.
- Do not delete approved rule/fact versions still referenced by findings.
- Never use a mutable "latest rule" reference in historical findings;
  store the exact version identifier.
- Migrations must be committed and reviewed.

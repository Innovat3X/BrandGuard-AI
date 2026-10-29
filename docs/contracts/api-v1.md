
# BrandGuard AI — API Contract v1

## 1. Purpose

This document is the shared API specification for BrandGuard AI.
All frontend and backend implementations must follow it.

## 2. Common conventions

- Base API path: /api/v1
- Data format: JSON, except file-upload requests.
- Field naming: snake_case.
- Record identifiers: UUID strings.
- Timestamps: ISO 8601 in UTC.
- Authentication: Bearer JWT token.
- All organisation-owned records must be scoped to the authenticated user's organisation.
- The backend is authoritative for permissions, statuses, findings and approval decisions.
- The frontend must never connect directly to PostgreSQL, RabbitMQ, private file storage or an AI provider.

## 3. Standard error response

Errors must use this structure:

{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [],
    "request_id": "request-id"
  }
}

Use meaningful HTTP status codes. Do not expose stack traces,
passwords, tokens or internal secrets in API responses.

## 4. Authentication

### POST /api/v1/auth/register

Purpose: register the initial user and create an organisation.

Request:
{
  "full_name": "Example User",
  "email": "user@example.com",
  "password": "example-password",
  "organization_name": "Example Organisation"
}

Response: access token, token type, expiry, user, organisation
and initial role.

The initial user is an organisation administrator.
Passwords must be hashed. Never store or return plaintext passwords.

### POST /api/v1/auth/login

Request:
{
  "email": "user@example.com",
  "password": "example-password"
}

Response: access token, token type, expiry, user, organisation
and role.

### GET /api/v1/me

Purpose: return the authenticated user's identity, organisation
and role. Requires authentication.

Initial role values:
- admin
- creator
- reviewer

## 5. Brand rules

### GET /api/v1/brand/rules

Return brand rules visible to the authenticated organisation.
Support filtering by status when implemented.

### POST /api/v1/brand/rules

Create a draft brand rule.

Request:
{
  "title": "Approved terminology",
  "category": "terminology",
  "description": "Terminology requirement",
  "rule_text": "Use the approved product name",
  "severity": "medium"
}

### PUT /api/v1/brand/rules/{rule_id}

Update a draft rule. Do not silently modify historical approved
rule versions. Changes to an approved rule must preserve the
previous approved version.

### POST /api/v1/brand/rules/{rule_id}/approve

Approve the applicable draft version. Only an authorised
organisation administrator or reviewer with the required
permission may approve it.

## 6. Approved facts

### GET /api/v1/brand/facts

Return facts and their version/approval information for the
authenticated organisation.

### POST /api/v1/brand/facts

Create a draft fact.

Request:
{
  "label": "Product price",
  "fact_text": "The currently approved product price is ₹999",
  "source_url": "https://example.com/source"
}

### POST /api/v1/brand/facts/{fact_id}/approve

Approve the applicable draft fact version.

Approved facts and their source information must remain
traceable by version.

## 7. Brand assets

### POST /api/v1/brand/assets

Upload a brand asset using multipart/form-data.

Fields include:
- name
- asset_type
- file

Validate file type, size and contents. Store uploaded files
privately. Do not expose internal storage paths or public URLs
for confidential assets.

## 8. Submission workflow

### POST /api/v1/submissions

Create a submission and its first immutable version.

Use multipart/form-data with:
- title
- text, for pasted text; OR
- file, for an uploaded file

Exactly one content source must be supplied.

Supported initial file types:
TXT, PDF, DOCX, PNG, JPG and JPEG.

Response includes:
- submission id
- version number
- submission status
- creation timestamp

A newly created submission starts in submitted status.

### POST /api/v1/submissions/{submission_id}/analysis


Request body (optional):

{
  "version_number": 1,
  "requested_checks": {
    "tone": true,
    "terminology": true,
    "factual_claim": true
  }
}

`requested_checks` specifies which supported analysis checks
should run. Each key identifies a check, and its Boolean value
indicates whether it was requested. If omitted, the backend
uses its documented default checks.

A check that is not run must not be reported as having passed.
Unsupported or unavailable checks must be represented honestly
in the analysis outcome.

Queue analysis of the specified version. The request may contain
a version number; if omitted, analyse the current version.

Response: HTTP 202 Accepted.

Example:
{
  "job_id": "uuid",
  "submission_id": "uuid",
  "version_number": 1,
  "status": "queued"
}

This endpoint queues work. It must not make the frontend wait
for the entire analysis to finish.

### GET /api/v1/analysis-jobs/{job_id}

Return job status and any safe, user-readable failure details.

### GET /api/v1/submissions/{submission_id}/findings?version=1

Return findings for the requested immutable submission version.
Do not mix findings from different versions.

### POST /api/v1/submissions/{submission_id}/versions

Create a new immutable version after changes are requested.
Use the same content-source rules as submission creation.

The old version and its findings must remain available for
history. A revision must not overwrite the original.

## 9. Human review

### POST /api/v1/submissions/{submission_id}/review-actions

Request:
{
  "action": "request_changes",
  "comment": "Please correct the unsupported claim."
}

Allowed actions:
- approve
- request_changes
- reject

The submission must be under_review. A comment is required
for request_changes and reject.

Only an authorised reviewer may submit a review action.
Approval must be a backend-enforced decision.

## 10. Submission statuses

Allowed values:
- draft
- submitted
- processing
- under_review
- changes_requested
- approved
- rejected
- failed_needs_attention

## 11. Analysis job statuses

Allowed values:
- queued
- processing
- completed
- partial
- failed

A partially completed analysis must not be represented as
a fully completed analysis.

## 12. Security rules

- Validate every request on the backend.
- Enforce role permissions on the backend.
- Scope every read and write to the authenticated organisation.
- Never trust an organisation_id supplied by a client as
  proof of access.
- Keep uploaded files private.
- Do not automatically publish or approve content.
- AI findings are advisory; human review remains authoritative.

## 13. Contract change procedure

Before changing an endpoint, field, status or response:
1. Explain the required change to the affected members.
2. Update this document.
3. Update dependent backend and frontend code.
4. Update tests.
5. Commit the agreed change before building further on it.

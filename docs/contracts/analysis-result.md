
# BrandGuard AI — Analysis Result Contract v1

## 1. Purpose

This contract defines the structure and meaning of every
finding returned by the content-analysis pipeline.

Anusha implements the analysis output according to this contract.
Girish persists the defined fields.
Bhumika exposes the data through the API.
Tanishqa renders the findings in the frontend.

## 2. Finding category

Allowed values:
- tone
- terminology
- messaging
- factual_claim
- visual
- accessibility
- other

## 3. Severity

Allowed values:
- info
- low
- medium
- high

Severity indicates the importance of the issue, not whether the
finding is definitely true.

## 4. Result classification

Allowed values:
- conflict
- unsupported
- inconclusive
- check_unavailable

Meanings:

- conflict: submitted content conflicts with an applicable
  approved rule or fact.
- unsupported: the submitted content makes a claim that could
  not be supported by the applicable approved evidence.
- inconclusive: the available information is insufficient to
  determine whether the content complies.
- check_unavailable: the relevant check could not be completed.

Missing evidence is not proof that a claim is false.
Do not report unsupported as a definitive falsehood.

## 5. Detection method

Allowed values:
- deterministic
- ai_assisted
- ocr
- visual_check

Use deterministic checks for exact comparisons where appropriate.
AI-assisted results must be validated before persistence.

## 6. Finding structure

Every finding must contain:

- id
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
- requires_human_review

Use null when an optional field is not applicable.
Do not fabricate evidence, sources or approved facts.

## 7. Evidence object

The evidence object may contain:
- submitted_text
- approved_reference
- source_name
- source_url

Values may be null when evidence is unavailable.
An explanation must distinguish observed conflicts from
uncertainty or missing evidence.

## 8. Location object

For text findings:
{
  "kind": "text_range",
  "start_offset": 0,
  "end_offset": 12,
  "matched_text": "example text"
}

Offsets are zero-based Unicode code-point positions into the
exact extracted/submitted text, with end_offset exclusive.

For image findings:
{
  "kind": "image_bbox",
  "x": 0.1,
  "y": 0.2,
  "width": 0.3,
  "height": 0.1
}

Image bounding-box values are normalised between 0 and 1
relative to the image dimensions.

Use null when a reliable location cannot be identified.

## 9. Suggested corrections

- A suggestion is advisory.
- A suggestion must never silently overwrite original content.
- Preserve the user's intended meaning where possible.
- Do not invent product facts, prices, dates, guarantees or claims.
- A reviewer or creator must be able to inspect the original
  content and the suggestion separately.

## 10. Example finding

{
  "id": "finding-uuid",
  "category": "terminology",
  "severity": "medium",
  "result": "conflict",
  "explanation": "The submitted text uses a term that conflicts
    with the approved terminology rule.",
  "evidence": {
    "submitted_text": "Example term",
    "approved_reference": "Approved term",
    "source_name": "Approved terminology rule",
    "source_url": null
  },
  "source_rule_version_id": "rule-version-uuid",
  "source_fact_version_id": null,
  "location": {
    "kind": "text_range",
    "start_offset": 0,
    "end_offset": 12,
    "matched_text": "Example term"
  },
  "suggested_correction": "Approved term",
  "detection_method": "deterministic",
  "requires_human_review": true
}

The IDs and example wording above are illustrative only.

## 11. Analysis response

A completed or partially completed job must be representable as:

{
  "job_id": "job-uuid",
  "submission_id": "submission-uuid",
  "submission_version_id": "submission-version-uuid",
  "status": "completed",
  "findings": [],
  "check_outcomes": [
    {
      "category": "terminology",
      "status": "supported",
      "message": "Terminology checks completed.",
      "detection_method": "deterministic",
      "assessed_count": 1,
      "scope": "submitted_text"
    }
  ],
  "summary": {
    "info": 0,
    "low": 0,
    "medium": 0,
    "high": 0,
    "total": 0
  }
}

The API may wrap findings in pagination metadata, but it must
preserve the defined finding fields.

The `check_outcomes` array records the status of each analysis check,
including checks that completed successfully, found issues, were
inconclusive, unavailable, intentionally disabled, not assessed, or
limited in coverage. Each outcome contains:

- `category`: the check category.
- `status`: `supported`, `issues_found`, `inconclusive`,
  `check_unavailable`, `disabled`, `not_assessed`, or
  `coverage_limited`.
- `message`: a user-readable description of the check result.
- `detection_method`: the detection method, or null when not applicable.
- `assessed_count`: a non-negative count of assessed items.
- `scope`: optional description of the assessed scope.

A disabled check is not a failed check and must not by itself make
the analysis partial. These outcomes are persisted with the job and
returned by the analysis-job status endpoint. Before any outcomes
have been persisted, the endpoint returns an empty array.

## 12. Human oversight and retries

- Findings are advisory; they do not approve or reject content.
- Only an authorised reviewer may change the review status.
- Analysis must operate on a specific immutable submission version.
- A failed check must not be presented as a successful check.
- A retry must not duplicate persisted findings for the same
  logical analysis result.
- Partial success must be represented by the partial job status.

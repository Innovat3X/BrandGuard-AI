from datetime import datetime, timezone
from uuid import uuid4

from app.schemas.submissions import AnalysisJobStatusResponse


def build_response(**overrides):
    values = {
        "job_id": uuid4(),
        "submission_id": uuid4(),
        "version_number": 1,
        "status": "completed",
        "attempts": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    values.update(overrides)
    return AnalysisJobStatusResponse(**values)


def test_analysis_job_status_response_defaults_to_empty_check_outcomes():
    response = build_response()

    assert response.check_outcomes == []


def test_analysis_job_status_response_validates_persisted_check_outcomes():
    response = build_response(
        check_outcomes=[
            {
                "category": "terminology",
                "status": "disabled",
                "message": "Terminology checking was not requested.",
                "detection_method": None,
                "assessed_count": 0,
                "scope": None,
            }
        ]
    )

    assert len(response.check_outcomes) == 1
    assert response.check_outcomes[0].category.value == "terminology"
    assert response.check_outcomes[0].status.value == "disabled"
    assert response.check_outcomes[0].assessed_count == 0

    serialized = response.model_dump(mode="json")
    assert serialized["check_outcomes"][0]["status"] == "disabled"

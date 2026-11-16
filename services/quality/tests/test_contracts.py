import pytest
from pydantic import ValidationError

from quality_service.schemas import InspectionReport


def report(**overrides):
    values = {
        "grade": "A",
        "moisture_pct": 12.5,
        "pest_found": False,
        "weight_kg": 80,
        "result": "PASS",
    }
    values.update(overrides)
    return InspectionReport(**values)


def test_pass_report_accepts_quality_measurements():
    result = report()
    assert result.result == "PASS"
    assert result.grade == "A"


def test_failed_harvest_report_requires_resolution():
    with pytest.raises(ValidationError):
        report(result="FAIL")


def test_lower_grade_resolution_requires_accepted_grade():
    with pytest.raises(ValidationError):
        report(result="FAIL", resolution="ACCEPT_LOWER_GRADE")


def test_failed_harvest_can_be_reharvested():
    result = report(result="FAIL", resolution="REHARVEST")
    assert result.resolution == "REHARVEST"


def test_lower_grade_resolution_records_accepted_grade():
    result = report(result="FAIL", resolution="ACCEPT_LOWER_GRADE", accepted_grade="C")
    assert result.accepted_grade == "C"


def test_accepted_grade_must_be_lower_than_inspected_grade():
    with pytest.raises(ValidationError):
        report(result="FAIL", resolution="ACCEPT_LOWER_GRADE", accepted_grade="A")

import re

from schools.models import Student


def _normalize(value):
    """Keep digits only and drop leading zeros: '2025-001' == '02025001'."""
    return re.sub(r"\D", "", value or "").lstrip("0")


def find_student_by_id(assessment, detected_id):
    """
    Return the active, enrolled student whose ID matches the detected ID,
    ignoring dashes and leading zeros. Returns None if the ID has unreadable
    digits ("?"), matches nobody, or matches more than one student.
    """
    if not detected_id or "?" in detected_id:
        return None

    target = _normalize(detected_id)
    if not target:
        return None

    classroom = assessment.classroom

    candidates = Student.objects.filter(
        school=classroom.school,
        is_active=True,
        enrollments__classroom=classroom,
        enrollments__status="ENROLLED",
    ).distinct()

    matches = [s for s in candidates if _normalize(s.student_id) == target]
    return matches[0] if len(matches) == 1 else None
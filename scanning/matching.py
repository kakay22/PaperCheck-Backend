from schools.models import Student


def find_student_by_id(assessment, detected_id):
    """
    Return the active, enrolled student whose ID equals the detected ID,
    or None. IDs containing "?" (unreadable digits) never match.
    """
    if not detected_id or "?" in detected_id:
        return None

    classroom = assessment.classroom

    return Student.objects.filter(
        school=classroom.school,
        student_id=detected_id,
        is_active=True,
        enrollments__classroom=classroom,
        enrollments__status="ENROLLED",
    ).first()
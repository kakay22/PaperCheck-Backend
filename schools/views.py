from rest_framework import viewsets
from rest_framework.permissions import (
    BasePermission,
    IsAuthenticated,
    SAFE_METHODS,
)
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import School, Classroom, Student, Enrollment
from .serializers import (
    SchoolSerializer,
    ClassroomSerializer,
    StudentSerializer,
    EnrollmentSerializer,
)


def is_school_admin(user):
    return (
        user.is_authenticated
        and (user.is_superuser or user.role == "SCHOOL_ADMIN")
    )


class IsSchoolAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_school_admin(request.user)


class IsSchoolAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        return (
            request.method in SAFE_METHODS
            or is_school_admin(request.user)
        )


class SchoolViewSet(viewsets.ModelViewSet):
    serializer_class = SchoolSerializer
    permission_classes = [IsSchoolAdminOrReadOnly]

    def get_queryset(self):
        queryset = School.objects.all()

        if not is_school_admin(self.request.user):
            return queryset.filter(is_active=True)

        return queryset


class ClassroomViewSet(viewsets.ModelViewSet):
    serializer_class = ClassroomSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Classroom.objects.select_related("school", "teacher")

        if is_school_admin(self.request.user):
            return queryset

        return queryset.filter(teacher=self.request.user)

    def perform_create(self, serializer):
        serializer.save(teacher=self.request.user)


class StudentViewSet(viewsets.ModelViewSet):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Student.objects.select_related("school")

        if is_school_admin(self.request.user):
            return queryset

        return queryset.filter(
            enrollments__classroom__teacher=self.request.user
        ).distinct()


class EnrollmentViewSet(viewsets.ModelViewSet):
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Enrollment.objects.select_related(
            "student",
            "classroom",
            "classroom__teacher",
        )

        if is_school_admin(self.request.user):
            return queryset

        return queryset.filter(classroom__teacher=self.request.user)

    def perform_create(self, serializer):
        classroom = serializer.validated_data["classroom"]
        student = serializer.validated_data["student"]

        if not is_school_admin(self.request.user):
            if classroom.teacher_id != self.request.user.id:
                raise PermissionDenied(
                    "You cannot enroll students in another teacher's class."
                )

        if classroom.school_id != student.school_id:
            raise ValidationError(
                "The student and classroom must belong to the same school."
            )

        serializer.save()

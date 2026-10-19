from rest_framework import serializers
from .models import School, Classroom, Student, Enrollment


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "code", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class ClassroomSerializer(serializers.ModelSerializer):
    teacher_username = serializers.CharField(
        source="teacher.username",
        read_only=True,
    )

    class Meta:
        model = Classroom
        fields = [
            "id",
            "school",
            "name",
            "academic_year",
            "teacher",
            "teacher_username",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "teacher", "created_at"]

    def validate_teacher(self, teacher):
        if not teacher.is_active:
            raise serializers.ValidationError("The teacher account is inactive.")
        if teacher.role != "TEACHER" and not teacher.is_superuser:
            raise serializers.ValidationError("Select a teacher account.")
        return teacher


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            "id", "school", "student_id", "first_name",
            "middle_name", "last_name", "full_name",
            "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at", "full_name"]

    def get_full_name(self, obj):
        return " ".join(
            part for part in [
                obj.first_name, obj.middle_name, obj.last_name
            ] if part
        )


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    classroom_name = serializers.CharField(
        source="classroom.name",
        read_only=True,
    )

    class Meta:
        model = Enrollment
        fields = [
            "id", "classroom", "classroom_name",
            "student", "student_name", "status", "enrolled_at",
        ]
        read_only_fields = ["id", "enrolled_at"]

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"
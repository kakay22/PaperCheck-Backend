from rest_framework import serializers
from .models import School, Classroom, Student, Enrollment
from django.utils.text import slugify


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "code", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]

def _generate_school_code(name):
    """Build a unique school code from the name, respecting max_length."""
    max_length = School._meta.get_field("code").max_length or 20
    base = (slugify(name).replace("-", "").upper() or "SCHOOL")[:max_length]

    code = base
    counter = 2
    while School.objects.filter(code=code).exists():
        suffix = str(counter)
        code = base[: max_length - len(suffix)] + suffix
        counter += 1

    return code


def _get_or_create_school(name):
    """Find a school by name (case-insensitive) or create it."""
    name = " ".join(name.split())

    school = School.objects.filter(name__iexact=name).first()
    if school:
        if not school.is_active:
            raise serializers.ValidationError(
                {"school_name": "This school is inactive."}
            )
        return school

    return School.objects.create(name=name, code=_generate_school_code(name))

class ClassroomSerializer(serializers.ModelSerializer):
    teacher_username = serializers.CharField(
        source="teacher.username",
        read_only=True,
    )
    school_name = serializers.CharField(
        write_only=True,
        required=False,
        max_length=150,
    )

    class Meta:
        model = Classroom
        fields = [
            "id",
            "school",
            "school_name",
            "name",
            "academic_year",
            "teacher",
            "teacher_username",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "teacher", "created_at"]
        extra_kwargs = {"school": {"required": False}}
        # The auto-generated unique-together validator would demand `school`,
        # so uniqueness is checked manually in validate() instead.
        validators = []

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["school_name"] = instance.school.name
        return data

    def validate(self, attrs):
        school_name = (attrs.get("school_name") or "").strip()

        if self.instance is None and not attrs.get("school") and not school_name:
            raise serializers.ValidationError(
                {"school_name": "Enter the school name."}
            )

        if school_name:
            attrs["school"] = _get_or_create_school(school_name)

        attrs.pop("school_name", None)

        school = attrs.get("school") or (self.instance and self.instance.school)
        name = attrs.get("name") or (self.instance and self.instance.name)
        year = attrs.get("academic_year") or (
            self.instance and self.instance.academic_year
        )

        duplicates = Classroom.objects.filter(
            school=school, name=name, academic_year=year
        )
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)

        if duplicates.exists():
            raise serializers.ValidationError(
                "This classroom already exists for that school and academic year."
            )

        return attrs


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
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError, PermissionDenied

from .models import Assessment, Question, QuestionOption

from schools.views import is_school_admin
from .models import Assessment, Question
from .serializers import AssessmentSerializer, QuestionSerializer


class AssessmentViewSet(viewsets.ModelViewSet):
    serializer_class = AssessmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Assessment.objects.select_related(
            "classroom", "classroom__school", "created_by"
        )

        if is_school_admin(self.request.user):
            return qs

        return qs.filter(classroom__teacher=self.request.user)

    def perform_create(self, serializer):
        classroom = serializer.validated_data["classroom"]

        if not is_school_admin(self.request.user):
            if classroom.teacher_id != self.request.user.id:
                raise PermissionDenied(
                    "You can create assessments only for your own classes."
                )

        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        assessment = self.get_object()

        if assessment.status != Assessment.Status.DRAFT:
            raise PermissionDenied(
                "Only draft assessments can be edited."
            )

        serializer.save()

    
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        assessment = self.get_object()

        # Only a school administrator or the assessment's teacher
        # may publish it.
        is_admin = (
            request.user.is_superuser
            or request.user.role == "SCHOOL_ADMIN"
        )

        if not is_admin and assessment.created_by_id != request.user.id:
            raise PermissionDenied(
                "You cannot publish another teacher's assessment."
            )

        if assessment.status != "DRAFT":
            raise ValidationError(
                "Only draft assessments can be published."
            )

        questions = Question.objects.filter(assessment=assessment)

        if not questions.exists():
            raise ValidationError(
                "Add at least one question before publishing."
            )

        errors = []

        for question in questions:
            if question.question_type == "MULTIPLE_CHOICE":
                options = QuestionOption.objects.filter(question=question)
                correct_count = options.filter(is_correct=True).count()

                if options.count() < 2:
                    errors.append(
                        f"Question {question.order}: add at least two options."
                    )

                if correct_count != 1:
                    errors.append(
                        f"Question {question.order}: mark exactly one correct option."
                    )

            if question.points <= 0:
                errors.append(
                    f"Question {question.order}: points must be greater than zero."
                )

        if errors:
            raise ValidationError({"questions": errors})

        assessment.status = "PUBLISHED"
        assessment.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "message": "Assessment published successfully.",
                "assessment": self.get_serializer(assessment).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        assessment = self.get_object()

        is_admin = (
            request.user.is_superuser
            or request.user.role == "SCHOOL_ADMIN"
        )

        if not is_admin and assessment.created_by_id != request.user.id:
            raise PermissionDenied(
                "You cannot close another teacher's assessment."
            )

        if assessment.status != "PUBLISHED":
            raise ValidationError(
                "Only published assessments can be closed."
            )

        assessment.status = "CLOSED"
        assessment.save(update_fields=["status", "updated_at"])

        return Response(
            {
                "message": "Assessment closed successfully.",
                "assessment": self.get_serializer(assessment).data,
            },
            status=status.HTTP_200_OK,
        )



class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Question.objects.select_related(
            "assessment", "assessment__classroom"
        ).prefetch_related("options")

        assessment_id = self.request.query_params.get("assessment")
        if assessment_id and assessment_id.isdigit():
            qs = qs.filter(assessment_id=int(assessment_id))

        if is_school_admin(self.request.user):
            return qs.order_by("order")

        return qs.filter(
            assessment__classroom__teacher=self.request.user
        ).order_by("order")

    def perform_create(self, serializer):
        assessment = serializer.validated_data["assessment"]

        if assessment.status != Assessment.Status.DRAFT:
            raise PermissionDenied(
                "Questions can only be added to draft assessments."
            )

        if not is_school_admin(self.request.user):
            if assessment.classroom.teacher_id != self.request.user.id:
                raise PermissionDenied(
                    "You cannot edit another teacher's assessment."
                )

        serializer.save()

    def perform_update(self, serializer):
        question = self.get_object()

        if question.assessment.status != Assessment.Status.DRAFT:
            raise PermissionDenied(
                "Questions in published assessments cannot be edited."
            )

        serializer.save()

    def perform_destroy(self, instance):
        if instance.assessment.status != Assessment.Status.DRAFT:
            raise PermissionDenied(
                "Questions in published assessments cannot be deleted."
            )

        instance.delete()
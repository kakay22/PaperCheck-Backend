from decimal import Decimal

from django.shortcuts import render


from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from schools.models import Enrollment, Student
from grading.models import Submission, GradeAuditLog, StudentAnswer

from .omr import detect_answers
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from rest_framework import status

import os

from django.db import transaction
from django.utils import timezone

from rest_framework import serializers, status as http_status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import ScanJob, ScanResult
from .models import ScanJob, ScanFile

from assessments.models import Assessment, QuestionOption
from .answer_sheets import generate_answer_sheet


class AnswerSheetDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, assessment_id):
        assessment = get_object_or_404(
            Assessment.objects.select_related(
                "classroom",
                "created_by",
            ),
            pk=assessment_id,
        )

        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        if not is_admin and assessment.classroom.teacher_id != user.id:
            raise PermissionDenied(
                "You cannot download another teacher's answer sheet."
            )

        if assessment.status != "PUBLISHED":
            raise ValidationError(
                "Only published assessments can have answer sheets downloaded."
            )

        pdf_buffer = generate_answer_sheet(assessment)

        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="papercheck-assessment-{assessment.pk}.pdf"'
        )
        return response


class ScanUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(),
        allow_empty=False,
        min_length=1,
        max_length=50,
    )

    
def validate_files(self, files):
    import os
    from io import BytesIO

    from PIL import Image, UnidentifiedImageError

    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
    max_file_size = 15 * 1024 * 1024

    for file in files:
        extension = os.path.splitext(file.name)[1].lower()

        if extension not in allowed_extensions:
            raise serializers.ValidationError(
                f"{file.name}: unsupported file type."
            )

        if file.size <= 0 or file.size > max_file_size:
            raise serializers.ValidationError(
                f"{file.name}: file must be between 1 byte and 15 MB."
            )

        file.seek(0)
        header = file.read(16)
        file.seek(0)

        if extension == ".pdf":
            if not header.startswith(b"%PDF-"):
                raise serializers.ValidationError(
                    f"{file.name}: file does not appear to be a valid PDF."
                )
        else:
            try:
                image = Image.open(file)
                image.verify()
            except (UnidentifiedImageError, OSError, ValueError):
                raise serializers.ValidationError(
                    f"{file.name}: invalid or unsupported image."
                )
            finally:
                file.seek(0)

    return files


class ScanUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, assessment_id):
        assessment = get_object_or_404(
            Assessment.objects.select_related("classroom", "created_by"),
            pk=assessment_id,
        )

        user = request.user
        is_admin = user.is_superuser or user.role == "SCHOOL_ADMIN"

        if not is_admin and assessment.classroom.teacher_id != user.id:
            raise PermissionDenied(
                "You cannot upload scans for another teacher's assessment."
            )

        if assessment.status != "PUBLISHED":
            raise ValidationError(
                "Only published assessments can receive scanned answer sheets."
            )

        serializer = ScanUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        files = serializer.validated_data["files"]

        with transaction.atomic():
            job = ScanJob.objects.create(
                assessment=assessment,
                uploaded_by=user,
                status="PENDING",
                total_files=len(files),
            )

            saved_files = []

            for uploaded_file in files:
                scan_file = ScanFile(
                    scan_job=job,
                    file=uploaded_file,
                    original_filename=os.path.basename(uploaded_file.name)[:255],
                    content_type=getattr(uploaded_file, "content_type", "") or "",
                    size_bytes=uploaded_file.size,
                    status=ScanFile.Status.UPLOADED,
                )
                scan_file.save()
                saved_files.append(scan_file)

        return Response(
            {
                "message": "Files uploaded successfully.",
                "scan_job_id": str(job.id),
                "status": job.status,
                "total_files": len(saved_files),
                "files": [
                    {
                        "id": scan_file.id,
                        "filename": scan_file.original_filename,
                        "status": scan_file.status,
                    }
                    for scan_file in saved_files
                ],
            },
            status=http_status.HTTP_201_CREATED,
        )


from rest_framework import viewsets
from .serializers import ScanJobSerializer


class ScanJobViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ScanJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        queryset = ScanJob.objects.select_related(
            "assessment",
            "assessment__classroom",
            "uploaded_by",
        ).prefetch_related("files")

        if user.is_superuser or user.role == "SCHOOL_ADMIN":
            return queryset

        return queryset.filter(
            assessment__classroom__teacher=user
        )


class ScanFileProcessView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_file_id):
        user = request.user

        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        # Restrict access to this teacher's own assessment scans.
        queryset = ScanFile.objects.select_related(
            "scan_job",
            "scan_job__assessment",
            "scan_job__assessment__classroom",
        )

        if not is_admin:
            queryset = queryset.filter(
                scan_job__assessment__classroom__teacher=user
            )

        scan_file = get_object_or_404(queryset, pk=scan_file_id)
        job = scan_file.scan_job
        assessment = job.assessment

        if assessment.status != "PUBLISHED":
            raise ValidationError(
                "Only scans for published assessments can be processed."
            )

        if scan_file.status == ScanFile.Status.PROCESSING:
            raise ValidationError("This file is already being processed.")

        if scan_file.status == ScanFile.Status.COMPLETED:
            raise ValidationError("This file has already been processed.")

        extension = os.path.splitext(
            scan_file.original_filename
        )[1].lower()

        if extension == ".pdf":
            raise ValidationError(
                "PDF processing is not supported yet. Upload an image file."
            )

        if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise ValidationError("Unsupported image format.")

        # Claim the file before starting processing.
        with transaction.atomic():
            scan_file = ScanFile.objects.select_for_update().get(
                pk=scan_file.pk
            )

            if scan_file.status in {
                ScanFile.Status.PROCESSING,
                ScanFile.Status.COMPLETED,
            }:
                raise ValidationError(
                    "This file is already processing or has completed."
                )

            scan_file.status = ScanFile.Status.PROCESSING
            scan_file.error_message = ""
            scan_file.save(update_fields=["status", "error_message"])

            job.status = "PROCESSING"
            job.error_message = ""
            job.save(update_fields=["status", "error_message"])

        try:
            if not scan_file.file:
                raise ValueError("No uploaded file is attached to this scan.")

            if not os.path.isfile(scan_file.file.path):
                raise ValueError("The uploaded file could not be found.")

            detected = detect_answers(
                scan_file.file.path,
                assessment,
                page_index=0,
            )

            questions_by_id = {
                question.id: question
                for question in assessment.questions.filter(
                    question_type="MULTIPLE_CHOICE"
                )
            }

            with transaction.atomic():
                for answer in detected["answers"]:
                    question = questions_by_id.get(
                        answer["question_id"]
                    )

                    if question is None:
                        continue

                    ScanResult.objects.update_or_create(
                        scan_file=scan_file,
                        question=question,
                        defaults={
                            "selected_label": (
                                answer["selected_option"] or ""
                            ),
                            "status": answer["status"],
                            "confidence": answer["confidence"],
                            "option_details": answer["options"],
                        },
                    )

                scan_file.status = ScanFile.Status.COMPLETED
                scan_file.error_message = ""
                scan_file.save(
                    update_fields=["status", "error_message"]
                )

                self.refresh_job_status(job.id)

            return Response(
                {
                    "message": "Scan processing completed.",
                    "scan_file_id": scan_file.id,
                    "scan_job_id": str(job.id),
                    "questions_processed": detected[
                        "questions_processed"
                    ],
                    "answers": detected["answers"],
                },
                status=http_status.HTTP_200_OK,
            )

        except Exception as exc:
            # Record the failure so the teacher can troubleshoot it.
            with transaction.atomic():
                scan_file.status = ScanFile.Status.FAILED
                scan_file.error_message = str(exc)[:2000]
                scan_file.save(
                    update_fields=["status", "error_message"]
                )

                self.refresh_job_status(job.id)

            return Response(
                {
                    "message": "Scan processing failed.",
                    "scan_file_id": scan_file.id,
                    "error": str(exc),
                },
                status=http_status.HTTP_400_BAD_REQUEST,
            )

    @staticmethod
    def refresh_job_status(job_id):
        job = ScanJob.objects.select_for_update().get(pk=job_id)

        terminal_statuses = [
            ScanFile.Status.COMPLETED,
            ScanFile.Status.FAILED,
        ]

        files = job.files.all()
        finished_count = files.filter(
            status__in=terminal_statuses
        ).count()
        failed_count = files.filter(
            status=ScanFile.Status.FAILED
        ).count()

        job.processed_files = finished_count

        if finished_count >= job.total_files:
            job.status = "FAILED" if failed_count else "COMPLETED"
            job.completed_at = timezone.now()
        else:
            job.status = "PROCESSING"
            job.completed_at = None

        job.save(
            update_fields=[
                "processed_files",
                "status",
                "completed_at",
            ]
        )

class ScanFileResultsView(APIView):
    """
    Return the detected answers for one uploaded scan.
    Only the assigned teacher or a school administrator may view them.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, scan_file_id):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        queryset = ScanFile.objects.select_related(
            "scan_job",
            "scan_job__assessment",
            "scan_job__assessment__classroom",
        )

        if not is_admin:
            queryset = queryset.filter(
                scan_job__assessment__classroom__teacher=user
            )

        scan_file = get_object_or_404(
            queryset,
            pk=scan_file_id,
        )

        results = (
            ScanResult.objects
            .filter(scan_file=scan_file)
            .select_related("question")
            .prefetch_related("question__options")
            .order_by("question__order")
        )

        data = []

        for result in results:
            data.append({
                "id": result.id,
                "question_id": result.question_id,
                "question_order": result.question.order,
                "question_prompt": result.question.prompt,
                "selected_label": result.selected_label,
                "status": result.status,
                "confidence": result.confidence,
                "option_details": result.option_details,
                "reviewed": result.reviewed,
                "options": [
                    {
                        "label": option.label,
                        "text": option.text,
                    }
                    for option in result.question.options.all()
                ],
            })

        return Response({
            "scan_file_id": scan_file.id,
            "original_filename": scan_file.original_filename,
            "scan_status": scan_file.status,
            "total_results": len(data),
            "results": data,
        })


class ScanResultReviewView(APIView):
    """
    Allow an authorized teacher to confirm or correct one detected answer.

    Send:
        {"selected_label": "B"}  to select option B
        {"selected_label": ""}   to confirm a blank answer
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, scan_result_id):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        queryset = ScanResult.objects.select_related(
            "scan_file",
            "scan_file__scan_job",
            "scan_file__scan_job__assessment",
            "scan_file__scan_job__assessment__classroom",
            "question",
        )

        if not is_admin:
            queryset = queryset.filter(
                scan_file__scan_job__assessment__classroom__teacher=user
            )

        result = get_object_or_404(
            queryset,
            pk=scan_result_id,
        )

        if "selected_label" not in request.data:
            return Response(
                {
                    "message": (
                        "Include selected_label. "
                        "Use an empty string to confirm a blank answer."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_label = request.data["selected_label"]

        if not isinstance(selected_label, str):
            return Response(
                {"message": "selected_label must be a string."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_label = selected_label.strip().upper()

        valid_labels = set(
            result.question.options.values_list("label", flat=True)
        )

        if selected_label and selected_label not in valid_labels:
            return Response(
                {
                    "message": "Invalid option label for this question.",
                    "valid_labels": sorted(valid_labels),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        result.selected_label = selected_label
        result.status = (
            ScanResult.Status.DETECTED
            if selected_label
            else ScanResult.Status.BLANK
        )
        result.reviewed = True
        result.reviewed_by = user
        result.reviewed_at = timezone.now()
        result.save(
            update_fields=[
                "selected_label",
                "status",
                "reviewed",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        return Response({
            "id": result.id,
            "selected_label": result.selected_label,
            "status": result.status,
            "reviewed": True,
            "reviewed_by": user.username,
            "reviewed_at": result.reviewed_at,
        })


class ScanFileGradeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_file_id):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        queryset = ScanFile.objects.select_related(
            "scan_job",
            "scan_job__assessment",
            "scan_job__assessment__classroom",
            "matched_student",
        )

        if not is_admin:
            queryset = queryset.filter(
                scan_job__assessment__classroom__teacher=user
            )

        scan_file = get_object_or_404(queryset, pk=scan_file_id)
        assessment = scan_file.scan_job.assessment
        classroom = assessment.classroom

        if scan_file.status != ScanFile.Status.COMPLETED:
            return Response(
                {"message": "Process the scan before grading it."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student_id = str(request.data.get("student_id", "")).strip()

        if not student_id:
            return Response(
                {"message": "student_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student = get_object_or_404(
            Student,
            school=classroom.school,
            student_id=student_id,
            is_active=True,
        )

        enrolled = Enrollment.objects.filter(
            classroom=classroom,
            student=student,
            status="ENROLLED",
        ).exists()

        if not enrolled:
            return Response(
                {
                    "message": (
                        "This student is not actively enrolled "
                        "in the assessment's classroom."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            scan_file.matched_student_id
            and scan_file.matched_student_id != student.id
        ):
            return Response(
                {
                    "message": (
                        "This scan is already matched to another student. "
                        "Resolve the existing match before changing it."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        questions = list(
            assessment.questions.filter(
                question_type="MULTIPLE_CHOICE"
            ).order_by("order")
        )

        if not questions:
            return Response(
                {
                    "message": (
                        "This assessment has no multiple-choice questions "
                        "to grade with OMR."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        results_by_question = {
            result.question_id: result
            for result in ScanResult.objects.filter(
                scan_file=scan_file,
                question__assessment=assessment,
            )
        }

        missing = [
            question.order
            for question in questions
            if question.id not in results_by_question
        ]

        unreviewed = [
            question.order
            for question in questions
            if (
                question.id in results_by_question
                and not results_by_question[question.id].reviewed
            )
        ]

        if missing or unreviewed:
            return Response(
                {
                    "message": (
                        "Review every multiple-choice answer before grading."
                    ),
                    "missing_question_orders": missing,
                    "unreviewed_question_orders": unreviewed,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                locked_file = ScanFile.objects.select_for_update().get(
                    pk=scan_file.pk
                )

                if (
                    locked_file.matched_student_id
                    and locked_file.matched_student_id != student.id
                ):
                    return Response(
                        {"message": "This scan is matched to another student."},
                        status=status.HTTP_409_CONFLICT,
                    )

                submission, created = Submission.objects.get_or_create(
                    assessment=assessment,
                    student=student,
                    defaults={
                        "scan_job": scan_file.scan_job,
                        "original_file": scan_file.file.name,
                        "status": "NEEDS_REVIEW",
                    },
                )

                if not created and submission.status == "APPROVED":
                    return Response(
                        {
                            "message": (
                                "This submission is already approved. "
                                "Do not overwrite an approved grade."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                score = Decimal("0.00")
                correct_count = 0
                answer_count = 0

                for question in questions:
                    result = results_by_question[question.id]
                    selected_label = result.selected_label.strip().upper()

                    selected_option = None

                    if selected_label:
                        selected_option = QuestionOption.objects.filter(
                            question=question,
                            label__iexact=selected_label,
                        ).first()

                        if selected_option is None:
                            raise ValueError(
                                f"Invalid answer label for question "
                                f"{question.order}."
                            )

                    is_correct = bool(
                        selected_option and selected_option.is_correct
                    )

                    awarded_points = (
                        question.points
                        if is_correct
                        else Decimal("0.00")
                    )

                    StudentAnswer.objects.update_or_create(
                        submission=submission,
                        question=question,
                        defaults={
                            "selected_option": selected_option,
                            "is_correct": is_correct,
                            "awarded_points": awarded_points,
                            "review_status": "CONFIRMED",
                        },
                    )

                    score += awarded_points
                    answer_count += 1

                    if is_correct:
                        correct_count += 1

                submission.scan_job = scan_file.scan_job
                submission.original_file = scan_file.file.name
                submission.score = score
                submission.status = "NEEDS_REVIEW"
                submission.save(
                    update_fields=[
                        "scan_job",
                        "original_file",
                        "score",
                        "status",
                    ]
                )

                locked_file.matched_student = student
                locked_file.save(update_fields=["matched_student"])

            return Response(
                {
                    "message": (
                        "Answers graded successfully. "
                        "The score still requires teacher approval."
                    ),
                    "submission_id": submission.id,
                    "student_id": student.student_id,
                    "student_name": (
                        f"{student.first_name} {student.last_name}"
                    ),
                    "assessment_id": assessment.id,
                    "answers_graded": answer_count,
                    "correct_answers": correct_count,
                    "total_points_earned": str(score),
                    "status": submission.status,
                    "approved": False,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as exc:
            return Response(
                {"message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class SubmissionApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        queryset = Submission.objects.select_related(
            "assessment",
            "assessment__classroom",
            "student",
        )

        if not is_admin:
            queryset = queryset.filter(
                assessment__classroom__teacher=user
            )

        submission = get_object_or_404(
            queryset,
            pk=submission_id,
        )

        if submission.status == "APPROVED":
            return Response(
                {"message": "This submission has already been approved."},
                status=status.HTTP_409_CONFLICT,
            )

        if submission.status != "NEEDS_REVIEW":
            return Response(
                {
                    "message": (
                        "Only submissions awaiting review can be approved."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if submission.score is None:
            return Response(
                {"message": "There is no calculated score to approve."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            submission = Submission.objects.select_for_update().get(
                pk=submission.pk
            )

            # Recheck status after acquiring the database lock.
            if submission.status != "NEEDS_REVIEW":
                return Response(
                    {"message": "This submission is no longer awaiting review."},
                    status=status.HTTP_409_CONFLICT,
                )

            previous_approved_score = submission.approved_score
            final_score = submission.score

            submission.approved_score = final_score
            submission.approved_by = user
            submission.approved_at = timezone.now()
            submission.status = "APPROVED"

            submission.save(
                update_fields=[
                    "approved_score",
                    "approved_by",
                    "approved_at",
                    "status",
                ]
            )

            GradeAuditLog.objects.create(
                submission=submission,
                question=None,
                changed_by=user,
                old_score=previous_approved_score,
                new_score=final_score,
                reason="Teacher approved the submission score.",
            )

        return Response({
            "message": "Grade approved successfully.",
            "submission_id": submission.id,
            "student_id": submission.student.student_id,
            "score": str(submission.approved_score),
            "status": submission.status,
            "approved_by": user.username,
            "approved_at": submission.approved_at,
        })


class SubmissionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        queryset = Submission.objects.select_related(
            "assessment",
            "assessment__classroom",
            "student",
            "approved_by",
        )

        if not is_admin:
            queryset = queryset.filter(
                assessment__classroom__teacher=user
            )

        assessment_id = request.query_params.get("assessment_id")
        student_id = request.query_params.get("student_id")
        submission_status = request.query_params.get("status")

        if assessment_id:
            queryset = queryset.filter(
                assessment_id=assessment_id
            )

        if student_id:
            queryset = queryset.filter(
                student__student_id=student_id
            )

        if submission_status:
            valid_statuses = {
                "UPLOADED",
                "PROCESSING",
                "NEEDS_REVIEW",
                "APPROVED",
                "FAILED",
            }

            if submission_status not in valid_statuses:
                return Response(
                    {
                        "message": "Invalid status filter.",
                        "valid_statuses": sorted(valid_statuses),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(status=submission_status)

        queryset = queryset.order_by("-created_at")

        data = []

        for submission in queryset:
            student = submission.student
            assessment = submission.assessment

            data.append({
                "id": submission.id,
                "assessment_id": assessment.id,
                "assessment_title": assessment.title,
                "classroom_id": assessment.classroom_id,
                "classroom_name": assessment.classroom.name,
                "student_id": student.student_id,
                "student_name": (
                    f"{student.first_name} {student.last_name}"
                ),
                "status": submission.status,
                "calculated_score": (
                    str(submission.score)
                    if submission.score is not None
                    else None
                ),
                "approved_score": (
                    str(submission.approved_score)
                    if submission.approved_score is not None
                    else None
                ),
                "approved_by": (
                    submission.approved_by.username
                    if submission.approved_by
                    else None
                ),
                "approved_at": submission.approved_at,
                "created_at": submission.created_at,
            })

        return Response({
            "count": len(data),
            "results": data,
        })


class SubmissionAuditHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        user = request.user
        is_admin = (
            user.is_superuser
            or user.role == "SCHOOL_ADMIN"
        )

        submissions = Submission.objects.select_related(
            "assessment",
            "assessment__classroom",
            "student",
        )

        if not is_admin:
            submissions = submissions.filter(
                assessment__classroom__teacher=user
            )

        submission = get_object_or_404(
            submissions,
            pk=submission_id,
        )

        logs = (
            GradeAuditLog.objects
            .filter(submission=submission)
            .select_related("changed_by", "question")
            .order_by("-created_at")
        )

        history = []

        for log in logs:
            history.append({
                "id": log.id,
                "question_id": log.question_id,
                "question_order": (
                    log.question.order if log.question else None
                ),
                "changed_by": log.changed_by.username,
                "old_score": (
                    str(log.old_score)
                    if log.old_score is not None
                    else None
                ),
                "new_score": (
                    str(log.new_score)
                    if log.new_score is not None
                    else None
                ),
                "reason": log.reason,
                "created_at": log.created_at,
            })

        return Response({
            "submission_id": submission.id,
            "student_id": submission.student.student_id,
            "student_name": (
                f"{submission.student.first_name} "
                f"{submission.student.last_name}"
            ),
            "assessment_title": submission.assessment.title,
            "current_status": submission.status,
            "current_score": (
                str(submission.approved_score)
                if submission.approved_score is not None
                else (
                    str(submission.score)
                    if submission.score is not None
                    else None
                )
            ),
            "history_count": len(history),
            "history": history,
        })

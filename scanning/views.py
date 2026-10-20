from decimal import Decimal

import math
import os
import tempfile

import pymupdf  # PyMuPDF

from .layout import QUESTIONS_PER_PAGE

from django.shortcuts import render

from .omr import detect_answers, detect_student_id
from .matching import find_student_by_id
from .preview import render_marked_sheet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from schools.models import Enrollment, Student
from grading.models import Submission, GradeAuditLog, StudentAnswer

from .omr import detect_answers, detect_student_id
from .matching import find_student_by_id
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
                        f"{file.name}: invalid PDF file."
                    )
            else:
                try:
                    image = Image.open(file)
                    image.verify()
                except (
                    UnidentifiedImageError,
                    OSError,
                    ValueError,
                ):
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
        if not serializer.is_valid():
            print("UPLOAD ERRORS:", serializer.errors)
            print("FILES RECEIVED:", [(f.name, f.size, f.content_type) for f in request.FILES.getlist("files")])
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
        is_admin = user.is_superuser or user.role == "SCHOOL_ADMIN"

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

        if scan_file.status in {
            ScanFile.Status.PROCESSING,
            ScanFile.Status.COMPLETED,
        }:
            raise ValidationError(
                "This file is already processing or has completed."
            )

        if not scan_file.file:
            raise ValidationError("No uploaded file is attached to this scan.")

        extension = os.path.splitext(scan_file.original_filename)[1].lower()

        if extension not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
            raise ValidationError("Unsupported file format.")

        questions = list(
            assessment.questions.filter(
                question_type="MULTIPLE_CHOICE"
            )
            .prefetch_related("options")
            .order_by("order")
        )

        if not questions:
            raise ValidationError(
                "This assessment has no multiple-choice questions to scan."
            )

        expected_pages = max(
            1,
            math.ceil(len(questions) / QUESTIONS_PER_PAGE),
        )

        # Claim the file before starting CPU-intensive processing.
        with transaction.atomic():
            locked_file = ScanFile.objects.select_for_update().get(
                pk=scan_file.pk
            )

            if locked_file.status in {
                ScanFile.Status.PROCESSING,
                ScanFile.Status.COMPLETED,
            }:
                raise ValidationError(
                    "This file is already processing or has completed."
                )

            locked_file.status = ScanFile.Status.PROCESSING
            locked_file.error_message = ""
            locked_file.save(
                update_fields=["status", "error_message"]
            )

            ScanJob.objects.filter(pk=job.pk).update(
                status=ScanJob.Status.PROCESSING,
                error_message="",
                completed_at=None,
            )

        try:
            source_path = scan_file.file.path

            if not os.path.isfile(source_path):
                raise ValueError("The uploaded file could not be found.")

            # --------------------------------------------------
            # 1. PREPARE PAGE IMAGES
            # --------------------------------------------------
            # Image uploads represent a single page. Multi-page
            # assessments must be uploaded as one PDF.
            with tempfile.TemporaryDirectory(prefix="papercheck_omr_") as temp_dir:
                page_paths = []

                if extension == ".pdf":
                    with pymupdf.open(source_path) as pdf_document:
                        if pdf_document.needs_pass:
                            raise ValueError(
                                "Password-protected PDFs are not supported."
                            )

                        if len(pdf_document) != expected_pages:
                            raise ValueError(
                                f"This assessment requires {expected_pages} "
                                f"page(s), but the uploaded PDF contains "
                                f"{len(pdf_document)} page(s). Upload the "
                                f"complete answer sheet as one PDF."
                            )

                        # Render at 2x PDF resolution for reliable bubble
                        # detection while keeping temporary files isolated.
                        render_matrix = pymupdf.Matrix(2, 2)

                        for page_index, page in enumerate(pdf_document):
                            pixmap = page.get_pixmap(
                                matrix=render_matrix,
                                alpha=False,
                            )
                            page_path = os.path.join(
                                temp_dir,
                                f"page_{page_index + 1}.png",
                            )
                            pixmap.save(page_path)
                            page_paths.append(page_path)
                else:
                    if expected_pages > 1:
                        raise ValueError(
                            f"This assessment needs {expected_pages} pages. "
                            "Upload all pages together as one PDF instead "
                            "of uploading a single image."
                        )

                    page_paths = [source_path]

                if len(page_paths) != expected_pages:
                    raise ValueError(
                        "The number of uploaded pages does not match "
                        "the assessment's answer sheet."
                    )

                # --------------------------------------------------
                # 2. DETECT STUDENT ID FROM THE FIRST PAGE
                # --------------------------------------------------
                student_id_detection = detect_student_id(page_paths[0])

                detected_student_id = str(
                    student_id_detection.get("student_id") or ""
                ).strip()

                student_id_complete = bool(
                    student_id_detection.get("complete", False)
                )

                suggested_student = None

                if student_id_complete and detected_student_id:
                    suggested_student = find_student_by_id(
                        assessment,
                        detected_student_id,
                    )

                # --------------------------------------------------
                # 3. DETECT ANSWERS ON EVERY PAGE
                # --------------------------------------------------
                all_answers = []
                total_questions_processed = 0

                for page_index, page_path in enumerate(page_paths):
                    page_result = detect_answers(
                        page_path,
                        assessment,
                        page_index=page_index,
                    )

                    total_questions_processed += page_result[
                        "questions_processed"
                    ]

                    for answer in page_result["answers"]:
                        answer_with_page = dict(answer)
                        answer_with_page["page_index"] = page_index
                        all_answers.append(answer_with_page)

                # --------------------------------------------------
                # 4. SAVE THE COMBINED RESULTS
                # --------------------------------------------------
                questions_by_id = {
                    question.id: question for question in questions
                }

                detected_question_ids = {
                    answer["question_id"] for answer in all_answers
                }

                expected_question_ids = {
                    question.id for question in questions
                }

                missing_question_ids = (
                    expected_question_ids - detected_question_ids
                )

                if missing_question_ids:
                    missing_orders = [
                        question.order
                        for question in questions
                        if question.id in missing_question_ids
                    ]
                    raise ValueError(
                        "OMR detection did not return every question. "
                        f"Missing question numbers: {missing_orders}. "
                        "Check the page alignment and scan quality."
                    )

                with transaction.atomic():
                    locked_file = ScanFile.objects.select_for_update().get(
                        pk=scan_file.pk
                    )

                    # A failed earlier attempt may have left partial results.
                    # Replace them only after all pages have been detected.
                    ScanResult.objects.filter(
                        scan_file=locked_file
                    ).delete()

                    for answer in all_answers:
                        question = questions_by_id.get(
                            answer["question_id"]
                        )

                        if question is None:
                            continue

                        ScanResult.objects.create(
                            scan_file=locked_file,
                            question=question,
                            selected_label=(
                                answer.get("selected_option") or ""
                            ),
                            status=answer["status"],
                            confidence=answer["confidence"],
                            option_details=answer["options"],
                        )

                    locked_file.detected_student_id = detected_student_id
                    locked_file.matched_student = suggested_student
                    locked_file.status = ScanFile.Status.COMPLETED
                    locked_file.error_message = ""
                    locked_file.save(
                        update_fields=[
                            "detected_student_id",
                            "matched_student",
                            "status",
                            "error_message",
                        ]
                    )

                    self.refresh_job_status(job.id)

            # --------------------------------------------------
            # 5. RETURN COMBINED RESULTS
            # --------------------------------------------------
            return Response(
                {
                    "message": "Scan processing completed.",
                    "scan_file_id": scan_file.id,
                    "scan_job_id": str(job.id),
                    "page_count": expected_pages,
                    "questions_processed": total_questions_processed,
                    "answers": all_answers,
                    "detected_student_id": detected_student_id,
                    "student_id_complete": student_id_complete,
                    "student_id_digits": student_id_detection.get(
                        "digits", []
                    ),
                    "suggested_student": (
                        {
                            "id": suggested_student.id,
                            "student_id": suggested_student.student_id,
                            "name": (
                                f"{suggested_student.first_name} "
                                f"{suggested_student.last_name}"
                            ),
                        }
                        if suggested_student
                        else None
                    ),
                },
                status=http_status.HTTP_200_OK,
            )

        except Exception as exc:
            with transaction.atomic():
                failed_file = ScanFile.objects.select_for_update().get(
                    pk=scan_file.pk
                )
                failed_file.status = ScanFile.Status.FAILED
                failed_file.error_message = str(exc)[:2000]
                failed_file.save(
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

        finished_count = job.files.filter(
            status__in=terminal_statuses
        ).count()

        failed_count = job.files.filter(
            status=ScanFile.Status.FAILED
        ).count()

        job.processed_files = finished_count

        if finished_count >= job.total_files:
            job.status = (
                ScanJob.Status.FAILED
                if failed_count
                else ScanJob.Status.COMPLETED
            )
            job.completed_at = timezone.now()
        else:
            job.status = ScanJob.Status.PROCESSING
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

        unreviewed = [item for item in data if not item["reviewed"]]
        needs_attention = [
            item for item in unreviewed if item["status"] != "DETECTED"
        ]

        suggested = find_student_by_id(
            scan_file.scan_job.assessment,
            scan_file.detected_student_id,
        )

        return Response({
            "scan_file_id": scan_file.id,
            "original_filename": scan_file.original_filename,
            "scan_status": scan_file.status,
            "detected_student_id": scan_file.detected_student_id,
            "matched_student_id": scan_file.matched_student_id,
            "suggested_student": (
                {
                    "student_id": suggested.student_id,
                    "name": f"{suggested.first_name} {suggested.last_name}",
                }
                if suggested
                else None
            ),
            "total_results": len(data),
            "unreviewed_count": len(unreviewed),
            "needs_attention_count": len(needs_attention),
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

class ScanFileConfirmDetectedView(APIView):
    """
    Mark every cleanly detected answer as reviewed in one call.
    Blank, multiple-mark, and uncertain answers stay unreviewed so the
    teacher must resolve them individually.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, scan_file_id):
        user = request.user
        is_admin = user.is_superuser or user.role == "SCHOOL_ADMIN"

        queryset = ScanFile.objects.all()

        if not is_admin:
            queryset = queryset.filter(
                scan_job__assessment__classroom__teacher=user
            )

        scan_file = get_object_or_404(queryset, pk=scan_file_id)

        if scan_file.status != ScanFile.Status.COMPLETED:
            return Response(
                {"message": "Process the scan before reviewing it."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        confirmed = ScanResult.objects.filter(
            scan_file=scan_file,
            status=ScanResult.Status.DETECTED,
            reviewed=False,
        ).update(
            reviewed=True,
            reviewed_by=user,
            reviewed_at=timezone.now(),
        )

        remaining = ScanResult.objects.filter(
            scan_file=scan_file,
            reviewed=False,
        ).count()

        return Response({
            "confirmed": confirmed,
            "needs_attention_count": remaining,
        })

class ScanFilePreviewView(APIView):
    """Return the scanned sheet as a JPEG marked with right and wrong answers."""
    permission_classes = [IsAuthenticated]

    def get(self, request, scan_file_id):
        user = request.user
        is_admin = user.is_superuser or user.role == "SCHOOL_ADMIN"

        queryset = ScanFile.objects.select_related(
            "scan_job", "scan_job__assessment"
        )

        if not is_admin:
            queryset = queryset.filter(
                scan_job__assessment__classroom__teacher=user
            )

        scan_file = get_object_or_404(queryset, pk=scan_file_id)

        if scan_file.status != ScanFile.Status.COMPLETED:
            return Response(
                {"message": "Process the scan before previewing it."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not scan_file.file or not os.path.isfile(scan_file.file.path):
            return Response(
                {"message": "The uploaded file could not be found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        results_by_question = {
            result.question_id: result
            for result in ScanResult.objects.filter(scan_file=scan_file)
        }

        try:
            jpeg = render_marked_sheet(
                scan_file.file.path,
                scan_file.scan_job.assessment,
                results_by_question,
            )
        except ValueError as exc:
            return Response(
                {"message": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return HttpResponse(jpeg, content_type="image/jpeg")

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
                    "total_points_possible": str(
                        sum(question.points for question in questions)
                    ),
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

from django.conf import settings
from django.db import models


class Submission(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        PROCESSING = "PROCESSING", "Processing"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"
        APPROVED = "APPROVED", "Approved"
        FAILED = "FAILED", "Failed"

    assessment = models.ForeignKey(
        "assessments.Assessment",
        on_delete=models.PROTECT,
        related_name="submissions",
    )
    student = models.ForeignKey(
        "schools.Student",
        on_delete=models.PROTECT,
        related_name="submissions",
    )
    scan_job = models.ForeignKey(
        "scanning.ScanJob",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    original_file = models.ImageField(
        upload_to="scans/original/%Y/%m/",
    )
    status = models.CharField(
        max_length=15,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    score = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    approved_score = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_submissions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"],
                name="unique_submission_per_student_assessment",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.assessment.title}"


class StudentAnswer(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        CORRECTED = "CORRECTED", "Corrected"

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        "assessments.Question",
        on_delete=models.PROTECT,
        related_name="student_answers",
    )
    selected_option = models.ForeignKey(
        "assessments.QuestionOption",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_answers",
    )
    extracted_text = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    is_correct = models.BooleanField(null=True, blank=True)
    awarded_points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    review_status = models.CharField(
        max_length=10,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "question"],
                name="unique_answer_per_submission_question",
            )
        ]

    def __str__(self):
        return f"{self.submission} - Q{self.question.order}"


class GradeAuditLog(models.Model):
    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="grade_audit_logs",
    )
    question = models.ForeignKey(
        "assessments.Question",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    old_score = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    new_score = models.DecimalField(
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Grade change - {self.submission_id}"
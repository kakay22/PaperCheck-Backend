import uuid

from django.conf import settings
from django.db import models


class ScanJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    assessment = models.ForeignKey(
        "assessments.Assessment",
        on_delete=models.PROTECT,
        related_name="scan_jobs",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="scan_jobs",
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_files = models.PositiveIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Scan {self.id} - {self.status}"

class ScanFile(models.Model):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Review"
        FAILED = "FAILED", "Failed"

    scan_job = models.ForeignKey(
        "scanning.ScanJob",
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.FileField(upload_to="scans/uploads/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    matched_student = models.ForeignKey(
        "schools.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_files",
    )

    matched_student = models.ForeignKey(
        "schools.Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scan_files",
    )
    detected_student_id = models.CharField(max_length=50, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"

class ScanResult(models.Model):
    class Status(models.TextChoices):
        DETECTED = "DETECTED", "Detected"
        BLANK = "BLANK", "Blank"
        MULTIPLE_MARKS = "MULTIPLE_MARKS", "Multiple Marks"
        UNCERTAIN = "UNCERTAIN", "Uncertain"
        ERROR = "ERROR", "Error"

    scan_file = models.ForeignKey(
        "scanning.ScanFile",
        on_delete=models.CASCADE,
        related_name="results",
    )
    question = models.ForeignKey(
        "assessments.Question",
        on_delete=models.CASCADE,
        related_name="scan_results",
    )
    selected_label = models.CharField(max_length=10, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNCERTAIN,
    )
    confidence = models.FloatField(null=True, blank=True)
    option_details = models.JSONField(default=list, blank=True)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_scan_results",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["question__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["scan_file", "question"],
                name="unique_scan_result_per_question",
            )
        ]

    def __str__(self):
        return f"Scan {self.scan_file_id} - Question {self.question_id}"

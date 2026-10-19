from django.contrib import admin
from .models import Submission, StudentAnswer, GradeAuditLog


class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "assessment",
        "status",
        "score",
        "approved_score",
        "created_at",
    )
    list_filter = ("status", "assessment")
    search_fields = ("student__student_id", "student__last_name")
    inlines = [StudentAnswerInline]


@admin.register(GradeAuditLog)
class GradeAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "submission",
        "question",
        "changed_by",
        "old_score",
        "new_score",
        "created_at",
    )
    list_filter = ("created_at",)
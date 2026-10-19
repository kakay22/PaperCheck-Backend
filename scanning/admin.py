from django.contrib import admin
from .models import ScanJob, ScanFile, ScanResult


@admin.register(ScanJob)
class ScanJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "assessment",
        "uploaded_by",
        "status",
        "total_files",
        "processed_files",
        "created_at",
    )
    list_filter = ("status",)

@admin.register(ScanFile)
class ScanFileAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "scan_job",
        "status",
        "size_bytes",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("original_filename", "scan_job__id")
    readonly_fields = ("created_at", "size_bytes")

@admin.register(ScanResult)
class ScanResultAdmin(admin.ModelAdmin):
    list_display = (
        "scan_file",
        "question",
        "selected_label",
        "status",
        "confidence",
        "reviewed",
    )
    list_filter = ("status", "reviewed")
    search_fields = ("scan_file__original_filename", "question__prompt")

from rest_framework import serializers

from .models import ScanJob, ScanFile


class ScanFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScanFile
        fields = [
            "id",
            "original_filename",
            "content_type",
            "size_bytes",
            "status",
            "error_message",
            "created_at",
        ]
        read_only_fields = fields


class ScanJobSerializer(serializers.ModelSerializer):
    files = ScanFileSerializer(many=True, read_only=True)
    assessment_title = serializers.CharField(
        source="assessment.title",
        read_only=True,
    )
    uploaded_by_username = serializers.CharField(
        source="uploaded_by.username",
        read_only=True,
    )

    class Meta:
        model = ScanJob
        fields = [
            "id",
            "assessment",
            "assessment_title",
            "uploaded_by_username",
            "status",
            "total_files",
            "processed_files",
            "error_message",
            "created_at",
            "completed_at",
            "files",
        ]
        read_only_fields = fields

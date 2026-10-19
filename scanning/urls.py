
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ScanFileProcessView, ScanFileResultsView, ScanResultReviewView, ScanFileGradeView, SubmissionApproveView, SubmissionListView, SubmissionAuditHistoryView

from .views import (
    AnswerSheetDownloadView,
    ScanUploadView,
    ScanJobViewSet,
)

router = DefaultRouter()
router.register("scan-jobs", ScanJobViewSet, basename="scan-job")

urlpatterns = [
    path(
        "assessments/<int:assessment_id>/answer-sheet/",
        AnswerSheetDownloadView.as_view(),
        name="answer-sheet-download",
    ),
    path(
        "assessments/<int:assessment_id>/scan-uploads/",
        ScanUploadView.as_view(),
        name="scan-upload",
    ),

    path(
        "scan-files/<int:scan_file_id>/process/",
        ScanFileProcessView.as_view(),
        name="scan-file-process",
    ),

    path(
        "scan-files/<int:scan_file_id>/results/",
        ScanFileResultsView.as_view(),
        name="scan-file-results",
    ),
    path(
        "scan-results/<int:scan_result_id>/review/",
        ScanResultReviewView.as_view(),
        name="scan-result-review",
    ),

    path(
        "scan-files/<int:scan_file_id>/grade/",
        ScanFileGradeView.as_view(),
        name="scan-file-grade",
    ),

    path(
        "submissions/<int:submission_id>/approve/",
        SubmissionApproveView.as_view(),
        name="submission-approve",
    ),

    path(
        "submissions/",
        SubmissionListView.as_view(),
        name="submission-list",
    ),
    path(
        "submissions/<int:submission_id>/audit-history/",
        SubmissionAuditHistoryView.as_view(),
        name="submission-audit-history",
    ),
]
